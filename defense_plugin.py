# -*- coding: utf-8 -*-
"""
# MODIFIED: defense_plugin.py (Part 1/2 — 황금시간 07:00~07:50 RSI<=19 올인 전면 영구 소각 &
# 바벨 모드[BARBELL_60_30_10] 수동 매매 화해 시 별도 수익금고 영구 격리 · 0주 청산 시 60/30/10 자동 리밸런싱 ·
# SOXL 60% 초과/100% 수동 보유 시 바벨 시드고갈 자동 인식 &
# SOXL 0주 달성 시 [실전] 암살자 전환 예약 자동 인계 및 16:00 일일 결산 바벨 브리핑 탑재)
순수 롱(SOXL) 매수 04:07 ~ 16:00 EST 제한 & 익절 매도 24시간 전 세션 확장
오버나이트 7층 골디락스 본 그리드(L2_L7_MERGE_SORT · Case 87) ·
Default-ON 3층 서브 그리드(SUB_L1_L3_MERGE · Case 88) ·
3단 운용 모드(복리 COMP_08PCT ➔ 단리 SIMPLE_08PCT ➔ 바벨 BARBELL_60_30_10 · Case 91) 방어 및 결산 플러그인
"""

from __future__ import annotations

import asyncio
import gc
import logging
import math
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import assassin_plugin
from barbell_plugin import (
    BARBELL_SAFE_SYMBOL,
    ensure_barbell_ledger,
    execute_barbell_sgov_tick_plugin,
    initialize_or_sync_barbell_on_mode_enter,
    is_barbell_mode,
    record_barbell_realized_profit,
    summarize_barbell_status,
)
from quant_engine import (
    BARBELL_SOXL_WEIGHT,
    BASE_MAX_LOTS_8PCT,
    DEFAULT_GRID_MERGE_MODE,
    MAX_GRID_TIERS_7,
    MAX_GRID_TIERS_12,
    MAX_RESERVE_PORTIONS,
    PORTION_MODE_BARBELL,
    PORTION_MODE_COMPOUND,
    PORTION_MODE_SIMPLE,
    SUB_FROZEN_DAYS_TRIGGER,
    SUB_MAX_TIERS_3,
    SUB_MAX_TOTAL_LOTS_4,
    SUB_MERGE_MODE_L1_L3,
    StratumBucket,
    buckets_from_dicts,
    buckets_to_dicts,
    calc_sell_realized_pnl,
    compute_reserve_repayment_on_zero,
    enforce_true_breakeven_floor_on_buckets,
    has_active_l1_bucket,
    is_simple_income_mode,
    match_and_remove_sold_buckets_7tier,
    relabel_sub_upper_grid_tiers,
    relabel_upper_grid_tiers,
    resolve_effective_round_trip_fee_rate_pct,
    resolve_portion_budget_base_equity,
    summarize_stratum_portfolio,
    vrev_add_quota_lot_and_merge_2tier,
)
from quant_indicators_plugin import (
    NEW_CYCLE_BUY_CUTOFF_HM,
    is_extended_sell_only_window,
    is_late_regular_new_cycle_cutoff_window,
)
from sniper_exit_plugin import (
    is_within_post_sell_time_shield,
    mark_extended_sell_restriction_cooldown,
    mark_post_sell_time_shield,
    reset_sniper_l1_trail_slots,
    sync_pending_sell_order_plugin,
)
from sniper_plugin import (
    is_within_auto_fill_grace_shield,
    mark_auto_fill_grace_shield,
    mark_reentry_monitor_60s_cycle_shield,
    mark_reserve_deposit_check_shield,
    mark_sub_reentry_monitor_60s_cycle_shield,
    sync_pending_buy_order_plugin,
)
from toss_api import (
    DEFAULT_INITIAL_SEED_USD,
    EST_TZ,
    TARGET_SYMBOL,
    get_folder_slug,
    safe_float,
    safe_int,
)

logger = logging.getLogger("toss_sniper.defense_plugin")

KRW_PER_USD_DEFAULT: float = 1380.0


def _resolve_valid_seed_from_state(st: Dict[str, Any]) -> float:
    """
    🚨 Case 68:
    상태 딕셔너리에서 initial_seed_usd 를 읽을 때 0.0 또는 비정상 $100 초기값으로 인해
    시드가 $100 으로 축소되는 현상을 방어한다.
    """
    raw_seed = safe_float(st.get("initial_seed_usd"), 0.0)
    explicit_100 = bool(st.get("seed_explicitly_set_100", False))
    if raw_seed > 100.0:
        return round(raw_seed, 4)
    if abs(raw_seed - 100.0) < 1e-6 and explicit_100:
        return 100.0
    return DEFAULT_INITIAL_SEED_USD


async def _probe_manual_fill_price_safe(
    context: Any,
    side: str,
    target_qty: int,
    st: Dict[str, Any],
    fallback_price: float,
) -> Tuple[float, List[str]]:
    """
    # [Case 19 & Case 63]:
    토스 GET /api/v1/orders?status=CLOSED&symbol=SOXL 에서 미정산 수동 체결 단가와 orderId 목록을 역추적한다.
    """
    settled_oids: List[str] = list(st.get("last_settled_order_ids") or [])
    if hasattr(context, "api") and hasattr(
        context.api, "last_probed_manual_fee_usd"
    ):
        context.api.last_probed_manual_fee_usd = 0.0
    probe_fn = getattr(context.api, "probe_latest_manual_fill_price", None)
    if callable(probe_fn):
        try:
            exec_p, matched_ids = await probe_fn(
                side=side,
                target_qty=target_qty,
                settled_order_ids=settled_oids,
                fallback_price=fallback_price,
                symbol=TARGET_SYMBOL,
            )
            if safe_float(exec_p, 0.0) > 0.0:
                for mid in matched_ids or []:
                    s_mid = str(mid or "").strip()
                    if s_mid and s_mid not in settled_oids:
                        settled_oids.append(s_mid)
                return (
                    round(safe_float(exec_p, fallback_price), 4),
                    settled_oids[-50:],
                )
        except Exception as exc:
            logger.debug("수동 체결 단가 역추적 폴백 사용(%s): %s", side, exc)
    return (
        round(max(0.01, safe_float(fallback_price, 0.01)), 4),
        settled_oids[-50:],
    )


def _get_last_probed_manual_fee(context: Any) -> Optional[float]:
    api_obj = getattr(context, "api", None)
    if api_obj is not None:
        f_val = safe_float(
            getattr(api_obj, "last_probed_manual_fee_usd", 0.0), 0.0
        )
        if f_val > 0.0:
            return round(f_val, 4)
    return None


async def _sync_barbell_sgov_holdings_if_idle(
    context: Any,
    holdings: Dict[str, Dict[str, Any]],
) -> None:
    """
    바벨 모드 가동 중 미체결 SGOV 주문이 없을 때 사용자가 토스 앱에서 SGOV를 수동 매수/매도한 경우
    바벨 원장의 SGOV 보유 수량 및 원금을 실계좌와 무결성 동기화한다.
    """
    if not isinstance(holdings, dict) or BARBELL_SAFE_SYMBOL not in holdings:
        return
    b_ledger = ensure_barbell_ledger(context)
    bst = b_ledger.get_state()
    if str(bst.get("sgov_buy_order_id") or "").strip() or str(
        bst.get("sgov_sell_order_id") or ""
    ).strip():
        return
    # MODIFIED: VM 재부팅 시 last_sgov_action_mono 역전으로 인한 영구 스킵 방지
    now_sg_m = time.monotonic()
    last_sg_m = safe_float(bst.get("last_sgov_action_mono"), 0.0)
    if 0.0 < last_sg_m <= now_sg_m and (now_sg_m - last_sg_m) < 15.0:
        return

    sg_h = holdings.get(BARBELL_SAFE_SYMBOL)
    if not isinstance(sg_h, dict):
        return
    h_sg_qty = max(0, safe_int(sg_h.get("qty"), 0))
    l_sg_qty = max(0, safe_int(bst.get("sgov_held_qty"), 0))
    sg_last = safe_float(sg_h.get("last_price"), 0.0)

    upd_sg: Dict[str, Any] = {}
    if sg_last > 1.0 and abs(
        sg_last - safe_float(bst.get("sgov_last_price"), 0.0)
    ) > 0.01:
        upd_sg["sgov_last_price"] = round(sg_last, 4)

    if h_sg_qty != l_sg_qty:
        old_sg_inv = (
            safe_float(bst.get("sgov_invested_usd"), 0.0)
            if l_sg_qty > 0
            else 0.0
        )
        cur_cash_b = max(0.0, safe_float(bst.get("cash_bucket_usd"), 0.0))
        cur_pend_b = max(
            0.0, safe_float(bst.get("pending_sgov_buy_budget_usd"), 0.0)
        )
        st_soxl_sg = context.ledger.get_state(TARGET_SYMBOL)
        init_seed_sg = max(
            100.0,
            safe_float(
                st_soxl_sg.get("initial_seed_usd"),
                safe_float(bst.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD),
            ),
        )
        sgov_30_sg = round(init_seed_sg * 0.30, 4)
        cash_10_sg = round(init_seed_sg * 0.10, 4)
        rt_sg = resolve_effective_round_trip_fee_rate_pct(
            state_dict=st_soxl_sg
        )
        # MODIFIED [Case 100]: 수동 SGOV 매도 동기화 시 합산 유동성 100% 1회분 회복 기준으로 매도예약 해제
        guard_floor_sg = round(
            init_seed_sg * 0.60 * 0.08 * (1.0 + rt_sg / 100.0), 4
        )
        soxl_free_sg = max(
            0.0, safe_float(st_soxl_sg.get("free_cash_usd"), 0.0)
        )

        if h_sg_qty <= 0:
            new_sg_inv = 0.0
            upd_sg["sgov_held_qty"] = 0
            upd_sg["sgov_avg_price"] = 0.0
            upd_sg["sgov_invested_usd"] = 0.0
            upd_sg["pending_sgov_tranche_sells"] = 0
        else:
            sg_avg = safe_float(sg_h.get("avg_price"), 100.30)
            sg_pur = safe_float(
                sg_h.get("purchase_amount"), float(h_sg_qty) * sg_avg
            )
            new_sg_inv = round(max(1.0, sg_pur), 4)
            upd_sg["sgov_held_qty"] = h_sg_qty
            upd_sg["sgov_invested_usd"] = new_sg_inv
            upd_sg["sgov_avg_price"] = round(
                new_sg_inv / float(h_sg_qty), 4
            )

        if h_sg_qty < l_sg_qty:
            freed_sg_usd = max(0.0, old_sg_inv - new_sg_inv)
            max_liq_sg = max(
                0.0, (cash_10_sg + sgov_30_sg) - new_sg_inv - cur_pend_b
            )
            next_cash_sg = round(min(max_liq_sg, cur_cash_b + freed_sg_usd), 4)
            upd_sg["cash_bucket_usd"] = next_cash_sg
            if (soxl_free_sg + next_cash_sg + cur_pend_b) >= (
                guard_floor_sg - 1e-6
            ):
                upd_sg["pending_sgov_tranche_sells"] = 0
                upd_sg["sgov_wait_alert_sent"] = False
        else:
            added_sg_usd = max(0.0, new_sg_inv - old_sg_inv)
            take_pend = min(cur_pend_b, added_sg_usd)
            rem_take = max(0.0, added_sg_usd - take_pend)
            next_pend_sg = round(
                min(
                    max(0.0, cur_pend_b - take_pend),
                    max(0.0, sgov_30_sg - new_sg_inv),
                ),
                4,
            )
            next_cash_sg = round(max(0.0, cur_cash_b - rem_take), 4)
            ref_sg_p = (
                sg_last
                if sg_last > 1.0
                else max(1.0, safe_float(bst.get("sgov_last_price"), 100.30))
            )
            if 0.0 < next_pend_sg < (ref_sg_p * 1.002):
                next_cash_sg = round(next_cash_sg + next_pend_sg, 4)
                next_pend_sg = 0.0
            upd_sg["pending_sgov_buy_budget_usd"] = next_pend_sg
            upd_sg["cash_bucket_usd"] = next_cash_sg

    if upd_sg:
        await b_ledger.update_state(**upd_sg)


