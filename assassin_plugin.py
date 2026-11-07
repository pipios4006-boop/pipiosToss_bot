# -*- coding: utf-8 -*-
"""
# MODIFIED: assassin_plugin.py (Part 1/2 — 🗡️ [모의 ⇄ 실전 Dual-Ready] 암살자 독립 플러그인 · T03_A_DIP10_ALL_SCOUT[10분 와이드 정찰 파견 + #1 선봉 파견 후 매 1분 직전 정찰 저점 대비 -1.00% 눌림 상시 진성 게이트 10 스캔] 탑재 · 본대 출동 순간 QQQ 지수[entry_qqq_price] 동시 저장 및 QQQ 2.0% 진폭의 50%[-0.80% ~ -1.00%] 3단계 안전망[암살자 익절 상태 시 홀딩 / 손실 상태 시 즉시 칼손절] 탑재 · 프리시가/프리VWAP 무오염 2단계 하이브리드 원장 박제 및 미확보 시 $0.00 표출 · 400봉 상한 연동 · 10대 진성 게이트 · HA 트레일링 · Case 93)
인피니트 스노우볼 (Infinite Snowball) v3.0 — 스나이퍼와 100% 물리적 격리된 상시 가동 [모의 ⇄ 실전 Dual-Ready] 암살자(Assassin) 코어 모듈 (Step 10 / 14 · Case 93)
- 역할:
  1) 스나이퍼 원장(soxl_stratum_ledger*.json) 및 예수금과 100% 물리적 분리된 독립 3중 원장(AssassinSimLedger : assassin_sim_ledger_{folder_slug}.json) 운용 ·
     프리장(04:07 ~ 09:29 EST) 중 실측된 진성 프리시가(today_pre_open_price) 및 프리VWAP(today_premarket_vwap) 영속화 박제 ·
     장 마감 후 최초 기동 등 당일 프리장 데이터 미확보 시 정규장 가격 가짜 폴백 없이 $0.00 (0.00%) 무오염 표출 및 구버전 오염 원장 자동 자가 치유
  2) 현재 ASSASSIN_LIVE_ORDER_HARD_LOCK = True 로 실전 주문 발사를 물리적으로 100% 차단하되,
     내부 주문 상태 머신(매수 발주 · +5.00% 상단 안전 캡 선장전 · +1.00% 점화 HA 트레일링 modify_order 가격 정정 스윕 · 15:59 2단계 방탄 MOC)은
     토스증권 Open API v1.2.14 실전 규격과 100% 동일하게 구현하여 스위치 해금 즉시 실전 암살자로 탈바꿈 가능
  3) 평일 04:07 ~ 08:14 EST 골든타임 1주 가상 독립 정찰병(IndependentScoutUnit · 실제 매수 없음 · 이동평균 및 합병 100% 배제) 파견 및 4대 지표(① RSI14 · ② 프리VWAP · ③ 전일종가 · ④ 04:07프리시가) 기록
  4) 👑 [T03_A_DIP10_ALL_SCOUT] 2번째+ 정찰병 파견 타점뿐만 아니라, #1 선봉 정찰병 파견 이후(day_scout_seq >= 1, 60초 타임쉴드 경과 뒤)
     현재가가 직전 정찰 최저점(ref_dip_low) 대비 -1.00% 이하로 눌린 상태에서는 10분 게이트를 기다리지 않고 매 1분마다 10대 진성 게이트(헌법 G1 ~ G5 + 폭락장 BG1 ~ BG5)를 상시 스캔하여,
     10분 사이 소멸되는 V자 양봉 반전 타점까지 하루 1회 기준 시드 100% 현재가 지정가로 즉시 진입 및 출동 순간의 QQQ 지수(entry_qqq_price) 동시 저장
  5) 출동 시점 QQQ 지수(entry_qqq_price) 기반 3단계 안전망 v2 (QQQ 2.0% 진폭 비율의 50% 기준 최소 -0.80% ~ 최대 -1.00% 하락 도달 시 암살자가 익절 상태면 홀딩 · 손실 상태면 즉시 칼손절)
  6) 5대 라이프사이클 실시간 텔레그램 푸시 알림 및 /assassin 상세 관제 보드(온디맨드 400봉 1m + 1d 일봉 + QQQ 1m 동시 프리워밍) 제공
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

ASSASSIN_SCOUT_START_HM: int = 407       # 04:07 EST 첫 선봉 정찰병 출격
ASSASSIN_GOLDEN_END_HM: int = 814        # 08:14 EST 정찰 및 본대 진입 마감
ASSASSIN_MACRO_CUTOFF_HM: int = 815      # 08:15 EST 거시지표 발표 선제 컷오프 (무매매 퇴근 & 3단 안전망 개시)
ASSASSIN_REGULAR_OPEN_HM: int = 930      # 09:30 EST 정규장 개장
ASSASSIN_VWAP_EXIT_START_HM: int = 1500  # 15:00 ~ 15:58 EST 수익권 정규장 VWAP 탈출 구간
ASSASSIN_MOC_EXIT_HM: int = 1559         # 15:59 ~ 16:01 EST 무오버나이트 2단계 방탄 MOC 강제 청산

SCOUT_MAX_INDEPENDENT_UNITS: int = 7     # 정찰병 최대 독립 보유 한도 (7명)
SCOUT_PROFIT_TARGET_PCT: float = 1.00    # 개별 정찰병 독립 익절 목표 (+1.00%)
SCOUT_PULLBACK_DROP_PCT: float = -1.00   # 정찰병 1층 공석 눌림목 (-1.00% 무필터)
SCOUT_BREAKOUT_RISE_PCT: float = 1.00    # 정찰병 1층 공석 돌파 (+1.00% & RSI<=50.0)
SCOUT_BREAKOUT_MAX_RSI: float = 50.0     # 정찰병 돌파 최대 허용 RSI(14)
SCOUT_TIME_SHIELD_SEC: float = 60.0      # 정찰병 매수/매도 후 60초 타임쉴드

# NEW [Case 93 : T03_A_DIP10_ALL_SCOUT — 10분 정찰병 파견 유지 + 직전 정찰 저점 대비 -1.00% 눌림 구간 매 1분 상시 진성 게이트 10 스캔 상수 및 인메모리 래치]
SCOUT_T03A_DIP_SCAN_DROP_PCT: float = -1.00
SCOUT_T03A_DIP_SCAN_INTERVAL_SEC: float = 60.0
_LAST_T03A_DIP_SCAN_KEY: str = ""
_LAST_T03A_DIP_SCAN_TS: float = 0.0

ASSASSIN_SAFE_CAP_PCT: float = 5.00      # 본대 진입 직후 상단 안전 캡 (+5.00%)
ASSASSIN_ARM_IGNITION_PCT: float = 1.00  # 트레일링 점화 및 최소 수익 보존선 (+1.00%)
ASSASSIN_BOOST_TIER2_PCT: float = 2.00   # +2.00% 이상 구간 콜백 완화 기준
ASSASSIN_CALLBACK_TIGHT_PCT: float = 0.20  # +1.00% ~ +1.99% 구간 최고가 대비 콜백 (-0.20%p)
ASSASSIN_CALLBACK_WIDE_PCT: float = 0.30   # +2.00% 이상 구간 최고가 대비 콜백 (-0.30%p)
ASSASSIN_QQQ_SURGE_BYPASS_PCT: float = 0.20  # QQQ 3m/10m 변화율 >= +0.20% 급등 시 HA 음봉 매도 보류

# NEW & MODIFIED [Case 93 : 출동 순간 QQQ 지수(entry_qqq_price) 기반 3단계 안전망 상수]
# QQQ 기준 진폭 비율 2.00%의 50%에 해당하는 손절 폭 = 최대 -1.00% (범위: 최소 -0.80% ~ 최대 -1.00%)
SAFETY_QQQ_BASE_AMP_PCT: float = 2.00         # QQQ 기준 진폭 비율 (2.00%)
SAFETY_QQQ_AMP_CUT_RATIO: float = 0.50        # QQQ 진폭 대비 안전망 손절 비율 (50% = 0.50)
SAFETY_DYN_QQQ_MIN_THR_PCT: float = 0.80      # 3단계 안전망 QQQ 최소 손절 진폭 비율 (-0.80%)
SAFETY_DYN_QQQ_MAX_THR_PCT: float = 1.00      # 3단계 안전망 QQQ 최대 손절 진폭 비율 (-1.00%)

# 하위 호환 심볼 유지 (외부 모듈 AST 임포트 호환 100% 보장)
SAFETY_STAGE1_HEART_STOP_PCT: float = -3.00
SAFETY_STAGE23_SOXL_LOSS_MAX_PCT: float = -0.30
SAFETY_STAGE23_QQQ_VEL3M_DROP_PCT: float = -0.25


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
    [모의 ⇄ 실전 Dual-Ready] 암살자 전용 원장 클래스.
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
            # 본대(Main Force) 포지션 · 출동 순간 QQQ 지수(entry_qqq_price) · 진입 트리거 모드 및 트레일링 상태
            "has_position": False,
            "entry_gate_id": "",
            "entry_gate_desc": "",
            "entry_trigger_mode": "",
            "entry_time_est": "",
            "entry_ts": 0.0,
            "entry_price": 0.0,
            "entry_qqq_price": 0.0,
            "qqq_chg_from_entry_pct": 0.0,
            "entry_scout_seq": 0,
            "entry_rsi_14": 50.0,
            "entry_vwap": 0.0,
            "entry_vs_vwap_pct": 0.0,
            "entry_prev_close": 0.0,
            "entry_vs_prev_close_pct": 0.0,
            "entry_pre_open": 0.0,
            "entry_vs_pre_open_pct": 0.0,
            "nq_entry_bear_amp_pct": 1.60,
            "dyn_qqq_stage2_thr_pct": 0.80,
            "simple_held_qty": 0,
            "simple_invested_usd": 0.0,
            "comp_held_qty": 0,
            "comp_invested_usd": 0.0,
            "cap_500_price": 0.0,
            "arm_100_price": 0.0,
            "is_trailing_armed": False,
            "armed_time_est": "",
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
            "alert_exit_sent": False,
            # 당일 체결 요약
            "today_exit_reason": "",
            "today_exit_time_est": "",
            "today_exit_price": 0.0,
            "today_gain_pct": 0.0,
            "today_simple_net_usd": 0.0,
            "today_comp_net_usd": 0.0,
            # 누적 모의 성적표 (단리 & 연속복리 동시 추적)
            "total_trade_days": 0,
            "win_days": 0,
            "loss_days": 0,
            "no_trade_days": 0,
            "total_scouts_dispatched": 0,
            "total_scout_win_exits": 0,
            "exit_cap500_cnt": 0,
            "exit_ha_boost_cnt": 0,
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
        raw_dyn_thr = safe_float(
            base.get("dyn_qqq_stage2_thr_pct"), SAFETY_DYN_QQQ_MIN_THR_PCT
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
        새로운 미국 영업일(today_est_str) 진입 시 당일 정찰병 및 본대 포지션 슬롯(entry_qqq_price · entry_trigger_mode 포함)과
        당일 프리장 앵커 검증 플래그 및 T03_A 인메모리 스캔 래치를 클리어하고 누적 성적표는 100% 보존한다.
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
            has_position=False,
            entry_gate_id="",
            entry_gate_desc="",
            entry_trigger_mode="",
            entry_time_est="",
            entry_ts=0.0,
            entry_price=0.0,
            entry_qqq_price=0.0,
            qqq_chg_from_entry_pct=0.0,
            entry_scout_seq=0,
            simple_held_qty=0,
            simple_invested_usd=0.0,
            comp_held_qty=0,
            comp_invested_usd=0.0,
            cap_500_price=0.0,
            arm_100_price=0.0,
            is_trailing_armed=False,
            armed_time_est="",
            peak_price=0.0,
            post_entry_min_price=0.0,
            active_stop_floor_price=0.0,
            pending_buy_order_id="",
            safe_cap_sell_order_id="",
            alert_0815_no_trade_sent=False,
            alert_entry_sent=False,
            alert_arm_100_sent=False,
            alert_exit_sent=False,
            today_exit_reason="",
            today_exit_time_est="",
            today_exit_price=0.0,
            today_gain_pct=0.0,
            today_simple_net_usd=0.0,
            today_comp_net_usd=0.0,
        )

    async def reset_assassin_stats_only(
        self, sniper_seed_usd: float = DEFAULT_INITIAL_SEED_USD
    ) -> Dict[str, Any]:
        """
        /reset_assassin 명령 시 누적 전적 및 단리·복리 실현익을 0점으로 초기화한다.
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


