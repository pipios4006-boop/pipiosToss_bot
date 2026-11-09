# -*- coding: utf-8 -*-
"""
# MODIFIED: assassin_plugin.py (Part 1/3 — 🗡️ [모의 ⇄ 실전 Dual-Ready] 암살자 독립 플러그인 · 변형 선택지 A [정책 4 진입 : PRE10_SYNC + 5분 SMART_WAIT 스마트 진바닥 대기 + DL_G6 프리장 강세 급눌림 진바닥 + 08:30~09:20 EST DL10 거시지표 무패 진바닥(16전 16승) 및 09:21 최종 퇴근] × [2단 하이브리드 래칫 : +1.00% 1차 보존선 하드 잠금(HA음봉 무시 홀딩) ➔ +1.25% 2차 보존선 격상 및 0.40초 HA음봉/콜백 부스트 점화] × [장중 HOLD : 오전 개장 흔들기 손절 OFF & 15:00 수익권 정규VWAP 탈출 / 15:59 2단계 방탄 MOC] 탑재 · 작동 게이트 및 진입➔청산 복기 일지 trade_journal_history 영속화 · 프리시가/프리VWAP 무오염 2단계 하이브리드 원장 박제 · 400봉 상한 연동 · Case 93)
인피니트 스노우볼 (Infinite Snowball) v3.0 — 스나이퍼와 100% 물리적 격리된 상시 가동 [모의 ⇄ 실전 Dual-Ready] 암살자(Assassin) 코어 모듈 (Step 10 / 14 · Case 93)
- 역할:
  1) 스나이퍼 원장(soxl_stratum_ledger*.json) 및 예수금과 100% 물리적 분리된 독립 3중 원장(AssassinSimLedger : assassin_sim_ledger_{folder_slug}.json) 운용 ·
     프리장(04:07 ~ 09:29 EST) 중 실측된 진성 프리시가(today_pre_open_price) 및 프리VWAP(today_premarket_vwap) 영속화 박제 ·
     장 마감 후 최초 기동 등 당일 프리장 데이터 미확보 시 정규장 가격 가짜 폴백 없이 $0.00 (0.00%) 무오염 표출 및 구버전 오염 원장 자동 자가 치유
  2) 현재 ASSASSIN_LIVE_ORDER_HARD_LOCK = True 로 실전 주문 발사를 물리적으로 100% 차단하되,
     내부 주문 상태 머신(매수 발주 · +5.00% 상단 안전 캡 선장전 · +1.00% 1차 잠금 ➔ +1.25% 2차 부스트 점화 HA 트레일링 modify_order 가격 정정 스윕 · 15:59 2단계 방탄 MOC)은
     토스증권 Open API v1.2.14 실전 규격과 100% 동일하게 구현하여 스위치 해금 즉시 실전 암살자로 탈바꿈 가능
  3) 평일 04:07 ~ 08:14 EST 골든타임 1주 가상 독립 정찰병(IndependentScoutUnit · 실제 매수 없음 · 이동평균 및 합병 100% 배제) 파견 및 4대 지표(① RSI14 · ② 프리VWAP · ③ 전일종가 · ④ 04:07프리시가) 기록
  4) 👑 [정책 4 : 3단계 시계열 연쇄 진입 엔진 (SMART_WAIT + DL_G6 + DL10)]
     - 1단계 (04:07 ~ 08:14 EST · PRE10_SYNC + SMART_WAIT) : 10분 와이드 정찰(#2+) 및 T03_A(#1 파견 후 저점 -1.00% 이하 매 1분 스캔)에서 10대 진성 게이트(G1~G5 + BG1~BG5) 점등 시,
       이미 프리장 고점 대비 -1.80% 이하 진바닥이거나 1분봉 양봉이면 즉시 100% 진입하고, 낙폭이 얕은 음봉 칼날이면 최대 5분(300초)간 스마트 대기(SMART_WAIT) 후 첫 양봉/QQQ반등/진바닥 도달 시 더 낮은 단가로 즉시 진입
     - 2단계 (04:07 ~ 08:14 EST · DL_G6 강세장 급눌림 진바닥) : 전일 종가 대비 강세 출발일 사각지대를 보완하는 고점 대비 -2.50% & 시가 <= -1.50% & VWAP <= -1.50% & RSI <= 27.5 & 양봉+QQQ반등 타점 포착
     - 3단계 (08:30 ~ 09:20 EST · DL10 거시지표 발표 직후 무패 진바닥) : 08:14 EST 까지 프리장 무매매일 때 08:30 ~ 09:20 EST 동안 RSI <= 24.0 & 프리VWAP <= -2.00% & 5분 급락 <= -1.20% 직후 첫 양봉+QQQ반등(+0.02%+) 포착 시 100% 진입(16전 16승 무패) · 09:21 EST 최종 무매매 안전 퇴근
  5) 🏆 [변형 선택지 A : 2단 하이브리드 래칫 (+1.00% 1차 잠금 ➔ +1.25% 2차 부스트) + 장중 HOLD 출구 엔진]
     - 구간 1 (미점화 · +0.00% ~ +0.99%) : 장중 안전망 조기 손절 OFF(ASSASSIN_SAFETY_HOLD_MODE = True)로 오전 개장 언더슈팅을 견디고 평균회귀를 기다리며, 15:00 ~ 15:58 EST 수익권(>= +0.20%) & 정규VWAP 이상 도달 시 익절 탈출 / 15:59 EST 무오버나이트 MOC 청산
     - 구간 2 (1차 잠금 · +1.00% ~ +1.24%) : +1.00%(arm_100_price) 도달 즉시 1차 최소익절 바닥(+1.00%)을 하드 잠그되, +1.24% 까지는 1분봉 HA 음봉이 나와도 털리지 않고 홀딩하며 다시 +1.00% 가격까지 내려올 때만 +1.00% 구출 익절(TRAIL_FLOOR_100)
     - 구간 3 (2차 부스트 점화 · +1.25% 이상) : +1.25%(arm_125_price) 돌파 즉시 최소익절 보존선을 +1.25% 로 2차 격상(TRAIL_FLOOR_125)하고, 최고가 콜백(-0.20% / +2% 이상 시 -0.30%) 및 1분봉 HA 음봉 전환(QQQ 급등 시 바이패스) 시 즉시 고수익 부스트 익절!
  6) 📋 [데이터 수집 강화] 5대 실시간 텔레그램 푸시 알림 + 청산 시 [진입 ➔ 청산 복기 스냅샷] 통합 타전 + 원장 trade_journal_history 최근 50건 자동 누적 및 /assassin 상세 관제 보드 제공
"""

from __future__ import annotations

import asyncio
import copy
import errno
import html
import json
import logging
import math
import os
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from quant_engine import (
    calc_sell_realized_pnl,
    get_golden8_prog_thresholds,
    get_runtime_round_trip_fee_rate_pct,
    get_runtime_us_commission_rate,
)
from quant_indicators_plugin import (
    compute_qqq_macro_metrics_1m,
    compute_soxl_quant_metrics_1m,
    evaluate_buy_gate_bucket_status,
    is_weekend_nyse_closed,
    refresh_metrics_with_live_tick,
)
from toss_api import (
    DEFAULT_INITIAL_SEED_USD,
    DEFAULT_US_COMMISSION_RATE,
    EST_TZ,
    GlobalThrottle,
    KRW_PER_USD_DEFAULT,
    LOCKED_BUY_INTERVAL_MIN,
    ROUND_TRIP_FEE_RATE_PCT,
    TARGET_SYMBOL,
    emergency_free_disk_space_sync,
    generate_client_order_id,
    get_bot_base_dir,
    get_folder_slug,
    safe_float,
    safe_int,
)

logger = logging.getLogger("toss_sniper.assassin_plugin")

# ---------------------------------------------------------------------------
# [핵심 상수 · Case 93] [모의 ⇄ 실전 Dual-Ready] 물리적 하드 락 및 타임라인 상수
# ---------------------------------------------------------------------------
ASSASSIN_LIVE_ORDER_HARD_LOCK: bool = True
ASSASSIN_MODE_SIMULATED: str = "SIMULATED"
ASSASSIN_MODE_LIVE: str = "LIVE"

MACRO_REF_SYMBOL: str = "QQQ"

ASSASSIN_SCOUT_START_HM: int = 407         # 04:07 EST 첫 선봉 정찰병 출격
ASSASSIN_GOLDEN_END_HM: int = 814          # 08:14 EST 프리장 정찰 및 PRE10/DL_G6 마감
ASSASSIN_MACRO_CUTOFF_HM: int = 815        # 08:15 EST 프리장 정찰 종료 & DL10 대기 전환 시각
ASSASSIN_MACRO_DL10_START_HM: int = 830    # 08:30 EST 거시지표 발표 직후 무패 진바닥(DL10) 스캔 개시
ASSASSIN_MACRO_DL10_END_HM: int = 920      # 09:20 EST 거시지표 진바닥(DL10) 스캔 마감
ASSASSIN_FINAL_CUTOFF_HM: int = 921        # 09:21 EST 당일 최종 무매매 안전 퇴근 판정 시각
ASSASSIN_REGULAR_OPEN_HM: int = 930        # 09:30 EST 정규장 개장
ASSASSIN_VWAP_EXIT_START_HM: int = 1500    # 15:00 ~ 15:58 EST 수익권 정규장 VWAP 탈출 구간
ASSASSIN_MOC_EXIT_HM: int = 1559           # 15:59 ~ 16:01 EST 무오버나이트 2단계 방탄 MOC 강제 청산

SCOUT_MAX_INDEPENDENT_UNITS: int = 7       # 정찰병 최대 독립 보유 한도 (7명)
SCOUT_PROFIT_TARGET_PCT: float = 1.00      # 개별 정찰병 독립 익절 목표 (+1.00%)
SCOUT_PULLBACK_DROP_PCT: float = -1.00     # 정찰병 1층 공석 눌림목 (-1.00% 무필터)
SCOUT_BREAKOUT_RISE_PCT: float = 1.00      # 정찰병 1층 공석 돌파 (+1.00% & RSI<=50.0)
SCOUT_BREAKOUT_MAX_RSI: float = 50.0       # 정찰병 돌파 최대 허용 RSI(14)
SCOUT_TIME_SHIELD_SEC: float = 60.0        # 정찰병 매수/매도 후 60초 타임쉴드

# [Case 93 : T03_A_DIP10_ALL_SCOUT — 10분 정찰병 파견 유지 + 직전 정찰 저점 대비 -1.00% 눌림 구간 매 1분 상시 진성 게이트 10 스캔 상수 및 인메모리 래치]
SCOUT_T03A_DIP_SCAN_DROP_PCT: float = -1.00
SCOUT_T03A_DIP_SCAN_INTERVAL_SEC: float = 60.0
_LAST_T03A_DIP_SCAN_KEY: str = ""
_LAST_T03A_DIP_SCAN_TS: float = 0.0

# NEW [정책 4 : SMART_WAIT (스마트 진바닥 대기) · DL_G6 (강세장 급눌림 진바닥) · DL10 (08:30~09:20 거시지표 무패 진바닥) 상수]
SMART_WAIT_DEEP_DD_PCT: float = -1.80      # 프리장 고점 대비 -1.80% 이하 진바닥이면 대기 없이 즉시 진입
SMART_WAIT_MAX_SEC: float = 300.0          # 음봉 칼날 시 최대 5분(300초) 스마트 대기 후 첫 양봉/진바닥 진입
SMART_WAIT_EXTRA_DIP_RATIO: float = 0.992  # 대기 중 포착가 대비 -0.80% 추가 급락 시 즉시 바겐세일 진입

DL_G6_MAX_DD_HIGH_PCT: float = -2.50       # DL_G6: 프리장 고점 대비 낙폭 <= -2.50%
DL_G6_MAX_VS_PRE_OPEN_PCT: float = -1.50   # DL_G6: 04:07 프리장 시가 대비 <= -1.50%
DL_G6_MAX_VS_VWAP_PCT: float = -1.50       # DL_G6: 프리장 VWAP 괴리율 <= -1.50%
DL_G6_MAX_RSI_14: float = 27.5             # DL_G6: Wilder RSI(14) <= 27.5

DL10_MAX_RSI_14: float = 24.0              # DL10(08:30~09:20): Wilder RSI(14) <= 24.0
DL10_MAX_VS_VWAP_PCT: float = -2.00        # DL10(08:30~09:20): 프리장 VWAP 괴리율 <= -2.00%
DL10_MAX_VEL_5M_PCT: float = -1.20         # DL10(08:30~09:20): 직전 5분 급락률 <= -1.20%
DL10_MIN_QQQ_VEL_1M_PCT: float = 0.02      # DL10(08:30~09:20): QQQ 1분 변화율 >= +0.02% 반등 확인

# NEW & MODIFIED [변형 선택지 A : 2단 하이브리드 래칫 (+1.00% 1차 보존잠금 ➔ +1.25% 2차 부스트 점화) + 장중 HOLD 상수]
ASSASSIN_SAFE_CAP_PCT: float = 5.00        # 본대 진입 직후 상단 안전 캡 (+5.00%)
ASSASSIN_ARM_IGNITION_PCT: float = 1.00    # 1차 최소 수익 보존선 하드 잠금 (+1.00% · HA 음봉 무시 홀딩 구간)
ASSASSIN_STAGE2_BOOST_PCT: float = 1.25    # 2차 부스트 점화 및 보존선 2차 격상 (+1.25% · HA 음봉/콜백 부스트 개시)
ASSASSIN_BOOST_TIER2_PCT: float = 2.00     # +2.00% 이상 구간 콜백 완화 기준
ASSASSIN_CALLBACK_TIGHT_PCT: float = 0.20  # +1.25% ~ +1.99% 구간 최고가 대비 콜백 (-0.20%p)
ASSASSIN_CALLBACK_WIDE_PCT: float = 0.30   # +2.00% 이상 구간 최고가 대비 콜백 (-0.30%p)
ASSASSIN_QQQ_SURGE_BYPASS_PCT: float = 0.20  # QQQ 3m/10m 변화율 >= +0.20% 급등 시 HA 음봉 매도 보류

# 장중 안전망 HOLD 모드 (True = 장중 개장 흔들기 바닥 손절 OFF · 15:00 수익권 정규VWAP 탈출 및 15:59 MOC로 평균회귀 수확)
ASSASSIN_SAFETY_HOLD_MODE: bool = True
SAFETY_NET_MODE_DEFAULT: str = "RATCHET_100_125_HOLD_POLICY4"
SAFETY_QQQ_BASE_AMP_PCT: float = 2.00
SAFETY_QQQ_AMP_CUT_RATIO: float = 0.50
SAFETY_DYN_QQQ_MIN_THR_PCT: float = 1.00
SAFETY_DYN_QQQ_MAX_THR_PCT: float = 1.00
SAFETY_STAGE1_HEART_STOP_PCT: float = -3.00
SAFETY_STAGE23_SOXL_LOSS_MAX_PCT: float = -1.50
SAFETY_STAGE23_QQQ_VEL3M_DROP_PCT: float = -0.25

ASSASSIN_MAX_JOURNAL_HISTORY: int = 50     # 원장 내 최근 매매 복기 일지 최대 보관 건수 (50건)


def _is_collapsed_assassin_anchors(
    prev_c: float, pre_o: float, pre_v: float
) -> bool:
    """
    # MODIFIED [Case 93 : 3대 가격 앵커(전일종가 · 04:07프리시가 · 프리VWAP)가 모두 양수이면서 단일 현재가 폴백값으로 오염되었는지 판별]:
    pre_o == 0.0 또는 pre_v == 0.0 은 프리장 미확보($0.00 표출) 정상 상태이므로 False 를 반환한다.
    """
    if prev_c <= 0.0 or pre_o <= 0.0 or pre_v <= 0.0:
        return False
    return bool(
        abs(prev_c - pre_o) < 1e-6 and abs(pre_v - prev_c) < 1e-6
    )


# ---------------------------------------------------------------------------
# [핵심 1] 1주 가상 독립 정찰병 데이터 구조 (IndependentScoutUnit — 실제 매수 없음 · 이동평균·합병 100% 배제)
# ---------------------------------------------------------------------------
@dataclass
class IndependentScoutUnit:
    """
    # [Case 93 : 1주 가상 독립 정찰병 객체]:
    실제 매수를 수행하지 않는 [모의] 가상 정찰병으로, 평균단가 합산이나 지층 합병 없이
    각 정찰병이 독립된 1주 단위로 자신의 진입가(entry_price), 목표 익절가(target_price = ceil(entry_price * 1.01 * 100) / 100),
    그리고 파견 시점의 4대 핵심 지표(① rsi_14 · ② pre_vwap / vs_vwap_pct · ③ prev_reg_close / vs_prev_close_pct · ④ pre_open_price / vs_pre_open_pct)를 보존한다.
    """

    scout_id: int
    tier_slot: int
    entry_type: str
    entry_time_est: str
    entry_ts: float
    entry_price: float
    target_price: float
    qty: int = 1
    rsi_14: float = 50.0
    pre_vwap: float = 0.0
    vs_vwap_pct: float = 0.0
    prev_reg_close: float = 0.0
    vs_prev_close_pct: float = 0.0
    pre_open_price: float = 0.0
    vs_pre_open_pct: float = 0.0
    vs_scout1_pct: float = 0.0
    is_bull_bar: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "IndependentScoutUnit":
        ep = round(max(0.01, safe_float(d.get("entry_price"), 10.0)), 4)
        tp_default = math.ceil((ep * 1.010 - 1e-9) * 100.0) / 100.0
        return cls(
            scout_id=max(1, safe_int(d.get("scout_id"), 1)),
            tier_slot=max(1, safe_int(d.get("tier_slot"), 1)),
            entry_type=str(d.get("entry_type") or "01_OPEN_0407"),
            entry_time_est=str(d.get("entry_time_est") or "04:07:00"),
            entry_ts=safe_float(d.get("entry_ts"), 0.0),
            entry_price=ep,
            target_price=round(
                max(ep, safe_float(d.get("target_price"), tp_default)), 2
            ),
            qty=max(1, safe_int(d.get("qty"), 1)),
            rsi_14=round(safe_float(d.get("rsi_14"), 50.0), 2),
            pre_vwap=round(safe_float(d.get("pre_vwap"), 0.0), 4),
            vs_vwap_pct=round(safe_float(d.get("vs_vwap_pct"), 0.0), 2),
            prev_reg_close=round(safe_float(d.get("prev_reg_close"), ep), 4),
            vs_prev_close_pct=round(
                safe_float(d.get("vs_prev_close_pct"), 0.0), 2
            ),
            pre_open_price=round(safe_float(d.get("pre_open_price"), 0.0), 4),
            vs_pre_open_pct=round(
                safe_float(d.get("vs_pre_open_pct"), 0.0), 2
            ),
            vs_scout1_pct=round(safe_float(d.get("vs_scout1_pct"), 0.0), 2),
            is_bull_bar=bool(d.get("is_bull_bar", True)),
        )


# ---------------------------------------------------------------------------
# [핵심 2] 폴더 격리형 암살자 전용 3중 원장 (AssassinSimLedger — 스나이퍼 원장 간섭 0%)
# ---------------------------------------------------------------------------
def resolve_assassin_ledger_paths(
    base_dir: Optional[str] = None,
) -> Tuple[str, str, str, str]:
    """
    # [Case 68, Case 85 & Case 93]:
    스나이퍼 본 원장(soxl_stratum_ledger*.json)과 물리적으로 완전히 분리된
    암살자 전용 3중 원장 경로(primary, compat_mirror, backup_vault, folder_slug)를 반환한다.
    """
    target_dir = get_bot_base_dir(base_dir)
    slug = get_folder_slug(target_dir)
    backup_dir = os.path.join(target_dir, "ledger_backups")
    os.makedirs(backup_dir, exist_ok=True)

    primary_fp = os.path.join(target_dir, f"assassin_sim_ledger_{slug}.json")
    mirror_fp = os.path.join(target_dir, "assassin_sim_ledger.json")
    backup_fp = os.path.join(
        backup_dir, f"assassin_sim_ledger_{slug}.bak.json"
    )
    return primary_fp, mirror_fp, backup_fp, slug


