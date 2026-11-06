# -*- coding: utf-8 -*-
"""
# MODIFIED: quant_indicators_plugin.py (Case 92 1층 공석 돌파 RSI<=50 실시간 합성기 · Case 93 암살자 4대 지표 및 QQQ 방향성 3단 안전망 벡터 지표 · 장 마감 후 프리시가/프리VWAP 정규장 오염 제거 및 $0.00 정합성 패치)
인피니트 스노우볼 (Infinite Snowball) v3.0 — 순수 롱(SOXL) 매수 04:07 ~ 16:00 EST 제한
(정규장 마감 30분 전 15:30 ~ 16:00 EST 본·서브 그리드 0주 새 사이클 첫 1층 진입 및 상단층 보유 중 1층 공석 +1.0% 돌파 추격 동시 차단 ·
04:07 ~ 15:29 EST 1층 공석 +1.0% 돌파 시 1분봉 Wilder RSI(14) <= 50.0 필터 결합 ·
2층 단가 이하 -1.0% 무필터 눌림목 재장전 및 10분 게이트 무필터 추매/잔량보충 100% 허용 · Case 84, Case 88, Case 92) &
익절 매도 24시간 전 세션(프리마켓 + 정규장 + 애프터마켓 + 데이마켓 · 방안 C 오버나이트 통합이평 사수) 확장 오버나이트 지층관리 스나이퍼 +
🗡️ 스나이퍼와 100% 격리된 [모의 ⇄ 실전 Dual-Ready] 암살자(Assassin · Case 93) 전용
시계열 100% 벡터화 지표 엔진 · 실시간 틱 인메모리 1분봉 자체 합성기(_LIVE_1M_BAR_STORE) 및
10분 고정 매수 게이트 버킷 산출(본 그리드 및 Default-ON 3층 서브 그리드 독립 평가 지원) 코어 모듈 (Step 03 / 14)
- 제4헌법 & Case 01, Case 79, Case 83, Case 84, Case 88, Case 92 & Case 93:
  1) 모든 시계열 및 세션 경계 연산은 미국 동부 시간(EST_TZ = ZoneInfo('America/New_York')) 단일 소스 락온
  2) 매수 허용 시간창(is_active_buy_window : 평일 04:07 ~ 16:00 EST)과
     익절 매도 허용 시간창(is_active_sell_window : 04:00 ~ 04:06 EST 오프닝 안정화 및 주말 휴장 외
     프리마켓 · 정규장 · 애프터마켓[16:00 ~ 19:59 EST] · 데이마켓[20:00 ~ 03:59 EST] 전 구간) 엄격 분리!
  3) 금요일 애프터마켓(16:00 ~ 19:59 EST) 익절 매도를 허용하기 위해 주말 휴장 구간을
     금요일 20:00 EST ~ 일요일 17:59 EST 로 제어 (일요일 18:00 EST 이후 월요일 데이마켓 정상 개방)
  4) API 1분봉(공식 거래량 V · 시가 O 우선 보존) + 실시간 1.5초 틱 인메모리 1분봉(고가 H · 저가 L 극단값 보존)
     하이브리드 무손실 벡터화 병합(_sync_api_candles_into_memory_store 경합 방어) ·
     Wilder's RSI(14) O(1) 상수 시간 무부하 합성(compute_realtime_synthetic_rsi · Case 92) 탑재!
  5) 🛡️ [Case 84 & Case 88] 정규장 마감 30분 전(is_late_regular_new_cycle_cutoff_window : 평일 15:30 ~ 16:00 EST) 판별기 탑재
  6) 🗡️ [Case 93] 암살자 4대 핵심 지표(① 1분봉 Wilder RSI(14) · ② 당일 04:07 이후 프리장 누적 VWAP 및 괴리율% ·
     ③ 전일 정규장 종가 prev_reg_close 및 등락률% · ④ 당일 04:07 프리장 시가 pre_open_price 및 등락률%) 및
     나스닥 100 대리변수 QQQ 단기 변화율(vel_1m_pct, vel_3m_pct, vel_10m_pct, bear_drop_amp_pct) 벡터 산출기(compute_qqq_macro_metrics_1m) 탑재!
     - 특히 장 마감 후 1분봉 윈도우(300봉)에서 프리장(04:00 ~ 09:29 EST) 봉이 밀려났을 때
       정규장 시가($48.70)나 정규장 VWAP($45.43)로 가짜 폴백하여 프리장 지표를 오염시키는 행위를 100% 금지하고,
       당일 프리장 중 박제된 스냅샷(_DAILY_PREMARKET_SNAPSHOT_CACHE)이 있으면 이를 보존하고 없으면 정확히 0.0($0.00)을 반환한다!
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

# 브로커 1분봉 차트 API 지연/결측 시에도 실시간 1.5초 현재가 틱으로 1분봉을 자체 축적하는 인메모리 링버퍼 (SOXL 및 QQQ 다중 심볼 지원)
_LIVE_1M_BAR_LOCK = threading.RLock()
_LIVE_1M_BAR_STORE: Dict[str, List[Dict[str, Any]]] = {
    TARGET_SYMBOL: [],
    "QQQ": [],
}
_MAX_MEMORY_1M_BARS: int = 420

# # NEW [Case 93 프리장 지표 무오염 보존 스냅샷 캐시]:
# 당일 프리장(04:00 ~ 09:29 EST) 실제 1분봉에서 계측된 pre_open_price 및 premarket_vwap 을 (symbol, date_str) 키로 박제하여,
# 오후장/장마감 후 API 300봉 윈도우에서 프리장 봉이 밀려나더라도 당일 프리장 진성 수치를 보존한다.
# (단, 프리장 이후에 봇을 처음 켜서 캐시가 비어 있을 때는 정규장 값으로 오염시키지 않고 0.0 을 반환한다!)
_DAILY_PREMARKET_SNAPSHOT_CACHE: Dict[Tuple[str, str], Dict[str, float]] = {}


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

        # 프리장 개장(04:07 ~ 09:29 EST) 중 실시간 틱이 들어왔는데 아직 당일 pre_open_price 캐시가 없다면 첫 틱을 박제
        hm_now = dt.hour * 100 + dt.minute
        if 407 <= hm_now <= 929:
            today_s = dt.strftime("%Y-%m-%d")
            snap_key = (sym, today_s)
            snap = _DAILY_PREMARKET_SNAPSHOT_CACHE.setdefault(snap_key, {})
            if safe_float(snap.get("pre_open_price"), 0.0) <= 0.0:
                snap["pre_open_price"] = lp

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
    인메모리 1분봉 선행 + 토스 API 공식 1분봉 후행 배치:
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
    - 본 그리드 및 서브 그리드의 모든 매수는 오직 평일(월~금) 프리장 개시(04:07 EST)부터 정규장 마감(16:00 EST)까지만 허용한다.
    - 애프터마켓(16:01 ~ 19:59 EST) 및 데이마켓(20:00 ~ 03:59 EST)에서는 매수를 100% 차단(False)한다.
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
    하위 호환 심볼 유지: is_active_buy_window(04:07 ~ 16:00 EST)와 동일하게 작동한다.
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
) -> Tuple[bool, int, str, Dict[str, Any]]:
    """
    🚨 Case 01, Case 36, Case 64, Case 79, Case 84 & Case 88:
    04:07 EST 기점 10분 고정 매수 게이트(04:07, 04:17, 04:27, ..., 15:57 및 16:00 마감봉)의
    현재 버킷 ID(cur_bucket_id)와 게이트 오픈 여부(is_gate_open), 차기 검문 시각(next_gate_hm_str)을 산출한다.
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
                "is_new_cycle_cutoff": False,
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
        "is_new_cycle_cutoff": is_late_regular_new_cycle_cutoff_window(
            hm, now_est=dt
        ),
        "mins_from_0407": mins_from_0407,
        "bucket_10m": cur_bucket_id,
        "is_exact_boundary_min": is_exact_boundary,
        "next_gate_hm_str": next_gate_str,
        "session_label": get_market_session_label(dt),
    }
    return is_gate_open, cur_bucket_id, today_str, info