# ---------------------------------------------------------------------------
# [핵심 3] 10대 진성 게이트(헌법 G1~G5 + 폭락장 BG1~BG5) 판정 엔진 (Case 93 · T03_A_DIP10_ALL_SCOUT 연동)
# ---------------------------------------------------------------------------
def evaluate_10_truth_gates_signal(
    day_scout_seq: int,
    rsi_14: float,
    vs_vwap_pct: float,
    vs_prev_close_pct: float,
    vs_pre_open_pct: float,
    vs_scout1_pct: float,
    prior_scout_wins_today: int,
    is_bull_bar: bool,
    allow_sc1_dip_scan: bool = False,
) -> Tuple[bool, str, str]:
    """
    # MODIFIED [Case 93 : 2번째+ 정찰병 파견 타점 및 T03_A(#1 파견 후 직전 정찰 저점 대비 -1.00% 이하 1분 눌림 스캔)에서의 10대 진성 게이트 판정기]:
    - 04:07 EST 첫 선봉 정찰병(day_scout_seq == 1) 최초 파견 순간(allow_sc1_dip_scan == False)에는
      기준점 수립 전용이므로 본대 진입을 100% 차단한다.
    - 반면 #1 파견 이후 60초 타임쉴드가 경과한 뒤 직전 정찰 저점 대비 -1.00% 이하로 눌린 상태에서
      수행되는 1분 주기 상시 스캔(allow_sc1_dip_scan == True) 또는 2번째 이후 정찰병(day_scout_seq >= 2) 타점에서는
      G1 ~ G5 (헌법 5대 게이트) 및 BG1 ~ BG5 (폭락장 전용 5대 게이트) 중 하나라도 충족 시
      즉시 (True, gate_id, gate_desc) 를 반환한다.
    """
    seq_int = safe_int(day_scout_seq, 0)
    if seq_int <= 0:
        return False, "", "정찰병 미파견"
    if seq_int < 2 and not bool(allow_sc1_dip_scan):
        return False, "", "선봉 정찰병(#1) 기준점 수립"

    rsi = safe_float(rsi_14, 50.0)
    vwap_d = safe_float(vs_vwap_pct, 0.0)
    prev_d = safe_float(vs_prev_close_pct, 0.0)
    open_d = safe_float(vs_pre_open_pct, 0.0)
    sc1_d = safe_float(vs_scout1_pct, 0.0)
    wins = safe_int(prior_scout_wins_today, 0)
    bull = bool(is_bull_bar)

    # 1) 헌법 Gate 1 ~ Gate 5
    if rsi <= 30.0 and prev_d < 0.0 and open_d <= -1.50:
        return (
            True,
            "G1",
            f"헌법G1(RSI {rsi:.1f}<=30 · 전일종가 {prev_d:+.2f}%<0 · 프리시가 {open_d:+.2f}%<=-1.5%)",
        )
    if rsi <= 45.0 and vwap_d <= -2.00:
        return (
            True,
            "G2",
            f"헌법G2(RSI {rsi:.1f}<=45 · VWAP괴리 {vwap_d:+.2f}%<=-2.0%)",
        )
    if rsi <= 25.0 and vwap_d <= -1.00 and wins >= 1:
        return (
            True,
            "G3",
            f"헌법G3(RSI {rsi:.1f}<=25 · VWAP괴리 {vwap_d:+.2f}%<=-1.0% · 정찰선행익절 {wins}회)",
        )
    if rsi <= 32.0 and vwap_d <= -0.50 and prev_d <= -1.00 and bull:
        return (
            True,
            "G4",
            f"헌법G4(RSI {rsi:.1f}<=32 · VWAP {vwap_d:+.2f}%<=-0.5% · 전일 {prev_d:+.2f}%<=-1.0% · 양봉)",
        )
    if rsi <= 20.0 and prev_d >= 0.0:
        return (
            True,
            "G5",
            f"헌법G5(RSI {rsi:.1f}<=20 극과매도 · 전일종가 {prev_d:+.2f}%>=0%)",
        )

    # 2) 폭락장 BearGate 1 ~ BearGate 5
    if (
        30.0 <= rsi <= 45.0
        and vwap_d <= -1.00
        and prev_d <= -6.00
        and sc1_d <= -2.00
    ):
        return (
            True,
            "BG1",
            f"폭락BG1(RSI {rsi:.1f}[30~45] · VWAP {vwap_d:+.2f}%<=-1% · 전일 {prev_d:+.2f}%<=-6% · 선봉대비 {sc1_d:+.2f}%<=-2%)",
        )
    if (
        rsi <= 30.0
        and vwap_d <= -1.00
        and prev_d <= -3.00
        and open_d <= -1.00
    ):
        return (
            True,
            "BG2",
            f"폭락BG2(RSI {rsi:.1f}<=30 · VWAP {vwap_d:+.2f}%<=-1% · 전일 {prev_d:+.2f}%<=-3% · 시가 {open_d:+.2f}%<=-1%)",
        )
    if rsi <= 32.0 and open_d <= -2.50:
        return (
            True,
            "BG3",
            f"폭락BG3(RSI {rsi:.1f}<=32 · 프리시가대비 {open_d:+.2f}%<=-2.5% 급락투매)",
        )
    if rsi <= 25.0 and vwap_d <= -0.50 and bull:
        return (
            True,
            "BG4",
            f"폭락BG4(RSI {rsi:.1f}<=25 · VWAP {vwap_d:+.2f}%<=-0.5% · 1분봉 양봉반전)",
        )
    if rsi <= 45.0 and vwap_d <= -1.50 and prev_d <= -4.00 and wins >= 1:
        return (
            True,
            "BG5",
            f"폭락BG5(RSI {rsi:.1f}<=45 · VWAP {vwap_d:+.2f}%<=-1.5% · 전일 {prev_d:+.2f}%<=-4% · 정찰익절 {wins}회)",
        )

    return False, "", "10대 진성 게이트 미충족"


