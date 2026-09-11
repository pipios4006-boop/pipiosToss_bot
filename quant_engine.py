# =====================================================================
# FILE: quant_engine.py
# 목적: SOXL, SOXS 듀얼 장부 격리 및 세션별 aVWAP 연산 엔진 (I/O 통제 결속)
# =====================================================================
# MODIFIED: 초과 Case 44 - 오버나이트 로직 전면 소각 및 수동 통제 위임
# MODIFIED: 3단 하향망 로직 전면 소각 (1.0% 고정 락온) 및 관련 플래그 증발
# NEW: 초과 Case 55 - 듀얼 휩소 동시 진입 방어를 위한 180초 교차 타임쉴드 원자적 장부 필드(entry_time) 증축

import os
import json
import pandas as pd
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from toss_api import GlobalThrottle

class AssassinLedger:
    @classmethod
    def _get_file_path(cls, symbol: str) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), f"AssassinLedger_{symbol}.json")

    @classmethod
    async def get_state(cls, symbol: str) -> tuple[float, float, str, bool, bool, float, str, str, str, float]:
        filepath = cls._get_file_path(symbol)
        async with GlobalThrottle.get_file_lock(filepath):
            def _read():
                if not os.path.exists(filepath):
                    return 0.0, 100.0, "", False, True, 0.0, "", "PRE_ONLY", "", 0.0
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        return (
                            float(data.get("last_buy_price", 0.0)),
                            float(data.get("budget", 100.0)),
                            str(data.get("last_session_id", "")),
                            bool(data.get("is_session_done", False)),
                            bool(data.get("is_active", True)),
                            float(data.get("target_sell_price", 0.0)),
                            str(data.get("cond_order_id", "")),
                            str(data.get("session_mode", "PRE_ONLY")),
                            str(data.get("entry_session", "")),
                            float(data.get("entry_time", 0.0))
                        )
                except Exception:
                    return 0.0, 100.0, "", False, True, 0.0, "", "PRE_ONLY", "", 0.0
            return await asyncio.to_thread(_read)

    @classmethod
    async def get_buy_order_id(cls, symbol: str) -> str:
        filepath = cls._get_file_path(symbol)
        async with GlobalThrottle.get_file_lock(filepath):
            def _read():
                if not os.path.exists(filepath):
                    return ""
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        return str(json.load(f).get("buy_order_id", ""))
                except Exception:
                    return ""
            return await asyncio.to_thread(_read)

    @classmethod
    async def save_state(cls, symbol: str, price: float = None, budget: float = None, 
                         last_session_id: str = None, is_session_done: bool = None, 
                         is_active: bool = None, target_sell_price: float = None, 
                         buy_order_id: str = None, cond_order_id: str = None, 
                         session_mode: str = None, entry_session: str = None, 
                         entry_time: float = None):
        filepath = cls._get_file_path(symbol)
        async with GlobalThrottle.get_file_lock(filepath):
            def _write():
                data = {}
                if os.path.exists(filepath):
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except Exception:
                        pass
                
                if price is not None: data["last_buy_price"] = price
                if budget is not None: data["budget"] = budget
                if last_session_id is not None: data["last_session_id"] = last_session_id
                if is_session_done is not None: data["is_session_done"] = is_session_done
                if is_active is not None: data["is_active"] = is_active
                if target_sell_price is not None: data["target_sell_price"] = target_sell_price
                if buy_order_id is not None: data["buy_order_id"] = buy_order_id
                if cond_order_id is not None: data["cond_order_id"] = cond_order_id
                if session_mode is not None: data["session_mode"] = session_mode
                if entry_session is not None: data["entry_session"] = entry_session
                if entry_time is not None: data["entry_time"] = entry_time
                
                # 사용되지 않는 레거시 키 증발 처리
                for obsolete_key in ["pre_first_flag", "force_downgrade", "force_downgrade_0_6", "is_stage_3"]:
                    data.pop(obsolete_key, None)
                
                tmp_path = filepath + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                os.replace(tmp_path, filepath) 
            await asyncio.to_thread(_write)

class AVWAPEngine:
    @staticmethod
    def calculate_vwap(candles_json: list, session_start_est: datetime) -> float:
        if not candles_json:
            return 0.0
            
        df = pd.DataFrame(candles_json)
        if df.empty: return 0.0
        
        df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601', utc=True)
        df['timestamp'] = df['timestamp'].dt.tz_convert(ZoneInfo('America/New_York'))
        df.set_index('timestamp', inplace=True)
        df.sort_index(ascending=True, inplace=True)
        
        for col in ['highPrice', 'lowPrice', 'closePrice', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            
        session_df = df[df.index >= session_start_est]
        if session_df.empty:
            return 0.0
            
        typical_price = (session_df['highPrice'] + session_df['lowPrice'] + session_df['closePrice']) / 3.0
        pv = typical_price * session_df['volume']
        
        cumulative_pv = pv.sum()
        cumulative_vol = session_df['volume'].sum()
        
        if cumulative_vol <= 0:
            return 0.0
            
        return float(cumulative_pv / cumulative_vol)
