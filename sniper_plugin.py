# -*- coding: utf-8 -*-
"""
# MODIFIED: sniper_plugin.py (Part 1/2 — _execute_sub_grid_buy_engine_plugin 및 execute_seed_protected_buy_gate_plugin 내 holdings·prices 선택 인자 안전 기본값 및 context 자동 폴백 탑재로 TypeError 원천 소각 · 황금시간 07:00~07:50 RSI<=19 올인 분기 G · 골든포켓 참조 · 임포트 전면 영구 소각 & Case 91 무제한 예비수혈 및 인출형[단리]/자산증식형[복리] 매수 정량 연동 & Case 92 본/서브 1층 공석 +1.00% 상승돌파 시 1분봉 Wilder RSI(14) <= 50.0 필터 탑재)
인피니트 스노우볼 (Infinite Snowball) v3.0 — 스나이퍼 매수 코어 Part 2 / 2 (Step 07 / 14)
역할:
1) sniper_plugin_core.py (Part 1 / 2) 의 모든 상수·타임쉴드·실시간 RSI(14) 추출기(_get_live_soxl_rsi_14)·GUARD30 무제한 예비수혈·체결커밋·미체결 동기화 심볼 명시적 재익스포트(Facade Re-export)로
   타 모듈(defense_plugin.py, tg_ui_plugin.py, main_runtime.py, main.py, plugin_updater.py) AST 임포트 호환성 100% 보장
2) 🛡️ [Case 88, Case 91 & Case 92 : 13_SUB_L1L3_RESV05_CAP4L] 스위치 없는 100% 기본 상시 적용(Default ON) 3층 서브 그리드 매수 엔진(_execute_sub_grid_buy_engine_plugin):
   - 본 그리드 1개 층 이상 보유 중(len(buckets) > 0) 본 그리드 5영업일 이상 연속 무매매(main_consec_frozen_days >= 5) 도달 시 또는 서브 그리드 기가동 중(len(sub_buckets) > 0) 상시 작동
   - 자산증식형(복리 · COMP_08PCT) / 인출형(단리 · SIMPLE_08PCT) 운용 모드에 연동된 본 그리드 0.5회분(4.0%) 보호예수금(reserved_for_main_usd) 차감 가용 유휴 현금(avail_idle_cash_usd) 및 서브 최대 누적 4회분(16.0%) 상한 캡(SUB_MAX_TOTAL_LOTS_4 = 4) 엄격 적용
   - 분기 S-A (서브 0주 첫 진입 SUB_REENTRY_1FL : 15:30 ~ 16:00 EST 차단 Case 84 & 유휴현금 부족 시 60초 쉴드 & 뮤텍스 2차 타임쉴드 검문) ·
     분기 S-B1 (서브 1층 공석 60초 주기 눌림[-1.0% 무필터]/돌파[+1.0% & RSI(14) <= 50.0 필터 · Case 92] 재장전 SUB_REENTRY_1FL : 서브 2층 단가 상한 가드 Case 73 & 15:30 ~ 16:00 EST 돌파 차단 Case 84 & 뮤텍스 2차 타임쉴드/RSI 검문) ·
     분기 S-B0 (서브 1층 부분체결 잔량 SUB_TOPUP_1FL 1.5초 모니터 재대기 Case 78 & 유휴현금 부족 시 60초 쉴드 & 뮤텍스 2차 타임쉴드 검문) ·
     분기 S-B2 (서브 활성 1층 보유 중 10분 게이트 : 서브 최고도달회차 4단 와이드 신저가 OR 서브 10영업일 무매매 & -10.0% 저가해금 SUB_UNLOCK_10D_D10 추매 SUB_DIP_1FL & 유휴현금 부족 시 해당 10분 버킷 즉시 소모 처리로 무한 API 폴링 차단)
3) 04:07 ~ 16:00 EST 비대칭 매수 타격 게이트 실행기 (execute_seed_protected_buy_gate_plugin):
   - 🛡️ [분기 A · Case 65, 67, 77, 84, 91] : 본 그리드 0주 상태(is_zero_shares)에서 0주 종료 후 60.0초 타임쉴드 경과 뒤 현재가 지정가 첫 1층(REENTRY_1FL) 산입하되,
     정규장 마감 30분 전(15:30 ~ 16:00 EST, is_late_regular_new_cycle_cutoff_window) 구간에서는 0주 새 사이클 첫 1층 진입을 100% 원천 차단(HOLD_LATE_SESSION_NEW_CYCLE_CUTOFF)!
   - 🔥 [분기 B-1 · Case 67, 73, 77, 84, 88, 91, 92] : 본 그리드 상단 2층 ~ 7층(GRID_L2 ~ GRID_L7) 보유 중 1층 공석 시 매 60.0초 주기 재장전 모니터
     (-1.00% 눌림목 무필터 승인 & +1.00% 상승돌파 시 1분봉 Wilder RSI(14) <= 50.0 필터 결합 · RSI > 50.0 과열 돌파 시 HOLD_BREAKOUT_RSI_OVER_50 차단 후 Default-ON 3층 서브 그리드 엔진으로 제어권 인계)
   - 🎯 [분기 B-0 · Case 78, 88] : 본 그리드 활성 1층 지정가 부분 체결 미체결 잔량(TOPUP_1FL) 1.5초 모니터 (원장 가용현금 1주 비용 선행 가드 및 부족 시 60초 쿨다운 쉴드 적용)
   - 🔵 [분기 B-2 · Case 60, 72, 76, 77, 87, 88, 91] : 본 그리드 활성 1층 보유 중 10분 고정 매수 게이트(4단 와이드 신저가 무필터 OR STEP2X_15PCT_C20 스텝업 해금) 및
     본 그리드 대기/패스 틱에서 Default-ON 3층 서브 그리드 매수 엔진 연속 가동
- 제1헌법 ~ 제6헌법 및 Case 01 ~ 93 완벽 준수
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime
from typing import Any, Dict, Optional

from quant_engine import (
    DEFAULT_GRID_MERGE_MODE,
    MAX_RESERVE_PORTIONS,
    MIN_DIP_BUDGET_RATIO,
    MIN_DIP_VS_L1_RATIO,
    PORTION_MODE_COMPOUND,
    PORTION_MODE_SIMPLE,
    PORTION_RATIO_LOCKED,
    PRIMER_1SH_LOT_TAG,
    PRIMER_1SH_VAC_LOT_TAG,
    PRIMER_MODE_AUTO_SMART,
    REENTRY_BREAKOUT_MAX_RSI_50,
    REENTRY_BREAKOUT_RISE_PCT,
    REG_OPEN_VWAP_SHIELD_END_HM,
    REG_OPEN_VWAP_SHIELD_START_HM,
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
    buckets_from_dicts,
    compute_golden8_quota_qty,
    compute_sub4_quota_qty,
    compute_sub_grid_available_idle_cash,
    compute_sub_upper_2_to_3_moving_avg,
    compute_upper_2_to_7_moving_avg,
    evaluate_l2_only_hybrid_reentry_signal,
    evaluate_l2_vacant_low_break_signal,
    evaluate_smart_primer_1sh_signal,
    evaluate_stalker_reversal_fire,
    evaluate_step_up_2x_dip_signal,
    evaluate_sub_grid_dip_signal,
    get_golden8_prog_thresholds,
    has_active_l1_bucket,
    has_active_l2_bucket,
    is_primer_1sh_tag,
    is_simple_income_mode,
    resolve_affordable_buy_qty,
    resolve_effective_round_trip_fee_rate_pct,
    resolve_portion_budget_base_equity,
    resolve_smart_primer_policy,
    resolve_smart_pullback_drop_pct,
    resolve_smart_rebound_policy,
    safe_bucket_lot_count,
)
from quant_indicators_plugin import (
    NEW_CYCLE_BUY_CUTOFF_HM,
    evaluate_buy_gate_bucket_status,
    is_active_buy_window,
    is_late_regular_new_cycle_cutoff_window,
    refresh_metrics_with_live_tick,
)
from sniper_exit_plugin import (
    POST_BUY_TO_SELL_SHIELD_SEC,
    POST_SELL_TO_BUY_SHIELD_SEC,
    is_within_post_buy_time_shield,
    is_within_post_sell_time_shield,
)
from sniper_plugin_core import (
    AUTO_FILL_GRACE_SHIELD_SEC,
    BUY_ORDER_MAX_WAIT_SEC,
    DEFAULT_UNLOCK_MODE,
    REENTRY_MONITOR_TIME_SHIELD_SEC,
    RESERVE_DEPOSIT_CHECK_INTERVAL_SEC,
    STEP_UP_2X_DROP_PCT,
    STEP_UP_2X_MAX_TIERS,
    STEP_UP_2X_MIN_CASH_RATIO,
    STEP_UP_2X_MIN_REBOUND_MULT,
    _check_and_execute_guard30_or_reserve_injection,
    _check_and_prepare_primer_1sh_cash,
    _commit_filled_buy_to_stratum_ledger,
    _fetch_fresh_current_soxl_price,
    _get_cached_soxl_session_vwap,
    _get_live_soxl_price,
    _get_live_soxl_reentry_snapshot,
    _get_live_soxl_rsi_14,
    _get_live_soxl_stalker_bar_snapshot,
    is_within_auto_fill_grace_shield,
    is_within_reentry_monitor_time_shield,
    is_within_reserve_deposit_check_shield,
    is_within_sub_reentry_monitor_time_shield,
    mark_auto_fill_grace_shield,
    mark_pullback_ha_bear_minute_wait,
    mark_reentry_monitor_60s_cycle_shield,
    mark_reserve_deposit_check_shield,
    mark_sub_pullback_ha_bear_minute_wait,
    mark_sub_reentry_monitor_60s_cycle_shield,
    min_req_cash_str,
    sync_dynamic_vwap_buy_order_modify,
    sync_pending_buy_order_plugin,
)
from barbell_plugin import (
    get_masked_soxl_buying_power_usd,
    is_barbell_mode,
)
from toss_api import (
    DEFAULT_INITIAL_SEED_USD,
    EST_TZ,
    LOCKED_BUY_INTERVAL_MIN,
    TARGET_SYMBOL,
    generate_client_order_id,
    safe_float,
    safe_int,
)

logger = logging.getLogger("toss_sniper.sniper_plugin")


# MODIFIED: 중복 선언 소각 완료 단일 정본
def _resolve_masked_bp_for_soxl_sub_or_topup(
    context: Any,
    st_soxl: Dict[str, Any],
    raw_bp_usd: float,
) -> float:
    raw_bp = max(0.0, safe_float(raw_bp_usd, 0.0))
    if raw_bp <= 0.0:
        return 0.0
    if is_barbell_mode(st_soxl.get("portion_mode")):
        return get_masked_soxl_buying_power_usd(
            context=context, raw_bp_usd=raw_bp, st_soxl=st_soxl
        )
    vault_locked = max(
        0.0, safe_float(st_soxl.get("vaulted_profit_locked_usd"), 0.0)
    )
    return round(max(0.0, raw_bp - vault_locked), 4)


# ---------------------------------------------------------------------------
# [핵심 1 · Case 88, Case 91 & Case 92] 스위치 없는 100% 기본 상시 적용(Default ON) 3층 서브 그리드 매수 엔진 (_execute_sub_grid_buy_engine_plugin)
# ---------------------------------------------------------------------------
async def _execute_sub_grid_buy_engine_plugin(
    context: Any,
    holdings: Optional[Dict[str, Dict[str, Any]]] = None,
    prices: Optional[Dict[str, float]] = None,
    dt_now: Optional[datetime] = None,
    live_p: float = 0.0,
    **kwargs: Any,
) -> Optional[Dict[str, Any]]:
    """
    # MODIFIED [Case 88, Case 91 & Case 92 : 🛡️ 13_SUB_L1L3_RESV05_CAP4L — Default-ON 3층 서브 그리드 매수 엔진 (holdings·prices 선택 인자 안전 기본값 처리 · 자산증식형[복리] ⇄ 인출형[단리] 연동 · 서브 1층 공석 +1.00% 돌파 시 RSI(14) <= 50.0 필터 · 유휴현금 부족 시 10분 버킷 즉시 소모 & 60초 쉴드 & 뮤텍스 2차 타임쉴드 검문 강화)]:
    본 그리드가 대기/패스한 틱에서 호출되어:
    1) 본 그리드가 최소 1개 층 이상 보유 중(len(buckets) > 0)이고,
       본 그리드 연속 무매매일(main_consec_frozen_days >= 5)이 5영업일 이상이거나 이미 서브 그리드가 가동 중(len(sub_buckets) > 0)일 때 작동한다.
    2) 운용 모드(portion_mode : COMP_08PCT 복리 vs SIMPLE_08PCT 단리)에 따라 산출된 본 그리드 보호예수금 0.5회분(reserved_for_main_usd, 기준자산의 4.0%)을 차감한
       순수 유휴 현금(avail_idle_cash_usd) 범위 내에서만 매수하며, 온디맨드 예비시드 차입이나 시드고갈 알림을 절대 발동하지 않는다.
    3) 서브 누적 합병 회차가 최대 상한 4회분(SUB_MAX_TOTAL_LOTS_4 = 4, 기준자산의 16.0%)에 도달하면
       미체결 잔량 보충(SUB_TOPUP_1FL) 외의 모든 신규/추가 서브 매수를 차단(HOLD_SUB_CAP_4_LOTS_REACHED)하여 본 그리드 탄약을 보전한다.
    4) 서브 1층 공석 재장전(S-B1) 시 -1.00% 눌림목은 무필터로 승인하고 +1.00% 상승돌파는 1분봉 Wilder RSI(14) <= 50.0 이하일 때만 승인한다 (Case 92).
    5) 서브 10분 게이트(S-B2)에서 유휴현금 부족 시 해당 10분 버킷(sub_last_evaluated_buy_bucket_id)을 즉시 소모 처리하고,
       서브 0주(S-A) 및 서브 잔량 보충(S-B0)에서 유휴현금 부족 시 60.0초 쿨다운 쉴드를 각인하여 불필요한 반복 API 호출을 원천 차단한다.
    """
    eff_dt_now = (
        dt_now.astimezone(EST_TZ) if dt_now else datetime.now(EST_TZ)
    )
    eff_holdings = (
        holdings
        if isinstance(holdings, dict) and holdings
        else (
            getattr(context, "latest_holdings", {})
            if context is not None
            else {}
        )
    )
    eff_prices = (
        prices
        if isinstance(prices, dict) and prices
        else (
            getattr(context, "latest_prices", {})
            if context is not None
            else {}
        )
    )
    if live_p <= 0.0:
        live_p = _get_live_soxl_price(
            context, eff_prices, eff_holdings, eff_dt_now
        )
    if live_p <= 0.0:
        return None

    st = context.ledger.get_state(TARGET_SYMBOL)
    if str(st.get("buy_order_id") or "").strip() or str(
        st.get("sell_order_id") or ""
    ).strip():
        return None

    buckets = buckets_from_dicts(st.get("buckets", []))
    if not buckets:
        return None

    sub_buckets = buckets_from_dicts(st.get("sub_buckets", []))
    # MODIFIED [Case 113 : 서브 그리드 신규 매수/추매 전면 영구 폐기 (기보유 잔량만 청산 엔진에서 익절 졸업)]
    if not bool(st.get("sub_grid_enabled", False)):
        return None
    main_frozen_d = max(0, safe_int(st.get("main_consec_frozen_days"), 0))
    if main_frozen_d < SUB_FROZEN_DAYS_TRIGGER and len(sub_buckets) == 0:
        return None

    hm = eff_dt_now.hour * 100 + eff_dt_now.minute
    if not is_active_buy_window(hm, now_est=eff_dt_now):
        return None

    in_sell_sh, _ = is_within_post_sell_time_shield(context, st, TARGET_SYMBOL)
    in_buy_sh, _ = is_within_post_buy_time_shield(context, st, TARGET_SYMBOL)
    if in_sell_sh or in_buy_sh:
        return None

    eff_rt_pct = resolve_effective_round_trip_fee_rate_pct(state_dict=st)
    fee_mult = 1.0 + (eff_rt_pct / 100.0)

    init_seed = max(
        100.0, safe_float(st.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD)
    )
    free_cash = max(0.0, safe_float(st.get("free_cash_usd"), 0.0))
    inj_res_usd = max(0.0, safe_float(st.get("injected_reserve_usd"), 0.0))
    actual_inv_total = sum(b.actual_cost_usd for b in buckets) + sum(
        sb.actual_cost_usd for sb in sub_buckets
    )
    core_equity = max(init_seed, (free_cash + actual_inv_total) - inj_res_usd)
    portion_mode = (
        str(st.get("portion_mode") or PORTION_MODE_COMPOUND).upper().strip()
    )

    idle_info = compute_sub_grid_available_idle_cash(
        free_cash_usd=free_cash,
        core_equity_usd=core_equity,
        broker_buying_power_usd=None,
        reserve_main_portions=SUB_RESERVE_MAIN_PORTIONS,
        initial_seed_usd=init_seed,
        portion_mode=portion_mode,
    )
    avail_idle_ledger = safe_float(idle_info.get("avail_idle_cash_usd"), 0.0)
    sub_portion_budget = safe_float(
        idle_info.get("sub_portion_budget"), round(core_equity * 0.04, 4)
    )

    sub_cur_total_lots = sum(max(1, sb.lot_count) for sb in sub_buckets)
    sub_max_lots_cap = max(
        1, safe_int(st.get("sub_max_total_lots"), SUB_MAX_TOTAL_LOTS_4)
    )
    has_sub_active_l1 = has_active_l1_bucket(sub_buckets)
    is_sub_l2_only = bool(len(sub_buckets) > 0 and not has_sub_active_l1)

    # -----------------------------------------------------------------------
    # [서브 분기 S-A : 서브 그리드 0주 첫 진입 (len(sub_buckets) == 0 and main_consec_frozen_days >= 5)]
    # -> 15:30 ~ 16:00 EST 구간에서는 서브 0주 새 사이클 첫 1층 진입 차단 (Case 84 & Case 88)
    # -----------------------------------------------------------------------
    if len(sub_buckets) == 0:
        smart_sub_pol = resolve_smart_primer_policy(
            portion_mode=portion_mode,
            primer_1sh_mode=st.get("primer_1sh_mode"),
        )
        if not bool(smart_sub_pol.get("allow_new_sub_entry", True)):
            return {
                "status": "HOLD_SUB_NEW_ENTRY_OFF_IN_SMART_COMPOUND",
                "portion_mode": portion_mode,
            }
        if is_late_regular_new_cycle_cutoff_window(hm, now_est=eff_dt_now):
            return {
                "status": "HOLD_SUB_LATE_SESSION_NEW_CYCLE_CUTOFF",
                "hm": hm,
                "cutoff_hm": NEW_CYCLE_BUY_CUTOFF_HM,
            }

        in_sub_re_sh, rem_sub_re = is_within_sub_reentry_monitor_time_shield(
            context, st, TARGET_SYMBOL
        )
        if in_sub_re_sh:
            return {
                "status": "HOLD_SUB_POST_SELL_60S_SHIELD",
                "remain_shield_sec": rem_sub_re,
            }

        min_req_sub_0sh = max(
            live_p * fee_mult, sub_portion_budget * MIN_DIP_BUDGET_RATIO
        )
        if avail_idle_ledger < min_req_sub_0sh:
            mark_sub_reentry_monitor_60s_cycle_shield(
                context=context,
                symbol=TARGET_SYMBOL,
                eval_price=live_p,
            )
            return {
                "status": "HOLD_SUB_INSUFFICIENT_IDLE_CASH",
                "avail_idle_cash_usd": avail_idle_ledger,
                "min_req_cash_usd": round(min_req_sub_0sh, 4),
            }

        async with context.in_memory_ordering_lock:
            async with context.dual_strike_mutex:
                st_now = context.ledger.get_state(TARGET_SYMBOL)
                if str(st_now.get("buy_order_id") or "").strip() or str(
                    st_now.get("sell_order_id") or ""
                ).strip():
                    return {"status": "ALREADY_ORDERING_IN_MUTEX"}

                in_s_sh, _ = is_within_post_sell_time_shield(
                    context, st_now, TARGET_SYMBOL
                )
                in_b_sh, _ = is_within_post_buy_time_shield(
                    context, st_now, TARGET_SYMBOL
                )
                in_sub_re_m, _ = is_within_sub_reentry_monitor_time_shield(
                    context, st_now, TARGET_SYMBOL
                )
                if in_s_sh or in_b_sh or in_sub_re_m:
                    return {"status": "HOLD_60S_TIME_SHIELD_IN_MUTEX"}

                now_buckets = buckets_from_dicts(st_now.get("buckets", []))
                now_sub_buckets = buckets_from_dicts(
                    st_now.get("sub_buckets", [])
                )
                now_main_frozen = max(
                    0, safe_int(st_now.get("main_consec_frozen_days"), 0)
                )
                if (
                    not now_buckets
                    or len(now_sub_buckets) > 0
                    or now_main_frozen < SUB_FROZEN_DAYS_TRIGGER
                ):
                    return {"status": "SUB_STATE_CHANGED_IN_MUTEX"}

                dt_mutex = datetime.now(EST_TZ)
                hm_mutex = dt_mutex.hour * 100 + dt_mutex.minute
                if is_late_regular_new_cycle_cutoff_window(
                    hm_mutex, now_est=dt_mutex
                ):
                    return {
                        "status": "HOLD_SUB_LATE_SESSION_NEW_CYCLE_CUTOFF",
                        "hm": hm_mutex,
                    }

                fresh_live_p = await _fetch_fresh_current_soxl_price(
                    context, fallback_price=live_p
                )
                if fresh_live_p <= 0.0:
                    return {"status": "NO_FRESH_LIVE_PRICE"}

                exec_order_p = max(
                    0.01, math.floor((fresh_live_p + 1e-9) * 100.0) / 100.0
                )
                eff_rt_pct_m = resolve_effective_round_trip_fee_rate_pct(
                    state_dict=st_now
                )
                fee_mult_m = 1.0 + (eff_rt_pct_m / 100.0)
                now_free_cash = max(
                    0.0, safe_float(st_now.get("free_cash_usd"), 0.0)
                )
                now_init_seed = max(
                    100.0,
                    safe_float(
                        st_now.get("initial_seed_usd"),
                        DEFAULT_INITIAL_SEED_USD,
                    ),
                )
                now_inj_res = max(
                    0.0, safe_float(st_now.get("injected_reserve_usd"), 0.0)
                )
                now_inv_tot = sum(b.actual_cost_usd for b in now_buckets)
                now_core_eq = max(
                    now_init_seed, (now_free_cash + now_inv_tot) - now_inj_res
                )
                now_p_mode = (
                    str(st_now.get("portion_mode") or PORTION_MODE_COMPOUND)
                    .upper()
                    .strip()
                )

                raw_bp_sub = await context.api.get_buying_power_usd(
                    safety_buffer_pct=0.2
                )
                if raw_bp_sub <= 0.0 and now_free_cash >= (
                    exec_order_p * fee_mult_m
                ):
                    await asyncio.sleep(0.25)
                    raw_bp_sub = await context.api.get_buying_power_usd(
                        safety_buffer_pct=0.2
                    )
                    if raw_bp_sub <= 0.0:
                        return {"status": "HOLD_SUB_TRANSIENT_BP_API_ERROR"}

                masked_bp_sub = _resolve_masked_bp_for_soxl_sub_or_topup(
                    context, st_now, raw_bp_sub
                )
                idle_m = compute_sub_grid_available_idle_cash(
                    free_cash_usd=now_free_cash,
                    core_equity_usd=now_core_eq,
                    broker_buying_power_usd=masked_bp_sub,
                    reserve_main_portions=SUB_RESERVE_MAIN_PORTIONS,
                    initial_seed_usd=now_init_seed,
                    portion_mode=now_p_mode,
                )
                avail_idle_m = safe_float(
                    idle_m.get("avail_idle_cash_usd"), 0.0
                )
                prev_sub_anc = safe_float(st_now.get("sub_anchor_price"), 0.0)
                ref_sub_anc = (
                    prev_sub_anc if prev_sub_anc > 0.0 else exec_order_p
                )
                sub_target_qty, sub_p_bud = compute_sub4_quota_qty(
                    sub_anchor_price=ref_sub_anc,
                    current_core_equity=now_core_eq,
                    initial_seed_usd=now_init_seed,
                    exec_price=exec_order_p,
                    portion_mode=now_p_mode,
                )
                min_req_sub_m = max(
                    exec_order_p * fee_mult_m,
                    sub_p_bud * MIN_DIP_BUDGET_RATIO,
                )
                if avail_idle_m < min_req_sub_m:
                    mark_sub_reentry_monitor_60s_cycle_shield(
                        context=context,
                        symbol=TARGET_SYMBOL,
                        eval_price=exec_order_p,
                    )
                    return {
                        "status": "HOLD_SUB_INSUFFICIENT_IDLE_CASH_IN_MUTEX",
                        "avail_idle_cash_usd": avail_idle_m,
                    }

                buy_qty_sub, _ = resolve_affordable_buy_qty(
                    target_qty=sub_target_qty,
                    price_t=exec_order_p,
                    free_cash_usd=avail_idle_m,
                    broker_buying_power_usd=avail_idle_m,
                    max_portion_budget_usd=sub_p_bud,
                    round_trip_fee_rate_pct=eff_rt_pct_m,
                )
                if buy_qty_sub <= 0:
                    mark_sub_reentry_monitor_60s_cycle_shield(
                        context=context,
                        symbol=TARGET_SYMBOL,
                        eval_price=exec_order_p,
                    )
                    return {"status": "INSUFFICIENT_IDLE_CASH_FOR_SUB_0SH"}

                _, sub_cur_bucket_id, sub_today_str, _ = (
                    evaluate_buy_gate_bucket_status(
                        now_est=eff_dt_now,
                        buy_interval_min=LOCKED_BUY_INTERVAL_MIN,
                        last_evaluated_bucket_id=safe_int(
                            st_now.get("sub_last_evaluated_buy_bucket_id"), -1
                        ),
                        last_evaluated_date=str(
                            st_now.get("sub_last_evaluated_date") or ""
                        ),
                    )
                )
                cid = generate_client_order_id(prefix="SUB1FL")
                try:
                    ord_res = await context.api.create_order(
                        symbol=TARGET_SYMBOL,
                        side="BUY",
                        quantity=buy_qty_sub,
                        price=exec_order_p,
                        order_type="LIMIT",
                        time_in_force="DAY",
                        client_order_id=cid,
                        enforce_daymarket_block=True,
                    )
                except Exception as exc:
                    mark_sub_reentry_monitor_60s_cycle_shield(
                        context=context,
                        symbol=TARGET_SYMBOL,
                        eval_price=exec_order_p,
                    )
                    logger.warning(
                        "Case 88 서브그리드 0주 첫 1층(SUB_REENTRY_1FL) 주문 예외: %s",
                        exc,
                    )
                    return {"status": "SUB_ORDER_ERROR", "error": str(exc)}

                oid = str(ord_res.get("orderId") or "").strip()
                await context.ledger.update_state(
                    TARGET_SYMBOL,
                    sub_l1_target_quota_qty=buy_qty_sub,
                    buy_order_id=oid,
                    client_order_id=cid,
                    ordered_qty=buy_qty_sub,
                    buy_price=exec_order_p,
                    pending_portion_budget=sub_p_bud,
                    pending_lot_type="SUB_REENTRY_1FL",
                    pending_step_up_min_price=0.0,
                    pending_sub_step_up_min_price=0.0,
                    sub_last_evaluated_buy_bucket_id=sub_cur_bucket_id,
                    sub_last_evaluated_date=sub_today_str,
                    last_modify_mono=time.monotonic(),
                    last_sub_reentry_eval_ts=0.0,
                )
                context.wakeup_event.set()
                logger.info(
                    "🛡️ [Case 88 SOXL 본그리드 %d일 무매매 동결 -> 3층 서브그리드 첫 1층(SUB_REENTRY_1FL) 발주] %d주 @ 지정가 $%.2f (4%%예산 $%.2f · 유휴현금 $%.2f · orderId=%s)",
                    now_main_frozen,
                    buy_qty_sub,
                    exec_order_p,
                    sub_p_bud,
                    avail_idle_m,
                    oid,
                )
                return {
                    "status": "SUB_ZERO_SHARES_1FL_ORDERED",
                    "orderId": oid,
                    "qty": buy_qty_sub,
                    "price": exec_order_p,
                    "main_consec_frozen_days": now_main_frozen,
                }

    # -----------------------------------------------------------------------
    # [서브 분기 S-B1 : 서브 상단(2~3층)만 보유 중 (서브 1층 공석, is_sub_l2_only == True)]
    # -> 서브 누적 4회분 미만 & 매 60.0초 주기 & 서브 2층 단가 상한(Case 73) & 15:30 돌파 차단(Case 84) & +1.0% 돌파 시 RSI(14) <= 50.0 필터(Case 92)
    # -----------------------------------------------------------------------
    if is_sub_l2_only:
        if sub_cur_total_lots >= sub_max_lots_cap:
            return {
                "status": "HOLD_SUB_CAP_4_LOTS_REACHED",
                "sub_cur_total_lots": sub_cur_total_lots,
                "sub_max_total_lots": sub_max_lots_cap,
            }

        sub_rebound_pol = resolve_smart_rebound_policy(portion_mode)
        use_sub_stalker = bool(sub_rebound_pol.get("use_stalker_l1", False))
        cur_stalk_sub_act = bool(
            use_sub_stalker and st.get("stalk_sub_active", False)
        )

        in_sub_re_sh, rem_sub_re = is_within_sub_reentry_monitor_time_shield(
            context, st, TARGET_SYMBOL, now_est=eff_dt_now
        )
        if in_sub_re_sh and (not cur_stalk_sub_act):
            return {
                "status": "HOLD_SUB_REENTRY_60S_TIME_SHIELD",
                "remain_shield_sec": rem_sub_re,
            }

        fresh_live_p = (
            live_p
            if (cur_stalk_sub_act and live_p > 0.0)
            else await _fetch_fresh_current_soxl_price(
                context, fallback_price=live_p, now_est=eff_dt_now
            )
        )
        if fresh_live_p <= 0.0:
            return {"status": "NO_FRESH_LIVE_PRICE"}
        sub_re_price_mono = (
            0.0 if cur_stalk_sub_act else time.monotonic()
        )  # MODIFIED [Case 112]: 스토커 추적 발사 시 뮤텍스 2차 실호가 강제 보장

        (
            live_rsi_14,
            sub_shaved_bear,
            sub_ha_bull,
            sub_ha_ready,
            sub_closed_mk,
        ) = await _get_live_soxl_reentry_snapshot(
            context, live_price=fresh_live_p, now_est=eff_dt_now
        )
        sub_sess_vwap = _get_cached_soxl_session_vwap(
            context, live_price=fresh_live_p, now_est=eff_dt_now
        )
        sub_min_upper_p = min(sb.book_price for sb in sub_buckets)
        sub_anchor_p = safe_float(
            st.get("sub_anchor_price"), sub_min_upper_p
        )
        sub_cycle_min_p_re = safe_float(
            st.get("sub_cycle_min_buy_price"), 0.0
        )
        is_late_cutoff = is_late_regular_new_cycle_cutoff_window(
            hm, now_est=eff_dt_now
        )

        sub_re_sig = evaluate_l2_only_hybrid_reentry_signal(
            live_price=fresh_live_p,
            anchor_price=sub_anchor_p,
            l2_book_price=sub_min_upper_p,
            min_upper_tier_price=sub_min_upper_p,
            is_late_new_cycle_cutoff=is_late_cutoff,
            is_late_cutoff=is_late_cutoff,
            rsi_14=live_rsi_14,
            breakout_max_rsi=REENTRY_BREAKOUT_MAX_RSI_50,
            closed_ha_shaved_bear=(False if use_sub_stalker else sub_shaved_bear),
            closed_ha_bull=sub_ha_bull,
            closed_ha_ready=(True if use_sub_stalker else sub_ha_ready),
            session_vwap=sub_sess_vwap,
            hm=hm,
            cycle_min_buy_price=(
                sub_cycle_min_p_re if sub_cycle_min_p_re > 0.0 else None
            ),
            portion_mode=portion_mode,
        )
        sub_sig_type = str(sub_re_sig.get("signal_type") or "HOLD_WAIT_GATE")

        # NEW [Case 112 : 바벨/단리 서브 1층 공석 리바운드 스토커 저점 추적 & 완결 양봉 반전 타격]
        if use_sub_stalker:
            s_bar_snap = _get_live_soxl_stalker_bar_snapshot(
                context, live_price=fresh_live_p, now_est=eff_dt_now
            )
            prev_s_low = safe_float(st.get("stalk_sub_low_price"), 0.0)
            want_s_stalk = bool(
                cur_stalk_sub_act
                or (
                    bool(sub_re_sig.get("should_buy"))
                    and sub_sig_type in ("PULLBACK_RELOAD", "LOW_BREAK_RELOAD")
                )
            )
            if want_s_stalk and fresh_live_p <= (sub_min_upper_p + 1e-6):
                s_stalk_ev = evaluate_stalker_reversal_fire(
                    live_price=fresh_live_p,
                    cur_bar_open=s_bar_snap["cur_bar_open"],
                    cur_bar_low=s_bar_snap["cur_bar_low"],
                    prev_stalk_low=(
                        prev_s_low if cur_stalk_sub_act else s_bar_snap["cur_bar_low"]
                    ),
                    closed_real_reversal=s_bar_snap["closed_real_reversal"],
                    closed_ha_shaved_bear=s_bar_snap["closed_ha_shaved_bear"],
                    closed_ha_ready=s_bar_snap["closed_ha_ready"],
                    stalk_rebound_pct=safe_float(
                        sub_rebound_pol.get("stalk_rebound_pct"), 0.25
                    ),
                    hm=hm,
                    is_sub_grid=True,
                )
                next_s_low = safe_float(
                    s_stalk_ev.get("stalk_low_price"), fresh_live_p
                )
                # MODIFIED [Audit-112-01]: 서브 스토커 바닥 반등 시 기준가·2층상한 미만 정당 반등 전면 허용 및 저가돌파 기준가 보존
                sub_pb_d = safe_float(
                    sub_re_sig.get("pullback_drop_pct"), -1.0
                )
                sub_chg_ex = safe_float(
                    sub_re_sig.get("chg_from_exit_pct"), 0.0
                )
                sub_ceil_lim = (
                    min(sub_anchor_p, sub_min_upper_p)
                    if sub_anchor_p > 0.0
                    else sub_min_upper_p
                )
                still_in_sub_dip = bool(
                    sub_chg_ex <= (sub_pb_d * 0.5)
                    or (
                        (cur_stalk_sub_act or bool(sub_re_sig.get("should_buy")))
                        and fresh_live_p < (sub_ceil_lim - 1e-6)
                    )
                )
                if bool(s_stalk_ev.get("should_fire")) and still_in_sub_dip:
                    sub_re_sig = dict(sub_re_sig)
                    sub_re_sig["should_buy"] = True
                    is_sub_lb_fire = bool(
                        sub_cycle_min_p_re > 0.0
                        and min(fresh_live_p, next_s_low)
                        < (sub_cycle_min_p_re - 1e-6)
                        and fresh_live_p <= sub_cycle_min_p_re * 1.005
                    )
                    sub_sig_type = (
                        "LOW_BREAK_RELOAD"
                        if is_sub_lb_fire
                        else "PULLBACK_RELOAD"
                    )
                    sub_re_sig["signal_type"] = sub_sig_type
                    if is_sub_lb_fire:
                        sub_re_sig["quota_ref_price"] = sub_cycle_min_p_re
                elif not still_in_sub_dip:
                    if cur_stalk_sub_act:
                        await context.ledger.update_state(
                            TARGET_SYMBOL,
                            stalk_sub_active=False,
                            stalk_sub_low_price=0.0,
                        )
                else:
                    if (not cur_stalk_sub_act) or (
                        next_s_low > 0.0 and abs(next_s_low - prev_s_low) > 1e-4
                    ):
                        await context.ledger.update_state(
                            TARGET_SYMBOL,
                            stalk_sub_active=True,
                            stalk_sub_low_price=next_s_low,
                            last_sub_reentry_eval_ts=0.0,
                        )
                    return {
                        "status": "SUB_STALKING_REBOUND_WAIT",
                        "signal_type": s_stalk_ev.get("fire_reason"),
                        "live_price": fresh_live_p,
                        "stalk_low_price": next_s_low,
                    }

        if not bool(sub_re_sig.get("should_buy")):
            if sub_sig_type in (
                "HOLD_PULLBACK_SHAVED_HA_BEAR",
                "HOLD_LOW_BREAK_SHAVED_HA_BEAR",
                "HOLD_REG_OPEN_7M_VWAP_SHIELD",
            ):
                mark_sub_pullback_ha_bear_minute_wait(
                    context=context,
                    symbol=TARGET_SYMBOL,
                    cur_min_key=eff_dt_now.strftime("%Y-%m-%d %H:%M"),
                )
                if safe_float(st.get("last_sub_reentry_eval_ts"), 0.0) > 0.0:
                    await context.ledger.update_state(
                        TARGET_SYMBOL, last_sub_reentry_eval_ts=0.0
                    )
                logger.info(
                    "🛡️ [Case 101/105 서브 1층 공석 분경계 패스(%s)] 현재가 $%.2f · 서브저가 $%.2f · 세션VWAP $%.2f · 완결봉(%s) -> 다음 분 정각 재검문",
                    sub_sig_type,
                    fresh_live_p,
                    sub_cycle_min_p_re,
                    sub_sess_vwap,
                    sub_closed_mk or "-",
                )
                return {
                    "status": "SUB_L2_ONLY_MINUTE_BOUNDARY_HOLD",
                    "signal_type": sub_sig_type,
                    "live_price": fresh_live_p,
                    "session_vwap": sub_sess_vwap,
                    "closed_ha_shaved_bear": sub_shaved_bear,
                    "closed_ha_bull": sub_ha_bull,
                    "sub_l2_ceiling_price": sub_min_upper_p,
                }
            sub_re_epoch = mark_sub_reentry_monitor_60s_cycle_shield(
                context=context,
                symbol=TARGET_SYMBOL,
                eval_price=fresh_live_p,
            )
            await context.ledger.update_state(
                TARGET_SYMBOL,
                last_sub_reentry_eval_ts=sub_re_epoch,
            )
            return {
                "status": "SUB_L2_ONLY_REENTRY_HOLD",
                "signal_type": sub_sig_type,
                "live_price": fresh_live_p,
                "session_vwap": sub_sess_vwap,
                "rsi_14": live_rsi_14,
                "sub_l2_ceiling_price": sub_min_upper_p,
            }

        async with context.in_memory_ordering_lock:
            async with context.dual_strike_mutex:
                st_now = context.ledger.get_state(TARGET_SYMBOL)
                if str(st_now.get("buy_order_id") or "").strip() or str(
                    st_now.get("sell_order_id") or ""
                ).strip():
                    return {"status": "ALREADY_ORDERING_IN_MUTEX"}

                in_s_sh, _ = is_within_post_sell_time_shield(
                    context, st_now, TARGET_SYMBOL
                )
                in_b_sh, _ = is_within_post_buy_time_shield(
                    context, st_now, TARGET_SYMBOL
                )
                in_sub_re_m, _ = is_within_sub_reentry_monitor_time_shield(
                    context, st_now, TARGET_SYMBOL
                )
                if in_s_sh or in_b_sh or in_sub_re_m:
                    return {"status": "HOLD_60S_TIME_SHIELD_IN_MUTEX"}

                now_buckets = buckets_from_dicts(st_now.get("buckets", []))
                now_sub_buckets = buckets_from_dicts(
                    st_now.get("sub_buckets", [])
                )
                if (
                    not now_buckets
                    or not now_sub_buckets
                    or has_active_l1_bucket(now_sub_buckets)
                ):
                    return {"status": "SUB_L1_STATE_CHANGED_IN_MUTEX"}

                now_sub_lots = sum(
                    max(1, sb.lot_count) for sb in now_sub_buckets
                )
                if now_sub_lots >= sub_max_lots_cap:
                    return {"status": "HOLD_SUB_CAP_4_LOTS_REACHED"}

                dt_re_m = datetime.now(EST_TZ)
                hm_re_m = dt_re_m.hour * 100 + dt_re_m.minute
                # NEW [Audit-111-02]: 뮤텍스 경합 대기(>=0.25s) 발생 시 브로커 2차 실호가 즉시 재동기화
                if (time.monotonic() - sub_re_price_mono) >= 0.25:
                    live_2nd_sub = await _fetch_fresh_current_soxl_price(
                        context, fallback_price=fresh_live_p, now_est=dt_re_m
                    )
                    if live_2nd_sub > 0.0:
                        fresh_live_p = live_2nd_sub
                if (
                    sub_sig_type == "BREAKOUT_RELOAD"
                    and is_late_regular_new_cycle_cutoff_window(
                        hm_re_m, now_est=dt_re_m
                    )
                ):
                    sub_re_epoch = mark_sub_reentry_monitor_60s_cycle_shield(
                        context=context,
                        symbol=TARGET_SYMBOL,
                        eval_price=fresh_live_p,
                    )
                    await context.ledger.update_state(
                        TARGET_SYMBOL,
                        last_sub_reentry_eval_ts=sub_re_epoch,
                    )
                    return {
                        "status": "SUB_L2_ONLY_LATE_BREAKOUT_BLOCKED",
                        "signal_type": "HOLD_LATE_SESSION_BREAKOUT_CUTOFF",
                    }

                # [Case 92 & 눌림목 완결1분HA : 뮤텍스 내부 서브 1층 공석 2차 검문]
                if sub_sig_type == "BREAKOUT_RELOAD":
                    mutex_sub_rsi = await _get_live_soxl_rsi_14(
                        context, live_price=fresh_live_p, now_est=dt_re_m
                    )
                    if mutex_sub_rsi > (REENTRY_BREAKOUT_MAX_RSI_50 + 1e-6):
                        sub_re_epoch = mark_sub_reentry_monitor_60s_cycle_shield(
                            context=context,
                            symbol=TARGET_SYMBOL,
                            eval_price=fresh_live_p,
                        )
                        await context.ledger.update_state(
                            TARGET_SYMBOL,
                            last_sub_reentry_eval_ts=sub_re_epoch,
                        )
                        return {
                            "status": "SUB_L2_ONLY_BREAKOUT_RSI_BLOCKED",
                            "signal_type": "HOLD_BREAKOUT_RSI_OVER_50",
                            "rsi_14": mutex_sub_rsi,
                        }
                elif sub_sig_type in ("PULLBACK_RELOAD", "LOW_BREAK_RELOAD"):
                    (
                        _,
                        m_sub_shaved_bear,
                        m_sub_ha_bull,
                        m_sub_ha_ready,
                        _,
                    ) = await _get_live_soxl_reentry_snapshot(
                        context, live_price=fresh_live_p, now_est=dt_re_m
                    )
                    m_sub_vwap = _get_cached_soxl_session_vwap(
                        context, live_price=fresh_live_p, now_est=dt_re_m
                    )
                    m_sub_c_min = safe_float(
                        st_now.get("sub_cycle_min_buy_price"), 0.0
                    )
                    m_exec_p_chk = max(
                        0.01, math.floor((fresh_live_p + 1e-9) * 100.0) / 100.0
                    )
                    if (
                        sub_sig_type == "PULLBACK_RELOAD"
                        and REG_OPEN_VWAP_SHIELD_START_HM
                        <= hm_re_m
                        <= REG_OPEN_VWAP_SHIELD_END_HM
                    ):
                        mark_sub_pullback_ha_bear_minute_wait(
                            context=context,
                            symbol=TARGET_SYMBOL,
                            cur_min_key=dt_re_m.strftime("%Y-%m-%d %H:%M"),
                        )
                        await context.ledger.update_state(
                            TARGET_SYMBOL, last_sub_reentry_eval_ts=0.0
                        )
                        return {
                            "status": "SUB_L2_ONLY_REG_OPEN_7M_SHIELD",
                            "signal_type": "HOLD_REG_OPEN_7M_VWAP_SHIELD",
                        }
                    m_use_sub_stalk = bool(
                        resolve_smart_rebound_policy(
                            st_now.get("portion_mode")
                        ).get("use_stalker_l1", False)
                    )
                    if (not m_use_sub_stalk) and (
                        (not m_sub_ha_ready) or m_sub_shaved_bear
                    ):
                        mark_sub_pullback_ha_bear_minute_wait(
                            context=context,
                            symbol=TARGET_SYMBOL,
                            cur_min_key=dt_re_m.strftime("%Y-%m-%d %H:%M"),
                        )
                        await context.ledger.update_state(
                            TARGET_SYMBOL,
                            last_sub_reentry_eval_ts=0.0,
                        )
                        return {
                            "status": "SUB_L2_ONLY_PULLBACK_SHAVED_HA_BEAR_BLOCKED",
                            "signal_type": (
                                "HOLD_LOW_BREAK_SHAVED_HA_BEAR"
                                if sub_sig_type == "LOW_BREAK_RELOAD"
                                else "HOLD_PULLBACK_SHAVED_HA_BEAR"
                            ),
                            "closed_ha_shaved_bear": m_sub_shaved_bear,
                            "closed_ha_bull": m_sub_ha_bull,
                        }
                    m_sub_lb_ceil = (
                        m_sub_c_min * 1.005 if m_use_sub_stalk else m_sub_c_min
                    )
                    if (
                        sub_sig_type == "LOW_BREAK_RELOAD"
                        and (
                            m_sub_c_min <= 0.0
                            or m_exec_p_chk >= (m_sub_lb_ceil - 1e-6)
                        )
                    ):
                        sub_re_epoch = mark_sub_reentry_monitor_60s_cycle_shield(
                            context=context,
                            symbol=TARGET_SYMBOL,
                            eval_price=fresh_live_p,
                        )
                        await context.ledger.update_state(
                            TARGET_SYMBOL,
                            last_sub_reentry_eval_ts=sub_re_epoch,
                        )
                        return {
                            "status": "SUB_L2_ONLY_LOW_BREAK_REBOUNDED",
                            "signal_type": "HOLD_ABOVE_CYCLE_MIN",
                        }
                    # MODIFIED [Audit-111-02]: sub_anchor_price=0.0 시 상단 최저단가 폴백 보장
                    m_spm = str(st_now.get("portion_mode") or "")
                    raw_m_sanc = safe_float(st_now.get("sub_anchor_price"), 0.0)
                    m_sanc = (
                        raw_m_sanc
                        if raw_m_sanc > 0.0
                        else min(sb.book_price for sb in now_sub_buckets)
                    )
                    # MODIFIED [Audit-112-01]: 서브 스토커 발사 시 기준가 미만 정당 반등 보호 (모드 전환으로 스토커 OFF 시 정식 눌림폭 강제)
                    m_spb = resolve_smart_pullback_drop_pct(m_spm)
                    m_was_sub_stalk = bool(
                        m_use_sub_stalk
                        and (
                            cur_stalk_sub_act
                            or bool(st_now.get("stalk_sub_active", False))
                        )
                    )
                    m_spb_lim = -0.01 if m_was_sub_stalk else m_spb
                    if (
                        sub_sig_type == "PULLBACK_RELOAD"
                        and m_sanc > 0.0
                        and ((fresh_live_p - m_sanc) / m_sanc * 100.0)
                        > (m_spb_lim + 1e-6)
                    ):
                        s_ep = mark_sub_reentry_monitor_60s_cycle_shield(
                            context=context,
                            symbol=TARGET_SYMBOL,
                            eval_price=fresh_live_p,
                        )
                        await context.ledger.update_state(
                            TARGET_SYMBOL, last_sub_reentry_eval_ts=s_ep
                        )
                        return {
                            "status": "SUB_PULLBACK_MODE_SHIFT_HOLD",
                            "signal_type": "HOLD_WAIT_GATE",
                        }
                    if (
                        sub_sig_type == "PULLBACK_RELOAD"
                        and m_sub_vwap > 0.0
                        and fresh_live_p > (m_sub_vwap + 1e-6)
                    ):
                        sub_re_epoch = mark_sub_reentry_monitor_60s_cycle_shield(
                            context=context,
                            symbol=TARGET_SYMBOL,
                            eval_price=fresh_live_p,
                        )
                        await context.ledger.update_state(
                            TARGET_SYMBOL,
                            last_sub_reentry_eval_ts=sub_re_epoch,
                        )
                        return {
                            "status": "SUB_L2_ONLY_PULLBACK_VWAP_BLOCKED",
                            "signal_type": "HOLD_PULLBACK_ABOVE_SESSION_VWAP",
                            "session_vwap": m_sub_vwap,
                        }

                sub_min_upper_p = min(sb.book_price for sb in now_sub_buckets)
                exec_order_p = max(
                    0.01, math.floor((fresh_live_p + 1e-9) * 100.0) / 100.0
                )
                if sub_min_upper_p > 0.0 and exec_order_p > (
                    sub_min_upper_p + 1e-6
                ):
                    sub_re_epoch = mark_sub_reentry_monitor_60s_cycle_shield(
                        context=context,
                        symbol=TARGET_SYMBOL,
                        eval_price=fresh_live_p,
                    )
                    await context.ledger.update_state(
                        TARGET_SYMBOL,
                        last_sub_reentry_eval_ts=sub_re_epoch,
                    )
                    return {
                        "status": "SUB_L2_ONLY_INVERSION_BLOCKED",
                        "signal_type": "HOLD_PREVENT_INVERSION",
                    }

                eff_rt_pct_re = resolve_effective_round_trip_fee_rate_pct(
                    state_dict=st_now
                )
                fee_mult_re = 1.0 + (eff_rt_pct_re / 100.0)
                now_free_cash = max(
                    0.0, safe_float(st_now.get("free_cash_usd"), 0.0)
                )
                now_init_seed = max(
                    100.0,
                    safe_float(
                        st_now.get("initial_seed_usd"),
                        DEFAULT_INITIAL_SEED_USD,
                    ),
                )
                now_inj_res = max(
                    0.0, safe_float(st_now.get("injected_reserve_usd"), 0.0)
                )
                now_inv_tot = sum(b.actual_cost_usd for b in now_buckets) + sum(
                    sb.actual_cost_usd for sb in now_sub_buckets
                )
                now_core_eq = max(
                    now_init_seed, (now_free_cash + now_inv_tot) - now_inj_res
                )
                now_p_mode = (
                    str(st_now.get("portion_mode") or PORTION_MODE_COMPOUND)
                    .upper()
                    .strip()
                )

                raw_bp_re = await context.api.get_buying_power_usd(
                    safety_buffer_pct=0.2
                )
                if raw_bp_re <= 0.0 and now_free_cash >= (
                    exec_order_p * fee_mult_re
                ):
                    await asyncio.sleep(0.25)
                    raw_bp_re = await context.api.get_buying_power_usd(
                        safety_buffer_pct=0.2
                    )
                    if raw_bp_re <= 0.0:
                        return {"status": "HOLD_SUB_TRANSIENT_BP_API_ERROR"}

                masked_bp_re = _resolve_masked_bp_for_soxl_sub_or_topup(
                    context, st_now, raw_bp_re
                )
                idle_re = compute_sub_grid_available_idle_cash(
                    free_cash_usd=now_free_cash,
                    core_equity_usd=now_core_eq,
                    broker_buying_power_usd=masked_bp_re,
                    reserve_main_portions=SUB_RESERVE_MAIN_PORTIONS,
                    initial_seed_usd=now_init_seed,
                    portion_mode=now_p_mode,
                )
                avail_idle_re = safe_float(
                    idle_re.get("avail_idle_cash_usd"), 0.0
                )
                quota_ref_p = max(
                    0.01,
                    safe_float(
                        sub_re_sig.get("quota_ref_price"),
                        safe_float(
                            sub_re_sig.get("ref_anchor"),
                            sub_anchor_p if sub_anchor_p > 0.0 else exec_order_p,
                        ),
                    ),
                )
                sub_target_qty, sub_p_bud = compute_sub4_quota_qty(
                    sub_anchor_price=quota_ref_p,
                    current_core_equity=now_core_eq,
                    initial_seed_usd=now_init_seed,
                    exec_price=exec_order_p,
                    portion_mode=now_p_mode,
                )
                min_req_sub_re = max(
                    exec_order_p * fee_mult_re,
                    sub_p_bud * MIN_DIP_BUDGET_RATIO,
                )
                if avail_idle_re < min_req_sub_re:
                    sub_re_epoch = mark_sub_reentry_monitor_60s_cycle_shield(
                        context=context,
                        symbol=TARGET_SYMBOL,
                        eval_price=exec_order_p,
                    )
                    await context.ledger.update_state(
                        TARGET_SYMBOL,
                        last_sub_reentry_eval_ts=sub_re_epoch,
                    )
                    return {"status": "HOLD_SUB_REENTRY_NO_IDLE_CASH"}

                buy_qty_sub, _ = resolve_affordable_buy_qty(
                    target_qty=sub_target_qty,
                    price_t=exec_order_p,
                    free_cash_usd=avail_idle_re,
                    broker_buying_power_usd=avail_idle_re,
                    max_portion_budget_usd=sub_p_bud,
                    round_trip_fee_rate_pct=eff_rt_pct_re,
                )
                if buy_qty_sub <= 0:
                    sub_re_epoch = mark_sub_reentry_monitor_60s_cycle_shield(
                        context=context,
                        symbol=TARGET_SYMBOL,
                        eval_price=exec_order_p,
                    )
                    await context.ledger.update_state(
                        TARGET_SYMBOL,
                        last_sub_reentry_eval_ts=sub_re_epoch,
                    )
                    return {"status": "HOLD_SUB_REENTRY_ZERO_QTY"}

                sub_re_epoch = mark_sub_reentry_monitor_60s_cycle_shield(
                    context=context,
                    symbol=TARGET_SYMBOL,
                    eval_price=exec_order_p,
                )
                pending_sub_lot_tag = (
                    "SUB_REENTRY_1FL_BREAKOUT"
                    if sub_sig_type == "BREAKOUT_RELOAD"
                    else (
                        "SUB_REENTRY_1FL_LOW_BREAK"
                        if sub_sig_type == "LOW_BREAK_RELOAD"
                        else "SUB_REENTRY_1FL"
                    )
                )
                cid = generate_client_order_id(prefix="SRE1FL")
                try:
                    ord_res = await context.api.create_order(
                        symbol=TARGET_SYMBOL,
                        side="BUY",
                        quantity=buy_qty_sub,
                        price=exec_order_p,
                        order_type="LIMIT",
                        time_in_force="DAY",
                        client_order_id=cid,
                        enforce_daymarket_block=True,
                    )
                except Exception as exc:
                    await context.ledger.update_state(
                        TARGET_SYMBOL, last_sub_reentry_eval_ts=sub_re_epoch
                    )
                    logger.warning(
                        "Case 88 서브그리드 1층 공석 재장전 주문 예외: %s",
                        exc,
                    )
                    return {"status": "SUB_ORDER_ERROR", "error": str(exc)}

                oid = str(ord_res.get("orderId") or "").strip()
                await context.ledger.update_state(
                    TARGET_SYMBOL,
                    sub_l1_target_quota_qty=buy_qty_sub,
                    buy_order_id=oid,
                    client_order_id=cid,
                    ordered_qty=buy_qty_sub,
                    buy_price=exec_order_p,
                    pending_portion_budget=sub_p_bud,
                    pending_lot_type=pending_sub_lot_tag,
                    pending_step_up_min_price=0.0,
                    pending_sub_step_up_min_price=0.0,
                    last_modify_mono=time.monotonic(),
                    last_sub_reentry_eval_ts=sub_re_epoch,
                )
                context.wakeup_event.set()
                logger.info(
                    "🛡️ [Case 88/92 SOXL 서브그리드 상단 %d개층 보유 중 60초 주기 서브 1층 재장전(%s · RSI=%.1f) 발주] %d주 @ 지정가 $%.2f <= 서브2층상한 $%.2f (4%%예산 $%.2f · orderId=%s)",
                    len(now_sub_buckets),
                    sub_sig_type,
                    live_rsi_14,
                    buy_qty_sub,
                    exec_order_p,
                    sub_min_upper_p,
                    sub_p_bud,
                    oid,
                )
                return {
                    "status": "SUB_L2_HELD_HYBRID_1FL_ORDERED",
                    "signal_type": sub_sig_type,
                    "rsi_14": live_rsi_14,
                    "orderId": oid,
                    "qty": buy_qty_sub,
                    "price": exec_order_p,
                }

    if not sub_buckets or not has_sub_active_l1:
        return None

    # -----------------------------------------------------------------------
    # [서브 분기 S-B0 · Case 78 & Case 88 : 서브 활성 1층 부분 체결 잔량(sub_rem_quota_qty > 0) 존재 시 1.5초 모니터]
    # -----------------------------------------------------------------------
    sub_l1_target_q = max(
        sub_buckets[0].qty, safe_int(st.get("sub_l1_target_quota_qty"), 0)
    )
    sub_rem_quota_qty = max(0, sub_l1_target_q - sub_buckets[0].qty)
    sub_l1_book_p = round(sub_buckets[0].book_price, 2)

    if sub_rem_quota_qty > 0 and live_p <= (sub_l1_book_p + 1e-6):
        in_sub_top_sh, _ = is_within_sub_reentry_monitor_time_shield(
            context, st, TARGET_SYMBOL
        )
        if not in_sub_top_sh and avail_idle_ledger >= (live_p * fee_mult):
            async with context.in_memory_ordering_lock:
                async with context.dual_strike_mutex:
                    st_now = context.ledger.get_state(TARGET_SYMBOL)
                    if str(st_now.get("buy_order_id") or "").strip() or str(
                        st_now.get("sell_order_id") or ""
                    ).strip():
                        return {"status": "ALREADY_ORDERING_IN_MUTEX"}

                    in_s_sh, _ = is_within_post_sell_time_shield(
                        context, st_now, TARGET_SYMBOL
                    )
                    in_b_sh, _ = is_within_post_buy_time_shield(
                        context, st_now, TARGET_SYMBOL
                    )
                    in_sub_top_m, _ = is_within_sub_reentry_monitor_time_shield(
                        context, st_now, TARGET_SYMBOL
                    )
                    if in_s_sh or in_b_sh or in_sub_top_m:
                        return {"status": "HOLD_60S_TIME_SHIELD_IN_MUTEX"}

                    now_buckets = buckets_from_dicts(st_now.get("buckets", []))
                    now_sub_buckets = buckets_from_dicts(
                        st_now.get("sub_buckets", [])
                    )
                    if (
                        not now_buckets
                        or not now_sub_buckets
                        or not has_active_l1_bucket(now_sub_buckets)
                    ):
                        return {"status": "SUB_L1_STATE_CHANGED_IN_MUTEX"}

                    now_sub_target_q = max(
                        now_sub_buckets[0].qty,
                        safe_int(st_now.get("sub_l1_target_quota_qty"), 0),
                    )
                    now_sub_rem_q = max(
                        0, now_sub_target_q - now_sub_buckets[0].qty
                    )
                    now_sub_l1_book_p = round(now_sub_buckets[0].book_price, 2)

                    if now_sub_rem_q > 0:
                        fresh_live_p = await _fetch_fresh_current_soxl_price(
                            context, fallback_price=live_p
                        )
                        if fresh_live_p > 0.0 and fresh_live_p <= (
                            now_sub_l1_book_p + 1e-6
                        ):
                            eff_rt_pct_top = (
                                resolve_effective_round_trip_fee_rate_pct(
                                    state_dict=st_now
                                )
                            )
                            fee_mult_top = 1.0 + (eff_rt_pct_top / 100.0)
                            cur_lim_p = (
                                math.floor((fresh_live_p + 1e-9) * 100.0)
                                / 100.0
                            )
                            exec_order_p = max(
                                0.01, min(cur_lim_p, now_sub_l1_book_p)
                            )
                            sub_topup_budget = round(
                                float(now_sub_rem_q) * now_sub_l1_book_p, 4
                            )
                            now_free_cash = max(
                                0.0, safe_float(st_now.get("free_cash_usd"), 0.0)
                            )
                            now_init_seed = max(
                                100.0,
                                safe_float(
                                    st_now.get("initial_seed_usd"),
                                    DEFAULT_INITIAL_SEED_USD,
                                ),
                            )
                            now_inj_res = max(
                                0.0,
                                safe_float(
                                    st_now.get("injected_reserve_usd"), 0.0
                                ),
                            )
                            now_inv_tot = sum(
                                b.actual_cost_usd for b in now_buckets
                            ) + sum(
                                sb.actual_cost_usd for sb in now_sub_buckets
                            )
                            now_core_eq = max(
                                now_init_seed,
                                (now_free_cash + now_inv_tot) - now_inj_res,
                            )
                            now_p_mode = (
                                str(
                                    st_now.get("portion_mode")
                                    or PORTION_MODE_COMPOUND
                                )
                                .upper()
                                .strip()
                            )
                            raw_bp_top = await context.api.get_buying_power_usd(
                                safety_buffer_pct=0.2
                            )
                            if raw_bp_top <= 0.0 and now_free_cash >= (
                                exec_order_p * fee_mult_top
                            ):
                                await asyncio.sleep(0.25)
                                raw_bp_top = (
                                    await context.api.get_buying_power_usd(
                                        safety_buffer_pct=0.2
                                    )
                                )
                                if raw_bp_top <= 0.0:
                                    return {
                                        "status": "HOLD_SUB_TRANSIENT_BP_API_ERROR"
                                    }
                            masked_bp_top = (
                                _resolve_masked_bp_for_soxl_sub_or_topup(
                                    context, st_now, raw_bp_top
                                )
                            )
                            idle_top = compute_sub_grid_available_idle_cash(
                                free_cash_usd=now_free_cash,
                                core_equity_usd=now_core_eq,
                                broker_buying_power_usd=masked_bp_top,
                                reserve_main_portions=SUB_RESERVE_MAIN_PORTIONS,
                                initial_seed_usd=now_init_seed,
                                portion_mode=now_p_mode,
                            )
                            avail_idle_top = safe_float(
                                idle_top.get("avail_idle_cash_usd"), 0.0
                            )
                            buy_qty_sub_top, _ = resolve_affordable_buy_qty(
                                target_qty=now_sub_rem_q,
                                price_t=exec_order_p,
                                free_cash_usd=avail_idle_top,
                                broker_buying_power_usd=avail_idle_top,
                                max_portion_budget_usd=sub_topup_budget,
                                round_trip_fee_rate_pct=eff_rt_pct_top,
                            )
                            if buy_qty_sub_top > 0:
                                eff_sub_top_bud = round(
                                    float(buy_qty_sub_top) * now_sub_l1_book_p,
                                    4,
                                )
                                cid = generate_client_order_id(prefix="STOP1F")
                                try:
                                    ord_res = await context.api.create_order(
                                        symbol=TARGET_SYMBOL,
                                        side="BUY",
                                        quantity=buy_qty_sub_top,
                                        price=exec_order_p,
                                        order_type="LIMIT",
                                        time_in_force="DAY",
                                        client_order_id=cid,
                                        enforce_daymarket_block=True,
                                    )
                                    oid = str(
                                        ord_res.get("orderId") or ""
                                    ).strip()
                                    await context.ledger.update_state(
                                        TARGET_SYMBOL,
                                        sub_l1_target_quota_qty=now_sub_target_q,
                                        buy_order_id=oid,
                                        client_order_id=cid,
                                        ordered_qty=buy_qty_sub_top,
                                        buy_price=exec_order_p,
                                        pending_portion_budget=eff_sub_top_bud,
                                        pending_lot_type="SUB_TOPUP_1FL",
                                        pending_step_up_min_price=0.0,
                                        pending_sub_step_up_min_price=0.0,
                                        last_modify_mono=time.monotonic(),
                                    )
                                    context.wakeup_event.set()
                                    logger.info(
                                        "🎯 [Case 78/88 SOXL 서브 1층 단가($%.2f) 재도래 -> 서브 미체결 잔량(SUB_TOPUP_1FL) 발주] +%d주 @ 지정가 $%.2f (orderId=%s)",
                                        now_sub_l1_book_p,
                                        buy_qty_sub_top,
                                        exec_order_p,
                                        oid,
                                    )
                                    return {
                                        "status": "SUB_L1_PARTIAL_TOPUP_ORDERED",
                                        "orderId": oid,
                                        "qty": buy_qty_sub_top,
                                        "price": exec_order_p,
                                    }
                                except Exception as exc:
                                    mark_sub_reentry_monitor_60s_cycle_shield(
                                        context=context,
                                        symbol=TARGET_SYMBOL,
                                        eval_price=exec_order_p,
                                    )
                                    logger.debug(
                                        "서브 1층 잔량(SUB_TOPUP_1FL) 주문 예외(60초 쿨다운): %s",
                                        exc,
                                    )
                            else:
                                mark_sub_reentry_monitor_60s_cycle_shield(
                                    context=context,
                                    symbol=TARGET_SYMBOL,
                                    eval_price=exec_order_p,
                                )

    # -----------------------------------------------------------------------
    # [서브 분기 S-B2 · Case 88 : 서브 활성 1층 보유 중 10분 고정 매수 게이트 (4단 와이드 신저가 무필터 OR 10영업일/-10% 저가해금)]
    # -----------------------------------------------------------------------
    if sub_cur_total_lots >= sub_max_lots_cap:
        return {
            "status": "HOLD_SUB_CAP_4_LOTS_REACHED",
            "sub_cur_total_lots": sub_cur_total_lots,
            "sub_max_total_lots": sub_max_lots_cap,
        }

    sub_gate_open, sub_cur_bucket_id, sub_today_str, _ = (
        evaluate_buy_gate_bucket_status(
            now_est=eff_dt_now,
            buy_interval_min=LOCKED_BUY_INTERVAL_MIN,
            last_evaluated_bucket_id=safe_int(
                st.get("sub_last_evaluated_buy_bucket_id"), -1
            ),
            last_evaluated_date=str(st.get("sub_last_evaluated_date") or ""),
        )
    )
    if not sub_gate_open:
        return None

    # NEW [충돌-02 방어]: 본대 VWAP 폭락 브레이커 구간에서는 서브 S-B2 추매도 완결 반전봉 확인 전까지 유예(버킷 보존)
    sub_dip_pol = resolve_smart_rebound_policy(portion_mode)
    sub_vwap_g_pct = safe_float(sub_dip_pol.get("vwap_crash_guard_pct"), 0.0)
    if sub_vwap_g_pct < -0.1:
        sub_dip_vwap = _get_cached_soxl_session_vwap(
            context, live_price=live_p, now_est=eff_dt_now
        )
        in_sub_vwap_crash = bool(
            bool(st.get("stalk_add_active", False))
            or (
                sub_dip_vwap > 0.0
                and live_p <= sub_dip_vwap * (1.0 + sub_vwap_g_pct / 100.0)
            )
        )
        if in_sub_vwap_crash:
            sub_dip_snap = _get_live_soxl_stalker_bar_snapshot(
                context, live_price=live_p, now_est=eff_dt_now
            )
            if not (
                bool(sub_dip_snap.get("closed_ha_ready"))
                and bool(sub_dip_snap.get("closed_real_reversal"))
                and live_p >= safe_float(sub_dip_snap.get("cur_bar_open"), live_p) - 1e-9
            ):
                return {
                    "status": "SUB_DIP_HOLD_VWAP_CRASH_GUARD",
                    "live_price": live_p,
                    "session_vwap": sub_dip_vwap,
                }

    fresh_live_p = await _fetch_fresh_current_soxl_price(
        context, fallback_price=live_p
    )
    if fresh_live_p <= 0.0:
        return None

    sub_ratchet_lots = max(
        sub_cur_total_lots, safe_int(st.get("sub_ratchet_max_lots"), 0)
    )
    threshold_mode = str(st.get("threshold_mode") or "WIDE_RUNWAY").upper()
    sub_drop_pct, _, _ = get_golden8_prog_thresholds(
        held_lots=sub_cur_total_lots,
        threshold_mode=threshold_mode,
        cycle_ratchet_max_lots=sub_ratchet_lots,
    )
    sub_anchor_p = safe_float(
        st.get("sub_anchor_price"), sub_buckets[0].book_price
    )
    sub_cycle_min_p = safe_float(
        st.get("sub_cycle_min_buy_price"), sub_anchor_p
    )
    sub_frozen_d = max(0, safe_int(st.get("sub_consec_frozen_days"), 0))

    sub_dip_eval = evaluate_sub_grid_dip_signal(
        live_price=fresh_live_p,
        sub_buckets=sub_buckets,
        sub_anchor_price=sub_anchor_p,
        sub_cycle_min_buy_price=sub_cycle_min_p,
        sub_drop_buy_pct=sub_drop_pct,
        sub_consec_frozen_days=sub_frozen_d,
        sub_max_total_lots=sub_max_lots_cap,
    )
    if not bool(sub_dip_eval.get("should_buy")):
        await context.ledger.update_state(
            TARGET_SYMBOL,
            sub_last_evaluated_buy_bucket_id=sub_cur_bucket_id,
            sub_last_evaluated_date=sub_today_str,
        )
        return {
            "status": "SUB_GATE_HOLD_PASSED",
            "trigger_tag": sub_dip_eval.get("trigger_tag"),
            "sub_cur_total_lots": sub_cur_total_lots,
        }

    async with context.in_memory_ordering_lock:
        async with context.dual_strike_mutex:
            st_now = context.ledger.get_state(TARGET_SYMBOL)
            if str(st_now.get("buy_order_id") or "").strip() or str(
                st_now.get("sell_order_id") or ""
            ).strip():
                return {"status": "ALREADY_ORDERING_IN_MUTEX"}

            in_s_sh, _ = is_within_post_sell_time_shield(
                context, st_now, TARGET_SYMBOL
            )
            in_b_sh, _ = is_within_post_buy_time_shield(
                context, st_now, TARGET_SYMBOL
            )
            if in_s_sh or in_b_sh:
                return {"status": "HOLD_60S_TIME_SHIELD_IN_MUTEX"}

            now_buckets = buckets_from_dicts(st_now.get("buckets", []))
            now_sub_buckets = buckets_from_dicts(st_now.get("sub_buckets", []))
            if (
                not now_buckets
                or not now_sub_buckets
                or not has_active_l1_bucket(now_sub_buckets)
            ):
                return {"status": "SUB_L1_STATE_CHANGED_IN_MUTEX"}

            now_sub_lots = sum(max(1, sb.lot_count) for sb in now_sub_buckets)
            if now_sub_lots >= sub_max_lots_cap:
                return {"status": "HOLD_SUB_CAP_4_LOTS_REACHED"}

            sub_gate_m, _, _, _ = evaluate_buy_gate_bucket_status(
                now_est=eff_dt_now,
                buy_interval_min=LOCKED_BUY_INTERVAL_MIN,
                last_evaluated_bucket_id=safe_int(
                    st_now.get("sub_last_evaluated_buy_bucket_id"), -1
                ),
                last_evaluated_date=str(
                    st_now.get("sub_last_evaluated_date") or ""
                ),
            )
            if not sub_gate_m:
                return {"status": "SUB_BUCKET_ALREADY_EVALUATED_IN_MUTEX"}

            now_sub_ratchet = max(
                now_sub_lots, safe_int(st_now.get("sub_ratchet_max_lots"), 0)
            )
            now_sub_drop, _, _ = get_golden8_prog_thresholds(
                held_lots=now_sub_lots,
                threshold_mode=threshold_mode,
                cycle_ratchet_max_lots=now_sub_ratchet,
            )
            now_sub_anc = safe_float(
                st_now.get("sub_anchor_price"), now_sub_buckets[0].book_price
            )
            now_sub_min_p = safe_float(
                st_now.get("sub_cycle_min_buy_price"), now_sub_anc
            )
            now_sub_frozen = max(
                0, safe_int(st_now.get("sub_consec_frozen_days"), 0)
            )

            now_sub_dip_eval = evaluate_sub_grid_dip_signal(
                live_price=fresh_live_p,
                sub_buckets=now_sub_buckets,
                sub_anchor_price=now_sub_anc,
                sub_cycle_min_buy_price=now_sub_min_p,
                sub_drop_buy_pct=now_sub_drop,
                sub_consec_frozen_days=now_sub_frozen,
                sub_max_total_lots=sub_max_lots_cap,
            )
            if not bool(now_sub_dip_eval.get("should_buy")):
                return {"status": "SUB_DIP_SIGNAL_CHANGED_IN_MUTEX"}

            is_sub_unlock = bool(now_sub_dip_eval.get("is_sub_unlock", False))
            sub_trig_tag = str(
                now_sub_dip_eval.get("trigger_tag") or "SUB_STATIC_NEW_LOW"
            )
            sub_ref_static = safe_float(
                now_sub_dip_eval.get("ref_static_anchor"),
                now_sub_buckets[0].book_price,
            )
            sub_quota_ref_p = max(
                0.01,
                safe_float(
                    now_sub_dip_eval.get("quota_ref_price"), sub_ref_static
                ),
            )
            sub_stepped_min_p = safe_float(
                now_sub_dip_eval.get("sub_stepped_min_price"), 0.0
            )

            if is_sub_unlock and sub_stepped_min_p > 0.0:
                max_sub_trig_p = (
                    math.floor((sub_stepped_min_p + 1e-9) * 100.0) / 100.0
                )
            else:
                max_sub_trig_p = (
                    math.floor(
                        (
                            sub_ref_static * (1.0 + now_sub_drop / 100.0)
                            + 1e-9
                        )
                        * 100.0
                    )
                    / 100.0
                )
            cur_limit_p = math.floor((fresh_live_p + 1e-9) * 100.0) / 100.0
            exec_order_p = max(0.01, min(cur_limit_p, max_sub_trig_p))

            eff_rt_pct_dip = resolve_effective_round_trip_fee_rate_pct(
                state_dict=st_now
            )
            fee_mult_dip = 1.0 + (eff_rt_pct_dip / 100.0)
            now_free_cash = max(
                0.0, safe_float(st_now.get("free_cash_usd"), 0.0)
            )
            now_init_seed = max(
                100.0,
                safe_float(
                    st_now.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD
                ),
            )
            now_inj_res = max(
                0.0, safe_float(st_now.get("injected_reserve_usd"), 0.0)
            )
            now_inv_tot = sum(b.actual_cost_usd for b in now_buckets) + sum(
                sb.actual_cost_usd for sb in now_sub_buckets
            )
            now_core_eq = max(
                now_init_seed, (now_free_cash + now_inv_tot) - now_inj_res
            )
            now_p_mode = (
                str(st_now.get("portion_mode") or PORTION_MODE_COMPOUND)
                .upper()
                .strip()
            )

            raw_bp_dip = await context.api.get_buying_power_usd(
                safety_buffer_pct=0.2
            )
            if raw_bp_dip <= 0.0 and now_free_cash >= (
                exec_order_p * fee_mult_dip
            ):
                await asyncio.sleep(0.25)
                raw_bp_dip = await context.api.get_buying_power_usd(
                    safety_buffer_pct=0.2
                )
                if raw_bp_dip <= 0.0:
                    return {"status": "HOLD_SUB_TRANSIENT_BP_API_ERROR"}

            masked_bp_dip = _resolve_masked_bp_for_soxl_sub_or_topup(
                context, st_now, raw_bp_dip
            )
            idle_dip = compute_sub_grid_available_idle_cash(
                free_cash_usd=now_free_cash,
                core_equity_usd=now_core_eq,
                broker_buying_power_usd=masked_bp_dip,
                reserve_main_portions=SUB_RESERVE_MAIN_PORTIONS,
                initial_seed_usd=now_init_seed,
                portion_mode=now_p_mode,
            )
            avail_idle_dip = safe_float(
                idle_dip.get("avail_idle_cash_usd"), 0.0
            )
            sub_target_qty, sub_p_bud = compute_sub4_quota_qty(
                sub_anchor_price=sub_quota_ref_p,
                current_core_equity=now_core_eq,
                initial_seed_usd=now_init_seed,
                exec_price=exec_order_p,
                portion_mode=now_p_mode,
            )
            min_req_sub_dip = max(
                exec_order_p * fee_mult_dip,
                sub_p_bud * MIN_DIP_BUDGET_RATIO,
                now_sub_buckets[0].actual_cost_usd * MIN_DIP_VS_L1_RATIO,
            )
            if avail_idle_dip < min_req_sub_dip:
                await context.ledger.update_state(
                    TARGET_SYMBOL,
                    sub_last_evaluated_buy_bucket_id=sub_cur_bucket_id,
                    sub_last_evaluated_date=sub_today_str,
                )
                return {
                    "status": "HOLD_SUB_DIP_INSUFFICIENT_IDLE_CASH",
                    "avail_idle_cash_usd": avail_idle_dip,
                }

            buy_qty_sub, _ = resolve_affordable_buy_qty(
                target_qty=sub_target_qty,
                price_t=exec_order_p,
                free_cash_usd=avail_idle_dip,
                broker_buying_power_usd=avail_idle_dip,
                max_portion_budget_usd=sub_p_bud,
                round_trip_fee_rate_pct=eff_rt_pct_dip,
            )
            if buy_qty_sub <= 0:
                await context.ledger.update_state(
                    TARGET_SYMBOL,
                    sub_last_evaluated_buy_bucket_id=sub_cur_bucket_id,
                    sub_last_evaluated_date=sub_today_str,
                )
                return {"status": "HOLD_SUB_DIP_ZERO_QTY"}

            cid_prefix = (
                f"SU{now_sub_lots + 1}L"
                if is_sub_unlock
                else f"SB{now_sub_lots + 1}L"
            )
            cid = generate_client_order_id(prefix=cid_prefix)
            try:
                ord_res = await context.api.create_order(
                    symbol=TARGET_SYMBOL,
                    side="BUY",
                    quantity=buy_qty_sub,
                    price=exec_order_p,
                    order_type="LIMIT",
                    time_in_force="DAY",
                    client_order_id=cid,
                    enforce_daymarket_block=True,
                )
            except Exception as exc:
                await context.ledger.update_state(
                    TARGET_SYMBOL,
                    sub_last_evaluated_buy_bucket_id=sub_cur_bucket_id,
                    sub_last_evaluated_date=sub_today_str,
                )
                logger.warning(
                    "Case 88 서브그리드 10분 게이트(%s) 추매 주문 예외: %s",
                    sub_trig_tag,
                    exc,
                )
                return {"status": "SUB_BUY_ORDER_ERROR", "error": str(exc)}

            oid = str(ord_res.get("orderId") or "").strip()
            await context.ledger.update_state(
                TARGET_SYMBOL,
                buy_order_id=oid,
                client_order_id=cid,
                ordered_qty=buy_qty_sub,
                buy_price=exec_order_p,
                pending_portion_budget=sub_p_bud,
                pending_lot_type="SUB_DIP_1FL",
                pending_step_up_min_price=0.0,
                pending_sub_step_up_min_price=(
                    round(sub_stepped_min_p, 4) if is_sub_unlock else 0.0
                ),
                sub_last_evaluated_buy_bucket_id=sub_cur_bucket_id,
                sub_last_evaluated_date=sub_today_str,
                last_modify_mono=time.monotonic(),
            )
            context.wakeup_event.set()
            logger.info(
                "🛡️ [Case 88 SOXL 3층 서브그리드 %d/%d회분(%s) 추매 발주] %d주 @ 지정가 $%.2f (4%%예산 $%.2f · 유휴현금 $%.2f · orderId=%s)",
                now_sub_lots + 1,
                sub_max_lots_cap,
                sub_trig_tag,
                buy_qty_sub,
                exec_order_p,
                sub_p_bud,
                avail_idle_dip,
                oid,
            )
            return {
                "status": "SUB_QUOTA_DIP_BUY_ORDERED",
                "trigger_tag": sub_trig_tag,
                "is_sub_unlock": is_sub_unlock,
                "orderId": oid,
                "qty": buy_qty_sub,
                "price": exec_order_p,
                "sub_cur_total_lots": now_sub_lots,
            }
# -*- coding: utf-8 -*-
"""
# MODIFIED: sniper_plugin.py (Part 2/2 — execute_seed_protected_buy_gate_plugin 의 holdings·prices 선택 인자 안전 기본값 및 context 자동 복원 방어벽 장착 · 15:30 0주/돌파 차단 · 1층 공석 +1.0% 돌파 RSI(14) <= 50.0 필터 · GUARD30 무제한 예비수혈 · STEP2X 스텝업 해금 · Default-ON 3층 서브 그리드 연속 가동 · Case 01 ~ Case 93 완비)
"""


# ---------------------------------------------------------------------------
# [핵심 2] 진화 챔피언 (👑 06_L2L7_RATCHET_8PCT × 🛡️ 13_SUB_L1L3_RESV05_CAP4L[Default ON] × 💉 무제한 예비수혈 × 🔓 06_STEP2X_15PCT_C20 × 🛡️ Case 84 × 🔹 Case 92 돌파 RSI<=50 × 💵 Case 91 복리/단리 연동) : 비대칭 매수 타격 엔진
#  - 분기 A   : 본 그리드 0주 상태(사이클 종료) -> 15:30 ~ 16:00 EST 구간에서는 새 사이클 첫 1층 진입 100% 차단(Case 84) · 그 외 60초 타임쉴드 후 첫 1층(REENTRY_1FL) 산입
#  - 분기 B-1 : 본 그리드 상단 2~7층 보유 중 1층 공석 -> 매 60.0초(1분) 주기 재장전 모니터 & 2층 단가 상한(Case 73) 하에서
#               -1.00% 눌림목(PULLBACK_RELOAD · 무필터 · 04:07 ~ 16:00 EST 전 구간 허용) 및
#               +1.00% 상승돌파(BREAKOUT_RELOAD · 1분봉 Wilder RSI(14) <= 50.0 필터 결합[Case 92] · 04:07 ~ 15:29 EST 허용 / 15:30 ~ 16:00 EST 돌파 차단[Case 84])
#               (본 그리드 대기/패스 시 Default-ON 3층 서브 그리드 엔진 연속 가동 · Case 88)
#  - 분기 B-0 : 본 그리드 활성 1층 부분체결 미체결 잔량(rem_quota_qty > 0) -> 60초 타임쉴드 후 매 1.5초 모니터에서 현재가 <= 1층 단가 도래 시 잔량(TOPUP_1FL) 발주(Case 78)
#  - 분기 B-2 : 본 그리드 활성 1층 보유 중 -> 10분 고정 게이트 & 정적 기억저가 및 최고도달회차(cycle_ratchet_max_lots · Case 87) 잠금 4단 와이드 신저가(무필터) OR STEP2X_15PCT_C20 스텝업 추매(Case 76) & GUARD30/무제한 예비수혈(Case 77, Case 91)
#               (본 그리드 대기/패스 시 Default-ON 3층 서브 그리드 엔진 연속 가동 · Case 88)
# ---------------------------------------------------------------------------
async def _try_execute_smart_primer_1sh_order(
    context: Any,
    dt_now: datetime,
    fresh_live_p: float,
    expect_vacant_l1: bool,
    buy_interval_min: int = LOCKED_BUY_INTERVAL_MIN,
    threshold_mode: str = "WIDE_RUNWAY",
    already_in_mutex: bool = False,
    ignore_bucket_gate: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    # NEW [Case 110 · 옵션 3 스마트 연동 1주 마중물 원자적 발주 실행기]:
    - expect_vacant_l1=True  : [1층: 공석] 쌍바닥 1주 구제 발주 (바벨/단리 전용 · PRIMER_1SH_VAC_L1)
    - expect_vacant_l1=False : [1층: 보유] 역산 1주 마중물 발주 (바벨/단리 만석허용 · 복리 무합병 6층↓/2층공석 · PRIMER_1SH)
    """
    async def _run_inside_mutex() -> Optional[Dict[str, Any]]:
        st_m = context.ledger.get_state(TARGET_SYMBOL)
        if str(st_m.get("buy_order_id") or "").strip() or str(
            st_m.get("sell_order_id") or ""
        ).strip():
            return None

        in_s_m, _ = is_within_post_sell_time_shield(context, st_m, TARGET_SYMBOL)
        in_b_m, _ = is_within_post_buy_time_shield(context, st_m, TARGET_SYMBOL)
        if in_s_m or in_b_m:
            return None

        now_bks = buckets_from_dicts(st_m.get("buckets", []))
        if not now_bks:
            return None
        has_l1_m = has_active_l1_bucket(now_bks)
        if expect_vacant_l1 and has_l1_m:
            return None
        if (not expect_vacant_l1) and (not has_l1_m):
            return None

        gate_ok_m, cur_bid_m, today_m, _ = evaluate_buy_gate_bucket_status(
            now_est=dt_now,
            buy_interval_min=buy_interval_min,
            last_evaluated_bucket_id=safe_int(
                st_m.get("last_evaluated_buy_bucket_id"), -1
            ),
            last_evaluated_date=str(st_m.get("last_evaluated_date") or ""),
        )
        if (not gate_ok_m) and (not ignore_bucket_gate):
            return None

        # MODIFIED [Case 98-B · Audit-110-03]: 실주문 직전 뮤텍스 내부 2차 브로커 실호가(bypass_shm_cache=True) 재검증
        live_2nd_p = await _fetch_fresh_current_soxl_price(
            context, fallback_price=fresh_live_p, now_est=dt_now
        )
        eff_primer_lp = live_2nd_p if live_2nd_p > 0.0 else fresh_live_p
        hm_m = dt_now.hour * 100 + dt_now.minute
        held_lots_m = sum(safe_bucket_lot_count(b) for b in now_bks)
        ratchet_m = max(
            held_lots_m, safe_int(st_m.get("cycle_ratchet_max_lots"), 0)
        )
        drop_pct_m, _, _ = get_golden8_prog_thresholds(
            held_lots=max(1, held_lots_m),
            threshold_mode=threshold_mode,
            cycle_ratchet_max_lots=ratchet_m,
        )
        p_mode_m = (
            str(st_m.get("portion_mode") or PORTION_MODE_COMPOUND).upper().strip()
        )
        primer_mode_m = (
            str(st_m.get("primer_1sh_mode") or PRIMER_MODE_AUTO_SMART)
            .upper()
            .strip()
        )
        anc_m = safe_float(
            st_m.get("anchor_price"),
            min(b.book_price for b in now_bks)
            if expect_vacant_l1
            else now_bks[0].book_price,
        )
        c_min_m = safe_float(st_m.get("cycle_min_buy_price"), 0.0)

        p_sig = evaluate_smart_primer_1sh_signal(
            live_price=eff_primer_lp,
            buckets=now_bks,
            anchor_price=anc_m,
            cycle_min_buy_price=c_min_m,
            drop_buy_pct=drop_pct_m,
            cycle_ratchet_max_lots=ratchet_m,
            portion_mode=p_mode_m,
            primer_1sh_mode=primer_mode_m,
            hm=hm_m,
        )
        if not bool(p_sig.get("should_buy")):
            return None

        exec_1sh_p = max(
            0.01, safe_float(p_sig.get("exec_limit_price"), eff_primer_lp)
        )
        lot_tag_1sh = str(p_sig.get("lot_type") or PRIMER_1SH_LOT_TAG)
        desc_1sh = (
            "1층공석 쌍바닥 1주 마중물 구제"
            if expect_vacant_l1
            else f"역산 {abs(drop_pct_m):.1f}%(-3.5%가드) 1주 마중물"
        )
        can_1sh, _, _, _ = await _check_and_prepare_primer_1sh_cash(
            context=context,
            st_now=st_m,
            exec_order_p=exec_1sh_p,
            is_vacant_l1_rescue=expect_vacant_l1,
            trigger_desc=desc_1sh,
        )
        if not can_1sh:
            return None

        cid_1sh = generate_client_order_id(
            prefix=("PV1S" if expect_vacant_l1 else "PM1S")
        )
        try:
            ord_1sh = await context.api.create_order(
                symbol=TARGET_SYMBOL,
                side="BUY",
                quantity=1,
                price=exec_1sh_p,
                order_type="LIMIT",
                time_in_force="DAY",
                client_order_id=cid_1sh,
                enforce_daymarket_block=True,
            )
        except Exception as exc:
            logger.warning("Case 110 1주 마중물 지정가 발주 예외: %s", exc)
            return {"status": "PRIMER_1SH_ORDER_ERROR", "error": str(exc)}

        oid_1sh = str(ord_1sh.get("orderId") or "").strip()
        upd_1sh_kw: Dict[str, Any] = {
            "l1_target_quota_qty": 1,
            "buy_order_id": oid_1sh,
            "client_order_id": cid_1sh,
            "ordered_qty": 1,
            "buy_price": exec_1sh_p,
            "pending_portion_budget": exec_1sh_p,
            "pending_lot_type": lot_tag_1sh,
            "pending_step_up_min_price": 0.0,
            "pending_sub_step_up_min_price": 0.0,
            "last_evaluated_buy_bucket_id": cur_bid_m,
            "last_evaluated_date": today_m,
            "last_modify_mono": time.monotonic(),
        }
        if expect_vacant_l1:
            upd_1sh_kw["last_reentry_eval_ts"] = (
                mark_reentry_monitor_60s_cycle_shield(
                    context=context,
                    symbol=TARGET_SYMBOL,
                    eval_price=exec_1sh_p,
                )
            )
        await context.ledger.update_state(TARGET_SYMBOL, **upd_1sh_kw)
        context.wakeup_event.set()
        logger.info(
            "🌱 [Case 110 SOXL %s 발주] +1주 @ 지정가 $%.2f (기억저가 $%.2f · 역산목표 $%.2f · 가드상한 $%.2f · 모드=%s · orderId=%s)",
            desc_1sh,
            exec_1sh_p,
            c_min_m,
            safe_float(p_sig.get("inv_target_price"), 0.0),
            safe_float(p_sig.get("gap_target_price"), 0.0),
            p_sig.get("vacancy_mode"),
            oid_1sh,
        )
        return {
            "status": "PRIMER_1SH_BUY_ORDERED",
            "signal_type": p_sig.get("signal_type"),
            "lot_type": lot_tag_1sh,
            "orderId": oid_1sh,
            "qty": 1,
            "price": exec_1sh_p,
            "trigger_price": safe_float(p_sig.get("trigger_price"), 0.0),
            "inv_target_price": safe_float(p_sig.get("inv_target_price"), 0.0),
            "vacancy_mode": p_sig.get("vacancy_mode"),
        }

    if already_in_mutex:
        return await _run_inside_mutex()
    async with context.in_memory_ordering_lock:
        async with context.dual_strike_mutex:
            return await _run_inside_mutex()


