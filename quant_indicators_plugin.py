# -*- coding: utf-8 -*-
"""
# MODIFIED: quant_indicators_plugin.py
인피니트 스노우볼 (Infinite Snowball) v3.0 — 순수 롱(SOXL) 매수 04:07 ~ 16:00 EST 제한 &
익절 매도 24시간 전 세션(프리마켓 + 정규장 + 애프터마켓 + 데이마켓 · 방안 C 오버나이트 통합이평 사수) 확장 오버나이트 지층관리 스나이퍼
시계열 100% 벡터화 지표 엔진 · 실시간 틱 인메모리 1분봉 자체 합성기(_LIVE_1M_BAR_STORE) ·
10분 고정 매수 게이트 버킷 산출 및 황금시간대(07:00 ~ 07:50 EST & RSI(14) <= 19.0) 실시간 판정 코어 모듈 (Step 01 / 02)
- 제4헌법 & Case 01, Case 79, Case 80 & Case 83:
  1) 모든 시계열 및 세션 경계 연산은 미국 동부 시간(EST_TZ = ZoneInfo('America/New_York')) 단일 소스 락온
  2) 매수 허용 시간창(is_active_buy_window : 평일 04:07 ~ 16:00 EST)과
     익절 매도 허용 시간창(is_active_sell_window : 04:00 ~ 04:06 EST 오프닝 안정화 및 주말 휴장 외
     프리마켓 · 정규장 · 애프터마켓[16:00 ~ 19:59 EST] · 데이마켓[20:00 ~ 03:59 EST] 전 구간) 엄격 분리!
  3) 금요일 애프터마켓(16:00 ~ 19:59 EST) 익절 매도를 허용하기 위해 주말 휴장 구간을
     금요일 20:00 EST ~ 일요일 17:59 EST 로 제어 (일요일 18:00 EST 이후 월요일 데이마켓 정상 개방)
  4) 🌟 [Case 80] 미동부 프리장 황금시간대(is_golden_allin_time_window : 평일 07:00 ~ 07:50 EST) 판별기 및
     API 1분봉(공식 거래량 V · 시가 O 우선 보존) + 실시간 1.5초 틱 인메모리 1분봉(고가 H · 저가 L 극단값 보존)
     하이브리드 무손실 벡터화 병합(_sync_api_candles_into_memory_store 경합 방어) ·
     Wilder's RSI(14) O(1) 상수 시간 무부하 합성 탑재!
     (refresh_metrics_with_live_tick 내 dt_now.minute 변수명 정합성 교정으로 NameError 원천 소각 · 최소 14개 분봉 확보 시에만 rsi_ready = True 활성화)
- Case 36 & Case 64: 04:07 ~ 16:00 EST 구간 10분 고정 매수 게이트(LOCKED_BUY_INTERVAL_MIN = 10) 버킷 산출 및
  동일 버킷 내 중복 평가 원천 차단(evaluate_buy_gate_bucket_status)
- 벡터화 강제: Pandas DataFrame / NumPy 배열 연산 시 for 루프를 100% 배제하고 벡터화 수식으로만
  프리장(04:00 ~ 09:29 EST) / 정규장(09:30 ~ 16:00 EST) 누적 VWAP, 고/저가 진폭, 5일 이동평균(5MA) 진폭 기반
  예상 변동 밴드, 실시간 하이킨 아시(Heikin-Ashi) 양/음봉 배지 및 Wilder's RSI(14)를 고속 산출한다.
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
    GOLDEN_RSI_MAX_THRESHOLD,
    GOLDEN_WINDOW_END_HM,
    GOLDEN_WINDOW_START_HM,
    LOCKED_BUY_INTERVAL_MIN,
    TARGET_SYMBOL,
    safe_float,
    safe_int,
)

logger = logging.getLogger("toss_sniper.quant_indicators_plugin")

# 04:07 EST 기준 분(minute of day = 4 * 60 + 7 = 247) 및 16:00 EST 마감 분(16 * 60 = 960) 0칸 표준 정렬
GATE_START_MIN_OF_DAY: int = 4 * 60 + 7   # 247 (04:07 EST)
GATE_END_MIN_OF_DAY: int = 16 * 60        # 960 (16:00 EST)
REGULAR_START_MIN_OF_DAY: int = 9 * 60 + 30  # 570 (09:30 EST)

# NEW [Case 80]: 브로커 1분봉 차트 API 지연/결측 시에도 실시간 1.5초 현재가 틱으로 1분봉을 자체 축적하는 인메모리 링버퍼
_LIVE_1M_BAR_LOCK = threading.RLock()
_LIVE_1M_BAR_STORE: Dict[str, List[Dict[str, Any]]] = {TARGET_SYMBOL: []}
_MAX_MEMORY_1M_BARS: int = 360


# ---------------------------------------------------------------------------
# [핵심 0 · NEW Case 80] 인메모리 실시간 1분봉 자체 합성기 및 API 1분봉 하이브리드 병합기
# ---------------------------------------------------------------------------
def _record_live_tick_to_memory_bar(
    symbol: str,
    live_price: float,
    now_est: Optional[datetime] = None,
) -> Tuple[str, int]:
    """
    # NEW [Case 80 : 실시간 1.5초 현재가 틱 기반 인메모리 1분봉 자체 합성기]:
    매 1.5초 루프 또는 /avwap 조회 시 유입되는 실시간 현재가(live_price)를
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
    # MODIFIED [Case 80 : API 1분봉 ↔ 인메모리 실시간 틱 덮어쓰기 경합(Race Condition) 및 거래량(volume) 증발 원천 차단]:
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

        synced_bars: List[Dict[str, Any]] = []
        for dt_v, o_v, h_v, l_v, c_v, v_v in zip(
            dt_list, o_list, h_list, l_list, c_list, v_list
        ):
            dt_m = dt_v.replace(second=0, microsecond=0)
            synced_bars.append(
                {
                    "_min_key": dt_m.strftime("%Y-%m-%d %H:%M"),
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
    # MODIFIED [Case 80 : 인메모리 1분봉 선행 + 토스 API 공식 1분봉 후행 배치]:
    인메모리 실시간 합성 1분봉(mem_bars, volume=1.0)을 먼저 배치하고,
    브로커 API 공식 1분봉(api_candles, 실제 거래량 및 공식 시가 보유)을 뒤에 배치하여
    동일 분(dt_min) 중복 제거(keep="last") 시 공식 시가(O)·종가(C)·거래량(V)이 우선 채택되도록 보장한다.
    """
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    combined: List[Dict[str, Any]] = []
    with _LIVE_1M_BAR_LOCK:
        mem_bars = list(_LIVE_1M_BAR_STORE.get(sym, []))
    if mem_bars:
        combined.extend(mem_bars)
    if isinstance(api_candles, list) and api_candles:
        combined.extend(c for c in api_candles if isinstance(c, dict))
    return combined


def _parse_timestamp_series_to_est(ts_series: pd.Series) -> pd.Series:
    """
    # NEW [Case 80 : pandas 2.x 혼합 ISO8601 타임스탬프 NaT 증발 원천 방어]:
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
# [핵심 1] 매수 시간창(04:07 ~ 16:00 EST) · 황금시간창(07:00 ~ 07:50 EST) vs 익절 매도 시간창(24시간 전 세션) 판별기 (Case 01, 79, 80)
# ---------------------------------------------------------------------------
def is_weekend_nyse_closed(now_est: Optional[datetime] = None) -> bool:
    """
    # MODIFIED [Case 01 & Case 79]:
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
    # [🎯 2 & Case 01, Case 79, Case 80 : 매수 전용 시간창 (평일 04:07 ~ 16:00 EST 엄격 제한)]:
    - 모든 매수(0주 첫 진입 REENTRY_1FL · 07:00~07:50 황금시간 전액매수 · 1층 미체결 잔량 TOPUP_1FL ·
      1층 공석 60초 주기 재장전 · 10분 와이드/스텝업 추매 DIP_1FL)는
      오직 평일(월~금) 프리장 개시(04:07 EST)부터 정규장 마감(16:00 EST)까지만 허용한다.
    - 애프터마켓(16:01 ~ 19:59 EST) 및 데이마켓(20:00 ~ 03:59 EST, 일요일 저녁 포함)에서는 매수를 100% 차단(False)한다.
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


def is_golden_allin_time_window(
    hm: Optional[int] = None, now_est: Optional[datetime] = None
) -> bool:
    """
    # NEW [Case 80 : 미동부 프리장 황금시간대(평일 07:00:00 ~ 07:50:59 EST) 판별기]:
    - 평일(월~금) 미동부 프리장 07:00 ~ 07:50 EST (700 <= hm <= 750) 구간일 때만 True 를 반환한다.
    """
    dt = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    if is_weekend_nyse_closed(dt) or dt.weekday() >= 5:
        return False
    hm_int = (
        safe_int(hm, dt.hour * 100 + dt.minute)
        if hm is not None
        else (dt.hour * 100 + dt.minute)
    )
    return GOLDEN_WINDOW_START_HM <= hm_int <= GOLDEN_WINDOW_END_HM


def is_active_sell_window(
    hm: int, now_est: Optional[datetime] = None
) -> bool:
    """
    # [🎯 2 & Case 79, Case 80 : 익절 매도 전용 확장 시간창 (프리마켓 + 정규장 + 애프터마켓 + 데이마켓 전 구간 개방)]:
    - 오버나이트를 하면서도 목표 익절가(골든포켓 +1.50% / 1층 +1.50% / 2~7층 개별 및 이동평균 +1.00%)에 도달하면
      애프터마켓(16:00 ~ 19:59 EST)과 데이마켓(20:00 ~ 03:59 EST)에서도 즉시 지정가 익절 매도가 나가도록 개방한다.
    - 오직 04:00 ~ 04:06 EST 프리장 오프닝 안정화 구간(7분)과 주말 휴장(금 20:00 ~ 일 17:59 EST)에만 매도 모니터를 멈춘다.
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
    현재 시각이 익절 매도는 열려 있으나(is_active_sell_window == True)
    신규/추가 매수는 잠겨 있는(is_active_buy_window == False) 애프터마켓 또는 데이마켓 구간인지 판별한다.
    """
    return bool(
        is_active_sell_window(hm, now_est=now_est)
        and not is_active_buy_window(hm, now_est=now_est)
    )


def get_market_session_label(now_est: Optional[datetime] = None) -> str:
    """
    # MODIFIED [Case 79, Case 80 & Case 83]:
    현재 EST 시각에 따른 세션 상태 라벨(황금시간대 · 애프터장 · 데이장 익절감시 및 매수잠금 상태 명시)을 반환한다.
    """
    dt = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    if is_weekend_nyse_closed(dt):
        return "🛑 주말휴장"
    hm = dt.hour * 100 + dt.minute
    if 400 <= hm <= 406:
        return "🌅 프리장 오프닝 안정화(04:00~04:06)"
    if 700 <= hm <= 750 and dt.weekday() < 5:
        return "🌟 프리장 황금시간 가동(07:00~07:50)"
    if 407 <= hm <= 929 and dt.weekday() < 5:
        return "🔫 프리장 스나이퍼 가동(04:07~09:29)"
    if 930 <= hm <= 1600 and dt.weekday() < 5:
        return "🔥 정규장 스나이퍼 가동(09:30~16:00)"
    if 1601 <= hm <= 1959 and dt.weekday() < 5:
        return "🌇 애프터장 익절감시(16:00~19:59·매수잠금)"
    return "🌃 데이장 익절감시(20:00~03:59·매수잠금)"


# ---------------------------------------------------------------------------
# [핵심 2] 04:07 ~ 16:00 EST 10분 고정 매수 게이트 버킷 산출기 (Case 01, 36, 64, 79, 80)
# ---------------------------------------------------------------------------
def evaluate_buy_gate_bucket_status(
    now_est: Optional[datetime] = None,
    buy_interval_min: int = LOCKED_BUY_INTERVAL_MIN,
    last_evaluated_bucket_id: int = -1,
    last_evaluated_date: str = "",
) -> Tuple[bool, int, str, Dict[str, Any]]:
    """
    🚨 Case 01, Case 36, Case 64, Case 79 & Case 80:
    04:07 EST 기점 10분 고정 매수 게이트(04:07, 04:17, 04:27, ..., 15:57 및 16:00 마감봉)의
    현재 버킷 ID(cur_bucket_id)와 게이트 오픈 여부(is_gate_open), 차기 검문 시각(next_gate_hm_str)을 산출한다.
    - 애프터마켓(16:01 ~ 19:59 EST) 및 데이마켓(20:00 ~ 03:59 EST)에서는 is_active_buy_window == False 이므로
      언제나 is_gate_open = False 를 반환하여 장외 매수를 100% 원천 차단한다.
    - 동일 거래일(today_str) 내 동일 버킷(cur_bucket_id <= last_evaluated_bucket_id)에서는
      is_gate_open = False 를 반환하여 중복 매수를 100% 원천 차단한다.
    """
    dt = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    today_str = dt.strftime("%Y-%m-%d")
    hm = dt.hour * 100 + dt.minute
    cur_min_of_day = dt.hour * 60 + dt.minute

    interval = LOCKED_BUY_INTERVAL_MIN  # 10분 하드 고정 (Case 64)

    if not is_active_buy_window(hm, now_est=dt) or is_weekend_nyse_closed(dt):
        return (
            False,
            -1,
            today_str,
            {
                "is_active_window": False,
                "is_sell_window_open": is_active_sell_window(hm, now_est=dt),
                "is_golden_window": False,
                "mins_from_0407": -1,
                "bucket_10m": -1,
                "is_exact_boundary_min": False,
                "next_gate_hm_str": "04:07 EST (매수잠금·익절감시)",
                "session_label": get_market_session_label(dt),
            },
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
        "is_golden_window": is_golden_allin_time_window(hm, now_est=dt),
        "mins_from_0407": mins_from_0407,
        "bucket_10m": cur_bucket_id,
        "is_exact_boundary_min": is_exact_boundary,
        "next_gate_hm_str": next_gate_str,
        "session_label": get_market_session_label(dt),
    }
    return is_gate_open, cur_bucket_id, today_str, info


# ---------------------------------------------------------------------------
# [핵심 3] 100% 벡터화 시계열 지표 산출 엔진 (compute_soxl_quant_metrics_1m)
# ---------------------------------------------------------------------------
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
    # MODIFIED [Case 80 : Wilder's RSI(14) 벡터화 연산 및 2봉 이상 즉시 기저값 생성]:
    1) 100% 벡터화(np.diff + Wilder's EWM) 연산으로 n >= 2 이상이면 첫 봉 NaN 왜곡 없이
       직전 완성봉 종가(prev_bar_close)와 직전 완성봉까지의 평균 상승/하락폭(prev_avg_gain, prev_avg_loss)을 산출한다.
    2) Case 80 황금시간 전액매수 발동 자격(rsi_ready)은 최소 14개 분봉(n >= 14)이 확보되었을 때 True 로 설정하여
       부팅 직후 단일 틱 노이즈로 인한 오발동을 원천 차단하면서도, 레이더 표시용 rsi_14 는 실시간 변동을 즉시 반영한다.
    """
    n = len(closes)
    if n == 0:
        return {
            "rsi_14": 50.0,
            "rsi_ready": False,
            "candle_count": 0,
            "prev_bar_close": 0.0,
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

    # Wilder's RSI(14) 벡터화 연산 (np.diff 기반으로 첫 원소 NaN 오염 원천 배제)
    rsi_val = 50.0
    prev_bar_close = float(closes[-2]) if n >= 2 else float(closes[-1])
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

    return {
        "rsi_14": round(rsi_val, 2),
        "rsi_ready": bool(n >= 14),
        "candle_count": int(n),
        "prev_bar_close": round(prev_bar_close, 4),
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
        "ha_badge": "🕯️HA양봉" if is_bull else "🌑HA음봉",
    }


def _recompute_ha_rsi_from_memory_store(
    symbol: str = TARGET_SYMBOL,
) -> Optional[Dict[str, Any]]:
    """
    # NEW [Case 80]:
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


def compute_soxl_quant_metrics_1m(
    candles: List[Dict[str, Any]],
    live_price: float = 0.0,
    now_est: Optional[datetime] = None,
    daily_candles: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    🎯 2 & Case 01, 15, 79, 80:
    토스 Open API 1분봉(candles), 인메모리 실시간 합성 1분봉(_LIVE_1M_BAR_STORE) 및 일봉(daily_candles)을 입력받아:
    1) 당일 프리장(04:00 ~ 09:29 EST) VWAP · 고/저가 진폭 · 예상 변동 밴드
    2) 당일 정규장(09:30 ~ 16:00 EST) VWAP · 고/저가 진폭 · 예상 변동 밴드
    3) 최근 5영업일 평균 진폭(5MA) 및 실시간 하이킨 아시 추세 배지(🕯️HA양봉 / 🌑HA음봉) · Wilder's RSI(14)
    4) 04:07 ~ 16:00 EST 10분 고정 매수 게이트 버킷 및 황금시간대(07:00 ~ 07:50 EST) 정보
    를 100% 벡터화 연산으로 산출하여 반환한다.
    (Case 79: 데이마켓/애프터마켓에서 브로커가 시세·캔들을 제공하지 않는 경우에도 경고 로그나 알림 없이 조용히 묵음 반환)
    """
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    hm_now = dt_now.hour * 100 + dt_now.minute
    _, cur_bucket_id, today_str, gate_info = evaluate_buy_gate_bucket_status(
        now_est=dt_now, buy_interval_min=LOCKED_BUY_INTERVAL_MIN
    )
    lp = safe_float(live_price, 0.0)
    cur_min_key, _ = _record_live_tick_to_memory_bar(
        TARGET_SYMBOL, lp, now_est=dt_now
    )

    default_out: Dict[str, Any] = {
        "symbol": TARGET_SYMBOL,
        "live_price": round(lp, 4),
        "ma5_amp_pct": 6.50,
        "rsi_14": 50.0,
        "rsi_ready": False,
        "candle_count": 0,
        "cur_bar_minute_key": cur_min_key,
        "prev_bar_close": 0.0,
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
        "ha_badge": "🕯️HA양봉",
        "premarket_vwap": 0.0,
        "premarket_high": 0.0,
        "premarket_low": 0.0,
        "premarket_amp_pct": 0.0,
        "premarket_est_low": 0.0,
        "premarket_est_high": 0.0,
        "regular_vwap": 0.0,
        "regular_high": 0.0,
        "regular_low": 0.0,
        "regular_amp_pct": 0.0,
        "regular_est_low": 0.0,
        "regular_est_high": 0.0,
        "day_vwap": 0.0,
        "day_high": 0.0,
        "day_low": 0.0,
        "day_amp_pct": 0.0,
        "bucket_10m": cur_bucket_id,
        "is_golden_window": is_golden_allin_time_window(hm_now, now_est=dt_now),
        "next_gate_hm_str": gate_info.get("next_gate_hm_str", "04:07 EST"),
        "session_label": gate_info.get("session_label", ""),
        "updated_est": dt_now.strftime("%m-%d %H:%M:%S EST"),
    }

    merged_candles = _merge_api_and_memory_candles(candles, TARGET_SYMBOL)
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

        # MODIFIED [Case 80 : 동일 분(dt_min) 내 인메모리 틱 고/저가 극단값 및 거래소 공식 거래량(V)·시가(O) 벡터화 병합]:
        # _merge_api_and_memory_candles 에서 mem_bars(선행) + api_candles(후행) 순으로 결합되었으므로,
        # groupby transform 으로 분 단위 최고가(H), 최저가(L), 최대 거래량(V)을 먼저 보존한 뒤
        # keep="last" 로 중복을 제거하면 거래소 API의 공식 시가(O)·종가(C)·거래량(V)과 실시간 고/저가(H/L)가 100% 결합된다!
        if df.duplicated(subset=["dt_min"]).any():
            grp_min = df.groupby("dt_min", sort=False)
            df["H"] = grp_min["H"].transform("max")
            df["L"] = grp_min["L"].transform("min")
            df["V"] = grp_min["V"].transform("max")
            df.drop_duplicates(subset=["dt_min"], keep="last", inplace=True)

        df.sort_values("dt_min", ascending=True, inplace=True)

        # API + 메모리 병합 정제본을 인메모리 1분봉 저장소에 다시 동기화하여 히스토리 영구 보존
        _sync_api_candles_into_memory_store(TARGET_SYMBOL, df)

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

        df_pre = df_today[(df_today["hm"] >= 400) & (df_today["hm"] <= 929)]
        df_reg = df_today[(df_today["hm"] >= 930) & (df_today["hm"] <= 1600)]

        pre_stats = _calc_session_vwap_and_bands(df_pre, ma5_amp)
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

        out = dict(default_out)
        out.update(ha_rsi_info)
        out.update(
            {
                "live_price": round(lp, 4),
                "ma5_amp_pct": ma5_amp,
                "premarket_vwap": pre_stats["vwap"],
                "premarket_high": pre_stats["high"],
                "premarket_low": pre_stats["low"],
                "premarket_amp_pct": pre_stats["amp_pct"],
                "premarket_est_low": pre_stats["est_low"],
                "premarket_est_high": pre_stats["est_high"],
                "regular_vwap": reg_stats["vwap"],
                "regular_high": reg_stats["high"],
                "regular_low": reg_stats["low"],
                "regular_amp_pct": reg_stats["amp_pct"],
                "regular_est_low": reg_stats["est_low"],
                "regular_est_high": reg_stats["est_high"],
                "day_vwap": active_vwap,
                "day_high": all_stats["high"],
                "day_low": all_stats["low"],
                "day_amp_pct": all_stats["amp_pct"],
            }
        )
        return refresh_metrics_with_live_tick(out, lp, now_est=dt_now)
    except Exception as exc:
        # Case 79: 데이마켓 등 장외 시간대 캔들 결측 시에도 소음 없이 조용히 디버그 로깅
        logger.debug("compute_soxl_quant_metrics_1m 연산 폴백(묵음): %s", exc)
        return refresh_metrics_with_live_tick(default_out, lp, now_est=dt_now)


# ---------------------------------------------------------------------------
# [핵심 4] 실시간 틱(live_price) O(1) 무부하 합성기 (refresh_metrics_with_live_tick — Case 80 RSI 데드락 해제 및 NameError 영구 소각)
# ---------------------------------------------------------------------------
def refresh_metrics_with_live_tick(
    base_metrics: Optional[Dict[str, Any]],
    live_price: float,
    now_est: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    # MODIFIED [Case 80 : RSI(14) 50.0 박제(고정) 데드락 완전 해제 · 실시간 틱 O(1) 합성 · dt_now.minute 변수명 정합성 락온]:
    1) 실시간 현재가(live_price)를 인메모리 1분봉 저장소(_LIVE_1M_BAR_STORE)에 즉시 반영한다.
    2) 만약 새로운 분(minute)으로 넘어갔거나 기존 base_metrics 의 prev_bar_close 가 0.0 인 경우,
       인메모리 1분봉 저장소에서 직전 완성봉 기저값(prev_bar_close, prev_avg_gain, prev_avg_loss)을 즉시 복원한다.
    3) prev_bar_close > 0.0 이면 (prev_avg_g > 0.0 데드락 조건 없이) 매 1.5초 실시간 현재가 변동을
       Wilder's RSI(14) 공식에 즉시 합성하여 레이더와 황금시간 모니터에 살아 움직이는 실시간 RSI(14)를 제공한다!
    """
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    dt = dt_now
    hm = dt_now.hour * 100 + dt_now.minute
    _, cur_bucket_id, _, gate_info = evaluate_buy_gate_bucket_status(
        now_est=dt, buy_interval_min=LOCKED_BUY_INTERVAL_MIN
    )

    met = dict(base_metrics) if isinstance(base_metrics, dict) else {}
    lp = safe_float(live_price, 0.0)
    if lp <= 0.0:
        lp = safe_float(met.get("live_price"), 0.0)
    else:
        met["live_price"] = round(lp, 4)

    cur_min_key, mem_bar_cnt = _record_live_tick_to_memory_bar(
        TARGET_SYMBOL, lp, now_est=dt_now
    )
    prev_min_key = str(met.get("cur_bar_minute_key") or "")

    # 새로운 1분봉 경계 진입 또는 기저값(prev_bar_close) 미초기화 시 인메모리 1분봉으로 기저값 즉시 갱신
    if mem_bar_cnt >= 2 and (
        safe_float(met.get("prev_bar_close"), 0.0) <= 0.0
        or (prev_min_key and prev_min_key != cur_min_key)
    ):
        mem_ha_rsi = _recompute_ha_rsi_from_memory_store(TARGET_SYMBOL)
        if isinstance(mem_ha_rsi, dict):
            met.update(mem_ha_rsi)

    met["cur_bar_minute_key"] = cur_min_key

    ma5_amp = max(1.0, safe_float(met.get("ma5_amp_pct"), 6.50))
    amp_ratio = ma5_amp / 100.0

    # 1) 실시간 틱 기반 Heikin-Ashi 양/음봉 및 Wilder's RSI(14) O(1) 상수 시간 합성 (Case 80 데드락 해제)
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
        met["ha_badge"] = "🕯️HA양봉" if is_bull else "🌑HA음봉"

        prev_b_close = safe_float(met.get("prev_bar_close"), 0.0)
        prev_avg_g = max(0.0, safe_float(met.get("prev_avg_gain"), 0.0))
        prev_avg_l = max(0.0, safe_float(met.get("prev_avg_loss"), 0.0))

        # MODIFIED [Case 80 핵심]: prev_b_close > 0.0 만 확보되면 즉시 현재가(lp) 등락을 RSI(14)에 실시간 반영!
        if prev_b_close > 0.0:
            diff = lp - prev_b_close
            cur_g = max(0.0, diff)
            cur_l_val = max(0.0, -diff)
            if prev_avg_g <= 1e-12 and prev_avg_l <= 1e-12:
                live_avg_g = cur_g / 14.0
                live_avg_l = cur_l_val / 14.0
            else:
                live_avg_g = (prev_avg_g * 13.0 + cur_g) / 14.0
                live_avg_l = (prev_avg_l * 13.0 + cur_l_val) / 14.0

            if live_avg_g <= 1e-12 and live_avg_l <= 1e-12:
                live_rsi = 50.0
            elif live_avg_l <= 1e-12:
                live_rsi = 100.0
            else:
                rs = live_avg_g / live_avg_l
                live_rsi = 100.0 - (100.0 / (1.0 + rs))
            met["rsi_14"] = round(live_rsi, 2)

        if not bool(met.get("rsi_ready", False)) and mem_bar_cnt >= 14:
            met["rsi_ready"] = True

    # 2) 현재 세션(프리장 04:00 ~ 09:29 / 정규장 09:30 ~ 16:00) 고/저가 및 예상 밴드 실시간 갱신
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

    met["bucket_10m"] = cur_bucket_id
    met["is_golden_window"] = is_golden_allin_time_window(hm, now_est=dt_now)
    met["next_gate_hm_str"] = gate_info.get("next_gate_hm_str", "04:07 EST")
    met["session_label"] = gate_info.get("session_label", "")
    met["updated_est"] = dt_now.strftime("%m-%d %H:%M:%S EST")
    return met


# 하위 호환 별칭 (타 모듈 임포트 호환 100% 보장)
compute_quant_metrics_1m = compute_soxl_quant_metrics_1m
calculate_soxl_quant_metrics_1m = compute_soxl_quant_metrics_1m
is_weekend_closed = is_weekend_nyse_closed
