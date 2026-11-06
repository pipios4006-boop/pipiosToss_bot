# -*- coding: utf-8 -*-
"""
# MODIFIED: quant_engine.py (황금시간 07:00~07:50 RSI<=19 올인 재익스포트·포켓매칭·다중익절·요약·TDD 전면 영구 소각 & Case 91 무제한 예비수혈 카운트 및 인출형[단리]/자산증식형[복리] 요약·TDD & Case 92 1층 공석 +1.00% 상승돌파 RSI(14) <= 50.0 필터 요약·TDD 탑재)
인피니트 스노우볼 (Infinite Snowball) v3.0 — 퀀트 엔진 코어 Part 2 / 2 (Step 05 / 13)
역할:
1) quant_engine_core.py (Part 1 / 2) 의 모든 상수(DEFAULT_GRID_MERGE_MODE · Case 88 서브 그리드 상수 · Case 91 복리/단리 모드 상수 · Case 92 REENTRY_BREAKOUT_MAX_RSI_50 포함)·구조체·정량/무제한수혈/스텝업/서브해금/컷오프/동적수수료 판정 심볼
   명시적 재익스포트(Facade Re-export)로 타 모듈 AST 임포트 호환성 100% 보장
2) 본 그리드 1층 ~ 7층 골디락스 순수 멀티 그리드 배치 및 병합기(vrev_add_quota_lot_and_merge_2tier :
   REENTRY_1FL 독립 1층 배치 / TOPUP_1FL 기존 1층 무승격 원자적 합산[Case 78] /
   DIP_1FL 7층 이하 개별 승격 및 7층 초과[8층 발생] 시 구 1층[새 2층 후보] 보존 + 구 2층 + 구 7층 통합 후 평단 오름차순 중간층 재배치[L2_L7_MERGE_SORT · Case 53, 72, 87] /
   수동 추가매수 시 단가 비교 오름차순 층간 스마트 중간 편입[Case 63]) 및
   🛡️ Default-ON 3층 서브 그리드 배치 및 양끝 합병기(add_lot_to_sub_grid_with_flag / add_lot_to_sub_grid :
   SUB_REENTRY_1FL 독립 서브 1층 배치 / SUB_TOPUP_1FL 기존 서브 1층 무승격 합산[Case 78] /
   SUB_DIP_1FL 3층 이하 개별 승격 및 3층 초과[4층 발생] 시 서브 구 1층 + 구 3층 양끝 합병 후 오름차순 재배치[SUB_L1_L3_MERGE · Case 88])
3) 수동 매도 시 3층 서브 그리드 · 7층 본 그리드 최하단 저가 지층 순차 1:1 매칭 정산기(match_and_remove_sold_buckets_7tier · Case 63, 69, 87, 88) 및
   계좌별 동적 왕복 수수료율(0.14% / 0.20%) · 실측 매도 수수료(execution.commission + tax) 반영 세후 실현손익 산출기(calc_sell_realized_pnl · Case 86)
4) 본 그리드 상단 2층 ~ 7층 순수 통합 이동평균(compute_upper_2_to_7_moving_avg : 1층 단가 100% 배제) 및 서브 그리드 상단 2층 ~ 3층 순수 통합 이동평균(compute_sub_upper_2_to_3_moving_avg · Case 88) 산출 ·
   🚨 [Case 83 방안 C & Case 88 & 상단 순수 통합이평 +1.00% 도달 시 1층 무조건 동시 포함 전량 졸업] 오버나이트(애프터·데이마켓, is_overnight_session=True) 중 상단층 보유 시
   해당 그리드의 개별 층(1층 및 상단 개별/합병층) 쪼개 팔기를 잠가 통합 이동평균(wma_2_to_7 / sub_wma_2_to_3) 도망을 원천 봉쇄하고,
   2층 ~ 7층(서브 2층 ~ 3층) 순수 이동평균 단가 대비 +1.00% 목표가(wma_target_p / sub_wma_target_p) 도달 시에는
   1층 매수 단가와 무관하게 1층 물량까지 동일한 가격(wma_target_p)에 조건 없이 100% 포함하여 전량 매도(SELL_ALL_GRAD / SELL_SUB_ALL_GRAD)함으로써 즉시 0주 사이클을 완전 종료시키는 하이브리드 매도 판정기(evaluate_multi_grid_sell_targets)
5) 포트폴리오 통합 요약기(summarize_stratum_portfolio · 자산증식형[복리] vs 인출형[단리] 예산 산출 · 당일 인출가능 실현수익[daily_withdrawable_profit_usd] · 누적 인출가능 잉여현금[withdrawable_surplus_usd] · 자체수혈 탄창[self_reserve_portions] · 무제한 예비시드 수혈 횟수 카운트 · 층별 자산 금액[$]/비중[%] · 10칸 유니코드 배분 게이지[🟦🟨🟩] · 현재 사이클 단위 실현수익[cycle_realized_net_usd] · 전량 졸업 시 확정 예정 총자산[projected_graduation_equity_usd] · Case 92 1층 공석 +1.00% 돌파 RSI(14) <= 50.0 필터 상태 산출 포함) 및
   기동 전 TDD 사전 무결성 검증 슈트(run_quant_engine_tdd · Case 25 ~ 92 전수 검증)
- 제1헌법 ~ 제6헌법 및 Case 01 ~ 92 완벽 준수
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from quant_engine_core import (
    BASE_MAX_LOTS_8PCT,
    DEFAULT_GRID_MERGE_MODE,
    DEFAULT_INITIAL_SEED_USD,
    DEFAULT_SUB_MERGE_MODE,
    DEFAULT_UNLOCK_MODE,
    DEFAULT_US_COMMISSION_RATE,
    MAX_GRID_TIERS,
    MAX_GRID_TIERS_7,
    MAX_GRID_TIERS_12,
    MAX_RESERVE_PORTIONS,
    MIN_DIP_BUDGET_RATIO,
    MIN_DIP_VS_L1_RATIO,
    NEW_CYCLE_BUY_CUTOFF_HM,
    PORTION_MODE_COMPOUND,
    PORTION_MODE_SIMPLE,
    PORTION_RATIO_LOCKED,
    REANCHOR_NET_BUFFER_MULT,
    REENTRY_BREAKOUT_MAX_RSI_50,
    REENTRY_BREAKOUT_RISE_PCT,
    REENTRY_PULLBACK_DROP_PCT,
    RESERVE_DEPOSIT_TOLERANCE_RATIO,
    ROUND_TRIP_FEE_RATE_PCT,
    STEP_UP_2X_DROP_PCT,
    STEP_UP_2X_MAX_TIERS,
    STEP_UP_2X_MIN_CASH_RATIO,
    STEP_UP_2X_MIN_REBOUND_MULT,
    SUB_FROZEN_DAYS_TRIGGER,
    SUB_GRID_DEFAULT_ENABLED,
    SUB_MAX_TIERS,
    SUB_MAX_TIERS_3,
    SUB_MAX_TOTAL_LOTS,
    SUB_MAX_TOTAL_LOTS_4,
    SUB_MERGE_MODE_L1_L3,
    SUB_PORTION_RATIO_4PCT,
    SUB_RESERVE_MAIN_PORTIONS,
    SUB_UNLOCK_DROP_FROM_L1_PCT,
    SUB_UNLOCK_FROZEN_DAYS_10,
    VALID_PORTION_MODES,
    StratumBucket,
    buckets_from_dicts,
    buckets_to_dicts,
    compute_golden8_quota_qty,
    compute_reserve_repayment_on_zero,
    compute_sub4_quota_qty,
    compute_sub_grid_available_idle_cash,
    enforce_true_breakeven_floor_on_buckets,
    evaluate_guard30_and_reserve_injection,
    evaluate_l2_only_hybrid_reentry_signal,
    evaluate_step_up_2x_dip_signal,
    evaluate_sub_grid_dip_signal,
    get_golden8_prog_thresholds,
    get_runtime_round_trip_fee_rate_pct,
    get_runtime_us_commission_rate,
    has_active_l1_bucket,
    is_simple_income_mode,
    is_upper_grid_tier,
    relabel_sub_upper_grid_tiers,
    relabel_sub_upper_grid_tiers_with_flag,
    relabel_upper_grid_tiers,
    resolve_affordable_buy_qty,
    resolve_effective_round_trip_fee_rate_pct,
    resolve_portion_budget_base_equity,
    set_runtime_round_trip_fee_rate_pct,
)
from toss_api import EST_TZ, safe_float, safe_int

logger = logging.getLogger("toss_sniper.quant_engine")


# ---------------------------------------------------------------------------
# [핵심 4 · Case 63, Case 71 ~ 88] 본 그리드 1층 ~ 7층(L2_L7_MERGE_SORT) & 서브 그리드 1층 ~ 3층(SUB_L1_L3_MERGE) 배치 · 매도 층 원가 매칭 정산기
# ---------------------------------------------------------------------------
def vrev_add_quota_lot_and_merge_2tier(
    queue: Sequence[StratumBucket],
    buy_qty: int,
    buy_price: float,
    actual_spent_usd: Optional[float] = None,
    lot_type: str = "QUOTA_L1",
    max_tiers: int = MAX_GRID_TIERS_7,
    merge_mode: str = DEFAULT_GRID_MERGE_MODE,
) -> List[StratumBucket]:
    """
    🎯 3 & 🎯 4 & Case 46 ~ 87 (함수명은 타 모듈 AST 호환을 위해 유지하되 내부는 1~7층 골디락스 L2_L7_MERGE_SORT 멀티 그리드로 작동):
    신규 정량 매수 체결 시 최대 7개 지층(1층 공격수 + 2~7층 상단 완충/합병 그리드 ·
    8층 발생 시 구 1층 보존 + 구 2층 + 구 7층 통합 후 평단 오름차순 중간층 재배치)을 관리한다.
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
    eff_merge_mode = (
        str(merge_mode or DEFAULT_GRID_MERGE_MODE).upper().strip()
    )

    # 🚨 Case 59, Case 71, Case 72 & Case 73: 상단 그리드(2층 ~ 7층)만 보유 중(1층 공석) REENTRY_1FL 유입 시 상단 비병합 독립 1층 배치!
    if not has_active_l1_bucket(existing) and tag in (
        "REENTRY_1FL",
        "TOPUP_1FL",
    ):
        preserved_uppers = relabel_upper_grid_tiers(
            existing, max_tiers=eff_max_tiers, merge_mode=eff_merge_mode
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
            existing[1:], max_tiers=eff_max_tiers, merge_mode=eff_merge_mode
        )
        return [merged_l1] + preserved_uppers

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

    # 🚨 [Case 63, Case 72 & Case 87 : 단가 비교 오름차순(저가 1층 ➔ 고가 7층) 층간 중간 편입]
    if pure_p > existing[0].book_price + 1e-6:
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
            combined[1:], max_tiers=eff_max_tiers, merge_mode=eff_merge_mode
        )
        return [lowest_b] + sorted_uppers

    shifted_uppers = relabel_upper_grid_tiers(
        existing, max_tiers=eff_max_tiers, merge_mode=eff_merge_mode
    )
    return [new_l1] + shifted_uppers


