# -*- coding: utf-8 -*-
"""
# MODIFIED: quant_engine_core.py
인피니트 스노우볼 (Infinite Snowball) v3.0 — 퀀트 엔진 코어 Part 1 / 2 (Step 02 / 11)
역할:
1) 전역 퀀트 상수 락온 (8% 황금비율 · 7-Layer 골디락스 그리드 · STEP2X_15PCT_C20 · GUARD30 예비수혈 · 황금시간 전액매수 기본값 NONE[OFF] · Case 84 15:30 컷오프)
2) 계좌별 미국 주식 매매 수수료율(GET /api/v1/commissions : 편도 0.07% -> 왕복 0.14% / 편도 0.10% -> 왕복 0.20%) 런타임 동적 동기화 브릿지 탑재
3) 순수 실물 매수 원가(book_price == actual_avg_price) 구조체 (StratumBucket, GoldenAllInPocket) 및
   상단 그리드(2층 ~ 6층 개별 완충층 + 통합 7층 본대 GRID_L7) 번호 정규화·합병기(relabel_upper_grid_tiers)
4) 8%(12.5분할) 황금비율 정액 기반 정량 산출기(min(1회분 예산 상한 주수, 기준가 고정 정량) 이중 캡핑 Case 67) 및
   황금시간대(07:00 ~ 07:50 EST & 1분봉 Wilder RSI(14) <= 19.0) 가용현금 100% 전액매수 판정기(Case 80)
5) 30% 자투리 1주 승격 방지 가드(GUARD30) & 토스 실계좌 여유자금 감지 기반 최대 +6회분 온디맨드 예비시드 자동 수혈 판정기 및
   0주 전량 졸업 시 예비시드 원금 자동 상환 연산기(Case 77)
6) 보유 회차별 4단 와이드 점진 활주로(1~4회 -1.0% / 5~8회 -2.0% / 9~10회 -3.5% / 11회+ -5.5%) ·
   1층 공석 시 2층 단가 상한 역전 차단(HOLD_PREVENT_INVERSION · Case 73) 및
   정규장 마감 30분 전(15:30 ~ 16:00 EST) +1.00% 상승돌파 추격 차단(HOLD_LATE_SESSION_BREAKOUT_CUTOFF · Case 84) 기반 하이브리드 재장전 판정기 ·
   3중 안전문(보유 2층 이하 & 현금비중 20%+ & 저점대비 2.0배+ 반등) 통과 시 -15.0% 스텝업 저가 해금 판정기(Case 76)
- 제1헌법 ~ 제6헌법 및 Case 01 ~ 85 완벽 준수
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import toss_api
from toss_api import safe_float, safe_int

logger = logging.getLogger("toss_sniper.quant_engine_core")

# toss_api.py 내부 상수 존재 여부와 무관하게 100% 안전하게 작동하는 자립형 폴백 상수 정의
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

# 8%(12.5분할) 황금비율 기준 기본 분할 회차 및 1~7층 골디락스 멀티 그리드 최대 층수 상수 (Case 72)
BASE_MAX_LOTS_8PCT: int = 12
MAX_GRID_TIERS_7: int = int(getattr(toss_api, "MAX_GRID_TIERS_7", 7))
MAX_GRID_TIERS: int = MAX_GRID_TIERS_7
# 타 모듈 AST 심볼 임포트 호환을 위해 MAX_GRID_TIERS_12 별칭을 7 로 동시 유지
MAX_GRID_TIERS_12: int = MAX_GRID_TIERS_7

# 🎯 4 & Case 59, Case 71, Case 72, Case 73, Case 84: 상단 그리드(2~7층) 보유 중 1층 공석 시 60초 주기 눌림목/상승돌파 임계치(%)
REENTRY_PULLBACK_DROP_PCT: float = -1.00
REENTRY_BREAKOUT_RISE_PCT: float = 1.00

# [Case 84]: 정규장 마감 30분 전(15:30 ~ 16:00 EST) 0주 새 사이클 1층 진입 및 1층 공석 +1.0% 돌파 추격 차단 기준 시각(HHMM)
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

# Case 77: 💉 05_RESV_6P_GUARD30 (30% 자투리 승격 방지 가드 & 최대 +6회분 온디맨드 예비시드 자동 수혈) 상수
MAX_RESERVE_PORTIONS: int = int(
    getattr(toss_api, "MAX_RESERVE_PORTIONS", 6)
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

# [Case 80]: 미동부 프리장 황금시간대(07:00 ~ 07:50 EST & RSI(14) <= 19.0) 가용현금 100% 전액 추가매수 상수
# 사용자 지시에 따라 기본값은 반드시 "NONE" (OFF) 으로 고정!
GOLDEN_ALLIN_MODES: Tuple[str, ...] = tuple(
    getattr(
        toss_api,
        "GOLDEN_ALLIN_MODES",
        ("NONE", "POCKET_ALLIN", "GRID_L1_ALLIN"),
    )
)
DEFAULT_GOLDEN_ALLIN_MODE: str = str(
    getattr(toss_api, "DEFAULT_GOLDEN_ALLIN_MODE", "NONE")
)
GOLDEN_WINDOW_START_HM: int = int(
    getattr(toss_api, "GOLDEN_WINDOW_START_HM", 700)
)
GOLDEN_WINDOW_END_HM: int = int(
    getattr(toss_api, "GOLDEN_WINDOW_END_HM", 750)
)
GOLDEN_RSI_MAX_THRESHOLD: float = float(
    getattr(toss_api, "GOLDEN_RSI_MAX_THRESHOLD", 19.0)
)
GOLDEN_POCKET_RISE_PCT: float = float(
    getattr(toss_api, "GOLDEN_POCKET_RISE_PCT", 1.50)
)


# ---------------------------------------------------------------------------
# [핵심 0 · NEW] 계좌별 미국 주식 수수료율 런타임 조회/갱신 브릿지
# ---------------------------------------------------------------------------
def get_runtime_us_commission_rate() -> float:
    """
    # NEW: 현재 프로세스에 락온된 미국 주식 편도 수수료율(소수 비율, 기본 0.0007)을 반환한다.
    """
    fn = getattr(toss_api, "get_runtime_us_commission_rate", None)
    if callable(fn):
        return safe_float(fn(), DEFAULT_US_COMMISSION_RATE)
    return DEFAULT_US_COMMISSION_RATE


def get_runtime_round_trip_fee_rate_pct() -> float:
    """
    # NEW: 현재 프로세스에 락온된 미국 주식 왕복 수수료율(%, 기본 0.14 / 0.10% 계좌는 0.20)을 반환한다.
    """
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
    """
    # NEW: 계좌별 왕복 수수료율(%)을 런타임 메모리에 동기화한다.
    """
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
    """
    # NEW: 명시적 인자 -> 원장 상태(state_dict["round_trip_fee_rate_pct"]) -> 런타임 메모리 -> 기본 상수(0.14%) 순으로
    유효 왕복 수수료율(%)을 결정한다.
    """
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


def get_golden_allin_mode_label(mode: str) -> str:
    """
    # [Case 80 : 황금시간대(07:00 ~ 07:50 EST & RSI <= 19.0) 전액매수 모드 한글 상태 라벨]:
    전술 제어반(/settlement), 레이더(/avwap), 지시서(/sync)에서 표출할 직관적인 모드명을 반환한다.
    """
    m = str(mode or DEFAULT_GOLDEN_ALLIN_MODE).upper().strip()
    if m == "POCKET_ALLIN":
        return "🌟 독립 골든포켓 100% (ON·권장)"
    if m == "GRID_L1_ALLIN":
        return "🔥 7층 그리드 1층편입 100% (ON)"
    return "⚪ 사용 안 함 (OFF·기본챔피언)"


# ---------------------------------------------------------------------------
# [핵심 1] StratumBucket & GoldenAllInPocket : 순수 실물 매수 원가(book_price == actual_avg_price) 구조체 (Case 46 ~ 85)
# ---------------------------------------------------------------------------
@dataclass
class StratumBucket:
    """
    🎯 3 & Case 46 ~ 85:
    SOXL 1층 ~ 7층 골디락스 멀티 그리드(1층 공격수 L1 / 2층 ~ 6층 개별 완충층 GRID_L2 ~ GRID_L6 / 통합 7층 본대 GRID_L7) 데이터 구조체.
    """

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


@dataclass
class GoldenAllInPocket:
    """
    # [Case 80 : 미동부 프리장 황금시간대(07:00 ~ 07:50 EST & RSI <= 19.0) 독립 골든포켓 분리회계 구조체]:
    7층 그리드(buckets)의 층수·회차·기억저가를 전혀 오염시키지 않고 독립 관리되는
    가용시드 100% 전액매수 전용 포켓 (목표 익절률 +1.50% 고정).
    """

    qty: int = 0
    book_price: float = 0.0
    book_invested_usd: float = 0.0
    actual_cost_usd: float = 0.0
    entry_ts: float = 0.0
    order_date: str = ""

    @property
    def is_active(self) -> bool:
        return bool(self.qty > 0 and self.actual_cost_usd > 0.0)

    @property
    def actual_avg_price(self) -> float:
        if self.qty <= 0:
            return 0.0
        return round(self.actual_cost_usd / float(self.qty), 4)

    def target_sell_price(
        self, rise_pct: float = GOLDEN_POCKET_RISE_PCT
    ) -> float:
        if not self.is_active:
            return 0.0
        pure_p = self.actual_avg_price
        return round(
            math.ceil((pure_p * (1.0 + rise_pct / 100.0) - 1e-9) * 100.0)
            / 100.0,
            2,
        )

    def to_dict(self) -> Dict[str, Any]:
        if self.qty <= 0:
            return {
                "qty": 0,
                "book_price": 0.0,
                "book_invested_usd": 0.0,
                "actual_cost_usd": 0.0,
                "entry_ts": 0.0,
                "order_date": "",
            }
        q_int = max(1, safe_int(self.qty, 1))
        a_cost = round(
            max(
                0.01 * float(q_int),
                safe_float(
                    self.actual_cost_usd,
                    float(q_int) * safe_float(self.book_price, 0.01),
                ),
            ),
            4,
        )
        pure_p = round(max(0.01, a_cost / float(q_int)), 4)
        return {
            "qty": q_int,
            "book_price": pure_p,
            "book_invested_usd": a_cost,
            "actual_cost_usd": a_cost,
            "entry_ts": round(max(0.0, safe_float(self.entry_ts, 0.0)), 4),
            "order_date": str(self.order_date or "").strip(),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "GoldenAllInPocket":
        if isinstance(data, GoldenAllInPocket):
            return cls.from_dict(data.to_dict())
        if not isinstance(data, dict):
            return cls()
        q_int = safe_int(data.get("qty"), 0)
        if q_int <= 0:
            return cls()
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
            return cls()
        clean_cost = round(max(0.01 * float(q_int), a_cost), 4)
        pure_p = round(max(0.01, clean_cost / float(q_int)), 4)
        return cls(
            qty=q_int,
            book_price=pure_p,
            book_invested_usd=clean_cost,
            actual_cost_usd=clean_cost,
            entry_ts=round(max(0.0, safe_float(data.get("entry_ts"), 0.0)), 4),
            order_date=str(data.get("order_date") or "").strip(),
        )


def pocket_from_dict(raw_data: Any) -> GoldenAllInPocket:
    return GoldenAllInPocket.from_dict(raw_data)


def pocket_to_dict(pocket: Any) -> Dict[str, Any]:
    if isinstance(pocket, GoldenAllInPocket):
        return pocket.to_dict()
    return GoldenAllInPocket.from_dict(pocket).to_dict()


def has_active_golden_pocket(pocket_or_state: Any) -> bool:
    if isinstance(pocket_or_state, GoldenAllInPocket):
        return pocket_or_state.is_active
    if isinstance(pocket_or_state, dict) and "golden_pocket" in pocket_or_state:
        return GoldenAllInPocket.from_dict(
            pocket_or_state.get("golden_pocket")
        ).is_active
    return GoldenAllInPocket.from_dict(pocket_or_state).is_active


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
# [핵심 1-B · Case 69, Case 71 & Case 72] 그리드 층 판별기 & 진성 손익분기점(순수 원가) 하한선 정규화기
# ---------------------------------------------------------------------------
def is_upper_grid_tier(bucket_or_lot_type: Any) -> bool:
    """
    🚨 [Case 71 & Case 72 상단 그리드(2층 ~ 7층) 여부 결정론적 판별기]:
    """
    if isinstance(bucket_or_lot_type, StratumBucket):
        tag = str(bucket_or_lot_type.lot_type or "").upper().strip()
    elif isinstance(bucket_or_lot_type, dict):
        tag = str(bucket_or_lot_type.get("lot_type") or "").upper().strip()
    else:
        tag = str(bucket_or_lot_type or "").upper().strip()

    if tag == "MERGED_UPPER":
        return True
    if tag.startswith("GRID_L") and tag != "GRID_L1":
        return True
    return False


def has_active_l1_bucket(buckets: Sequence[StratumBucket]) -> bool:
    """
    🚨 [Case 71 & Case 72 활성 1층 공격수 보유 여부 판별기]:
    """
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
) -> List[StratumBucket]:
    """
    🚨 [Case 71 & Case 72 상단 그리드(2층 ~ 6층 개별 완충층 + 통합 7층 본대) 번호 정규화 및 합병기]:
    """
    valid = [
        b
        for b in (upper_buckets or [])
        if isinstance(b, StratumBucket) and b.qty > 0
    ]
    if not valid:
        return []

    max_upper_cnt = max(1, safe_int(max_tiers, MAX_GRID_TIERS_7) - 1)
    if len(valid) > max_upper_cnt:
        kept = valid[: max_upper_cnt - 1]
        overflow = valid[max_upper_cnt - 1 :]
        tot_q = sum(b.qty for b in overflow)
        tot_cost = round(sum(b.actual_cost_usd for b in overflow), 4)
        tot_lots = sum(max(1, b.lot_count) for b in overflow)
        overall_book_avg = (
            sum(float(b.qty) * b.book_price for b in overflow) / float(tot_q)
        )
        raw_avg_p = max(0.01, tot_cost / float(tot_q))
        capped_avg_p = round(min(raw_avg_p, overall_book_avg), 4)
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


def enforce_true_breakeven_floor_on_buckets(
    buckets: Sequence[StratumBucket],
    max_allowed_discount_usd: Optional[float] = None,
) -> List[StratumBucket]:
    """
    🚨 [Case 69, Case 71 & Case 72 진성 손익분기점(순수 매수 원가) 하한선 강제]:
    """
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
# [핵심 2] 8%(12.5분할) 정량 주수 · 100% 전액매수 주수 · GUARD30 판정 · 온디맨드 수혈/상환기 (🎯 1 & Case 25 ~ 35, 67, 77, 80)
# ---------------------------------------------------------------------------
def compute_golden8_quota_qty(
    anchor_price: float,
    current_total_equity: float,
    initial_seed_usd: float = DEFAULT_INITIAL_SEED_USD,
    portion_mode: str = "COMP_08PCT",
    exec_price: Optional[float] = None,
) -> Tuple[int, float]:
    """
    🎯 1 & Case 25 ~ 35, Case 67 & Case 77:
    직전 매매 기준가(anchor_price)를 기반으로 8%(12.5분할) 황금비율 1회분 예산(portion_budget)과
    고정 목표 매수 주수(anchor_quota_qty)를 산출하되, 실제 매수 지정가(exec_price)가 제공된 경우
    상승 돌파 등으로 인해 1회분(8%) 예산을 초과하지 않도록 min(budget_cap_qty, anchor_quota_qty)로 캡핑한다.
    반환값: (target_qty, portion_budget)
    """
    init_seed = max(
        100.0, safe_float(initial_seed_usd, DEFAULT_INITIAL_SEED_USD)
    )
    tot_eq = max(init_seed, safe_float(current_total_equity, init_seed))
    mode = str(portion_mode or "COMP_08PCT").upper().strip()

    if mode == "FIXED_800":
        portion_budget = round(init_seed * PORTION_RATIO_LOCKED, 4)
    else:
        portion_budget = round(tot_eq * PORTION_RATIO_LOCKED, 4)

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


def resolve_affordable_buy_qty(
    target_qty: int,
    price_t: float,
    free_cash_usd: float,
    broker_buying_power_usd: Optional[float] = None,
    max_portion_budget_usd: Optional[float] = None,
    round_trip_fee_rate_pct: Optional[float] = None,
) -> Tuple[int, float]:
    """
    # MODIFIED [Case 25 ~ 35, Case 67 & 계좌별 동적 왕복 수수료율 연동]:
    직전 기준가로 산출된 목표 정량(target_qty)을 실제 주문가(price_t)로 매수하기 직전:
    1) max_portion_budget_usd(1회분 8% 예산) 상한 주수(budget_cap_qty)와 target_qty 중 작은 값으로 캡핑한다.
    2) 계좌의 왕복 수수료율(round_trip_fee_rate_pct, 미지정 시 런타임 락온 수수료율 0.14% 또는 0.20%) 버퍼를 감안한
       가용 현금(free_cash_usd) 및 토스 실계좌 매수가능금액 한도 내로 캡핑한다.
    반환값: (buy_qty, actual_spent_usd)
    """
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


def resolve_allin_affordable_buy_qty(
    price_t: float,
    free_cash_usd: float,
    broker_buying_power_usd: Optional[float] = None,
    round_trip_fee_rate_pct: Optional[float] = None,
) -> Tuple[int, float]:
    """
    # MODIFIED [Case 80 : 황금시간대(07:00 ~ 07:50 EST & RSI <= 19.0) 가용 현금 시드 100% 전액 매수 주수 산출기]:
    계좌의 왕복 수수료 버퍼(0.14% 또는 0.20%)를 감안하여 현재 가용 현금(free_cash_usd)과
    토스 실계좌 주문가능 달러(broker_buying_power_usd) 중 작은 금액의 100% 전액으로 매수할 수 있는
    최대 정수 주식 수(allin_qty)와 실투입 원금(actual_spent_usd)을 반환한다.
    """
    exec_p = safe_float(price_t, 0.0)
    if exec_p <= 0.0:
        return 0, 0.0

    avail_cash = max(0.0, safe_float(free_cash_usd, 0.0))
    if broker_buying_power_usd is not None:
        bp_val = safe_float(broker_buying_power_usd, 0.0)
        if bp_val > 0.0:
            avail_cash = min(avail_cash, bp_val)

    eff_rt_pct = resolve_effective_round_trip_fee_rate_pct(
        round_trip_fee_rate_pct
    )
    fee_mult = 1.0 + (eff_rt_pct / 100.0)
    unit_cost_with_fee = exec_p * fee_mult
    if avail_cash < unit_cost_with_fee:
        return 0, 0.0

    allin_qty = max(
        0, int(math.floor((avail_cash + 1e-9) / unit_cost_with_fee))
    )
    actual_spent_usd = (
        round(float(allin_qty) * exec_p, 4) if allin_qty > 0 else 0.0
    )
    return allin_qty, actual_spent_usd


def evaluate_golden_allin_signal(
    hm: int,
    rsi_14: float,
    live_price: float,
    golden_allin_mode: str = DEFAULT_GOLDEN_ALLIN_MODE,
    today_str: str = "",
    last_golden_allin_date: str = "",
    golden_pocket: Optional[Any] = None,
    rsi_ready: bool = True,
) -> Dict[str, Any]:
    """
    # [Case 80 : 미동부 프리장 황금시간대(07:00 ~ 07:50 EST) & RSI(14) <= 19.0 가용시드 100% 전액 추가매수 판정기]:
    """
    mode = str(golden_allin_mode or DEFAULT_GOLDEN_ALLIN_MODE).upper().strip()
    if mode not in GOLDEN_ALLIN_MODES:
        mode = DEFAULT_GOLDEN_ALLIN_MODE

    hm_int = safe_int(hm, 0)
    rsi_val = round(safe_float(rsi_14, 50.0), 2)
    lp = safe_float(live_price, 0.0)
    in_window = bool(GOLDEN_WINDOW_START_HM <= hm_int <= GOLDEN_WINDOW_END_HM)
    gp = pocket_from_dict(golden_pocket)
    lot_tag = "GOLDEN_POCKET" if mode == "POCKET_ALLIN" else "GOLDEN_L1"

    if mode == "NONE":
        return {
            "should_buy": False,
            "mode": mode,
            "lot_type": "",
            "reason": "MODE_OFF",
            "in_window": in_window,
            "rsi_14": rsi_val,
            "rsi_threshold": GOLDEN_RSI_MAX_THRESHOLD,
        }

    if not in_window:
        return {
            "should_buy": False,
            "mode": mode,
            "lot_type": lot_tag,
            "reason": "OUTSIDE_GOLDEN_WINDOW",
            "in_window": False,
            "rsi_14": rsi_val,
            "rsi_threshold": GOLDEN_RSI_MAX_THRESHOLD,
        }

    if (
        today_str
        and str(last_golden_allin_date or "").strip() == str(today_str).strip()
    ):
        return {
            "should_buy": False,
            "mode": mode,
            "lot_type": lot_tag,
            "reason": "ALREADY_EXECUTED_TODAY",
            "in_window": True,
            "rsi_14": rsi_val,
            "rsi_threshold": GOLDEN_RSI_MAX_THRESHOLD,
        }

    if mode == "POCKET_ALLIN" and gp.is_active:
        return {
            "should_buy": False,
            "mode": mode,
            "lot_type": lot_tag,
            "reason": "GOLDEN_POCKET_ALREADY_HELD",
            "in_window": True,
            "rsi_14": rsi_val,
            "rsi_threshold": GOLDEN_RSI_MAX_THRESHOLD,
        }

    if lp <= 0.0 or not rsi_ready or rsi_val <= 0.0:
        return {
            "should_buy": False,
            "mode": mode,
            "lot_type": lot_tag,
            "reason": "RSI_OR_PRICE_NOT_READY",
            "in_window": True,
            "rsi_14": rsi_val,
            "rsi_threshold": GOLDEN_RSI_MAX_THRESHOLD,
        }

    if rsi_val <= GOLDEN_RSI_MAX_THRESHOLD:
        return {
            "should_buy": True,
            "mode": mode,
            "lot_type": lot_tag,
            "reason": f"GOLDEN_{mode}_RSI_{rsi_val:.1f}",
            "in_window": True,
            "rsi_14": rsi_val,
            "rsi_threshold": GOLDEN_RSI_MAX_THRESHOLD,
        }

    return {
        "should_buy": False,
        "mode": mode,
        "lot_type": lot_tag,
        "reason": "HOLD_RSI_ABOVE_19",
        "in_window": True,
        "rsi_14": rsi_val,
        "rsi_threshold": GOLDEN_RSI_MAX_THRESHOLD,
    }


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
    # MODIFIED [Case 77 : 💉 05_RESV_6P_GUARD30 — 30% 자투리 1주 승격 방지 가드 & 온디맨드 예비시드 자동 수혈 판정기 (계좌별 동적 수수료율 반영)]:
    """
    f_cash = max(0.0, safe_float(free_cash_usd, 0.0))
    ex_p = max(0.01, safe_float(exec_price, 0.01))
    p_bud = max(0.01, safe_float(portion_budget, 800.0))
    l1_cost = max(0.0, safe_float(l1_actual_cost_usd, 0.0))
    used_cnt = max(0, safe_int(used_reserve_portions_cnt, 0))
    max_res = max(0, safe_int(max_reserve_portions, MAX_RESERVE_PORTIONS))
    rem_portions = max(0, max_res - used_cnt)

    eff_rt_pct = resolve_effective_round_trip_fee_rate_pct(
        round_trip_fee_rate_pct
    )
    fee_mult = 1.0 + (eff_rt_pct / 100.0)
    one_share_cost = ex_p * fee_mult

    bud_ratio = max(0.0, safe_float(min_dip_budget_ratio, MIN_DIP_BUDGET_RATIO))
    l1_ratio = max(0.0, safe_float(min_dip_vs_l1_ratio, MIN_DIP_VS_L1_RATIO))
    tol_ratio = max(
        0.50,
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
        rem_portions >= needed_portions
        and eff_bp >= min_req_cash
        and unallocated_deposit_usd >= (required_inj_usd * tol_ratio)
    ):
        if unallocated_deposit_usd >= required_inj_usd:
            actual_inj_usd = required_inj_usd
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
                "rem_portions_before": rem_portions,
                "rem_portions_after": rem_portions - needed_portions,
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
) -> Dict[str, Any]:
    """
    # [Case 77 : 0주 전량 졸업 시 온디맨드 예비시드 원금 자동 상환 및 6회분 한도 복구 연산기]:
    """
    init_seed = max(
        100.0, safe_float(initial_seed_usd, DEFAULT_INITIAL_SEED_USD)
    )
    cum_net = round(safe_float(cumulative_realized_net_usd, 0.0), 4)
    inj_usd = round(max(0.0, safe_float(injected_reserve_usd, 0.0)), 4)
    used_cnt = max(0, safe_int(used_reserve_portions_cnt, 0))
    max_res = max(1, safe_int(max_reserve_portions, MAX_RESERVE_PORTIONS))

    total_cash_before = round(max(0.0, init_seed + cum_net + inj_usd), 4)
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
        est_portion_unit = max(1.0, (init_seed + max(0.0, cum_net)) * 0.08)
        rem_used_cnt = max(
            1,
            min(
                used_cnt if used_cnt > 0 else max_res,
                int(math.ceil(rem_inj_usd / est_portion_unit)),
            ),
        )

    free_cash_after = round(max(0.0, init_seed + cum_net + rem_inj_usd), 4)
    return {
        "did_repay": bool(repaid_usd > 0.0),
        "repaid_usd": repaid_usd,
        "rem_injected_reserve_usd": rem_inj_usd,
        "rem_used_reserve_portions_cnt": rem_used_cnt,
        "avail_reserve_portions": max(0, max_res - rem_used_cnt),
        "free_cash_after_repay_usd": free_cash_after,
    }


