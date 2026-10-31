# -*- coding: utf-8 -*-
"""
# MODIFIED: quant_engine.py
인피니트 스노우볼 (Infinite Snowball) v3.0 — 퀀트 엔진 코어 Part 2 / 2 (Step 03 / 09)
역할:
1) quant_engine_core.py (Part 1 / 2) 의 모든 상수·구조체·정량/수혈/스텝업/컷오프 판정 심볼 명시적 재익스포트(Facade Re-export)로
   타 모듈 AST 임포트 호환성 100% 보장
2) 1층 ~ 7층 골디락스 순수 멀티 그리드 배치 및 병합기(vrev_add_quota_lot_and_merge_2tier :
   REENTRY_1FL 독립 1층 배치 / TOPUP_1FL 기존 1층 무승격 원자적 합산[Case 78] /
   DIP_1FL·GOLDEN_L1 2~6층 개별 승격 및 7층 초과분 최상단 통합 7층 본대[GRID_L7] 가중평균 병합[Case 53, 72] /
   수동 추가매수 시 단가 비교 오름차순 층간 스마트 중간 편입[Case 63])
3) 수동 매도 시 독립 골든포켓 및 1~7층 순수 원가 1:1 매칭 정산기(match_and_remove_sold_buckets_7tier · Case 63, 69, 80)
4) 상단 2층 ~ 7층 통합 이동평균(compute_upper_2_to_7_moving_avg) 산출 및
   🚨 [Case 83 방안 C] 오버나이트(애프터·데이마켓, is_overnight_session=True) 중 상단 2~7층 보유 시
   개별 층(1층 및 2~6층 개별) 쪼개 팔기를 잠가 통합 이동평균(wma_2_to_7) 도망을 원천 봉쇄하고,
   장외에서는 통합 이동평균(+1.00%) 일괄 졸업(1층 본전 이상 시 SELL_ALL_GRAD 전량 졸업 / 1층 본전 미달 시 SELL_WMA_UPPER 상단 일괄 졸업,
   또는 1층 단독 보유 +1.50% / 독립 골든포켓 +1.50%)만 허용한 뒤
   04:07 EST 프리장 개장(is_overnight_session=False) 즉시 4중 다중 익절을 전면 개방하는 하이브리드 매도 판정기(evaluate_multi_grid_sell_targets)
5) 포트폴리오 통합 요약기(summarize_stratum_portfolio · Case 84 15:30~16:00 돌파 차단 상태 동기화) 및
   기동 전 TDD 사전 무결성 검증 슈트(run_quant_engine_tdd · Case 25 ~ 84 전수 검증)
- 제1헌법 ~ 제6헌법 및 Case 01 ~ 84 완벽 준수
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from quant_engine_core import (
    BASE_MAX_LOTS_8PCT,
    DEFAULT_GOLDEN_ALLIN_MODE,
    DEFAULT_INITIAL_SEED_USD,
    DEFAULT_UNLOCK_MODE,
    GOLDEN_ALLIN_MODES,
    GOLDEN_POCKET_RISE_PCT,
    GOLDEN_RSI_MAX_THRESHOLD,
    GOLDEN_WINDOW_END_HM,
    GOLDEN_WINDOW_START_HM,
    GoldenAllInPocket,
    MAX_GRID_TIERS,
    MAX_GRID_TIERS_7,
    MAX_GRID_TIERS_12,
    MAX_RESERVE_PORTIONS,
    MIN_DIP_BUDGET_RATIO,
    MIN_DIP_VS_L1_RATIO,
    NEW_CYCLE_BUY_CUTOFF_HM,
    PORTION_RATIO_LOCKED,
    REANCHOR_NET_BUFFER_MULT,
    REENTRY_BREAKOUT_RISE_PCT,
    REENTRY_PULLBACK_DROP_PCT,
    RESERVE_DEPOSIT_TOLERANCE_RATIO,
    ROUND_TRIP_FEE_RATE_PCT,
    STEP_UP_2X_DROP_PCT,
    STEP_UP_2X_MAX_TIERS,
    STEP_UP_2X_MIN_CASH_RATIO,
    STEP_UP_2X_MIN_REBOUND_MULT,
    StratumBucket,
    buckets_from_dicts,
    buckets_to_dicts,
    compute_golden8_quota_qty,
    compute_reserve_repayment_on_zero,
    enforce_true_breakeven_floor_on_buckets,
    evaluate_golden_allin_signal,
    evaluate_guard30_and_reserve_injection,
    evaluate_l2_only_hybrid_reentry_signal,
    evaluate_step_up_2x_dip_signal,
    get_golden8_prog_thresholds,
    get_golden_allin_mode_label,
    has_active_golden_pocket,
    has_active_l1_bucket,
    is_upper_grid_tier,
    pocket_from_dict,
    pocket_to_dict,
    relabel_upper_grid_tiers,
    resolve_affordable_buy_qty,
    resolve_allin_affordable_buy_qty,
)
from toss_api import EST_TZ, safe_float, safe_int

logger = logging.getLogger("toss_sniper.quant_engine")


# ---------------------------------------------------------------------------
# [핵심 4 · Case 63, Case 71 ~ 84] 1층 ~ 7층 골디락스 순수 멀티 그리드 배치 & 매도 층/포켓 원가 매칭 정산기
# ---------------------------------------------------------------------------
def vrev_add_quota_lot_and_merge_2tier(
    queue: Sequence[StratumBucket],
    buy_qty: int,
    buy_price: float,
    actual_spent_usd: Optional[float] = None,
    lot_type: str = "QUOTA_L1",
    max_tiers: int = MAX_GRID_TIERS_7,
) -> List[StratumBucket]:
    """
    🎯 3 & 🎯 4 & Case 46 ~ 84 (함수명은 타 모듈 AST 호환을 위해 유지하되 내부는 1~7층 골디락스 멀티 그리드로 작동):
    신규 정량 매수(또는 GRID_L1_ALLIN 모드 1층 전액편입 GOLDEN_L1) 체결 시
    최대 7개 지층(1층 공격수 + 2~6층 개별 완충층[5개] + 통합 7층 본대[GRID_L7])을 관리한다.
    """
    q_int = max(1, safe_int(buy_qty, 1))
    p_val = round(max(0.0001, safe_float(buy_price, 0.01)), 4)
    spent = (
        round(
            max(0.01, safe_float(actual_spent_usd, float(q_int) * p_val)), 4
        )
        if actual_spent_usd is not None
        else round(float(q_int) * p_val, 4)
    )
    pure_p = round(max(0.0001, spent / float(q_int)), 4)
    tag = str(lot_type or "QUOTA_L1").upper().strip()
    if is_upper_grid_tier(tag):
        tag = "QUOTA_L1"

    new_l1 = StratumBucket(
        qty=q_int,
        book_price=pure_p,
        book_invested_usd=spent,
        actual_cost_usd=spent,
        lot_count=1,
        lot_type=(tag if tag != "TOPUP_1FL" else "REENTRY_1FL"),
    )

    existing = [
        b
        for b in (queue or [])
        if isinstance(b, StratumBucket) and b.qty > 0
    ]
    if not existing:
        return [new_l1]

    eff_max_tiers = max(2, safe_int(max_tiers, MAX_GRID_TIERS_7))

    # 🚨 Case 59, Case 71, Case 72, Case 73 & Case 80: 상단 그리드(2층 ~ 7층)만 보유 중(1층 공석) REENTRY_1FL / GOLDEN_L1 유입 시 상단 비병합 독립 1층 배치!
    if not has_active_l1_bucket(existing) and tag in (
        "REENTRY_1FL",
        "TOPUP_1FL",
        "GOLDEN_L1",
    ):
        preserved_uppers = relabel_upper_grid_tiers(
            existing, max_tiers=eff_max_tiers
        )
        return [new_l1] + preserved_uppers

    # 🚨 [Case 78]: 활성 1층 보유 중 미체결 잔량 보충(TOPUP_1FL) 체결 시
    # 지층 승격(GRID_L2) 및 회차(lot_count) 증가 없이 기존 1층(existing[0])에 그대로 원자적 가중평균 합산!
    if tag == "TOPUP_1FL" and has_active_l1_bucket(existing):
        old_b1 = existing[0]
        comb_qty = old_b1.qty + q_int
        comb_cost = round(old_b1.actual_cost_usd + spent, 4)
        comb_p = round(max(0.0001, comb_cost / float(comb_qty)), 4)
        keep_tag = (
            old_b1.lot_type
            if not is_upper_grid_tier(old_b1.lot_type)
            else "REENTRY_1FL"
        )
        merged_l1 = StratumBucket(
            qty=comb_qty,
            book_price=comb_p,
            book_invested_usd=comb_cost,
            actual_cost_usd=comb_cost,
            lot_count=max(1, old_b1.lot_count),
            lot_type=keep_tag,
        )
        preserved_uppers = relabel_upper_grid_tiers(
            existing[1:], max_tiers=eff_max_tiers
        )
        return [merged_l1] + preserved_uppers

    # 2-Layer 레거시 모드 호환 분기
    if eff_max_tiers <= 2:
        old_total_qty = sum(b.qty for b in existing)
        old_actual_cost = round(sum(b.actual_cost_usd for b in existing), 4)
        old_lot_cnt = sum(max(1, b.lot_count) for b in existing)
        old_overall_avg = (
            sum(float(b.qty) * b.book_price for b in existing)
            / float(old_total_qty)
        )
        raw_upper_p = old_actual_cost / float(old_total_qty)
        capped_upper_p = round(min(raw_upper_p, old_overall_avg), 4)
        merged_l2 = StratumBucket(
            qty=old_total_qty,
            book_price=capped_upper_p,
            book_invested_usd=old_actual_cost,
            actual_cost_usd=old_actual_cost,
            lot_count=old_lot_cnt,
            lot_type="GRID_L2",
        )
        return [new_l1, merged_l2]

    # 🚨 [Case 63 & Case 72 : 단가 비교 오름차순(저가 1층 ➔ 고가 7층) 층간 중간 편입]
    # 단, GOLDEN_L1 은 백테스트 GRID_L1_ALLIN 규격대로 항상 새 1층(index 0)으로 편입하고 기존 지층을 승격시킨다.
    if tag != "GOLDEN_L1" and pure_p > existing[0].book_price + 1e-6:
        combined = list(existing) + [new_l1]
        combined.sort(key=lambda b: round(b.book_price, 4))
        lowest_b = combined[0]
        if is_upper_grid_tier(lowest_b.lot_type):
            lowest_b = StratumBucket(
                qty=lowest_b.qty,
                book_price=lowest_b.book_price,
                book_invested_usd=lowest_b.book_invested_usd,
                actual_cost_usd=lowest_b.actual_cost_usd,
                lot_count=max(1, lowest_b.lot_count),
                lot_type=tag,
            )
        sorted_uppers = relabel_upper_grid_tiers(
            combined[1:], max_tiers=eff_max_tiers
        )
        return [lowest_b] + sorted_uppers

    shifted_uppers = relabel_upper_grid_tiers(
        existing, max_tiers=eff_max_tiers
    )
    return [new_l1] + shifted_uppers


def match_and_remove_sold_buckets_7tier(
    buckets: Sequence[StratumBucket],
    delta_remove_qty: int,
    sell_exec_price: float = 0.0,
    max_tiers: int = MAX_GRID_TIERS_7,
    golden_pocket: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    # [Case 63, Case 69, Case 71, Case 72 & Case 80 : 매도 수량 층/골든포켓 판별 및 순수 원가 1:1 매칭 정산기]:
    수동 매도(전량 또는 부분 매도)로 보유 수량이 delta_remove_qty 만큼 줄었을 때:
    1) 독립 골든포켓(golden_pocket)이 존재하고 수량이 일치하거나 단가가 하단 층 이하일 때 골든포켓부터(또는 하단 층부터)
       순차 차감하여 골든포켓과 1층 ~ 7층 각 레이어의 고유 순수 원가를 100% 보존한다.
    2) 실제로 차감된 물량의 고유 순수 매수 원금(sold_actual_cost_usd)만 적용하여
       calc_sell_realized_pnl() 로 세후 실현수익(net_pnl_usd)을 정밀 산출한다.
    """
    valid = [
        b
        for b in (buckets or [])
        if isinstance(b, StratumBucket) and b.qty > 0
    ]
    gp = pocket_from_dict(golden_pocket)
    rem_to_cut = max(0, safe_int(delta_remove_qty, 0))
    exec_p = round(max(0.0, safe_float(sell_exec_price, 0.0)), 4)

    if (not valid and not gp.is_active) or rem_to_cut <= 0:
        return {
            "rem_buckets": valid,
            "rem_golden_pocket": gp.to_dict(),
            "sold_pocket_qty": 0,
            "sold_buckets": [],
            "sold_qty": 0,
            "sold_actual_cost_usd": 0.0,
            "sold_avg_cost_price": 0.0,
            "sold_tier_desc": "없음",
            "sold_l1_completely": False,
            "sold_upper_tier": False,
            "pnl_info": calc_sell_realized_pnl(0, exec_p, 0.0),
        }

    sold_pocket_qty = 0
    sold_pocket_cost = 0.0
    rem_gp = pocket_from_dict(gp.to_dict())
    sold_tier_parts: List[str] = []

    def _cut_from_golden_pocket(cut_q: int) -> int:
        nonlocal sold_pocket_qty, sold_pocket_cost, rem_gp
        if not rem_gp.is_active or cut_q <= 0:
            return 0
        if cut_q >= rem_gp.qty:
            taken = rem_gp.qty
            sold_pocket_qty += taken
            sold_pocket_cost = round(
                sold_pocket_cost + rem_gp.actual_cost_usd, 4
            )
            sold_tier_parts.append(
                f"골든포켓({taken}주@${rem_gp.book_price:.2f})"
            )
            rem_gp = GoldenAllInPocket()
            return taken
        taken = cut_q
        keep_q = rem_gp.qty - taken
        unit_p = rem_gp.actual_avg_price
        part_cost = round(float(taken) * unit_p, 4)
        keep_cost = round(
            max(0.01 * float(keep_q), rem_gp.actual_cost_usd - part_cost), 4
        )
        sold_pocket_qty += taken
        sold_pocket_cost = round(sold_pocket_cost + part_cost, 4)
        sold_tier_parts.append(f"골든포켓부분({taken}주@${unit_p:.2f})")
        rem_gp = GoldenAllInPocket(
            qty=keep_q,
            book_price=round(keep_cost / float(keep_q), 4),
            book_invested_usd=keep_cost,
            actual_cost_usd=keep_cost,
            entry_ts=rem_gp.entry_ts,
            order_date=rem_gp.order_date,
        )
        return taken

    # 골든포켓 수량과 정확히 일치하거나 골든포켓 단가가 최저 그리드 층 단가 이하(또는 그리드가 비어 있음)면 골든포켓 우선 차감
    if rem_gp.is_active and (
        not valid
        or rem_to_cut == rem_gp.qty
        or rem_gp.book_price <= valid[0].book_price + 1e-6
    ):
        cut_done = _cut_from_golden_pocket(rem_to_cut)
        rem_to_cut -= cut_done

    was_active_l1 = has_active_l1_bucket(valid)
    rem_buckets: List[StratumBucket] = []
    sold_buckets: List[StratumBucket] = []
    removed_first_tier_completely = False
    sold_upper_tier = False

    for idx, b in enumerate(valid):
        tier_label = (
            "1층"
            if (idx == 0 and was_active_l1)
            else f"{idx + 1 if was_active_l1 else idx + 2}층"
        )
        if rem_to_cut <= 0:
            rem_buckets.append(b)
            continue

        if rem_to_cut >= b.qty:
            sold_buckets.append(b)
            sold_tier_parts.append(
                f"{tier_label}({b.qty}주@${b.book_price:.2f})"
            )
            rem_to_cut -= b.qty
            if idx == 0 and was_active_l1:
                removed_first_tier_completely = True
            else:
                sold_upper_tier = True
        else:
            sold_q_part = rem_to_cut
            keep_q = b.qty - rem_to_cut
            rem_to_cut = 0

            pure_unit_p = b.actual_avg_price
            sold_cost_part = round(float(sold_q_part) * pure_unit_p, 4)
            keep_cost_part = round(
                max(0.01 * float(keep_q), b.actual_cost_usd - sold_cost_part),
                4,
            )

            sold_buckets.append(
                StratumBucket(
                    qty=sold_q_part,
                    book_price=round(sold_cost_part / float(sold_q_part), 4),
                    book_invested_usd=sold_cost_part,
                    actual_cost_usd=sold_cost_part,
                    lot_count=1,
                    lot_type=b.lot_type,
                )
            )
            rem_buckets.append(
                StratumBucket(
                    qty=keep_q,
                    book_price=round(keep_cost_part / float(keep_q), 4),
                    book_invested_usd=keep_cost_part,
                    actual_cost_usd=keep_cost_part,
                    lot_count=max(1, b.lot_count),
                    lot_type=b.lot_type,
                )
            )
            sold_tier_parts.append(
                f"{tier_label}부분({sold_q_part}주@${pure_unit_p:.2f})"
            )
            if not (idx == 0 and was_active_l1):
                sold_upper_tier = True

    if rem_to_cut > 0 and rem_gp.is_active:
        cut_done = _cut_from_golden_pocket(rem_to_cut)
        rem_to_cut -= cut_done

    eff_max_t = max(2, safe_int(max_tiers, MAX_GRID_TIERS_7))
    if rem_buckets:
        if was_active_l1 and not removed_first_tier_completely:
            active_b1 = rem_buckets[0]
            re_uppers = relabel_upper_grid_tiers(
                rem_buckets[1:], max_tiers=eff_max_t
            )
            rem_buckets = [active_b1] + re_uppers
        else:
            rem_buckets = relabel_upper_grid_tiers(
                rem_buckets, max_tiers=eff_max_t
            )

    sold_qty_total = sum(b.qty for b in sold_buckets) + sold_pocket_qty
    sold_cost_total = round(
        sum(b.actual_cost_usd for b in sold_buckets) + sold_pocket_cost, 4
    )
    sold_avg_cost_p = (
        round(sold_cost_total / float(sold_qty_total), 4)
        if sold_qty_total > 0
        else 0.0
    )
    eff_sell_p = exec_p if exec_p > 0.0 else sold_avg_cost_p
    pnl_info = calc_sell_realized_pnl(
        sold_qty=sold_qty_total,
        sell_exec_price=eff_sell_p,
        sold_actual_cost_usd=sold_cost_total,
    )

    return {
        "rem_buckets": rem_buckets,
        "rem_golden_pocket": rem_gp.to_dict(),
        "sold_pocket_qty": sold_pocket_qty,
        "sold_buckets": sold_buckets,
        "sold_qty": sold_qty_total,
        "sold_actual_cost_usd": sold_cost_total,
        "sold_avg_cost_price": sold_avg_cost_p,
        "sold_tier_desc": (
            " + ".join(sold_tier_parts) if sold_tier_parts else "없음"
        ),
        "sold_l1_completely": removed_first_tier_completely,
        "sold_upper_tier": sold_upper_tier,
        "pnl_info": pnl_info,
    }