async def execute_seed_protected_buy_gate_plugin(
    context: Any,
    holdings: Optional[Dict[str, Dict[str, Any]]] = None,
    prices: Optional[Dict[str, float]] = None,
    now_est: Optional[datetime] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    🎯 1, 🎯 2, 🎯 4 & Case 25 ~ 92 (챔피언 : 👑 06_L2L7_RATCHET_8PCT × 🛡️ 13_SUB_L1L3_RESV05_CAP4L[Default ON] × 💉 무제한 예비수혈 × 🔓 06_STEP2X_15PCT_C20 × 🛡️ Case 84 × 🔹 Case 92 돌파 RSI<=50 × 💵 Case 91 복리/단리 모드 연동):
    04:07:00 ~ 16:00:00 EST 운용 구간에서 작동하는 비대칭 매수 타격 엔진.
    - holdings 또는 prices 인자가 생략되더라도 context.latest_holdings / context.latest_prices 로 자동 복원한다.
    """
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    hm = dt_now.hour * 100 + dt_now.minute

    eff_holdings = (
        holdings
        if isinstance(holdings, dict) and holdings
        else (
            getattr(context, "latest_holdings", {})
            if context is not None
            else {}
        )
    )
    eff_prices = (
        dict(prices)
        if isinstance(prices, dict) and prices
        else (
            dict(getattr(context, "latest_prices", {}))
            if context is not None
            and isinstance(getattr(context, "latest_prices", None), dict)
            else {}
        )
    )
    kw_lp = safe_float(kwargs.get("live_price"), 0.0)
    if kw_lp > 0.0 and safe_float(eff_prices.get(TARGET_SYMBOL), 0.0) <= 0.0:
        eff_prices[TARGET_SYMBOL] = kw_lp

    # 1) 미체결 매수 주문이 있으면 먼저 체결 확인 수행
    st = context.ledger.get_state(TARGET_SYMBOL)
    if str(st.get("buy_order_id") or "").strip():
        return await sync_pending_buy_order_plugin(
            context=context,
            holdings=eff_holdings,
            prices=eff_prices,
            now_est=dt_now,
        )

    # 2) 04:07 ~ 16:00 EST 운용 시간대 및 마스터 전원(is_active) 확인
    if not is_active_buy_window(hm, now_est=dt_now):
        return {"status": "OUTSIDE_TRADING_WINDOW"}

    if not bool(st.get("is_active", True)):
        return {"status": "BOT_INACTIVE"}

    # 미체결 매도 주문이 진행 중이면 매도 완료까지 대기 (동일 틱 자전거래 방지, Case 44)
    if str(st.get("sell_order_id") or "").strip():
        return {"status": "SELL_ORDER_IN_PROGRESS"}

    # 🛡️ 3) [Case 65 핵심] 매도(및 0주 싸이클 종료) 후 60.0초 타임쉴드 & 직전 매수 후 60.0초 타임쉴드 최우선 강제 검문!
    in_sell_shield, remain_sell_sec = is_within_post_sell_time_shield(
        context, st, TARGET_SYMBOL
    )
    if in_sell_shield:
        return {
            "status": "HOLD_POST_SELL_60S_TIME_SHIELD",
            "remain_shield_sec": remain_sell_sec,
        }

    in_buy_shield, remain_buy_sec = is_within_post_buy_time_shield(
        context, st, TARGET_SYMBOL
    )
    if in_buy_shield:
        return {
            "status": "HOLD_POST_BUY_60S_TIME_SHIELD",
            "remain_shield_sec": remain_buy_sec,
        }

    live_p = _get_live_soxl_price(context, eff_prices, eff_holdings, dt_now)
    if live_p <= 0.0:
        return {"status": "NO_LIVE_PRICE"}

    buckets = buckets_from_dicts(st.get("buckets", []))
    sub_buckets = buckets_from_dicts(st.get("sub_buckets", []))
    h_qty = safe_int((eff_holdings or {}).get(TARGET_SYMBOL, {}).get("qty"), 0)

    # 🛡️ 3-B) [Case 77 & Case 88] 본 그리드 시드고갈 입금 대기 중일 때 60.0초 감지 타임쉴드 검문
    # (단, 본 그리드가 입금 대기 쉴드 중이더라도 서브 그리드 미체결 잔량 보충 등 서브 엔진 작동 가능 여부를 먼저 점검)
    in_res_sh, rem_res_sec = is_within_reserve_deposit_check_shield(
        context, st, TARGET_SYMBOL
    )
    if in_res_sh:
        if buckets:
            sub_res_during_sh = await _execute_sub_grid_buy_engine_plugin(
                context=context,
                holdings=eff_holdings,
                prices=eff_prices,
                dt_now=dt_now,
                live_p=live_p,
            )
            if isinstance(sub_res_during_sh, dict) and str(
                sub_res_during_sh.get("status") or ""
            ).endswith("_ORDERED"):
                return sub_res_during_sh
        return {
            "status": "HOLD_WAITING_RESERVE_DEPOSIT_60S_SHIELD",
            "remain_shield_sec": rem_res_sec,
            "required_reserve_deposit_usd": safe_float(
                st.get("required_reserve_deposit_usd"), 0.0
            ),
        }

    eff_rt_pct = resolve_effective_round_trip_fee_rate_pct(state_dict=st)
    init_seed = max(
        100.0,
        safe_float(st.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD),
    )
    injected_reserve_usd = max(
        0.0, safe_float(st.get("injected_reserve_usd"), 0.0)
    )
    free_cash = max(0.0, safe_float(st.get("free_cash_usd"), 0.0))
    actual_invested = sum(b.actual_cost_usd for b in buckets) + sum(
        sb.actual_cost_usd for sb in sub_buckets
    )
    # Case 77, Case 88 & Case 91: 온디맨드 예비시드 수혈금(injected_reserve_usd)을 제외한 순수 코어 총자산(core_equity) 및 운용 모드 기준자산 산출
    core_equity = max(
        init_seed, (free_cash + actual_invested) - injected_reserve_usd
    )
    portion_mode = (
        str(st.get("portion_mode") or PORTION_MODE_COMPOUND).upper().strip()
    )
    budget_base_eq = resolve_portion_budget_base_equity(
        initial_seed_usd=init_seed,
        core_equity_usd=core_equity,
        portion_mode=portion_mode,
    )
    threshold_mode = str(st.get("threshold_mode") or "WIDE_RUNWAY").upper()
    unlock_mode = str(
        st.get("unlock_mode") or DEFAULT_UNLOCK_MODE
    ).upper()
    buy_interval_min = LOCKED_BUY_INTERVAL_MIN

    sub_total_sh = sum(sb.qty for sb in sub_buckets)
    is_zero_shares = bool(
        len(buckets) == 0 and (h_qty == 0 or h_qty == sub_total_sh)
    )
    has_active_l1 = has_active_l1_bucket(buckets)
    # 🚨 Case 71, Case 72 & Case 73: 본 그리드 상단에 2층 ~ 7층 그리드(GRID_L2 ~ GRID_L7)가 남아 있고 1층이 익절되어 공석인 상태!
    is_l2_only_vacant_l1 = bool(len(buckets) > 0 and not has_active_l1)

    # -----------------------------------------------------------------------
    # [분기 A : 본 그리드 보유 잔고 0주 상태 (is_zero_shares)]
    # -> 🛡️ [Case 84 핵심 방어] : 정규장 마감 30분 전(15:30 ~ 16:00 EST) 구간에서는 0주 새 사이클 첫 1층(REENTRY_1FL) 진입 100% 금지!
    # -----------------------------------------------------------------------
    if is_zero_shares:
        if is_late_regular_new_cycle_cutoff_window(hm, now_est=dt_now):
            return {
                "status": "HOLD_LATE_SESSION_NEW_CYCLE_CUTOFF",
                "hm": hm,
                "cutoff_hm": NEW_CYCLE_BUY_CUTOFF_HM,
            }
        # NEW [Case 113 : 0주 첫 1층 진입 시 정규장 개장 7분(09:30~09:36 EST) 안정화 쉴드 & 직전 완결 1분봉 무머리 HA음봉 패스]
        if REG_OPEN_VWAP_SHIELD_START_HM <= hm <= REG_OPEN_VWAP_SHIELD_END_HM:
            mark_pullback_ha_bear_minute_wait(
                context=context,
                symbol=TARGET_SYMBOL,
                cur_min_key=dt_now.strftime("%Y-%m-%d %H:%M"),
            )
            return {
                "status": "HOLD_ZERO_SHARES_REG_OPEN_7M_SHIELD",
                "hm": hm,
            }
        (
            _,
            z_shaved_bear,
            _,
            z_ha_ready,
            z_closed_mk,
        ) = await _get_live_soxl_reentry_snapshot(
            context, live_price=live_p, now_est=dt_now
        )
        if (not z_ha_ready) or z_shaved_bear:
            mark_pullback_ha_bear_minute_wait(
                context=context,
                symbol=TARGET_SYMBOL,
                cur_min_key=dt_now.strftime("%Y-%m-%d %H:%M"),
            )
            logger.info(
                "🛡️ [Case 113 0주 첫 진입 무머리 HA음봉 패스] 현재가 $%.2f · 완결봉(%s) 무머리 HA음봉 -> 다음 1분 정각 최저가 대기",
                live_p,
                z_closed_mk or "-",
            )
            return {
                "status": "HOLD_ZERO_SHARES_SHAVED_HA_BEAR",
                "live_price": live_p,
                "closed_bar_minute_key": z_closed_mk,
            }

        async with context.in_memory_ordering_lock:
            async with context.dual_strike_mutex:
                st_now = context.ledger.get_state(TARGET_SYMBOL)
                if str(st_now.get("buy_order_id") or "").strip() or str(
                    st_now.get("sell_order_id") or ""
                ).strip():
                    return {"status": "ALREADY_ORDERING_IN_MUTEX"}

                now_buckets = buckets_from_dicts(st_now.get("buckets", []))
                if len(now_buckets) > 0:
                    return {"status": "L1_ALREADY_FILLED_IN_MUTEX"}

                # [Case 84 뮤텍스 내부 2차 시각 재검문 : 15:29:59 -> 15:30:00 경계 경합 원천 차단]
                dt_mutex = (
                    now_est.astimezone(EST_TZ)
                    if now_est
                    else datetime.now(EST_TZ)
                )
                hm_mutex = dt_mutex.hour * 100 + dt_mutex.minute
                if is_late_regular_new_cycle_cutoff_window(
                    hm_mutex, now_est=dt_mutex
                ):
                    return {
                        "status": "HOLD_LATE_SESSION_NEW_CYCLE_CUTOFF",
                        "hm": hm_mutex,
                        "cutoff_hm": NEW_CYCLE_BUY_CUTOFF_HM,
                    }

                in_s_sh, rem_s = is_within_post_sell_time_shield(
                    context, st_now, TARGET_SYMBOL
                )
                if in_s_sh:
                    return {
                        "status": "HOLD_POST_SELL_60S_TIME_SHIELD_IN_MUTEX",
                        "remain_shield_sec": rem_s,
                    }

                in_b_sh, rem_b = is_within_post_buy_time_shield(
                    context, st_now, TARGET_SYMBOL
                )
                if in_b_sh:
                    return {
                        "status": "HOLD_POST_BUY_60S_TIME_SHIELD_IN_MUTEX",
                        "remain_shield_sec": rem_b,
                    }

                fresh_live_p = await _fetch_fresh_current_soxl_price(
                    context, fallback_price=live_p, now_est=dt_mutex
                )
                if fresh_live_p <= 0.0:
                    return {"status": "NO_FRESH_LIVE_PRICE"}

                # NEW [Case 113 : 뮤텍스 내부 0주 진입 2차 무머리 HA음봉 & 개장 7분 쉴드 검문]
                if (
                    REG_OPEN_VWAP_SHIELD_START_HM
                    <= hm_mutex
                    <= REG_OPEN_VWAP_SHIELD_END_HM
                ):
                    mark_pullback_ha_bear_minute_wait(
                        context=context,
                        symbol=TARGET_SYMBOL,
                        cur_min_key=dt_mutex.strftime("%Y-%m-%d %H:%M"),
                    )
                    return {"status": "HOLD_ZERO_SHARES_REG_OPEN_7M_SHIELD"}
                (
                    _,
                    m_z_shaved_bear,
                    _,
                    m_z_ha_ready,
                    _,
                ) = await _get_live_soxl_reentry_snapshot(
                    context, live_price=fresh_live_p, now_est=dt_mutex
                )
                if (not m_z_ha_ready) or m_z_shaved_bear:
                    mark_pullback_ha_bear_minute_wait(
                        context=context,
                        symbol=TARGET_SYMBOL,
                        cur_min_key=dt_mutex.strftime("%Y-%m-%d %H:%M"),
                    )
                    return {"status": "HOLD_ZERO_SHARES_SHAVED_HA_BEAR"}

                exec_order_p = max(
                    0.01, math.floor((fresh_live_p + 1e-9) * 100.0) / 100.0
                )

                # [Case 67, Case 77, Case 88 & Case 91 : 뮤텍스 내부 st_now 기준 now_core_eq, now_init_seed, now_p_mode 재산출 통일]
                eff_rt_pct_0sh = resolve_effective_round_trip_fee_rate_pct(
                    state_dict=st_now
                )
                now_sub_0sh = buckets_from_dicts(st_now.get("sub_buckets", []))
                now_free_cash_0sh = max(
                    0.0, safe_float(st_now.get("free_cash_usd"), 0.0)
                )
                now_init_seed_0sh = max(
                    100.0,
                    safe_float(
                        st_now.get("initial_seed_usd"),
                        DEFAULT_INITIAL_SEED_USD,
                    ),
                )
                now_inj_res_0sh = max(
                    0.0, safe_float(st_now.get("injected_reserve_usd"), 0.0)
                )
                now_inv_tot_0sh = sum(
                    sb.actual_cost_usd for sb in now_sub_0sh
                )
                now_core_eq_0sh = max(
                    now_init_seed_0sh,
                    (now_free_cash_0sh + now_inv_tot_0sh) - now_inj_res_0sh,
                )
                now_p_mode_0sh = (
                    str(st_now.get("portion_mode") or PORTION_MODE_COMPOUND)
                    .upper()
                    .strip()
                )

                prev_anchor_p = safe_float(st_now.get("anchor_price"), 0.0)
                ref_zero_anchor = (
                    prev_anchor_p if prev_anchor_p > 0.0 else exec_order_p
                )
                target_qty, portion_budget = compute_golden8_quota_qty(
                    anchor_price=ref_zero_anchor,
                    current_total_equity=now_core_eq_0sh,
                    initial_seed_usd=now_init_seed_0sh,
                    portion_mode=now_p_mode_0sh,
                    exec_price=exec_order_p,
                )

                (
                    can_proceed_0sh,
                    eff_free_cash_0sh,
                    bp_usd_0sh,
                    guard_res_0sh,
                ) = await _check_and_execute_guard30_or_reserve_injection(
                    context=context,
                    st_now=st_now,
                    exec_order_p=exec_order_p,
                    portion_budget=portion_budget,
                    l1_actual_cost_usd=0.0,
                    is_dip_promotion=False,
                    is_vacant_l1_reentry=False,
                    trigger_desc="0주 첫 1층 진입",
                    target_qty=target_qty,
                )
                if not can_proceed_0sh:
                    return {
                        "status": "HOLD_GUARD30_WAITING_RESERVE_DEPOSIT",
                        "guard_eval": guard_res_0sh,
                    }

                buy_qty, _est_spent = resolve_affordable_buy_qty(
                    target_qty=target_qty,
                    price_t=exec_order_p,
                    free_cash_usd=eff_free_cash_0sh,
                    broker_buying_power_usd=(
                        bp_usd_0sh if bp_usd_0sh > 0.0 else None
                    ),
                    max_portion_budget_usd=portion_budget,
                    round_trip_fee_rate_pct=eff_rt_pct_0sh,
                )

                if buy_qty <= 0:
                    return {"status": "INSUFFICIENT_CASH_FOR_0SH_ENTRY"}

                _, cur_bucket_id, today_str, _ = evaluate_buy_gate_bucket_status(
                    now_est=dt_now,
                    buy_interval_min=buy_interval_min,
                    last_evaluated_bucket_id=safe_int(
                        st_now.get("last_evaluated_buy_bucket_id"), -1
                    ),
                    last_evaluated_date=str(
                        st_now.get("last_evaluated_date") or ""
                    ),
                )

                cid = generate_client_order_id(prefix="INI1FL")
                try:
                    ord_res = await context.api.create_order(
                        symbol=TARGET_SYMBOL,
                        side="BUY",
                        quantity=buy_qty,
                        price=exec_order_p,
                        order_type="LIMIT",
                        time_in_force="DAY",
                        client_order_id=cid,
                        enforce_daymarket_block=True,
                    )
                except Exception as exc:
                    logger.warning(
                        "0주 현재가 지정가 실물 1층(REENTRY_1FL) 매수 주문 예외: %s",
                        exc,
                    )
                    return {"status": "ORDER_ERROR", "error": str(exc)}

                oid = str(ord_res.get("orderId") or "").strip()
                await context.ledger.update_state(
                    TARGET_SYMBOL,
                    l1_target_quota_qty=buy_qty,
                    buy_order_id=oid,
                    client_order_id=cid,
                    ordered_qty=buy_qty,
                    buy_price=exec_order_p,
                    pending_portion_budget=portion_budget,
                    pending_lot_type="REENTRY_1FL",
                    pending_step_up_min_price=0.0,
                    pending_sub_step_up_min_price=0.0,
                    last_evaluated_buy_bucket_id=cur_bucket_id,
                    last_evaluated_date=today_str,
                    last_modify_mono=time.monotonic(),
                    last_reentry_eval_ts=0.0,
                )
                context.wakeup_event.set()
                logger.info(
                    "🔵 [SOXL 0주 60초 타임쉴드 완료 후 현재가 지정가 1층 매수 발주] %d주 @ 지정가 $%.2f (1회예산 $%.2f · orderId=%s)",
                    buy_qty,
                    exec_order_p,
                    portion_budget,
                    oid,
                )
                return {
                    "status": "ZERO_SHARES_IMMEDIATE_1FL_ORDERED",
                    "orderId": oid,
                    "qty": buy_qty,
                    "price": exec_order_p,
                }

    # -----------------------------------------------------------------------
    # [분기 B-1 · Case 73, Case 77, Case 84, Case 88, Case 91 & Case 92 : 본 그리드 상단(2층 ~ 7층)만 보유 중 (1층 공석, is_l2_only_vacant_l1 == True)]
    # -> 2층 단가 이하(Case 73) 안전 영역 내에서:
    #    - 눌림목(-1.00%, PULLBACK_RELOAD)은 무필터로 04:07 ~ 16:00 EST 전 구간 허용!
    #    - 상승돌파(+1.00%, BREAKOUT_RELOAD)는 04:07 ~ 15:29 EST 구간에서 1분봉 Wilder RSI(14) <= 50.0 (Case 92) 조건을 충족할 때만 허용하며,
    #      RSI(14) > 50.0 과열 구간에서는 HOLD_BREAKOUT_RSI_OVER_50 으로 차단해 저점 -1.00% 눌림목 진입으로 전환하고,
    #      15:30 ~ 16:00 EST 구간에서는 데드캣 고점 추격 방어를 위해 HOLD_LATE_SESSION_BREAKOUT_CUTOFF 로 원천 차단! (Case 84)
    #    - 본 그리드가 60초 재장전 쉴드 중이거나 패스했을 때는 즉시 Default-ON 3층 서브 그리드 엔진을 가동!
    # -----------------------------------------------------------------------
    if is_l2_only_vacant_l1:
        rebound_pol_l1 = resolve_smart_rebound_policy(portion_mode)
        use_stalker_l1 = bool(rebound_pol_l1.get("use_stalker_l1", False))
        cur_stalk_l1_act = bool(
            use_stalker_l1 and st.get("stalk_l1_active", False)
        )

        in_re_shield, rem_re_sec = is_within_reentry_monitor_time_shield(
            context, st, TARGET_SYMBOL, now_est=dt_now
        )
        if in_re_shield and (not cur_stalk_l1_act):
            sub_res_re = await _execute_sub_grid_buy_engine_plugin(
                context=context,
                holdings=eff_holdings,
                prices=eff_prices,
                dt_now=dt_now,
                live_p=live_p,
            )
            if isinstance(sub_res_re, dict) and str(
                sub_res_re.get("status") or ""
            ).endswith("_ORDERED"):
                return sub_res_re
            return {
                "status": "HOLD_REENTRY_60S_TIME_SHIELD",
                "remain_shield_sec": rem_re_sec,
            }

        fresh_live_p = (
            live_p
            if (cur_stalk_l1_act and live_p > 0.0)
            else await _fetch_fresh_current_soxl_price(
                context, fallback_price=live_p, now_est=dt_now
            )
        )
        if fresh_live_p <= 0.0:
            return {"status": "NO_FRESH_LIVE_PRICE"}
        re_price_mono = (
            0.0 if cur_stalk_l1_act else time.monotonic()
        )  # MODIFIED [Case 112]: 스토커 반전 포착 시 뮤텍스 2차 브로커 실호가 강제 재동기화

        (
            live_rsi_14,
            closed_shaved_bear,
            closed_ha_bull,
            closed_ha_ready,
            closed_mk,
        ) = await _get_live_soxl_reentry_snapshot(
            context, live_price=fresh_live_p, now_est=dt_now
        )
        sess_vwap = _get_cached_soxl_session_vwap(
            context, live_price=fresh_live_p, now_est=dt_now
        )
        min_upper_tier_p = min(b.book_price for b in buckets)
        wma_info = compute_upper_2_to_7_moving_avg(buckets)
        upper_wma_p = safe_float(
            wma_info.get("upper_wma_price"), min_upper_tier_p
        )
        anchor_p = safe_float(st.get("anchor_price"), min_upper_tier_p)
        cycle_min_p_re = safe_float(st.get("cycle_min_buy_price"), 0.0)
        is_late_cutoff = is_late_regular_new_cycle_cutoff_window(
            hm, now_est=dt_now
        )

        reentry_sig = evaluate_l2_only_hybrid_reentry_signal(
            live_price=fresh_live_p,
            anchor_price=anchor_p,
            l2_book_price=min_upper_tier_p,
            min_upper_tier_price=min_upper_tier_p,
            is_late_new_cycle_cutoff=is_late_cutoff,
            is_late_cutoff=is_late_cutoff,
            rsi_14=live_rsi_14,
            breakout_max_rsi=REENTRY_BREAKOUT_MAX_RSI_50,
            closed_ha_shaved_bear=(False if use_stalker_l1 else closed_shaved_bear),
            closed_ha_bull=closed_ha_bull,
            closed_ha_ready=(True if use_stalker_l1 else closed_ha_ready),
            session_vwap=sess_vwap,
            hm=hm,
            cycle_min_buy_price=(cycle_min_p_re if cycle_min_p_re > 0.0 else None),
            portion_mode=portion_mode,
        )
        sig_type = str(reentry_sig.get("signal_type") or "HOLD_WAIT_GATE")

        # NEW [Case 112 : 바벨(B-12)·단리(S-112) 본 1층 공석 리바운드 스토커(+0.25% 반등 / 완결양봉 반전 타격)]
        if use_stalker_l1:
            l1_bar_snap = _get_live_soxl_stalker_bar_snapshot(
                context, live_price=fresh_live_p, now_est=dt_now
            )
            prev_l1_low = safe_float(st.get("stalk_l1_low_price"), 0.0)
            want_l1_stalk = bool(
                cur_stalk_l1_act
                or (
                    bool(reentry_sig.get("should_buy"))
                    and sig_type in ("PULLBACK_RELOAD", "LOW_BREAK_RELOAD")
                )
            )
            if want_l1_stalk and fresh_live_p <= (min_upper_tier_p + 1e-6):
                l1_stalk_ev = evaluate_stalker_reversal_fire(
                    live_price=fresh_live_p,
                    cur_bar_open=l1_bar_snap["cur_bar_open"],
                    cur_bar_low=l1_bar_snap["cur_bar_low"],
                    prev_stalk_low=(
                        prev_l1_low if cur_stalk_l1_act else l1_bar_snap["cur_bar_low"]
                    ),
                    closed_real_reversal=l1_bar_snap["closed_real_reversal"],
                    closed_ha_shaved_bear=l1_bar_snap["closed_ha_shaved_bear"],
                    closed_ha_ready=l1_bar_snap["closed_ha_ready"],
                    stalk_rebound_pct=safe_float(
                        rebound_pol_l1.get("stalk_rebound_pct"), 0.25
                    ),
                    hm=hm,
                )
                next_l1_low = safe_float(
                    l1_stalk_ev.get("stalk_low_price"), fresh_live_p
                )
                # MODIFIED [Audit-112-01]: 본 1층 스토커 바닥 반등 시 기준가·2층상한 미만 정당 반등 전면 허용 및 저가돌파 기준가 보존
                pb_d_val = safe_float(
                    reentry_sig.get("pullback_drop_pct"), -1.0
                )
                chg_ex_val = safe_float(
                    reentry_sig.get("chg_from_exit_pct"), 0.0
                )
                l1_ceil_lim = (
                    min(anchor_p, min_upper_tier_p)
                    if anchor_p > 0.0
                    else min_upper_tier_p
                )
                still_in_l1_dip = bool(
                    chg_ex_val <= (pb_d_val * 0.5)
                    or (
                        (cur_stalk_l1_act or bool(reentry_sig.get("should_buy")))
                        and fresh_live_p < (l1_ceil_lim - 1e-6)
                    )
                )
                if bool(l1_stalk_ev.get("should_fire")) and still_in_l1_dip:
                    reentry_sig = dict(reentry_sig)
                    reentry_sig["should_buy"] = True
                    is_l1_lb_fire = bool(
                        cycle_min_p_re > 0.0
                        and min(fresh_live_p, next_l1_low)
                        < (cycle_min_p_re - 1e-6)
                        and fresh_live_p <= cycle_min_p_re * 1.005
                    )
                    sig_type = (
                        "LOW_BREAK_RELOAD"
                        if is_l1_lb_fire
                        else "PULLBACK_RELOAD"
                    )
                    reentry_sig["signal_type"] = sig_type
                    if is_l1_lb_fire:
                        reentry_sig["quota_ref_price"] = cycle_min_p_re
                elif not still_in_l1_dip:
                    if cur_stalk_l1_act:
                        await context.ledger.update_state(
                            TARGET_SYMBOL,
                            stalk_l1_active=False,
                            stalk_l1_low_price=0.0,
                        )
                else:
                    if (not cur_stalk_l1_act) or (
                        next_l1_low > 0.0
                        and abs(next_l1_low - prev_l1_low) > 1e-4
                    ):
                        await context.ledger.update_state(
                            TARGET_SYMBOL,
                            stalk_l1_active=True,
                            stalk_l1_low_price=next_l1_low,
                            last_reentry_eval_ts=0.0,
                        )
                    sub_res_st = await _execute_sub_grid_buy_engine_plugin(
                        context=context,
                        holdings=eff_holdings,
                        prices=eff_prices,
                        dt_now=dt_now,
                        live_p=fresh_live_p,
                    )
                    if isinstance(sub_res_st, dict) and str(
                        sub_res_st.get("status") or ""
                    ).endswith("_ORDERED"):
                        return sub_res_st
                    return {
                        "status": "L1_VACANT_STALKING_FALLING_KNIFE",
                        "signal_type": l1_stalk_ev.get("fire_reason"),
                        "live_price": fresh_live_p,
                        "stalk_low_price": next_l1_low,
                        "rebound_from_low_pct": l1_stalk_ev.get(
                            "rebound_from_low_pct"
                        ),
                    }

        if not bool(reentry_sig.get("should_buy")):
            # NEW [Case 110]: 바벨/단리 모드에서 [1층 공석] 정규 재장전 미충족 시 10분 게이트 쌍바닥 1주 마중물 구제 검문
            vac_pol_chk = resolve_smart_primer_policy(
                portion_mode=portion_mode,
                primer_1sh_mode=st.get("primer_1sh_mode"),
            )
            if bool(vac_pol_chk.get("allow_vacant_l1_rescue", False)):
                gate_ok_v, cur_bid_v, today_v, _ = evaluate_buy_gate_bucket_status(
                    now_est=dt_now,
                    buy_interval_min=buy_interval_min,
                    last_evaluated_bucket_id=safe_int(
                        st.get("last_evaluated_buy_bucket_id"), -1
                    ),
                    last_evaluated_date=str(st.get("last_evaluated_date") or ""),
                )
                if gate_ok_v:
                    held_l_v = sum(safe_bucket_lot_count(b) for b in buckets)
                    rat_l_v = max(
                        held_l_v, safe_int(st.get("cycle_ratchet_max_lots"), 0)
                    )
                    drop_v, _, _ = get_golden8_prog_thresholds(
                        held_lots=max(1, held_l_v),
                        threshold_mode=threshold_mode,
                        cycle_ratchet_max_lots=rat_l_v,
                    )
                    p_vac_eval = evaluate_smart_primer_1sh_signal(
                        live_price=fresh_live_p,
                        buckets=buckets,
                        anchor_price=anchor_p,
                        cycle_min_buy_price=cycle_min_p_re,
                        drop_buy_pct=drop_v,
                        cycle_ratchet_max_lots=rat_l_v,
                        portion_mode=portion_mode,
                        primer_1sh_mode=str(
                            st.get("primer_1sh_mode") or PRIMER_MODE_AUTO_SMART
                        ),
                        hm=hm,
                    )
                    if bool(p_vac_eval.get("should_buy")):
                        vac_ord_res = await _try_execute_smart_primer_1sh_order(
                            context=context,
                            dt_now=dt_now,
                            fresh_live_p=fresh_live_p,
                            expect_vacant_l1=True,
                            buy_interval_min=buy_interval_min,
                            threshold_mode=threshold_mode,
                            already_in_mutex=False,
                        )
                        if isinstance(vac_ord_res, dict) and str(
                            vac_ord_res.get("status") or ""
                        ).endswith("_ORDERED"):
                            return vac_ord_res
                    if (
                        str(p_vac_eval.get("signal_type") or "")
                        != "HOLD_REG_OPEN_7M_VWAP_SHIELD"
                    ):
                        await context.ledger.update_state(
                            TARGET_SYMBOL,
                            last_evaluated_buy_bucket_id=cur_bid_v,
                            last_evaluated_date=today_v,
                        )
            new_pass_cnt = safe_int(st.get("seed_protect_pass_cnt"), 0) + 1
            new_day_pass = (
                safe_int(st.get("daily_seed_protect_pass_cnt"), 0) + 1
            )
            if sig_type in (
                "HOLD_PULLBACK_SHAVED_HA_BEAR",
                "HOLD_LOW_BREAK_SHAVED_HA_BEAR",
                "HOLD_REG_OPEN_7M_VWAP_SHIELD",
            ):
                mark_pullback_ha_bear_minute_wait(
                    context=context,
                    symbol=TARGET_SYMBOL,
                    cur_min_key=dt_now.strftime("%Y-%m-%d %H:%M"),
                )
                re_eval_epoch = 0.0
            else:
                re_eval_epoch = mark_reentry_monitor_60s_cycle_shield(
                    context=context,
                    symbol=TARGET_SYMBOL,
                    eval_price=fresh_live_p,
                )
            await context.ledger.update_state(
                TARGET_SYMBOL,
                last_reentry_eval_ts=re_eval_epoch,
                seed_protect_pass_cnt=new_pass_cnt,
                daily_seed_protect_pass_cnt=new_day_pass,
            )
            sub_res_after_pass = await _execute_sub_grid_buy_engine_plugin(
                context=context,
                holdings=eff_holdings,
                prices=eff_prices,
                dt_now=dt_now,
                live_p=fresh_live_p,
            )
            if isinstance(sub_res_after_pass, dict) and str(
                sub_res_after_pass.get("status") or ""
            ).endswith("_ORDERED"):
                return sub_res_after_pass

            if sig_type in (
                "HOLD_PULLBACK_SHAVED_HA_BEAR",
                "HOLD_LOW_BREAK_SHAVED_HA_BEAR",
            ):
                logger.info(
                    "🛡️ [Case 101/105 1층 공석 무머리 HA음봉 패스(%s)] 현재가 $%.2f (기억저가 $%.2f · 직전익절 $%.2f 대비 %+.2f%%) · 완결봉(%s) -> 다음 1분 정각 대기",
                    sig_type,
                    fresh_live_p,
                    cycle_min_p_re,
                    safe_float(reentry_sig.get("ref_anchor"), anchor_p),
                    safe_float(reentry_sig.get("chg_from_exit_pct"), 0.0),
                    closed_mk or "-",
                )
                return {
                    "status": "L2_ONLY_REENTRY_PULLBACK_SHAVED_HA_BEAR_BLOCKED",
                    "signal_type": sig_type,
                    "live_price": fresh_live_p,
                    "rsi_14": live_rsi_14,
                    "closed_ha_shaved_bear": closed_shaved_bear,
                    "closed_ha_bull": closed_ha_bull,
                    "l2_ceiling_price": min_upper_tier_p,
                    "ref_anchor": reentry_sig.get("ref_anchor"),
                    "chg_from_exit_pct": reentry_sig.get("chg_from_exit_pct"),
                    "seed_protect_pass_cnt": new_day_pass,
                }
            if sig_type == "HOLD_REG_OPEN_7M_VWAP_SHIELD":
                logger.info(
                    "🛡️ [Case 105 정규장 개장 7분(09:30~09:36 EST) VWAP 안정화 쉴드] 현재가 $%.2f (직전익절 $%.2f 대비 %+.2f%%) -> 09:37 EST 해금 대기",
                    fresh_live_p,
                    safe_float(reentry_sig.get("ref_anchor"), anchor_p),
                    safe_float(reentry_sig.get("chg_from_exit_pct"), 0.0),
                )
                return {
                    "status": "L2_ONLY_REENTRY_REG_OPEN_7M_SHIELD",
                    "signal_type": sig_type,
                    "live_price": fresh_live_p,
                    "session_vwap": sess_vwap,
                    "seed_protect_pass_cnt": new_day_pass,
                }
            if sig_type == "HOLD_PULLBACK_ABOVE_SESSION_VWAP":
                logger.info(
                    "🛡️ [Case 105/111 1층 공석 스마트눌림목 > 세션VWAP 패스] 현재가 $%.2f > 세션VWAP $%.2f (직전익절 $%.2f 대비 %+.2f%%) -> 고가매수 차단 & 60초 타임쉴드",
                    fresh_live_p,
                    sess_vwap,
                    safe_float(reentry_sig.get("ref_anchor"), anchor_p),
                    safe_float(reentry_sig.get("chg_from_exit_pct"), 0.0),
                )
                return {
                    "status": "L2_ONLY_REENTRY_ABOVE_SESSION_VWAP_BLOCKED",
                    "signal_type": sig_type,
                    "live_price": fresh_live_p,
                    "session_vwap": sess_vwap,
                    "seed_protect_pass_cnt": new_day_pass,
                    "next_reentry_check_sec": REENTRY_MONITOR_TIME_SHIELD_SEC,
                }

            if sig_type == "HOLD_PREVENT_INVERSION":
                logger.info(
                    "🛡️ [Case 73 1층>2층 단가역전 원천 차단] 현재가 $%.2f > 2층단가 상한 $%.2f (직전익절 $%.2f 대비 %+.2f%%) -> 매수 패스 & 60초 타임쉴드 재장전",
                    fresh_live_p,
                    min_upper_tier_p,
                    safe_float(reentry_sig.get("ref_anchor"), anchor_p),
                    safe_float(reentry_sig.get("chg_from_exit_pct"), 0.0),
                )
                return {
                    "status": "L2_ONLY_REENTRY_INVERSION_BLOCKED",
                    "signal_type": sig_type,
                    "live_price": fresh_live_p,
                    "rsi_14": live_rsi_14,
                    "l2_ceiling_price": min_upper_tier_p,
                    "ref_anchor": reentry_sig.get("ref_anchor"),
                    "chg_from_exit_pct": reentry_sig.get("chg_from_exit_pct"),
                    "seed_protect_pass_cnt": new_day_pass,
                    "next_reentry_check_sec": REENTRY_MONITOR_TIME_SHIELD_SEC,
                }
            if sig_type == "HOLD_LATE_SESSION_BREAKOUT_CUTOFF":
                logger.info(
                    "🛡️ [Case 84/111 장마감 30분전(15:30~16:00 EST) 1층 공석 +1.0%% 돌파 추격 원천 차단] 현재가 $%.2f (직전익절 $%.2f 대비 %+.2f%%) -> 돌파매수 패스 & 눌림목(%.1f%%)만 감시",
                    fresh_live_p,
                    safe_float(reentry_sig.get("ref_anchor"), anchor_p),
                    safe_float(reentry_sig.get("chg_from_exit_pct"), 0.0),
                    resolve_smart_pullback_drop_pct(portion_mode),
                )
                return {
                    "status": "L2_ONLY_REENTRY_LATE_BREAKOUT_BLOCKED",
                    "signal_type": sig_type,
                    "live_price": fresh_live_p,
                    "rsi_14": live_rsi_14,
                    "l2_ceiling_price": min_upper_tier_p,
                    "ref_anchor": reentry_sig.get("ref_anchor"),
                    "chg_from_exit_pct": reentry_sig.get("chg_from_exit_pct"),
                    "seed_protect_pass_cnt": new_day_pass,
                    "next_reentry_check_sec": REENTRY_MONITOR_TIME_SHIELD_SEC,
                }
            if sig_type == "HOLD_BREAKOUT_RSI_OVER_50":
                logger.info(
                    "🛡️ [Case 92/111 1층 공석 +1.0%% 상승돌파 시 RSI(14) > 50.0 과열 차단] 현재가 $%.2f (직전익절 $%.2f 대비 %+.2f%%) · 실시간 RSI(14)=%.1f > %.1f -> 과열 돌파 패스 & 저점 눌림목(%.1f%%) 대기 (60초 타임쉴드 재장전)",
                    fresh_live_p,
                    safe_float(reentry_sig.get("ref_anchor"), anchor_p),
                    safe_float(reentry_sig.get("chg_from_exit_pct"), 0.0),
                    live_rsi_14,
                    REENTRY_BREAKOUT_MAX_RSI_50,
                    resolve_smart_pullback_drop_pct(portion_mode),
                )
                return {
                    "status": "L2_ONLY_REENTRY_BREAKOUT_RSI_BLOCKED",
                    "signal_type": sig_type,
                    "live_price": fresh_live_p,
                    "rsi_14": live_rsi_14,
                    "breakout_max_rsi": REENTRY_BREAKOUT_MAX_RSI_50,
                    "l2_ceiling_price": min_upper_tier_p,
                    "ref_anchor": reentry_sig.get("ref_anchor"),
                    "chg_from_exit_pct": reentry_sig.get("chg_from_exit_pct"),
                    "seed_protect_pass_cnt": new_day_pass,
                    "next_reentry_check_sec": REENTRY_MONITOR_TIME_SHIELD_SEC,
                }
            return {
                "status": "L2_ONLY_REENTRY_HOLD_PASSED",
                "signal_type": sig_type,
                "rsi_14": live_rsi_14,
                "ref_anchor": reentry_sig.get("ref_anchor"),
                "l2_ceiling_price": min_upper_tier_p,
                "chg_from_exit_pct": reentry_sig.get("chg_from_exit_pct"),
                "seed_protect_pass_cnt": new_day_pass,
                "next_reentry_check_sec": REENTRY_MONITOR_TIME_SHIELD_SEC,
            }

        async with context.in_memory_ordering_lock:
            async with context.dual_strike_mutex:
                st_now = context.ledger.get_state(TARGET_SYMBOL)
                if str(st_now.get("buy_order_id") or "").strip() or str(
                    st_now.get("sell_order_id") or ""
                ).strip():
                    return {"status": "ALREADY_ORDERING_IN_MUTEX"}

                now_buckets = buckets_from_dicts(st_now.get("buckets", []))
                if not now_buckets or has_active_l1_bucket(now_buckets):
                    return {"status": "L1_STATE_CHANGED_IN_MUTEX"}

                in_re_m, _ = is_within_reentry_monitor_time_shield(
                    context, st_now, TARGET_SYMBOL
                )
                if in_re_m and not bool(st_now.get("stalk_l1_active", False)):
                    return {"status": "HOLD_60S_REENTRY_TIME_SHIELD_IN_MUTEX"}

                # [Case 84 : 뮤텍스 내부 15:29:59 -> 15:30:00 경계 돌파 추격 2차 차단]
                dt_re_mutex = (
                    now_est.astimezone(EST_TZ)
                    if now_est
                    else datetime.now(EST_TZ)
                )
                hm_re_mutex = dt_re_mutex.hour * 100 + dt_re_mutex.minute
                # NEW [Audit-111-02]: 뮤텍스 경합 대기(>=0.25s) 발생 시 브로커 2차 실호가 즉시 재동기화
                if (time.monotonic() - re_price_mono) >= 0.25:
                    live_2nd_re = await _fetch_fresh_current_soxl_price(
                        context, fallback_price=fresh_live_p, now_est=dt_re_mutex
                    )
                    if live_2nd_re > 0.0:
                        fresh_live_p = live_2nd_re
                if (
                    sig_type == "BREAKOUT_RELOAD"
                    and is_late_regular_new_cycle_cutoff_window(
                        hm_re_mutex, now_est=dt_re_mutex
                    )
                ):
                    new_pass_cnt = (
                        safe_int(st_now.get("seed_protect_pass_cnt"), 0) + 1
                    )
                    new_day_pass = (
                        safe_int(st_now.get("daily_seed_protect_pass_cnt"), 0)
                        + 1
                    )
                    re_eval_epoch = mark_reentry_monitor_60s_cycle_shield(
                        context=context,
                        symbol=TARGET_SYMBOL,
                        eval_price=fresh_live_p,
                    )
                    await context.ledger.update_state(
                        TARGET_SYMBOL,
                        last_reentry_eval_ts=re_eval_epoch,
                        seed_protect_pass_cnt=new_pass_cnt,
                        daily_seed_protect_pass_cnt=new_day_pass,
                    )
                    return {
                        "status": "L2_ONLY_REENTRY_LATE_BREAKOUT_BLOCKED",
                        "signal_type": "HOLD_LATE_SESSION_BREAKOUT_CUTOFF",
                        "live_price": fresh_live_p,
                        "seed_protect_pass_cnt": new_day_pass,
                    }

                # [Case 92 & 눌림목 완결1분HA : 뮤텍스 내부 본 그리드 1층 공석 2차 검문]
                if sig_type == "BREAKOUT_RELOAD":
                    mutex_rsi_14 = await _get_live_soxl_rsi_14(
                        context, live_price=fresh_live_p, now_est=dt_re_mutex
                    )
                    if mutex_rsi_14 > (REENTRY_BREAKOUT_MAX_RSI_50 + 1e-6):
                        new_pass_cnt = (
                            safe_int(st_now.get("seed_protect_pass_cnt"), 0)
                            + 1
                        )
                        new_day_pass = (
                            safe_int(
                                st_now.get("daily_seed_protect_pass_cnt"), 0
                            )
                            + 1
                        )
                        re_eval_epoch = mark_reentry_monitor_60s_cycle_shield(
                            context=context,
                            symbol=TARGET_SYMBOL,
                            eval_price=fresh_live_p,
                        )
                        await context.ledger.update_state(
                            TARGET_SYMBOL,
                            last_reentry_eval_ts=re_eval_epoch,
                            seed_protect_pass_cnt=new_pass_cnt,
                            daily_seed_protect_pass_cnt=new_day_pass,
                        )
                        return {
                            "status": "L2_ONLY_REENTRY_BREAKOUT_RSI_BLOCKED",
                            "signal_type": "HOLD_BREAKOUT_RSI_OVER_50",
                            "live_price": fresh_live_p,
                            "rsi_14": mutex_rsi_14,
                            "seed_protect_pass_cnt": new_day_pass,
                        }
                elif sig_type in ("PULLBACK_RELOAD", "LOW_BREAK_RELOAD"):
                    (
                        _,
                        m_shaved_bear,
                        m_ha_bull,
                        m_ha_ready,
                        _,
                    ) = await _get_live_soxl_reentry_snapshot(
                        context, live_price=fresh_live_p, now_est=dt_re_mutex
                    )
                    m_sess_vwap = _get_cached_soxl_session_vwap(
                        context, live_price=fresh_live_p, now_est=dt_re_mutex
                    )
                    m_c_min_now = safe_float(
                        st_now.get("cycle_min_buy_price"), 0.0
                    )
                    m_exec_chk = max(
                        0.01, math.floor((fresh_live_p + 1e-9) * 100.0) / 100.0
                    )
                    if (
                        sig_type == "PULLBACK_RELOAD"
                        and REG_OPEN_VWAP_SHIELD_START_HM
                        <= hm_re_mutex
                        <= REG_OPEN_VWAP_SHIELD_END_HM
                    ):
                        new_pass_cnt = (
                            safe_int(st_now.get("seed_protect_pass_cnt"), 0) + 1
                        )
                        new_day_pass = (
                            safe_int(
                                st_now.get("daily_seed_protect_pass_cnt"), 0
                            )
                            + 1
                        )
                        mark_pullback_ha_bear_minute_wait(
                            context=context,
                            symbol=TARGET_SYMBOL,
                            cur_min_key=dt_re_mutex.strftime("%Y-%m-%d %H:%M"),
                        )
                        await context.ledger.update_state(
                            TARGET_SYMBOL,
                            last_reentry_eval_ts=0.0,
                            seed_protect_pass_cnt=new_pass_cnt,
                            daily_seed_protect_pass_cnt=new_day_pass,
                        )
                        return {
                            "status": "L2_ONLY_REENTRY_REG_OPEN_7M_SHIELD",
                            "signal_type": "HOLD_REG_OPEN_7M_VWAP_SHIELD",
                            "live_price": fresh_live_p,
                            "seed_protect_pass_cnt": new_day_pass,
                        }
                    m_use_l1_stalk = bool(
                        resolve_smart_rebound_policy(
                            st_now.get("portion_mode")
                        ).get("use_stalker_l1", False)
                    )
                    if (not m_use_l1_stalk) and (
                        (not m_ha_ready) or m_shaved_bear
                    ):
                        new_pass_cnt = (
                            safe_int(st_now.get("seed_protect_pass_cnt"), 0)
                            + 1
                        )
                        new_day_pass = (
                            safe_int(
                                st_now.get("daily_seed_protect_pass_cnt"), 0
                            )
                            + 1
                        )
                        mark_pullback_ha_bear_minute_wait(
                            context=context,
                            symbol=TARGET_SYMBOL,
                            cur_min_key=dt_re_mutex.strftime("%Y-%m-%d %H:%M"),
                        )
                        await context.ledger.update_state(
                            TARGET_SYMBOL,
                            last_reentry_eval_ts=0.0,
                            seed_protect_pass_cnt=new_pass_cnt,
                            daily_seed_protect_pass_cnt=new_day_pass,
                        )
                        return {
                            "status": "L2_ONLY_REENTRY_PULLBACK_SHAVED_HA_BEAR_BLOCKED",
                            "signal_type": (
                                "HOLD_LOW_BREAK_SHAVED_HA_BEAR"
                                if sig_type == "LOW_BREAK_RELOAD"
                                else "HOLD_PULLBACK_SHAVED_HA_BEAR"
                            ),
                            "live_price": fresh_live_p,
                            "closed_ha_shaved_bear": m_shaved_bear,
                            "closed_ha_bull": m_ha_bull,
                            "seed_protect_pass_cnt": new_day_pass,
                        }
                    m_l1_lb_ceil = (
                        m_c_min_now * 1.005 if m_use_l1_stalk else m_c_min_now
                    )
                    if (
                        sig_type == "LOW_BREAK_RELOAD"
                        and (
                            m_c_min_now <= 0.0
                            or m_exec_chk >= (m_l1_lb_ceil - 1e-6)
                        )
                    ):
                        re_eval_epoch = mark_reentry_monitor_60s_cycle_shield(
                            context=context,
                            symbol=TARGET_SYMBOL,
                            eval_price=fresh_live_p,
                        )
                        await context.ledger.update_state(
                            TARGET_SYMBOL, last_reentry_eval_ts=re_eval_epoch
                        )
                        return {
                            "status": "L2_ONLY_LOW_BREAK_REBOUNDED",
                            "signal_type": "HOLD_ABOVE_CYCLE_MIN",
                            "live_price": fresh_live_p,
                        }
                    # MODIFIED [Case 113]: T4 대칭 데드존 공석 기준가 = min(직전매도가, 최하단상단가)
                    m_pm = str(st_now.get("portion_mode") or "")
                    raw_m_anc = safe_float(st_now.get("anchor_price"), 0.0)
                    m_min_up = min(b.book_price for b in now_buckets)
                    m_anc = (
                        min(raw_m_anc, m_min_up)
                        if (raw_m_anc > 0.0 and m_min_up > 0.0)
                        else (raw_m_anc if raw_m_anc > 0.0 else m_min_up)
                    )
                    m_pb_r = resolve_smart_pullback_drop_pct(m_pm)
                    m_was_l1_stalk = bool(
                        m_use_l1_stalk
                        and (
                            cur_stalk_l1_act
                            or bool(st_now.get("stalk_l1_active", False))
                        )
                    )
                    m_pb_lim = -0.01 if m_was_l1_stalk else m_pb_r
                    if (
                        sig_type == "PULLBACK_RELOAD"
                        and m_anc > 0.0
                        and ((fresh_live_p - m_anc) / m_anc * 100.0)
                        > (m_pb_lim + 1e-6)
                    ):
                        m_ep = mark_reentry_monitor_60s_cycle_shield(
                            context=context,
                            symbol=TARGET_SYMBOL,
                            eval_price=fresh_live_p,
                        )
                        await context.ledger.update_state(
                            TARGET_SYMBOL, last_reentry_eval_ts=m_ep
                        )
                        return {
                            "status": "L2_PULLBACK_MODE_SHIFT_HOLD",
                            "signal_type": "HOLD_WAIT_GATE",
                        }
                    if (
                        sig_type == "PULLBACK_RELOAD"
                        and m_sess_vwap > 0.0
                        and fresh_live_p > (m_sess_vwap + 1e-6)
                    ):
                        new_pass_cnt = (
                            safe_int(st_now.get("seed_protect_pass_cnt"), 0) + 1
                        )
                        new_day_pass = (
                            safe_int(
                                st_now.get("daily_seed_protect_pass_cnt"), 0
                            )
                            + 1
                        )
                        re_eval_epoch = mark_reentry_monitor_60s_cycle_shield(
                            context=context,
                            symbol=TARGET_SYMBOL,
                            eval_price=fresh_live_p,
                        )
                        await context.ledger.update_state(
                            TARGET_SYMBOL,
                            last_reentry_eval_ts=re_eval_epoch,
                            seed_protect_pass_cnt=new_pass_cnt,
                            daily_seed_protect_pass_cnt=new_day_pass,
                        )
                        return {
                            "status": "L2_ONLY_REENTRY_ABOVE_SESSION_VWAP_BLOCKED",
                            "signal_type": "HOLD_PULLBACK_ABOVE_SESSION_VWAP",
                            "live_price": fresh_live_p,
                            "session_vwap": m_sess_vwap,
                            "seed_protect_pass_cnt": new_day_pass,
                        }

                min_upper_tier_p = min(b.book_price for b in now_buckets)
                exec_order_p = max(
                    0.01, math.floor((fresh_live_p + 1e-9) * 100.0) / 100.0
                )
                if min_upper_tier_p > 0.0 and exec_order_p > (
                    min_upper_tier_p + 1e-6
                ):
                    new_pass_cnt = (
                        safe_int(st_now.get("seed_protect_pass_cnt"), 0) + 1
                    )
                    new_day_pass = (
                        safe_int(st_now.get("daily_seed_protect_pass_cnt"), 0)
                        + 1
                    )
                    re_eval_epoch = mark_reentry_monitor_60s_cycle_shield(
                        context=context,
                        symbol=TARGET_SYMBOL,
                        eval_price=fresh_live_p,
                    )
                    await context.ledger.update_state(
                        TARGET_SYMBOL,
                        last_reentry_eval_ts=re_eval_epoch,
                        seed_protect_pass_cnt=new_pass_cnt,
                        daily_seed_protect_pass_cnt=new_day_pass,
                    )
                    return {
                        "status": "L2_ONLY_REENTRY_INVERSION_BLOCKED",
                        "signal_type": "HOLD_PREVENT_INVERSION",
                        "live_price": fresh_live_p,
                        "l2_ceiling_price": min_upper_tier_p,
                        "seed_protect_pass_cnt": new_day_pass,
                    }

                eff_rt_pct_re = resolve_effective_round_trip_fee_rate_pct(
                    state_dict=st_now
                )
                now_sub_re = buckets_from_dicts(st_now.get("sub_buckets", []))
                now_free_cash = max(
                    0.0, safe_float(st_now.get("free_cash_usd"), 0.0)
                )
                now_init_seed = max(
                    100.0,
                    safe_float(
                        st_now.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD
                    ),
                )
                now_inj_res = max(
                    0.0, safe_float(st_now.get("injected_reserve_usd"), 0.0)
                )
                now_inv_tot = sum(
                    b.actual_cost_usd for b in now_buckets
                ) + sum(sb.actual_cost_usd for sb in now_sub_re)
                now_core_eq = max(
                    now_init_seed,
                    (now_free_cash + now_inv_tot) - now_inj_res,
                )
                now_p_mode_re = (
                    str(st_now.get("portion_mode") or PORTION_MODE_COMPOUND)
                    .upper()
                    .strip()
                )

                quota_ref_p = max(
                    0.01,
                    safe_float(
                        reentry_sig.get("quota_ref_price"),
                        safe_float(
                            reentry_sig.get("ref_anchor"),
                            anchor_p if anchor_p > 0.0 else exec_order_p,
                        ),
                    ),
                )
                target_qty, portion_budget = compute_golden8_quota_qty(
                    anchor_price=quota_ref_p,
                    current_total_equity=now_core_eq,
                    initial_seed_usd=now_init_seed,
                    portion_mode=now_p_mode_re,
                    exec_price=exec_order_p,
                )

                (
                    can_proceed_re,
                    eff_free_cash_re,
                    bp_usd_re,
                    guard_res_re,
                ) = await _check_and_execute_guard30_or_reserve_injection(
                    context=context,
                    st_now=st_now,
                    exec_order_p=exec_order_p,
                    portion_budget=portion_budget,
                    l1_actual_cost_usd=0.0,
                    is_dip_promotion=False,
                    is_vacant_l1_reentry=True,
                    trigger_desc=f"1층 공석 재장전({sig_type})",
                    target_qty=target_qty,
                )
                if not can_proceed_re:
                    # NEW [Case 110]: 정규 8% 재장전이 30% 시드가드($240) 미달로 차단된 경우 자투리 현금으로 1주 구제 시도!
                    vac_rescue_in_mtx = await _try_execute_smart_primer_1sh_order(
                        context=context,
                        dt_now=dt_re_mutex,
                        fresh_live_p=fresh_live_p,
                        expect_vacant_l1=True,
                        buy_interval_min=buy_interval_min,
                        threshold_mode=threshold_mode,
                        already_in_mutex=True,
                        ignore_bucket_gate=True,
                    )
                    if isinstance(vac_rescue_in_mtx, dict) and str(
                        vac_rescue_in_mtx.get("status") or ""
                    ).endswith("_ORDERED"):
                        return vac_rescue_in_mtx
                    return {
                        "status": "HOLD_L2_ONLY_GUARD30_WAITING_RESERVE_DEPOSIT",
                        "signal_type": sig_type,
                        "guard_eval": guard_res_re,
                    }

                buy_qty, _est_spent = resolve_affordable_buy_qty(
                    target_qty=target_qty,
                    price_t=exec_order_p,
                    free_cash_usd=eff_free_cash_re,
                    broker_buying_power_usd=(
                        bp_usd_re if bp_usd_re > 0.0 else None
                    ),
                    max_portion_budget_usd=portion_budget,
                    round_trip_fee_rate_pct=eff_rt_pct_re,
                )

                if buy_qty <= 0:
                    re_eval_epoch = mark_reentry_monitor_60s_cycle_shield(
                        context=context,
                        symbol=TARGET_SYMBOL,
                        eval_price=fresh_live_p,
                    )
                    await context.ledger.update_state(
                        TARGET_SYMBOL,
                        last_reentry_eval_ts=re_eval_epoch,
                    )
                    return {"status": "HOLD_L2_ONLY_NO_CASH_FOR_REENTRY"}

                re_eval_epoch = mark_reentry_monitor_60s_cycle_shield(
                    context=context,
                    symbol=TARGET_SYMBOL,
                    eval_price=exec_order_p,
                )
                pending_lot_tag_re = (
                    "REENTRY_1FL_BREAKOUT"
                    if sig_type == "BREAKOUT_RELOAD"
                    else (
                        "REENTRY_1FL_LOW_BREAK"
                        if sig_type == "LOW_BREAK_RELOAD"
                        else "REENTRY_1FL"
                    )
                )
                cid = generate_client_order_id(prefix="RE1FL")
                try:
                    ord_res = await context.api.create_order(
                        symbol=TARGET_SYMBOL,
                        side="BUY",
                        quantity=buy_qty,
                        price=exec_order_p,
                        order_type="LIMIT",
                        time_in_force="DAY",
                        client_order_id=cid,
                        enforce_daymarket_block=True,
                    )
                except Exception as exc:
                    await context.ledger.update_state(
                        TARGET_SYMBOL, last_reentry_eval_ts=re_eval_epoch
                    )
                    logger.warning(
                        "상단 그리드 보유 중 60초 주기 현재가 지정가 1층(REENTRY_1FL) 재장전 주문 예외: %s",
                        exc,
                    )
                    return {"status": "ORDER_ERROR", "error": str(exc)}

                oid = str(ord_res.get("orderId") or "").strip()
                await context.ledger.update_state(
                    TARGET_SYMBOL,
                    l1_target_quota_qty=buy_qty,
                    buy_order_id=oid,
                    client_order_id=cid,
                    ordered_qty=buy_qty,
                    buy_price=exec_order_p,
                    pending_portion_budget=portion_budget,
                    pending_lot_type=pending_lot_tag_re,
                    pending_step_up_min_price=0.0,
                    pending_sub_step_up_min_price=0.0,
                    last_modify_mono=time.monotonic(),
                    last_reentry_eval_ts=re_eval_epoch,
                    stalk_l1_active=False,
                    stalk_l1_low_price=0.0,
                )
                context.wakeup_event.set()
                logger.info(
                    "🔥 [Case 92 SOXL 상단 %d개층 보유 중 60초 주기 현재가 지정가 1층 재장전(%s · RSI=%.1f) 발주] %d주 @ 지정가 $%.2f <= 2층상한 $%.2f (1회예산 $%.2f · 직전익절 $%.2f · 이평 $%.2f · orderId=%s)",
                    len(now_buckets),
                    sig_type,
                    live_rsi_14,
                    buy_qty,
                    exec_order_p,
                    min_upper_tier_p,
                    portion_budget,
                    quota_ref_p,
                    upper_wma_p,
                    oid,
                )
                return {
                    "status": "L2_HELD_HYBRID_REAL_1FL_ORDERED",
                    "signal_type": sig_type,
                    "rsi_14": live_rsi_14,
                    "orderId": oid,
                    "qty": buy_qty,
                    "price": exec_order_p,
                    "l2_ceiling_price": min_upper_tier_p,
                }

    if not buckets or not has_active_l1:
        return {
            "status": "WAIT_HOLDINGS_RECONCILE_SYNC",
            "ledger_grid_qty": len(buckets),
            "broker_qty": h_qty,
        }

    # -----------------------------------------------------------------------
    # [분기 B-0 · Case 77, Case 78 & Case 88 : 본 그리드 활성 1층 부분 체결 미체결 잔량(rem_quota_qty > 0) 존재 시]
    # -> 원장 가용현금(free_cash)이 최소 1주 매수 비용 이상일 때만 진입하고, 부족 시 60초 쿨다운 쉴드 각인!
    # -----------------------------------------------------------------------
    l1_target_q = max(
        buckets[0].qty, safe_int(st.get("l1_target_quota_qty"), 0)
    )
    rem_quota_qty = max(0, l1_target_q - buckets[0].qty)
    l1_book_p = round(buckets[0].book_price, 2)
    one_share_min_cost = live_p * (1.0 + eff_rt_pct / 100.0)

    if (
        rem_quota_qty > 0
        and live_p <= (l1_book_p + 1e-6)
        and free_cash >= one_share_min_cost
    ):
        async with context.in_memory_ordering_lock:
            async with context.dual_strike_mutex:
                st_now = context.ledger.get_state(TARGET_SYMBOL)
                if str(st_now.get("buy_order_id") or "").strip() or str(
                    st_now.get("sell_order_id") or ""
                ).strip():
                    return {"status": "ALREADY_ORDERING_IN_MUTEX"}

                now_buckets = buckets_from_dicts(st_now.get("buckets", []))
                if not now_buckets or not has_active_l1_bucket(now_buckets):
                    return {"status": "L1_STATE_CHANGED_IN_MUTEX"}

                in_s_sh, _ = is_within_post_sell_time_shield(
                    context, st_now, TARGET_SYMBOL
                )
                in_b_sh, _ = is_within_post_buy_time_shield(
                    context, st_now, TARGET_SYMBOL
                )
                in_res_m, _ = is_within_reserve_deposit_check_shield(
                    context, st_now, TARGET_SYMBOL
                )
                if in_s_sh or in_b_sh or in_res_m:
                    return {"status": "HOLD_60S_TIME_SHIELD_IN_MUTEX"}

                now_target_q = max(
                    now_buckets[0].qty,
                    safe_int(st_now.get("l1_target_quota_qty"), 0),
                )
                now_rem_qty = max(0, now_target_q - now_buckets[0].qty)
                now_l1_book_p = round(now_buckets[0].book_price, 2)

                if now_rem_qty > 0:
                    fresh_live_p = await _fetch_fresh_current_soxl_price(
                        context, fallback_price=live_p
                    )
                    if fresh_live_p > 0.0 and fresh_live_p <= (
                        now_l1_book_p + 1e-6
                    ):
                        eff_rt_pct_top = resolve_effective_round_trip_fee_rate_pct(
                            state_dict=st_now
                        )
                        cur_lim_p = (
                            math.floor((fresh_live_p + 1e-9) * 100.0) / 100.0
                        )
                        exec_order_p = max(
                            0.01, min(cur_lim_p, now_l1_book_p)
                        )
                        topup_budget = round(
                            float(now_rem_qty) * now_l1_book_p, 4
                        )
                        now_free_cash = max(
                            0.0, safe_float(st_now.get("free_cash_usd"), 0.0)
                        )
                        one_share_top_cost = exec_order_p * (
                            1.0 + eff_rt_pct_top / 100.0
                        )
                        if now_free_cash < one_share_top_cost:
                            mark_reserve_deposit_check_shield(
                                context=context,
                                symbol=TARGET_SYMBOL,
                                clear_shield=False,
                            )
                            return {
                                "status": "HOLD_TOPUP_INSUFFICIENT_FREE_CASH",
                                "free_cash_usd": now_free_cash,
                            }

                        raw_bp_top = await context.api.get_buying_power_usd(
                            safety_buffer_pct=0.2
                        )
                        if (
                            raw_bp_top <= 0.0
                            and now_free_cash >= one_share_top_cost
                        ):
                            await asyncio.sleep(0.25)
                            raw_bp_top = await context.api.get_buying_power_usd(
                                safety_buffer_pct=0.2
                            )
                            if raw_bp_top <= 0.0:
                                return {
                                    "status": "HOLD_TOPUP_TRANSIENT_BP_ERROR"
                                }

                        masked_bp_main_top = (
                            _resolve_masked_bp_for_soxl_sub_or_topup(
                                context, st_now, raw_bp_top
                            )
                        )
                        if masked_bp_main_top < one_share_top_cost:
                            mark_reserve_deposit_check_shield(
                                context=context,
                                symbol=TARGET_SYMBOL,
                                clear_shield=False,
                            )
                            return {
                                "status": "HOLD_TOPUP_INSUFFICIENT_BROKER_BP",
                                "broker_bp_usd": masked_bp_main_top,
                                "free_cash_usd": now_free_cash,
                            }

                        buy_qty_top, _ = resolve_affordable_buy_qty(
                            target_qty=now_rem_qty,
                            price_t=exec_order_p,
                            free_cash_usd=now_free_cash,
                            broker_buying_power_usd=masked_bp_main_top,
                            max_portion_budget_usd=topup_budget,
                            round_trip_fee_rate_pct=eff_rt_pct_top,
                        )
                        if buy_qty_top > 0:
                            eff_topup_budget = round(
                                float(buy_qty_top) * now_l1_book_p, 4
                            )
                            cid = generate_client_order_id(prefix="TOP1FL")
                            try:
                                ord_res = await context.api.create_order(
                                    symbol=TARGET_SYMBOL,
                                    side="BUY",
                                    quantity=buy_qty_top,
                                    price=exec_order_p,
                                    order_type="LIMIT",
                                    time_in_force="DAY",
                                    client_order_id=cid,
                                    enforce_daymarket_block=True,
                                )
                                oid = str(
                                    ord_res.get("orderId") or ""
                                ).strip()
                                await context.ledger.update_state(
                                    TARGET_SYMBOL,
                                    l1_target_quota_qty=now_target_q,
                                    buy_order_id=oid,
                                    client_order_id=cid,
                                    ordered_qty=buy_qty_top,
                                    buy_price=exec_order_p,
                                    pending_portion_budget=eff_topup_budget,
                                    pending_lot_type="TOPUP_1FL",
                                    pending_step_up_min_price=0.0,
                                    pending_sub_step_up_min_price=0.0,
                                    last_modify_mono=time.monotonic(),
                                )
                                context.wakeup_event.set()
                                logger.info(
                                    "🎯 [Case 78 SOXL 1.5초 모니터 1층 단가($%.2f) 재도래 포착 -> 미체결 잔량(TOPUP_1FL) 지정가 발주] +%d주 @ 지정가 $%.2f (기보유 %d주 / 목표 %d주 · 60초 지정가 대기 개시 · orderId=%s)",
                                    now_l1_book_p,
                                    buy_qty_top,
                                    exec_order_p,
                                    now_buckets[0].qty,
                                    now_target_q,
                                    oid,
                                )
                                return {
                                    "status": "L1_PARTIAL_TOPUP_ORDERED",
                                    "orderId": oid,
                                    "qty": buy_qty_top,
                                    "price": exec_order_p,
                                    "l1_cur_qty": now_buckets[0].qty,
                                    "l1_target_quota_qty": now_target_q,
                                }
                            except Exception as exc:
                                mark_reserve_deposit_check_shield(
                                    context=context,
                                    symbol=TARGET_SYMBOL,
                                    clear_shield=False,
                                )
                                logger.warning(
                                    "Case 78 1층 미체결 잔량(TOPUP_1FL) 지정가 주문 예외(60초 쿨다운): %s",
                                    exc,
                                )
                                return {
                                    "status": "TOPUP_ORDER_ERROR",
                                    "error": str(exc),
                                }
                        else:
                            mark_reserve_deposit_check_shield(
                                context=context,
                                symbol=TARGET_SYMBOL,
                                clear_shield=False,
                            )

    # -----------------------------------------------------------------------
    # MODIFIED [Case 113 : 2층 공석 최저가 돌파매수 영구 폐기 -> 10분 와이드 추매 일원화]
    if False and has_active_l1 and (not has_active_l2_bucket(buckets)):
        held_lots_l2v = sum(safe_bucket_lot_count(b) for b in buckets)
        ratchet_l2v = max(
            held_lots_l2v, safe_int(st.get("cycle_ratchet_max_lots"), 0)
        )
        c_min_l2v = safe_float(st.get("cycle_min_buy_price"), 0.0)
        exec_pre_l2v = max(
            0.01, math.floor((live_p + 1e-9) * 100.0) / 100.0
        )
        l2v_reb_pol = resolve_smart_rebound_policy(portion_mode)
        l2v_vwap_g = safe_float(l2v_reb_pol.get("vwap_crash_guard_pct"), 0.0)
        l2v_sess_vwap = _get_cached_soxl_session_vwap(
            context, live_price=live_p, now_est=dt_now
        )
        defer_l2v_to_crash_stalker = bool(
            l2v_vwap_g < -0.1
            and (
                bool(st.get("stalk_add_active", False))
                or (
                    l2v_sess_vwap > 0.0
                    and live_p <= l2v_sess_vwap * (1.0 + l2v_vwap_g / 100.0)
                )
            )
        )
        if (
            (not defer_l2v_to_crash_stalker)
            and ratchet_l2v >= 2
            and c_min_l2v > 0.0
            and exec_pre_l2v < (c_min_l2v - 1e-6)
        ):
            in_re_l2v, _ = is_within_reentry_monitor_time_shield(
                context, st, TARGET_SYMBOL, now_est=dt_now
            )
            in_res_l2v, _ = is_within_reserve_deposit_check_shield(
                context, st, TARGET_SYMBOL
            )
            if (not in_re_l2v) and (not in_res_l2v):
                fresh_l2v_p = await _fetch_fresh_current_soxl_price(
                    context, fallback_price=live_p, now_est=dt_now
                )
                if fresh_l2v_p > 0.0:
                    (
                        l2v_rsi,
                        l2v_shaved_bear,
                        l2v_ha_bull,
                        l2v_ha_ready,
                        l2v_closed_mk,
                    ) = await _get_live_soxl_reentry_snapshot(
                        context, live_price=fresh_l2v_p, now_est=dt_now
                    )
                    l2v_eval = evaluate_l2_vacant_low_break_signal(
                        live_price=fresh_l2v_p,
                        buckets=buckets,
                        cycle_min_buy_price=c_min_l2v,
                        cycle_ratchet_max_lots=ratchet_l2v,
                        closed_ha_shaved_bear=l2v_shaved_bear,
                        closed_ha_bull=l2v_ha_bull,
                        closed_ha_ready=l2v_ha_ready,
                    )
                    l2v_sig_type = str(
                        l2v_eval.get("signal_type") or "NOT_ELIGIBLE"
                    )
                    if l2v_sig_type == "HOLD_LOW_BREAK_SHAVED_HA_BEAR":
                        mark_pullback_ha_bear_minute_wait(
                            context=context,
                            symbol=TARGET_SYMBOL,
                            cur_min_key=dt_now.strftime("%Y-%m-%d %H:%M"),
                        )
                        logger.info(
                            "🛡️ [Case 105 본 2층공석 최저가 돌파 무머리 HA음봉 패스] 현재가 $%.2f < 기억저가 $%.2f · 완결봉(%s) 무머리 HA음봉 -> 다음 1분 정각 대기",
                            fresh_l2v_p,
                            c_min_l2v,
                            l2v_closed_mk or "-",
                        )
                    elif bool(l2v_eval.get("should_buy")):
                        async with context.in_memory_ordering_lock:
                            async with context.dual_strike_mutex:
                                st_now = context.ledger.get_state(TARGET_SYMBOL)
                                if str(
                                    st_now.get("buy_order_id") or ""
                                ).strip() or str(
                                    st_now.get("sell_order_id") or ""
                                ).strip():
                                    return {"status": "ALREADY_ORDERING_IN_MUTEX"}

                                now_buckets = buckets_from_dicts(
                                    st_now.get("buckets", [])
                                )
                                if (
                                    not now_buckets
                                    or not has_active_l1_bucket(now_buckets)
                                    or has_active_l2_bucket(now_buckets)
                                ):
                                    return {"status": "L2_VACANT_STATE_CHANGED_IN_MUTEX"}

                                in_s_sh, _ = is_within_post_sell_time_shield(
                                    context, st_now, TARGET_SYMBOL
                                )
                                in_b_sh, _ = is_within_post_buy_time_shield(
                                    context, st_now, TARGET_SYMBOL
                                )
                                in_re_m2, _ = is_within_reentry_monitor_time_shield(
                                    context, st_now, TARGET_SYMBOL, now_est=dt_now
                                )
                                if in_s_sh or in_b_sh or in_re_m2:
                                    return {"status": "HOLD_60S_TIME_SHIELD_IN_MUTEX"}

                                dt_l2v_m = (
                                    now_est.astimezone(EST_TZ)
                                    if now_est
                                    else datetime.now(EST_TZ)
                                )
                                (
                                    _,
                                    m_l2v_shaved_bear,
                                    m_l2v_ha_bull,
                                    m_l2v_ha_ready,
                                    _,
                                ) = await _get_live_soxl_reentry_snapshot(
                                    context,
                                    live_price=fresh_l2v_p,
                                    now_est=dt_l2v_m,
                                )
                                now_held_l2v = sum(
                                    safe_bucket_lot_count(b) for b in now_buckets
                                )
                                now_ratchet_l2v = max(
                                    now_held_l2v,
                                    safe_int(
                                        st_now.get("cycle_ratchet_max_lots"), 0
                                    ),
                                )
                                now_c_min_l2v = safe_float(
                                    st_now.get("cycle_min_buy_price"), 0.0
                                )
                                m_l2v_eval = evaluate_l2_vacant_low_break_signal(
                                    live_price=fresh_l2v_p,
                                    buckets=now_buckets,
                                    cycle_min_buy_price=now_c_min_l2v,
                                    cycle_ratchet_max_lots=now_ratchet_l2v,
                                    closed_ha_shaved_bear=m_l2v_shaved_bear,
                                    closed_ha_bull=m_l2v_ha_bull,
                                    closed_ha_ready=m_l2v_ha_ready,
                                )
                                if not bool(m_l2v_eval.get("should_buy")):
                                    if (
                                        str(m_l2v_eval.get("signal_type") or "")
                                        == "HOLD_LOW_BREAK_SHAVED_HA_BEAR"
                                    ):
                                        mark_pullback_ha_bear_minute_wait(
                                            context=context,
                                            symbol=TARGET_SYMBOL,
                                            cur_min_key=dt_l2v_m.strftime(
                                                "%Y-%m-%d %H:%M"
                                            ),
                                        )
                                    return {
                                        "status": "L2_VACANT_LOW_BREAK_CHANGED_IN_MUTEX",
                                        "signal_type": m_l2v_eval.get(
                                            "signal_type"
                                        ),
                                    }

                                exec_order_p = max(
                                    0.01,
                                    math.floor((fresh_l2v_p + 1e-9) * 100.0)
                                    / 100.0,
                                )
                                eff_rt_l2v = resolve_effective_round_trip_fee_rate_pct(
                                    state_dict=st_now
                                )
                                now_sub_l2v = buckets_from_dicts(
                                    st_now.get("sub_buckets", [])
                                )
                                now_free_l2v = max(
                                    0.0,
                                    safe_float(st_now.get("free_cash_usd"), 0.0),
                                )
                                now_seed_l2v = max(
                                    100.0,
                                    safe_float(
                                        st_now.get("initial_seed_usd"),
                                        DEFAULT_INITIAL_SEED_USD,
                                    ),
                                )
                                now_inj_l2v = max(
                                    0.0,
                                    safe_float(
                                        st_now.get("injected_reserve_usd"), 0.0
                                    ),
                                )
                                now_inv_l2v = sum(
                                    b.actual_cost_usd for b in now_buckets
                                ) + sum(
                                    sb.actual_cost_usd for sb in now_sub_l2v
                                )
                                now_core_eq_l2v = max(
                                    now_seed_l2v,
                                    (now_free_l2v + now_inv_l2v) - now_inj_l2v,
                                )
                                now_p_mode_l2v = (
                                    str(
                                        st_now.get("portion_mode")
                                        or PORTION_MODE_COMPOUND
                                    )
                                    .upper()
                                    .strip()
                                )
                                target_qty, portion_budget = (
                                    compute_golden8_quota_qty(
                                        anchor_price=now_c_min_l2v,
                                        current_total_equity=now_core_eq_l2v,
                                        initial_seed_usd=now_seed_l2v,
                                        portion_mode=now_p_mode_l2v,
                                        exec_price=exec_order_p,
                                    )
                                )
                                (
                                    can_proc_l2v,
                                    eff_free_l2v,
                                    bp_usd_l2v,
                                    guard_res_l2v,
                                ) = await _check_and_execute_guard30_or_reserve_injection(
                                    context=context,
                                    st_now=st_now,
                                    exec_order_p=exec_order_p,
                                    portion_budget=portion_budget,
                                    l1_actual_cost_usd=(
                                        0.0
                                        if is_primer_1sh_tag(now_buckets[0])
                                        else now_buckets[0].actual_cost_usd
                                    ),
                                    is_dip_promotion=True,
                                    is_vacant_l1_reentry=False,
                                    trigger_desc="2층공석 최저가 돌파매수",
                                    target_qty=target_qty,
                                )
                                if not can_proc_l2v:
                                    # MODIFIED [Audit-110-04]: 60초 쉴드 각인(1.5초 스레싱 및 B-2/서브 아사 원천 차단) & 즉시 1주 마중물 구제 시도!
                                    mark_reentry_monitor_60s_cycle_shield(
                                        context=context,
                                        symbol=TARGET_SYMBOL,
                                        eval_price=exec_order_p,
                                    )
                                    l2v_primer_res = await _try_execute_smart_primer_1sh_order(
                                        context=context,
                                        dt_now=dt_now,
                                        fresh_live_p=fresh_l2v_p,
                                        expect_vacant_l1=False,
                                        buy_interval_min=buy_interval_min,
                                        threshold_mode=threshold_mode,
                                        already_in_mutex=True,
                                    )
                                    if isinstance(l2v_primer_res, dict) and str(
                                        l2v_primer_res.get("status") or ""
                                    ).endswith("_ORDERED"):
                                        return l2v_primer_res
                                    return {
                                        "status": "HOLD_L2_VACANT_LOW_BREAK_GUARD30",
                                        "guard_eval": guard_res_l2v,
                                    }

                                buy_qty_l2v, _ = resolve_affordable_buy_qty(
                                    target_qty=target_qty,
                                    price_t=exec_order_p,
                                    free_cash_usd=eff_free_l2v,
                                    broker_buying_power_usd=(
                                        bp_usd_l2v if bp_usd_l2v > 0.0 else None
                                    ),
                                    max_portion_budget_usd=portion_budget,
                                    round_trip_fee_rate_pct=eff_rt_l2v,
                                )
                                if buy_qty_l2v <= 0:
                                    mark_reentry_monitor_60s_cycle_shield(
                                        context=context,
                                        symbol=TARGET_SYMBOL,
                                        eval_price=exec_order_p,
                                    )
                                    return {
                                        "status": "HOLD_L2_VACANT_LOW_BREAK_ZERO_QTY"
                                    }

                                _, cur_b10_l2v, today_l2v, _ = (
                                    evaluate_buy_gate_bucket_status(
                                        now_est=dt_now,
                                        buy_interval_min=buy_interval_min,
                                        last_evaluated_bucket_id=safe_int(
                                            st_now.get(
                                                "last_evaluated_buy_bucket_id"
                                            ),
                                            -1,
                                        ),
                                        last_evaluated_date=str(
                                            st_now.get("last_evaluated_date")
                                            or ""
                                        ),
                                    )
                                )
                                prev_b10_l2v = safe_int(
                                    st_now.get("last_evaluated_buy_bucket_id"),
                                    -1,
                                )
                                prev_dt_l2v = str(
                                    st_now.get("last_evaluated_date") or ""
                                )
                                next_b10_l2v = (
                                    max(prev_b10_l2v, cur_b10_l2v)
                                    if prev_dt_l2v == today_l2v
                                    else cur_b10_l2v
                                )
                                cid = generate_client_order_id(prefix="LB2VAC")
                                try:
                                    ord_res = await context.api.create_order(
                                        symbol=TARGET_SYMBOL,
                                        side="BUY",
                                        quantity=buy_qty_l2v,
                                        price=exec_order_p,
                                        order_type="LIMIT",
                                        time_in_force="DAY",
                                        client_order_id=cid,
                                        enforce_daymarket_block=True,
                                    )
                                except Exception as exc:
                                    mark_reentry_monitor_60s_cycle_shield(
                                        context=context,
                                        symbol=TARGET_SYMBOL,
                                        eval_price=exec_order_p,
                                    )
                                    logger.warning(
                                        "Case 105 본 2층공석 최저가 돌파매수 주문 예외: %s",
                                        exc,
                                    )
                                    return {
                                        "status": "ORDER_ERROR",
                                        "error": str(exc),
                                    }

                                oid = str(ord_res.get("orderId") or "").strip()
                                mark_reentry_monitor_60s_cycle_shield(
                                    context=context,
                                    symbol=TARGET_SYMBOL,
                                    eval_price=exec_order_p,
                                )
                                await context.ledger.update_state(
                                    TARGET_SYMBOL,
                                    buy_order_id=oid,
                                    client_order_id=cid,
                                    ordered_qty=buy_qty_l2v,
                                    buy_price=exec_order_p,
                                    pending_portion_budget=portion_budget,
                                    pending_lot_type="DIP_1FL_LOW_BREAK",
                                    pending_step_up_min_price=0.0,
                                    pending_sub_step_up_min_price=0.0,
                                    last_evaluated_buy_bucket_id=next_b10_l2v,
                                    last_evaluated_date=today_l2v,
                                    last_modify_mono=time.monotonic(),
                                )
                                context.wakeup_event.set()
                                logger.info(
                                    "🔥 [Case 105 SOXL 본 2층공석 최저가 돌파매수 발주] %d주 @ 지정가 $%.2f < 기억저가 $%.2f (1층 $%.2f ➔ 2층 이관 예정 · RSI=%.1f · orderId=%s)",
                                    buy_qty_l2v,
                                    exec_order_p,
                                    now_c_min_l2v,
                                    now_buckets[0].book_price,
                                    l2v_rsi,
                                    oid,
                                )
                                return {
                                    "status": "L2_VACANT_LOW_BREAK_1FL_ORDERED",
                                    "signal_type": "LOW_BREAK_L2_VAC_RELOAD",
                                    "orderId": oid,
                                    "qty": buy_qty_l2v,
                                    "price": exec_order_p,
                                    "cycle_min_buy_price": now_c_min_l2v,
                                }

    # -----------------------------------------------------------------------
    # [분기 B-2 · Case 60 ~ 112 : 본 그리드 활성 1층 보유 중 추매 및 바벨(VWAP -4.5%)·단리(VWAP -3.0%) 심층 폭락 스토커 방어막]
    # -----------------------------------------------------------------------
    rebound_pol_b2 = resolve_smart_rebound_policy(portion_mode)
    vwap_guard_pct = safe_float(
        rebound_pol_b2.get("vwap_crash_guard_pct"), 0.0
    )
    sess_vwap_b2 = _get_cached_soxl_session_vwap(
        context, live_price=live_p, now_est=dt_now
    )
    cur_stalk_add_act = bool(
        vwap_guard_pct < -0.1 and st.get("stalk_add_active", False)
    )
    deep_below_vwap = bool(
        vwap_guard_pct < -0.1
        and sess_vwap_b2 > 0.0
        and live_p <= sess_vwap_b2 * (1.0 + vwap_guard_pct / 100.0)
    )

    is_gate_open, cur_bucket_id, today_str, b_info = (
        evaluate_buy_gate_bucket_status(
            now_est=dt_now,
            buy_interval_min=buy_interval_min,
            last_evaluated_bucket_id=safe_int(
                st.get("last_evaluated_buy_bucket_id"), -1
            ),
            last_evaluated_date=str(st.get("last_evaluated_date") or ""),
        )
    )

    bypass_10m_for_crash_stalk = bool(deep_below_vwap or cur_stalk_add_act)
    if (not is_gate_open) and (not bypass_10m_for_crash_stalk):
        sub_res_wait = await _execute_sub_grid_buy_engine_plugin(
            context=context,
            holdings=eff_holdings,
            prices=eff_prices,
            dt_now=dt_now,
            live_p=live_p,
        )
        if isinstance(sub_res_wait, dict) and str(
            sub_res_wait.get("status") or ""
        ).endswith("_ORDERED"):
            return sub_res_wait

        if rem_quota_qty > 0:
            return {
                "status": "MONITORING_1_5S_L1_TOPUP_PRICE",
                "l1_cur_qty": buckets[0].qty,
                "l1_target_quota_qty": l1_target_q,
                "l1_rem_quota_qty": rem_quota_qty,
                "l1_book_price": l1_book_p,
                "live_price": live_p,
            }
        return {
            "status": "WAIT_NEXT_BUY_GATE",
            "next_gate": b_info.get("next_gate_hm_str", ""),
        }

    fresh_live_p = (
        live_p
        if (bypass_10m_for_crash_stalk and (not is_gate_open) and live_p > 0.0)
        else await _fetch_fresh_current_soxl_price(
            context, fallback_price=live_p, now_est=dt_now
        )
    )
    if fresh_live_p <= 0.0:
        return {"status": "NO_FRESH_LIVE_PRICE"}

    held_lots = sum(safe_bucket_lot_count(b) for b in buckets)
    ratchet_max_lots = max(
        held_lots, safe_int(st.get("cycle_ratchet_max_lots"), 0)
    )
    drop_buy_pct, _, _ = get_golden8_prog_thresholds(
        held_lots=max(1, held_lots),
        threshold_mode=threshold_mode,
        cycle_ratchet_max_lots=ratchet_max_lots,
    )

    anchor_p = safe_float(st.get("anchor_price"), buckets[0].book_price)
    cycle_min_p = safe_float(st.get("cycle_min_buy_price"), anchor_p)
    eff_step_drop = (
        0.0 if unlock_mode in ("STATIC", "NONE", "OFF") else STEP_UP_2X_DROP_PCT
    )

    dip_eval = evaluate_step_up_2x_dip_signal(
        live_price=fresh_live_p,
        buckets=buckets,
        anchor_price=anchor_p,
        cycle_min_buy_price=cycle_min_p,
        drop_buy_pct=drop_buy_pct,
        free_cash_usd=free_cash,
        realized_equity_usd=budget_base_eq,
        step_up_drop_pct=eff_step_drop,
        min_cash_ratio=STEP_UP_2X_MIN_CASH_RATIO,
        min_rebound_mult=STEP_UP_2X_MIN_REBOUND_MULT,
        max_tiers_for_unlock=STEP_UP_2X_MAX_TIERS,
    )
    ref_buy_anchor = safe_float(
        dip_eval.get("ref_static_anchor"), buckets[0].book_price
    )
    chg_for_buy_pct = safe_float(dip_eval.get("chg_static_pct"), 0.0)
    lot_tag = "DIP_1FL"

    # NEW [Case 112 : 바벨(B-12 : VWAP -4.5%) · 단리(S-112 : VWAP -3.0%) 심층 폭락장 추매 칼날받이 스토커 방어막]
    fired_by_crash_stalker = False
    fresh_deep_vwap = bool(
        vwap_guard_pct < -0.1
        and sess_vwap_b2 > 0.0
        and fresh_live_p <= sess_vwap_b2 * (1.0 + vwap_guard_pct / 100.0)
    )
    if fresh_deep_vwap or cur_stalk_add_act:
        add_bar_snap = _get_live_soxl_stalker_bar_snapshot(
            context, live_price=fresh_live_p, now_est=dt_now
        )
        prev_add_low = safe_float(st.get("stalk_add_low_price"), 0.0)
        if bool(dip_eval.get("should_buy")) or cur_stalk_add_act:
            add_stalk_ev = evaluate_stalker_reversal_fire(
                live_price=fresh_live_p,
                cur_bar_open=add_bar_snap["cur_bar_open"],
                cur_bar_low=add_bar_snap["cur_bar_low"],
                prev_stalk_low=(
                    prev_add_low if cur_stalk_add_act else add_bar_snap["cur_bar_low"]
                ),
                closed_real_reversal=add_bar_snap["closed_real_reversal"],
                closed_ha_shaved_bear=add_bar_snap["closed_ha_shaved_bear"],
                closed_ha_ready=add_bar_snap["closed_ha_ready"],
                stalk_rebound_pct=safe_float(
                    rebound_pol_b2.get("stalk_rebound_pct"), 0.25
                ),
                hm=hm,
                is_dip_add=True,
            )
            next_add_low = safe_float(
                add_stalk_ev.get("stalk_low_price"), fresh_live_p
            )
            # MODIFIED [Audit-112-02]: 단차 비례 반등 허용폭(min(-0.50, drop*0.5)) 및 1층 단가 하단 강제
            add_reb_ceil_pct = min(-0.50, drop_buy_pct * 0.50)
            still_valid_add_dip = bool(
                fresh_live_p < (buckets[0].book_price - 1e-6)
                and (
                    chg_for_buy_pct <= add_reb_ceil_pct
                    or bool(dip_eval.get("should_buy"))
                )
            )
            if bool(add_stalk_ev.get("should_fire")) and still_valid_add_dip:
                fresh_2nd = await _fetch_fresh_current_soxl_price(
                    context, fallback_price=fresh_live_p, now_est=dt_now
                )
                if fresh_2nd > 0.0:
                    fresh_live_p = fresh_2nd
                dip_eval = dict(dip_eval)
                dip_eval["should_buy"] = True
                fired_by_crash_stalker = True
            elif not still_valid_add_dip:
                if cur_stalk_add_act:
                    await context.ledger.update_state(
                        TARGET_SYMBOL,
                        stalk_add_active=False,
                        stalk_add_low_price=0.0,
                    )
                if not is_gate_open:
                    return {"status": "CRASH_STALK_REBOUNDED_CLEARED"}
                dip_eval = dict(dip_eval)
                dip_eval["should_buy"] = False
            else:
                if (not cur_stalk_add_act) or (
                    next_add_low > 0.0
                    and abs(next_add_low - prev_add_low) > 1e-4
                ):
                    await context.ledger.update_state(
                        TARGET_SYMBOL,
                        stalk_add_active=True,
                        stalk_add_low_price=next_add_low,
                    )
                sub_res_cs = await _execute_sub_grid_buy_engine_plugin(
                    context=context,
                    holdings=eff_holdings,
                    prices=eff_prices,
                    dt_now=dt_now,
                    live_p=fresh_live_p,
                )
                if isinstance(sub_res_cs, dict) and str(
                    sub_res_cs.get("status") or ""
                ).endswith("_ORDERED"):
                    return sub_res_cs
                return {
                    "status": "DIP_ADD_STALKING_VWAP_CRASH",
                    "signal_type": add_stalk_ev.get("fire_reason"),
                    "live_price": fresh_live_p,
                    "session_vwap": sess_vwap_b2,
                    "stalk_low_price": next_add_low,
                    "vwap_crash_guard_pct": vwap_guard_pct,
                }
        elif not is_gate_open:
            sub_res_cs2 = await _execute_sub_grid_buy_engine_plugin(
                context=context,
                holdings=eff_holdings,
                prices=eff_prices,
                dt_now=dt_now,
                live_p=fresh_live_p,
            )
            if isinstance(sub_res_cs2, dict) and str(
                sub_res_cs2.get("status") or ""
            ).endswith("_ORDERED"):
                return sub_res_cs2
            return {
                "status": "WAIT_NEXT_BUY_GATE",
                "next_gate": b_info.get("next_gate_hm_str", ""),
            }

    if not bool(dip_eval.get("should_buy")):
        # NEW [Case 110]: 정규 신저가/스텝업 미충족 시 모드별 스마트 역산 1주 마중물(PRIMER_1SH) 타점 검문!
        # (시드고갈 waiting_reserve_deposit 래치 중이라도 계좌에 1주 비용[$45 내외]이 남아 있으면 즉시 출동!)
        primer_b2_eval = evaluate_smart_primer_1sh_signal(
            live_price=fresh_live_p,
            buckets=buckets,
            anchor_price=anchor_p,
            cycle_min_buy_price=cycle_min_p,
            drop_buy_pct=drop_buy_pct,
            cycle_ratchet_max_lots=ratchet_max_lots,
            portion_mode=portion_mode,
            primer_1sh_mode=str(
                st.get("primer_1sh_mode") or PRIMER_MODE_AUTO_SMART
            ),
            hm=hm,
        )
        if (
            str(primer_b2_eval.get("signal_type") or "")
            == "HOLD_REG_OPEN_7M_VWAP_SHIELD"
        ):
            return {
                "status": "HOLD_PRIMER_REG_OPEN_7M_SHIELD",
                "signal_type": "HOLD_REG_OPEN_7M_VWAP_SHIELD",
                "live_price": fresh_live_p,
                "trigger_price": primer_b2_eval.get("trigger_price"),
            }
        if bool(primer_b2_eval.get("should_buy")):
            primer_ord_res = await _try_execute_smart_primer_1sh_order(
                context=context,
                dt_now=dt_now,
                fresh_live_p=fresh_live_p,
                expect_vacant_l1=False,
                buy_interval_min=buy_interval_min,
                threshold_mode=threshold_mode,
                already_in_mutex=False,
            )
            if isinstance(primer_ord_res, dict) and str(
                primer_ord_res.get("status") or ""
            ).endswith("_ORDERED"):
                return primer_ord_res

        if bool(st.get("waiting_reserve_deposit", False)):
            mark_reserve_deposit_check_shield(
                context=context, symbol=TARGET_SYMBOL, clear_shield=False
            )
            sub_res_dep = await _execute_sub_grid_buy_engine_plugin(
                context=context,
                holdings=eff_holdings,
                prices=eff_prices,
                dt_now=dt_now,
                live_p=fresh_live_p,
            )
            if isinstance(sub_res_dep, dict) and str(
                sub_res_dep.get("status") or ""
            ).endswith("_ORDERED"):
                return sub_res_dep
            return {
                "status": "HOLD_WAITING_RESERVE_DEPOSIT_PRICE_REBOUND",
                "trigger_tag": dip_eval.get("trigger_tag", "HOLD"),
                "ref_buy_anchor": round(ref_buy_anchor, 4),
                "chg_pct": round(chg_for_buy_pct, 2),
                "required_drop_pct": drop_buy_pct,
            }

        new_pass_cnt = safe_int(st.get("seed_protect_pass_cnt"), 0) + 1
        new_day_pass = safe_int(st.get("daily_seed_protect_pass_cnt"), 0) + 1
        await context.ledger.update_state(
            TARGET_SYMBOL,
            last_evaluated_buy_bucket_id=cur_bucket_id,
            last_evaluated_date=today_str,
            seed_protect_pass_cnt=new_pass_cnt,
            daily_seed_protect_pass_cnt=new_day_pass,
        )

        # 🛡️ [Case 88 핵심 : 본 그리드가 10분 게이트를 패스한 즉시 Default-ON 3층 서브 그리드 엔진 가동!]
        sub_res_gate = await _execute_sub_grid_buy_engine_plugin(
            context=context,
            holdings=eff_holdings,
            prices=eff_prices,
            dt_now=dt_now,
            live_p=fresh_live_p,
        )
        if isinstance(sub_res_gate, dict) and str(
            sub_res_gate.get("status") or ""
        ).endswith("_ORDERED"):
            return sub_res_gate

        return {
            "status": "SEED_PROTECT_PASSED",
            "trigger_tag": dip_eval.get("trigger_tag", "HOLD"),
            "ref_buy_anchor": round(ref_buy_anchor, 4),
            "chg_pct": round(chg_for_buy_pct, 2),
            "required_drop_pct": drop_buy_pct,
            "cycle_ratchet_max_lots": ratchet_max_lots,
            "step_up_eligible": bool(dip_eval.get("step_up_eligible", False)),
            "stepped_min_price": safe_float(
                dip_eval.get("stepped_min_price"), 0.0
            ),
            "seed_protect_pass_cnt": new_day_pass,
            "sub_grid_eval": sub_res_gate,
        }

    # NEW [Case 113 : 10분 게이트 추매(B-2) 시에도 직전 완결 1분봉 무머리 HA음봉이면 버킷 미소모 패스하여 진바닥 최저가 매수!]
    if REG_OPEN_VWAP_SHIELD_START_HM <= hm <= REG_OPEN_VWAP_SHIELD_END_HM:
        return {
            "status": "HOLD_DIP_REG_OPEN_7M_SHIELD",
            "hm": hm,
            "live_price": fresh_live_p,
        }
    (
        _,
        b2_shaved_bear,
        _,
        b2_ha_ready,
        b2_closed_mk,
    ) = await _get_live_soxl_reentry_snapshot(
        context, live_price=fresh_live_p, now_est=dt_now
    )
    if (not b2_ha_ready) or b2_shaved_bear:
        logger.info(
            "🛡️ [Case 113 10분게이트 추매 무머리 HA음봉 패스] 현재가 $%.2f (저가 $%.2f 대비 %.2f%% <= %.1f%%) · 완결봉(%s) 무머리 HA음봉 -> 버킷 미소모 다음 분 대기",
            fresh_live_p,
            ref_buy_anchor,
            chg_for_buy_pct,
            drop_buy_pct,
            b2_closed_mk or "-",
        )
        return {
            "status": "HOLD_DIP_SHAVED_HA_BEAR_WAIT",
            "live_price": fresh_live_p,
            "closed_bar_minute_key": b2_closed_mk,
            "chg_pct": round(chg_for_buy_pct, 2),
        }

    async with context.in_memory_ordering_lock:
        async with context.dual_strike_mutex:
            st_now = context.ledger.get_state(TARGET_SYMBOL)
            if str(st_now.get("buy_order_id") or "").strip() or str(
                st_now.get("sell_order_id") or ""
            ).strip():
                return {"status": "ALREADY_ORDERING_IN_MUTEX"}

            now_buckets = buckets_from_dicts(st_now.get("buckets", []))
            if not now_buckets or not has_active_l1_bucket(now_buckets):
                return {"status": "L1_STATE_CHANGED_IN_MUTEX"}

            gate_open_m, cur_b10_m, today_m_b2, _ = evaluate_buy_gate_bucket_status(
                now_est=dt_now,
                buy_interval_min=buy_interval_min,
                last_evaluated_bucket_id=safe_int(
                    st_now.get("last_evaluated_buy_bucket_id"), -1
                ),
                last_evaluated_date=str(
                    st_now.get("last_evaluated_date") or ""
                ),
            )
            if (not gate_open_m) and (not fired_by_crash_stalker):
                return {"status": "BUCKET_ALREADY_EVALUATED_IN_MUTEX"}
            cur_bucket_id = max(cur_bucket_id, cur_b10_m)
            today_str = today_m_b2

            in_s_sh, _ = is_within_post_sell_time_shield(
                context, st_now, TARGET_SYMBOL
            )
            in_b_sh, _ = is_within_post_buy_time_shield(
                context, st_now, TARGET_SYMBOL
            )
            if in_s_sh or in_b_sh:
                return {"status": "HOLD_60S_TIME_SHIELD_IN_MUTEX"}

            eff_rt_pct_dip = resolve_effective_round_trip_fee_rate_pct(
                state_dict=st_now
            )
            now_held_lots = sum(safe_bucket_lot_count(b) for b in now_buckets)
            now_ratchet_lots = max(
                now_held_lots, safe_int(st_now.get("cycle_ratchet_max_lots"), 0)
            )
            now_drop_pct, _, _ = get_golden8_prog_thresholds(
                held_lots=max(1, now_held_lots),
                threshold_mode=threshold_mode,
                cycle_ratchet_max_lots=now_ratchet_lots,
            )
            now_sub_dip = buckets_from_dicts(st_now.get("sub_buckets", []))
            now_free_cash = max(0.0, safe_float(st_now.get("free_cash_usd"), 0.0))
            now_init_seed = max(
                100.0,
                safe_float(
                    st_now.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD
                ),
            )
            now_inj_res = max(
                0.0, safe_float(st_now.get("injected_reserve_usd"), 0.0)
            )
            now_inv_tot = sum(
                b.actual_cost_usd for b in now_buckets
            ) + sum(sb.actual_cost_usd for sb in now_sub_dip)
            now_core_eq = max(
                now_init_seed,
                (now_free_cash + now_inv_tot) - now_inj_res,
            )
            now_p_mode_dip = (
                str(st_now.get("portion_mode") or PORTION_MODE_COMPOUND)
                .upper()
                .strip()
            )
            now_budget_base_eq = resolve_portion_budget_base_equity(
                initial_seed_usd=now_init_seed,
                core_equity_usd=now_core_eq,
                portion_mode=now_p_mode_dip,
            )

            now_dip_eval = evaluate_step_up_2x_dip_signal(
                live_price=fresh_live_p,
                buckets=now_buckets,
                anchor_price=safe_float(
                    st_now.get("anchor_price"), now_buckets[0].book_price
                ),
                cycle_min_buy_price=safe_float(
                    st_now.get("cycle_min_buy_price"), 0.0
                ),
                drop_buy_pct=now_drop_pct,
                free_cash_usd=now_free_cash,
                realized_equity_usd=now_budget_base_eq,
                step_up_drop_pct=eff_step_drop,
                min_cash_ratio=STEP_UP_2X_MIN_CASH_RATIO,
                min_rebound_mult=STEP_UP_2X_MIN_REBOUND_MULT,
                max_tiers_for_unlock=STEP_UP_2X_MAX_TIERS,
            )
            if (not bool(now_dip_eval.get("should_buy"))) and (
                not fired_by_crash_stalker
            ):
                return {"status": "DIP_SIGNAL_CHANGED_IN_MUTEX"}

            is_step_up_unlock = bool(
                now_dip_eval.get("is_step_up_unlock", False)
            )
            trigger_tag = str(
                now_dip_eval.get("trigger_tag") or "STATIC_NEW_LOW"
            )
            quota_ref_p = max(
                0.01,
                safe_float(
                    now_dip_eval.get("quota_ref_price"), ref_buy_anchor
                ),
            )
            stepped_min_p = safe_float(
                now_dip_eval.get("stepped_min_price"), 0.0
            )

            if is_step_up_unlock and stepped_min_p > 0.0:
                max_trigger_p = (
                    math.floor((stepped_min_p + 1e-9) * 100.0) / 100.0
                )
            else:
                max_trigger_p = (
                    math.floor(
                        (
                            ref_buy_anchor * (1.0 + now_drop_pct / 100.0)
                            + 1e-9
                        )
                        * 100.0
                    )
                    / 100.0
                )
            cur_limit_p = (
                math.floor((fresh_live_p + 1e-9) * 100.0) / 100.0
            )
            if fired_by_crash_stalker and cur_limit_p >= (
                now_buckets[0].book_price - 1e-6
            ):
                await context.ledger.update_state(
                    TARGET_SYMBOL,
                    stalk_add_active=False,
                    stalk_add_low_price=0.0,
                )
                return {"status": "CRASH_STALK_ABOVE_L1_ABORTED"}
            exec_order_p = (
                max(0.01, cur_limit_p)
                if fired_by_crash_stalker
                else max(0.01, min(cur_limit_p, max_trigger_p))
            )

            target_qty, portion_budget = compute_golden8_quota_qty(
                anchor_price=quota_ref_p,
                current_total_equity=now_core_eq,
                initial_seed_usd=now_init_seed,
                portion_mode=now_p_mode_dip,
                exec_price=exec_order_p,
            )

            (
                can_proceed_dip,
                eff_free_cash_dip,
                bp_usd_dip,
                guard_res_dip,
            ) = await _check_and_execute_guard30_or_reserve_injection(
                context=context,
                st_now=st_now,
                exec_order_p=exec_order_p,
                portion_budget=portion_budget,
                l1_actual_cost_usd=(
                    0.0
                    if is_primer_1sh_tag(now_buckets[0])
                    else now_buckets[0].actual_cost_usd
                ),
                is_dip_promotion=True,
                is_vacant_l1_reentry=False,
                trigger_desc=f"{now_held_lots + 1}회차 추매({trigger_tag})",
                target_qty=target_qty,
            )
            if not can_proceed_dip:
                # NEW [Case 110 · Audit-110-03]: 정규 8% 추매가 30% 시드가드에 차단된 경우 자투리 현금으로 1주 마중물 즉시 구제 시도!
                dip_primer_rescue = await _try_execute_smart_primer_1sh_order(
                    context=context,
                    dt_now=dt_now,
                    fresh_live_p=fresh_live_p,
                    expect_vacant_l1=False,
                    buy_interval_min=buy_interval_min,
                    threshold_mode=threshold_mode,
                    already_in_mutex=True,
                )
                if isinstance(dip_primer_rescue, dict) and str(
                    dip_primer_rescue.get("status") or ""
                ).endswith("_ORDERED"):
                    return dip_primer_rescue
                return {
                    "status": "HOLD_DIP_GUARD30_WAITING_RESERVE_DEPOSIT",
                    "trigger_tag": trigger_tag,
                    "guard_eval": guard_res_dip,
                }

            buy_qty, _est_spent = resolve_affordable_buy_qty(
                target_qty=target_qty,
                price_t=exec_order_p,
                free_cash_usd=eff_free_cash_dip,
                broker_buying_power_usd=(
                    bp_usd_dip if bp_usd_dip > 0.0 else None
                ),
                max_portion_budget_usd=portion_budget,
                round_trip_fee_rate_pct=eff_rt_pct_dip,
            )

            if buy_qty <= 0:
                return {"status": "CASH_EXHAUSTED_SKIP"}

            cid_prefix = (
                f"U{now_held_lots + 1}L"
                if is_step_up_unlock
                else f"B{now_held_lots + 1}L"
            )
            cid = generate_client_order_id(prefix=cid_prefix)
            try:
                ord_res = await context.api.create_order(
                    symbol=TARGET_SYMBOL,
                    side="BUY",
                    quantity=buy_qty,
                    price=exec_order_p,
                    order_type="LIMIT",
                    time_in_force="DAY",
                    client_order_id=cid,
                    enforce_daymarket_block=True,
                )
            except Exception as exc:
                logger.error(
                    "SOXL 10분 게이트(%s) 현재가 지정가 그리드 추매 주문 발사 예외: %s",
                    trigger_tag,
                    exc,
                )
                return {"status": "BUY_ORDER_ERROR", "error": str(exc)}

            oid = str(ord_res.get("orderId") or "").strip()
            await context.ledger.update_state(
                TARGET_SYMBOL,
                buy_order_id=oid,
                client_order_id=cid,
                ordered_qty=buy_qty,
                buy_price=exec_order_p,
                pending_portion_budget=portion_budget,
                pending_lot_type=lot_tag,
                pending_step_up_min_price=(
                    round(stepped_min_p, 4) if is_step_up_unlock else 0.0
                ),
                pending_sub_step_up_min_price=0.0,
                last_evaluated_buy_bucket_id=cur_bucket_id,
                last_evaluated_date=today_str,
                last_modify_mono=time.monotonic(),
                stalk_add_active=False,
                stalk_add_low_price=0.0,
            )
            context.wakeup_event.set()
            if is_step_up_unlock:
                logger.info(
                    "🔓 [Case 76 SOXL 스텝업 저가 해금(%s) 추매 발주] %d주 @ 지정가 $%.2f (1층 $%.2f 대비 -15%% 해금가 $%.2f · 구저가 $%.2f[%.2fx] · 현금비중 %.1f%% · orderId=%s)",
                    trigger_tag,
                    buy_qty,
                    exec_order_p,
                    now_buckets[0].book_price,
                    stepped_min_p,
                    ref_buy_anchor,
                    safe_float(now_dip_eval.get("rebound_mult"), 2.0),
                    safe_float(now_dip_eval.get("cash_ratio_pct"), 20.0),
                    oid,
                )
            else:
                logger.info(
                    "🔵 [SOXL %d회차(잠금%d회차 · 단차 %.1f%%) 현재가 지정가 그리드 추매 발주] %d주 @ 지정가 $%.2f (기억저가 $%.2f 대비 %.2f%% · orderId=%s)",
                    now_held_lots + 1,
                    now_ratchet_lots,
                    now_drop_pct,
                    buy_qty,
                    exec_order_p,
                    ref_buy_anchor,
                    chg_for_buy_pct,
                    oid,
                )
            return {
                "status": "QUOTA_DIP_BUY_ORDERED",
                "trigger_tag": trigger_tag,
                "is_step_up_unlock": is_step_up_unlock,
                "orderId": oid,
                "qty": buy_qty,
                "price": exec_order_p,
                "ref_buy_anchor": round(quota_ref_p, 4),
                "chg_pct": round(chg_for_buy_pct, 2),
                "drop_threshold_pct": now_drop_pct,
                "cycle_ratchet_max_lots": now_ratchet_lots,
            }


# 하위 호환 별칭 (외부 모듈에서 구 함수명으로 호출하더라도 신규 게이트 엔진으로 안전 직결)
execute_premarket_vwap_sniper_plugin = execute_seed_protected_buy_gate_plugin