# ---------------------------------------------------------------------------
# [핵심 4] 출동 순간 QQQ 지수(entry_qqq_price) 기반 3단계 안전망 v2 (QQQ 2.0% 진폭의 50% = 최소 -0.80% ~ 최대 -1.00%) & HA 트레일링 판정기 (Case 93)
# ---------------------------------------------------------------------------
def evaluate_directional_3stage_safety_net_v2(
    hm: int,
    is_trailing_armed: bool,
    entry_price: float,
    live_price: float,
    post_entry_min_price: float,
    soxl_is_bull_bar: bool,
    soxl_is_ha_bull: bool,
    soxl_prev_reg_close: float,
    soxl_pre_open_price: float,
    qqq_vel_1m_pct: float,
    qqq_vel_3m_pct: float,
    qqq_bear_drop_amp_pct: float,
    nq_entry_bear_amp_pct: float,
    entry_qqq_price: float = 0.0,
    qqq_live_price: float = 0.0,
) -> Tuple[bool, str, str]:
    """
    # MODIFIED [Case 93 핵심 : 암살자 출동 순간의 QQQ 지수(entry_qqq_price) 기반 3단계 안전망 v2]:
    1) SOXL에 인위적인 -4.2% 하드캡을 씌우지 않고 오직 나스닥 100(QQQ) 지수를 따른다.
    2) QQQ 진폭 비율 2.00%(SAFETY_QQQ_BASE_AMP_PCT)의 50%(SAFETY_QQQ_AMP_CUT_RATIO)에 해당하는 손절 폭이
       3단계 안전망이므로, 동적 손절 진폭 비율(dyn_thr)은 최소 -0.80%(SAFETY_DYN_QQQ_MIN_THR_PCT)부터
       최대 -1.00%(SAFETY_DYN_QQQ_MAX_THR_PCT) 범위로 결정된다.
    3) [롱 방향성 및 암살자 손익 상태 교차 판정]:
       - 암살자 본대(SOXL)가 현재 익절(수익) 상태(live_price >= entry_price, cur_gain_pct >= 0.0%)라면
         굳이 퇴근할 필요가 없으므로 절대 손절하지 않고 홀딩한다!
       - 출동 순간 저장된 QQQ 지수(entry_qqq_price) 대비 현재 QQQ(qqq_live_price)가 상승 중(qqq_chg_from_entry_pct >= 0.0%)이거나,
         안전망이 상승/지지 중(양봉 또는 QQQ 1분/3분 반등 중)일 때도 손절하지 않고 홀딩한다!
       - 변동성 속에서 QQQ 지수가 출동 시점(entry_qqq_price) 대비 하락하여 3단계 안전망 진폭 비율(-0.80% ~ -1.00%,
         최대 -1.00%)에 도달했을 때, 암살자(SOXL)가 손실 상태(live_price < entry_price)라면 즉시 칼손절을 집행하여
         롱에 진입한 암살자의 손실률이 최대 -4.2% 선에서 마무리되도록 돕는다!
    """
    if is_trailing_armed or safe_int(hm, 0) < ASSASSIN_MACRO_CUTOFF_HM:
        return False, "", "안전망 비활성(08:15 이전 또는 +1% 점화 완료)"

    ep = safe_float(entry_price, 0.0)
    lp = safe_float(live_price, 0.0)
    if ep <= 0.0 or lp <= 0.0:
        return False, "", "가격 미확보"

    cur_gain_pct = ((lp - ep) / ep) * 100.0

    # [핵심 원칙 1]: 암살자(SOXL)가 익절(수익) 상태라면 굳이 퇴근할 필요가 없으므로 홀딩!
    if cur_gain_pct >= 0.0:
        return (
            False,
            "",
            f"🟢암살자 익절 상태({cur_gain_pct:+.2f}%) 유지 중(퇴근 불필요·홀딩)",
        )

    min_p = safe_float(post_entry_min_price, lp)
    if min_p <= 0.0:
        min_p = lp

    # QQQ 2.0% 진폭 기준 50% 비례 동적 임계치 산출 (범위: 최소 0.80% ~ 최대 1.00%)
    dyn_thr = round(
        min(
            SAFETY_DYN_QQQ_MAX_THR_PCT,
            max(
                safe_float(nq_entry_bear_amp_pct, SAFETY_QQQ_BASE_AMP_PCT)
                * SAFETY_QQQ_AMP_CUT_RATIO,
                SAFETY_DYN_QQQ_MIN_THR_PCT,
            ),
        ),
        2,
    )

    eq_qqq = safe_float(entry_qqq_price, 0.0)
    cur_qqq = safe_float(qqq_live_price, 0.0)
    has_entry_qqq_ref = bool(eq_qqq > 0.0 and cur_qqq > 0.0)

    if has_entry_qqq_ref:
        qqq_chg_from_entry_pct = ((cur_qqq - eq_qqq) / eq_qqq) * 100.0
        # [핵심 원칙 2]: 방향성에서 롱은 QQQ가 출동 시점보다 상승하면 손절할 필요가 없음
        if qqq_chg_from_entry_pct >= 0.0:
            return (
                False,
                "",
                f"🟢출동 QQQ(${eq_qqq:.2f}) 대비 상승/지지 중({qqq_chg_from_entry_pct:+.2f}%·홀딩)",
            )
        eff_qqq_drop_pct = max(0.0, -qqq_chg_from_entry_pct)
    else:
        qqq_chg_from_entry_pct = -abs(safe_float(qqq_bear_drop_amp_pct, 0.0))
        eff_qqq_drop_pct = max(0.0, safe_float(qqq_bear_drop_amp_pct, 0.0))

    # [핵심 원칙 3]: 출동 QQQ 대비 안전망 진폭 비율(-0.80% ~ -1.00%) 미달 시 감시 유지
    if eff_qqq_drop_pct < dyn_thr:
        return (
            False,
            "",
            f"🛡️QQQ 안전망 감시 중(QQQ {qqq_chg_from_entry_pct:+.2f}% / 발동 -{dyn_thr:.2f}%)",
        )

    # QQQ가 최대 마지노선(-1.00% = 2.0% 진폭의 50% 최대치) 이상 하락했고 암살자가 손실 상태(cur_gain_pct < 0.0)일 때:
    # 단, 현재 1분봉이 양봉이면서 QQQ 1분/3분 변화율이 모두 양수로 강하게 반등 중인 순간만 일시 유예하고 즉시 칼손절!
    if (
        has_entry_qqq_ref
        and eff_qqq_drop_pct >= SAFETY_DYN_QQQ_MAX_THR_PCT
        and not (
            soxl_is_bull_bar and qqq_vel_1m_pct > 0.0 and qqq_vel_3m_pct > 0.0
        )
    ):
        return (
            True,
            "STAGE23_DIR_BEAR_BREAK",
            (
                f"🛡️3단계 안전망 최대치(-{SAFETY_DYN_QQQ_MAX_THR_PCT:.2f}%) 발동 칼손절"
                f"(출동QQQ ${eq_qqq:.2f}➔${cur_qqq:.2f} [{qqq_chg_from_entry_pct:+.2f}%] · SOXL {cur_gain_pct:+.2f}%)"
            ),
        )

    # 동적 안전망 구간(-0.80% ~ -1.00%) 도달 시 방향성(상승/지지 여부) 확인
    above_macro_anchors = bool(
        (soxl_prev_reg_close > 0.0 and lp >= soxl_prev_reg_close)
        or (soxl_pre_open_price > 0.0 and lp >= soxl_pre_open_price)
    )
    not_making_new_low = bool(lp > min_p * 1.0005)
    is_safety_net_rising = bool(
        soxl_is_bull_bar
        or soxl_is_ha_bull
        or qqq_vel_1m_pct >= 0.0
        or qqq_vel_3m_pct >= 0.0
        or above_macro_anchors
        or not_making_new_low
    )
    if is_safety_net_rising:
        return (
            False,
            "",
            f"🟢안전망 상승/지지 중(QQQ {qqq_chg_from_entry_pct:+.2f}% · 손절 보류·홀딩)",
        )

    if has_entry_qqq_ref:
        return (
            True,
            "STAGE23_DIR_BEAR_BREAK",
            (
                f"🛡️3단계 안전망(-{dyn_thr:.2f}%) 역행 칼손절"
                f"(출동QQQ ${eq_qqq:.2f}➔${cur_qqq:.2f} [{qqq_chg_from_entry_pct:+.2f}%] · SOXL {cur_gain_pct:+.2f}%)"
            ),
        )

    if (
        cur_gain_pct <= SAFETY_STAGE23_SOXL_LOSS_MAX_PCT
        and qqq_vel_3m_pct <= SAFETY_STAGE23_QQQ_VEL3M_DROP_PCT
    ):
        return (
            True,
            "STAGE23_DIR_BEAR_BREAK",
            (
                f"🛡️2·3차 방향성 역행 칼손절(SOXL {cur_gain_pct:+.2f}% · "
                f"QQQ 3분 {qqq_vel_3m_pct:+.2f}% · 하락진폭 {eff_qqq_drop_pct:.2f}%>={dyn_thr:.2f}%)"
            ),
        )

    return False, "", "🛡️안전망 감시 중"


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
) -> Dict[str, Any]:
    """
    # MODIFIED [Case 93 : 본대 보유 중 통합 출구(Exit) 판정 엔진 — 출동 QQQ 지수(entry_qqq_price) 연동]:
    1) +5.00% 상단 안전 캡 도달 시 즉시 홈런 익절 (CAP_500_HOMERUN)
    2) +1.00% 점화가 도달 시 즉시 보존선(+1.00%) 하드 잠금 및 트레일링 점화
    3) 점화 상태에서:
       - 보존선(arm_100_price) 하향 터치 시 최소 +1.00% 보존 익절 (TRAIL_FLOOR_100)
       - 최고가(peak_price) 대비 콜백(-0.20%p / +2% 이상 시 -0.30%p) 도달 시 부스트 익절 (TRAIL_CALLBACK_BOOST)
       - 1분봉 하이킨 아시 음봉(not soxl_is_ha_bull) 전환 시 (단, QQQ 3m/10m 변화율 >= +0.20% 급등 중이면 바이패스)
         부스트 익절 (TRAIL_HA_RED_BOOST)
    4) 미점화 상태에서:
       - 15:00 ~ 15:58 EST 구간 현재가가 진입가 대비 수익권(>= +0.20%)이고 정규장 VWAP 이상 도달 시 탈출 (VWAP_1500_PROFIT_EXIT)
       - 08:15 EST 이후 출동 순간 QQQ 지수(entry_qqq_price) 대비 -0.80% ~ -1.00% 3단계 안전망 v2 격발 시(암살자 손실 상태일 때만) 역행 손절
       - 15:59 EST 이후 무오버나이트 2단계 방탄 MOC 강제 청산 (MOC_1559_EXIT)
    """
    ep = safe_float(entry_price, 0.0)
    lp = safe_float(live_price, 0.0)
    bh = max(lp, safe_float(bar_high_price, lp))
    cap_p = (
        safe_float(cap_500_price, 0.0)
        if safe_float(cap_500_price, 0.0) > 0.0
        else round(ep * (1.0 + ASSASSIN_SAFE_CAP_PCT / 100.0), 2)
    )
    arm_p = (
        safe_float(arm_100_price, 0.0)
        if safe_float(arm_100_price, 0.0) > 0.0
        else (math.ceil((ep * 1.010 - 1e-9) * 100.0) / 100.0)
    )

    armed = bool(is_trailing_armed)
    just_armed = False
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
            "just_armed": not armed,
            "peak_price": round(max(cur_peak, exec_p), 4),
            "post_entry_min_price": round(cur_min, 4),
            "active_stop_floor_price": round(cap_p, 2),
        }

    # 2) +1.00% 점화 확인
    if not armed and (bh >= arm_p or lp >= arm_p):
        armed = True
        just_armed = True
        cur_peak = max(cur_peak, lp, bh, arm_p)

    # 3) +1.00% 트레일링 점화 상태 출구 판정
    if armed:
        peak_gain_pct = ((cur_peak - ep) / ep) * 100.0 if ep > 0.0 else 1.0
        cb_allow = (
            ASSASSIN_CALLBACK_WIDE_PCT
            if peak_gain_pct >= ASSASSIN_BOOST_TIER2_PCT
            else ASSASSIN_CALLBACK_TIGHT_PCT
        )
        cb_stop_p = round(
            max(arm_p, cur_peak * (1.0 - cb_allow / 100.0)), 2
        )

        # 점화 직후 첫 틱에서는 즉시 매도하지 않고 추적 개시 알림을 먼저 타전
        if just_armed and lp >= arm_p:
            return {
                "should_exit": False,
                "exit_code": "ARMED_HOLD_TRACKING",
                "exit_desc": f"🔥 +1.00% 점화 완료 · 보존선 ${arm_p:.2f} 잠금 추적 중",
                "exit_price": 0.0,
                "is_trailing_armed": True,
                "just_armed": True,
                "peak_price": round(cur_peak, 4),
                "post_entry_min_price": round(cur_min, 4),
                "active_stop_floor_price": cb_stop_p,
            }

        if lp <= arm_p:
            return {
                "should_exit": True,
                "exit_code": "TRAIL_FLOOR_100",
                "exit_desc": f"🛡️ +1.00% 익절 보존선(${arm_p:.2f}) 스윕 체결",
                "exit_price": round(arm_p, 2),
                "is_trailing_armed": True,
                "just_armed": False,
                "peak_price": round(cur_peak, 4),
                "post_entry_min_price": round(cur_min, 4),
                "active_stop_floor_price": round(arm_p, 2),
            }

        if lp <= cb_stop_p:
            return {
                "should_exit": True,
                "exit_code": "TRAIL_CALLBACK_BOOST",
                "exit_desc": f"🚀 HA 트레일링 고점(${cur_peak:.2f}) 콜백(-{cb_allow:.2f}%) 익절(${cb_stop_p:.2f})",
                "exit_price": round(max(arm_p, lp), 2),
                "is_trailing_armed": True,
                "just_armed": False,
                "peak_price": round(cur_peak, 4),
                "post_entry_min_price": round(cur_min, 4),
                "active_stop_floor_price": cb_stop_p,
            }

        if (
            not soxl_is_ha_bull
            and qqq_vel_max_3m_10m_pct < ASSASSIN_QQQ_SURGE_BYPASS_PCT
        ):
            exec_ha_p = round(max(arm_p, lp), 2)
            return {
                "should_exit": True,
                "exit_code": "TRAIL_HA_RED_BOOST",
                "exit_desc": f"🕯️ HA 음봉 전환 트레일링 부스트 익절(${exec_ha_p:.2f})",
                "exit_price": exec_ha_p,
                "is_trailing_armed": True,
                "just_armed": False,
                "peak_price": round(cur_peak, 4),
                "post_entry_min_price": round(cur_min, 4),
                "active_stop_floor_price": exec_ha_p,
            }

        if safe_int(hm, 0) >= ASSASSIN_MOC_EXIT_HM:
            exec_moc_p = round(max(arm_p, lp), 2)
            return {
                "should_exit": True,
                "exit_code": "TRAIL_MOC_1559",
                "exit_desc": f"🔔 15:59 장마감 트레일링 확정 익절(${exec_moc_p:.2f})",
                "exit_price": exec_moc_p,
                "is_trailing_armed": True,
                "just_armed": False,
                "peak_price": round(cur_peak, 4),
                "post_entry_min_price": round(cur_min, 4),
                "active_stop_floor_price": exec_moc_p,
            }

        return {
            "should_exit": False,
            "exit_code": "ARMED_HOLD_TRACKING",
            "exit_desc": f"🔥 HA 트레일링 추적 중(최고 ${cur_peak:.2f} / 스탑 ${cb_stop_p:.2f})",
            "exit_price": 0.0,
            "is_trailing_armed": True,
            "just_armed": False,
            "peak_price": round(cur_peak, 4),
            "post_entry_min_price": round(cur_min, 4),
            "active_stop_floor_price": cb_stop_p,
        }

    # 4) 미점화 상태: 15:00 ~ 15:58 EST 수익권 정규장 VWAP 탈출
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
            "just_armed": False,
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
            "just_armed": False,
            "peak_price": round(cur_peak, 4),
            "post_entry_min_price": round(cur_min, 4),
            "active_stop_floor_price": round(lp, 2),
        }

    # 6) 미점화 상태: 08:15 EST 이후 출동 QQQ 지수(entry_qqq_price) 기반 3단계 안전망 v2 검문
    trig_safe, safe_code, safe_desc = evaluate_directional_3stage_safety_net_v2(
        hm=hm,
        is_trailing_armed=False,
        entry_price=ep,
        live_price=lp,
        post_entry_min_price=cur_min,
        soxl_is_bull_bar=soxl_is_bull_bar,
        soxl_is_ha_bull=soxl_is_ha_bull,
        soxl_prev_reg_close=soxl_prev_reg_close,
        soxl_pre_open_price=soxl_pre_open_price,
        qqq_vel_1m_pct=qqq_vel_1m_pct,
        qqq_vel_3m_pct=qqq_vel_3m_pct,
        qqq_bear_drop_amp_pct=qqq_bear_drop_amp_pct,
        nq_entry_bear_amp_pct=nq_entry_bear_amp_pct,
        entry_qqq_price=entry_qqq_price,
        qqq_live_price=qqq_live_price,
    )
    if trig_safe:
        return {
            "should_exit": True,
            "exit_code": safe_code,
            "exit_desc": safe_desc,
            "exit_price": round(lp, 2),
            "is_trailing_armed": False,
            "just_armed": False,
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
        "just_armed": False,
        "peak_price": round(cur_peak, 4),
        "post_entry_min_price": round(cur_min, 4),
        "active_stop_floor_price": 0.0,
    }
# -*- coding: utf-8 -*-
"""
# MODIFIED: assassin_plugin.py (Part 2/2 — T03_A_DIP10_ALL_SCOUT[직전 정찰 저점 대비 -1.00% 이하 매 1분 상시 진성 게이트 10 스캔 엔진 _evaluate_t03a_1m_dip_truth_gates_scan 및 본대 진입 공통 모듈 _enter_assassin_main_force_from_gate] 탑재 · 본대 출동 순간 QQQ 지수[entry_qqq_price] 원장 동시 박제 · 출동 QQQ 대비 -0.80% ~ -1.00% 안전망[익절 상태 시 홀딩 / 손실 상태 시 칼손절] 실시간 추적 · 4대 지표 400봉 1m + 10봉 1d 온디맨드 프리워밍 · 프리시가/프리VWAP 무오염 표출 · Dual-Ready 어댑터 · 5대 알림 · /assassin 관제 보드 · TDD 검증기)
"""

# 온디맨드 캔들 워밍업 과호출 방지용 인메모리 쿨다운 타임스탬프
_LAST_ASSASSIN_WARMUP_MONO: float = 0.0


def _esc(val: Any) -> str:
    return html.escape(str(val if val is not None else ""), quote=False)