def compute_upper_2_to_12_moving_avg(
    buckets: Sequence[StratumBucket],
    rise_upper_pct: float = 1.00,
) -> Dict[str, Any]:
    """
    🚨 [Case 71 & Case 72 상단 2층 ~ 7층 통합 이동평균법(수량 가중평균) 단가 및 목표가 산출기]:
    (타 모듈 AST 임포트 호환을 위해 함수명 compute_upper_2_to_12_moving_avg 를 유지하며 compute_upper_2_to_7_moving_avg 별칭 동시 제공)
    """
    valid = [
        b
        for b in (buckets or [])
        if isinstance(b, StratumBucket) and b.qty > 0
    ]
    active_l1 = has_active_l1_bucket(valid)
    upper_list = valid[1:] if active_l1 else valid[:]

    if not upper_list:
        return {
            "has_active_l1": active_l1,
            "upper_tier_count": 0,
            "upper_qty": 0,
            "upper_lots": 0,
            "upper_actual_cost_usd": 0.0,
            "upper_wma_price": 0.0,
            "upper_wma_target_price": 0.0,
            "min_indiv_upper_price": 0.0,
            "min_indiv_upper_target_price": 0.0,
            "upper_buckets": [],
        }

    u_qty = sum(b.qty for b in upper_list)
    u_lots = sum(max(1, b.lot_count) for b in upper_list)
    u_cost = round(sum(b.actual_cost_usd for b in upper_list), 4)
    wma_p = round(u_cost / float(u_qty), 4) if u_qty > 0 else 0.0
    wma_target_p = (
        round(
            math.ceil(
                (wma_p * (1.0 + rise_upper_pct / 100.0) - 1e-9) * 100.0
            )
            / 100.0,
            2,
        )
        if wma_p > 0.0
        else 0.0
    )

    min_indiv_p = min(b.book_price for b in upper_list)
    min_indiv_target_p = round(
        math.ceil(
            (min_indiv_p * (1.0 + rise_upper_pct / 100.0) - 1e-9) * 100.0
        )
        / 100.0,
        2,
    )

    return {
        "has_active_l1": active_l1,
        "upper_tier_count": len(upper_list),
        "upper_qty": u_qty,
        "upper_lots": u_lots,
        "upper_actual_cost_usd": u_cost,
        "upper_wma_price": wma_p,
        "upper_wma_target_price": wma_target_p,
        "min_indiv_upper_price": round(min_indiv_p, 4),
        "min_indiv_upper_target_price": min_indiv_target_p,
        "upper_buckets": upper_list,
    }


compute_upper_2_to_7_moving_avg = compute_upper_2_to_12_moving_avg