class AssassinSimLedger:
    """
    🚨 Case 75, Case 85 & Case 93:
    Dirty-Check(변경 감지) 기반 디스크 쓰기 최소화 및 3중 원자적 백업 금고를 지원하는
    [모의 ⇄ 실전 Dual-Ready] 암살자 전용 원장 클래스
    (정책 4 SMART_WAIT · DL_G6 · DL10 & 변형 선택지 A 2단 하이브리드 래칫 [+1.00% ➔ +1.25%] & trade_journal_history 탑재).
    """

    def __init__(
        self,
        base_dir: Optional[str] = None,
        sniper_seed_usd: float = DEFAULT_INITIAL_SEED_USD,
    ) -> None:
        self.base_dir: str = get_bot_base_dir(base_dir)
        (
            self.primary_filepath,
            self.mirror_filepath,
            self.backup_filepath,
            self.folder_slug,
        ) = resolve_assassin_ledger_paths(self.base_dir)
        self._lock = threading.RLock()
        self._async_lock = asyncio.Lock()
        self._last_serialized_payload: str = ""
        self._data: Dict[str, Any] = {}
        self._load_or_init_sync(sniper_seed_usd=sniper_seed_usd)

    def _default_symbol_state(
        self, seed_usd: float = DEFAULT_INITIAL_SEED_USD
    ) -> Dict[str, Any]:
        clean_seed = round(
            max(100.0, safe_float(seed_usd, DEFAULT_INITIAL_SEED_USD)), 4
        )
        now_est = datetime.now(EST_TZ)
        return {
            "symbol": TARGET_SYMBOL,
            "folder_slug": self.folder_slug,
            "execution_mode": (
                ASSASSIN_MODE_SIMULATED
                if ASSASSIN_LIVE_ORDER_HARD_LOCK
                else ASSASSIN_MODE_LIVE
            ),
            "safety_net_mode": SAFETY_NET_MODE_DEFAULT,
            "safety_hold_mode": bool(ASSASSIN_SAFETY_HOLD_MODE),
            "live_order_hard_lock": bool(ASSASSIN_LIVE_ORDER_HARD_LOCK),
            "is_enabled": True,
            "initial_seed_usd": clean_seed,
            "us_commission_rate": get_runtime_us_commission_rate(),
            "round_trip_fee_rate_pct": get_runtime_round_trip_fee_rate_pct(),
            # 당일 세션 상태 머신
            "current_session_date": now_est.strftime("%Y-%m-%d"),
            "session_phase": "IDLE_WAIT_0407",
            "is_session_done": False,
            "session_done_reason": "",
            # 당일 확정 4대 앵커 지표 원장 백업 (진성 확인된 값만 개별 검증 플래그와 함께 보존)
            "today_anchors_locked": False,
            "today_prev_close_verified": False,
            "today_pre_open_verified": False,
            "today_pre_vwap_verified": False,
            "today_prev_reg_close": 0.0,
            "today_pre_open_price": 0.0,
            "today_premarket_vwap": 0.0,
            "today_regular_vwap": 0.0,
            # 04:07 ~ 08:14 EST 1주 가상 독립 정찰병 상태
            "scout_units": [],
            "day_scout_history": [],
            "day_scout_seq": 0,
            "prior_scout_wins_today": 0,
            "scout1_open_price": 0.0,
            "scout_anchor_price": 0.0,
            "scout_cycle_min_buy_price": 0.0,
            "scout_ratchet_max_lots": 0,
            "scout_has_active_l1": False,
            "last_scout_buy_ts": 0.0,
            "last_scout_sell_ts": 0.0,
            "last_scout_reentry_eval_ts": 0.0,
            "last_scout_bucket_10m": -1,
            # NEW [정책 4 : SMART_WAIT (음봉 칼날 시 최대 5분 스마트 진바닥 대기) 슬롯]
            "smart_wait_active": False,
            "smart_wait_start_ts": 0.0,
            "smart_wait_gate_id": "",
            "smart_wait_gate_desc": "",
            "smart_wait_trigger_price": 0.0,
            "smart_wait_scout_seq": 0,
            "smart_wait_trigger_mode": "",
            # 본대(Main Force) 포지션 · 작동 게이트(G1~G5/BG1~BG5/DL_G6/DL10) · 진입 6대 지표 및 출동 순간 QQQ 지수
            "has_position": False,
            "entry_gate_id": "",
            "entry_gate_desc": "",
            "entry_trigger_mode": "",
            "entry_time_est": "",
            "entry_ts": 0.0,
            "entry_price": 0.0,
            "entry_qqq_price": 0.0,
            "entry_qqq_vel_1m_pct": 0.0,
            "entry_qqq_vel_3m_pct": 0.0,
            "qqq_chg_from_entry_pct": 0.0,
            "entry_scout_seq": 0,
            "entry_prior_scout_wins": 0,
            "entry_rsi_14": 50.0,
            "entry_vwap": 0.0,
            "entry_vs_vwap_pct": 0.0,
            "entry_prev_close": 0.0,
            "entry_vs_prev_close_pct": 0.0,
            "entry_pre_open": 0.0,
            "entry_vs_pre_open_pct": 0.0,
            "entry_vs_scout1_pct": 0.0,
            "entry_dd_from_pre_high_pct": 0.0,
            "entry_vel_5m_pct": 0.0,
            "entry_is_bull_bar": True,
            "entry_is_ha_bull": True,
            "nq_entry_bear_amp_pct": SAFETY_QQQ_BASE_AMP_PCT,
            "dyn_qqq_stage2_thr_pct": SAFETY_DYN_QQQ_MAX_THR_PCT,
            "simple_held_qty": 0,
            "simple_invested_usd": 0.0,
            "comp_held_qty": 0,
            "comp_invested_usd": 0.0,
            # 변형 선택지 A : 2단 하이브리드 래칫 (+1.00% 1차 잠금 ➔ +1.25% 2차 부스트 점화) 가격 및 상태 슬롯
            "cap_500_price": 0.0,
            "arm_100_price": 0.0,
            "arm_125_price": 0.0,
            "is_trailing_armed": False,
            "armed_time_est": "",
            "is_stage2_boost_armed": False,
            "stage2_armed_time_est": "",
            "peak_price": 0.0,
            "post_entry_min_price": 0.0,
            "active_stop_floor_price": 0.0,
            # Dual-Ready 주문 ID 슬롯 (실전 전환 시 사용)
            "pending_buy_order_id": "",
            "safe_cap_sell_order_id": "",
            # 5대 알림 1회 발송 래치
            "alert_0815_no_trade_sent": False,
            "alert_entry_sent": False,
            "alert_arm_100_sent": False,
            "alert_arm_125_sent": False,
            "alert_exit_sent": False,
            # 당일 청산 체결 요약 및 데이터 수집용 청산 시점 지표 스냅샷
            "today_exit_code": "",
            "today_exit_reason": "",
            "today_exit_time_est": "",
            "today_exit_price": 0.0,
            "today_gain_pct": 0.0,
            "today_simple_net_usd": 0.0,
            "today_comp_net_usd": 0.0,
            "today_exit_rsi_14": 50.0,
            "today_exit_reg_vwap": 0.0,
            "today_exit_vs_reg_vwap_pct": 0.0,
            "today_exit_pre_vwap": 0.0,
            "today_exit_vs_pre_vwap_pct": 0.0,
            "today_exit_qqq_price": 0.0,
            "today_exit_qqq_vel_1m_pct": 0.0,
            "today_exit_qqq_vel_3m_pct": 0.0,
            "today_exit_is_bull_bar": True,
            "today_exit_is_ha_bull": True,
            # 누적 모의 성적표 (단리 & 연속복리 동시 추적) 및 매매 복기 일지(최근 50건)
            "total_trade_days": 0,
            "win_days": 0,
            "loss_days": 0,
            "no_trade_days": 0,
            "total_scouts_dispatched": 0,
            "total_scout_win_exits": 0,
            "exit_cap500_cnt": 0,
            "exit_ha_boost_cnt": 0,
            "exit_floor125_cnt": 0,
            "exit_floor100_cnt": 0,
            "exit_vwap_1500_cnt": 0,
            "exit_safety_stage1_cnt": 0,
            "exit_safety_stage23_cnt": 0,
            "exit_moc_cnt": 0,
            "simple_cum_net_usd": 0.0,
            "comp_free_cash_usd": clean_seed,
            "comp_cum_net_usd": 0.0,
            "comp_peak_equity_usd": clean_seed,
            "comp_max_dd_pct": 0.0,
            "gate_hit_counts": {},
            "trade_journal_history": [],
            "updated_at": now_est.isoformat(),
        }

    def _sanitize_state(
        self, raw_st: Dict[str, Any], default_seed: float
    ) -> Dict[str, Any]:
        base = self._default_symbol_state(default_seed)
        if isinstance(raw_st, dict):
            base.update(raw_st)

        base["execution_mode"] = (
            ASSASSIN_MODE_SIMULATED
            if ASSASSIN_LIVE_ORDER_HARD_LOCK
            else str(base.get("execution_mode") or ASSASSIN_MODE_SIMULATED)
        )
        base["safety_net_mode"] = SAFETY_NET_MODE_DEFAULT
        base["safety_hold_mode"] = bool(
            base.get("safety_hold_mode", ASSASSIN_SAFETY_HOLD_MODE)
        )
        base["live_order_hard_lock"] = bool(ASSASSIN_LIVE_ORDER_HARD_LOCK)

        init_s = safe_float(base.get("initial_seed_usd"), default_seed)
        if init_s < 100.0:
            init_s = max(100.0, default_seed)
        base["initial_seed_usd"] = round(init_s, 4)

        comp_net = round(safe_float(base.get("comp_cum_net_usd"), 0.0), 4)
        base["comp_cum_net_usd"] = comp_net
        base["simple_cum_net_usd"] = round(
            safe_float(base.get("simple_cum_net_usd"), 0.0), 4
        )
        base["comp_free_cash_usd"] = round(max(100.0, init_s + comp_net), 4)
        base["comp_peak_equity_usd"] = round(
            max(
                safe_float(base.get("comp_peak_equity_usd"), init_s),
                base["comp_free_cash_usd"],
            ),
            4,
        )

        base["entry_qqq_price"] = round(
            max(0.0, safe_float(base.get("entry_qqq_price"), 0.0)), 4
        )
        base["qqq_chg_from_entry_pct"] = round(
            safe_float(base.get("qqq_chg_from_entry_pct"), 0.0), 3
        )
        base["entry_trigger_mode"] = str(
            base.get("entry_trigger_mode") or ""
        ).strip()

        ep_now = safe_float(base.get("entry_price"), 0.0)
        if ep_now > 0.0:
            if safe_float(base.get("arm_100_price"), 0.0) <= 0.0:
                base["arm_100_price"] = round(
                    math.ceil(
                        (ep_now * (1.0 + ASSASSIN_ARM_IGNITION_PCT / 100.0) - 1e-9)
                        * 100.0
                    )
                    / 100.0,
                    2,
                )
            if safe_float(base.get("arm_125_price"), 0.0) <= 0.0:
                base["arm_125_price"] = round(
                    math.ceil(
                        (ep_now * (1.0 + ASSASSIN_STAGE2_BOOST_PCT / 100.0) - 1e-9)
                        * 100.0
                    )
                    / 100.0,
                    2,
                )

        raw_dyn_thr = safe_float(
            base.get("dyn_qqq_stage2_thr_pct"), SAFETY_DYN_QQQ_MAX_THR_PCT
        )
        base["dyn_qqq_stage2_thr_pct"] = round(
            min(
                SAFETY_DYN_QQQ_MAX_THR_PCT,
                max(SAFETY_DYN_QQQ_MIN_THR_PCT, raw_dyn_thr),
            ),
            2,
        )

        if not isinstance(base.get("scout_units"), list):
            base["scout_units"] = []
        if not isinstance(base.get("day_scout_history"), list):
            base["day_scout_history"] = []
        if not isinstance(base.get("gate_hit_counts"), dict):
            base["gate_hit_counts"] = {}
        if not isinstance(base.get("trade_journal_history"), list):
            base["trade_journal_history"] = []
        else:
            base["trade_journal_history"] = list(
                base["trade_journal_history"]
            )[-ASSASSIN_MAX_JOURNAL_HISTORY:]

        # 🚨 [Case 93 자가 치유 : 구버전 폴백으로 인해 오염된 프리시가 및 프리VWAP 자동 감지 및 0.0 초기화!]
        t_prev = safe_float(base.get("today_prev_reg_close"), 0.0)
        t_open = safe_float(base.get("today_pre_open_price"), 0.0)
        t_vwap = safe_float(base.get("today_premarket_vwap"), 0.0)
        t_reg_vwap = safe_float(base.get("today_regular_vwap"), 0.0)

        pre_open_ver = bool(base.get("today_pre_open_verified", False))
        pre_vwap_ver = bool(base.get("today_pre_vwap_verified", False))

        if _is_collapsed_assassin_anchors(t_prev, t_open, t_vwap):
            base["today_anchors_locked"] = False
            base["today_prev_close_verified"] = False
            base["today_pre_open_verified"] = False
            base["today_pre_vwap_verified"] = False
            base["today_prev_reg_close"] = 0.0
            base["today_pre_open_price"] = 0.0
            base["today_premarket_vwap"] = 0.0
            base["today_regular_vwap"] = 0.0
        else:
            hist = base.get("day_scout_history") or []
            if (not pre_open_ver or not pre_vwap_ver) and len(hist) > 0:
                first_sc = hist[0] if isinstance(hist[0], dict) else {}
                sc_open = safe_float(
                    first_sc.get("pre_open_price")
                    or first_sc.get("entry_price"),
                    0.0,
                )
                sc_vwap = safe_float(first_sc.get("pre_vwap"), 0.0)
                if sc_open > 0.0:
                    base["today_pre_open_price"] = round(sc_open, 4)
                    base["today_pre_open_verified"] = True
                    pre_open_ver = True
                if sc_vwap > 0.0:
                    base["today_premarket_vwap"] = round(sc_vwap, 4)
                    base["today_pre_vwap_verified"] = True
                    pre_vwap_ver = True

            if not pre_open_ver:
                base["today_pre_open_price"] = 0.0
                base["today_pre_open_verified"] = False
            if not pre_vwap_ver or (
                not pre_vwap_ver
                and t_vwap > 0.0
                and t_reg_vwap > 0.0
                and abs(t_vwap - t_reg_vwap) < 1e-6
            ):
                base["today_premarket_vwap"] = 0.0
                base["today_pre_vwap_verified"] = False

        return base

    def _load_or_init_sync(
        self, sniper_seed_usd: float = DEFAULT_INITIAL_SEED_USD
    ) -> None:
        with self._lock:
            loaded_st: Optional[Dict[str, Any]] = None
            for fp in (
                self.primary_filepath,
                self.mirror_filepath,
                self.backup_filepath,
            ):
                if not os.path.isfile(fp):
                    continue
                try:
                    with GlobalThrottle.get_file_lock(fp):
                        with open(fp, "r", encoding="utf-8") as rf:
                            raw = json.load(rf)
                    if isinstance(raw, dict):
                        cand = (
                            raw.get(TARGET_SYMBOL)
                            if isinstance(raw.get(TARGET_SYMBOL), dict)
                            else raw
                        )
                        if isinstance(cand, dict):
                            loaded_st = cand
                            break
                except Exception:
                    continue

            clean_st = self._sanitize_state(
                loaded_st or {}, default_seed=sniper_seed_usd
            )
            self._data = {TARGET_SYMBOL: clean_st}
            self._save_sync_unlocked(force=(loaded_st is None))

    def _comparable_payload_str(self) -> str:
        st_copy = copy.deepcopy(self._data.get(TARGET_SYMBOL, {}))
        st_copy.pop("updated_at", None)
        return json.dumps(st_copy, ensure_ascii=False, sort_keys=True)

    def _atomic_write_single_file_sync(
        self, filepath: str, serialized_json: str
    ) -> None:
        parent_d = os.path.dirname(os.path.abspath(filepath))
        with GlobalThrottle.get_file_lock(filepath):
            if os.path.isfile(filepath):
                try:
                    with open(filepath, "r", encoding="utf-8") as rf:
                        if rf.read() == serialized_json:
                            return
                except Exception:
                    pass

            for attempt in range(2):
                if parent_d and not os.path.isdir(parent_d):
                    os.makedirs(parent_d, exist_ok=True)
                tmp_fp = (
                    f"{filepath}.tmp.{os.getpid()}.{threading.get_ident()}"
                )
                try:
                    with open(tmp_fp, "w", encoding="utf-8") as wf:
                        wf.write(serialized_json)
                        wf.flush()
                        os.fsync(wf.fileno())
                    os.replace(tmp_fp, filepath)
                    break
                except OSError as os_err:
                    try:
                        if os.path.exists(tmp_fp):
                            os.remove(tmp_fp)
                    except Exception:
                        pass
                    if os_err.errno == errno.ENOSPC and attempt == 0:
                        emergency_free_disk_space_sync(
                            base_dir=self.base_dir,
                            keep_backup_days=3,
                            remove_pycache=True,
                        )
                        continue
                    break
                except Exception:
                    try:
                        if os.path.exists(tmp_fp):
                            os.remove(tmp_fp)
                    except Exception:
                        pass
                    break

    def _save_sync_unlocked(self, force: bool = False) -> None:
        comp_str = self._comparable_payload_str()
        if not force and comp_str == self._last_serialized_payload:
            return
        self._last_serialized_payload = comp_str
        self._data[TARGET_SYMBOL]["updated_at"] = datetime.now(
            EST_TZ
        ).isoformat()
        full_json = json.dumps(self._data, ensure_ascii=False, indent=2)
        for fp in (
            self.primary_filepath,
            self.mirror_filepath,
            self.backup_filepath,
        ):
            self._atomic_write_single_file_sync(fp, full_json)

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data.get(TARGET_SYMBOL, {}))

    def update_state_sync(self, **kwargs: Any) -> Dict[str, Any]:
        with self._lock:
            st = self._data.setdefault(
                TARGET_SYMBOL, self._default_symbol_state()
            )
            for k, v in kwargs.items():
                st[k] = v
            self._data[TARGET_SYMBOL] = self._sanitize_state(
                st,
                default_seed=safe_float(
                    st.get("initial_seed_usd"), 10000.0
                ),
            )
            self._save_sync_unlocked(force=False)
            return copy.deepcopy(self._data[TARGET_SYMBOL])

    async def update_state(self, **kwargs: Any) -> Dict[str, Any]:
        async with self._async_lock:
            return await asyncio.to_thread(self.update_state_sync, **kwargs)

    async def rollover_daily_session_if_needed(
        self, today_est_str: str, sniper_seed_usd: float = 0.0
    ) -> Dict[str, Any]:
        """
        새로운 미국 영업일(today_est_str) 진입 시 당일 정찰병·스마트대기·본대 포지션 슬롯(arm_100_price, arm_125_price, is_stage2_boost_armed 포함)과
        당일 프리장 앵커 검증 플래그 및 T03_A 인메모리 스캔 래치를 클리어하고 누적 성적표 및 trade_journal_history 는 100% 보존한다.
        """
        global _LAST_T03A_DIP_SCAN_KEY, _LAST_T03A_DIP_SCAN_TS
        st = self.get_state()
        cur_date = str(st.get("current_session_date") or "").strip()
        if cur_date == today_est_str:
            if (
                sniper_seed_usd >= 100.0
                and abs(
                    safe_float(st.get("initial_seed_usd"), 0.0)
                    - sniper_seed_usd
                )
                > 1e-4
                and not bool(st.get("has_position", False))
            ):
                return await self.update_state(
                    initial_seed_usd=round(sniper_seed_usd, 4)
                )
            return st

        _LAST_T03A_DIP_SCAN_KEY = ""
        _LAST_T03A_DIP_SCAN_TS = 0.0

        eff_seed = (
            round(sniper_seed_usd, 4)
            if sniper_seed_usd >= 100.0
            else safe_float(
                st.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD
            )
        )
        return await self.update_state(
            initial_seed_usd=eff_seed,
            safety_net_mode=SAFETY_NET_MODE_DEFAULT,
            safety_hold_mode=bool(ASSASSIN_SAFETY_HOLD_MODE),
            current_session_date=today_est_str,
            session_phase="IDLE_WAIT_0407",
            is_session_done=False,
            session_done_reason="",
            today_anchors_locked=False,
            today_prev_close_verified=False,
            today_pre_open_verified=False,
            today_pre_vwap_verified=False,
            today_prev_reg_close=0.0,
            today_pre_open_price=0.0,
            today_premarket_vwap=0.0,
            today_regular_vwap=0.0,
            scout_units=[],
            day_scout_history=[],
            day_scout_seq=0,
            prior_scout_wins_today=0,
            scout1_open_price=0.0,
            scout_anchor_price=0.0,
            scout_cycle_min_buy_price=0.0,
            scout_ratchet_max_lots=0,
            scout_has_active_l1=False,
            last_scout_buy_ts=0.0,
            last_scout_sell_ts=0.0,
            last_scout_reentry_eval_ts=0.0,
            last_scout_bucket_10m=-1,
            smart_wait_active=False,
            smart_wait_start_ts=0.0,
            smart_wait_gate_id="",
            smart_wait_gate_desc="",
            smart_wait_trigger_price=0.0,
            smart_wait_scout_seq=0,
            smart_wait_trigger_mode="",
            has_position=False,
            entry_gate_id="",
            entry_gate_desc="",
            entry_trigger_mode="",
            entry_time_est="",
            entry_ts=0.0,
            entry_price=0.0,
            entry_qqq_price=0.0,
            entry_qqq_vel_1m_pct=0.0,
            entry_qqq_vel_3m_pct=0.0,
            qqq_chg_from_entry_pct=0.0,
            entry_scout_seq=0,
            entry_prior_scout_wins=0,
            entry_rsi_14=50.0,
            entry_vwap=0.0,
            entry_vs_vwap_pct=0.0,
            entry_prev_close=0.0,
            entry_vs_prev_close_pct=0.0,
            entry_pre_open=0.0,
            entry_vs_pre_open_pct=0.0,
            entry_vs_scout1_pct=0.0,
            entry_dd_from_pre_high_pct=0.0,
            entry_vel_5m_pct=0.0,
            entry_is_bull_bar=True,
            entry_is_ha_bull=True,
            dyn_qqq_stage2_thr_pct=SAFETY_DYN_QQQ_MAX_THR_PCT,
            simple_held_qty=0,
            simple_invested_usd=0.0,
            comp_held_qty=0,
            comp_invested_usd=0.0,
            cap_500_price=0.0,
            arm_100_price=0.0,
            arm_125_price=0.0,
            is_trailing_armed=False,
            armed_time_est="",
            is_stage2_boost_armed=False,
            stage2_armed_time_est="",
            peak_price=0.0,
            post_entry_min_price=0.0,
            active_stop_floor_price=0.0,
            pending_buy_order_id="",
            safe_cap_sell_order_id="",
            alert_0815_no_trade_sent=False,
            alert_entry_sent=False,
            alert_arm_100_sent=False,
            alert_arm_125_sent=False,
            alert_exit_sent=False,
            today_exit_code="",
            today_exit_reason="",
            today_exit_time_est="",
            today_exit_price=0.0,
            today_gain_pct=0.0,
            today_simple_net_usd=0.0,
            today_comp_net_usd=0.0,
            today_exit_rsi_14=50.0,
            today_exit_reg_vwap=0.0,
            today_exit_vs_reg_vwap_pct=0.0,
            today_exit_pre_vwap=0.0,
            today_exit_vs_pre_vwap_pct=0.0,
            today_exit_qqq_price=0.0,
            today_exit_qqq_vel_1m_pct=0.0,
            today_exit_qqq_vel_3m_pct=0.0,
            today_exit_is_bull_bar=True,
            today_exit_is_ha_bull=True,
        )

    async def reset_assassin_stats_only(
        self, sniper_seed_usd: float = DEFAULT_INITIAL_SEED_USD
    ) -> Dict[str, Any]:
        """
        /reset_assassin 명령 시 누적 전적, 단리·복리 실현익 및 매매 복기 일지를 0점으로 초기화한다.
        """
        eff_seed = round(
            max(100.0, safe_float(sniper_seed_usd, DEFAULT_INITIAL_SEED_USD)),
            4,
        )
        return await self.update_state(
            initial_seed_usd=eff_seed,
            total_trade_days=0,
            win_days=0,
            loss_days=0,
            no_trade_days=0,
            total_scouts_dispatched=0,
            total_scout_win_exits=0,
            exit_cap500_cnt=0,
            exit_ha_boost_cnt=0,
            exit_floor125_cnt=0,
            exit_floor100_cnt=0,
            exit_vwap_1500_cnt=0,
            exit_safety_stage1_cnt=0,
            exit_safety_stage23_cnt=0,
            exit_moc_cnt=0,
            simple_cum_net_usd=0.0,
            comp_free_cash_usd=eff_seed,
            comp_cum_net_usd=0.0,
            comp_peak_equity_usd=eff_seed,
            comp_max_dd_pct=0.0,
            gate_hit_counts={},
            trade_journal_history=[],
        )


def ensure_assassin_ledger(context: Any) -> AssassinSimLedger:
    """
    SniperAppContext 에 assassin_ledger 인스턴스가 없으면 생성하여 장착하고 반환한다.
    """
    existing = getattr(context, "assassin_ledger", None)
    if isinstance(existing, AssassinSimLedger):
        return existing

    base_dir = get_bot_base_dir(getattr(context, "base_dir", None))
    sniper_seed = DEFAULT_INITIAL_SEED_USD
    if context is not None and hasattr(context, "ledger"):
        try:
            st_sp = context.ledger.get_state(TARGET_SYMBOL)
            sniper_seed = safe_float(
                st_sp.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD
            )
        except Exception:
            pass

    ledger = AssassinSimLedger(base_dir=base_dir, sniper_seed_usd=sniper_seed)
    if context is not None:
        try:
            setattr(context, "assassin_ledger", ledger)
        except Exception:
            pass
    return ledger
# -*- coding: utf-8 -*-
"""
# MODIFIED: assassin_plugin.py (Part 2/3 — 정책 4 진입 판정기 [10대 진성 게이트 + SMART_WAIT 스마트 진바닥 대기 + DL_G6 강세장 급눌림 진바닥 + 08:30~09:20 DL10 거시지표 무패 진바닥] · 400봉 1m + 10봉 1d 프리워밍 및 vel_5m_pct / dd_from_pre_high_pct 추출기 · Dual-Ready 주문 어댑터 · 2단 하이브리드 래칫 [+1.00% 1차 잠금 ➔ +1.25% 2차 부스트] 실시간 알림 및 복기 스냅샷 포맷터 · Case 93)
"""


# ---------------------------------------------------------------------------
# [핵심 3] 정책 4 진입 엔진 : 10대 진성 게이트 (G1~G5 + BG1~BG5) · 강세장 급눌림(DL_G6) · 거시지표 무패 진바닥(DL10) · 스마트 대기(SMART_WAIT) 판정기
# ---------------------------------------------------------------------------
def evaluate_10_truth_gates_signal(
    scout_seq: int,
    rsi_14: float,
    vs_vwap_pct: float,
    vs_prev_close_pct: float,
    vs_pre_open_pct: float,
    vs_scout1_pct: float,
    prior_scout_wins: int,
    is_bull_bar: bool,
    allow_sc1_dip_scan: bool = False,
) -> Tuple[bool, str, str]:
    """
    # [Case 93 : 10대 진성 게이트 판정 (T03_A_DIP10_ALL_SCOUT 완벽 지원)]:
    기본적으로 #1 선봉 정찰병(04:07 EST) 파견 순간에는 본대 진입을 보류(scout_seq >= 2 필수)하되,
    T03_A_DIP10_ALL_SCOUT 규율에 따라 #1 선봉 파견 이후 직전 정찰 저점 대비 -1.00% 이하 눌림 구간에서
    실행되는 매 1분 상시 스캔(allow_sc1_dip_scan=True) 시에는 scout_seq >= 1 상태에서 즉시
    10대 진성 게이트(G1 ~ G5 + BG1 ~ BG5) 충족 여부를 판정하여 반환한다.
    """
    if int(scout_seq) < 1:
        return False, "", "WAIT_SCOUT_2_PLUS"
    if int(scout_seq) < 2 and not bool(allow_sc1_dip_scan):
        return False, "", "WAIT_SCOUT_2_PLUS"

    r = safe_float(rsi_14, 50.0)
    vw = safe_float(vs_vwap_pct, 0.0)
    pc = safe_float(vs_prev_close_pct, 0.0)
    po = safe_float(vs_pre_open_pct, 0.0)
    s1 = safe_float(vs_scout1_pct, 0.0)
    wins = max(0, int(prior_scout_wins))
    bull = bool(is_bull_bar)

    # [헌법 G1 ~ G5]
    if r <= 30.0 and pc < 0.0 and po <= -1.50:
        return (
            True,
            "G1",
            "헌법G1(RSI≤30 · 전일종가<0% · 프리시가≤-1.5%)",
        )
    if r <= 45.0 and vw <= -2.00:
        return True, "G2", "헌법G2(RSI≤45 · 프리VWAP≤-2.0%)"
    if r <= 25.0 and vw <= -1.00 and wins >= 1:
        return (
            True,
            "G3",
            "헌법G3(RSI≤25 · 프리VWAP≤-1.0% · 정찰선행익절≥1회)",
        )
    if r <= 32.0 and vw <= -0.50 and pc <= -1.00 and bull:
        return (
            True,
            "G4",
            "헌법G4(RSI≤32 · 프리VWAP≤-0.5% · 전일종가≤-1.0% · 양봉)",
        )
    if r <= 20.0 and pc >= 0.0:
        return True, "G5", "헌법G5(RSI≤20 극과매도 · 전일종가≥0%)"

    # [폭락장 BG1 ~ BG5]
    if (
        30.0 <= r <= 45.0
        and vw <= -1.00
        and pc <= -6.00
        and s1 <= -2.00
    ):
        return (
            True,
            "BG1",
            "폭락BG1(RSI 30~45 · VWAP≤-1.0% · 전일≤-6.0% · 선봉≤-2.0%)",
        )
    if r <= 30.0 and vw <= -1.00 and pc <= -3.00 and po <= -1.00:
        return (
            True,
            "BG2",
            "폭락BG2(RSI≤30 · VWAP≤-1.0% · 전일≤-3.0% · 프리시가≤-1.0%)",
        )
    if r <= 32.0 and po <= -2.50:
        return True, "BG3", "폭락BG3(RSI≤32 · 프리장시가대비≤-2.5%)"
    if r <= 25.0 and vw <= -0.50 and bull:
        return True, "BG4", "폭락BG4(RSI≤25 · 프리VWAP≤-0.5% · 1분봉양봉)"
    if r <= 45.0 and vw <= -1.50 and pc <= -4.00 and wins >= 1:
        return (
            True,
            "BG5",
            "폭락BG5(RSI≤45 · VWAP≤-1.5% · 전일≤-4.0% · 정찰익절≥1회)",
        )

    return False, "", "NO_GATE_MATCH"


def evaluate_dl_g6_bull_pullback_signal(
    hm: int,
    scout_seq: int,
    rsi_14: float,
    vs_vwap_pct: float,
    vs_prev_close_pct: float,
    vs_pre_open_pct: float,
    dd_from_pre_high_pct: float,
    is_bull_bar: bool,
    qqq_vel_1m_pct: float,
) -> Tuple[bool, str, str]:
    """
    # NEW [정책 4 · 2단계 : 프리장(04:07 ~ 08:14 EST) 강세장 급눌림 진바닥(DL_G6) 포착기]:
    전일 정규장 종가 대비 강세 출발일(vs_prev_close_pct >= -0.50%) 사각지대를 보완하여,
    프리장 고점 대비 -2.50% 이상 급락 & 프리시가 대비 <= -1.50% & 프리VWAP 대비 <= -1.50% &
    Wilder RSI(14) <= 27.5 상태에서 1분봉 양봉(is_bull_bar) + QQQ 반등(qqq_vel_1m_pct >= 0.0%)이
    동시에 켜지면 DL_G6 로 즉시 진입을 승인한다.
    """
    if not (ASSASSIN_SCOUT_START_HM <= int(hm) <= ASSASSIN_GOLDEN_END_HM):
        return False, "", "OUTSIDE_PRE_GOLDEN"
    if int(scout_seq) < 1:
        return False, "", "WAIT_SCOUT_1"

    r = safe_float(rsi_14, 50.0)
    vw = safe_float(vs_vwap_pct, 0.0)
    po = safe_float(vs_pre_open_pct, 0.0)
    dd_h = safe_float(dd_from_pre_high_pct, 0.0)
    q_v1 = safe_float(qqq_vel_1m_pct, 0.0)
    bull = bool(is_bull_bar)

    if (
        dd_h <= DL_G6_MAX_DD_HIGH_PCT
        and po <= DL_G6_MAX_VS_PRE_OPEN_PCT
        and vw <= DL_G6_MAX_VS_VWAP_PCT
        and r <= DL_G6_MAX_RSI_14
        and bull
        and q_v1 >= 0.0
    ):
        return (
            True,
            "DL_G6",
            "강세진바닥DL_G6(고점DD≤-2.5% · 시가≤-1.5% · VWAP≤-1.5% · RSI≤27.5 · 양봉+QQQ반등)",
        )
    return False, "", "NO_DL_G6_MATCH"


def evaluate_dl10_macro_bottom_signal(
    hm: int,
    rsi_14: float,
    vs_vwap_pct: float,
    vel_5m_pct: float,
    is_bull_bar: bool,
    qqq_vel_1m_pct: float,
) -> Tuple[bool, str, str]:
    """
    # NEW [정책 4 · 3단계 : 08:30 ~ 09:20 EST 미국 거시지표 발표 직후 무패 진바닥(DL10 · 16전 16승) 포착기]:
    08:14 EST 까지 프리장 매매가 없었던 날(무매매일)에 한해,
    08:30 ~ 09:20 EST 구간에서 알고리즘 투매로 직전 5분간 -1.20% 이하 급락(vel_5m_pct <= -1.20%)하며
    RSI(14) <= 24.0 & 프리VWAP 괴리율 <= -2.00% 에 도달한 직후 첫 1분봉 양봉(is_bull_bar) +
    QQQ 1분 변화율 >= +0.02% 반등이 동시 점등되면 DL10 으로 즉시 100% 진입을 승인한다.
    """
    if not (
        ASSASSIN_MACRO_DL10_START_HM <= int(hm) <= ASSASSIN_MACRO_DL10_END_HM
    ):
        return False, "", "OUTSIDE_DL10_WINDOW"

    r = safe_float(rsi_14, 50.0)
    vw = safe_float(vs_vwap_pct, 0.0)
    v5 = safe_float(vel_5m_pct, 0.0)
    q_v1 = safe_float(qqq_vel_1m_pct, 0.0)
    bull = bool(is_bull_bar)

    if (
        r <= DL10_MAX_RSI_14
        and vw <= DL10_MAX_VS_VWAP_PCT
        and v5 <= DL10_MAX_VEL_5M_PCT
        and bull
        and q_v1 >= DL10_MIN_QQQ_VEL_1M_PCT - 1e-6
    ):
        return (
            True,
            "DL10",
            "지표진바닥DL10(08:30~09:20 · RSI≤24 · VWAP≤-2.0% · 5m≤-1.2% · 양봉+QQQ≥+0.02%)",
        )
    return False, "", "NO_DL10_MATCH"