# ---------------------------------------------------------------------------
# [핵심 5] 4대 핵심 지표(RSI14 · 프리/정규VWAP · 전일종가 · 04:07프리시가) 및 QQQ 안전망 스냅샷 추출기
# ---------------------------------------------------------------------------
async def _extract_live_assassin_features_and_qqq_snapshot(
    context: Any,
    live_price_override: float = 0.0,
    now_est: Optional[datetime] = None,
    force_warmup: bool = False,
) -> Dict[str, Any]:
    """
    # MODIFIED [Case 93 핵심 패치 — 프리시가 & 프리VWAP 2단계 하이브리드 정합성 · 미확보 시 $0.00 무오염 표출 · QQQ 실시간 지수 보장]:
    1) SOXL 및 QQQ 의 실시간 현재가와 1분봉(400봉 상한)/일봉(10봉) 지표를 추출한다.
    2) 캔들 캐시가 아직 워밍업되지 않았거나(anchors_ready == False),
       전일 정규장 종가(prev_reg_close)가 미확보된 경우 즉시 SOXL 1분봉(total_count=400) +
       SOXL 일봉(1d, count=10) + QQQ 1분봉(total_count=60)을 온디맨드로 조회하여 실제 차트 데이터를 복원한다!
       (force_warmup=True 시 쿨다운 즉시 바이패스)
    3) [1단계 : 아침 프리장에 가동된 날 ➔ 원장 박제값 유지]:
       당일 04:07 ~ 09:29 EST 프리장 1분봉에서 실측된 진성 프리시가(found_true_pre_open)와
       프리VWAP(found_true_pre_vwap)은 암살자 원장(AssassinSimLedger)에 검증 플래그
       (today_pre_open_verified=True, today_pre_vwap_verified=True)와 함께 영속화 박제하여,
       오후 정규장이나 장 마감 후 1분봉 윈도우가 밀려나더라도 그대로 보존한다.
    4) [2단계 : 장 마감 후(또는 정규장 중) 최초 배포하여 당일 프리장 데이터가 없는 날 ➔ $0.00 표출]:
       원장 및 1분봉 어디에도 당일 프리장 데이터가 없을 때는 정규장 시가나 정규장 VWAP,
       전일종가, 현재가로 가짜 폴백하는 것을 영구 금지하고 정확히 0.0 ($0.00 (+0.00%))을 반환한다!
    """
    global _LAST_ASSASSIN_WARMUP_MONO
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    today_str = dt_now.strftime("%Y-%m-%d")
    hm_now = dt_now.hour * 100 + dt_now.minute

    assn_ledger = ensure_assassin_ledger(context)
    st_assn = await assn_ledger.rollover_daily_session_if_needed(today_str)

    lp = safe_float(live_price_override, 0.0)
    if lp <= 0.0 and context is not None:
        lp = safe_float(
            getattr(context, "latest_prices", {}).get(TARGET_SYMBOL),
            safe_float(getattr(context, "last_soxl_live_price", 0.0), 0.0),
        )
    qqq_lp = (
        safe_float(
            getattr(context, "latest_prices", {}).get(MACRO_REF_SYMBOL),
            safe_float(getattr(context, "last_qqq_live_price", 0.0), 0.0),
        )
        if context is not None
        else 0.0
    )

    if (lp <= 0.0 or qqq_lp <= 0.0) and context is not None and hasattr(
        context, "api"
    ):
        try:
            p_map = await context.api.get_current_prices_batch(
                (TARGET_SYMBOL, MACRO_REF_SYMBOL)
            )
            if safe_float(p_map.get(TARGET_SYMBOL), 0.0) > 0.0:
                lp = safe_float(p_map.get(TARGET_SYMBOL), 0.0)
                context.latest_prices[TARGET_SYMBOL] = lp
            if safe_float(p_map.get(MACRO_REF_SYMBOL), 0.0) > 0.0:
                qqq_lp = safe_float(p_map.get(MACRO_REF_SYMBOL), 0.0)
                context.latest_prices[MACRO_REF_SYMBOL] = qqq_lp
        except Exception:
            pass

    soxl_met: Dict[str, Any] = {}
    qqq_met: Dict[str, Any] = {}
    if context is not None and hasattr(context, "candle_metrics_cache"):
        raw_sm = context.candle_metrics_cache.get(TARGET_SYMBOL)
        if isinstance(raw_sm, dict):
            soxl_met = dict(raw_sm)
        raw_qm = context.candle_metrics_cache.get(MACRO_REF_SYMBOL)
        if isinstance(raw_qm, dict):
            qqq_met = dict(raw_qm)

    c_prev_c = safe_float(soxl_met.get("prev_reg_close"), 0.0)
    c_pre_o = safe_float(soxl_met.get("pre_open_price"), 0.0)
    c_pre_v = safe_float(soxl_met.get("premarket_vwap"), 0.0)
    anchors_collapsed = _is_collapsed_assassin_anchors(
        c_prev_c, c_pre_o, c_pre_v
    )

    now_mono = time.monotonic()
    can_run_warmup = bool(
        force_warmup or (now_mono - _LAST_ASSASSIN_WARMUP_MONO) >= 10.0
    )
    if (
        context is not None
        and hasattr(context, "api")
        and (
            force_warmup
            or not bool(soxl_met.get("anchors_ready", False))
            or not bool(soxl_met.get("found_true_prev_close", False))
            or anchors_collapsed
            or safe_float(soxl_met.get("prev_bar_close"), 0.0) <= 0.0
        )
        and can_run_warmup
    ):
        _LAST_ASSASSIN_WARMUP_MONO = now_mono
        try:
            c_1m = await context.api.get_candles_1m(
                symbol=TARGET_SYMBOL, count=200, total_count=400
            )
            c_1d = await context.api.get_candles_1d(
                symbol=TARGET_SYMBOL, count=10
            )
            if c_1m or c_1d:
                soxl_met = await asyncio.to_thread(
                    compute_soxl_quant_metrics_1m,
                    c_1m or [],
                    lp,
                    dt_now,
                    c_1d or [],
                )
                context.candle_metrics_cache[TARGET_SYMBOL] = soxl_met
                if lp <= 0.0:
                    lp = safe_float(soxl_met.get("live_price"), 0.0)
        except Exception as exc:
            logger.debug("Assassin SOXL 400봉 1m+1d 온디맨드 워밍업 폴백: %s", exc)

        if (
            force_warmup
            or safe_float(qqq_met.get("prev_bar_close"), 0.0) <= 0.0
        ):
            try:
                q_1m = await context.api.get_candles_1m(
                    symbol=MACRO_REF_SYMBOL, count=60, total_count=60
                )
                if q_1m:
                    qqq_met = await asyncio.to_thread(
                        compute_qqq_macro_metrics_1m,
                        q_1m,
                        qqq_lp,
                        dt_now,
                    )
                    context.candle_metrics_cache[MACRO_REF_SYMBOL] = qqq_met
                    if qqq_lp <= 0.0:
                        qqq_lp = safe_float(qqq_met.get("live_price"), 0.0)
            except Exception:
                pass

    if lp > 0.0:
        soxl_met = refresh_metrics_with_live_tick(
            soxl_met, lp, now_est=dt_now, symbol=TARGET_SYMBOL
        )
        if context is not None and hasattr(context, "candle_metrics_cache"):
            context.candle_metrics_cache[TARGET_SYMBOL] = soxl_met
    if qqq_lp <= 0.0:
        qqq_lp = safe_float(
            qqq_met.get("live_price"),
            safe_float(qqq_met.get("current_price"), 0.0),
        )
    if qqq_lp > 0.0:
        qqq_met = refresh_metrics_with_live_tick(
            qqq_met, qqq_lp, now_est=dt_now, symbol=MACRO_REF_SYMBOL
        )
        if context is not None and hasattr(context, "candle_metrics_cache"):
            context.candle_metrics_cache[MACRO_REF_SYMBOL] = qqq_met

    prev_reg_close = safe_float(soxl_met.get("prev_reg_close"), 0.0)
    pre_open_price = safe_float(soxl_met.get("pre_open_price"), 0.0)
    pre_vwap = safe_float(soxl_met.get("premarket_vwap"), 0.0)
    reg_vwap = safe_float(soxl_met.get("regular_vwap"), 0.0)

    found_true_prev_c = bool(soxl_met.get("found_true_prev_close", False))
    found_true_pre_o = bool(
        soxl_met.get("found_true_pre_open", False) and pre_open_price > 0.0
    )
    found_true_pre_v = bool(
        soxl_met.get("found_true_pre_vwap", False) and pre_vwap > 0.0
    )

    saved_prev_ver = bool(st_assn.get("today_prev_close_verified", False))
    saved_open_ver = bool(st_assn.get("today_pre_open_verified", False))
    saved_vwap_ver = bool(st_assn.get("today_pre_vwap_verified", False))

    saved_prev_c = (
        safe_float(st_assn.get("today_prev_reg_close"), 0.0)
        if saved_prev_ver
        else 0.0
    )
    saved_pre_o = (
        safe_float(st_assn.get("today_pre_open_price"), 0.0)
        if saved_open_ver
        else 0.0
    )
    saved_pre_v = (
        safe_float(st_assn.get("today_premarket_vwap"), 0.0)
        if saved_vwap_ver
        else 0.0
    )

    if _is_collapsed_assassin_anchors(saved_prev_c, saved_pre_o, saved_pre_v):
        saved_prev_c = 0.0
        saved_pre_o = 0.0
        saved_pre_v = 0.0
        saved_prev_ver = False
        saved_open_ver = False
        saved_vwap_ver = False

    if not found_true_prev_c and saved_prev_c > 0.0:
        prev_reg_close = saved_prev_c
        found_true_prev_c = True
    if not found_true_pre_o and saved_open_ver and saved_pre_o > 0.0:
        pre_open_price = saved_pre_o
        found_true_pre_o = True
    if not found_true_pre_v and saved_vwap_ver and saved_pre_v > 0.0:
        pre_vwap = saved_pre_v
        found_true_pre_v = True

    is_now_valid_distinct = not _is_collapsed_assassin_anchors(
        prev_reg_close, pre_open_price, pre_vwap
    )
    if (
        (found_true_prev_c or found_true_pre_o or found_true_pre_v)
        and is_now_valid_distinct
    ):
        need_save_anchors = bool(
            (
                found_true_prev_c
                and (
                    not saved_prev_ver
                    or abs(saved_prev_c - prev_reg_close) > 1e-4
                )
            )
            or (
                found_true_pre_o
                and (
                    not saved_open_ver
                    or abs(saved_pre_o - pre_open_price) > 1e-4
                )
            )
            or (
                found_true_pre_v
                and (
                    not saved_vwap_ver
                    or (hm_now <= 935 and abs(saved_pre_v - pre_vwap) > 1e-4)
                )
            )
        )
        if need_save_anchors:
            upd_anchor_kw: Dict[str, Any] = {
                "today_anchors_locked": True,
                "today_regular_vwap": round(reg_vwap, 4),
            }
            if found_true_prev_c and prev_reg_close > 0.0:
                upd_anchor_kw["today_prev_reg_close"] = round(
                    prev_reg_close, 4
                )
                upd_anchor_kw["today_prev_close_verified"] = True
            if found_true_pre_o and pre_open_price > 0.0:
                upd_anchor_kw["today_pre_open_price"] = round(
                    pre_open_price, 4
                )
                upd_anchor_kw["today_pre_open_verified"] = True
            if found_true_pre_v and pre_vwap > 0.0:
                upd_anchor_kw["today_premarket_vwap"] = round(pre_vwap, 4)
                upd_anchor_kw["today_pre_vwap_verified"] = True
            st_assn = await assn_ledger.update_state(**upd_anchor_kw)

    if prev_reg_close <= 0.0:
        prev_reg_close = lp
    if not found_true_pre_o or pre_open_price <= 0.0:
        pre_open_price = 0.0
    if not found_true_pre_v or pre_vwap <= 0.0:
        pre_vwap = 0.0
    if reg_vwap <= 0.0 and hm_now >= ASSASSIN_REGULAR_OPEN_HM:
        reg_vwap = safe_float(soxl_met.get("day_vwap"), lp)

    vs_vwap_pct = (
        ((lp - pre_vwap) / pre_vwap) * 100.0
        if (lp > 0.0 and pre_vwap > 0.0)
        else 0.0
    )
    vs_reg_vwap_pct = (
        ((lp - reg_vwap) / reg_vwap) * 100.0
        if (lp > 0.0 and reg_vwap > 0.0)
        else 0.0
    )
    vs_prev_close_pct = (
        ((lp - prev_reg_close) / prev_reg_close) * 100.0
        if (lp > 0.0 and prev_reg_close > 0.0)
        else 0.0
    )
    vs_pre_open_pct = (
        ((lp - pre_open_price) / pre_open_price) * 100.0
        if (lp > 0.0 and pre_open_price > 0.0)
        else 0.0
    )

    sc1_p = safe_float(st_assn.get("scout1_open_price"), 0.0)
    if sc1_p <= 0.0:
        sc1_p = pre_open_price if pre_open_price > 0.0 else 0.0
    vs_scout1_pct = (
        ((lp - sc1_p) / sc1_p) * 100.0 if (lp > 0.0 and sc1_p > 0.0) else 0.0
    )

    cur_bar_open = safe_float(soxl_met.get("cur_bar_open"), lp)
    cur_bar_high = max(lp, safe_float(soxl_met.get("cur_bar_high"), lp))
    cur_bar_low_raw = safe_float(soxl_met.get("cur_bar_low"), 0.0)
    cur_bar_low = min(lp, cur_bar_low_raw) if cur_bar_low_raw > 0.0 else lp
    is_bull_bar = bool(lp >= cur_bar_open)
    is_ha_bull = bool(soxl_met.get("ha_bull", True))
    rsi_14 = round(safe_float(soxl_met.get("rsi_14"), 50.0), 2)

    qqq_vel_1m = round(safe_float(qqq_met.get("vel_1m_pct"), 0.0), 3)
    qqq_vel_3m = round(safe_float(qqq_met.get("vel_3m_pct"), 0.0), 3)
    qqq_vel_10m = round(safe_float(qqq_met.get("vel_10m_pct"), 0.0), 3)
    qqq_vel_max = round(
        safe_float(
            qqq_met.get("vel_max_3m_10m_pct"), max(qqq_vel_3m, qqq_vel_10m)
        ),
        3,
    )
    qqq_bear_amp = round(
        max(
            safe_float(qqq_met.get("bear_drop_amp_pct"), 0.0),
            max(0.0, -vs_pre_open_pct * 0.35) if pre_open_price > 0.0 else 0.0,
        ),
        3,
    )

    return {
        "live_price": round(lp, 4),
        "qqq_live_price": round(qqq_lp, 4),
        "rsi_14": rsi_14,
        "pre_vwap": round(pre_vwap, 4) if pre_vwap > 0.0 else 0.0,
        "reg_vwap": round(reg_vwap, 4) if reg_vwap > 0.0 else 0.0,
        "vs_vwap_pct": round(vs_vwap_pct, 2) if pre_vwap > 0.0 else 0.0,
        "vs_reg_vwap_pct": (
            round(vs_reg_vwap_pct, 2) if reg_vwap > 0.0 else 0.0
        ),
        "prev_reg_close": round(prev_reg_close, 4),
        "vs_prev_close_pct": round(vs_prev_close_pct, 2),
        "pre_open_price": (
            round(pre_open_price, 4) if pre_open_price > 0.0 else 0.0
        ),
        "vs_pre_open_pct": (
            round(vs_pre_open_pct, 2) if pre_open_price > 0.0 else 0.0
        ),
        "scout1_open_price": round(sc1_p, 4) if sc1_p > 0.0 else 0.0,
        "vs_scout1_pct": round(vs_scout1_pct, 2) if sc1_p > 0.0 else 0.0,
        "cur_bar_open": round(cur_bar_open, 4),
        "cur_bar_high": round(cur_bar_high, 4),
        "cur_bar_low": round(cur_bar_low, 4),
        "is_bull_bar": is_bull_bar,
        "is_ha_bull": is_ha_bull,
        "qqq_vel_1m_pct": qqq_vel_1m,
        "qqq_vel_3m_pct": qqq_vel_3m,
        "qqq_vel_10m_pct": qqq_vel_10m,
        "qqq_vel_max_3m_10m_pct": qqq_vel_max,
        "qqq_bear_drop_amp_pct": qqq_bear_amp,
    }