# ---------------------------------------------------------------------------
# [핵심 1] 로컬 7층 본 그리드 + Default-ON 3층 서브 그리드 원장 ↔ 토스 실보유 잔고 무결성 화해
# ---------------------------------------------------------------------------
async def reconcile_stratum_with_broker_holdings_plugin(
    context: Any,
    holdings: Dict[str, Dict[str, Any]],
    prices: Dict[str, float],
    now_est: Optional[datetime] = None,
    force_sync: bool = False,
) -> Dict[str, Any]:
    if not isinstance(holdings, dict) or not getattr(
        context, "holdings_fetch_ok", True
    ):
        return {"status": "SKIP_HOLDINGS_NOT_READY"}

    st = context.ledger.get_state(TARGET_SYMBOL)
    portion_mode = (
        str(st.get("portion_mode") or PORTION_MODE_COMPOUND).upper().strip()
    )
    is_barbell = is_barbell_mode(portion_mode)
    is_simple_mode = (not is_barbell) and is_simple_income_mode(portion_mode)

    if is_barbell:
        try:
            await _sync_barbell_sgov_holdings_if_idle(context, holdings)
        except Exception as sg_exc:
            logger.debug("바벨 SGOV 수동잔고 동기화 스킵: %s", sg_exc)

    pending_buy_oid = str(st.get("buy_order_id") or "").strip()
    pending_sell_oid = str(st.get("sell_order_id") or "").strip()

    if not force_sync and (pending_buy_oid or pending_sell_oid):
        if pending_buy_oid:
            try:
                await sync_pending_buy_order_plugin(
                    context=context,
                    holdings=holdings,
                    prices=prices,
                    now_est=now_est,
                )
            except Exception as exc:
                logger.debug("Case 66 미결 매수 선행 동기화 예외(묵음): %s", exc)
        if pending_sell_oid:
            try:
                await sync_pending_sell_order_plugin(
                    context=context,
                    holdings=holdings,
                    prices=prices,
                    now_est=now_est,
                )
            except Exception as exc:
                logger.debug("Case 66 미결 매도 선행 동기화 예외(묵음): %s", exc)
        return {
            "status": "SKIP_RECONCILE_BOT_ORDER_PENDING",
            "buy_order_id": pending_buy_oid,
            "sell_order_id": pending_sell_oid,
        }

    buckets = enforce_true_breakeven_floor_on_buckets(
        buckets_from_dicts(st.get("buckets", []))
    )
    sub_buckets = enforce_true_breakeven_floor_on_buckets(
        buckets_from_dicts(st.get("sub_buckets", []))
    )
    grid_qty = sum(b.qty for b in buckets)
    sub_qty = sum(sb.qty for sb in sub_buckets)
    ledger_qty = grid_qty + sub_qty
    eff_rt_pct = resolve_effective_round_trip_fee_rate_pct(state_dict=st)
    eff_merge_mode = str(
        st.get("grid_merge_mode") or DEFAULT_GRID_MERGE_MODE
    ).upper()
    eff_sub_merge_mode = str(
        st.get("sub_merge_mode") or SUB_MERGE_MODE_L1_L3
    ).upper()

    h_info = holdings.get(TARGET_SYMBOL, {})
    h_qty = max(0, safe_int(h_info.get("qty"), 0))
    h_avg = round(max(0.0, safe_float(h_info.get("avg_price"), 0.0)), 4)
    h_pur = round(
        max(
            0.0,
            safe_float(h_info.get("purchase_amount"), float(h_qty) * h_avg),
        ),
        4,
    )
    live_p = safe_float(
        (prices or {}).get(TARGET_SYMBOL),
        safe_float(h_info.get("last_price"), h_avg),
    )

    if pending_buy_oid or pending_sell_oid:
        open_orders = await context.api.get_open_orders(symbol=TARGET_SYMBOL)
        if open_orders:
            return {
                "status": "SKIP_OPEN_ORDER_ACTIVE",
                "open_count": len(open_orders),
            }

    # [케이스 1] 수량이 완벽히 일치하는 경우 -> 즉시 통과 (0주 상태에서 실전 암살자 전환 예약이 걸려 있으면 즉시 인계)
    if h_qty == ledger_qty:
        if h_qty == 0:
            activate_fn = getattr(
                assassin_plugin,
                "activate_live_assassin_on_zero_soxl_if_armed",
                None,
            )
            if callable(activate_fn):
                try:
                    await activate_fn(context)
                except Exception:
                    pass
        return {
            "status": "STRATUM_IN_SYNC",
            "held_shares": h_qty,
            "grid_shares": grid_qty,
            "sub_shares": sub_qty,
            "tiers": len(buckets),
            "sub_tiers": len(sub_buckets),
        }

    # 🚨 [Case 61, Case 69 & Case 88 최상단 양방향 15.0초 인덱싱 그레이스 쉴드]
    if is_within_auto_fill_grace_shield(context, TARGET_SYMBOL):
        logger.info(
            "🛡️ [Case 61/69/88 양방향 인덱싱 그레이스 쉴드 작동] 최근 자동 체결 직후 잔고 API 시차 감지(토스 %d주 vs 원장 %d주[본 %d+서브 %d]) -> 원장 무결성 안전 보호",
            h_qty,
            ledger_qty,
            grid_qty,
            sub_qty,
        )
        return {
            "status": "PROTECTED_BY_AUTO_FILL_GRACE_SHIELD",
            "held_shares": ledger_qty,
            "broker_shares": h_qty,
        }

    open_orders = await context.api.get_open_orders(symbol=TARGET_SYMBOL)
    if open_orders:
        return {
            "status": "WAIT_OPEN_ORDER_SETTLEMENT",
            "open_count": len(open_orders),
        }

    # [케이스 2] 토스 실보유 0주인데 로컬 원장에 지층이 남아 있는 경우 (수동 전량 청산)
    if h_qty == 0 and ledger_qty > 0:
        default_fb_p = (
            buckets[0].actual_avg_price
            if buckets
            else (sub_buckets[0].actual_avg_price if sub_buckets else 50.0)
        )
        fb_sell_p = (
            live_p
            if live_p > 0.0
            else (safe_float(st.get("anchor_price"), 0.0) or default_fb_p)
        )
        (
            manual_sell_p,
            updated_settled_oids,
        ) = await _probe_manual_fill_price_safe(
            context=context,
            side="SELL",
            target_qty=ledger_qty,
            st=st,
            fallback_price=fb_sell_p,
        )
        probed_fee = _get_last_probed_manual_fee(context)

        match_res = match_and_remove_sold_buckets_7tier(
            buckets=buckets,
            delta_remove_qty=ledger_qty,
            sell_exec_price=manual_sell_p,
            max_tiers=MAX_GRID_TIERS_7,
            round_trip_fee_rate_pct=eff_rt_pct,
            actual_sell_fee_usd=probed_fee,
            merge_mode=eff_merge_mode,
            sub_buckets=sub_buckets,
            sub_max_tiers=SUB_MAX_TIERS_3,
            sub_merge_mode=eff_sub_merge_mode,
        )
        pnl_info = match_res["pnl_info"]
        gross_pnl = safe_float(pnl_info.get("gross_pnl_usd"), 0.0)
        fee_usd = safe_float(pnl_info.get("fee_usd"), 0.0)
        net_pnl = safe_float(pnl_info.get("net_pnl_usd"), 0.0)
        net_rate = safe_float(pnl_info.get("net_rate_pct"), 0.0)

        sold_sub_q = safe_int(match_res.get("sold_sub_qty"), 0)
        sold_sub_cost = safe_float(match_res.get("sold_sub_cost_usd"), 0.0)
        sub_sell_inc = 1 if sold_sub_q > 0 else 0
        sub_gross_pnl = 0.0
        sub_fee_usd = 0.0
        sub_net_pnl = 0.0
        if sold_sub_q > 0 and sold_sub_cost > 0.0:
            sub_fee_part: Optional[float] = None
            if probed_fee is not None and ledger_qty > 0:
                sub_fee_part = round(
                    probed_fee * (float(sold_sub_q) / float(ledger_qty)), 4
                )
            s_pnl = calc_sell_realized_pnl(
                sold_qty=sold_sub_q,
                sell_exec_price=manual_sell_p,
                sold_actual_cost_usd=sold_sub_cost,
                round_trip_fee_rate_pct=eff_rt_pct,
                actual_sell_fee_usd=sub_fee_part,
            )
            sub_gross_pnl = safe_float(s_pnl.get("gross_pnl_usd"), 0.0)
            sub_fee_usd = safe_float(s_pnl.get("fee_usd"), 0.0)
            sub_net_pnl = safe_float(s_pnl.get("net_pnl_usd"), 0.0)

        tot_sell_ev = safe_int(st.get("total_sell_events"), 0) + 1
        tot_sold_sh = safe_int(st.get("total_sold_shares"), 0) + ledger_qty
        win_ev = safe_int(st.get("win_sell_events"), 0) + (
            1 if net_pnl > 0.0 else 0
        )
        day_sell_ev = safe_int(st.get("daily_sell_events"), 0) + 1
        day_main_sell_cnt = safe_int(st.get("daily_main_sell_cnt"), 0) + (
            1 if grid_qty > 0 else 0
        )

        wma_inc_zero = (
            1
            if (grid_qty > 0 and bool(match_res.get("sold_upper_tier")))
            else 0
        )
        wma_cnt = safe_int(st.get("wma_grad_sell_cnt"), 0) + wma_inc_zero
        day_wma_cnt = (
            safe_int(st.get("daily_wma_grad_sell_cnt"), 0) + wma_inc_zero
        )

        sub_sell_ev = safe_int(st.get("sub_sell_events"), 0) + sub_sell_inc
        sub_sold_sh = safe_int(st.get("sub_sold_shares"), 0) + sold_sub_q
        day_sub_sell_cnt = (
            safe_int(st.get("daily_sub_sell_cnt"), 0) + sub_sell_inc
        )
        day_sub_sell_ev = (
            safe_int(st.get("daily_sub_sell_events"), 0) + sub_sell_inc
        )
        sub_comp_cycles = safe_int(st.get("sub_completed_cycles"), 0) + (
            1 if sub_qty > 0 else 0
        )
        sub_gross_cum = round(
            safe_float(st.get("sub_realized_gross_usd"), 0.0) + sub_gross_pnl,
            4,
        )
        sub_fee_cum = round(
            safe_float(st.get("sub_realized_fee_usd"), 0.0) + sub_fee_usd, 4
        )
        sub_net_cum = round(
            safe_float(st.get("sub_realized_net_usd"), 0.0) + sub_net_pnl, 4
        )
        sub_net_day = round(
            safe_float(st.get("daily_sub_realized_net_usd"), 0.0)
            + sub_net_pnl,
            4,
        )

        cum_gross = round(
            safe_float(st.get("cumulative_realized_gross_usd"), 0.0)
            + gross_pnl,
            4,
        )
        cum_fee = round(
            safe_float(st.get("cumulative_realized_fee_usd"), 0.0) + fee_usd, 4
        )
        cum_net = round(
            safe_float(st.get("cumulative_realized_net_usd"), 0.0) + net_pnl, 4
        )
        day_net = round(
            safe_float(st.get("daily_realized_net_usd"), 0.0) + net_pnl, 4
        )

        # MODIFIED: 수동 부분손절 후 전량매도 시 사이클 순흑자 초과분만 금고 격리
        prev_cyc_z = safe_float(st.get("cycle_realized_net_usd"), 0.0)
        vault_delta_z = round(
            max(0.0, net_pnl + min(0.0, prev_cyc_z)), 4
        )
        prev_vault_locked = max(
            0.0, safe_float(st.get("vaulted_profit_locked_usd"), 0.0)
        )
        next_vault_locked = (
            round(prev_vault_locked + vault_delta_z, 4)
            if is_barbell
            else prev_vault_locked
        )

        final_cyc_net = round(prev_cyc_z + net_pnl, 4)
        final_cyc_ev = max(0, safe_int(st.get("cycle_sell_events"), 0)) + 1
        next_comp_main_cycles = (
            max(0, safe_int(st.get("completed_main_cycles"), 0)) + 1
        )

        init_seed = _resolve_valid_seed_from_state(st)
        cur_inj_res_usd = max(
            0.0, safe_float(st.get("injected_reserve_usd"), 0.0)
        )
        cur_used_res_cnt = max(
            0, safe_int(st.get("used_reserve_portions_cnt"), 0)
        )
        cum_repaid_usd = max(
            0.0, safe_float(st.get("cumulative_reserve_repaid_usd"), 0.0)
        )
        repaid_this_time = 0.0
        next_inj_res_usd = cur_inj_res_usd
        next_used_res_cnt = cur_used_res_cnt

        if (not is_barbell) and cur_inj_res_usd > 0.0:
            repay_info = compute_reserve_repayment_on_zero(
                initial_seed_usd=init_seed,
                cumulative_realized_net_usd=cum_net,
                injected_reserve_usd=cur_inj_res_usd,
                used_reserve_portions_cnt=cur_used_res_cnt,
                max_reserve_portions=MAX_RESERVE_PORTIONS,
                portion_mode=portion_mode,
                vaulted_profit_locked_usd=next_vault_locked,
            )
            if bool(repay_info.get("did_repay")):
                repaid_this_time = round(
                    safe_float(repay_info.get("repaid_usd"), 0.0), 4
                )
                next_inj_res_usd = round(
                    safe_float(
                        repay_info.get("rem_injected_reserve_usd"), 0.0
                    ),
                    4,
                )
                next_used_res_cnt = max(
                    0,
                    safe_int(
                        repay_info.get("rem_used_reserve_portions_cnt"), 0
                    ),
                )
                cum_repaid_usd = round(cum_repaid_usd + repaid_this_time, 4)

        now_zero_ts = time.time()
        mark_post_sell_time_shield(
            context=context,
            symbol=TARGET_SYMBOL,
            fill_price=manual_sell_p,
            sold_qty=ledger_qty,
            is_cycle_end=True,
        )
        mark_reentry_monitor_60s_cycle_shield(
            context=context,
            symbol=TARGET_SYMBOL,
            eval_price=manual_sell_p,
            clear_shield=True,
        )
        mark_sub_reentry_monitor_60s_cycle_shield(
            context=context,
            symbol=TARGET_SYMBOL,
            eval_price=manual_sell_p,
            clear_shield=True,
        )
        mark_reserve_deposit_check_shield(
            context=context,
            symbol=TARGET_SYMBOL,
            clear_shield=True,
        )
        updated_st = await context.ledger.update_state(
            TARGET_SYMBOL,
            buckets=[],
            sub_buckets=[],
            anchor_price=manual_sell_p,
            cycle_min_buy_price=0.0,
            cycle_ratchet_max_lots=0,
            ratchet_anchor_price=manual_sell_p,
            cycle_reanchor_credit_usd=0.0,
            l1_target_quota_qty=0,
            sub_anchor_price=manual_sell_p,
            sub_cycle_min_buy_price=0.0,
            sub_ratchet_max_lots=0,
            sub_l1_target_quota_qty=0,
            main_consec_frozen_days=0,
            sub_consec_frozen_days=0,
            daily_main_sell_cnt=day_main_sell_cnt,
            wma_grad_sell_cnt=wma_cnt,
            daily_wma_grad_sell_cnt=day_wma_cnt,
            sub_sell_events=sub_sell_ev,
            sub_sold_shares=sub_sold_sh,
            daily_sub_sell_cnt=day_sub_sell_cnt,
            daily_sub_sell_events=day_sub_sell_ev,
            sub_completed_cycles=sub_comp_cycles,
            sub_realized_gross_usd=sub_gross_cum,
            sub_realized_fee_usd=sub_fee_cum,
            sub_realized_net_usd=sub_net_cum,
            daily_sub_realized_net_usd=sub_net_day,
            used_reserve_portions_cnt=next_used_res_cnt,
            injected_reserve_usd=next_inj_res_usd,
            cumulative_reserve_repaid_usd=cum_repaid_usd,
            vaulted_profit_locked_usd=next_vault_locked,
            waiting_reserve_deposit=False,
            waiting_reserve_deposit_alert_sent=False,
            required_reserve_deposit_usd=0.0,
            last_reserve_check_ts=0.0,
            last_sell_fill_ts=now_zero_ts,
            last_cycle_end_ts=now_zero_ts,
            last_sub_sell_fill_ts=now_zero_ts,
            last_sub_cycle_end_ts=now_zero_ts,
            last_sell_gate_eval_ts=0.0,
            last_reentry_eval_ts=0.0,
            last_sub_reentry_eval_ts=0.0,
            buy_order_id="",
            sell_order_id="",
            ordered_qty=0,
            target_sell_price=0.0,
            pending_sell_mode="",
            pending_sell_indices=[],
            pending_sub_sell_indices=[],
            pending_lot_type="",
            pending_step_up_min_price=0.0,
            pending_sub_step_up_min_price=0.0,
            last_settled_order_ids=updated_settled_oids,
            total_sell_events=tot_sell_ev,
            total_sold_shares=tot_sold_sh,
            win_sell_events=win_ev,
            daily_sell_events=day_sell_ev,
            cumulative_realized_gross_usd=cum_gross,
            cumulative_realized_fee_usd=cum_fee,
            cumulative_realized_net_usd=cum_net,
            daily_realized_net_usd=day_net,
            cycle_realized_gross_usd=0.0,
            cycle_realized_fee_usd=0.0,
            cycle_realized_net_usd=0.0,
            cycle_sub_realized_net_usd=0.0,
            cycle_sell_events=0,
            cycle_leftover_saved_usd=0.0,
            last_cycle_realized_net_usd=final_cyc_net,
            last_cycle_sell_events=final_cyc_ev,
            completed_main_cycles=next_comp_main_cycles,
        )

        barbell_vault_total = next_vault_locked
        if is_barbell:
            b_rec = await record_barbell_realized_profit(
                context=context,
                net_pnl_usd=vault_delta_z,  # MODIFIED: 유령현금 이중계상 차단
                is_graduated_zero=True,
                prev_soxl_injected_usd=cur_inj_res_usd,
                prev_soxl_used_portions_cnt=cur_used_res_cnt,
                cycle_realized_net_override=final_cyc_net,
            )
            barbell_vault_total = safe_float(
                b_rec.get("vault_realized_profit_usd"), next_vault_locked
            )
            repaid_this_time = safe_float(
                b_rec.get("repaid_from_soxl_usd"), 0.0
            )
            updated_st = context.ledger.get_state(TARGET_SYMBOL)

        switched_to_live_assassin = False
        activate_fn = getattr(
            assassin_plugin, "activate_live_assassin_on_zero_soxl_if_armed", None
        )
        if callable(activate_fn):
            try:
                switched_to_live_assassin = bool(await activate_fn(context))
            except Exception:
                pass

        free_cash_now = safe_float(updated_st.get("free_cash_usd"), 0.0)
        logger.info(
            "🧹 [SOXL 수동 전량청산 0주 싸이클 종료 & 실현익 정산] %d주 @ $%.2f (매칭층: %s · 세후손익 %+.2f$ · 가용현금 $%.2f)",
            ledger_qty,
            manual_sell_p,
            match_res.get("sold_tier_desc"),
            net_pnl,
            free_cash_now,
        )
        if hasattr(context, "send_slim_alert"):
            s_sign = "+" if net_pnl >= 0.0 else "-"
            r_sign = "+" if net_rate >= 0.0 else ""
            cyc_sign = "+" if final_cyc_net >= 0.0 else "-"
            cum_sign = "+" if cum_net >= 0.0 else "-"
            repay_note = ""
            if is_barbell:
                repay_note = f" · ⚖️바벨 60/30/10 리밸런싱 완료(별도금고 +${barbell_vault_total:,.2f})"
            elif repaid_this_time > 0.0:
                repay_note = (
                    f" · 💉예비시드 원금 ${repaid_this_time:,.2f} 자동상환"
                    f"(잔여수혈 {next_used_res_cnt}회분 · ${next_inj_res_usd:,.2f})"
                )

            dt_chk = (
                now_est.astimezone(EST_TZ)
                if now_est
                else datetime.now(EST_TZ)
            )
            hm_chk = dt_chk.hour * 100 + dt_chk.minute
            is_ext_now = is_extended_sell_only_window(hm_chk, now_est=dt_chk)
            will_hit_late_cutoff = bool(
                is_late_regular_new_cycle_cutoff_window(hm_chk, now_est=dt_chk)
                or (
                    dt_chk.weekday() < 5
                    and hm_chk == (NEW_CYCLE_BUY_CUTOFF_HM - 1)
                    and dt_chk.second >= 1
                )
            )
            if switched_to_live_assassin:
                next_entry_note = "🗡️[실전] 암살자 모드 자동 전환 완료! (보유 SGOV는 수동매도 위임)"
            elif is_ext_now:
                next_entry_note = (
                    "🔒장외 매수잠금 · 04:07 EST 프리장 개시 후 새 1층 진입 대기"
                )
            elif will_hit_late_cutoff:
                next_entry_note = "🔒장마감 30분전(15:30 ~ 16:00) 새 사이클 진입 차단 · 익일 04:07 EST 프리장 새 1층 진입 대기"
            else:
                next_entry_note = "🛡️04:07 ~ 15:29 EST 매수구간 내 60초 타임쉴드 후 새 1층 진입 대기"

            if is_barbell:
                credit_note = f"별도 수익금고 영구격리(⚖️바벨 · 누적금고 +${barbell_vault_total:,.2f})"
            elif is_simple_mode:
                credit_note = f"현금금고 적립(💵인출형 · 당일실현 +${max(0.0, day_net):,.2f} 인출가능!)"
            else:
                credit_note = "시드 복리산입 완료"

            await context.send_slim_alert(
                title=f"🧹 [SOXL 수동 전량매도 0주 동기화] {ledger_qty}주 @ ${manual_sell_p:.2f} ({r_sign}{net_rate:.2f}%)",
                body=(
                    f"소진층: {match_res.get('sold_tier_desc')} · "
                    f"세후순익 {s_sign}${abs(net_pnl):,.2f} {credit_note} · "
                    f"🏆이번 사이클 최종수익: {cyc_sign}${abs(final_cyc_net):,.2f} (총 {final_cyc_ev}회 익절 ➔ 새 사이클 $0.00 리셋!) · "
                    f"💰전체 누적실현익: {cum_sign}${abs(cum_net):,.2f} (누적 {next_comp_main_cycles}회 졸업){repay_note} · "
                    f"가용현금 ${free_cash_now:,.2f} ({next_entry_note})"
                ),
            )
        return {
            "status": "CLEARED_TO_ZERO_HOLDINGS",
            "prev_qty": ledger_qty,
            "manual_sell_price": manual_sell_p,
            "net_pnl_usd": net_pnl,
            "last_cycle_realized_net_usd": final_cyc_net,
            "completed_main_cycles": next_comp_main_cycles,
            "repaid_reserve_usd": repaid_this_time,
            "switched_to_live_assassin": switched_to_live_assassin,
            "free_cash_usd": free_cash_now,
        }

    # [케이스 3] 토스 실보유 수량(h_qty > 0)이 존재하는데 로컬 원장이 비어 있는 경우
    if h_qty > 0 and ledger_qty == 0:
        in_sell_sh, rem_sell_s = is_within_post_sell_time_shield(
            context, st, TARGET_SYMBOL
        )
        if not force_sync and in_sell_sh:
            logger.info(
                "🛡️ [Case 65/69 0주 졸업 타임쉴드 사수] 매도 후 60초 타임쉴드 가동 중(잔여 %.1f초) -> 잔고 시차(h_qty=%d) 무시 및 0주 유지",
                rem_sell_s,
                h_qty,
            )
            return {
                "status": "PROTECTED_BY_POST_SELL_ZERO_SHIELD",
                "remain_shield_sec": rem_sell_s,
            }

        vault_st: Optional[Dict[str, Any]] = None
        recover_fn = getattr(
            context.ledger, "recover_from_backup_vault_sync", None
        )
        if callable(recover_fn):
            try:
                vault_st = await asyncio.to_thread(recover_fn)
            except Exception as exc:
                logger.debug("백업 금고 조회 예외(무시): %s", exc)

        if isinstance(vault_st, dict):
            vault_buckets = enforce_true_breakeven_floor_on_buckets(
                buckets_from_dicts(vault_st.get("buckets", []))
            )
            vault_sub_buckets = enforce_true_breakeven_floor_on_buckets(
                buckets_from_dicts(vault_st.get("sub_buckets", []))
            )
            vault_qty = sum(b.qty for b in vault_buckets) + sum(
                sb.qty for sb in vault_sub_buckets
            )
            vault_seed = _resolve_valid_seed_from_state(vault_st)

            is_fresh_empty_ledger = bool(
                safe_int(st.get("total_buy_events"), 0) == 0
                and safe_int(st.get("total_sell_events"), 0) == 0
                and safe_int(st.get("completed_main_cycles"), 0) == 0
                and safe_float(st.get("last_cycle_end_ts"), 0.0) <= 0.0
            )
            vault_not_older = bool(
                safe_int(vault_st.get("total_sell_events"), 0)
                >= safe_int(st.get("total_sell_events"), 0)
                and safe_int(vault_st.get("completed_main_cycles"), 0)
                >= safe_int(st.get("completed_main_cycles"), 0)
            )
            if (
                (is_fresh_empty_ledger or vault_not_older)
                and vault_qty == h_qty
                and (len(vault_buckets) > 0 or len(vault_sub_buckets) > 0)
            ):
                vault_lots = sum(max(1, b.lot_count) for b in vault_buckets)
                vault_ratchet_lots = (
                    max(
                        vault_lots,
                        safe_int(vault_st.get("cycle_ratchet_max_lots"), 0),
                    )
                    if vault_buckets
                    else 0
                )
                vault_sub_lots = sum(
                    max(1, sb.lot_count) for sb in vault_sub_buckets
                )
                vault_sub_ratchet_lots = (
                    max(
                        vault_sub_lots,
                        safe_int(vault_st.get("sub_ratchet_max_lots"), 0),
                    )
                    if vault_sub_buckets
                    else 0
                )
                restored_kw: Dict[str, Any] = dict(vault_st)
                restored_kw["buckets"] = buckets_to_dicts(vault_buckets)
                restored_kw["sub_buckets"] = buckets_to_dicts(vault_sub_buckets)
                restored_kw["initial_seed_usd"] = vault_seed
                restored_kw["cycle_ratchet_max_lots"] = vault_ratchet_lots
                restored_kw["sub_ratchet_max_lots"] = vault_sub_ratchet_lots
                restored_kw["cycle_reanchor_credit_usd"] = 0.0
                restored_kw["buy_order_id"] = ""
                restored_kw["sell_order_id"] = ""
                restored_kw["ordered_qty"] = 0
                restored_kw["pending_sell_indices"] = []
                restored_kw["pending_sub_sell_indices"] = []
                restored_kw["pending_step_up_min_price"] = 0.0
                restored_kw["pending_sub_step_up_min_price"] = 0.0
                if has_active_l1_bucket(vault_buckets):
                    restored_kw["last_reentry_eval_ts"] = 0.0
                    restored_kw["l1_target_quota_qty"] = max(
                        vault_buckets[0].qty,
                        safe_int(vault_st.get("l1_target_quota_qty"), 0),
                    )
                else:
                    restored_kw["l1_target_quota_qty"] = 0

                if has_active_l1_bucket(vault_sub_buckets):
                    restored_kw["last_sub_reentry_eval_ts"] = 0.0
                    restored_kw["sub_l1_target_quota_qty"] = max(
                        vault_sub_buckets[0].qty,
                        safe_int(vault_st.get("sub_l1_target_quota_qty"), 0),
                    )
                else:
                    restored_kw["sub_l1_target_quota_qty"] = 0

                reset_sniper_l1_trail_slots(
                    context, grid_kind="ALL", symbol=TARGET_SYMBOL
                )
                await context.ledger.update_state(TARGET_SYMBOL, **restored_kw)
                return {
                    "status": "RESTORED_FROM_BACKUP_VAULT",
                    "held_shares": h_qty,
                    "tiers": len(vault_buckets),
                    "sub_tiers": len(vault_sub_buckets),
                    "cycle_ratchet_max_lots": vault_ratchet_lots,
                    "sub_ratchet_max_lots": vault_sub_ratchet_lots,
                }

        ref_p = h_avg if h_avg > 0.0 else (live_p if live_p > 0.0 else 100.0)
        (
            probed_0sh_p,
            updated_settled_oids,
        ) = await _probe_manual_fill_price_safe(
            context=context,
            side="BUY",
            target_qty=h_qty,
            st=st,
            fallback_price=ref_p,
        )
        if h_pur > 0.0:
            cost_u = round(h_pur, 4)
            pure_ref_p = round(cost_u / float(h_qty), 4)
        else:
            pure_ref_p = (
                round(probed_0sh_p, 4)
                if probed_0sh_p > 0.0
                else round(ref_p, 4)
            )
            cost_u = round(float(h_qty) * pure_ref_p, 4)

        init_seed = _resolve_valid_seed_from_state(st)
        if isinstance(vault_st, dict) and init_seed <= 100.0:
            init_seed = _resolve_valid_seed_from_state(vault_st)

        default_0sh_pool = (
            round(init_seed * BARBELL_SOXL_WEIGHT, 4)
            if is_barbell
            else init_seed
        )
        cur_free_cash_0sh = max(
            0.0, safe_float(st.get("free_cash_usd"), default_0sh_pool)
        )
        cur_inj_res_0sh = max(
            0.0, safe_float(st.get("injected_reserve_usd"), 0.0)
        )
        cur_used_res_0sh = max(
            0, safe_int(st.get("used_reserve_portions_cnt"), 0)
        )
        base_eq_0sh = resolve_portion_budget_base_equity(
            initial_seed_usd=init_seed,
            core_equity_usd=max(
                default_0sh_pool, cur_free_cash_0sh - cur_inj_res_0sh
            ),
            portion_mode=portion_mode,
        )
        est_p_unit_0sh = max(1.0, base_eq_0sh * 0.08)
        if cost_u > (cur_free_cash_0sh + 0.01):
            excess_0sh_usd = round(cost_u - cur_free_cash_0sh, 4)
            next_inj_res_0sh = round(cur_inj_res_0sh + excess_0sh_usd, 4)
            add_p_cnt_0sh = max(
                1, int(math.ceil((excess_0sh_usd - 1e-9) / est_p_unit_0sh))
            )
            next_used_res_0sh = max(1, cur_used_res_0sh + add_p_cnt_0sh)
        else:
            next_inj_res_0sh = cur_inj_res_0sh
            next_used_res_0sh = cur_used_res_0sh

        est_lots = max(1, int(round(cost_u / est_p_unit_0sh)))
        restored_bucket = StratumBucket(
            qty=h_qty,
            book_price=pure_ref_p,
            book_invested_usd=cost_u,
            actual_cost_usd=cost_u,
            lot_count=est_lots,
            lot_type="QUOTA_L1",
        )
        now_sync_ts = time.time()
        mark_auto_fill_grace_shield(
            context=context,
            symbol=TARGET_SYMBOL,
            lot_type="QUOTA_L1",
            fill_price=pure_ref_p,
            filled_qty=h_qty,
        )
        mark_reentry_monitor_60s_cycle_shield(
            context=context,
            symbol=TARGET_SYMBOL,
            eval_price=pure_ref_p,
            clear_shield=True,
        )
        mark_sub_reentry_monitor_60s_cycle_shield(
            context=context,
            symbol=TARGET_SYMBOL,
            eval_price=pure_ref_p,
            clear_shield=True,
        )
        mark_reserve_deposit_check_shield(
            context=context,
            symbol=TARGET_SYMBOL,
            clear_shield=True,
        )
        tot_buy_ev_0sh = safe_int(st.get("total_buy_events"), 0) + 1
        tot_buy_sh_0sh = safe_int(st.get("total_buy_shares"), 0) + h_qty
        day_buy_ev_0sh = safe_int(st.get("daily_buy_events"), 0) + 1
        day_main_buy_0sh = safe_int(st.get("daily_main_buy_cnt"), 0) + 1

        update_kw: Dict[str, Any] = {
            "initial_seed_usd": init_seed,
            "buckets": buckets_to_dicts([restored_bucket]),
            "sub_buckets": [],
            "anchor_price": pure_ref_p,
            "cycle_min_buy_price": pure_ref_p,
            "cycle_ratchet_max_lots": est_lots,
            "ratchet_anchor_price": pure_ref_p,
            "cycle_reanchor_credit_usd": 0.0,
            "l1_target_quota_qty": h_qty,
            "sub_anchor_price": 0.0,
            "sub_cycle_min_buy_price": 0.0,
            "sub_ratchet_max_lots": 0,
            "sub_l1_target_quota_qty": 0,
            "main_consec_frozen_days": 0,
            "sub_consec_frozen_days": 0,
            "injected_reserve_usd": next_inj_res_0sh,
            "used_reserve_portions_cnt": next_used_res_0sh,
            "total_buy_events": tot_buy_ev_0sh,
            "total_buy_shares": tot_buy_sh_0sh,
            "daily_buy_events": day_buy_ev_0sh,
            "daily_main_buy_cnt": day_main_buy_0sh,
            "buy_order_id": "",
            "sell_order_id": "",
            "ordered_qty": 0,
            "pending_sell_indices": [],
            "pending_sub_sell_indices": [],
            "pending_step_up_min_price": 0.0,
            "pending_sub_step_up_min_price": 0.0,
            "waiting_reserve_deposit": False,
            "waiting_reserve_deposit_alert_sent": False,
            "required_reserve_deposit_usd": 0.0,
            "last_reserve_check_ts": 0.0,
            "last_settled_order_ids": updated_settled_oids,
            "entry_ts": now_sync_ts,
            "last_buy_fill_ts": now_sync_ts,
            "last_reentry_eval_ts": 0.0,
            "last_sub_reentry_eval_ts": 0.0,
        }
        is_ledger_brand_new = bool(
            safe_int(st.get("total_buy_events"), 0) == 0
            and safe_int(st.get("total_sell_events"), 0) == 0
            and safe_int(st.get("completed_main_cycles"), 0) == 0
            and safe_float(st.get("last_cycle_end_ts"), 0.0) <= 0.0
        )
        if isinstance(vault_st, dict) and is_ledger_brand_new:
            for stat_k in (
                "vaulted_profit_locked_usd",
                "us_commission_rate",
                "round_trip_fee_rate_pct",
                "cumulative_realized_net_usd",
                "cumulative_realized_gross_usd",
                "cumulative_realized_fee_usd",
                "cumulative_leftover_saved_usd",
                "cumulative_reanchor_drop_usd",
                "last_cycle_realized_net_usd",
                "last_cycle_sell_events",
                "completed_main_cycles",
                "reanchor_cnt",
                "indiv_grid_sell_cnt",
                "wma_grad_sell_cnt",
                "seed_protect_pass_cnt",
                "cond_unlock_buy_events",
                "sub_buy_events",
                "sub_buy_shares",
                "sub_sell_events",
                "sub_sold_shares",
                "sub_merge_events",
                "sub_merged_indiv_escape_cnt",
                "sub_unlock_events",
                "sub_completed_cycles",
                "sub_realized_gross_usd",
                "sub_realized_fee_usd",
                "sub_realized_net_usd",
                "total_reserve_injected_cnt",
                "cumulative_reserve_repaid_usd",
                "dust_guard_blocked_cnt",
                "extra_13plus_buy_events",
                "total_buy_events",
                "total_sell_events",
                "win_sell_events",
            ):
                if safe_float(st.get(stat_k), 0.0) == 0.0 and safe_float(
                    vault_st.get(stat_k), 0.0
                ) != 0.0:
                    update_kw[stat_k] = vault_st[stat_k]

        updated_st = await context.ledger.update_state(
            TARGET_SYMBOL, **update_kw
        )
        if is_barbell_mode(updated_st.get("portion_mode")):
            await initialize_or_sync_barbell_on_mode_enter(
                context=context, holdings_map=holdings
            )
            updated_st = context.ledger.get_state(TARGET_SYMBOL)

        summary_0sh = summarize_stratum_portfolio(
            updated_st, live_price=pure_ref_p
        )
        l1_target_0sh = safe_float(summary_0sh.get("l1_target_price"), 0.0)
        free_cash_0sh = safe_float(summary_0sh.get("free_cash_usd"), 0.0)
        trig_buy_0sh = safe_float(summary_0sh.get("trigger_buy_price"), 0.0)
        drop_req_0sh = safe_float(summary_0sh.get("drop_buy_pct"), -1.0)

        if hasattr(context, "send_slim_alert"):
            await context.send_slim_alert(
                title=f"➕ [SOXL 수동 신규매수 1층 동기화] {h_qty}주 @ ${pure_ref_p:.2f}",
                body=(
                    f"실투입 원금 ${cost_u:,.2f} ({est_lots}회차분) · "
                    f"🛡️60초 타임쉴드 후 1층 익절목표 ${l1_target_0sh:.2f}(+1.5%) ⚡1.5초 실시간 감시! · "
                    f"기억저가 ${pure_ref_p:.2f} 잠금(와이드 {drop_req_0sh:.1f}% 추매가 ${trig_buy_0sh:.2f}) · "
                    f"가용현금 ${free_cash_0sh:,.2f}"
                ),
            )
        return {
            "status": "RESTORED_FROM_BROKER_HOLDINGS",
            "held_shares": h_qty,
            "avg_price": pure_ref_p,
        }
    # [케이스 4] 토스 실보유 수량(h_qty > 0)과 로컬 원장 수량(ledger_qty > 0)이 부분 불일치하는 경우
    if h_qty > ledger_qty:
        delta_q = h_qty - ledger_qty
        fb_buy_p = live_p if live_p > 0.0 else h_avg
        if fb_buy_p <= 0.0:
            fb_buy_p = (
                buckets[0].actual_avg_price
                if buckets
                else (
                    sub_buckets[0].actual_avg_price
                    if sub_buckets
                    else 50.0
                )
            )

        est_buy_p, updated_settled_oids = await _probe_manual_fill_price_safe(
            context=context,
            side="BUY",
            target_qty=delta_q,
            st=st,
            fallback_price=fb_buy_p,
        )
        prev_had_active_l1 = has_active_l1_bucket(buckets)
        prev_l1_p = buckets[0].book_price if buckets else 0.0
        added_spent_usd = round(float(delta_q) * est_buy_p, 4)

        init_seed_add = _resolve_valid_seed_from_state(st)
        cur_free_cash_add = max(0.0, safe_float(st.get("free_cash_usd"), 0.0))
        cur_inj_res_add = max(
            0.0, safe_float(st.get("injected_reserve_usd"), 0.0)
        )
        cur_used_res_add = max(
            0, safe_int(st.get("used_reserve_portions_cnt"), 0)
        )
        cur_inv_tot_add = sum(b.actual_cost_usd for b in buckets) + sum(
            sb.actual_cost_usd for sb in sub_buckets
        )
        min_core_floor = (
            init_seed_add * BARBELL_SOXL_WEIGHT
            if is_barbell
            else init_seed_add
        )
        core_eq_add = max(
            min_core_floor,
            (cur_free_cash_add + cur_inv_tot_add) - cur_inj_res_add,
        )
        base_eq_add = resolve_portion_budget_base_equity(
            initial_seed_usd=init_seed_add,
            core_equity_usd=core_eq_add,
            portion_mode=portion_mode,
        )
        if added_spent_usd > (cur_free_cash_add + 0.01):
            excess_add_usd = round(added_spent_usd - cur_free_cash_add, 4)
            next_inj_res_add = round(cur_inj_res_add + excess_add_usd, 4)
            est_p_unit_add = max(1.0, base_eq_add * 0.08)
            add_p_cnt = max(
                1, int(math.ceil((excess_add_usd - 1e-9) / est_p_unit_add))
            )
            next_used_res_add = max(1, cur_used_res_add + add_p_cnt)
        else:
            next_inj_res_add = cur_inj_res_add
            next_used_res_add = cur_used_res_add

        merged_buckets = vrev_add_quota_lot_and_merge_2tier(
            queue=buckets,
            buy_qty=delta_q,
            buy_price=est_buy_p,
            actual_spent_usd=added_spent_usd,
            lot_type="MANUAL_SYNC_L1",
            max_tiers=MAX_GRID_TIERS_7,
            merge_mode=eff_merge_mode,
        )

        is_mid_tier_inserted = bool(
            prev_had_active_l1
            and est_buy_p > (prev_l1_p + 1e-6)
            and merged_buckets
            and abs(merged_buckets[0].book_price - prev_l1_p) < 1e-4
        )
        if merged_buckets and has_active_l1_bucket(merged_buckets):
            if is_mid_tier_inserted:
                next_l1_target_q_manual = max(
                    merged_buckets[0].qty,
                    safe_int(st.get("l1_target_quota_qty"), 0),
                )
            else:
                next_l1_target_q_manual = merged_buckets[0].qty
        else:
            next_l1_target_q_manual = 0

        new_held_lots = sum(max(1, b.lot_count) for b in merged_buckets)
        new_ratchet_lots = max(
            new_held_lots, safe_int(st.get("cycle_ratchet_max_lots"), 0)
        )
        tot_buy_ev_add = safe_int(st.get("total_buy_events"), 0) + 1
        tot_buy_sh_add = safe_int(st.get("total_buy_shares"), 0) + delta_q
        day_buy_ev_add = safe_int(st.get("daily_buy_events"), 0) + 1
        day_main_buy_cnt = safe_int(st.get("daily_main_buy_cnt"), 0) + 1
        extra_13_add = safe_int(st.get("extra_13plus_buy_events"), 0) + (
            1 if new_held_lots > BASE_MAX_LOTS_8PCT else 0
        )

        # MODIFIED: 1층 공석 유지 상태에서 상단층 수동 편입 시 기존 재장전 anchor_price 보존
        eff_l1_anchor_p = (
            merged_buckets[0].book_price
            if (merged_buckets and has_active_l1_bucket(merged_buckets))
            else (
                safe_float(st.get("anchor_price"), 0.0)
                or (
                    merged_buckets[0].book_price
                    if merged_buckets
                    else est_buy_p
                )
            )
        )
        old_min_p = safe_float(st.get("cycle_min_buy_price"), 0.0)
        new_min_p = (
            min(old_min_p, est_buy_p) if old_min_p > 0.0 else est_buy_p
        )
        now_sync_ts = time.time()
        mark_auto_fill_grace_shield(
            context=context,
            symbol=TARGET_SYMBOL,
            lot_type="MANUAL_SYNC_L1",
            fill_price=est_buy_p,
            filled_qty=delta_q,
        )
        mark_reentry_monitor_60s_cycle_shield(
            context=context,
            symbol=TARGET_SYMBOL,
            eval_price=est_buy_p,
            clear_shield=True,
        )
        mark_reserve_deposit_check_shield(
            context=context,
            symbol=TARGET_SYMBOL,
            clear_shield=True,
        )
        updated_st = await context.ledger.update_state(
            TARGET_SYMBOL,
            buckets=buckets_to_dicts(merged_buckets),
            anchor_price=eff_l1_anchor_p,
            cycle_min_buy_price=round(new_min_p, 4),
            cycle_ratchet_max_lots=new_ratchet_lots,
            ratchet_anchor_price=eff_l1_anchor_p,
            cycle_reanchor_credit_usd=0.0,
            l1_target_quota_qty=next_l1_target_q_manual,
            main_consec_frozen_days=0,
            injected_reserve_usd=next_inj_res_add,
            used_reserve_portions_cnt=next_used_res_add,
            total_buy_events=tot_buy_ev_add,
            total_buy_shares=tot_buy_sh_add,
            daily_buy_events=day_buy_ev_add,
            daily_main_buy_cnt=day_main_buy_cnt,
            extra_13plus_buy_events=extra_13_add,
            pending_step_up_min_price=0.0,
            waiting_reserve_deposit=False,
            waiting_reserve_deposit_alert_sent=False,
            required_reserve_deposit_usd=0.0,
            last_reserve_check_ts=0.0,
            last_settled_order_ids=updated_settled_oids,
            entry_ts=now_sync_ts,
            last_buy_fill_ts=now_sync_ts,
            last_reentry_eval_ts=0.0,
        )
        if is_barbell:
            await initialize_or_sync_barbell_on_mode_enter(
                context=context, holdings_map=holdings
            )
            updated_st = context.ledger.get_state(TARGET_SYMBOL)

        summary_add = summarize_stratum_portfolio(
            updated_st, live_price=est_buy_p
        )
        l1_target_add = safe_float(summary_add.get("l1_target_price"), 0.0)
        u_cnt_add = safe_int(summary_add.get("upper_tier_count"), 0)
        u_qty_add = safe_int(summary_add.get("upper_qty"), 0)
        u_wma_p_add = safe_float(summary_add.get("upper_wma_price"), 0.0)
        u_wma_t_add = safe_float(summary_add.get("upper_wma_target_price"), 0.0)
        free_cash_add = safe_float(summary_add.get("free_cash_usd"), 0.0)

        logger.info(
            "➕ [SOXL 수동 추가매수 7층 본그리드 단가비교 편입 완료] +%d주 @ $%.2f 반영 -> 총 %d주(본 %d개층·보유%d/잠금%d회차 + 서브 %d주)",
            delta_q,
            est_buy_p,
            h_qty,
            len(merged_buckets),
            new_held_lots,
            new_ratchet_lots,
            sub_qty,
        )
        if hasattr(context, "send_slim_alert"):
            if not prev_had_active_l1:
                pos_desc = (
                    "공석 1층 독립 편입(상단 비병합)"
                    if has_active_l1_bucket(merged_buckets)
                    else f"1층 공석 유지 · 상단 2~{len(merged_buckets) + 1}층 단가비교 편입"
                )
            elif is_mid_tier_inserted:
                pos_desc = f"상단 2~{len(merged_buckets)}층 단가비교 중간편입"
            else:
                pos_desc = "새 1층 배치(기존층 상단승격/L2+L7중간합병)"

            upper_add_note = (
                f" · 2~{len(merged_buckets)}층({u_cnt_add}개층·{u_qty_add}주) 이평 ${u_wma_p_add:.2f}(목표 ${u_wma_t_add:.2f})"
                if len(merged_buckets) >= 2
                else ""
            )
            sub_add_note = f"+서브 {sub_qty}주" if sub_qty > 0 else ""
            ratchet_add_note = (
                f"(단차잠금 {new_ratchet_lots}회차)"
                if new_ratchet_lots > new_held_lots
                else ""
            )
            await context.send_slim_alert(
                title=(
                    f"➕ [SOXL 수동 추가매수 그리드 편입] "
                    f"+{delta_q}주 @ ${est_buy_p:.2f} (총 {h_qty}주 · {len(merged_buckets)}개층{sub_add_note})"
                ),
                body=(
                    f"편입위치: {pos_desc} (추가원금 ${added_spent_usd:,.2f}) · "
                    f"🛡️60초 타임쉴드 후 1층목표 ${l1_target_add:.2f}(+1.5%) 감시{upper_add_note} · "
                    f"기억저가 ${new_min_p:.2f}{ratchet_add_note} 잠금 · 가용현금 ${free_cash_add:,.2f}"
                ),
            )
        return {
            "status": "SYNCED_MANUAL_BUY_ADDITION",
            "added_qty": delta_q,
            "buy_price": est_buy_p,
            "held_shares": h_qty,
            "tiers": len(merged_buckets),
            "cycle_ratchet_max_lots": new_ratchet_lots,
            "l1_target_quota_qty": next_l1_target_q_manual,
        }

    # 4-2) h_qty < ledger_qty (수동 부분 매도 또는 체결 후 잔여 수량 조정):
    delta_remove = ledger_qty - h_qty
    orig_l1_qty = (
        buckets[0].qty
        if (buckets and has_active_l1_bucket(buckets))
        else 0
    )
    orig_sub_l1_qty = (
        sub_buckets[0].qty
        if (sub_buckets and has_active_l1_bucket(sub_buckets))
        else 0
    )
    default_part_p = (
        buckets[0].actual_avg_price
        if buckets
        else (
            sub_buckets[0].actual_avg_price
            if sub_buckets
            else 50.0
        )
    )
    fb_part_sell_p = live_p if live_p > 0.0 else default_part_p
    manual_sell_p, updated_settled_oids = await _probe_manual_fill_price_safe(
        context=context,
        side="SELL",
        target_qty=delta_remove,
        st=st,
        fallback_price=fb_part_sell_p,
    )
    probed_part_fee = _get_last_probed_manual_fee(context)

    match_res = match_and_remove_sold_buckets_7tier(
        buckets=buckets,
        delta_remove_qty=delta_remove,
        sell_exec_price=manual_sell_p,
        max_tiers=MAX_GRID_TIERS_7,
        round_trip_fee_rate_pct=eff_rt_pct,
        actual_sell_fee_usd=probed_part_fee,
        merge_mode=eff_merge_mode,
        sub_buckets=sub_buckets,
        sub_max_tiers=SUB_MAX_TIERS_3,
        sub_merge_mode=eff_sub_merge_mode,
    )
    rem_buckets: List[StratumBucket] = match_res["rem_buckets"]
    rem_sub_buckets: List[StratumBucket] = match_res.get("rem_sub_buckets", [])
    sold_sub_q = safe_int(match_res.get("sold_sub_qty"), 0)
    sold_sub_cost = safe_float(match_res.get("sold_sub_cost_usd"), 0.0)
    sold_sub_merged_flag = bool(match_res.get("sold_sub_merged_bucket", False))
    sold_main_q = sum(b.qty for b in match_res.get("sold_buckets", []))
    sold_main_upper_flag = bool(match_res.get("sold_upper_tier", False))

    pnl_info = match_res["pnl_info"]
    gross_pnl = safe_float(pnl_info.get("gross_pnl_usd"), 0.0)
    fee_usd = safe_float(pnl_info.get("fee_usd"), 0.0)
    net_pnl = safe_float(pnl_info.get("net_pnl_usd"), 0.0)
    net_rate = safe_float(pnl_info.get("net_rate_pct"), 0.0)

    sub_sell_inc = 1 if sold_sub_q > 0 else 0
    sub_gross_pnl = 0.0
    sub_fee_usd = 0.0
    sub_net_pnl = 0.0
    if sold_sub_q > 0 and sold_sub_cost > 0.0:
        sub_fee_part2: Optional[float] = None
        if probed_part_fee is not None and delta_remove > 0:
            sub_fee_part2 = round(
                probed_part_fee * (float(sold_sub_q) / float(delta_remove)), 4
            )
        s_pnl = calc_sell_realized_pnl(
            sold_qty=sold_sub_q,
            sell_exec_price=manual_sell_p,
            sold_actual_cost_usd=sold_sub_cost,
            round_trip_fee_rate_pct=eff_rt_pct,
            actual_sell_fee_usd=sub_fee_part2,
        )
        sub_gross_pnl = safe_float(s_pnl.get("gross_pnl_usd"), 0.0)
        sub_fee_usd = safe_float(s_pnl.get("fee_usd"), 0.0)
        sub_net_pnl = safe_float(s_pnl.get("net_pnl_usd"), 0.0)

    rem_has_l1 = has_active_l1_bucket(rem_buckets)
    if (
        not rem_buckets
        or not rem_has_l1
        or bool(match_res.get("sold_l1_completely"))
    ):
        next_l1_target_q = 0
    elif orig_l1_qty > 0 and rem_buckets[0].qty < orig_l1_qty:
        next_l1_target_q = rem_buckets[0].qty
    else:
        next_l1_target_q = max(
            rem_buckets[0].qty, safe_int(st.get("l1_target_quota_qty"), 0)
        )

    rem_sub_has_l1 = has_active_l1_bucket(rem_sub_buckets)
    if (
        not rem_sub_buckets
        or not rem_sub_has_l1
        or bool(match_res.get("sold_sub_l1_completely"))
    ):
        next_sub_l1_target_q = 0
    elif orig_sub_l1_qty > 0 and rem_sub_buckets[0].qty < orig_sub_l1_qty:
        next_sub_l1_target_q = rem_sub_buckets[0].qty
    else:
        next_sub_l1_target_q = max(
            rem_sub_buckets[0].qty,
            safe_int(st.get("sub_l1_target_quota_qty"), 0),
        )

    prev_ratchet_lots = max(0, safe_int(st.get("cycle_ratchet_max_lots"), 0))
    rem_held_lots = sum(max(1, b.lot_count) for b in rem_buckets)
    next_ratchet_lots = (
        max(rem_held_lots, prev_ratchet_lots) if rem_buckets else 0
    )

    prev_sub_ratchet_lots = max(0, safe_int(st.get("sub_ratchet_max_lots"), 0))
    rem_sub_held_lots = sum(max(1, sb.lot_count) for sb in rem_sub_buckets)
    next_sub_ratchet_lots = (
        max(rem_sub_held_lots, prev_sub_ratchet_lots) if rem_sub_buckets else 0
    )

    tot_sell_ev = safe_int(st.get("total_sell_events"), 0) + 1
    tot_sold_sh = safe_int(st.get("total_sold_shares"), 0) + delta_remove
    win_ev = safe_int(st.get("win_sell_events"), 0) + (
        1 if net_pnl > 0.0 else 0
    )
    day_sell_ev = safe_int(st.get("daily_sell_events"), 0) + 1
    day_main_sell_cnt = safe_int(st.get("daily_main_sell_cnt"), 0) + (
        1 if sold_main_q > 0 else 0
    )
    next_main_frozen_d = (
        0
        if (sold_main_q > 0 or not rem_buckets)
        else max(0, safe_int(st.get("main_consec_frozen_days"), 0))
    )

    rem_upper_cnt_part = (
        max(0, len(rem_buckets) - (1 if rem_has_l1 else 0))
        if rem_buckets
        else 0
    )
    if sold_main_upper_flag and sold_main_q > 0:
        if rem_upper_cnt_part == 0:
            wma_inc_part = 1
            indiv_inc_part = 0
        else:
            wma_inc_part = 0
            indiv_inc_part = 1
    else:
        wma_inc_part = 0
        indiv_inc_part = 0

    indiv_cnt = safe_int(st.get("indiv_grid_sell_cnt"), 0) + indiv_inc_part
    day_indiv_cnt = (
        safe_int(st.get("daily_indiv_grid_sell_cnt"), 0) + indiv_inc_part
    )
    wma_cnt = safe_int(st.get("wma_grad_sell_cnt"), 0) + wma_inc_part
    day_wma_cnt = (
        safe_int(st.get("daily_wma_grad_sell_cnt"), 0) + wma_inc_part
    )

    sub_sell_ev = safe_int(st.get("sub_sell_events"), 0) + sub_sell_inc
    sub_sold_sh = safe_int(st.get("sub_sold_shares"), 0) + sold_sub_q
    day_sub_sell_cnt = (
        safe_int(st.get("daily_sub_sell_cnt"), 0) + sub_sell_inc
    )
    day_sub_sell_ev = (
        safe_int(st.get("daily_sub_sell_events"), 0) + sub_sell_inc
    )
    sub_comp_cycles = safe_int(st.get("sub_completed_cycles"), 0) + (
        1 if (sub_qty > 0 and not rem_sub_buckets) else 0
    )
    sub_m_esc_inc = (
        1 if (sold_sub_merged_flag and len(rem_sub_buckets) > 0) else 0
    )
    sub_m_esc_cnt = (
        safe_int(st.get("sub_merged_indiv_escape_cnt"), 0) + sub_m_esc_inc
    )
    sub_gross_cum = round(
        safe_float(st.get("sub_realized_gross_usd"), 0.0) + sub_gross_pnl, 4
    )
    sub_fee_cum = round(
        safe_float(st.get("sub_realized_fee_usd"), 0.0) + sub_fee_usd, 4
    )
    sub_net_cum = round(
        safe_float(st.get("sub_realized_net_usd"), 0.0) + sub_net_pnl, 4
    )
    sub_net_day = round(
        safe_float(st.get("daily_sub_realized_net_usd"), 0.0) + sub_net_pnl, 4
    )
    next_sub_frozen_d = (
        0
        if (sold_sub_q > 0 or not rem_sub_buckets)
        else max(0, safe_int(st.get("sub_consec_frozen_days"), 0))
    )

    cum_gross = round(
        safe_float(st.get("cumulative_realized_gross_usd"), 0.0) + gross_pnl, 4
    )
    cum_fee = round(
        safe_float(st.get("cumulative_realized_fee_usd"), 0.0) + fee_usd, 4
    )
    cum_net = round(
        safe_float(st.get("cumulative_realized_net_usd"), 0.0) + net_pnl, 4
    )
    day_net = round(
        safe_float(st.get("daily_realized_net_usd"), 0.0) + net_pnl, 4
    )

    # MODIFIED: 수동 부분손절 후 부분익절 시 사이클 결손 우선 보전
    prev_cyc_p = safe_float(st.get("cycle_realized_net_usd"), 0.0)
    vault_delta_p = round(
        max(0.0, net_pnl + min(0.0, prev_cyc_p)), 4
    )
    prev_vault_locked_p = max(
        0.0, safe_float(st.get("vaulted_profit_locked_usd"), 0.0)
    )
    next_vault_locked_p = (
        round(prev_vault_locked_p + vault_delta_p, 4)
        if is_barbell
        else prev_vault_locked_p
    )

    cur_cyc_gross = round(
        safe_float(st.get("cycle_realized_gross_usd"), 0.0) + gross_pnl, 4
    )
    cur_cyc_fee = round(
        safe_float(st.get("cycle_realized_fee_usd"), 0.0) + fee_usd, 4
    )
    cur_cyc_net = round(
        safe_float(st.get("cycle_realized_net_usd"), 0.0) + net_pnl, 4
    )
    cur_cyc_sub_net = round(
        safe_float(st.get("cycle_sub_realized_net_usd"), 0.0) + sub_net_pnl, 4
    )
    cur_cyc_ev = max(0, safe_int(st.get("cycle_sell_events"), 0)) + 1

    total_rem_cost = round(
        sum(b.actual_cost_usd for b in rem_buckets)
        + sum(sb.actual_cost_usd for sb in rem_sub_buckets),
        4,
    )
    pure_overall_avg = (
        round(total_rem_cost / float(h_qty), 4) if h_qty > 0 else 0.0
    )

    old_anchor_p = safe_float(st.get("anchor_price"), manual_sell_p)
    next_anchor_p = (
        manual_sell_p
        if (sold_main_q > 0 or not rem_buckets)
        else (old_anchor_p if old_anchor_p > 0.0 else manual_sell_p)
    )
    old_cycle_min_p = safe_float(st.get("cycle_min_buy_price"), 0.0)
    next_cycle_min_p = round(old_cycle_min_p, 4) if rem_buckets else 0.0

    old_sub_anchor_p = safe_float(st.get("sub_anchor_price"), manual_sell_p)
    next_sub_anchor_p = (
        manual_sell_p
        if (sold_sub_q > 0 or not rem_sub_buckets)
        else (old_sub_anchor_p if old_sub_anchor_p > 0.0 else manual_sell_p)
    )
    old_sub_cycle_min_p = safe_float(st.get("sub_cycle_min_buy_price"), 0.0)
    next_sub_cycle_min_p = (
        round(old_sub_cycle_min_p, 4) if rem_sub_buckets else 0.0
    )

    now_part_sell_ts = time.time()
    mark_post_sell_time_shield(
        context=context,
        symbol=TARGET_SYMBOL,
        fill_price=manual_sell_p,
        sold_qty=delta_remove,
        is_cycle_end=False,
    )
    mark_reentry_monitor_60s_cycle_shield(
        context=context,
        symbol=TARGET_SYMBOL,
        eval_price=manual_sell_p,
        clear_shield=True,
    )
    mark_sub_reentry_monitor_60s_cycle_shield(
        context=context,
        symbol=TARGET_SYMBOL,
        eval_price=manual_sell_p,
        clear_shield=True,
    )
    mark_reserve_deposit_check_shield(
        context=context,
        symbol=TARGET_SYMBOL,
        clear_shield=True,
    )

    part_update_kw: Dict[str, Any] = {
        "buckets": buckets_to_dicts(rem_buckets),
        "sub_buckets": buckets_to_dicts(rem_sub_buckets),
        "anchor_price": next_anchor_p,
        "cycle_min_buy_price": next_cycle_min_p,
        "cycle_ratchet_max_lots": next_ratchet_lots,
        "ratchet_anchor_price": next_anchor_p,
        "cycle_reanchor_credit_usd": 0.0,
        "l1_target_quota_qty": next_l1_target_q,
        "sub_anchor_price": next_sub_anchor_p,
        "sub_cycle_min_buy_price": next_sub_cycle_min_p,
        "sub_ratchet_max_lots": next_sub_ratchet_lots,
        "sub_l1_target_quota_qty": next_sub_l1_target_q,
        "main_consec_frozen_days": next_main_frozen_d,
        "sub_consec_frozen_days": next_sub_frozen_d,
        "daily_main_sell_cnt": day_main_sell_cnt,
        "indiv_grid_sell_cnt": indiv_cnt,
        "daily_indiv_grid_sell_cnt": day_indiv_cnt,
        "wma_grad_sell_cnt": wma_cnt,
        "daily_wma_grad_sell_cnt": day_wma_cnt,
        "sub_sell_events": sub_sell_ev,
        "sub_sold_shares": sub_sold_sh,
        "daily_sub_sell_cnt": day_sub_sell_cnt,
        "daily_sub_sell_events": day_sub_sell_ev,
        "sub_completed_cycles": sub_comp_cycles,
        "sub_merged_indiv_escape_cnt": sub_m_esc_cnt,
        "sub_realized_gross_usd": sub_gross_cum,
        "sub_realized_fee_usd": sub_fee_cum,
        "sub_realized_net_usd": sub_net_cum,
        "daily_sub_realized_net_usd": sub_net_day,
        "vaulted_profit_locked_usd": next_vault_locked_p,
        "waiting_reserve_deposit": False,
        "waiting_reserve_deposit_alert_sent": False,
        "required_reserve_deposit_usd": 0.0,
        "last_reserve_check_ts": 0.0,
        "last_sell_fill_ts": now_part_sell_ts,
        "last_sell_gate_eval_ts": 0.0,
        "last_reentry_eval_ts": 0.0,
        "last_sub_reentry_eval_ts": 0.0,
        "pending_sell_indices": [],
        "pending_sub_sell_indices": [],
        "pending_step_up_min_price": 0.0,
        "pending_sub_step_up_min_price": 0.0,
        "last_settled_order_ids": updated_settled_oids,
        "total_sell_events": tot_sell_ev,
        "total_sold_shares": tot_sold_sh,
        "win_sell_events": win_ev,
        "daily_sell_events": day_sell_ev,
        "cumulative_realized_gross_usd": cum_gross,
        "cumulative_realized_fee_usd": cum_fee,
        "cumulative_realized_net_usd": cum_net,
        "daily_realized_net_usd": day_net,
        "cycle_realized_gross_usd": cur_cyc_gross,
        "cycle_realized_fee_usd": cur_cyc_fee,
        "cycle_realized_net_usd": cur_cyc_net,
        "cycle_sub_realized_net_usd": cur_cyc_sub_net,
        "cycle_sell_events": cur_cyc_ev,
    }
    if sold_sub_q > 0:
        part_update_kw["last_sub_sell_fill_ts"] = now_part_sell_ts
    if sub_qty > 0 and not rem_sub_buckets:
        part_update_kw["last_sub_cycle_end_ts"] = now_part_sell_ts

    updated_st = await context.ledger.update_state(
        TARGET_SYMBOL, **part_update_kw
    )

    barbell_vault_part = next_vault_locked_p
    repaid_part_soxl = 0.0
    added_part_sgov = 0.0
    cash_b_part = 0.0
    if is_barbell:
        b_rec_p = await record_barbell_realized_profit(
            context=context,
            net_pnl_usd=vault_delta_p,  # MODIFIED: 유령현금 이중계상 차단
            is_graduated_zero=False,
            prev_soxl_injected_usd=safe_float(
                st.get("injected_reserve_usd"), 0.0
            ),
            prev_soxl_used_portions_cnt=safe_int(
                st.get("used_reserve_portions_cnt"), 0
            ),
            cycle_realized_net_override=cur_cyc_net,
        )
        barbell_vault_part = safe_float(
            b_rec_p.get("vault_realized_profit_usd"), next_vault_locked_p
        )
        repaid_part_soxl = safe_float(
            b_rec_p.get("repaid_from_soxl_usd"), 0.0
        )
        added_part_sgov = safe_float(
            b_rec_p.get("added_sgov_buy_budget_usd"), 0.0
        )
        cash_b_part = safe_float(b_rec_p.get("cash_bucket_usd"), 0.0)
        updated_st = context.ledger.get_state(TARGET_SYMBOL)

    free_cash_now = safe_float(updated_st.get("free_cash_usd"), 0.0)
    rem_sub_sh = sum(sb.qty for sb in rem_sub_buckets)
    if hasattr(context, "send_slim_alert"):
        s_sign = "+" if net_pnl >= 0.0 else "-"
        r_sign = "+" if net_rate >= 0.0 else ""
        cyc_sign = "+" if cur_cyc_net >= 0.0 else "-"
        sub_rem_note = (
            f"+서브 {rem_sub_sh}주({len(rem_sub_buckets)}개층)"
            if rem_sub_sh > 0
            else ""
        )
        ratchet_rem_note = (
            f" · 단차잠금 {next_ratchet_lots}회차"
            if next_ratchet_lots > rem_held_lots
            else ""
        )
        if is_barbell:
            rt_part_note = (
                f" · ⚡실시간환수 ${repaid_part_soxl:,.0f}(현금 ${cash_b_part:,.0f}"
                + (
                    f"·SGOV예약 +${added_part_sgov:,.0f})"
                    if added_part_sgov > 0.0
                    else ")"
                )
                if repaid_part_soxl > 0.0
                else ""
            )
            part_credit_note = (
                f"별도 수익금고 격리(⚖️바벨 · 누적금고 +${barbell_vault_part:,.2f}){rt_part_note}"
            )
        elif is_simple_mode:
            part_credit_note = (
                f"현금금고 적립(💵인출형 · 당일실현 +${max(0.0, day_net):,.2f} 인출가능)"
            )
        else:
            part_credit_note = "시드 복리산입"

        await context.send_slim_alert(
            title=f"➖ [SOXL 수동 부분매도 정산] {delta_remove}주 @ ${manual_sell_p:.2f} ({r_sign}{net_rate:.2f}%)",
            body=(
                f"매칭층: {match_res.get('sold_tier_desc')} · "
                f"세후순익 {s_sign}${abs(net_pnl):,.2f} {part_credit_note} · "
                f"🔄이번사이클 누적: {cyc_sign}${abs(cur_cyc_net):,.2f}({cur_cyc_ev}회) · "
                f"잔여 {h_qty}주({len(rem_buckets)}개층{sub_rem_note}{ratchet_rem_note} · 순수평단 ${pure_overall_avg:.2f}) 보존 · 가용현금 ${free_cash_now:,.2f}"
            ),
        )
    return {
        "status": "SYNCED_MANUAL_PARTIAL_REDUCTION",
        "held_shares": h_qty,
        "sold_qty": delta_remove,
        "manual_sell_price": manual_sell_p,
        "net_pnl_usd": net_pnl,
        "cycle_realized_net_usd": cur_cyc_net,
        "tiers": len(rem_buckets),
        "sub_tiers": len(rem_sub_buckets),
        "cycle_ratchet_max_lots": next_ratchet_lots,
        "sub_ratchet_max_lots": next_sub_ratchet_lots,
        "l1_target_quota_qty": next_l1_target_q,
        "sub_l1_target_quota_qty": next_sub_l1_target_q,
        "actual_avg_price": pure_overall_avg,
        "book_price": pure_overall_avg,
    }


