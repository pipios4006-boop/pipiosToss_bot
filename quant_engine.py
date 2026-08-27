# =====================================================================
# 파일명: quant_engine.py
# 목적: 3분봉 HA 100% 벡터화 연산 및 상태 장부(JSON) 원자적 쓰기 엔진
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
    async def get_state(cls) -> tuple[float, int, float, bool]:
        async with GlobalThrottle.get_file_lock(cls.FILE_PATH):
            def _read():
                # MODIFIED: Rule 4 파라미터 (reference_buy_price, rule4_shield_active) 추가 반환
                if not os.path.exists(cls.FILE_PATH):
                    return 0.0, 10, 0.0, True
                try:
                    with open(cls.FILE_PATH, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        last_price = float(data.get("last_buy_price", 0.0))
                        target_qty = int(data.get("target_qty", 10))
                        ref_price = float(data.get("reference_buy_price", 0.0))
                        shield = bool(data.get("rule4_shield_active", True))
                        return last_price, target_qty, ref_price, shield
                except Exception:
                    return 0.0, 10, 0.0, True
            return await asyncio.to_thread(_read)

    @classmethod
    async def save_state(cls, price: float = None, target_qty: int = None, reference_buy_price: float = None, rule4_shield_active: bool = None):
        async with GlobalThrottle.get_file_lock(cls.FILE_PATH):
            def _write():
                curr_price = 0.0
                curr_qty = 10
                curr_ref = 0.0
                curr_shield = True
                
                # 기존 데이터 병합 (None인 파라미터는 기존 상태 유지)
                if os.path.exists(cls.FILE_PATH):
                    try:
                        with open(cls.FILE_PATH, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            curr_price = float(data.get("last_buy_price", 0.0))
                            curr_qty = int(data.get("target_qty", 10))
                            curr_ref = float(data.get("reference_buy_price", 0.0))
                            curr_shield = bool(data.get("rule4_shield_active", True))
                    except Exception:
                        pass
                
                new_price = curr_price if price is None else price
                new_qty = curr_qty if target_qty is None else target_qty
                new_ref = curr_ref if reference_buy_price is None else reference_buy_price
                new_shield = curr_shield if rule4_shield_active is None else rule4_shield_active
                
                tmp_path = cls.FILE_PATH + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "last_buy_price": new_price, 
                        "target_qty": new_qty,
                        "reference_buy_price": new_ref,
                        "rule4_shield_active": new_shield
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
        
        return ha_df.sort_index(ascending=True)