def add_lot_to_sub_grid_with_flag(
    sub_queue: Sequence[StratumBucket],
    buy_qty: int,
    buy_price: float,
    actual_spent_usd: Optional[float] = None,
    lot_type: str = "SUB_REENTRY_1FL",
    max_tiers: int = SUB_MAX_TIERS_3,
    merge_mode: str = SUB_MERGE_MODE_L1_L3,
) -> Tuple[List[StratumBucket], bool]:
    """
    # [Case 88 : 🛡️ 13_SUB_L1L3_RESV05_CAP4L — 스위치 없는 100% 기본 상시 적용(Default ON) 3층 서브 그리드 배치 및 양끝 합병기]:
    1) 서브 0주 첫 진입 시 단일 서브 1층([new_sub_l1], False) 생성.
    2) 서브 상단(2~3층)만 보유 중(서브 1층 공석) SUB_REENTRY_1FL / SUB_TOPUP_1FL 유입 시 상단 비병합 독립 서브 1층 배치.
    3) 서브 활성 1층 보유 중 미체결 잔량 보충(SUB_TOPUP_1FL) 유입 시 지층 승격이나 회차 증가 없이 기존 서브 1층에 원자적 가중평균 합산(Case 78).
    4) 서브 활성 1층 보유 중 추매(SUB_DIP_1FL) 유입 시:
       - 기존 서브 지층이 2개 이하이면 GRID_L2, GRID_L3 로 1칸씩 승격.
       - 기존 서브 지층이 이미 3개(4회분 유입으로 4층 발생)이면 relabel_sub_upper_grid_tiers_with_flag() 를 통해
         서브 구 1층(existing[0])과 구 3층(existing[-1])을 양끝 가중평균 합병(SUB_L1_L3_MERGE)하고 오름차순 재배치한 뒤 did_merge=True 를 반환한다!
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
    raw_tag = str(lot_type or "SUB_REENTRY_1FL").upper().strip()
    if raw_tag in (
        "SUB_REENTRY_1FL_BREAKOUT",
        "SUB_REENTRY_1FL_PULLBACK",
        "SUB_TOPUP_1FL",
    ):
        clean_tag = "SUB_REENTRY_1FL"
    elif is_upper_grid_tier(raw_tag):
        clean_tag = "SUB_DIP_1FL"
    else:
        clean_tag = raw_tag

    new_sub_l1 = StratumBucket(
        qty=q_int,
        book_price=pure_p,
        book_invested_usd=spent,
        actual_cost_usd=spent,
        lot_count=1,
        lot_type=clean_tag,
    )

    existing = [
        sb
        for sb in (sub_queue or [])
        if isinstance(sb, StratumBucket) and sb.qty > 0
    ]
    if not existing:
        return [new_sub_l1], False

    eff_max_tiers = max(2, safe_int(max_tiers, SUB_MAX_TIERS_3))
    eff_merge_mode = str(merge_mode or SUB_MERGE_MODE_L1_L3).upper().strip()

    # 서브 1층 공석 재장전 시 기존 서브 상단(2~3층) 비병합 독립 서브 1층 배치
    if not has_active_l1_bucket(existing) and raw_tag in (
        "SUB_REENTRY_1FL",
        "SUB_REENTRY_1FL_BREAKOUT",
        "SUB_REENTRY_1FL_PULLBACK",
        "SUB_TOPUP_1FL",
        "REENTRY_1FL",
        "TOPUP_1FL",
    ):
        preserved_uppers, did_m = relabel_sub_upper_grid_tiers_with_flag(
            existing, max_tiers=eff_max_tiers, merge_mode=eff_merge_mode
        )
        return [new_sub_l1] + preserved_uppers, did_m

    # [Case 78]: 서브 활성 1층 부분체결 잔량 보충(SUB_TOPUP_1FL) 시 무승격 원자적 합산
    if raw_tag in ("SUB_TOPUP_1FL", "TOPUP_1FL") and has_active_l1_bucket(
        existing
    ):
        old_sb1 = existing[0]
        comb_qty = old_sb1.qty + q_int
        comb_cost = round(old_sb1.actual_cost_usd + spent, 4)
        comb_p = round(max(0.0001, comb_cost / float(comb_qty)), 4)
        keep_tag = (
            old_sb1.lot_type
            if not is_upper_grid_tier(old_sb1.lot_type)
            else "SUB_REENTRY_1FL"
        )
        merged_sub_l1 = StratumBucket(
            qty=comb_qty,
            book_price=comb_p,
            book_invested_usd=comb_cost,
            actual_cost_usd=comb_cost,
            lot_count=max(1, old_sb1.lot_count),
            lot_type=keep_tag,
        )
        preserved_uppers, did_m = relabel_sub_upper_grid_tiers_with_flag(
            existing[1:], max_tiers=eff_max_tiers, merge_mode=eff_merge_mode
        )
        return [merged_sub_l1] + preserved_uppers, did_m

    if pure_p > existing[0].book_price + 1e-6:
        combined = list(existing) + [new_sub_l1]
        combined.sort(key=lambda b: round(b.book_price, 4))
        lowest_b = combined[0]
        if is_upper_grid_tier(lowest_b.lot_type):
            lowest_b = StratumBucket(
                qty=lowest_b.qty,
                book_price=lowest_b.book_price,
                book_invested_usd=lowest_b.book_invested_usd,
                actual_cost_usd=lowest_b.actual_cost_usd,
                lot_count=max(1, lowest_b.lot_count),
                lot_type=clean_tag,
            )
        sorted_uppers, did_m = relabel_sub_upper_grid_tiers_with_flag(
            combined[1:], max_tiers=eff_max_tiers, merge_mode=eff_merge_mode
        )
        return [lowest_b] + sorted_uppers, did_m

    shifted_uppers, did_m = relabel_sub_upper_grid_tiers_with_flag(
        existing, max_tiers=eff_max_tiers, merge_mode=eff_merge_mode
    )
    return [new_sub_l1] + shifted_uppers, did_m


def add_lot_to_sub_grid(
    sub_queue: Sequence[StratumBucket],
    buy_qty: int,
    buy_price: float,
    actual_spent_usd: Optional[float] = None,
    lot_type: str = "SUB_REENTRY_1FL",
    max_tiers: int = SUB_MAX_TIERS_3,
    merge_mode: str = SUB_MERGE_MODE_L1_L3,
) -> List[StratumBucket]:
    new_sub_q, _ = add_lot_to_sub_grid_with_flag(
        sub_queue=sub_queue,
        buy_qty=buy_qty,
        buy_price=buy_price,
        actual_spent_usd=actual_spent_usd,
        lot_type=lot_type,
        max_tiers=max_tiers,
        merge_mode=merge_mode,
    )
    return new_sub_q


def match_and_remove_sold_buckets_7tier(
    buckets: Sequence[StratumBucket],
    delta_remove_qty: int,
    sell_exec_price: float = 0.0,
    max_tiers: int = MAX_GRID_TIERS_7,
    round_trip_fee_rate_pct: Optional[float] = None,
    actual_sell_fee_usd: Optional[float] = None,
    merge_mode: str = DEFAULT_GRID_MERGE_MODE,
    sub_buckets: Optional[Sequence[StratumBucket]] = None,
    sub_max_tiers: int = SUB_MAX_TIERS_3,
    sub_merge_mode: str = SUB_MERGE_MODE_L1_L3,
) -> Dict[str, Any]:
    """
    # MODIFIED [Case 63, Case 69, Case 71, Case 72, Case 86, Case 87 & Case 88 최하단 저가 지층 순차 매칭 정산기]:
    수동 매도(전량 또는 부분 매도)로 보유 수량이 delta_remove_qty 만큼 줄었을 때:
    1) 차감 수량(rem_to_cut)이 서브 그리드(sub_buckets) 또는 본 그리드(buckets)의
       단독 보유 수량과 정확히 일치하면 해당 레이어를 1:1 우선 차감한다.
    2) 복합 수량 차감 시에는 매 스텝마다 잔존 (sub_queue[0], main_queue[0]) 후보 중
       매수 단가(book_price)가 가장 낮은 최하단 저가 지층부터 순차적으로 차감하여,
       본 그리드 고가 상단층이 서브 그리드 저가 1층보다 먼저 차감되는 원가 왜곡 역설을 100% 원천 차단한다!
    3) 실제로 차감된 물량의 고유 순수 매수 원금(sold_actual_cost_usd)과 계좌별 수수료율을 적용하여
       calc_sell_realized_pnl() 로 세후 실현수익(net_pnl_usd)을 정밀 산출한다.
    """
    valid = [
        b
        for b in (buckets or [])
        if isinstance(b, StratumBucket) and b.qty > 0
    ]
    valid_sub = [
        sb
        for sb in (sub_buckets or [])
        if isinstance(sb, StratumBucket) and sb.qty > 0
    ]
    rem_to_cut = max(0, safe_int(delta_remove_qty, 0))
    exec_p = round(max(0.0, safe_float(sell_exec_price, 0.0)), 4)

    if (not valid and not valid_sub) or rem_to_cut <= 0:
        return {
            "rem_buckets": valid,
            "rem_sub_buckets": valid_sub,
            "sold_sub_qty": 0,
            "sold_sub_cost_usd": 0.0,
            "sold_sub_buckets": [],
            "sold_sub_l1_completely": False,
            "sold_sub_merged_bucket": False,
            "sold_buckets": [],
            "sold_qty": 0,
            "sold_actual_cost_usd": 0.0,
            "sold_avg_cost_price": 0.0,
            "sold_tier_desc": "없음",
            "sold_l1_completely": False,
            "sold_upper_tier": False,
            "pnl_info": calc_sell_realized_pnl(
                0,
                exec_p,
                0.0,
                round_trip_fee_rate_pct=round_trip_fee_rate_pct,
                actual_sell_fee_usd=actual_sell_fee_usd,
            ),
        }

    sold_tier_parts: List[str] = []

    was_active_l1 = has_active_l1_bucket(valid)
    was_sub_active_l1 = has_active_l1_bucket(valid_sub)

    main_queue: List[Tuple[int, StratumBucket]] = [
        (idx, b) for idx, b in enumerate(valid)
    ]
    sub_queue: List[Tuple[int, StratumBucket]] = [
        (s_idx, sb) for s_idx, sb in enumerate(valid_sub)
    ]

    sold_buckets: List[StratumBucket] = []
    sold_sub_buckets: List[StratumBucket] = []
    removed_first_tier_completely = False
    sold_upper_tier = False
    sold_sub_l1_completely = False
    sold_sub_merged_bucket = False

    def _pop_from_sub(cut_q: int) -> int:
        nonlocal sold_sub_l1_completely, sold_sub_merged_bucket
        if not sub_queue or cut_q <= 0:
            return 0
        s_idx, sb = sub_queue[0]
        s_label = (
            "서브1층"
            if (s_idx == 0 and was_sub_active_l1)
            else f"서브{s_idx + 1 if was_sub_active_l1 else s_idx + 2}층"
        )
        if cut_q >= sb.qty:
            taken = sb.qty
            sold_sub_buckets.append(sb)
            sold_tier_parts.append(
                f"{s_label}({sb.qty}주@${sb.book_price:.2f})"
            )
            sub_queue.pop(0)
            if s_idx == 0 and was_sub_active_l1:
                sold_sub_l1_completely = True
            if max(1, sb.lot_count) > 1:
                sold_sub_merged_bucket = True
            return taken

        sold_sq_part = cut_q
        keep_sq = sb.qty - cut_q
        pure_s_unit_p = sb.actual_avg_price
        sold_scost_part = round(float(sold_sq_part) * pure_s_unit_p, 4)
        keep_scost_part = round(
            max(
                0.01 * float(keep_sq),
                sb.actual_cost_usd - sold_scost_part,
            ),
            4,
        )
        sold_sub_buckets.append(
            StratumBucket(
                qty=sold_sq_part,
                book_price=round(sold_scost_part / float(sold_sq_part), 4),
                book_invested_usd=sold_scost_part,
                actual_cost_usd=sold_scost_part,
                lot_count=1,
                lot_type=sb.lot_type,
            )
        )
        sub_queue[0] = (
            s_idx,
            StratumBucket(
                qty=keep_sq,
                book_price=round(keep_scost_part / float(keep_sq), 4),
                book_invested_usd=keep_scost_part,
                actual_cost_usd=keep_scost_part,
                lot_count=max(1, sb.lot_count),
                lot_type=sb.lot_type,
            ),
        )
        sold_tier_parts.append(
            f"{s_label}부분({sold_sq_part}주@${pure_s_unit_p:.2f})"
        )
        return sold_sq_part

    def _pop_from_main(cut_q: int) -> int:
        nonlocal removed_first_tier_completely, sold_upper_tier
        if not main_queue or cut_q <= 0:
            return 0
        idx, b = main_queue[0]
        tier_label = (
            "1층"
            if (idx == 0 and was_active_l1)
            else f"{idx + 1 if was_active_l1 else idx + 2}층"
        )
        if cut_q >= b.qty:
            taken = b.qty
            sold_buckets.append(b)
            sold_tier_parts.append(
                f"{tier_label}({b.qty}주@${b.book_price:.2f})"
            )
            main_queue.pop(0)
            if idx == 0 and was_active_l1:
                removed_first_tier_completely = True
            else:
                sold_upper_tier = True
            return taken

        sold_q_part = cut_q
        keep_q = b.qty - cut_q
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
        main_queue[0] = (
            idx,
            StratumBucket(
                qty=keep_q,
                book_price=round(keep_cost_part / float(keep_q), 4),
                book_invested_usd=keep_cost_part,
                actual_cost_usd=keep_cost_part,
                lot_count=max(1, b.lot_count),
                lot_type=b.lot_type,
            ),
        )
        sold_tier_parts.append(
            f"{tier_label}부분({sold_q_part}주@${pure_unit_p:.2f})"
        )
        if not (idx == 0 and was_active_l1):
            sold_upper_tier = True
        return sold_q_part

    # 1단계: 단독 레이어 전체 수량과 1:1 정확히 일치하는 수동 청산일 경우 해당 레이어 우선 차감
    tot_sub_q = sum(sb.qty for _, sb in sub_queue)
    tot_main_q = sum(b.qty for _, b in main_queue)

    if sub_queue and rem_to_cut == tot_sub_q and rem_to_cut != tot_main_q:
        while rem_to_cut > 0 and sub_queue:
            rem_to_cut -= _pop_from_sub(rem_to_cut)
    elif main_queue and rem_to_cut == tot_main_q and rem_to_cut != tot_sub_q:
        while rem_to_cut > 0 and main_queue:
            rem_to_cut -= _pop_from_main(rem_to_cut)

    # 2단계: 매 스텝마다 잔존 (서브 최하단층, 본그리드 최하단층) 중 단가(book_price)가 가장 낮은 층부터 순차 차감
    while rem_to_cut > 0 and (sub_queue or main_queue):
        candidates: List[Tuple[float, int, str]] = []
        if sub_queue:
            candidates.append((round(sub_queue[0][1].book_price, 4), 1, "SUB"))
        if main_queue:
            candidates.append(
                (round(main_queue[0][1].book_price, 4), 2, "MAIN")
            )
        if not candidates:
            break

        _, _, chosen_src = min(candidates, key=lambda item: (item[0], item[1]))
        if chosen_src == "SUB":
            cut_done = _pop_from_sub(rem_to_cut)
        else:
            cut_done = _pop_from_main(rem_to_cut)

        if cut_done <= 0:
            break
        rem_to_cut -= cut_done

    rem_buckets: List[StratumBucket] = [b for _, b in main_queue]
    rem_sub_buckets: List[StratumBucket] = [sb for _, sb in sub_queue]

    eff_max_t = max(2, safe_int(max_tiers, MAX_GRID_TIERS_7))
    eff_merge_mode = (
        str(merge_mode or DEFAULT_GRID_MERGE_MODE).upper().strip()
    )
    if rem_buckets:
        if was_active_l1 and not removed_first_tier_completely:
            active_b1 = rem_buckets[0]
            re_uppers = relabel_upper_grid_tiers(
                rem_buckets[1:],
                max_tiers=eff_max_t,
                merge_mode=eff_merge_mode,
            )
            rem_buckets = [active_b1] + re_uppers
        else:
            rem_buckets = relabel_upper_grid_tiers(
                rem_buckets,
                max_tiers=eff_max_t,
                merge_mode=eff_merge_mode,
            )

    eff_sub_max_t = max(2, safe_int(sub_max_tiers, SUB_MAX_TIERS_3))
    eff_sub_merge_mode = (
        str(sub_merge_mode or SUB_MERGE_MODE_L1_L3).upper().strip()
    )
    if rem_sub_buckets:
        if was_sub_active_l1 and not sold_sub_l1_completely:
            active_sb1 = rem_sub_buckets[0]
            re_sub_uppers = relabel_sub_upper_grid_tiers(
                rem_sub_buckets[1:],
                max_tiers=eff_sub_max_t,
                merge_mode=eff_sub_merge_mode,
            )
            rem_sub_buckets = [active_sb1] + re_sub_uppers
        else:
            rem_sub_buckets = relabel_sub_upper_grid_tiers(
                rem_sub_buckets,
                max_tiers=eff_sub_max_t,
                merge_mode=eff_sub_merge_mode,
            )

    sold_sub_qty_total = sum(sb.qty for sb in sold_sub_buckets)
    sold_sub_cost_total = round(
        sum(sb.actual_cost_usd for sb in sold_sub_buckets), 4
    )
    sold_qty_total = sum(b.qty for b in sold_buckets) + sold_sub_qty_total
    sold_cost_total = round(
        sum(b.actual_cost_usd for b in sold_buckets) + sold_sub_cost_total,
        4,
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
        round_trip_fee_rate_pct=round_trip_fee_rate_pct,
        actual_sell_fee_usd=actual_sell_fee_usd,
    )

    return {
        "rem_buckets": rem_buckets,
        "rem_sub_buckets": rem_sub_buckets,
        "sold_sub_qty": sold_sub_qty_total,
        "sold_sub_cost_usd": sold_sub_cost_total,
        "sold_sub_buckets": sold_sub_buckets,
        "sold_sub_l1_completely": sold_sub_l1_completely,
        "sold_sub_merged_bucket": sold_sub_merged_bucket,
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
    🚨 [Case 71, Case 72 & Case 88 상단 지층(본 2층 ~ 7층 / 서브 2층 ~ 3층) 순수 통합 이동평균법(수량 가중평균) 단가 및 목표가 산출기]:
    - 활성 1층(active_l1 == True)이 존재할 때 valid[1:] 만 슬라이싱하여 1층 매수 가격을 절대 포함하지 않고
      오직 2층 ~ 7층(서브 2층 ~ 3층)의 순수 이동평균 단가(upper_wma_price)와 +1.00% 익절 목표가(upper_wma_target_price)를 산출한다.
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
compute_sub_upper_2_to_3_moving_avg = compute_upper_2_to_12_moving_avg


def evaluate_multi_grid_sell_targets(
    buckets: Sequence[StratumBucket],
    live_price: float,
    rise_l1_pct: float = 1.50,
    rise_upper_pct: float = 1.00,
    is_overnight_session: bool = False,
    sub_buckets: Optional[Sequence[StratumBucket]] = None,
) -> Dict[str, Any]:
    """
    # MODIFIED [Case 69, Case 70, Case 71, Case 72, Case 83, Case 87, Case 88 & Case 89 (방안 C 오버나이트 통합이평 사수 & 2~7층 순수 통합이평 +1.00% 도달 시 1층 물량 무조건 동일 가격 포함 전량 매도 사이클 종료 판정기)]:
    - 2층 ~ 7층(서브 2층 ~ 3층) 이동평균 단가는 1층 매수 가격을 포함하지 않고 순수 2층 ~ 7층(서브 2층 ~ 3층) 물량만으로 산출한다.
    - 현재가(lp)가 2층 ~ 7층 순수 이동평균 단가 대비 +1.00% 익절가(wma_target_p)에 도달하면,
      1층 매수 가격과 무관하게 1층(index 0) 물량도 조건 없이 동일한 가격(wma_target_p)에 포함하여
      전 지층(0 ~ len(valid)-1)을 전량 매도(SELL_ALL_GRAD)함으로써 즉시 0주 사이클을 종료시킨다!
    """
    valid = [
        b
        for b in (buckets or [])
        if isinstance(b, StratumBucket) and b.qty > 0
    ]
    valid_sub = [
        sb
        for sb in (sub_buckets or [])
        if isinstance(sb, StratumBucket) and sb.qty > 0
    ]
    lp = safe_float(live_price, 0.0)
    if (not valid and not valid_sub) or lp <= 0.0:
        return {
            "should_sell": False,
            "sold_indices": [],
            "sub_sold_indices": [],
            "grid_sell_qty": 0,
            "sub_sell_qty": 0,
            "sell_qty": 0,
            "min_floor_price": 0.0,
            "reason_tag": "NONE",
            "hit_l1": False,
            "hit_indiv_grid": False,
            "hit_wma_grad": False,
            "hit_sub_l1": False,
            "hit_sub_indiv": False,
            "hit_sub_wma_grad": False,
            "overnight_indiv_locked": False,
        }

    sold_idx_set: Set[int] = set()
    sub_sold_idx_set: Set[int] = set()
    floor_candidates: List[float] = []
    hit_l1 = False
    hit_indiv_grid = False
    hit_wma_grad = False
    hit_sub_l1 = False
    hit_sub_indiv = False
    hit_sub_wma_grad = False
    overnight_indiv_locked = False

    # ① ~ ③ 본 그리드(valid) : 2~7층 순수 통합이평(+1.00%) 전량 졸업 최우선 판정 후 미달 시 1층(+1.50%) / 2~7층 개별층(+1.00%) 판정
    active_l1 = has_active_l1_bucket(valid)
    upper_start_idx = 1 if (active_l1 and valid) else 0
    has_upper_tiers = bool(len(valid) > upper_start_idx)

    if has_upper_tiers:
        # 1층(valid[0]) 가격을 배제한 순수 2~7층 이동평균 및 +1.00% 익절가 산출
        wma_info = compute_upper_2_to_12_moving_avg(
            valid, rise_upper_pct=rise_upper_pct
        )
        wma_target_p = safe_float(wma_info.get("upper_wma_target_price"), 0.0)

        # 2~7층 순수 이동평균 +1.00% 익절가 도달 시 1층 물량도 같은 가격(wma_target_p)에 무조건 포함하여 전량 매도(사이클 완전 종료)
        if wma_target_p > 0.0 and lp >= wma_target_p:
            for k in range(len(valid)):
                sold_idx_set.add(k)
            floor_candidates.append(wma_target_p)
            hit_wma_grad = True

    if not hit_wma_grad:
        if active_l1 and valid:
            b1 = valid[0]
            min_l1_target_p = (
                math.ceil(
                    (b1.book_price * (1.0 + rise_l1_pct / 100.0) - 1e-9)
                    * 100.0
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

        if has_upper_tiers:
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

    # ④ ~ ⑥ 서브 그리드(valid_sub) : 2~3층 순수 통합이평(+1.00%) 전량 졸업 최우선 판정 후 미달 시 서브 1층(+1.50%) / 2~3층 개별층(+1.00%) 판정 (Case 88)
    sub_active_l1 = has_active_l1_bucket(valid_sub)
    sub_upper_start_idx = 1 if (sub_active_l1 and valid_sub) else 0
    has_sub_upper_tiers = bool(len(valid_sub) > sub_upper_start_idx)

    if has_sub_upper_tiers:
        # 서브 1층(valid_sub[0]) 가격을 배제한 순수 서브 2~3층 이동평균 및 +1.00% 익절가 산출
        sub_wma_info = compute_sub_upper_2_to_3_moving_avg(
            valid_sub, rise_upper_pct=rise_upper_pct
        )
        sub_wma_target_p = safe_float(
            sub_wma_info.get("upper_wma_target_price"), 0.0
        )

        # 서브 2~3층 순수 이동평균 +1.00% 익절가 도달 시 서브 1층 물량도 같은 가격(sub_wma_target_p)에 무조건 포함하여 전량 매도
        if sub_wma_target_p > 0.0 and lp >= sub_wma_target_p:
            for sk in range(len(valid_sub)):
                sub_sold_idx_set.add(sk)
            floor_candidates.append(sub_wma_target_p)
            hit_sub_wma_grad = True

    if not hit_sub_wma_grad:
        if sub_active_l1 and valid_sub:
            sb1 = valid_sub[0]
            min_sub_l1_target_p = (
                math.ceil(
                    (sb1.book_price * (1.0 + rise_l1_pct / 100.0) - 1e-9)
                    * 100.0
                )
                / 100.0
            )
            if lp >= min_sub_l1_target_p:
                if is_overnight_session and has_sub_upper_tiers:
                    overnight_indiv_locked = True
                else:
                    sub_sold_idx_set.add(0)
                    floor_candidates.append(min_sub_l1_target_p)
                    hit_sub_l1 = True

        if has_sub_upper_tiers:
            for sk in range(sub_upper_start_idx, len(valid_sub)):
                sbk = valid_sub[sk]
                sbk_target_p = (
                    math.ceil(
                        (
                            sbk.book_price * (1.0 + rise_upper_pct / 100.0)
                            - 1e-9
                        )
                        * 100.0
                    )
                    / 100.0
                )
                if lp >= sbk_target_p:
                    if is_overnight_session:
                        overnight_indiv_locked = True
                    else:
                        sub_sold_idx_set.add(sk)
                        floor_candidates.append(sbk_target_p)
                        hit_sub_indiv = True

    if not sold_idx_set and not sub_sold_idx_set:
        return {
            "should_sell": False,
            "sold_indices": [],
            "sub_sold_indices": [],
            "grid_sell_qty": 0,
            "sub_sell_qty": 0,
            "sell_qty": 0,
            "min_floor_price": 0.0,
            "reason_tag": (
                "HOLD_OVERNIGHT_WMA_LOCK"
                if overnight_indiv_locked
                else "NONE"
            ),
            "hit_l1": False,
            "hit_indiv_grid": False,
            "hit_wma_grad": False,
            "hit_sub_l1": False,
            "hit_sub_indiv": False,
            "hit_sub_wma_grad": False,
            "overnight_indiv_locked": overnight_indiv_locked,
        }

    sorted_indices = sorted(sold_idx_set)
    sorted_sub_indices = sorted(sub_sold_idx_set)
    grid_sell_qty = sum(valid[idx].qty for idx in sorted_indices)
    sub_sell_qty = sum(valid_sub[s_idx].qty for s_idx in sorted_sub_indices)
    total_sell_qty = grid_sell_qty + sub_sell_qty
    min_floor_p = max(floor_candidates) if floor_candidates else round(lp, 2)

    if sorted_sub_indices and not sorted_indices:
        if len(sorted_sub_indices) == len(valid_sub):
            reason_tag = (
                "SELL_SUB_ALL_GRAD"
                if (hit_sub_wma_grad or len(valid_sub) > 1)
                else "SELL_SUB_L1_ONLY"
            )
        elif hit_sub_wma_grad:
            reason_tag = "SELL_SUB_ALL_GRAD"
        elif hit_sub_l1 and hit_sub_indiv:
            reason_tag = "SELL_SUB_L1_AND_GRID"
        elif hit_sub_indiv:
            reason_tag = "SELL_SUB_GRID_INDIV"
        else:
            reason_tag = "SELL_SUB_L1_ONLY"
    elif sorted_sub_indices and sorted_indices:
        if len(sorted_indices) == len(valid) and len(sorted_sub_indices) == len(
            valid_sub
        ):
            reason_tag = "SELL_ALL_GRAD"
        else:
            reason_tag = "SELL_MAIN_AND_SUB"
    elif len(sorted_indices) == len(valid):
        reason_tag = (
            "SELL_ALL_GRAD"
            if hit_wma_grad or len(valid) > 1
            else "SELL_L1_ONLY"
        )
    elif hit_wma_grad:
        reason_tag = "SELL_ALL_GRAD"
    elif hit_l1 and hit_indiv_grid:
        reason_tag = "SELL_L1_AND_GRID"
    elif hit_indiv_grid:
        reason_tag = "SELL_GRID_INDIV"
    else:
        reason_tag = "SELL_L1_ONLY"

    return {
        "should_sell": True,
        "sold_indices": sorted_indices,
        "sub_sold_indices": sorted_sub_indices,
        "grid_sell_qty": grid_sell_qty,
        "sub_sell_qty": sub_sell_qty,
        "sell_qty": total_sell_qty,
        "min_floor_price": round(min_floor_p, 2),
        "reason_tag": reason_tag,
        "hit_l1": hit_l1,
        "hit_indiv_grid": hit_indiv_grid,
        "hit_wma_grad": hit_wma_grad,
        "hit_sub_l1": hit_sub_l1,
        "hit_sub_indiv": hit_sub_indiv,
        "hit_sub_wma_grad": hit_sub_wma_grad,
        "overnight_indiv_locked": False,
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
    round_trip_fee_rate_pct: Optional[float] = None,
    actual_sell_fee_usd: Optional[float] = None,
) -> Dict[str, float]:
    """
    # [Case 86 : 계좌별 동적 왕복 수수료율(0.14% / 0.20%) 및 토스 실측 매도 수수료(execution.commission + tax) 연동 정산]:
    매도 체결 수량(sold_qty), 실제 체결 단가(sell_exec_price), 매도 지층들의 실제 매수 원금 합계(sold_actual_cost_usd)를
    기반으로 왕복 수수료 차감 후 세후 실현 손익을 정밀 산출한다.
    - actual_sell_fee_usd (토스 GET /api/v1/orders/{orderId} 의 execution.commission + execution.tax 실측값)가
      양수(> 0.0)로 전달되면: 매수 당시 편도 수수료(actual_cost * one_way_rate) + 실측 매도 수수료(actual_sell_fee_usd)를 합산 차감한다.
    - 미전달 시에는 계좌 고유 왕복 수수료율(eff_rt_pct : pipiosToss 0.14% / wonToss 0.20%)을 적용하여 차감한다.
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

    eff_rt_pct = resolve_effective_round_trip_fee_rate_pct(
        round_trip_fee_rate_pct
    )
    one_way_rate = (eff_rt_pct / 100.0) * 0.5

    proceeds = round(float(q_int) * exec_p, 4)
    gross_pnl = round(proceeds - actual_cost, 4)

    sell_fee_actual = (
        safe_float(actual_sell_fee_usd, 0.0)
        if actual_sell_fee_usd is not None
        else 0.0
    )
    if sell_fee_actual > 0.0:
        buy_side_fee = actual_cost * one_way_rate
        fee_usd = round(buy_side_fee + sell_fee_actual, 4)
    else:
        fee_usd = round(
            ((actual_cost + proceeds) * 0.5) * (eff_rt_pct / 100.0), 4
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
# [핵심 5] 포트폴리오 · 1~7층 골디락스 본 그리드(L2_L7_MERGE_SORT & 최고도달회차 잠금) · Default-ON 1~3층 서브 그리드(SUB_L1_L3_MERGE & 최대4회분 캡) · 복리/단리(일일 인출가능 수익 & 자체수혈 탄창) · 무제한 예비수혈 카운트 · 시드 배분 게이지(🟦🟨🟩) · 현재 사이클 단위 수익 · 전량졸업 예정자산(🎓) · Case 92 돌파 RSI<=50 필터 통합 요약기 (Case 59 ~ 92)
# ---------------------------------------------------------------------------
def _build_10block_allocation_gauge(
    main_cost: float,
    sub_cost: float,
    free_cash: float,
) -> Tuple[str, float, float, float, float]:
    """
    # [시드 배분 10칸 유니코드 블록 게이지(🟦본그리드 · 🟨서브그리드 · 🟩가용현금) 및 비중(%) 산출기]:
    보유 물량이 존재하는 영역은 최소 1칸 이상 표시되도록 보정하며 총 10칸 길이를 100% 유지한다.
    반환값: (gauge_bar_10blocks, main_pct, sub_pct, stock_pct, cash_pct)
    """
    m_val = max(0.0, safe_float(main_cost, 0.0))
    s_val = max(0.0, safe_float(sub_cost, 0.0))
    c_val = max(0.0, safe_float(free_cash, 0.0))
    tot = m_val + s_val + c_val

    if tot <= 0.0:
        return "🟩" * 10, 0.0, 0.0, 0.0, 100.0

    main_pct = round((m_val / tot) * 100.0, 1)
    sub_pct = round((s_val / tot) * 100.0, 1)
    stock_pct = round(((m_val + s_val) / tot) * 100.0, 1)
    cash_pct = round(max(0.0, 100.0 - stock_pct), 1)

    m_blk = int(round((m_val / tot) * 10.0))
    s_blk = int(round((s_val / tot) * 10.0))
    c_blk = int(round((c_val / tot) * 10.0))

    if m_val > 0.0 and m_blk == 0:
        m_blk = 1
    if s_val > 0.0 and s_blk == 0:
        s_blk = 1
    if c_val > 0.0 and c_blk == 0:
        c_blk = 1

    while (m_blk + s_blk + c_blk) > 10:
        if m_blk >= s_blk and m_blk >= c_blk and m_blk > 1:
            m_blk -= 1
        elif c_blk >= m_blk and c_blk >= s_blk and c_blk > 1:
            c_blk -= 1
        elif s_blk > 1:
            s_blk -= 1
        else:
            break

    while (m_blk + s_blk + c_blk) < 10:
        if m_val >= c_val and m_val >= s_val:
            m_blk += 1
        elif c_val >= m_val and c_val >= s_val:
            c_blk += 1
        else:
            s_blk += 1

    gauge_bar = ("🟦" * m_blk) + ("🟨" * s_blk) + ("🟩" * c_blk)
    return gauge_bar, main_pct, sub_pct, stock_pct, cash_pct


def summarize_stratum_portfolio(
    state_dict: Dict[str, Any],
    live_price: float = 0.0,
    now_est: Optional[datetime] = None,
    rsi_14: Optional[float] = None,
) -> Dict[str, Any]:
    """
    # MODIFIED [🎯 1 ~ 🎯 5 & Case 59 ~ 92 & 본/서브 최고 도달 회차 단차 잠금 · Default-ON 3층 서브 그리드 · 자산증식형(복리) ⇄ 인출형(단리 · 당일 인출가능 실현수익 & 누적 잉여현금 자체수혈 탄창) · 무제한 예비시드 수혈 횟수 카운트 · 층별 자산 비중(%) · 10칸 유니코드 배분 게이지(🟦🟨🟩) · 현재 사이클 단위 수익 · 전량졸업 예정자산(🎓) · Case 92 1층 공석 +1.00% 돌파 RSI(14) <= 50.0 필터 상태 통합 요약기]:
    """
    st = state_dict if isinstance(state_dict, dict) else {}
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    hm_now = dt_now.hour * 100 + dt_now.minute
    is_late_cutoff = bool(
        dt_now.weekday() < 5 and (NEW_CYCLE_BUY_CUTOFF_HM <= hm_now <= 1600)
    )

    eff_rsi_14: Optional[float] = (
        safe_float(rsi_14, 0.0)
        if rsi_14 is not None
        else (
            safe_float(st.get("rsi_14"), 0.0)
            if st.get("rsi_14") is not None
            else None
        )
    )
    if eff_rsi_14 is not None and eff_rsi_14 <= 0.0:
        eff_rsi_14 = None

    raw_buckets = buckets_from_dicts(st.get("buckets", []))
    buckets = enforce_true_breakeven_floor_on_buckets(raw_buckets)
    raw_sub_buckets = buckets_from_dicts(st.get("sub_buckets", []))
    sub_buckets = enforce_true_breakeven_floor_on_buckets(raw_sub_buckets)

    eff_rt_fee_pct = resolve_effective_round_trip_fee_rate_pct(state_dict=st)
    us_comm_rate = safe_float(
        st.get("us_commission_rate"),
        round((eff_rt_fee_pct / 100.0) * 0.5, 6),
    )
    if us_comm_rate <= 0.0 or us_comm_rate > 0.01:
        us_comm_rate = round((eff_rt_fee_pct / 100.0) * 0.5, 6)

    init_seed = max(
        100.0, safe_float(st.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD)
    )
    cum_realized = round(
        safe_float(st.get("cumulative_realized_net_usd"), 0.0), 4
    )
    daily_realized_net_usd = round(
        safe_float(st.get("daily_realized_net_usd"), 0.0), 4
    )
    injected_reserve_usd = round(
        max(0.0, safe_float(st.get("injected_reserve_usd"), 0.0)), 4
    )
    # MODIFIED [Case 91 : 예비시드 6회 상한 제한 제거 — 실제 수혈된 횟수만 카운트]
    used_reserve_portions_cnt = (
        0
        if injected_reserve_usd <= 0.0
        else max(1, safe_int(st.get("used_reserve_portions_cnt"), 1))
    )
    avail_reserve_portions = max(
        0, MAX_RESERVE_PORTIONS - used_reserve_portions_cnt
    )

    actual_invested_buckets = round(sum(b.actual_cost_usd for b in buckets), 4)
    book_invested_buckets = round(sum(b.book_invested_usd for b in buckets), 4)
    actual_invested_sub = round(
        sum(sb.actual_cost_usd for sb in sub_buckets), 4
    )
    book_invested_sub = round(
        sum(sb.book_invested_usd for sb in sub_buckets), 4
    )

    actual_invested = round(
        actual_invested_buckets + actual_invested_sub, 4
    )
    book_invested = round(
        book_invested_buckets + book_invested_sub, 4
    )

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
    sub_held_shares = sum(sb.qty for sb in sub_buckets)
    total_held_shares = held_shares + sub_held_shares

    held_lots = sum(max(1, b.lot_count) for b in buckets)
    held_tiers = len(buckets)

    sub_held_lots = sum(max(1, sb.lot_count) for sb in sub_buckets)
    sub_held_tiers = len(sub_buckets)

    # [Case 87 & Case 88 : 본 그리드 및 서브 그리드 사이클 최고 도달 회차(cycle_ratchet_max_lots / sub_ratchet_max_lots) 산출]
    raw_ratchet_lots = max(0, safe_int(st.get("cycle_ratchet_max_lots"), 0))
    if held_tiers > 0:
        cycle_ratchet_max_lots = max(held_lots, raw_ratchet_lots)
        eff_lots = max(1, held_lots, cycle_ratchet_max_lots)
    else:
        cycle_ratchet_max_lots = 0
        eff_lots = 1

    raw_sub_ratchet_lots = max(0, safe_int(st.get("sub_ratchet_max_lots"), 0))
    if sub_held_tiers > 0:
        sub_ratchet_max_lots = max(sub_held_lots, raw_sub_ratchet_lots)
        sub_eff_lots = max(1, sub_held_lots, sub_ratchet_max_lots)
    else:
        sub_ratchet_max_lots = 0
        sub_eff_lots = 1

    lp = safe_float(live_price, 0.0)
    if lp <= 0.0:
        if buckets:
            lp = buckets[0].actual_avg_price
        elif sub_buckets:
            lp = sub_buckets[0].actual_avg_price

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
    sub_actual_avg_p = (
        round(actual_invested_sub / float(sub_held_shares), 4)
        if sub_held_shares > 0
        else 0.0
    )
    book_avg_p = (
        round(book_invested / float(total_held_shares), 4)
        if total_held_shares > 0
        else 0.0
    )

    threshold_mode = str(st.get("threshold_mode") or "WIDE_RUNWAY").upper()
    raw_portion_mode = (
        str(st.get("portion_mode") or PORTION_MODE_COMPOUND).upper().strip()
    )
    is_simple_mode = is_simple_income_mode(raw_portion_mode)
    portion_mode = (
        PORTION_MODE_SIMPLE if is_simple_mode else PORTION_MODE_COMPOUND
    )
    portion_mode_label = (
        "💵인출형(단리)" if is_simple_mode else "📈자산증식형(복리)"
    )

    grid_merge_mode = str(
        st.get("grid_merge_mode") or DEFAULT_GRID_MERGE_MODE
    ).upper()
    sub_merge_mode = str(
        st.get("sub_merge_mode") or SUB_MERGE_MODE_L1_L3
    ).upper()
    unlock_mode = str(
        st.get("unlock_mode") or DEFAULT_UNLOCK_MODE
    ).upper()

    drop_buy_pct, rise_l1_pct, rise_l2_pct = get_golden8_prog_thresholds(
        held_lots=max(1, held_lots),
        threshold_mode=threshold_mode,
        cycle_ratchet_max_lots=cycle_ratchet_max_lots,
    )
    sub_drop_buy_pct, sub_rise_l1_pct, sub_rise_l2_pct = (
        get_golden8_prog_thresholds(
            held_lots=max(1, sub_held_lots),
            threshold_mode=threshold_mode,
            cycle_ratchet_max_lots=sub_ratchet_max_lots,
        )
    )

    active_l1 = has_active_l1_bucket(buckets)
    is_l2_only = bool(len(buckets) > 0 and not active_l1)

    upper_slice = buckets[1:] if active_l1 else buckets[:]
    merged_upper_tiers_cnt = sum(
        1 for b in upper_slice if max(1, b.lot_count) > 1
    )

    has_pending_buy = bool(str(st.get("buy_order_id") or "").strip())
    pending_lot_tag = str(st.get("pending_lot_type") or "").upper().strip()
    is_pending_sub_buy = pending_lot_tag.startswith("SUB_")

    raw_l1_target_q = max(0, safe_int(st.get("l1_target_quota_qty"), 0))
    if active_l1 and buckets:
        l1_cur_qty = buckets[0].qty
        l1_target_quota_qty = max(l1_cur_qty, raw_l1_target_q)
        l1_rem_quota_qty = max(0, l1_target_quota_qty - l1_cur_qty)
    else:
        l1_cur_qty = 0
        l1_target_quota_qty = (
            raw_l1_target_q
            if (has_pending_buy and not is_pending_sub_buy)
            else 0
        )
        l1_rem_quota_qty = 0

    wma_info = compute_upper_2_to_12_moving_avg(
        buckets, rise_upper_pct=rise_l2_pct
    )
    upper_tier_count = safe_int(wma_info.get("upper_tier_count"), 0)
    upper_qty = safe_int(wma_info.get("upper_qty"), 0)
    upper_lots = safe_int(wma_info.get("upper_lots"), 0)
    upper_actual_cost_usd = round(
        safe_float(wma_info.get("upper_actual_cost_usd"), 0.0), 4
    )
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
    core_equity_for_quota = max(
        init_seed, (free_cash + actual_invested) - injected_reserve_usd
    )
    budget_base_equity_usd = resolve_portion_budget_base_equity(
        initial_seed_usd=init_seed,
        core_equity_usd=core_equity_for_quota,
        portion_mode=portion_mode,
    )

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
        is_late_cutoff=is_late_cutoff,
        rsi_14=eff_rsi_14,
        breakout_max_rsi=REENTRY_BREAKOUT_MAX_RSI_50,
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
    reentry_rsi_14 = safe_float(
        reentry_sig.get("rsi_14"),
        eff_rsi_14 if eff_rsi_14 is not None else 50.0,
    )
    reentry_breakout_max_rsi = safe_float(
        reentry_sig.get("breakout_max_rsi"), REENTRY_BREAKOUT_MAX_RSI_50
    )
    reentry_breakout_rsi_blocked = bool(
        reentry_sig.get("breakout_rsi_blocked", False)
    )

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
        realized_equity_usd=budget_base_equity_usd,
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

    # NEW [Case 91 : 💵 인출형(단리) 및 자체수혈 보유 탄창 지표 산출]
    daily_withdrawable_profit_usd = round(
        max(0.0, daily_realized_net_usd), 4
    )
    withdrawable_surplus_usd = round(
        max(0.0, free_cash - init_seed - injected_reserve_usd), 4
    )
    self_reserve_portions = (
        round(withdrawable_surplus_usd / max(0.01, next_portion_budget), 1)
        if next_portion_budget > 0.0
        else 0.0
    )

    # -----------------------------------------------------------------------
    # [Case 88, Case 91 & Case 92 : 🛡️ 13_SUB_L1L3_RESV05_CAP4L — Default-ON 3층 서브 그리드 상태 및 지표 산출]
    # -----------------------------------------------------------------------
    main_consec_frozen_days = max(
        0, safe_int(st.get("main_consec_frozen_days"), 0)
    )
    sub_consec_frozen_days = max(
        0, safe_int(st.get("sub_consec_frozen_days"), 0)
    )
    sub_active_l1 = has_active_l1_bucket(sub_buckets)
    is_sub_l2_only = bool(len(sub_buckets) > 0 and not sub_active_l1)
    sub_upper_slice = sub_buckets[1:] if sub_active_l1 else sub_buckets[:]
    sub_merged_upper_tiers_cnt = sum(
        1 for sb in sub_upper_slice if max(1, sb.lot_count) > 1
    )
    sub_max_total_lots = max(
        1, safe_int(st.get("sub_max_total_lots"), SUB_MAX_TOTAL_LOTS_4)
    )
    sub_cap_reached = bool(sub_held_lots >= sub_max_total_lots)
    is_sub_grid_triggered = bool(
        len(buckets) > 0
        and (
            main_consec_frozen_days >= SUB_FROZEN_DAYS_TRIGGER
            or len(sub_buckets) > 0
        )
    )

    raw_sub_l1_target_q = max(
        0, safe_int(st.get("sub_l1_target_quota_qty"), 0)
    )
    if sub_active_l1 and sub_buckets:
        sub_l1_cur_qty = sub_buckets[0].qty
        sub_l1_target_quota_qty = max(sub_l1_cur_qty, raw_sub_l1_target_q)
        sub_l1_rem_quota_qty = max(0, sub_l1_target_quota_qty - sub_l1_cur_qty)
    else:
        sub_l1_cur_qty = 0
        sub_l1_target_quota_qty = (
            raw_sub_l1_target_q
            if (has_pending_buy and is_pending_sub_buy)
            else 0
        )
        sub_l1_rem_quota_qty = 0

    sub_wma_info = compute_sub_upper_2_to_3_moving_avg(
        sub_buckets, rise_upper_pct=sub_rise_l2_pct
    )
    sub_upper_tier_count = safe_int(sub_wma_info.get("upper_tier_count"), 0)
    sub_upper_qty = safe_int(sub_wma_info.get("upper_qty"), 0)
    sub_upper_lots = safe_int(sub_wma_info.get("upper_lots"), 0)
    sub_upper_actual_cost_usd = round(
        safe_float(sub_wma_info.get("upper_actual_cost_usd"), 0.0), 4
    )
    sub_upper_wma_price = safe_float(sub_wma_info.get("upper_wma_price"), 0.0)
    sub_upper_wma_target_price = safe_float(
        sub_wma_info.get("upper_wma_target_price"), 0.0
    )
    sub_min_indiv_upper_price = safe_float(
        sub_wma_info.get("min_indiv_upper_price"), 0.0
    )
    sub_min_indiv_upper_target_price = safe_float(
        sub_wma_info.get("min_indiv_upper_target_price"), 0.0
    )

    sub_l1_target_price = 0.0
    sub_l1_gain_pct = 0.0
    sub_l2_gain_pct = 0.0
    if sub_active_l1 and sub_buckets:
        sb1 = sub_buckets[0]
        sub_l1_target_price = round(
            math.ceil(
                (sb1.book_price * (1.0 + sub_rise_l1_pct / 100.0) - 1e-9)
                * 100.0
            )
            / 100.0,
            2,
        )
        if lp > 0.0 and sb1.book_price > 0.0:
            sub_l1_gain_pct = round(
                ((lp - sb1.book_price) / sb1.book_price) * 100.0, 2
            )
    if sub_upper_wma_price > 0.0 and lp > 0.0:
        sub_l2_gain_pct = round(
            ((lp - sub_upper_wma_price) / sub_upper_wma_price) * 100.0, 2
        )

    sub_anchor_p = safe_float(st.get("sub_anchor_price"), 0.0)
    sub_cycle_min_p = safe_float(st.get("sub_cycle_min_buy_price"), 0.0)

    sub_reentry_sig = evaluate_l2_only_hybrid_reentry_signal(
        live_price=lp,
        anchor_price=sub_anchor_p,
        l2_book_price=(
            sub_min_indiv_upper_price
            if sub_min_indiv_upper_price > 0.0
            else sub_upper_wma_price
        ),
        min_upper_tier_price=sub_min_indiv_upper_price,
        is_late_new_cycle_cutoff=is_late_cutoff,
        is_late_cutoff=is_late_cutoff,
        rsi_14=eff_rsi_14,
        breakout_max_rsi=REENTRY_BREAKOUT_MAX_RSI_50,
    )
    sub_reentry_ref_anchor = safe_float(
        sub_reentry_sig.get("ref_anchor"), sub_anchor_p
    )
    sub_reentry_pullback_price = safe_float(
        sub_reentry_sig.get("pullback_target_price"), 0.0
    )
    sub_reentry_breakout_price = safe_float(
        sub_reentry_sig.get("breakout_target_price"), 0.0
    )
    sub_chg_from_reentry_anchor_pct = safe_float(
        sub_reentry_sig.get("chg_from_exit_pct"), 0.0
    )
    sub_l2_ceiling_price = safe_float(
        sub_reentry_sig.get("l2_ceiling_price"), sub_min_indiv_upper_price
    )
    sub_reentry_signal_type = str(
        sub_reentry_sig.get("signal_type") or "HOLD_WAIT_GATE"
    )
    sub_reentry_breakout_rsi_blocked = bool(
        sub_reentry_sig.get("breakout_rsi_blocked", False)
    )

    if sub_buckets:
        sub_cands = [
            p
            for p in (sub_buckets[0].book_price, sub_anchor_p, sub_cycle_min_p)
            if p > 0.0
        ]
        sub_active_buy_anchor = (
            min(sub_cands) if sub_cands else sub_buckets[0].book_price
        )
    else:
        sub_active_buy_anchor = (
            sub_anchor_p
            if sub_anchor_p > 0.0
            else (lp if lp > 0.0 else active_buy_anchor)
        )

    sub_trigger_buy_price = (
        round(sub_active_buy_anchor * (1.0 + sub_drop_buy_pct / 100.0), 2)
        if sub_active_buy_anchor > 0.0
        else 0.0
    )

    sub_dip_eval = evaluate_sub_grid_dip_signal(
        live_price=lp,
        sub_buckets=sub_buckets,
        sub_anchor_price=sub_anchor_p,
        sub_cycle_min_buy_price=sub_cycle_min_p,
        sub_drop_buy_pct=sub_drop_buy_pct,
        sub_consec_frozen_days=sub_consec_frozen_days,
        sub_max_total_lots=sub_max_total_lots,
    )
    sub_unlock_eligible = bool(sub_dip_eval.get("sub_unlock_eligible", False))
    sub_stepped_min_price = safe_float(
        sub_dip_eval.get("sub_stepped_min_price"), 0.0
    )
    sub_stepped_trigger_price = safe_float(
        sub_dip_eval.get("sub_stepped_trigger_price"), 0.0
    )
    sub_trigger_tag = str(sub_dip_eval.get("trigger_tag") or "HOLD_SUB_GATE")

    if is_sub_l2_only:
        sub_ref_buy_anchor = (
            sub_reentry_ref_anchor
            if sub_reentry_ref_anchor > 0.0
            else sub_active_buy_anchor
        )
        sub_chg_from_buy_anchor_pct = sub_chg_from_reentry_anchor_pct
    else:
        sub_ref_buy_anchor = sub_active_buy_anchor
        sub_chg_from_buy_anchor_pct = (
            round(
                ((lp - sub_active_buy_anchor) / sub_active_buy_anchor) * 100.0,
                2,
            )
            if (lp > 0.0 and sub_active_buy_anchor > 0.0)
            else 0.0
        )

    if len(sub_buckets) == 0:
        sub_ref_for_quota = (
            sub_anchor_p
            if sub_anchor_p > 0.0
            else (lp if lp > 0.0 else active_buy_anchor)
        )
    elif is_sub_l2_only:
        sub_ref_for_quota = (
            sub_reentry_ref_anchor
            if sub_reentry_ref_anchor > 0.0
            else (lp if lp > 0.0 else sub_active_buy_anchor)
        )
    elif (
        bool(sub_dip_eval.get("is_sub_unlock")) and sub_stepped_min_price > 0.0
    ):
        sub_ref_for_quota = sub_stepped_min_price
    else:
        sub_ref_for_quota = sub_active_buy_anchor

    sub_anchor_quota_qty, sub_next_portion_budget = compute_sub4_quota_qty(
        sub_anchor_price=max(0.01, sub_ref_for_quota),
        current_core_equity=core_equity_for_quota,
        initial_seed_usd=init_seed,
        exec_price=None,
        portion_mode=portion_mode,
    )
    sub_eff_exec_for_cap = lp if lp > 0.0 else max(0.01, sub_ref_for_quota)
    sub_budget_cap_qty = max(
        1,
        int(
            math.floor(
                (sub_next_portion_budget + 1e-9) / sub_eff_exec_for_cap
            )
        ),
    )
    sub_next_target_qty = min(sub_budget_cap_qty, sub_anchor_quota_qty)

    idle_cash_info = compute_sub_grid_available_idle_cash(
        free_cash_usd=free_cash,
        core_equity_usd=core_equity_for_quota,
        broker_buying_power_usd=None,
        reserve_main_portions=SUB_RESERVE_MAIN_PORTIONS,
        initial_seed_usd=init_seed,
        portion_mode=portion_mode,
    )
    reserved_for_main_usd = safe_float(
        idle_cash_info.get("reserved_for_main_usd"), 0.0
    )
    avail_idle_cash_usd = safe_float(
        idle_cash_info.get("avail_idle_cash_usd"), 0.0
    )

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
        round_trip_fee_rate_pct=eff_rt_fee_pct,
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
    total_mark_equity_usd = round(
        max(0.0, gross_mark_equity_usd - injected_reserve_usd), 4
    )
    total_net_pnl_usd = round(cum_realized + unrealized_pnl_usd, 4)
    total_roi_pct = round((total_net_pnl_usd / init_seed) * 100.0, 2)

    # [시드 배분 10칸 유니코드 블록 게이지(🟦🟨🟩) 및 비중(%) 산출]
    (
        allocation_gauge_bar,
        main_alloc_pct,
        sub_alloc_pct,
        stock_alloc_pct,
        cash_alloc_pct,
    ) = _build_10block_allocation_gauge(
        main_cost=actual_invested_buckets,
        sub_cost=actual_invested_sub,
        free_cash=free_cash,
    )

    # [🎓 전량 졸업 시 확정 예정 총자산(projected_graduation_equity_usd) 산출]
    proj_main_l1_net = 0.0
    if active_l1 and buckets and l1_target_price > 0.0:
        proj_main_l1_net = calc_sell_realized_pnl(
            sold_qty=buckets[0].qty,
            sell_exec_price=l1_target_price,
            sold_actual_cost_usd=buckets[0].actual_cost_usd,
            round_trip_fee_rate_pct=eff_rt_fee_pct,
        )["net_pnl_usd"]

    proj_main_upper_net = 0.0
    if upper_qty > 0 and upper_wma_target_price > 0.0:
        proj_main_upper_net = calc_sell_realized_pnl(
            sold_qty=upper_qty,
            sell_exec_price=upper_wma_target_price,
            sold_actual_cost_usd=upper_actual_cost_usd,
            round_trip_fee_rate_pct=eff_rt_fee_pct,
        )["net_pnl_usd"]

    proj_sub_l1_net = 0.0
    if sub_active_l1 and sub_buckets and sub_l1_target_price > 0.0:
        proj_sub_l1_net = calc_sell_realized_pnl(
            sold_qty=sub_buckets[0].qty,
            sell_exec_price=sub_l1_target_price,
            sold_actual_cost_usd=sub_buckets[0].actual_cost_usd,
            round_trip_fee_rate_pct=eff_rt_fee_pct,
        )["net_pnl_usd"]

    proj_sub_upper_net = 0.0
    if sub_upper_qty > 0 and sub_upper_wma_target_price > 0.0:
        proj_sub_upper_net = calc_sell_realized_pnl(
            sold_qty=sub_upper_qty,
            sell_exec_price=sub_upper_wma_target_price,
            sold_actual_cost_usd=sub_upper_actual_cost_usd,
            round_trip_fee_rate_pct=eff_rt_fee_pct,
        )["net_pnl_usd"]

    projected_graduation_pending_net_usd = round(
        proj_main_l1_net
        + proj_main_upper_net
        + proj_sub_l1_net
        + proj_sub_upper_net,
        4,
    )
    projected_graduation_equity_usd = round(
        realized_equity_usd + projected_graduation_pending_net_usd, 4
    )
    projected_graduation_net_pnl_usd = round(
        cum_realized + projected_graduation_pending_net_usd, 4
    )
    projected_graduation_roi_pct = round(
        (projected_graduation_net_pnl_usd / init_seed) * 100.0, 2
    )

    # [현재 진행 사이클 단위 수익 및 완료 사이클 통계 추출]
    cycle_realized_gross_usd = round(
        safe_float(st.get("cycle_realized_gross_usd"), 0.0), 4
    )
    cycle_realized_fee_usd = round(
        safe_float(st.get("cycle_realized_fee_usd"), 0.0), 4
    )
    cycle_realized_net_usd = round(
        safe_float(st.get("cycle_realized_net_usd"), 0.0), 4
    )
    cycle_sub_realized_net_usd = round(
        safe_float(st.get("cycle_sub_realized_net_usd"), 0.0), 4
    )
    cycle_sell_events = max(0, safe_int(st.get("cycle_sell_events"), 0))
    cycle_leftover_saved_usd = round(
        safe_float(st.get("cycle_leftover_saved_usd"), 0.0), 4
    )
    last_cycle_realized_net_usd = round(
        safe_float(st.get("last_cycle_realized_net_usd"), 0.0), 4
    )
    last_cycle_sell_events = max(
        0, safe_int(st.get("last_cycle_sell_events"), 0)
    )
    completed_main_cycles = max(
        0, safe_int(st.get("completed_main_cycles"), 0)
    )

    reanchor_cnt = safe_int(st.get("reanchor_cnt"), 0)
    cum_reanchor_drop = round(
        safe_float(st.get("cumulative_reanchor_drop_usd"), 0.0), 4
    )
    indiv_grid_sell_cnt = safe_int(st.get("indiv_grid_sell_cnt"), 0)
    wma_grad_sell_cnt = safe_int(st.get("wma_grad_sell_cnt"), 0)

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

    # 서브 그리드 통계 추출 (Case 88)
    sub_buy_events = safe_int(st.get("sub_buy_events"), 0)
    sub_buy_shares = safe_int(st.get("sub_buy_shares"), 0)
    daily_sub_buy_cnt = safe_int(st.get("daily_sub_buy_cnt"), 0)
    sub_sell_events = safe_int(st.get("sub_sell_events"), 0)
    sub_sold_shares = safe_int(st.get("sub_sold_shares"), 0)
    daily_sub_sell_cnt = safe_int(st.get("daily_sub_sell_cnt"), 0)
    sub_merge_events = safe_int(st.get("sub_merge_events"), 0)
    sub_merged_indiv_escape_cnt = safe_int(
        st.get("sub_merged_indiv_escape_cnt"), 0
    )
    sub_unlock_events = safe_int(st.get("sub_unlock_events"), 0)
    daily_sub_unlock_events = safe_int(st.get("daily_sub_unlock_events"), 0)
    sub_completed_cycles = safe_int(st.get("sub_completed_cycles"), 0)
    sub_realized_net_usd = round(
        safe_float(st.get("sub_realized_net_usd"), 0.0), 4
    )
    daily_sub_realized_net_usd = round(
        safe_float(st.get("daily_sub_realized_net_usd"), 0.0), 4
    )
    daily_main_buy_cnt = safe_int(st.get("daily_main_buy_cnt"), 0)
    daily_main_sell_cnt = safe_int(st.get("daily_main_sell_cnt"), 0)

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
        "grid_merge_mode": grid_merge_mode,
        # NEW [Case 91 : 운용 모드(복리/단리) · 당일 인출가능 실현수익 · 누적 잉여현금 · 자체수혈 탄창 요약 필드]
        "portion_mode": portion_mode,
        "is_simple_mode": is_simple_mode,
        "portion_mode_label": portion_mode_label,
        "budget_base_equity_usd": budget_base_equity_usd,
        "daily_realized_net_usd": daily_realized_net_usd,
        "daily_withdrawable_profit_usd": daily_withdrawable_profit_usd,
        "withdrawable_surplus_usd": withdrawable_surplus_usd,
        "self_reserve_portions": self_reserve_portions,
        # [Case 88 : Default-ON 3층 서브 그리드 요약 필드]
        "sub_grid_enabled": True,
        "sub_merge_mode": sub_merge_mode,
        "sub_buckets": sub_buckets,
        "has_sub_buckets": bool(len(sub_buckets) > 0),
        "has_sub_active_l1": sub_active_l1,
        "is_sub_l2_only": is_sub_l2_only,
        "sub_l1_cur_qty": sub_l1_cur_qty,
        "sub_l1_target_quota_qty": sub_l1_target_quota_qty,
        "sub_l1_rem_quota_qty": sub_l1_rem_quota_qty,
        "sub_held_shares": sub_held_shares,
        "sub_held_lots": sub_held_lots,
        "sub_ratchet_max_lots": sub_ratchet_max_lots,
        "sub_eff_lots": sub_eff_lots,
        "sub_held_tiers": sub_held_tiers,
        "sub_max_tiers": SUB_MAX_TIERS_3,
        "sub_max_total_lots": sub_max_total_lots,
        "sub_cap_reached": sub_cap_reached,
        "sub_merged_upper_tiers_cnt": sub_merged_upper_tiers_cnt,
        "sub_upper_tier_count": sub_upper_tier_count,
        "sub_upper_qty": sub_upper_qty,
        "sub_upper_lots": sub_upper_lots,
        "sub_upper_actual_cost_usd": sub_upper_actual_cost_usd,
        "sub_upper_wma_price": sub_upper_wma_price,
        "sub_upper_wma_target_price": sub_upper_wma_target_price,
        "sub_min_indiv_upper_price": sub_min_indiv_upper_price,
        "sub_min_indiv_upper_target_price": sub_min_indiv_upper_target_price,
        "sub_l1_target_price": sub_l1_target_price,
        "sub_l1_gain_pct": sub_l1_gain_pct,
        "sub_l2_gain_pct": sub_l2_gain_pct,
        "sub_drop_buy_pct": sub_drop_buy_pct,
        "sub_rise_sell_l1_pct": sub_rise_l1_pct,
        "sub_rise_sell_l2_pct": sub_rise_l2_pct,
        "sub_active_buy_anchor": round(sub_active_buy_anchor, 4),
        "sub_ref_buy_anchor": round(sub_ref_buy_anchor, 4),
        "sub_chg_from_buy_anchor_pct": sub_chg_from_buy_anchor_pct,
        "sub_cycle_min_buy_price": round(
            sub_cycle_min_p if sub_cycle_min_p > 0.0 else sub_active_buy_anchor,
            4,
        ),
        "sub_trigger_buy_price": sub_trigger_buy_price,
        "sub_unlock_eligible": sub_unlock_eligible,
        "sub_stepped_min_price": sub_stepped_min_price,
        "sub_stepped_trigger_price": sub_stepped_trigger_price,
        "sub_trigger_tag": sub_trigger_tag,
        "sub_reentry_ref_anchor": round(sub_reentry_ref_anchor, 4),
        "sub_reentry_pullback_price": sub_reentry_pullback_price,
        "sub_reentry_breakout_price": sub_reentry_breakout_price,
        "sub_chg_from_reentry_anchor_pct": sub_chg_from_reentry_anchor_pct,
        "sub_l2_ceiling_price": round(sub_l2_ceiling_price, 4),
        "sub_reentry_signal_type": sub_reentry_signal_type,
        "sub_reentry_breakout_rsi_blocked": sub_reentry_breakout_rsi_blocked,
        "sub_next_target_qty": sub_next_target_qty,
        "sub_anchor_quota_qty": sub_anchor_quota_qty,
        "sub_budget_cap_qty": sub_budget_cap_qty,
        "sub_next_portion_budget": sub_next_portion_budget,
        "reserved_for_main_usd": reserved_for_main_usd,
        "avail_idle_cash_usd": avail_idle_cash_usd,
        "main_consec_frozen_days": main_consec_frozen_days,
        "sub_consec_frozen_days": sub_consec_frozen_days,
        "sub_frozen_days_trigger": SUB_FROZEN_DAYS_TRIGGER,
        "is_sub_grid_triggered": is_sub_grid_triggered,
        "sub_buy_events": sub_buy_events,
        "sub_buy_shares": sub_buy_shares,
        "daily_sub_buy_cnt": daily_sub_buy_cnt,
        "sub_sell_events": sub_sell_events,
        "sub_sold_shares": sub_sold_shares,
        "daily_sub_sell_cnt": daily_sub_sell_cnt,
        "sub_merge_events": sub_merge_events,
        "sub_merged_indiv_escape_cnt": sub_merged_indiv_escape_cnt,
        "sub_unlock_events": sub_unlock_events,
        "daily_sub_unlock_events": daily_sub_unlock_events,
        "sub_completed_cycles": sub_completed_cycles,
        "sub_realized_net_usd": sub_realized_net_usd,
        "daily_sub_realized_net_usd": daily_sub_realized_net_usd,
        "daily_main_buy_cnt": daily_main_buy_cnt,
        "daily_main_sell_cnt": daily_main_sell_cnt,
        "us_commission_rate": us_comm_rate,
        "round_trip_fee_rate_pct": eff_rt_fee_pct,
        "has_active_l1": active_l1,
        "l1_cur_qty": l1_cur_qty,
        "l1_target_quota_qty": l1_target_quota_qty,
        "l1_rem_quota_qty": l1_rem_quota_qty,
        "held_shares": held_shares,
        "total_held_shares": total_held_shares,
        "held_lots": held_lots,
        "cycle_ratchet_max_lots": cycle_ratchet_max_lots,
        "eff_lots": eff_lots,
        "held_tiers": held_tiers,
        "merged_upper_tiers_cnt": merged_upper_tiers_cnt,
        "upper_tier_count": upper_tier_count,
        "upper_qty": upper_qty,
        "upper_lots": upper_lots,
        "upper_actual_cost_usd": upper_actual_cost_usd,
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
        "actual_invested_sub_usd": actual_invested_sub,
        "actual_invested_usd": actual_invested,
        "book_invested_usd": book_invested,
        "actual_avg_price": actual_avg_p,
        "grid_actual_avg_price": grid_actual_avg_p,
        "sub_actual_avg_price": sub_actual_avg_p,
        "book_avg_price": book_avg_p,
        "cycle_reanchor_credit_usd": 0.0,
        "market_eval_usd": market_eval_usd,
        "unrealized_pnl_usd": unrealized_pnl_usd,
        "unrealized_rate_pct": unrealized_rate_pct,
        "cumulative_realized_net_usd": cum_realized,
        "realized_equity_usd": realized_equity_usd,
        "core_equity_usd": core_equity_for_quota,
        "realized_roi_pct": realized_roi_pct,
        "gross_mark_equity_usd": gross_mark_equity_usd,
        "total_mark_equity_usd": total_mark_equity_usd,
        "mark_equity_usd": total_mark_equity_usd,
        "total_net_pnl_usd": total_net_pnl_usd,
        "total_roi_pct": total_roi_pct,
        "mark_roi_pct": total_roi_pct,
        # 시드 배분 게이지 및 비중(%) · 현재 사이클 수익 · 전량졸업 예정자산(🎓) 요약 필드
        "allocation_gauge_bar": allocation_gauge_bar,
        "main_alloc_pct": main_alloc_pct,
        "sub_alloc_pct": sub_alloc_pct,
        "stock_alloc_pct": stock_alloc_pct,
        "cash_alloc_pct": cash_alloc_pct,
        "projected_graduation_pending_net_usd": projected_graduation_pending_net_usd,
        "projected_graduation_equity_usd": projected_graduation_equity_usd,
        "projected_graduation_net_pnl_usd": projected_graduation_net_pnl_usd,
        "projected_graduation_roi_pct": projected_graduation_roi_pct,
        "cycle_realized_gross_usd": cycle_realized_gross_usd,
        "cycle_realized_fee_usd": cycle_realized_fee_usd,
        "cycle_realized_net_usd": cycle_realized_net_usd,
        "cycle_sub_realized_net_usd": cycle_sub_realized_net_usd,
        "cycle_sell_events": cycle_sell_events,
        "cycle_leftover_saved_usd": cycle_leftover_saved_usd,
        "last_cycle_realized_net_usd": last_cycle_realized_net_usd,
        "last_cycle_sell_events": last_cycle_sell_events,
        "completed_main_cycles": completed_main_cycles,
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
            cycle_min_p if cycle_min_p > 0.0 else active_buy_anchor, 4,
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
        "reentry_rsi_14": reentry_rsi_14,
        "reentry_breakout_max_rsi": reentry_breakout_max_rsi,
        "reentry_breakout_rsi_blocked": reentry_breakout_rsi_blocked,
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
# [핵심 6] TDD 사전 무결성 자동 검증 슈트 (Case 25 ~ 92 전수 검증)
# ---------------------------------------------------------------------------
def run_quant_engine_tdd() -> bool:
    """
    기동 직전 8%(본 그리드) 및 4%(서브 그리드) 황금정량 산출(복리 COMP_08PCT vs 단리 SIMPLE_08PCT 연동 · Case 91),
    Case 67 min(1회분 예산 상한 주수, 기준가 고정 정량) 이중 캡핑,
    4단 와이드 활주로(-1.0% / -2.0% / -3.5% / -5.5%) 및 사이클 최고 도달 회차(cycle_ratchet_max_lots / sub_ratchet_max_lots) 단차 잠금(Case 87, 88),
    👑 Case 87: 본 그리드 7층 초과(8회차 유입) 시 구 1층(새 2층 후보) 보존 + 구 2층 + 구 7층 가중평균 통합 후 평단 오름차순 중간층 재배치(L2_L7_MERGE_SORT),
    🛡️ Case 88: Default-ON 3층 서브 그리드(4.0% 정량 · 0.5회분 보호예수금 · 최대 4회분[16%] 상한 캡 · 3층 초과 시 구 1층+구 3층 양끝합병 SUB_L1_L3_MERGE · 10일/-10% 저가해금),
    본·서브 1층(+1.50%) / 본 2~7층·서브 2~3층 개별 및 합병층(+1.00%) / 본 2~7층·서브 2~3층 순수 통합 이동평균(+1.00% 도달 시 1층 물량 무조건 동일 가격 포함 전량 매도 사이클 종료) 다중 익절 판정(Case 71, 72, 87, 88),
    🚨 Case 83 (방안 C) 오버나이트(is_overnight_session=True) 중 상단층 보유 시 개별층 매도 잠금 및 상단 순수 통합이평(+1.00%) 도달 시 1층 포함 전량 일괄 졸업 허용,
    상단 그리드 단독 보유(1층 공석) 시 2층 단가 상한 역전 차단(HOLD_PREVENT_INVERSION · Case 73) 및
    눌림(-1.0% 무필터)/돌파(+1.0% & RSI(14) <= 50.0 필터 · Case 92) 독립 1층 재장전(Case 59, 73, 92),
    🛡️ Case 84: 정규장 마감 30분 전(is_late_new_cycle_cutoff=True, 15:30 ~ 16:00 EST) 구간에서 상단 지층 보유 중 1층 공석 시
    +1.0% 상승돌파(BREAKOUT_RELOAD)를 HOLD_LATE_SESSION_BREAKOUT_CUTOFF 로 원천 차단하고 2층 단가 이하 -1.0% 눌림목(PULLBACK_RELOAD)만 정상 승인,
    정적 기억저가 잠금 및 🔓 06_STEP2X_15PCT_C20 3중 안전문 스텝업 저가 해금(Case 60, 72, 76),
    💉 Case 77, Case 89 & Case 91: 30% 자투리 승격 방지 가드(GUARD30) · 6회 수혈 제한 해제(7회차+ 무제한 온디맨드 수혈 카운트) · 0주 졸업 자동 상환,
    🎯 Case 78 지정가 부분 체결 후 미체결 잔량(TOPUP_1FL / SUB_TOPUP_1FL) 기존 1층 무승격 원자적 합산,
    💰 Case 86 계좌별 동적 왕복 수수료율(0.14% vs 0.20%) 및 실측 수수료(actual_sell_fee_usd) 정산 검증,
    📊 시드 배분 10칸 유니코드 블록 게이지 · 현재 사이클 단위 수익(cycle_realized_net_usd) · 당일 인출가능 수익(daily_withdrawable_profit_usd) · 전량졸업 예정자산(projected_graduation_equity_usd) 검증을 전수 수행한다.
    """
    prev_rt = get_runtime_round_trip_fee_rate_pct()
    prev_one = get_runtime_us_commission_rate()
    set_runtime_round_trip_fee_rate_pct(0.14, us_commission_rate=0.0007)

    try:
        assert DEFAULT_GRID_MERGE_MODE == "L2_L7_MERGE_SORT", (
            f"TDD 실패(Case 87 기본 합병모드 위반): {DEFAULT_GRID_MERGE_MODE}"
        )
        assert (
            SUB_GRID_DEFAULT_ENABLED is True
            and SUB_MERGE_MODE_L1_L3 == "SUB_L1_L3_MERGE"
            and SUB_MAX_TIERS_3 == 3
            and SUB_MAX_TOTAL_LOTS_4 == 4
            and abs(REENTRY_BREAKOUT_MAX_RSI_50 - 50.0) < 1e-6
        ), "TDD 실패(Case 88/92 서브 그리드 및 돌파 RSI 상한 상수 위반)"

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

        mock_zero_st = {
            "buckets": [],
            "sub_buckets": [],
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
            and zero_sum["cycle_ratchet_max_lots"] == 0
            and zero_sum["sub_grid_enabled"] is True
            and zero_sum["allocation_gauge_bar"] == "🟩" * 10
            and abs(zero_sum["projected_graduation_equity_usd"] - 10000.0) < 1e-4
        ), f"TDD 실패(Case 67/87/88 0주 정량/기본모드 일치): {zero_sum}"

        # 2) 4단 와이드 활주로 단차 및 Case 87 최고 도달 회차(cycle_ratchet_max_lots) 잠금 검증
        d1, s1, s2 = get_golden8_prog_thresholds(1, "WIDE_RUNWAY", 0)
        d5, _, _ = get_golden8_prog_thresholds(5, "WIDE_RUNWAY", 0)
        d9, _, _ = get_golden8_prog_thresholds(9, "WIDE_RUNWAY", 0)
        d11, _, _ = get_golden8_prog_thresholds(11, "WIDE_RUNWAY", 0)
        d_ratchet_9, _, _ = get_golden8_prog_thresholds(3, "WIDE_RUNWAY", 9)
        d_ratchet_11, _, _ = get_golden8_prog_thresholds(2, 11)
        assert (
            d1 == -1.00
            and d5 == -2.00
            and d9 == -3.50
            and d11 == -5.50
            and d_ratchet_9 == -3.50
            and d_ratchet_11 == -5.50
            and s1 == 1.50
            and s2 == 1.00
        ), "TDD 실패(Case 87): 4단 와이드 단차 및 최고 도달 회차 잠금 불일치"

        # 3) 👑 Case 72 & Case 87: 8회차 유입 시 구 1층($94.0) 보존 + 구 2층($95.0) + 구 7층($100.0) 통합 후 중간층(5층 $97.50) 재배치 검증
        grid_q: List[StratumBucket] = []
        for step in range(8):
            p_step = round(100.0 - float(step), 2)
            tag_step = "REENTRY_1FL" if step == 0 else "DIP_1FL"
            grid_q = vrev_add_quota_lot_and_merge_2tier(
                grid_q, 10, p_step, round(10.0 * p_step, 4), tag_step
            )
            assert len(grid_q) == min(MAX_GRID_TIERS_7, step + 1), (
                f"TDD 실패(Case 72/87 그리드 층수): step={step}, len={len(grid_q)}"
            )

        assert (
            len(grid_q) == 7
            and has_active_l1_bucket(grid_q)
            and grid_q[0].book_price == 93.0
            and grid_q[1].book_price == 94.0
            and grid_q[1].lot_count == 1
            and grid_q[4].lot_type == "GRID_L5"
            and grid_q[4].lot_count == 2
            and grid_q[4].qty == 20
            and abs(grid_q[4].book_price - 97.50) < 1e-4
            and grid_q[-1].lot_type == "GRID_L7"
            and abs(grid_q[-1].book_price - 99.00) < 1e-4
        ), f"TDD 실패(Case 87 L2+L7 중간층 재배치 불일치): {[b.to_dict() for b in grid_q]}"

        # 4) 🚨 Case 71, Case 72 & Case 83(방안 C): 다중 익절 및 오버나이트 개별층 잠금 & 2~7층 순수 통합이평(+1.00%) 도달 시 1층 무조건 동시 포함 전량 매도 검증
        test_grid = [
            StratumBucket(10, 80.0, 800.0, 800.0, 1, "DIP_1FL"),
            StratumBucket(10, 81.0, 810.0, 810.0, 1, "GRID_L2"),
            StratumBucket(10, 85.0, 850.0, 850.0, 1, "GRID_L3"),
            StratumBucket(10, 90.0, 900.0, 900.0, 1, "GRID_L4"),
        ]
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

        res_ov_lock = evaluate_multi_grid_sell_targets(
            test_grid, live_price=81.90, is_overnight_session=True
        )
        assert (
            res_ov_lock["should_sell"] is False
            and res_ov_lock["overnight_indiv_locked"] is True
            and res_ov_lock["reason_tag"] == "HOLD_OVERNIGHT_WMA_LOCK"
        ), f"TDD 실패(Case 83 방안 C 오버나이트 개별층 잠금 미작동): {res_ov_lock}"

        res_ov_grad = evaluate_multi_grid_sell_targets(
            test_grid, live_price=86.25, is_overnight_session=True
        )
        assert (
            res_ov_grad["should_sell"] is True
            and res_ov_grad["sold_indices"] == [0, 1, 2, 3]
            and res_ov_grad["sell_qty"] == 40
            and abs(res_ov_grad["min_floor_price"] - 86.19) < 1e-4
            and res_ov_grad["hit_wma_grad"] is True
            and res_ov_grad["reason_tag"] == "SELL_ALL_GRAD"
        ), f"TDD 실패(Case 83 방안 C 오버나이트 통합이평 전량 졸업 미작동): {res_ov_grad}"

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

        # 1층 단가($88.00)가 2~3층 순수 이동평균($83.00 -> +1.00% 목표 $83.83)보다 높더라도
        # 2~3층 순수 이동평균 +1.00%($83.83) 도달 시 1층 물량까지 동일한 가격($83.83)에 전량 매도(SELL_ALL_GRAD) 검증
        res_ov_wma_all = evaluate_multi_grid_sell_targets(
            [
                StratumBucket(20, 88.0, 1760.0, 1760.0, 1, "DIP_1FL"),
                StratumBucket(10, 81.0, 810.0, 810.0, 1, "GRID_L2"),
                StratumBucket(10, 85.0, 850.0, 850.0, 1, "GRID_L3"),
            ],
            live_price=84.00,
            is_overnight_session=True,
        )
        assert (
            res_ov_wma_all["should_sell"] is True
            and res_ov_wma_all["sold_indices"] == [0, 1, 2]
            and res_ov_wma_all["sell_qty"] == 40
            and abs(res_ov_wma_all["min_floor_price"] - 83.83) < 1e-4
            and res_ov_wma_all["hit_wma_grad"] is True
            and res_ov_wma_all["reason_tag"] == "SELL_ALL_GRAD"
        ), f"TDD 실패(Case 83 2~7층 순수 이평 +1.00% 도달 시 1층 포함 전량졸업 SELL_ALL_GRAD 미작동): {res_ov_wma_all}"

        rem_uppers = relabel_upper_grid_tiers(test_grid[2:])
        assert len(rem_uppers) == 2 and not has_active_l1_bucket(rem_uppers), (
            "TDD 실패(Case 71/72): 1층 익절 후 1층 공석(상단 그리드만 보유) 상태 판별 오류"
        )

        # 5) 🚨 Case 73, Case 84 & Case 92: 1층 공석 상태에서 현재가 > 2층 단가($85.00) 역전 차단 · 15:30~16:00 돌파 차단 · +1.00% 돌파 시 RSI(14) <= 50.0 필터 · -1.00% 눌림목 무필터 승인 검증
        sig_inv = evaluate_l2_only_hybrid_reentry_signal(
            live_price=85.50,
            anchor_price=83.41,
            l2_book_price=85.00,
            min_upper_tier_price=85.00,
            rsi_14=42.0,
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
            rsi_14=48.5,
        )
        assert (
            sig_brk_ok["should_buy"] is True
            and sig_brk_ok["signal_type"] == "BREAKOUT_RELOAD"
            and sig_brk_ok["breakout_rsi_blocked"] is False
        ), f"TDD 실패(Case 73/92 04:07~15:29 RSI<=50 안전 돌파 승인): {sig_brk_ok}"

        sig_brk_rsi_blocked = evaluate_l2_only_hybrid_reentry_signal(
            live_price=84.30,
            anchor_price=83.41,
            l2_book_price=85.00,
            min_upper_tier_price=85.00,
            is_late_new_cycle_cutoff=False,
            rsi_14=54.2,
        )
        assert (
            sig_brk_rsi_blocked["should_buy"] is False
            and sig_brk_rsi_blocked["signal_type"]
            == "HOLD_BREAKOUT_RSI_OVER_50"
            and sig_brk_rsi_blocked["breakout_rsi_blocked"] is True
        ), f"TDD 실패(Case 92 1층공석 +1.0% 돌파 시 RSI(14)>50 과열 차단 미작동): {sig_brk_rsi_blocked}"

        sig_brk_late_blocked = evaluate_l2_only_hybrid_reentry_signal(
            live_price=84.30,
            anchor_price=83.41,
            l2_book_price=85.00,
            min_upper_tier_price=85.00,
            is_late_new_cycle_cutoff=True,
            rsi_14=42.0,
        )
        assert (
            sig_brk_late_blocked["should_buy"] is False
            and sig_brk_late_blocked["signal_type"]
            == "HOLD_LATE_SESSION_BREAKOUT_CUTOFF"
        ), f"TDD 실패(Case 84 장마감 30분전 1층공석 돌파 차단 미작동): {sig_brk_late_blocked}"

        sig_pull_ok = evaluate_l2_only_hybrid_reentry_signal(
            live_price=82.50,
            anchor_price=83.41,
            l2_book_price=85.00,
            min_upper_tier_price=85.00,
            is_late_new_cycle_cutoff=True,
            rsi_14=62.5,
        )
        assert (
            sig_pull_ok["should_buy"] is True
            and sig_pull_ok["signal_type"] == "PULLBACK_RELOAD"
            and sig_pull_ok["breakout_rsi_blocked"] is False
        ), f"TDD 실패(Case 73/84/92 눌림목 무필터 재장전 승인): {sig_pull_ok}"

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

        res_grad = evaluate_multi_grid_sell_targets(
            reloaded_grid, live_price=88.50
        )
        assert (
            res_grad["should_sell"]
            and res_grad["sold_indices"] == [0, 1, 2]
            and res_grad["sell_qty"] == 30
            and abs(res_grad["min_floor_price"] - 88.38) < 1e-4
            and res_grad["hit_wma_grad"]
        ), f"TDD 실패(Case 71/72 2~7층 이동평균 일괄졸업): {res_grad}"

        # 6) Case 60, Case 72, Case 74 & Case 87: 정적 기억 최저가($80.00) 잠금 · 최고 도달 회차(cycle_ratchet_max_lots=9) 단차 잠금 · 사이클 수익 · 졸업예정자산 요약 검증
        mock_st = {
            "buckets": buckets_to_dicts(reloaded_grid),
            "initial_seed_usd": 10000.0,
            "anchor_price": 80.50,
            "cycle_min_buy_price": 80.00,
            "cycle_ratchet_max_lots": 9,
            "cumulative_realized_net_usd": 25.0,
            "cycle_realized_net_usd": 12.50,
            "cycle_sell_events": 2,
            "completed_main_cycles": 5,
            "seed_protect_pass_cnt": 120,
            "daily_seed_protect_pass_cnt": 7,
        }
        sum_info = summarize_stratum_portfolio(mock_st, live_price=81.00)
        assert abs(sum_info["active_buy_anchor"] - 80.00) < 1e-4, (
            "TDD 실패(Case 60/72): 정적 기억 최저가 잠금 풀림"
        )
        assert (
            sum_info["held_tiers"] == 3
            and sum_info["held_lots"] == 3
            and sum_info["cycle_ratchet_max_lots"] == 9
            and sum_info["eff_lots"] == 9
            and abs(sum_info["drop_buy_pct"] - (-3.50)) < 1e-4
            and sum_info["upper_tier_count"] == 2
            and abs(sum_info["upper_wma_price"] - 87.50) < 1e-4
            and abs(sum_info["l2_ceiling_price"] - 85.00) < 1e-4
            and sum_info["seed_protect_pass_cnt"] == 7
            and abs(sum_info["cycle_realized_net_usd"] - 12.50) < 1e-4
            and sum_info["cycle_sell_events"] == 2
            and sum_info["completed_main_cycles"] == 5
            and sum_info["projected_graduation_equity_usd"]
            > sum_info["realized_equity_usd"]
            and len(sum_info["allocation_gauge_bar"]) == 10
        ), f"TDD 실패(Case 72/73/74/87): 상단 이동평균 또는 최고도달회차/졸업예정자산 요약 오류 {sum_info}"

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

        # 8) 단가 비교 층간 스마트 중간 편입 & 매도 층 원가 매칭 정산(본 그리드 + 서브 그리드 교차 저가 매칭 포함) 검증
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

        # 본 그리드 [10주@$40.0, 50주@$90.0] + 서브 그리드 [8주@$45.0] 보유 중 18주 수동 매도 시 저가인 본 1층(10주@$40) + 서브 1층(8주@$45) 우선 매칭 검증
        cross_match = match_and_remove_sold_buckets_7tier(
            buckets=[
                StratumBucket(10, 40.0, 400.0, 400.0, 1, "REENTRY_1FL"),
                StratumBucket(50, 90.0, 4500.0, 4500.0, 5, "GRID_L2"),
            ],
            sub_buckets=[
                StratumBucket(8, 45.0, 360.0, 360.0, 1, "SUB_REENTRY_1FL"),
            ],
            delta_remove_qty=18,
            sell_exec_price=48.0,
        )
        assert (
            cross_match["sold_qty"] == 18
            and cross_match["sold_sub_qty"] == 8
            and abs(cross_match["sold_actual_cost_usd"] - 760.0) < 1e-4
            and len(cross_match["rem_buckets"]) == 1
            and cross_match["rem_buckets"][0].qty == 50
            and abs(cross_match["rem_buckets"][0].book_price - 90.0) < 1e-4
            and len(cross_match["rem_sub_buckets"]) == 0
        ), f"TDD 실패(Case 88 본+서브 교차 저가 매칭 오류): {cross_match}"

        # 9) [Case 77 & Case 91 : 💉 GUARD30 및 6회 제한 없는 무제한 온디맨드 예비수혈 검증]
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

        # 이미 8회 수혈된 상태에서도 실계좌에 여유자금이 있으면 9회차 무제한 수혈 승인 검증 (Case 91)
        g30_inj_unlim = evaluate_guard30_and_reserve_injection(
            free_cash_usd=180.0,
            broker_bp_usd=1680.0,
            exec_price=29.0,
            portion_budget=1440.0,
            l1_actual_cost_usd=1426.0,
            is_dip_promotion=True,
            used_reserve_portions_cnt=8,
        )
        assert (
            g30_inj_unlim["action"] == "INJECT_AND_PROCEED"
            and g30_inj_unlim["should_proceed"] is True
            and g30_inj_unlim["inject_portions"] == 1
            and abs(g30_inj_unlim["inject_usd"] - 1440.0) < 1e-4
            and g30_inj_unlim["used_portions_after"] == 9
        ), f"TDD 실패(Case 91 무제한 9회차 예비수혈 오류): {g30_inj_unlim}"

        repay_res = compute_reserve_repayment_on_zero(
            initial_seed_usd=10000.0,
            cumulative_realized_net_usd=11418.55,
            injected_reserve_usd=13242.27,
            used_reserve_portions_cnt=9,
        )
        assert (
            repay_res["did_repay"] is True
            and abs(repay_res["repaid_usd"] - 13242.27) < 1e-4
            and repay_res["rem_injected_reserve_usd"] == 0.0
            and repay_res["rem_used_reserve_portions_cnt"] == 0
            and abs(repay_res["free_cash_after_repay_usd"] - 21418.55) < 1e-4
        ), f"TDD 실패(Case 77/91 0주 졸업 예비시드 상환 오류): {repay_res}"

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

        # 11) [Case 86 : 계좌별 동적 왕복 수수료율(0.14% vs 0.20%) 및 실측 수수료(actual_sell_fee_usd) 정산 검증]
        pnl_014 = calc_sell_realized_pnl(
            sold_qty=10,
            sell_exec_price=74.29,
            sold_actual_cost_usd=731.00,
            round_trip_fee_rate_pct=0.14,
        )
        pnl_020 = calc_sell_realized_pnl(
            sold_qty=10,
            sell_exec_price=74.29,
            sold_actual_cost_usd=731.00,
            round_trip_fee_rate_pct=0.20,
        )
        assert (
            abs(pnl_014["net_pnl_usd"] - 10.8683) < 1e-3
            and abs(pnl_020["net_pnl_usd"] - 10.4261) < 1e-3
            and pnl_014["net_pnl_usd"] > pnl_020["net_pnl_usd"]
        ), f"TDD 실패(계좌별 0.14% vs 0.20% 수수료 정산 불일치): {pnl_014} vs {pnl_020}"

        # 12) [Case 88 & Case 91 : Default-ON 3층 서브 그리드 및 자산증식형(복리) ⇄ 인출형(단리 · 당일 인출가능 수익 & 자체수혈 탄창) 검증]
        mock_simple_st = {
            "buckets": [],
            "sub_buckets": [],
            "initial_seed_usd": 10000.0,
            "portion_mode": "SIMPLE_08PCT",
            "anchor_price": 50.0,
            "cumulative_realized_net_usd": 15000.0,
            "daily_realized_net_usd": 125.50,
            "free_cash_usd": 25000.0,
        }
        simple_sum = summarize_stratum_portfolio(
            mock_simple_st, live_price=50.0
        )
        assert (
            simple_sum["is_simple_mode"] is True
            and simple_sum["portion_mode"] == "SIMPLE_08PCT"
            and abs(simple_sum["next_portion_budget"] - 800.0) < 1e-4
            and simple_sum["next_target_qty"] == 16
            and abs(simple_sum["sub_next_portion_budget"] - 400.0) < 1e-4
            and simple_sum["sub_next_target_qty"] == 8
            and abs(simple_sum["reserved_for_main_usd"] - 400.0) < 1e-4
            and abs(simple_sum["withdrawable_surplus_usd"] - 15000.0) < 1e-4
            and abs(simple_sum["self_reserve_portions"] - 18.8) < 1e-2
            and abs(simple_sum["daily_withdrawable_profit_usd"] - 125.50) < 1e-4
        ), f"TDD 실패(Case 91 인출형[단리] 정량/잉여현금/당일인출수익 오류): {simple_sum}"

        sub_q_qty, sub_q_bud = compute_sub4_quota_qty(
            sub_anchor_price=50.0,
            current_core_equity=10000.0,
            initial_seed_usd=10000.0,
            exec_price=50.0,
        )
        idle_info = compute_sub_grid_available_idle_cash(
            free_cash_usd=2400.0, core_equity_usd=10000.0
        )
        assert (
            sub_q_qty == 8
            and abs(sub_q_bud - 400.0) < 1e-4
            and abs(idle_info["reserved_for_main_usd"] - 400.0) < 1e-4
            and abs(idle_info["avail_idle_cash_usd"] - 2000.0) < 1e-4
        ), f"TDD 실패(Case 88 서브 4% 정량 및 0.5회분 보호예수금 산출 오류): {idle_info}"

        sub_q: List[StratumBucket] = []
        for s_step, s_p in enumerate((50.0, 49.0, 48.0)):
            sub_q, did_m = add_lot_to_sub_grid_with_flag(
                sub_q,
                8,
                s_p,
                round(8.0 * s_p, 4),
                "SUB_REENTRY_1FL" if s_step == 0 else "SUB_DIP_1FL",
            )
            assert did_m is False and len(sub_q) == s_step + 1

        # 3회분 보유 중 10일 무매매 & -10% 저가 해금 판정 검증
        sub_unlock_ok = evaluate_sub_grid_dip_signal(
            live_price=43.00,
            sub_buckets=sub_q,
            sub_anchor_price=48.0,
            sub_cycle_min_buy_price=20.0,
            sub_drop_buy_pct=-1.00,
            sub_consec_frozen_days=10,
            sub_max_total_lots=4,
        )
        assert (
            sub_unlock_ok["should_buy"] is True
            and sub_unlock_ok["is_sub_unlock"] is True
            and sub_unlock_ok["trigger_tag"] == "SUB_UNLOCK_10D_D10"
        ), f"TDD 실패(Case 88 서브 10일/-10% 저가해금 미작동): {sub_unlock_ok}"

        # 4회분 유입 시 구 1층($48.0) + 구 3층($50.0) 양끝 합병(SUB_L1_L3_MERGE -> 16주@$49.00, 2회분) 검증
        sub_q, did_m4 = add_lot_to_sub_grid_with_flag(
            sub_q, 8, 47.0, round(8.0 * 47.0, 4), "SUB_DIP_1FL"
        )
        sub_tot_lots = sum(sb.lot_count for sb in sub_q)
        assert (
            did_m4 is True
            and len(sub_q) == 3
            and sub_tot_lots == 4
            and abs(sub_q[0].book_price - 47.0) < 1e-4
            and abs(sub_q[1].book_price - 49.0) < 1e-4
            and abs(sub_q[2].book_price - 49.0) < 1e-4
            and max(sub_q[1].lot_count, sub_q[2].lot_count) == 2
        ), f"TDD 실패(Case 88 SUB_L1_L3_MERGE 양끝합병 불일치): {[sb.to_dict() for sb in sub_q]}"

        # 누적 4회분 도달 시 추가 서브 매수 차단(HOLD_SUB_CAP_4_LOTS_REACHED) 검증
        sub_cap_blk = evaluate_sub_grid_dip_signal(
            live_price=40.0,
            sub_buckets=sub_q,
            sub_anchor_price=47.0,
            sub_cycle_min_buy_price=47.0,
            sub_drop_buy_pct=-1.00,
            sub_consec_frozen_days=15,
            sub_max_total_lots=4,
        )
        assert (
            sub_cap_blk["should_buy"] is False
            and sub_cap_blk["trigger_tag"] == "HOLD_SUB_CAP_4_LOTS_REACHED"
        ), f"TDD 실패(Case 88 최대 4회분 상한 캡 차단 미작동): {sub_cap_blk}"

        # 서브 그리드 통합이평(+1.00%) 일괄 졸업 판정 검증
        res_sub_grad = evaluate_multi_grid_sell_targets(
            buckets=[StratumBucket(10, 95.0, 950.0, 950.0, 1, "REENTRY_1FL")],
            live_price=49.55,
            sub_buckets=sub_q,
            is_overnight_session=True,
        )
        assert (
            res_sub_grad["should_sell"] is True
            and res_sub_grad["sold_indices"] == []
            and res_sub_grad["sub_sold_indices"] == [0, 1, 2]
            and res_sub_grad["sub_sell_qty"] == 32
            and abs(res_sub_grad["min_floor_price"] - 49.49) < 1e-4
            and res_sub_grad["reason_tag"] == "SELL_SUB_ALL_GRAD"
        ), f"TDD 실패(Case 88 서브 그리드 통합이평 전량 졸업 판정 오류): {res_sub_grad}"
    finally:
        set_runtime_round_trip_fee_rate_pct(prev_rt, us_commission_rate=prev_one)

    logger.info(
        "✅ [QuantEngine TDD 사전 무결성 검증 통과] 챔피언 👑 06_L2L7_RATCHET_8PCT × 🛡️ 13_SUB_L1L3_RESV05_CAP4L(Default ON) × 💉 무제한 예비수혈 × 🔓 06_STEP2X_15PCT_C20 × 🔹 BRK_RSI50 × 💵 인출형(단리)/자산증식형(복리) & Case 84 ~ 92 전수 검증 완료"
    )
    return True