def should_enter_immediately_or_smart_wait(
    gate_id: str,
    dd_from_pre_high_pct: float,
    is_bull_bar: bool,
    qqq_vel_1m_pct: float,
) -> Tuple[bool, str]:
    """
    # NEW [정책 4 · 1단계 : SMART_WAIT (스마트 진바닥 대기) 분기 판정기]:
    프리장에서 10대 진성 게이트가 점등되었을 때:
    - 이미 프리장 고점 대비 충분히 빠진 진바닥(dd_from_pre_high_pct <= -1.80%)이거나,
      현재 1분봉이 양봉(is_bull_bar == True)이거나 QQQ가 반등 중(qqq_vel_1m_pct >= +0.02%)이면
      지체 없이 즉시 진입(True, "IMMEDIATE_ENTRY")한다.
    - 반면 G1 등이 막 켜졌는데 아직 고점 대비 낙폭이 얕고(dd_from_pre_high_pct > -1.80%)
      현재 1분봉이 시퍼런 음봉 칼날(not is_bull_bar)이면 최대 5분(300초) 스마트 대기(False, "SMART_WAIT_ARMED")를 가동하여
      첫 양봉 브레이크 또는 진바닥 단가에서 더 싸게 진입한다.
    """
    gid = str(gate_id or "").upper().strip()
    if gid in ("G4", "BG4", "DL_G6", "DL10"):
        return True, "IMMEDIATE_BULL_GATE"
    if bool(is_bull_bar):
        return True, "IMMEDIATE_BULL_BAR"
    if safe_float(dd_from_pre_high_pct, 0.0) <= SMART_WAIT_DEEP_DD_PCT:
        return True, "IMMEDIATE_DEEP_BOTTOM"
    if safe_float(qqq_vel_1m_pct, 0.0) >= DL10_MIN_QQQ_VEL_1M_PCT:
        return True, "IMMEDIATE_QQQ_REBOUND"
    return False, "SMART_WAIT_FALLING_KNIFE"


# ---------------------------------------------------------------------------
# [핵심 4] 08:15 EST 이후 안전망 함수 (HOLD 모드 시 장중 흔들기 손절 OFF & 하위 호환 유지)
# ---------------------------------------------------------------------------
def evaluate_directional_3stage_safety_net_v2(
    hm: int,
    is_trailing_armed: bool,
    entry_price: float,
    live_price: float,
    post_entry_min_price: float,
    prev_reg_close: float,
    pre_open_price: float,
    is_bull_bar: bool,
    is_ha_bull: bool,
    nq_entry_bear_amp_pct: float,
    qqq_vel_1m_pct: float,
    qqq_vel_3m_pct: float,
    qqq_chg_from_entry_pct: float = 0.0,
    entry_qqq_price: float = 0.0,
    qqq_live_price: float = 0.0,
    safety_hold_mode: bool = False,
) -> Tuple[bool, str, str, float]:
    """
    # MODIFIED [Case 93 : 변형 선택지 A 장중 HOLD 모드(safety_hold_mode=True) 및 SN4_DEEP_1000 / SN3_SMART_HYBRID 호환]:
    - safety_hold_mode=True (변형 선택지 A 기본값)일 때는 정규장 개장 직후(09:45 ~ 11:10 EST)의
      일시적 언더슈팅에 바닥 손절당하지 않도록 장중 안전망 손절을 OFF(False, "", "HOLD_MODE_ACTIVE")하고
      오후 15:00 VWAP 탈출 및 15:59 MOC 까지 평균회귀를 기다린다.
    - safety_hold_mode=False 로 호출될 때는 기존 SN4_DEEP_1000 / SN3_SMART_HYBRID 결합형 안전망이 그대로 작동한다.
    """
    bear_amp = max(
        0.0, safe_float(nq_entry_bear_amp_pct, SAFETY_QQQ_BASE_AMP_PCT)
    )
    dyn_thr = round(
        min(
            SAFETY_DYN_QQQ_MAX_THR_PCT,
            max(
                bear_amp * SAFETY_QQQ_AMP_CUT_RATIO,
                SAFETY_DYN_QQQ_MIN_THR_PCT,
            ),
        ),
        2,
    )

    if bool(safety_hold_mode):
        return False, "", "HOLD_MODE_ACTIVE", dyn_thr

    if int(hm) < ASSASSIN_MACRO_CUTOFF_HM or bool(is_trailing_armed):
        return False, "", "PRE_0815_OR_ARMED", dyn_thr

    ep = max(0.01, safe_float(entry_price, 10.0))
    lp = max(0.01, safe_float(live_price, ep))
    cur_gain_pct = ((lp - ep) / ep) * 100.0

    eq_p = max(0.0, safe_float(entry_qqq_price, 0.0))
    lq_p = max(0.0, safe_float(qqq_live_price, 0.0))
    if eq_p > 0.0 and lq_p > 0.0:
        qqq_chg_from_entry = ((lq_p - eq_p) / eq_p) * 100.0
    else:
        qqq_chg_from_entry = safe_float(qqq_chg_from_entry_pct, 0.0)

    if cur_gain_pct >= 0.0:
        return False, "", "HOLD_PROFIT_ZONE", dyn_thr

    v1 = safe_float(qqq_vel_1m_pct, 0.0)
    v3 = safe_float(qqq_vel_3m_pct, 0.0)
    if qqq_chg_from_entry >= 0.0 and v3 > -dyn_thr:
        return False, "", "HOLD_QQQ_ABOVE_ENTRY", dyn_thr

    post_min = max(0.01, safe_float(post_entry_min_price, lp))
    is_making_new_low = bool(lp <= post_min + 1e-4)
    prev_c = safe_float(prev_reg_close, 0.0)
    pre_o = safe_float(pre_open_price, 0.0)
    above_key_anchors = bool(
        (prev_c > 0.0 and lp >= prev_c) or (pre_o > 0.0 and lp >= pre_o)
    )

    is_safety_net_rising = bool(
        is_bull_bar
        or is_ha_bull
        or (v1 >= 0.0)
        or (v3 >= 0.0)
        or above_key_anchors
        or (not is_making_new_low)
    )

    qqq_drop_from_entry_mag = (
        abs(qqq_chg_from_entry) if qqq_chg_from_entry < 0.0 else 0.0
    )
    qqq_vel3_drop_mag = abs(v3) if v3 < 0.0 else 0.0
    eff_qqq_drop_pct = max(qqq_drop_from_entry_mag, qqq_vel3_drop_mag)

    if eff_qqq_drop_pct >= dyn_thr - 1e-9:
        if is_safety_net_rising:
            return False, "", "HOLD_RISING_OR_MILD_DIP", dyn_thr

        is_severe_soxl_crash = bool(
            cur_gain_pct <= SAFETY_STAGE1_HEART_STOP_PCT
            or (
                cur_gain_pct <= SAFETY_STAGE23_SOXL_LOSS_MAX_PCT
                and (
                    v1 < 0.0
                    or v3 <= SAFETY_STAGE23_QQQ_VEL3M_DROP_PCT
                    or qqq_drop_from_entry_mag >= dyn_thr - 1e-9
                )
            )
        )
        if not is_severe_soxl_crash:
            return False, "", "HOLD_RISING_OR_MILD_DIP", dyn_thr

        desc = (
            f"SN4×SN3 스마트 안전망 칼손절(출동QQQ대비 {qqq_chg_from_entry:+.2f}% "
            f"[기준 -{dyn_thr:.2f}%] · QQQ3m {v3:+.2f}% · "
            f"SOXL {cur_gain_pct:+.2f}% 음봉 신저가 진성하락)"
        )
        return True, "STAGE23_DIR_BEAR_BREAK", desc, dyn_thr

    return False, "", "HOLD_NORMAL_MONITOR", dyn_thr


# ---------------------------------------------------------------------------
# [핵심 5] SOXL & QQQ 1분봉(최대 400봉=2페이지) + 1d 일봉(10봉) 자동 프리워밍 및 무오염 추출기
# ---------------------------------------------------------------------------
_LAST_ASSASSIN_WARMUP_MONO: Dict[str, float] = {"SOXL": 0.0, "QQQ": 0.0}
_ASSASSIN_WARMUP_INTERVAL_SEC: float = 55.0


def _has_today_0407_open_bar_in_candles(
    candles: List[Dict[str, Any]], today_str: str
) -> bool:
    """
    수집된 1분봉 배열 안에 당일 프리장 오프닝 구간(04:00 ~ 04:15 EST) 캔들이 포함되어 있는지 판별한다.
    """
    if not candles:
        return False
    for c in candles:
        if not isinstance(c, dict):
            continue
        ts_raw = str(
            c.get("timestamp")
            or c.get("dt")
            or c.get("date")
            or c.get("time")
            or ""
        ).strip()
        if not ts_raw:
            continue
        try:
            if ts_raw.endswith("Z"):
                ts_raw = ts_raw[:-1] + "+00:00"
            dt_est = datetime.fromisoformat(ts_raw).astimezone(EST_TZ)
            if dt_est.strftime("%Y-%m-%d") == today_str:
                hm = dt_est.hour * 100 + dt_est.minute
                if 400 <= hm <= 415:
                    return True
        except Exception:
            continue
    return False


async def _ensure_assassin_candles_warmed_up(
    context: Any,
    now_est: datetime,
    force_warmup: bool = False,
    need_full_premarket: bool = False,
) -> None:
    """
    # [Case 93 : SOXL 1m(최대 400봉[2페이지]) + SOXL 1d(10봉) + QQQ 1m(120봉) 정밀 프리워밍]:
    """
    api = getattr(context, "api", None)
    if api is None:
        return

    cache = getattr(context, "candle_metrics_cache", None)
    if not isinstance(cache, dict):
        cache = {}
        try:
            setattr(context, "candle_metrics_cache", cache)
        except Exception:
            pass

    now_mono = time.monotonic()
    today_str = now_est.strftime("%Y-%m-%d")
    hm = now_est.hour * 100 + now_est.minute

    soxl_m = cache.get(TARGET_SYMBOL) or {}
    soxl_last_mono = _LAST_ASSASSIN_WARMUP_MONO.get(TARGET_SYMBOL, 0.0)
    soxl_prev_bar = safe_float(soxl_m.get("prev_bar_close"), 0.0)
    soxl_pre_open = safe_float(soxl_m.get("pre_open_price"), 0.0)
    soxl_pre_vwap = safe_float(soxl_m.get("premarket_vwap"), 0.0)
    soxl_prev_reg = safe_float(soxl_m.get("prev_reg_close"), 0.0)

    is_premarket_session = bool(407 <= hm < 930)
    need_soxl_anchor = bool(
        need_full_premarket
        and (
            soxl_prev_reg <= 0.0
            or (
                is_premarket_session
                and (soxl_pre_open <= 0.0 or soxl_pre_vwap <= 0.0)
            )
            or _is_collapsed_assassin_anchors(
                soxl_prev_reg, soxl_pre_open, soxl_pre_vwap
            )
        )
    )

    if (
        force_warmup
        or soxl_prev_bar <= 0.0
        or need_soxl_anchor
        or (now_mono - soxl_last_mono >= _ASSASSIN_WARMUP_INTERVAL_SEC)
    ):
        _LAST_ASSASSIN_WARMUP_MONO[TARGET_SYMBOL] = now_mono
        try:
            fetch_cnt = (
                400 if (force_warmup or need_soxl_anchor or hm >= 700) else 200
            )
            candles_soxl = await api.get_candles_1m(
                TARGET_SYMBOL, total_count=fetch_cnt
            )
            if (
                candles_soxl
                and fetch_cnt < 400
                and 407 <= hm < 930
                and not _has_today_0407_open_bar_in_candles(
                    candles_soxl, today_str
                )
            ):
                candles_400 = await api.get_candles_1m(
                    TARGET_SYMBOL, total_count=400
                )
                if candles_400:
                    candles_soxl = candles_400

            daily_soxl: List[Dict[str, Any]] = []
            if hasattr(api, "get_candles_1d"):
                try:
                    daily_soxl = await api.get_candles_1d(
                        TARGET_SYMBOL, count=10
                    )
                except Exception:
                    daily_soxl = []

            if candles_soxl:
                live_p = safe_float(
                    candles_soxl[-1].get("closePrice")
                    or candles_soxl[-1].get("close"),
                    0.0,
                )
                metrics_soxl = await asyncio.to_thread(
                    compute_soxl_quant_metrics_1m,
                    candles_soxl,
                    live_p,
                    now_est,
                    daily_soxl,
                )
                if isinstance(metrics_soxl, dict) and bool(
                    metrics_soxl.get("is_valid", False)
                ):
                    cache[TARGET_SYMBOL] = metrics_soxl
        except Exception:
            pass

    qqq_m = cache.get(MACRO_REF_SYMBOL) or {}
    qqq_last_mono = _LAST_ASSASSIN_WARMUP_MONO.get(MACRO_REF_SYMBOL, 0.0)
    qqq_live_cached = safe_float(qqq_m.get("qqq_live_price"), 0.0)
    if (
        force_warmup
        or qqq_live_cached <= 0.0
        or (now_mono - qqq_last_mono >= _ASSASSIN_WARMUP_INTERVAL_SEC)
    ):
        _LAST_ASSASSIN_WARMUP_MONO[MACRO_REF_SYMBOL] = now_mono
        try:
            qqq_cnt = 400 if (force_warmup or hm >= 700) else 120
            candles_qqq = await api.get_candles_1m(
                MACRO_REF_SYMBOL, total_count=qqq_cnt
            )
            if candles_qqq:
                q_lp = safe_float(
                    candles_qqq[-1].get("closePrice")
                    or candles_qqq[-1].get("close"),
                    0.0,
                )
                metrics_qqq = await asyncio.to_thread(
                    compute_qqq_macro_metrics_1m,
                    candles_qqq,
                    q_lp,
                    now_est,
                )
                if isinstance(metrics_qqq, dict) and bool(
                    metrics_qqq.get("is_valid", False)
                ):
                    cache[MACRO_REF_SYMBOL] = metrics_qqq
        except Exception:
            pass


async def _extract_live_assassin_features_and_qqq_snapshot(
    context: Any,
    now_est: datetime,
    ledger: Optional[AssassinSimLedger] = None,
    force_warmup: bool = False,
) -> Dict[str, Any]:
    """
    # MODIFIED [Case 93 : 실시간 4대 핵심 지표 + 정책 4(vel_5m_pct, dd_from_pre_high_pct) + QQQ 거시 지표 스냅샷 추출 + 2단계 하이브리드 원장 영속화]:
    """
    st_led = ledger.get_state() if ledger is not None else {}
    led_prev_ver = bool(st_led.get("today_prev_close_verified", False))
    led_open_ver = bool(st_led.get("today_pre_open_verified", False))
    led_vwap_ver = bool(st_led.get("today_pre_vwap_verified", False))

    led_prev_c = (
        safe_float(st_led.get("today_prev_reg_close"), 0.0)
        if led_prev_ver
        else 0.0
    )
    led_pre_o = (
        safe_float(st_led.get("today_pre_open_price"), 0.0)
        if led_open_ver
        else 0.0
    )
    led_pre_v = (
        safe_float(st_led.get("today_premarket_vwap"), 0.0)
        if led_vwap_ver
        else 0.0
    )
    led_reg_v = safe_float(st_led.get("today_regular_vwap"), 0.0)

    if _is_collapsed_assassin_anchors(led_prev_c, led_pre_o, led_pre_v):
        led_prev_ver = False
        led_open_ver = False
        led_vwap_ver = False
        led_prev_c = 0.0
        led_pre_o = 0.0
        led_pre_v = 0.0

    hm = now_est.hour * 100 + now_est.minute
    is_premarket_now = bool(407 <= hm < 930)
    need_full = bool(
        force_warmup
        or (not led_prev_ver)
        or (is_premarket_now and (not led_open_ver or not led_vwap_ver))
    )

    await _ensure_assassin_candles_warmed_up(
        context,
        now_est,
        force_warmup=force_warmup,
        need_full_premarket=need_full,
    )

    api = getattr(context, "api", None)
    cache = getattr(context, "candle_metrics_cache", None)
    if not isinstance(cache, dict):
        cache = {}

    soxl_m = copy.deepcopy(cache.get(TARGET_SYMBOL) or {})
    qqq_m = copy.deepcopy(cache.get(MACRO_REF_SYMBOL) or {})

    live_p = safe_float(
        soxl_m.get("current_price") or soxl_m.get("close"), 0.0
    )
    qqq_lp = safe_float(qqq_m.get("qqq_live_price"), 0.0)

    if api is not None and hasattr(api, "get_prices"):
        try:
            prices_map = await api.get_prices(
                [TARGET_SYMBOL, MACRO_REF_SYMBOL]
            )
            if isinstance(prices_map, dict):
                p_soxl = safe_float(prices_map.get(TARGET_SYMBOL), 0.0)
                p_qqq = safe_float(prices_map.get(MACRO_REF_SYMBOL), 0.0)
                if p_soxl > 0.0:
                    live_p = p_soxl
                if p_qqq > 0.0:
                    qqq_lp = p_qqq
        except Exception:
            pass

    if live_p > 0.0 and soxl_m:
        soxl_m = refresh_metrics_with_live_tick(soxl_m, live_p)
        cache[TARGET_SYMBOL] = soxl_m

    rsi_14 = round(safe_float(soxl_m.get("rsi_14"), 50.0), 2)
    m_prev_c = safe_float(soxl_m.get("prev_reg_close"), 0.0)
    m_pre_o = safe_float(soxl_m.get("pre_open_price"), 0.0)
    m_pre_v = safe_float(soxl_m.get("premarket_vwap"), 0.0)
    m_reg_v = safe_float(
        soxl_m.get("regular_vwap") or soxl_m.get("active_vwap"), 0.0
    )

    if _is_collapsed_assassin_anchors(m_prev_c, m_pre_o, m_pre_v):
        m_pre_o = 0.0
        m_pre_v = 0.0

    prev_reg_close = m_prev_c if m_prev_c > 0.0 else led_prev_c
    prev_close_verified = bool(prev_reg_close > 0.0)

    if m_pre_o > 0.0:
        pre_open_price = m_pre_o
        pre_open_verified = True
    elif led_open_ver and led_pre_o > 0.0:
        pre_open_price = led_pre_o
        pre_open_verified = True
    else:
        pre_open_price = 0.0
        pre_open_verified = False

    if m_pre_v > 0.0:
        pre_vwap = m_pre_v
        pre_vwap_verified = True
    elif led_vwap_ver and led_pre_v > 0.0:
        pre_vwap = led_pre_v
        pre_vwap_verified = True
    else:
        pre_vwap = 0.0
        pre_vwap_verified = False

    reg_vwap = (
        m_reg_v
        if m_reg_v > 0.0
        else (led_reg_v if led_reg_v > 0.0 else live_p)
    )

    if ledger is not None and live_p > 0.0:
        need_save = False
        upd_kw: Dict[str, Any] = {}
        if prev_close_verified and (
            not led_prev_ver
            or abs(prev_reg_close - led_prev_c) > 1e-4
        ):
            upd_kw["today_prev_reg_close"] = round(prev_reg_close, 4)
            upd_kw["today_prev_close_verified"] = True
            need_save = True
        if pre_open_verified and (
            not led_open_ver or abs(pre_open_price - led_pre_o) > 1e-4
        ):
            upd_kw["today_pre_open_price"] = round(pre_open_price, 4)
            upd_kw["today_pre_open_verified"] = True
            need_save = True
        elif not pre_open_verified and safe_float(
            st_led.get("today_pre_open_price"), 0.0
        ) > 0.0:
            upd_kw["today_pre_open_price"] = 0.0
            upd_kw["today_pre_open_verified"] = False
            need_save = True

        if pre_vwap_verified and (
            not led_vwap_ver or abs(pre_vwap - led_pre_v) > 1e-4
        ):
            upd_kw["today_premarket_vwap"] = round(pre_vwap, 4)
            upd_kw["today_pre_vwap_verified"] = True
            need_save = True
        elif not pre_vwap_verified and safe_float(
            st_led.get("today_premarket_vwap"), 0.0
        ) > 0.0:
            upd_kw["today_premarket_vwap"] = 0.0
            upd_kw["today_pre_vwap_verified"] = False
            need_save = True

        if reg_vwap > 0.0 and abs(reg_vwap - led_reg_v) > 1e-4:
            upd_kw["today_regular_vwap"] = round(reg_vwap, 4)
            need_save = True

        upd_kw["today_anchors_locked"] = bool(
            prev_close_verified and pre_open_verified and pre_vwap_verified
        )
        if need_save:
            await ledger.update_state(**upd_kw)

    vs_vwap_pct = (
        round(((live_p - pre_vwap) / pre_vwap) * 100.0, 2)
        if (live_p > 0.0 and pre_vwap > 0.0)
        else 0.0
    )
    vs_prev_close_pct = (
        round(((live_p - prev_reg_close) / prev_reg_close) * 100.0, 2)
        if (live_p > 0.0 and prev_reg_close > 0.0)
        else 0.0
    )
    vs_pre_open_pct = (
        round(((live_p - pre_open_price) / pre_open_price) * 100.0, 2)
        if (live_p > 0.0 and pre_open_price > 0.0)
        else 0.0
    )

    pre_high = safe_float(soxl_m.get("premarket_high"), 0.0)
    dd_from_pre_high_pct = safe_float(
        soxl_m.get("dd_from_pre_high_pct"),
        (((live_p - pre_high) / pre_high) * 100.0)
        if (live_p > 0.0 and pre_high > 0.0)
        else 0.0,
    )
    soxl_vel_5m_pct = safe_float(soxl_m.get("vel_5m_pct"), 0.0)

    return {
        "is_valid": bool(live_p > 0.0),
        "live_price": round(live_p, 4),
        "rsi_14": rsi_14,
        "pre_vwap": round(pre_vwap, 4),
        "vs_vwap_pct": vs_vwap_pct,
        "regular_vwap": round(reg_vwap, 4),
        "prev_reg_close": round(prev_reg_close, 4),
        "vs_prev_close_pct": vs_prev_close_pct,
        "pre_open_price": round(pre_open_price, 4),
        "vs_pre_open_pct": vs_pre_open_pct,
        "premarket_high": round(pre_high, 4),
        "dd_from_pre_high_pct": round(dd_from_pre_high_pct, 2),
        "vel_1m_pct": round(safe_float(soxl_m.get("vel_1m_pct"), 0.0), 3),
        "vel_3m_pct": round(safe_float(soxl_m.get("vel_3m_pct"), 0.0), 3),
        "vel_5m_pct": round(soxl_vel_5m_pct, 3),
        "is_bull_bar": bool(soxl_m.get("is_bull_bar", True)),
        "is_ha_bull": bool(soxl_m.get("is_ha_bull", True)),
        "qqq_live_price": round(qqq_lp, 4),
        "qqq_vel_1m_pct": round(
            safe_float(qqq_m.get("qqq_vel_1m_pct"), 0.0), 3
        ),
        "qqq_vel_3m_pct": round(
            safe_float(qqq_m.get("qqq_vel_3m_pct"), 0.0), 3
        ),
        "qqq_vel_10m_pct": round(
            safe_float(qqq_m.get("qqq_vel_10m_pct"), 0.0), 3
        ),
        "nq_bear_amp_pct": round(
            max(
                SAFETY_QQQ_BASE_AMP_PCT,
                safe_float(
                    qqq_m.get("qqq_bear_drop_amp_pct"),
                    SAFETY_QQQ_BASE_AMP_PCT,
                ),
            ),
            2,
        ),
    }


# ---------------------------------------------------------------------------
# [핵심 6] [모의 ⇄ 실전 Dual-Ready] 주문 실행 어댑터 (현재 ASSASSIN_LIVE_ORDER_HARD_LOCK = True)
# ---------------------------------------------------------------------------
async def _dispatch_assassin_buy_order(
    context: Any, qty: int, limit_price: float
) -> Tuple[bool, str, float]:
    """
    Dual-Ready 매수 주문 어댑터:
    - ASSASSIN_LIVE_ORDER_HARD_LOCK == True (현재): 토스 API 호출 없이 모의 즉시 체결 반환.
    - ASSASSIN_LIVE_ORDER_HARD_LOCK == False (향후 실전 전환 시):
      POST /api/v1/orders LIMIT BUY 발주 및 체결 확인 수행.
    """
    exec_p = round(max(0.01, safe_float(limit_price, 10.0)), 2)
    if ASSASSIN_LIVE_ORDER_HARD_LOCK:
        sim_oid = generate_client_order_id("SIM-ASSN-BUY")
        return True, sim_oid, exec_p

    api = getattr(context, "api", None)
    if api is None:
        return False, "", exec_p
    cid = generate_client_order_id("ASSN-BUY")
    res = await api.create_limit_order(
        symbol=TARGET_SYMBOL,
        side="BUY",
        quantity=max(1, int(qty)),
        price=exec_p,
        client_order_id=cid,
        enforce_daymarket_block=True,
    )
    oid = str((res or {}).get("orderId") or "").strip()
    return bool(oid), oid, exec_p


async def _dispatch_assassin_safe_cap_sell_order(
    context: Any, qty: int, cap_500_price: float
) -> Tuple[bool, str]:
    """
    Dual-Ready 본대 진입 직후 +5.00% 상단 안전 캡 지정가 매도 선장전 어댑터.
    """
    cap_p = round(max(0.01, safe_float(cap_500_price, 10.0)), 2)
    if ASSASSIN_LIVE_ORDER_HARD_LOCK:
        sim_oid = generate_client_order_id("SIM-ASSN-CAP500")
        return True, sim_oid

    api = getattr(context, "api", None)
    if api is None:
        return False, ""
    cid = generate_client_order_id("ASSN-CAP500")
    res = await api.create_limit_order(
        symbol=TARGET_SYMBOL,
        side="SELL",
        quantity=max(1, int(qty)),
        price=cap_p,
        client_order_id=cid,
        enforce_daymarket_block=False,
    )
    oid = str((res or {}).get("orderId") or "").strip()
    return bool(oid), oid


async def _dispatch_assassin_exit_sweep_order(
    context: Any,
    existing_sell_order_id: str,
    qty: int,
    target_exit_price: float,
) -> Tuple[bool, str, float]:
    """
    Dual-Ready 익절/안전망/MOC 스윕 어댑터:
    - ASSASSIN_LIVE_ORDER_HARD_LOCK == True (현재): 모의 즉시 체결 처리.
    - ASSASSIN_LIVE_ORDER_HARD_LOCK == False (향후 실전 전환 시):
      선장전된 +5.00% 안전 캡 매도 주문(existing_sell_order_id)이 있으면
      POST /api/v1/orders/{orderId}/modify (quantity 제외, price 만 전송)로 0.1초 즉시 가격 정정 스윕!
    """
    sweep_p = round(max(0.01, safe_float(target_exit_price, 10.0)), 2)
    if ASSASSIN_LIVE_ORDER_HARD_LOCK:
        sim_oid = (
            existing_sell_order_id
            or generate_client_order_id("SIM-ASSN-EXIT")
        )
        return True, sim_oid, sweep_p

    api = getattr(context, "api", None)
    if api is None:
        return False, "", sweep_p

    if existing_sell_order_id:
        mod_res = await api.modify_order_price_us(
            order_id=existing_sell_order_id, new_price=sweep_p
        )
        new_oid = str(
            (mod_res or {}).get("orderId") or existing_sell_order_id
        ).strip()
        return True, new_oid, sweep_p

    cid = generate_client_order_id("ASSN-EXIT")
    res = await api.create_limit_order(
        symbol=TARGET_SYMBOL,
        side="SELL",
        quantity=max(1, int(qty)),
        price=sweep_p,
        client_order_id=cid,
        enforce_daymarket_block=False,
    )
    oid = str((res or {}).get("orderId") or "").strip()
    return bool(oid), oid, sweep_p