# ---------------------------------------------------------------------------
# [핵심 3] 100% 벡터화 시계열 지표 산출 엔진 & 실시간 Wilder RSI(14) 합성기 (Case 92 & Case 93)
# ---------------------------------------------------------------------------
def compute_realtime_synthetic_rsi(
    live_price: float,
    prev_bar_close: float,
    prev_avg_gain: float,
    prev_avg_loss: float,
    default_rsi: float = 50.0,
) -> float:
    """
    # NEW [Case 92 & Case 93 : 실시간 현재가(live_price) 기반 O(1) 상수 시간 Wilder's RSI(14) 합성기]:
    직전 완성봉 종가(prev_bar_close)와 직전 완성봉까지의 Wilder 평균 상승/하락폭(prev_avg_gain, prev_avg_loss)에
    현재 틱(live_price) 변동을 즉시 합성하여 API 호출 없이 살아 움직이는 실시간 1분봉 Wilder RSI(14)를 반환한다.
    """
    lp = safe_float(live_price, 0.0)
    prev_c = safe_float(prev_bar_close, 0.0)
    if lp <= 0.0 or prev_c <= 0.0:
        return round(safe_float(default_rsi, 50.0), 2)

    prev_g = max(0.0, safe_float(prev_avg_gain, 0.0))
    prev_l = max(0.0, safe_float(prev_avg_loss, 0.0))
    diff = lp - prev_c
    cur_g = max(0.0, diff)
    cur_l = max(0.0, -diff)

    if prev_g <= 1e-12 and prev_l <= 1e-12:
        live_avg_g = cur_g / 14.0
        live_avg_l = cur_l / 14.0
    else:
        live_avg_g = (prev_g * 13.0 + cur_g) / 14.0
        live_avg_l = (prev_l * 13.0 + cur_l) / 14.0

    if live_avg_g <= 1e-12 and live_avg_l <= 1e-12:
        return 50.0
    if live_avg_l <= 1e-12:
        return 100.0
    rs = live_avg_g / live_avg_l
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
# ---------------------------------------------------------------------------
# [핵심 3-B] 전일 정규장 종가(prev_reg_close) 및 당일 04:07 프리장 시가(pre_open_price) 무오염 추출기 (Case 93)
# ---------------------------------------------------------------------------
def _resolve_prev_reg_close_and_pre_open(
    symbol: str,
    today_str: str,
    daily_candles: Optional[List[Dict[str, Any]]],
    df_valid: pd.DataFrame,
    df_today: pd.DataFrame,
    df_pre: pd.DataFrame,
) -> Tuple[float, float]:
    """
    # NEW [Case 93 프리시가(pre_open_price) 정규장 시가($48.70) 오염 원천 차단]:
    1) prev_reg_close (전일 정규장 종가):
       - 일봉(daily_candles)에서 당일(today_str) 이전 가장 최근 영업일 종가(closePrice)를 최우선 추출하고,
         보조로 1분봉(df_valid) 내 당일 이전 날짜의 정규장(09:30 ~ 16:00 EST) 마지막 종가를 사용한다.
    2) pre_open_price (당일 04:07 EST 프리장 시가):
       - 오직 당일 프리장(04:00 ~ 09:29 EST) 1분봉(df_pre)이 실제로 존재할 때만
         04:07 EST 이후 첫 프리장 1분봉의 시가(O)를 추출하여 _DAILY_PREMARKET_SNAPSHOT_CACHE 에 영속 박제한다.
       - 만약 장 마감 후(또는 오후장) 재기동으로 인해 API 300봉 윈도우에 df_pre 가 없고
         _DAILY_PREMARKET_SNAPSHOT_CACHE 에도 당일 프리시가 기록이 없다면,
         절대로 일봉 시가(정규장 09:30 시가 $48.70)나 정규장 1분봉 시가로 폴백하지 않고 정확히 0.0 ($0.00)을 반환한다!
    """
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    snap_key = (sym, today_str)

    # 1. 전일 정규장 종가(prev_reg_close) 추출
    prev_reg_close: float = 0.0
    if isinstance(daily_candles, list) and len(daily_candles) >= 1:
        try:
            sorted_d: List[Tuple[str, float, float]] = []
            for item in daily_candles:
                if not isinstance(item, dict):
                    continue
                ts_raw = str(item.get("timestamp") or item.get("date") or "").strip()
                if not ts_raw:
                    continue
                d_str = ts_raw[:10]
                c_val = safe_float(item.get("closePrice"), 0.0)
                o_val = safe_float(item.get("openPrice"), 0.0)
                if c_val > 0.0:
                    sorted_d.append((d_str, o_val, c_val))
            if sorted_d:
                sorted_d.sort(key=lambda x: x[0])
                prev_candidates = [x for x in sorted_d if x[0] < today_str]
                if prev_candidates:
                    prev_reg_close = round(float(prev_candidates[-1][2]), 4)
                elif len(sorted_d) >= 2:
                    prev_reg_close = round(float(sorted_d[-2][2]), 4)
        except Exception:
            pass

    if prev_reg_close <= 0.0 and df_valid is not None and not df_valid.empty:
        try:
            df_prev_days = df_valid[df_valid["Date"] < today_str]
            if not df_prev_days.empty:
                df_prev_reg = df_prev_days[
                    (df_prev_days["HM"] >= 930) & (df_prev_days["HM"] <= 1600)
                ]
                if not df_prev_reg.empty:
                    prev_reg_close = round(
                        float(df_prev_reg["C"].iloc[-1]), 4
                    )
                else:
                    prev_reg_close = round(
                        float(df_prev_days["C"].iloc[-1]), 4
                    )
        except Exception:
            pass

    # 2. 당일 04:07 EST 프리장 시가(pre_open_price) 추출 (정규장 시가 폴백 100% 금지!)
    pre_open_price: float = 0.0
    if df_pre is not None and not df_pre.empty:
        try:
            df_pre_0407 = df_pre[df_pre["HM"] >= 407]
            if not df_pre_0407.empty:
                pre_open_price = round(float(df_pre_0407["O"].iloc[0]), 4)
            else:
                pre_open_price = round(float(df_pre["O"].iloc[0]), 4)
        except Exception:
            pre_open_price = 0.0

    with _LIVE_1M_BAR_LOCK:
        snap = _DAILY_PREMARKET_SNAPSHOT_CACHE.setdefault(snap_key, {})
        if pre_open_price > 0.0:
            snap["pre_open_price"] = pre_open_price
        else:
            cached_pre_open = safe_float(snap.get("pre_open_price"), 0.0)
            if cached_pre_open > 0.0:
                pre_open_price = round(cached_pre_open, 4)
            else:
                pre_open_price = 0.0

        if prev_reg_close > 0.0:
            snap["prev_reg_close"] = prev_reg_close
        else:
            cached_prev_c = safe_float(snap.get("prev_reg_close"), 0.0)
            if cached_prev_c > 0.0:
                prev_reg_close = round(cached_prev_c, 4)

    return prev_reg_close, pre_open_price