# ---------------------------------------------------------------------------
# [핵심 1-B] tg_ui_plugin.py 호환 : 봇 작동 재개(OFF ➔ ON) 시 실잔고 즉시 재락온 헬퍼
# ---------------------------------------------------------------------------
async def relock_stratum_on_bot_resume(
    context: Any,
    holdings: Optional[Dict[str, Dict[str, Any]]] = None,
    prices: Optional[Dict[str, float]] = None,
    now_est: Optional[datetime] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    eff_holdings = holdings
    if not isinstance(eff_holdings, dict) or not eff_holdings:
        try:
            h_map, ok = await context.api.get_holdings_map_with_status()
            if ok and isinstance(h_map, dict):
                eff_holdings = h_map
                context.latest_holdings = h_map
                context.holdings_fetch_ok = True
        except Exception:
            eff_holdings = getattr(context, "latest_holdings", {})

    eff_prices = prices
    if not isinstance(eff_prices, dict) or not eff_prices:
        try:
            p_map = await context.api.get_current_prices_batch(
                (TARGET_SYMBOL,)
            )
            if (
                isinstance(p_map, dict)
                and safe_float(p_map.get(TARGET_SYMBOL), 0.0) > 0.0
            ):
                eff_prices = p_map
                context.latest_prices = p_map
        except Exception:
            eff_prices = getattr(context, "latest_prices", {})

    return await reconcile_stratum_with_broker_holdings_plugin(
        context=context,
        holdings=eff_holdings or {},
        prices=eff_prices or {},
        now_est=dt_now,
        force_sync=True,
    )


# ---------------------------------------------------------------------------
# [핵심 2] 04:00 ~ 04:06 EST 프리장 개장 초기 호가 안정화 · 선취소-후정산 · 수수료 갱신 · 일일 롤오버
# ---------------------------------------------------------------------------
async def execute_0400_premarket_stabilization_plugin(
    context: Any,
    holdings: Dict[str, Dict[str, Any]],
    prices: Dict[str, float],
    now_est: Optional[datetime] = None,
) -> Dict[str, Any]:
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    today_str = dt_now.strftime("%Y-%m-%d")

    st_pre = context.ledger.get_state(TARGET_SYMBOL)
    has_pending_pre = bool(
        str(st_pre.get("sell_order_id") or "").strip()
        or str(st_pre.get("buy_order_id") or "").strip()
    )
    if has_pending_pre:
        try:
            await context.api.cancel_all_open_orders(symbol=TARGET_SYMBOL)
        except Exception:
            pass
        if str(st_pre.get("sell_order_id") or "").strip():
            try:
                await sync_pending_sell_order_plugin(
                    context=context,
                    holdings=holdings,
                    prices=prices,
                    now_est=dt_now,
                    force_settle=True,
                )
            except Exception as exc:
                logger.debug("04:00 EST 미결 매도 후정산 예외(묵음): %s", exc)
        if str(st_pre.get("buy_order_id") or "").strip():
            try:
                await sync_pending_buy_order_plugin(
                    context=context,
                    holdings=holdings,
                    prices=prices,
                    now_est=dt_now,
                    force_settle=True,
                )
            except Exception as exc:
                logger.debug("04:00 EST 미결 매수 후정산 예외(묵음): %s", exc)

    if hasattr(context.ledger, "rollover_daily_counters_if_needed"):
        try:
            await context.ledger.rollover_daily_counters_if_needed(today_str)
        except Exception as exc:
            logger.debug("04:00 EST 일일 카운터 롤오버 예외(무시): %s", exc)

    try:
        await ensure_barbell_ledger(context).rollover_daily_if_needed(today_str)
    except Exception:
        pass

    done_date = str(getattr(context, "last_0400_sync_date", "") or "")
    if done_date == today_str:
        return {"status": "ALREADY_STABILIZED_TODAY", "date": today_str}

    setattr(context, "last_0400_sync_date", today_str)

    canceled_cnt = await context.api.cancel_all_open_orders(
        symbol=TARGET_SYMBOL
    )
    try:
        await context.api.cancel_all_open_orders(symbol=BARBELL_SAFE_SYMBOL)
    except Exception:
        pass

    st_after_cancel = context.ledger.get_state(TARGET_SYMBOL)
    if str(st_after_cancel.get("sell_order_id") or "").strip():
        try:
            await sync_pending_sell_order_plugin(
                context=context,
                holdings=holdings,
                prices=prices,
                now_est=dt_now,
                force_settle=True,
            )
        except Exception:
            pass
    if str(st_after_cancel.get("buy_order_id") or "").strip():
        try:
            await sync_pending_buy_order_plugin(
                context=context,
                holdings=holdings,
                prices=prices,
                now_est=dt_now,
                force_settle=True,
            )
        except Exception:
            pass

    us_comm_r = safe_float(
        st_after_cancel.get("us_commission_rate"), 0.0007
    )
    rt_fee_pct = safe_float(
        st_after_cancel.get("round_trip_fee_rate_pct"), 0.14
    )
    ensure_comm_fn = getattr(context.api, "ensure_us_commission_rate", None)
    if callable(ensure_comm_fn):
        try:
            c_res = await ensure_comm_fn(force_refresh=True)
            if isinstance(c_res, tuple) and len(c_res) == 2:
                us_comm_r = safe_float(c_res[0], us_comm_r)
                rt_fee_pct = safe_float(c_res[1], rt_fee_pct)
        except Exception as exc:
            logger.debug("04:00 EST 수수료율 갱신 폴백 사용: %s", exc)

    mark_reentry_monitor_60s_cycle_shield(
        context=context, symbol=TARGET_SYMBOL, clear_shield=True
    )
    mark_sub_reentry_monitor_60s_cycle_shield(
        context=context, symbol=TARGET_SYMBOL, clear_shield=True
    )
    mark_reserve_deposit_check_shield(
        context=context, symbol=TARGET_SYMBOL, clear_shield=True
    )
    reset_sniper_l1_trail_slots(
        context, grid_kind="ALL", symbol=TARGET_SYMBOL
    )
    mark_extended_sell_restriction_cooldown(
        context=context, symbol=TARGET_SYMBOL, cooldown_sec=0.0, reason="CLEAR"
    )
    snap_map = getattr(context, "exit_snapshot_cache", None)
    if isinstance(snap_map, dict) and isinstance(
        snap_map.get(TARGET_SYMBOL), dict
    ):
        snap_map[TARGET_SYMBOL]["ext_sell_restrict_until_mono"] = 0.0

    st_post_0400 = context.ledger.get_state(TARGET_SYMBOL)
    has_rem_0400_ord = bool(
        str(st_post_0400.get("buy_order_id") or "").strip()
        or str(st_post_0400.get("sell_order_id") or "").strip()
    )
    clear_0400_ord_kw: Dict[str, Any] = (
        {}
        if has_rem_0400_ord
        else {
            "buy_order_id": "",
            "sell_order_id": "",
            "ordered_qty": 0,
            "target_sell_price": 0.0,
            "pending_sell_mode": "",
            "pending_sell_indices": [],
            "pending_sub_sell_indices": [],
            "pending_lot_type": "",
            "pending_step_up_min_price": 0.0,
            "pending_sub_step_up_min_price": 0.0,
        }
    )
    await context.ledger.update_state(
        TARGET_SYMBOL,
        us_commission_rate=us_comm_r,
        round_trip_fee_rate_pct=rt_fee_pct,
        **clear_0400_ord_kw,
        daily_seed_protect_pass_cnt=0,
        daily_unlock_buy_events=0,
        daily_sub_buy_cnt=0,
        daily_sub_buy_events=0,
        daily_sub_sell_cnt=0,
        daily_sub_sell_events=0,
        daily_sub_unlock_events=0,
        daily_sub_realized_net_usd=0.0,
        daily_main_buy_cnt=0,
        daily_main_sell_cnt=0,
        daily_reserve_injected_cnt=0,
        daily_dust_guard_blocked_cnt=0,
        last_evaluated_buy_bucket_id=-1,
        last_evaluated_date=today_str,
        sub_last_evaluated_buy_bucket_id=-1,
        sub_last_evaluated_date=today_str,
        last_reentry_eval_ts=0.0,
        last_sub_reentry_eval_ts=0.0,
        last_reserve_check_ts=0.0,
    )

    sync_res = await reconcile_stratum_with_broker_holdings_plugin(
        context=context,
        holdings=holdings,
        prices=prices,
        now_est=dt_now,
        force_sync=True,
    )

    logger.info(
        "🌅 [04:00 EST 프리장 오프닝 안정화 완료] 당일 카운터 0회 리셋 · 왕복수수료=%.2f%% · 잔류주문 취소=%d건 · 그리드동기화=%s",
        rt_fee_pct,
        canceled_cnt,
        sync_res.get("status"),
    )
    return {
        "status": "PREMARKET_0400_STABILIZED",
        "canceled_orders": canceled_cnt,
        "round_trip_fee_rate_pct": rt_fee_pct,
        "sync_result": sync_res,
    }


# ---------------------------------------------------------------------------
# [핵심 3] 16:00 ~ 16:59 EST 정규장 마감 일일 결산 보고 & 3단 모드별(복리/단리/바벨) 브리핑 & 본/서브 무매매 동결일 갱신
# ---------------------------------------------------------------------------
async def execute_1600_daily_closing_settlement_plugin(
    context: Any,
    holdings: Dict[str, Dict[str, Any]],
    prices: Dict[str, float],
    now_est: Optional[datetime] = None,
) -> Dict[str, Any]:
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    hm = dt_now.hour * 100 + dt_now.minute
    if not (1600 <= hm <= 1659):
        return {"status": "NOT_CLOSING_WINDOW"}

    today_str = dt_now.strftime("%Y-%m-%d")
    if hasattr(context.ledger, "rollover_daily_counters_if_needed"):
        try:
            await context.ledger.rollover_daily_counters_if_needed(today_str)
        except Exception as exc:
            logger.debug("16:00 마감 선행 일일 롤오버 예외(묵음): %s", exc)

    st = context.ledger.get_state(TARGET_SYMBOL)
    if str(st.get("last_closing_report_date") or "") == today_str:
        return {"status": "CLOSING_REPORT_ALREADY_SENT", "date": today_str}

    if hm == 1600 and (
        str(st.get("buy_order_id") or "").strip()
        or str(st.get("sell_order_id") or "").strip()
    ):
        if str(st.get("buy_order_id") or "").strip():
            try:
                await sync_pending_buy_order_plugin(
                    context=context,
                    holdings=holdings,
                    prices=prices,
                    now_est=dt_now,
                    force_settle=False,
                )
            except Exception:
                pass
        if str(st.get("sell_order_id") or "").strip():
            try:
                await sync_pending_sell_order_plugin(
                    context=context,
                    holdings=holdings,
                    prices=prices,
                    now_est=dt_now,
                    force_settle=False,
                )
            except Exception:
                pass
        st_recheck = context.ledger.get_state(TARGET_SYMBOL)
        if str(st_recheck.get("buy_order_id") or "").strip() or str(
            st_recheck.get("sell_order_id") or ""
        ).strip():
            return {
                "status": "WAIT_1600_PENDING_ORDER_SETTLEMENT",
                "buy_order_id": st_recheck.get("buy_order_id"),
                "sell_order_id": st_recheck.get("sell_order_id"),
            }

    await context.api.cancel_all_open_orders(symbol=TARGET_SYMBOL)
    try:
        await context.api.cancel_all_open_orders(symbol=BARBELL_SAFE_SYMBOL)
        await execute_barbell_sgov_tick_plugin(context, now_est=dt_now)
    except Exception:
        pass

    st_after_cancel = context.ledger.get_state(TARGET_SYMBOL)
    if str(st_after_cancel.get("buy_order_id") or "").strip():
        try:
            await sync_pending_buy_order_plugin(
                context=context,
                holdings=holdings,
                prices=prices,
                now_est=dt_now,
                force_settle=True,
            )
        except Exception as exc:
            logger.debug("16:00 마감 미결 매수 후정산 예외(묵음): %s", exc)
    if str(st_after_cancel.get("sell_order_id") or "").strip():
        try:
            await sync_pending_sell_order_plugin(
                context=context,
                holdings=holdings,
                prices=prices,
                now_est=dt_now,
                force_settle=True,
            )
        except Exception as exc:
            logger.debug("16:00 마감 미결 매도 후정산 예외(묵음): %s", exc)

    st_final = context.ledger.get_state(TARGET_SYMBOL)
    cur_buckets = buckets_from_dicts(st_final.get("buckets", []))
    cur_sub_buckets = buckets_from_dicts(st_final.get("sub_buckets", []))

    prev_frozen_eval_date = str(st_final.get("last_frozen_eval_date") or "")
    cur_main_frozen = max(
        0, safe_int(st_final.get("main_consec_frozen_days"), 0)
    )
    cur_sub_frozen = max(
        0, safe_int(st_final.get("sub_consec_frozen_days"), 0)
    )

    if prev_frozen_eval_date != today_str:
        day_main_trades = safe_int(
            st_final.get("daily_main_buy_cnt"), 0
        ) + safe_int(st_final.get("daily_main_sell_cnt"), 0)
        if not cur_buckets:
            next_main_frozen = 0
        elif day_main_trades == 0:
            next_main_frozen = cur_main_frozen + 1
        else:
            next_main_frozen = 0

        day_sub_trades = safe_int(
            st_final.get("daily_sub_buy_cnt"), 0
        ) + safe_int(st_final.get("daily_sub_sell_cnt"), 0)
        if not cur_sub_buckets:
            next_sub_frozen = 0
        elif day_sub_trades == 0:
            next_sub_frozen = cur_sub_frozen + 1
        else:
            next_sub_frozen = 0
    else:
        next_main_frozen = cur_main_frozen if cur_buckets else 0
        next_sub_frozen = cur_sub_frozen if cur_sub_buckets else 0

    has_rem_1600_ord = bool(
        str(st_final.get("buy_order_id") or "").strip()
        or str(st_final.get("sell_order_id") or "").strip()
    )
    clear_1600_ord_kw: Dict[str, Any] = (
        {}
        if has_rem_1600_ord
        else {
            "buy_order_id": "",
            "sell_order_id": "",
            "ordered_qty": 0,
            "target_sell_price": 0.0,
            "pending_sell_mode": "",
            "pending_sell_indices": [],
            "pending_sub_sell_indices": [],
            "pending_lot_type": "",
            "pending_step_up_min_price": 0.0,
            "pending_sub_step_up_min_price": 0.0,
        }
    )
    updated_st = await context.ledger.update_state(
        TARGET_SYMBOL,
        main_consec_frozen_days=next_main_frozen,
        sub_consec_frozen_days=next_sub_frozen,
        last_frozen_eval_date=today_str,
        last_closing_report_date=today_str,
        **clear_1600_ord_kw,
    )

    snap_fn = getattr(context.ledger, "create_daily_backup_snapshot", None)
    if callable(snap_fn):
        try:
            await snap_fn(logical_date=today_str, keep_days=14)
        except Exception as exc:
            logger.debug("16:00 마감 스냅샷 백업 예외(무시): %s", exc)

    live_p = safe_float(
        (prices or {}).get(TARGET_SYMBOL),
        safe_float(
            (holdings or {}).get(TARGET_SYMBOL, {}).get("last_price"),
            safe_float(updated_st.get("anchor_price"), 0.0),
        ),
    )
    summary = summarize_stratum_portfolio(updated_st, live_price=live_p)
    fx_rate = await context.api.get_usd_krw_rate()
    if fx_rate <= 0.0:
        fx_rate = KRW_PER_USD_DEFAULT

    folder_slug = str(
        getattr(context.ledger, "folder_slug", "")
        or updated_st.get("folder_slug")
        or get_folder_slug(getattr(context, "base_dir", None))
    )
    is_barbell = bool(summary.get("is_barbell_mode", False))
    is_simple_mode = bool(summary.get("is_simple_mode", False))
    mode_lbl = str(summary.get("portion_mode_label") or "📈자산증식형(복리)")
    day_net = safe_float(updated_st.get("daily_realized_net_usd"), 0.0)
    day_krw = day_net * fx_rate
    withdrawable_surplus = safe_float(
        summary.get("withdrawable_surplus_usd"), 0.0
    )
    self_res_p = safe_float(summary.get("self_reserve_portions"), 0.0)
    cyc_net = safe_float(summary.get("cycle_realized_net_usd"), 0.0)
    cyc_ev = safe_int(summary.get("cycle_sell_events"), 0)
    comp_cycles = safe_int(summary.get("completed_main_cycles"), 0)
    cum_net = safe_float(summary.get("cumulative_realized_net_usd"), 0.0)
    cum_roi = safe_float(summary.get("realized_roi_pct"), 0.0)
    free_cash = safe_float(summary.get("free_cash_usd"), 0.0)
    held_sh = safe_int(summary.get("held_shares"), 0)
    sub_sh = safe_int(summary.get("sub_held_shares"), 0)
    sub_tiers = safe_int(summary.get("sub_held_tiers"), 0)
    sub_lots = safe_int(summary.get("sub_held_lots"), 0)
    sub_comp_cycles = safe_int(summary.get("sub_completed_cycles"), 0)
    sub_net_cum = safe_float(summary.get("sub_realized_net_usd"), 0.0)
    day_sub_buy = safe_int(updated_st.get("daily_sub_buy_cnt"), 0)
    day_sub_sell = safe_int(updated_st.get("daily_sub_sell_cnt"), 0)
    held_tiers = safe_int(summary.get("held_tiers"), 0)
    held_lots = safe_int(summary.get("held_lots"), 0)
    ratchet_lots = safe_int(summary.get("cycle_ratchet_max_lots"), held_lots)
    day_buy_ev = safe_int(updated_st.get("daily_buy_events"), 0)
    day_unlock_ev = safe_int(updated_st.get("daily_unlock_buy_events"), 0)
    cum_unlock_ev = safe_int(updated_st.get("cond_unlock_buy_events"), 0)
    day_res_inj = safe_int(updated_st.get("daily_reserve_injected_cnt"), 0)
    used_res_cnt = safe_int(summary.get("used_reserve_portions_cnt"), 0)
    tot_res_cnt = safe_int(summary.get("total_reserve_injected_cnt"), 0)
    inj_res_usd = safe_float(summary.get("injected_reserve_usd"), 0.0)
    day_sell_ev = safe_int(updated_st.get("daily_sell_events"), 0)
    day_wma_grad = safe_int(updated_st.get("daily_wma_grad_sell_cnt"), 0)
    day_indiv_sell = safe_int(updated_st.get("daily_indiv_grid_sell_cnt"), 0)
    day_pass = safe_int(updated_st.get("daily_seed_protect_pass_cnt"), 0)
    day_saved = safe_float(updated_st.get("daily_leftover_saved_usd"), 0.0)

    if hasattr(context, "send_slim_alert"):
        d_sign = "+" if day_net >= 0.0 else "-"
        cyc_sign = "+" if cyc_net >= 0.0 else "-"
        c_sign = "+" if cum_net >= 0.0 else "-"
        unlock_note = (
            f"(🔓해금 {day_unlock_ev}회/누적 {cum_unlock_ev}회)"
            if (day_unlock_ev > 0 or cum_unlock_ev > 0)
            else ""
        )
        sub_day_note = (
            f" · 🛡️서브(매수 {day_sub_buy}/익절 {day_sub_sell}회 · 누적졸업 {sub_comp_cycles}회 · +${sub_net_cum:,.2f})"
            if (
                day_sub_buy > 0
                or day_sub_sell > 0
                or sub_comp_cycles > 0
                or sub_sh > 0
            )
            else f" · 🛡️본동결 {next_main_frozen}/{SUB_FROZEN_DAYS_TRIGGER}일"
        )
        sub_carry_note = (
            f"+서브 {sub_sh}주({sub_tiers}층·{sub_lots}/{SUB_MAX_TOTAL_LOTS_4}회분)"
            if sub_sh > 0
            else ""
        )
        lot_carry_str = (
            f"{held_lots}회차[단차잠금 {ratchet_lots}회차]"
            if ratchet_lots > held_lots
            else f"{held_lots}회차"
        )
        res_note = (
            f" · 💉예비수혈: 당일 +{day_res_inj}회(현재 {used_res_cnt}회/누적 {tot_res_cnt}회·${inj_res_usd:,.2f})"
            if (day_res_inj > 0 or used_res_cnt > 0 or tot_res_cnt > 0)
            else " · 💉예비수혈: 0회(대기)"
        )

        if is_barbell:
            b_stat = summarize_barbell_status(context, st_soxl=updated_st)
            income_withdraw_guide = (
                f" · ⚖️[바벨 60/30/10 결산] 금일 실현수익 전액 별도 수익금고 격리 완료"
                f"(누적금고 +${b_stat['vault_realized_profit_usd']:,.2f} · 가용 ${b_stat['vault_available_usd']:,.2f} | "
                f"SGOV {b_stat['sgov_held_qty']}주[${b_stat['sgov_invested_usd']:,.0f}] · 현금버킷 ${b_stat['cash_bucket_usd']:,.0f})"
            )
        elif is_simple_mode:
            if day_net > 0.0:
                income_withdraw_guide = (
                    f" · 💵[인출형 정산안내] 오늘 확정된 실현수익 +${day_net:,.2f}(약 +{day_krw:,.0f}원)는 "
                    f"지금 현금으로 인출하여 사용하셔도 됩니다! "
                    f"(미인출 시 계좌에 적립되어 누적 잉여현금 ${withdrawable_surplus:,.2f}[자체수혈 +{self_res_p:.1f}회분]로 폭락장을 자동 방어합니다)"
                )
            else:
                income_withdraw_guide = (
                    f" · 💵[인출형 정산안내] 금일 실현수익 $0.00 (인출 보류 · "
                    f"현재 누적 잉여현금 ${withdrawable_surplus:,.2f}[자체수혈 +{self_res_p:.1f}회분] 보유중)"
                )
        else:
            income_withdraw_guide = (
                " · 📈[자산증식형(복리)] 당일 실현수익 전액 코어시드에 자동 복리 재투자 완료"
            )

        await context.send_slim_alert(
            title=f"🌙 [16:00 EST 정규장 마감 일일 결산 · {mode_lbl}] ({today_str})",
            body=(
                f"당일 세후실현수익: {d_sign}${abs(day_net):,.2f} ({d_sign}{abs(day_krw):,.0f}원)"
                f"{income_withdraw_guide} "
                f"· 🔄이번사이클: {cyc_sign}${abs(cyc_net):,.2f}({cyc_ev}회) "
                f"· 💰누적실현: {c_sign}${abs(cum_net):,.2f} ({c_sign}{abs(cum_roi):.2f}% · 졸업 {comp_cycles}회) "
                f"· 당일 매수 {day_buy_ev}회{unlock_note} / 익절 {day_sell_ev}회(2~7층이평졸업 {day_wma_grad}회·개별층 {day_indiv_sell}회)"
                f"{sub_day_note}{res_note} "
                f"· 🛡️시드패스 {day_pass:,}회 / 자투리절약 +${day_saved:,.2f} "
                f"· 오버나이트 이월: 본 {held_sh}주({held_tiers}개층·{lot_carry_str}){sub_carry_note} · 가용현금 ${free_cash:,.2f} "
                f"(🌇애프터·🌃데이장 ⚡1.5s 본1·2층 개별채굴 & 3~7층 통합졸업 연속가동 · 매수잠금)"
            ),
        )

    logger.info(
        "🌙 [16:00 EST 일일 결산 완료 · %s · %s] 당일실현=$%.2f · 이번사이클=$%.2f · 누적실현=$%.2f · 본동결=%d일 · 서브동결=%d일",
        folder_slug,
        mode_lbl,
        day_net,
        cyc_net,
        cum_net,
        next_main_frozen,
        next_sub_frozen,
    )
    return {
        "status": "DAILY_CLOSING_SETTLEMENT_DONE",
        "date": today_str,
        "portion_mode": summary.get("portion_mode"),
        "daily_realized_net_usd": day_net,
        "daily_withdrawable_profit_usd": max(0.0, day_net),
        "cycle_realized_net_usd": cyc_net,
        "cumulative_realized_net_usd": cum_net,
        "held_shares": held_sh,
        "sub_held_shares": sub_sh,
        "held_tiers": held_tiers,
        "sub_held_tiers": sub_tiers,
        "cycle_ratchet_max_lots": ratchet_lots,
        "main_consec_frozen_days": next_main_frozen,
        "sub_consec_frozen_days": next_sub_frozen,
    }


# ---------------------------------------------------------------------------
# [핵심 4] 17:00 EST 일일 가비지 컬렉션(GC) · 일일 카운터 롤오버 · 날짜별 원장 백업
# ---------------------------------------------------------------------------
async def execute_daily_1700_gc_and_backup_plugin(
    context: Any,
    now_est: Optional[datetime] = None,
) -> Dict[str, Any]:
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    logical_date = dt_now.strftime("%Y-%m-%d")

    snap_file = ""
    snap_fn = getattr(context.ledger, "create_daily_backup_snapshot", None)
    if callable(snap_fn):
        try:
            snap_file = await snap_fn(logical_date=logical_date, keep_days=14)
        except Exception as exc:
            logger.warning("17:00 EST 원장 스냅샷 백업 예외: %s", exc)

    await context.ledger.rollover_daily_counters_if_needed(logical_date)
    try:
        await ensure_barbell_ledger(context).rollover_daily_if_needed(
            logical_date
        )
    except Exception:
        pass

    mark_reentry_monitor_60s_cycle_shield(
        context=context, symbol=TARGET_SYMBOL, clear_shield=True
    )
    mark_sub_reentry_monitor_60s_cycle_shield(
        context=context, symbol=TARGET_SYMBOL, clear_shield=True
    )
    st_gc = context.ledger.get_state(TARGET_SYMBOL)
    if not str(st_gc.get("buy_order_id") or "").strip():
        await context.ledger.update_state(
            TARGET_SYMBOL,
            pending_step_up_min_price=0.0,
            pending_sub_step_up_min_price=0.0,
            last_evaluated_buy_bucket_id=-1,
            sub_last_evaluated_buy_bucket_id=-1,
            last_reentry_eval_ts=0.0,
            last_sub_reentry_eval_ts=0.0,
        )
    collected = gc.collect()
    logger.info(
        "🧹 [17:00 EST 일일 GC 및 원장 금고 백업 완료] date=%s · snapshot=%s · gc_collected=%d",
        logical_date,
        os.path.basename(snap_file) if snap_file else "none",
        collected,
    )
    return {
        "status": "DAILY_GC_DONE",
        "logical_date": logical_date,
        "snapshot_file": snap_file,
        "gc_collected": collected,
    }


# 하위 호환 별칭 (타 모듈 및 프롬프트 심볼 완벽 호환)
execute_1600_market_close_settlement_plugin = (
    execute_1600_daily_closing_settlement_plugin
)
execute_macro_defense_plugin = reconcile_stratum_with_broker_holdings_plugin
enforce_0930_regular_cutoff_plugin = reconcile_stratum_with_broker_holdings_plugin
execute_moc_zero_overnight_plugin = execute_1600_daily_closing_settlement_plugin