# ---------------------------------------------------------------------------
# [핵심 7] 5대 라이프사이클 실시간 텔레그램 푸시 알림 & 데이터 수집용 [진입 ➔ 청산 복기 스냅샷] 포맷터
# ---------------------------------------------------------------------------
async def _send_assassin_telegram_push(
    context: Any, html_msg: str
) -> None:
    tg = getattr(context, "tg", None)
    if tg is not None and hasattr(tg, "send_slim_alert"):
        try:
            await tg.send_slim_alert(html_msg)
        except Exception as e:
            logger.debug(f"암살자 텔레그램 알림 발송 생략: {e}")


def _fmt_anchor_price_and_pct(
    price_val: float, pct_val: float
) -> str:
    """
    # [Case 93 : 프리장 미확보 앵커($0.00) 깔끔 표출 포맷터]:
    """
    p = safe_float(price_val, 0.0)
    c = safe_float(pct_val, 0.0)
    if p <= 0.0:
        return "$0.00 (0.00%)"
    return f"${p:,.2f} ({c:+.2f}%)"


def _format_assassin_trade_review_block(st: Dict[str, Any]) -> str:
    """
    # MODIFIED [Case 93 : 변형 선택지 A (2단래칫 +1.00% ➔ +1.25% + HOLD) 데이터 수집용 진입 ➔ 청산 복기 스냅샷 생성기]:
    """
    gid = html.escape(str(st.get("entry_gate_id") or "G1"))
    gdesc = html.escape(str(st.get("entry_gate_desc") or ""))
    trig_m = html.escape(str(st.get("entry_trigger_mode") or "SCOUT_GATE"))
    sc_seq = safe_int(st.get("entry_scout_seq"), 1)
    pr_wins = safe_int(st.get("entry_prior_scout_wins"), 0)

    ep = safe_float(st.get("entry_price"), 0.0)
    e_rsi = safe_float(st.get("entry_rsi_14"), 50.0)
    e_bull = "양봉🟢" if bool(st.get("entry_is_bull_bar", True)) else "음봉🔴"
    e_ha = "HA🟢" if bool(st.get("entry_is_ha_bull", True)) else "HA🔴"
    e_vwap_txt = _fmt_anchor_price_and_pct(
        safe_float(st.get("entry_vwap"), 0.0),
        safe_float(st.get("entry_vs_vwap_pct"), 0.0),
    )
    e_prev_txt = _fmt_anchor_price_and_pct(
        safe_float(st.get("entry_prev_close"), 0.0),
        safe_float(st.get("entry_vs_prev_close_pct"), 0.0),
    )
    e_open_txt = _fmt_anchor_price_and_pct(
        safe_float(st.get("entry_pre_open"), 0.0),
        safe_float(st.get("entry_vs_pre_open_pct"), 0.0),
    )
    e_sc1_pct = safe_float(st.get("entry_vs_scout1_pct"), 0.0)

    pk_p = safe_float(st.get("peak_price"), ep)
    mn_p = safe_float(st.get("post_entry_min_price"), ep)
    pk_pct = ((pk_p - ep) / ep * 100.0) if ep > 0.0 else 0.0
    mn_pct = ((mn_p - ep) / ep * 100.0) if ep > 0.0 else 0.0
    armed1 = bool(st.get("is_trailing_armed", False))
    armed2 = bool(st.get("is_stage2_boost_armed", False))
    armed1_t = str(st.get("armed_time_est") or "").strip()
    armed2_t = str(st.get("stage2_armed_time_est") or "").strip()
    if armed2:
        armed_str = f"2차부스트점화(+1.25% · {html.escape(armed2_t or armed1_t)})"
    elif armed1:
        armed_str = f"1차잠금완료(+1.00% · {html.escape(armed1_t)})"
    else:
        armed_str = "미점화(HOLD)"

    x_rsi = safe_float(st.get("today_exit_rsi_14"), 50.0)
    x_bull = (
        "양봉🟢" if bool(st.get("today_exit_is_bull_bar", True)) else "음봉🔴"
    )
    x_ha = "HA🟢" if bool(st.get("today_exit_is_ha_bull", True)) else "HA🔴"
    x_reg_v_txt = _fmt_anchor_price_and_pct(
        safe_float(st.get("today_exit_reg_vwap"), 0.0),
        safe_float(st.get("today_exit_vs_reg_vwap_pct"), 0.0),
    )
    x_pre_v_txt = _fmt_anchor_price_and_pct(
        safe_float(st.get("today_exit_pre_vwap"), 0.0),
        safe_float(st.get("today_exit_vs_pre_vwap_pct"), 0.0),
    )

    eq_qqq = safe_float(st.get("entry_qqq_price"), 0.0)
    xq_qqq = safe_float(st.get("today_exit_qqq_price"), 0.0)
    qqq_chg = safe_float(st.get("qqq_chg_from_entry_pct"), 0.0)
    eq_v1 = safe_float(st.get("entry_qqq_vel_1m_pct"), 0.0)
    eq_v3 = safe_float(st.get("entry_qqq_vel_3m_pct"), 0.0)
    xq_v1 = safe_float(st.get("today_exit_qqq_vel_1m_pct"), 0.0)
    xq_v3 = safe_float(st.get("today_exit_qqq_vel_3m_pct"), 0.0)

    return "\n".join(
        [
            "📋 <b>[데이터 수집용 진입 ➔ 청산 복기 스냅샷]</b>",
            f"• 작동게이트: <b>{gid}</b> ({gdesc})",
            f"• 포착경로: <code>{trig_m}</code> · 정찰 <b>#{sc_seq}</b> (선행익절 <b>{pr_wins}회</b>)",
            f"• 진입지표①: RSI <b>{e_rsi:.1f}</b> ({e_bull}/{e_ha}) · 프리VWAP <code>{e_vwap_txt}</code>",
            f"• 진입지표②: 전일종가 <code>{e_prev_txt}</code> · 04:07시가 <code>{e_open_txt}</code> · 선봉대비 <code>{e_sc1_pct:+.2f}%</code>",
            f"• 보유궤적: 고점 <b>${pk_p:,.2f} ({pk_pct:+.2f}%)</b> / 저점 <b>${mn_p:,.2f} ({mn_pct:+.2f}%)</b> · {armed_str}",
            f"• 청산지표: RSI <b>{x_rsi:.1f}</b> ({x_bull}/{x_ha}) · 정규VWAP <code>{x_reg_v_txt}</code> · 프리VWAP <code>{x_pre_v_txt}</code>",
            f"• QQQ궤적: 출동 <b>${eq_qqq:,.2f}</b>(1m {eq_v1:+.2f}%/3m {eq_v3:+.2f}%) ➔ 청산 <b>${xq_qqq:,.2f}</b>(<b>{qqq_chg:+.2f}%</b> · 1m {xq_v1:+.2f}%/3m {xq_v3:+.2f}%)",
        ]
    )


async def _send_1_scout_dispatched_alert(
    context: Any,
    scout: IndependentScoutUnit,
    active_cnt: int,
    prior_wins: int,
) -> None:
    """
    [알림 ① : 🕵️ 정찰병 파견 시 (04:07 첫 선봉 #1 및 후속 #2, #3... 정찰병 투입 알림)]
    """
    vwap_txt = _fmt_anchor_price_and_pct(
        scout.pre_vwap, scout.vs_vwap_pct
    )
    prev_txt = _fmt_anchor_price_and_pct(
        scout.prev_reg_close, scout.vs_prev_close_pct
    )
    open_txt = _fmt_anchor_price_and_pct(
        scout.pre_open_price, scout.vs_pre_open_pct
    )
    msg = (
        f"🕵️ <b>[모의 암살자 · 정찰병 #{scout.scout_id} 파견]</b>\n"
        f"• 시각/유형: <code>{html.escape(scout.entry_time_est)} EST</code> · "
        f"<code>{html.escape(scout.entry_type)}</code>\n"
        f"• 정찰단가: <b>${scout.entry_price:,.2f}</b> (1주 가상 · 익절목표 ${scout.target_price:,.2f})\n"
        f"• 핵심지표 ① RSI(14): <b>{scout.rsi_14:.1f}</b> "
        f"({'양봉🟢' if scout.is_bull_bar else '음봉🔴'})\n"
        f"• 핵심지표 ② 프리VWAP: <code>{vwap_txt}</code>\n"
        f"• 핵심지표 ③ 전일종가: <code>{prev_txt}</code>\n"
        f"• 핵심지표 ④ 04:07시가: <code>{open_txt}</code>\n"
        f"• 정찰대오: 독립보유 <b>{active_cnt}/7명</b> · 금일 정찰익절 <b>{prior_wins}회</b>"
    )
    await _send_assassin_telegram_push(context, msg)


async def _send_2_0815_no_trade_retire_alert(
    context: Any, st: Dict[str, Any], feat: Dict[str, Any]
) -> None:
    """
    [알림 ② : 🏠 프리장(04:07~08:14) 및 거시지표 진바닥(08:30~09:20 DL10) 스캔 후 무매매 안전 퇴근 시]
    """
    sc_cnt = safe_int(st.get("day_scout_seq"), 0)
    sc_wins = safe_int(st.get("prior_scout_wins_today"), 0)
    lp = safe_float(feat.get("live_price"), 0.0)
    rsi = safe_float(feat.get("rsi_14"), 50.0)
    vw_pct = safe_float(feat.get("vs_vwap_pct"), 0.0)
    msg = (
        f"🏠 <b>[모의 암살자 · 프리장 & DL10 무매매 안전 퇴근]</b>\n"
        f"• 판정시각: <code>09:21:00 EST</code> (04:07~08:14 진성10/G6 & 08:30~09:20 DL10 스캔 완료)\n"
        f"• 정찰요약: 총 <b>{sc_cnt}명</b> 파견 · 독립익절 <b>{sc_wins}회</b> (진입 조건 미충족)\n"
        f"• 마감지표: 현재가 <b>${lp:,.2f}</b> · RSI <b>{rsi:.1f}</b> · VWAP괴리 <code>{vw_pct:+.2f}%</code>\n"
        f"• 조치결과: <b>금일 시드 100% 현금 보존 안전 퇴근 완료</b>"
    )
    await _send_assassin_telegram_push(context, msg)


async def _send_3_gate10_main_entry_alert(
    context: Any, st: Dict[str, Any]
) -> None:
    """
    # MODIFIED [알림 ③ : 🗡️ 정책 4 (PRE10/SMART_WAIT/DL_G6/DL10) 본대 진입 시 (2단래칫 +1.00% 1차 잠금가 · +1.25% 2차 부스트가 · +5.00% 캡 명시)]
    """
    ep = safe_float(st.get("entry_price"), 0.0)
    eq_qqq = safe_float(st.get("entry_qqq_price"), 0.0)
    eq_v1 = safe_float(st.get("entry_qqq_vel_1m_pct"), 0.0)
    eq_v3 = safe_float(st.get("entry_qqq_vel_3m_pct"), 0.0)
    cap_p = safe_float(st.get("cap_500_price"), 0.0)
    arm100_p = safe_float(st.get("arm_100_price"), 0.0)
    arm125_p = safe_float(st.get("arm_125_price"), 0.0)
    gid = str(st.get("entry_gate_id") or "G1")
    gdesc = str(st.get("entry_gate_desc") or "")
    trig_mode = str(st.get("entry_trigger_mode") or "SCOUT_10M_GATE")
    sc_seq = safe_int(st.get("entry_scout_seq"), 1)
    pr_wins = safe_int(st.get("entry_prior_scout_wins"), 0)
    s_qty = safe_int(st.get("simple_held_qty"), 0)
    s_inv = safe_float(st.get("simple_invested_usd"), 0.0)
    e_bull = "양봉🟢" if bool(st.get("entry_is_bull_bar", True)) else "음봉🔴"
    e_ha = "HA🟢" if bool(st.get("entry_is_ha_bull", True)) else "HA🔴"

    vwap_txt = _fmt_anchor_price_and_pct(
        safe_float(st.get("entry_vwap"), 0.0),
        safe_float(st.get("entry_vs_vwap_pct"), 0.0),
    )
    prev_txt = _fmt_anchor_price_and_pct(
        safe_float(st.get("entry_prev_close"), 0.0),
        safe_float(st.get("entry_vs_prev_close_pct"), 0.0),
    )
    open_txt = _fmt_anchor_price_and_pct(
        safe_float(st.get("entry_pre_open"), 0.0),
        safe_float(st.get("entry_vs_pre_open_pct"), 0.0),
    )
    sc1_pct = safe_float(st.get("entry_vs_scout1_pct"), 0.0)

    msg = (
        f"🗡️ <b>[모의 암살자 · 게이트 {html.escape(gid)} 포착 본대 진입!]</b>\n"
        f"• 작동게이트: <b>{html.escape(gid)}</b> ({html.escape(gdesc)})\n"
        f"• 포착경로: <code>{html.escape(trig_mode)}</code> · 정찰 <b>#{sc_seq}</b> (선행익절 <b>{pr_wins}회</b>)\n"
        f"• 진입단가: <b>${ep:,.2f}</b> (<code>{html.escape(str(st.get('entry_time_est') or ''))} EST</code> · 가상 <b>{s_qty:,}주</b> / ${s_inv:,.2f})\n"
        f"• 출동QQQ: <b>${eq_qqq:,.2f}</b> (1m <code>{eq_v1:+.2f}%</code> · 3m <code>{eq_v3:+.2f}%</code> · 장중 <b>HOLD</b> 모드)\n"
        f"• 진입지표①: RSI(14) <b>{safe_float(st.get('entry_rsi_14'), 50.0):.1f}</b> ({e_bull}/{e_ha}) · 프리VWAP <code>{vwap_txt}</code>\n"
        f"• 진입지표②: 전일종가 <code>{prev_txt}</code> · 04:07시가 <code>{open_txt}</code> · 선봉대비 <code>{sc1_pct:+.2f}%</code>\n"
        f"• 2단래칫: 1차잠금 <b>${arm100_p:,.2f}(+1.00%)</b> ➔ 2차부스트 <b>${arm125_p:,.2f}(+1.25%)</b> / 안전캡 <b>${cap_p:,.2f}(+5.00%)</b>"
    )
    await _send_assassin_telegram_push(context, msg)


async def _send_4_trailing_ignition_alert(
    context: Any, st: Dict[str, Any], live_price: float
) -> None:
    """
    # MODIFIED [알림 ④-A : 🔒 +1.00% 도달 1차 보존선 하드 잠금 완료 (+1.24% 까지 HA 음봉 무시 홀딩)]
    """
    ep = safe_float(st.get("entry_price"), 0.0)
    arm100_p = safe_float(st.get("arm_100_price"), 0.0)
    arm125_p = safe_float(st.get("arm_125_price"), 0.0)
    cap_p = safe_float(st.get("cap_500_price"), 0.0)
    gid = html.escape(str(st.get("entry_gate_id") or "G1"))
    gain_pct = ((live_price - ep) / ep * 100.0) if ep > 0 else 1.00
    msg = (
        f"🔒 <b>[모의 암살자 · +1.00% 1차 보존선 잠금! (게이트 {gid})]</b>\n"
        f"• 잠금시각: <code>{html.escape(str(st.get('armed_time_est') or ''))} EST</code>\n"
        f"• 현재단가: <b>${live_price:,.2f} ({gain_pct:+.2f}%)</b> [진입가 ${ep:,.2f}]\n"
        f"• 1차방어막: <b>최소 +1.00% 보존선(${arm100_p:,.2f}) 하드 잠금 완료!</b> (HA음봉 흔들기 무시 홀딩)\n"
        f"• 다음목표: 2차 부스트 점화가 <b>${arm125_p:,.2f} (+1.25%)</b> 돌파 대기 (안전캡 ${cap_p:,.2f})"
    )
    await _send_assassin_telegram_push(context, msg)


async def _send_4b_stage2_boost_ignition_alert(
    context: Any, st: Dict[str, Any], live_price: float
) -> None:
    """
    # NEW [알림 ④-B : 🚀 +1.25% 돌파 2차 보존선 격상 및 HA 음봉/콜백 부스트 점화!]
    """
    ep = safe_float(st.get("entry_price"), 0.0)
    arm125_p = safe_float(st.get("arm_125_price"), 0.0)
    cap_p = safe_float(st.get("cap_500_price"), 0.0)
    gid = html.escape(str(st.get("entry_gate_id") or "G1"))
    gain_pct = ((live_price - ep) / ep * 100.0) if ep > 0 else 1.25
    msg = (
        f"🚀 <b>[모의 암살자 · +1.25% 2차 부스트 점화! (게이트 {gid})]</b>\n"
        f"• 점화시각: <code>{html.escape(str(st.get('stage2_armed_time_est') or ''))} EST</code>\n"
        f"• 현재단가: <b>${live_price:,.2f} ({gain_pct:+.2f}%)</b> [진입가 ${ep:,.2f}]\n"
        f"• 2차보존선: <b>최소 +1.25% 보존선(${arm125_p:,.2f})으로 2차 격상 완료!</b>\n"
        f"• 추적모드: <code>0.40초</code> 고주파 HA 양봉 홀딩 & 콜백(-0.20%/-0.30%) 부스트 · 안전캡 <b>${cap_p:,.2f} (+5.00%)</b>"
    )
    await _send_assassin_telegram_push(context, msg)


async def _send_5_exit_and_cumulative_score_alert(
    context: Any, st: Dict[str, Any], exit_desc: str
) -> None:
    """
    # MODIFIED [알림 ⑤ : 🎯 2단래칫 익절 / 15:00 VWAP / 15:59 장마감 MOC 퇴근 완료 및 데이터 수집용 복기 스냅샷 + 누적 성적표 알림]
    """
    ep = safe_float(st.get("entry_price"), 0.0)
    xp = safe_float(st.get("today_exit_price"), 0.0)
    e_time = html.escape(str(st.get("entry_time_est") or ""))
    x_time = html.escape(str(st.get("today_exit_time_est") or ""))
    gain_pct = safe_float(st.get("today_gain_pct"), 0.0)
    s_net = safe_float(st.get("today_simple_net_usd"), 0.0)
    c_net = safe_float(st.get("today_comp_net_usd"), 0.0)

    t_days = safe_int(st.get("total_trade_days"), 0)
    w_days = safe_int(st.get("win_days"), 0)
    win_rate = (w_days / t_days * 100.0) if t_days > 0 else 0.0
    cum_s = safe_float(st.get("simple_cum_net_usd"), 0.0)
    cum_c = safe_float(st.get("comp_cum_net_usd"), 0.0)
    comp_eq = safe_float(st.get("comp_free_cash_usd"), 10000.0)

    review_block = _format_assassin_trade_review_block(st)

    icon = "🎯" if s_net >= 0.0 else "🛡️"
    msg = (
        f"{icon} <b>[모의 암살자 · 청산 퇴근 및 데이터 복기 리포트]</b>\n"
        f"• 청산사유: <b>{html.escape(str(st.get('today_exit_code') or st.get('today_exit_reason') or ''))}</b> ({html.escape(exit_desc)})\n"
        f"• 체결내역: 진입 <b>${ep:,.2f}</b>(<code>{e_time}</code>) ➔ 청산 <b>${xp:,.2f}</b>(<code>{x_time}</code> · <b>{gain_pct:+.2f}%</b>)\n"
        f"• 금일손익: 단리 <b>{s_net:+,.2f}$</b> / 복리 <b>{c_net:+,.2f}$</b> (수수료 차감)\n"
        f"─────────────────\n"
        f"{review_block}\n"
        f"─────────────────\n"
        f"📊 <b>[누적 모의 성적표]</b>\n"
        f"• 누적전적: <b>{t_days}전 {w_days}승 {t_days - w_days}패 (승률 {win_rate:.2f}%)</b>\n"
        f"• 단리누적: <b>{cum_s:+,.2f}$</b>\n"
        f"• 복리누적: <b>{cum_c:+,.2f}$</b> (복리자산 <b>${comp_eq:,.2f}</b>)"
    )
    await _send_assassin_telegram_push(context, msg)
# -*- coding: utf-8 -*-
"""
# MODIFIED: assassin_plugin.py (Part 3/4 — 변형 선택지 A 2단 하이브리드 래칫 [+1.00% 1차 보존잠금(HA음봉 무시 홀딩) ➔ +1.25% 2차 보존선 격상 및 HA음봉/콜백 부스트] + 장중 HOLD 통합 출구 판정기 · 정책 4 SMART_WAIT 5분 스마트 진바닥 대기 및 DL_G6 강세장 급눌림 / T03_A 1분 눌림 스캔 진입 실행기 · Case 93)
"""


# ---------------------------------------------------------------------------
# [핵심 8] 본대 보유 중 통합 출구(2단 하이브리드 래칫 +1.00% ➔ +1.25% · 장중 HOLD · 15:00 VWAP · 15:59 MOC) 판정 및 진입 브릿지
# ---------------------------------------------------------------------------
def _esc(val: Any) -> str:
    return html.escape(str(val if val is not None else ""), quote=False)


async def _sync_context_cache_for_assassin_snapshot(
    context: Any,
    now_est: datetime,
    live_price_override: float = 0.0,
    force_warmup: bool = False,
) -> Dict[str, Any]:
    """
    # NEW [Case 93 : 캔들 캐시 및 실시간 시세 브릿지 동기화기]:
    _extract_live_assassin_features_and_qqq_snapshot 호출 직전에 SOXL 1m(400봉)+1d(10봉) 및
    QQQ 1m(120봉) 캐시 키(current_price, is_bull_bar, is_ha_bull, vel_5m_pct, dd_from_pre_high_pct,
    qqq_live_price, qqq_vel_1m_pct, qqq_vel_3m_pct, qqq_vel_10m_pct, qqq_bear_drop_amp_pct)를 정규화하여 주입한다.
    """
    if context is None:
        return {}

    cache = getattr(context, "candle_metrics_cache", None)
    if not isinstance(cache, dict):
        cache = {}
        try:
            setattr(context, "candle_metrics_cache", cache)
        except Exception:
            pass

    lp = safe_float(live_price_override, 0.0)
    if lp <= 0.0:
        lp = safe_float(
            getattr(context, "latest_prices", {}).get(TARGET_SYMBOL),
            safe_float(getattr(context, "last_soxl_live_price", 0.0), 0.0),
        )
    qqq_lp = safe_float(
        getattr(context, "latest_prices", {}).get(MACRO_REF_SYMBOL),
        safe_float(getattr(context, "last_qqq_live_price", 0.0), 0.0),
    )

    api = getattr(context, "api", None)
    if (lp <= 0.0 or qqq_lp <= 0.0 or force_warmup) and api is not None:
        if hasattr(api, "get_current_prices_batch"):
            try:
                p_map = await api.get_current_prices_batch(
                    (TARGET_SYMBOL, MACRO_REF_SYMBOL)
                )
                if isinstance(p_map, dict):
                    p_s = safe_float(p_map.get(TARGET_SYMBOL), 0.0)
                    p_q = safe_float(p_map.get(MACRO_REF_SYMBOL), 0.0)
                    if p_s > 0.0:
                        lp = p_s
                        if isinstance(
                            getattr(context, "latest_prices", None), dict
                        ):
                            context.latest_prices[TARGET_SYMBOL] = lp
                    if p_q > 0.0:
                        qqq_lp = p_q
                        if isinstance(
                            getattr(context, "latest_prices", None), dict
                        ):
                            context.latest_prices[MACRO_REF_SYMBOL] = qqq_lp
            except Exception:
                pass

    soxl_m = cache.get(TARGET_SYMBOL)
    if not isinstance(soxl_m, dict):
        soxl_m = {}

    need_soxl_warm = bool(
        force_warmup
        or not bool(soxl_m.get("anchors_ready", False))
        or not bool(soxl_m.get("found_true_prev_close", False))
        or safe_float(soxl_m.get("prev_bar_close"), 0.0) <= 0.0
    )
    if need_soxl_warm and api is not None and hasattr(api, "get_candles_1m"):
        try:
            c_1m = await api.get_candles_1m(
                symbol=TARGET_SYMBOL, count=200, total_count=400
            )
            c_1d: List[Dict[str, Any]] = []
            if hasattr(api, "get_candles_1d"):
                try:
                    c_1d = await api.get_candles_1d(
                        symbol=TARGET_SYMBOL, count=10
                    )
                except Exception:
                    c_1d = []
            if c_1m or c_1d:
                soxl_m = await asyncio.to_thread(
                    compute_soxl_quant_metrics_1m,
                    c_1m or [],
                    lp,
                    now_est,
                    c_1d or [],
                )
        except Exception:
            pass

    if lp > 0.0 and isinstance(soxl_m, dict):
        soxl_m = refresh_metrics_with_live_tick(
            soxl_m, lp, now_est=now_est, symbol=TARGET_SYMBOL
        )
    if isinstance(soxl_m, dict):
        eff_lp = safe_float(
            soxl_m.get("live_price") or soxl_m.get("current_price"), lp
        )
        cur_o = safe_float(soxl_m.get("cur_bar_open"), eff_lp)
        soxl_m["current_price"] = round(eff_lp, 4)
        soxl_m["is_bull_bar"] = bool(eff_lp >= cur_o)
        soxl_m["is_ha_bull"] = bool(soxl_m.get("ha_bull", True))
        soxl_m["is_valid"] = bool(eff_lp > 0.0)
        cache[TARGET_SYMBOL] = soxl_m

    qqq_m = cache.get(MACRO_REF_SYMBOL)
    if not isinstance(qqq_m, dict):
        qqq_m = {}
    need_qqq_warm = bool(
        force_warmup or safe_float(qqq_m.get("prev_bar_close"), 0.0) <= 0.0
    )
    if need_qqq_warm and api is not None and hasattr(api, "get_candles_1m"):
        try:
            q_1m = await api.get_candles_1m(
                symbol=MACRO_REF_SYMBOL, count=120, total_count=120
            )
            if q_1m:
                qqq_m = await asyncio.to_thread(
                    compute_qqq_macro_metrics_1m,
                    q_1m,
                    qqq_lp,
                    now_est,
                )
        except Exception:
            pass

    if qqq_lp > 0.0 and isinstance(qqq_m, dict):
        qqq_m = refresh_metrics_with_live_tick(
            qqq_m, qqq_lp, now_est=now_est, symbol=MACRO_REF_SYMBOL
        )
    if isinstance(qqq_m, dict):
        eff_qp = safe_float(
            qqq_m.get("live_price") or qqq_m.get("current_price"), qqq_lp
        )
        qqq_m["qqq_live_price"] = round(eff_qp, 4)
        qqq_m["qqq_vel_1m_pct"] = round(
            safe_float(qqq_m.get("vel_1m_pct"), 0.0), 3
        )
        qqq_m["qqq_vel_3m_pct"] = round(
            safe_float(qqq_m.get("vel_3m_pct"), 0.0), 3
        )
        qqq_m["qqq_vel_10m_pct"] = round(
            safe_float(qqq_m.get("vel_10m_pct"), 0.0), 3
        )
        qqq_m["qqq_bear_drop_amp_pct"] = round(
            max(
                SAFETY_QQQ_BASE_AMP_PCT,
                safe_float(
                    qqq_m.get("bear_drop_amp_pct"), SAFETY_QQQ_BASE_AMP_PCT
                ),
            ),
            2,
        )
        qqq_m["is_valid"] = bool(eff_qp > 0.0)
        cache[MACRO_REF_SYMBOL] = qqq_m

    return {
        "cur_bar_high": round(
            max(
                lp,
                safe_float(
                    (cache.get(TARGET_SYMBOL) or {}).get("cur_bar_high"), lp
                ),
            ),
            4,
        ),
        "cur_bar_low": round(
            safe_float(
                (cache.get(TARGET_SYMBOL) or {}).get("cur_bar_low"), lp
            ),
            4,
        ),
    }


