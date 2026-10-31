# -*- coding: utf-8 -*-
"""
# MODIFIED: sniper_plugin.py
인피니트 스노우볼 (Infinite Snowball) v3.0 — 스나이퍼 매수 코어 Part 2 / 2 (Step 05 / 09)
역할:
1) sniper_plugin_core.py (Part 1 / 2) 의 모든 상수·타임쉴드·GUARD30 예비수혈·체결커밋·미체결 동기화 심볼 명시적 재익스포트(Facade Re-export)로
   타 모듈(defense_plugin.py, tg_ui_plugin.py, main_runtime.py, main.py, plugin_updater.py) AST 임포트 호환성 100% 보장
2) 04:07 ~ 16:00 EST 비대칭 매수 타격 게이트 실행기 (execute_seed_protected_buy_gate_plugin):
   - 🌟 [분기 G · Case 80] : 미동부 프리장 황금시간대(07:00 ~ 07:50 EST & 14봉 이상 확보된 1분봉 Wilder RSI(14) <= 19.0) 도달 시
     전술 제어반 선택 모드(기본값 NONE[OFF] ↔ POCKET_ALLIN ↔ GRID_L1_ALLIN)에 따라 가용 현금 시드 100% 전액 추가매수 발주
   - 🛡️ [분기 A · Case 65, 80, 84] : 그리드 0주 상태(is_zero_shares)에서 0주 종료 후 60.0초 타임쉴드 경과 뒤 현재가 지정가 첫 1층(REENTRY_1FL) 산입하되,
     정규장 마감 30분 전(15:30 ~ 16:00 EST, is_late_regular_new_cycle_cutoff_window) 구간에서는 고점 오버나이트 방어를 위해
     0주 새 사이클 첫 1층 진입을 100% 원천 차단(HOLD_LATE_SESSION_NEW_CYCLE_CUTOFF)!
   - 🔥 [분기 B-1 · Case 67, 73, 77, 84] : 상단 2층 ~ 7층(GRID_L2 ~ GRID_L7) 보유 중 1층 공석(is_l2_only_vacant_l1) 시
     매 60.0초(1분) 타임쉴드 주기마다 실시간 현재가를 조회하되, 현재가 <= 2층 단가 상한 가드(HOLD_PREVENT_INVERSION · Case 73) 하에서
     직전 익절가 대비 눌림목(-1.00%, PULLBACK_RELOAD) OR 상승돌파(+1.00%, BREAKOUT_RELOAD) 시 독립 실물 1층(REENTRY_1FL)을 재장전하며,
     정규장 마감 30분 전(15:30 ~ 16:00 EST) 구간에서는 +1.00% 상승돌파(BREAKOUT_RELOAD) 추격만 핀포인트 차단(HOLD_LATE_SESSION_BREAKOUT_CUTOFF)하고
     -1.00% 눌림목(PULLBACK_RELOAD) 재장전은 100% 정상 허용!
   - 🎯 [분기 B-0 · Case 78] : 활성 1층 지정가 부분 체결(buckets[0].qty < l1_target_quota_qty) 시 매수 후 60.0초 타임쉴드 경과 뒤
     매 1.5초 실시간 모니터에서 현재가 <= 1층 단가(buckets[0].book_price) 재도래 시 미체결 잔량(TOPUP_1FL) 지정가 60.0초 재대기 발주 (15:30 ~ 16:00 EST 정상 허용)
   - 🔵 [분기 B-2 · Case 60, 72, 76, 77] : 활성 1층 보유 중 04:07 EST 기점 10분 고정 매수 게이트 도래 시
     정적 기억 최저가 대비 4단 와이드 활주로(-1.0% / -2.0% / -3.5% / -5.5%) 신저가 OR STEP2X_15PCT_C20 3중 안전문(-15.0% 스텝업) 추매(DIP_1FL) 집행
     (15:30 ~ 16:00 EST 정상 허용)
- 제1헌법 ~ 제6헌법 및 Case 01 ~ 84 완벽 준수
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime
from typing import Any, Dict, Optional

from quant_engine import (
    DEFAULT_GOLDEN_ALLIN_MODE,
    GOLDEN_ALLIN_MODES,
    MAX_RESERVE_PORTIONS,
    MIN_DIP_BUDGET_RATIO,
    PORTION_RATIO_LOCKED,
    ROUND_TRIP_FEE_RATE_PCT,
    buckets_from_dicts,
    compute_golden8_quota_qty,
    compute_upper_2_to_7_moving_avg,
    evaluate_golden_allin_signal,
    evaluate_l2_only_hybrid_reentry_signal,
    evaluate_step_up_2x_dip_signal,
    get_golden8_prog_thresholds,
    has_active_l1_bucket,
    pocket_from_dict,
    resolve_affordable_buy_qty,
    resolve_allin_affordable_buy_qty,
)
from quant_indicators_plugin import (
    NEW_CYCLE_BUY_CUTOFF_HM,
    evaluate_buy_gate_bucket_status,
    is_active_buy_window,
    is_golden_allin_time_window,
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
    _commit_filled_buy_to_stratum_ledger,
    _fetch_fresh_current_soxl_price,
    _get_live_soxl_price,
    is_within_auto_fill_grace_shield,
    is_within_reentry_monitor_time_shield,
    is_within_reserve_deposit_check_shield,
    mark_auto_fill_grace_shield,
    mark_reentry_monitor_60s_cycle_shield,
    mark_reserve_deposit_check_shield,
    min_req_cash_str,
    sync_dynamic_vwap_buy_order_modify,
    sync_pending_buy_order_plugin,
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


# ---------------------------------------------------------------------------
# [핵심 2] 진화 챔피언 (🌟 POCKET_ALLIN / 🔥 GRID_L1_ALLIN × 💉 05_RESV_6P_GUARD30 × 🔓 06_STEP2X_15PCT_C20 × 🛡️ Case 84) : 비대칭 매수 타격 엔진
#  - 분기 G   : 07:00 ~ 07:50 EST & RSI(14) <= 19.0 황금시간 가용시드 100% 전액 추가매수 (제어반 ON 시 · Case 80)
#  - 분기 A   : 그리드 0주 상태 -> 15:30 ~ 16:00 EST 구간에서는 새 사이클 1층 진입 100% 차단(Case 84) · 그 외 60초 타임쉴드 후 첫 1층(REENTRY_1FL) 산입
#  - 분기 B-1 : 상단 2~7층 보유 중 1층 공석 -> 매 60.0초(1분) 주기 재장전 모니터 & 2층 단가 상한(Case 73) &
#               15:30 ~ 16:00 EST 구간 +1.00% 상승돌파(BREAKOUT_RELOAD)만 차단 / -1.00% 눌림목(PULLBACK_RELOAD) 허용(Case 84)
#  - 분기 B-0 : 활성 1층 부분체결 미체결 잔량(rem_quota_qty > 0) -> 60초 타임쉴드 후 매 1.5초 모니터에서 현재가 <= 1층 단가 도래 시 잔량(TOPUP_1FL) 발주(Case 78)
#  - 분기 B-2 : 활성 1층 보유 중 -> 10분 고정 게이트 & 정적 기억저가 4단 와이드 신저가 OR STEP2X_15PCT_C20 스텝업 추매(Case 76) & GUARD30/예비수혈(Case 77)
# ---------------------------------------------------------------------------
async def execute_seed_protected_buy_gate_plugin(
    context: Any,
    holdings: Dict[str, Dict[str, Any]],
    prices: Dict[str, float],
    now_est: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    🎯 1, 🎯 2, 🎯 4 & Case 25 ~ 84 (챔피언 : 🌟 POCKET_ALLIN / 🔥 GRID_L1_ALLIN × 💉 05_RESV_6P_GUARD30 × 🔓 06_STEP2X_15PCT_C20 × 🛡️ Case 84):
    04:07:00 ~ 16:00:00 EST 운용 구간에서 작동하는 비대칭 매수 타격 엔진.
    """
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    hm = dt_now.hour * 100 + dt_now.minute
    today_est_str = dt_now.strftime("%Y-%m-%d")

    # 1) 미체결 매수 주문이 있으면 먼저 체결 확인 수행
    st = context.ledger.get_state(TARGET_SYMBOL)
    if str(st.get("buy_order_id") or "").strip():
        return await sync_pending_buy_order_plugin(
            context=context,
            holdings=holdings,
            prices=prices,
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

    # 🛡️ 3-B) [Case 77 & Case 80] 시드고갈 입금 대기 또는 골든포켓 현금 가동 중일 때 60.0초 감지 타임쉴드 검문
    in_res_sh, rem_res_sec = is_within_reserve_deposit_check_shield(
        context, st, TARGET_SYMBOL
    )
    if in_res_sh:
        return {
            "status": "HOLD_WAITING_RESERVE_DEPOSIT_60S_SHIELD",
            "remain_shield_sec": rem_res_sec,
            "required_reserve_deposit_usd": safe_float(
                st.get("required_reserve_deposit_usd"), 0.0
            ),
        }

    live_p = _get_live_soxl_price(context, prices, holdings, dt_now)
    if live_p <= 0.0:
        return {"status": "NO_LIVE_PRICE"}

    buckets = buckets_from_dicts(st.get("buckets", []))
    gp = pocket_from_dict(st.get("golden_pocket"))
    h_qty = safe_int((holdings or {}).get(TARGET_SYMBOL, {}).get("qty"), 0)

    init_seed = max(
        100.0,
        safe_float(st.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD),
    )
    cum_realized = safe_float(st.get("cumulative_realized_net_usd"), 0.0)
    injected_reserve_usd = max(
        0.0, safe_float(st.get("injected_reserve_usd"), 0.0)
    )
    realized_equity = max(100.0, init_seed + cum_realized)
    free_cash = max(0.0, safe_float(st.get("free_cash_usd"), 0.0))
    actual_invested = sum(b.actual_cost_usd for b in buckets) + (
        gp.actual_cost_usd if gp.is_active else 0.0
    )
    # Case 77 & Case 80: 온디맨드 예비시드 수혈금(injected_reserve_usd)을 제외한 순수 코어 총자산(core_equity) 산출
    core_equity = max(
        init_seed, (free_cash + actual_invested) - injected_reserve_usd
    )
    portion_mode = str(st.get("portion_mode") or "COMP_08PCT").upper()
    threshold_mode = str(st.get("threshold_mode") or "WIDE_RUNWAY").upper()
    unlock_mode = str(
        st.get("unlock_mode") or DEFAULT_UNLOCK_MODE
    ).upper()
    golden_allin_mode = (
        str(st.get("golden_allin_mode") or DEFAULT_GOLDEN_ALLIN_MODE)
        .upper()
        .strip()
    )
    if golden_allin_mode not in GOLDEN_ALLIN_MODES:
        golden_allin_mode = DEFAULT_GOLDEN_ALLIN_MODE
    buy_interval_min = LOCKED_BUY_INTERVAL_MIN

    # -----------------------------------------------------------------------
    # [분기 G · Case 80 : 미동부 프리장 황금시간대(07:00 ~ 07:50 EST & RSI(14) <= 19.0) 가용현금 100% 전액 추가매수]
    # -> 전술 제어반에서 POCKET_ALLIN 또는 GRID_L1_ALLIN 이 선택된 경우에만 작동(기본값 "NONE" [OFF])!
    # -----------------------------------------------------------------------
    if golden_allin_mode != "NONE" and is_golden_allin_time_window(
        hm, now_est=dt_now
    ):
        raw_cache = getattr(context, "candle_metrics_cache", {})
        base_met = (
            raw_cache.get(TARGET_SYMBOL)
            if isinstance(raw_cache, dict)
            else None
        )
        met = refresh_metrics_with_live_tick(base_met, live_p, now_est=dt_now)
        rsi_val = safe_float(met.get("rsi_14"), 50.0)
        # [Case 80]: 최소 14개 이상의 1분봉이 확보된 rsi_ready == True 만 엄격히 신뢰!
        rsi_ready = bool(met.get("rsi_ready", False))

        golden_sig = evaluate_golden_allin_signal(
            hm=hm,
            rsi_14=rsi_val,
            live_price=live_p,
            golden_allin_mode=golden_allin_mode,
            today_str=today_est_str,
            last_golden_allin_date=str(st.get("last_golden_allin_date") or ""),
            golden_pocket=gp,
            rsi_ready=rsi_ready,
        )
        if bool(golden_sig.get("should_buy")):
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

                    fresh_live_p = await _fetch_fresh_current_soxl_price(
                        context, fallback_price=live_p
                    )
                    if fresh_live_p <= 0.0:
                        return {"status": "NO_FRESH_LIVE_PRICE"}

                    met_fresh = refresh_metrics_with_live_tick(
                        base_met, fresh_live_p, now_est=dt_now
                    )
                    fresh_rsi = safe_float(met_fresh.get("rsi_14"), rsi_val)
                    fresh_rsi_ready = bool(
                        met_fresh.get("rsi_ready", rsi_ready)
                    )
                    now_gp = pocket_from_dict(st_now.get("golden_pocket"))
                    now_g_mode = (
                        str(
                            st_now.get("golden_allin_mode")
                            or DEFAULT_GOLDEN_ALLIN_MODE
                        )
                        .upper()
                        .strip()
                    )

                    re_g_sig = evaluate_golden_allin_signal(
                        hm=hm,
                        rsi_14=fresh_rsi,
                        live_price=fresh_live_p,
                        golden_allin_mode=now_g_mode,
                        today_str=today_est_str,
                        last_golden_allin_date=str(
                            st_now.get("last_golden_allin_date") or ""
                        ),
                        golden_pocket=now_gp,
                        rsi_ready=fresh_rsi_ready,
                    )
                    if bool(re_g_sig.get("should_buy")):
                        exec_order_p = max(
                            0.01,
                            math.floor((fresh_live_p + 1e-9) * 100.0) / 100.0,
                        )
                        now_buckets = buckets_from_dicts(
                            st_now.get("buckets", [])
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
                            safe_float(st_now.get("injected_reserve_usd"), 0.0),
                        )
                        now_inv_tot = sum(
                            b.actual_cost_usd for b in now_buckets
                        ) + (now_gp.actual_cost_usd if now_gp.is_active else 0.0)
                        now_core_eq = max(
                            now_init_seed,
                            (now_free_cash + now_inv_tot) - now_inj_res,
                        )
                        _, portion_budget_g = compute_golden8_quota_qty(
                            anchor_price=exec_order_p,
                            current_total_equity=now_core_eq,
                            initial_seed_usd=now_init_seed,
                            portion_mode=portion_mode,
                            exec_price=exec_order_p,
                        )

                        (
                            can_proceed_g,
                            eff_free_cash_g,
                            bp_usd_g,
                            guard_res_g,
                        ) = await _check_and_execute_guard30_or_reserve_injection(
                            context=context,
                            st_now=st_now,
                            exec_order_p=exec_order_p,
                            portion_budget=portion_budget_g,
                            l1_actual_cost_usd=0.0,
                            is_dip_promotion=False,
                            is_vacant_l1_reentry=False,
                            trigger_desc=(
                                f"황금시간({now_g_mode} · RSI {fresh_rsi:.1f}) 전액매수"
                            ),
                        )
                        if not can_proceed_g:
                            return {
                                "status": "HOLD_GOLDEN_GUARD30_WAITING_DEPOSIT",
                                "guard_eval": guard_res_g,
                            }

                        buy_qty_g, est_spent_g = (
                            resolve_allin_affordable_buy_qty(
                                price_t=exec_order_p,
                                free_cash_usd=eff_free_cash_g,
                                broker_buying_power_usd=(
                                    bp_usd_g if bp_usd_g > 0.0 else None
                                ),
                            )
                        )
                        if buy_qty_g > 0:
                            g_lot_type = str(
                                re_g_sig.get("lot_type") or "GOLDEN_POCKET"
                            )
                            cid_prefix = (
                                "GLDPKT"
                                if g_lot_type == "GOLDEN_POCKET"
                                else "GLDL1"
                            )
                            cid = generate_client_order_id(prefix=cid_prefix)
                            try:
                                ord_res = await context.api.create_order(
                                    symbol=TARGET_SYMBOL,
                                    side="BUY",
                                    quantity=buy_qty_g,
                                    price=exec_order_p,
                                    order_type="LIMIT",
                                    time_in_force="DAY",
                                    client_order_id=cid,
                                    enforce_daymarket_block=True,
                                )
                                oid = str(
                                    ord_res.get("orderId") or ""
                                ).strip()
                                # [Case 78 & Case 80]:
                                # 이미 활성 1층이 존재하는 상태에서 GOLDEN_L1 이 발주될 때는 기존 1층의 l1_target_quota_qty 를 유지하고
                                # 실제 체결 커밋 시점에 체결 수량으로 확정하여, 0주 미체결 취소 시 기존 1층 정량이 오염되지 않게 보호!
                                has_l1_g = has_active_l1_bucket(now_buckets)
                                prev_target_q_g = safe_int(
                                    st_now.get("l1_target_quota_qty"), 0
                                )
                                if (
                                    g_lot_type == "GOLDEN_POCKET"
                                    or has_l1_g
                                ):
                                    next_target_q_g = prev_target_q_g
                                else:
                                    next_target_q_g = buy_qty_g
                                await context.ledger.update_state(
                                    TARGET_SYMBOL,
                                    l1_target_quota_qty=next_target_q_g,
                                    last_golden_allin_date=today_est_str,
                                    buy_order_id=oid,
                                    client_order_id=cid,
                                    ordered_qty=buy_qty_g,
                                    buy_price=exec_order_p,
                                    pending_portion_budget=est_spent_g,
                                    pending_lot_type=g_lot_type,
                                    pending_step_up_min_price=0.0,
                                    last_modify_mono=time.monotonic(),
                                )
                                context.wakeup_event.set()
                                logger.info(
                                    "🌟 [Case 80 SOXL 황금시간(07:00~07:50 EST) RSI %.2f <= 19.0 가용시드 100%% 전액매수(%s) 발주] %d주 @ 지정가 $%.2f (예상원금 $%.2f · orderId=%s)",
                                    fresh_rsi,
                                    g_lot_type,
                                    buy_qty_g,
                                    exec_order_p,
                                    est_spent_g,
                                    oid,
                                )
                                return {
                                    "status": "GOLDEN_ALLIN_BUY_ORDERED",
                                    "mode": now_g_mode,
                                    "lot_type": g_lot_type,
                                    "rsi_14": fresh_rsi,
                                    "orderId": oid,
                                    "qty": buy_qty_g,
                                    "price": exec_order_p,
                                }
                            except Exception as exc:
                                logger.warning(
                                    "Case 80 황금시간 전액매수(%s) 주문 발주 예외: %s",
                                    g_lot_type,
                                    exc,
                                )
                                return {
                                    "status": "GOLDEN_ORDER_ERROR",
                                    "error": str(exc),
                                }

    is_zero_shares = bool(len(buckets) == 0 and (h_qty == 0 or h_qty == gp.qty))
    has_active_l1 = has_active_l1_bucket(buckets)
    # 🚨 Case 71, Case 72 & Case 73: 상단에 2층 ~ 7층 그리드(GRID_L2 ~ GRID_L7)가 남아 있고 1층이 익절되어 공석인 상태!
    is_l2_only_vacant_l1 = bool(len(buckets) > 0 and not has_active_l1)

    # -----------------------------------------------------------------------
    # [분기 A : 그리드 보유 잔고 0주 상태 (is_zero_shares)]
    # -> 0주 싸이클 종료 후 60.0초 타임쉴드 경과 확인 완료 뒤 실시간 현재가를 직접 조회하여 '현재가 지정가(LIMIT)'로 1층 산입!
    # -> 🛡️ [Case 84 핵심 방어] : 정규장 마감 30분 전(15:30 ~ 16:00 EST) 구간에서는 장 막판 랠리 고점 박제 및
    #    익일 급락 오버나이트 리스크를 원천 차단하기 위해 0주 새 사이클 첫 1층(REENTRY_1FL) 진입을 100% 금지한다!
    # -----------------------------------------------------------------------
    if is_zero_shares:
        # [Case 84 : 정규장 마감 30분 전(15:30 ~ 16:00 EST) 0주 새 사이클 첫 1층 진입 원천 차단]
        if is_late_regular_new_cycle_cutoff_window(hm, now_est=dt_now):
            return {
                "status": "HOLD_LATE_SESSION_NEW_CYCLE_CUTOFF",
                "hm": hm,
                "cutoff_hm": NEW_CYCLE_BUY_CUTOFF_HM,
            }

        # [Case 80]: 그리드가 0주인데 독립 골든포켓(gp.is_active)에 가용 현금 100%가 투입되어 있는 동안에는
        # 매 1.5초마다 불필요하게 시세 API를 재조회하지 않고 골든포켓(+1.50%) 익절로 현금이 환원될 때까지 조용히 대기한다!
        min_req_0sh_guard = max(
            live_p * (1.0 + ROUND_TRIP_FEE_RATE_PCT / 100.0),
            (core_equity * PORTION_RATIO_LOCKED) * MIN_DIP_BUDGET_RATIO,
        )
        if gp.is_active and free_cash < min_req_0sh_guard:
            return {
                "status": "HOLD_ZERO_GRID_CASH_IN_GOLDEN_POCKET",
                "golden_pocket_qty": gp.qty,
                "free_cash_usd": free_cash,
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
                    context, fallback_price=live_p
                )
                if fresh_live_p <= 0.0:
                    return {"status": "NO_FRESH_LIVE_PRICE"}

                exec_order_p = max(
                    0.01, math.floor((fresh_live_p + 1e-9) * 100.0) / 100.0
                )

                # 🚨 Case 67 & Case 77: 0주 진입 시 순수 코어 총자산 기준 min(1회분 상한, 기준가 정량) 적용
                prev_anchor_p = safe_float(st_now.get("anchor_price"), 0.0)
                ref_zero_anchor = (
                    prev_anchor_p if prev_anchor_p > 0.0 else exec_order_p
                )
                target_qty, portion_budget = compute_golden8_quota_qty(
                    anchor_price=ref_zero_anchor,
                    current_total_equity=core_equity,
                    initial_seed_usd=init_seed,
                    portion_mode=portion_mode,
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
    # [분기 B-1 · Case 73, Case 77 & Case 84 : 상단 그리드(2층 ~ 7층)만 보유 중 (1층 공석, is_l2_only_vacant_l1 == True)]
    # -> 2층 단가 상한 가드(HOLD_PREVENT_INVERSION) 하에서 눌림목(-1.00%) OR 상승돌파(+1.00%) 판정!
    # -> 🛡️ [Case 84 핵심 방어] : 정규장 마감 30분 전(15:30 ~ 16:00 EST) 구간에서는 +1.00% 상승돌파(BREAKOUT_RELOAD)
    #    추격 재장전만 핀포인트 차단(HOLD_LATE_SESSION_BREAKOUT_CUTOFF)하고, -1.00% 눌림목(PULLBACK_RELOAD) 재장전은 정상 허용!
    # -----------------------------------------------------------------------
    if is_l2_only_vacant_l1:
        in_re_shield, rem_re_sec = is_within_reentry_monitor_time_shield(
            context, st, TARGET_SYMBOL
        )
        if in_re_shield:
            return {
                "status": "HOLD_REENTRY_60S_TIME_SHIELD",
                "remain_shield_sec": rem_re_sec,
            }

        fresh_live_p = await _fetch_fresh_current_soxl_price(
            context, fallback_price=live_p
        )
        if fresh_live_p <= 0.0:
            return {"status": "NO_FRESH_LIVE_PRICE"}

        # 상단 최하단 층인 2층의 순수 매수 단가(min_upper_tier_price) 추출
        min_upper_tier_p = min(b.book_price for b in buckets)
        wma_info = compute_upper_2_to_7_moving_avg(buckets)
        upper_wma_p = safe_float(
            wma_info.get("upper_wma_price"), min_upper_tier_p
        )
        anchor_p = safe_float(st.get("anchor_price"), min_upper_tier_p)
        is_late_cutoff = is_late_regular_new_cycle_cutoff_window(
            hm, now_est=dt_now
        )

        # MODIFIED [Case 84]: 코어 판정기 evaluate_l2_only_hybrid_reentry_signal 에 is_late_new_cycle_cutoff 직접 주입
        reentry_sig = evaluate_l2_only_hybrid_reentry_signal(
            live_price=fresh_live_p,
            anchor_price=anchor_p,
            l2_book_price=min_upper_tier_p,
            min_upper_tier_price=min_upper_tier_p,
            is_late_new_cycle_cutoff=is_late_cutoff,
        )
        sig_type = str(reentry_sig.get("signal_type") or "HOLD_WAIT_GATE")

        if (
            sig_type == "HOLD_LATE_SESSION_BREAKOUT_CUTOFF"
            or (
                bool(reentry_sig.get("should_buy"))
                and sig_type == "BREAKOUT_RELOAD"
                and is_late_cutoff
            )
        ):
            new_pass_cnt = safe_int(st.get("seed_protect_pass_cnt"), 0) + 1
            new_day_pass = (
                safe_int(st.get("daily_seed_protect_pass_cnt"), 0) + 1
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
            logger.info(
                "🛡️ [Case 84 장마감 30분전(15:30~16:00) 1층 공석 +1%% 돌파 추격 차단] 현재가 $%.2f (직전익절 $%.2f 대비 %+.2f%%) -> 돌파 재장전 패스 & 눌림목(-1.0%%)만 허용 (60초 타임쉴드 재장전)",
                fresh_live_p,
                safe_float(reentry_sig.get("ref_anchor"), anchor_p),
                safe_float(reentry_sig.get("chg_from_exit_pct"), 0.0),
            )
            return {
                "status": "L2_ONLY_REENTRY_LATE_BREAKOUT_BLOCKED",
                "signal_type": "HOLD_LATE_SESSION_BREAKOUT_CUTOFF",
                "live_price": fresh_live_p,
                "l2_ceiling_price": min_upper_tier_p,
                "ref_anchor": reentry_sig.get("ref_anchor"),
                "chg_from_exit_pct": reentry_sig.get("chg_from_exit_pct"),
                "seed_protect_pass_cnt": new_day_pass,
                "next_reentry_check_sec": REENTRY_MONITOR_TIME_SHIELD_SEC,
            }

        if not bool(reentry_sig.get("should_buy")):
            new_pass_cnt = safe_int(st.get("seed_protect_pass_cnt"), 0) + 1
            new_day_pass = (
                safe_int(st.get("daily_seed_protect_pass_cnt"), 0) + 1
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
                    "l2_ceiling_price": min_upper_tier_p,
                    "ref_anchor": reentry_sig.get("ref_anchor"),
                    "chg_from_exit_pct": reentry_sig.get("chg_from_exit_pct"),
                    "seed_protect_pass_cnt": new_day_pass,
                    "next_reentry_check_sec": REENTRY_MONITOR_TIME_SHIELD_SEC,
                }
            return {
                "status": "L2_ONLY_REENTRY_HOLD_PASSED",
                "signal_type": sig_type,
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
                if in_re_m:
                    return {"status": "HOLD_60S_REENTRY_TIME_SHIELD_IN_MUTEX"}

                # [Case 84 뮤텍스 내부 2차 시각 재검문 : 15:30 ~ 16:00 EST 구간 BREAKOUT_RELOAD 원천 차단]
                dt_mutex = (
                    now_est.astimezone(EST_TZ)
                    if now_est
                    else datetime.now(EST_TZ)
                )
                hm_mutex = dt_mutex.hour * 100 + dt_mutex.minute
                if (
                    sig_type == "BREAKOUT_RELOAD"
                    and is_late_regular_new_cycle_cutoff_window(
                        hm_mutex, now_est=dt_mutex
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
                        "l2_ceiling_price": min(
                            b.book_price for b in now_buckets
                        ),
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

                now_gp = pocket_from_dict(st_now.get("golden_pocket"))
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
                now_inv_tot = sum(b.actual_cost_usd for b in now_buckets) + (
                    now_gp.actual_cost_usd if now_gp.is_active else 0.0
                )
                now_core_eq = max(
                    now_init_seed,
                    (now_free_cash + now_inv_tot) - now_inj_res,
                )

                quota_ref_p = max(
                    0.01,
                    safe_float(
                        reentry_sig.get("ref_anchor"),
                        anchor_p if anchor_p > 0.0 else exec_order_p,
                    ),
                )
                target_qty, portion_budget = compute_golden8_quota_qty(
                    anchor_price=quota_ref_p,
                    current_total_equity=now_core_eq,
                    initial_seed_usd=now_init_seed,
                    portion_mode=portion_mode,
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
                )
                if not can_proceed_re:
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
                    pending_lot_type="REENTRY_1FL",
                    pending_step_up_min_price=0.0,
                    last_modify_mono=time.monotonic(),
                    last_reentry_eval_ts=re_eval_epoch,
                )
                context.wakeup_event.set()
                logger.info(
                    "🔥 [SOXL 상단 %d개층 보유 중 60초 주기 현재가 지정가 1층 재장전(%s) 발주] %d주 @ 지정가 $%.2f <= 2층상한 $%.2f (1회예산 $%.2f · 직전익절 $%.2f · 이평 $%.2f · orderId=%s)",
                    len(now_buckets),
                    sig_type,
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
                    "orderId": oid,
                    "qty": buy_qty,
                    "price": exec_order_p,
                    "l2_ceiling_price": min_upper_tier_p,
                }

    # 원장 그리드가 비어 있으나(len(buckets) == 0) 실계좌 잔고(h_qty)와 일시 시차가 존재하는 경우 IndexError 원천 차단
    if not buckets or not has_active_l1:
        return {
            "status": "WAIT_HOLDINGS_RECONCILE_SYNC",
            "ledger_grid_qty": len(buckets),
            "broker_qty": h_qty,
            "pocket_qty": gp.qty,
        }

    # -----------------------------------------------------------------------
    # [분기 B-0 · Case 77, Case 78 & Case 80 : 활성 1층 부분 체결 미체결 잔량(rem_quota_qty > 0) 존재 시]
    # -> 이미 진입한 1층의 미체결 잔량이므로 15:30 ~ 16:00 EST 에도 100% 정상 보충 허용!
    # -----------------------------------------------------------------------
    l1_target_q = max(
        buckets[0].qty, safe_int(st.get("l1_target_quota_qty"), 0)
    )
    rem_quota_qty = max(0, l1_target_q - buckets[0].qty)
    l1_book_p = round(buckets[0].book_price, 2)

    if rem_quota_qty > 0 and live_p <= (l1_book_p + 1e-6):
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
                if in_s_sh or in_b_sh:
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
                            1.0 + ROUND_TRIP_FEE_RATE_PCT / 100.0
                        )
                        now_gp_top = pocket_from_dict(
                            st_now.get("golden_pocket")
                        )
                        if (
                            now_gp_top.is_active
                            and now_free_cash < one_share_top_cost
                        ):
                            mark_reserve_deposit_check_shield(
                                context=context,
                                symbol=TARGET_SYMBOL,
                                clear_shield=False,
                            )
                            return {
                                "status": "HOLD_TOPUP_CASH_IN_GOLDEN_POCKET",
                                "golden_pocket_qty": now_gp_top.qty,
                            }

                        # [Case 77 & Case 78 : 예수금 API 0.0 반환 시 0.25초 재시도 및 None 우회 422 루프 원천 차단]:
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

                        if raw_bp_top < one_share_top_cost:
                            mark_reserve_deposit_check_shield(
                                context=context,
                                symbol=TARGET_SYMBOL,
                                clear_shield=False,
                            )
                            return {
                                "status": "HOLD_TOPUP_INSUFFICIENT_BROKER_BP",
                                "broker_bp_usd": raw_bp_top,
                                "free_cash_usd": now_free_cash,
                            }

                        buy_qty_top, _ = resolve_affordable_buy_qty(
                            target_qty=now_rem_qty,
                            price_t=exec_order_p,
                            free_cash_usd=now_free_cash,
                            broker_buying_power_usd=raw_bp_top,
                            max_portion_budget_usd=topup_budget,
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

    # -----------------------------------------------------------------------
    # [분기 B-2 : 활성 1층 보유 중 (has_active_l1_bucket(buckets) == True)]
    # -> 04:07 EST 기점 10분 고정 매수 게이트 신규 버킷 도래 시 정적 기억 최저가 4단 와이드 OR STEP2X_15PCT_C20 스텝업 추매 판정!
    # -> 기보유 지층의 신저가/스텝업 추매이므로 15:30 ~ 16:00 EST 에도 100% 정상 가동!
    # -----------------------------------------------------------------------
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

    if not is_gate_open:
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

    fresh_live_p = await _fetch_fresh_current_soxl_price(
        context, fallback_price=live_p
    )
    if fresh_live_p <= 0.0:
        return {"status": "NO_FRESH_LIVE_PRICE"}

    held_lots = sum(b.lot_count for b in buckets)
    drop_buy_pct, _, _ = get_golden8_prog_thresholds(
        held_lots=held_lots, threshold_mode=threshold_mode
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
        realized_equity_usd=realized_equity,
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

    if not bool(dip_eval.get("should_buy")):
        # [Case 75 & Case 77]:
        # 이미 시드고갈 입금 대기(waiting_reserve_deposit == True) 상태에서 60초 주기로 깨어났는데
        # 가격이 일시 반등해 있는 경우에는 10분 버킷(last_evaluated_buy_bucket_id)을 소모하거나
        # 매 60초마다 패스 카운터를 디스크에 기록하지 않고 인메모리 60초 입금 감시 쉴드만 재장전한다!
        if bool(st.get("waiting_reserve_deposit", False)):
            mark_reserve_deposit_check_shield(
                context=context, symbol=TARGET_SYMBOL, clear_shield=False
            )
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
        return {
            "status": "SEED_PROTECT_PASSED",
            "trigger_tag": dip_eval.get("trigger_tag", "HOLD"),
            "ref_buy_anchor": round(ref_buy_anchor, 4),
            "chg_pct": round(chg_for_buy_pct, 2),
            "required_drop_pct": drop_buy_pct,
            "step_up_eligible": bool(dip_eval.get("step_up_eligible", False)),
            "stepped_min_price": safe_float(
                dip_eval.get("stepped_min_price"), 0.0
            ),
            "seed_protect_pass_cnt": new_day_pass,
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

            gate_open_m, _, _, _ = evaluate_buy_gate_bucket_status(
                now_est=dt_now,
                buy_interval_min=buy_interval_min,
                last_evaluated_bucket_id=safe_int(
                    st_now.get("last_evaluated_buy_bucket_id"), -1
                ),
                last_evaluated_date=str(
                    st_now.get("last_evaluated_date") or ""
                ),
            )
            if not gate_open_m:
                return {"status": "BUCKET_ALREADY_EVALUATED_IN_MUTEX"}

            in_s_sh, _ = is_within_post_sell_time_shield(
                context, st_now, TARGET_SYMBOL
            )
            in_b_sh, _ = is_within_post_buy_time_shield(
                context, st_now, TARGET_SYMBOL
            )
            if in_s_sh or in_b_sh:
                return {"status": "HOLD_60S_TIME_SHIELD_IN_MUTEX"}

            now_held_lots = sum(b.lot_count for b in now_buckets)
            now_drop_pct, _, _ = get_golden8_prog_thresholds(
                held_lots=now_held_lots, threshold_mode=threshold_mode
            )
            now_gp = pocket_from_dict(st_now.get("golden_pocket"))
            now_free_cash = max(0.0, safe_float(st_now.get("free_cash_usd"), 0.0))
            now_init_seed = max(
                100.0,
                safe_float(
                    st_now.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD
                ),
            )
            now_cum_net = safe_float(
                st_now.get("cumulative_realized_net_usd"), 0.0
            )
            now_inj_res = max(
                0.0, safe_float(st_now.get("injected_reserve_usd"), 0.0)
            )
            now_real_eq = max(100.0, now_init_seed + now_cum_net)
            now_inv_tot = sum(b.actual_cost_usd for b in now_buckets) + (
                now_gp.actual_cost_usd if now_gp.is_active else 0.0
            )
            now_core_eq = max(
                now_init_seed,
                (now_free_cash + now_inv_tot) - now_inj_res,
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
                realized_equity_usd=now_real_eq,
                step_up_drop_pct=eff_step_drop,
                min_cash_ratio=STEP_UP_2X_MIN_CASH_RATIO,
                min_rebound_mult=STEP_UP_2X_MIN_REBOUND_MULT,
                max_tiers_for_unlock=STEP_UP_2X_MAX_TIERS,
            )
            if not bool(now_dip_eval.get("should_buy")):
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
            exec_order_p = max(0.01, min(cur_limit_p, max_trigger_p))

            target_qty, portion_budget = compute_golden8_quota_qty(
                anchor_price=quota_ref_p,
                current_total_equity=now_core_eq,
                initial_seed_usd=now_init_seed,
                portion_mode=portion_mode,
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
                l1_actual_cost_usd=now_buckets[0].actual_cost_usd,
                is_dip_promotion=True,
                is_vacant_l1_reentry=False,
                trigger_desc=f"{now_held_lots + 1}회차 추매({trigger_tag})",
            )
            if not can_proceed_dip:
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
                l1_target_quota_qty=buy_qty,
                buy_order_id=oid,
                client_order_id=cid,
                ordered_qty=buy_qty,
                buy_price=exec_order_p,
                pending_portion_budget=portion_budget,
                pending_lot_type=lot_tag,
                pending_step_up_min_price=(
                    round(stepped_min_p, 4) if is_step_up_unlock else 0.0
                ),
                last_evaluated_buy_bucket_id=cur_bucket_id,
                last_evaluated_date=today_str,
                last_modify_mono=time.monotonic(),
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
                    "🔵 [SOXL %d회차 현재가 지정가 그리드 추매 발주] %d주 @ 지정가 $%.2f (기억저가 $%.2f 대비 %.2f%% · orderId=%s)",
                    now_held_lots + 1,
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
            }


# 하위 호환 별칭 (외부 모듈에서 구 함수명으로 호출하더라도 신규 게이트 엔진으로 안전 직결)
execute_premarket_vwap_sniper_plugin = execute_seed_protected_buy_gate_plugin
