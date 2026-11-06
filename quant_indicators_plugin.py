# -*- coding: utf-8 -*-
"""
# MODIFIED: quant_indicators_plugin.py (Case 92 Wilder RSI14 실시간 합성 + Case 93 암살자 4대 지표[RSI·프리VWAP·전일정규장종가·04:07프리장시가] 일봉/분봉 정밀 분리 및 당일 인메모리 래치 보존)
인피니트 스노우볼 (Infinite Snowball) v3.0 — 순수 롱(SOXL) 매수 04:07 ~ 16:00 EST 제한
(정규장 마감 30분 전 15:30 ~ 16:00 EST 본·서브 그리드 0주 새 사이클 첫 1층 진입 및 상단층 보유 중 1층 공석 +1.0% 돌파 추격 동시 차단 ·
04:07 ~ 15:29 EST 1층 공석 +1.0% 돌파 시 RSI(14) <= 50.0 필터 결합 · 2층 단가 이하 -1.0% 눌림목 재장전 및 10분 게이트 추매/잔량보충 100% 허용 · Case 84, Case 88, Case 92) &
익절 매도 24시간 전 세션(프리마켓 + 정규장 + 애프터마켓 + 데이마켓 · 방안 C 오버나이트 통합이평 사수) 확장 오버나이트 지층관리 스나이퍼 +
🗡️ [모의 ⇄ 실전 Dual-Ready] 암살자(Assassin) 정찰병 4대 지표(① RSI14 · ② 프리장/정규장 VWAP · ③ 전날 정규장 종가 · ④ 당일 04:07 프리장 시가) 및
나스닥(QQQ) 방향성 인지 3단계 안전망(1분/3분/10분 변화율 · 순수 하락 진폭) 100% 벡터화 지표 엔진 코어 모듈 (Step 03 / 14 · Case 93)
"""

from __future__ import annotations

import logging
import math
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from toss_api import (
    EST_TZ,
    LOCKED_BUY_INTERVAL_MIN,
    NEW_CYCLE_BUY_CUTOFF_HM as _API_NEW_CYCLE_BUY_CUTOFF_HM,
    TARGET_SYMBOL,
    safe_float,
    safe_int,
)

logger = logging.getLogger("toss_sniper.quant_indicators_plugin")

# 04:07 EST 기준 분(minute of day = 4 * 60 + 7 = 247) 및 16:00 EST 마감 분(16 * 60 = 960) 0칸 표준 정렬
GATE_START_MIN_OF_DAY: int = 4 * 60 + 7   # 247 (04:07 EST)
GATE_END_MIN_OF_DAY: int = 16 * 60        # 960 (16:00 EST)
REGULAR_START_MIN_OF_DAY: int = 9 * 60 + 30  # 570 (09:30 EST)

# [Case 84 & Case 88]: 정규장 마감 30분 전(15:30 ~ 16:00 EST) 본·서브 0주 새 사이클 첫 1층 진입 및 1층 공석 +1.0% 돌파 추격 동시 차단 기준 시각(HHMM)
NEW_CYCLE_BUY_CUTOFF_HM: int = safe_int(_API_NEW_CYCLE_BUY_CUTOFF_HM, 1530)

# 브로커 1분봉 차트 API 지연/결측 시에도 실시간 1.5초 현재가 틱으로 1분봉을 자체 축적하는 인메모리 링버퍼
_LIVE_1M_BAR_LOCK = threading.RLock()
_LIVE_1M_BAR_STORE: Dict[str, List[Dict[str, Any]]] = {
    TARGET_SYMBOL: [],
    "QQQ": [],
}
_MAX_MEMORY_1M_BARS: int = 600

# [Case 93]: 정규장 진입 후에도 당일 한번 확보된 전일 정규장 종가 · 04:07 프리장 시가 · 프리장 누적 VWAP을 보존하는 당일 인메모리 래치
_DAILY_ANCHOR_LOCK = threading.RLock()
_DAILY_SESSION_ANCHOR_STORE: Dict[Tuple[str, str], Dict[str, Any]] = {}


class _BuyGateBucketResultTuple(tuple):
    """
    기존 스나이퍼 코어의 4-튜플 언패킹:
      is_gate_open, cur_bucket_id, today_str, info = evaluate_buy_gate_bucket_status(...)
    과 암살자(assassin_plugin.py)의 딕셔너리 스타일 조회:
      b_stat = evaluate_buy_gate_bucket_status(...)
      cur_b10 = b_stat.get("bucket_10m", -1)
    를 동시에 100% 지원하는 하이브리드 튜플 클래스.
    """

    def get(self, key: str, default: Any = None) -> Any:
        if len(self) >= 4 and isinstance(self[3], dict):
            return self[3].get(key, default)
        return default


def _get_daily_anchor_latch(symbol: str, target_date: str) -> Dict[str, Any]:
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    d_key = str(target_date or "").strip()
    if not d_key:
        return {}
    with _DAILY_ANCHOR_LOCK:
        saved = _DAILY_SESSION_ANCHOR_STORE.get((sym, d_key))
        return dict(saved) if isinstance(saved, dict) else {}


def _update_daily_anchor_latch(
    symbol: str,
    target_date: str,
    prev_reg_close: float = 0.0,
    pre_open_price: float = 0.0,
    pre_stats: Optional[Dict[str, float]] = None,
) -> None:
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    d_key = str(target_date or "").strip()
    if not d_key:
        return
    with _DAILY_ANCHOR_LOCK:
        # 오래된 날짜 캐시 자동 정리 (최대 6개 유지)
        if len(_DAILY_SESSION_ANCHOR_STORE) > 12:
            oldest_keys = sorted(_DAILY_SESSION_ANCHOR_STORE.keys())[:-6]
            for ok in oldest_keys:
                _DAILY_SESSION_ANCHOR_STORE.pop(ok, None)

        entry = _DAILY_SESSION_ANCHOR_STORE.setdefault((sym, d_key), {})
        if prev_reg_close > 0.0:
            entry["prev_reg_close"] = round(float(prev_reg_close), 4)
        if pre_open_price > 0.0:
            entry["pre_open_price"] = round(float(pre_open_price), 4)
        if isinstance(pre_stats, dict) and safe_float(
            pre_stats.get("vwap"), 0.0
        ) > 0.0:
            entry["pre_stats"] = dict(pre_stats)


# ---------------------------------------------------------------------------
# [핵심 0] 인메모리 실시간 1분봉 자체 합성기 및 API 1분봉 하이브리드 병합기
# ---------------------------------------------------------------------------
def _record_live_tick_to_memory_bar(
    symbol: str,
    live_price: float,
    now_est: Optional[datetime] = None,
) -> Tuple[str, int]:
    """
    실시간 1.5초 현재가 틱 기반 인메모리 1분봉 자체 합성기:
    매 1.5초 루프 또는 /avwap · /assassin 조회 시 유입되는 실시간 현재가(live_price)를
    미국 동부 시간(EST_TZ) 분 단위 버킷(YYYY-MM-DDTHH:MM:00±HH:MM)으로 축적한다.
    반환값: (현재 분 키 문자열 cur_min_key, 인메모리 누적 분봉 개수)
    """
    dt = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    dt_min = dt.replace(second=0, microsecond=0)
    min_key = dt_min.strftime("%Y-%m-%d %H:%M")
    iso_ts = dt_min.isoformat()
    lp = round(safe_float(live_price, 0.0), 4)
    sym = str(symbol or TARGET_SYMBOL).upper().strip()

    if lp <= 0.0:
        with _LIVE_1M_BAR_LOCK:
            bars = _LIVE_1M_BAR_STORE.get(sym, [])
            return min_key, len(bars)

    with _LIVE_1M_BAR_LOCK:
        bars = _LIVE_1M_BAR_STORE.setdefault(sym, [])
        if bars and str(bars[-1].get("_min_key") or "") == min_key:
            last_b = bars[-1]
            prev_h = safe_float(last_b.get("highPrice"), lp)
            prev_l = safe_float(last_b.get("lowPrice"), lp)
            last_b["highPrice"] = round(max(prev_h, lp), 4)
            last_b["lowPrice"] = round(
                min(prev_l, lp) if prev_l > 0.0 else lp, 4
            )
            last_b["closePrice"] = lp
        else:
            bars.append(
                {
                    "_min_key": min_key,
                    "_synthetic": True,
                    "timestamp": iso_ts,
                    "openPrice": lp,
                    "highPrice": lp,
                    "lowPrice": lp,
                    "closePrice": lp,
                    "volume": 1.0,
                    "currency": "USD",
                }
            )
            if len(bars) > _MAX_MEMORY_1M_BARS:
                del bars[: len(bars) - _MAX_MEMORY_1M_BARS]
        return min_key, len(bars)