def evaluate_assassin_ha_trailing_and_exits(
    hm: int,
    entry_price: float,
    live_price: float,
    bar_high_price: float,
    is_trailing_armed: bool,
    peak_price: float,
    arm_100_price: float,
    cap_500_price: float,
    soxl_is_bull_bar: bool,
    soxl_is_ha_bull: bool,
    soxl_prev_reg_close: float,
    soxl_pre_open_price: float,
    soxl_reg_vwap: float,
    post_entry_min_price: float,
    qqq_vel_1m_pct: float,
    qqq_vel_3m_pct: float,
    qqq_vel_max_3m_10m_pct: float,
    qqq_bear_drop_amp_pct: float,
    nq_entry_bear_amp_pct: float,
    entry_qqq_price: float = 0.0,
    qqq_live_price: float = 0.0,
    arm_125_price: float = 0.0,
    is_stage2_boost_armed: bool = False,
    safety_hold_mode: bool = ASSASSIN_SAFETY_HOLD_MODE,
) -> Dict[str, Any]:
    """
    # MODIFIED [Case 93 : 변형 선택지 A — 2단 하이브리드 래칫 (+1.00% 1차 보존잠금 ➔ +1.25% 2차 부스트 점화) + 장중 HOLD 통합 출구 판정 엔진]:
    1) +5.00% 상단 안전 캡 도달 시 즉시 홈런 익절 (CAP_500_HOMERUN)
    2) 1차 점화가(+1.00% · arm_100_price) 도달 시 즉시 1차 최소 수익 보존선(+1.00%) 하드 잠금 (is_trailing_armed = True)
    3) 2차 부스트 점화가(+1.25% · arm_125_price) 도달 시 즉시 최소 수익 보존선을 +1.25% 로 2차 격상 및 HA 부스트 점화 (is_stage2_boost_armed = True)
    4) [구간 3 : +1.25% 이상 2차 부스트 점화 상태 (is_stage2_boost_armed == True)]:
       - 2차 보존선(arm_125_price) 하향 터치 시 최소 +1.25% 확정 익절 (TRAIL_FLOOR_125)
       - 최고가(peak_price) 대비 콜백(-0.20%p / +2.00% 이상 시 -0.30%p) 도달 시 부스트 익절 (TRAIL_CALLBACK_BOOST)
       - 1분봉 하이킨 아시 음봉(not soxl_is_ha_bull) 전환 시 (단, QQQ 3m/10m 변화율 >= +0.20% 급등 중이면 바이패스)
         부스트 익절 (TRAIL_HA_RED_BOOST)
    5) [구간 2 : +1.00% ~ +1.24% 1차 잠금 완충 상태 (is_trailing_armed == True and not is_stage2_boost_armed)]:
       - 1분봉 HA 음봉이 나와도 털리지 않고 +1.25% 돌파까지 홀딩 (STAGE1_FLOOR100_LOCKED)!
       - 단, 주가가 다시 밀려 1차 보존선(arm_100_price) 이하로 내려올 때만 +1.00% 익절로 즉시 구출 (TRAIL_FLOOR_100)!
    6) [구간 1 : +0.00% ~ +0.99% 미점화 상태 (장중 HOLD 모드)]:
       - 15:00 ~ 15:58 EST 구간 현재가가 진입가 대비 수익권(>= +0.20%)이고 정규장 VWAP 이상 도달 시 탈출 (VWAP_1500_PROFIT_EXIT)
       - 15:59 EST 이후 무오버나이트 2단계 방탄 MOC 강제 청산 (MOC_1559_EXIT)
       - safety_hold_mode == True (기본값)일 때는 오전 개장 흔들기 바닥 손절을 OFF하고 평균회귀를 기다린다.
    """
    ep = safe_float(entry_price, 0.0)
    lp = safe_float(live_price, 0.0)
    bh = max(lp, safe_float(bar_high_price, lp))
    cap_p = (
        safe_float(cap_500_price, 0.0)
        if safe_float(cap_500_price, 0.0) > 0.0
        else round(ep * (1.0 + ASSASSIN_SAFE_CAP_PCT / 100.0), 2)
    )
    arm100_p = (
        safe_float(arm_100_price, 0.0)
        if safe_float(arm_100_price, 0.0) > 0.0
        else (
            math.ceil(
                (ep * (1.0 + ASSASSIN_ARM_IGNITION_PCT / 100.0) - 1e-9) * 100.0
            )
            / 100.0
        )
    )
    arm125_p = (
        safe_float(arm_125_price, 0.0)
        if safe_float(arm_125_price, 0.0) > 0.0
        else (
            math.ceil(
                (ep * (1.0 + ASSASSIN_STAGE2_BOOST_PCT / 100.0) - 1e-9) * 100.0
            )
            / 100.0
        )
    )

    armed1 = bool(is_trailing_armed)
    armed2 = bool(is_stage2_boost_armed)
    just_armed_100 = False
    just_armed_125 = False

    cur_peak = max(safe_float(peak_price, ep), lp, bh)
    cur_min = (
        min(safe_float(post_entry_min_price, lp), lp)
        if safe_float(post_entry_min_price, 0.0) > 0.0
        else lp
    )

    # 1) +5.00% 상단 안전 캡 홈런 도달
    if bh >= cap_p or lp >= cap_p:
        exec_p = max(lp, cap_p)
        return {
            "should_exit": True,
            "exit_code": "CAP_500_HOMERUN",
            "exit_desc": f"👑 +5.00% 상단 안전 캡 홈런 익절(${exec_p:.2f})",
            "exit_price": round(exec_p, 2),
            "is_trailing_armed": True,
            "is_stage2_boost_armed": True,
            "just_armed": not armed1,
            "just_stage2_armed": not armed2,
            "peak_price": round(max(cur_peak, exec_p), 4),
            "post_entry_min_price": round(cur_min, 4),
            "active_stop_floor_price": round(cap_p, 2),
        }

    # 2) 1차(+1.00%) 잠금 및 2차(+1.25%) 부스트 점화 상태 전이 확인
    if not armed1 and (bh >= arm100_p or lp >= arm100_p):
        armed1 = True
        just_armed_100 = True
        cur_peak = max(cur_peak, lp, bh, arm100_p)

    if not armed2 and (bh >= arm125_p or lp >= arm125_p):
        armed1 = True
        armed2 = True
        just_armed_125 = True
        cur_peak = max(cur_peak, lp, bh, arm125_p)

    # 3-A) [구간 3] 2차 (+1.25% 이상) 부스트 점화 상태 : 최소 +1.25% 보존 + 최고가 콜백 + HA 음봉 스윕
    if armed2:
        peak_gain_pct = ((cur_peak - ep) / ep) * 100.0 if ep > 0.0 else 1.25
        cb_allow = (
            ASSASSIN_CALLBACK_WIDE_PCT
            if peak_gain_pct >= ASSASSIN_BOOST_TIER2_PCT
            else ASSASSIN_CALLBACK_TIGHT_PCT
        )
        cb_stop_p = round(
            max(arm125_p, cur_peak * (1.0 - cb_allow / 100.0)), 2
        )

        if just_armed_125 and lp >= arm125_p:
            return {
                "should_exit": False,
                "exit_code": "STAGE2_BOOST_TRACKING",
                "exit_desc": f"🚀 +1.25% 2차 부스트 점화 완료 · 2차 보존선 ${arm125_p:.2f} 격상 추적 중",
                "exit_price": 0.0,
                "is_trailing_armed": True,
                "is_stage2_boost_armed": True,
                "just_armed": just_armed_100,
                "just_stage2_armed": True,
                "peak_price": round(cur_peak, 4),
                "post_entry_min_price": round(cur_min, 4),
                "active_stop_floor_price": cb_stop_p,
            }

        if lp <= arm125_p:
            return {
                "should_exit": True,
                "exit_code": "TRAIL_FLOOR_125",
                "exit_desc": f"🛡️ +1.25% 2차 익절 보존선(${arm125_p:.2f}) 스윕 체결",
                "exit_price": round(arm125_p, 2),
                "is_trailing_armed": True,
                "is_stage2_boost_armed": True,
                "just_armed": False,
                "just_stage2_armed": False,
                "peak_price": round(cur_peak, 4),
                "post_entry_min_price": round(cur_min, 4),
                "active_stop_floor_price": round(arm125_p, 2),
            }

        if lp <= cb_stop_p:
            exec_cb_p = round(max(arm125_p, lp), 2)
            return {
                "should_exit": True,
                "exit_code": "TRAIL_CALLBACK_BOOST",
                "exit_desc": f"🚀 HA 트레일링 고점(${cur_peak:.2f}) 콜백(-{cb_allow:.2f}%) 익절(${exec_cb_p:.2f})",
                "exit_price": exec_cb_p,
                "is_trailing_armed": True,
                "is_stage2_boost_armed": True,
                "just_armed": False,
                "just_stage2_armed": False,
                "peak_price": round(cur_peak, 4),
                "post_entry_min_price": round(cur_min, 4),
                "active_stop_floor_price": cb_stop_p,
            }

        if (
            not soxl_is_ha_bull
            and qqq_vel_max_3m_10m_pct < ASSASSIN_QQQ_SURGE_BYPASS_PCT
        ):
            exec_ha_p = round(max(arm125_p, lp), 2)
            return {
                "should_exit": True,
                "exit_code": "TRAIL_HA_RED_BOOST",
                "exit_desc": f"🕯️ HA 음봉 전환 트레일링 부스트 익절(${exec_ha_p:.2f})",
                "exit_price": exec_ha_p,
                "is_trailing_armed": True,
                "is_stage2_boost_armed": True,
                "just_armed": False,
                "just_stage2_armed": False,
                "peak_price": round(cur_peak, 4),
                "post_entry_min_price": round(cur_min, 4),
                "active_stop_floor_price": exec_ha_p,
            }

        if safe_int(hm, 0) >= ASSASSIN_MOC_EXIT_HM:
            exec_moc_p = round(max(arm125_p, lp), 2)
            return {
                "should_exit": True,
                "exit_code": "TRAIL_MOC_1559",
                "exit_desc": f"🔔 15:59 장마감 2차 부스트 확정 익절(${exec_moc_p:.2f})",
                "exit_price": exec_moc_p,
                "is_trailing_armed": True,
                "is_stage2_boost_armed": True,
                "just_armed": False,
                "just_stage2_armed": False,
                "peak_price": round(cur_peak, 4),
                "post_entry_min_price": round(cur_min, 4),
                "active_stop_floor_price": exec_moc_p,
            }

        return {
            "should_exit": False,
            "exit_code": "STAGE2_BOOST_TRACKING",
            "exit_desc": f"🚀 2차 부스트 HA 추적 중(최고 ${cur_peak:.2f} / 스탑 ${cb_stop_p:.2f})",
            "exit_price": 0.0,
            "is_trailing_armed": True,
            "is_stage2_boost_armed": True,
            "just_armed": False,
            "just_stage2_armed": False,
            "peak_price": round(cur_peak, 4),
            "post_entry_min_price": round(cur_min, 4),
            "active_stop_floor_price": cb_stop_p,
        }

    # 3-B) [구간 2] 1차 (+1.00% ~ +1.24%) 보존선 잠금 완충 상태 : HA 음봉 무시 홀딩 & +1.00% 하향 터치 시에만 구출 익절!
    if armed1:
        if just_armed_100 and lp >= arm100_p:
            return {
                "should_exit": False,
                "exit_code": "STAGE1_FLOOR100_LOCKED",
                "exit_desc": f"🔒 +1.00% 1차 보존선(${arm100_p:.2f}) 잠금 · +1.25% 부스트(${arm125_p:.2f}) 돌파 대기",
                "exit_price": 0.0,
                "is_trailing_armed": True,
                "is_stage2_boost_armed": False,
                "just_armed": True,
                "just_stage2_armed": False,
                "peak_price": round(cur_peak, 4),
                "post_entry_min_price": round(cur_min, 4),
                "active_stop_floor_price": round(arm100_p, 2),
            }

        if lp <= arm100_p:
            return {
                "should_exit": True,
                "exit_code": "TRAIL_FLOOR_100",
                "exit_desc": f"🛡️ +1.00% 1차 익절 보존선(${arm100_p:.2f}) 구출 스윕 체결",
                "exit_price": round(arm100_p, 2),
                "is_trailing_armed": True,
                "is_stage2_boost_armed": False,
                "just_armed": False,
                "just_stage2_armed": False,
                "peak_price": round(cur_peak, 4),
                "post_entry_min_price": round(cur_min, 4),
                "active_stop_floor_price": round(arm100_p, 2),
            }

        if safe_int(hm, 0) >= ASSASSIN_MOC_EXIT_HM:
            exec_moc1_p = round(max(arm100_p, lp), 2)
            return {
                "should_exit": True,
                "exit_code": "TRAIL_MOC_1559",
                "exit_desc": f"🔔 15:59 장마감 1차 보존 확정 익절(${exec_moc1_p:.2f})",
                "exit_price": exec_moc1_p,
                "is_trailing_armed": True,
                "is_stage2_boost_armed": False,
                "just_armed": False,
                "just_stage2_armed": False,
                "peak_price": round(cur_peak, 4),
                "post_entry_min_price": round(cur_min, 4),
                "active_stop_floor_price": exec_moc1_p,
            }

        return {
            "should_exit": False,
            "exit_code": "STAGE1_FLOOR100_LOCKED",
            "exit_desc": f"🔒 1차 보존선(${arm100_p:.2f}) 잠금 홀딩 중 (2차 점화 ${arm125_p:.2f} 대기 · HA음봉 무시)",
            "exit_price": 0.0,
            "is_trailing_armed": True,
            "is_stage2_boost_armed": False,
            "just_armed": False,
            "just_stage2_armed": False,
            "peak_price": round(cur_peak, 4),
            "post_entry_min_price": round(cur_min, 4),
            "active_stop_floor_price": round(arm100_p, 2),
        }

    # 4) [구간 1] 미점화 상태: 15:00 ~ 15:58 EST 수익권 정규장 VWAP 탈출
    cur_gain_pct = ((lp - ep) / ep) * 100.0 if ep > 0.0 else 0.0
    if (
        ASSASSIN_VWAP_EXIT_START_HM <= safe_int(hm, 0) < ASSASSIN_MOC_EXIT_HM
        and cur_gain_pct >= 0.20
        and soxl_reg_vwap > 0.0
        and lp >= soxl_reg_vwap
    ):
        return {
            "should_exit": True,
            "exit_code": "VWAP_1500_PROFIT_EXIT",
            "exit_desc": f"🎯 15:00 이후 수익권 정규장 VWAP(${soxl_reg_vwap:.2f}) 탈출 익절(${lp:.2f})",
            "exit_price": round(lp, 2),
            "is_trailing_armed": False,
            "is_stage2_boost_armed": False,
            "just_armed": False,
            "just_stage2_armed": False,
            "peak_price": round(cur_peak, 4),
            "post_entry_min_price": round(cur_min, 4),
            "active_stop_floor_price": round(lp, 2),
        }

    # 5) 미점화 상태: 15:59 EST 무오버나이트 2단계 방탄 MOC
    if safe_int(hm, 0) >= ASSASSIN_MOC_EXIT_HM:
        return {
            "should_exit": True,
            "exit_code": "MOC_1559_EXIT",
            "exit_desc": f"🔔 15:59 정규장 마감 무오버나이트 MOC 청산(${lp:.2f})",
            "exit_price": round(lp, 2),
            "is_trailing_armed": False,
            "is_stage2_boost_armed": False,
            "just_armed": False,
            "just_stage2_armed": False,
            "peak_price": round(cur_peak, 4),
            "post_entry_min_price": round(cur_min, 4),
            "active_stop_floor_price": round(lp, 2),
        }

    # 6) 미점화 상태: 장중 안전망 검문 (변형 선택지 A 에서는 safety_hold_mode=True 로 오전 개장 흔들기 손절 OFF)
    eq_p = safe_float(entry_qqq_price, 0.0)
    lq_p = safe_float(qqq_live_price, 0.0)
    qqq_chg_pct = (
        ((lq_p - eq_p) / eq_p) * 100.0
        if (eq_p > 0.0 and lq_p > 0.0)
        else -abs(safe_float(qqq_bear_drop_amp_pct, 0.0))
    )

    trig_safe, safe_code, safe_desc, _dyn_thr = (
        evaluate_directional_3stage_safety_net_v2(
            hm=hm,
            is_trailing_armed=False,
            entry_price=ep,
            live_price=lp,
            post_entry_min_price=cur_min,
            prev_reg_close=soxl_prev_reg_close,
            pre_open_price=soxl_pre_open_price,
            is_bull_bar=soxl_is_bull_bar,
            is_ha_bull=soxl_is_ha_bull,
            nq_entry_bear_amp_pct=nq_entry_bear_amp_pct,
            qqq_vel_1m_pct=qqq_vel_1m_pct,
            qqq_vel_3m_pct=qqq_vel_3m_pct,
            qqq_chg_from_entry_pct=qqq_chg_pct,
            entry_qqq_price=eq_p,
            qqq_live_price=lq_p,
            safety_hold_mode=safety_hold_mode,
        )
    )
    if trig_safe:
        return {
            "should_exit": True,
            "exit_code": safe_code,
            "exit_desc": safe_desc,
            "exit_price": round(lp, 2),
            "is_trailing_armed": False,
            "is_stage2_boost_armed": False,
            "just_armed": False,
            "just_stage2_armed": False,
            "peak_price": round(cur_peak, 4),
            "post_entry_min_price": round(cur_min, 4),
            "active_stop_floor_price": round(lp, 2),
        }

    return {
        "should_exit": False,
        "exit_code": "HOLD_WAITING_IGNITION",
        "exit_desc": safe_desc,
        "exit_price": 0.0,
        "is_trailing_armed": False,
        "is_stage2_boost_armed": False,
        "just_armed": False,
        "just_stage2_armed": False,
        "peak_price": round(cur_peak, 4),
        "post_entry_min_price": round(cur_min, 4),
        "active_stop_floor_price": 0.0,
    }


async def _enter_assassin_main_force_from_gate(
    context: Any,
    assn_ledger: AssassinSimLedger,
    st: Dict[str, Any],
    feat: Dict[str, Any],
    gate_id: str,
    gate_desc: str,
    entry_scout_seq: int,
    entry_trigger_mode: str,
    now_est: datetime,
    now_ts: float,
    entry_rsi_14: float,
    entry_vwap: float,
    entry_vs_vwap_pct: float,
    entry_prev_close: float,
    entry_vs_prev_close_pct: float,
    entry_pre_open: float,
    entry_vs_pre_open_pct: float,
    entry_vs_scout1_pct: float = 0.0,
    extra_state_updates: Optional[Dict[str, Any]] = None,
) -> str:
    """
    # MODIFIED [Case 93 : 본대 즉시 진입 및 2단 하이브리드 래칫(arm_100_price +1.00% · arm_125_price +1.25% · cap_500_price +5.00%) + 출동 QQQ 지수 원장 박제 공통 함수]:
    """
    lp = safe_float(feat.get("live_price"), 0.0)
    if lp <= 0.0:
        return "ASSASSIN_BUY_NO_PRICE"

    init_seed = max(
        100.0, safe_float(st.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD)
    )
    comp_cash = max(
        100.0, safe_float(st.get("comp_free_cash_usd"), init_seed)
    )
    rt_fee_pct = safe_float(
        st.get("round_trip_fee_rate_pct"), ROUND_TRIP_FEE_RATE_PCT
    )
    fee_mult = 1.0 + (rt_fee_pct / 100.0) * 0.5

    simple_qty = max(1, int(math.floor(init_seed / (lp * fee_mult))))
    comp_qty = max(1, int(math.floor(comp_cash / (lp * fee_mult))))

    ok_buy, buy_oid, fill_p = await _dispatch_assassin_buy_order(
        context=context,
        qty=comp_qty,
        limit_price=lp,
    )
    if not ok_buy:
        return "ASSASSIN_BUY_FAILED"

    arm100_p = (
        math.ceil(
            (fill_p * (1.0 + ASSASSIN_ARM_IGNITION_PCT / 100.0) - 1e-9) * 100.0
        )
        / 100.0
    )
    arm125_p = (
        math.ceil(
            (fill_p * (1.0 + ASSASSIN_STAGE2_BOOST_PCT / 100.0) - 1e-9) * 100.0
        )
        / 100.0
    )
    cap_p = round(fill_p * (1.0 + ASSASSIN_SAFE_CAP_PCT / 100.0), 2)
    _, cap_oid = await _dispatch_assassin_safe_cap_sell_order(
        context=context,
        qty=comp_qty,
        cap_500_price=cap_p,
    )

    entry_qqq_p = round(safe_float(feat.get("qqq_live_price"), 0.0), 4)
    entry_qqq_v1 = round(safe_float(feat.get("qqq_vel_1m_pct"), 0.0), 3)
    entry_qqq_v3 = round(safe_float(feat.get("qqq_vel_3m_pct"), 0.0), 3)
    raw_nq_amp = safe_float(
        feat.get("nq_bear_amp_pct"), SAFETY_QQQ_BASE_AMP_PCT
    )
    nq_bear_amp = (
        max(SAFETY_QQQ_BASE_AMP_PCT, raw_nq_amp)
        if raw_nq_amp > 0.0
        else SAFETY_QQQ_BASE_AMP_PCT
    )
    dyn_qqq_thr = round(
        min(
            SAFETY_DYN_QQQ_MAX_THR_PCT,
            max(
                nq_bear_amp * SAFETY_QQQ_AMP_CUT_RATIO,
                SAFETY_DYN_QQQ_MIN_THR_PCT,
            ),
        ),
        2,
    )

    gate_counts = dict(st.get("gate_hit_counts") or {})
    gate_counts[gate_id] = safe_int(gate_counts.get(gate_id), 0) + 1
    prior_wins = safe_int(st.get("prior_scout_wins_today"), 0)

    state_kw: Dict[str, Any] = {
        "session_phase": "MAIN_FORCE_ACTIVE",
        "safety_net_mode": SAFETY_NET_MODE_DEFAULT,
        "safety_hold_mode": bool(
            st.get("safety_hold_mode", ASSASSIN_SAFETY_HOLD_MODE)
        ),
        "smart_wait_active": False,
        "smart_wait_start_ts": 0.0,
        "smart_wait_gate_id": "",
        "smart_wait_gate_desc": "",
        "smart_wait_trigger_price": 0.0,
        "smart_wait_scout_seq": 0,
        "smart_wait_trigger_mode": "",
        "has_position": True,
        "entry_gate_id": gate_id,
        "entry_gate_desc": gate_desc,
        "entry_trigger_mode": str(entry_trigger_mode or "SCOUT_GATE"),
        "entry_time_est": now_est.strftime("%H:%M:%S"),
        "entry_ts": now_ts,
        "entry_price": round(fill_p, 4),
        "entry_qqq_price": entry_qqq_p,
        "entry_qqq_vel_1m_pct": entry_qqq_v1,
        "entry_qqq_vel_3m_pct": entry_qqq_v3,
        "qqq_chg_from_entry_pct": 0.0,
        "entry_scout_seq": max(1, safe_int(entry_scout_seq, 1)),
        "entry_prior_scout_wins": prior_wins,
        "entry_rsi_14": round(entry_rsi_14, 2),
        "entry_vwap": round(entry_vwap, 4),
        "entry_vs_vwap_pct": round(entry_vs_vwap_pct, 2),
        "entry_prev_close": round(entry_prev_close, 4),
        "entry_vs_prev_close_pct": round(entry_vs_prev_close_pct, 2),
        "entry_pre_open": round(entry_pre_open, 4),
        "entry_vs_pre_open_pct": round(entry_vs_pre_open_pct, 2),
        "entry_vs_scout1_pct": round(entry_vs_scout1_pct, 2),
        "entry_dd_from_pre_high_pct": round(
            safe_float(feat.get("dd_from_pre_high_pct"), 0.0), 2
        ),
        "entry_vel_5m_pct": round(
            safe_float(feat.get("vel_5m_pct"), 0.0), 3
        ),
        "entry_is_bull_bar": bool(feat.get("is_bull_bar", True)),
        "entry_is_ha_bull": bool(feat.get("is_ha_bull", True)),
        "nq_entry_bear_amp_pct": round(nq_bear_amp, 3),
        "dyn_qqq_stage2_thr_pct": dyn_qqq_thr,
        "simple_held_qty": simple_qty,
        "simple_invested_usd": round(float(simple_qty) * fill_p, 4),
        "comp_held_qty": comp_qty,
        "comp_invested_usd": round(float(comp_qty) * fill_p, 4),
        "cap_500_price": cap_p,
        "arm_100_price": round(arm100_p, 2),
        "arm_125_price": round(arm125_p, 2),
        "is_trailing_armed": False,
        "armed_time_est": "",
        "is_stage2_boost_armed": False,
        "stage2_armed_time_est": "",
        "peak_price": round(fill_p, 4),
        "post_entry_min_price": round(fill_p, 4),
        "active_stop_floor_price": 0.0,
        "pending_buy_order_id": buy_oid,
        "safe_cap_sell_order_id": cap_oid,
        "alert_entry_sent": True,
        "alert_arm_100_sent": False,
        "alert_arm_125_sent": False,
        "gate_hit_counts": gate_counts,
    }
    if isinstance(extra_state_updates, dict) and extra_state_updates:
        state_kw.update(extra_state_updates)

    st = await assn_ledger.update_state(**state_kw)
    await _send_3_gate10_main_entry_alert(context=context, st=st)
    return f"ASSASSIN_MAIN_FORCE_ENTERED_{gate_id}"


async def _activate_or_enter_from_gate_with_smart_wait(
    context: Any,
    assn_ledger: AssassinSimLedger,
    st: Dict[str, Any],
    feat: Dict[str, Any],
    gate_id: str,
    gate_desc: str,
    entry_scout_seq: int,
    entry_trigger_mode: str,
    now_est: datetime,
    now_ts: float,
    entry_rsi_14: float,
    entry_vwap: float,
    entry_vs_vwap_pct: float,
    entry_prev_close: float,
    entry_vs_prev_close_pct: float,
    entry_pre_open: float,
    entry_vs_pre_open_pct: float,
    entry_vs_scout1_pct: float = 0.0,
    extra_state_updates: Optional[Dict[str, Any]] = None,
) -> str:
    """
    # NEW [정책 4 · 1단계 : SMART_WAIT (스마트 진바닥 대기) 또는 즉시 진입 실행기]:
    - should_enter_immediately_or_smart_wait() 가 True 이면 즉시 _enter_assassin_main_force_from_gate() 를 실행한다.
    - False (아직 고점 대비 낙폭이 얕은 음봉 칼날)이면 원장에 smart_wait_active = True 를 설정하고
      최대 5분(300초)간 첫 양봉 전환 / QQQ 반등 / 고점 대비 -1.80% 진바닥 도달을 기다려 더 낮은 단가로 진입한다.
    """
    enter_now, wait_reason = should_enter_immediately_or_smart_wait(
        gate_id=gate_id,
        dd_from_pre_high_pct=safe_float(feat.get("dd_from_pre_high_pct"), 0.0),
        is_bull_bar=bool(feat.get("is_bull_bar", True)),
        qqq_vel_1m_pct=safe_float(feat.get("qqq_vel_1m_pct"), 0.0),
    )
    if enter_now:
        return await _enter_assassin_main_force_from_gate(
            context=context,
            assn_ledger=assn_ledger,
            st=st,
            feat=feat,
            gate_id=gate_id,
            gate_desc=gate_desc,
            entry_scout_seq=entry_scout_seq,
            entry_trigger_mode=f"{entry_trigger_mode}:{wait_reason}",
            now_est=now_est,
            now_ts=now_ts,
            entry_rsi_14=entry_rsi_14,
            entry_vwap=entry_vwap,
            entry_vs_vwap_pct=entry_vs_vwap_pct,
            entry_prev_close=entry_prev_close,
            entry_vs_prev_close_pct=entry_vs_prev_close_pct,
            entry_pre_open=entry_pre_open,
            entry_vs_pre_open_pct=entry_vs_pre_open_pct,
            entry_vs_scout1_pct=entry_vs_scout1_pct,
            extra_state_updates=extra_state_updates,
        )

    lp = safe_float(feat.get("live_price"), 0.0)
    sw_kw: Dict[str, Any] = {
        "smart_wait_active": True,
        "smart_wait_start_ts": now_ts,
        "smart_wait_gate_id": gate_id,
        "smart_wait_gate_desc": gate_desc,
        "smart_wait_trigger_price": round(lp, 4),
        "smart_wait_scout_seq": max(1, int(entry_scout_seq)),
        "smart_wait_trigger_mode": str(entry_trigger_mode or "SCOUT_GATE"),
    }
    if isinstance(extra_state_updates, dict) and extra_state_updates:
        sw_kw.update(extra_state_updates)
    await assn_ledger.update_state(**sw_kw)
    return f"ASSASSIN_SMART_WAIT_ARMED_{gate_id}"