def compute_1m_indicators_vectorized(
    candles_1m: List[Dict[str, Any]],
    daily_candles: Optional[List[Dict[str, Any]]] = None,
    now_est: Optional[datetime] = None,
    live_price: float = 0.0,
    buy_interval_min: int = LOCKED_BUY_INTERVAL_MIN,
    last_evaluated_bucket_id: int = -1,
    last_evaluated_date: str = "",
    symbol: str = TARGET_SYMBOL,
) -> Dict[str, Any]:
    """
    🚨 벡터화 강제 & Case 01, Case 23, Case 64, Case 79, Case 84, Case 88, Case 92 & Case 93:
    1분봉 리스트(candles_1m) 및 실시간 현재가(live_price)를 받아 Pandas/NumPy 벡터 연산으로:
    - 10분 고정 매수 게이트 상태 (is_buy_gate_open, cur_buy_bucket_id, next_gate_hm_str, is_new_cycle_cutoff)
    - 당일 프리마켓 누적 VWAP (premarket_vwap : 04:00 ~ 09:29 EST 전용 · 미확보 시 정규장 VWAP 폴백 없이 0.0 반환!)
    - 당일 정규장 누적 VWAP (regular_vwap : 09:30 ~ 16:00 EST 전용) 및 전체 누적 VWAP (day_vwap)
    - 전일 정규장 종가 (prev_reg_close) 및 당일 04:07 프리장 시가 (pre_open_price · 미확보 시 정규시가 폴백 없이 0.0 반환!)
    - Wilder's RSI(14) 및 O(1) 실시간 합성용 기저 상태 (prev_bar_close, prev_avg_gain, prev_avg_loss · Case 92 & Case 93)
    - 하이킨 아시(Heikin-Ashi) 1분봉 상태 (ha_open, ha_close, ha_high, ha_low, ha_is_bull, is_1m_bull · Case 93)
    를 산출한다.
    """
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    today_str = dt_now.strftime("%Y-%m-%d")
    hm_now = dt_now.hour * 100 + dt_now.minute
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    snap_key = (sym, today_str)

    is_gate_open, cur_bucket_id, eval_date_str, gate_info = (
        evaluate_buy_gate_bucket_status(
            now_est=dt_now,
            buy_interval_min=LOCKED_BUY_INTERVAL_MIN,
            last_evaluated_bucket_id=last_evaluated_bucket_id,
            last_evaluated_date=last_evaluated_date,
        )
    )

    lp = round(safe_float(live_price, 0.0), 4)
    if lp > 0.0:
        _record_live_tick_to_memory_bar(sym, lp, dt_now)

    merged_candles = _merge_api_and_memory_candles(candles_1m, symbol=sym)
    amp_5d_pct = _compute_5ma_intraday_amp_pct_pct_safe(daily_candles)

    with _LIVE_1M_BAR_LOCK:
        cached_snap = dict(_DAILY_PREMARKET_SNAPSHOT_CACHE.get(snap_key, {}))

    default_pre_open = round(safe_float(cached_snap.get("pre_open_price"), 0.0), 4)
    default_pre_vwap = round(safe_float(cached_snap.get("premarket_vwap"), 0.0), 4)
    default_prev_close = round(safe_float(cached_snap.get("prev_reg_close"), 0.0), 4)

    default_res: Dict[str, Any] = {
        "valid": False,
        "symbol": sym,
        "date_est": today_str,
        "hm_est": hm_now,
        "session_label": gate_info.get("session_label", ""),
        "is_active_window": bool(gate_info.get("is_active_window", False)),
        "is_sell_window_open": bool(gate_info.get("is_sell_window_open", True)),
        "is_new_cycle_cutoff": bool(gate_info.get("is_new_cycle_cutoff", False)),
        "is_buy_gate_open": is_gate_open,
        "cur_buy_bucket_id": cur_bucket_id,
        "eval_date_str": eval_date_str,
        "next_gate_hm_str": gate_info.get("next_gate_hm_str", "04:07 EST"),
        "buy_interval_min": LOCKED_BUY_INTERVAL_MIN,
        "live_price": lp,
        "vwap": lp,
        "day_vwap": lp,
        "premarket_vwap": default_pre_vwap,
        "regular_vwap": 0.0,
        "vwap_distance_pct": 0.0,
        "vs_vwap_pct": 0.0,
        "vs_reg_vwap_pct": 0.0,
        "prev_reg_close": default_prev_close,
        "vs_prev_close_pct": 0.0,
        "pre_open_price": default_pre_open,
        "vs_pre_open_pct": 0.0,
        "rsi_14": 50.0,
        "prev_bar_close": lp,
        "prev_avg_gain": 0.0,
        "prev_avg_loss": 0.0,
        "open_1m": lp,
        "high_1m": lp,
        "low_1m": lp,
        "close_1m": lp,
        "is_1m_bull": True,
        "ha_open": lp,
        "ha_close": lp,
        "ha_high": lp,
        "ha_low": lp,
        "ha_is_bull": True,
        "amp_5d_pct": amp_5d_pct,
        "day_high": lp,
        "day_low": lp,
        "day_open": lp,
        "bar_count": 0,
        "today_bar_count": 0,
    }

    if not merged_candles:
        if lp > 0.0:
            default_res["valid"] = True
            if default_pre_vwap > 0.0:
                default_res["vs_vwap_pct"] = round(
                    ((lp - default_pre_vwap) / default_pre_vwap) * 100.0, 2
                )
            if default_prev_close > 0.0:
                default_res["vs_prev_close_pct"] = round(
                    ((lp - default_prev_close) / default_prev_close) * 100.0, 2
                )
            if default_pre_open > 0.0:
                default_res["vs_pre_open_pct"] = round(
                    ((lp - default_pre_open) / default_pre_open) * 100.0, 2
                )
        return default_res

    try:
        df = pd.DataFrame(merged_candles)
        required_cols = {
            "timestamp",
            "openPrice",
            "highPrice",
            "lowPrice",
            "closePrice",
        }
        if not required_cols.issubset(set(df.columns)):
            if lp > 0.0:
                default_res["valid"] = True
            return default_res

        ts_utc = _parse_timestamp_series_to_est(df["timestamp"])
        df["dt_est"] = ts_utc.dt.tz_convert(EST_TZ)
        df = df.dropna(subset=["dt_est"]).copy()
        if df.empty:
            if lp > 0.0:
                default_res["valid"] = True
            return default_res

        df["O"] = pd.to_numeric(df["openPrice"], errors="coerce")
        df["H"] = pd.to_numeric(df["highPrice"], errors="coerce")
        df["L"] = pd.to_numeric(df["lowPrice"], errors="coerce")
        df["C"] = pd.to_numeric(df["closePrice"], errors="coerce")
        if "volume" in df.columns:
            df["V"] = pd.to_numeric(df["volume"], errors="coerce").fillna(1.0)
        else:
            df["V"] = 1.0
        df["V"] = np.maximum(1.0, df["V"].to_numpy(dtype=float))

        valid_mask = (
            (df["C"] > 0.0) & (df["H"] > 0.0) & (df["L"] > 0.0) & (df["O"] > 0.0)
        )
        df = df[valid_mask].copy()
        if df.empty:
            if lp > 0.0:
                default_res["valid"] = True
            return default_res

        df["dt_min"] = df["dt_est"].dt.floor("min")
        df = (
            df.sort_values("dt_est", kind="mergesort")
            .drop_duplicates(subset=["dt_min"], keep="last")
            .reset_index(drop=True)
        )

        _sync_api_candles_into_memory_store(sym, df)

        df["Date"] = df["dt_est"].dt.strftime("%Y-%m-%d")
        df["HM"] = df["dt_est"].dt.hour * 100 + df["dt_est"].dt.minute

        # 실시간 현재가(live_price) 반영
        if lp > 0.0 and len(df) > 0:
            last_idx = df.index[-1]
            df.loc[last_idx, "C"] = lp
            if lp > float(df.loc[last_idx, "H"]):
                df.loc[last_idx, "H"] = lp
            if lp < float(df.loc[last_idx, "L"]) or float(df.loc[last_idx, "L"]) <= 0.0:
                df.loc[last_idx, "L"] = lp
        else:
            lp = round(float(df["C"].iloc[-1]), 4)

        amp_5d_pct = _compute_5ma_intraday_amp_pct_vectorized(daily_candles, df)

        # ------------------------------------------------------------------
        # 1) 당일 프리장 VWAP (04:00 ~ 09:29 EST) · 정규장 VWAP (09:30 ~ 16:00 EST) · 당일 전체 VWAP 분리 산출
        #    # MODIFIED [Case 93]: df_pre 가 비어 있을 때 regular_vwap 이나 day_vwap 으로 덮어쓰는 가짜 폴백 영구 제거!
        # ------------------------------------------------------------------
        df_today = df[
            (df["Date"] == today_str) & (df["HM"] >= 400) & (df["HM"] <= 2000)
        ]
        if df_today.empty:
            latest_date = str(df["Date"].iloc[-1])
            df_today = df[
                (df["Date"] == latest_date) & (df["HM"] >= 400) & (df["HM"] <= 2000)
            ]
            if df_today.empty:
                df_today = df.tail(min(60, len(df)))

        tp_today = (
            df_today["H"].to_numpy(dtype=float)
            + df_today["L"].to_numpy(dtype=float)
            + df_today["C"].to_numpy(dtype=float)
        ) / 3.0
        vol_today = df_today["V"].to_numpy(dtype=float)
        vol_sum = float(np.sum(vol_today))
        day_vwap = (
            round(float(np.sum(tp_today * vol_today) / vol_sum), 4)
            if vol_sum > 0.0
            else lp
        )

        # 프리마켓 전용 캔들 (당일 Date == today_str 이고 04:00 <= HM <= 09:29 인 봉만 엄격 필터링!)
        df_pre = df[
            (df["Date"] == today_str) & (df["HM"] >= 400) & (df["HM"] <= 929)
        ]
        if not df_pre.empty:
            tp_pre = (
                df_pre["H"].to_numpy(dtype=float)
                + df_pre["L"].to_numpy(dtype=float)
                + df_pre["C"].to_numpy(dtype=float)
            ) / 3.0
            vol_pre = df_pre["V"].to_numpy(dtype=float)
            vol_pre_sum = float(np.sum(vol_pre))
            premarket_vwap = (
                round(float(np.sum(tp_pre * vol_pre) / vol_pre_sum), 4)
                if vol_pre_sum > 0.0
                else 0.0
            )
            if premarket_vwap > 0.0:
                with _LIVE_1M_BAR_LOCK:
                    _DAILY_PREMARKET_SNAPSHOT_CACHE.setdefault(snap_key, {})[
                        "premarket_vwap"
                    ] = premarket_vwap
        else:
            # # MODIFIED: 당일 프리장 1분봉이 윈도우 밖으로 밀려난 경우 캐시된 당일 프리VWAP만 참조하고, 없으면 0.0 반환!
            with _LIVE_1M_BAR_LOCK:
                cached_pv = safe_float(
                    _DAILY_PREMARKET_SNAPSHOT_CACHE.get(snap_key, {}).get(
                        "premarket_vwap"
                    ),
                    0.0,
                )
            premarket_vwap = round(cached_pv, 4) if cached_pv > 0.0 else 0.0

        # 정규장 전용 캔들 (당일 Date == today_str 이고 09:30 <= HM <= 16:00)
        df_reg = df[
            (df["Date"] == today_str) & (df["HM"] >= 930) & (df["HM"] <= 1600)
        ]
        if not df_reg.empty:
            tp_reg = (
                df_reg["H"].to_numpy(dtype=float)
                + df_reg["L"].to_numpy(dtype=float)
                + df_reg["C"].to_numpy(dtype=float)
            ) / 3.0
            vol_reg = df_reg["V"].to_numpy(dtype=float)
            vol_reg_sum = float(np.sum(vol_reg))
            regular_vwap = (
                round(float(np.sum(tp_reg * vol_reg) / vol_reg_sum), 4)
                if vol_reg_sum > 0.0
                else 0.0
            )
        else:
            regular_vwap = 0.0

        # 스나이퍼 레이더 기본 표시용 vwap 은 세션에 맞는 day_vwap 유지
        vwap_val = day_vwap if day_vwap > 0.0 else lp
        vwap_dist_pct = (
            round(((lp - vwap_val) / vwap_val) * 100.0, 2)
            if vwap_val > 0.0
            else 0.0
        )
        # 암살자 프리VWAP 괴리율 (premarket_vwap == 0.0 이면 0.0%)
        vs_pre_vwap_pct = (
            round(((lp - premarket_vwap) / premarket_vwap) * 100.0, 2)
            if premarket_vwap > 0.0
            else 0.0
        )
        vs_reg_vwap_pct = (
            round(((lp - regular_vwap) / regular_vwap) * 100.0, 2)
            if regular_vwap > 0.0
            else 0.0
        )

        # ------------------------------------------------------------------
        # 2) 전일 정규장 종가(prev_reg_close) 및 당일 04:07 프리장 시가(pre_open_price) 추출
        # ------------------------------------------------------------------
        prev_reg_close, pre_open_price = _resolve_prev_reg_close_and_pre_open(
            symbol=sym,
            today_str=today_str,
            daily_candles=daily_candles,
            df_valid=df,
            df_today=df_today,
            df_pre=df_pre,
        )
        vs_prev_close_pct = (
            round(((lp - prev_reg_close) / prev_reg_close) * 100.0, 2)
            if prev_reg_close > 0.0
            else 0.0
        )
        vs_pre_open_pct = (
            round(((lp - pre_open_price) / pre_open_price) * 100.0, 2)
            if pre_open_price > 0.0
            else 0.0
        )

        # ------------------------------------------------------------------
        # 3) Wilder's RSI(14) 벡터 산출 및 O(1) 합성용 기저 상태 추출 (Case 92 & Case 93)
        # ------------------------------------------------------------------
        closes = df["C"].to_numpy(dtype=float)
        opens = df["O"].to_numpy(dtype=float)
        highs = df["H"].to_numpy(dtype=float)
        lows = df["L"].to_numpy(dtype=float)

        rsi_14 = 50.0
        prev_bar_close = float(closes[-2]) if len(closes) >= 2 else lp
        prev_avg_gain = 0.0
        prev_avg_loss = 0.0

        if len(closes) >= 3:
            deltas = np.diff(closes)
            gains = np.maximum(0.0, deltas)
            losses = np.maximum(0.0, -deltas)
            period = 14
            if len(deltas) <= period:
                avg_g = float(np.mean(gains))
                avg_l = float(np.mean(losses))
                if len(deltas) >= 2:
                    prev_avg_gain = float(np.mean(gains[:-1]))
                    prev_avg_loss = float(np.mean(losses[:-1]))
            else:
                avg_g = float(np.mean(gains[:period]))
                avg_l = float(np.mean(losses[:period]))
                for idx_d in range(period, len(deltas)):
                    prev_avg_gain = avg_g
                    prev_avg_loss = avg_l
                    avg_g = (avg_g * (period - 1) + float(gains[idx_d])) / float(
                        period
                    )
                    avg_l = (avg_l * (period - 1) + float(losses[idx_d])) / float(
                        period
                    )
            if avg_g <= 1e-12 and avg_l <= 1e-12:
                rsi_14 = 50.0
            elif avg_l <= 1e-12:
                rsi_14 = 100.0
            else:
                rs = avg_g / avg_l
                rsi_14 = round(100.0 - (100.0 / (1.0 + rs)), 2)

        # ------------------------------------------------------------------
        # 4) 하이킨 아시(Heikin-Ashi) 1분봉 및 일반 1분봉 양봉/음봉 상태 산출 (Case 93)
        # ------------------------------------------------------------------
        n_bars = len(closes)
        ha_close_arr = (opens + highs + lows + closes) / 4.0
        ha_open_arr = np.zeros(n_bars, dtype=float)
        ha_open_arr[0] = (opens[0] + closes[0]) / 2.0
        for idx_h in range(1, n_bars):
            ha_open_arr[idx_h] = (
                ha_open_arr[idx_h - 1] + ha_close_arr[idx_h - 1]
            ) / 2.0
        ha_high_arr = np.maximum(highs, np.maximum(ha_open_arr, ha_close_arr))
        ha_low_arr = np.minimum(lows, np.minimum(ha_open_arr, ha_close_arr))

        cur_o_1m = round(float(opens[-1]), 4)
        cur_h_1m = round(float(highs[-1]), 4)
        cur_l_1m = round(float(lows[-1]), 4)
        cur_c_1m = round(float(closes[-1]), 4)
        is_1m_bull = bool(cur_c_1m >= cur_o_1m)

        ha_o = round(float(ha_open_arr[-1]), 4)
        ha_c = round(float(ha_close_arr[-1]), 4)
        ha_h = round(float(ha_high_arr[-1]), 4)
        ha_l = round(float(ha_low_arr[-1]), 4)
        ha_is_bull = bool(ha_c > ha_o)

        day_high = round(float(df_today["H"].max()), 4)
        day_low = round(float(df_today["L"].min()), 4)
        day_open = round(float(df_today["O"].iloc[0]), 4)

        return {
            "valid": True,
            "symbol": sym,
            "date_est": today_str,
            "hm_est": hm_now,
            "session_label": gate_info.get("session_label", ""),
            "is_active_window": bool(gate_info.get("is_active_window", False)),
            "is_sell_window_open": bool(
                gate_info.get("is_sell_window_open", True)
            ),
            "is_new_cycle_cutoff": bool(
                gate_info.get("is_new_cycle_cutoff", False)
            ),
            "is_buy_gate_open": is_gate_open,
            "cur_buy_bucket_id": cur_bucket_id,
            "eval_date_str": eval_date_str,
            "next_gate_hm_str": gate_info.get("next_gate_hm_str", "04:07 EST"),
            "buy_interval_min": LOCKED_BUY_INTERVAL_MIN,
            "live_price": lp,
            "vwap": vwap_val,
            "day_vwap": day_vwap,
            "premarket_vwap": premarket_vwap,
            "regular_vwap": regular_vwap,
            "vwap_distance_pct": vwap_dist_pct,
            "vs_vwap_pct": vs_pre_vwap_pct,
            "vs_reg_vwap_pct": vs_reg_vwap_pct,
            "prev_reg_close": prev_reg_close,
            "vs_prev_close_pct": vs_prev_close_pct,
            "pre_open_price": pre_open_price,
            "vs_pre_open_pct": vs_pre_open_pct,
            "rsi_14": rsi_14,
            "prev_bar_close": round(prev_bar_close, 4),
            "prev_avg_gain": round(prev_avg_gain, 6),
            "prev_avg_loss": round(prev_avg_loss, 6),
            "open_1m": cur_o_1m,
            "high_1m": cur_h_1m,
            "low_1m": cur_l_1m,
            "close_1m": cur_c_1m,
            "is_1m_bull": is_1m_bull,
            "ha_open": ha_o,
            "ha_close": ha_c,
            "ha_high": ha_h,
            "ha_low": ha_l,
            "ha_is_bull": ha_is_bull,
            "amp_5d_pct": amp_5d_pct,
            "day_high": day_high,
            "day_low": day_low,
            "day_open": day_open,
            "bar_count": int(len(df)),
            "today_bar_count": int(len(df_today)),
        }
    except Exception as exc:
        logger.warning(f"⚠️ compute_1m_indicators_vectorized 예외 폴백: {exc}")
        if lp > 0.0:
            default_res["valid"] = True
        return default_res