def evaluate_multi_grid_sell_targets(
    buckets: Sequence[StratumBucket],
    live_price: float,
    rise_l1_pct: float = 1.50,
    rise_upper_pct: float = 1.00,
    golden_pocket: Optional[Any] = None,
    rise_pocket_pct: float = GOLDEN_POCKET_RISE_PCT,
    is_overnight_session: bool = False,
) -> Dict[str, Any]:
    """
    🚨 [Case 69, Case 70, Case 71, Case 72, Case 80 & Case 83 (방안 C 오버나이트 통합이평 사수 하이브리드)]:
    매수 후 60초 타임쉴드 뒤 매 1.5초 실시간 현재가(live_price)로 매도 조건을 스캔한다:
    1) [조건 ① : 독립 골든포켓(golden_pocket) +1.50% 이상 도래 (Case 80)]
       gp.is_active == True 이고 live_price >= gp.target_sell_price(rise_pocket_pct) 이면
       전 세션(프리·정규·애프터·데이장) 언제든 sell_pocket_qty = gp.qty 를 매도 물량에 즉시 포함!
    2) [Case 83 방안 C : 오버나이트(애프터·데이마켓, is_overnight_session == True) 구간에서의 그리드 보호 규율]
       - 상단 지층(2층 ~ 7층)이 존재할 때(has_upper_tiers == True):
         하단 1층(+1.50%)이나 개별 완충층(2~6층 +1.00%)을 장외에서 먼저 쪼개 팔면 저가 물량 가중치가 사라져
         2~7층 통합 이동평균(wma_2_to_7)이 위로 도망가고 04:07 EST 프리장 시초가 갭상승 수익을 잃게 된다.
         따라서 오버나이트 중 상단 지층 보유 시에는 개별 층 매도(hit_l1 단독 및 hit_indiv_grid)를 전면 잠그고,
         오직 '상단 2층 ~ 7층 통합 이동평균(wma_2_to_7) +1.00% 도달' 시의 상단 일괄 졸업(SELL_WMA_UPPER,
         활성 1층 보유 중 1층 본전 이상 동시 충족 시 1층까지 포함한 전량 졸업 SELL_ALL_GRAD)만 허용한다!
       - 단, 상단 지층 없이 활성 1층 단독 1개 층만 보유 중(has_upper_tiers == False)일 때는
         통합이평 도망 역설이 없으므로 오버나이트 중에도 +1.50% 도달 시 즉시 익절(SELL_L1_ONLY)한다.
    3) [프리마켓 + 정규장 (04:07 ~ 16:00 EST, is_overnight_session == False) 구간에서의 4중 다중 익절 전면 개방]
       - 04:07 EST 프리장 개장과 동시에 ① 골든포켓(+1.50%), ② 활성 1층(+1.50%),
         ③ 상단 2~7층 통합 이동평균(+1.00% 일괄 졸업), ④ 상단 2~7층 개별 완충층(+1.00% 개별 익절)을
         모두 개방하여 프리장이 상승(또는 갭상승) 시작한 가격으로 즉시 익절한다!
    """
    valid = [
        b
        for b in (buckets or [])
        if isinstance(b, StratumBucket) and b.qty > 0
    ]
    gp = pocket_from_dict(golden_pocket)
    lp = safe_float(live_price, 0.0)
    if (not valid and not gp.is_active) or lp <= 0.0:
        return {
            "should_sell": False,
            "sold_indices": [],
            "sell_pocket_qty": 0,
            "grid_sell_qty": 0,
            "sell_qty": 0,
            "min_floor_price": 0.0,
            "reason_tag": "NONE",
            "hit_golden_pocket": False,
            "hit_l1": False,
            "hit_indiv_grid": False,
            "hit_wma_grad": False,
            "overnight_indiv_locked": False,
        }

    sold_idx_set: Set[int] = set()
    floor_candidates: List[float] = []
    hit_golden_pocket = False
    sell_pocket_qty = 0
    hit_l1 = False
    hit_indiv_grid = False
    hit_wma_grad = False
    overnight_indiv_locked = False

    # ① 독립 골든포켓(+1.50%) 익절 판정 (Case 80 — 전 세션 허용)
    if gp.is_active:
        gp_target_p = gp.target_sell_price(rise_pct=rise_pocket_pct)
        if gp_target_p > 0.0 and lp >= gp_target_p:
            hit_golden_pocket = True
            sell_pocket_qty = gp.qty
            floor_candidates.append(gp_target_p)

    active_l1 = has_active_l1_bucket(valid)
    upper_start_idx = 1 if (active_l1 and valid) else 0
    has_upper_tiers = bool(len(valid) > upper_start_idx)

    # ② 활성 1층(index 0) +1.50% 개별 익절 판정
    # [Case 83 방안 C]: 오버나이트(is_overnight_session == True)이면서 상단 지층(2~7층)이 함께 존재할 때는
    # 1층 단독 조기 이탈을 잠그고 통합이평 일괄 졸업 시 함께 졸업시키거나 04:07 EST 프리장 시초가에 매도한다!
    if active_l1 and valid:
        b1 = valid[0]
        min_l1_target_p = (
            math.ceil(
                (b1.book_price * (1.0 + rise_l1_pct / 100.0) - 1e-9) * 100.0
            )
            / 100.0
        )
        if lp >= min_l1_target_p:
            if is_overnight_session and has_upper_tiers:
                overnight_indiv_locked = True
            else:
                sold_idx_set.add(0)
                floor_candidates.append(min_l1_target_p)
                hit_l1 = True

    # ③ & ④ 상단 2층 ~ 7층 통합 이동평균(+1.00%) 및 개별 그리드(+1.00%) 판정
    if has_upper_tiers:
        wma_info = compute_upper_2_to_12_moving_avg(
            valid, rise_upper_pct=rise_upper_pct
        )
        wma_target_p = safe_float(wma_info.get("upper_wma_target_price"), 0.0)
        # [Case 69, Case 71 & Case 83]:
        # 1) 소수점 절사로 인한 원금 손실을 막기 위해 1층 본전 하한가(b1_breakeven_p)를 math.ceil 로 정밀 산출한다.
        # 2) 오버나이트 중에도 lp >= wma_target_p 이면 상단 2~7층 일괄 졸업(SELL_WMA_UPPER)을 항상 허용하고,
        #    동시에 1층 본전 이상(lp >= b1_breakeven_p)이면 1층까지 포함하여 전량 졸업(SELL_ALL_GRAD)시킨다!
        b1_breakeven_p = (
            round(
                math.ceil(
                    (
                        max(0.01, valid[0].actual_avg_price, valid[0].book_price)
                        - 1e-9
                    )
                    * 100.0
                )
                / 100.0,
                2,
            )
            if (active_l1 and valid)
            else 0.0
        )

        # ③ 상단 2~7층 통합 이동평균(+1.00%) 도달 시 상단(및 본전 이상 1층) 일괄 졸업 (프리·정규·오버나이트 전 세션 허용!)
        if wma_target_p > 0.0 and lp >= wma_target_p:
            for k in range(upper_start_idx, len(valid)):
                sold_idx_set.add(k)
            floor_candidates.append(wma_target_p)
            hit_wma_grad = True
            overnight_indiv_locked = False
            if active_l1 and valid and lp >= b1_breakeven_p:
                sold_idx_set.add(0)
                floor_candidates.append(b1_breakeven_p)
        else:
            # ④ 상단 2~7층 개별 층(+1.00%) 판정
            # [Case 83 방안 C]: 오버나이트(is_overnight_session == True) 중에는 개별 상단층 쪼개 팔기를 잠가
            # 하단 완충층(2~3층) 조기 이탈로 인한 통합이평(wma_2_to_7) 도망을 100% 원천 봉쇄한다!
            for k in range(upper_start_idx, len(valid)):
                bk = valid[k]
                bk_target_p = (
                    math.ceil(
                        (bk.book_price * (1.0 + rise_upper_pct / 100.0) - 1e-9)
                        * 100.0
                    )
                    / 100.0
                )
                if lp >= bk_target_p:
                    if is_overnight_session:
                        overnight_indiv_locked = True
                    else:
                        sold_idx_set.add(k)
                        floor_candidates.append(bk_target_p)
                        hit_indiv_grid = True

    if not sold_idx_set and sell_pocket_qty <= 0:
        return {
            "should_sell": False,
            "sold_indices": [],
            "sell_pocket_qty": 0,
            "grid_sell_qty": 0,
            "sell_qty": 0,
            "min_floor_price": 0.0,
            "reason_tag": (
                "HOLD_OVERNIGHT_WMA_LOCK"
                if overnight_indiv_locked
                else "NONE"
            ),
            "hit_golden_pocket": False,
            "hit_l1": False,
            "hit_indiv_grid": False,
            "hit_wma_grad": False,
            "overnight_indiv_locked": overnight_indiv_locked,
        }

    sorted_indices = sorted(sold_idx_set)
    grid_sell_qty = sum(valid[idx].qty for idx in sorted_indices)
    total_sell_qty = grid_sell_qty + sell_pocket_qty
    min_floor_p = max(floor_candidates) if floor_candidates else round(lp, 2)

    if hit_golden_pocket and not sorted_indices:
        reason_tag = "SELL_GOLDEN_POCKET"
    elif hit_golden_pocket and sorted_indices:
        if len(sorted_indices) == len(valid):
            reason_tag = "SELL_ALL_GRAD"
        else:
            reason_tag = "SELL_POCKET_AND_GRID"
    elif len(sorted_indices) == len(valid):
        reason_tag = (
            "SELL_ALL_GRAD"
            if hit_wma_grad or len(valid) > 1
            else "SELL_L1_ONLY"
        )
    elif hit_wma_grad:
        reason_tag = "SELL_WMA_UPPER"
    elif hit_l1 and hit_indiv_grid:
        reason_tag = "SELL_L1_AND_GRID"
    elif hit_indiv_grid:
        reason_tag = "SELL_GRID_INDIV"
    else:
        reason_tag = "SELL_L1_ONLY"

    return {
        "should_sell": True,
        "sold_indices": sorted_indices,
        "sell_pocket_qty": sell_pocket_qty,
        "grid_sell_qty": grid_sell_qty,
        "sell_qty": total_sell_qty,
        "min_floor_price": round(min_floor_p, 2),
        "reason_tag": reason_tag,
        "hit_golden_pocket": hit_golden_pocket,
        "hit_l1": hit_l1,
        "hit_indiv_grid": hit_indiv_grid,
        "hit_wma_grad": hit_wma_grad,
        "overnight_indiv_locked": overnight_indiv_locked,
    }


