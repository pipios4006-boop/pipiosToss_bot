# -*- coding: utf-8 -*-
"""
# MODIFIED: quant_engine_core.py (Part 1/2 — 황금시간 07:00~07:50 RSI<=19 올인 전면 영구 소각 &
# Case 91 무제한 예비수혈 카운트 · 복리[COMP_08PCT] ➔ 단리[SIMPLE_08PCT] ➔ 바벨모드[BARBELL_60_30_10 · SOXL 60% 코어 예산 산출] 확장 &
# Case 92 1층 공석 +1.00% 상승돌파 시 RSI(14) <= 50.0 필터 탑재)
인피니트 스노우볼 (Infinite Snowball) v3.0 — 퀀트 엔진 코어 Part 1 / 2
역할:
1) 전역 퀀트 상수 락온 (본 그리드 8% 황금비율 · 7-Layer 골디락스 그리드 · DEFAULT_GRID_MERGE_MODE = "L2_L7_MERGE_SORT" [Case 87] ·
   🛡️ 스위치 없는 100% 기본 상시 적용[Default ON] 3-Layer 서브 그리드 4% 정량 · 0.5회분 보호예수 · 최대 4회분[16%] 상한 캡 · SUB_L1_L3_MERGE [Case 88] ·
   📈 자산증식형[복리 · COMP_08PCT] ➔ 💵 인출형[단리 · SIMPLE_08PCT] ➔ ⚖️ 바벨모드[BARBELL_60_30_10 · SOXL 60% 코어] 3단 운용 모드 [Case 91] ·
   STEP2X_15PCT_C20 · GUARD30 무제한 예비수혈[Case 89, Case 91] ·
   Case 84 15:30 0주 신규진입 및 1층 공석 돌파추격 차단 ·
   Case 92 1층 공석 +1.00% 상승돌파 시 1분봉 Wilder RSI(14) <= 50.0 필터 REENTRY_BREAKOUT_MAX_RSI_50 = 50.0)
2) 계좌별 미국 주식 매매 수수료율 런타임 동적 동기화 브릿지 탑재 (Case 86)
3) 순수 실물 매수 원가(book_price == actual_avg_price) 구조체 (StratumBucket) ·
   본 그리드 상단(L2_L7_MERGE_SORT · Case 87) 및 서브 그리드 상단(SUB_L1_L3_MERGE · Case 88) 번호 정규화·합병기
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import toss_api
from toss_api import safe_float, safe_int

logger = logging.getLogger("toss_sniper.quant_engine_core")

DEFAULT_INITIAL_SEED_USD: float = float(
    getattr(toss_api, "DEFAULT_INITIAL_SEED_USD", 10000.0)
)
PORTION_RATIO_LOCKED: float = float(
    getattr(toss_api, "PORTION_RATIO_LOCKED", 0.08)
)
REANCHOR_NET_BUFFER_MULT: float = float(
    getattr(toss_api, "REANCHOR_NET_BUFFER_MULT", 0.994)
)
DEFAULT_US_COMMISSION_RATE: float = float(
    getattr(toss_api, "DEFAULT_US_COMMISSION_RATE", 0.0007)
)
ROUND_TRIP_FEE_RATE_PCT: float = float(
    getattr(toss_api, "ROUND_TRIP_FEE_RATE_PCT", 0.14)
)

# MODIFIED [Case 91 + 바벨 확장 : 📈 복리(COMP_08PCT) ➔ 💵 단리(SIMPLE_08PCT) ➔ ⚖️ 바벨(BARBELL_60_30_10) 상수]
PORTION_MODE_COMPOUND: str = "COMP_08PCT"
PORTION_MODE_SIMPLE: str = "SIMPLE_08PCT"
PORTION_MODE_BARBELL: str = "BARBELL_60_30_10"

BARBELL_SOXL_WEIGHT: float = float(
    getattr(toss_api, "BARBELL_SOXL_WEIGHT", 0.60)
)
BARBELL_SGOV_WEIGHT: float = float(
    getattr(toss_api, "BARBELL_SGOV_WEIGHT", 0.30)
)
BARBELL_CASH_WEIGHT: float = float(
    getattr(toss_api, "BARBELL_CASH_WEIGHT", 0.10)
)

VALID_PORTION_MODES: Tuple[str, ...] = (
    "COMP_08PCT",
    "SIMPLE_08PCT",
    "BARBELL_60_30_10",
    "FIXED_800",
)

# 8%(12.5분할) 황금비율 기준 기본 분할 회차 및 1~7층 골디락스 멀티 그리드 최대 층수 상수 (Case 72 & Case 87)
BASE_MAX_LOTS_8PCT: int = 12
MAX_GRID_TIERS_7: int = int(getattr(toss_api, "MAX_GRID_TIERS_7", 7))
MAX_GRID_TIERS: int = MAX_GRID_TIERS_7
MAX_GRID_TIERS_12: int = MAX_GRID_TIERS_7

# [Case 87 : 👑 06_L2L7_RATCHET_8PCT — 7층 초과(8층 발생) 시 구 1층 보존 + 구 2층 + 구 7층 통합 후 평단 오름차순 중간층 재배치 모드]
DEFAULT_GRID_MERGE_MODE: str = str(
    getattr(toss_api, "DEFAULT_GRID_MERGE_MODE", "L2_L7_MERGE_SORT")
)

# [Case 88 : 🛡️ 13_SUB_L1L3_RESV05_CAP4L — 스위치 없는 100% 기본 상시 적용(Default ON) 3층 서브 그리드 상수 락온]
SUB_GRID_DEFAULT_ENABLED: bool = bool(
    getattr(toss_api, "SUB_GRID_DEFAULT_ENABLED", True)
)
SUB_FROZEN_DAYS_TRIGGER: int = int(
    getattr(toss_api, "SUB_FROZEN_DAYS_TRIGGER", 5)
)
SUB_PORTION_RATIO_4PCT: float = float(
    getattr(toss_api, "SUB_PORTION_RATIO_4PCT", 0.04)
)
SUB_MAX_TIERS_3: int = int(getattr(toss_api, "SUB_MAX_TIERS_3", 3))
SUB_MAX_TIERS: int = SUB_MAX_TIERS_3
SUB_MAX_TOTAL_LOTS_4: int = int(
    getattr(toss_api, "SUB_MAX_TOTAL_LOTS_4", 4)
)
SUB_MAX_TOTAL_LOTS: int = SUB_MAX_TOTAL_LOTS_4
SUB_RESERVE_MAIN_PORTIONS: float = float(
    getattr(toss_api, "SUB_RESERVE_MAIN_PORTIONS", 0.5)
)
SUB_MERGE_MODE_L1_L3: str = str(
    getattr(toss_api, "SUB_MERGE_MODE_L1_L3", "SUB_L1_L3_MERGE")
)
DEFAULT_SUB_MERGE_MODE: str = SUB_MERGE_MODE_L1_L3
SUB_UNLOCK_FROZEN_DAYS_10: int = int(
    getattr(toss_api, "SUB_UNLOCK_FROZEN_DAYS_10", 10)
)
SUB_UNLOCK_DROP_FROM_L1_PCT: float = float(
    getattr(toss_api, "SUB_UNLOCK_DROP_FROM_L1_PCT", 10.0)
)

# 🎯 4 & Case 59, Case 71, Case 72, Case 73, Case 84, Case 88, Case 92: 상단 그리드 보유 중 1층 공석 시 60초 주기 눌림목/상승돌파 임계치(%) 및 돌파 RSI 상한(50.0)
REENTRY_PULLBACK_DROP_PCT: float = -1.00
REENTRY_BREAKOUT_RISE_PCT: float = 1.00
REENTRY_BREAKOUT_MAX_RSI_50: float = float(
    getattr(toss_api, "REENTRY_BREAKOUT_MAX_RSI_50", 50.0)
)

# NEW [Case 99 : 🛡️ 스나이퍼 1층 스텝 락온 트레일링(1.00% ➔ 1.45%시 1.25% 하드보존) + 완결 1분봉 HA 음봉 + <1% 용서·망각 상수]
SNIPER_L1_TRAIL_ENABLED: bool = True
SNIPER_L1_TRAIL_IGNITE_PCT: float = 1.00
SNIPER_L1_TRAIL_STEP_TRIG_PCT: float = 1.45
SNIPER_L1_TRAIL_STEP_LOCK_PCT: float = 1.25
SNIPER_L1_TRAIL_SAFE_CAP_PCT: float = 5.00
SNIPER_L1_TRAIL_BOOST_TIER2_PCT: float = 2.00
SNIPER_L1_TRAIL_CB_TIGHT_PCT: float = 0.20
SNIPER_L1_TRAIL_CB_WIDE_PCT: float = 0.30
SNIPER_L1_TRAIL_QQQ_BYPASS_PCT: float = 0.20

# [Case 84 & Case 88]: 정규장 마감 30분 전(15:30 ~ 16:00 EST) 본·서브 0주 새 사이클 첫 1층 진입 및 1층 공석 +1.0% 돌파 추격 동시 차단 기준 시각(HHMM)
NEW_CYCLE_BUY_CUTOFF_HM: int = int(
    getattr(toss_api, "NEW_CYCLE_BUY_CUTOFF_HM", 1530)
)

# Case 76: 🔓 06_STEP2X_15PCT_C20 3중 안전문 기반 조건부 스텝업 저가 해금 상수
DEFAULT_UNLOCK_MODE: str = str(
    getattr(toss_api, "DEFAULT_UNLOCK_MODE", "STEP2X_15PCT_C20")
)
STEP_UP_2X_MIN_REBOUND_MULT: float = float(
    getattr(toss_api, "STEP_UP_2X_MIN_REBOUND_MULT", 2.0)
)
STEP_UP_2X_MAX_TIERS: int = int(
    getattr(toss_api, "STEP_UP_2X_MAX_TIERS", 2)
)
STEP_UP_2X_MIN_CASH_RATIO: float = float(
    getattr(toss_api, "STEP_UP_2X_MIN_CASH_RATIO", 0.20)
)
STEP_UP_2X_DROP_PCT: float = float(
    getattr(toss_api, "STEP_UP_2X_DROP_PCT", 15.0)
)

# MODIFIED [Case 77 & Case 91 : 30% 자투리 승격 방지 가드(GUARD30) & 횟수 제한 없는 무제한 온디맨드 예비시드 자동 수혈 상수]
MAX_RESERVE_PORTIONS: int = int(
    getattr(toss_api, "MAX_RESERVE_PORTIONS", 999999)
)
MIN_DIP_BUDGET_RATIO: float = float(
    getattr(toss_api, "MIN_DIP_BUDGET_RATIO", 0.30)
)
MIN_DIP_VS_L1_RATIO: float = float(
    getattr(toss_api, "MIN_DIP_VS_L1_RATIO", 0.30)
)
RESERVE_DEPOSIT_TOLERANCE_RATIO: float = float(
    getattr(toss_api, "RESERVE_DEPOSIT_TOLERANCE_RATIO", 0.95)
)


# ---------------------------------------------------------------------------
# [핵심 0 · Case 86, Case 91 & 바벨 확장] 계좌별 미국 주식 수수료율 브릿지 및 3단 운용 모드(복리/단리/바벨) 예산 기준자산 리졸버
# ---------------------------------------------------------------------------
def is_barbell_mode(portion_mode: Any) -> bool:
    """
    # NEW:
    현재 운용 모드가 ⚖️ 바벨 모드(BARBELL_60_30_10 · SOXL 60% / SGOV 30% / 현금 10%)인지 판별한다.
    """
    return str(portion_mode or "").upper().strip() in (
        "BARBELL_60_30_10",
        "BARBELL",
        "BARBELL_04PCT",
    )


def is_simple_income_mode(portion_mode: Any) -> bool:
    """
    # [Case 91]:
    현재 운용 모드가 💵 인출형(단리 · 설정 기준시드의 8% / 서브 4% 고정 · 채굴 수익 현금 적립 및 일일 인출)인지 판별한다.
    """
    return str(portion_mode or PORTION_MODE_COMPOUND).upper().strip() in (
        "SIMPLE_08PCT",
        "FIXED_800",
        "SIMPLE",
        "INCOME",
    )


def next_cycled_portion_mode(cur_mode: Any) -> str:
    """
    # NEW:
    운용 정량모드 3단 순환기:
    COMP_08PCT(복리) ➔ SIMPLE_08PCT(단리) ➔ BARBELL_60_30_10(바벨) ➔ COMP_08PCT(복리)
    """
    if is_barbell_mode(cur_mode):
        return PORTION_MODE_COMPOUND
    if is_simple_income_mode(cur_mode):
        return PORTION_MODE_BARBELL
    return PORTION_MODE_SIMPLE


def resolve_portion_budget_base_equity(
    initial_seed_usd: float,
    core_equity_usd: float,
    portion_mode: str = PORTION_MODE_COMPOUND,
) -> float:
    """
    # MODIFIED [Case 91 + 바벨 모드 확장]:
    - ⚖️ 바벨 모드(BARBELL_60_30_10)일 때는 설정 기준 시드(initial_seed_usd)의 60%(BARBELL_SOXL_WEIGHT)를
      SOXL 코어 기준자산으로 고정 반환하여 본 1회분(8% = 전체의 4.8%) / 서브 1회분(4% = 전체의 2.4%) / 보호예수(4%)를 산출한다.
    - 💵 인출형(단리 · SIMPLE_08PCT / FIXED_800) 모드일 때는 설정 기준 시드(initial_seed_usd)를 반환한다.
    - 📈 자산증식형(복리 · COMP_08PCT) 모드일 때는 순수 코어 총자산(core_equity_usd)을 반환하여 1회분 예산을 복리 증액한다.
    """
    init_s = max(
        100.0, safe_float(initial_seed_usd, DEFAULT_INITIAL_SEED_USD)
    )
    core_eq = max(init_s, safe_float(core_equity_usd, init_s))
    if is_barbell_mode(portion_mode):
        return round(init_s * BARBELL_SOXL_WEIGHT, 4)
    if is_simple_income_mode(portion_mode):
        return round(init_s, 4)
    return round(core_eq, 4)


def get_runtime_us_commission_rate() -> float:
    fn = getattr(toss_api, "get_runtime_us_commission_rate", None)
    if callable(fn):
        return safe_float(fn(), DEFAULT_US_COMMISSION_RATE)
    return DEFAULT_US_COMMISSION_RATE


def get_runtime_round_trip_fee_rate_pct() -> float:
    fn = getattr(toss_api, "get_runtime_round_trip_fee_rate_pct", None)
    if callable(fn):
        val = safe_float(fn(), ROUND_TRIP_FEE_RATE_PCT)
        if 0.0 < val <= 2.0:
            return val
    return ROUND_TRIP_FEE_RATE_PCT


def set_runtime_round_trip_fee_rate_pct(
    round_trip_pct: float,
    us_commission_rate: Optional[float] = None,
) -> float:
    fn = getattr(toss_api, "set_runtime_round_trip_fee_rate_pct", None)
    if callable(fn):
        return safe_float(
            fn(round_trip_pct, us_commission_rate=us_commission_rate),
            ROUND_TRIP_FEE_RATE_PCT,
        )
    return ROUND_TRIP_FEE_RATE_PCT


def resolve_effective_round_trip_fee_rate_pct(
    explicit_rate_pct: Optional[float] = None,
    state_dict: Optional[Dict[str, Any]] = None,
) -> float:
    if explicit_rate_pct is not None:
        v = safe_float(explicit_rate_pct, 0.0)
        if 0.0 < v <= 2.0:
            return round(v, 4)
    if isinstance(state_dict, dict):
        st_rt = safe_float(state_dict.get("round_trip_fee_rate_pct"), 0.0)
        if 0.0 < st_rt <= 2.0:
            return round(st_rt, 4)
        st_one = safe_float(state_dict.get("us_commission_rate"), 0.0)
        if 0.0 < st_one <= 0.01:
            return round(st_one * 200.0, 4)
    return get_runtime_round_trip_fee_rate_pct()


# ---------------------------------------------------------------------------
# [핵심 1] StratumBucket : 순수 실물 매수 원가(book_price == actual_avg_price) 구조체 (Case 46 ~ 88)
# ---------------------------------------------------------------------------
@dataclass
class StratumBucket:
    qty: int
    book_price: float
    book_invested_usd: float
    actual_cost_usd: float
    lot_count: int = 1
    lot_type: str = "QUOTA_L1"

    @property
    def actual_avg_price(self) -> float:
        if self.qty <= 0:
            return 0.0
        return round(self.actual_cost_usd / float(self.qty), 4)

    def to_dict(self) -> Dict[str, Any]:
        q_int = max(1, safe_int(self.qty, 1))
        a_cost = round(
            max(
                0.01 * float(q_int),
                safe_float(
                    self.actual_cost_usd,
                    safe_float(
                        self.book_invested_usd,
                        float(q_int) * safe_float(self.book_price, 0.01),
                    ),
                ),
            ),
            4,
        )
        pure_p = round(max(0.0001, a_cost / float(q_int)), 4)
        l_cnt = max(1, safe_int(self.lot_count, 1))
        return {
            "qty": q_int,
            "book_price": pure_p,
            "book_invested_usd": a_cost,
            "actual_cost_usd": a_cost,
            "lot_count": l_cnt,
            "lot_type": str(self.lot_type or "QUOTA_L1").upper().strip(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional["StratumBucket"]:
        if not isinstance(data, dict):
            return None
        q_int = safe_int(data.get("qty"), 0)
        if q_int <= 0:
            return None
        raw_p = safe_float(
            data.get("book_price"), safe_float(data.get("buy_price"), 0.0)
        )
        raw_bi = safe_float(
            data.get("book_invested_usd"), float(q_int) * max(0.0, raw_p)
        )
        a_cost = safe_float(data.get("actual_cost_usd"), raw_bi)
        if a_cost <= 0.0 and raw_p > 0.0:
            a_cost = float(q_int) * raw_p
        if a_cost <= 0.0:
            return None
        clean_cost = round(a_cost, 4)
        pure_p = round(clean_cost / float(q_int), 4)
        l_cnt = max(1, safe_int(data.get("lot_count"), 1))
        l_type = str(data.get("lot_type") or "QUOTA_L1").upper().strip()
        return cls(
            qty=q_int,
            book_price=pure_p,
            book_invested_usd=clean_cost,
            actual_cost_usd=clean_cost,
            lot_count=l_cnt,
            lot_type=l_type,
        )


def buckets_from_dicts(
    raw_list: Sequence[Dict[str, Any]],
) -> List[StratumBucket]:
    out: List[StratumBucket] = []
    if not isinstance(raw_list, (list, tuple)):
        return out
    for item in raw_list:
        b_obj = StratumBucket.from_dict(item)
        if b_obj is not None:
            out.append(b_obj)
    return out


def buckets_to_dicts(
    buckets: Sequence[StratumBucket],
) -> List[Dict[str, Any]]:
    return [
        b.to_dict()
        for b in (buckets or [])
        if isinstance(b, StratumBucket) and b.qty > 0
    ]


# ---------------------------------------------------------------------------
# [핵심 1-B · Case 69, Case 71, Case 72, Case 87 & Case 88] 그리드 층 판별기 · 본 그리드 구 2층+구 7층 통합 중간배치기 · 서브 그리드 구 1층+구 3층 양끝 합병기 & 진성 손익분기점 하한선 정규화기
# ---------------------------------------------------------------------------
def is_upper_grid_tier(bucket_or_lot_type: Any) -> bool:
    if isinstance(bucket_or_lot_type, StratumBucket):
        tag = str(bucket_or_lot_type.lot_type or "").upper().strip()
    elif isinstance(bucket_or_lot_type, dict):
        tag = str(bucket_or_lot_type.get("lot_type") or "").upper().strip()
    else:
        tag = str(bucket_or_lot_type or "").upper().strip()

    if tag in ("MERGED_UPPER", "SUB_MERGED"):
        return True
    if tag.startswith("GRID_L") and tag != "GRID_L1":
        return True
    if tag.startswith("SUB_L") and tag != "SUB_L1":
        return True
    return False


def has_active_l1_bucket(buckets: Sequence[StratumBucket]) -> bool:
    valid = [
        b
        for b in (buckets or [])
        if isinstance(b, StratumBucket) and b.qty > 0
    ]
    if not valid:
        return False
    return not is_upper_grid_tier(valid[0])


def relabel_upper_grid_tiers(
    upper_buckets: Sequence[StratumBucket],
    max_tiers: int = MAX_GRID_TIERS_7,
    merge_mode: str = DEFAULT_GRID_MERGE_MODE,
) -> List[StratumBucket]:
    valid = [
        b
        for b in (upper_buckets or [])
        if isinstance(b, StratumBucket) and b.qty > 0
    ]
    if not valid:
        return []

    max_upper_cnt = max(1, safe_int(max_tiers, MAX_GRID_TIERS_7) - 1)
    m_mode = str(merge_mode or DEFAULT_GRID_MERGE_MODE).upper().strip()

    while len(valid) > max_upper_cnt:
        if m_mode == "L2_L7_MERGE_SORT" and len(valid) >= 3:
            kept_lowest_upper = [valid[0]]
            low_b = valid[1]
            high_b = valid[-1]
            middle_rest = valid[2:-1]

            m_qty = low_b.qty + high_b.qty
            m_cost = round(low_b.actual_cost_usd + high_b.actual_cost_usd, 4)
            m_lots = max(1, low_b.lot_count) + max(1, high_b.lot_count)
            overall_book_avg = (
                float(low_b.qty) * low_b.book_price
                + float(high_b.qty) * high_b.book_price
            ) / float(max(1, m_qty))
            raw_upper_p = max(0.01, m_cost / float(max(1, m_qty)))
            capped_avg_p = round(min(raw_upper_p, overall_book_avg), 4)
            merged_bucket = StratumBucket(
                qty=m_qty,
                book_price=capped_avg_p,
                book_invested_usd=m_cost,
                actual_cost_usd=m_cost,
                lot_count=m_lots,
                lot_type=f"GRID_L{max_upper_cnt + 1}",
            )
            valid = kept_lowest_upper + middle_rest + [merged_bucket]
            valid.sort(key=lambda b: round(b.book_price, 4))
        else:
            kept = valid[: max_upper_cnt - 1]
            overflow = valid[max_upper_cnt - 1 :]
            tot_q = sum(b.qty for b in overflow)
            tot_cost = round(sum(b.actual_cost_usd for b in overflow), 4)
            tot_lots = sum(max(1, b.lot_count) for b in overflow)
            overall_book_avg = (
                sum(float(b.qty) * b.book_price for b in overflow)
                / float(max(1, tot_q))
            )
            raw_upper_p = max(0.01, tot_cost / float(max(1, tot_q)))
            capped_avg_p = round(min(raw_upper_p, overall_book_avg), 4)
            merged_top = StratumBucket(
                qty=tot_q,
                book_price=capped_avg_p,
                book_invested_usd=tot_cost,
                actual_cost_usd=tot_cost,
                lot_count=tot_lots,
                lot_type=f"GRID_L{max_upper_cnt + 1}",
            )
            valid = kept + [merged_top]

    out: List[StratumBucket] = []
    for idx, b in enumerate(valid):
        tier_no = min(max_upper_cnt + 1, idx + 2)
        pure_cost = round(max(0.01 * float(b.qty), b.actual_cost_usd), 4)
        pure_p = round(max(0.01, pure_cost / float(b.qty)), 4)
        out.append(
            StratumBucket(
                qty=b.qty,
                book_price=pure_p,
                book_invested_usd=pure_cost,
                actual_cost_usd=pure_cost,
                lot_count=max(1, b.lot_count),
                lot_type=f"GRID_L{tier_no}",
            )
        )
    return out


def relabel_sub_upper_grid_tiers_with_flag(
    sub_upper_buckets: Sequence[StratumBucket],
    max_tiers: int = SUB_MAX_TIERS_3,
    merge_mode: str = SUB_MERGE_MODE_L1_L3,
) -> Tuple[List[StratumBucket], bool]:
    valid = [
        b
        for b in (sub_upper_buckets or [])
        if isinstance(b, StratumBucket) and b.qty > 0
    ]
    if not valid:
        return [], False

    max_upper_cnt = max(1, safe_int(max_tiers, SUB_MAX_TIERS_3) - 1)
    m_mode = str(merge_mode or SUB_MERGE_MODE_L1_L3).upper().strip()
    did_merge = False

    while len(valid) > max_upper_cnt:
        did_merge = True
        if m_mode == "SUB_L1_L3_MERGE" and len(valid) >= 3:
            low_b = valid[0]
            high_b = valid[-1]
            middle_rest = valid[1:-1]

            m_qty = low_b.qty + high_b.qty
            m_cost = round(low_b.actual_cost_usd + high_b.actual_cost_usd, 4)
            m_lots = max(1, low_b.lot_count) + max(1, high_b.lot_count)
            overall_book_avg = (
                float(low_b.qty) * low_b.book_price
                + float(high_b.qty) * high_b.book_price
            ) / float(max(1, m_qty))
            raw_upper_p = max(0.01, m_cost / float(max(1, m_qty)))
            capped_avg_p = round(min(raw_upper_p, overall_book_avg), 4)
            merged_bucket = StratumBucket(
                qty=m_qty,
                book_price=capped_avg_p,
                book_invested_usd=m_cost,
                actual_cost_usd=m_cost,
                lot_count=m_lots,
                lot_type="SUB_MERGED",
            )
            valid = middle_rest + [merged_bucket]
            valid.sort(key=lambda b: round(b.book_price, 4))
        else:
            kept = valid[: max_upper_cnt - 1]
            overflow = valid[max_upper_cnt - 1 :]
            tot_q = sum(b.qty for b in overflow)
            tot_cost = round(sum(b.actual_cost_usd for b in overflow), 4)
            tot_lots = sum(max(1, b.lot_count) for b in overflow)
            overall_book_avg = (
                sum(float(b.qty) * b.book_price for b in overflow)
                / float(max(1, tot_q))
            )
            raw_upper_p = max(0.01, tot_cost / float(max(1, tot_q)))
            capped_avg_p = round(min(raw_upper_p, overall_book_avg), 4)
            merged_top = StratumBucket(
                qty=tot_q,
                book_price=capped_avg_p,
                book_invested_usd=tot_cost,
                actual_cost_usd=tot_cost,
                lot_count=tot_lots,
                lot_type="SUB_MERGED",
            )
            valid = kept + [merged_top]

    out: List[StratumBucket] = []
    for idx, b in enumerate(valid):
        tier_no = min(max_upper_cnt + 1, idx + 2)
        pure_cost = round(max(0.01 * float(b.qty), b.actual_cost_usd), 4)
        pure_p = round(max(0.01, pure_cost / float(b.qty)), 4)
        out.append(
            StratumBucket(
                qty=b.qty,
                book_price=pure_p,
                book_invested_usd=pure_cost,
                actual_cost_usd=pure_cost,
                lot_count=max(1, b.lot_count),
                lot_type=f"GRID_L{tier_no}",
            )
        )
    return out, did_merge


def relabel_sub_upper_grid_tiers(
    sub_upper_buckets: Sequence[StratumBucket],
    max_tiers: int = SUB_MAX_TIERS_3,
    merge_mode: str = SUB_MERGE_MODE_L1_L3,
) -> List[StratumBucket]:
    relabeled, _ = relabel_sub_upper_grid_tiers_with_flag(
        sub_upper_buckets=sub_upper_buckets,
        max_tiers=max_tiers,
        merge_mode=merge_mode,
    )
    return relabeled


def enforce_true_breakeven_floor_on_buckets(
    buckets: Sequence[StratumBucket],
    max_allowed_discount_usd: Optional[float] = None,
) -> List[StratumBucket]:
    valid = [
        b
        for b in (buckets or [])
        if isinstance(b, StratumBucket) and b.qty > 0
    ]
    if not valid:
        return []

    adjusted: List[StratumBucket] = []
    for b in valid:
        pure_cost = round(max(0.01 * float(b.qty), b.actual_cost_usd), 4)
        pure_p = round(max(0.01, pure_cost / float(b.qty)), 4)
        adjusted.append(
            StratumBucket(
                qty=b.qty,
                book_price=pure_p,
                book_invested_usd=pure_cost,
                actual_cost_usd=pure_cost,
                lot_count=max(1, b.lot_count),
                lot_type=str(b.lot_type or "QUOTA_L1").upper().strip(),
            )
        )
    return adjusted
# ---------------------------------------------------------------------------
# [핵심 2] 본 그리드 8%(12.5분할) & 서브 그리드 4%(25분할) 정량 주수(복리/단리/바벨 연동) · 유휴현금(0.5회분 보호예수) · GUARD30 판정 · 무제한 온디맨드 수혈/상환기
# ---------------------------------------------------------------------------
def compute_golden8_quota_qty(
    anchor_price: float,
    current_total_equity: float,
    initial_seed_usd: float = DEFAULT_INITIAL_SEED_USD,
    portion_mode: str = PORTION_MODE_COMPOUND,
    exec_price: Optional[float] = None,
    portion_ratio: Optional[float] = None,
) -> Tuple[int, float]:
    """
    # MODIFIED [🎯 1 & Case 25 ~ 35, Case 67, Case 77, Case 88, Case 91 & 바벨 모드 확장]:
    직전 매매 기준가(anchor_price)를 기반으로 황금비율(본 그리드 8% / 서브 그리드 4%) 1회분 예산(portion_budget)과
    고정 목표 매수 주수(anchor_quota_qty)를 산출한다.
    - ⚖️ 바벨 모드(BARBELL_60_30_10): 설정 시드의 60%(SOXL 코어 시드)에 대해 8%(서브 4%) 고정 산출.
    - 💵 인출형(단리 · SIMPLE_08PCT / FIXED_800): 설정 시드(100%)의 8%(서브 4%) 고정 산출.
    - 📈 자산증식형(복리 · COMP_08PCT): 순수 코어 총자산(tot_eq)의 8%(서브 4%) 동적 복리 증액.
    반환값: (target_qty, portion_budget)
    """
    init_seed = max(
        100.0, safe_float(initial_seed_usd, DEFAULT_INITIAL_SEED_USD)
    )
    mode = str(portion_mode or PORTION_MODE_COMPOUND).upper().strip()
    min_eq_floor = (
        init_seed * BARBELL_SOXL_WEIGHT
        if is_barbell_mode(mode)
        else init_seed
    )
    tot_eq = max(
        min_eq_floor, safe_float(current_total_equity, min_eq_floor)
    )

    if portion_ratio is not None and safe_float(portion_ratio, 0.0) > 0.0:
        eff_ratio = safe_float(portion_ratio, PORTION_RATIO_LOCKED)
    elif mode in (
        "SUB_04PCT",
        "COMP_04PCT",
        "SIMPLE_04PCT",
        "BARBELL_04PCT",
    ):
        eff_ratio = SUB_PORTION_RATIO_4PCT
    else:
        eff_ratio = PORTION_RATIO_LOCKED

    if is_barbell_mode(mode):
        eff_p_mode = PORTION_MODE_BARBELL
    elif is_simple_income_mode(mode) or mode == "SIMPLE_04PCT":
        eff_p_mode = PORTION_MODE_SIMPLE
    else:
        eff_p_mode = PORTION_MODE_COMPOUND

    base_eq = resolve_portion_budget_base_equity(
        initial_seed_usd=init_seed,
        core_equity_usd=tot_eq,
        portion_mode=eff_p_mode,
    )
    portion_budget = round(base_eq * eff_ratio, 4)

    ref_p = max(0.01, safe_float(anchor_price, 0.01))
    anchor_quota_qty = max(1, int(math.floor((portion_budget + 1e-9) / ref_p)))

    if exec_price is not None and safe_float(exec_price, 0.0) > 0.0:
        eff_exec_p = max(0.01, safe_float(exec_price, ref_p))
        budget_cap_qty = max(
            1, int(math.floor((portion_budget + 1e-9) / eff_exec_p))
        )
        target_qty = min(budget_cap_qty, anchor_quota_qty)
    else:
        target_qty = anchor_quota_qty

    return target_qty, portion_budget


def compute_sub4_quota_qty(
    sub_anchor_price: float,
    current_core_equity: float,
    initial_seed_usd: float = DEFAULT_INITIAL_SEED_USD,
    exec_price: Optional[float] = None,
    portion_mode: str = PORTION_MODE_COMPOUND,
) -> Tuple[int, float]:
    """
    # MODIFIED [Case 88, Case 91 & 바벨 모드 확장 : 3층 서브 그리드 전용 4.0%(25분할) 정량 주수 산출기]:
    - 📈 자산증식형(복리 · COMP_08PCT): 순수 코어 총자산의 4.0% 산출
    - 💵 인출형(단리 · SIMPLE_08PCT): 설정 기준 시드(100%)의 4.0% 고정 산출
    - ⚖️ 바벨 모드(BARBELL_60_30_10): SOXL 코어 시드(60%)의 4.0% 고정 산출
    """
    if is_barbell_mode(portion_mode):
        sub_mode = "BARBELL_04PCT"
    elif is_simple_income_mode(portion_mode):
        sub_mode = "SIMPLE_04PCT"
    else:
        sub_mode = "SUB_04PCT"
    return compute_golden8_quota_qty(
        anchor_price=sub_anchor_price,
        current_total_equity=current_core_equity,
        initial_seed_usd=initial_seed_usd,
        portion_mode=sub_mode,
        exec_price=exec_price,
        portion_ratio=SUB_PORTION_RATIO_4PCT,
    )


def compute_sub_grid_available_idle_cash(
    free_cash_usd: float,
    core_equity_usd: float,
    broker_buying_power_usd: Optional[float] = None,
    reserve_main_portions: float = SUB_RESERVE_MAIN_PORTIONS,
    initial_seed_usd: Optional[float] = None,
    portion_mode: str = PORTION_MODE_COMPOUND,
) -> Dict[str, Any]:
    """
    # MODIFIED [Case 88, Case 91 & 바벨 모드 확장 : 본 그리드 보호예수금 0.5회분(4.0%) 차감 후 서브 그리드 가용 유휴 현금 산출기]:
    """
    f_cash = max(0.0, safe_float(free_cash_usd, 0.0))
    init_s = max(
        100.0,
        safe_float(
            initial_seed_usd
            if initial_seed_usd is not None
            else core_equity_usd,
            DEFAULT_INITIAL_SEED_USD,
        ),
    )
    min_core_floor = (
        init_s * BARBELL_SOXL_WEIGHT
        if is_barbell_mode(portion_mode)
        else init_s
    )
    c_eq = max(min_core_floor, safe_float(core_equity_usd, min_core_floor))
    res_mult = max(
        0.0, safe_float(reserve_main_portions, SUB_RESERVE_MAIN_PORTIONS)
    )

    budget_base_eq = resolve_portion_budget_base_equity(
        initial_seed_usd=init_s,
        core_equity_usd=c_eq,
        portion_mode=portion_mode,
    )
    main_portion_budget = round(budget_base_eq * PORTION_RATIO_LOCKED, 4)
    sub_portion_budget = round(budget_base_eq * SUB_PORTION_RATIO_4PCT, 4)
    reserved_for_main_usd = round(main_portion_budget * res_mult, 4)

    eff_cash = f_cash
    if broker_buying_power_usd is not None:
        bp_val = safe_float(broker_buying_power_usd, -1.0)
        if bp_val >= 0.0:
            eff_cash = min(f_cash, bp_val)

    avail_idle_cash_usd = round(max(0.0, eff_cash - reserved_for_main_usd), 4)
    free_idle_cash_ledger_usd = round(
        max(0.0, f_cash - reserved_for_main_usd), 4
    )

    return {
        "free_cash_usd": round(f_cash, 4),
        "eff_cash_usd": round(eff_cash, 4),
        "reserved_for_main_usd": reserved_for_main_usd,
        "avail_idle_cash_usd": avail_idle_cash_usd,
        "free_idle_cash_ledger_usd": free_idle_cash_ledger_usd,
        "main_portion_budget": main_portion_budget,
        "sub_portion_budget": sub_portion_budget,
    }


def resolve_affordable_buy_qty(
    target_qty: int,
    price_t: float,
    free_cash_usd: float,
    broker_buying_power_usd: Optional[float] = None,
    max_portion_budget_usd: Optional[float] = None,
    round_trip_fee_rate_pct: Optional[float] = None,
) -> Tuple[int, float]:
    t_qty = max(0, safe_int(target_qty, 0))
    exec_p = safe_float(price_t, 0.0)
    if t_qty <= 0 or exec_p <= 0.0:
        return 0, 0.0

    if (
        max_portion_budget_usd is not None
        and safe_float(max_portion_budget_usd, 0.0) > 0.0
    ):
        p_bud = safe_float(max_portion_budget_usd, 0.0)
        budget_cap_qty = max(1, int(math.floor((p_bud + 1e-9) / exec_p)))
        t_qty = min(budget_cap_qty, t_qty)

    avail_cash = max(0.0, safe_float(free_cash_usd, 0.0))
    if broker_buying_power_usd is not None:
        bp_val = safe_float(broker_buying_power_usd, 0.0)
        if bp_val >= 0.0:
            avail_cash = min(avail_cash, bp_val)

    eff_rt_pct = resolve_effective_round_trip_fee_rate_pct(
        round_trip_fee_rate_pct
    )
    fee_mult = 1.0 + (eff_rt_pct / 100.0)
    unit_cost_with_fee = exec_p * fee_mult
    if avail_cash < unit_cost_with_fee:
        return 0, 0.0

    max_affordable = int(math.floor((avail_cash + 1e-9) / unit_cost_with_fee))
    buy_qty = max(0, min(t_qty, max_affordable))
    actual_spent_usd = (
        round(float(buy_qty) * exec_p, 4) if buy_qty > 0 else 0.0
    )
    return buy_qty, actual_spent_usd


def evaluate_guard30_and_reserve_injection(
    free_cash_usd: float,
    broker_bp_usd: Optional[float],
    exec_price: float,
    portion_budget: float,
    l1_actual_cost_usd: float = 0.0,
    is_dip_promotion: bool = False,
    used_reserve_portions_cnt: int = 0,
    max_reserve_portions: int = MAX_RESERVE_PORTIONS,
    min_dip_budget_ratio: float = MIN_DIP_BUDGET_RATIO,
    min_dip_vs_l1_ratio: float = MIN_DIP_VS_L1_RATIO,
    deposit_tolerance_ratio: float = RESERVE_DEPOSIT_TOLERANCE_RATIO,
    round_trip_fee_rate_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """
    # [Case 77, Case 86, Case 89 & Case 91 : 💉 GUARD30 — 30% 자투리 1주 승격 방지 가드 & 무제한 온디맨드 수혈 판정기]
    """
    f_cash = max(0.0, safe_float(free_cash_usd, 0.0))
    ex_p = max(0.01, safe_float(exec_price, 0.01))
    p_bud = max(0.01, safe_float(portion_budget, 800.0))
    l1_cost = max(0.0, safe_float(l1_actual_cost_usd, 0.0))
    used_cnt = max(0, safe_int(used_reserve_portions_cnt, 0))
    max_res = max(
        used_cnt + 1, safe_int(max_reserve_portions, MAX_RESERVE_PORTIONS)
    )
    rem_portions = max(0, max_res - used_cnt)

    eff_rt_pct = resolve_effective_round_trip_fee_rate_pct(
        round_trip_fee_rate_pct
    )
    fee_mult = 1.0 + (eff_rt_pct / 100.0)
    one_share_cost = ex_p * fee_mult

    bud_ratio = max(0.0, safe_float(min_dip_budget_ratio, MIN_DIP_BUDGET_RATIO))
    l1_ratio = max(0.0, safe_float(min_dip_vs_l1_ratio, MIN_DIP_VS_L1_RATIO))
    tol_ratio = max(
        0.30,
        min(
            1.0,
            safe_float(
                deposit_tolerance_ratio, RESERVE_DEPOSIT_TOLERANCE_RATIO
            ),
        ),
    )

    if is_dip_promotion:
        min_req_cash = max(
            one_share_cost,
            p_bud * bud_ratio,
            l1_cost * l1_ratio,
        )
    else:
        min_req_cash = max(one_share_cost, p_bud * bud_ratio)

    eff_bp = (
        safe_float(broker_bp_usd, -1.0) if broker_bp_usd is not None else -1.0
    )

    if f_cash >= min_req_cash and (eff_bp < 0.0 or eff_bp >= min_req_cash):
        return {
            "action": "PROCEED_NORMAL",
            "should_proceed": True,
            "is_dust_blocked": False,
            "inject_portions": 0,
            "inject_usd": 0.0,
            "min_req_cash": round(min_req_cash, 4),
            "used_portions_before": used_cnt,
            "used_portions_after": used_cnt,
            "rem_portions_before": rem_portions,
            "rem_portions_after": rem_portions,
            "unallocated_deposit_usd": round(
                max(0.0, eff_bp - f_cash) if eff_bp >= 0.0 else 0.0, 4
            ),
            "recommended_deposit_usd": 0.0,
            "minimum_shortfall_usd": 0.0,
        }

    shortfall_for_guard = max(0.0, min_req_cash - f_cash)
    needed_portions = max(
        1, int(math.ceil((shortfall_for_guard - 1e-9) / p_bud))
    )
    unallocated_deposit_usd = (
        max(0.0, eff_bp - f_cash) if eff_bp >= 0.0 else 0.0
    )
    required_inj_usd = round(float(needed_portions) * p_bud, 4)

    if (
        eff_bp >= min_req_cash
        and unallocated_deposit_usd > 0.0
        and (f_cash + unallocated_deposit_usd) >= min_req_cash
    ):
        if unallocated_deposit_usd >= required_inj_usd:
            actual_inj_usd = required_inj_usd
        elif unallocated_deposit_usd >= (required_inj_usd * tol_ratio):
            actual_inj_usd = round(unallocated_deposit_usd, 4)
        else:
            actual_inj_usd = round(unallocated_deposit_usd, 4)

        if (f_cash + actual_inj_usd) >= min_req_cash:
            return {
                "action": "INJECT_AND_PROCEED",
                "should_proceed": True,
                "is_dust_blocked": False,
                "inject_portions": needed_portions,
                "inject_usd": actual_inj_usd,
                "min_req_cash": round(min_req_cash, 4),
                "used_portions_before": used_cnt,
                "used_portions_after": used_cnt + needed_portions,
                "rem_portions_before": rem_portions,
                "rem_portions_after": max(0, rem_portions - needed_portions),
                "unallocated_deposit_usd": round(unallocated_deposit_usd, 4),
                "recommended_deposit_usd": 0.0,
                "minimum_shortfall_usd": 0.0,
            }

    is_dust_blocked = bool(f_cash >= one_share_cost)
    eff_bp_nonneg = max(0.0, eff_bp) if eff_bp >= 0.0 else f_cash
    min_shortfall_usd = round(max(0.0, min_req_cash - eff_bp_nonneg), 2)
    rec_deposit_usd = round(
        max(p_bud, required_inj_usd - unallocated_deposit_usd), 2
    )

    return {
        "action": "BLOCK_AND_ALERT_DEPOSIT",
        "should_proceed": False,
        "is_dust_blocked": is_dust_blocked,
        "inject_portions": 0,
        "inject_usd": 0.0,
        "needed_portions": needed_portions,
        "min_req_cash": round(min_req_cash, 4),
        "used_portions_before": used_cnt,
        "used_portions_after": used_cnt,
        "rem_portions_before": rem_portions,
        "rem_portions_after": rem_portions,
        "unallocated_deposit_usd": round(unallocated_deposit_usd, 4),
        "recommended_deposit_usd": rec_deposit_usd,
        "minimum_shortfall_usd": min_shortfall_usd,
    }


def compute_reserve_repayment_on_zero(
    initial_seed_usd: float,
    cumulative_realized_net_usd: float,
    injected_reserve_usd: float,
    used_reserve_portions_cnt: int,
    max_reserve_portions: int = MAX_RESERVE_PORTIONS,
    portion_mode: str = PORTION_MODE_COMPOUND,
    vaulted_profit_locked_usd: float = 0.0,
) -> Dict[str, Any]:
    """
    # MODIFIED [Case 77, Case 88, Case 91 & 바벨 모드 확장 : 0주 전량 졸업 시 예비시드 원금 자동 상환 및 잔여 수혈 횟수 정산기]:
    """
    init_seed = max(
        100.0, safe_float(initial_seed_usd, DEFAULT_INITIAL_SEED_USD)
    )
    cum_net = round(safe_float(cumulative_realized_net_usd, 0.0), 4)
    inj_usd = round(max(0.0, safe_float(injected_reserve_usd, 0.0)), 4)
    v_locked = round(max(0.0, safe_float(vaulted_profit_locked_usd, 0.0)), 4)
    used_cnt = max(0, safe_int(used_reserve_portions_cnt, 0))
    max_res = max(1, safe_int(max_reserve_portions, MAX_RESERVE_PORTIONS))

    if is_barbell_mode(portion_mode):
        soxl_core_60 = round(init_seed * BARBELL_SOXL_WEIGHT, 4)
        return {
            "did_repay": bool(inj_usd > 0.0),
            "repaid_usd": inj_usd,
            "rem_injected_reserve_usd": 0.0,
            "rem_used_reserve_portions_cnt": 0,
            "avail_reserve_portions": max_res,
            "free_cash_after_repay_usd": soxl_core_60,
        }

    eff_realized = cum_net - v_locked
    total_cash_before = round(max(0.0, init_seed + eff_realized + inj_usd), 4)
    if inj_usd <= 0.0:
        return {
            "did_repay": False,
            "repaid_usd": 0.0,
            "rem_injected_reserve_usd": 0.0,
            "rem_used_reserve_portions_cnt": 0,
            "avail_reserve_portions": max_res,
            "free_cash_after_repay_usd": total_cash_before,
        }

    repayable_surplus = max(0.0, total_cash_before - init_seed)
    repaid_usd = round(min(inj_usd, repayable_surplus), 4)
    rem_inj_usd = round(max(0.0, inj_usd - repaid_usd), 4)

    if rem_inj_usd <= 0.01:
        rem_inj_usd = 0.0
        rem_used_cnt = 0
    else:
        base_eq = resolve_portion_budget_base_equity(
            initial_seed_usd=init_seed,
            core_equity_usd=(init_seed + max(0.0, eff_realized)),
            portion_mode=portion_mode,
        )
        est_portion_unit = max(1.0, base_eq * PORTION_RATIO_LOCKED)
        est_cnt = max(1, int(math.ceil(rem_inj_usd / est_portion_unit)))
        rem_used_cnt = (
            min(used_cnt, est_cnt) if used_cnt > 0 else est_cnt
        )

    free_cash_after = round(
        max(0.0, init_seed + eff_realized + rem_inj_usd), 4
    )
    return {
        "did_repay": bool(repaid_usd > 0.0),
        "repaid_usd": repaid_usd,
        "rem_injected_reserve_usd": rem_inj_usd,
        "rem_used_reserve_portions_cnt": rem_used_cnt,
        "avail_reserve_portions": max(0, max_res - rem_used_cnt),
        "free_cash_after_repay_usd": free_cash_after,
    }


# ---------------------------------------------------------------------------
# [핵심 3] 사이클 최고 도달 회차 잠금 기반 4단 와이드 점진 단차(Case 87, 88) · 하이브리드 1층 재장전(Case 84 돌파차단 & Case 92 돌파 RSI<=50) · STEP2X 스텝업 해금 · 서브 4회분 캡 판정기
# ---------------------------------------------------------------------------
def get_golden8_prog_thresholds(
    held_lots: int,
    threshold_mode: Any = "WIDE_RUNWAY",
    cycle_ratchet_max_lots: int = 0,
) -> Tuple[float, float, float]:
    if isinstance(threshold_mode, (int, float)) and not isinstance(
        threshold_mode, bool
    ):
        eff_ratchet = max(
            safe_int(threshold_mode, 0), safe_int(cycle_ratchet_max_lots, 0)
        )
        mode = "WIDE_RUNWAY"
    else:
        eff_ratchet = safe_int(cycle_ratchet_max_lots, 0)
        mode = str(threshold_mode or "WIDE_RUNWAY").upper().strip()

    lots = max(1, safe_int(held_lots, 1), max(0, eff_ratchet))
    if lots <= 4:
        drop_buy_pct = -1.00
    elif lots <= 8:
        drop_buy_pct = -2.00
    elif lots <= 10:
        drop_buy_pct = -3.50
    else:
        drop_buy_pct = -5.50

    if mode == "01_PROG_LOT":
        prog_rise = 1.00 if lots <= 6 else (1.50 if lots <= 11 else 2.00)
        return drop_buy_pct, prog_rise, prog_rise
    return drop_buy_pct, 1.50, 1.00


def evaluate_l2_only_hybrid_reentry_signal(
    live_price: float,
    anchor_price: float,
    l2_book_price: float = 0.0,
    min_upper_tier_price: float = 0.0,
    is_late_new_cycle_cutoff: bool = False,
    is_late_cutoff: Optional[bool] = None,
    rsi_14: Optional[float] = None,
    breakout_max_rsi: float = REENTRY_BREAKOUT_MAX_RSI_50,
) -> Dict[str, Any]:
    lp = safe_float(live_price, 0.0)
    anc = safe_float(anchor_price, 0.0)
    b2_p = safe_float(l2_book_price, 0.0)
    ceil_p = safe_float(min_upper_tier_price, 0.0)
    if ceil_p <= 0.0 and b2_p > 0.0:
        ceil_p = b2_p

    late_cutoff = bool(
        is_late_cutoff
        if is_late_cutoff is not None
        else is_late_new_cycle_cutoff
    )

    max_rsi_cap = safe_float(breakout_max_rsi, REENTRY_BREAKOUT_MAX_RSI_50)
    has_rsi_filter = bool(
        rsi_14 is not None
        and safe_float(rsi_14, -1.0) > 0.0
        and max_rsi_cap > 0.0
    )
    eff_rsi_val = (
        round(safe_float(rsi_14, 50.0), 2) if rsi_14 is not None else 50.0
    )
    is_breakout_rsi_blocked = bool(
        has_rsi_filter and eff_rsi_val > (max_rsi_cap + 1e-6)
    )

    ref_anchor = (
        anc
        if anc > 0.0
        else (ceil_p if ceil_p > 0.0 else (b2_p if b2_p > 0.0 else lp))
    )

    pullback_target_p = (
        round(ref_anchor * (1.0 + REENTRY_PULLBACK_DROP_PCT / 100.0), 2)
        if ref_anchor > 0.0
        else 0.0
    )
    breakout_target_p = (
        round(ref_anchor * (1.0 + REENTRY_BREAKOUT_RISE_PCT / 100.0), 2)
        if ref_anchor > 0.0
        else 0.0
    )

    if lp <= 0.0 or ref_anchor <= 0.0:
        return {
            "should_buy": False,
            "signal_type": "NO_PRICE",
            "ref_anchor": round(ref_anchor, 4),
            "quota_ref_price": round(ref_anchor, 4),
            "chg_from_exit_pct": 0.0,
            "pullback_target_price": pullback_target_p,
            "breakout_target_price": breakout_target_p,
            "l2_ceiling_price": round(ceil_p, 4),
            "rsi_14": eff_rsi_val,
            "breakout_max_rsi": round(max_rsi_cap, 2),
            "breakout_rsi_blocked": is_breakout_rsi_blocked,
        }

    chg_from_exit_pct = ((lp - ref_anchor) / ref_anchor) * 100.0

    if ceil_p > 0.0 and lp > (ceil_p + 1e-6):
        return {
            "should_buy": False,
            "signal_type": "HOLD_PREVENT_INVERSION",
            "ref_anchor": round(ref_anchor, 4),
            "quota_ref_price": round(ref_anchor, 4),
            "chg_from_exit_pct": round(chg_from_exit_pct, 2),
            "pullback_target_price": pullback_target_p,
            "breakout_target_price": breakout_target_p,
            "l2_ceiling_price": round(ceil_p, 4),
            "rsi_14": eff_rsi_val,
            "breakout_max_rsi": round(max_rsi_cap, 2),
            "breakout_rsi_blocked": is_breakout_rsi_blocked,
        }

    if chg_from_exit_pct <= REENTRY_PULLBACK_DROP_PCT:
        return {
            "should_buy": True,
            "signal_type": "PULLBACK_RELOAD",
            "ref_anchor": round(ref_anchor, 4),
            "quota_ref_price": round(ref_anchor, 4),
            "chg_from_exit_pct": round(chg_from_exit_pct, 2),
            "pullback_target_price": pullback_target_p,
            "breakout_target_price": breakout_target_p,
            "l2_ceiling_price": round(ceil_p, 4),
            "rsi_14": eff_rsi_val,
            "breakout_max_rsi": round(max_rsi_cap, 2),
            "breakout_rsi_blocked": False,
        }

    if chg_from_exit_pct >= REENTRY_BREAKOUT_RISE_PCT:
        if late_cutoff:
            return {
                "should_buy": False,
                "signal_type": "HOLD_LATE_SESSION_BREAKOUT_CUTOFF",
                "ref_anchor": round(ref_anchor, 4),
                "quota_ref_price": round(ref_anchor, 4),
                "chg_from_exit_pct": round(chg_from_exit_pct, 2),
                "pullback_target_price": pullback_target_p,
                "breakout_target_price": breakout_target_p,
                "l2_ceiling_price": round(ceil_p, 4),
                "rsi_14": eff_rsi_val,
                "breakout_max_rsi": round(max_rsi_cap, 2),
                "breakout_rsi_blocked": is_breakout_rsi_blocked,
            }
        if is_breakout_rsi_blocked:
            return {
                "should_buy": False,
                "signal_type": "HOLD_BREAKOUT_RSI_OVER_50",
                "ref_anchor": round(ref_anchor, 4),
                "quota_ref_price": round(ref_anchor, 4),
                "chg_from_exit_pct": round(chg_from_exit_pct, 2),
                "pullback_target_price": pullback_target_p,
                "breakout_target_price": breakout_target_p,
                "l2_ceiling_price": round(ceil_p, 4),
                "rsi_14": eff_rsi_val,
                "breakout_max_rsi": round(max_rsi_cap, 2),
                "breakout_rsi_blocked": True,
            }
        return {
            "should_buy": True,
            "signal_type": "BREAKOUT_RELOAD",
            "ref_anchor": round(ref_anchor, 4),
            "quota_ref_price": round(ref_anchor, 4),
            "chg_from_exit_pct": round(chg_from_exit_pct, 2),
            "pullback_target_price": pullback_target_p,
            "breakout_target_price": breakout_target_p,
            "l2_ceiling_price": round(ceil_p, 4),
            "rsi_14": eff_rsi_val,
            "breakout_max_rsi": round(max_rsi_cap, 2),
            "breakout_rsi_blocked": False,
        }

    return {
        "should_buy": False,
        "signal_type": "HOLD_WAIT_GATE",
        "ref_anchor": round(ref_anchor, 4),
        "quota_ref_price": round(ref_anchor, 4),
        "chg_from_exit_pct": round(chg_from_exit_pct, 2),
        "pullback_target_price": pullback_target_p,
        "breakout_target_price": breakout_target_p,
        "l2_ceiling_price": round(ceil_p, 4),
        "rsi_14": eff_rsi_val,
        "breakout_max_rsi": round(max_rsi_cap, 2),
        "breakout_rsi_blocked": is_breakout_rsi_blocked,
    }


def evaluate_step_up_2x_dip_signal(
    live_price: float,
    buckets: Sequence[StratumBucket],
    anchor_price: float,
    cycle_min_buy_price: float,
    drop_buy_pct: float,
    free_cash_usd: float,
    realized_equity_usd: float,
    step_up_drop_pct: float = STEP_UP_2X_DROP_PCT,
    min_cash_ratio: float = STEP_UP_2X_MIN_CASH_RATIO,
    min_rebound_mult: float = STEP_UP_2X_MIN_REBOUND_MULT,
    max_tiers_for_unlock: int = STEP_UP_2X_MAX_TIERS,
) -> Dict[str, Any]:
    valid = [
        b
        for b in (buckets or [])
        if isinstance(b, StratumBucket) and b.qty > 0
    ]
    lp = safe_float(live_price, 0.0)
    anc = safe_float(anchor_price, 0.0)
    c_min = safe_float(cycle_min_buy_price, 0.0)
    req_drop = safe_float(drop_buy_pct, -1.0)
    f_cash = max(0.0, safe_float(free_cash_usd, 0.0))
    r_eq = max(1.0, safe_float(realized_equity_usd, DEFAULT_INITIAL_SEED_USD))

    if not valid or not has_active_l1_bucket(valid):
        return {
            "should_buy": False,
            "is_step_up_unlock": False,
            "trigger_tag": "NO_ACTIVE_L1",
            "quota_ref_price": round(c_min if c_min > 0.0 else lp, 4),
            "ref_static_anchor": round(c_min if c_min > 0.0 else lp, 4),
            "chg_static_pct": 0.0,
            "step_up_eligible": False,
            "stepped_min_price": 0.0,
            "stepped_trigger_price": 0.0,
            "chg_from_l1_pct": 0.0,
            "rebound_mult": 0.0,
            "cash_ratio_pct": round((f_cash / r_eq) * 100.0, 2),
            "next_cycle_min_price": round(c_min, 4),
        }

    l1_p = valid[0].book_price
    valid_refs = [p for p in (l1_p, anc, c_min) if p > 0.0]
    ref_static_anchor = min(valid_refs) if valid_refs else l1_p
    eff_min_p = c_min if c_min > 0.0 else ref_static_anchor

    chg_static_pct = (
        ((lp - ref_static_anchor) / ref_static_anchor) * 100.0
        if (lp > 0.0 and ref_static_anchor > 0.0)
        else 0.0
    )
    chg_from_l1_pct = (
        ((lp - l1_p) / l1_p) * 100.0 if (lp > 0.0 and l1_p > 0.0) else 0.0
    )

    rebound_mult = l1_p / max(0.01, eff_min_p) if eff_min_p > 0.0 else 1.0
    cash_ratio = f_cash / r_eq
    tiers_cnt = len(valid)

    s_drop = safe_float(step_up_drop_pct, STEP_UP_2X_DROP_PCT)
    m_cash = safe_float(min_cash_ratio, STEP_UP_2X_MIN_CASH_RATIO)
    m_reb = safe_float(min_rebound_mult, STEP_UP_2X_MIN_REBOUND_MULT)
    m_tiers = max(1, safe_int(max_tiers_for_unlock, STEP_UP_2X_MAX_TIERS))

    step_up_eligible = bool(
        s_drop > 0.0
        and tiers_cnt <= m_tiers
        and cash_ratio >= (m_cash - 1e-9)
        and rebound_mult >= (m_reb - 1e-9)
    )
    stepped_min_p = (
        round(l1_p * (1.0 - s_drop / 100.0), 4) if step_up_eligible else 0.0
    )
    stepped_trigger_p = (
        round(math.floor((stepped_min_p + 1e-9) * 100.0) / 100.0, 2)
        if stepped_min_p > 0.0
        else 0.0
    )

    if lp <= 0.0:
        return {
            "should_buy": False,
            "is_step_up_unlock": False,
            "trigger_tag": "NO_LIVE_PRICE",
            "quota_ref_price": round(ref_static_anchor, 4),
            "ref_static_anchor": round(ref_static_anchor, 4),
            "chg_static_pct": 0.0,
            "step_up_eligible": step_up_eligible,
            "stepped_min_price": stepped_min_p,
            "stepped_trigger_price": stepped_trigger_p,
            "chg_from_l1_pct": 0.0,
            "rebound_mult": round(rebound_mult, 2),
            "cash_ratio_pct": round(cash_ratio * 100.0, 2),
            "next_cycle_min_price": round(eff_min_p, 4),
        }

    if chg_static_pct <= req_drop:
        return {
            "should_buy": True,
            "is_step_up_unlock": False,
            "trigger_tag": "STATIC_NEW_LOW",
            "quota_ref_price": round(ref_static_anchor, 4),
            "ref_static_anchor": round(ref_static_anchor, 4),
            "chg_static_pct": round(chg_static_pct, 2),
            "step_up_eligible": step_up_eligible,
            "stepped_min_price": 0.0,
            "stepped_trigger_price": stepped_trigger_p,
            "chg_from_l1_pct": round(chg_from_l1_pct, 2),
            "rebound_mult": round(rebound_mult, 2),
            "cash_ratio_pct": round(cash_ratio * 100.0, 2),
            "next_cycle_min_price": round(min(eff_min_p, lp), 4),
        }

    if s_drop <= 0.0:
        return {
            "should_buy": False,
            "is_step_up_unlock": False,
            "trigger_tag": "HOLD_STATIC_LOCK",
            "quota_ref_price": round(ref_static_anchor, 4),
            "ref_static_anchor": round(ref_static_anchor, 4),
            "chg_static_pct": round(chg_static_pct, 2),
            "step_up_eligible": False,
            "stepped_min_price": 0.0,
            "stepped_trigger_price": 0.0,
            "chg_from_l1_pct": round(chg_from_l1_pct, 2),
            "rebound_mult": round(rebound_mult, 2),
            "cash_ratio_pct": round(cash_ratio * 100.0, 2),
            "next_cycle_min_price": round(eff_min_p, 4),
        }

    if l1_p <= 0.0 or lp >= l1_p:
        return {
            "should_buy": False,
            "is_step_up_unlock": False,
            "trigger_tag": "HOLD_ABOVE_L1",
            "quota_ref_price": round(ref_static_anchor, 4),
            "ref_static_anchor": round(ref_static_anchor, 4),
            "chg_static_pct": round(chg_static_pct, 2),
            "step_up_eligible": step_up_eligible,
            "stepped_min_price": stepped_min_p,
            "stepped_trigger_price": stepped_trigger_p,
            "chg_from_l1_pct": round(chg_from_l1_pct, 2),
            "rebound_mult": round(rebound_mult, 2),
            "cash_ratio_pct": round(cash_ratio * 100.0, 2),
            "next_cycle_min_price": round(eff_min_p, 4),
        }

    if step_up_eligible and stepped_min_p > 0.0 and lp <= stepped_min_p:
        tag_str = (
            f"UNLOCK_STEP2X_{int(round(s_drop))}P_"
            f"C{int(round(m_cash * 100))}"
        )
        return {
            "should_buy": True,
            "is_step_up_unlock": True,
            "trigger_tag": tag_str,
            "quota_ref_price": stepped_min_p,
            "ref_static_anchor": round(ref_static_anchor, 4),
            "chg_static_pct": round(chg_static_pct, 2),
            "step_up_eligible": True,
            "stepped_min_price": stepped_min_p,
            "stepped_trigger_price": stepped_trigger_p,
            "chg_from_l1_pct": round(chg_from_l1_pct, 2),
            "rebound_mult": round(rebound_mult, 2),
            "cash_ratio_pct": round(cash_ratio * 100.0, 2),
            "next_cycle_min_price": round(min(stepped_min_p, lp), 4),
        }

    return {
        "should_buy": False,
        "is_step_up_unlock": False,
        "trigger_tag": "HOLD_STEP_UP_2X",
        "quota_ref_price": round(ref_static_anchor, 4),
        "ref_static_anchor": round(ref_static_anchor, 4),
        "chg_static_pct": round(chg_static_pct, 2),
        "step_up_eligible": step_up_eligible,
        "stepped_min_price": stepped_min_p,
        "stepped_trigger_price": stepped_trigger_p,
        "chg_from_l1_pct": round(chg_from_l1_pct, 2),
        "rebound_mult": round(rebound_mult, 2),
        "cash_ratio_pct": round(cash_ratio * 100.0, 2),
        "next_cycle_min_price": round(eff_min_p, 4),
    }


def evaluate_sub_grid_dip_signal(
    live_price: float,
    sub_buckets: Sequence[StratumBucket],
    sub_anchor_price: float,
    sub_cycle_min_buy_price: float,
    sub_drop_buy_pct: float,
    sub_consec_frozen_days: int = 0,
    sub_max_total_lots: int = SUB_MAX_TOTAL_LOTS_4,
    unlock_frozen_days: int = SUB_UNLOCK_FROZEN_DAYS_10,
    unlock_drop_pct: float = SUB_UNLOCK_DROP_FROM_L1_PCT,
) -> Dict[str, Any]:
    valid = [
        sb
        for sb in (sub_buckets or [])
        if isinstance(sb, StratumBucket) and sb.qty > 0
    ]
    lp = safe_float(live_price, 0.0)
    anc = safe_float(sub_anchor_price, 0.0)
    c_min = safe_float(sub_cycle_min_buy_price, 0.0)
    req_drop = safe_float(sub_drop_buy_pct, -1.0)
    frozen_d = max(0, safe_int(sub_consec_frozen_days, 0))
    max_lots_cap = max(1, safe_int(sub_max_total_lots, SUB_MAX_TOTAL_LOTS_4))
    req_frozen_d = max(
        1, safe_int(unlock_frozen_days, SUB_UNLOCK_FROZEN_DAYS_10)
    )
    u_drop_pct = max(
        1.0, safe_float(unlock_drop_pct, SUB_UNLOCK_DROP_FROM_L1_PCT)
    )

    sub_cur_total_lots = sum(max(1, sb.lot_count) for sb in valid)

    if not valid or not has_active_l1_bucket(valid):
        return {
            "should_buy": False,
            "is_sub_unlock": False,
            "trigger_tag": "NO_ACTIVE_SUB_L1",
            "quota_ref_price": round(c_min if c_min > 0.0 else lp, 4),
            "ref_static_anchor": round(c_min if c_min > 0.0 else lp, 4),
            "chg_static_pct": 0.0,
            "sub_unlock_eligible": False,
            "sub_stepped_min_price": 0.0,
            "sub_stepped_trigger_price": 0.0,
            "sub_cur_total_lots": sub_cur_total_lots,
            "sub_max_total_lots": max_lots_cap,
            "next_sub_cycle_min_price": round(c_min, 4),
        }

    sub_l1_p = valid[0].book_price
    valid_refs = [p for p in (sub_l1_p, anc, c_min) if p > 0.0]
    ref_static_anchor = min(valid_refs) if valid_refs else sub_l1_p
    eff_min_p = c_min if c_min > 0.0 else ref_static_anchor

    chg_static_pct = (
        ((lp - ref_static_anchor) / ref_static_anchor) * 100.0
        if (lp > 0.0 and ref_static_anchor > 0.0)
        else 0.0
    )

    sub_unlock_eligible = bool(frozen_d >= req_frozen_d and sub_l1_p > 0.0)
    sub_stepped_min_p = (
        round(sub_l1_p * (1.0 - u_drop_pct / 100.0), 4)
        if sub_l1_p > 0.0
        else 0.0
    )
    sub_stepped_trig_p = (
        round(math.floor((sub_stepped_min_p + 1e-9) * 100.0) / 100.0, 2)
        if sub_stepped_min_p > 0.0
        else 0.0
    )

    if sub_cur_total_lots >= max_lots_cap:
        return {
            "should_buy": False,
            "is_sub_unlock": False,
            "trigger_tag": "HOLD_SUB_CAP_4_LOTS_REACHED",
            "quota_ref_price": round(ref_static_anchor, 4),
            "ref_static_anchor": round(ref_static_anchor, 4),
            "chg_static_pct": round(chg_static_pct, 2),
            "sub_unlock_eligible": False,
            "sub_stepped_min_price": sub_stepped_min_p,
            "sub_stepped_trigger_price": sub_stepped_trig_p,
            "sub_cur_total_lots": sub_cur_total_lots,
            "sub_max_total_lots": max_lots_cap,
            "next_sub_cycle_min_price": round(eff_min_p, 4),
        }

    if lp <= 0.0:
        return {
            "should_buy": False,
            "is_sub_unlock": False,
            "trigger_tag": "NO_LIVE_PRICE",
            "quota_ref_price": round(ref_static_anchor, 4),
            "ref_static_anchor": round(ref_static_anchor, 4),
            "chg_static_pct": 0.0,
            "sub_unlock_eligible": sub_unlock_eligible,
            "sub_stepped_min_price": sub_stepped_min_p,
            "sub_stepped_trigger_price": sub_stepped_trig_p,
            "sub_cur_total_lots": sub_cur_total_lots,
            "sub_max_total_lots": max_lots_cap,
            "next_sub_cycle_min_price": round(eff_min_p, 4),
        }

    if chg_static_pct <= req_drop:
        return {
            "should_buy": True,
            "is_sub_unlock": False,
            "trigger_tag": "SUB_STATIC_NEW_LOW",
            "quota_ref_price": round(ref_static_anchor, 4),
            "ref_static_anchor": round(ref_static_anchor, 4),
            "chg_static_pct": round(chg_static_pct, 2),
            "sub_unlock_eligible": sub_unlock_eligible,
            "sub_stepped_min_price": 0.0,
            "sub_stepped_trigger_price": sub_stepped_trig_p,
            "sub_cur_total_lots": sub_cur_total_lots,
            "sub_max_total_lots": max_lots_cap,
            "next_sub_cycle_min_price": round(min(eff_min_p, lp), 4),
        }

    if (
        sub_unlock_eligible
        and sub_stepped_min_p > 0.0
        and lp <= sub_stepped_min_p
    ):
        return {
            "should_buy": True,
            "is_sub_unlock": True,
            "trigger_tag": "SUB_UNLOCK_10D_D10",
            "quota_ref_price": sub_stepped_min_p,
            "ref_static_anchor": round(ref_static_anchor, 4),
            "chg_static_pct": round(chg_static_pct, 2),
            "sub_unlock_eligible": True,
            "sub_stepped_min_price": sub_stepped_min_p,
            "sub_stepped_trigger_price": sub_stepped_trig_p,
            "sub_cur_total_lots": sub_cur_total_lots,
            "sub_max_total_lots": max_lots_cap,
            "next_sub_cycle_min_price": round(min(sub_stepped_min_p, lp), 4),
        }

    return {
        "should_buy": False,
        "is_sub_unlock": False,
        "trigger_tag": "HOLD_SUB_GATE",
        "quota_ref_price": round(ref_static_anchor, 4),
        "ref_static_anchor": round(ref_static_anchor, 4),
        "chg_static_pct": round(chg_static_pct, 2),
        "sub_unlock_eligible": sub_unlock_eligible,
        "sub_stepped_min_price": sub_stepped_min_p,
        "sub_stepped_trigger_price": sub_stepped_trig_p,
        "sub_cur_total_lots": sub_cur_total_lots,
        "sub_max_total_lots": max_lots_cap,
        "next_sub_cycle_min_price": round(eff_min_p, 4),
    }
