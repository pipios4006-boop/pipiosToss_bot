# =====================================================================
# 파일명: quant_engine.py
# 목적: 5분봉 HA 100% 벡터화 연산 및 5일/당일 세션 체력 진폭 산출 엔진
# =====================================================================

import os
import json
import asyncio
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from toss_api import GlobalThrottle

class HAStateManager:
    FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ha_state.json")

    # MODIFIED: is_trailing_active 상태 락온 추가 (8-Tier 반환)
    @classmethod
    async def get_state(cls) -> tuple[float, int, float, str, bool, bool, bool]:
        async with GlobalThrottle.get_file_lock(cls.FILE_PATH):
            def _read():
                if not os.path.exists(cls.FILE_PATH):
                    return 0.0, 10, 0.0, "", False, True, False
                try:
                    with open(cls.FILE_PATH, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        last_price = float(data.get("last_buy_price", 0.0))
                        target_qty = int(data.get("target_qty", 10))
                        target_sell_price = float(data.get("target_sell_price", 0.0))
                        last_session_id = str(data.get("last_session_id", ""))
                        is_session_done = bool(data.get("is_session_done", False))
                        is_active = bool(data.get("is_active", True))
                        is_trailing_active = bool(data.get("is_trailing_active", False))
                        return last_price, target_qty, target_sell_price, last_session_id, is_session_done, is_active, is_trailing_active
                except Exception:
                    return 0.0, 10, 0.0, "", False, True, False
            return await asyncio.to_thread(_read)

    # MODIFIED: is_trailing_active 원자적 쓰기 병합
    @classmethod
    async def save_state(cls, price: float = None, target_qty: int = None, target_sell_price: float = None, last_session_id: str = None, is_session_done: bool = None, is_active: bool = None, is_trailing_active: bool = None):
        async with GlobalThrottle.get_file_lock(cls.FILE_PATH):
            def _write():
                data = {}
                if os.path.exists(cls.FILE_PATH):
                    try:
                        with open(cls.FILE_PATH, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except Exception:
                        pass
                
                if price is not None:
                    data["last_buy_price"] = price
                if target_qty is not None:
                    data["target_qty"] = target_qty
                if target_sell_price is not None:
                    data["target_sell_price"] = target_sell_price
                if last_session_id is not None:
                    data["last_session_id"] = last_session_id
                if is_session_done is not None:
                    data["is_session_done"] = is_session_done
                if is_active is not None:
                    data["is_active"] = is_active
                if is_trailing_active is not None:
                    data["is_trailing_active"] = is_trailing_active
                
                tmp_path = cls.FILE_PATH + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                os.replace(tmp_path, cls.FILE_PATH)
            await asyncio.to_thread(_write)

    @classmethod
    async def get_session_state(cls) -> tuple[str, float, float]:
        async with GlobalThrottle.get_file_lock(cls.FILE_PATH):
            def _read():
                if not os.path.exists(cls.FILE_PATH):
                    return "", 0.0, 0.0
                try:
                    with open(cls.FILE_PATH, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        return str(data.get("session_id", "")), float(data.get("session_high", 0.0)), float(data.get("session_low", 0.0))
                except Exception:
                    return "", 0.0, 0.0
            return await asyncio.to_thread(_read)

    @classmethod
    async def save_session_state(cls, session_id: str, session_high: float, session_low: float):
        async with GlobalThrottle.get_file_lock(cls.FILE_PATH):
            def _write():
                data = {}
                if os.path.exists(cls.FILE_PATH):
                    try:
                        with open(cls.FILE_PATH, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except Exception:
                        pass
                
                data["session_id"] = session_id
                data["session_high"] = session_high
                data["session_low"] = session_low
                
                tmp_path = cls.FILE_PATH + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                os.replace(tmp_path, cls.FILE_PATH)
            await asyncio.to_thread(_write)

class HeikinAshiEngine:
    @staticmethod
    def calculate_5m_ha(candles_json: list) -> pd.DataFrame:
        if not candles_json:
            return pd.DataFrame()
            
        df = pd.DataFrame(candles_json)
        
        df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601')
        df['timestamp'] = df['timestamp'].dt.tz_convert(ZoneInfo('America/New_York'))
        df.set_index('timestamp', inplace=True)
        df.sort_index(ascending=True, inplace=True)
        
        for col in ['openPrice', 'highPrice', 'lowPrice', 'closePrice', 'volume']:
            df[col] = df[col].astype(float)
            
        df_5m = df.resample('5min', label='left', closed='left').agg({
            'openPrice': 'first',
            'highPrice': 'max',
            'lowPrice': 'min',
            'closePrice': 'last',
            'volume': 'sum'
        }).ffill()
        
        ha_df = pd.DataFrame(index=df_5m.index)
        
        ha_df['HA_Close'] = (df_5m['openPrice'] + df_5m['highPrice'] + df_5m['lowPrice'] + df_5m['closePrice']) / 4.0
        
        shifted_ha_close = ha_df['HA_Close'].shift(1)
        shifted_ha_close.iloc[0] = (df_5m['openPrice'].iloc[0] + df_5m['closePrice'].iloc[0]) / 2.0
        ha_df['HA_Open'] = shifted_ha_close.ewm(alpha=0.5, adjust=False).mean()
        
        ha_df['HA_High'] = pd.concat([df_5m['highPrice'], ha_df['HA_Open'], ha_df['HA_Close']], axis=1).max(axis=1)
        ha_df['HA_Low'] = pd.concat([df_5m['lowPrice'], ha_df['HA_Open'], ha_df['HA_Close']], axis=1).min(axis=1)
        ha_df['Volume'] = df_5m['volume']
        
        ha_df['EMA_5'] = ha_df['HA_Close'].ewm(span=5, adjust=False).mean()
        ha_df['EMA_10'] = ha_df['HA_Close'].ewm(span=10, adjust=False).mean()
        
        return ha_df.sort_index(ascending=True)

    @staticmethod
    def calculate_amplitude_stamina(daily_candles_json: list) -> float:
        if not daily_candles_json or len(daily_candles_json) < 2:
            return 0.0
            
        df = pd.DataFrame(daily_candles_json)
        for col in ['highPrice', 'lowPrice']:
            df[col] = df[col].astype(float)
            
        df = df.iloc[:-1]
        df = df.tail(5)
        df['amplitude'] = (df['highPrice'] - df['lowPrice']) / df['lowPrice']
        
        return float(df['amplitude'].mean())

    @staticmethod
    async def get_dynamic_session_amp(session_start_est: datetime, session_name: str, session_candles: pd.DataFrame) -> float:
        if session_candles.empty:
            return 0.0

        current_window_high = float(session_candles['HA_High'].max())
        current_window_low = float(session_candles['HA_Low'].min())
        
        session_id = f"{session_start_est.strftime('%Y%m%d')}_{session_name}"
        
        saved_id, saved_high, saved_low = await HAStateManager.get_session_state()
        
        if saved_id != session_id:
            session_high = current_window_high
            session_low = current_window_low
        else:
            session_high = max(saved_high, current_window_high)
            session_low = min(saved_low, current_window_low) if saved_low > 0 else current_window_low
            
        await HAStateManager.save_session_state(session_id, session_high, session_low)
        
        if session_low > 0:
            return float((session_high - session_low) / session_low)
        return 0.0

    @staticmethod
    def calculate_volatility_bands(session_high: float, session_low: float, current_price: float, avg_stamina: float, entry_price: float) -> tuple[float, float, float, float]:
        if session_low <= 0.0 or session_high <= 0.0 or avg_stamina <= 0.0 or current_price <= 0.0:
            return 0.0, 0.0, 0.0, 0.0
            
        raw_ceiling = session_low * (1.0 + avg_stamina)
        raw_floor = session_high * (1.0 - avg_stamina)
        
        ceiling = max(current_price, raw_ceiling)
        floor = min(current_price, raw_floor)
        
        anchor_price = entry_price if entry_price > 0.0 else current_price
        
        if anchor_price > 0.0:
            max_profit_pct = (ceiling / anchor_price - 1.0) * 100.0
            max_loss_pct = (floor / anchor_price - 1.0) * 100.0
        else:
            max_profit_pct = 0.0
            max_loss_pct = 0.0
            
        return ceiling, floor, max_profit_pct, max_loss_pct