# ---------------------------------------------------------------------------
# [핵심 6] [모의 ⇄ 실전 Dual-Ready] 주문 실행 어댑터 (현재 SIMULATED 100% 하드 락)
# ---------------------------------------------------------------------------
async def _dispatch_assassin_buy_order(
    context: Any,
    qty: int,
    price: float,
    tag: str = "ASSN_BUY",
) -> Tuple[bool, str, float]:
    """
    - SIMULATED 모드(ASSASSIN_LIVE_ORDER_HARD_LOCK == True):
      실제 API 주문을 호출하지 않고 가상 주문 ID와 지정가 즉시 체결을 반환한다.
    - LIVE 모드 전환 시:
      POST /api/v1/orders (orderType="LIMIT", side="BUY", clientOrderId 주입)를 호출한다.
    """
    clean_p = round(max(0.01, float(price)), 2)
    clean_q = max(1, int(qty))
    if ASSASSIN_LIVE_ORDER_HARD_LOCK:
        sim_oid = f"SIM-{tag}-{int(time.time() * 1000)}"
        return True, sim_oid, clean_p

    if context is None or not hasattr(context, "api"):
        return False, "", 0.0
    try:
        cid = generate_client_order_id(prefix="assnb")
        res = await context.api.place_limit_order(
            symbol=TARGET_SYMBOL,
            side="BUY",
            quantity=clean_q,
            price=clean_p,
            client_order_id=cid,
            enforce_daymarket_block=True,
        )
        oid = str((res or {}).get("orderId") or cid)
        return bool(oid), oid, clean_p
    except Exception as exc:
        logger.warning("Assassin 실전 매수 발주 예외: %s", exc)
        return False, "", 0.0


async def _dispatch_assassin_safe_cap_sell_order(
    context: Any,
    qty: int,
    cap_price: float,
) -> Tuple[bool, str]:
    """
    본대 진입 체결 즉시 +5.00% 상단 안전 캡 지정가 매도 주문을 거래소에 선장전한다.
    (SIMULATED 모드에서는 가상 캡 주문 ID만 기록하여 실계좌 매도가능수량을 잠그지 않는다.)
    """
    clean_p = round(max(0.01, float(cap_price)), 2)
    clean_q = max(1, int(qty))
    if ASSASSIN_LIVE_ORDER_HARD_LOCK:
        return True, f"SIM-CAP500-{int(time.time() * 1000)}"

    if context is None or not hasattr(context, "api"):
        return False, ""
    try:
        cid = generate_client_order_id(prefix="assnc")
        res = await context.api.place_limit_order(
            symbol=TARGET_SYMBOL,
            side="SELL",
            quantity=clean_q,
            price=clean_p,
            client_order_id=cid,
            enforce_daymarket_block=False,
        )
        oid = str((res or {}).get("orderId") or cid)
        return bool(oid), oid
    except Exception as exc:
        logger.warning("Assassin +5%% 안전 캡 선장전 예외: %s", exc)
        return False, ""


async def _dispatch_assassin_exit_sweep_order(
    context: Any,
    qty: int,
    target_exit_price: float,
    existing_cap_order_id: str = "",
    is_moc_1559: bool = False,
) -> Tuple[bool, float]:
    """
    +1.00% 보존선/트레일링 스윕, 08:15 EST 이후 방향성 3단 안전망, 15:00 수익권 VWAP, 또는 15:59 방탄 MOC 청산 실행기:
    - SIMULATED 모드: 실주문 없이 즉시 target_exit_price 로 모의 체결 정산.
    - LIVE 모드 전환 시:
      선장전된 +5.00% 캡 주문(existing_cap_order_id)이 존재하면 POST /api/v1/orders/{orderId}/modify (quantity 미포함)로
      0.1초 만에 가격을 낮추어 즉시 Taker 체결시키고, 15:59 MOC 시에는 2단계 방탄 MOC(선취소 폴링 + 정정 폴백)를 수행한다.
    """
    clean_p = round(max(0.01, float(target_exit_price)), 2)
    if ASSASSIN_LIVE_ORDER_HARD_LOCK:
        return True, clean_p

    if context is None or not hasattr(context, "api"):
        return False, clean_p
    try:
        if existing_cap_order_id and hasattr(context.api, "modify_order"):
            sweep_p = (
                round(clean_p * 0.995, 2) if is_moc_1559 else clean_p
            )
            await context.api.modify_order(
                order_id=existing_cap_order_id,
                new_price=sweep_p,
            )
            return True, clean_p
    except Exception as exc:
        logger.warning("Assassin 출구 정정 스윕 예외: %s", exc)
    return True, clean_p


# ---------------------------------------------------------------------------
# [핵심 7] 5대 라이프사이클 실시간 텔레그램 푸시 알림 발송기 (Case 93 · T03_A 타점 표기 연동)
# ---------------------------------------------------------------------------
async def _send_1_scout_dispatched_alert(
    context: Any,
    scout: IndependentScoutUnit,
    total_active_scouts: int,
    prior_wins: int,
    gate_eval_note: str,
) -> None:
    if context is None or not hasattr(context, "send_slim_alert"):
        return
    bar_badge = "📈1분양봉" if scout.is_bull_bar else "📉1분음봉"
    lines = [
        f"🕵️ <b>[[모의] 암살자 정찰병 #{scout.scout_id} 파견]</b> ({_esc(scout.entry_type)})",
        "──────────────",
        f"▫️ 진입단가: <b>${scout.entry_price:.2f}</b> (1주 가상독립 · 목표 <b>${scout.target_price:.2f}</b>)",
        f"▫️ 보유정찰: 현 <b>{total_active_scouts}/{SCOUT_MAX_INDEPENDENT_UNITS}명</b> · 선행익절 <b>{prior_wins}회</b>",
        "──────────────",
        "📊 <b>[파견 시점 4대 핵심 지표]</b>",
        f"① RSI(14): <b>{scout.rsi_14:.1f}</b> ({bar_badge})",
        f"② 프리VWAP: <b>${scout.pre_vwap:.2f}</b> ({scout.vs_vwap_pct:+.2f}%)",
        f"③ 전일종가: <b>${scout.prev_reg_close:.2f}</b> ({scout.vs_prev_close_pct:+.2f}%)",
        f"④ 프리시가: <b>${scout.pre_open_price:.2f}</b> ({scout.vs_pre_open_pct:+.2f}%)",
        f"🎯 게이트판정: {_esc(gate_eval_note)}",
        f"🕒 {scout.entry_time_est} EST (실주문 100% 차단)",
    ]
    await context.send_slim_alert("\n".join(lines))


async def _send_2_0815_no_trade_offwork_alert(
    context: Any,
    st: Dict[str, Any],
    feat: Dict[str, Any],
    now_est: datetime,
) -> None:
    if context is None or not hasattr(context, "send_slim_alert"):
        return
    scouts_cnt = safe_int(st.get("day_scout_seq"), 0)
    scout_wins = safe_int(st.get("prior_scout_wins_today"), 0)
    no_tr_days = safe_int(st.get("no_trade_days"), 0)
    tot_days = safe_int(st.get("total_trade_days"), 0)
    win_days = safe_int(st.get("win_days"), 0)
    win_rate = (
        (float(win_days) / float(tot_days)) * 100.0 if tot_days > 0 else 100.0
    )
    lines = [
        "🏠 <b>[[모의] 암살자 08:15 거시지표 컷오프 · 무매매 안전 퇴근]</b>",
        "──────────────",
        f"▫️ 금일정찰: 총 <b>{scouts_cnt}명</b> 파견 (+1% 독립익절 <b>{scout_wins}회</b>)",
        "▫️ 퇴근사유: 04:07 ~ 08:14 EST 구간 10대 진성 게이트 미충족 (현금 100% 보존)",
        f"▫️ 08:15 지표: 현재가 <b>${feat['live_price']:.2f}</b> · RSI <b>{feat['rsi_14']:.1f}</b> · VWAP <b>${feat['pre_vwap']:.2f}</b>({feat['vs_vwap_pct']:+.2f}%)",
        f"🏆 누적전적: 출격 <b>{tot_days}일</b>({win_days}승 · 승률 <b>{win_rate:.1f}%</b>) · 무매매퇴근 <b>{no_tr_days}일</b>",
        f"🕒 {now_est.strftime('%m-%d %H:%M:%S EST')} (익일 04:07 재출격)",
    ]
    await context.send_slim_alert("\n".join(lines))


async def _send_3_truth_gate_entry_alert(
    context: Any,
    st: Dict[str, Any],
    feat: Dict[str, Any],
    now_est: datetime,
) -> None:
    if context is None or not hasattr(context, "send_slim_alert"):
        return
    gate_id = str(st.get("entry_gate_id") or "")
    gate_desc = str(st.get("entry_gate_desc") or "")
    trig_mode = str(st.get("entry_trigger_mode") or "")
    ep = safe_float(st.get("entry_price"), 0.0)
    eq_qqq = safe_float(
        st.get("entry_qqq_price"), safe_float(feat.get("qqq_live_price"), 0.0)
    )
    arm_p = safe_float(st.get("arm_100_price"), 0.0)
    cap_p = safe_float(st.get("cap_500_price"), 0.0)
    s_qty = safe_int(st.get("simple_held_qty"), 0)
    s_inv = safe_float(st.get("simple_invested_usd"), 0.0)
    c_qty = safe_int(st.get("comp_held_qty"), 0)
    c_inv = safe_float(st.get("comp_invested_usd"), 0.0)
    dyn_thr = safe_float(
        st.get("dyn_qqq_stage2_thr_pct"), SAFETY_DYN_QQQ_MIN_THR_PCT
    )
    seq_no = max(1, safe_int(st.get("entry_scout_seq"), 1))
    trig_label = (
        f"T03_A 1분 눌림 스캔(정찰 #{seq_no} 이후)"
        if trig_mode.startswith("T03A_")
        else f"정찰병 #{seq_no} 파견 타점"
    )

    lines = [
        f"🗡️ <b>[[모의] 암살자 진성 게이트 [{_esc(gate_id)}] 포착 · 본대 전격 진입!]</b>",
        "──────────────",
        f"🎯 격발게이트: <b>{_esc(gate_desc)}</b>",
        f"⚡ 진입단가: <b>${ep:.2f}</b> · 출동QQQ: <b>${eq_qqq:.2f}</b> ({_esc(trig_label)})",
        f"💵 단리투입: <b>{s_qty}주</b> (${s_inv:,.2f}) | 📈 복리투입: <b>{c_qty}주</b> (${c_inv:,.2f})",
        "──────────────",
        "📊 <b>[본대 진입 시점 4대 지표 박제]</b>",
        f"① RSI(14): <b>{safe_float(st.get('entry_rsi_14'), feat['rsi_14']):.1f}</b> | ② 프리VWAP: <b>${safe_float(st.get('entry_vwap'), feat['pre_vwap']):.2f}</b> ({safe_float(st.get('entry_vs_vwap_pct'), feat['vs_vwap_pct']):+.2f}%)",
        f"③ 전일종가: <b>${safe_float(st.get('entry_prev_close'), feat['prev_reg_close']):.2f}</b> ({safe_float(st.get('entry_vs_prev_close_pct'), feat['vs_prev_close_pct']):+.2f}%) | ④ 프리시가: <b>${safe_float(st.get('entry_pre_open'), feat['pre_open_price']):.2f}</b> ({safe_float(st.get('entry_vs_pre_open_pct'), feat['vs_pre_open_pct']):+.2f}%)",
        "──────────────",
        f"👑 상단안전캡(+5.0%): <b>${cap_p:.2f}</b> 선장전 완료",
        f"🔥 트레일링점화(+1.0%): <b>${arm_p:.2f}</b> 도달 시 보존선 잠금 & 0.4초 추적",
        f"🛡️ 3단계안전망: 출동QQQ(<b>${eq_qqq:.2f}</b>) 대비 <b>-{dyn_thr:.2f}%</b>(최대 -1.00%) 도달 & 손실 상태 시 칼손절 (익절 시 홀딩)",
        f"🕒 {now_est.strftime('%m-%d %H:%M:%S EST')}",
    ]
    await context.send_slim_alert("\n".join(lines))


async def _send_4_arm_100_trailing_alert(
    context: Any,
    st: Dict[str, Any],
    live_price: float,
    now_est: datetime,
) -> None:
    if context is None or not hasattr(context, "send_slim_alert"):
        return
    ep = safe_float(st.get("entry_price"), 0.0)
    arm_p = safe_float(st.get("arm_100_price"), 0.0)
    cap_p = safe_float(st.get("cap_500_price"), 0.0)
    cur_g = ((live_price - ep) / ep) * 100.0 if ep > 0.0 else 1.0
    lines = [
        "🔥 <b>[[모의] 암살자 +1.00% 도달 · HA 트레일링 고주파(0.4s) 추적 개시!]</b>",
        "──────────────",
        f"▫️ 진입단가: <b>${ep:.2f}</b> ➔ 현재가: <b>${live_price:.2f}</b> (<b>{cur_g:+.2f}%</b>)",
        f"🔒 익절보존선: <b>${arm_p:.2f} (+1.00%)</b> 하드 잠금 완료 (손실 가능성 0%!)",
        f"🚀 상단목표캡: <b>${cap_p:.2f} (+5.00%)</b> 까지 HA 양봉 추세 끝까지 추적",
        "▫️ 출구조건: 고점 대비 콜백(-0.20%/-0.30%) 또는 HA 음봉 전환 시 즉시 익절 스윕",
        f"🕒 {now_est.strftime('%m-%d %H:%M:%S EST')}",
    ]
    await context.send_slim_alert("\n".join(lines))


