# -*- coding: utf-8 -*-
"""
# MODIFIED: quant_engine_core.py
인피니트 스노우볼 (Infinite Snowball) v3.0 — 퀀트 엔진 코어 Part 1 / 2 (Step 02 / 09)
역할:
1) 전역 퀀트 상수 락온 (8% 황금비율 · 7-Layer 골디락스 그리드 · STEP2X_15PCT_C20 · GUARD30 예비수혈 · 황금시간 전액매수 기본값 NONE[OFF] · Case 84 15:30 컷오프)
2) 순수 실물 매수 원가(book_price == actual_avg_price) 구조체 (StratumBucket, GoldenAllInPocket) 및
   상단 그리드(2층 ~ 6층 개별 완충층 + 통합 7층 본대 GRID_L7) 번호 정규화·합병기(relabel_upper_grid_tiers)
3) 8%(12.5분할) 황금비율 정액 기반 정량 산출기(min(1회분 예산 상한 주수, 기준가 고정 정량) 이중 캡핑 Case 67) 및
   황금시간대(07:00 ~ 07:50 EST & 1분봉 Wilder RSI(14) <= 19.0) 가용현금 100% 전액매수 판정기(Case 80)
4) 30% 자투리 1주 승격 방지 가드(GUARD30) & 토스 실계좌 여유자금 감지 기반 최대 +6회분 온디맨드 예비시드 자동 수혈 판정기 및
   0주 전량 졸업 시 예비시드 원금 자동 상환 연산기(Case 77)
5) 보유 회차별 4단 와이드 점진 활주로(1~4회 -1.0% / 5~8회 -2.0% / 9~10회 -3.5% / 11회+ -5.5%) ·
   1층 공석 시 2층 단가 상한 역전 차단(HOLD_PREVENT_INVERSION · Case 73) 및
   정규장 마감 30분 전(15:30 ~ 16:00 EST) +1.00% 상승돌파 추격 차단(HOLD_LATE_SESSION_BREAKOUT_CUTOFF · Case 84) 기반 하이브리드 재장전 판정기 ·
   3중 안전문(보유 2층 이하 & 현금비중 20%+ & 저점대비 2.0배+ 반등) 통과 시 -15.0% 스텝업 저가 해금 판정기(Case 76)
- 제1헌법 ~ 제6헌법 및 Case 01 ~ 84 완벽 준수
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

# NEW [Case 84]: 정규장 마감 30분 전(15:30 ~ 16:00 EST) 0주 새 사이클 1층 진입 및 1층 공석 +1.0% 돌파 추격 차단 기준 시각(HHMM)
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
# [핵심 1] StratumBucket & GoldenAllInPocket : 순수 실물 매수 원가(book_price == actual_avg_price) 구조체 (Case 46 ~ 84)
# ---------------------------------------------------------------------------
@dataclass
class StratumBucket:
    """
    🎯 3 & Case 46 ~ 84:
    SOXL 1층 ~ 7층 골디락스 멀티 그리드(1층 공격수 L1 / 2층 ~ 6층 개별 완충층 GRID_L2 ~ GRID_L6 / 통합 7층 본대 GRID_L7) 데이터 구조체.
    - qty              : 보유 정수 주식 수 (주)
    - book_price       : 목표 탈출 기준 단가 ($, 순수 원가 모드에서는 actual_avg_price 와 100% 동일)
    - book_invested_usd: 장부상 투자금 ($, 순수 원가 모드에서는 actual_cost_usd 와 100% 동일)
    - actual_cost_usd  : 실제 가용 현금 시드에서 지출된 순수 매수 원금 ($, 회계 항등식 보존용)
    - lot_count        : 해당 그리드 층에 포함된 누적 매수 회차 수 (1~6층은 개별 회차, 7층은 7회차 이상 통합 회차 수)
    - lot_type         : 지층 성격 태그 ("REENTRY_1FL", "TOPUP_1FL", "DIP_1FL", "GOLDEN_L1", "QUOTA_L1", "MANUAL_SYNC_L1", "GRID_L2" ~ "GRID_L7")
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
        # Case 69, Case 71 & Case 72: 순수 매수 원가(a_cost) 기준으로 단가와 장부원금을 100% 일치시켜 원가 훼손 원천 차단
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
    - lot_type 이 "MERGED_UPPER" 이거나 "GRID_L2" ~ "GRID_L7" (즉, "GRID_L" 로 시작하되 "GRID_L1" 이 아닌 경우)이면
      상단 그리드(2층 ~ 7층) 버킷이므로 True 를 반환한다.
    - "REENTRY_1FL", "TOPUP_1FL", "DIP_1FL", "GOLDEN_L1", "QUOTA_L1", "MANUAL_SYNC_L1", "SYNCED_1FL", "GRID_L1" 등은
      최하단 활성 공격수 1층이므로 False 를 반환한다.
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
    - buckets 가 비어 있지 않고 맨 앞(buckets[0])이 상단 그리드(GRID_L2 ~ GRID_L7 / MERGED_UPPER)가 아니면
      현재 활성 1층 공격수가 존재하는 상태(True)이다.
    - 만약 1층이 익절되어 빠져나가고 buckets[0] 이 GRID_L2(또는 MERGED_UPPER)라면
      현재 1층이 공석이고 상단 2층 ~ 7층 그리드만 보유 중인 상태(False)이다!
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
    1층(공격수)을 제외한 상단 그리드 버킷 리스트를 받아:
    - max_upper_cnt = max_tiers - 1 (기본 6개 : GRID_L2 ~ GRID_L7) 기준으로
    - 2층 ~ 6층(GRID_L2 ~ GRID_L6, 5개 완충층)은 개별 순수 원가를 100% 분리 보존하고,
    - 7층을 초과하는 물량(valid[5:])은 최상단 '통합 7층 본대(GRID_L7)'로 가중평균 합병(Case 53 하드 캡핑 적용)하여 반환한다.
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
    인위적 리앵커링 차감을 수행하지 않으므로,
    모든 보유 지층(1층 ~ 7층)의 book_invested_usd 와 book_price 가 실제 매수 원금(actual_cost_usd / actual_avg_price)
    밑으로 절대 내려가지 못하도록 100% 순수 원가 하한선을 강제한다.
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

    # 🚨 Case 67: 실제 매수가(exec_price)가 기준가보다 높을 때 1회분(8%) 예산 초과 원천 차단!
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
) -> Tuple[int, float]:
    """
    🚨 Case 25 ~ 35 & Case 67:
    직전 기준가로 산출된 목표 정량(target_qty)을 실제 주문가(price_t)로 매수하기 직전:
    1) max_portion_budget_usd(1회분 8% 예산) 상한 주수(budget_cap_qty)와 target_qty 중 작은 값으로 캡핑한다.
    2) 왕복 수수료 버퍼(0.14%)를 감안한 가용 현금(free_cash_usd) 및 토스 실계좌 매수가능금액 한도 내로 캡핑한다.
    반환값: (buy_qty, actual_spent_usd)
    """
    t_qty = max(0, safe_int(target_qty, 0))
    exec_p = safe_float(price_t, 0.0)
    if t_qty <= 0 or exec_p <= 0.0:
        return 0, 0.0

    # 🚨 Case 67: 1회분(8%) 예산 상한 주수(budget_cap_qty) 하드 캡핑
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

    fee_mult = 1.0 + (ROUND_TRIP_FEE_RATE_PCT / 100.0)
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
) -> Tuple[int, float]:
    """
    # [Case 80 : 황금시간대(07:00 ~ 07:50 EST & RSI <= 19.0) 가용 현금 시드 100% 전액 매수 주수 산출기]:
    왕복 수수료 버퍼(0.14%)를 감안하여 현재 가용 현금(free_cash_usd)과 토스 실계좌 주문가능 달러(broker_buying_power_usd) 중
    작은 금액의 100% 전액으로 매수할 수 있는 최대 정수 주식 수(allin_qty)와 실투입 원금(actual_spent_usd)을 반환한다.
    """
    exec_p = safe_float(price_t, 0.0)
    if exec_p <= 0.0:
        return 0, 0.0

    avail_cash = max(0.0, safe_float(free_cash_usd, 0.0))
    if broker_buying_power_usd is not None:
        bp_val = safe_float(broker_buying_power_usd, 0.0)
        if bp_val > 0.0:
            avail_cash = min(avail_cash, bp_val)

    fee_mult = 1.0 + (ROUND_TRIP_FEE_RATE_PCT / 100.0)
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
    1) 제어반 선택 모드(golden_allin_mode)가 "NONE" (기본값 OFF)이면 즉시 should_buy=False ("MODE_OFF")를 반환한다.
    2) 미동부 프리장 07:00 ~ 07:50 EST (700 <= hm <= 750) 구간인지 확인한다.
    3) 당일 이미 황금시간 전액매수를 실행했는지(last_golden_allin_date == today_str) 확인한다(1일 최대 1회).
    4) POCKET_ALLIN 모드인 경우 현재 미청산 골든포켓 물량(gp.qty > 0)이 남아 있으면 중복 진입을 차단한다.
    5) 1분봉 Wilder's RSI(14)가 유효(rsi_ready == True)하고 0.0 < rsi_14 <= 19.0 (GOLDEN_RSI_MAX_THRESHOLD) 이하이면
       전액 매수(lot_type="GOLDEN_POCKET" 또는 "GOLDEN_L1")를 승인한다!
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
) -> Dict[str, Any]:
    """
    # [Case 77 : 💉 05_RESV_6P_GUARD30 — 30% 자투리 1주 승격 방지 가드 & 토스 실계좌 여유자금 감지 기반 최대 +6회분 온디맨드 예비시드 자동 수혈 판정기]:
    매수 타점(0주 진입 / 황금시간 전액매수 / 1층 공석 재장전 / 10분 와이드·스텝업 추매) 도달 시:
    1) [30% 자투리 승격 방지 가드 최소 필요 현금(min_req_cash) 산출]:
       - 추매(is_dip_promotion == True) 시:
         min_req_cash = max(1주 수수료포함 비용, portion_budget * 0.30, l1_actual_cost_usd * 0.30)
       - 1층 공석 재장전, 황금시간 전액매수 또는 0주 진입(is_dip_promotion == False) 시:
         min_req_cash = max(1주 수수료포함 비용, portion_budget * 0.30)
    2) [정상 진행 판정 (PROCEED_NORMAL)]
    3) [온디맨드 예비시드 자동 수혈 판정 (INJECT_AND_PROCEED)]
    4) [미입금 시 자투리 매수 차단 및 입금 요청 알림 트리거 (BLOCK_AND_ALERT_DEPOSIT)]
    """
    f_cash = max(0.0, safe_float(free_cash_usd, 0.0))
    ex_p = max(0.01, safe_float(exec_price, 0.01))
    p_bud = max(0.01, safe_float(portion_budget, 800.0))
    l1_cost = max(0.0, safe_float(l1_actual_cost_usd, 0.0))
    used_cnt = max(0, safe_int(used_reserve_portions_cnt, 0))
    max_res = max(0, safe_int(max_reserve_portions, MAX_RESERVE_PORTIONS))
    rem_portions = max(0, max_res - used_cnt)

    fee_mult = 1.0 + (ROUND_TRIP_FEE_RATE_PCT / 100.0)
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

    # 1) 현재 가용현금이 min_req_cash 이상이고 실계좌 예수금도 충분한 경우 -> 정상 매수 진행
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

    # 2) f_cash < min_req_cash (시드고갈 / 30% 자투리 가드 감지) -> 온디맨드 예비시드 수혈 가능 여부 확인
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
        # 사용자가 토스 계좌에 1회분 이상 여유자금을 입금해 둔 상태 -> 즉시 자동 수혈 승인!
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

    # 3) 토스 계좌에 아직 여유자금이 입금되지 않았거나 예비 한도(6회분)가 모두 소진된 경우 -> 자투리 차단 & 입금 요청
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
    스나이퍼 자동 매도 또는 수동 전량 청산으로 보유 지층 및 골든포켓이 0주가 되었을 때:
    - 수혈받았던 예비시드 잔액(injected_reserve_usd > 0.0)이 존재하면,
      상환 전 총 현금 풀(total_cash_before = initial_seed_usd + cumulative_realized_net_usd + injected_reserve_usd)에서
      기본 시드(initial_seed_usd)를 초과하는 여유 현금 범위 내에서 injected_reserve_usd 를 즉시 분리 상환한다.
    - 전액 상환 완료 시 injected_reserve_usd = 0.0 및 used_reserve_portions_cnt = 0 으로 초기화하여
      6/6회분 예비 한도를 100% 원상 복구한다!
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
# [핵심 3] 보유 회차별 4단 와이드 점진 단차 · 하이브리드 1층 재장전(Case 84 돌파차단 포함) · STEP2X_15PCT_C20 스텝업 해금 판정기 (Case 36 ~ 84)
# ---------------------------------------------------------------------------
def get_golden8_prog_thresholds(
    held_lots: int,
    threshold_mode: str = "WIDE_RUNWAY",
) -> Tuple[float, float, float]:
    """
    🎯 2 & Case 36 ~ 45, 60, 71, 72 : 4단 와이드 점진 활주로:
    현재 보유 중인 총 투입 회차(held_lots)에 따른:
    1) 10분 시드보호 매수 게이트 요구 하락률(drop_buy_pct):
       -  1 ~  4회차 보유 중 : -1.00%
       -  5 ~  8회차 보유 중 : -2.00%
       -  9 ~ 10회차 보유 중 : -3.50%
       - 11회차 이상 보유 중 : -5.50%
    2) 실시간 스나이퍼 매도 모니터 목표 상승률(rise_sell_l1_pct, rise_sell_upper_pct):
       - 1층(공격수) 및 골든포켓 +1.50% / 2층 ~ 7층(개별 완충층·통합 7층 및 상단 통합 이동평균) +1.00%
    반환값: (drop_buy_pct, rise_sell_l1_pct, rise_sell_upper_pct)
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
    # MODIFIED [🎯 4 & Case 59, Case 67, Case 71, Case 72, Case 73 & Case 84]:
    1층이 실물 익절되어 장부에 상단 그리드(2층 ~ 7층)만 남아 1층이 공석일 때,
    매도 후 60.0초 타임쉴드 및 매 60.0초(1분) 타임쉴드 주기마다 호출되는 하이브리드 독립 1층 재장전 판정기:
    1) 🛡️ [Case 73 단가 역전 원천 차단 가드 (HOLD_PREVENT_INVERSION · 후자)]:
       실시간 현재가(lp)가 상단 최하단 층인 2층 단가(ceil_p = min_upper_tier_price)보다 높으면
       (lp > ceil_p + 1e-6), 새로 매수할 1층 공격수 단가가 2층 단가보다 비싸지는 단가 역전(1층 > 2층) 및
       고점 중복 매수를 막기 위해 즉시 매수를 패스(should_buy = False, signal_type = "HOLD_PREVENT_INVERSION")하고
       실시간 매도 모니터가 수익권에 들어선 2층(+1.00%)을 익절하도록 위임한다!
    2) 🎯 [현재가 <= 2층 단가 안전 영역 내 눌림목(-1.00%) OR 상승돌파(+1.00%) 타점 판정 & Case 84 장마감 30분전 돌파 차단]:
       - 조건 A (눌림목 재장전 : chg_from_exit <= -1.00% & lp <= ceil_p) -> 04:07 ~ 16:00 EST 전 구간 PULLBACK_RELOAD 승인!
       - 조건 B (상승돌파 재장전 : chg_from_exit >= +1.00% & lp <= ceil_p) ->
         정규장 마감 30분 전(15:30 ~ 16:00 EST, is_late_new_cycle_cutoff == True) 구간에서는
         장 막판 고점 추격을 막기 위해 HOLD_LATE_SESSION_BREAKOUT_CUTOFF 로 즉시 차단하고,
         04:07 ~ 15:29 EST 구간에서만 BREAKOUT_RELOAD 로 독립 실물 1층(REENTRY_1FL) 재장전을 승인한다!
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
    활성 1층 보유 중(has_active_l1_bucket(buckets) == True) 04:07 EST 기점 10분 고정 매수 게이트 도래 시:
    1) [제1경로 : 기본 정적 신저가 추매 판정]
    2) [제2경로 : 정적 신저가 미달 시 🔓 06_STEP2X_15PCT_C20 3중 안전문 스텝업 해금 판정]
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
