# -*- coding: utf-8 -*-
"""
# MODIFIED: defense_plugin.py
순수 롱(SOXL) 매수 04:07 ~ 16:00 EST 제한(정규장 마감 30분 전 15:30 ~ 16:00 EST 0주 새 사이클 1층 진입 및 1층 공석 +1.0% 돌파 추격 차단 · Case 84) &
익절 매도 24시간 전 세션(프리마켓 + 정규장 + 애프터마켓 + 데이마켓 · 방안 C 오버나이트 통합이평 사수 · Case 83) 확장
오버나이트 7층 골디락스 멀티 그리드(1층 공격수 + 2 ~ 6층 개별 완충층 + 통합 7층 본대) 및
황금시간대(07:00 ~ 07:50 EST & RSI <= 19.0) 독립 골든포켓(GoldenAllInPocket) 지층관리 스나이퍼 전용 (Step 07 / 09):
1) 🚨 [Case 66, Case 78, Case 79 & Case 80 봇 주문 진행 중 가로채기 차단 및 04:00 / 16:01 세션 경계 force_settle 선취소-후정산(Cancel-then-Sync) 가드]
   - 평시 원장에 미결 매수(buy_order_id) 또는 미결 매도(sell_order_id)가 존재할 때 reconcile 모듈이 호출되면
     즉시 sync_pending_buy_order_plugin() / sync_pending_sell_order_plugin() 을 선행 호출하여 가로채기를 차단한다.
   - 04:00 EST 오프닝 안정화 및 16:01 EST 정규장 마감 결산 진입 시에는 먼저 cancel_all_open_orders() 로 거래소 미체결 잔량을 확정 취소 종료시킨 직후
     sync_pending_buy_order_plugin(..., force_settle=True) / sync_pending_sell_order_plugin(..., force_settle=True) 를 호출하여,
     발주 후 60초 미만인 부분 체결(PARTIAL_FILLED / PENDING_CANCEL) 대기 물량이나 취소 직전 체결분의
     비례 자투리 절약금 · 골든포켓 분리 기록 · 세후 실현익 복리 산입 · 텔레그램 체결 알림 · 양방향 60초 타임쉴드 각인이 단 1주도 유실되지 않도록 100% 보장!
   - 특히 16:00:00 ~ 16:00:59 EST (hm == 1600) 동안에는 15:59:xx EST 발주 미결 주문 및 16:00 EST 마감봉(72번 버킷) 타격 기회를 보호한 뒤
     16:01 EST 부터(또는 16:00 에 미결 주문이 없고 72번 버킷 평가가 완료된 직후) 마감 결산을 집행한다.
2) 🛡️ [Case 61, Case 65, Case 69, Case 80 & Case 84 양방향 15초 인덱싱 그레이스 쉴드 전 구간(h_qty != ledger_qty) 최우선 적용]
   - 원장 총 보유 수량을 ledger_qty = sum(b.qty for b in buckets) + golden_pocket.qty 로 통합 산출하여
     골든포켓 보유 중에도 유령 추매/매도 오판을 원천 차단!
   - 매수 체결뿐만 아니라 매도 체결(개별 층 익절 · 골든포켓 익절 및 0주 졸업) 직후 15.0초 동안은 모든 수량 불일치(h_qty != ledger_qty)에서
     즉시 PROTECTED_BY_AUTO_FILL_GRACE_SHIELD 를 반환하여, 토스 잔고 API 인덱싱 시차(0.1 ~ 0.4초)로 인한
     유령 추매(h_qty > ledger_qty) ➔ 유령 부분매도(h_qty < ledger_qty) 핑퐁 오염 및 0주 졸업 직후 과거 백업 덮어쓰기를 원천 봉쇄!
   - 수동 전량 청산(CLEARED_TO_ZERO_HOLDINGS)으로 0주 싸이클이 끝나는 순간에도 토스 CLOSED 체결원장에서 실제 매도 체결가를 역추적하여
     보유 지층 및 골든포켓의 순수 매수 원금 대비 세후 실현수익(net_pnl_usd)을 원장(cumulative_realized_net_usd · free_cash_usd)에 즉시 복리 산입하고,
     l1_target_quota_qty = 0 클리어(Case 78) 및 compute_reserve_repayment_on_zero() 로 온디맨드 예비시드 원금을 자동 상환(Case 77)하며,
     mark_post_sell_time_shield(is_cycle_end=True) 와 last_sell_fill_ts / last_cycle_end_ts / last_reentry_eval_ts=0.0 을 각인하여 60.0초 타임쉴드를 강제하고
     15:29:01 ~ 16:00:00 EST 구간에는 Case 84 새 사이클 진입 차단 안내를 표출!
3) 🛡️ [Case 63, Case 69, Case 71 ~ Case 80 : 수동 매수·매도 CLOSED 체결가 역추적 · 단가 비교 층간 편입 · 수동 매수 실시간 텔레그램 알림 타전 · 층별/포켓별 순수 원가 1:1 매칭 복리 정산 및 수동 부분매도 시 1층 목표정량 동기화]
4) 🔗 [tg_ui_plugin.py 심볼 완벽 호환] 전술 제어반(/settlement)에서 봇 작동 OFF ➔ ON 재개 시 호출되는
   relock_stratum_on_bot_resume() 함수를 정식 제공하여 AST 심볼 임포트 무결성 100% 충족!
5) 04:00 ~ 04:06 EST 프리장 개장 초기 호가 안정화 및 당일 시드보호 패스(Case 74) · 당일 스텝업 해금(Case 76) ·
   당일 황금시간 전액매수/포켓익절(Case 80) · 당일 예비수혈/자투리차단(Case 77) 0회 리셋(단 1회 입금 알림 래치 보존) ·
   16:00 EST 일일 결산 후 애프터·데이마켓 익절 감시 무중단 직결(Case 79, Case 83) · 17:00 EST 일일 GC 및 3중 금고 스냅샷 백업(Case 68)
- 제1헌법 ~ 제6헌법 및 Case 01 ~ 84 완벽 준수
"""

from __future__ import annotations