def _compute_5ma_intraday_amp_pct_pct_safe(
    daily_candles: Optional[List[Dict[str, Any]]],
) -> float:
    return _compute_5ma_intraday_amp_pct_vectorized(daily_candles, None)


def compute_soxl_quant_metrics_1m(
    candles_1m: List[Dict[str, Any]],
    daily_candles: Optional[List[Dict[str, Any]]] = None,
    now_est: Optional[datetime] = None,
    live_price: float = 0.0,
    buy_interval_min: int = LOCKED_BUY_INTERVAL_MIN,
    last_evaluated_bucket_id: int = -1,
    last_evaluated_date: str = "",
) -> Dict[str, Any]:
    """
    하위 호환 래퍼: SOXL 1분봉 및 일봉을 받아 벡터화 시계열 지표를 반환한다.
    """
    return compute_1m_indicators_vectorized(
        candles_1m=candles_1m,
        daily_candles=daily_candles,
        now_est=now_est,
        live_price=live_price,
        buy_interval_min=buy_interval_min,
        last_evaluated_bucket_id=last_evaluated_bucket_id,
        last_evaluated_date=last_evaluated_date,
        symbol=TARGET_SYMBOL,
    )


# ---------------------------------------------------------------------------
# [핵심 4] 🗡️ 암살자(Case 93) 전용 나스닥 100 대리변수 QQQ 단기 모멘텀 & 방향성 3단계 안전망 지표 산출기
# ---------------------------------------------------------------------------
def compute_qqq_macro_metrics_1m(
    candles_1m: List[Dict[str, Any]],
    daily_candles: Optional[List[Dict[str, Any]]] = None,
    live_price: float = 0.0,
    now_est: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    # NEW [Case 93 : 나스닥 100 선물 대리변수 QQQ 1분봉 벡터 지표 산출기]:
    - QQQ 현재가(qqq_live_price), 1분 변화율(vel_1m_pct), 3분 변화율(vel_3m_pct), 10분 변화율(vel_10m_pct)
    - 당일 고점 대비 하락 진폭(bear_drop_amp_pct = (day_high - live_p) / day_high * 100)
    - QQQ 1분봉 양봉 여부(is_1m_bull), 하이킨 아시 양봉 여부(ha_is_bull)
    - 전일 정규장 종가(prev_reg_close) 및 당일 프리장 시가(pre_open_price)
    를 100% 벡터 연산으로 산출하여 순수 롱 방향성 인지 3단계 안전망 v2 에 공급한다.
    """
    base = compute_1m_indicators_vectorized(
        candles_1m=candles_1m,
        daily_candles=daily_candles,
        now_est=now_est,
        live_price=live_price,
        symbol="QQQ",
    )
    lp = safe_float(base.get("live_price"), safe_float(live_price, 0.0))
    vel_1m_pct: float = 0.0
    vel_3m_pct: float = 0.0
    vel_10m_pct: float = 0.0
    bear_drop_amp_pct: float = 0.80

    merged_q = _merge_api_and_memory_candles(candles_1m, symbol="QQQ")
    if merged_q:
        try:
            df_q = pd.DataFrame(merged_q)
            if "closePrice" in df_q.columns and "timestamp" in df_q.columns:
                ts_u = _parse_timestamp_series_to_est(df_q["timestamp"])
                df_q["dt_est"] = ts_u.dt.tz_convert(EST_TZ)
                df_q = df_q.dropna(subset=["dt_est"]).copy()
                df_q["C"] = pd.to_numeric(df_q["closePrice"], errors="coerce")
                df_q["H"] = pd.to_numeric(
                    df_q.get("highPrice", df_q["C"]), errors="coerce"
                )
                df_q["L"] = pd.to_numeric(
                    df_q.get("lowPrice", df_q["C"]), errors="coerce"
                )
                df_q = df_q[df_q["C"] > 0.0].copy()
                if not df_q.empty:
                    df_q["dt_min"] = df_q["dt_est"].dt.floor("min")
                    df_q = (
                        df_q.sort_values("dt_est", kind="mergesort")
                        .drop_duplicates(subset=["dt_min"], keep="last")
                        .reset_index(drop=True)
                    )
                    closes_q = df_q["C"].to_numpy(dtype=float)
                    if lp <= 0.0:
                        lp = round(float(closes_q[-1]), 4)
                    else:
                        closes_q[-1] = lp

                    if len(closes_q) >= 2 and closes_q[-2] > 0.0:
                        vel_1m_pct = round(
                            ((lp - float(closes_q[-2])) / float(closes_q[-2]))
                            * 100.0,
                            3,
                        )
                    if len(closes_q) >= 4 and closes_q[-4] > 0.0:
                        vel_3m_pct = round(
                            ((lp - float(closes_q[-4])) / float(closes_q[-4]))
                            * 100.0,
                            3,
                        )
                    elif len(closes_q) >= 2 and closes_q[0] > 0.0:
                        vel_3m_pct = round(
                            ((lp - float(closes_q[0])) / float(closes_q[0]))
                            * 100.0,
                            3,
                        )
                    if len(closes_q) >= 11 and closes_q[-11] > 0.0:
                        vel_10m_pct = round(
                            ((lp - float(closes_q[-11])) / float(closes_q[-11]))
                            * 100.0,
                            3,
                        )
                    else:
                        vel_10m_pct = vel_3m_pct

                    day_h_q = max(
                        lp,
                        safe_float(base.get("day_high"), lp),
                        safe_float(base.get("prev_reg_close"), lp),
                    )
                    if day_h_q > 0.0 and lp > 0.0:
                        bear_drop_amp_pct = round(
                            max(0.40, ((day_h_q - lp) / day_h_q) * 100.0),
                            2,
                        )
        except Exception:
            pass

    return {
        "valid": bool(base.get("valid", False) or lp > 0.0),
        "qqq_live_price": round(lp, 4),
        "vel_1m_pct": vel_1m_pct,
        "vel_3m_pct": vel_3m_pct,
        "vel_10m_pct": vel_10m_pct,
        "bear_drop_amp_pct": bear_drop_amp_pct,
        "is_1m_bull": bool(base.get("is_1m_bull", True)),
        "ha_is_bull": bool(base.get("ha_is_bull", True)),
        "prev_reg_close": safe_float(base.get("prev_reg_close"), 0.0),
        "pre_open_price": safe_float(base.get("pre_open_price"), 0.0),
        "rsi_14": safe_float(base.get("rsi_14"), 50.0),
    }


def run_quant_indicators_tdd() -> None:
    """
    🛠️ [TDD 검증]:
    1) Case 84: 15:30 ~ 16:00 EST 컷오프 판정
    2) Case 92: compute_realtime_synthetic_rsi O(1) 합성 정합성
    3) Case 93: 장 마감 후 프리장(04:00 ~ 09:29 EST) 캔들 부재 시 pre_open_price 및 premarket_vwap 이
       정규장 시가($48.70)나 정규장 VWAP($45.43)로 오염되지 않고 정확히 0.0 ($0.00)을 반환하는지 검증
    """
    dt_late = datetime(2026, 5, 11, 15, 35, 0, tzinfo=EST_TZ)
    assert is_late_regular_new_cycle_cutoff_window(1535, dt_late) is True
    dt_early = datetime(2026, 5, 11, 15, 29, 0, tzinfo=EST_TZ)
    assert is_late_regular_new_cycle_cutoff_window(1529, dt_early) is False

    syn_rsi = compute_realtime_synthetic_rsi(45.0, 46.0, 0.25, 0.25)
    assert 0.0 <= syn_rsi <= 100.0

    # 장 마감 후(16:30 EST) 정규장 캔들만 존재할 때 프리시가/프리VWAP 0.0 반환 검증
    dt_after = datetime(2026, 5, 12, 16, 30, 0, tzinfo=EST_TZ)
    _DAILY_PREMARKET_SNAPSHOT_CACHE.pop(("SOXL", "2026-05-12"), None)
    with _LIVE_1M_BAR_LOCK:
        _LIVE_1M_BAR_STORE["SOXL"] = []

    reg_only_candles = [
        {
            "timestamp": "2026-05-12T15:58:00-04:00",
            "openPrice": "48.70",
            "highPrice": "48.80",
            "lowPrice": "45.00",
            "closePrice": "46.31",
            "volume": "10000",
            "currency": "USD",
        }
    ]
    daily_mock = [
        {
            "timestamp": "2026-05-11T00:00:00-04:00",
            "openPrice": "40.00",
            "highPrice": "41.50",
            "lowPrice": "39.80",
            "closePrice": "40.87",
            "volume": "500000",
        },
        {
            "timestamp": "2026-05-12T00:00:00-04:00",
            "openPrice": "48.70",
            "highPrice": "49.10",
            "lowPrice": "44.20",
            "closePrice": "46.31",
            "volume": "600000",
        },
    ]
    res_after = compute_1m_indicators_vectorized(
        candles_1m=reg_only_candles,
        daily_candles=daily_mock,
        now_est=dt_after,
        live_price=46.31,
        symbol="SOXL",
    )
    assert res_after["prev_reg_close"] == 40.87
    assert res_after["pre_open_price"] == 0.0, (
        f"Expected 0.0 pre_open_price when no premarket bars, got {res_after['pre_open_price']}"
    )
    assert res_after["premarket_vwap"] == 0.0, (
        f"Expected 0.0 premarket_vwap when no premarket bars, got {res_after['premarket_vwap']}"
    )
    assert res_after["vs_pre_open_pct"] == 0.0
    assert res_after["vs_vwap_pct"] == 0.0


if __name__ == "__main__":
    run_quant_indicators_tdd()
    print("✅ [quant_indicators_plugin.py] TDD Self-Test Passed!")