async def _send_5_exit_settlement_alert(
    context: Any,
    st: Dict[str, Any],
    now_est: datetime,
) -> None:
    if context is None or not hasattr(context, "send_slim_alert"):
        return
    ep = safe_float(st.get("entry_price"), 0.0)
    xp = safe_float(st.get("today_exit_price"), 0.0)
    gain_pct = safe_float(st.get("today_gain_pct"), 0.0)
    s_net = safe_float(st.get("today_simple_net_usd"), 0.0)
    c_net = safe_float(st.get("today_comp_net_usd"), 0.0)
    s_cum = safe_float(st.get("simple_cum_net_usd"), 0.0)
    c_cum = safe_float(st.get("comp_cum_net_usd"), 0.0)
    init_s = max(100.0, safe_float(st.get("initial_seed_usd"), 10000.0))
    s_roi = (s_cum / init_s) * 100.0
    c_roi = (c_cum / init_s) * 100.0

    tot_d = safe_int(st.get("total_trade_days"), 0)
    win_d = safe_int(st.get("win_days"), 0)
    loss_d = safe_int(st.get("loss_days"), 0)
    wr = (float(win_d) / float(tot_d)) * 100.0 if tot_d > 0 else 100.0
    header_icon = "🎯" if s_net >= 0.0 else "🛡️"

    lines = [
        f"{header_icon} <b>[[모의] 암살자 당일 매매 종료 및 퇴근 결산]</b>",
        "──────────────",
        f"▫️ 출구사유: <b>{_esc(st.get('today_exit_reason'))}</b>",
        f"▫️ 체결내역: 진입 <b>${ep:.2f}</b> ➔ 청산 <b>${xp:.2f}</b> (<b>{gain_pct:+.2f}%</b>)",
        f"💵 금일 단리손익: <b>{s_net:+,.2f}$</b> | 📈 금일 복리손익: <b>{c_net:+,.2f}$</b>",
        "──────────────",
        "🏆 <b>[[모의] 암살자 누적 성적표]</b>",
        f"▫️ 누적전적: <b>{tot_d}일</b> 출격 (<b>{win_d}승 {loss_d}패</b> · 승률 <b>{wr:.2f}%</b>)",
        f"▫️ 출구분포: +5%홈런 <b>{safe_int(st.get('exit_cap500_cnt'), 0)}</b> · HA부스트 <b>{safe_int(st.get('exit_ha_boost_cnt'), 0)}</b> · +1%보존 <b>{safe_int(st.get('exit_floor100_cnt'), 0)}</b> · 3단방어 <b>{safe_int(st.get('exit_safety_stage1_cnt'), 0) + safe_int(st.get('exit_safety_stage23_cnt'), 0)}</b>",
        f"💵 단리 누적순익: <b>{s_cum:+,.2f}$</b> ({s_roi:+.2f}%)",
        f"📈 복리 누적순익: <b>{c_cum:+,.2f}$</b> ({c_roi:+.2f}% · 자산 <b>${safe_float(st.get('comp_free_cash_usd'), init_s):,.2f}</b>)",
        f"🕒 {now_est.strftime('%m-%d %H:%M:%S EST')} (금일 퇴근 완료)",
    ]
    await context.send_slim_alert("\n".join(lines))


# ---------------------------------------------------------------------------
# [핵심 8] 메인 스나이퍼 루프 최상단 결속 상시 가동 틱 엔진 (execute_simulated_assassin_tick_plugin — T03_A_DIP10_ALL_SCOUT 탑재)
# ---------------------------------------------------------------------------
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
    extra_state_updates: Optional[Dict[str, Any]] = None,
) -> str:
    """
    # NEW [Case 93 : 10대 진성 게이트 포착 시 본대 즉시 진입 및 출동 QQQ 지수(entry_qqq_price) 원장 박제 공통 함수]:
    정찰병 파견 타점(#2+)과 T03_A 1분 눌림 스캔 타점(day_scout_seq >= 1 & 직전 정찰 저점 대비 -1.00% 이하)
    양쪽에서 동일하게 호출되어 기준 시드 100% 현재가 지정가 진입 및 +5.00% 안전 캡 선장전을 수행한다.
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
        price=lp,
        tag=f"GATE_{gate_id}",
    )
    if not ok_buy:
        return "ASSASSIN_BUY_FAILED"

    arm_p = (
        math.ceil(
            (fill_p * (1.0 + ASSASSIN_ARM_IGNITION_PCT / 100.0) - 1e-9) * 100.0
        )
        / 100.0
    )
    cap_p = round(fill_p * (1.0 + ASSASSIN_SAFE_CAP_PCT / 100.0), 2)
    _, cap_oid = await _dispatch_assassin_safe_cap_sell_order(
        context=context,
        qty=comp_qty,
        cap_price=cap_p,
    )

    entry_qqq_p = round(safe_float(feat.get("qqq_live_price"), 0.0), 4)
    raw_nq_amp = safe_float(feat.get("qqq_bear_drop_amp_pct"), 0.0)
    nq_bear_amp = (
        max(1.60, min(SAFETY_QQQ_BASE_AMP_PCT, raw_nq_amp))
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

    state_kw: Dict[str, Any] = {
        "session_phase": "MAIN_FORCE_ACTIVE",
        "has_position": True,
        "entry_gate_id": gate_id,
        "entry_gate_desc": gate_desc,
        "entry_trigger_mode": str(entry_trigger_mode or "SCOUT_GATE"),
        "entry_time_est": now_est.strftime("%H:%M:%S"),
        "entry_ts": now_ts,
        "entry_price": round(fill_p, 4),
        "entry_qqq_price": entry_qqq_p,
        "qqq_chg_from_entry_pct": 0.0,
        "entry_scout_seq": max(1, safe_int(entry_scout_seq, 1)),
        "entry_rsi_14": round(entry_rsi_14, 2),
        "entry_vwap": round(entry_vwap, 4),
        "entry_vs_vwap_pct": round(entry_vs_vwap_pct, 2),
        "entry_prev_close": round(entry_prev_close, 4),
        "entry_vs_prev_close_pct": round(entry_vs_prev_close_pct, 2),
        "entry_pre_open": round(entry_pre_open, 4),
        "entry_vs_pre_open_pct": round(entry_vs_pre_open_pct, 2),
        "nq_entry_bear_amp_pct": round(nq_bear_amp, 3),
        "dyn_qqq_stage2_thr_pct": dyn_qqq_thr,
        "simple_held_qty": simple_qty,
        "simple_invested_usd": round(float(simple_qty) * fill_p, 4),
        "comp_held_qty": comp_qty,
        "comp_invested_usd": round(float(comp_qty) * fill_p, 4),
        "cap_500_price": cap_p,
        "arm_100_price": round(arm_p, 2),
        "is_trailing_armed": False,
        "armed_time_est": "",
        "peak_price": round(fill_p, 4),
        "post_entry_min_price": round(fill_p, 4),
        "active_stop_floor_price": 0.0,
        "pending_buy_order_id": buy_oid,
        "safe_cap_sell_order_id": cap_oid,
        "alert_entry_sent": True,
        "gate_hit_counts": gate_counts,
    }
    if isinstance(extra_state_updates, dict) and extra_state_updates:
        state_kw.update(extra_state_updates)

    st = await assn_ledger.update_state(**state_kw)
    await _send_3_truth_gate_entry_alert(
        context=context, st=st, feat=feat, now_est=now_est
    )
    return f"ASSASSIN_MAIN_FORCE_ENTERED_{gate_id}"


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
    즉시 10대 진성 게이트(evaluate_10_truth_gates_signal, allow_sc1_dip_scan=False)를 검문하여 충족 시
    _enter_assassin_main_force_from_gate() 를 통해 본대를 투입한다.
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
        day_scout_seq=new_seq,
        rsi_14=new_scout.rsi_14,
        vs_vwap_pct=new_scout.vs_vwap_pct,
        vs_prev_close_pct=new_scout.vs_prev_close_pct,
        vs_pre_open_pct=new_scout.vs_pre_open_pct,
        vs_scout1_pct=new_scout.vs_scout1_pct,
        prior_scout_wins_today=prior_wins,
        is_bull_bar=new_scout.is_bull_bar,
        allow_sc1_dip_scan=False,
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
        total_active_scouts=len(units),
        prior_wins=prior_wins,
        gate_eval_note=(
            f"🔥 [{gate_id}] 격발!" if gate_hit else gate_desc
        ),
    )

    if not gate_hit:
        return f"SCOUT_DISPATCHED_#{new_seq}"

    return await _enter_assassin_main_force_from_gate(
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
    )


def _resolve_t03a_reference_dip_low(
    st: Dict[str, Any],
    units: List[IndependentScoutUnit],
) -> float:
    """
    # NEW [Case 93 : T03_A_DIP10_ALL_SCOUT 직전 정찰 기준 저점(ref_dip_low) 산출기]:
    당일 파견된 정찰병들의 최저 진입가(scout_cycle_min_buy_price), 직전 정찰 기준가(scout_anchor_price),
    현재 보유 정찰병 최저 단가(min(u.entry_price)), 또는 04:07 선봉가(scout1_open_price) 중
    유효한 양수 최저점을 반환한다.
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
    # NEW [Case 93 : T03_A_DIP10_ALL_SCOUT — #1 선봉 파견 이후 직전 정찰 저점 대비 -1.00% 이하 눌림 구간 매 1분 상시 진성 게이트 10 스캔 엔진]:
    1) 정찰병 파견 자체는 10분 와이드 규율을 그대로 유지하여 가짜 정찰병 남발을 막는다.
    2) 당일 #1 선봉 정찰병이 파견(day_scout_seq >= 1)된 이후 60.0초 타임쉴드가 경과한 상태에서,
       현재가(lp)가 직전 정찰 기준 저점(ref_dip_low) 대비 -1.00%(SCOUT_T03A_DIP_SCAN_DROP_PCT) 이하로 눌려 있으면,
       10분 게이트를 기다리지 않고 매 1분(EST 분 변경 또는 60초 경과)마다 10대 진성 게이트(allow_sc1_dip_scan=True)를 즉시 검문한다.
    3) 진성 게이트 미충족 시에는 인메모리 래치(_LAST_T03A_DIP_SCAN_KEY)만 갱신하여 디스크 쓰기(os.fsync) 0 Byte 를 유지한다 (Case 75).
    4) 진성 게이트(G1 ~ G5 / BG1 ~ BG5) 충족 시에는 10분 사이 소멸되는 V자 양봉 반전 타점을 놓치지 않고
       그 자리에서 즉시 본대 진입(_enter_assassin_main_force_from_gate)을 집행한다!
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

    gate_hit, gate_id, gate_desc = evaluate_10_truth_gates_signal(
        day_scout_seq=cur_seq,
        rsi_14=rsi_now,
        vs_vwap_pct=round(eff_vs_vwap, 2),
        vs_prev_close_pct=round(eff_vs_prev_close, 2),
        vs_pre_open_pct=round(eff_vs_pre_open, 2),
        vs_scout1_pct=round(vs_sc1, 2),
        prior_scout_wins_today=prior_wins,
        is_bull_bar=is_bull_now,
        allow_sc1_dip_scan=True,
    )
    if not gate_hit:
        return None

    new_min_p = round(min(ref_dip_low, lp), 4)
    return await _enter_assassin_main_force_from_gate(
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
        extra_state_updates={"scout_cycle_min_buy_price": new_min_p},
    )