# ---------------------------------------------------------------------------
# [핵심 3] 보유 회차별 4단 와이드 점진 단차 · 하이브리드 1층 재장전(Case 84 돌파차단 포함) · STEP2X_15PCT_C20 스텝업 해금 판정기 (Case 36 ~ 85)
# ---------------------------------------------------------------------------
def get_golden8_prog_thresholds(
    held_lots: int,
    threshold_mode: str = "WIDE_RUNWAY",
) -> Tuple[float, float, float]:
    """
    🎯 2 & Case 36 ~ 45, 60, 71, 72 : 4단 와이드 점진 활주로
    """
    lots = max(1, safe_int(held_lots, 1))
    if lots <= 4:
        drop_buy_pct = -1.00
    elif lots <= 8:
        drop_buy_pct = -2.00
    elif lots <= 10:
        drop_buy_pct = -3.50
    else:
        drop_buy_pct = -5.50

    mode = str(threshold_mode or "WIDE_RUNWAY").upper().strip()
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
) -> Dict[str, Any]:
    """
    # [🎯 4 & Case 59, Case 67, Case 71, Case 72, Case 73 & Case 84]:
    """
    lp = safe_float(live_price, 0.0)
    anc = safe_float(anchor_price, 0.0)
    b2_p = safe_float(l2_book_price, 0.0)
    ceil_p = safe_float(min_upper_tier_price, 0.0)
    if ceil_p <= 0.0 and b2_p > 0.0:
        ceil_p = b2_p

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
        }

    chg_from_exit_pct = ((lp - ref_anchor) / ref_anchor) * 100.0

    # 🚨 [Case 73 핵심 방어 : 현재가 > 2층 단가(ceil_p) 시 1층 > 2층 단가 역전 원천 차단 (후자)]
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
        }

    # 조건 A : -1.00% 이하 눌림목 재장전 (15:30 ~ 16:00 EST 구간 포함 전 매수 구간 100% 정상 허용)
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
        }

    # 조건 B : +1.00% 이상 상승돌파 재장전 (Case 84 : 15:30 ~ 16:00 EST 구간에서는 돌파 추격 차단!)
    if chg_from_exit_pct >= REENTRY_BREAKOUT_RISE_PCT:
        if is_late_new_cycle_cutoff:
            return {
                "should_buy": False,
                "signal_type": "HOLD_LATE_SESSION_BREAKOUT_CUTOFF",
                "ref_anchor": round(ref_anchor, 4),
                "quota_ref_price": round(ref_anchor, 4),
                "chg_from_exit_pct": round(chg_from_exit_pct, 2),
                "pullback_target_price": pullback_target_p,
                "breakout_target_price": breakout_target_p,
                "l2_ceiling_price": round(ceil_p, 4),
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
    """
    # [🎯 2 Step 1 & Case 60, Case 72, Case 76 : 🔓 06_STEP2X_15PCT_C20 3중 안전문 기반 조건부 스텝업 저가 해금 판정기]:
    """
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

    # 1) 제1경로 : 기본 정적 최저가 대비 4단 와이드 신저가 도달 시 최우선 승인
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

    # 2) 제2경로 : 3중 안전문(step_up_eligible) 통과 & 현재가가 활성 1층 대비 -15.0%(stepped_min_p) 이하 도달 시 스텝업 해금 승인!
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
