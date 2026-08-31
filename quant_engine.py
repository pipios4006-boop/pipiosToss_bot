# =====================================================================
# FILE: quant_engine.py
# 목적: SOXL, SOXS 듀얼 장부 격리 및 세션별 aVWAP 연산 엔진 (I/O 통제 결속)
# =====================================================================

import os
import json
import pandas as pd
import math
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from toss_api import GlobalThrottle

class AssassinLedger:
    @classmethod
    def _get_file_path(cls, symbol: str) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), f"AssassinLedger_{symbol}.json")

    @classmethod
    async def get_state(cls, symbol: str) -> tuple[float, float, str, bool, bool, bool, float]:
        filepath = cls._get_file_path(symbol)
        # 제1헌법: 파일 I/O 스레드 밀어내기 및 락온 (Case 30)
        async with GlobalThrottle.get_file_lock(filepath):
            def _read():
                if not os.path.exists(filepath):
                    return 0.0, 100.0, "", False, True, False, 0.0
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        return (
                            float(data.get("last_buy_price", 0.0)),
                            float(data.get("budget", 100.0)),
                            str(data.get("last_session_id", "")),
                            bool(data.get("is_session_done", False)),
                            bool(data.get("is_active", True)),
                            bool(data.get("overnight_on", False)),
                            float(data.get("target_sell_price", 0.0))
                        )
                except Exception:
                    return 0.0, 100.0, "", False, True, False, 0.0
            return await asyncio.to_thread(_read)

    # NEW: 하위 호환성 파괴를 막기 위한 주문번호 절대 기억(Amnesia 방어) 조회망 분리
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
                         is_active: bool = None, overnight_on: bool = None, 
                         target_sell_price: float = None, buy_order_id: str = None):
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
                if overnight_on is not None: data["overnight_on"] = overnight_on
                if target_sell_price is not None: data["target_sell_price"] = target_sell_price
                if buy_order_id is not None: data["buy_order_id"] = buy_order_id
                
                tmp_path = filepath + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                # Case 06: 원자적 덮어쓰기 사수 (EAFP 패턴)
                os.replace(tmp_path, filepath) 
            await asyncio.to_thread(_write)

class AVWAPEngine:
    @staticmethod
    def calculate_vwap(candles_json: list, session_start_est: datetime) -> float:
        if not candles_json:
            return 0.0
            
        df = pd.DataFrame(candles_json)
        if df.empty: return 0.0
        
        # MODIFIED: Case 08 & 제4헌법 타임존 파싱 안정성 강화를 위한 utc=True 강제 주입
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
        
        # Case 23: 섀도우 렌더링 멱등성 사수 (ZeroDivision 방어)
        if cumulative_vol <= 0:
            return 0.0
            
        return float(cumulative_pv / cumulative_vol)
