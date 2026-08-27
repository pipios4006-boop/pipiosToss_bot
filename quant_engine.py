# =====================================================================
# 파일명: quant_engine.py
# 목적: 3분봉 HA 100% 벡터화 연산 (EMA 장세 필터 탑재) 및 상태 장부(JSON) 원자적 쓰기 엔진
# =====================================================================

import os
import json
import asyncio
import pandas as pd
from zoneinfo import ZoneInfo
from toss_api import GlobalThrottle

class HAStateManager:
    FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ha_state.json")

    @classmethod
    async def get_state(cls) -> tuple[float, int]:
        async with GlobalThrottle.get_file_lock(cls.FILE_PATH):
            def _read():
                # MODIFIED: Rule 4 파라미터 완전 소각. 오직 단가와 수량만 관리.
                if not os.path.exists(cls.FILE_PATH):
                    return 0.0, 10
                try:
                    with open(cls.FILE_PATH, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        last_price = float(data.get("last_buy_price", 0.0))
                        target_qty = int(data.get("target_qty", 10))
                        return last_price, target_qty
                except Exception:
                    return 0.0, 10
            return await asyncio.to_thread(_read)

    @classmethod
    async def save_state(cls, price: float = None, target_qty: int = None):
        async with GlobalThrottle.get_file_lock(cls.FILE_PATH):
            def _write():
                curr_price = 0.0
                curr_qty = 10
                
                if os.path.exists(cls.FILE_PATH):
                    try:
                        with open(cls.FILE_PATH, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            curr_price = float(data.get("last_buy_price", 0.0))
                            curr_qty = int(data.get("target_qty", 10))
                    except Exception:
                        pass
                
                new_price = curr_price if price is None else price
                new_qty = curr_qty if target_qty is None else target_qty
                
                tmp_path = cls.FILE_PATH + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "last_buy_price": new_price, 
                        "target_qty": new_qty
                    }, f)
                # 원자적 덮어쓰기
                os.replace(tmp_path, cls.FILE_PATH)
            await asyncio.to_thread(_write)

class HeikinAshiEngine:
    @staticmethod
    def calculate_3m_ha(candles_json: list) -> pd.DataFrame:
        if not candles_json:
            return pd.DataFrame()
            
        df = pd.DataFrame(candles_json)
        
        df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601')
        df['timestamp'] = df['timestamp'].dt.tz_convert(ZoneInfo('America/New_York'))
        df.set_index('timestamp', inplace=True)
        df.sort_index(ascending=True, inplace=True)
        
        for col in ['openPrice', 'highPrice', 'lowPrice', 'closePrice', 'volume']:
            df[col] = df[col].astype(float)
            
        df_3m = df.resample('3min', label='left', closed='left').agg({
            'openPrice': 'first',
            'highPrice': 'max',
            'lowPrice': 'min',
            'closePrice': 'last',
            'volume': 'sum'
        }).ffill()
        
        ha_df = pd.DataFrame(index=df_3m.index)
        
        ha_df['HA_Close'] = (df_3m['openPrice'] + df_3m['highPrice'] + df_3m['lowPrice'] + df_3m['closePrice']) / 4.0
        
        shifted_ha_close = ha_df['HA_Close'].shift(1)
        shifted_ha_close.iloc[0] = (df_3m['openPrice'].iloc[0] + df_3m['closePrice'].iloc[0]) / 2.0
        ha_df['HA_Open'] = shifted_ha_close.ewm(alpha=0.5, adjust=False).mean()
        
        ha_df['HA_High'] = pd.concat([df_3m['highPrice'], ha_df['HA_Open'], ha_df['HA_Close']], axis=1).max(axis=1)
        ha_df['HA_Low'] = pd.concat([df_3m['lowPrice'], ha_df['HA_Open'], ha_df['HA_Close']], axis=1).min(axis=1)
        ha_df['Volume'] = df_3m['volume']
        
        # NEW: 거시적 장세(Macro Trend) 판별을 위한 EMA 10/20 지수이동평균선 벡터화 섀도우 렌더링
        ha_df['EMA_10'] = ha_df['HA_Close'].ewm(span=10, adjust=False).mean()
        ha_df['EMA_20'] = ha_df['HA_Close'].ewm(span=20, adjust=False).mean()
        
        return ha_df.sort_index(ascending=True)
