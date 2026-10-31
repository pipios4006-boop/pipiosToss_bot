# -*- coding: utf-8 -*-
"""
# NEW: sniper_plugin_core.py
인피니트 스노우볼 (Infinite Snowball) v3.0 — 스나이퍼 매수 코어 Part 1 / 2 (Step 02 / 06)
역할:
1) 스나이퍼 매수 전역 상수 락온 (STEP2X_15PCT_C20 · BUY_ORDER_MAX_WAIT_SEC = 60.0 · AUTO_FILL_GRACE_SHIELD_SEC = 15.0 ·
   REENTRY_MONITOR_TIME_SHIELD_SEC = 60.0 · RESERVE_DEPOSIT_CHECK_INTERVAL_SEC = 60.0)
2) 매수·매도 체결 직후 토스 잔고 API 인덱싱 시차(0.1 ~ 0.4초) 보호 양방향 15.0초 그레이스 쉴드 및
   매수 체결 후 60.0초 타임쉴드 각인기 (mark_auto_fill_grace_shield, is_within_auto_fill_grace_shield · Case 61, 65, 69)
3) 상단 2층 ~ 7층 보유 중 1층 공석 시 60.0초(1분) 타임쉴드 주기 하이브리드 재장전 모니터 타임쉴드 관리기
   (mark_reentry_monitor_60s_cycle_shield, is_within_reentry_monitor_time_shield · Case 73)
4) 시드고갈 입금 대기(waiting_reserve_deposit) 및 독립 골든포켓 현금 가동 중 60.0초 주기 확인 타임쉴드 관리기
   (mark_reserve_deposit_check_shield, is_within_reserve_deposit_check_shield · Case 77, 80)
5) 실시간 SOXL 현재가 추출 및 60초 타임쉴드 경과 직후 최신 현재가 직접 재조회기
   (_get_live_soxl_price, _fetch_fresh_current_soxl_price · Case 65, 73, 80)
6) 💉 05_RESV_6P_GUARD30 (30% 자투리 1주 승격 방지 가드 · 골든포켓 가동 중 오발동 방어 · 예수금 API 0.0 반환 시 0.25초 재시도 ·
   시드고갈 단 1회 입금 요청 알림 영구 래치 waiting_reserve_deposit_alert_sent 및 중복 디스크 쓰기 스킵 ·
   토스 실계좌 여유자금 감지 기반 최대 +6회분 온디맨드 예비시드 자동 수혈) 실행 엔진
   (_check_and_execute_guard30_or_reserve_injection · Case 75, 77, 80)
7) 매수 체결(FILLED / 부분 체결 후 60초 취소 종료) 원장 커밋 · 독립 골든포켓(GOLDEN_POCKET) 분리 정산(Case 80) ·
   부분 체결 수량 비례 자투리 정산 및 1층 목표 정량(l1_target_quota_qty) 보존(Case 78) ·
   STEP2X_15PCT_C20 스텝업 잠금 저가 갱신(Case 76) 및 미체결 매수 주문 60.0초 동기화/안전 취소기
   (_commit_filled_buy_to_stratum_ledger, sync_pending_buy_order_plugin · Case 19, 24, 59 ~ 80)
- 제1헌법 ~ 제6헌법 및 Case 01 ~ 84 완벽 준수
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from quant_engine import (
    BASE_MAX_LOTS_8PCT,
    GOLDEN_POCKET_RISE_PCT,
    GoldenAllInPocket,
    MAX_GRID_TIERS_7,
    MAX_RESERVE_PORTIONS,
    MIN_DIP_BUDGET_RATIO,
    MIN_DIP_VS_L1_RATIO,
    ROUND_TRIP_FEE_RATE_PCT,
    buckets_from_dicts,
    buckets_to_dicts,
    evaluate_guard30_and_reserve_injection,
    has_active_l1_bucket,
    pocket_from_dict,
    summarize_stratum_portfolio,
    vrev_add_quota_lot_and_merge_2tier,
)
from quant_indicators_plugin import refresh_metrics_with_live_tick
from sniper_exit_plugin import (
    is_within_post_buy_time_shield,
    is_within_post_sell_time_shield,
)
import toss_api
from toss_api import (
    EST_TZ,
    TARGET_SYMBOL,
    safe_float,
    safe_int,
)

logger = logging.getLogger("toss_sniper.sniper_plugin_core")

# Case 76: 🔓 06_STEP2X_15PCT_C20 스텝업 저가 해금 상수 폴백 바인딩
DEFAULT_UNLOCK_MODE: str = str(
    getattr(toss_api, "DEFAULT_UNLOCK_MODE", "STEP2X_15PCT_C20")
)
STEP_UP_2X_DROP_PCT: float = float(
    getattr(toss_api, "STEP_UP_2X_DROP_PCT", 15.0)
)
STEP_UP_2X_MIN_CASH_RATIO: float = float(
    getattr(toss_api, "STEP_UP_2X_MIN_CASH_RATIO", 0.20)
)
STEP_UP_2X_MIN_REBOUND_MULT: float = float(
    getattr(toss_api, "STEP_UP_2X_MIN_REBOUND_MULT", 2.0)
)
STEP_UP_2X_MAX_TIERS: int = int(
    getattr(toss_api, "STEP_UP_2X_MAX_TIERS", 2)
)

# 순수 현재가 지정가 매수 주문 발주 후 미체결 최대 대기 시간(초) — 상향 추격 정정 없이 60초 미체결 시 안전 취소
BUY_ORDER_MAX_WAIT_SEC: float = 60.0

# Case 61 & Case 69: 매수 또는 매도 FILLED 직후 토스 잔고 API(/api/v1/holdings) 인덱싱 시차(0.1 ~ 0.4초) 보호 그레이스 쉴드(초)
AUTO_FILL_GRACE_SHIELD_SEC: float = 15.0

# Case 73: 상단 2층 ~ 7층 보유 중 1층 공석 시 하이브리드 독립 1층(REENTRY_1FL) 재장전 모니터 주기 타임쉴드(60.0초 = 1분)
REENTRY_MONITOR_TIME_SHIELD_SEC: float = 60.0

# Case 77: 시드고갈 입금 대기(waiting_reserve_deposit == True) 상태에서 토스 계좌 입금 감지 주기 타임쉴드(60.0초 = 1분)
RESERVE_DEPOSIT_CHECK_INTERVAL_SEC: float = 60.0


# ---------------------------------------------------------------------------
# 내부 헬퍼 : 매수·매도 체결 직후 잔고 인덱싱 시차 보호 그레이스 쉴드 & 60초 타임쉴드 각인 (Case 61, 65, 69, 73, 77, 80)
# ---------------------------------------------------------------------------
def mark_auto_fill_grace_shield(
    context: Any,
    symbol: str = TARGET_SYMBOL,
    lot_type: str = "QUOTA_L1",
    fill_price: float = 0.0,
    filled_qty: int = 0,
) -> None:
    """
    🚨 Case 61, Case 65, Case 69, Case 73, Case 77 & Case 80:
    1) 매수(또는 매도) 주문이 거래소에서 FILLED 된 직후 토스 잔고 API(/api/v1/holdings) 인덱싱 시차(0.1 ~ 0.4초) 동안
       잔고 동기화 모듈(reconcile)이 시차를 수동 매매로 오판하지 않도록 15.0초 그레이스 쉴드(last_auto_fill_ts)를 각인한다.
    2) 매수 체결 시에는 last_buy_fill_mono(단조 시계)와 last_buy_fill_ts(Epoch)를 전용 키로 각인하여,
       매수 체결 후 정확히 60.0초(POST_BUY_TO_SELL_SHIELD_SEC) 동안 매도 및 중복 매수가 발사되지 않도록 타임쉴드를 건다!
    3) 그리드 매수 체결로 1층이 채워지면 1층 공석 재장전 모니터 타임쉴드(last_reentry_eval_mono / last_reentry_eval_ts) 및
       예비시드 입금 대기 타임쉴드(last_reserve_check_mono / last_reserve_check_ts)는 0.0 으로 리셋한다.
    """
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    now_mono = time.monotonic()
    now_epoch = time.time()
    tag = str(lot_type or "QUOTA_L1").upper().strip()

    guard_map = getattr(context, "indexing_grace_cache", None)
    if isinstance(guard_map, dict):
        prev = guard_map.get(sym) if isinstance(guard_map.get(sym), dict) else {}
        updated = dict(prev)
        updated["last_auto_fill_ts"] = now_mono
        updated["lot_type"] = tag
        updated["fill_price"] = safe_float(fill_price, 0.0)
        updated["filled_qty"] = safe_int(filled_qty, 0)
        if tag != "SELL_FILL":
            updated["last_buy_fill_mono"] = now_mono
            updated["last_buy_fill_ts"] = now_epoch
            if tag != "GOLDEN_POCKET":
                updated["last_reentry_eval_mono"] = 0.0
                updated["last_reentry_eval_ts"] = 0.0
            updated["last_reserve_check_mono"] = 0.0
            updated["last_reserve_check_ts"] = 0.0
        else:
            updated["last_sell_fill_mono"] = now_mono
            updated["last_sell_fill_ts"] = now_epoch
        guard_map[sym] = updated

    if tag != "SELL_FILL":
        snap_map = getattr(context, "exit_snapshot_cache", None)
        if isinstance(snap_map, dict):
            s_entry = (
                snap_map.get(sym) if isinstance(snap_map.get(sym), dict) else {}
            )
            if tag != "GOLDEN_POCKET":
                s_entry["last_reentry_eval_mono"] = 0.0
                s_entry["last_reentry_eval_ts"] = 0.0
            s_entry["last_reserve_check_mono"] = 0.0
            s_entry["last_reserve_check_ts"] = 0.0
            snap_map[sym] = s_entry


def is_within_auto_fill_grace_shield(
    context: Any, symbol: str = TARGET_SYMBOL
) -> bool:
    """
    🚨 Case 61 & Case 69 [양방향 15.0초 잔고 인덱싱 시차 보호 그레이스 쉴드]:
    최근 15.0초(AUTO_FILL_GRACE_SHIELD_SEC) 이내에 자동 매수 체결 또는 자동 매도 체결(개별 층 익절 / 골든포켓 익절 / 0주 졸업)
    이력이 존재하면 True 를 반환하여, defense_plugin.py 의 reconcile 모듈이 잔고 API 인덱싱 시차로 인해
    유령 추매(h_qty > ledger_qty)나 유령 부분매도(h_qty < ledger_qty) 또는 백업 덮어쓰기를 수행하는 것을 100% 차단한다!
    """
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    now_mono = time.monotonic()

    guard_map = getattr(context, "indexing_grace_cache", None)
    if isinstance(guard_map, dict):
        info = guard_map.get(sym)
        if isinstance(info, dict):
            last_mono = max(
                safe_float(info.get("last_auto_fill_ts"), 0.0),
                safe_float(info.get("last_buy_fill_mono"), 0.0),
                safe_float(info.get("last_sell_fill_mono"), 0.0),
                safe_float(info.get("last_cycle_end_mono"), 0.0),
            )
            if (
                last_mono > 0.0
                and 0.0 <= (now_mono - last_mono) <= AUTO_FILL_GRACE_SHIELD_SEC
            ):
                return True

    snap_map = getattr(context, "exit_snapshot_cache", None)
    if isinstance(snap_map, dict):
        s_info = snap_map.get(sym)
        if isinstance(s_info, dict):
            last_s_mono = max(
                safe_float(s_info.get("last_sell_fill_mono"), 0.0),
                safe_float(s_info.get("last_cycle_end_mono"), 0.0),
            )
            if (
                last_s_mono > 0.0
                and 0.0 <= (now_mono - last_s_mono) <= AUTO_FILL_GRACE_SHIELD_SEC
            ):
                return True

    if hasattr(context, "ledger"):
        try:
            st = context.ledger.get_state(sym)
            last_epoch = max(
                safe_float(st.get("last_buy_fill_ts"), 0.0),
                safe_float(st.get("last_sell_fill_ts"), 0.0),
                safe_float(st.get("last_cycle_end_ts"), 0.0),
            )
            if (
                last_epoch > 0.0
                and 0.0 <= (time.time() - last_epoch) <= AUTO_FILL_GRACE_SHIELD_SEC
            ):
                return True
        except Exception:
            pass

    return False


# ---------------------------------------------------------------------------
# [Case 73 & Case 77] 1층 공석 60초 재장전 타임쉴드 & 시드고갈 60초 입금 감지 타임쉴드 관리기
# ---------------------------------------------------------------------------
def mark_reentry_monitor_60s_cycle_shield(
    context: Any,
    symbol: str = TARGET_SYMBOL,
    eval_price: float = 0.0,
    clear_shield: bool = False,
) -> float:
    """
    🚨 [Case 73 : 1층 공석 60.0초(1분) 타임쉴드 주기 하이브리드 재장전 모니터 재장전기]:
    - 상단 2층 ~ 7층 보유 중 1층이 공석일 때(len(buckets) > 0 and not has_active_l1_bucket(buckets)),
      60.0초 주기 재장전 검문 결과 조건 미달(-1.00% < chg < +1.00%)이거나
      현재가 > 2층 단가로 역전 차단(HOLD_PREVENT_INVERSION)되었거나,
      장마감 30분 전(15:30 ~ 16:00 EST) +1.00% 상승돌파가 차단(HOLD_LATE_SESSION_BREAKOUT_CUTOFF)되었을 때,
      또는 1층 재장전 지정가 주문이 60.0초 미체결로 안전 취소된 직후 호출되어
      인메모리 캐시(indexing_grace_cache 및 exit_snapshot_cache)에
      last_reentry_eval_mono 와 last_reentry_eval_ts 를 기록하고 현재 Epoch 시각을 반환한다.
    - 1층 재장전이 체결되어 활성 1층이 채워지거나 0주 졸업 시에는 clear_shield=True 로 호출하여 0.0 으로 리셋한다.
    """
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    now_mono = 0.0 if clear_shield else time.monotonic()
    now_epoch = 0.0 if clear_shield else time.time()

    guard_map = getattr(context, "indexing_grace_cache", None)
    if isinstance(guard_map, dict):
        g_entry = (
            guard_map.get(sym) if isinstance(guard_map.get(sym), dict) else {}
        )
        g_entry["last_reentry_eval_mono"] = now_mono
        g_entry["last_reentry_eval_ts"] = now_epoch
        if eval_price > 0.0:
            g_entry["last_reentry_eval_price"] = round(
                safe_float(eval_price, 0.0), 4
            )
        guard_map[sym] = g_entry

    snap_map = getattr(context, "exit_snapshot_cache", None)
    if isinstance(snap_map, dict):
        s_entry = (
            snap_map.get(sym) if isinstance(snap_map.get(sym), dict) else {}
        )
        s_entry["last_reentry_eval_mono"] = now_mono
        s_entry["last_reentry_eval_ts"] = now_epoch
        if eval_price > 0.0:
            s_entry["last_reentry_eval_price"] = round(
                safe_float(eval_price, 0.0), 4
            )
        snap_map[sym] = s_entry

    return now_epoch


def is_within_reentry_monitor_time_shield(
    context: Any,
    st: Optional[Dict[str, Any]] = None,
    symbol: str = TARGET_SYMBOL,
) -> Tuple[bool, float]:
    """
    🚨 [Case 73 : 1층 공석 60.0초(1분) 주기 재장전 모니터 타임쉴드 작동 여부 판별]:
    1) 먼저 직전 매도 체결 후 60.0초 타임쉴드(is_within_post_sell_time_shield) 및
       직전 매수 체결 후 60.0초 타임쉴드(is_within_post_buy_time_shield)를 확인한다.
    2) 이후 1층 공석 상태에서 직전 60.0초 재장전 모니터 검문 시각(last_reentry_eval_mono / last_reentry_eval_ts)으로부터
       60.0초(REENTRY_MONITOR_TIME_SHIELD_SEC = 60.0)가 경과하지 않았으면 True 와 잔여 초(remain_sec)를 반환한다.
    """
    in_post_sell, rem_sell = is_within_post_sell_time_shield(
        context, st, symbol
    )
    if in_post_sell:
        return True, rem_sell

    in_post_buy, rem_buy = is_within_post_buy_time_shield(context, st, symbol)
    if in_post_buy:
        return True, rem_buy

    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    now_mono = time.monotonic()

    guard_map = getattr(context, "indexing_grace_cache", None)
    if isinstance(guard_map, dict):
        g_entry = guard_map.get(sym)
        if isinstance(g_entry, dict):
            re_mono = safe_float(g_entry.get("last_reentry_eval_mono"), 0.0)
            if re_mono > 0.0:
                elapsed_g = now_mono - re_mono
                if 0.0 <= elapsed_g < REENTRY_MONITOR_TIME_SHIELD_SEC:
                    return True, round(
                        REENTRY_MONITOR_TIME_SHIELD_SEC - elapsed_g, 1
                    )

    snap_map = getattr(context, "exit_snapshot_cache", None)
    if isinstance(snap_map, dict):
        s_entry = snap_map.get(sym)
        if isinstance(s_entry, dict):
            s_re_mono = safe_float(s_entry.get("last_reentry_eval_mono"), 0.0)
            if s_re_mono > 0.0:
                elapsed_s = now_mono - s_re_mono
                if 0.0 <= elapsed_s < REENTRY_MONITOR_TIME_SHIELD_SEC:
                    return True, round(
                        REENTRY_MONITOR_TIME_SHIELD_SEC - elapsed_s, 1
                    )

    state_obj = (
        st
        if isinstance(st, dict)
        else (
            context.ledger.get_state(sym)
            if hasattr(context, "ledger")
            else {}
        )
    )
    re_epoch = safe_float(state_obj.get("last_reentry_eval_ts"), 0.0)
    if re_epoch > 0.0:
        elapsed_epoch = time.time() - re_epoch
        if 0.0 <= elapsed_epoch < REENTRY_MONITOR_TIME_SHIELD_SEC:
            return True, round(REENTRY_MONITOR_TIME_SHIELD_SEC - elapsed_epoch, 1)

    return False, 0.0


def mark_reserve_deposit_check_shield(
    context: Any,
    symbol: str = TARGET_SYMBOL,
    clear_shield: bool = False,
) -> float:
    """
    # [Case 77 & Case 80 : 시드고갈 입금 대기 또는 골든포켓 현금 가동 중 60.0초 주기 확인 타임쉴드 기록기]:
    시드고갈(GUARD30) 또는 골든포켓 전액 투입으로 일반 매수가 보류된 상태에서
    매 1.5초마다 /api/v1/buying-power 나 시세를 과도하게 호출하지 않고
    정확히 60.0초(1분) 주기로 확인하도록 타임쉴드를 기록한다.
    """
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    now_mono = 0.0 if clear_shield else time.monotonic()
    now_epoch = 0.0 if clear_shield else time.time()

    guard_map = getattr(context, "indexing_grace_cache", None)
    if isinstance(guard_map, dict):
        g_entry = (
            guard_map.get(sym) if isinstance(guard_map.get(sym), dict) else {}
        )
        g_entry["last_reserve_check_mono"] = now_mono
        g_entry["last_reserve_check_ts"] = now_epoch
        guard_map[sym] = g_entry

    snap_map = getattr(context, "exit_snapshot_cache", None)
    if isinstance(snap_map, dict):
        s_entry = (
            snap_map.get(sym) if isinstance(snap_map.get(sym), dict) else {}
        )
        s_entry["last_reserve_check_mono"] = now_mono
        s_entry["last_reserve_check_ts"] = now_epoch
        snap_map[sym] = s_entry

    return now_epoch


def is_within_reserve_deposit_check_shield(
    context: Any,
    st: Optional[Dict[str, Any]] = None,
    symbol: str = TARGET_SYMBOL,
) -> Tuple[bool, float]:
    """
    # [Case 77 & Case 80 : 시드고갈 입금 대기 중 60.0초 타임쉴드 판별기]:
    직전 예비시드 입금(또는 골든포켓 현금 대기) 확인 시각(last_reserve_check_mono / last_reserve_check_ts)으로부터
    60.0초(RESERVE_DEPOSIT_CHECK_INTERVAL_SEC)가 경과하지 않았으면 True 와 잔여 초를 반환한다.
    """
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    now_mono = time.monotonic()

    guard_map = getattr(context, "indexing_grace_cache", None)
    if isinstance(guard_map, dict):
        g_entry = guard_map.get(sym)
        if isinstance(g_entry, dict):
            rc_mono = safe_float(g_entry.get("last_reserve_check_mono"), 0.0)
            if rc_mono > 0.0:
                elapsed_g = now_mono - rc_mono
                if 0.0 <= elapsed_g < RESERVE_DEPOSIT_CHECK_INTERVAL_SEC:
                    return True, round(
                        RESERVE_DEPOSIT_CHECK_INTERVAL_SEC - elapsed_g, 1
                    )

    snap_map = getattr(context, "exit_snapshot_cache", None)
    if isinstance(snap_map, dict):
        s_entry = snap_map.get(sym)
        if isinstance(s_entry, dict):
            s_rc_mono = safe_float(s_entry.get("last_reserve_check_mono"), 0.0)
            if s_rc_mono > 0.0:
                elapsed_s = now_mono - s_rc_mono
                if 0.0 <= elapsed_s < RESERVE_DEPOSIT_CHECK_INTERVAL_SEC:
                    return True, round(
                        RESERVE_DEPOSIT_CHECK_INTERVAL_SEC - elapsed_s, 1
                    )

    state_obj = (
        st
        if isinstance(st, dict)
        else (
            context.ledger.get_state(sym)
            if hasattr(context, "ledger")
            else {}
        )
    )
    rc_epoch = safe_float(state_obj.get("last_reserve_check_ts"), 0.0)
    if rc_epoch > 0.0:
        elapsed_epoch = time.time() - rc_epoch
        if 0.0 <= elapsed_epoch < RESERVE_DEPOSIT_CHECK_INTERVAL_SEC:
            return True, round(
                RESERVE_DEPOSIT_CHECK_INTERVAL_SEC - elapsed_epoch, 1
            )

    return False, 0.0


def _get_live_soxl_price(
    context: Any,
    prices: Dict[str, float],
    holdings: Dict[str, Dict[str, Any]],
    now_est: datetime,
) -> float:
    """
    실시간 가격 딕셔너리(prices) -> 캔들 캐시 -> 보유 잔고 현재가 순으로 SOXL 현재가를 추출한다.
    """
    lp = safe_float((prices or {}).get(TARGET_SYMBOL), 0.0)
    if lp > 0.0:
        return lp
    raw_cache = getattr(context, "candle_metrics_cache", {})
    base_met = (
        raw_cache.get(TARGET_SYMBOL) if isinstance(raw_cache, dict) else None
    )
    if isinstance(base_met, dict):
        met = refresh_metrics_with_live_tick(base_met, 0.0, now_est=now_est)
        lp = safe_float(met.get("live_price"), 0.0)
        if lp > 0.0:
            return lp
    h_info = (holdings or {}).get(TARGET_SYMBOL, {})
    return safe_float(h_info.get("last_price"), 0.0)


async def _fetch_fresh_current_soxl_price(
    context: Any,
    fallback_price: float = 0.0,
) -> float:
    """
    🚨 Case 65, Case 73 & Case 80:
    60초 타임쉴드가 경과한 뒤 매수 조건 판정 및 지정가 주문 발주 직전에
    토스 Open API(/api/v1/prices)를 직접 호출하여 가장 최신의 실시간 현재가를 조회한다.
    """
    try:
        fresh_map = await context.api.get_current_prices_batch((TARGET_SYMBOL,))
        fresh_p = safe_float((fresh_map or {}).get(TARGET_SYMBOL), 0.0)
        if fresh_p > 0.0:
            if isinstance(getattr(context, "latest_prices", None), dict):
                context.latest_prices[TARGET_SYMBOL] = fresh_p
            if isinstance(getattr(context, "candle_metrics_cache", None), dict):
                base_met = context.candle_metrics_cache.get(TARGET_SYMBOL)
                if isinstance(base_met, dict):
                    context.candle_metrics_cache[TARGET_SYMBOL] = (
                        refresh_metrics_with_live_tick(base_met, fresh_p)
                    )
            return fresh_p
    except Exception as exc:
        logger.debug("매수 직전 실시간 현재가 재조회 폴백 사용: %s", exc)
    return safe_float(fallback_price, 0.0)


def min_req_cash_str(val: float) -> str:
    return f"{safe_float(val, 0.0):,.2f}"


# ---------------------------------------------------------------------------
# [핵심 0-B · Case 75, Case 77 & Case 80] GUARD30 자투리 차단 · 예수금 API 일시 오류 방어 · 토스 계좌 여유자금 감지 자동 수혈 · 단 1회 입금 요청 알림 실행기
# ---------------------------------------------------------------------------
async def _check_and_execute_guard30_or_reserve_injection(
    context: Any,
    st_now: Dict[str, Any],
    exec_order_p: float,
    portion_budget: float,
    l1_actual_cost_usd: float,
    is_dip_promotion: bool,
    is_vacant_l1_reentry: bool,
    trigger_desc: str,
) -> Tuple[bool, float, float, Dict[str, Any]]:
    """
    🚨 [Case 75, Case 77 & Case 80 : 💉 05_RESV_6P_GUARD30 실행 엔진]:
    매수 주문 발주 직전(뮤텍스 내부)에 호출되어:
    0) [Case 80 골든포켓 일시 가동 중 오발동 방어 및 60초 인메모리 쉴드]:
       만약 현재 독립 골든포켓(golden_pocket.qty > 0)에 가용 현금 100%가 일시 투입되어 있어
       now_free_cash 가 부족한 상태라면, 이는 시드 고갈이 아니라 골든포켓(+1.50% 익절 대기) 가동 상태이므로
       예비시드 수혈이나 입금 요청 알림을 발송하지 않고 60초 인메모리 쉴드(mark_reserve_deposit_check_shield)를
       작동시킨 뒤 조용히 대기(HOLD_CASH_DEPLOYED_IN_GOLDEN_POCKET)한다!
    1) 토스 실계좌 주문가능 달러(`raw_bp_usd = await context.api.get_buying_power_usd(safety_buffer_pct=0.0)`)를 조회하되,
       원장 가용현금이 충분함에도(`now_free_cash >= est_min_req`) 일시 네트워크 타임아웃으로 `0.0` 이 반환되면
       `0.25초` 후 1회 재시도하고, 여전히 `0.0` 이면 허위 시드고갈 알림 발송이나 영구 래치 잠금 없이
       해당 틱만 조용히 보류(`HOLD_TRANSIENT_BP_API_ERROR`)한다!
    2) `evaluate_guard30_and_reserve_injection()` 으로 30% 자투리 가드(`min_req_cash`) 통과 여부 및
       토스 계좌 미할당 여유 입금액(`raw_bp_usd - free_cash_usd`) 기반 예비시드 수혈 가능 여부를 판정한다.
    3) [PROCEED_NORMAL] / [INJECT_AND_PROCEED] / [BLOCK_AND_ALERT_DEPOSIT] 분기 처리:
       - MODIFIED [Case 75 & Case 77]: 이미 `waiting_reserve_deposit == True` 및 `waiting_reserve_deposit_alert_sent == True` 로
         진입해 있는 상태에서 60초 주기 재확인 시 미입금이 지속될 때는 인메모리 60초 쉴드만 재장전하고
         카운터(`dust_guard_blocked_cnt`, `daily_seed_protect_pass_cnt`) 중복 증가 및 원장 디스크 쓰기를 스킵한다!
    """
    now_free_cash = max(0.0, safe_float(st_now.get("free_cash_usd"), 0.0))
    cur_used_res = max(0, safe_int(st_now.get("used_reserve_portions_cnt"), 0))
    cur_inj_usd = max(0.0, safe_float(st_now.get("injected_reserve_usd"), 0.0))

    # MODIFIED [Case 80]: 독립 골든포켓(golden_pocket)이 보유 중이어서 현금이 골든포켓에 가동 중일 때
    # 일반 그리드 매수 시도로 인해 시드고갈 알림이나 예비시드 수혈이 오발동하는 현상을 차단하고 60초 인메모리 쉴드로 API 스팸을 방지!
    gp_now = pocket_from_dict(st_now.get("golden_pocket"))
    fee_mult = 1.0 + (ROUND_TRIP_FEE_RATE_PCT / 100.0)
    est_min_req = max(
        exec_order_p * fee_mult,
        portion_budget * MIN_DIP_BUDGET_RATIO,
        (l1_actual_cost_usd * MIN_DIP_VS_L1_RATIO if is_dip_promotion else 0.0),
    )
    if gp_now.is_active and now_free_cash < est_min_req:
        mark_reserve_deposit_check_shield(
            context=context, symbol=TARGET_SYMBOL, clear_shield=False
        )
        if is_vacant_l1_reentry:
            mark_reentry_monitor_60s_cycle_shield(
                context=context, symbol=TARGET_SYMBOL, eval_price=exec_order_p
            )
        return (
            False,
            now_free_cash,
            0.0,
            {
                "action": "HOLD_CASH_DEPLOYED_IN_GOLDEN_POCKET",
                "should_proceed": False,
                "golden_pocket_qty": gp_now.qty,
                "golden_pocket_cost_usd": gp_now.actual_cost_usd,
            },
        )

    raw_bp_usd = await context.api.get_buying_power_usd(safety_buffer_pct=0.0)
    # MODIFIED [Case 77 예수금 API 일시 오류(0.0 반환) 시 허위 시드고갈 알림 원천 차단]:
    # 원장 가용현금이 충분한데(now_free_cash >= est_min_req) 브로커 API가 0.0을 반환했다면 0.25초 후 1회 재시도한다.
    if raw_bp_usd <= 0.0 and now_free_cash >= est_min_req:
        await asyncio.sleep(0.25)
        raw_bp_usd = await context.api.get_buying_power_usd(
            safety_buffer_pct=0.0
        )
        if raw_bp_usd <= 0.0:
            logger.debug(
                "🛡️ [Case 77 예수금 API 일시 조회 지연 방어] 원장 가용현금($%.2f >= 최소 $%.2f) 정상이나 예수금 API가 0.0을 반환하여 허위 시드고갈 알림 없이 다음 루프 재시도",
                now_free_cash,
                est_min_req,
            )
            return (
                False,
                now_free_cash,
                0.0,
                {
                    "action": "HOLD_TRANSIENT_BP_API_ERROR",
                    "should_proceed": False,
                    "free_cash_usd": now_free_cash,
                    "min_req_cash": round(est_min_req, 4),
                },
            )

    eff_bp_for_eval: Optional[float] = (
        raw_bp_usd if raw_bp_usd > 0.0 else 0.0
    )

    guard_eval = evaluate_guard30_and_reserve_injection(
        free_cash_usd=now_free_cash,
        broker_bp_usd=eff_bp_for_eval,
        exec_price=exec_order_p,
        portion_budget=portion_budget,
        l1_actual_cost_usd=l1_actual_cost_usd,
        is_dip_promotion=is_dip_promotion,
        used_reserve_portions_cnt=cur_used_res,
        max_reserve_portions=MAX_RESERVE_PORTIONS,
    )
    action = str(guard_eval.get("action") or "BLOCK_AND_ALERT_DEPOSIT")
    eff_bp_for_order = round(raw_bp_usd * 0.998, 4) if raw_bp_usd > 0.0 else 0.0

    # [케이스 1] 현재 가용현금 및 실계좌 예수금이 충분한 경우 -> 정상 매수 진행
    if action == "PROCEED_NORMAL":
        if bool(st_now.get("waiting_reserve_deposit")) or bool(
            st_now.get("waiting_reserve_deposit_alert_sent")
        ):
            mark_reserve_deposit_check_shield(
                context, TARGET_SYMBOL, clear_shield=True
            )
            await context.ledger.update_state(
                TARGET_SYMBOL,
                waiting_reserve_deposit=False,
                waiting_reserve_deposit_alert_sent=False,
                required_reserve_deposit_usd=0.0,
                last_reserve_check_ts=0.0,
            )
        return True, now_free_cash, eff_bp_for_order, guard_eval

    # [케이스 2] 토스 계좌에 1회분 이상 여유자금이 입금되어 있어 온디맨드 예비시드 자동 수혈 실행!
    if action == "INJECT_AND_PROCEED":
        inj_portions = max(1, safe_int(guard_eval.get("inject_portions"), 1))
        inj_usd = round(max(0.01, safe_float(guard_eval.get("inject_usd"), 0.0)), 4)
        new_used_cnt = min(MAX_RESERVE_PORTIONS, cur_used_res + inj_portions)
        new_inj_usd = round(cur_inj_usd + inj_usd, 4)
        new_tot_inj_cnt = (
            safe_int(st_now.get("total_reserve_injected_cnt"), 0) + inj_portions
        )
        new_day_inj_cnt = (
            safe_int(st_now.get("daily_reserve_injected_cnt"), 0) + inj_portions
        )
        rem_after = max(0, MAX_RESERVE_PORTIONS - new_used_cnt)

        mark_reserve_deposit_check_shield(
            context, TARGET_SYMBOL, clear_shield=True
        )
        updated_st = await context.ledger.update_state(
            TARGET_SYMBOL,
            used_reserve_portions_cnt=new_used_cnt,
            injected_reserve_usd=new_inj_usd,
            total_reserve_injected_cnt=new_tot_inj_cnt,
            daily_reserve_injected_cnt=new_day_inj_cnt,
            waiting_reserve_deposit=False,
            waiting_reserve_deposit_alert_sent=False,
            required_reserve_deposit_usd=0.0,
            last_reserve_check_ts=0.0,
        )
        updated_free_cash = max(
            0.0,
            safe_float(updated_st.get("free_cash_usd"), now_free_cash + inj_usd),
        )
        logger.info(
            "💉 [Case 77 SOXL 온디맨드 예비시드 자동 수혈 완료] +%d회분(+%.2f$) 수혈 -> 가용현금 $%.2f (사용 %d/%d회분 · 잔여한도 %d회분 · 타점=%s)",
            inj_portions,
            inj_usd,
            updated_free_cash,
            new_used_cnt,
            MAX_RESERVE_PORTIONS,
            rem_after,
            trigger_desc,
        )
        if hasattr(context, "send_slim_alert"):
            await context.send_slim_alert(
                title=f"💉 [SOXL 예비시드 자동 수혈 (+{inj_portions}회분 · +${inj_usd:,.2f})]",
                body=(
                    f"시드고갈(30% 가드) 감지 즉시 토스 계좌 여유자금에서 +{inj_portions}회분(${inj_usd:,.2f}) 자동 수혈 완료! · "
                    f"수혈 후 가용현금 ${updated_free_cash:,.2f} · "
                    f"예비시드 사용 {new_used_cnt}/{MAX_RESERVE_PORTIONS}회분(잔여 {rem_after}회분 · 누적수혈 ${new_inj_usd:,.2f} / 0주 졸업 시 자동 상환) · "
                    f"즉시 {trigger_desc} 정량 매수를 집행합니다!"
                ),
            )
        return True, updated_free_cash, eff_bp_for_order, guard_eval

    # [케이스 3] 계좌 미입금 또는 6회분 한도 소진 -> 자투리 1주 매수 차단 & 단 1회 입금 요청 알림(영구 래치)
    already_waiting_dep = bool(st_now.get("waiting_reserve_deposit", False))
    alert_already_sent = bool(
        st_now.get("waiting_reserve_deposit_alert_sent", False)
    )
    rec_dep_usd = round(
        max(
            portion_budget,
            safe_float(guard_eval.get("recommended_deposit_usd"), portion_budget),
        ),
        2,
    )
    min_req_c = safe_float(guard_eval.get("min_req_cash"), portion_budget * 0.30)
    rem_portions = safe_int(guard_eval.get("rem_portions_before"), 0)
    needed_p = max(1, safe_int(guard_eval.get("needed_portions"), 1))

    now_rc_epoch = mark_reserve_deposit_check_shield(
        context, TARGET_SYMBOL, clear_shield=False
    )
    re_epoch = safe_float(st_now.get("last_reentry_eval_ts"), 0.0)
    if is_vacant_l1_reentry:
        re_epoch = mark_reentry_monitor_60s_cycle_shield(
            context=context, symbol=TARGET_SYMBOL, eval_price=exec_order_p
        )

    # MODIFIED [Case 75 & Case 77 : 이미 시드고갈 입금 대기 상태이고 1회 알림도 발송 완료된 경우 중복 카운터 증가 및 매 60초 os.fsync 디스크 쓰기 스킵!]
    if already_waiting_dep and alert_already_sent:
        prev_req_dep = safe_float(
            st_now.get("required_reserve_deposit_usd"), 0.0
        )
        if abs(prev_req_dep - rec_dep_usd) >= 1.0:
            await context.ledger.update_state(
                TARGET_SYMBOL,
                required_reserve_deposit_usd=rec_dep_usd,
            )
        return False, now_free_cash, eff_bp_for_order, guard_eval

    is_dust_blk = bool(guard_eval.get("is_dust_blocked", False))
    dust_inc = 1 if is_dust_blk else 0
    new_dust_cnt = safe_int(st_now.get("dust_guard_blocked_cnt"), 0) + dust_inc
    new_day_dust_cnt = (
        safe_int(st_now.get("daily_dust_guard_blocked_cnt"), 0) + dust_inc
    )
    new_pass_cnt = safe_int(st_now.get("seed_protect_pass_cnt"), 0) + 1
    new_day_pass = safe_int(st_now.get("daily_seed_protect_pass_cnt"), 0) + 1

    await context.ledger.update_state(
        TARGET_SYMBOL,
        waiting_reserve_deposit=True,
        waiting_reserve_deposit_alert_sent=True,
        required_reserve_deposit_usd=rec_dep_usd,
        last_reserve_check_ts=now_rc_epoch,
        last_reentry_eval_ts=re_epoch,
        dust_guard_blocked_cnt=new_dust_cnt,
        daily_dust_guard_blocked_cnt=new_day_dust_cnt,
        seed_protect_pass_cnt=new_pass_cnt,
        daily_seed_protect_pass_cnt=new_day_pass,
    )

    # 🚨 [스팸 원천 차단 안전망]: waiting_reserve_deposit_alert_sent 가 False 였을 때만 단 1회 발송!
    if not alert_already_sent and hasattr(context, "send_slim_alert"):
        if rem_portions >= needed_p:
            title_msg = (
                f"🚨 [💉 SOXL 시드고갈 감지 · 예비시드 {needed_p}회분(${rec_dep_usd:,.2f}) 입금 요청]"
            )
            body_msg = (
                f"타점({trigger_desc} @ ${exec_order_p:.2f}) 도달 · "
                f"현재 가용현금(${now_free_cash:,.2f}) 및 토스 주문가능금액(${raw_bp_usd:,.2f})이 "
                f"30% 자투리 승격 방지 가드(${min_req_cash_str(min_req_c)}) 미만이어서 자투리 매수를 차단했습니다. · "
                f"토스 달러 계좌에 1회분 이상(권장 ${rec_dep_usd:,.2f} · 잔여 예비한도 {rem_portions}/{MAX_RESERVE_PORTIONS}회분) 입금해 주시면 "
                f"60초 내 자동 감지하여 즉시 수혈 매수합니다! (※ 스팸 방지를 위해 입금 요청 알림은 1회만 발송됩니다)"
            )
        else:
            title_msg = (
                "🚨 [🛑 SOXL 시드고갈 및 예비시드 6회분 한도 소진 안내]"
            )
            body_msg = (
                f"타점({trigger_desc} @ ${exec_order_p:.2f}) 도달했으나 "
                f"가용현금(${now_free_cash:,.2f})이 30% 가드(${min_req_cash_str(min_req_c)}) 미만이고 "
                f"온디맨드 예비시드 한도({MAX_RESERVE_PORTIONS}/{MAX_RESERVE_PORTIONS}회분)를 모두 사용하여 추매를 보류하고 반등 익절을 대기합니다. "
                f"(※ 스팸 방지를 위해 본 알림은 1회만 발송됩니다)"
            )
        await context.send_slim_alert(title=title_msg, body=body_msg)
        logger.warning(
            "🚨 [Case 77 시드고갈 단 1회 입금 요청 알림 발송 완료 & 래치 잠금] 가용=$%.2f · 토스예수금=$%.2f · 30%%가드=$%.2f · 권장입금=$%.2f · 잔여한도=%d/%d회분",
            now_free_cash,
            raw_bp_usd,
            min_req_c,
            rec_dep_usd,
            rem_portions,
            MAX_RESERVE_PORTIONS,
        )

    return False, now_free_cash, eff_bp_for_order, guard_eval


# ---------------------------------------------------------------------------
# [핵심 1] 매수 체결(FILLED) 커밋 · 비례 자투리 정산(Case 78) · 독립 골든포켓/1~7층 순수 그리드 배치(Case 80) · 매수 후 60초 타임쉴드 각인
# ---------------------------------------------------------------------------
async def _commit_filled_buy_to_stratum_ledger(
    context: Any,
    filled_qty: int,
    avg_fill_price: float,
    portion_budget: float,
    lot_type: str,
    settled_order_id: str = "",
    ordered_qty: Optional[int] = None,
) -> Dict[str, Any]:
    """
    🎯 1, 🎯 3, 🎯 4 & Case 25, 46, 53, 59, 60, 61, 65, 67, 69, 71, 72, 73, 74, 76, 77, 78, 80:
    매수 주문 체결(FILLED 또는 부분 체결 후 60초 타임아웃 종료)이 확인된 즉시:
    0) 🚨 [Case 80 : POCKET_ALLIN 모드 독립 골든포켓(lot_type == "GOLDEN_POCKET") 체결 분리 정산]:
       - 기존 1층 ~ 7층 그리드(old_buckets), anchor_price, cycle_min_buy_price, l1_target_quota_qty 를
         전혀 변경하거나 승격시키지 않고 원장의 golden_pocket 에 순수 원가로 독립 기록한다!
       - 자투리 절약금은 0.0 으로 처리하여 허위 자투리 누적을 방지하고,
         매수 후 60.0초 타임쉴드 및 15.0초 인덱싱 그레이스 쉴드를 각인한 뒤 +1.50% 독립 익절 타점을 감시한다.
    1) 🚨 [Case 78 부분 체결 시 체결 수량 비례 예산 자투리 정산 (GOLDEN_L1 전액매수는 자투리 0.0 처리)]:
       - 일반 8% 정량 매수 시 전량 체결이면 eff_portion_budget = raw_portion_budget 으로 산출하고,
         부분 체결(q_int < ord_q)이면 체결 수량 비례 예산 대비 절약액만 자투리로 정산한다.
    2) vrev_add_quota_lot_and_merge_2tier() 를 호출하여 1~7층 그리드 배치/승격/합산을 수행한다.
    """
    st = context.ledger.get_state(TARGET_SYMBOL)
    old_buckets = buckets_from_dicts(st.get("buckets", []))
    old_gp = pocket_from_dict(st.get("golden_pocket"))
    today_est_str = datetime.now(EST_TZ).strftime("%Y-%m-%d")

    q_int = max(1, safe_int(filled_qty, 1))
    ord_q = max(
        q_int,
        safe_int(
            ordered_qty
            if ordered_qty is not None
            else st.get("ordered_qty"),
            q_int,
        ),
    )
    fill_p = round(max(0.01, safe_float(avg_fill_price, 0.01)), 4)
    actual_spent = round(float(q_int) * fill_p, 4)
    tag = str(lot_type or "QUOTA_L1").upper().strip()
    eff_oid = str(settled_order_id or st.get("buy_order_id") or "").strip()

    settled_oids: List[str] = list(st.get("last_settled_order_ids") or [])
    if eff_oid and eff_oid not in settled_oids:
        settled_oids.append(eff_oid)
    settled_oids = settled_oids[-50:]

    now_buy_epoch = time.time()

    # -----------------------------------------------------------------------
    # [Case 80 분기 : 독립 골든포켓(lot_type == "GOLDEN_POCKET") 체결 커밋]
    # -> 기존 1~7층 그리드(old_buckets) 및 기억저가를 전혀 건드리지 않고 golden_pocket 에만 독립 기록!
    # -----------------------------------------------------------------------
    if tag == "GOLDEN_POCKET":
        if old_gp.is_active:
            comb_gp_q = old_gp.qty + q_int
            comb_gp_cost = round(old_gp.actual_cost_usd + actual_spent, 4)
            comb_gp_p = round(comb_gp_cost / float(comb_gp_q), 4)
            new_gp = GoldenAllInPocket(
                qty=comb_gp_q,
                book_price=comb_gp_p,
                book_invested_usd=comb_gp_cost,
                actual_cost_usd=comb_gp_cost,
                entry_ts=now_buy_epoch,
                order_date=today_est_str,
            )
        else:
            new_gp = GoldenAllInPocket(
                qty=q_int,
                book_price=fill_p,
                book_invested_usd=actual_spent,
                actual_cost_usd=actual_spent,
                entry_ts=now_buy_epoch,
                order_date=today_est_str,
            )

        tot_buy_ev = safe_int(st.get("total_buy_events"), 0) + 1
        tot_buy_sh = safe_int(st.get("total_buy_shares"), 0) + q_int
        day_buy_ev = safe_int(st.get("daily_buy_events"), 0) + 1
        g_buy_ev = safe_int(st.get("golden_allin_buy_events"), 0) + 1
        day_g_buy_ev = safe_int(st.get("daily_golden_allin_buy_events"), 0) + 1

        mark_auto_fill_grace_shield(
            context=context,
            symbol=TARGET_SYMBOL,
            lot_type="GOLDEN_POCKET",
            fill_price=fill_p,
            filled_qty=q_int,
        )
        mark_reserve_deposit_check_shield(
            context=context,
            symbol=TARGET_SYMBOL,
            clear_shield=True,
        )

        updated_st = await context.ledger.update_state(
            TARGET_SYMBOL,
            golden_pocket=new_gp.to_dict(),
            last_golden_allin_date=today_est_str,
            buy_order_id="",
            ordered_qty=0,
            buy_price=0.0,
            pending_portion_budget=0.0,
            pending_lot_type="",
            pending_step_up_min_price=0.0,
            waiting_reserve_deposit=False,
            waiting_reserve_deposit_alert_sent=False,
            required_reserve_deposit_usd=0.0,
            last_reserve_check_ts=0.0,
            last_settled_order_ids=settled_oids,
            total_buy_events=tot_buy_ev,
            total_buy_shares=tot_buy_sh,
            daily_buy_events=day_buy_ev,
            golden_allin_buy_events=g_buy_ev,
            daily_golden_allin_buy_events=day_g_buy_ev,
            last_buy_fill_ts=now_buy_epoch,
        )
        context.wakeup_event.set()
        free_cash_now = safe_float(updated_st.get("free_cash_usd"), 0.0)
        gp_target_p = new_gp.target_sell_price(rise_pct=GOLDEN_POCKET_RISE_PCT)
        grid_sh = sum(b.qty for b in old_buckets)

        if hasattr(context, "send_slim_alert"):
            await context.send_slim_alert(
                title=(
                    f"🌟 [SOXL 황금시간 독립 골든포켓 100% 전액매수 체결] "
                    f"{q_int}주 @ ${fill_p:.2f}"
                ),
                body=(
                    f"실사용 ${actual_spent:,.2f} · "
                    f"🛡️60초 타임쉴드 후 골든포켓 단독 익절목표 ${gp_target_p:.2f}(+1.5%) ⚡1.5초 실시간 감시! · "
                    f"기존 그리드({len(old_buckets)}개층·{grid_sh}주) 원가·회차·기억저가 100% 비오염 보존 · "
                    f"잔여 가용현금 ${free_cash_now:,.2f}"
                ),
            )
        return {
            "status": "GOLDEN_POCKET_FILLED",
            "symbol": TARGET_SYMBOL,
            "lot_type": "GOLDEN_POCKET",
            "filled_qty": q_int,
            "ordered_qty": ord_q,
            "fill_price": fill_p,
            "actual_spent_usd": actual_spent,
            "golden_pocket_target_price": gp_target_p,
            "free_cash_usd": free_cash_now,
        }

    # -----------------------------------------------------------------------
    # [일반 8% 정량 매수(REENTRY_1FL / TOPUP_1FL / DIP_1FL) 및 GRID_L1_ALLIN(GOLDEN_L1) 커밋]
    # -----------------------------------------------------------------------
    raw_portion_budget = safe_float(portion_budget, 0.0)
    if tag == "GOLDEN_L1" or raw_portion_budget <= 0.0:
        eff_portion_budget = actual_spent
        saved_from_portion = 0.0
    elif q_int < ord_q and ord_q > 0:
        eff_portion_budget = round(
            raw_portion_budget * (float(q_int) / float(ord_q)), 4
        )
        saved_from_portion = round(
            max(0.0, eff_portion_budget - actual_spent), 4
        )
    else:
        eff_portion_budget = raw_portion_budget
        saved_from_portion = round(
            max(0.0, eff_portion_budget - actual_spent), 4
        )

    was_empty = len(old_buckets) == 0
    was_l2_only = bool(
        len(old_buckets) > 0 and not has_active_l1_bucket(old_buckets)
    )
    prev_l1_p = (
        old_buckets[0].book_price
        if (old_buckets and has_active_l1_bucket(old_buckets))
        else 0.0
    )

    new_buckets = vrev_add_quota_lot_and_merge_2tier(
        queue=old_buckets,
        buy_qty=q_int,
        buy_price=fill_p,
        actual_spent_usd=actual_spent,
        lot_type=tag,
        max_tiers=MAX_GRID_TIERS_7,
    )

    # MODIFIED [Case 67, Case 78 & Case 80 : 1층 목표 정량(l1_target_quota_qty) 보존 및 이전 층 수량 오염 차단]
    raw_target_q = max(0, safe_int(st.get("l1_target_quota_qty"), 0))
    cur_l1_qty = new_buckets[0].qty if new_buckets else q_int
    if tag == "GOLDEN_L1":
        next_l1_target_q = cur_l1_qty
    elif tag == "TOPUP_1FL":
        next_l1_target_q = max(cur_l1_qty, raw_target_q)
    else:
        next_l1_target_q = max(cur_l1_qty, ord_q)
    rem_after_fill = max(0, next_l1_target_q - cur_l1_qty)

    # 🚨 Case 60, Case 72 & Case 76: 정적 기억 최저가 잠금 및 STEP2X_15PCT_C20 스텝업 해금 갱신!
    old_min_p = safe_float(st.get("cycle_min_buy_price"), 0.0)
    pending_step_up_p = safe_float(st.get("pending_step_up_min_price"), 0.0)
    is_step_up_unlock_fill = False

    if was_empty or old_min_p <= 0.0:
        new_cycle_min_p = fill_p
    elif pending_step_up_p > 0.0 and tag not in (
        "REENTRY_1FL",
        "TOPUP_1FL",
        "GOLDEN_L1",
    ):
        new_cycle_min_p = round(min(pending_step_up_p, fill_p), 4)
        is_step_up_unlock_fill = True
    else:
        new_cycle_min_p = round(min(old_min_p, fill_p), 4)

    new_held_lots = sum(b.lot_count for b in new_buckets)
    new_held_shares = sum(b.qty for b in new_buckets)
    new_held_tiers = len(new_buckets)

    tot_buy_ev = safe_int(st.get("total_buy_events"), 0) + 1
    tot_buy_sh = safe_int(st.get("total_buy_shares"), 0) + q_int
    day_buy_ev = safe_int(st.get("daily_buy_events"), 0) + 1
    unlock_inc = 1 if is_step_up_unlock_fill else 0
    cond_unlock_ev = safe_int(st.get("cond_unlock_buy_events"), 0) + unlock_inc
    day_unlock_ev = safe_int(st.get("daily_unlock_buy_events"), 0) + unlock_inc
    g_inc = 1 if tag == "GOLDEN_L1" else 0
    g_buy_ev = safe_int(st.get("golden_allin_buy_events"), 0) + g_inc
    day_g_buy_ev = safe_int(st.get("daily_golden_allin_buy_events"), 0) + g_inc
    last_g_date = (
        today_est_str
        if tag == "GOLDEN_L1"
        else str(st.get("last_golden_allin_date") or "")
    )
    extra_13 = safe_int(st.get("extra_13plus_buy_events"), 0) + (
        1
        if (tag != "TOPUP_1FL" and new_held_lots > BASE_MAX_LOTS_8PCT)
        else 0
    )
    cum_saved = round(
        safe_float(st.get("cumulative_leftover_saved_usd"), 0.0)
        + saved_from_portion,
        4,
    )
    day_saved = round(
        safe_float(st.get("daily_leftover_saved_usd"), 0.0)
        + saved_from_portion,
        4,
    )

    mark_auto_fill_grace_shield(
        context=context,
        symbol=TARGET_SYMBOL,
        lot_type=tag,
        fill_price=fill_p,
        filled_qty=q_int,
    )
    mark_reentry_monitor_60s_cycle_shield(
        context=context,
        symbol=TARGET_SYMBOL,
        eval_price=fill_p,
        clear_shield=True,
    )
    mark_reserve_deposit_check_shield(
        context=context,
        symbol=TARGET_SYMBOL,
        clear_shield=True,
    )

    updated_st = await context.ledger.update_state(
        TARGET_SYMBOL,
        buckets=buckets_to_dicts(new_buckets),
        anchor_price=new_buckets[0].book_price if new_buckets else fill_p,
        cycle_min_buy_price=round(new_cycle_min_p, 4),
        ratchet_anchor_price=new_buckets[0].book_price if new_buckets else fill_p,
        cycle_reanchor_credit_usd=0.0,
        l1_target_quota_qty=next_l1_target_q,
        last_golden_allin_date=last_g_date,
        buy_order_id="",
        ordered_qty=0,
        buy_price=0.0,
        pending_portion_budget=0.0,
        pending_lot_type="",
        pending_step_up_min_price=0.0,
        waiting_reserve_deposit=False,
        waiting_reserve_deposit_alert_sent=False,
        required_reserve_deposit_usd=0.0,
        last_reserve_check_ts=0.0,
        last_settled_order_ids=settled_oids,
        total_buy_events=tot_buy_ev,
        total_buy_shares=tot_buy_sh,
        daily_buy_events=day_buy_ev,
        cond_unlock_buy_events=cond_unlock_ev,
        daily_unlock_buy_events=day_unlock_ev,
        golden_allin_buy_events=g_buy_ev,
        daily_golden_allin_buy_events=day_g_buy_ev,
        extra_13plus_buy_events=extra_13,
        cumulative_leftover_saved_usd=cum_saved,
        daily_leftover_saved_usd=day_saved,
        entry_ts=now_buy_epoch,
        last_buy_fill_ts=now_buy_epoch,
        last_reentry_eval_ts=0.0,
    )

    context.wakeup_event.set()
    free_cash_now = safe_float(updated_st.get("free_cash_usd"), 0.0)
    summary = summarize_stratum_portfolio(updated_st, live_price=fill_p)
    l1_target = safe_float(summary.get("l1_target_price"), 0.0)
    u_cnt = safe_int(summary.get("upper_tier_count"), 0)
    u_qty = safe_int(summary.get("upper_qty"), 0)
    u_wma_p = safe_float(summary.get("upper_wma_price"), 0.0)
    u_wma_t = safe_float(summary.get("upper_wma_target_price"), 0.0)
    trig_buy_p = safe_float(summary.get("trigger_buy_price"), 0.0)
    drop_req_p = safe_float(summary.get("drop_buy_pct"), -1.0)
    l1_book_now = new_buckets[0].book_price if new_buckets else fill_p

    if hasattr(context, "send_slim_alert"):
        rem_quota_note = (
            f" · 🎯미체결 잔량 {rem_after_fill}주(목표 {next_l1_target_q}주 중 {cur_l1_qty}주 체결 ➔ "
            f"🛡️60초 타임쉴드 후 1.5초 모니터에서 ${l1_book_now:.2f} 이하 도래 시 잔량 60초 지정가 재대기!)"
            if rem_after_fill > 0
            else ""
        )
        if tag == "GOLDEN_L1":
            upper_note = (
                f" · 2~{new_held_tiers}층({u_cnt}개층·{u_qty}주) 순수이평 ${u_wma_p:.2f}(목표 ${u_wma_t:.2f})"
                if len(new_buckets) >= 2
                else ""
            )
            title_str = (
                f"🔥 [SOXL 황금시간 7층그리드 1층 100% 전액편입 체결] "
                f"{q_int}주 @ ${fill_p:.2f} ({new_held_tiers}개층)"
            )
            body_str = (
                f"실사용 ${actual_spent:,.2f} · "
                f"🛡️60초 타임쉴드 후 1층목표 ${l1_target:.2f}(+1.5%) 감시{upper_note} · "
                f"기억저가 ${new_cycle_min_p:.2f} · 가용현금 ${free_cash_now:,.2f} (총 {new_held_shares}주)"
            )
        elif tag == "TOPUP_1FL":
            done_badge = (
                f"정량 {next_l1_target_q}주 완수!"
                if rem_after_fill == 0
                else f"잔여 {rem_after_fill}주 추가 대기"
            )
            title_str = (
                f"🎯 [SOXL 1층 미체결 잔량 보충 체결] +{q_int}주 @ ${fill_p:.2f} "
                f"(1층 {cur_l1_qty}/{next_l1_target_q}주 합산 · {done_badge})"
            )
            body_str = (
                f"실사용 ${actual_spent:,.2f} (자투리 +${saved_from_portion:.2f} 시드보존) · "
                f"2층 승격 없이 기존 1층 합산(단가 ${l1_book_now:.2f} · 익절목표 ${l1_target:.2f}){rem_quota_note} · "
                f"가용현금 ${free_cash_now:,.2f} (총 {new_held_shares}주)"
            )
        elif was_l2_only and tag == "REENTRY_1FL" and len(new_buckets) >= 2:
            title_str = (
                f"🔥 [SOXL 현재가 지정가 1층 재장전 체결] {q_int}주 @ ${fill_p:.2f} (상단 {u_cnt}개층 비병합)"
            )
            body_str = (
                f"실사용 ${actual_spent:,.2f} (자투리 +${saved_from_portion:.2f} 시드보존) · "
                f"🛡️60초 타임쉴드 후 1층목표 ${l1_target:.2f}(+1.5%) 감시{rem_quota_note} · "
                f"2~{new_held_tiers}층({u_qty}주) 이평 ${u_wma_p:.2f}(목표 ${u_wma_t:.2f}) 유지 · "
                f"기억저가 ${new_cycle_min_p:.2f}(와이드 {drop_req_p:.1f}% 추매가 ${trig_buy_p:.2f}) · "
                f"가용현금 ${free_cash_now:,.2f}"
            )
        elif is_step_up_unlock_fill:
            reb_m = (
                prev_l1_p / max(0.01, old_min_p)
                if (prev_l1_p > 0.0 and old_min_p > 0.0)
                else 2.0
            )
            title_str = (
                f"🔓 [SOXL 스텝업 저가 해금 추매 체결 ({new_held_lots}회차/{new_held_tiers}개층)] {q_int}주 @ ${fill_p:.2f}"
            )
            body_str = (
                f"구저가 ${old_min_p:.2f}(반등 {reb_m:.2f}x) ➔ 스텝업 잠금저가 ${new_cycle_min_p:.2f} 갱신! · "
                f"실사용 ${actual_spent:,.2f} (자투리 +${saved_from_portion:.2f} 시드보존) · "
                f"🛡️60초 타임쉴드 후 1층목표 ${l1_target:.2f} & 2~{new_held_tiers}층({u_qty}주) 이평 ${u_wma_p:.2f}(목표 ${u_wma_t:.2f}) 감시{rem_quota_note} · "
                f"차기단차 {drop_req_p:.1f}%(${trig_buy_p:.2f}) · 가용현금 ${free_cash_now:,.2f}"
            )
        else:
            upper_note = ""
            if len(new_buckets) >= 2:
                upper_note = (
                    f" · 2~{new_held_tiers}층({u_cnt}개층·{u_qty}주) 순수이평 ${u_wma_p:.2f}(목표 ${u_wma_t:.2f})"
                )
            title_str = (
                f"🔵 [SOXL {new_held_lots}회차({new_held_tiers}개층) 현재가 지정가 매수 체결] {q_int}주 @ ${fill_p:.2f}"
            )
            body_str = (
                f"실사용 ${actual_spent:,.2f} (자투리 +${saved_from_portion:.2f} 시드보존) "
                f"· 🛡️60초 타임쉴드 후 1층목표 ${l1_target:.2f} 감시{upper_note}{rem_quota_note} · 차기단차 {drop_req_p:.1f}%(${trig_buy_p:.2f}) "
                f"· 가용현금 ${free_cash_now:,.2f} (총 {new_held_shares}주)"
            )
        await context.send_slim_alert(title=title_str, body=body_str)

    return {
        "status": "BUY_FILLED_AND_MERGED",
        "symbol": TARGET_SYMBOL,
        "lot_type": tag,
        "is_step_up_unlock": is_step_up_unlock_fill,
        "filled_qty": q_int,
        "ordered_qty": ord_q,
        "l1_target_quota_qty": next_l1_target_q,
        "l1_rem_quota_qty": rem_after_fill,
        "fill_price": fill_p,
        "actual_spent_usd": actual_spent,
        "saved_from_portion_usd": saved_from_portion,
        "cycle_min_buy_price": round(new_cycle_min_p, 4),
        "held_lots": new_held_lots,
        "held_tiers": new_held_tiers,
        "held_shares": new_held_shares,
        "free_cash_usd": free_cash_now,
    }


async def sync_pending_buy_order_plugin(
    context: Any,
    holdings: Dict[str, Dict[str, Any]],
    prices: Dict[str, float],
    now_est: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    🎯 1 & 🎯 5 & Case 19, 24, 59, 60, 61, 65, 71, 72, 73, 76, 77, 78, 80:
    장부에 대기 중인 미체결 매수 주문(buy_order_id)이 존재할 때:
    1) GET /api/v1/orders/{orderId} 로 실제 체결 상태(FILLED / PARTIAL_FILLED / PENDING / CANCELED)를 조회한다.
    2) FILLED(또는 부분 체결 후 취소 종료) 확인 즉시 실제 평균 체결가(execution.averageFilledPrice)와
       체결 수량(filledQuantity), 원주문 수량(ordered_qty)을 _commit_filled_buy_to_stratum_ledger() 에 전달한다.
    3) 단 1주도 체결되지 않고(filled_q == 0) 취소/거부된 경우:
       - GOLDEN_POCKET / GOLDEN_L1 주문이었으면 last_golden_allin_date 를 "" 로 원복하여
         07:00 ~ 07:50 EST 시간창 내 재타격 기회를 보존한다(Case 80).
    4) 프로세스 재기동으로 인해 last_modify_mono 단조시계가 역전(last_mod > now_mono)되었거나 0.0 인 경우
       즉시 현재 단조시계로 자가 치유하여 60.0초(BUY_ORDER_MAX_WAIT_SEC) 타임아웃 안전 취소를 100% 보장한다(Case 65).
    """
    st = context.ledger.get_state(TARGET_SYMBOL)
    buy_oid = str(st.get("buy_order_id") or "").strip()
    if not buy_oid:
        return {"status": "NO_PENDING_BUY"}

    ordered_qty = max(1, safe_int(st.get("ordered_qty"), 1))
    ord_price = safe_float(st.get("buy_price"), 0.0)
    portion_budget = safe_float(
        st.get("pending_portion_budget"), float(ordered_qty) * ord_price
    )
    lot_type = str(st.get("pending_lot_type") or "QUOTA_L1").upper().strip()
    buckets_now = buckets_from_dicts(st.get("buckets", []))
    has_active_l1_now = has_active_l1_bucket(buckets_now)
    is_vacant_l1_now = bool(len(buckets_now) > 0 and not has_active_l1_now)
    cur_target_q = max(0, safe_int(st.get("l1_target_quota_qty"), 0))
    fallback_target_q_on_zero_cancel = (
        max(buckets_now[0].qty, cur_target_q)
        if (lot_type in ("TOPUP_1FL", "GOLDEN_POCKET") and has_active_l1_now)
        else (buckets_now[0].qty if has_active_l1_now else 0)
    )
    is_golden_lot = lot_type in ("GOLDEN_POCKET", "GOLDEN_L1")

    # MODIFIED [Case 65 : 프로세스 재기동 후 단조 시계(last_modify_mono) 역전 또는 결측 시 즉시 자가 치유]
    now_mono = time.monotonic()
    last_mod = safe_float(st.get("last_modify_mono"), 0.0)
    if last_mod <= 0.0 or last_mod > now_mono:
        last_mod = now_mono
        await context.ledger.update_state(
            TARGET_SYMBOL, last_modify_mono=last_mod
        )
    elapsed_mod = max(0.0, now_mono - last_mod)

    detail = await context.api.get_order_detail(buy_oid)
    if isinstance(detail, dict):
        ord_status = str(detail.get("status") or "").upper().strip()
        exec_obj = (
            detail.get("execution")
            if isinstance(detail.get("execution"), dict)
            else {}
        )
        filled_q = safe_int(exec_obj.get("filledQuantity"), 0)
        avg_fill_p = safe_float(exec_obj.get("averageFilledPrice"), 0.0)

        # 1) 전량 체결 완료(FILLED) 또는 부분 체결 후 종료된 경우
        if ord_status == "FILLED" or (
            filled_q > 0 and ord_status in ("CANCELED", "REJECTED", "REPLACED")
        ):
            eff_q = filled_q if filled_q > 0 else ordered_qty
            eff_p = avg_fill_p if avg_fill_p > 0.0 else ord_price
            return await _commit_filled_buy_to_stratum_ledger(
                context=context,
                filled_qty=eff_q,
                avg_fill_price=eff_p,
                portion_budget=portion_budget,
                lot_type=lot_type,
                settled_order_id=buy_oid,
                ordered_qty=ordered_qty,
            )

        # 2) 부분 체결(PARTIAL_FILLED) 진행 중인 경우 -> 60.0초까지 잔량 체결 대기 후 미체결분 안전 취소 & 기체결분 반영
        if ord_status == "PARTIAL_FILLED" or filled_q > 0:
            if elapsed_mod >= BUY_ORDER_MAX_WAIT_SEC:
                try:
                    await context.api.cancel_order(buy_oid)
                except Exception:
                    pass
                final_det = await context.api.get_order_detail(buy_oid)
                if isinstance(final_det, dict):
                    f_ex = (
                        final_det.get("execution")
                        if isinstance(final_det.get("execution"), dict)
                        else {}
                    )
                    f_q2 = safe_int(f_ex.get("filledQuantity"), filled_q)
                    f_p2 = safe_float(
                        f_ex.get("averageFilledPrice"), avg_fill_p
                    )
                    if f_q2 > 0:
                        filled_q = f_q2
                    if f_p2 > 0.0:
                        avg_fill_p = f_p2
                eff_p = avg_fill_p if avg_fill_p > 0.0 else ord_price
                return await _commit_filled_buy_to_stratum_ledger(
                    context=context,
                    filled_qty=filled_q,
                    avg_fill_price=eff_p,
                    portion_budget=portion_budget,
                    lot_type=lot_type,
                    settled_order_id=buy_oid,
                    ordered_qty=ordered_qty,
                )
            return {
                "status": "BUY_PARTIAL_FILLED_WAITING",
                "filled_qty": filled_q,
                "ordered_qty": ordered_qty,
            }

        # 3) 미체결 상태로 취소/거부된 경우 장부 락 해제
        if ord_status in ("CANCELED", "REJECTED") and filled_q == 0:
            re_epoch = (
                mark_reentry_monitor_60s_cycle_shield(
                    context=context, symbol=TARGET_SYMBOL, eval_price=ord_price
                )
                if (is_vacant_l1_now and not is_golden_lot)
                else safe_float(st.get("last_reentry_eval_ts"), 0.0)
            )
            clear_kw: Dict[str, Any] = {
                "l1_target_quota_qty": fallback_target_q_on_zero_cancel,
                "buy_order_id": "",
                "ordered_qty": 0,
                "buy_price": 0.0,
                "pending_portion_budget": 0.0,
                "pending_lot_type": "",
                "pending_step_up_min_price": 0.0,
                "last_reentry_eval_ts": re_epoch,
            }
            if is_golden_lot:
                clear_kw["last_golden_allin_date"] = ""
            await context.ledger.update_state(TARGET_SYMBOL, **clear_kw)
            return {"status": f"BUY_ORDER_{ord_status}_CLEARED"}

    # 🚨 4) [Case 65, Case 73, Case 76, Case 78 & Case 80] 매도 1호가(Ask 1) 상향 추격 정정 완전 소각! (60초 대기 후 안전 취소)
    if elapsed_mod >= BUY_ORDER_MAX_WAIT_SEC:
        try:
            await context.api.cancel_order(buy_oid)
        except Exception:
            pass

        final_detail = await context.api.get_order_detail(buy_oid)
        if isinstance(final_detail, dict):
            f_status = str(final_detail.get("status") or "").upper().strip()
            f_exec = (
                final_detail.get("execution")
                if isinstance(final_detail.get("execution"), dict)
                else {}
            )
            f_qty = safe_int(f_exec.get("filledQuantity"), 0)
            f_avg = safe_float(f_exec.get("averageFilledPrice"), 0.0)
            if f_status == "FILLED" or f_qty > 0:
                return await _commit_filled_buy_to_stratum_ledger(
                    context=context,
                    filled_qty=(f_qty if f_qty > 0 else ordered_qty),
                    avg_fill_price=(f_avg if f_avg > 0.0 else ord_price),
                    portion_budget=portion_budget,
                    lot_type=lot_type,
                    settled_order_id=buy_oid,
                    ordered_qty=ordered_qty,
                )

        re_epoch = (
            mark_reentry_monitor_60s_cycle_shield(
                context=context, symbol=TARGET_SYMBOL, eval_price=ord_price
            )
            if (is_vacant_l1_now and not is_golden_lot)
            else safe_float(st.get("last_reentry_eval_ts"), 0.0)
        )
        timeout_kw: Dict[str, Any] = {
            "l1_target_quota_qty": fallback_target_q_on_zero_cancel,
            "buy_order_id": "",
            "ordered_qty": 0,
            "buy_price": 0.0,
            "pending_portion_budget": 0.0,
            "pending_lot_type": "",
            "pending_step_up_min_price": 0.0,
            "last_reentry_eval_ts": re_epoch,
        }
        if is_golden_lot:
            timeout_kw["last_golden_allin_date"] = ""
        await context.ledger.update_state(TARGET_SYMBOL, **timeout_kw)
        logger.info(
            "⏳ [SOXL 현재가 지정가 매수(%s) 60초 미체결 안전 취소] 지정가 $%.2f 유지 종료 ➔ 관망 복귀",
            lot_type,
            ord_price,
        )
        return {"status": "BUY_ORDER_UNFILLED_CANCELED_SAFE"}

    return {"status": "BUY_ORDER_PENDING", "orderId": buy_oid}


# 하위 호환 별칭
sync_dynamic_vwap_buy_order_modify = sync_pending_buy_order_plugin