def _sync_api_candles_into_memory_store(
    symbol: str,
    df_valid: pd.DataFrame,
) -> None:
    """
    API 1분봉 ↔ 인메모리 실시간 틱 덮어쓰기 경합(Race Condition) 및 거래량(volume) 증발 원천 차단:
    API에서 정상적으로 수신·정제된 1분봉 DataFrame(df_valid)을 인메모리 1분봉 저장소(_LIVE_1M_BAR_STORE)와
    동기화하되, 차트 연산 도중 1.5초 메인 스나이퍼 루프가 기록한 최신 분봉(_min_key)의
    고가(max)·저가(min)·최신 종가(closePrice)·거래량(max) 및 연산 도중 새로 열린 분봉이 절대 덮어써져 유실되지 않도록
    _LIVE_1M_BAR_LOCK 내부에서 원자적으로 병합 보존한다.
    """
    if df_valid is None or df_valid.empty:
        return
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    try:
        tail_df = df_valid.tail(_MAX_MEMORY_1M_BARS)
        dt_list = tail_df["dt_est"].tolist()
        o_list = tail_df["O"].tolist()
        h_list = tail_df["H"].tolist()
        l_list = tail_df["L"].tolist()
        c_list = tail_df["C"].tolist()
        v_list = tail_df["V"].tolist()
        syn_list = (
            tail_df["is_synthetic"].tolist()
            if "is_synthetic" in tail_df.columns
            else [False] * len(dt_list)
        )

        synced_bars: List[Dict[str, Any]] = []
        for dt_v, o_v, h_v, l_v, c_v, v_v, syn_v in zip(
            dt_list, o_list, h_list, l_list, c_list, v_list, syn_list
        ):
            dt_m = dt_v.replace(second=0, microsecond=0)
            synced_bars.append(
                {
                    "_min_key": dt_m.strftime("%Y-%m-%d %H:%M"),
                    "_synthetic": bool(syn_v),
                    "timestamp": dt_m.isoformat(),
                    "openPrice": round(float(o_v), 4),
                    "highPrice": round(float(h_v), 4),
                    "lowPrice": round(float(l_v), 4),
                    "closePrice": round(float(c_v), 4),
                    "volume": round(max(1.0, float(v_v)), 2),
                    "currency": "USD",
                }
            )
        if synced_bars:
            with _LIVE_1M_BAR_LOCK:
                existing_bars = _LIVE_1M_BAR_STORE.get(sym, [])
                if existing_bars:
                    last_sync_key = str(synced_bars[-1].get("_min_key") or "")
                    for eb in existing_bars[-3:]:
                        eb_key = str(eb.get("_min_key") or "")
                        if not eb_key:
                            continue
                        if eb_key == last_sync_key:
                            eb_h = safe_float(eb.get("highPrice"), 0.0)
                            eb_l = safe_float(eb.get("lowPrice"), 0.0)
                            eb_c = safe_float(eb.get("closePrice"), 0.0)
                            eb_v = safe_float(eb.get("volume"), 0.0)
                            cur_s = synced_bars[-1]
                            if eb_h > 0.0:
                                cur_s["highPrice"] = round(
                                    max(
                                        safe_float(cur_s.get("highPrice"), eb_h),
                                        eb_h,
                                    ),
                                    4,
                                )
                            if eb_l > 0.0:
                                cur_s_l = safe_float(cur_s.get("lowPrice"), eb_l)
                                cur_s["lowPrice"] = round(
                                    min(cur_s_l, eb_l)
                                    if cur_s_l > 0.0
                                    else eb_l,
                                    4,
                                )
                            if eb_c > 0.0:
                                cur_s["closePrice"] = round(eb_c, 4)
                            if eb_v > 0.0:
                                cur_s["volume"] = round(
                                    max(
                                        safe_float(cur_s.get("volume"), 1.0),
                                        eb_v,
                                    ),
                                    2,
                                )
                        elif eb_key > last_sync_key:
                            synced_bars.append(dict(eb))
                            last_sync_key = eb_key
                _LIVE_1M_BAR_STORE[sym] = synced_bars[-_MAX_MEMORY_1M_BARS:]
    except Exception:
        pass


def _merge_api_and_memory_candles(
    api_candles: Optional[List[Dict[str, Any]]],
    symbol: str = TARGET_SYMBOL,
) -> List[Dict[str, Any]]:
    """
    인메모리 1분봉 선행 + 토스 API 공식 1분봉 후행 배치:
    인메모리 실시간 합성 1분봉(mem_bars, _synthetic=True)을 먼저 배치하고,
    브로커 API 공식 1분봉(api_candles, _synthetic=False, 실제 거래량 및 공식 시가 보유)을 뒤에 배치하여
    동일 분(dt_min) 중복 제거(keep="last") 시 공식 시가(O)·종가(C)·거래량(V)이 우선 채택되도록 보장한다.
    """
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    combined: List[Dict[str, Any]] = []
    with _LIVE_1M_BAR_LOCK:
        mem_bars = list(_LIVE_1M_BAR_STORE.get(sym, []))
    if mem_bars:
        for mb in mem_bars:
            if isinstance(mb, dict):
                c_mb = dict(mb)
                c_mb.setdefault("_synthetic", True)
                combined.append(c_mb)
    if isinstance(api_candles, list) and api_candles:
        for ac in api_candles:
            if isinstance(ac, dict):
                c_ac = dict(ac)
                c_ac["_synthetic"] = False
                combined.append(c_ac)
    return combined


def _parse_timestamp_series_to_est(ts_series: pd.Series) -> pd.Series:
    """
    pandas 2.x 혼합 ISO8601 타임스탬프 NaT 증발 원천 방어:
    밀리초(.123)가 포함된 문자열과 초 단위로 끝나는 문자열이 혼재된 경우에도
    format="ISO8601" 로 전수 파싱하여 단 1개의 유효 캔들도 NaT 로 유실되지 않게 보장한다.
    """
    try:
        ts_utc = pd.to_datetime(
            ts_series, format="ISO8601", utc=True, errors="coerce"
        )
    except Exception:
        ts_utc = pd.to_datetime(ts_series, utc=True, errors="coerce")

    if ts_utc.notna().sum() == 0 and len(ts_series) > 0:
        ts_utc = pd.to_datetime(ts_series, utc=True, errors="coerce")
    return ts_utc


# ---------------------------------------------------------------------------
# [핵심 1] 매수 시간창(04:07 ~ 16:00 EST) · 장마감 30분전 0주 신규 및 1층 공석 돌파 차단창(15:30 ~ 16:00 EST) vs 익절 매도 시간창(24시간 전 세션) 판별기 (Case 01, 79, 84, 88)
# ---------------------------------------------------------------------------
def is_weekend_nyse_closed(now_est: Optional[datetime] = None) -> bool:
    """
    # [Case 01 & Case 79]:
    미국 동부 시간(EST/EDT) 기준 주말 휴장 판정:
    - 금요일 애프터마켓(16:00 ~ 19:59 EST) 익절 매도 주문을 허용하기 위해 금요일(wd == 4)은 20:00 EST 부터 휴장으로 판정한다.
    - 토요일(wd == 5) 전 구간 및 일요일(wd == 6) 17:59 EST 까지를 주말 휴장으로 판정하며,
      일요일 18:00 EST 이후(한국 시간 월요일 오전 데이마켓)는 익절 매도 감시를 위해 정상 개장(False)으로 판정한다.
    """
    dt = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    wd = dt.weekday()  # 월=0, 화=1, ..., 금=4, 토=5, 일=6
    hm = dt.hour * 100 + dt.minute

    if wd == 4 and hm >= 2000:
        return True
    if wd == 5:
        return True
    if wd == 6 and hm < 1800:
        return True
    return False


def is_active_buy_window(
    hm: int, now_est: Optional[datetime] = None
) -> bool:
    """
    # [🎯 2 & Case 01, Case 79, Case 88 : 매수 전용 시간창 (평일 04:07 ~ 16:00 EST 엄격 제한)]:
    """
    if now_est is not None:
        dt = now_est.astimezone(EST_TZ)
        if is_weekend_nyse_closed(dt) or dt.weekday() >= 5:
            return False
    hm_int = safe_int(hm, 0)
    return 407 <= hm_int <= 1600


def is_active_trading_window(
    hm: int, now_est: Optional[datetime] = None
) -> bool:
    """
    하위 호환 심볼 유지: 기존 매수 게이트 및 10분 버킷 산출기에서 호출하는 함수로
    is_active_buy_window(04:07 ~ 16:00 EST)와 동일하게 작동한다.
    """
    return is_active_buy_window(hm, now_est=now_est)