def vrev_reanchor_single_tier_quota(
    queue: Sequence[StratumBucket],
    net_realized_cash_profit: float,
    max_allowed_total_discount_usd: Optional[float] = None,
    enable_reanchor: bool = False,
) -> Tuple[List[StratumBucket], float]:
    """
    하위 호환 심볼 유지용 함수:
    챔피언에서는 리앵커링 원가 차감을 수행하지 않으므로 기본값(enable_reanchor=False) 호출 시
    원가를 100% 그대로 보존하고 (existing, 0.0)을 반환한다.
    """
    existing = [
        b
        for b in (queue or [])
        if isinstance(b, StratumBucket) and b.qty > 0
    ]
    if not enable_reanchor or len(existing) != 1:
        return existing, 0.0

    rem = existing[0]
    net_profit = safe_float(net_realized_cash_profit, 0.0)
    if net_profit <= 0.0 or rem.qty <= 0:
        return existing, 0.0

    credit_usd = max(0.0, net_profit * REANCHOR_NET_BUFFER_MULT)
    old_book_p = rem.book_price
    min_floor_inv = 0.01 * float(rem.qty)
    if (
        max_allowed_total_discount_usd is not None
        and safe_float(max_allowed_total_discount_usd, -1.0) >= 0.0
    ):
        allowed_disc = max(0.0, safe_float(max_allowed_total_discount_usd, 0.0))
        min_floor_inv = max(
            min_floor_inv, round(rem.actual_cost_usd - allowed_disc, 4)
        )

    new_book_inv = round(
        max(min_floor_inv, rem.book_invested_usd - credit_usd), 4
    )
    new_book_p = round(
        min(old_book_p, max(0.01, new_book_inv / float(rem.qty))), 4
    )
    price_drop = round(max(0.0, old_book_p - new_book_p), 4)
    updated_bucket = StratumBucket(
        qty=rem.qty,
        book_price=new_book_p,
        book_invested_usd=round(new_book_p * float(rem.qty), 4),
        actual_cost_usd=rem.actual_cost_usd,
        lot_count=rem.lot_count,
        lot_type=rem.lot_type,
    )
    return [updated_bucket], price_drop


def calc_sell_realized_pnl(
    sold_qty: int,
    sell_exec_price: float,
    sold_actual_cost_usd: float,
) -> Dict[str, float]:
    """
    매도 체결 수량(sold_qty), 실제 체결 단가(sell_exec_price), 매도 지층/포켓들의 실제 매수 원금 합계(sold_actual_cost_usd)를
    기반으로 왕복 수수료(0.14%) 차감 후 세후 실현 손익을 정밀 산출한다.
    """
    q_int = max(0, safe_int(sold_qty, 0))
    exec_p = max(0.0, safe_float(sell_exec_price, 0.0))
    actual_cost = max(0.0, safe_float(sold_actual_cost_usd, 0.0))
    if q_int <= 0 or exec_p <= 0.0:
        return {
            "proceeds_usd": 0.0,
            "actual_cost_usd": actual_cost,
            "gross_pnl_usd": 0.0,
            "fee_usd": 0.0,
            "net_pnl_usd": 0.0,
            "net_rate_pct": 0.0,
        }

    proceeds = round(float(q_int) * exec_p, 4)
    gross_pnl = round(proceeds - actual_cost, 4)
    fee_usd = round(
        ((actual_cost + proceeds) * 0.5) * (ROUND_TRIP_FEE_RATE_PCT / 100.0), 4
    )
    net_pnl = round(gross_pnl - fee_usd, 4)
    net_rate_pct = (
        round((net_pnl / actual_cost) * 100.0, 4) if actual_cost > 0.0 else 0.0
    )
    return {
        "proceeds_usd": proceeds,
        "actual_cost_usd": actual_cost,
        "gross_pnl_usd": gross_pnl,
        "fee_usd": fee_usd,
        "net_pnl_usd": net_pnl,
        "net_rate_pct": net_rate_pct,
    }


