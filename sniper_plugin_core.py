# -*- coding: utf-8 -*-
"""
# MODIFIED: sniper_plugin_core.py (Part 1/2 — 황금시간 07:00~07:50 RSI<=19 올인 전면 영구 소각 &
# 바벨 모드[BARBELL_60_30_10] 시 4단계 우선순위[현금10%➔정규장SGOV10%➔수익금고➔추가현금] 8% 자동수혈 위임 훅 결속 &
# 타 모드 전환 시 격리 수익금[vaulted_profit_locked_usd] 오인 수혈 차단 마스킹 &
# Case 91 무제한 예비수혈 카운트 · Case 92 실시간 1분봉 Wilder RSI(14) 추출기 탑재)
인피니트 스노우볼 (Infinite Snowball) v3.0 — 스나이퍼 매수 코어 Part 1 / 2
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from barbell_plugin import (
    PORTION_MODE_BARBELL,
    evaluate_and_execute_barbell_guard30_or_injection,
    is_barbell_mode,
)
from quant_engine import (
    BASE_MAX_LOTS_8PCT,
    DEFAULT_GRID_MERGE_MODE,
    MAX_GRID_TIERS_7,
    MAX_RESERVE_PORTIONS,
    MIN_DIP_BUDGET_RATIO,
    MIN_DIP_VS_L1_RATIO,
    PORTION_MODE_COMPOUND,
    PORTION_MODE_SIMPLE,
    REENTRY_BREAKOUT_MAX_RSI_50,
    REENTRY_BREAKOUT_RISE_PCT,
    ROUND_TRIP_FEE_RATE_PCT,
    SUB_FROZEN_DAYS_TRIGGER,
    SUB_GRID_DEFAULT_ENABLED,
    SUB_MAX_TIERS_3,
    SUB_MAX_TOTAL_LOTS_4,
    SUB_MERGE_MODE_L1_L3,
    SUB_PORTION_RATIO_4PCT,
    SUB_RESERVE_MAIN_PORTIONS,
    SUB_UNLOCK_DROP_FROM_L1_PCT,
    SUB_UNLOCK_FROZEN_DAYS_10,
    add_lot_to_sub_grid,
    add_lot_to_sub_grid_with_flag,
    buckets_from_dicts,
    buckets_to_dicts,
    evaluate_guard30_and_reserve_injection,
    has_active_l1_bucket,
    is_simple_income_mode,
    resolve_effective_round_trip_fee_rate_pct,
    resolve_portion_budget_base_equity,
    summarize_stratum_portfolio,
    vrev_add_quota_lot_and_merge_2tier,
)
from quant_indicators_plugin import (
    compute_soxl_quant_metrics_1m,
    is_late_regular_new_cycle_cutoff_window,
    refresh_metrics_with_live_tick,
)
from sniper_exit_plugin import (
    is_within_post_buy_time_shield,
    is_within_post_sell_time_shield,
    reset_sniper_l1_trail_slots,
)
import toss_api
from toss_api import (
    EST_TZ,
    TARGET_SYMBOL,
    safe_float,
    safe_int,
)

logger = logging.getLogger("toss_sniper.sniper_plugin_core")

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

BUY_ORDER_MAX_WAIT_SEC: float = 60.0
AUTO_FILL_GRACE_SHIELD_SEC: float = 15.0
REENTRY_MONITOR_TIME_SHIELD_SEC: float = 60.0
RESERVE_DEPOSIT_CHECK_INTERVAL_SEC: float = 60.0


# ---------------------------------------------------------------------------
# 내부 헬퍼 : 매수·매도 체결 직후 잔고 인덱싱 시차 보호 그레이스 쉴드 & 60초 타임쉴드 각인
# ---------------------------------------------------------------------------
def mark_auto_fill_grace_shield(
    context: Any,
    symbol: str = TARGET_SYMBOL,
    lot_type: str = "QUOTA_L1",
    fill_price: float = 0.0,
    filled_qty: int = 0,
) -> None:
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    now_mono = time.monotonic()
    now_epoch = time.time()
    tag = str(lot_type or "QUOTA_L1").upper().strip()
    is_sub_tag = tag.startswith("SUB_")

    guard_map = getattr(context, "indexing_grace_cache", None)
    if isinstance(guard_map, dict):
        prev = (
            guard_map.get(sym) if isinstance(guard_map.get(sym), dict) else {}
        )
        updated = dict(prev)
        updated["last_auto_fill_ts"] = now_mono
        updated["lot_type"] = tag
        updated["fill_price"] = safe_float(fill_price, 0.0)
        updated["filled_qty"] = safe_int(filled_qty, 0)
        if tag != "SELL_FILL":
            updated["last_buy_fill_mono"] = now_mono
            updated["last_buy_fill_ts"] = now_epoch
            if is_sub_tag:
                updated["last_sub_buy_fill_mono"] = now_mono
                updated["last_sub_buy_fill_ts"] = now_epoch
                updated["last_sub_reentry_eval_mono"] = 0.0
                updated["last_sub_reentry_eval_ts"] = 0.0
            else:
                updated["last_reentry_eval_mono"] = 0.0
                updated["last_reentry_eval_ts"] = 0.0
            updated["last_reserve_check_mono"] = 0.0
            updated["last_reserve_check_ts"] = 0.0
        else:
            updated["last_sell_fill_mono"] = now_mono
            updated["last_sell_fill_ts"] = now_epoch
        guard_map[sym] = updated

    if tag != "SELL_FILL":
        reset_sniper_l1_trail_slots(
            context,
            grid_kind=("SUB" if is_sub_tag else "MAIN"),
            symbol=sym,
        )
        snap_map = getattr(context, "exit_snapshot_cache", None)
        if isinstance(snap_map, dict):
            s_entry = (
                snap_map.get(sym)
                if isinstance(snap_map.get(sym), dict)
                else {}
            )
            if is_sub_tag:
                s_entry["last_sub_reentry_eval_mono"] = 0.0
                s_entry["last_sub_reentry_eval_ts"] = 0.0
            else:
                s_entry["last_reentry_eval_mono"] = 0.0
                s_entry["last_reentry_eval_ts"] = 0.0
            s_entry["last_reserve_check_mono"] = 0.0
            s_entry["last_reserve_check_ts"] = 0.0
            snap_map[sym] = s_entry


def is_within_auto_fill_grace_shield(
    context: Any, symbol: str = TARGET_SYMBOL
) -> bool:
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    now_mono = time.monotonic()

    guard_map = getattr(context, "indexing_grace_cache", None)
    if isinstance(guard_map, dict):
        info = guard_map.get(sym)
        if isinstance(info, dict):
            last_mono = max(
                safe_float(info.get("last_auto_fill_ts"), 0.0),
                safe_float(info.get("last_buy_fill_mono"), 0.0),
                safe_float(info.get("last_sub_buy_fill_mono"), 0.0),
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
                and 0.0
                <= (now_mono - last_s_mono)
                <= AUTO_FILL_GRACE_SHIELD_SEC
            ):
                return True

    if hasattr(context, "ledger"):
        try:
            st = context.ledger.get_state(sym)
            last_epoch = max(
                safe_float(st.get("last_buy_fill_ts"), 0.0),
                safe_float(st.get("last_sub_buy_fill_ts"), 0.0),
                safe_float(st.get("last_sell_fill_ts"), 0.0),
                safe_float(st.get("last_sub_sell_fill_ts"), 0.0),
                safe_float(st.get("last_cycle_end_ts"), 0.0),
                safe_float(st.get("last_sub_cycle_end_ts"), 0.0),
            )
            if (
                last_epoch > 0.0
                and 0.0
                <= (time.time() - last_epoch)
                <= AUTO_FILL_GRACE_SHIELD_SEC
            ):
                return True
        except Exception:
            pass

    return False


# ---------------------------------------------------------------------------
# [Case 73, Case 77 & Case 88] 본 그리드 / 서브 그리드 1층 공석 60초 재장전 타임쉴드 & 시드고갈 60초 입금 감지 타임쉴드 관리기
# ---------------------------------------------------------------------------
def mark_reentry_monitor_60s_cycle_shield(
    context: Any,
    symbol: str = TARGET_SYMBOL,
    eval_price: float = 0.0,
    clear_shield: bool = False,
) -> float:
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


def mark_sub_reentry_monitor_60s_cycle_shield(
    context: Any,
    symbol: str = TARGET_SYMBOL,
    eval_price: float = 0.0,
    clear_shield: bool = False,
) -> float:
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    now_mono = 0.0 if clear_shield else time.monotonic()
    now_epoch = 0.0 if clear_shield else time.time()

    guard_map = getattr(context, "indexing_grace_cache", None)
    if isinstance(guard_map, dict):
        g_entry = (
            guard_map.get(sym) if isinstance(guard_map.get(sym), dict) else {}
        )
        g_entry["last_sub_reentry_eval_mono"] = now_mono
        g_entry["last_sub_reentry_eval_ts"] = now_epoch
        if eval_price > 0.0:
            g_entry["last_sub_reentry_eval_price"] = round(
                safe_float(eval_price, 0.0), 4
            )
        guard_map[sym] = g_entry

    snap_map = getattr(context, "exit_snapshot_cache", None)
    if isinstance(snap_map, dict):
        s_entry = (
            snap_map.get(sym) if isinstance(snap_map.get(sym), dict) else {}
        )
        s_entry["last_sub_reentry_eval_mono"] = now_mono
        s_entry["last_sub_reentry_eval_ts"] = now_epoch
        if eval_price > 0.0:
            s_entry["last_sub_reentry_eval_price"] = round(
                safe_float(eval_price, 0.0), 4
            )
        snap_map[sym] = s_entry

    return now_epoch


def is_within_sub_reentry_monitor_time_shield(
    context: Any,
    st: Optional[Dict[str, Any]] = None,
    symbol: str = TARGET_SYMBOL,
) -> Tuple[bool, float]:
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
            sub_re_mono = safe_float(
                g_entry.get("last_sub_reentry_eval_mono"), 0.0
            )
            if sub_re_mono > 0.0:
                elapsed_g = now_mono - sub_re_mono
                if 0.0 <= elapsed_g < REENTRY_MONITOR_TIME_SHIELD_SEC:
                    return True, round(
                        REENTRY_MONITOR_TIME_SHIELD_SEC - elapsed_g, 1
                    )

    snap_map = getattr(context, "exit_snapshot_cache", None)
    if isinstance(snap_map, dict):
        s_entry = snap_map.get(sym)
        if isinstance(s_entry, dict):
            s_sub_re_mono = safe_float(
                s_entry.get("last_sub_reentry_eval_mono"), 0.0
            )
            if s_sub_re_mono > 0.0:
                elapsed_s = now_mono - s_sub_re_mono
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
    sub_re_epoch = max(
        safe_float(state_obj.get("last_sub_reentry_eval_ts"), 0.0),
        safe_float(state_obj.get("last_sub_sell_fill_ts"), 0.0),
        safe_float(state_obj.get("last_sub_cycle_end_ts"), 0.0),
    )
    if sub_re_epoch > 0.0:
        elapsed_epoch = time.time() - sub_re_epoch
        if 0.0 <= elapsed_epoch < REENTRY_MONITOR_TIME_SHIELD_SEC:
            return True, round(
                REENTRY_MONITOR_TIME_SHIELD_SEC - elapsed_epoch, 1
            )

    return False, 0.0


def mark_reserve_deposit_check_shield(
    context: Any,
    symbol: str = TARGET_SYMBOL,
    clear_shield: bool = False,
) -> float:
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
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    now_mono = time.monotonic()

    state_obj = (
        st
        if isinstance(st, dict)
        else (
            context.ledger.get_state(sym)
            if hasattr(context, "ledger")
            else {}
        )
    )

    # 바벨 모드에서 정규장 SGOV 매도가 방금 체결되어 현금 버킷이 충전된 경우 즉시 쉴드 해제!
    if is_barbell_mode(state_obj.get("portion_mode")) and hasattr(
        context, "barbell_ledger"
    ):
        try:
            bst = context.barbell_ledger.get_state()
            last_sgov_m = safe_float(bst.get("last_sgov_action_mono"), 0.0)
            guard_map_chk = getattr(context, "indexing_grace_cache", None)
            rc_m = (
                safe_float((guard_map_chk.get(sym) or {}).get("last_reserve_check_mono"), 0.0)
                if isinstance(guard_map_chk, dict)
                else 0.0
            )
            if (
                0.0 < last_sgov_m <= now_mono  # MODIFIED: VM 재부팅 mono 역전 가드
                and rc_m > 0.0
                and last_sgov_m > rc_m
                and safe_float(bst.get("cash_bucket_usd"), 0.0) > 50.0
            ):
                mark_reserve_deposit_check_shield(
                    context, sym, clear_shield=True
                )
                return False, 0.0
        except Exception:
            pass

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
    try:
        try:
            fresh_map = (
                await context.api.get_current_prices_batch(
                    (TARGET_SYMBOL,),
                    bypass_shm_cache=True,
                )
            )
        except TypeError:
            fresh_map = (
                await context.api.get_current_prices_batch(
                    (TARGET_SYMBOL,)
                )
            )
        fresh_p = safe_float(
            (fresh_map or {}).get(TARGET_SYMBOL), 0.0
        )
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


async def _get_live_soxl_rsi_14(
    context: Any,
    live_price: float = 0.0,
    now_est: Optional[datetime] = None,
) -> float:
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    lp = safe_float(live_price, 0.0)
    raw_cache = getattr(context, "candle_metrics_cache", None)
    base_met = (
        raw_cache.get(TARGET_SYMBOL) if isinstance(raw_cache, dict) else None
    )

    last_warm_m = safe_float(getattr(context, "_last_rsi_warm_mono", 0.0), 0.0)
    if (
        not isinstance(base_met, dict)
        or not bool(base_met.get("rsi_ready", False))
        or safe_float(base_met.get("prev_bar_close"), 0.0) <= 0.0
    ) and (time.monotonic() - last_warm_m) >= 10.0:
        if context is not None:
            setattr(context, "_last_rsi_warm_mono", time.monotonic())
        api_obj = getattr(context, "api", None)
        if api_obj is not None and hasattr(api_obj, "get_candles_1m"):
            try:
                c_1m = await api_obj.get_candles_1m(
                    symbol=TARGET_SYMBOL, total_count=400
                )
                c_1d = (
                    await api_obj.get_candles_1d(
                        symbol=TARGET_SYMBOL, count=10
                    )
                    if hasattr(api_obj, "get_candles_1d")
                    else []
                )
                if c_1m or c_1d:
                    base_met = await asyncio.to_thread(
                        compute_soxl_quant_metrics_1m,
                        c_1m or [],
                        lp,
                        dt_now,
                        c_1d or [],
                    )
            except Exception as exc:
                logger.debug("RSI(14) 온디맨드 400봉 프리워밍 폴백: %s", exc)

    met = refresh_metrics_with_live_tick(
        base_met if isinstance(base_met, dict) else {},
        lp,
        now_est=dt_now,
    )
    if isinstance(raw_cache, dict):
        raw_cache[TARGET_SYMBOL] = met
    return round(safe_float(met.get("rsi_14"), 50.0), 2)


def min_req_cash_str(val: float) -> str:
    return f"{safe_float(val, 0.0):,.2f}"


# ---------------------------------------------------------------------------
# [핵심 0-B · Case 75, Case 77, Case 86, Case 89, Case 91 & 바벨 4단계 자동수혈 위임]
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
    target_qty: int = 0,
) -> Tuple[bool, float, float, Dict[str, Any]]:
    """
    # MODIFIED [Case 77, Case 86, Case 89, Case 91 + Case 94/100 바벨 100% 정량 차액 Top-Up 워터폴 결속]:
    1) 토스 실계좌 주문가능 달러(`raw_bp_usd`)를 조회하고 일시 0.0 반환 시(바벨 내부 대기버킷 포함) 0.25초 후 재시도한다.
    2) 현재 운용 모드가 ⚖️ 바벨 모드(`BARBELL_60_30_10`)이면 `target_qty` 를 포함해
       `barbell_plugin.evaluate_and_execute_barbell_guard30_or_injection()` 으로 즉시 위임하여
       100% 1회분 정량 완충(부족 차액 Top-Up) 자동수혈을 집행한다!
    3) 복리/단리 모드일 때는 기존에 격리된 수익금(`vaulted_profit_locked_usd`)을 제외한 `eff_raw_bp` 로
       무제한 온디맨드 수혈(`evaluate_guard30_and_reserve_injection`)을 수행한다.
    """
    now_free_cash = max(0.0, safe_float(st_now.get("free_cash_usd"), 0.0))
    cur_used_res = max(0, safe_int(st_now.get("used_reserve_portions_cnt"), 0))
    cur_inj_usd = max(0.0, safe_float(st_now.get("injected_reserve_usd"), 0.0))

    eff_rt_pct = resolve_effective_round_trip_fee_rate_pct(state_dict=st_now)
    fee_mult = 1.0 + (eff_rt_pct / 100.0)
    est_min_req = max(
        exec_order_p * fee_mult,
        portion_budget * MIN_DIP_BUDGET_RATIO,
        (l1_actual_cost_usd * MIN_DIP_VS_L1_RATIO if is_dip_promotion else 0.0),
    )

    ledger_liquid_est = now_free_cash
    if is_barbell_mode(st_now.get("portion_mode")) and hasattr(
        context, "barbell_ledger"
    ):
        try:
            bst_chk = context.barbell_ledger.get_state()
            ledger_liquid_est += (
                max(0.0, safe_float(bst_chk.get("cash_bucket_usd"), 0.0))
                + max(
                    0.0,
                    safe_float(
                        bst_chk.get("pending_sgov_buy_budget_usd"), 0.0
                    ),
                )
                + max(0.0, safe_float(bst_chk.get("vault_available_usd"), 0.0))
            )
        except Exception:
            pass

    raw_bp_usd = await context.api.get_buying_power_usd(safety_buffer_pct=0.0)
    if raw_bp_usd <= 0.0 and ledger_liquid_est >= est_min_req:
        await asyncio.sleep(0.25)
        raw_bp_usd = await context.api.get_buying_power_usd(
            safety_buffer_pct=0.0
        )
        if raw_bp_usd <= 0.0:
            logger.debug(
                "🛡️ [Case 77/100 예수금 API 일시 조회 지연 방어] 원장 유동성($%.2f >= 최소 $%.2f) 정상이나 예수금 API가 0.0을 반환하여 보류",
                ledger_liquid_est,
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

    # [바벨 모드 전용 100% 정량 차액 Top-Up 4단계 워터폴 위임]
    if is_barbell_mode(st_now.get("portion_mode")):
        (
            can_proc_b,
            eff_cash_b,
            bp_ord_b,
            g_eval_b,
        ) = await evaluate_and_execute_barbell_guard30_or_injection(
            context=context,
            st_now=st_now,
            raw_bp_usd=raw_bp_usd,
            exec_order_p=exec_order_p,
            portion_budget=portion_budget,
            l1_actual_cost_usd=l1_actual_cost_usd,
            is_dip_promotion=is_dip_promotion,
            trigger_desc=trigger_desc,
            target_qty=target_qty,
        )
        if can_proc_b:
            mark_reserve_deposit_check_shield(
                context, TARGET_SYMBOL, clear_shield=True
            )
            return True, eff_cash_b, bp_ord_b, g_eval_b

        now_rc_b = mark_reserve_deposit_check_shield(
            context, TARGET_SYMBOL, clear_shield=False
        )
        upd_b_kw: Dict[str, Any] = {
            "last_reserve_check_ts": now_rc_b,
            "seed_protect_pass_cnt": safe_int(
                st_now.get("seed_protect_pass_cnt"), 0
            )
            + 1,
            "daily_seed_protect_pass_cnt": safe_int(
                st_now.get("daily_seed_protect_pass_cnt"), 0
            )
            + 1,
        }
        if is_vacant_l1_reentry:
            upd_b_kw["last_reentry_eval_ts"] = (
                mark_reentry_monitor_60s_cycle_shield(
                    context=context,
                    symbol=TARGET_SYMBOL,
                    eval_price=exec_order_p,
                )
            )
        await context.ledger.update_state(TARGET_SYMBOL, **upd_b_kw)
        return False, eff_cash_b, 0.0, g_eval_b

    # [복리 / 단리 모드]: 기존 바벨 수익금고 격리액(vaulted_profit_locked_usd) 오인 수혈 원천 차단
    vault_locked = max(
        0.0, safe_float(st_now.get("vaulted_profit_locked_usd"), 0.0)
    )
    eff_raw_bp = max(0.0, raw_bp_usd - vault_locked)
    eff_bp_for_eval: Optional[float] = (
        eff_raw_bp if eff_raw_bp > 0.0 else 0.0
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
        round_trip_fee_rate_pct=eff_rt_pct,
    )
    action = str(guard_eval.get("action") or "BLOCK_AND_ALERT_DEPOSIT")
    eff_bp_for_order = (
        round(eff_raw_bp * 0.998, 4) if eff_raw_bp > 0.0 else 0.0
    )

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

    if action == "INJECT_AND_PROCEED":
        inj_portions = max(1, safe_int(guard_eval.get("inject_portions"), 1))
        inj_usd = round(
            max(0.01, safe_float(guard_eval.get("inject_usd"), 0.0)), 4
        )
        new_used_cnt = cur_used_res + inj_portions
        new_inj_usd = round(cur_inj_usd + inj_usd, 4)
        new_tot_inj_cnt = (
            safe_int(st_now.get("total_reserve_injected_cnt"), 0)
            + inj_portions
        )
        new_day_inj_cnt = (
            safe_int(st_now.get("daily_reserve_injected_cnt"), 0)
            + inj_portions
        )

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
            safe_float(
                updated_st.get("free_cash_usd"), now_free_cash + inj_usd
            ),
        )
        logger.info(
            "💉 [Case 77/89/91 SOXL 온디맨드 예비시드 자동 수혈 완료] +%d회분(+%.2f$) 수혈 -> 가용현금 $%.2f (현재수혈 %d회분 · 누적총 %d회 · 수혈잔액 $%.2f · 타점=%s)",
            inj_portions,
            inj_usd,
            updated_free_cash,
            new_used_cnt,
            new_tot_inj_cnt,
            new_inj_usd,
            trigger_desc,
        )
        if hasattr(context, "send_slim_alert"):
            await context.send_slim_alert(
                title=f"💉 [SOXL 예비시드 자동 수혈 (+{inj_portions}회분 · +${inj_usd:,.2f})]",
                body=(
                    f"시드고갈(30% 가드) 감지 즉시 토스 계좌 여유자금에서 +{inj_portions}회분(${inj_usd:,.2f}) 자동 수혈 완료! · "
                    f"수혈 후 가용현금 ${updated_free_cash:,.2f} · "
                    f"현재 수혈 {new_used_cnt}회분(누적 총 {new_tot_inj_cnt}회 · 수혈잔액 ${new_inj_usd:,.2f} / 0주 졸업 시 원금 자동 상환) · "
                    f"즉시 {trigger_desc} 정량 매수를 집행합니다!"
                ),
            )
        return True, updated_free_cash, eff_bp_for_order, guard_eval

    already_waiting_dep = bool(st_now.get("waiting_reserve_deposit", False))
    alert_already_sent = bool(
        st_now.get("waiting_reserve_deposit_alert_sent", False)
    )
    rec_dep_usd = round(
        max(
            portion_budget,
            safe_float(
                guard_eval.get("recommended_deposit_usd"), portion_budget
            ),
        ),
        2,
    )
    min_req_c = safe_float(
        guard_eval.get("min_req_cash"), portion_budget * 0.30
    )
    needed_p = max(1, safe_int(guard_eval.get("needed_portions"), 1))
    tot_inj_cnt_now = safe_int(st_now.get("total_reserve_injected_cnt"), 0)

    now_rc_epoch = mark_reserve_deposit_check_shield(
        context, TARGET_SYMBOL, clear_shield=False
    )
    re_epoch = safe_float(st_now.get("last_reentry_eval_ts"), 0.0)
    if is_vacant_l1_reentry:
        re_epoch = mark_reentry_monitor_60s_cycle_shield(
            context=context, symbol=TARGET_SYMBOL, eval_price=exec_order_p
        )

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

    if not alert_already_sent and hasattr(context, "send_slim_alert"):
        title_msg = (
            f"🚨 [💉 SOXL 시드고갈 감지 · 예비시드 {needed_p}회분(${rec_dep_usd:,.2f}) 입금 요청]"
        )
        body_msg = (
            f"타점({trigger_desc} @ ${exec_order_p:.2f}) 도달 · "
            f"현재 가용현금(${now_free_cash:,.2f}) 및 토스 주문가능금액(${eff_raw_bp:,.2f})이 "
            f"30% 자투리 승격 방지 가드(${min_req_cash_str(min_req_c)}) 미만이어서 자투리 매수를 차단했습니다. · "
            f"토스 달러 계좌에 예비시드(권장 ${rec_dep_usd:,.2f} · 최소 30% 가드 이상 · 현재수혈 {cur_used_res}회/누적 {tot_inj_cnt_now}회)를 입금해 주시면 "
            f"60초 내 자동 감지하여 횟수 제한 없이 즉시 수혈 매수합니다! (※ 스팸 방지를 위해 입금 요청 알림은 1회만 발송됩니다)"
        )
        await context.send_slim_alert(title=title_msg, body=body_msg)
        logger.warning(
            "🚨 [Case 77/91 시드고갈 단 1회 입금 요청 알림 발송 완료 & 래치 잠금] 가용=$%.2f · 토스예수금=$%.2f · 30%%가드=$%.2f · 권장입금=$%.2f",
            now_free_cash,
            eff_raw_bp,
            min_req_c,
            rec_dep_usd,
        )

    return False, now_free_cash, eff_bp_for_order, guard_eval
# ---------------------------------------------------------------------------
# [핵심 1] 매수 체결(FILLED) 커밋 · 비례 자투리 정산(Case 78) · 현재 사이클 자투리 절약금 누적 · Default-ON 3층 서브 그리드 SUB_L1_L3_MERGE(Case 88) · 1~7층 본 그리드 L2+L7 중간합병 및 최고도달회차 잠금(Case 87) · 매수 후 60초 타임쉴드 각인
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
    # MODIFIED [🎯 1, 🎯 3, 🎯 4 & Case 25 ~ 91 + 바벨 모드(60% SOXL 코어 회계 항등식 연동)]:
    매수 주문 체결(FILLED 또는 부분 체결 후 60초 타임아웃/세션 경계 취소 종료)이 확인된 즉시:
    1) 🛡️ [Case 88 : Default-ON 3층 서브 그리드(lot_type 이 "SUB_" 로 시작) 체결 분리 정산 · SUB_L1_L3_MERGE 양끝 합병 · sub_consec_frozen_days = 0 리셋]
    2) 👑 [Case 78 & Case 87 : 본 그리드 부분 체결 비례 자투리 정산 · L2_L7_MERGE_SORT 중간층 재배치 · cycle_ratchet_max_lots 잠금 갱신 · main_consec_frozen_days = 0 리셋]
    """
    st = context.ledger.get_state(TARGET_SYMBOL)
    old_buckets = buckets_from_dicts(st.get("buckets", []))
    old_sub_buckets = buckets_from_dicts(st.get("sub_buckets", []))

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
    raw_tag = str(lot_type or "QUOTA_L1").upper().strip()
    eff_oid = str(settled_order_id or st.get("buy_order_id") or "").strip()

    settled_oids: List[str] = list(st.get("last_settled_order_ids") or [])
    if eff_oid and eff_oid not in settled_oids:
        settled_oids.append(eff_oid)
    settled_oids = settled_oids[-50:]

    now_buy_epoch = time.time()

    # -----------------------------------------------------------------------
    # [트랙 1 · Case 88 분기 : Default-ON 3층 서브 그리드(lot_type 이 "SUB_" 로 시작) 체결 커밋]
    # -----------------------------------------------------------------------
    if raw_tag.startswith("SUB_"):
        sub_tag = (
            "SUB_REENTRY_1FL"
            if raw_tag
            in ("SUB_REENTRY_1FL_BREAKOUT", "SUB_REENTRY_1FL_PULLBACK")
            else raw_tag
        )
        raw_sub_budget = safe_float(portion_budget, 0.0)
        if raw_sub_budget <= 0.0:
            eff_sub_budget = actual_spent
            saved_from_sub_portion = 0.0
        elif q_int < ord_q and ord_q > 0:
            eff_sub_budget = round(
                raw_sub_budget * (float(q_int) / float(ord_q)), 4
            )
            saved_from_sub_portion = round(
                max(0.0, eff_sub_budget - actual_spent), 4
            )
        else:
            eff_sub_budget = raw_sub_budget
            saved_from_sub_portion = round(
                max(0.0, eff_sub_budget - actual_spent), 4
            )

        was_sub_empty = len(old_sub_buckets) == 0
        was_sub_l2_only = bool(
            len(old_sub_buckets) > 0
            and not has_active_l1_bucket(old_sub_buckets)
        )
        eff_sub_merge_mode = str(
            st.get("sub_merge_mode") or SUB_MERGE_MODE_L1_L3
        ).upper()

        new_sub_buckets, did_sub_merge = add_lot_to_sub_grid_with_flag(
            sub_queue=old_sub_buckets,
            buy_qty=q_int,
            buy_price=fill_p,
            actual_spent_usd=actual_spent,
            lot_type=sub_tag,
            max_tiers=SUB_MAX_TIERS_3,
            merge_mode=eff_sub_merge_mode,
        )

        raw_sub_target_q = max(
            0, safe_int(st.get("sub_l1_target_quota_qty"), 0)
        )
        cur_sub_l1_qty = new_sub_buckets[0].qty if new_sub_buckets else q_int
        if sub_tag == "SUB_TOPUP_1FL":
            next_sub_l1_target_q = max(cur_sub_l1_qty, raw_sub_target_q)
        else:
            next_sub_l1_target_q = max(cur_sub_l1_qty, ord_q)
        sub_rem_after_fill = max(0, next_sub_l1_target_q - cur_sub_l1_qty)

        old_sub_min_p = safe_float(st.get("sub_cycle_min_buy_price"), 0.0)
        pending_sub_step_p = safe_float(
            st.get("pending_sub_step_up_min_price"), 0.0
        )
        is_sub_unlock_fill = False

        if was_sub_empty or old_sub_min_p <= 0.0:
            new_sub_cycle_min_p = fill_p
        elif pending_sub_step_p > 0.0 and sub_tag not in (
            "SUB_REENTRY_1FL",
            "SUB_TOPUP_1FL",
        ):
            new_sub_cycle_min_p = round(min(pending_sub_step_p, fill_p), 4)
            is_sub_unlock_fill = True
        else:
            new_sub_cycle_min_p = round(min(old_sub_min_p, fill_p), 4)

        new_sub_lots = sum(sb.lot_count for sb in new_sub_buckets)
        new_sub_shares = sum(sb.qty for sb in new_sub_buckets)
        new_sub_tiers = len(new_sub_buckets)

        prev_sub_ratchet_lots = max(
            0, safe_int(st.get("sub_ratchet_max_lots"), 0)
        )
        if was_sub_empty or is_sub_unlock_fill:
            new_sub_ratchet_lots = new_sub_lots
        else:
            new_sub_ratchet_lots = max(prev_sub_ratchet_lots, new_sub_lots)

        tot_buy_ev = safe_int(st.get("total_buy_events"), 0) + 1
        tot_buy_sh = safe_int(st.get("total_buy_shares"), 0) + q_int
        day_buy_ev = safe_int(st.get("daily_buy_events"), 0) + 1

        sub_buy_ev = safe_int(st.get("sub_buy_events"), 0) + 1
        sub_buy_sh = safe_int(st.get("sub_buy_shares"), 0) + q_int
        day_sub_buy_cnt = safe_int(st.get("daily_sub_buy_cnt"), 0) + 1
        day_sub_buy_ev = safe_int(st.get("daily_sub_buy_events"), 0) + 1
        sub_merge_ev = safe_int(st.get("sub_merge_events"), 0) + (
            1 if did_sub_merge else 0
        )
        sub_unlock_inc = 1 if is_sub_unlock_fill else 0
        sub_unlock_ev = (
            safe_int(st.get("sub_unlock_events"), 0) + sub_unlock_inc
        )
        day_sub_unlock_ev = (
            safe_int(st.get("daily_sub_unlock_events"), 0) + sub_unlock_inc
        )

        cum_saved = round(
            safe_float(st.get("cumulative_leftover_saved_usd"), 0.0)
            + saved_from_sub_portion,
            4,
        )
        day_saved = round(
            safe_float(st.get("daily_leftover_saved_usd"), 0.0)
            + saved_from_sub_portion,
            4,
        )
        cyc_saved = round(
            safe_float(st.get("cycle_leftover_saved_usd"), 0.0)
            + saved_from_sub_portion,
            4,
        )

        mark_auto_fill_grace_shield(
            context=context,
            symbol=TARGET_SYMBOL,
            lot_type=sub_tag,
            fill_price=fill_p,
            filled_qty=q_int,
        )
        mark_sub_reentry_monitor_60s_cycle_shield(
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
            sub_buckets=buckets_to_dicts(new_sub_buckets),
            sub_anchor_price=(
                new_sub_buckets[0].book_price if new_sub_buckets else fill_p
            ),
            sub_cycle_min_buy_price=round(new_sub_cycle_min_p, 4),
            sub_ratchet_max_lots=new_sub_ratchet_lots,
            sub_l1_target_quota_qty=next_sub_l1_target_q,
            sub_consec_frozen_days=0,
            buy_order_id="",
            ordered_qty=0,
            buy_price=0.0,
            pending_portion_budget=0.0,
            pending_lot_type="",
            pending_step_up_min_price=0.0,
            pending_sub_step_up_min_price=0.0,
            waiting_reserve_deposit=False,
            waiting_reserve_deposit_alert_sent=False,
            required_reserve_deposit_usd=0.0,
            last_reserve_check_ts=0.0,
            last_settled_order_ids=settled_oids,
            total_buy_events=tot_buy_ev,
            total_buy_shares=tot_buy_sh,
            daily_buy_events=day_buy_ev,
            sub_buy_events=sub_buy_ev,
            sub_buy_shares=sub_buy_sh,
            daily_sub_buy_cnt=day_sub_buy_cnt,
            daily_sub_buy_events=day_sub_buy_ev,
            sub_merge_events=sub_merge_ev,
            sub_unlock_events=sub_unlock_ev,
            daily_sub_unlock_events=day_sub_unlock_ev,
            cumulative_leftover_saved_usd=cum_saved,
            daily_leftover_saved_usd=day_saved,
            cycle_leftover_saved_usd=cyc_saved,
            entry_ts=now_buy_epoch,
            last_buy_fill_ts=now_buy_epoch,
            last_sub_buy_fill_ts=now_buy_epoch,
            last_sub_reentry_eval_ts=0.0,
        )

        context.wakeup_event.set()
        free_cash_now = safe_float(updated_st.get("free_cash_usd"), 0.0)
        summary = summarize_stratum_portfolio(updated_st, live_price=fill_p)
        sub_l1_target = safe_float(summary.get("sub_l1_target_price"), 0.0)
        sub_u_cnt = safe_int(summary.get("sub_upper_tier_count"), 0)
        sub_u_qty = safe_int(summary.get("sub_upper_qty"), 0)
        sub_u_wma_p = safe_float(summary.get("sub_upper_wma_price"), 0.0)
        sub_u_wma_t = safe_float(summary.get("sub_upper_wma_target_price"), 0.0)
        sub_trig_buy_p = safe_float(summary.get("sub_trigger_buy_price"), 0.0)
        sub_drop_req_p = safe_float(summary.get("sub_drop_buy_pct"), -1.0)
        sub_l1_book_now = (
            new_sub_buckets[0].book_price if new_sub_buckets else fill_p
        )
        merge_badge = " · 🔄구1층+구3층 양끝합병 완료!" if did_sub_merge else ""
        cap_badge = (
            " · 🔒4/4회분 상한 캡 도달"
            if new_sub_lots >= SUB_MAX_TOTAL_LOTS_4
            else ""
        )

        if hasattr(context, "send_slim_alert"):
            sub_rem_note = (
                f" · 🎯서브잔량 {sub_rem_after_fill}주(목표 {next_sub_l1_target_q}주 중 {cur_sub_l1_qty}주 체결 ➔ "
                f"🛡️60초 타임쉴드 후 1.5초 모니터에서 ${sub_l1_book_now:.2f} 이하 도래 시 잔량 60초 지정가 재대기!)"
                if sub_rem_after_fill > 0
                else ""
            )
            sub_upper_note = (
                f" · 서브2~{new_sub_tiers}층({sub_u_cnt}개층·{sub_u_qty}주) 이평 ${sub_u_wma_p:.2f}(목표 ${sub_u_wma_t:.2f})"
                if len(new_sub_buckets) >= 2
                else ""
            )
            if sub_tag == "SUB_TOPUP_1FL":
                title_str = (
                    f"🛡️ [SOXL 서브그리드 1층 미체결 잔량 보충 체결] +{q_int}주 @ ${fill_p:.2f} "
                    f"(서브1층 {cur_sub_l1_qty}/{next_sub_l1_target_q}주 합산)"
                )
            elif is_sub_unlock_fill:
                title_str = (
                    f"🔓 [SOXL 서브그리드 10일/-10% 저가해금 추매 체결 ({new_sub_lots}/{SUB_MAX_TOTAL_LOTS_4}회분 · {new_sub_tiers}개층)] "
                    f"{q_int}주 @ ${fill_p:.2f}"
                )
            elif was_sub_l2_only and sub_tag == "SUB_REENTRY_1FL":
                title_str = (
                    f"🛡️ [SOXL 서브그리드 1층 재장전 체결 ({new_sub_lots}/{SUB_MAX_TOTAL_LOTS_4}회분 · {new_sub_tiers}개층)] "
                    f"{q_int}주 @ ${fill_p:.2f}"
                )
            else:
                title_str = (
                    f"🛡️ [SOXL 3층 서브그리드 ({new_sub_lots}/{SUB_MAX_TOTAL_LOTS_4}회분 · {new_sub_tiers}개층) 지정가 매수 체결] "
                    f"{q_int}주 @ ${fill_p:.2f}"
                )
            body_str = (
                f"실사용 ${actual_spent:,.2f} (4%정량 자투리 +${saved_from_sub_portion:.2f} 시드보존){merge_badge}{cap_badge} · "
                f"🛡️60초 타임쉴드 후 서브1층목표 ${sub_l1_target:.2f}(+1.5%) 감시{sub_upper_note}{sub_rem_note} · "
                f"서브기억저가 ${new_sub_cycle_min_p:.2f}(단차 {sub_drop_req_p:.1f}% ➔ ${sub_trig_buy_p:.2f}) · "
                f"가용현금 ${free_cash_now:,.2f} (서브 총 {new_sub_shares}주)"
            )
            await context.send_slim_alert(title=title_str, body=body_str)

        return {
            "status": "SUB_BUY_FILLED_AND_MERGED",
            "symbol": TARGET_SYMBOL,
            "lot_type": sub_tag,
            "is_sub_unlock": is_sub_unlock_fill,
            "did_sub_merge": did_sub_merge,
            "filled_qty": q_int,
            "ordered_qty": ord_q,
            "sub_l1_target_quota_qty": next_sub_l1_target_q,
            "sub_l1_rem_quota_qty": sub_rem_after_fill,
            "fill_price": fill_p,
            "actual_spent_usd": actual_spent,
            "saved_from_portion_usd": saved_from_sub_portion,
            "sub_cycle_min_buy_price": round(new_sub_cycle_min_p, 4),
            "sub_ratchet_max_lots": new_sub_ratchet_lots,
            "sub_held_lots": new_sub_lots,
            "sub_held_tiers": new_sub_tiers,
            "sub_held_shares": new_sub_shares,
            "free_cash_usd": free_cash_now,
        }

    # -----------------------------------------------------------------------
    # [트랙 2 : 본 그리드 8% 정량 매수(REENTRY_1FL / TOPUP_1FL / DIP_1FL) 커밋]
    # -----------------------------------------------------------------------
    tag = (
        "REENTRY_1FL"
        if raw_tag in ("REENTRY_1FL_BREAKOUT", "REENTRY_1FL_PULLBACK")
        else raw_tag
    )
    raw_portion_budget = safe_float(portion_budget, 0.0)
    if raw_portion_budget <= 0.0:
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

    eff_merge_mode = str(
        st.get("grid_merge_mode") or DEFAULT_GRID_MERGE_MODE
    ).upper()
    new_buckets = vrev_add_quota_lot_and_merge_2tier(
        queue=old_buckets,
        buy_qty=q_int,
        buy_price=fill_p,
        actual_spent_usd=actual_spent,
        lot_type=tag,
        max_tiers=MAX_GRID_TIERS_7,
        merge_mode=eff_merge_mode,
    )

    raw_target_q = max(0, safe_int(st.get("l1_target_quota_qty"), 0))
    cur_l1_qty = new_buckets[0].qty if new_buckets else q_int
    if tag == "TOPUP_1FL":
        next_l1_target_q = max(cur_l1_qty, raw_target_q)
    else:
        next_l1_target_q = max(cur_l1_qty, ord_q)
    rem_after_fill = max(0, next_l1_target_q - cur_l1_qty)

    old_min_p = safe_float(st.get("cycle_min_buy_price"), 0.0)
    pending_step_up_p = safe_float(st.get("pending_step_up_min_price"), 0.0)
    is_step_up_unlock_fill = False

    if was_empty or old_min_p <= 0.0:
        new_cycle_min_p = fill_p
    elif pending_step_up_p > 0.0 and tag not in (
        "REENTRY_1FL",
        "TOPUP_1FL",
    ):
        new_cycle_min_p = round(min(pending_step_up_p, fill_p), 4)
        is_step_up_unlock_fill = True
    else:
        new_cycle_min_p = round(min(old_min_p, fill_p), 4)

    new_held_lots = sum(b.lot_count for b in new_buckets)
    new_held_shares = sum(b.qty for b in new_buckets)
    new_held_tiers = len(new_buckets)

    prev_ratchet_lots = max(0, safe_int(st.get("cycle_ratchet_max_lots"), 0))
    if was_empty or is_step_up_unlock_fill:
        new_ratchet_max_lots = new_held_lots
    else:
        new_ratchet_max_lots = max(prev_ratchet_lots, new_held_lots)

    tot_buy_ev = safe_int(st.get("total_buy_events"), 0) + 1
    tot_buy_sh = safe_int(st.get("total_buy_shares"), 0) + q_int
    day_buy_ev = safe_int(st.get("daily_buy_events"), 0) + 1
    day_main_buy_cnt = safe_int(st.get("daily_main_buy_cnt"), 0) + 1
    unlock_inc = 1 if is_step_up_unlock_fill else 0
    cond_unlock_ev = safe_int(st.get("cond_unlock_buy_events"), 0) + unlock_inc
    day_unlock_ev = safe_int(st.get("daily_unlock_buy_events"), 0) + unlock_inc
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
    cyc_saved = round(
        safe_float(st.get("cycle_leftover_saved_usd"), 0.0)
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
        cycle_ratchet_max_lots=new_ratchet_max_lots,
        ratchet_anchor_price=new_buckets[0].book_price if new_buckets else fill_p,
        cycle_reanchor_credit_usd=0.0,
        l1_target_quota_qty=next_l1_target_q,
        main_consec_frozen_days=0,
        daily_main_buy_cnt=day_main_buy_cnt,
        buy_order_id="",
        ordered_qty=0,
        buy_price=0.0,
        pending_portion_budget=0.0,
        pending_lot_type="",
        pending_step_up_min_price=0.0,
        pending_sub_step_up_min_price=0.0,
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
        extra_13plus_buy_events=extra_13,
        cumulative_leftover_saved_usd=cum_saved,
        daily_leftover_saved_usd=day_saved,
        cycle_leftover_saved_usd=cyc_saved,
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
    ratchet_note = (
        f"(단차잠금 {new_ratchet_max_lots}회차)"
        if new_ratchet_max_lots > new_held_lots
        else ""
    )
    mode_cash_lbl = (
        "바벨SOXL현금"
        if is_barbell_mode(updated_st.get("portion_mode"))
        else "가용현금"
    )

    if hasattr(context, "send_slim_alert"):
        rem_quota_note = (
            f" · 🎯미체결 잔량 {rem_after_fill}주(목표 {next_l1_target_q}주 중 {cur_l1_qty}주 체결 ➔ "
            f"🛡️60초 타임쉴드 후 1.5초 모니터에서 ${l1_book_now:.2f} 이하 도래 시 잔량 60초 지정가 재대기!)"
            if rem_after_fill > 0
            else ""
        )
        if tag == "TOPUP_1FL":
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
                f"{mode_cash_lbl} ${free_cash_now:,.2f} (총 {new_held_shares}주)"
            )
        elif was_l2_only and tag == "REENTRY_1FL" and len(new_buckets) >= 2:
            title_str = (
                f"🔥 [SOXL 현재가 지정가 1층 재장전 체결] {q_int}주 @ ${fill_p:.2f} (상단 {u_cnt}개층 비병합)"
            )
            body_str = (
                f"실사용 ${actual_spent:,.2f} (자투리 +${saved_from_portion:.2f} 시드보존) · "
                f"🛡️60초 타임쉴드 후 1층목표 ${l1_target:.2f}(+1.5%) 감시{rem_quota_note} · "
                f"2~{new_held_tiers}층({u_qty}주) 이평 ${u_wma_p:.2f}(목표 ${u_wma_t:.2f}) 유지 · "
                f"기억저가 ${new_cycle_min_p:.2f}{ratchet_note}(와이드 {drop_req_p:.1f}% 추매가 ${trig_buy_p:.2f}) · "
                f"{mode_cash_lbl} ${free_cash_now:,.2f}"
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
                f"구저가 ${old_min_p:.2f}(반등 {reb_m:.2f}x) ➔ 스텝업 잠금저가 ${new_cycle_min_p:.2f}(잠금 {new_ratchet_max_lots}회차) 갱신! · "
                f"실사용 ${actual_spent:,.2f} (자투리 +${saved_from_portion:.2f} 시드보존) · "
                f"🛡️60초 타임쉴드 후 1층목표 ${l1_target:.2f} & 2~{new_held_tiers}층({u_qty}주) 이평 ${u_wma_p:.2f}(목표 ${u_wma_t:.2f}) 감시{rem_quota_note} · "
                f"차기단차 {drop_req_p:.1f}%(${trig_buy_p:.2f}) · {mode_cash_lbl} ${free_cash_now:,.2f}"
            )
        else:
            upper_note = ""
            if len(new_buckets) >= 2:
                upper_note = (
                    f" · 2~{new_held_tiers}층({u_cnt}개층·{u_qty}주) 순수이평 ${u_wma_p:.2f}(목표 ${u_wma_t:.2f})"
                )
            title_str = (
                f"🔵 [SOXL {new_held_lots}회차{ratchet_note}({new_held_tiers}개층) 현재가 지정가 매수 체결] {q_int}주 @ ${fill_p:.2f}"
            )
            body_str = (
                f"실사용 ${actual_spent:,.2f} (자투리 +${saved_from_portion:.2f} 시드보존) "
                f"· 🛡️60초 타임쉴드 후 1층목표 ${l1_target:.2f} 감시{upper_note}{rem_quota_note} · 차기단차 {drop_req_p:.1f}%(${trig_buy_p:.2f}) "
                f"· {mode_cash_lbl} ${free_cash_now:,.2f} (총 {new_held_shares}주)"
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
        "cycle_ratchet_max_lots": new_ratchet_max_lots,
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
    force_settle: bool = False,
) -> Dict[str, Any]:
    st = context.ledger.get_state(TARGET_SYMBOL)
    buy_oid = str(st.get("buy_order_id") or "").strip()
    if not buy_oid:
        return {"status": "NO_PENDING_BUY"}

    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    hm_now = dt_now.hour * 100 + dt_now.minute
    is_late_cutoff_now = is_late_regular_new_cycle_cutoff_window(
        hm_now, now_est=dt_now
    )

    ordered_qty = max(1, safe_int(st.get("ordered_qty"), 1))
    ord_price = safe_float(st.get("buy_price"), 0.0)
    portion_budget = safe_float(
        st.get("pending_portion_budget"), float(ordered_qty) * ord_price
    )
    raw_lot_type = (
        str(st.get("pending_lot_type") or "QUOTA_L1").upper().strip()
    )
    is_sub_lot = raw_lot_type.startswith("SUB_")
    if raw_lot_type in ("REENTRY_1FL_BREAKOUT", "REENTRY_1FL_PULLBACK"):
        lot_type = "REENTRY_1FL"
    elif raw_lot_type in (
        "SUB_REENTRY_1FL_BREAKOUT",
        "SUB_REENTRY_1FL_PULLBACK",
    ):
        lot_type = "SUB_REENTRY_1FL"
    else:
        lot_type = raw_lot_type

    buckets_now = buckets_from_dicts(st.get("buckets", []))
    has_active_l1_now = has_active_l1_bucket(buckets_now)
    is_vacant_l1_now = bool(len(buckets_now) > 0 and not has_active_l1_now)
    cur_target_q = max(0, safe_int(st.get("l1_target_quota_qty"), 0))
    fallback_target_q_on_zero_cancel = (
        max(buckets_now[0].qty, cur_target_q) if has_active_l1_now else 0
    )

    sub_buckets_now = buckets_from_dicts(st.get("sub_buckets", []))
    has_sub_active_l1_now = has_active_l1_bucket(sub_buckets_now)
    is_sub_vacant_l1_now = bool(
        len(sub_buckets_now) > 0 and not has_sub_active_l1_now
    )
    cur_sub_target_q = max(0, safe_int(st.get("sub_l1_target_quota_qty"), 0))
    fallback_sub_target_q_on_zero_cancel = (
        max(sub_buckets_now[0].qty, cur_sub_target_q)
        if has_sub_active_l1_now
        else 0
    )

    is_zero_grid_reentry = bool(
        not is_sub_lot and len(buckets_now) == 0 and lot_type == "REENTRY_1FL"
    )
    anchor_p_now = safe_float(st.get("anchor_price"), 0.0)
    is_vacant_l1_breakout_reentry = bool(
        not is_sub_lot
        and is_vacant_l1_now
        and lot_type == "REENTRY_1FL"
        and (
            raw_lot_type == "REENTRY_1FL_BREAKOUT"
            or (
                anchor_p_now > 0.0
                and ord_price
                >= anchor_p_now
                * (1.0 + REENTRY_BREAKOUT_RISE_PCT / 100.0 - 1e-4)
            )
        )
    )

    is_zero_sub_reentry = bool(
        is_sub_lot
        and len(sub_buckets_now) == 0
        and lot_type == "SUB_REENTRY_1FL"
    )
    sub_anchor_p_now = safe_float(st.get("sub_anchor_price"), 0.0)
    is_sub_vacant_l1_breakout_reentry = bool(
        is_sub_lot
        and is_sub_vacant_l1_now
        and lot_type == "SUB_REENTRY_1FL"
        and (
            raw_lot_type == "SUB_REENTRY_1FL_BREAKOUT"
            or (
                sub_anchor_p_now > 0.0
                and ord_price
                >= sub_anchor_p_now
                * (1.0 + REENTRY_BREAKOUT_RISE_PCT / 100.0 - 1e-4)
            )
        )
    )

    should_abort_late_cutoff = bool(
        is_late_cutoff_now
        and (
            is_zero_grid_reentry
            or is_vacant_l1_breakout_reentry
            or is_zero_sub_reentry
            or is_sub_vacant_l1_breakout_reentry
        )
    )

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

        if (
            ord_status in ("PARTIAL_FILLED", "PENDING_CANCEL")
            or filled_q > 0
        ):
            if (
                elapsed_mod >= BUY_ORDER_MAX_WAIT_SEC
                or force_settle
                or should_abort_late_cutoff
                or ord_status == "PENDING_CANCEL"
            ):
                try:
                    await context.api.cancel_order(buy_oid)
                except Exception:
                    pass
                final_det = await context.api.get_order_detail(buy_oid)
                f_st2 = (
                    str(final_det.get("status") or "").upper().strip()
                    if isinstance(final_det, dict)
                    else ""
                )
                if not isinstance(final_det, dict) or f_st2 in (
                    "PENDING",
                    "PARTIAL_FILLED",
                    "PENDING_CANCEL",
                    "PENDING_REPLACE",
                ):
                    await asyncio.sleep(0.35)
                    final_det = await context.api.get_order_detail(buy_oid)
                    f_st2 = (
                        str(final_det.get("status") or "").upper().strip()
                        if isinstance(final_det, dict)
                        else ""
                    )
                if not isinstance(final_det, dict) or f_st2 in (
                    "PENDING",
                    "PARTIAL_FILLED",
                    "PENDING_CANCEL",
                    "PENDING_REPLACE",
                ):
                    return {
                        "status": "BUY_PARTIAL_CANCEL_CONFIRMING",
                        "orderId": buy_oid,
                        "filled_qty": filled_q,
                    }
                f_ex = (
                    final_det.get("execution")
                    if isinstance(final_det.get("execution"), dict)
                    else {}
                )
                f_q2 = safe_int(f_ex.get("filledQuantity"), filled_q)
                f_p2 = safe_float(f_ex.get("averageFilledPrice"), avg_fill_p)
                if f_q2 > 0:
                    filled_q = f_q2
                if f_p2 > 0.0:
                    avg_fill_p = f_p2
                if filled_q > 0:
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
            else:
                return {
                    "status": "BUY_PARTIAL_FILLED_WAITING",
                    "filled_qty": filled_q,
                    "ordered_qty": ordered_qty,
                }

        if ord_status in ("CANCELED", "REJECTED", "REPLACED") and filled_q == 0:
            re_epoch = (
                mark_reentry_monitor_60s_cycle_shield(
                    context=context, symbol=TARGET_SYMBOL, eval_price=ord_price
                )
                if (is_vacant_l1_now and not is_sub_lot)
                else safe_float(st.get("last_reentry_eval_ts"), 0.0)
            )
            sub_re_epoch = (
                mark_sub_reentry_monitor_60s_cycle_shield(
                    context=context, symbol=TARGET_SYMBOL, eval_price=ord_price
                )
                if (is_sub_vacant_l1_now and is_sub_lot)
                else safe_float(st.get("last_sub_reentry_eval_ts"), 0.0)
            )
            clear_kw: Dict[str, Any] = {
                "l1_target_quota_qty": fallback_target_q_on_zero_cancel,
                "sub_l1_target_quota_qty": fallback_sub_target_q_on_zero_cancel,
                "buy_order_id": "",
                "ordered_qty": 0,
                "buy_price": 0.0,
                "pending_portion_budget": 0.0,
                "pending_lot_type": "",
                "pending_step_up_min_price": 0.0,
                "pending_sub_step_up_min_price": 0.0,
                "last_reentry_eval_ts": re_epoch,
                "last_sub_reentry_eval_ts": sub_re_epoch,
            }
            await context.ledger.update_state(TARGET_SYMBOL, **clear_kw)
            return {"status": f"BUY_ORDER_{ord_status}_CLEARED"}

    if (
        elapsed_mod >= BUY_ORDER_MAX_WAIT_SEC
        or force_settle
        or should_abort_late_cutoff
    ):
        try:
            await context.api.cancel_order(buy_oid)
        except Exception:
            pass

        final_detail = await context.api.get_order_detail(buy_oid)
        f_status = (
            str(final_detail.get("status") or "").upper().strip()
            if isinstance(final_detail, dict)
            else ""
        )
        if not isinstance(final_detail, dict) or f_status in (
            "PENDING",
            "PARTIAL_FILLED",
            "PENDING_CANCEL",
            "PENDING_REPLACE",
        ):
            await asyncio.sleep(0.35)
            final_detail = await context.api.get_order_detail(buy_oid)
            f_status = (
                str(final_detail.get("status") or "").upper().strip()
                if isinstance(final_detail, dict)
                else ""
            )

        if not isinstance(final_detail, dict) and elapsed_mod >= (
            BUY_ORDER_MAX_WAIT_SEC + 15.0
        ):
            closed_cands = await context.api.get_closed_orders(
                symbol=TARGET_SYMBOL, limit=25
            )
            for c_item in closed_cands:
                if str(c_item.get("orderId") or "").strip() == buy_oid:
                    final_detail = c_item
                    f_status = (
                        str(c_item.get("status") or "").upper().strip()
                    )
                    break

        if isinstance(final_detail, dict):
            if f_status in (
                "PENDING",
                "PARTIAL_FILLED",
                "PENDING_CANCEL",
                "PENDING_REPLACE",
            ):
                return {
                    "status": "BUY_CANCEL_IN_FLIGHT",
                    "orderId": buy_oid,
                }
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
        elif elapsed_mod < (BUY_ORDER_MAX_WAIT_SEC + 30.0):
            return {
                "status": "BUY_CANCEL_VERIFY_RETRY",
                "orderId": buy_oid,
            }

        re_epoch = (
            mark_reentry_monitor_60s_cycle_shield(
                context=context, symbol=TARGET_SYMBOL, eval_price=ord_price
            )
            if (is_vacant_l1_now and not is_sub_lot)
            else safe_float(st.get("last_reentry_eval_ts"), 0.0)
        )
        sub_re_epoch = (
            mark_sub_reentry_monitor_60s_cycle_shield(
                context=context, symbol=TARGET_SYMBOL, eval_price=ord_price
            )
            if (is_sub_vacant_l1_now and is_sub_lot)
            else safe_float(st.get("last_sub_reentry_eval_ts"), 0.0)
        )
        timeout_kw: Dict[str, Any] = {
            "l1_target_quota_qty": fallback_target_q_on_zero_cancel,
            "sub_l1_target_quota_qty": fallback_sub_target_q_on_zero_cancel,
            "buy_order_id": "",
            "ordered_qty": 0,
            "buy_price": 0.0,
            "pending_portion_budget": 0.0,
            "pending_lot_type": "",
            "pending_step_up_min_price": 0.0,
            "pending_sub_step_up_min_price": 0.0,
            "last_reentry_eval_ts": re_epoch,
            "last_sub_reentry_eval_ts": sub_re_epoch,
        }
        await context.ledger.update_state(TARGET_SYMBOL, **timeout_kw)
        if should_abort_late_cutoff:
            abort_desc = (
                "서브 0주 신규 진입"
                if is_zero_sub_reentry
                else (
                    "서브 1층 공석 돌파 추격"
                    if is_sub_vacant_l1_breakout_reentry
                    else (
                        "0주 신규 진입"
                        if is_zero_grid_reentry
                        else "1층 공석 돌파 추격"
                    )
                )
            )
            logger.info(
                "🛡️ [Case 84/88 장마감 30분전(15:30 EST) 도래 -> 미체결 %s(%s) 즉시 안전 취소] 지정가 $%.2f 취소 ➔ 컷오프 방어 전환",
                abort_desc,
                raw_lot_type,
                ord_price,
            )
            return {
                "status": "BUY_ORDER_LATE_CUTOFF_CANCELED_SAFE",
                "abort_type": abort_desc,
            }
        logger.info(
            "⏳ [SOXL 현재가 지정가 매수(%s) 60초 미체결 안전 취소] 지정가 $%.2f 유지 종료 ➔ 관망 복귀",
            lot_type,
            ord_price,
        )
        return {"status": "BUY_ORDER_UNFILLED_CANCELED_SAFE"}

    return {"status": "BUY_ORDER_PENDING", "orderId": buy_oid}


# 하위 호환 별칭
sync_dynamic_vwap_buy_order_modify = sync_pending_buy_order_plugin