async def _dispatch_new_scout_unit_and_check_gates(
    context: Any,
    assn_ledger: AssassinSimLedger,
    st: Dict[str, Any],
    feat: Dict[str, Any],
    entry_type: str,
    now_est: datetime,
    cur_bucket_10m: int,
) -> str:
    """
    1주 가상 독립 정찰병을 파견하고, 2번째 이후 정찰병(day_scout_seq >= 2)이면
    즉시 10대 진성 게이트(evaluate_10_truth_gates_signal) 또는 강세장 급눌림 진바닥(DL_G6)을 검문하여
    충족 시 스마트 대기(SMART_WAIT) 또는 즉시 본대 투입을 수행한다.
    """
    global _LAST_T03A_DIP_SCAN_KEY, _LAST_T03A_DIP_SCAN_TS
    lp = safe_float(feat.get("live_price"), 0.0)
    if lp <= 0.0:
        return "HOLD_NO_PRICE"

    raw_units = st.get("scout_units") or []
    units = [
        IndependentScoutUnit.from_dict(u)
        for u in raw_units
        if isinstance(u, dict)
    ]
    new_seq = safe_int(st.get("day_scout_seq"), 0) + 1
    sc1_p = safe_float(st.get("scout1_open_price"), 0.0)
    if new_seq == 1 or sc1_p <= 0.0:
        sc1_p = lp

    eff_pre_open = safe_float(feat.get("pre_open_price"), 0.0)
    if eff_pre_open <= 0.0:
        eff_pre_open = sc1_p
    eff_vs_pre_open = (
        ((lp - eff_pre_open) / eff_pre_open) * 100.0
        if eff_pre_open > 0.0
        else 0.0
    )

    eff_pre_vwap = safe_float(feat.get("pre_vwap"), 0.0)
    if eff_pre_vwap <= 0.0:
        eff_pre_vwap = lp
    eff_vs_vwap = (
        ((lp - eff_pre_vwap) / eff_pre_vwap) * 100.0
        if eff_pre_vwap > 0.0
        else 0.0
    )

    vs_sc1 = ((lp - sc1_p) / sc1_p) * 100.0 if sc1_p > 0.0 else 0.0
    tp = (
        math.ceil((lp * (1.0 + SCOUT_PROFIT_TARGET_PCT / 100.0) - 1e-9) * 100.0)
        / 100.0
    )
    now_ts = time.time()
    hm_now = now_est.hour * 100 + now_est.minute

    new_scout = IndependentScoutUnit(
        scout_id=new_seq,
        tier_slot=len(units) + 1,
        entry_type=entry_type,
        entry_time_est=now_est.strftime("%H:%M:%S"),
        entry_ts=now_ts,
        entry_price=round(lp, 4),
        target_price=round(tp, 2),
        qty=1,
        rsi_14=safe_float(feat.get("rsi_14"), 50.0),
        pre_vwap=round(eff_pre_vwap, 4),
        vs_vwap_pct=round(eff_vs_vwap, 2),
        prev_reg_close=safe_float(feat.get("prev_reg_close"), lp),
        vs_prev_close_pct=safe_float(feat.get("vs_prev_close_pct"), 0.0),
        pre_open_price=round(eff_pre_open, 4),
        vs_pre_open_pct=round(eff_vs_pre_open, 2),
        vs_scout1_pct=round(vs_sc1, 2),
        is_bull_bar=bool(feat.get("is_bull_bar", True)),
    )
    units.insert(0, new_scout)
    for idx_u, u_obj in enumerate(units):
        u_obj.tier_slot = idx_u + 1

    history_list = list(st.get("day_scout_history") or [])
    history_list.append(new_scout.to_dict())

    prev_min_p = safe_float(st.get("scout_cycle_min_buy_price"), 0.0)
    new_min_p = (
        round(min(prev_min_p, lp), 4) if prev_min_p > 0.0 else round(lp, 4)
    )
    new_ratchet = max(
        safe_int(st.get("scout_ratchet_max_lots"), 0), len(units)
    )

    prior_wins = safe_int(st.get("prior_scout_wins_today"), 0)
    gate_hit, gate_id, gate_desc = evaluate_10_truth_gates_signal(
        scout_seq=new_seq,
        rsi_14=new_scout.rsi_14,
        vs_vwap_pct=new_scout.vs_vwap_pct,
        vs_prev_close_pct=new_scout.vs_prev_close_pct,
        vs_pre_open_pct=new_scout.vs_pre_open_pct,
        vs_scout1_pct=new_scout.vs_scout1_pct,
        prior_scout_wins=prior_wins,
        is_bull_bar=new_scout.is_bull_bar,
        allow_sc1_dip_scan=False,
    )
    if not gate_hit:
        gate_hit, gate_id, gate_desc = evaluate_dl_g6_bull_pullback_signal(
            hm=hm_now,
            scout_seq=new_seq,
            rsi_14=new_scout.rsi_14,
            vs_vwap_pct=new_scout.vs_vwap_pct,
            vs_prev_close_pct=new_scout.vs_prev_close_pct,
            vs_pre_open_pct=new_scout.vs_pre_open_pct,
            dd_from_pre_high_pct=safe_float(
                feat.get("dd_from_pre_high_pct"), 0.0
            ),
            is_bull_bar=new_scout.is_bull_bar,
            qqq_vel_1m_pct=safe_float(feat.get("qqq_vel_1m_pct"), 0.0),
        )

    _LAST_T03A_DIP_SCAN_KEY = now_est.strftime("%Y-%m-%d %H:%M")
    _LAST_T03A_DIP_SCAN_TS = now_ts

    upd_kw: Dict[str, Any] = {
        "session_phase": "SCOUTING_0407_0814",
        "scout_units": [u.to_dict() for u in units],
        "day_scout_history": history_list[-30:],
        "day_scout_seq": new_seq,
        "scout1_open_price": round(sc1_p, 4),
        "today_pre_open_price": round(eff_pre_open, 4),
        "today_pre_open_verified": True,
        "today_premarket_vwap": round(eff_pre_vwap, 4),
        "today_pre_vwap_verified": True,
        "scout_anchor_price": round(lp, 4),
        "scout_cycle_min_buy_price": new_min_p,
        "scout_ratchet_max_lots": new_ratchet,
        "scout_has_active_l1": True,
        "last_scout_buy_ts": now_ts,
        "last_scout_reentry_eval_ts": now_ts,
        "total_scouts_dispatched": safe_int(
            st.get("total_scouts_dispatched"), 0
        )
        + 1,
    }
    if cur_bucket_10m >= 0:
        upd_kw["last_scout_bucket_10m"] = cur_bucket_10m

    st = await assn_ledger.update_state(**upd_kw)
    await _send_1_scout_dispatched_alert(
        context=context,
        scout=new_scout,
        active_cnt=len(units),
        prior_wins=prior_wins,
    )

    if not gate_hit:
        return f"SCOUT_DISPATCHED_#{new_seq}"

    return await _activate_or_enter_from_gate_with_smart_wait(
        context=context,
        assn_ledger=assn_ledger,
        st=st,
        feat=feat,
        gate_id=gate_id,
        gate_desc=gate_desc,
        entry_scout_seq=new_seq,
        entry_trigger_mode=f"SCOUT_#{new_seq}_{entry_type}",
        now_est=now_est,
        now_ts=now_ts,
        entry_rsi_14=new_scout.rsi_14,
        entry_vwap=new_scout.pre_vwap,
        entry_vs_vwap_pct=new_scout.vs_vwap_pct,
        entry_prev_close=new_scout.prev_reg_close,
        entry_vs_prev_close_pct=new_scout.vs_prev_close_pct,
        entry_pre_open=new_scout.pre_open_price,
        entry_vs_pre_open_pct=new_scout.vs_pre_open_pct,
        entry_vs_scout1_pct=new_scout.vs_scout1_pct,
    )


def _resolve_t03a_reference_dip_low(
    st: Dict[str, Any],
    units: List[IndependentScoutUnit],
) -> float:
    """
    # [Case 93 : T03_A_DIP10_ALL_SCOUT 직전 정찰 기준 저점(ref_dip_low) 산출기]:
    """
    cands: List[float] = []
    c_min = safe_float(st.get("scout_cycle_min_buy_price"), 0.0)
    if c_min > 0.0:
        cands.append(c_min)
    anc = safe_float(st.get("scout_anchor_price"), 0.0)
    if anc > 0.0:
        cands.append(anc)
    if units:
        u_min = min(u.entry_price for u in units if u.entry_price > 0.0)
        if u_min > 0.0:
            cands.append(u_min)
    if not cands:
        sc1 = safe_float(st.get("scout1_open_price"), 0.0)
        if sc1 > 0.0:
            cands.append(sc1)
    return round(min(cands), 4) if cands else 0.0


async def _evaluate_t03a_1m_dip_truth_gates_scan(
    context: Any,
    assn_ledger: AssassinSimLedger,
    st: Dict[str, Any],
    feat: Dict[str, Any],
    units: List[IndependentScoutUnit],
    now_est: datetime,
    now_ts: float,
) -> Optional[str]:
    """
    # MODIFIED [Case 93 : T03_A_DIP10_ALL_SCOUT + DL_G6 강세장 급눌림 진바닥 + SMART_WAIT 1분 상시 스캔 엔진]:
    """
    global _LAST_T03A_DIP_SCAN_KEY, _LAST_T03A_DIP_SCAN_TS

    cur_seq = safe_int(st.get("day_scout_seq"), 0)
    if cur_seq < 1:
        return None

    last_b_ts = safe_float(st.get("last_scout_buy_ts"), 0.0)
    if (now_ts - last_b_ts) < SCOUT_TIME_SHIELD_SEC:
        return None

    lp = safe_float(feat.get("live_price"), 0.0)
    ref_dip_low = _resolve_t03a_reference_dip_low(st, units)
    if lp <= 0.0 or ref_dip_low <= 0.0:
        return None

    hm_now = now_est.hour * 100 + now_est.minute
    sc1_p = safe_float(
        st.get("scout1_open_price"),
        safe_float(feat.get("pre_open_price"), ref_dip_low),
    )
    if sc1_p <= 0.0:
        sc1_p = ref_dip_low

    eff_pre_open = safe_float(feat.get("pre_open_price"), 0.0)
    if eff_pre_open <= 0.0:
        eff_pre_open = sc1_p
    eff_vs_pre_open = (
        ((lp - eff_pre_open) / eff_pre_open) * 100.0
        if eff_pre_open > 0.0
        else 0.0
    )

    eff_pre_vwap = safe_float(feat.get("pre_vwap"), 0.0)
    if eff_pre_vwap <= 0.0:
        eff_pre_vwap = lp
    eff_vs_vwap = (
        ((lp - eff_pre_vwap) / eff_pre_vwap) * 100.0
        if eff_pre_vwap > 0.0
        else 0.0
    )

    eff_prev_close = safe_float(feat.get("prev_reg_close"), lp)
    eff_vs_prev_close = safe_float(feat.get("vs_prev_close_pct"), 0.0)
    vs_sc1 = ((lp - sc1_p) / sc1_p) * 100.0 if sc1_p > 0.0 else 0.0
    rsi_now = safe_float(feat.get("rsi_14"), 50.0)
    is_bull_now = bool(feat.get("is_bull_bar", True))
    prior_wins = safe_int(st.get("prior_scout_wins_today"), 0)

    # 1) 강세장 급눌림 진바닥(DL_G6) 상시 검문
    dl_g6_hit, g6_id, g6_desc = evaluate_dl_g6_bull_pullback_signal(
        hm=hm_now,
        scout_seq=cur_seq,
        rsi_14=rsi_now,
        vs_vwap_pct=round(eff_vs_vwap, 2),
        vs_prev_close_pct=round(eff_vs_prev_close, 2),
        vs_pre_open_pct=round(eff_vs_pre_open, 2),
        dd_from_pre_high_pct=safe_float(feat.get("dd_from_pre_high_pct"), 0.0),
        is_bull_bar=is_bull_now,
        qqq_vel_1m_pct=safe_float(feat.get("qqq_vel_1m_pct"), 0.0),
    )
    if dl_g6_hit:
        new_min_p = round(min(ref_dip_low, lp), 4)
        return await _enter_assassin_main_force_from_gate(
            context=context,
            assn_ledger=assn_ledger,
            st=st,
            feat=feat,
            gate_id=g6_id,
            gate_desc=g6_desc,
            entry_scout_seq=cur_seq,
            entry_trigger_mode="DL_G6_BULL_PULLBACK_1M",
            now_est=now_est,
            now_ts=now_ts,
            entry_rsi_14=rsi_now,
            entry_vwap=eff_pre_vwap,
            entry_vs_vwap_pct=eff_vs_vwap,
            entry_prev_close=eff_prev_close,
            entry_vs_prev_close_pct=eff_vs_prev_close,
            entry_pre_open=eff_pre_open,
            entry_vs_pre_open_pct=eff_vs_pre_open,
            entry_vs_scout1_pct=vs_sc1,
            extra_state_updates={"scout_cycle_min_buy_price": new_min_p},
        )

    # 2) T03_A 직전 정찰 저점 대비 -1.00% 이하 1분 상시 진성 게이트 10 스캔
    chg_from_dip_low = ((lp - ref_dip_low) / ref_dip_low) * 100.0
    if chg_from_dip_low > (SCOUT_T03A_DIP_SCAN_DROP_PCT + 1e-6):
        return None

    cur_min_key = now_est.strftime("%Y-%m-%d %H:%M")
    if (
        _LAST_T03A_DIP_SCAN_KEY == cur_min_key
        and (now_ts - _LAST_T03A_DIP_SCAN_TS) < SCOUT_T03A_DIP_SCAN_INTERVAL_SEC
    ):
        return None

    _LAST_T03A_DIP_SCAN_KEY = cur_min_key
    _LAST_T03A_DIP_SCAN_TS = now_ts

    gate_hit, gate_id, gate_desc = evaluate_10_truth_gates_signal(
        scout_seq=cur_seq,
        rsi_14=rsi_now,
        vs_vwap_pct=round(eff_vs_vwap, 2),
        vs_prev_close_pct=round(eff_vs_prev_close, 2),
        vs_pre_open_pct=round(eff_vs_pre_open, 2),
        vs_scout1_pct=round(vs_sc1, 2),
        prior_scout_wins=prior_wins,
        is_bull_bar=is_bull_now,
        allow_sc1_dip_scan=True,
    )
    if not gate_hit:
        return None

    new_min_p = round(min(ref_dip_low, lp), 4)
    return await _activate_or_enter_from_gate_with_smart_wait(
        context=context,
        assn_ledger=assn_ledger,
        st=st,
        feat=feat,
        gate_id=gate_id,
        gate_desc=gate_desc,
        entry_scout_seq=cur_seq,
        entry_trigger_mode=f"T03A_1M_DIP_SCAN(저점${ref_dip_low:.2f}대비{chg_from_dip_low:+.2f}%)",
        now_est=now_est,
        now_ts=now_ts,
        entry_rsi_14=rsi_now,
        entry_vwap=eff_pre_vwap,
        entry_vs_vwap_pct=eff_vs_vwap,
        entry_prev_close=eff_prev_close,
        entry_vs_prev_close_pct=eff_vs_prev_close,
        entry_pre_open=eff_pre_open,
        entry_vs_pre_open_pct=eff_vs_pre_open,
        entry_vs_scout1_pct=vs_sc1,
        extra_state_updates={"scout_cycle_min_buy_price": new_min_p},
    )
# -*- coding: utf-8 -*-
"""
# MODIFIED: assassin_plugin.py (Part 4/4 완결 — 정책 4 SMART_WAIT 대기 체결기 · 08:30~09:20 DL10 무패 진바닥 스캔 및 09:21 최종 퇴근 · 변형 선택지 A 2단 하이브리드 래칫 [+1.00% 1차 잠금 ➔ +1.25% 2차 부스트 + HOLD] 상시 틱 상태 머신 · /assassin 상세 관제 보드 및 TDD 자가 검증기 · Case 93)
"""


async def _evaluate_smart_wait_pending_entry(
    context: Any,
    assn_ledger: AssassinSimLedger,
    st: Dict[str, Any],
    feat: Dict[str, Any],
    now_est: datetime,
    now_ts: float,
) -> Optional[str]:
    """
    # NEW [정책 4 · 1단계 : SMART_WAIT (최대 5분 스마트 진바닥 대기) 감시 및 격발기]:
    프리장에서 10대 진성 게이트가 점등되었으나 고점 대비 낙폭이 얕은 음봉 칼날이어서
    smart_wait_active == True 로 대기 중일 때 매 틱 호출되어:
    ① 현재 1분봉이 양봉(is_bull_bar == True)으로 전환되었거나,
    ② QQQ 1분 변화율이 반등(qqq_vel_1m_pct >= +0.02%)했거나,
    ③ 당일 프리장 고점 대비 낙폭이 진바닥(dd_from_pre_high_pct <= -1.80%)에 도달했거나,
    ④ 대기 시작가(smart_wait_trigger_price) 대비 -0.80% 이하 바겐세일 단가에 도달했거나,
    ⑤ 대기 시작 후 5분(300초)이 경과했거나 08:14 EST 골든타임 마감 시각에 도달했을 때
    단 1건의 타점 유실도 없이 즉시 본대 100% 진입(_enter_assassin_main_force_from_gate)을 집행한다!
    """
    if not bool(st.get("smart_wait_active", False)):
        return None

    lp = safe_float(feat.get("live_price"), 0.0)
    if lp <= 0.0:
        return "HOLD_SMART_WAIT_NO_PRICE"

    hm_now = now_est.hour * 100 + now_est.minute
    start_ts = safe_float(st.get("smart_wait_start_ts"), now_ts)
    elapsed_sec = max(0.0, now_ts - start_ts)
    trig_p = safe_float(st.get("smart_wait_trigger_price"), lp)
    dd_h = safe_float(feat.get("dd_from_pre_high_pct"), 0.0)
    is_bull = bool(feat.get("is_bull_bar", True))
    q_v1 = safe_float(feat.get("qqq_vel_1m_pct"), 0.0)

    fire_reason = ""
    if is_bull:
        fire_reason = "SW_BULL_TURN"
    elif q_v1 >= DL10_MIN_QQQ_VEL_1M_PCT:
        fire_reason = "SW_QQQ_REBOUND"
    elif dd_h <= SMART_WAIT_DEEP_DD_PCT:
        fire_reason = "SW_DEEP_DD180"
    elif trig_p > 0.0 and lp <= (trig_p * SMART_WAIT_EXTRA_DIP_RATIO):
        fire_reason = "SW_EXTRA_DIP"
    elif elapsed_sec >= SMART_WAIT_MAX_SEC or hm_now >= ASSASSIN_GOLDEN_END_HM:
        fire_reason = "SW_TIMEOUT_5M"

    if not fire_reason:
        return "HOLD_SMART_WAIT_MONITORING"

    gate_id = str(st.get("smart_wait_gate_id") or "G1")
    gate_desc = str(st.get("smart_wait_gate_desc") or "")
    sc_seq = max(1, safe_int(st.get("smart_wait_scout_seq"), 1))
    base_trig_mode = str(st.get("smart_wait_trigger_mode") or "SMART_WAIT")

    sc1_p = safe_float(
        st.get("scout1_open_price"),
        safe_float(feat.get("pre_open_price"), lp),
    )
    eff_pre_open = safe_float(feat.get("pre_open_price"), sc1_p)
    eff_vs_pre_open = (
        ((lp - eff_pre_open) / eff_pre_open) * 100.0
        if eff_pre_open > 0.0
        else 0.0
    )
    eff_pre_vwap = safe_float(feat.get("pre_vwap"), lp)
    eff_vs_vwap = (
        ((lp - eff_pre_vwap) / eff_pre_vwap) * 100.0
        if eff_pre_vwap > 0.0
        else 0.0
    )
    eff_prev_close = safe_float(feat.get("prev_reg_close"), lp)
    eff_vs_prev_close = safe_float(feat.get("vs_prev_close_pct"), 0.0)
    vs_sc1 = ((lp - sc1_p) / sc1_p) * 100.0 if sc1_p > 0.0 else 0.0

    return await _enter_assassin_main_force_from_gate(
        context=context,
        assn_ledger=assn_ledger,
        st=st,
        feat=feat,
        gate_id=gate_id,
        gate_desc=gate_desc,
        entry_scout_seq=sc_seq,
        entry_trigger_mode=f"{base_trig_mode}->{fire_reason}(${trig_p:.2f}->${lp:.2f})",
        now_est=now_est,
        now_ts=now_ts,
        entry_rsi_14=safe_float(feat.get("rsi_14"), 50.0),
        entry_vwap=eff_pre_vwap,
        entry_vs_vwap_pct=eff_vs_vwap,
        entry_prev_close=eff_prev_close,
        entry_vs_prev_close_pct=eff_vs_prev_close,
        entry_pre_open=eff_pre_open,
        entry_vs_pre_open_pct=eff_vs_pre_open,
        entry_vs_scout1_pct=vs_sc1,
    )