def is_late_regular_new_cycle_cutoff_window(
    hm: Optional[int] = None, now_est: Optional[datetime] = None
) -> bool:
    """
    # [Case 84 & Case 88 : 정규장 마감 30분 전(평일 15:30:00 ~ 16:00:59 EST) 본·서브 0주 새 사이클 첫 1층 진입 및 상단층 보유 중 1층 공석 +1.0% 돌파 추격 동시 차단 판별기]:
    """
    dt = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    if is_weekend_nyse_closed(dt) or dt.weekday() >= 5:
        return False
    hm_int = (
        safe_int(hm, dt.hour * 100 + dt.minute)
        if hm is not None
        else (dt.hour * 100 + dt.minute)
    )
    return NEW_CYCLE_BUY_CUTOFF_HM <= hm_int <= 1600


def is_active_sell_window(
    hm: int, now_est: Optional[datetime] = None
) -> bool:
    """
    # [🎯 2 & Case 79, Case 88 : 익절 매도 전용 확장 시간창 (프리마켓 + 정규장 + 애프터마켓 + 데이마켓 전 구간 개방)]:
    """
    if now_est is not None:
        dt = now_est.astimezone(EST_TZ)
        if is_weekend_nyse_closed(dt):
            return False
    hm_int = safe_int(hm, 0)
    if 400 <= hm_int <= 406:
        return False
    return True


def is_extended_sell_only_window(
    hm: int, now_est: Optional[datetime] = None
) -> bool:
    """
    # [Case 79 : 장외 익절 매도 전용 구간(애프터마켓 · 데이마켓) 여부 판별기]:
    """
    return bool(
        is_active_sell_window(hm, now_est=now_est)
        and not is_active_buy_window(hm, now_est=now_est)
    )


def get_market_session_label(now_est: Optional[datetime] = None) -> str:
    """
    # [Case 79, Case 83, Case 84 & Case 88]:
    현재 EST 시각에 따른 세션 상태 라벨을 반환한다.
    """
    dt = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    if is_weekend_nyse_closed(dt):
        return "🛑 주말휴장"
    hm = dt.hour * 100 + dt.minute
    if 400 <= hm <= 406:
        return "🌅 프리장 오프닝 안정화(04:00~04:06)"
    if 407 <= hm <= 929 and dt.weekday() < 5:
        return "🔫 프리장 스나이퍼 가동(04:07~09:29)"
    if 1530 <= hm <= 1600 and dt.weekday() < 5:
        return "🔥 정규장 마감30분전 가동(15:30~16:00·0주/돌파차단)"
    if 930 <= hm <= 1529 and dt.weekday() < 5:
        return "🔥 정규장 스나이퍼 가동(09:30~16:00)"
    if 1601 <= hm <= 1959 and dt.weekday() < 5:
        return "🌇 애프터장 익절감시(16:00~19:59·매수잠금)"
    return "🌃 데이장 익절감시(20:00~03:59·매수잠금)"