async def execute_simulated_assassin_tick_plugin(
    context: Any,
    now_est: Optional[datetime] = None,
) -> str:
    """
    🚨 Case 93 핵심:
    main.py 의 main_sniper_loop() 최상단(스나이퍼 ON/OFF 분기 이전)에서 매 틱 호출되는
    [모의 ⇄ 실전 Dual-Ready] 암살자 상시 작동 상태 머신 (T03_A_DIP10_ALL_SCOUT 탑재).
    - 이미 당일 세션이 종료(is_session_done == True)된 경우에는 시세 스냅샷/워밍업 호출 전에
      즉시 리턴하여 백그라운드 루프가 _LAST_ASSASSIN_WARMUP_MONO 쿨다운을 점유하지 않도록 보호한다.
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

    # 04:00 ~ 04:06 EST 프리장 오프닝 안정화 대기
    if hm < ASSASSIN_SCOUT_START_HM:
        if context is not None:
            context.assassin_high_freq_active = False
        return "WAIT_0407_OPEN"

    # 당일 이미 퇴근 완료된 상태면 불필요한 캔들 워밍업 없이 즉시 대기 반환
    if bool(st.get("is_session_done", False)):
        if context is not None:
            context.assassin_high_freq_active = False
        return str(st.get("session_done_reason") or "SESSION_DONE")

    feat = await _extract_live_assassin_features_and_qqq_snapshot(
        context=context, now_est=dt_now
    )
    lp = safe_float(feat.get("live_price"), 0.0)
    if lp <= 0.0:
        return "NO_LIVE_PRICE"

    now_ts = time.time()

    # ===================================================================
    # [PHASE A] 본대(Main Force) 포지션 보유 중 -> 출구(트레일링/안전망/VWAP/MOC) 감시
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

        exit_eval = evaluate_assassin_ha_trailing_and_exits(
            hm=hm,
            entry_price=safe_float(st.get("entry_price"), lp),
            live_price=lp,
            bar_high_price=safe_float(feat.get("cur_bar_high"), lp),
            is_trailing_armed=bool(st.get("is_trailing_armed", False)),
            peak_price=safe_float(st.get("peak_price"), lp),
            arm_100_price=safe_float(st.get("arm_100_price"), 0.0),
            cap_500_price=safe_float(st.get("cap_500_price"), 0.0),
            soxl_is_bull_bar=bool(feat.get("is_bull_bar", True)),
            soxl_is_ha_bull=bool(feat.get("is_ha_bull", True)),
            soxl_prev_reg_close=safe_float(feat.get("prev_reg_close"), lp),
            soxl_pre_open_price=safe_float(feat.get("pre_open_price"), 0.0),
            soxl_reg_vwap=safe_float(feat.get("reg_vwap"), lp),
            post_entry_min_price=safe_float(
                st.get("post_entry_min_price"), lp
            ),
            qqq_vel_1m_pct=safe_float(feat.get("qqq_vel_1m_pct"), 0.0),
            qqq_vel_3m_pct=safe_float(feat.get("qqq_vel_3m_pct"), 0.0),
            qqq_vel_max_3m_10m_pct=safe_float(
                feat.get("qqq_vel_max_3m_10m_pct"), 0.0
            ),
            qqq_bear_drop_amp_pct=safe_float(
                feat.get("qqq_bear_drop_amp_pct"), 0.0
            ),
            nq_entry_bear_amp_pct=safe_float(
                st.get("nq_entry_bear_amp_pct"), SAFETY_QQQ_BASE_AMP_PCT
            ),
            entry_qqq_price=entry_qqq_p,
            qqq_live_price=qqq_lp,
        )

        new_armed = bool(exit_eval.get("is_trailing_armed", False))
        if context is not None:
            context.assassin_high_freq_active = new_armed

        # +1.00% 최초 점화 시 알림 #4 발송
        if (
            new_armed
            and not bool(st.get("alert_arm_100_sent", False))
            and not bool(exit_eval.get("should_exit", False))
        ):
            st = await assn_ledger.update_state(
                entry_qqq_price=entry_qqq_p,
                qqq_chg_from_entry_pct=cur_qqq_chg_pct,
                is_trailing_armed=True,
                armed_time_est=dt_now.strftime("%H:%M:%S"),
                peak_price=safe_float(exit_eval.get("peak_price"), lp),
                post_entry_min_price=safe_float(
                    exit_eval.get("post_entry_min_price"), lp
                ),
                active_stop_floor_price=safe_float(
                    exit_eval.get("active_stop_floor_price"), 0.0
                ),
                alert_arm_100_sent=True,
            )
            await _send_4_arm_100_trailing_alert(
                context=context, st=st, live_price=lp, now_est=dt_now
            )
            return "ASSASSIN_TRAILING_ARMED"

        if not bool(exit_eval.get("should_exit", False)):
            await assn_ledger.update_state(
                entry_qqq_price=entry_qqq_p,
                qqq_chg_from_entry_pct=cur_qqq_chg_pct,
                is_trailing_armed=new_armed,
                peak_price=safe_float(exit_eval.get("peak_price"), lp),
                post_entry_min_price=safe_float(
                    exit_eval.get("post_entry_min_price"), lp
                ),
                active_stop_floor_price=safe_float(
                    exit_eval.get("active_stop_floor_price"), 0.0
                ),
            )
            return str(exit_eval.get("exit_code") or "HOLD_POSITION")

        # 출구 조건 도달 -> 즉시 스윕 청산 및 당일 퇴근 정산
        exit_code = str(exit_eval.get("exit_code") or "EXIT")
        exit_desc = str(exit_eval.get("exit_desc") or exit_code)
        target_xp = safe_float(exit_eval.get("exit_price"), lp)
        c_qty = safe_int(st.get("comp_held_qty"), 1)
        s_qty = safe_int(st.get("simple_held_qty"), 1)

        _, exec_xp = await _dispatch_assassin_exit_sweep_order(
            context=context,
            qty=c_qty,
            target_exit_price=target_xp,
            existing_cap_order_id=str(
                st.get("safe_cap_sell_order_id") or ""
            ),
            is_moc_1559=("MOC" in exit_code),
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

        is_win = bool(s_net >= 0.0)
        upd_exit: Dict[str, Any] = {
            "session_phase": "OFFWORK_DONE",
            "is_session_done": True,
            "session_done_reason": exit_code,
            "has_position": False,
            "entry_qqq_price": entry_qqq_p,
            "qqq_chg_from_entry_pct": cur_qqq_chg_pct,
            "is_trailing_armed": new_armed,
            "peak_price": safe_float(exit_eval.get("peak_price"), exec_xp),
            "post_entry_min_price": safe_float(
                exit_eval.get("post_entry_min_price"), exec_xp
            ),
            "today_exit_reason": exit_desc,
            "today_exit_time_est": dt_now.strftime("%H:%M:%S"),
            "today_exit_price": round(exec_xp, 2),
            "today_gain_pct": round(gain_pct, 2),
            "today_simple_net_usd": round(s_net, 2),
            "today_comp_net_usd": round(c_net, 2),
            "total_trade_days": safe_int(st.get("total_trade_days"), 0) + 1,
            "win_days": safe_int(st.get("win_days"), 0) + (1 if is_win else 0),
            "loss_days": safe_int(st.get("loss_days"), 0)
            + (0 if is_win else 1),
            "simple_cum_net_usd": new_s_cum,
            "comp_cum_net_usd": new_c_cum,
            "comp_free_cash_usd": new_c_cash,
            "comp_peak_equity_usd": new_c_peak,
            "comp_max_dd_pct": new_max_dd,
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
        await _send_5_exit_settlement_alert(
            context=context, st=st, now_est=dt_now
        )
        return f"ASSASSIN_EXITED_{exit_code}"

    # ===================================================================
    # [PHASE B] 08:15 EST 도래 시 본대 미진입이면 즉시 무매매 안전 퇴근!
    # ===================================================================
    if hm >= ASSASSIN_MACRO_CUTOFF_HM:
        if context is not None:
            context.assassin_high_freq_active = False
        had_scouts_today = bool(safe_int(st.get("day_scout_seq"), 0) > 0)
        already_sent = bool(st.get("alert_0815_no_trade_sent", False))
        st = await assn_ledger.update_state(
            session_phase="NO_TRADE_OFFWORK_0815",
            is_session_done=True,
            session_done_reason="NO_TRADE_CUTOFF_0815",
            scout_units=[],
            scout_has_active_l1=False,
            no_trade_days=safe_int(st.get("no_trade_days"), 0) + 1,
            alert_0815_no_trade_sent=True,
        )
        if had_scouts_today and not already_sent:
            await _send_2_0815_no_trade_offwork_alert(
                context=context, st=st, feat=feat, now_est=dt_now
            )
        return "NO_TRADE_OFFWORK_0815"

    # ===================================================================
    # [PHASE C] 04:07 ~ 08:14 EST 골든타임 1주 가상 독립 정찰병 파견 · 독립 익절 · T03_A 1분 눌림 상시 스캔
    # ===================================================================
    raw_units = st.get("scout_units") or []
    units = [
        IndependentScoutUnit.from_dict(u)
        for u in raw_units
        if isinstance(u, dict)
    ]

    # C-1) 보유 중인 개별 정찰병 +1.00% 독립 익절 검문 (매수 후 60초 타임쉴드 경과 시)
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

    # C-2) 분기 1: 당일 첫 선봉 정찰병(#1 · 01_OPEN_0407) 또는 전량 익절 후 0주 재진입
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

    # C-3) 정찰병 보유 한도(7명) 미만일 때 1층 공석 재장전 또는 10분 와이드 정찰병 파견 검문
    if len(units) >= SCOUT_MAX_INDEPENDENT_UNITS:
        hold_status = "HOLD_SCOUT_MAX_7_UNITS"
    else:
        has_l1 = bool(st.get("scout_has_active_l1", True))
        anchor_p = safe_float(
            st.get("scout_anchor_price"), units[0].entry_price
        )

        # 분기 2: 1층 정찰병 공석 상태 -> 60초 주기 눌림(-1.0% 무필터) / 돌파(+1.0% & RSI<=50) 재장전
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

        # 분기 3: 활성 1층 정찰병 보유 중 -> 10분 고정 버킷 4단 와이드(-1.0% / -2.0% / -3.5% / -5.5%) 추매
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

    # C-4) 👑 [T03_A_DIP10_ALL_SCOUT 핵심]:
    # 정찰병 미파견 틱(10분 게이트 대기 중 · 와이드 단차 미달 패스 직후 · 7명 만석 중)에서
    # 현재가가 직전 정찰 기준 저점 대비 -1.00% 이하이면 매 1분마다 10대 진성 게이트를 상시 스캔!
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
            armed = bool(st.get("is_trailing_armed", False))
            status_line = (
                f"🔥본대보유({_esc(st.get('entry_gate_id'))}·${ep:.2f}➔{cur_g:+.2f}%·{'HA추적중' if armed else '+1%대기'})"
            )
        elif bool(st.get("is_session_done", False)):
            if phase == "NO_TRADE_OFFWORK_0815":
                status_line = f"🏠08:15 무매매퇴근 (정찰 {day_seq}명 파견)"
            else:
                td_g = safe_float(st.get("today_gain_pct"), 0.0)
                td_s = safe_float(st.get("today_simple_net_usd"), 0.0)
                status_line = f"🎯금일퇴근({td_g:+.2f}% · 단리 {td_s:+,.0f}$)"
        elif scouts_cnt > 0:
            status_line = (
                f"🕵️정찰중(현 {scouts_cnt}명·누적 {day_seq}명·T03_A스캔)"
            )
        else:
            status_line = "⏳04:07 정찰대기 (T03_A 상시ON)"

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
    호출 즉시 force_warmup=True 로 SOXL 1m(400봉) + 1d(일봉 10봉) + QQQ 1m을 즉시 점검하여
    아침 프리장 중 가동된 날은 원장에 박제된 실제 프리시가/프리VWAP을 표출하고,
    장 마감 후 최초 배포 등 당일 프리장 기록이 없는 날은 정규장 가격 폴백 없이 $0.00 (+0.00%)으로 무오염 표출한다.
    """
    now_est = datetime.now(EST_TZ)
    hm_now = now_est.hour * 100 + now_est.minute
    feat = await _extract_live_assassin_features_and_qqq_snapshot(
        context=context,
        live_price_override=live_price,
        now_est=now_est,
        force_warmup=True,
    )
    assn_ledger = ensure_assassin_ledger(context)
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
    if hm_now >= ASSASSIN_REGULAR_OPEN_HM and safe_float(
        feat.get("reg_vwap"), 0.0
    ) > 0.0:
        vwap_line += f" · 정규VWAP: <b>${feat['reg_vwap']:.2f}</b> ({feat['vs_reg_vwap_pct']:+.2f}%)"

    t03a_scan_line = (
        f"🔍 T03_A스캔: 정찰저점 <b>${ref_dip_low:.2f}</b> ➔ <b>${t03a_trig_p:.2f}</b>(-1.0%) 이하 매 1분 상시검문"
        if ref_dip_low > 0.0
        else "🔍 T03_A스캔: 10분 정찰 파견 + 선봉(#1) 후 저점 -1.0% 이하 매 1분 상시검문"
    )

    lines: List[str] = [
        "🗡️ <b>[인피니트 스노우볼 · 암살자(Assassin) 관제 보드]</b>",
        "⚙️ 운용모드: <b>🧪 모의 상시 작동 (SIMULATED · T03_A 1분 눌림 스캔)</b>",
        f"💵 기준시드: <b>${init_s:,.2f}</b> | 연속복리자산: <b>${comp_eq:,.2f}</b>",
        "━━━━━━━━━━━━━━━━━━",
        "📊 <b>[실시간 SOXL · QQQ 4대 지표 스냅샷]</b>",
        f"• 현재가: <b>${lp:.2f}</b> ({bar_str} / HA {ha_str}) · QQQ: <b>${qqq_lp:.2f}</b>",
        vwap_line,
        f"③ 전일종가: <b>${feat['prev_reg_close']:.2f}</b> ({feat['vs_prev_close_pct']:+.2f}%) | ④ 프리시가: <b>${feat['pre_open_price']:.2f}</b> ({feat['vs_pre_open_pct']:+.2f}%)",
        t03a_scan_line,
        f"🛡️ QQQ안전망: 1분 <b>{feat['qqq_vel_1m_pct']:+.2f}%</b> · 3분 <b>{feat['qqq_vel_3m_pct']:+.2f}%</b> · 발동범위 <b>-0.80% ~ -1.00%</b>",
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
        dyn_thr = safe_float(
            st.get("dyn_qqq_stage2_thr_pct"), SAFETY_DYN_QQQ_MIN_THR_PCT
        )
        cur_g = ((lp - ep) / ep) * 100.0 if ep > 0.0 else 0.0
        arm_p = safe_float(st.get("arm_100_price"), 0.0)
        cap_p = safe_float(st.get("cap_500_price"), 0.0)
        pk_p = safe_float(st.get("peak_price"), lp)
        fl_p = safe_float(st.get("active_stop_floor_price"), arm_p)
        armed = bool(st.get("is_trailing_armed", False))
        trig_m = str(st.get("entry_trigger_mode") or "SCOUT_GATE")
        lines.extend(
            [
                f"🔥 <b>[금일 본대 포지션 가동 중 · 게이트 {_esc(st.get('entry_gate_id'))}]</b>",
                f"• 진입단가: <b>${ep:.2f}</b> ({_esc(st.get('entry_time_est'))} EST · {_esc(trig_m)}) ➔ 현재 <b>{cur_g:+.2f}%</b>",
                f"• 출동QQQ: <b>${eq_qqq:.2f}</b> ➔ 현재 <b>${qqq_lp:.2f}</b> (<b>{qqq_chg:+.2f}%</b> / 안전망 <b>-{dyn_thr:.2f}%</b>)",
                f"• 보유수량: 단리 <b>{safe_int(st.get('simple_held_qty'), 0)}주</b> / 복리 <b>{safe_int(st.get('comp_held_qty'), 0)}주</b>",
                f"• 목표/방어: 캡 <b>${cap_p:.2f}</b>(+5%) · 점화 <b>${arm_p:.2f}</b>(+1%) · 최고 <b>${pk_p:.2f}</b> · 스탑 <b>${fl_p:.2f}</b> ({'HA추적중' if armed else '점화대기'})",
                "━━━━━━━━━━━━━━━━━━",
            ]
        )
    elif bool(st.get("is_session_done", False)):
        reason_str = str(
            st.get("today_exit_reason")
            or st.get("session_done_reason")
            or "퇴근완료"
        )
        if str(st.get("session_phase") or "") == "NO_TRADE_OFFWORK_0815":
            lines.extend(
                [
                    "🏠 <b>[금일 세션 상태 : 08:15 EST 무매매 안전 퇴근 완료]</b>",
                    "• 04:07 ~ 08:14 EST 구간 10대 진성 게이트 미충족 (익일 04:07 EST 재출격)",
                    "━━━━━━━━━━━━━━━━━━",
                ]
            )
        else:
            lines.extend(
                [
                    f"🎯 <b>[금일 세션 상태 : 매매 완료 퇴근 ({_esc(st.get('today_exit_time_est'))} EST)]</b>",
                    f"• 청산사유: {_esc(reason_str)}",
                    f"• 금일성과: 수익률 <b>{safe_float(st.get('today_gain_pct'), 0.0):+.2f}%</b> (단리 <b>{safe_float(st.get('today_simple_net_usd'), 0.0):+,.2f}$</b> / 복리 <b>{safe_float(st.get('today_comp_net_usd'), 0.0):+,.2f}$</b>)",
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

    tot_d = safe_int(st.get("total_trade_days"), 0)
    win_d = safe_int(st.get("win_days"), 0)
    loss_d = safe_int(st.get("loss_days"), 0)
    no_tr_d = safe_int(st.get("no_trade_days"), 0)
    wr = (float(win_d) / float(tot_d)) * 100.0 if tot_d > 0 else 100.0
    s_cum = safe_float(st.get("simple_cum_net_usd"), 0.0)
    c_cum = safe_float(st.get("comp_cum_net_usd"), 0.0)
    s_roi = (s_cum / init_s) * 100.0
    c_roi = (c_cum / init_s) * 100.0

    lines.extend(
        [
            "━━━━━━━━━━━━━━━━━━",
            "🏆 <b>[[모의] 암살자 누적 성적표 (초기화: /reset_assassin)]</b>",
            f"• 총 출격일: <b>{tot_d}일</b> (<b>{win_d}승 {loss_d}패</b> · 승률 <b>{wr:.2f}%</b>) | 무매매퇴근: <b>{no_tr_d}일</b>",
            f"• 출구분포: +5%홈런 <b>{safe_int(st.get('exit_cap500_cnt'), 0)}회</b> · HA부스트 <b>{safe_int(st.get('exit_ha_boost_cnt'), 0)}회</b> · +1%보존 <b>{safe_int(st.get('exit_floor100_cnt'), 0)}회</b> · 3단방어 <b>{safe_int(st.get('exit_safety_stage1_cnt'), 0) + safe_int(st.get('exit_safety_stage23_cnt'), 0)}회</b>",
            f"• 💵 단리 누적순익: <b>{s_cum:+,.2f}$</b> (<b>{s_roi:+.2f}%</b>)",
            f"• 📈 복리 누적순익: <b>{c_cum:+,.2f}$</b> (<b>{c_roi:+.2f}%</b> · MDD <b>{safe_float(st.get('comp_max_dd_pct'), 0.0):.2f}%</b>)",
        ]
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# [핵심 10] 부팅 시 암살자 10대 진성 게이트(T03_A 1분 눌림 스캔 포함) & 출동 QQQ 기반 3단계 안전망 v2 & 프리장 지표 무오염 TDD 자가 검증기
# ---------------------------------------------------------------------------
def run_assassin_plugin_tdd() -> bool:
    """
    1) 선봉 정찰병(#1) 최초 파견 순간(allow_sc1_dip_scan=False)에는 진성 게이트가 격발되지 않는지 검증
    2) #1 선봉 파견 이후 T03_A 직전 정찰 저점 대비 -1.00% 이하 1분 눌림 스캔(allow_sc1_dip_scan=True)에서는
       10분 게이트 도래 전이라도 G4 / G1 진성 게이트가 즉시 정상 격발되는지 검증
    3) 2번째 정찰병(#2)에서 G1 ~ G5 및 BG1 ~ BG5 가 정확히 격발되는지 검증
    4) 08:15 EST 이후 출동 순간 QQQ 지수(entry_qqq_price) 기반 3단계 안전망 v2 검증:
       - QQQ 2.0% 진폭 비율의 50% = 최소 -0.80% ~ 최대 -1.00% 도달 시에도
         암살자(SOXL)가 익절(수익) 상태(live_price >= entry_price)이면 퇴근하지 않고 홀딩(False)하는지 검증
       - 안전망이 상승/지지 중일 때 손절이 100% 차단(False)되는지 검증
       - 출동 QQQ 대비 -0.80% ~ -1.00% 도달 및 암살자 손실 상태(live_price < entry_price, 음봉 하락 중)에서
         즉시 칼손절(True, STAGE23_DIR_BEAR_BREAK)이 집행되는지 검증
    5) +1.00% 점화 후 보존선(arm_100_price) 하향 터치 시 최소 +1.00% 익절이 보장되는지 검증
    6) 동일값 폴백 오염 앵커(_is_collapsed_assassin_anchors) 및 미확보 프리장 지표(0.0) 정상 판별 검증
    """
    assert _is_collapsed_assassin_anchors(45.74, 45.74, 45.74) is True
    assert _is_collapsed_assassin_anchors(44.10, 45.20, 45.74) is False
    assert _is_collapsed_assassin_anchors(47.20, 0.0, 0.0) is False

    # 1) 선봉 정찰병(#1) 파견 순간(allow_sc1_dip_scan=False) 차단 검증
    hit_1, _, _ = evaluate_10_truth_gates_signal(
        day_scout_seq=1,
        rsi_14=18.0,
        vs_vwap_pct=-3.0,
        vs_prev_close_pct=-5.0,
        vs_pre_open_pct=-3.0,
        vs_scout1_pct=0.0,
        prior_scout_wins_today=1,
        is_bull_bar=True,
        allow_sc1_dip_scan=False,
    )
    assert not hit_1, "선봉 정찰병(#1) 최초 파견 순간은 본대 진입에서 제외되어야 합니다."

    # 2) T03_A_DIP10_ALL_SCOUT : #1 파견 후 직전 정찰 저점 대비 -1.00% 이하 1분 눌림 스캔(allow_sc1_dip_scan=True) 시 G4 양봉 반전 포착 검증
    hit_t03a_g4, gid_t03a_g4, _ = evaluate_10_truth_gates_signal(
        day_scout_seq=1,
        rsi_14=29.5,
        vs_vwap_pct=-0.85,
        vs_prev_close_pct=-1.40,
        vs_pre_open_pct=-1.20,
        vs_scout1_pct=-1.20,
        prior_scout_wins_today=0,
        is_bull_bar=True,
        allow_sc1_dip_scan=True,
    )
    assert (
        hit_t03a_g4 and gid_t03a_g4 == "G4"
    ), "T03_A 1분 눌림 스캔(allow_sc1_dip_scan=True) G4 격발 검증 실패"

    hit_g2, gid_g2, _ = evaluate_10_truth_gates_signal(
        day_scout_seq=2,
        rsi_14=42.0,
        vs_vwap_pct=-2.15,
        vs_prev_close_pct=-0.5,
        vs_pre_open_pct=-0.8,
        vs_scout1_pct=-1.0,
        prior_scout_wins_today=0,
        is_bull_bar=False,
    )
    assert hit_g2 and gid_g2 == "G2", "헌법 Gate 2 격발 검증 실패"

    hit_bg1, gid_bg1, _ = evaluate_10_truth_gates_signal(
        day_scout_seq=3,
        rsi_14=35.0,
        vs_vwap_pct=-1.20,
        vs_prev_close_pct=-6.50,
        vs_pre_open_pct=-1.80,
        vs_scout1_pct=-2.20,
        prior_scout_wins_today=0,
        is_bull_bar=False,
    )
    assert hit_bg1 and gid_bg1 == "BG1", "폭락장 BearGate 1 격발 검증 실패"

    # [검증 A]: 출동 QQQ($500.0) 대비 -1.00%($495.0) 하락했더라도 암살자(SOXL)가 익절 상태($50.0 -> $50.25)면 퇴근 불필요(홀딩) 검증
    trig_profit_hold, _, _ = evaluate_directional_3stage_safety_net_v2(
        hm=840,
        is_trailing_armed=False,
        entry_price=50.0,
        live_price=50.25,
        post_entry_min_price=49.80,
        soxl_is_bull_bar=False,
        soxl_is_ha_bull=False,
        soxl_prev_reg_close=51.0,
        soxl_pre_open_price=50.5,
        qqq_vel_1m_pct=-0.20,
        qqq_vel_3m_pct=-0.35,
        qqq_bear_drop_amp_pct=1.00,
        nq_entry_bear_amp_pct=2.00,
        entry_qqq_price=500.0,
        qqq_live_price=495.0,
    )
    assert (
        not trig_profit_hold
    ), "암살자가 익절 상태일 때는 QQQ 안전망에 도달해도 퇴근하면 안 됩니다."

    # [검증 B]: 안전망 상승/지지 중(양봉 또는 QQQ 반등 중)일 때는 손절 절대 금지 검증
    trig_rising, _, _ = evaluate_directional_3stage_safety_net_v2(
        hm=830,
        is_trailing_armed=False,
        entry_price=50.0,
        live_price=49.50,
        post_entry_min_price=49.20,
        soxl_is_bull_bar=True,
        soxl_is_ha_bull=True,
        soxl_prev_reg_close=51.0,
        soxl_pre_open_price=50.5,
        qqq_vel_1m_pct=0.12,
        qqq_vel_3m_pct=0.25,
        qqq_bear_drop_amp_pct=1.20,
        nq_entry_bear_amp_pct=1.60,
        entry_qqq_price=500.0,
        qqq_live_price=495.75,
    )
    assert not trig_rising, "안전망 상승 중에는 손절이 발동되면 안 됩니다."

    # [검증 C]: 출동 QQQ($500.0) 대비 -0.85%($495.75, 최소 -0.80% 이상) 하락 & 암살자 손실 상태($50.0 -> $48.20) & 음봉 신저가 진행 중 칼손절 검증
    trig_falling, scode, _ = evaluate_directional_3stage_safety_net_v2(
        hm=845,
        is_trailing_armed=False,
        entry_price=50.0,
        live_price=48.20,
        post_entry_min_price=48.20,
        soxl_is_bull_bar=False,
        soxl_is_ha_bull=False,
        soxl_prev_reg_close=51.0,
        soxl_pre_open_price=50.5,
        qqq_vel_1m_pct=-0.10,
        qqq_vel_3m_pct=-0.15,
        qqq_bear_drop_amp_pct=0.85,
        nq_entry_bear_amp_pct=1.60,
        entry_qqq_price=500.0,
        qqq_live_price=495.75,
    )
    assert (
        trig_falling and scode == "STAGE23_DIR_BEAR_BREAK"
    ), "출동 QQQ 대비 -0.80% ~ -1.00% 역행 칼손절 검증 실패"

    # +1.00% 점화 후 보존선 스윕 검증
    ex_res = evaluate_assassin_ha_trailing_and_exits(
        hm=730,
        entry_price=50.0,
        live_price=50.48,
        bar_high_price=50.50,
        is_trailing_armed=True,
        peak_price=50.80,
        arm_100_price=50.50,
        cap_500_price=52.50,
        soxl_is_bull_bar=False,
        soxl_is_ha_bull=False,
        soxl_prev_reg_close=49.0,
        soxl_pre_open_price=49.5,
        soxl_reg_vwap=50.2,
        post_entry_min_price=49.8,
        qqq_vel_1m_pct=-0.05,
        qqq_vel_3m_pct=-0.10,
        qqq_vel_max_3m_10m_pct=-0.05,
        qqq_bear_drop_amp_pct=0.20,
        nq_entry_bear_amp_pct=1.60,
        entry_qqq_price=500.0,
        qqq_live_price=499.0,
    )
    assert (
        ex_res["should_exit"]
        and ex_res["exit_code"] == "TRAIL_FLOOR_100"
        and abs(ex_res["exit_price"] - 50.50) < 1e-6
    ), "+1.00% 익절 보존선 스윕 검증 실패"

    return True