async def execute_simulated_assassin_tick_plugin(
    context: Any,
    now_est: Optional[datetime] = None,
) -> str:
    """
    🚨 Case 93 핵심:
    main.py 의 main_sniper_loop() 최상단(스나이퍼 ON/OFF 분기 이전)에서 매 틱 호출되는
    [모의 ⇄ 실전 Dual-Ready] 암살자 상시 작동 상태 머신
    (정책 4 [SMART_WAIT + DL_G6 + 08:30~09:20 DL10] × 변형 선택지 A [2단 하이브리드 래칫 +1.00% 1차 잠금 ➔ +1.25% 2차 부스트 + 장중 HOLD] 탑재).
    """
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    if is_weekend_nyse_closed(dt_now) or dt_now.weekday() >= 5:
        if context is not None:
            context.assassin_high_freq_active = False
        return "WEEKEND_CLOSED"

    hm = dt_now.hour * 100 + dt_now.minute
    today_str = dt_now.strftime("%Y-%m-%d")

    sniper_seed = DEFAULT_INITIAL_SEED_USD
    if context is not None and hasattr(context, "ledger"):
        try:
            st_sp = context.ledger.get_state(TARGET_SYMBOL)
            sniper_seed = safe_float(
                st_sp.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD
            )
        except Exception:
            pass

    assn_ledger = ensure_assassin_ledger(context)
    st = await assn_ledger.rollover_daily_session_if_needed(
        today_est_str=today_str, sniper_seed_usd=sniper_seed
    )

    if not bool(st.get("is_enabled", True)):
        if context is not None:
            context.assassin_high_freq_active = False
        return "ASSASSIN_DISABLED"

    if hm < ASSASSIN_SCOUT_START_HM:
        if context is not None:
            context.assassin_high_freq_active = False
        return "WAIT_0407_OPEN"

    if bool(st.get("is_session_done", False)):
        if context is not None:
            context.assassin_high_freq_active = False
        return str(st.get("session_done_reason") or "SESSION_DONE")

    bar_ext = await _sync_context_cache_for_assassin_snapshot(
        context=context, now_est=dt_now, force_warmup=False
    )
    feat = await _extract_live_assassin_features_and_qqq_snapshot(
        context=context, now_est=dt_now, ledger=assn_ledger, force_warmup=False
    )
    lp = safe_float(feat.get("live_price"), 0.0)
    if lp <= 0.0:
        return "NO_LIVE_PRICE"

    bar_high_p = max(lp, safe_float(bar_ext.get("cur_bar_high"), lp))
    now_ts = time.time()

    # ===================================================================
    # [PHASE A] 본대(Main Force) 포지션 보유 중 -> 변형 선택지 A (2단래칫 +1.00% ➔ +1.25% + HOLD / 15:00 VWAP / 15:59 MOC) 감시
    # ===================================================================
    if bool(st.get("has_position", False)):
        qqq_lp = safe_float(feat.get("qqq_live_price"), 0.0)
        entry_qqq_p = safe_float(st.get("entry_qqq_price"), 0.0)
        if entry_qqq_p <= 0.0 and qqq_lp > 0.0:
            entry_qqq_p = round(qqq_lp, 4)

        cur_qqq_chg_pct = (
            round(((qqq_lp - entry_qqq_p) / entry_qqq_p) * 100.0, 3)
            if (entry_qqq_p > 0.0 and qqq_lp > 0.0)
            else 0.0
        )
        vel_1m = safe_float(feat.get("qqq_vel_1m_pct"), 0.0)
        vel_3m = safe_float(feat.get("qqq_vel_3m_pct"), 0.0)
        vel_10m = safe_float(feat.get("qqq_vel_10m_pct"), 0.0)

        exit_eval = evaluate_assassin_ha_trailing_and_exits(
            hm=hm,
            entry_price=safe_float(st.get("entry_price"), lp),
            live_price=lp,
            bar_high_price=bar_high_p,
            is_trailing_armed=bool(st.get("is_trailing_armed", False)),
            peak_price=safe_float(st.get("peak_price"), lp),
            arm_100_price=safe_float(st.get("arm_100_price"), 0.0),
            cap_500_price=safe_float(st.get("cap_500_price"), 0.0),
            soxl_is_bull_bar=bool(feat.get("is_bull_bar", True)),
            soxl_is_ha_bull=bool(feat.get("is_ha_bull", True)),
            soxl_prev_reg_close=safe_float(feat.get("prev_reg_close"), lp),
            soxl_pre_open_price=safe_float(feat.get("pre_open_price"), 0.0),
            soxl_reg_vwap=safe_float(feat.get("regular_vwap"), lp),
            post_entry_min_price=safe_float(
                st.get("post_entry_min_price"), lp
            ),
            qqq_vel_1m_pct=vel_1m,
            qqq_vel_3m_pct=vel_3m,
            qqq_vel_max_3m_10m_pct=max(vel_3m, vel_10m),
            qqq_bear_drop_amp_pct=safe_float(
                feat.get("nq_bear_amp_pct"), SAFETY_QQQ_BASE_AMP_PCT
            ),
            nq_entry_bear_amp_pct=safe_float(
                st.get("nq_entry_bear_amp_pct"), SAFETY_QQQ_BASE_AMP_PCT
            ),
            entry_qqq_price=entry_qqq_p,
            qqq_live_price=qqq_lp,
            arm_125_price=safe_float(st.get("arm_125_price"), 0.0),
            is_stage2_boost_armed=bool(
                st.get("is_stage2_boost_armed", False)
            ),
            safety_hold_mode=bool(
                st.get("safety_hold_mode", ASSASSIN_SAFETY_HOLD_MODE)
            ),
        )

        new_armed1 = bool(exit_eval.get("is_trailing_armed", False))
        new_armed2 = bool(exit_eval.get("is_stage2_boost_armed", False))
        if context is not None:
            context.assassin_high_freq_active = bool(new_armed1 or new_armed2)

        if not bool(exit_eval.get("should_exit", False)):
            upd_hold_kw: Dict[str, Any] = {
                "entry_qqq_price": entry_qqq_p,
                "qqq_chg_from_entry_pct": cur_qqq_chg_pct,
                "is_trailing_armed": new_armed1,
                "is_stage2_boost_armed": new_armed2,
                "peak_price": safe_float(exit_eval.get("peak_price"), lp),
                "post_entry_min_price": safe_float(
                    exit_eval.get("post_entry_min_price"), lp
                ),
                "active_stop_floor_price": safe_float(
                    exit_eval.get("active_stop_floor_price"), 0.0
                ),
            }
            send_stage2_alert = False
            send_stage1_alert = False

            if new_armed2 and not bool(st.get("alert_arm_125_sent", False)):
                upd_hold_kw["stage2_armed_time_est"] = dt_now.strftime(
                    "%H:%M:%S"
                )
                if not str(st.get("armed_time_est") or "").strip():
                    upd_hold_kw["armed_time_est"] = dt_now.strftime("%H:%M:%S")
                upd_hold_kw["alert_arm_100_sent"] = True
                upd_hold_kw["alert_arm_125_sent"] = True
                send_stage2_alert = True
            elif new_armed1 and not bool(st.get("alert_arm_100_sent", False)):
                upd_hold_kw["armed_time_est"] = dt_now.strftime("%H:%M:%S")
                upd_hold_kw["alert_arm_100_sent"] = True
                send_stage1_alert = True

            st = await assn_ledger.update_state(**upd_hold_kw)
            if send_stage2_alert:
                await _send_4b_stage2_boost_ignition_alert(
                    context=context, st=st, live_price=lp
                )
                return "ASSASSIN_STAGE2_BOOST_ARMED"
            if send_stage1_alert:
                await _send_4_trailing_ignition_alert(
                    context=context, st=st, live_price=lp
                )
                return "ASSASSIN_STAGE1_FLOOR100_LOCKED"

            return str(exit_eval.get("exit_code") or "HOLD_POSITION")

        exit_code = str(exit_eval.get("exit_code") or "EXIT")
        exit_desc = str(exit_eval.get("exit_desc") or exit_code)
        target_xp = safe_float(exit_eval.get("exit_price"), lp)
        c_qty = safe_int(st.get("comp_held_qty"), 1)
        s_qty = safe_int(st.get("simple_held_qty"), 1)

        _, _, exec_xp = await _dispatch_assassin_exit_sweep_order(
            context=context,
            existing_sell_order_id=str(
                st.get("safe_cap_sell_order_id") or ""
            ),
            qty=c_qty,
            target_exit_price=target_xp,
        )

        ep = safe_float(st.get("entry_price"), exec_xp)
        rt_fee = safe_float(
            st.get("round_trip_fee_rate_pct"), ROUND_TRIP_FEE_RATE_PCT
        )
        s_inv = safe_float(
            st.get("simple_invested_usd"), float(s_qty) * ep
        )
        c_inv = safe_float(
            st.get("comp_invested_usd"), float(c_qty) * ep
        )

        s_pnl_info = calc_sell_realized_pnl(
            sold_qty=s_qty,
            sell_exec_price=exec_xp,
            sold_actual_cost_usd=s_inv,
            round_trip_fee_rate_pct=rt_fee,
        )
        c_pnl_info = calc_sell_realized_pnl(
            sold_qty=c_qty,
            sell_exec_price=exec_xp,
            sold_actual_cost_usd=c_inv,
            round_trip_fee_rate_pct=rt_fee,
        )
        s_net = safe_float(s_pnl_info.get("net_pnl_usd"), 0.0)
        c_net = safe_float(c_pnl_info.get("net_pnl_usd"), 0.0)
        gain_pct = ((exec_xp - ep) / ep) * 100.0 if ep > 0.0 else 0.0

        init_s = max(
            100.0,
            safe_float(st.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD),
        )
        new_s_cum = round(
            safe_float(st.get("simple_cum_net_usd"), 0.0) + s_net, 4
        )
        new_c_cum = round(
            safe_float(st.get("comp_cum_net_usd"), 0.0) + c_net, 4
        )
        new_c_cash = round(max(100.0, init_s + new_c_cum), 4)
        new_c_peak = round(
            max(
                safe_float(st.get("comp_peak_equity_usd"), init_s),
                new_c_cash,
            ),
            4,
        )
        cur_dd = (
            ((new_c_cash - new_c_peak) / new_c_peak) * 100.0
            if new_c_peak > 0.0
            else 0.0
        )
        new_max_dd = round(
            min(safe_float(st.get("comp_max_dd_pct"), 0.0), cur_dd), 2
        )

        exit_rsi = round(safe_float(feat.get("rsi_14"), 50.0), 2)
        exit_reg_v = round(safe_float(feat.get("regular_vwap"), 0.0), 4)
        exit_vs_reg_v = (
            round(((exec_xp - exit_reg_v) / exit_reg_v) * 100.0, 2)
            if (exec_xp > 0.0 and exit_reg_v > 0.0)
            else 0.0
        )
        exit_pre_v = round(safe_float(feat.get("pre_vwap"), 0.0), 4)
        exit_vs_pre_v = (
            round(((exec_xp - exit_pre_v) / exit_pre_v) * 100.0, 2)
            if (exec_xp > 0.0 and exit_pre_v > 0.0)
            else 0.0
        )
        final_peak_p = round(
            safe_float(exit_eval.get("peak_price"), exec_xp), 4
        )
        final_min_p = round(
            safe_float(exit_eval.get("post_entry_min_price"), exec_xp), 4
        )
        exit_time_str = dt_now.strftime("%H:%M:%S")
        is_win = bool(s_net >= 0.0)

        journal_entry: Dict[str, Any] = {
            "session_date": today_str,
            "is_win": is_win,
            "entry_gate_id": str(st.get("entry_gate_id") or ""),
            "entry_gate_desc": str(st.get("entry_gate_desc") or ""),
            "entry_trigger_mode": str(st.get("entry_trigger_mode") or ""),
            "entry_scout_seq": safe_int(st.get("entry_scout_seq"), 1),
            "entry_prior_scout_wins": safe_int(
                st.get("entry_prior_scout_wins"), 0
            ),
            "entry_time_est": str(st.get("entry_time_est") or ""),
            "entry_price": round(ep, 4),
            "entry_rsi_14": safe_float(st.get("entry_rsi_14"), 50.0),
            "entry_vwap": safe_float(st.get("entry_vwap"), 0.0),
            "entry_vs_vwap_pct": safe_float(st.get("entry_vs_vwap_pct"), 0.0),
            "entry_prev_close": safe_float(st.get("entry_prev_close"), 0.0),
            "entry_vs_prev_close_pct": safe_float(
                st.get("entry_vs_prev_close_pct"), 0.0
            ),
            "entry_pre_open": safe_float(st.get("entry_pre_open"), 0.0),
            "entry_vs_pre_open_pct": safe_float(
                st.get("entry_vs_pre_open_pct"), 0.0
            ),
            "entry_vs_scout1_pct": safe_float(
                st.get("entry_vs_scout1_pct"), 0.0
            ),
            "entry_is_bull_bar": bool(st.get("entry_is_bull_bar", True)),
            "entry_is_ha_bull": bool(st.get("entry_is_ha_bull", True)),
            "entry_qqq_price": entry_qqq_p,
            "entry_qqq_vel_1m_pct": safe_float(
                st.get("entry_qqq_vel_1m_pct"), 0.0
            ),
            "entry_qqq_vel_3m_pct": safe_float(
                st.get("entry_qqq_vel_3m_pct"), 0.0
            ),
            "peak_price": final_peak_p,
            "post_entry_min_price": final_min_p,
            "is_trailing_armed": new_armed1,
            "is_stage2_boost_armed": new_armed2,
            "armed_time_est": str(st.get("armed_time_est") or ""),
            "stage2_armed_time_est": str(
                st.get("stage2_armed_time_est") or ""
            ),
            "exit_code": exit_code,
            "exit_reason": exit_desc,
            "exit_time_est": exit_time_str,
            "exit_price": round(exec_xp, 2),
            "gain_pct": round(gain_pct, 2),
            "simple_net_usd": round(s_net, 2),
            "comp_net_usd": round(c_net, 2),
            "exit_rsi_14": exit_rsi,
            "exit_reg_vwap": exit_reg_v,
            "exit_vs_reg_vwap_pct": exit_vs_reg_v,
            "exit_pre_vwap": exit_pre_v,
            "exit_vs_pre_vwap_pct": exit_vs_pre_v,
            "exit_qqq_price": round(qqq_lp, 4),
            "qqq_chg_from_entry_pct": cur_qqq_chg_pct,
            "exit_qqq_vel_1m_pct": round(vel_1m, 3),
            "exit_qqq_vel_3m_pct": round(vel_3m, 3),
            "exit_is_bull_bar": bool(feat.get("is_bull_bar", True)),
            "exit_is_ha_bull": bool(feat.get("is_ha_bull", True)),
        }
        journal_list = list(st.get("trade_journal_history") or [])
        journal_list.append(journal_entry)
        journal_list = journal_list[-ASSASSIN_MAX_JOURNAL_HISTORY:]

        upd_exit: Dict[str, Any] = {
            "session_phase": "OFFWORK_DONE",
            "is_session_done": True,
            "session_done_reason": exit_code,
            "has_position": False,
            "entry_qqq_price": entry_qqq_p,
            "qqq_chg_from_entry_pct": cur_qqq_chg_pct,
            "is_trailing_armed": new_armed1,
            "is_stage2_boost_armed": new_armed2,
            "peak_price": final_peak_p,
            "post_entry_min_price": final_min_p,
            "today_exit_code": exit_code,
            "today_exit_reason": exit_desc,
            "today_exit_time_est": exit_time_str,
            "today_exit_price": round(exec_xp, 2),
            "today_gain_pct": round(gain_pct, 2),
            "today_simple_net_usd": round(s_net, 2),
            "today_comp_net_usd": round(c_net, 2),
            "today_exit_rsi_14": exit_rsi,
            "today_exit_reg_vwap": exit_reg_v,
            "today_exit_vs_reg_vwap_pct": exit_vs_reg_v,
            "today_exit_pre_vwap": exit_pre_v,
            "today_exit_vs_pre_vwap_pct": exit_vs_pre_v,
            "today_exit_qqq_price": round(qqq_lp, 4),
            "today_exit_qqq_vel_1m_pct": round(vel_1m, 3),
            "today_exit_qqq_vel_3m_pct": round(vel_3m, 3),
            "today_exit_is_bull_bar": bool(feat.get("is_bull_bar", True)),
            "today_exit_is_ha_bull": bool(feat.get("is_ha_bull", True)),
            "total_trade_days": safe_int(st.get("total_trade_days"), 0) + 1,
            "win_days": safe_int(st.get("win_days"), 0) + (1 if is_win else 0),
            "loss_days": safe_int(st.get("loss_days"), 0)
            + (0 if is_win else 1),
            "simple_cum_net_usd": new_s_cum,
            "comp_cum_net_usd": new_c_cum,
            "comp_free_cash_usd": new_c_cash,
            "comp_peak_equity_usd": new_c_peak,
            "comp_max_dd_pct": new_max_dd,
            "trade_journal_history": journal_list,
            "alert_exit_sent": True,
        }
        if exit_code == "CAP_500_HOMERUN":
            upd_exit["exit_cap500_cnt"] = (
                safe_int(st.get("exit_cap500_cnt"), 0) + 1
            )
        elif exit_code in (
            "TRAIL_CALLBACK_BOOST",
            "TRAIL_HA_RED_BOOST",
            "TRAIL_MOC_1559",
        ):
            upd_exit["exit_ha_boost_cnt"] = (
                safe_int(st.get("exit_ha_boost_cnt"), 0) + 1
            )
        elif exit_code == "TRAIL_FLOOR_125":
            upd_exit["exit_floor125_cnt"] = (
                safe_int(st.get("exit_floor125_cnt"), 0) + 1
            )
        elif exit_code == "TRAIL_FLOOR_100":
            upd_exit["exit_floor100_cnt"] = (
                safe_int(st.get("exit_floor100_cnt"), 0) + 1
            )
        elif exit_code == "VWAP_1500_PROFIT_EXIT":
            upd_exit["exit_vwap_1500_cnt"] = (
                safe_int(st.get("exit_vwap_1500_cnt"), 0) + 1
            )
        elif exit_code == "STAGE1_HEART_STOP_3PCT":
            upd_exit["exit_safety_stage1_cnt"] = (
                safe_int(st.get("exit_safety_stage1_cnt"), 0) + 1
            )
        elif exit_code == "STAGE23_DIR_BEAR_BREAK":
            upd_exit["exit_safety_stage23_cnt"] = (
                safe_int(st.get("exit_safety_stage23_cnt"), 0) + 1
            )
        else:
            upd_exit["exit_moc_cnt"] = safe_int(st.get("exit_moc_cnt"), 0) + 1

        if context is not None:
            context.assassin_high_freq_active = False

        st = await assn_ledger.update_state(**upd_exit)
        await _send_5_exit_and_cumulative_score_alert(
            context=context, st=st, exit_desc=exit_desc
        )
        return f"ASSASSIN_EXITED_{exit_code}"

    # ===================================================================
    # [PHASE B] 08:15 ~ 09:20 EST 거시지표 직후 무패 진바닥(DL10 · 16전 16승) 스캔 & 09:21 EST 최종 무매매 퇴근
    # ===================================================================
    if hm >= ASSASSIN_MACRO_CUTOFF_HM:
        # 만약 08:14 EST 직전에 SMART_WAIT 가 걸려 있었다면 유실 없이 즉시 진입 처리
        if bool(st.get("smart_wait_active", False)):
            sw_res = await _evaluate_smart_wait_pending_entry(
                context=context,
                assn_ledger=assn_ledger,
                st=st,
                feat=feat,
                now_est=dt_now,
                now_ts=now_ts,
            )
            if sw_res and sw_res.startswith("ASSASSIN_MAIN_FORCE_ENTERED"):
                return sw_res

        if context is not None:
            context.assassin_high_freq_active = False

        # 08:15 ~ 09:20 EST 구간: 정찰병 가상 해산 후 08:30 ~ 09:20 EST DL10 무패 진바닥 감시
        if hm <= ASSASSIN_MACRO_DL10_END_HM:
            if st.get("scout_units") or str(
                st.get("session_phase") or ""
            ) not in ("MACRO_WAIT_0830_0920",):
                st = await assn_ledger.update_state(
                    session_phase="MACRO_WAIT_0830_0920",
                    scout_units=[],
                    scout_has_active_l1=False,
                )

            if hm >= ASSASSIN_MACRO_DL10_START_HM:
                dl10_hit, dl10_id, dl10_desc = (
                    evaluate_dl10_macro_bottom_signal(
                        hm=hm,
                        rsi_14=safe_float(feat.get("rsi_14"), 50.0),
                        vs_vwap_pct=safe_float(feat.get("vs_vwap_pct"), 0.0),
                        vel_5m_pct=safe_float(feat.get("vel_5m_pct"), 0.0),
                        is_bull_bar=bool(feat.get("is_bull_bar", True)),
                        qqq_vel_1m_pct=safe_float(
                            feat.get("qqq_vel_1m_pct"), 0.0
                        ),
                    )
                )
                if dl10_hit:
                    sc1_p = safe_float(
                        st.get("scout1_open_price"),
                        safe_float(feat.get("pre_open_price"), lp),
                    )
                    vs_sc1 = (
                        ((lp - sc1_p) / sc1_p) * 100.0 if sc1_p > 0.0 else 0.0
                    )
                    return await _enter_assassin_main_force_from_gate(
                        context=context,
                        assn_ledger=assn_ledger,
                        st=st,
                        feat=feat,
                        gate_id=dl10_id,
                        gate_desc=dl10_desc,
                        entry_scout_seq=max(
                            1, safe_int(st.get("day_scout_seq"), 1)
                        ),
                        entry_trigger_mode=f"DL10_MACRO_BOTTOM(5m:{safe_float(feat.get('vel_5m_pct'), 0.0):+.2f}%)",
                        now_est=dt_now,
                        now_ts=now_ts,
                        entry_rsi_14=safe_float(feat.get("rsi_14"), 50.0),
                        entry_vwap=safe_float(feat.get("pre_vwap"), lp),
                        entry_vs_vwap_pct=safe_float(
                            feat.get("vs_vwap_pct"), 0.0
                        ),
                        entry_prev_close=safe_float(
                            feat.get("prev_reg_close"), lp
                        ),
                        entry_vs_prev_close_pct=safe_float(
                            feat.get("vs_prev_close_pct"), 0.0
                        ),
                        entry_pre_open=safe_float(
                            feat.get("pre_open_price"), sc1_p
                        ),
                        entry_vs_pre_open_pct=safe_float(
                            feat.get("vs_pre_open_pct"), 0.0
                        ),
                        entry_vs_scout1_pct=vs_sc1,
                    )
                return "SCANNING_DL10_0830_0920"
            return "WAIT_DL10_0815_0829"

        # 09:21 EST 이상 도래 시 프리장 및 DL10 모두 미진입 -> 최종 무매매 안전 퇴근 확정!
        had_scouts_today = bool(safe_int(st.get("day_scout_seq"), 0) > 0)
        already_sent = bool(st.get("alert_0815_no_trade_sent", False))
        st = await assn_ledger.update_state(
            session_phase="NO_TRADE_OFFWORK_0921",
            is_session_done=True,
            session_done_reason="NO_TRADE_CUTOFF_0921",
            scout_units=[],
            scout_has_active_l1=False,
            no_trade_days=safe_int(st.get("no_trade_days"), 0) + 1,
            alert_0815_no_trade_sent=True,
        )
        if had_scouts_today and not already_sent:
            await _send_2_0815_no_trade_retire_alert(
                context=context, st=st, feat=feat
            )
        return "NO_TRADE_OFFWORK_0921"

    # ===================================================================
    # [PHASE C] 04:07 ~ 08:14 EST 골든타임 : SMART_WAIT 감시 · 1주 가상 독립 정찰병 파견 · 독립 익절 · DL_G6 & T03_A 1분 스캔
    # ===================================================================
    if bool(st.get("smart_wait_active", False)):
        if context is not None:
            context.assassin_high_freq_active = True
        sw_res = await _evaluate_smart_wait_pending_entry(
            context=context,
            assn_ledger=assn_ledger,
            st=st,
            feat=feat,
            now_est=dt_now,
            now_ts=now_ts,
        )
        if sw_res is not None:
            return sw_res

    raw_units = st.get("scout_units") or []
    units = [
        IndependentScoutUnit.from_dict(u)
        for u in raw_units
        if isinstance(u, dict)
    ]

    last_b_ts = safe_float(st.get("last_scout_buy_ts"), 0.0)
    if units and (now_ts - last_b_ts) >= SCOUT_TIME_SHIELD_SEC:
        kept_units: List[IndependentScoutUnit] = []
        sold_any = False
        sold_l1 = False
        sold_count = 0
        for idx_u, u_obj in enumerate(units):
            if (
                (now_ts - u_obj.entry_ts) >= SCOUT_TIME_SHIELD_SEC
                and lp >= u_obj.target_price
            ):
                sold_any = True
                sold_count += 1
                if idx_u == 0 and bool(st.get("scout_has_active_l1", False)):
                    sold_l1 = True
            else:
                kept_units.append(u_obj)

        if sold_any:
            for idx_k, k_obj in enumerate(kept_units):
                k_obj.tier_slot = idx_k + 1
            new_has_l1 = (
                False
                if (not kept_units or sold_l1)
                else bool(st.get("scout_has_active_l1", False))
            )
            st = await assn_ledger.update_state(
                scout_units=[u.to_dict() for u in kept_units],
                scout_has_active_l1=new_has_l1,
                scout_anchor_price=round(lp, 4),
                last_scout_sell_ts=now_ts,
                last_scout_reentry_eval_ts=now_ts,
                prior_scout_wins_today=safe_int(
                    st.get("prior_scout_wins_today"), 0
                )
                + sold_count,
                total_scout_win_exits=safe_int(
                    st.get("total_scout_win_exits"), 0
                )
                + sold_count,
                scout_cycle_min_buy_price=(
                    0.0
                    if not kept_units
                    else safe_float(st.get("scout_cycle_min_buy_price"), 0.0)
                ),
                scout_ratchet_max_lots=(
                    0
                    if not kept_units
                    else safe_int(st.get("scout_ratchet_max_lots"), 0)
                ),
            )
            return f"SCOUT_PROFIT_EXIT_{sold_count}"

    b_stat = evaluate_buy_gate_bucket_status(
        now_est=dt_now,
        buy_interval_min=LOCKED_BUY_INTERVAL_MIN,
        last_evaluated_bucket_id=safe_int(
            st.get("last_scout_bucket_10m"), -1
        ),
        last_evaluated_date=today_str,
    )
    cur_b10 = safe_int(b_stat.get("bucket_10m"), -1)
    is_b10_open = bool(b_stat[0]) if len(b_stat) >= 1 else False

    last_s_ts = safe_float(st.get("last_scout_sell_ts"), 0.0)
    in_60s_shield = bool(
        (now_ts - max(last_b_ts, last_s_ts)) < SCOUT_TIME_SHIELD_SEC
    )

    if not units:
        if safe_int(st.get("day_scout_seq"), 0) == 0:
            return await _dispatch_new_scout_unit_and_check_gates(
                context=context,
                assn_ledger=assn_ledger,
                st=st,
                feat=feat,
                entry_type="01_OPEN_0407",
                now_est=dt_now,
                cur_bucket_10m=cur_b10,
            )
        if not in_60s_shield:
            return await _dispatch_new_scout_unit_and_check_gates(
                context=context,
                assn_ledger=assn_ledger,
                st=st,
                feat=feat,
                entry_type="01_ZERO_REENTRY",
                now_est=dt_now,
                cur_bucket_10m=cur_b10,
            )
        return "HOLD_SCOUT_60S_SHIELD"

    if in_60s_shield:
        return "HOLD_SCOUT_60S_SHIELD"

    hold_status = "SCOUTING_ACTIVE"

    if len(units) >= SCOUT_MAX_INDEPENDENT_UNITS:
        hold_status = "HOLD_SCOUT_MAX_7_UNITS"
    else:
        has_l1 = bool(st.get("scout_has_active_l1", True))
        anchor_p = safe_float(
            st.get("scout_anchor_price"), units[0].entry_price
        )

        if not has_l1:
            last_re_ts = safe_float(st.get("last_scout_reentry_eval_ts"), 0.0)
            if (now_ts - last_re_ts) < SCOUT_TIME_SHIELD_SEC:
                hold_status = "HOLD_SCOUT_VACANT_L1_60S"
            else:
                l2_ceil_p = min(u.entry_price for u in units)
                if lp > l2_ceil_p + 1e-6:
                    await assn_ledger.update_state(
                        last_scout_reentry_eval_ts=now_ts
                    )
                    hold_status = "HOLD_SCOUT_PREVENT_INVERSION"
                else:
                    chg_from_anchor = (
                        ((lp - anchor_p) / anchor_p) * 100.0
                        if anchor_p > 0.0
                        else 0.0
                    )
                    if chg_from_anchor <= SCOUT_PULLBACK_DROP_PCT:
                        return await _dispatch_new_scout_unit_and_check_gates(
                            context=context,
                            assn_ledger=assn_ledger,
                            st=st,
                            feat=feat,
                            entry_type="02_PULL_1PCT_NOFILT",
                            now_est=dt_now,
                            cur_bucket_10m=-1,
                        )
                    if chg_from_anchor >= SCOUT_BREAKOUT_RISE_PCT:
                        if (
                            safe_float(feat.get("rsi_14"), 50.0)
                            <= SCOUT_BREAKOUT_MAX_RSI
                        ):
                            return (
                                await _dispatch_new_scout_unit_and_check_gates(
                                    context=context,
                                    assn_ledger=assn_ledger,
                                    st=st,
                                    feat=feat,
                                    entry_type="03_BRK_1PCT_RSI50",
                                    now_est=dt_now,
                                    cur_bucket_10m=-1,
                                )
                            )
                        await assn_ledger.update_state(
                            last_scout_reentry_eval_ts=now_ts
                        )
                        hold_status = "HOLD_SCOUT_BRK_RSI_OVER_50"
                    else:
                        await assn_ledger.update_state(
                            last_scout_reentry_eval_ts=now_ts
                        )
                        hold_status = "HOLD_SCOUT_VACANT_L1_WAIT"

        elif is_b10_open and cur_b10 >= 0:
            eff_lots = max(
                len(units),
                safe_int(st.get("scout_ratchet_max_lots"), len(units)),
            )
            drop_req_pct, _, _ = get_golden8_prog_thresholds(
                held_lots=len(units),
                cycle_ratchet_max_lots=eff_lots,
            )
            ref_min_p = min(
                units[0].entry_price,
                anchor_p,
                safe_float(
                    st.get("scout_cycle_min_buy_price"), units[0].entry_price
                ),
            )
            chg_from_min = (
                ((lp - ref_min_p) / ref_min_p) * 100.0
                if ref_min_p > 0.0
                else 0.0
            )
            if chg_from_min <= drop_req_pct:
                return await _dispatch_new_scout_unit_and_check_gates(
                    context=context,
                    assn_ledger=assn_ledger,
                    st=st,
                    feat=feat,
                    entry_type="04_WIDE_GRID_DIP",
                    now_est=dt_now,
                    cur_bucket_10m=cur_b10,
                )
            st = await assn_ledger.update_state(
                last_scout_bucket_10m=cur_b10
            )
            hold_status = "HOLD_SCOUT_10M_WIDE_PASS"

    t03a_res = await _evaluate_t03a_1m_dip_truth_gates_scan(
        context=context,
        assn_ledger=assn_ledger,
        st=st,
        feat=feat,
        units=units,
        now_est=dt_now,
        now_ts=now_ts,
    )
    if t03a_res is not None:
        return t03a_res

    return hold_status