# ---------------------------------------------------------------------------
# [핵심 5] 포트폴리오 · 1~7층 골디락스 멀티 그리드 · 독립 골든포켓 · 2~7층 이동평균 · STEP2X_15PCT_C20 · GUARD30 · Case 84 통합 요약기 (Case 59 ~ 84)
# ---------------------------------------------------------------------------
def summarize_stratum_portfolio(
    state_dict: Dict[str, Any],
    live_price: float = 0.0,
    now_est: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    # MODIFIED [🎯 1 ~ 🎯 5 & Case 59, 60, 67, 69, 71, 72, 73, 74, 76, 77, 78, 80, 83, 84]:
    원장 상태(state_dict)와 현재가(live_price)를 받아:
    - 1층(활성 공격수) 및 상단 2층 ~ 6층 개별 완충층 · 통합 7층 본대(GRID_L2 ~ GRID_L7) 현황
    - 🌟 Case 80: 황금시간대 전액매수 모드(golden_allin_mode · 기본값 "NONE") 및 독립 골든포켓(golden_pocket) 보유 현황,
      +1.50% 목표가(golden_pocket_target_price), 수익률(golden_pocket_gain_pct), 황금시간 매매 통계 요약
    - 🎯 Case 78: 활성 1층 현재 보유 주수(l1_cur_qty), 1층 목표 정량(l1_target_quota_qty),
      미체결 잔량(l1_rem_quota_qty = max(0, l1_target_quota_qty - l1_cur_qty)) 산출
    - 상단 2층 ~ 7층 통합 이동평균 단가(upper_wma_price) 및 +1.00% 일괄 익절 목표가
    - 🛡️ Case 84: 현재 시각이 정규장 마감 30분 전(평일 15:30 ~ 16:00 EST)인지 판별하여
      evaluate_l2_only_hybrid_reentry_signal(..., is_late_new_cycle_cutoff=is_late_cutoff)에 반영
    - 💉 Case 77 & Case 80: 온디맨드 예비시드 수혈 잔액(injected_reserve_usd)을 제외한 순수 코어 자산(core_equity_for_quota) 기반
      8% 정량 산출 및 30% 자투리 가드 최소 필요 현금(min_req_cash_guard30), 예비시드 한도(used/6회분) 요약을 반환한다.
    """
    st = state_dict if isinstance(state_dict, dict) else {}
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    hm_now = dt_now.hour * 100 + dt_now.minute
    is_late_cutoff = bool(
        dt_now.weekday() < 5 and (NEW_CYCLE_BUY_CUTOFF_HM <= hm_now <= 1600)
    )

    raw_buckets = buckets_from_dicts(st.get("buckets", []))
    buckets = enforce_true_breakeven_floor_on_buckets(raw_buckets)
    gp = pocket_from_dict(st.get("golden_pocket"))

    init_seed = max(
        100.0, safe_float(st.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD)
    )
    cum_realized = round(
        safe_float(st.get("cumulative_realized_net_usd"), 0.0), 4
    )
    injected_reserve_usd = round(
        max(0.0, safe_float(st.get("injected_reserve_usd"), 0.0)), 4
    )
    used_reserve_portions_cnt = (
        0
        if injected_reserve_usd <= 0.0
        else max(
            1,
            min(
                MAX_RESERVE_PORTIONS,
                safe_int(st.get("used_reserve_portions_cnt"), 1),
            ),
        )
    )
    avail_reserve_portions = max(
        0, MAX_RESERVE_PORTIONS - used_reserve_portions_cnt
    )

    actual_invested_buckets = round(sum(b.actual_cost_usd for b in buckets), 4)
    book_invested_buckets = round(sum(b.book_invested_usd for b in buckets), 4)
    gp_qty = gp.qty if gp.is_active else 0
    gp_cost = round(gp.actual_cost_usd if gp.is_active else 0.0, 4)
    gp_price = round(gp.book_price if gp.is_active else 0.0, 4)

    actual_invested = round(actual_invested_buckets + gp_cost, 4)
    book_invested = round(book_invested_buckets + gp_cost, 4)

    # [Case 77 & Case 80 회계 항등식 확장]:
    expected_free_cash = round(
        max(
            0.0,
            (init_seed + cum_realized + injected_reserve_usd)
            - actual_invested,
        ),
        4,
    )
    free_cash = safe_float(st.get("free_cash_usd"), expected_free_cash)
    if abs(free_cash - expected_free_cash) > 0.05:
        free_cash = expected_free_cash

    held_shares = sum(b.qty for b in buckets)
    total_held_shares = held_shares + gp_qty
    held_lots = sum(max(1, b.lot_count) for b in buckets)
    held_tiers = len(buckets)
    lp = safe_float(live_price, 0.0)
    if lp <= 0.0:
        if buckets:
            lp = buckets[0].actual_avg_price
        elif gp.is_active:
            lp = gp.actual_avg_price

    actual_avg_p = (
        round(actual_invested / float(total_held_shares), 4)
        if total_held_shares > 0
        else 0.0
    )
    grid_actual_avg_p = (
        round(actual_invested_buckets / float(held_shares), 4)
        if held_shares > 0
        else 0.0
    )
    book_avg_p = (
        round(book_invested / float(total_held_shares), 4)
        if total_held_shares > 0
        else 0.0
    )

    threshold_mode = str(st.get("threshold_mode") or "WIDE_RUNWAY").upper()
    portion_mode = str(st.get("portion_mode") or "COMP_08PCT").upper()
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

    drop_buy_pct, rise_l1_pct, rise_l2_pct = get_golden8_prog_thresholds(
        held_lots=max(1, held_lots), threshold_mode=threshold_mode
    )

    gp_target_price = gp.target_sell_price(rise_pct=GOLDEN_POCKET_RISE_PCT)
    gp_gain_pct = (
        round(((lp - gp_price) / gp_price) * 100.0, 2)
        if (gp.is_active and lp > 0.0 and gp_price > 0.0)
        else 0.0
    )

    active_l1 = has_active_l1_bucket(buckets)
    is_l2_only = bool(len(buckets) > 0 and not active_l1)

    # [Case 78 : 활성 1층 현재 보유 주수, 목표 정량 및 미체결 잔량(l1_rem_quota_qty) 산출]
    raw_l1_target_q = max(0, safe_int(st.get("l1_target_quota_qty"), 0))
    pending_lot_tag = str(st.get("pending_lot_type") or "").upper().strip()
    if active_l1 and buckets:
        l1_cur_qty = buckets[0].qty
        l1_target_quota_qty = max(l1_cur_qty, raw_l1_target_q)
        l1_rem_quota_qty = max(0, l1_target_quota_qty - l1_cur_qty)
    else:
        l1_cur_qty = 0
        l1_target_quota_qty = (
            raw_l1_target_q
            if (
                bool(str(st.get("buy_order_id") or "").strip())
                and pending_lot_tag != "GOLDEN_POCKET"
            )
            else 0
        )
        l1_rem_quota_qty = 0

    wma_info = compute_upper_2_to_12_moving_avg(
        buckets, rise_upper_pct=rise_l2_pct
    )
    upper_tier_count = safe_int(wma_info.get("upper_tier_count"), 0)
    upper_qty = safe_int(wma_info.get("upper_qty"), 0)
    upper_lots = safe_int(wma_info.get("upper_lots"), 0)
    upper_wma_price = safe_float(wma_info.get("upper_wma_price"), 0.0)
    upper_wma_target_price = safe_float(
        wma_info.get("upper_wma_target_price"), 0.0
    )
    min_indiv_upper_price = safe_float(
        wma_info.get("min_indiv_upper_price"), 0.0
    )
    min_indiv_upper_target_price = safe_float(
        wma_info.get("min_indiv_upper_target_price"), 0.0
    )

    l1_target_price = 0.0
    l2_target_price = upper_wma_target_price
    l1_gain_pct = 0.0
    l2_gain_pct = 0.0
    min_indiv_upper_gain_pct = 0.0

    if active_l1 and buckets:
        b1 = buckets[0]
        l1_target_price = round(
            math.ceil(
                (b1.book_price * (1.0 + rise_l1_pct / 100.0) - 1e-9) * 100.0
            )
            / 100.0,
            2,
        )
        if lp > 0.0 and b1.book_price > 0.0:
            l1_gain_pct = round(
                ((lp - b1.book_price) / b1.book_price) * 100.0, 2
            )

    if upper_wma_price > 0.0 and lp > 0.0:
        l2_gain_pct = round(
            ((lp - upper_wma_price) / upper_wma_price) * 100.0, 2
        )
    if min_indiv_upper_price > 0.0 and lp > 0.0:
        min_indiv_upper_gain_pct = round(
            ((lp - min_indiv_upper_price) / min_indiv_upper_price) * 100.0, 2
        )

    anchor_p = safe_float(st.get("anchor_price"), 0.0)
    cycle_min_p = safe_float(st.get("cycle_min_buy_price"), 0.0)
    ratchet_p = safe_float(st.get("ratchet_anchor_price"), anchor_p)
    realized_equity_usd = round(max(0.0, init_seed + cum_realized), 4)

    # 🚨 Case 73 & Case 84: 1층 공석 시 상단 최하단 층(2층, min_indiv_upper_price) 및 장마감 30분전 돌파 차단 여부를 함께 전달!
    reentry_sig = evaluate_l2_only_hybrid_reentry_signal(
        live_price=lp,
        anchor_price=anchor_p,
        l2_book_price=(
            min_indiv_upper_price
            if min_indiv_upper_price > 0.0
            else upper_wma_price
        ),
        min_upper_tier_price=min_indiv_upper_price,
        is_late_new_cycle_cutoff=is_late_cutoff,
    )
    reentry_ref_anchor = safe_float(reentry_sig.get("ref_anchor"), anchor_p)
    reentry_pullback_price = safe_float(
        reentry_sig.get("pullback_target_price"), 0.0
    )
    reentry_breakout_price = safe_float(
        reentry_sig.get("breakout_target_price"), 0.0
    )
    chg_from_reentry_anchor_pct = safe_float(
        reentry_sig.get("chg_from_exit_pct"), 0.0
    )
    l2_ceiling_price = safe_float(
        reentry_sig.get("l2_ceiling_price"), min_indiv_upper_price
    )
    reentry_signal_type = str(
        reentry_sig.get("signal_type") or "HOLD_WAIT_GATE"
    )

    # 🚨 Case 60, Case 67, Case 72 & Case 76:
    if buckets:
        candidates = [
            p
            for p in (buckets[0].book_price, anchor_p, cycle_min_p)
            if p > 0.0
        ]
        active_buy_anchor = (
            min(candidates) if candidates else buckets[0].book_price
        )
    else:
        active_buy_anchor = (
            anchor_p if anchor_p > 0.0 else (lp if lp > 0.0 else 1.0)
        )

    trigger_buy_price = (
        round(active_buy_anchor * (1.0 + drop_buy_pct / 100.0), 2)
        if active_buy_anchor > 0.0
        else 0.0
    )

    # Case 76: 활성 1층 보유 중 STEP2X_15PCT_C20 스텝업 해금 자격 및 목표가 평가
    eff_step_drop = (
        0.0 if unlock_mode in ("STATIC", "NONE", "OFF") else STEP_UP_2X_DROP_PCT
    )
    step_up_eval = evaluate_step_up_2x_dip_signal(
        live_price=lp,
        buckets=buckets,
        anchor_price=anchor_p,
        cycle_min_buy_price=cycle_min_p,
        drop_buy_pct=drop_buy_pct,
        free_cash_usd=free_cash,
        realized_equity_usd=realized_equity_usd,
        step_up_drop_pct=eff_step_drop,
        min_cash_ratio=STEP_UP_2X_MIN_CASH_RATIO,
        min_rebound_mult=STEP_UP_2X_MIN_REBOUND_MULT,
        max_tiers_for_unlock=STEP_UP_2X_MAX_TIERS,
    )
    step_up_eligible = bool(step_up_eval.get("step_up_eligible", False))
    stepped_min_price = safe_float(step_up_eval.get("stepped_min_price"), 0.0)
    stepped_trigger_price = safe_float(
        step_up_eval.get("stepped_trigger_price"), 0.0
    )
    rebound_mult = safe_float(step_up_eval.get("rebound_mult"), 0.0)
    cash_ratio_pct = safe_float(step_up_eval.get("cash_ratio_pct"), 0.0)

    if is_l2_only:
        ref_buy_anchor = (
            reentry_ref_anchor
            if reentry_ref_anchor > 0.0
            else active_buy_anchor
        )
        chg_from_buy_anchor_pct = chg_from_reentry_anchor_pct
    else:
        ref_buy_anchor = active_buy_anchor
        chg_from_buy_anchor_pct = (
            round(((lp - active_buy_anchor) / active_buy_anchor) * 100.0, 2)
            if (lp > 0.0 and active_buy_anchor > 0.0)
            else 0.0
        )

    # [Case 77 & Case 80 : 온디맨드 예비시드 수혈금(injected_reserve_usd)을 제외한 순수 코어 자산 기준으로 8% 정량 예산 산출]:
    core_equity_for_quota = max(
        init_seed, (free_cash + actual_invested) - injected_reserve_usd
    )
    if len(buckets) == 0:
        ref_for_quota = (
            anchor_p if anchor_p > 0.0 else (lp if lp > 0.0 else 1.0)
        )
    elif is_l2_only:
        ref_for_quota = (
            reentry_ref_anchor
            if reentry_ref_anchor > 0.0
            else (lp if lp > 0.0 else active_buy_anchor)
        )
    elif bool(step_up_eval.get("is_step_up_unlock")) and stepped_min_price > 0.0:
        ref_for_quota = stepped_min_price
    else:
        ref_for_quota = active_buy_anchor

    anchor_quota_qty, next_portion_budget = compute_golden8_quota_qty(
        anchor_price=max(0.01, ref_for_quota),
        current_total_equity=core_equity_for_quota,
        initial_seed_usd=init_seed,
        portion_mode=portion_mode,
        exec_price=None,
    )
    eff_exec_for_cap = lp if lp > 0.0 else max(0.01, ref_for_quota)
    budget_cap_qty = max(
        1, int(math.floor((next_portion_budget + 1e-9) / eff_exec_for_cap))
    )
    next_target_qty = min(budget_cap_qty, anchor_quota_qty)

    # [Case 77]: 현재 상태에서의 30% 자투리 승격 방지 가드 최소 필요 현금(min_req_cash_guard30) 산출
    l1_cost_now = (
        buckets[0].actual_cost_usd if (active_l1 and buckets) else 0.0
    )
    guard30_eval = evaluate_guard30_and_reserve_injection(
        free_cash_usd=free_cash,
        broker_bp_usd=None,
        exec_price=eff_exec_for_cap,
        portion_budget=next_portion_budget,
        l1_actual_cost_usd=l1_cost_now,
        is_dip_promotion=bool(active_l1 and len(buckets) > 0),
        used_reserve_portions_cnt=used_reserve_portions_cnt,
        max_reserve_portions=MAX_RESERVE_PORTIONS,
    )
    min_req_cash_guard30 = safe_float(guard30_eval.get("min_req_cash"), 0.0)

    market_eval_usd = (
        round(float(total_held_shares) * lp, 4)
        if total_held_shares > 0 and lp > 0.0
        else 0.0
    )
    unrealized_pnl_usd = (
        round(market_eval_usd - actual_invested, 4)
        if total_held_shares > 0 and lp > 0.0
        else 0.0
    )
    unrealized_rate_pct = (
        round((unrealized_pnl_usd / actual_invested) * 100.0, 2)
        if actual_invested > 0.0
        else 0.0
    )

    realized_roi_pct = round((cum_realized / init_seed) * 100.0, 2)
    gross_mark_equity_usd = round(free_cash + market_eval_usd, 4)
    # 순수 자기자본 시가평가 총자산 (수혈받은 예비시드 원금 injected_reserve_usd 차감 기준)
    total_mark_equity_usd = round(
        max(0.0, gross_mark_equity_usd - injected_reserve_usd), 4
    )
    total_net_pnl_usd = round(cum_realized + unrealized_pnl_usd, 4)
    total_roi_pct = round((total_net_pnl_usd / init_seed) * 100.0, 2)

    reanchor_cnt = safe_int(st.get("reanchor_cnt"), 0)
    cum_reanchor_drop = round(
        safe_float(st.get("cumulative_reanchor_drop_usd"), 0.0), 4
    )
    indiv_grid_sell_cnt = safe_int(st.get("indiv_grid_sell_cnt"), 0)
    wma_grad_sell_cnt = safe_int(st.get("wma_grad_sell_cnt"), 0)

    # Case 74: 🛡️ 시드보호 패스는 당일 프리장 ~ 정규장(04:07 ~ 16:00 EST) 일일 주기 카운터(daily_seed_protect_pass_cnt)로 바인딩!
    daily_seed_protect_pass_cnt = safe_int(
        st.get("daily_seed_protect_pass_cnt"), 0
    )
    total_seed_protect_pass_cnt = safe_int(
        st.get("seed_protect_pass_cnt"), 0
    )
    seed_protect_pass_cnt = daily_seed_protect_pass_cnt

    extra_13plus_buy_events = safe_int(st.get("extra_13plus_buy_events"), 0)
    cond_unlock_buy_events = safe_int(st.get("cond_unlock_buy_events"), 0)
    daily_unlock_buy_events = safe_int(st.get("daily_unlock_buy_events"), 0)
    cum_leftover_saved = round(
        safe_float(st.get("cumulative_leftover_saved_usd"), 0.0), 4
    )

    # [Case 80]: 황금시간대 전액매수 및 골든포켓 통계 바인딩
    golden_allin_buy_events = safe_int(st.get("golden_allin_buy_events"), 0)
    daily_golden_allin_buy_events = safe_int(
        st.get("daily_golden_allin_buy_events"), 0
    )
    golden_pocket_sell_cnt = safe_int(st.get("golden_pocket_sell_cnt"), 0)
    daily_golden_pocket_sell_cnt = safe_int(
        st.get("daily_golden_pocket_sell_cnt"), 0
    )
    golden_realized_net_usd = round(
        safe_float(st.get("golden_realized_net_usd"), 0.0), 4
    )
    daily_golden_realized_net_usd = round(
        safe_float(st.get("daily_golden_realized_net_usd"), 0.0), 4
    )
    last_golden_allin_date = str(st.get("last_golden_allin_date") or "").strip()

    total_reserve_injected_cnt = safe_int(
        st.get("total_reserve_injected_cnt"), 0
    )
    daily_reserve_injected_cnt = safe_int(
        st.get("daily_reserve_injected_cnt"), 0
    )
    cumulative_reserve_repaid_usd = round(
        safe_float(st.get("cumulative_reserve_repaid_usd"), 0.0), 4
    )
    dust_guard_blocked_cnt = safe_int(st.get("dust_guard_blocked_cnt"), 0)
    daily_dust_guard_blocked_cnt = safe_int(
        st.get("daily_dust_guard_blocked_cnt"), 0
    )
    waiting_reserve_deposit = bool(st.get("waiting_reserve_deposit", False))
    waiting_reserve_deposit_alert_sent = bool(
        st.get("waiting_reserve_deposit_alert_sent", False)
    )
    required_reserve_deposit_usd = round(
        max(0.0, safe_float(st.get("required_reserve_deposit_usd"), 0.0)), 2
    )

    return {
        "buckets": buckets,
        "golden_allin_mode": golden_allin_mode,
        "golden_allin_mode_label": get_golden_allin_mode_label(
            golden_allin_mode
        ),
        "golden_pocket": gp,
        "has_golden_pocket": gp.is_active,
        "golden_pocket_qty": gp_qty,
        "golden_pocket_price": gp_price,
        "golden_pocket_cost_usd": gp_cost,
        "golden_pocket_target_price": gp_target_price,
        "golden_pocket_gain_pct": gp_gain_pct,
        "last_golden_allin_date": last_golden_allin_date,
        "golden_allin_buy_events": golden_allin_buy_events,
        "daily_golden_allin_buy_events": daily_golden_allin_buy_events,
        "golden_pocket_sell_cnt": golden_pocket_sell_cnt,
        "daily_golden_pocket_sell_cnt": daily_golden_pocket_sell_cnt,
        "golden_realized_net_usd": golden_realized_net_usd,
        "daily_golden_realized_net_usd": daily_golden_realized_net_usd,
        "has_active_l1": active_l1,
        "l1_cur_qty": l1_cur_qty,
        "l1_target_quota_qty": l1_target_quota_qty,
        "l1_rem_quota_qty": l1_rem_quota_qty,
        "held_shares": held_shares,
        "total_held_shares": total_held_shares,
        "held_lots": held_lots,
        "held_tiers": held_tiers,
        "upper_tier_count": upper_tier_count,
        "upper_qty": upper_qty,
        "upper_lots": upper_lots,
        "upper_wma_price": upper_wma_price,
        "upper_wma_target_price": upper_wma_target_price,
        "min_indiv_upper_price": min_indiv_upper_price,
        "min_indiv_upper_target_price": min_indiv_upper_target_price,
        "min_indiv_upper_gain_pct": min_indiv_upper_gain_pct,
        "is_l2_only_anti_bloat": is_l2_only,
        "is_late_new_cycle_cutoff": is_late_cutoff,
        "initial_seed_usd": init_seed,
        "free_cash_usd": free_cash,
        "actual_invested_buckets_usd": actual_invested_buckets,
        "actual_invested_usd": actual_invested,
        "book_invested_usd": book_invested,
        "actual_avg_price": actual_avg_p,
        "grid_actual_avg_price": grid_actual_avg_p,
        "book_avg_price": book_avg_p,
        "cycle_reanchor_credit_usd": 0.0,
        "market_eval_usd": market_eval_usd,
        "unrealized_pnl_usd": unrealized_pnl_usd,
        "unrealized_rate_pct": unrealized_rate_pct,
        "cumulative_realized_net_usd": cum_realized,
        "realized_equity_usd": realized_equity_usd,
        "realized_roi_pct": realized_roi_pct,
        "gross_mark_equity_usd": gross_mark_equity_usd,
        "total_mark_equity_usd": total_mark_equity_usd,
        "mark_equity_usd": total_mark_equity_usd,
        "total_net_pnl_usd": total_net_pnl_usd,
        "total_roi_pct": total_roi_pct,
        "mark_roi_pct": total_roi_pct,
        "drop_buy_pct": drop_buy_pct,
        "rise_sell_l1_pct": rise_l1_pct,
        "rise_sell_l2_pct": rise_l2_pct,
        "l1_target_price": l1_target_price,
        "l2_target_price": l2_target_price,
        "l1_gain_pct": l1_gain_pct,
        "l2_gain_pct": l2_gain_pct,
        "active_buy_anchor": round(active_buy_anchor, 4),
        "ref_buy_anchor": round(ref_buy_anchor, 4),
        "chg_from_buy_anchor_pct": chg_from_buy_anchor_pct,
        "cycle_min_buy_price": round(
            cycle_min_p if cycle_min_p > 0.0 else active_buy_anchor, 4
        ),
        "ratchet_anchor_price": round(ratchet_p, 4),
        "trigger_buy_price": trigger_buy_price,
        "unlock_mode": unlock_mode,
        "step_up_eligible": step_up_eligible,
        "stepped_min_price": stepped_min_price,
        "stepped_trigger_price": stepped_trigger_price,
        "rebound_mult": rebound_mult,
        "cash_ratio_pct": cash_ratio_pct,
        "cond_unlock_buy_events": cond_unlock_buy_events,
        "daily_unlock_buy_events": daily_unlock_buy_events,
        "reentry_ref_anchor": round(reentry_ref_anchor, 4),
        "reentry_pullback_price": reentry_pullback_price,
        "reentry_breakout_price": reentry_breakout_price,
        "chg_from_reentry_anchor_pct": chg_from_reentry_anchor_pct,
        "l2_ceiling_price": round(l2_ceiling_price, 4),
        "reentry_signal_type": reentry_signal_type,
        "next_target_qty": next_target_qty,
        "anchor_quota_qty": anchor_quota_qty,
        "budget_cap_qty": budget_cap_qty,
        "next_portion_budget": next_portion_budget,
        "min_req_cash_guard30": min_req_cash_guard30,
        "used_reserve_portions_cnt": used_reserve_portions_cnt,
        "avail_reserve_portions": avail_reserve_portions,
        "max_reserve_portions": MAX_RESERVE_PORTIONS,
        "injected_reserve_usd": injected_reserve_usd,
        "total_reserve_injected_cnt": total_reserve_injected_cnt,
        "daily_reserve_injected_cnt": daily_reserve_injected_cnt,
        "cumulative_reserve_repaid_usd": cumulative_reserve_repaid_usd,
        "dust_guard_blocked_cnt": dust_guard_blocked_cnt,
        "daily_dust_guard_blocked_cnt": daily_dust_guard_blocked_cnt,
        "waiting_reserve_deposit": waiting_reserve_deposit,
        "waiting_reserve_deposit_alert_sent": waiting_reserve_deposit_alert_sent,
        "required_reserve_deposit_usd": required_reserve_deposit_usd,
        "indiv_grid_sell_cnt": indiv_grid_sell_cnt,
        "wma_grad_sell_cnt": wma_grad_sell_cnt,
        "reanchor_cnt": reanchor_cnt,
        "cumulative_reanchor_drop_usd": cum_reanchor_drop,
        "seed_protect_pass_cnt": seed_protect_pass_cnt,
        "daily_seed_protect_pass_cnt": daily_seed_protect_pass_cnt,
        "total_seed_protect_pass_cnt": total_seed_protect_pass_cnt,
        "extra_13plus_buy_events": extra_13plus_buy_events,
        "cumulative_leftover_saved_usd": cum_leftover_saved,
    }


# ---------------------------------------------------------------------------
# [핵심 6] TDD 사전 무결성 자동 검증 슈트 (Case 25 ~ 84 전수 검증)
# ---------------------------------------------------------------------------
def run_quant_engine_tdd() -> bool:
    """
    기동 직전 8% 황금정량 산출, Case 67 min(1회분 예산 상한 주수, 기준가 고정 정량) 이중 캡핑,
    4단 와이드 활주로(-1.0% / -2.0% / -3.5% / -5.5%),
    1층 ~ 6층 개별 완충층 보존 및 8회차 최상단(6층+7층 ➔ 통합 7층 GRID_L7) 병합(Case 72),
    골든포켓(+1.50%) / 1층(+1.50%) / 2~7층 개별(+1.00%) / 2~7층 통합 이동평균(+1.00%) 4중 다중 익절 판정(Case 71, 72, 80),
    🚨 Case 83 (방안 C) 오버나이트(is_overnight_session=True) 중 상단 2~7층 보유 시 개별층 매도 잠금 및 통합이평 일괄 졸업 허용,
    상단 그리드 단독 보유(1층 공석) 시 2층 단가 상한 역전 차단(HOLD_PREVENT_INVERSION · Case 73) 및
    눌림/돌파 독립 1층 재장전(Case 59, 73),
    🛡️ Case 84 정규장 마감 30분 전(is_late_new_cycle_cutoff=True, 15:30 ~ 16:00 EST) 구간 +1.0% 상승돌파 추격 차단 및 -1.0% 눌림목 정상 허용,
    정적 기억저가 잠금 및 🔓 06_STEP2X_15PCT_C20 3중 안전문 스텝업 해금(Case 60, 72, 76),
    💉 05_RESV_6P_GUARD30 30% 자투리 승격 방지 가드 · 토스 계좌 여유자금 감지 자동 수혈 · 0주 졸업 자동 상환(Case 77),
    🎯 Case 78 지정가 부분 체결 후 미체결 잔량(TOPUP_1FL) 기존 1층 무승격 원자적 합산,
    🌟 Case 80 황금시간대(07:00 ~ 07:50 EST & RSI <= 19.0) 기본값 OFF("NONE") 및 POCKET_ALLIN / GRID_L1_ALLIN 판정 검증을 전수 수행한다.
    """
    assert DEFAULT_GOLDEN_ALLIN_MODE == "NONE", (
        f"TDD 실패(Case 80 기본값 OFF 위반): {DEFAULT_GOLDEN_ALLIN_MODE}"
    )

    # 1) 8% 황금정량 및 Case 67 min(budget_cap_qty, anchor_quota_qty) 캡핑 검증
    q_dip, bud_c67 = compute_golden8_quota_qty(
        82.39, 19155.74, 19000.0, "COMP_08PCT", exec_price=79.52
    )
    q_brk, _ = compute_golden8_quota_qty(
        82.39, 19155.74, 19000.0, "COMP_08PCT", exec_price=86.00
    )
    assert q_dip == 18 and q_brk == 17 and (q_brk * 86.00) <= bud_c67, (
        f"TDD 실패(Case 67): q_dip={q_dip}, q_brk={q_brk}"
    )

    # Case 67: 0주 상태에서 직전 anchor_price($85.00)가 존재하고 현재가($80.00)가 낮을 때 정량 일치 검증
    mock_zero_st = {
        "buckets": [],
        "initial_seed_usd": 10000.0,
        "anchor_price": 85.00,
        "cumulative_realized_net_usd": 0.0,
    }
    zero_sum = summarize_stratum_portfolio(mock_zero_st, live_price=80.00)
    q_zero_order, _ = compute_golden8_quota_qty(
        85.00, 10000.0, 10000.0, "COMP_08PCT", exec_price=80.00
    )
    assert (
        zero_sum["anchor_quota_qty"] == 9
        and zero_sum["budget_cap_qty"] == 10
        and zero_sum["next_target_qty"] == q_zero_order == 9
        and zero_sum["golden_allin_mode"] == "NONE"
    ), f"TDD 실패(Case 67/80 0주 정량/기본모드 일치): {zero_sum}"

    # 2) 4단 와이드 활주로 단차 검증
    d1, s1, s2 = get_golden8_prog_thresholds(1, "WIDE_RUNWAY")
    d5, _, _ = get_golden8_prog_thresholds(5, "WIDE_RUNWAY")
    d9, _, _ = get_golden8_prog_thresholds(9, "WIDE_RUNWAY")
    d11, _, _ = get_golden8_prog_thresholds(11, "WIDE_RUNWAY")
    assert (
        d1 == -1.00
        and d5 == -2.00
        and d9 == -3.50
        and d11 == -5.50
        and s1 == 1.50
        and s2 == 1.00
    ), "TDD 실패: 4단 와이드 단차 불일치"

    # 3) 🚨 Case 72: 1층 ~ 6층 개별 완충층 적재 및 8회차 유입 시 최상단(6층+7층 ➔ 통합 7층 GRID_L7) 병합 검증
    grid_q: List[StratumBucket] = []
    for step in range(8):
        p_step = round(100.0 - float(step), 2)
        tag_step = "REENTRY_1FL" if step == 0 else "DIP_1FL"
        grid_q = vrev_add_quota_lot_and_merge_2tier(
            grid_q, 10, p_step, round(10.0 * p_step, 4), tag_step
        )
        assert len(grid_q) == min(MAX_GRID_TIERS_7, step + 1), (
            f"TDD 실패(Case 72 그리드 층수): step={step}, len={len(grid_q)}"
        )

    assert (
        len(grid_q) == 7
        and has_active_l1_bucket(grid_q)
        and grid_q[0].book_price == 93.0
        and grid_q[-1].lot_type == "GRID_L7"
        and grid_q[-1].lot_count == 2
        and abs(grid_q[-1].book_price - 99.50) < 1e-4
    ), f"TDD 실패(Case 72): 8회차 시 최상단 통합 7층 병합 불일치 {grid_q[-1]}"

    # 4) 🚨 Case 71, Case 72, Case 80 & Case 83(방안 C): 4중 다중 익절 및 오버나이트 개별층 잠금 검증
    test_grid = [
        StratumBucket(10, 80.0, 800.0, 800.0, 1, "DIP_1FL"),
        StratumBucket(10, 81.0, 810.0, 810.0, 1, "GRID_L2"),
        StratumBucket(10, 85.0, 850.0, 850.0, 1, "GRID_L3"),
        StratumBucket(10, 90.0, 900.0, 900.0, 1, "GRID_L4"),
    ]
    # 4-A) 프리장/정규장(is_overnight_session=False)에서는 $81.90 에 1층+2층 개별 익절 정상 작동
    res_part = evaluate_multi_grid_sell_targets(
        test_grid, live_price=81.90, is_overnight_session=False
    )
    assert (
        res_part["should_sell"]
        and res_part["sold_indices"] == [0, 1]
        and res_part["sell_qty"] == 20
        and res_part["hit_l1"]
        and res_part["hit_indiv_grid"]
    ), f"TDD 실패(Case 71/72 프리·정규 부분 다중익절): {res_part}"

    # 4-B) [Case 83 방안 C] 오버나이트(is_overnight_session=True) 중에는 $81.90 에 1층+2층 개별 매도를 잠그고 통합이평($85.33 -> 목표 $86.19) 사수!
    res_ov_lock = evaluate_multi_grid_sell_targets(
        test_grid, live_price=81.90, is_overnight_session=True
    )
    assert (
        res_ov_lock["should_sell"] is False
        and res_ov_lock["overnight_indiv_locked"] is True
        and res_ov_lock["reason_tag"] == "HOLD_OVERNIGHT_WMA_LOCK"
    ), f"TDD 실패(Case 83 방안 C 오버나이트 개별층 잠금 미작동): {res_ov_lock}"

    # 4-C) [Case 83 방안 C] 오버나이트(is_overnight_session=True) 중에도 2~4층 통합이평 목표가($86.19) 이상 도달 시 전량 졸업!
    res_ov_grad = evaluate_multi_grid_sell_targets(
        test_grid, live_price=86.25, is_overnight_session=True
    )
    assert (
        res_ov_grad["should_sell"] is True
        and res_ov_grad["sold_indices"] == [0, 1, 2, 3]
        and res_ov_grad["sell_qty"] == 40
        and res_ov_grad["hit_wma_grad"] is True
        and res_ov_grad["reason_tag"] == "SELL_ALL_GRAD"
    ), f"TDD 실패(Case 83 방안 C 오버나이트 통합이평 전량 졸업 미작동): {res_ov_grad}"

    # 4-D) [Case 83 방안 C] 1층 단독 1개 층만 보유 시에는 오버나이트 중에도 +1.50% 에 즉시 익절!
    res_ov_l1_single = evaluate_multi_grid_sell_targets(
        [StratumBucket(10, 80.0, 800.0, 800.0, 1, "REENTRY_1FL")],
        live_price=81.25,
        is_overnight_session=True,
    )
    assert (
        res_ov_l1_single["should_sell"] is True
        and res_ov_l1_single["sold_indices"] == [0]
        and res_ov_l1_single["sell_qty"] == 10
        and res_ov_l1_single["reason_tag"] == "SELL_L1_ONLY"
    ), f"TDD 실패(Case 83 1층 단독 오버나이트 익절 미작동): {res_ov_l1_single}"

    # 4-E) [Case 83 방안 C] GOLDEN_L1 등으로 1층 단가($88.00) > 상단 2~3층 통합이평 목표가($83.83)일 때 오버나이트 중 상단 일괄 졸업(SELL_WMA_UPPER) 정상 작동 검증
    res_ov_wma_upper = evaluate_multi_grid_sell_targets(
        [
            StratumBucket(20, 88.0, 1760.0, 1760.0, 1, "GOLDEN_L1"),
            StratumBucket(10, 81.0, 810.0, 810.0, 1, "GRID_L2"),
            StratumBucket(10, 85.0, 850.0, 850.0, 1, "GRID_L3"),
        ],
        live_price=84.00,
        is_overnight_session=True,
    )
    assert (
        res_ov_wma_upper["should_sell"] is True
        and res_ov_wma_upper["sold_indices"] == [1, 2]
        and res_ov_wma_upper["sell_qty"] == 20
        and res_ov_wma_upper["reason_tag"] == "SELL_WMA_UPPER"
    ), f"TDD 실패(Case 83 1층 고단가 시 상단 일괄졸업 SELL_WMA_UPPER 미작동): {res_ov_wma_upper}"

    # Case 80: 독립 골든포켓 단독 익절(+1.50%) 및 오버나이트 중 골든포켓 단독 익절 검증
    mock_gp = GoldenAllInPocket(
        qty=50,
        book_price=70.00,
        book_invested_usd=3500.0,
        actual_cost_usd=3500.0,
        entry_ts=1000.0,
        order_date="2026-03-10",
    )
    res_gp_only = evaluate_multi_grid_sell_targets(
        test_grid,
        live_price=71.05,
        golden_pocket=mock_gp,
        is_overnight_session=True,
    )
    assert (
        res_gp_only["should_sell"] is True
        and res_gp_only["hit_golden_pocket"] is True
        and res_gp_only["sell_pocket_qty"] == 50
        and res_gp_only["grid_sell_qty"] == 0
        and res_gp_only["sell_qty"] == 50
        and res_gp_only["reason_tag"] == "SELL_GOLDEN_POCKET"
    ), f"TDD 실패(Case 80 골든포켓 단독 익절): {res_gp_only}"

    rem_uppers = relabel_upper_grid_tiers(test_grid[2:])
    assert len(rem_uppers) == 2 and not has_active_l1_bucket(rem_uppers), (
        "TDD 실패(Case 71/72): 1층 익절 후 1층 공석(상단 그리드만 보유) 상태 판별 오류"
    )

    # 5) 🚨 Case 73 & Case 84: 1층 공석 상태에서 현재가 > 2층 단가($85.00) 역전 차단 및 15:30~16:00 돌파 차단 검증
    sig_inv = evaluate_l2_only_hybrid_reentry_signal(
        live_price=85.50,
        anchor_price=83.41,
        l2_book_price=85.00,
        min_upper_tier_price=85.00,
    )
    assert (
        sig_inv["should_buy"] is False
        and sig_inv["signal_type"] == "HOLD_PREVENT_INVERSION"
        and abs(sig_inv["l2_ceiling_price"] - 85.00) < 1e-4
    ), f"TDD 실패(Case 73 단가 역전 차단): {sig_inv}"

    sig_brk_ok = evaluate_l2_only_hybrid_reentry_signal(
        live_price=84.30,
        anchor_price=83.41,
        l2_book_price=85.00,
        min_upper_tier_price=85.00,
        is_late_new_cycle_cutoff=False,
    )
    assert (
        sig_brk_ok["should_buy"] is True
        and sig_brk_ok["signal_type"] == "BREAKOUT_RELOAD"
    ), f"TDD 실패(Case 73 2층 이하 안전 돌파 승인): {sig_brk_ok}"

    # NEW [Case 84 TDD 검증 1]: 15:30 ~ 16:00 EST (is_late_new_cycle_cutoff=True) 구간에서 +1.0% 돌파 추격 차단 검증
    sig_brk_late_blocked = evaluate_l2_only_hybrid_reentry_signal(
        live_price=84.30,
        anchor_price=83.41,
        l2_book_price=85.00,
        min_upper_tier_price=85.00,
        is_late_new_cycle_cutoff=True,
    )
    assert (
        sig_brk_late_blocked["should_buy"] is False
        and sig_brk_late_blocked["signal_type"]
        == "HOLD_LATE_SESSION_BREAKOUT_CUTOFF"
    ), f"TDD 실패(Case 84 장마감 30분전 1층공석 돌파차단 미작동): {sig_brk_late_blocked}"

    # NEW [Case 84 TDD 검증 2]: 15:30 ~ 16:00 EST (is_late_new_cycle_cutoff=True) 구간에서도 -1.0% 눌림목 재장전은 정상 허용 검증
    sig_pull_ok = evaluate_l2_only_hybrid_reentry_signal(
        live_price=82.50,
        anchor_price=83.41,
        l2_book_price=85.00,
        min_upper_tier_price=85.00,
        is_late_new_cycle_cutoff=True,
    )
    assert (
        sig_pull_ok["should_buy"] is True
        and sig_pull_ok["signal_type"] == "PULLBACK_RELOAD"
    ), f"TDD 실패(Case 73/84 눌림목 재장전 승인): {sig_pull_ok}"

    reloaded_grid = vrev_add_quota_lot_and_merge_2tier(
        rem_uppers, 10, 80.50, 805.0, "REENTRY_1FL"
    )
    assert (
        len(reloaded_grid) == 3
        and has_active_l1_bucket(reloaded_grid)
        and reloaded_grid[0].book_price == 80.50
        and reloaded_grid[1].book_price == 85.00
        and reloaded_grid[2].book_price == 90.00
    ), "TDD 실패(Case 59/72): 1층 공석 재장전 시 상단 그리드 비병합 배치 오류"

    res_grad = evaluate_multi_grid_sell_targets(reloaded_grid, live_price=88.50)
    assert (
        res_grad["should_sell"]
        and res_grad["sold_indices"] == [0, 1, 2]
        and res_grad["sell_qty"] == 30
        and res_grad["hit_wma_grad"]
    ), f"TDD 실패(Case 71/72 2~7층 이동평균 일괄졸업): {res_grad}"

    # 6) Case 60 & Case 72 정적 기억 최저가($80.00) 잠금 및 Case 74 당일 시드보호 패스 바인딩 검증
    mock_st = {
        "buckets": buckets_to_dicts(reloaded_grid),
        "initial_seed_usd": 10000.0,
        "anchor_price": 80.50,
        "cycle_min_buy_price": 80.00,
        "cumulative_realized_net_usd": 25.0,
        "seed_protect_pass_cnt": 120,
        "daily_seed_protect_pass_cnt": 7,
    }
    sum_info = summarize_stratum_portfolio(mock_st, live_price=81.00)
    assert abs(sum_info["active_buy_anchor"] - 80.00) < 1e-4, (
        "TDD 실패(Case 60/72): 정적 기억 최저가 잠금 풀림"
    )
    assert (
        sum_info["held_tiers"] == 3
        and sum_info["upper_tier_count"] == 2
        and abs(sum_info["upper_wma_price"] - 87.50) < 1e-4
        and abs(sum_info["l2_ceiling_price"] - 85.00) < 1e-4
        and sum_info["seed_protect_pass_cnt"] == 7
    ), "TDD 실패(Case 72/73/74): 상단 2~7층 이동평균 또는 당일 시드패스 요약 오류"

    # 7) [Case 76 : 🔓 06_STEP2X_15PCT_C20 3중 안전문 스텝업 저가 해금 검증]
    mock_2022_deadcat = [
        StratumBucket(75, 14.43, 1082.25, 1082.25, 1, "REENTRY_1FL"),
        StratumBucket(189, 47.82, 9037.98, 9037.98, 11, "GRID_L2"),
    ]
    res_deadcat = evaluate_step_up_2x_dip_signal(
        live_price=11.50,
        buckets=mock_2022_deadcat,
        anchor_price=14.43,
        cycle_min_buy_price=8.56,
        drop_buy_pct=-5.50,
        free_cash_usd=4500.0,
        realized_equity_usd=13913.0,
    )
    assert (
        res_deadcat["should_buy"] is False
        and res_deadcat["step_up_eligible"] is False
    ), f"TDD 실패(Case 76 2022 데드캣 오발동): {res_deadcat}"

    mock_2025_nov = [
        StratumBucket(41, 50.10, 2054.10, 2054.10, 1, "REENTRY_1FL"),
        StratumBucket(308, 60.64, 18677.12, 18677.12, 10, "GRID_L2"),
    ]
    res_step_ok = evaluate_step_up_2x_dip_signal(
        live_price=42.44,
        buckets=mock_2025_nov,
        anchor_price=50.10,
        cycle_min_buy_price=12.09,
        drop_buy_pct=-5.50,
        free_cash_usd=5699.55,
        realized_equity_usd=26431.99,
    )
    assert (
        res_step_ok["should_buy"] is True
        and res_step_ok["is_step_up_unlock"] is True
        and res_step_ok["trigger_tag"] == "UNLOCK_STEP2X_15P_C20"
        and abs(res_step_ok["quota_ref_price"] - 42.585) < 1e-4
        and abs(res_step_ok["next_cycle_min_price"] - 42.44) < 1e-4
    ), f"TDD 실패(Case 76 2025-11-05 스텝업 해금 미작동): {res_step_ok}"

    # 8) 단가 비교 층간 스마트 중간 편입 & 매도 층 원가 매칭 정산 검증
    mid_inserted = vrev_add_quota_lot_and_merge_2tier(
        reloaded_grid, 10, 84.50, 845.0, "MANUAL_SYNC_L1"
    )
    assert (
        len(mid_inserted) == 4
        and mid_inserted[0].book_price == 80.50
        and mid_inserted[1].book_price == 84.50
        and mid_inserted[1].lot_type == "GRID_L2"
        and mid_inserted[2].book_price == 85.00
        and mid_inserted[2].lot_type == "GRID_L3"
    ), f"TDD 실패(단가 비교 층간 편입): {mid_inserted}"

    match_res = match_and_remove_sold_buckets_7tier(
        mid_inserted, delta_remove_qty=10, sell_exec_price=82.50
    )
    assert (
        match_res["sold_qty"] == 10
        and abs(match_res["sold_actual_cost_usd"] - 805.0) < 1e-4
        and match_res["sold_l1_completely"] is True
        and len(match_res["rem_buckets"]) == 3
        and not has_active_l1_bucket(match_res["rem_buckets"])
        and match_res["pnl_info"]["net_pnl_usd"] > 0.0
    ), f"TDD 실패(수동 매도 층별 원가 매칭 정산): {match_res}"

    # 9) [Case 77 : 💉 05_RESV_6P_GUARD30 검증]
    g30_block = evaluate_guard30_and_reserve_injection(
        free_cash_usd=180.0,
        broker_bp_usd=180.0,
        exec_price=29.0,
        portion_budget=1440.0,
        l1_actual_cost_usd=1426.0,
        is_dip_promotion=True,
        used_reserve_portions_cnt=0,
    )
    assert (
        g30_block["action"] == "BLOCK_AND_ALERT_DEPOSIT"
        and g30_block["should_proceed"] is False
        and g30_block["is_dust_blocked"] is True
        and abs(g30_block["min_req_cash"] - 432.0) < 1e-4
        and abs(g30_block["recommended_deposit_usd"] - 1440.0) < 1e-4
    ), f"TDD 실패(Case 77 미입금 시 자투리 차단 오류): {g30_block}"

    g30_inj = evaluate_guard30_and_reserve_injection(
        free_cash_usd=180.0,
        broker_bp_usd=1680.0,
        exec_price=29.0,
        portion_budget=1440.0,
        l1_actual_cost_usd=1426.0,
        is_dip_promotion=True,
        used_reserve_portions_cnt=0,
    )
    assert (
        g30_inj["action"] == "INJECT_AND_PROCEED"
        and g30_inj["should_proceed"] is True
        and g30_inj["inject_portions"] == 1
        and abs(g30_inj["inject_usd"] - 1440.0) < 1e-4
        and g30_inj["rem_portions_after"] == 5
    ), f"TDD 실패(Case 77 입금 감지 자동 수혈 오류): {g30_inj}"

    repay_res = compute_reserve_repayment_on_zero(
        initial_seed_usd=10000.0,
        cumulative_realized_net_usd=11418.55,
        injected_reserve_usd=13242.27,
        used_reserve_portions_cnt=6,
    )
    assert (
        repay_res["did_repay"] is True
        and abs(repay_res["repaid_usd"] - 13242.27) < 1e-4
        and repay_res["rem_injected_reserve_usd"] == 0.0
        and repay_res["rem_used_reserve_portions_cnt"] == 0
        and repay_res["avail_reserve_portions"] == 6
        and abs(repay_res["free_cash_after_repay_usd"] - 21418.55) < 1e-4
    ), f"TDD 실패(Case 77 0주 졸업 예비시드 상환 오류): {repay_res}"

    # 10) [Case 78 : 지정가 부분 체결 후 잔량(TOPUP_1FL) 체결 시 무승격 단일 1층 합산 검증]
    partial_q = vrev_add_quota_lot_and_merge_2tier(
        [], 2, 90.71, round(2.0 * 90.71, 4), "REENTRY_1FL"
    )
    mock_part_st = {
        "buckets": buckets_to_dicts(partial_q),
        "initial_seed_usd": 19000.0,
        "anchor_price": 90.71,
        "cycle_min_buy_price": 90.71,
        "l1_target_quota_qty": 17,
    }
    part_sum = summarize_stratum_portfolio(mock_part_st, live_price=90.75)
    assert (
        part_sum["l1_cur_qty"] == 2
        and part_sum["l1_target_quota_qty"] == 17
        and part_sum["l1_rem_quota_qty"] == 15
    ), f"TDD 실패(Case 78 부분체결 잔량 요약 불일치): {part_sum}"

    completed_q = vrev_add_quota_lot_and_merge_2tier(
        partial_q, 15, 90.71, round(15.0 * 90.71, 4), "TOPUP_1FL"
    )
    assert (
        len(completed_q) == 1
        and completed_q[0].qty == 17
        and completed_q[0].lot_count == 1
        and abs(completed_q[0].book_price - 90.71) < 1e-4
        and abs(completed_q[0].actual_cost_usd - 1542.07) < 1e-4
    ), f"TDD 실패(Case 78 TOPUP_1FL 무승격 1층 합산 불일치): {completed_q}"

    # 11) [Case 80 : 황금시간대(07:00 ~ 07:50 EST & RSI <= 19.0) 전액매수 판정 검증]
    g_off = evaluate_golden_allin_signal(
        hm=715,
        rsi_14=17.5,
        live_price=40.0,
        golden_allin_mode="NONE",
        today_str="2026-03-10",
    )
    assert g_off["should_buy"] is False and g_off["reason"] == "MODE_OFF", (
        f"TDD 실패(Case 80 OFF 모드 차단 오류): {g_off}"
    )

    g_pocket_ok = evaluate_golden_allin_signal(
        hm=725,
        rsi_14=18.4,
        live_price=40.0,
        golden_allin_mode="POCKET_ALLIN",
        today_str="2026-03-10",
        last_golden_allin_date="2026-03-09",
    )
    assert (
        g_pocket_ok["should_buy"] is True
        and g_pocket_ok["lot_type"] == "GOLDEN_POCKET"
    ), f"TDD 실패(Case 80 POCKET_ALLIN 승인 오류): {g_pocket_ok}"

    g_grid_ok = evaluate_golden_allin_signal(
        hm=745,
        rsi_14=19.0,
        live_price=40.0,
        golden_allin_mode="GRID_L1_ALLIN",
        today_str="2026-03-10",
        last_golden_allin_date="",
    )
    assert (
        g_grid_ok["should_buy"] is True
        and g_grid_ok["lot_type"] == "GOLDEN_L1"
    ), f"TDD 실패(Case 80 GRID_L1_ALLIN 승인 오류): {g_grid_ok}"

    allin_q, allin_spent = resolve_allin_affordable_buy_qty(
        price_t=40.0, free_cash_usd=8000.0
    )
    assert allin_q == 199 and abs(allin_spent - 7960.0) < 1e-4, (
        f"TDD 실패(Case 80 전액매수 주수 산출 오류): q={allin_q}, spent={allin_spent}"
    )

    logger.info(
        "✅ [QuantEngine TDD 사전 무결성 검증 통과] 챔피언 🌟 POCKET_ALLIN / 🔥 GRID_L1_ALLIN × 💉 05_RESV_6P_GUARD30 × 🔓 06_STEP2X_15PCT_C20 & 방안 C · Case 84(Case 59~84) 검증 완료"
    )
    return True