# ---------------------------------------------------------------------------
# [핵심 2] 04:07 ~ 16:00 EST 10분 고정 매수 게이트 버킷 산출기 (Case 01, 36, 64, 79, 84, 88)
# ---------------------------------------------------------------------------
def evaluate_buy_gate_bucket_status(
    now_est: Optional[datetime] = None,
    buy_interval_min: int = LOCKED_BUY_INTERVAL_MIN,
    last_evaluated_bucket_id: int = -1,
    last_evaluated_date: str = "",
) -> _BuyGateBucketResultTuple:
    """
    🚨 Case 01, Case 36, Case 64, Case 79, Case 84 & Case 88:
    04:07 EST 기점 10분 고정 매수 게이트(04:07, 04:17, 04:27, ..., 15:57 및 16:00 마감봉)의
    현재 버킷 ID(cur_bucket_id)와 게이트 오픈 여부(is_gate_open), 차기 검문 시각(next_gate_hm_str)을 산출한다.
    - 반환 객체(_BuyGateBucketResultTuple)는 기존 4-튜플 언패킹과 .get("bucket_10m") 조회를 동시에 지원한다.
    """
    dt = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    today_str = dt.strftime("%Y-%m-%d")
    hm = dt.hour * 100 + dt.minute
    cur_min_of_day = dt.hour * 60 + dt.minute

    interval = LOCKED_BUY_INTERVAL_MIN  # 10분 하드 고정 (Case 64)

    if not is_active_buy_window(hm, now_est=dt) or is_weekend_nyse_closed(dt):
        return _BuyGateBucketResultTuple(
            (
                False,
                -1,
                today_str,
                {
                    "is_active_window": False,
                    "is_sell_window_open": is_active_sell_window(
                        hm, now_est=dt
                    ),
                    "is_new_cycle_cutoff": False,
                    "mins_from_0407": -1,
                    "bucket_10m": -1,
                    "is_exact_boundary_min": False,
                    "next_gate_hm_str": "04:07 EST (매수잠금·익절감시)",
                    "session_label": get_market_session_label(dt),
                },
            )
        )

    mins_from_0407 = max(0, cur_min_of_day - GATE_START_MIN_OF_DAY)
    if hm == 1600:
        cur_bucket_id = 72
        is_exact_boundary = True
        next_gate_str = "익일 04:07 EST"
    else:
        cur_bucket_id = int(mins_from_0407 // interval)
        is_exact_boundary = bool((mins_from_0407 % interval) == 0)
        next_bucket_min_of_day = (
            GATE_START_MIN_OF_DAY + (cur_bucket_id + 1) * interval
        )
        if next_bucket_min_of_day >= GATE_END_MIN_OF_DAY:
            next_gate_str = "16:00 EST"
        else:
            nh = next_bucket_min_of_day // 60
            nm = next_bucket_min_of_day % 60
            next_gate_str = f"{nh:02d}:{nm:02d} EST"

    prev_date = str(last_evaluated_date or "").strip()
    prev_bucket = safe_int(last_evaluated_bucket_id, -1)

    if prev_date != today_str:
        is_gate_open = True
    else:
        is_gate_open = bool(cur_bucket_id > prev_bucket)

    info: Dict[str, Any] = {
        "is_active_window": True,
        "is_sell_window_open": True,
        "is_new_cycle_cutoff": is_late_regular_new_cycle_cutoff_window(
            hm, now_est=dt
        ),
        "mins_from_0407": mins_from_0407,
        "bucket_10m": cur_bucket_id,
        "is_exact_boundary_min": is_exact_boundary,
        "next_gate_hm_str": next_gate_str,
        "session_label": get_market_session_label(dt),
    }
    return _BuyGateBucketResultTuple(
        (is_gate_open, cur_bucket_id, today_str, info)
    )


# ---------------------------------------------------------------------------
# [핵심 3] 100% 벡터화 시계열 지표 산출 엔진 (compute_soxl_quant_metrics_1m & compute_1m_indicators_vectorized)
# ---------------------------------------------------------------------------
def compute_realtime_synthetic_rsi(
    live_price: float,
    prev_bar_close: float,
    prev_avg_gain: float,
    prev_avg_loss: float,
    period: int = 14,
) -> float:
    """
    # [Case 92 & 암살자 4대 지표]:
    직전 완성봉 종가(prev_bar_close) 및 Wilder 평균 상승/하락폭(prev_avg_gain, prev_avg_loss)에
    현재 실시간 틱 가격(live_price)을 O(1) 상수 시간에 합성하여 실시간 Wilder's RSI(14)를 반환한다.
    """
    lp = safe_float(live_price, 0.0)
    p_close = safe_float(prev_bar_close, 0.0)
    if lp <= 0.0 or p_close <= 0.0:
        return 50.0

    p_len = float(max(2, safe_int(period, 14)))
    prev_g = max(0.0, safe_float(prev_avg_gain, 0.0))
    prev_l = max(0.0, safe_float(prev_avg_loss, 0.0))

    diff = lp - p_close
    cur_g = max(0.0, diff)
    cur_l = max(0.0, -diff)

    if prev_g <= 1e-12 and prev_l <= 1e-12:
        live_g = cur_g / p_len
        live_l = cur_l / p_len
    else:
        live_g = (prev_g * (p_len - 1.0) + cur_g) / p_len
        live_l = (prev_l * (p_len - 1.0) + cur_l) / p_len

    if live_g <= 1e-12 and live_l <= 1e-12:
        return 50.0
    if live_l <= 1e-12:
        return 100.0
    rs = live_g / live_l
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def _compute_5ma_intraday_amp_pct_vectorized(
    daily_candles: Optional[List[Dict[str, Any]]],
    df_1m: Optional[pd.DataFrame] = None,
) -> float:
    """
    최근 5영업일 일봉(또는 1분봉 일별 집계)의 일중 진폭 ((High - Low) / Low * 100.0) 평균을
    100% 벡터화 연산으로 산출한다.
    """
    if isinstance(daily_candles, list) and len(daily_candles) >= 2:
        try:
            df_d = pd.DataFrame(daily_candles)
            if "highPrice" in df_d.columns and "lowPrice" in df_d.columns:
                h_s = pd.to_numeric(df_d["highPrice"], errors="coerce")
                l_s = pd.to_numeric(df_d["lowPrice"], errors="coerce")
                valid = (h_s > 0.0) & (l_s > 0.0) & (h_s >= l_s)
                h_v = h_s[valid].to_numpy(dtype=float)
                l_v = l_s[valid].to_numpy(dtype=float)
                if len(l_v) >= 2:
                    if len(l_v) > 5:
                        h_sub = h_v[-6:-1]
                        l_sub = l_v[-6:-1]
                    else:
                        h_sub = h_v[-5:]
                        l_sub = l_v[-5:]
                    amps = ((h_sub - l_sub) / np.maximum(0.01, l_sub)) * 100.0
                    mean_amp = float(np.mean(amps))
                    if not math.isnan(mean_amp) and mean_amp > 0.0:
                        return round(mean_amp, 2)
        except Exception:
            pass

    if df_1m is not None and not df_1m.empty and "Date" in df_1m.columns:
        try:
            grp = df_1m.groupby("Date", sort=True).agg(
                day_h=("H", "max"), day_l=("L", "min")
            )
            valid_g = grp[(grp["day_l"] > 0.0) & (grp["day_h"] >= grp["day_l"])]
            if not valid_g.empty:
                amps = (
                    (
                        valid_g["day_h"].to_numpy(dtype=float)
                        - valid_g["day_l"].to_numpy(dtype=float)
                    )
                    / np.maximum(0.01, valid_g["day_l"].to_numpy(dtype=float))
                ) * 100.0
                mean_amp = float(np.mean(amps[-5:]))
                if not math.isnan(mean_amp) and mean_amp > 0.0:
                    return round(mean_amp, 2)
        except Exception:
            pass

    return 6.50


def _compute_vectorized_heikin_ashi_and_rsi(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
) -> Dict[str, Any]:
    """
    Wilder's RSI(14), Heikin-Ashi(HA_Open, HA_Close), 및 단기 변화율(1분/3분/10분) 벡터화 연산기:
    100% 벡터화(np.diff + Wilder's EWM) 연산으로 n >= 2 이상이면 첫 봉 NaN 왜곡 없이
    직전 완성봉 종가(prev_bar_close)와 직전 완성봉까지의 평균 상승/하락폭(prev_avg_gain, prev_avg_loss)을 산출한다.
    """
    n = len(closes)
    if n == 0:
        return {
            "rsi_14": 50.0,
            "rsi": 50.0,
            "rsi_ready": False,
            "candle_count": 0,
            "prev_bar_close": 0.0,
            "close_3m_ago": 0.0,
            "close_10m_ago": 0.0,
            "vel_1m_pct": 0.0,
            "vel_3m_pct": 0.0,
            "vel_10m_pct": 0.0,
            "vel_max_3m_10m_pct": 0.0,
            "prev_avg_gain": 0.0,
            "prev_avg_loss": 0.0,
            "ha_open": 0.0,
            "ha_close": 0.0,
            "prev_ha_open": 0.0,
            "prev_ha_close": 0.0,
            "cur_bar_open": 0.0,
            "cur_bar_high": 0.0,
            "cur_bar_low": 0.0,
            "ha_bull": True,
            "is_ha_bull": True,
            "ha_badge": "🕯️HA양봉",
        }

    ha_close_arr = (opens + highs + lows + closes) * 0.25
    ha_seed = (opens[0] + closes[0]) * 0.5
    shifted_hc = np.empty(n, dtype=float)
    shifted_hc[0] = ha_seed
    if n > 1:
        shifted_hc[1:] = ha_close_arr[:-1]
    ha_open_series = (
        pd.Series(shifted_hc)
        .ewm(alpha=0.5, adjust=False)
        .mean()
        .to_numpy(dtype=float)
    )

    cur_ha_open = float(ha_open_series[-1])
    cur_ha_close = float(ha_close_arr[-1])
    prev_ha_open = float(ha_open_series[-2]) if n >= 2 else cur_ha_open
    prev_ha_close = float(ha_close_arr[-2]) if n >= 2 else cur_ha_close
    is_bull = bool(cur_ha_close >= cur_ha_open)

    cur_c = float(closes[-1])
    prev_bar_close = float(closes[-2]) if n >= 2 else cur_c
    c_3m_ago = float(closes[-4]) if n >= 4 else float(closes[0])
    c_10m_ago = float(closes[-11]) if n >= 11 else float(closes[0])

    vel_1m_pct = (
        ((cur_c - prev_bar_close) / prev_bar_close) * 100.0
        if prev_bar_close > 0.0
        else 0.0
    )
    vel_3m_pct = (
        ((cur_c - c_3m_ago) / c_3m_ago) * 100.0 if c_3m_ago > 0.0 else 0.0
    )
    vel_10m_pct = (
        ((cur_c - c_10m_ago) / c_10m_ago) * 100.0 if c_10m_ago > 0.0 else 0.0
    )

    rsi_val = 50.0
    prev_avg_g = 0.0
    prev_avg_l = 0.0

    if n >= 2:
        deltas = np.diff(closes)
        gains = np.maximum(0.0, deltas)
        losses = np.maximum(0.0, -deltas)
        avg_gain_arr = (
            pd.Series(gains)
            .ewm(alpha=1.0 / 14.0, min_periods=1, adjust=False)
            .mean()
            .to_numpy(dtype=float)
        )
        avg_loss_arr = (
            pd.Series(losses)
            .ewm(alpha=1.0 / 14.0, min_periods=1, adjust=False)
            .mean()
            .to_numpy(dtype=float)
        )
        last_g = float(avg_gain_arr[-1])
        last_l = float(avg_loss_arr[-1])
        if len(avg_gain_arr) >= 2:
            prev_avg_g = float(avg_gain_arr[-2])
            prev_avg_l = float(avg_loss_arr[-2])
        else:
            prev_avg_g = 0.0
            prev_avg_l = 0.0

        if last_g <= 1e-12 and last_l <= 1e-12:
            rsi_val = 50.0
        elif last_l <= 1e-12:
            rsi_val = 100.0
        else:
            rs = last_g / last_l
            rsi_val = 100.0 - (100.0 / (1.0 + rs))

    clean_rsi = round(rsi_val, 2)
    return {
        "rsi_14": clean_rsi,
        "rsi": clean_rsi,
        "rsi_ready": bool(n >= 14),
        "candle_count": int(n),
        "prev_bar_close": round(prev_bar_close, 4),
        "close_3m_ago": round(c_3m_ago, 4),
        "close_10m_ago": round(c_10m_ago, 4),
        "vel_1m_pct": round(vel_1m_pct, 4),
        "vel_3m_pct": round(vel_3m_pct, 4),
        "vel_10m_pct": round(vel_10m_pct, 4),
        "vel_max_3m_10m_pct": round(max(vel_3m_pct, vel_10m_pct), 4),
        "prev_avg_gain": round(prev_avg_g, 6),
        "prev_avg_loss": round(prev_avg_l, 6),
        "ha_open": round(cur_ha_open, 4),
        "ha_close": round(cur_ha_close, 4),
        "prev_ha_open": round(prev_ha_open, 4),
        "prev_ha_close": round(prev_ha_close, 4),
        "cur_bar_open": round(float(opens[-1]), 4),
        "cur_bar_high": round(float(highs[-1]), 4),
        "cur_bar_low": round(float(lows[-1]), 4),
        "ha_bull": is_bull,
        "is_ha_bull": is_bull,
        "ha_badge": "🕯️HA양봉" if is_bull else "🌑HA음봉",
    }


def _recompute_ha_rsi_from_memory_store(
    symbol: str = TARGET_SYMBOL,
) -> Optional[Dict[str, Any]]:
    """
    인메모리 1분봉 저장소(_LIVE_1M_BAR_STORE)에 축적된 분봉이 2개 이상일 때,
    O(1) 수준의 경량 배열 연산으로 Wilder's RSI(14) 및 Heikin-Ashi 기저값을 즉시 재산출한다.
    """
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    with _LIVE_1M_BAR_LOCK:
        bars = list(_LIVE_1M_BAR_STORE.get(sym, []))
    if len(bars) < 2:
        return None
    try:
        df_m = pd.DataFrame(bars)
        opens = pd.to_numeric(df_m["openPrice"], errors="coerce").to_numpy(
            dtype=float
        )
        highs = pd.to_numeric(df_m["highPrice"], errors="coerce").to_numpy(
            dtype=float
        )
        lows = pd.to_numeric(df_m["lowPrice"], errors="coerce").to_numpy(
            dtype=float
        )
        closes = pd.to_numeric(df_m["closePrice"], errors="coerce").to_numpy(
            dtype=float
        )
        valid_mask = (
            np.isfinite(opens)
            & np.isfinite(highs)
            & np.isfinite(lows)
            & np.isfinite(closes)
            & (closes > 0.0)
        )
        if int(np.sum(valid_mask)) < 2:
            return None
        res = _compute_vectorized_heikin_ashi_and_rsi(
            opens[valid_mask],
            highs[valid_mask],
            lows[valid_mask],
            closes[valid_mask],
        )
        res["cur_bar_minute_key"] = str(bars[-1].get("_min_key") or "")
        return res
    except Exception:
        return None


def _calc_session_vwap_and_bands(
    df_sess: pd.DataFrame,
    ma5_amp_pct: float,
) -> Dict[str, float]:
    """
    주어진 세션(프리장 또는 정규장) DataFrame 에 대해 누적 VWAP, 고가, 저가, 진폭(%),
    5MA 진폭 기반 예상 저가/고가 밴드를 100% 벡터화 연산으로 산출한다.
    """
    if df_sess is None or df_sess.empty:
        return {
            "vwap": 0.0,
            "high": 0.0,
            "low": 0.0,
            "amp_pct": 0.0,
            "est_low": 0.0,
            "est_high": 0.0,
        }

    h_arr = df_sess["H"].to_numpy(dtype=float)
    l_arr = df_sess["L"].to_numpy(dtype=float)
    c_arr = df_sess["C"].to_numpy(dtype=float)
    v_arr = np.maximum(0.0, df_sess["V"].to_numpy(dtype=float))

    tp_arr = (h_arr + l_arr + c_arr) / 3.0
    tot_vol = float(np.sum(v_arr))
    if tot_vol > 0.0:
        vwap_val = float(np.sum(tp_arr * v_arr) / tot_vol)
    else:
        vwap_val = float(np.mean(tp_arr))

    sess_h = float(np.max(h_arr))
    sess_l = float(np.min(l_arr))
    amp_pct = (
        ((sess_h - sess_l) / sess_l) * 100.0 if sess_l > 0.0 else 0.0
    )

    amp_ratio = max(0.01, float(ma5_amp_pct) / 100.0)
    est_high = sess_l * (1.0 + amp_ratio) if sess_l > 0.0 else 0.0
    est_low = sess_h / (1.0 + amp_ratio) if sess_h > 0.0 else 0.0

    return {
        "vwap": round(vwap_val, 4),
        "high": round(sess_h, 4),
        "low": round(sess_l, 4),
        "amp_pct": round(amp_pct, 2),
        "est_low": round(min(est_low, sess_l), 2),
        "est_high": round(max(est_high, sess_h), 2),
    }


def _extract_daily_candle_date_str(
    dc: Dict[str, Any],
) -> Tuple[str, str]:
    """
    일봉(1d) 캔들의 timestamp 에서 원본 날짜 문자열(raw_date)과 EST 변환 날짜(est_date)를 추출한다.
    """
    ts_raw = str(
        dc.get("timestamp") or dc.get("date") or dc.get("dt") or ""
    ).strip()
    raw_date = ts_raw[:10] if len(ts_raw) >= 10 else ""
    est_date = raw_date
    if ts_raw and "T" in ts_raw:
        try:
            dt_obj = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            est_date = dt_obj.astimezone(EST_TZ).strftime("%Y-%m-%d")
        except Exception:
            pass
    return raw_date, est_date


def _extract_prev_reg_close_and_pre_open(
    df_all: pd.DataFrame,
    target_date: str,
    daily_candles: Optional[List[Dict[str, Any]]] = None,
    explicit_prev_close: float = 0.0,
    fallback_price: float = 0.0,
    symbol: str = TARGET_SYMBOL,
) -> Tuple[float, float]:
    """
    # MODIFIED [Case 93 : 암살자 정찰병 필수 조건 3(전날 정규장 종가 prev_reg_close) & 조건 4(당일 04:07 프리장 시가 pre_open_price) 정밀 분리 추출기]:
    1) prev_reg_close (전일 정규장 종가):
       - explicit_prev_close > 0.0 이면 최우선 채택
       - 1분봉(df_all) 내 target_date 이전 영업일의 정규장(09:30 ~ 16:00 EST) 마지막 완성봉 종가(C) 추출
       - 일봉(daily_candles)이 존재하면 당일 진행중 일봉(raw_date >= target_date 또는 est_date >= target_date)을 제외한
         직전 영업일 확정 일봉의 closePrice 추출
       - 당일 인메모리 래치(_DAILY_SESSION_ANCHOR_STORE) 보존값 활용
    2) pre_open_price (당일 04:07 프리장 시가):
       - 당일(target_date) 실제 API 1분봉(_synthetic == False) 중 04:07 ~ 09:29 EST 첫 봉의 시가(O) 추출
       - 부재 시 당일 인메모리 래치(_DAILY_SESSION_ANCHOR_STORE) 보존값 활용
       - 부재 시 당일 04:00 ~ 09:29 EST 프리장 첫 봉 시가 또는 일봉 당일 openPrice 활용
    """
    latch = _get_daily_anchor_latch(symbol, target_date)
    prev_reg_c = safe_float(explicit_prev_close, 0.0)
    pre_open_p = 0.0
    daily_today_open = 0.0

    # 1단계: 일봉(1d)에서 직전 영업일 확정 정규장 종가 및 당일 일봉 시가 추출
    if isinstance(daily_candles, list) and len(daily_candles) >= 1:
        try:
            valid_d = [
                c
                for c in daily_candles
                if isinstance(c, dict)
                and safe_float(c.get("closePrice") or c.get("close"), 0.0)
                > 0.0
            ]
            sorted_d = sorted(
                valid_d,
                key=lambda x: str(
                    x.get("timestamp") or x.get("date") or ""
                ),
            )
            if sorted_d:
                last_dc = sorted_d[-1]
                raw_d, est_d = _extract_daily_candle_date_str(last_dc)
                last_close = safe_float(
                    last_dc.get("closePrice") or last_dc.get("close"), 0.0
                )
                last_open = safe_float(
                    last_dc.get("openPrice") or last_dc.get("open"), 0.0
                )

                # 최신 일봉이 오늘(target_date) 진행중인 일봉인 경우 -> 어제 확정 종가는 sorted_d[-2]
                if (raw_d and raw_d >= target_date) or (
                    est_d and est_d >= target_date
                ):
                    if last_open > 0.0:
                        daily_today_open = last_open
                    if prev_reg_c <= 0.0 and len(sorted_d) >= 2:
                        prev_reg_c = safe_float(
                            sorted_d[-2].get("closePrice")
                            or sorted_d[-2].get("close"),
                            0.0,
                        )
                else:
                    # 최신 일봉이 어제(target_date 이전) 확정 일봉인 경우 -> 어제 확정 종가는 sorted_d[-1]
                    if prev_reg_c <= 0.0:
                        prev_reg_c = last_close
        except Exception:
            pass

    # 2단계: 1분봉(df_all)에서 전일 정규장(09:30 ~ 16:00 EST) 마감 종가 및 당일 04:07 프리장 시가 추출
    if df_all is not None and not df_all.empty and "Date" in df_all.columns:
        df_today = df_all[df_all["Date"] == target_date]
        if not df_today.empty:
            has_syn_col = "is_synthetic" in df_today.columns
            df_today_api = (
                df_today[~df_today["is_synthetic"]]
                if has_syn_col
                else df_today
            )
            source_today = (
                df_today_api if not df_today_api.empty else df_today
            )

            pre_0407 = source_today[
                (source_today["hm"] >= 407) & (source_today["hm"] <= 929)
            ]
            if not pre_0407.empty:
                pre_open_p = float(pre_0407["O"].iloc[0])
            else:
                pre_0400 = source_today[
                    (source_today["hm"] >= 400) & (source_today["hm"] <= 929)
                ]
                if not pre_0400.empty:
                    pre_open_p = float(pre_0400["O"].iloc[0])

        if prev_reg_c <= 0.0:
            df_prev = df_all[df_all["Date"] < target_date]
            if not df_prev.empty:
                prev_dates = sorted(df_prev["Date"].unique())
                last_prev_d = str(prev_dates[-1])
                df_last_d = df_prev[df_prev["Date"] == last_prev_d]
                reg_prev = df_last_d[
                    (df_last_d["hm"] >= 930) & (df_last_d["hm"] <= 1600)
                ]
                if not reg_prev.empty:
                    prev_reg_c = float(reg_prev["C"].iloc[-1])
                else:
                    prev_reg_c = float(df_last_d["C"].iloc[-1])

    # 3단계: 당일 인메모리 래치(_DAILY_SESSION_ANCHOR_STORE) 복원 및 갱신
    latched_prev_c = safe_float(latch.get("prev_reg_close"), 0.0)
    latched_pre_o = safe_float(latch.get("pre_open_price"), 0.0)

    if prev_reg_c <= 0.0 and latched_prev_c > 0.0:
        prev_reg_c = latched_prev_c
    if pre_open_p <= 0.0 and latched_pre_o > 0.0:
        pre_open_p = latched_pre_o

    # 진성으로 추출된 값은 즉시 당일 래치에 영속 보관
    if prev_reg_c > 0.0 or pre_open_p > 0.0:
        _update_daily_anchor_latch(
            symbol=symbol,
            target_date=target_date,
            prev_reg_close=prev_reg_c,
            pre_open_price=pre_open_p,
        )

    # 4단계: 최후 안전 폴백 (일봉 당일 시가 -> 당일 첫 봉 시가 -> 현재가 순)
    fb = safe_float(fallback_price, 0.0)
    if pre_open_p <= 0.0:
        if daily_today_open > 0.0:
            pre_open_p = daily_today_open
        elif (
            df_all is not None
            and not df_all.empty
            and (df_all["Date"] == target_date).any()
        ):
            pre_open_p = float(
                df_all[df_all["Date"] == target_date]["O"].iloc[0]
            )
        else:
            pre_open_p = prev_reg_c if prev_reg_c > 0.0 else fb

    if prev_reg_c <= 0.0:
        prev_reg_c = pre_open_p if pre_open_p > 0.0 else fb

    return round(prev_reg_c, 4), round(pre_open_p, 4)


def compute_soxl_quant_metrics_1m(
    candles: List[Dict[str, Any]],
    live_price: float = 0.0,
    now_est: Optional[datetime] = None,
    daily_candles: Optional[List[Dict[str, Any]]] = None,
    prev_day_close: float = 0.0,
    symbol: str = TARGET_SYMBOL,
) -> Dict[str, Any]:
    """
    🎯 2 & Case 01, 15, 79, 84, 88, 92, 93 & 암살자 4대 지표 통합 연산기:
    토스 Open API 1분봉(candles), 인메모리 실시간 합성 1분봉(_LIVE_1M_BAR_STORE) 및 일봉(daily_candles)을 입력받아:
    1) 당일 프리장(04:07 ~ 09:29 EST) 누적 VWAP · 고/저가 진폭 · 예상 변동 밴드 (정규장 진입 후에도 당일 래치 보존)
    2) 당일 정규장(09:30 ~ 16:00 EST) 누적 VWAP · 고/저가 진폭 · 예상 변동 밴드
    3) 최근 5영업일 평균 진폭(5MA) · 실시간 하이킨 아시 추세 배지(🕯️HA양봉 / 🌑HA음봉) · Wilder's RSI(14)
    4) 암살자 4대 필수 조건(① rsi_14/rsi · ② premarket_vwap/vwap · ③ prev_reg_close/prev_day_close · ④ pre_open_price) 및
       단기 변화율(vel_1m_pct, vel_3m_pct, vel_10m_pct) · 시가 대비 순수 하락 진폭(bear_drop_amp_pct)
    5) 04:07 ~ 16:00 EST 10분 고정 매수 게이트 버킷 · 장마감 30분전 0주 신규 및 1층 공석 돌파 컷오프(15:30 ~ 16:00 EST) 정보
    를 100% 벡터화 연산으로 산출하여 반환한다.
    """
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    hm_now = dt_now.hour * 100 + dt_now.minute
    _, cur_bucket_id, today_str, gate_info = evaluate_buy_gate_bucket_status(
        now_est=dt_now, buy_interval_min=LOCKED_BUY_INTERVAL_MIN
    )
    lp = safe_float(live_price, 0.0)
    cur_min_key, _ = _record_live_tick_to_memory_bar(
        sym, lp, now_est=dt_now
    )
    init_prev_c = safe_float(prev_day_close, 0.0)
    api_candle_cnt = len(candles) if isinstance(candles, list) else 0
    daily_candle_cnt = (
        len(daily_candles) if isinstance(daily_candles, list) else 0
    )

    default_out: Dict[str, Any] = {
        "symbol": sym,
        "live_price": round(lp, 4),
        "current_price": round(lp, 4),
        "ma5_amp_pct": 6.50,
        "rsi_14": 50.0,
        "rsi": 50.0,
        "rsi_ready": False,
        "anchors_ready": False,
        "api_candle_count": api_candle_cnt,
        "daily_candle_count": daily_candle_cnt,
        "candle_count": 0,
        "cur_bar_minute_key": cur_min_key,
        "prev_bar_close": 0.0,
        "close_3m_ago": 0.0,
        "close_10m_ago": 0.0,
        "vel_1m_pct": 0.0,
        "vel_3m_pct": 0.0,
        "vel_10m_pct": 0.0,
        "vel_max_3m_10m_pct": 0.0,
        "bear_drop_amp_pct": 0.0,
        "prev_avg_gain": 0.0,
        "prev_avg_loss": 0.0,
        "ha_open": round(lp, 4),
        "ha_close": round(lp, 4),
        "prev_ha_open": round(lp, 4),
        "prev_ha_close": round(lp, 4),
        "cur_bar_open": round(lp, 4),
        "cur_bar_high": round(lp, 4),
        "cur_bar_low": round(lp, 4),
        "ha_bull": True,
        "is_ha_bull": True,
        "ha_badge": "🕯️HA양봉",
        "prev_reg_close": round(init_prev_c if init_prev_c > 0.0 else lp, 4),
        "prev_day_close": round(init_prev_c if init_prev_c > 0.0 else lp, 4),
        "pre_open_price": round(lp, 4),
        "premarket_vwap": round(lp, 4),
        "premarket_high": round(lp, 4),
        "premarket_low": round(lp, 4),
        "premarket_amp_pct": 0.0,
        "premarket_est_low": round(lp, 2),
        "premarket_est_high": round(lp, 2),
        "regular_vwap": round(lp, 4),
        "regular_high": round(lp, 4),
        "regular_low": round(lp, 4),
        "regular_amp_pct": 0.0,
        "regular_est_low": round(lp, 2),
        "regular_est_high": round(lp, 2),
        "day_vwap": round(lp, 4),
        "vwap": round(lp, 4),
        "day_high": round(lp, 4),
        "day_low": round(lp, 4),
        "day_amp_pct": 0.0,
        "bucket_10m": cur_bucket_id,
        "is_new_cycle_cutoff": is_late_regular_new_cycle_cutoff_window(
            hm_now, now_est=dt_now
        ),
        "next_gate_hm_str": gate_info.get("next_gate_hm_str", "04:07 EST"),
        "session_label": gate_info.get("session_label", ""),
        "updated_est": dt_now.strftime("%m-%d %H:%M:%S EST"),
    }

    merged_candles = _merge_api_and_memory_candles(candles, sym)
    if not merged_candles:
        default_out["ma5_amp_pct"] = _compute_5ma_intraday_amp_pct_vectorized(
            daily_candles, None
        )
        return default_out

    try:
        df = pd.DataFrame(merged_candles)
        if df.empty:
            return default_out

        ts_col = (
            "timestamp"
            if "timestamp" in df.columns
            else (
                "dt"
                if "dt" in df.columns
                else ("dateTime" if "dateTime" in df.columns else None)
            )
        )
        if ts_col is None:
            return default_out

        ts_utc = _parse_timestamp_series_to_est(df[ts_col])
        valid_ts = ts_utc.notna()
        df = df.loc[valid_ts].copy()
        if df.empty:
            return default_out

        df["dt_est"] = ts_utc[valid_ts].dt.tz_convert(EST_TZ)
        df["dt_min"] = df["dt_est"].dt.floor("min")
        df["is_synthetic"] = (
            df["_synthetic"].fillna(False).astype(bool)
            if "_synthetic" in df.columns
            else False
        )

        df["O"] = pd.to_numeric(
            df.get("openPrice", df.get("open", df.get("price"))),
            errors="coerce",
        )
        df["H"] = pd.to_numeric(
            df.get("highPrice", df.get("high", df.get("price"))),
            errors="coerce",
        )
        df["L"] = pd.to_numeric(
            df.get("lowPrice", df.get("low", df.get("price"))),
            errors="coerce",
        )
        df["C"] = pd.to_numeric(
            df.get("closePrice", df.get("close", df.get("price"))),
            errors="coerce",
        )
        df["V"] = pd.to_numeric(
            df.get("volume", 0.0), errors="coerce"
        ).fillna(0.0)

        df.dropna(subset=["O", "H", "L", "C"], inplace=True)
        df = df[
            (df["O"] > 0.0)
            & (df["H"] > 0.0)
            & (df["L"] > 0.0)
            & (df["C"] > 0.0)
        ].copy()
        if df.empty:
            return default_out

        if df.duplicated(subset=["dt_min"]).any():
            grp_min = df.groupby("dt_min", sort=False)
            df["H"] = grp_min["H"].transform("max")
            df["L"] = grp_min["L"].transform("min")
            df["V"] = grp_min["V"].transform("max")
            df.drop_duplicates(subset=["dt_min"], keep="last", inplace=True)

        df.sort_values("dt_min", ascending=True, inplace=True)
        _sync_api_candles_into_memory_store(sym, df)

        df["Date"] = df["dt_est"].dt.strftime("%Y-%m-%d")
        df["hm"] = df["dt_est"].dt.hour * 100 + df["dt_est"].dt.minute

        last_candle_close = float(df["C"].iloc[-1])
        if lp <= 0.0:
            lp = last_candle_close

        ma5_amp = _compute_5ma_intraday_amp_pct_vectorized(daily_candles, df)

        opens = df["O"].to_numpy(dtype=float)
        highs = df["H"].to_numpy(dtype=float)
        lows = df["L"].to_numpy(dtype=float)
        closes = df["C"].to_numpy(dtype=float)
        if lp > 0.0 and len(closes) > 0:
            closes[-1] = lp
            highs[-1] = max(highs[-1], lp)
            lows[-1] = min(lows[-1], lp)

        ha_rsi_info = _compute_vectorized_heikin_ashi_and_rsi(
            opens, highs, lows, closes
        )
        last_dt_min = df["dt_min"].iloc[-1]
        ha_rsi_info["cur_bar_minute_key"] = last_dt_min.strftime(
            "%Y-%m-%d %H:%M"
        )

        target_date = (
            today_str
            if (df["Date"] == today_str).any()
            else str(df["Date"].iloc[-1])
        )
        df_today = df[df["Date"] == target_date]

        prev_reg_c, pre_open_p = _extract_prev_reg_close_and_pre_open(
            df_all=df,
            target_date=target_date,
            daily_candles=daily_candles,
            explicit_prev_close=init_prev_c,
            fallback_price=lp,
            symbol=sym,
        )

        # 백테스트(build_soxl_scout_cache.py)와 동일하게 04:07 EST 이후 실제 API 프리장 누적 VWAP 산출
        df_today_api = (
            df_today[~df_today["is_synthetic"]]
            if "is_synthetic" in df_today.columns
            else df_today
        )
        pre_source = (
            df_today_api if not df_today_api.empty else df_today
        )
        df_pre_0407 = pre_source[
            (pre_source["hm"] >= 407) & (pre_source["hm"] <= 929)
        ]
        df_pre = (
            df_pre_0407
            if not df_pre_0407.empty
            else pre_source[
                (pre_source["hm"] >= 400) & (pre_source["hm"] <= 929)
            ]
        )
        df_reg = df_today[(df_today["hm"] >= 930) & (df_today["hm"] <= 1600)]

        pre_stats = _calc_session_vwap_and_bands(df_pre, ma5_amp)
        if pre_stats["vwap"] > 0.0:
            _update_daily_anchor_latch(
                symbol=sym,
                target_date=target_date,
                pre_stats=pre_stats,
            )
        else:
            latched_info = _get_daily_anchor_latch(sym, target_date)
            latched_pre_stats = latched_info.get("pre_stats")
            if isinstance(latched_pre_stats, dict) and safe_float(
                latched_pre_stats.get("vwap"), 0.0
            ) > 0.0:
                pre_stats = dict(latched_pre_stats)

        reg_stats = _calc_session_vwap_and_bands(df_reg, ma5_amp)
        all_stats = _calc_session_vwap_and_bands(df_today, ma5_amp)

        active_vwap = (
            reg_stats["vwap"]
            if reg_stats["vwap"] > 0.0
            else (
                pre_stats["vwap"]
                if pre_stats["vwap"] > 0.0
                else all_stats["vwap"]
            )
        )
        eff_pre_vwap = (
            pre_stats["vwap"] if pre_stats["vwap"] > 0.0 else active_vwap
        )
        bear_drop_amp = (
            max(0.0, ((pre_open_p - lp) / pre_open_p) * 100.0)
            if pre_open_p > 0.0
            else 0.0
        )

        anchors_ready = bool(
            (api_candle_cnt > 0 or daily_candle_cnt > 0)
            and prev_reg_c > 0.0
            and pre_open_p > 0.0
        )

        out = dict(default_out)
        out.update(ha_rsi_info)
        out.update(
            {
                "live_price": round(lp, 4),
                "current_price": round(lp, 4),
                "ma5_amp_pct": ma5_amp,
                "anchors_ready": anchors_ready,
                "api_candle_count": api_candle_cnt,
                "daily_candle_count": daily_candle_cnt,
                "prev_reg_close": prev_reg_c,
                "prev_day_close": prev_reg_c,
                "pre_open_price": pre_open_p,
                "bear_drop_amp_pct": round(bear_drop_amp, 4),
                "premarket_vwap": eff_pre_vwap,
                "premarket_high": pre_stats["high"],
                "premarket_low": pre_stats["low"],
                "premarket_amp_pct": pre_stats["amp_pct"],
                "premarket_est_low": pre_stats["est_low"],
                "premarket_est_high": pre_stats["est_high"],
                "regular_vwap": (
                    reg_stats["vwap"]
                    if reg_stats["vwap"] > 0.0
                    else active_vwap
                ),
                "regular_high": reg_stats["high"],
                "regular_low": reg_stats["low"],
                "regular_amp_pct": reg_stats["amp_pct"],
                "regular_est_low": reg_stats["est_low"],
                "regular_est_high": reg_stats["est_high"],
                "day_vwap": active_vwap,
                "vwap": eff_pre_vwap if hm_now <= 929 else active_vwap,
                "day_high": all_stats["high"],
                "day_low": all_stats["low"],
                "day_amp_pct": all_stats["amp_pct"],
            }
        )
        return refresh_metrics_with_live_tick(
            out, lp, now_est=dt_now, symbol=sym
        )
    except Exception as exc:
        logger.debug("compute_soxl_quant_metrics_1m 연산 폴백(묵음): %s", exc)
        return refresh_metrics_with_live_tick(
            default_out, lp, now_est=dt_now, symbol=sym
        )


def compute_1m_indicators_vectorized(
    candles: List[Dict[str, Any]],
    prev_day_close: float = 0.0,
    live_price: float = 0.0,
    now_est: Optional[datetime] = None,
    daily_candles: Optional[List[Dict[str, Any]]] = None,
    symbol: str = TARGET_SYMBOL,
) -> Dict[str, Any]:
    """
    # NEW: assassin_plugin.py 및 sniper_plugin_core.py 온디맨드 1분봉 벡터 지표 산출기 호환 엔트리
    """
    return compute_soxl_quant_metrics_1m(
        candles=candles,
        live_price=live_price,
        now_est=now_est,
        daily_candles=daily_candles,
        prev_day_close=prev_day_close,
        symbol=symbol,
    )


def compute_qqq_macro_metrics_1m(
    candles: List[Dict[str, Any]],
    live_price: float = 0.0,
    now_est: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    # NEW: 나스닥 100 추종 QQQ 1분봉 기반 방향성 인지 3단계 안전망 지표 산출기
    """
    return compute_soxl_quant_metrics_1m(
        candles=candles,
        live_price=live_price,
        now_est=now_est,
        daily_candles=None,
        prev_day_close=0.0,
        symbol="QQQ",
    )


# ---------------------------------------------------------------------------
# [핵심 4] 실시간 틱(live_price) O(1) 무부하 합성기 (refresh_metrics_with_live_tick — Case 84, 88, 92, 93 연동)
# ---------------------------------------------------------------------------
def refresh_metrics_with_live_tick(
    base_metrics: Optional[Dict[str, Any]],
    live_price: float,
    now_est: Optional[datetime] = None,
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """
    # MODIFIED [Case 84, Case 88, Case 92, Case 93 & 암살자 4대 지표 실시간 O(1) 틱 합성]:
    1) 실시간 현재가(live_price)를 인메모리 1분봉 저장소(_LIVE_1M_BAR_STORE)에 즉시 반영한다.
    2) 당일 인메모리 래치(_DAILY_SESSION_ANCHOR_STORE)에 보존된 전일 정규장 종가(prev_reg_close),
       당일 04:07 프리장 시가(pre_open_price), 프리장 누적 VWAP(premarket_vwap)이 있으면 우선 복원하여
       틱 합성 과정에서 앵커 가격이 현재가로 덮어써지는 현상을 원천 차단한다.
    3) prev_bar_close > 0.0 이면 매 1.5초(또는 0.4초) 실시간 틱 변동을 Wilder's RSI(14)와
       단기 변화율(vel_1m_pct, vel_3m_pct, vel_10m_pct), 하이킨 아시(ha_bull / is_ha_bull)에 즉시 합성한다!
    """
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    dt = dt_now
    today_str = dt_now.strftime("%Y-%m-%d")
    hm = dt_now.hour * 100 + dt_now.minute
    _, cur_bucket_id, _, gate_info = evaluate_buy_gate_bucket_status(
        now_est=dt, buy_interval_min=LOCKED_BUY_INTERVAL_MIN
    )

    met = dict(base_metrics) if isinstance(base_metrics, dict) else {}
    sym = str(
        symbol or met.get("symbol") or TARGET_SYMBOL
    ).upper().strip()
    met["symbol"] = sym

    lp = safe_float(live_price, 0.0)
    if lp <= 0.0:
        lp = safe_float(
            met.get("live_price"), safe_float(met.get("current_price"), 0.0)
        )
    else:
        met["live_price"] = round(lp, 4)
        met["current_price"] = round(lp, 4)

    cur_min_key, mem_bar_cnt = _record_live_tick_to_memory_bar(
        sym, lp, now_est=dt_now
    )
    prev_min_key = str(met.get("cur_bar_minute_key") or "")

    if mem_bar_cnt >= 2 and (
        safe_float(met.get("prev_bar_close"), 0.0) <= 0.0
        or (prev_min_key and prev_min_key != cur_min_key)
    ):
        mem_ha_rsi = _recompute_ha_rsi_from_memory_store(sym)
        if isinstance(mem_ha_rsi, dict):
            met.update(mem_ha_rsi)

    met["cur_bar_minute_key"] = cur_min_key

    # 당일 인메모리 래치에서 확정된 앵커(전일종가·04:07프리시가·프리VWAP) 복원
    latch = _get_daily_anchor_latch(sym, today_str)
    latched_prev_c = safe_float(latch.get("prev_reg_close"), 0.0)
    latched_pre_o = safe_float(latch.get("pre_open_price"), 0.0)
    latched_pre_stats = latch.get("pre_stats")

    if latched_prev_c > 0.0:
        met["prev_reg_close"] = latched_prev_c
        met["prev_day_close"] = latched_prev_c
    if latched_pre_o > 0.0:
        met["pre_open_price"] = latched_pre_o
    if isinstance(latched_pre_stats, dict) and safe_float(
        latched_pre_stats.get("vwap"), 0.0
    ) > 0.0:
        if safe_float(met.get("premarket_vwap"), 0.0) <= 0.0 or hm > 929:
            met["premarket_vwap"] = round(
                safe_float(latched_pre_stats.get("vwap"), lp), 4
            )

    ma5_amp = max(1.0, safe_float(met.get("ma5_amp_pct"), 6.50))
    amp_ratio = ma5_amp / 100.0

    if lp > 0.0:
        prev_ho = safe_float(met.get("prev_ha_open"), lp)
        prev_hc = safe_float(met.get("prev_ha_close"), lp)
        cur_o = safe_float(met.get("cur_bar_open"), lp)
        if cur_o <= 0.0:
            cur_o = lp
        cur_h = max(safe_float(met.get("cur_bar_high"), lp), lp)
        cur_l_raw = safe_float(met.get("cur_bar_low"), 0.0)
        cur_l = min(cur_l_raw, lp) if cur_l_raw > 0.0 else lp
        live_ha_open = (prev_ho + prev_hc) * 0.5
        live_ha_close = (cur_o + cur_h + cur_l + lp) * 0.25
        is_bull = bool(live_ha_close >= live_ha_open)
        met["cur_bar_open"] = round(cur_o, 4)
        met["cur_bar_high"] = round(cur_h, 4)
        met["cur_bar_low"] = round(cur_l, 4)
        met["ha_open"] = round(live_ha_open, 4)
        met["ha_close"] = round(live_ha_close, 4)
        met["ha_bull"] = is_bull
        met["is_ha_bull"] = is_bull
        met["ha_badge"] = "🕯️HA양봉" if is_bull else "🌑HA음봉"

        prev_b_close = safe_float(met.get("prev_bar_close"), 0.0)
        prev_avg_g = max(0.0, safe_float(met.get("prev_avg_gain"), 0.0))
        prev_avg_l = max(0.0, safe_float(met.get("prev_avg_loss"), 0.0))

        if prev_b_close > 0.0:
            live_rsi = compute_realtime_synthetic_rsi(
                live_price=lp,
                prev_bar_close=prev_b_close,
                prev_avg_gain=prev_avg_g,
                prev_avg_loss=prev_avg_l,
                period=14,
            )
            met["rsi_14"] = live_rsi
            met["rsi"] = live_rsi
            met["vel_1m_pct"] = round(
                ((lp - prev_b_close) / prev_b_close) * 100.0, 4
            )

        c_3m = safe_float(met.get("close_3m_ago"), prev_b_close)
        c_10m = safe_float(met.get("close_10m_ago"), prev_b_close)
        if c_3m > 0.0:
            met["vel_3m_pct"] = round(((lp - c_3m) / c_3m) * 100.0, 4)
        if c_10m > 0.0:
            met["vel_10m_pct"] = round(((lp - c_10m) / c_10m) * 100.0, 4)
        met["vel_max_3m_10m_pct"] = round(
            max(
                safe_float(met.get("vel_3m_pct"), 0.0),
                safe_float(met.get("vel_10m_pct"), 0.0),
            ),
            4,
        )

        pre_open_p = safe_float(met.get("pre_open_price"), lp)
        if pre_open_p <= 0.0:
            pre_open_p = lp
            met["pre_open_price"] = round(lp, 4)
        met["bear_drop_amp_pct"] = round(
            max(0.0, ((pre_open_p - lp) / pre_open_p) * 100.0), 4
        )

        if safe_float(met.get("prev_reg_close"), 0.0) <= 0.0:
            met["prev_reg_close"] = round(
                safe_float(met.get("prev_day_close"), pre_open_p), 4
            )
        if safe_float(met.get("prev_day_close"), 0.0) <= 0.0:
            met["prev_day_close"] = met["prev_reg_close"]

        if not bool(met.get("rsi_ready", False)) and mem_bar_cnt >= 14:
            met["rsi_ready"] = True

    if lp > 0.0 and 400 <= hm <= 929:
        ph = max(safe_float(met.get("premarket_high"), 0.0), lp)
        pl_prev = safe_float(met.get("premarket_low"), 0.0)
        pl = min(pl_prev, lp) if pl_prev > 0.0 else lp
        p_amp = ((ph - pl) / pl) * 100.0 if pl > 0.0 else 0.0
        met["premarket_high"] = round(ph, 4)
        met["premarket_low"] = round(pl, 4)
        met["premarket_amp_pct"] = round(p_amp, 2)
        met["premarket_est_high"] = round(max(ph, pl * (1.0 + amp_ratio)), 2)
        met["premarket_est_low"] = round(min(pl, ph / (1.0 + amp_ratio)), 2)
        if safe_float(met.get("premarket_vwap"), 0.0) <= 0.0:
            met["premarket_vwap"] = round(lp, 4)
        met["vwap"] = met["premarket_vwap"]
    elif lp > 0.0 and 930 <= hm <= 1600:
        rh = max(safe_float(met.get("regular_high"), 0.0), lp)
        rl_prev = safe_float(met.get("regular_low"), 0.0)
        rl = min(rl_prev, lp) if rl_prev > 0.0 else lp
        r_amp = ((rh - rl) / rl) * 100.0 if rl > 0.0 else 0.0
        met["regular_high"] = round(rh, 4)
        met["regular_low"] = round(rl, 4)
        met["regular_amp_pct"] = round(r_amp, 2)
        met["regular_est_high"] = round(max(rh, rl * (1.0 + amp_ratio)), 2)
        met["regular_est_low"] = round(min(rl, rh / (1.0 + amp_ratio)), 2)
        if safe_float(met.get("regular_vwap"), 0.0) <= 0.0:
            met["regular_vwap"] = round(lp, 4)
        met["vwap"] = met["regular_vwap"]

    if safe_float(met.get("vwap"), 0.0) <= 0.0 and lp > 0.0:
        met["vwap"] = round(
            safe_float(met.get("day_vwap"), lp),
            4,
        )

    met["bucket_10m"] = cur_bucket_id
    met["is_new_cycle_cutoff"] = is_late_regular_new_cycle_cutoff_window(
        hm, now_est=dt_now
    )
    met["next_gate_hm_str"] = gate_info.get("next_gate_hm_str", "04:07 EST")
    met["session_label"] = gate_info.get("session_label", "")
    met["updated_est"] = dt_now.strftime("%m-%d %H:%M:%S EST")
    return met


# 하위 호환 별칭 (타 모듈 임포트 호환 100% 보장)
compute_quant_metrics_1m = compute_soxl_quant_metrics_1m
calculate_soxl_quant_metrics_1m = compute_soxl_quant_metrics_1m
is_weekend_closed = is_weekend_nyse_closed