# ---------------------------------------------------------------------------
# [핵심 9] 스나이퍼 레이더(/avwap · /sync · /settlement) 결합용 슬림 블록 & /assassin 상세 관제 보드
# ---------------------------------------------------------------------------
def format_assassin_slim_radar_block(
    context: Any, live_price: float = 0.0
) -> str:
    """
    /avwap, /sync, /settlement 하단에 결합되는 36자 칼맞춤 [모의] 암살자 요약 블록.
    """
    try:
        assn_ledger = ensure_assassin_ledger(context)
        st = assn_ledger.get_state()
        lp = safe_float(
            live_price,
            safe_float(
                getattr(context, "latest_prices", {}).get(TARGET_SYMBOL), 0.0
            ),
        )
        phase = str(st.get("session_phase") or "IDLE_WAIT_0407")
        has_pos = bool(st.get("has_position", False))
        scouts_cnt = len(st.get("scout_units") or [])
        day_seq = safe_int(st.get("day_scout_seq"), 0)
        tot_d = safe_int(st.get("total_trade_days"), 0)
        win_d = safe_int(st.get("win_days"), 0)
        loss_d = safe_int(st.get("loss_days"), 0)
        s_cum = safe_float(st.get("simple_cum_net_usd"), 0.0)
        c_cum = safe_float(st.get("comp_cum_net_usd"), 0.0)

        if has_pos:
            ep = safe_float(st.get("entry_price"), lp)
            cur_g = ((lp - ep) / ep) * 100.0 if (lp > 0.0 and ep > 0.0) else 0.0
            armed1 = bool(st.get("is_trailing_armed", False))
            armed2 = bool(st.get("is_stage2_boost_armed", False))
            if armed2:
                r_tag = "🚀+1.25%부스트"
            elif armed1:
                r_tag = "🔒+1.00%잠금"
            else:
                r_tag = "🛡️HOLD대기"
            status_line = (
                f"🔥본대보유({_esc(st.get('entry_gate_id'))}·${ep:.2f}➔{cur_g:+.2f}%·{r_tag})"
            )
        elif bool(st.get("smart_wait_active", False)):
            sw_gid = _esc(str(st.get("smart_wait_gate_id") or "G1"))
            status_line = f"⏳스마트대기({sw_gid}·양봉/진바닥 포착중)"
        elif bool(st.get("is_session_done", False)):
            if phase in ("NO_TRADE_OFFWORK_0815", "NO_TRADE_OFFWORK_0921"):
                status_line = f"🏠09:21 무매매퇴근 (정찰 {day_seq}명 파견)"
            else:
                gid_done = _esc(str(st.get("entry_gate_id") or "G1"))
                td_g = safe_float(st.get("today_gain_pct"), 0.0)
                td_s = safe_float(st.get("today_simple_net_usd"), 0.0)
                status_line = (
                    f"🎯금일퇴근({gid_done} · {td_g:+.2f}% · 단리 {td_s:+,.0f}$)"
                )
        elif phase == "MACRO_WAIT_0830_0920":
            status_line = "⚡08:30~09:20 지표진바닥(DL10) 스캔중"
        elif scouts_cnt > 0:
            status_line = (
                f"🕵️정찰중(현 {scouts_cnt}명·누적 {day_seq}명·정책4)"
            )
        else:
            status_line = "⏳04:07 정찰대기 (정책4 · 1.0➔1.25%래칫)"

        return "\n".join(
            [
                "──────────────",
                f"🗡️ <b>[[모의] 암살자]</b> {status_line}",
                f"▫️ 전적: <b>{tot_d}전 {win_d}승 {loss_d}패</b> · 단리 <b>{s_cum:+,.0f}$</b> / 복리 <b>{c_cum:+,.0f}$</b> (<code>/assassin</code>)",
            ]
        )
    except Exception:
        return ""


async def build_assassin_detail_dashboard_html(
    context: Any, live_price: float = 0.0
) -> str:
    """
    /assassin 명령어 또는 전술 제어반 [🗡️ [모의] 암살자 상세 관제] 버튼 클릭 시 호출되는 상세 관제 보드.
    """
    now_est = datetime.now(EST_TZ)
    hm_now = now_est.hour * 100 + now_est.minute
    assn_ledger = ensure_assassin_ledger(context)
    await _sync_context_cache_for_assassin_snapshot(
        context=context,
        now_est=now_est,
        live_price_override=live_price,
        force_warmup=True,
    )
    feat = await _extract_live_assassin_features_and_qqq_snapshot(
        context=context,
        now_est=now_est,
        ledger=assn_ledger,
        force_warmup=True,
    )
    st = assn_ledger.get_state()

    lp = safe_float(feat.get("live_price"), 0.0)
    qqq_lp = safe_float(feat.get("qqq_live_price"), 0.0)
    init_s = max(
        100.0, safe_float(st.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD)
    )
    comp_eq = max(100.0, safe_float(st.get("comp_free_cash_usd"), init_s))
    bar_str = "📈양봉" if feat.get("is_bull_bar") else "📉음봉"
    ha_str = "🟢양봉" if feat.get("is_ha_bull") else "🔴음봉"

    raw_units = st.get("scout_units") or []
    units = [
        IndependentScoutUnit.from_dict(u)
        for u in raw_units
        if isinstance(u, dict)
    ]
    ref_dip_low = _resolve_t03a_reference_dip_low(st, units)
    t03a_trig_p = (
        round(
            ref_dip_low * (1.0 + SCOUT_T03A_DIP_SCAN_DROP_PCT / 100.0), 2
        )
        if ref_dip_low > 0.0
        else 0.0
    )

    vwap_line = (
        f"① RSI(14): <b>{feat['rsi_14']:.1f}</b> | ② 프리VWAP: <b>${feat['pre_vwap']:.2f}</b> ({feat['vs_vwap_pct']:+.2f}%)"
    )
    reg_vwap_val = safe_float(feat.get("regular_vwap"), 0.0)
    if hm_now >= ASSASSIN_REGULAR_OPEN_HM and reg_vwap_val > 0.0 and lp > 0.0:
        vs_reg_v = ((lp - reg_vwap_val) / reg_vwap_val) * 100.0
        vwap_line += (
            f" · 정규VWAP: <b>${reg_vwap_val:.2f}</b> ({vs_reg_v:+.2f}%)"
        )

    t03a_scan_line = (
        f"🔍 정책4스캔: 정찰저점 <b>${ref_dip_low:.2f}</b> ➔ <b>${t03a_trig_p:.2f}</b>(-1%) · 스마트대기 · DL_G6 · DL10(08:30~09:20)"
        if ref_dip_low > 0.0
        else "🔍 정책4스캔: PRE10(스마트대기) + 강세진바닥(DL_G6) + 지표진바닥(DL10 08:30~09:20)"
    )

    lines: List[str] = [
        "🗡️ <b>[인피니트 스노우볼 · 암살자(Assassin) 관제 보드]</b>",
        "⚙️ 운용모드: <b>🧪 변형 선택지 A (정책4 진입 × 2단래칫[+1.00%잠금➔+1.25%부스트] × HOLD)</b>",
        f"💵 기준시드: <b>${init_s:,.2f}</b> | 연속복리자산: <b>${comp_eq:,.2f}</b>",
        "━━━━━━━━━━━━━━━━━━",
        "📊 <b>[실시간 SOXL · QQQ 핵심 지표 스냅샷]</b>",
        f"• 현재가: <b>${lp:.2f}</b> ({bar_str} / HA {ha_str}) · QQQ: <b>${qqq_lp:.2f}</b>",
        vwap_line,
        f"③ 전일종가: <b>${feat['prev_reg_close']:.2f}</b> ({feat['vs_prev_close_pct']:+.2f}%) | ④ 프리시가: <b>${feat['pre_open_price']:.2f}</b> ({feat['vs_pre_open_pct']:+.2f}%)",
        f"• 프리고점DD: <b>{safe_float(feat.get('dd_from_pre_high_pct'), 0.0):+.2f}%</b> · SOXL 5분변화율: <b>{safe_float(feat.get('vel_5m_pct'), 0.0):+.2f}%</b> · QQQ 1분: <b>{feat['qqq_vel_1m_pct']:+.2f}%</b>",
        t03a_scan_line,
        "🛡️ 출구엔진: <b>🔒1차 +1.00% 바닥잠금(HA음봉 무시) ➔ 🚀2차 +1.25% HA부스트 & 장중 HOLD</b>",
        "━━━━━━━━━━━━━━━━━━",
    ]

    if bool(st.get("has_position", False)):
        ep = safe_float(st.get("entry_price"), lp)
        eq_qqq = safe_float(st.get("entry_qqq_price"), qqq_lp)
        qqq_chg = (
            ((qqq_lp - eq_qqq) / eq_qqq) * 100.0
            if (eq_qqq > 0.0 and qqq_lp > 0.0)
            else safe_float(st.get("qqq_chg_from_entry_pct"), 0.0)
        )
        cur_g = ((lp - ep) / ep) * 100.0 if ep > 0.0 else 0.0
        arm100_p = safe_float(st.get("arm_100_price"), 0.0)
        arm125_p = safe_float(st.get("arm_125_price"), 0.0)
        cap_p = safe_float(st.get("cap_500_price"), 0.0)
        pk_p = safe_float(st.get("peak_price"), lp)
        fl_p = safe_float(st.get("active_stop_floor_price"), 0.0)
        armed1 = bool(st.get("is_trailing_armed", False))
        armed2 = bool(st.get("is_stage2_boost_armed", False))
        if armed2:
            stage_badge = f"🚀2차부스트 추적중(스탑 ${fl_p:.2f})"
        elif armed1:
            stage_badge = f"🔒1차잠금 홀딩중(보존 ${arm100_p:.2f})"
        else:
            stage_badge = "🛡️미점화 HOLD(15:00 VWAP/15:59 MOC)"
        trig_m = str(st.get("entry_trigger_mode") or "SCOUT_GATE")
        e_rsi = safe_float(st.get("entry_rsi_14"), 50.0)
        e_vw_pct = safe_float(st.get("entry_vs_vwap_pct"), 0.0)
        e_pc_pct = safe_float(st.get("entry_vs_prev_close_pct"), 0.0)
        e_po_pct = safe_float(st.get("entry_vs_pre_open_pct"), 0.0)
        lines.extend(
            [
                f"🔥 <b>[금일 본대 포지션 가동 중 · 게이트 {_esc(st.get('entry_gate_id'))}]</b>",
                f"• 작동게이트: <b>{_esc(st.get('entry_gate_id'))}</b> ({_esc(st.get('entry_gate_desc'))})",
                f"• 진입단가: <b>${ep:.2f}</b> ({_esc(st.get('entry_time_est'))} EST · {_esc(trig_m)}) ➔ 현재 <b>{cur_g:+.2f}%</b>",
                f"• 진입지표: RSI <b>{e_rsi:.1f}</b> · VWAP <code>{e_vw_pct:+.2f}%</code> · 전일 <code>{e_pc_pct:+.2f}%</code> · 시가 <code>{e_po_pct:+.2f}%</code>",
                f"• 출동QQQ: <b>${eq_qqq:.2f}</b> ➔ 현재 <b>${qqq_lp:.2f}</b> (<b>{qqq_chg:+.2f}%</b>)",
                f"• 보유수량: 단리 <b>{safe_int(st.get('simple_held_qty'), 0)}주</b> / 복리 <b>{safe_int(st.get('comp_held_qty'), 0)}주</b>",
                f"• 2단래칫: 1차 <b>${arm100_p:.2f}</b>(+1.0%) ➔ 2차 <b>${arm125_p:.2f}</b>(+1.25%) · 캡 <b>${cap_p:.2f}</b>(+5%) · 최고 <b>${pk_p:.2f}</b> ({stage_badge})",
                "━━━━━━━━━━━━━━━━━━",
            ]
        )
    elif bool(st.get("is_session_done", False)):
        reason_str = str(
            st.get("today_exit_reason")
            or st.get("session_done_reason")
            or "퇴근완료"
        )
        if str(st.get("session_phase") or "") in (
            "NO_TRADE_OFFWORK_0815",
            "NO_TRADE_OFFWORK_0921",
        ):
            lines.extend(
                [
                    "🏠 <b>[금일 세션 상태 : 09:21 EST 무매매 안전 퇴근 완료]</b>",
                    "• 04:07~08:14 진성10/G6 및 08:30~09:20 DL10 미충족 (익일 04:07 EST 재출격)",
                    "━━━━━━━━━━━━━━━━━━",
                ]
            )
        else:
            lines.extend(
                [
                    f"🎯 <b>[금일 세션 상태 : 매매 완료 퇴근 ({_esc(st.get('today_exit_time_est'))} EST)]</b>",
                    f"• 청산사유: {_esc(reason_str)}",
                    f"• 금일성과: 수익률 <b>{safe_float(st.get('today_gain_pct'), 0.0):+.2f}%</b> (단리 <b>{safe_float(st.get('today_simple_net_usd'), 0.0):+,.2f}$</b> / 복리 <b>{safe_float(st.get('today_comp_net_usd'), 0.0):+,.2f}$</b>)",
                    _format_assassin_trade_review_block(st),
                    "━━━━━━━━━━━━━━━━━━",
                ]
            )

    hist_list = st.get("day_scout_history") or []
    prior_wins = safe_int(st.get("prior_scout_wins_today"), 0)
    lines.append(
        f"🕵️ <b>[금일 1주 가상 독립 정찰병 기록 (총 {len(hist_list)}명 · +1%익절 {prior_wins}회)]</b>"
    )
    if not hist_list:
        lines.append(
            "• 금일 파견된 정찰병이 아직 없습니다 (04:07 EST 첫 선봉 출격)."
        )
    else:
        for sc_d in hist_list[-7:]:
            sc = IndependentScoutUnit.from_dict(sc_d)
            lines.append(
                f"• <b>#{sc.scout_id}</b>({sc.entry_time_est[:5]}·{_esc(sc.entry_type[:7])}): "
                f"<b>${sc.entry_price:.2f}</b> | RSI <b>{sc.rsi_14:.1f}</b> | "
                f"VWAP {sc.vs_vwap_pct:+.1f}% | 전일 {sc.vs_prev_close_pct:+.1f}% | 시가 {sc.vs_pre_open_pct:+.1f}%"
            )

    journal_list = st.get("trade_journal_history") or []
    if journal_list:
        lines.append("━━━━━━━━━━━━━━━━━━")
        lines.append(
            f"📓 <b>[최근 출격 게이트·지표 복기 일지 (최근 {min(5, len(journal_list))}/{len(journal_list)}건)]</b>"
        )
        for j_item in journal_list[-5:]:
            if not isinstance(j_item, dict):
                continue
            j_dt = _esc(str(j_item.get("session_date") or "")[5:])
            j_gid = _esc(str(j_item.get("entry_gate_id") or "G1"))
            j_gain = safe_float(j_item.get("gain_pct"), 0.0)
            j_e_rsi = safe_float(j_item.get("entry_rsi_14"), 50.0)
            j_e_vw = safe_float(j_item.get("entry_vs_vwap_pct"), 0.0)
            j_x_code = _esc(str(j_item.get("exit_code") or "")[:14])
            j_icon = "🟢" if bool(j_item.get("is_win", True)) else "🔴"
            lines.append(
                f"• {j_icon}<code>{j_dt}</code> <b>{j_gid}</b>: <b>{j_gain:+.2f}%</b> "
                f"(진입RSI {j_e_rsi:.1f}·VWAP {j_e_vw:+.1f}% ➔ <code>{j_x_code}</code>)"
            )

    tot_d = safe_int(st.get("total_trade_days"), 0)
    win_d = safe_int(st.get("win_days"), 0)
    loss_d = safe_int(st.get("loss_days"), 0)
    no_tr_d = safe_int(st.get("no_trade_days"), 0)
    wr = (float(win_d) / float(tot_d)) * 100.0 if tot_d > 0 else 100.0
    s_cum = safe_float(st.get("simple_cum_net_usd"), 0.0)
    c_cum = safe_float(st.get("comp_cum_net_usd"), 0.0)
    s_roi = (s_cum / init_s) * 100.0
    c_roi = (c_cum / init_s) * 100.0

    gate_counts = st.get("gate_hit_counts") or {}
    gate_stat_str = (
        " · ".join(
            f"{_esc(k)}:{safe_int(v, 0)}회"
            for k, v in sorted(gate_counts.items())
        )
        if gate_counts
        else "기록대기"
    )

    lines.extend(
        [
            "━━━━━━━━━━━━━━━━━━",
            "🏆 <b>[[모의] 암살자 누적 성적표 (초기화: /reset_assassin)]</b>",
            f"• 총 출격일: <b>{tot_d}일</b> (<b>{win_d}승 {loss_d}패</b> · 승률 <b>{wr:.2f}%</b>) | 무매매퇴근: <b>{no_tr_d}일</b>",
            f"• 게이트분포: <code>{gate_stat_str}</code>",
            f"• 출구분포: +5%홈런 <b>{safe_int(st.get('exit_cap500_cnt'), 0)}회</b> · HA부스트 <b>{safe_int(st.get('exit_ha_boost_cnt'), 0)}회</b> · +1.25%보존 <b>{safe_int(st.get('exit_floor125_cnt'), 0)}회</b> · +1.0%보존 <b>{safe_int(st.get('exit_floor100_cnt'), 0)}회</b> · VWAP <b>{safe_int(st.get('exit_vwap_1500_cnt'), 0)}회</b> · MOC <b>{safe_int(st.get('exit_moc_cnt'), 0)}회</b>",
            f"• 💵 단리 누적순익: <b>{s_cum:+,.2f}$</b> (<b>{s_roi:+.2f}%</b>)",
            f"• 📈 복리 누적순익: <b>{c_cum:+,.2f}$</b> (<b>{c_roi:+.2f}%</b> · MDD <b>{safe_float(st.get('comp_max_dd_pct'), 0.0):.2f}%</b>)",
        ]
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# [핵심 10] 부팅 시 암살자 정책 4 (PRE10 + SMART_WAIT + DL_G6 + DL10) & 변형 선택지 A (2단 하이브리드 래칫 +1.00% ➔ +1.25% + HOLD) TDD 자가 검증기
# ---------------------------------------------------------------------------
def run_assassin_plugin_tdd() -> bool:
    """
    1) 선봉 정찰병(#1) 최초 파견 순간(allow_sc1_dip_scan=False) 차단 및 T03_A 1분 눌림 스캔(allow_sc1_dip_scan=True) G4 격발 검증
    2) 정책 4 : SMART_WAIT 분기(낙폭 얕은 음봉 칼날 시 대기 vs 양봉/진바닥 시 즉시 진입), DL_G6 강세장 급눌림 진바닥, 08:30~09:20 DL10 거시지표 무패 진바닥 격발 검증
    3) 변형 선택지 A (2단 하이브리드 래칫 +1.00% 1차 잠금 ➔ +1.25% 2차 부스트 점화 + HOLD) 검증:
       - [구간 2 : +1.00% ~ +1.24% 완충 홀딩 검증]: 진입가 $50.00 에서 $50.55(+1.10%) 도달 시 1차 잠금(STAGE1_FLOOR100_LOCKED)이 켜지고,
         이 구간에서 1분봉 HA 음봉(soxl_is_ha_bull=False)이 발생하더라도 조기 매도하지 않고 홀딩(should_exit=False)하는지 검증!
       - [구간 2 ➔ +1.00% 구출 익절 검증]: 1차 잠금 상태에서 +1.25% 에 닿지 못하고 $50.48(<= $50.50)로 되밀릴 때
         정확히 $50.50(+1.00%) 보존선(TRAIL_FLOOR_100)으로 익절 구출되는지 검증!
       - [구간 3 : +1.25% 2차 부스트 격상 및 HA 음봉/보존선 익절 검증]: $50.65(+1.30%) 돌파 시 2차 부스트(is_stage2_boost_armed=True, arm_125_price=$50.63)가 켜지고,
         이후 HA 음봉 발생 시 최소 $50.63(+1.25%) 이상(TRAIL_HA_RED_BOOST 또는 TRAIL_FLOOR_125)으로 확정 익절되는지 검증!
       - [구간 1 : 장중 HOLD 모드 검증]: 09:50 EST 정규장 개장 흔들기(-4.0%)에서도 바닥 손절하지 않고 홀딩(HOLD_WAITING_IGNITION)하는지 검증!
    """
    assert _is_collapsed_assassin_anchors(45.74, 45.74, 45.74) is True
    assert _is_collapsed_assassin_anchors(44.10, 45.20, 45.74) is False
    assert _is_collapsed_assassin_anchors(47.20, 0.0, 0.0) is False
    assert SAFETY_NET_MODE_DEFAULT == "RATCHET_100_125_HOLD_POLICY4"
    assert abs(ASSASSIN_ARM_IGNITION_PCT - 1.00) < 1e-6
    assert abs(ASSASSIN_STAGE2_BOOST_PCT - 1.25) < 1e-6

    # 1) 선봉 정찰병(#1) 파견 순간 차단 및 T03_A 1분 눌림 스캔 G4 격발 검증
    hit_1, _, _ = evaluate_10_truth_gates_signal(
        scout_seq=1,
        rsi_14=18.0,
        vs_vwap_pct=-3.0,
        vs_prev_close_pct=-5.0,
        vs_pre_open_pct=-3.0,
        vs_scout1_pct=0.0,
        prior_scout_wins=1,
        is_bull_bar=True,
        allow_sc1_dip_scan=False,
    )
    assert not hit_1

    hit_t03a_g4, gid_t03a_g4, _ = evaluate_10_truth_gates_signal(
        scout_seq=1,
        rsi_14=29.5,
        vs_vwap_pct=-0.85,
        vs_prev_close_pct=-1.40,
        vs_pre_open_pct=-1.20,
        vs_scout1_pct=-1.20,
        prior_scout_wins=0,
        is_bull_bar=True,
        allow_sc1_dip_scan=True,
    )
    assert hit_t03a_g4 and gid_t03a_g4 == "G4"

    # 2) 정책 4 : SMART_WAIT 분기 · DL_G6 · DL10 검증
    enter_now_knife, sw_code = should_enter_immediately_or_smart_wait(
        gate_id="G1",
        dd_from_pre_high_pct=-1.35,
        is_bull_bar=False,
        qqq_vel_1m_pct=-0.05,
    )
    assert not enter_now_knife and sw_code == "SMART_WAIT_FALLING_KNIFE"

    enter_now_deep, _ = should_enter_immediately_or_smart_wait(
        gate_id="G1",
        dd_from_pre_high_pct=-2.10,
        is_bull_bar=False,
        qqq_vel_1m_pct=-0.05,
    )
    assert enter_now_deep is True

    hit_g6, gid_g6, _ = evaluate_dl_g6_bull_pullback_signal(
        hm=553,
        scout_seq=2,
        rsi_14=26.4,
        vs_vwap_pct=-1.65,
        vs_prev_close_pct=0.45,
        vs_pre_open_pct=-1.70,
        dd_from_pre_high_pct=-2.65,
        is_bull_bar=True,
        qqq_vel_1m_pct=0.05,
    )
    assert hit_g6 and gid_g6 == "DL_G6"

    hit_dl10, gid_dl10, _ = evaluate_dl10_macro_bottom_signal(
        hm=835,
        rsi_14=22.5,
        vs_vwap_pct=-2.20,
        vel_5m_pct=-1.45,
        is_bull_bar=True,
        qqq_vel_1m_pct=0.04,
    )
    assert hit_dl10 and gid_dl10 == "DL10"

    # 3) 변형 선택지 A : 구간 2 (+1.00% ~ +1.24%) 1차 잠금 시 HA 음봉 무시 홀딩 검증
    res_stage1_hold = evaluate_assassin_ha_trailing_and_exits(
        hm=610,
        entry_price=50.00,
        live_price=50.55,          # +1.10% (+1.00% 이상, +1.25% 미달)
        bar_high_price=50.56,
        is_trailing_armed=True,
        is_stage2_boost_armed=False,
        peak_price=50.56,
        arm_100_price=50.50,
        arm_125_price=50.63,
        cap_500_price=52.50,
        soxl_is_bull_bar=False,
        soxl_is_ha_bull=False,     # HA 음봉 발생!
        soxl_prev_reg_close=49.50,
        soxl_pre_open_price=50.10,
        soxl_reg_vwap=50.20,
        post_entry_min_price=49.80,
        qqq_vel_1m_pct=-0.05,
        qqq_vel_3m_pct=-0.10,
        qqq_vel_max_3m_10m_pct=-0.05,
        qqq_bear_drop_amp_pct=0.20,
        nq_entry_bear_amp_pct=2.00,
    )
    assert (
        not res_stage1_hold["should_exit"]
        and res_stage1_hold["exit_code"] == "STAGE1_FLOOR100_LOCKED"
        and res_stage1_hold["is_trailing_armed"] is True
        and res_stage1_hold["is_stage2_boost_armed"] is False
    ), "+1.00% ~ +1.24% 구간에서는 HA 음봉에 털리지 않고 홀딩해야 합니다."

    # 4) 변형 선택지 A : 구간 2 에서 +1.00% 보존선($50.50) 하향 터치 시 즉시 +1.00% 구출 익절 검증
    res_floor100 = evaluate_assassin_ha_trailing_and_exits(
        hm=615,
        entry_price=50.00,
        live_price=50.48,          # $50.50 이하로 되밀림
        bar_high_price=50.52,
        is_trailing_armed=True,
        is_stage2_boost_armed=False,
        peak_price=50.58,
        arm_100_price=50.50,
        arm_125_price=50.63,
        cap_500_price=52.50,
        soxl_is_bull_bar=False,
        soxl_is_ha_bull=False,
        soxl_prev_reg_close=49.50,
        soxl_pre_open_price=50.10,
        soxl_reg_vwap=50.20,
        post_entry_min_price=49.80,
        qqq_vel_1m_pct=-0.05,
        qqq_vel_3m_pct=-0.10,
        qqq_vel_max_3m_10m_pct=-0.05,
        qqq_bear_drop_amp_pct=0.20,
        nq_entry_bear_amp_pct=2.00,
    )
    assert (
        res_floor100["should_exit"]
        and res_floor100["exit_code"] == "TRAIL_FLOOR_100"
        and abs(res_floor100["exit_price"] - 50.50) < 1e-6
    ), "+1.00% 1차 보존선 구출 스윕 검증 실패"

    # 5) 변형 선택지 A : 구간 3 (+1.25% 이상 돌파) 후 HA 음봉 발생 시 최소 +1.25%($50.63) 이상 부스트 익절 검증
    res_stage2_ha = evaluate_assassin_ha_trailing_and_exits(
        hm=625,
        entry_price=50.00,
        live_price=50.68,          # +1.36% (> +1.25% $50.63)
        bar_high_price=50.72,
        is_trailing_armed=True,
        is_stage2_boost_armed=True,
        peak_price=50.72,
        arm_100_price=50.50,
        arm_125_price=50.63,
        cap_500_price=52.50,
        soxl_is_bull_bar=False,
        soxl_is_ha_bull=False,     # 2차 점화 상태에서 HA 음봉 전환!
        soxl_prev_reg_close=49.50,
        soxl_pre_open_price=50.10,
        soxl_reg_vwap=50.20,
        post_entry_min_price=49.80,
        qqq_vel_1m_pct=-0.05,
        qqq_vel_3m_pct=-0.10,
        qqq_vel_max_3m_10m_pct=-0.05,
        qqq_bear_drop_amp_pct=0.20,
        nq_entry_bear_amp_pct=2.00,
    )
    assert (
        res_stage2_ha["should_exit"]
        and res_stage2_ha["exit_code"] == "TRAIL_HA_RED_BOOST"
        and abs(res_stage2_ha["exit_price"] - 50.68) < 1e-6
    ), "+1.25% 2차 점화 후 HA 음봉 부스트 익절 검증 실패"

    # 6) 변형 선택지 A : 장중 HOLD 모드(safety_hold_mode=True) 오전 개장 언더슈팅 홀딩 검증
    res_hold_0950 = evaluate_assassin_ha_trailing_and_exits(
        hm=950,
        entry_price=50.00,
        live_price=48.00,          # -4.00% 개장 흔들기
        bar_high_price=48.20,
        is_trailing_armed=False,
        is_stage2_boost_armed=False,
        peak_price=50.20,
        arm_100_price=50.50,
        arm_125_price=50.63,
        cap_500_price=52.50,
        soxl_is_bull_bar=False,
        soxl_is_ha_bull=False,
        soxl_prev_reg_close=51.00,
        soxl_pre_open_price=50.50,
        soxl_reg_vwap=49.50,
        post_entry_min_price=48.00,
        qqq_vel_1m_pct=-0.20,
        qqq_vel_3m_pct=-0.40,
        qqq_vel_max_3m_10m_pct=-0.20,
        qqq_bear_drop_amp_pct=1.50,
        nq_entry_bear_amp_pct=2.00,
        entry_qqq_price=500.0,
        qqq_live_price=492.0,
        safety_hold_mode=True,
    )
    assert (
        not res_hold_0950["should_exit"]
        and res_hold_0950["exit_code"] == "HOLD_WAITING_IGNITION"
    ), "변형 선택지 A HOLD 모드에서는 오전 개장 흔들기에 바닥 손절하면 안 됩니다."

    return True