import asyncio
import gc
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from quant_engine import (
    GoldenAllInPocket,
    MAX_GRID_TIERS_7,
    MAX_GRID_TIERS_12,
    MAX_RESERVE_PORTIONS,
    StratumBucket,
    buckets_from_dicts,
    buckets_to_dicts,
    calc_sell_realized_pnl,
    compute_reserve_repayment_on_zero,
    enforce_true_breakeven_floor_on_buckets,
    has_active_l1_bucket,
    match_and_remove_sold_buckets_7tier,
    pocket_from_dict,
    pocket_to_dict,
    relabel_upper_grid_tiers,
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
    sync_pending_sell_order_plugin,
)
from sniper_plugin import (
    is_within_auto_fill_grace_shield,
    mark_auto_fill_grace_shield,
    mark_reentry_monitor_60s_cycle_shield,
    mark_reserve_deposit_check_shield,
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

# toss_api 심볼 불일치 방지를 위해 기본 환율 상수를 모듈 내부에 직접 정의
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
    context.api.probe_latest_manual_fill_price() 가 존재하면 호출하여
    토스 GET /api/v1/orders?status=CLOSED&symbol=SOXL 에서 미정산 수동 체결 단가와 orderId 목록을 역추적하고,
    폴백 시 fallback_price 를 안전하게 반환한다.
    """
    settled_oids: List[str] = list(st.get("last_settled_order_ids") or [])
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
                return round(safe_float(exec_p, fallback_price), 4), settled_oids[-50:]
        except Exception as exc:
            logger.debug("수동 체결 단가 역추적 폴백 사용(%s): %s", side, exc)
    return round(max(0.01, safe_float(fallback_price, 0.01)), 4), settled_oids[-50:]


# ---------------------------------------------------------------------------
# [핵심 1] 로컬 7층 골디락스 그리드 + 독립 골든포켓 원장 ↔ 토스 실보유 잔고(/api/v1/holdings) 무결성 화해 (Case 58 ~ 84)
# ---------------------------------------------------------------------------
async def reconcile_stratum_with_broker_holdings_plugin(
    context: Any,
    holdings: Dict[str, Dict[str, Any]],
    prices: Dict[str, float],
    now_est: Optional[datetime] = None,
    force_sync: bool = False,
) -> Dict[str, Any]:
    """
    🚨 Case 58, Case 60, Case 61, Case 63, Case 65, Case 66, Case 68, Case 69, Case 71 ~ Case 84:
    프로세스 재기동 시, 04:00 EST 오프닝 동기화 시, 또는 장중/애프터장/데이장 사용자가 토스 앱에서 수동 매매했을 때
    로컬 7층 그리드 원장(buckets)과 독립 골든포켓(golden_pocket)의 합산 보유 주수(ledger_qty = grid_qty + gp_qty)를
    토스 실계좌 보유 주수(h_qty)와 대조하여 화해한다.
    """
    if not isinstance(holdings, dict) or not getattr(
        context, "holdings_fetch_ok", True
    ):
        return {"status": "SKIP_HOLDINGS_NOT_READY"}

    st = context.ledger.get_state(TARGET_SYMBOL)
    pending_buy_oid = str(st.get("buy_order_id") or "").strip()
    pending_sell_oid = str(st.get("sell_order_id") or "").strip()

    # 🚨 [Case 66 핵심 방어] 봇이 발주한 지정가 매수/매도 주문이 대기 중일 때 가로채기 금지 및 선행 정산!
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
    gp = pocket_from_dict(st.get("golden_pocket"))
    grid_qty = sum(b.qty for b in buckets)
    gp_qty = gp.qty if gp.is_active else 0
    # [Case 80]: 그리드 보유 수량 + 독립 골든포켓 수량 통합 대조
    ledger_qty = grid_qty + gp_qty

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

    # [케이스 1] 수량이 완벽히 일치하는 경우 -> 즉시 통과
    if h_qty == ledger_qty:
        return {
            "status": "STRATUM_IN_SYNC",
            "held_shares": h_qty,
            "grid_shares": grid_qty,
            "pocket_shares": gp_qty,
            "tiers": len(buckets),
        }

    # 🚨 [Case 61 & Case 69 최상단 양방향 15.0초 인덱싱 그레이스 쉴드]
    if is_within_auto_fill_grace_shield(context, TARGET_SYMBOL):
        logger.info(
            "🛡️ [Case 61/69 양방향 인덱싱 그레이스 쉴드 작동] 최근 자동 체결 직후 잔고 API 시차 감지(토스 %d주 vs 원장 %d주[그리드 %d+포켓 %d]) -> 원장 무결성 안전 보호",
            h_qty,
            ledger_qty,
            grid_qty,
            gp_qty,
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

    # [케이스 2] 토스 실보유 0주인데 로컬 원장에 지층/골든포켓이 남아 있는 경우
    # (데이장/장중 수동 전량 청산 -> 전 지층 및 골든포켓 순수원가 매칭 세후 실현수익 복리 산입 & 예비시드 자동 상환 & 0주 싸이클 종료)
    if h_qty == 0 and ledger_qty > 0:
        default_fb_p = (
            buckets[0].actual_avg_price
            if buckets
            else (gp.actual_avg_price if gp.is_active else 50.0)
        )
        fb_sell_p = (
            live_p
            if live_p > 0.0
            else (safe_float(st.get("anchor_price"), 0.0) or default_fb_p)
        )
        manual_sell_p, updated_settled_oids = await _probe_manual_fill_price_safe(
            context=context,
            side="SELL",
            target_qty=ledger_qty,
            st=st,
            fallback_price=fb_sell_p,
        )
        match_res = match_and_remove_sold_buckets_7tier(
            buckets=buckets,
            delta_remove_qty=ledger_qty,
            sell_exec_price=manual_sell_p,
            max_tiers=MAX_GRID_TIERS_7,
            golden_pocket=gp,
        )
        pnl_info = match_res["pnl_info"]
        gross_pnl = safe_float(pnl_info.get("gross_pnl_usd"), 0.0)
        fee_usd = safe_float(pnl_info.get("fee_usd"), 0.0)
        net_pnl = safe_float(pnl_info.get("net_pnl_usd"), 0.0)
        net_rate = safe_float(pnl_info.get("net_rate_pct"), 0.0)

        sold_pocket_q = safe_int(match_res.get("sold_pocket_qty"), 0)
        gp_sell_inc = 1 if sold_pocket_q > 0 else 0
        pocket_net_pnl = 0.0
        if sold_pocket_q > 0 and gp.is_active:
            p_pnl = calc_sell_realized_pnl(
                sold_qty=sold_pocket_q,
                sell_exec_price=manual_sell_p,
                sold_actual_cost_usd=gp.actual_cost_usd,
            )
            pocket_net_pnl = safe_float(p_pnl.get("net_pnl_usd"), 0.0)

        tot_sell_ev = safe_int(st.get("total_sell_events"), 0) + 1
        tot_sold_sh = safe_int(st.get("total_sold_shares"), 0) + ledger_qty
        win_ev = safe_int(st.get("win_sell_events"), 0) + (
            1 if net_pnl > 0.0 else 0
        )
        day_sell_ev = safe_int(st.get("daily_sell_events"), 0) + 1
        gp_sell_cnt = safe_int(st.get("golden_pocket_sell_cnt"), 0) + gp_sell_inc
        day_gp_sell_cnt = (
            safe_int(st.get("daily_golden_pocket_sell_cnt"), 0) + gp_sell_inc
        )
        gp_net_cum = round(
            safe_float(st.get("golden_realized_net_usd"), 0.0) + pocket_net_pnl,
            4,
        )
        gp_net_day = round(
            safe_float(st.get("daily_golden_realized_net_usd"), 0.0)
            + pocket_net_pnl,
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

        # [Case 77 : 수동 전량 매도(0주) 시 온디맨드 예비시드 원금 자동 상환 및 6/6회분 한도 복구]
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

        if cur_inj_res_usd > 0.0:
            repay_info = compute_reserve_repayment_on_zero(
                initial_seed_usd=init_seed,
                cumulative_realized_net_usd=cum_net,
                injected_reserve_usd=cur_inj_res_usd,
                used_reserve_portions_cnt=cur_used_res_cnt,
                max_reserve_portions=MAX_RESERVE_PORTIONS,
            )
            if bool(repay_info.get("did_repay")):
                repaid_this_time = round(
                    safe_float(repay_info.get("repaid_usd"), 0.0), 4
                )
                next_inj_res_usd = round(
                    safe_float(repay_info.get("rem_injected_reserve_usd"), 0.0),
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
        mark_reserve_deposit_check_shield(
            context=context,
            symbol=TARGET_SYMBOL,
            clear_shield=True,
        )
        updated_st = await context.ledger.update_state(
            TARGET_SYMBOL,
            buckets=[],
            golden_pocket=GoldenAllInPocket().to_dict(),
            anchor_price=manual_sell_p,
            cycle_min_buy_price=0.0,
            ratchet_anchor_price=manual_sell_p,
            cycle_reanchor_credit_usd=0.0,
            l1_target_quota_qty=0,
            used_reserve_portions_cnt=next_used_res_cnt,
            injected_reserve_usd=next_inj_res_usd,
            cumulative_reserve_repaid_usd=cum_repaid_usd,
            waiting_reserve_deposit=False,
            waiting_reserve_deposit_alert_sent=False,
            required_reserve_deposit_usd=0.0,
            last_reserve_check_ts=0.0,
            last_sell_fill_ts=now_zero_ts,
            last_cycle_end_ts=now_zero_ts,
            last_sell_gate_eval_ts=0.0,
            last_reentry_eval_ts=0.0,
            buy_order_id="",
            sell_order_id="",
            ordered_qty=0,
            target_sell_price=0.0,
            pending_sell_mode="",
            pending_sell_indices=[],
            pending_sell_pocket_qty=0,
            pending_lot_type="",
            pending_step_up_min_price=0.0,
            last_settled_order_ids=updated_settled_oids,
            total_sell_events=tot_sell_ev,
            total_sold_shares=tot_sold_sh,
            win_sell_events=win_ev,
            daily_sell_events=day_sell_ev,
            golden_pocket_sell_cnt=gp_sell_cnt,
            daily_golden_pocket_sell_cnt=day_gp_sell_cnt,
            golden_realized_net_usd=gp_net_cum,
            daily_golden_realized_net_usd=gp_net_day,
            cumulative_realized_gross_usd=cum_gross,
            cumulative_realized_fee_usd=cum_fee,
            cumulative_realized_net_usd=cum_net,
            daily_realized_net_usd=day_net,
        )
        free_cash_now = safe_float(updated_st.get("free_cash_usd"), 0.0)
        logger.info(
            "🧹 [SOXL 수동 전량청산 0주 싸이클 종료 & 실현익 복리 정산] %d주 @ $%.2f (매칭층: %s · 세후손익 %+.2f$ · 예비상환 $%.2f · 가용현금 $%.2f · 🛡️60초 타임쉴드 각인)",
            ledger_qty,
            manual_sell_p,
            match_res.get("sold_tier_desc"),
            net_pnl,
            repaid_this_time,
            free_cash_now,
        )
        if hasattr(context, "send_slim_alert"):
            s_sign = "+" if net_pnl >= 0.0 else "-"
            r_sign = "+" if net_rate >= 0.0 else ""
            repay_note = ""
            if repaid_this_time > 0.0:
                avail_p = max(0, MAX_RESERVE_PORTIONS - next_used_res_cnt)
                repay_note = (
                    f" · 💉예비시드 원금 ${repaid_this_time:,.2f} 자동상환"
                    f"({avail_p}/{MAX_RESERVE_PORTIONS}회분 복구)"
                )
            # MODIFIED [Case 79 & Case 84]: 수동 전량매도 시 현재 세션(장외 또는 15:29:01 ~ 16:00:00 EST 마감 30분전 컷오프)에 따른 안내 문구 분기
            dt_chk = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
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
            if is_ext_now:
                next_entry_note = "🔒장외 매수잠금 · 04:07 EST 프리장 개시 후 새 1층 진입 대기"
            elif will_hit_late_cutoff:
                next_entry_note = "🔒장마감 30분전(15:30~16:00) 새 사이클 진입 차단(고점 오버나이트 방어) · 익일 04:07 EST 프리장 새 1층 진입 대기"
            else:
                next_entry_note = "🛡️04:07~15:29 EST 매수구간 내 60초 타임쉴드 후 새 1층 진입 대기"

            await context.send_slim_alert(
                title=f"🧹 [SOXL 수동 전량매도 0주 동기화] {ledger_qty}주 @ ${manual_sell_p:.2f} ({r_sign}{net_rate:.2f}%)",
                body=(
                    f"소진층: {match_res.get('sold_tier_desc')} · "
                    f"세후순익 {s_sign}${abs(net_pnl):,.2f} 시드 복리산입 완료{repay_note} · "
                    f"가용현금 ${free_cash_now:,.2f} ({next_entry_note})"
                ),
            )
        return {
            "status": "CLEARED_TO_ZERO_HOLDINGS",
            "prev_qty": ledger_qty,
            "manual_sell_price": manual_sell_p,
            "net_pnl_usd": net_pnl,
            "repaid_reserve_usd": repaid_this_time,
            "free_cash_usd": free_cash_now,
        }

    # [케이스 3] 토스 실보유 수량(h_qty > 0)이 존재하는데 로컬 원장이 비어 있는 경우 (Case 68 & Case 80 백업 금고 우선 복원)
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
            vault_gp = pocket_from_dict(vault_st.get("golden_pocket"))
            vault_qty = sum(b.qty for b in vault_buckets) + (
                vault_gp.qty if vault_gp.is_active else 0
            )
            vault_seed = _resolve_valid_seed_from_state(vault_st)

            if vault_qty == h_qty and (
                len(vault_buckets) > 0 or vault_gp.is_active
            ):
                restored_kw: Dict[str, Any] = dict(vault_st)
                restored_kw["buckets"] = buckets_to_dicts(vault_buckets)
                restored_kw["golden_pocket"] = vault_gp.to_dict()
                restored_kw["initial_seed_usd"] = vault_seed
                restored_kw["cycle_reanchor_credit_usd"] = 0.0
                restored_kw["buy_order_id"] = ""
                restored_kw["sell_order_id"] = ""
                restored_kw["ordered_qty"] = 0
                restored_kw["pending_sell_indices"] = []
                restored_kw["pending_sell_pocket_qty"] = 0
                restored_kw["pending_step_up_min_price"] = 0.0
                # [Case 68 & Case 78]: 백업 금고 복원 시 활성 1층 여부에 따라 l1_target_quota_qty 정합성 보장
                if has_active_l1_bucket(vault_buckets):
                    restored_kw["last_reentry_eval_ts"] = 0.0
                    restored_kw["l1_target_quota_qty"] = max(
                        vault_buckets[0].qty,
                        safe_int(vault_st.get("l1_target_quota_qty"), 0),
                    )
                else:
                    restored_kw["l1_target_quota_qty"] = 0
                await context.ledger.update_state(TARGET_SYMBOL, **restored_kw)
                logger.info(
                    "🛡️ [Case 68/72/76/77/80 백업 금고 7층 그리드/골든포켓 100%% 원형 복원 완료] 총 %d주 (그리드 %d개층 + 골든포켓 %d주 · 시드 $%.2f · 기억저가 $%.2f)",
                    h_qty,
                    len(vault_buckets),
                    vault_gp.qty,
                    vault_seed,
                    safe_float(vault_st.get("cycle_min_buy_price"), 0.0),
                )
                return {
                    "status": "RESTORED_FROM_BACKUP_VAULT",
                    "held_shares": h_qty,
                    "tiers": len(vault_buckets),
                    "pocket_shares": vault_gp.qty,
                }

        # [Case 19 & Case 63]: 백업 금고에 일치하는 지층이 없는 경우(0주 상태에서 수동 신규 매수 진입):
        # 토스 CLOSED 주문 원장에서 수동 매수 체결단가 및 orderId를 역추적하여 기정산 목록에 등록하고 텔레그램 알림을 즉시 타전!
        ref_p = h_avg if h_avg > 0.0 else (live_p if live_p > 0.0 else 100.0)
        probed_0sh_p, updated_settled_oids = await _probe_manual_fill_price_safe(
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
                round(probed_0sh_p, 4) if probed_0sh_p > 0.0 else round(ref_p, 4)
            )
            cost_u = round(float(h_qty) * pure_ref_p, 4)

        init_seed = _resolve_valid_seed_from_state(st)
        if isinstance(vault_st, dict) and init_seed <= 100.0:
            init_seed = _resolve_valid_seed_from_state(vault_st)

        est_lots = max(
            1, int(round(cost_u / max(1.0, init_seed * 0.08)))
        )
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
        mark_reserve_deposit_check_shield(
            context=context,
            symbol=TARGET_SYMBOL,
            clear_shield=True,
        )
        update_kw: Dict[str, Any] = {
            "initial_seed_usd": init_seed,
            "buckets": buckets_to_dicts([restored_bucket]),
            "golden_pocket": GoldenAllInPocket().to_dict(),
            "anchor_price": pure_ref_p,
            "cycle_min_buy_price": pure_ref_p,
            "ratchet_anchor_price": pure_ref_p,
            "cycle_reanchor_credit_usd": 0.0,
            "l1_target_quota_qty": h_qty,
            "buy_order_id": "",
            "sell_order_id": "",
            "ordered_qty": 0,
            "pending_sell_indices": [],
            "pending_sell_pocket_qty": 0,
            "pending_step_up_min_price": 0.0,
            "waiting_reserve_deposit": False,
            "waiting_reserve_deposit_alert_sent": False,
            "required_reserve_deposit_usd": 0.0,
            "last_reserve_check_ts": 0.0,
            "last_settled_order_ids": updated_settled_oids,
            "entry_ts": now_sync_ts,
            "last_buy_fill_ts": now_sync_ts,
            "last_reentry_eval_ts": 0.0,
        }
        if isinstance(vault_st, dict):
            if vault_st.get("golden_allin_mode"):
                update_kw["golden_allin_mode"] = vault_st["golden_allin_mode"]
            for stat_k in (
                "cumulative_realized_net_usd",
                "cumulative_realized_gross_usd",
                "cumulative_realized_fee_usd",
                "cumulative_leftover_saved_usd",
                "cumulative_reanchor_drop_usd",
                "reanchor_cnt",
                "indiv_grid_sell_cnt",
                "wma_grad_sell_cnt",
                "seed_protect_pass_cnt",
                "daily_seed_protect_pass_cnt",
                "cond_unlock_buy_events",
                "daily_unlock_buy_events",
                "golden_allin_buy_events",
                "daily_golden_allin_buy_events",
                "golden_pocket_sell_cnt",
                "daily_golden_pocket_sell_cnt",
                "golden_realized_net_usd",
                "daily_golden_realized_net_usd",
                "used_reserve_portions_cnt",
                "injected_reserve_usd",
                "total_reserve_injected_cnt",
                "daily_reserve_injected_cnt",
                "cumulative_reserve_repaid_usd",
                "dust_guard_blocked_cnt",
                "daily_dust_guard_blocked_cnt",
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
        summary_0sh = summarize_stratum_portfolio(
            updated_st, live_price=pure_ref_p
        )
        l1_target_0sh = safe_float(summary_0sh.get("l1_target_price"), 0.0)
        free_cash_0sh = safe_float(summary_0sh.get("free_cash_usd"), 0.0)
        trig_buy_0sh = safe_float(summary_0sh.get("trigger_buy_price"), 0.0)
        drop_req_0sh = safe_float(summary_0sh.get("drop_buy_pct"), -1.0)

        logger.info(
            "♻️ [SOXL 실잔고 기반 순수원가 1층 복원 완료] %d주 @ $%.2f (원금 $%.2f · 시드 $%.2f · 추정 %d회차 · 기억저가 $%.2f)",
            h_qty,
            pure_ref_p,
            cost_u,
            init_seed,
            est_lots,
            pure_ref_p,
        )
        # [Case 63 수동 신규 매수 1층 동기화 텔레그램 슬림 알림 즉시 타전]
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
        # 4-1) 수동 추가 매수 동기화:
        delta_q = h_qty - ledger_qty
        fb_buy_p = live_p if live_p > 0.0 else h_avg
        if fb_buy_p <= 0.0:
            fb_buy_p = (
                buckets[0].actual_avg_price
                if buckets
                else (gp.actual_avg_price if gp.is_active else 50.0)
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

        merged_buckets = vrev_add_quota_lot_and_merge_2tier(
            queue=buckets,
            buy_qty=delta_q,
            buy_price=est_buy_p,
            actual_spent_usd=added_spent_usd,
            lot_type="MANUAL_SYNC_L1",
            max_tiers=MAX_GRID_TIERS_7,
        )

        # [Case 63 & Case 78]:
        # 수동 추가매수 물량이 기존 1층보다 높아서 상단 층(GRID_L2~L7)으로 중간 편입된 경우에는 기존 1층의 l1_target_quota_qty 를 유지하고,
        # 수동 추가매수 물량이 새로운 1층(merged_buckets[0])이 된 경우에는 새 1층 수량(merged_buckets[0].qty)으로 동기화하여
        # 이전 1층 목표 정량과의 차이로 인한 허위 잔량 발주(TOPUP_1FL)를 100% 원천 차단!
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
            anchor_price=est_buy_p,
            cycle_min_buy_price=round(new_min_p, 4),
            ratchet_anchor_price=est_buy_p,
            cycle_reanchor_credit_usd=0.0,
            l1_target_quota_qty=next_l1_target_q_manual,
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
            "➕ [SOXL 수동 추가매수 7층 그리드 단가비교 편입 완료] +%d주 @ $%.2f 반영 -> 총 %d주(%d개층 + 골든포켓 %d주 · 1층목표 %d주 · 기억저가 $%.2f)",
            delta_q,
            est_buy_p,
            h_qty,
            len(merged_buckets),
            gp_qty,
            next_l1_target_q_manual,
            new_min_p,
        )
        # [Case 63 수동 추가매수 7층 그리드 편입 텔레그램 슬림 알림 즉시 타전]
        if hasattr(context, "send_slim_alert"):
            if not prev_had_active_l1:
                pos_desc = "공석 1층 독립 편입(상단 비병합)"
            elif is_mid_tier_inserted:
                pos_desc = f"상단 2~{len(merged_buckets)}층 단가비교 중간편입"
            else:
                pos_desc = "새 1층 배치(기존층 상단승격)"

            upper_add_note = (
                f" · 2~{len(merged_buckets)}층({u_cnt_add}개층·{u_qty_add}주) 이평 ${u_wma_p_add:.2f}(목표 ${u_wma_t_add:.2f})"
                if len(merged_buckets) >= 2
                else ""
            )
            gp_add_note = f"+골든포켓 {gp_qty}주" if gp_qty > 0 else ""
            await context.send_slim_alert(
                title=(
                    f"➕ [SOXL 수동 추가매수 그리드 편입] "
                    f"+{delta_q}주 @ ${est_buy_p:.2f} (총 {h_qty}주 · {len(merged_buckets)}개층{gp_add_note})"
                ),
                body=(
                    f"편입위치: {pos_desc} (추가원금 ${added_spent_usd:,.2f}) · "
                    f"🛡️60초 타임쉴드 후 1층목표 ${l1_target_add:.2f}(+1.5%) 감시{upper_add_note} · "
                    f"기억저가 ${new_min_p:.2f} 잠금 · 가용현금 ${free_cash_add:,.2f}"
                ),
            )
        return {
            "status": "SYNCED_MANUAL_BUY_ADDITION",
            "added_qty": delta_q,
            "buy_price": est_buy_p,
            "held_shares": h_qty,
            "tiers": len(merged_buckets),
            "l1_target_quota_qty": next_l1_target_q_manual,
        }

    # 4-2) h_qty < ledger_qty (수동 부분 매도 또는 체결 후 잔여 수량 조정):
    delta_remove = ledger_qty - h_qty
    orig_l1_qty = (
        buckets[0].qty
        if (buckets and has_active_l1_bucket(buckets))
        else 0
    )
    default_part_p = (
        buckets[0].actual_avg_price
        if buckets
        else (gp.actual_avg_price if gp.is_active else 50.0)
    )
    fb_part_sell_p = live_p if live_p > 0.0 else default_part_p
    manual_sell_p, updated_settled_oids = await _probe_manual_fill_price_safe(
        context=context,
        side="SELL",
        target_qty=delta_remove,
        st=st,
        fallback_price=fb_part_sell_p,
    )
    match_res = match_and_remove_sold_buckets_7tier(
        buckets=buckets,
        delta_remove_qty=delta_remove,
        sell_exec_price=manual_sell_p,
        max_tiers=MAX_GRID_TIERS_7,
        golden_pocket=gp,
    )
    rem_buckets: List[StratumBucket] = match_res["rem_buckets"]
    rem_gp_dict: Dict[str, Any] = match_res.get(
        "rem_golden_pocket", GoldenAllInPocket().to_dict()
    )
    rem_gp_obj = pocket_from_dict(rem_gp_dict)
    sold_pocket_q = safe_int(match_res.get("sold_pocket_qty"), 0)

    pnl_info = match_res["pnl_info"]
    gross_pnl = safe_float(pnl_info.get("gross_pnl_usd"), 0.0)
    fee_usd = safe_float(pnl_info.get("fee_usd"), 0.0)
    net_pnl = safe_float(pnl_info.get("net_pnl_usd"), 0.0)
    net_rate = safe_float(pnl_info.get("net_rate_pct"), 0.0)

    gp_sell_inc = 1 if sold_pocket_q > 0 else 0
    pocket_net_pnl = 0.0
    if sold_pocket_q > 0 and gp.is_active:
        sold_gp_cost = round(
            gp.actual_cost_usd
            - (rem_gp_obj.actual_cost_usd if rem_gp_obj.is_active else 0.0),
            4,
        )
        p_pnl = calc_sell_realized_pnl(
            sold_qty=sold_pocket_q,
            sell_exec_price=manual_sell_p,
            sold_actual_cost_usd=max(0.0, sold_gp_cost),
        )
        pocket_net_pnl = safe_float(p_pnl.get("net_pnl_usd"), 0.0)

    # [Case 63 & Case 78]:
    # 1) 수동 부분매도로 1층이 전량 소진되었으면 l1_target_quota_qty = 0 클리어.
    # 2) 수동 부분매도로 1층 수량이 일부 차감(rem_buckets[0].qty < orig_l1_qty)된 경우에는
    #    방금 매도한 수량을 미체결 잔량(TOPUP_1FL)으로 오인해 자동 재매수하지 않도록
    #    next_l1_target_q = rem_buckets[0].qty 로 즉시 하향 동기화!
    # 3) 오직 1층 수량이 전혀 줄어들지 않은 경우(예: 골든포켓만 수동 매도된 경우)에만 기존 l1_target_quota_qty 보존.
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

    tot_sell_ev = safe_int(st.get("total_sell_events"), 0) + 1
    tot_sold_sh = safe_int(st.get("total_sold_shares"), 0) + delta_remove
    win_ev = safe_int(st.get("win_sell_events"), 0) + (
        1 if net_pnl > 0.0 else 0
    )
    day_sell_ev = safe_int(st.get("daily_sell_events"), 0) + 1
    gp_sell_cnt = safe_int(st.get("golden_pocket_sell_cnt"), 0) + gp_sell_inc
    day_gp_sell_cnt = (
        safe_int(st.get("daily_golden_pocket_sell_cnt"), 0) + gp_sell_inc
    )
    gp_net_cum = round(
        safe_float(st.get("golden_realized_net_usd"), 0.0) + pocket_net_pnl, 4
    )
    gp_net_day = round(
        safe_float(st.get("daily_golden_realized_net_usd"), 0.0)
        + pocket_net_pnl,
        4,
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

    total_rem_cost = round(
        sum(b.actual_cost_usd for b in rem_buckets)
        + (rem_gp_obj.actual_cost_usd if rem_gp_obj.is_active else 0.0),
        4,
    )
    pure_overall_avg = (
        round(total_rem_cost / float(h_qty), 4) if h_qty > 0 else 0.0
    )

    # 골든포켓만 수동 부분매도된 경우 기존 그리드 anchor_price 보존
    is_pocket_only_manual = bool(
        sold_pocket_q == delta_remove and len(rem_buckets) == len(buckets)
    )
    old_anchor_p = safe_float(st.get("anchor_price"), manual_sell_p)
    next_anchor_p = (
        old_anchor_p
        if (is_pocket_only_manual and old_anchor_p > 0.0)
        else manual_sell_p
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
    mark_reserve_deposit_check_shield(
        context=context,
        symbol=TARGET_SYMBOL,
        clear_shield=True,
    )
    updated_st = await context.ledger.update_state(
        TARGET_SYMBOL,
        buckets=buckets_to_dicts(rem_buckets),
        golden_pocket=rem_gp_obj.to_dict(),
        anchor_price=next_anchor_p,
        ratchet_anchor_price=next_anchor_p,
        cycle_reanchor_credit_usd=0.0,
        l1_target_quota_qty=next_l1_target_q,
        waiting_reserve_deposit=False,
        waiting_reserve_deposit_alert_sent=False,
        required_reserve_deposit_usd=0.0,
        last_reserve_check_ts=0.0,
        last_sell_fill_ts=now_part_sell_ts,
        last_sell_gate_eval_ts=0.0,
        last_reentry_eval_ts=0.0,
        pending_sell_indices=[],
        pending_sell_pocket_qty=0,
        pending_step_up_min_price=0.0,
        last_settled_order_ids=updated_settled_oids,
        total_sell_events=tot_sell_ev,
        total_sold_shares=tot_sold_sh,
        win_sell_events=win_ev,
        daily_sell_events=day_sell_ev,
        golden_pocket_sell_cnt=gp_sell_cnt,
        daily_golden_pocket_sell_cnt=day_gp_sell_cnt,
        golden_realized_net_usd=gp_net_cum,
        daily_golden_realized_net_usd=gp_net_day,
        cumulative_realized_gross_usd=cum_gross,
        cumulative_realized_fee_usd=cum_fee,
        cumulative_realized_net_usd=cum_net,
        daily_realized_net_usd=day_net,
    )
    free_cash_now = safe_float(updated_st.get("free_cash_usd"), 0.0)
    logger.info(
        "➖ [Case 69/72/78/80 SOXL 수동 부분매도 순수원가 정산 완료] %d주 -> %d주(%d개층+포켓 %d주) 조정 (매칭층: %s @ 체결가 $%.2f · 세후손익 %+.2f$ 복리산입 · 1층목표 %d주 · 잔여순수평단 $%.2f 보존)",
        ledger_qty,
        h_qty,
        len(rem_buckets),
        rem_gp_obj.qty,
        match_res.get("sold_tier_desc"),
        manual_sell_p,
        net_pnl,
        next_l1_target_q,
        pure_overall_avg,
    )
    if hasattr(context, "send_slim_alert"):
        s_sign = "+" if net_pnl >= 0.0 else "-"
        r_sign = "+" if net_rate >= 0.0 else ""
        gp_rem_note = (
            f"+골든포켓 {rem_gp_obj.qty}주" if rem_gp_obj.is_active else ""
        )
        await context.send_slim_alert(
            title=f"➖ [SOXL 수동 부분매도 정산] {delta_remove}주 @ ${manual_sell_p:.2f} ({r_sign}{net_rate:.2f}%)",
            body=(
                f"매칭층: {match_res.get('sold_tier_desc')} · "
                f"세후순익 {s_sign}${abs(net_pnl):,.2f} 시드 복리산입 · "
                f"잔여 {h_qty}주({len(rem_buckets)}개층{gp_rem_note} · 순수평단 ${pure_overall_avg:.2f}) 보존 · 가용현금 ${free_cash_now:,.2f}"
            ),
        )
    return {
        "status": "SYNCED_MANUAL_PARTIAL_REDUCTION",
        "held_shares": h_qty,
        "sold_qty": delta_remove,
        "manual_sell_price": manual_sell_p,
        "net_pnl_usd": net_pnl,
        "tiers": len(rem_buckets),
        "pocket_shares": rem_gp_obj.qty,
        "l1_target_quota_qty": next_l1_target_q,
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
    """
    전술 제어반(/settlement)에서 스나이퍼 작동을 🔴 OFF ➔ 🟢 ON 으로 전환할 때
    tg_ui_plugin.py 에서 호출하는 실잔고 ↔ 7층 그리드/골든포켓 원장 즉시 동기화 함수.
    """
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
# [핵심 2] 04:00 ~ 04:06 EST 프리장 개장 초기 호가 안정화 · force_settle 선취소-후정산(Cancel-then-Sync) · 일일 카운터 롤오버 (Case 66, 74, 76, 77, 78, 79, 80)
# ---------------------------------------------------------------------------
async def execute_0400_premarket_stabilization_plugin(
    context: Any,
    holdings: Dict[str, Dict[str, Any]],
    prices: Dict[str, float],
    now_est: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    # MODIFIED [Case 66, Case 73, Case 74, Case 76, Case 77, Case 78, Case 79 & Case 80]:
    🔹 04:00 ~ 04:06 EST:
    1) 데이마켓 잔류 미체결 주문을 먼저 취소(cancel_all_open_orders)하여 주문 상태를 최종 확정(CANCELED / FILLED)한 직후,
       sync_pending_sell_order_plugin(..., force_settle=True) / sync_pending_buy_order_plugin(..., force_settle=True) 를 호출하여
       발주 후 60초 미만인 부분 체결(PARTIAL_FILLED / PENDING_CANCEL) 또는 취소 직전 체결분을
       단 1주도 유실하지 않고 100% 정식 커밋 정산한다 (Cancel-then-Force-Sync 파이프라인).
    2) 일일 카운터(시드보호패스 · 스텝업해금 · 황금시간 전액매수/포켓익절 · 예비수혈 · 자투리차단)를 0회로 리셋한다
       (단, waiting_reserve_deposit_alert_sent 단 1회 입금 알림 래치는 보존).
    3) 오버나이트 이월 SOXL 1 ~ 7층 지층 및 golden_pocket 을 실계좌와 대조 동기화한다.
    """
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

    done_date = str(getattr(context, "last_0400_sync_date", "") or "")
    if done_date == today_str:
        return {"status": "ALREADY_STABILIZED_TODAY", "date": today_str}

    setattr(context, "last_0400_sync_date", today_str)

    canceled_cnt = await context.api.cancel_all_open_orders(
        symbol=TARGET_SYMBOL
    )
    # 취소 직후 혹시 남아 있던 미결 주문이 부분/전량 체결되었는지 force_settle=True 로 한 번 더 확인 커밋
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

    mark_reentry_monitor_60s_cycle_shield(
        context=context, symbol=TARGET_SYMBOL, clear_shield=True
    )
    mark_reserve_deposit_check_shield(
        context=context, symbol=TARGET_SYMBOL, clear_shield=True
    )
    mark_extended_sell_restriction_cooldown(
        context=context, symbol=TARGET_SYMBOL, cooldown_sec=0.0, reason="CLEAR"
    )
    snap_map = getattr(context, "exit_snapshot_cache", None)
    if isinstance(snap_map, dict) and isinstance(
        snap_map.get(TARGET_SYMBOL), dict
    ):
        snap_map[TARGET_SYMBOL]["ext_sell_restrict_until_mono"] = 0.0

    await context.ledger.update_state(
        TARGET_SYMBOL,
        buy_order_id="",
        sell_order_id="",
        ordered_qty=0,
        target_sell_price=0.0,
        pending_sell_mode="",
        pending_sell_indices=[],
        pending_sell_pocket_qty=0,
        pending_lot_type="",
        pending_step_up_min_price=0.0,
        daily_seed_protect_pass_cnt=0,
        daily_unlock_buy_events=0,
        daily_golden_allin_buy_events=0,
        daily_golden_pocket_sell_cnt=0,
        daily_golden_realized_net_usd=0.0,
        daily_reserve_injected_cnt=0,
        daily_dust_guard_blocked_cnt=0,
        last_evaluated_buy_bucket_id=-1,
        last_evaluated_date=today_str,
        last_reentry_eval_ts=0.0,
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
        "🌅 [04:00 EST 프리장 오프닝 안정화 완료] 당일 패스/해금/골든/예비수혈 0회 리셋 · 잔류주문 취소=%d건 · 7층그리드동기화=%s",
        canceled_cnt,
        sync_res.get("status"),
    )
    return {
        "status": "PREMARKET_0400_STABILIZED",
        "canceled_orders": canceled_cnt,
        "sync_result": sync_res,
    }


# ---------------------------------------------------------------------------
# [핵심 3] 16:00 ~ 16:59 EST 정규장 마감 일일 결산 보고 & force_settle 선취소-후정산 · 애프터마켓 익절 감시 무중단 직결 (Case 66 ~ 84)
# ---------------------------------------------------------------------------
async def execute_1600_daily_closing_settlement_plugin(
    context: Any,
    holdings: Dict[str, Dict[str, Any]],
    prices: Dict[str, float],
    now_est: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    # MODIFIED [Case 01, Case 65, Case 66, Case 68, Case 72, Case 74, Case 76, Case 77, Case 78, Case 79, Case 80, Case 83 & Case 84]:
    🔹 16:00 ~ 16:59 EST:
    0) 만약 현재 시각이 정확히 16:00:xx EST (hm == 1600)이고 원장에 아직 60.0초 대기 중인 미결 주문(buy_order_id / sell_order_id)이
       살아 있다면, 15:59:xx EST 또는 16:00:00 EST(72번 마감 버킷)에 발주된 주문이 60초를 채우지 못하고 조기 취소되는 일을 막기 위해
       먼저 일반 동기화(force_settle=False)만 수행하고 미결 주문이 유지 중이면 WAIT_1600_PENDING_ORDER_SETTLEMENT 를 반환하여
       주문이 완료되거나 16:01 EST 가 될 때까지 결산을 잠시 유예한다!
    1) 정규장 마감 결산 확정 시 먼저 cancel_all_open_orders() 로 미체결 잔량을 확정 취소 종료시킨 직후,
       sync_pending_buy_order_plugin(..., force_settle=True) / sync_pending_sell_order_plugin(..., force_settle=True) 를 호출하여
       발주 후 60초 미만인 부분 체결(PARTIAL_FILLED / PENDING_CANCEL) 또는 마감 직전 체결분을
       단 1주도 유실하지 않고 100% 정식 커밋(비례 자투리 절약금 · 골든포켓 · 세후 실현익) 정산한다.
    2) 보유 지층(1층 ~ 7층 및 golden_pocket)을 100% 오버나이트 안전 보존하며 당일 결산 보고를 단 1회 발송한다.
    3) 결산 직후 애프터마켓 및 데이마켓 ⚡1.5초 실시간 익절 매도 모니터가 무중단으로 이어진다!
    """
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    hm = dt_now.hour * 100 + dt_now.minute
    if not (1600 <= hm <= 1659):
        return {"status": "NOT_CLOSING_WINDOW"}

    today_str = dt_now.strftime("%Y-%m-%d")
    st = context.ledger.get_state(TARGET_SYMBOL)
    if str(st.get("last_closing_report_date") or "") == today_str:
        return {"status": "CLOSING_REPORT_ALREADY_SENT", "date": today_str}

    # NEW [Case 01, Case 65 & Case 66 : 16:00:xx EST 진행 중 미결 주문의 60초 대기 보호]
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

    # MODIFIED [Case 66, Case 78 & Case 80 : 16:00/16:01 마감 시 선(先) 미체결 취소 ➔ 후(後) force_settle=True 체결 정산]:
    # 먼저 미체결 잔량을 취소하여 PARTIAL_FILLED 주문을 CANCELED(부분 체결 완료) 상태로 확정시킨 직후
    # force_settle=True 로 sync_pending_buy/sell_order_plugin 을 호출함으로써 60초 미만 부분 체결 및 직전 체결 물량을 100% 정식 커밋한다!
    await context.api.cancel_all_open_orders(symbol=TARGET_SYMBOL)

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

    updated_st = await context.ledger.update_state(
        TARGET_SYMBOL,
        buy_order_id="",
        sell_order_id="",
        ordered_qty=0,
        target_sell_price=0.0,
        pending_sell_mode="",
        pending_sell_indices=[],
        pending_sell_pocket_qty=0,
        pending_lot_type="",
        pending_step_up_min_price=0.0,
        last_closing_report_date=today_str,
    )

    # 🛡️ Case 68: 정규장 마감 시점의 원장 상태를 날짜별 백업 금고에 즉시 스냅샷 저장
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
    day_net = safe_float(updated_st.get("daily_realized_net_usd"), 0.0)
    day_krw = day_net * fx_rate
    cum_net = safe_float(summary.get("cumulative_realized_net_usd"), 0.0)
    cum_roi = safe_float(summary.get("realized_roi_pct"), 0.0)
    free_cash = safe_float(summary.get("free_cash_usd"), 0.0)
    held_sh = safe_int(summary.get("held_shares"), 0)
    gp_sh = safe_int(summary.get("golden_pocket_qty"), 0)
    held_tiers = safe_int(summary.get("held_tiers"), 0)
    held_lots = safe_int(summary.get("held_lots"), 0)
    day_buy_ev = safe_int(updated_st.get("daily_buy_events"), 0)
    day_unlock_ev = safe_int(updated_st.get("daily_unlock_buy_events"), 0)
    cum_unlock_ev = safe_int(updated_st.get("cond_unlock_buy_events"), 0)
    day_g_buy = safe_int(updated_st.get("daily_golden_allin_buy_events"), 0)
    day_g_sell = safe_int(updated_st.get("daily_golden_pocket_sell_cnt"), 0)
    day_res_inj = safe_int(updated_st.get("daily_reserve_injected_cnt"), 0)
    used_res_cnt = safe_int(summary.get("used_reserve_portions_cnt"), 0)
    inj_res_usd = safe_float(summary.get("injected_reserve_usd"), 0.0)
    day_sell_ev = safe_int(updated_st.get("daily_sell_events"), 0)
    day_wma_grad = safe_int(updated_st.get("daily_wma_grad_sell_cnt"), 0)
    day_indiv_sell = safe_int(updated_st.get("daily_indiv_grid_sell_cnt"), 0)
    day_pass = safe_int(updated_st.get("daily_seed_protect_pass_cnt"), 0)
    day_saved = safe_float(updated_st.get("daily_leftover_saved_usd"), 0.0)

    if hasattr(context, "send_slim_alert"):
        d_sign = "+" if day_net >= 0.0 else "-"
        c_sign = "+" if cum_net >= 0.0 else "-"
        unlock_note = (
            f"(🔓해금 {day_unlock_ev}회/누적 {cum_unlock_ev}회)"
            if (day_unlock_ev > 0 or cum_unlock_ev > 0)
            else ""
        )
        golden_note = (
            f" · 🌟골든전액 매수 {day_g_buy}회/익절 {day_g_sell}회"
            if (day_g_buy > 0 or day_g_sell > 0)
            else ""
        )
        gp_carry_note = f"+골든포켓 {gp_sh}주" if gp_sh > 0 else ""
        res_note = (
            f" · 💉예비수혈: 당일 +{day_res_inj}회분(사용 {used_res_cnt}/{MAX_RESERVE_PORTIONS}회분·${inj_res_usd:,.2f})"
            if (day_res_inj > 0 or used_res_cnt > 0)
            else f" · 💉예비탄창: {MAX_RESERVE_PORTIONS}/{MAX_RESERVE_PORTIONS}회분 대기"
        )
        await context.send_slim_alert(
            title=f"🌙 [16:00 EST 정규장 마감 일일 결산] ({today_str})",
            body=(
                f"당일 세후실현: {d_sign}${abs(day_net):,.2f} ({d_sign}{abs(day_krw):,.0f}원) "
                f"· 누적실현: {c_sign}${abs(cum_net):,.2f} ({c_sign}{abs(cum_roi):.2f}%) "
                f"· 당일 매수 {day_buy_ev}회{unlock_note} / 익절 {day_sell_ev}회(2~7층이평졸업 {day_wma_grad}회·개별층 {day_indiv_sell}회)"
                f"{golden_note}{res_note} "
                f"· 🛡️시드패스 {day_pass:,}회 / 자투리절약 +${day_saved:,.2f} "
                f"· 오버나이트 이월: {held_sh}주({held_tiers}개층·{held_lots}회차{gp_carry_note}) · 가용현금 ${free_cash:,.2f} "
                f"(🌇애프터·🌃데이장 ⚡1.5s 방안 C 통합졸업감시 연속가동 · 개별층/매수잠금)"
            ),
        )

    logger.info(
        "🌙 [16:00 EST 일일 결산 완료 · %s] 당일실현=$%.2f · 누적실현=$%.2f · 예비수혈=%d/%d회분 · 오버나이트보유=%d주(%d개층·포켓 %d주) -> 애프터/데이장 익절감시 직결",
        folder_slug,
        day_net,
        cum_net,
        used_res_cnt,
        MAX_RESERVE_PORTIONS,
        held_sh,
        held_tiers,
        gp_sh,
    )
    return {
        "status": "DAILY_CLOSING_SETTLEMENT_DONE",
        "date": today_str,
        "daily_realized_net_usd": day_net,
        "cumulative_realized_net_usd": cum_net,
        "held_shares": held_sh,
        "pocket_shares": gp_sh,
        "held_tiers": held_tiers,
    }


# ---------------------------------------------------------------------------
# [핵심 4] 17:00 EST 일일 가비지 컬렉션(GC) · 일일 카운터 롤오버 · 날짜별 원장 백업 (Case 22, 68, 74, 76, 77, 79, 80)
# ---------------------------------------------------------------------------
async def execute_daily_1700_gc_and_backup_plugin(
    context: Any,
    now_est: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    🔹 17:00 EST (Case 22, Case 68, Case 74, Case 76, Case 77, Case 79 & Case 80):
    1) 롤오버 직전 당일 원장 상태를 `ledger_backups/soxl_stratum_ledger_<folder_slug>_YYYY-MM-DD.json` 에
       날짜별 물리적 스냅샷으로 백업(최근 14일분 유지)한다.
    2) 원장 일일 카운터(daily_seed_protect_pass_cnt=0, daily_unlock_buy_events=0,
       daily_golden_allin_buy_events=0, daily_golden_pocket_sell_cnt=0, daily_golden_realized_net_usd=0.0,
       daily_reserve_injected_cnt=0, daily_dust_guard_blocked_cnt=0, last_reentry_eval_ts=0.0 등)를
       새 거래일 기준으로 확실히 리셋하고 가비지 컬렉션(gc.collect)을 수행한다.
    """
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
    mark_reentry_monitor_60s_cycle_shield(
        context=context, symbol=TARGET_SYMBOL, clear_shield=True
    )
    await context.ledger.update_state(
        TARGET_SYMBOL,
        daily_seed_protect_pass_cnt=0,
        daily_unlock_buy_events=0,
        daily_golden_allin_buy_events=0,
        daily_golden_pocket_sell_cnt=0,
        daily_golden_realized_net_usd=0.0,
        daily_reserve_injected_cnt=0,
        daily_dust_guard_blocked_cnt=0,
        pending_step_up_min_price=0.0,
        last_evaluated_buy_bucket_id=-1,
        last_reentry_eval_ts=0.0,
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


# 하위 호환 별칭 (구버전 호출부가 존재하더라도 무해하게 동작하도록 연결)
execute_macro_defense_plugin = reconcile_stratum_with_broker_holdings_plugin
enforce_0930_regular_cutoff_plugin = reconcile_stratum_with_broker_holdings_plugin
execute_moc_zero_overnight_plugin = execute_1600_daily_closing_settlement_plugin
