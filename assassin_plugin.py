# -*- coding: utf-8 -*-
"""
# NEW: assassin_plugin.py (Part 1/2)
인피니트 스노우볼 (Infinite Snowball) v3.0 — 🗡️ [모의 ⇄ 실전 Dual-Ready] 암살자(Assassin) 독립 플러그인 코어 모듈
- 핵심 설계 원칙:
  1) 스나이퍼(Sniper v3.0)와 100% 물리적 격리된 독립 원장(assassin_sim_ledger_<folder_slug>.json) 사용:
     실전 스나이퍼의 예수금·보유지층·원장에 단 1바이트의 간섭도 일으키지 않는다.
  2) 상시 가동 [모의] 모드 (ASSASSIN_LIVE_ORDER_HARD_LOCK = True 기본 잠금):
     실전 스나이퍼가 ON 이든 OFF 이든, 주식을 보유 중이든 0주이든 상관없이
     매일 04:07 ~ 16:00 EST 전 구간에서 백그라운드로 상시 작동하며 아래 5대 실시간 알림을 타전한다:
       ① 🕵️ 정찰병 파견 알림 (04:07 선봉 #1 및 후속 #2, #3... 1주 독립 정찰병 투입 시 4대 지표 브리핑)
       ② 🏠 무매매 퇴근 알림 (08:15:00 EST 정각 도래 시 진성 게이트 10 미충족으로 시드 100% 보존 퇴근)
       ③ 🗡️ 진성 게이트 10 조건 달성 & 본대 진입 알림 (G1 ~ G5 / BG1 ~ BG5 포착 즉시 진입)
       ④ 🔥 +1.00% 익절가 도달 & 하이킨 아시(HA) 트레일링 추적 개시 알림 (+1.00% 보존선 하드 잠금)
       ⑤ 🎯 익절(또는 방향성 3단 안전망 / 15:00 수익권 VWAP / 15:59 방탄 MOC) 퇴근 완료 및 누적 성적표 알림
  3) 즉시 실전 전환 가능한 Dual-Ready 상태 머신:
     내부 매수 발주(LIMIT) -> 체결 동기화 -> +5.00% 상단 안전 캡 매도 주문 선장전 ->
     +1.00% 점화 하이킨 아시 트레일링 & modify_order(quantity 제외) 0.1초 즉시 가격 정정 스윕 ->
     08:15 이후 순수 롱 방향성 인지 3단계 안전망(안전망 상승 중 손절 절대 금지 · 하락 진행 중 역행만 칼손절) ->
     15:59 ~ 16:01 EST 2단계 방탄 MOC(선취소+폴링 발사 / 수량 잠김 시 modify_order 직접 정정) 로직이
     실전 토스증권 Open API v1.2.14 규격과 100% 동일하게 구현되어 있어,
     향후 실전 가동 승인 시 코드 재작성 없이 즉시 실전 암살자로 탈바꿈한다.
"""

from __future__ import annotations

import asyncio
import errno
import glob
import html
import json
import logging
import math
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from quant_engine import (
    calc_sell_realized_pnl,
    resolve_effective_round_trip_fee_rate_pct,
)
from quant_indicators_plugin import (
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
    ROUND_TRIP_FEE_RATE_PCT,
    TARGET_SYMBOL,
    _NonRetryableApiError,
    emergency_free_disk_space_sync,
    generate_client_order_id,
    get_bot_base_dir,
    get_folder_slug,
    safe_float,
    safe_int,
)

logger = logging.getLogger("toss_sniper.assassin_plugin")

# ---------------------------------------------------------------------------
# [핵심 상수] Dual-Ready 실행 모드 스위치 및 5개년 백테스트 검증 완료 챔피언 파라미터
# ---------------------------------------------------------------------------
ASSASSIN_MODE_SIMULATED: str = "SIMULATED"
ASSASSIN_MODE_LIVE: str = "LIVE"

# 🚨 현재는 실제 투자를 물리적으로 100% 금지하고 [모의] 암살자로만 상시 운영 (향후 실전 전환 시 False 해제)
ASSASSIN_LIVE_ORDER_HARD_LOCK: bool = True

ASSASSIN_SYMBOL: str = "SOXL"
MACRO_REF_SYMBOL: str = "QQQ"

# 골든타임(04:07 ~ 08:14 EST) 및 08:15 거시지표 선제 컷오프 / 15:00 VWAP / 15:59 방탄 MOC 시각(HHMM)
ASSASSIN_BUY_START_HM: int = 407
ASSASSIN_BUY_END_HM: int = 814
ASSASSIN_MACRO_CUTOFF_HM: int = 815
ASSASSIN_VWAP_ESCAPE_START_HM: int = 1500
ASSASSIN_VWAP_ESCAPE_END_HM: int = 1558
ASSASSIN_MOC_START_HM: int = 1559
ASSASSIN_MOC_END_HM: int = 1601

# 1주 독립 정찰병(Scout) 파라미터 (이동평균 및 물량 합병 100% 배제)
SCOUT_TAKE_PROFIT_PCT: float = 1.00
SCOUT_PULLBACK_RELOAD_PCT: float = -1.00
SCOUT_BREAKOUT_RELOAD_PCT: float = 1.00
SCOUT_BREAKOUT_MAX_RSI_50: float = 50.0
SCOUT_MAX_LAYERS_7: int = 7
SCOUT_TIME_SHIELD_SEC: float = 60.0

# 암살자 본대 익절 엔진: +5.00% 상단 안전 캡 선장전 & +1.00% 점화 이원화 하이킨 아시(HA) 트레일링
ASSASSIN_SAFE_CAP_PROFIT_PCT: float = 5.00
ASSASSIN_TRAIL_ARM_PROFIT_PCT: float = 1.00
ASSASSIN_PEAK_LOCK_BOOST_PCT: float = 1.30
ASSASSIN_CUSHION_FLOOR_PCT: float = 0.75
ASSASSIN_CALLBACK_TECH_REBOUND_PCT: float = 0.30
ASSASSIN_CALLBACK_TREND_PB_PCT: float = 0.20
ASSASSIN_QQQ_VEL_BYPASS_SURGE_PCT: float = 0.20

# 순수 롱(SOXL) 방향성 인지 나스닥 100 선물(NQ=F) / QQQ 3단계 안전망 v2 파라미터
# (안전망이 상승/지지 중일 때는 절대 손절 퇴근 금지 · 오직 08:15 이후 안전망 하락 진행 중일 때만 작동)
LEVERAGE_3X_FACTOR: float = 3.0
STAGE1_FREEFALL_BEAR_AMP_PCT: float = 3.00
STAGE1_FREEFALL_VEL_3M_PCT: float = -0.35
STAGE2_NQ_DROP_OVERHEAT_PCT: float = 2.00
STAGE3_MIN_QQQ_ADVERSE_PCT: float = 0.80
STAGE3_MAX_QQQ_ADVERSE_PCT: float = 1.00
STAGE3_MIN_HOLD_SEC: float = 900.0
STAGE3_ACCEL_VEL_3M_PCT: float = -0.25

ASSASSIN_BUY_MAX_WAIT_SEC: float = 60.0
ASSASSIN_POST_BUY_SHIELD_SEC: float = 60.0
ASSASSIN_SELLABLE_POLL_WAIT_SEC: float = 2.0
ASSASSIN_SELLABLE_POLL_INTERVAL_SEC: float = 0.25


def _esc(val: Any) -> str:
    return html.escape(str(val if val is not None else ""), quote=False)


def _fmt_signed_usd(val: float) -> str:
    v = safe_float(val, 0.0)
    sign = "+" if v >= 0.0 else "-"
    return f"{sign}${abs(v):,.2f}"


def _fmt_signed_pct(val: float) -> str:
    v = safe_float(val, 0.0)
    sign = "+" if v >= 0.0 else ""
    return f"{sign}{v:.2f}%"


def is_live_execution_enabled(st_assassin: Optional[Dict[str, Any]] = None) -> bool:
    """
    현재 암살자 엔진이 실전 주문(LIVE) 모드인지 판별한다.
    ASSASSIN_LIVE_ORDER_HARD_LOCK == True 인 동안에는 어떠한 경우에도 False 를 반환하여
    실전 주문 발사를 물리적으로 100% 차단한다.
    """
    if ASSASSIN_LIVE_ORDER_HARD_LOCK:
        return False
    if not isinstance(st_assassin, dict):
        return False
    mode_str = str(
        st_assassin.get("execution_mode") or ASSASSIN_MODE_SIMULATED
    ).upper().strip()
    return bool(mode_str == ASSASSIN_MODE_LIVE)


def resolve_assassin_ledger_paths(
    base_dir: Optional[str] = None,
) -> Tuple[str, str, str, str]:
    """
    폴더 위치(base_dir) 기준 [모의 ⇄ 실전] 암살자 전용 3중 안전 원장 경로를 반환한다.
    1) primary_path : <base_dir>/assassin_sim_ledger_<folder_slug>.json
    2) legacy_path  : <base_dir>/assassin_sim_ledger.json
    3) backup_path  : <base_dir>/ledger_backups/assassin_sim_ledger_<folder_slug>.bak.json
    4) folder_slug  : 폴더 식별자
    """
    target_dir = get_bot_base_dir(base_dir)
    folder_slug = get_folder_slug(target_dir)
    primary_path = os.path.join(
        target_dir, f"assassin_sim_ledger_{folder_slug}.json"
    )
    legacy_path = os.path.join(target_dir, "assassin_sim_ledger.json")
    backup_dir = os.path.join(target_dir, "ledger_backups")
    backup_path = os.path.join(
        backup_dir, f"assassin_sim_ledger_{folder_slug}.bak.json"
    )
    return primary_path, legacy_path, backup_path, folder_slug


# ---------------------------------------------------------------------------
# [핵심 1] 1주 독립 정찰병(Virtual Scout) 데이터 구조체 및 10대 진성 게이트 판정기
# ---------------------------------------------------------------------------
@dataclass
class IndependentScoutUnit:
    """
    이동평균(WMA)이나 합병 없이 1주씩 완전히 독립 운용되는 개별 정찰병 객체
    """

    scout_id: int
    seq_in_day: int
    buy_ts: float
    entry_hm: int
    entry_type: str
    stage_tag: str
    layer_no: int
    lot_seq: int
    entry_price: float
    target_1pct_price: float
    rsi14: float
    vwap_price: float
    prev_reg_close: float
    pre_open_price: float
    vs_vwap_pct: float
    vs_prev_close_pct: float
    vs_pre_open_pct: float
    vs_scout1_pct: float
    prior_wins_at_entry: int
    is_bull_bar: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scout_id": int(self.scout_id),
            "seq_in_day": int(self.seq_in_day),
            "buy_ts": round(float(self.buy_ts), 4),
            "entry_hm": int(self.entry_hm),
            "entry_type": str(self.entry_type),
            "stage_tag": str(self.stage_tag),
            "layer_no": int(self.layer_no),
            "lot_seq": int(self.lot_seq),
            "entry_price": round(float(self.entry_price), 4),
            "target_1pct_price": round(float(self.target_1pct_price), 2),
            "rsi14": round(float(self.rsi14), 2),
            "vwap_price": round(float(self.vwap_price), 4),
            "prev_reg_close": round(float(self.prev_reg_close), 4),
            "pre_open_price": round(float(self.pre_open_price), 4),
            "vs_vwap_pct": round(float(self.vs_vwap_pct), 2),
            "vs_prev_close_pct": round(float(self.vs_prev_close_pct), 2),
            "vs_pre_open_pct": round(float(self.vs_pre_open_pct), 2),
            "vs_scout1_pct": round(float(self.vs_scout1_pct), 2),
            "prior_wins_at_entry": int(self.prior_wins_at_entry),
            "is_bull_bar": bool(self.is_bull_bar),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> Optional["IndependentScoutUnit"]:
        if not isinstance(d, dict):
            return None
        ep = safe_float(d.get("entry_price"), 0.0)
        if ep <= 0.0:
            return None
        tp = safe_float(
            d.get("target_1pct_price"),
            round(math.ceil((ep * 1.01 - 1e-9) * 100.0) / 100.0, 2),
        )
        return cls(
            scout_id=max(1, safe_int(d.get("scout_id"), 1)),
            seq_in_day=max(1, safe_int(d.get("seq_in_day"), 1)),
            buy_ts=safe_float(d.get("buy_ts"), 0.0),
            entry_hm=safe_int(d.get("entry_hm"), 407),
            entry_type=str(d.get("entry_type") or "01_OPEN_0407"),
            stage_tag=str(d.get("stage_tag") or "OPEN_0407_L1"),
            layer_no=max(1, safe_int(d.get("layer_no"), 1)),
            lot_seq=max(1, safe_int(d.get("lot_seq"), 1)),
            entry_price=round(ep, 4),
            target_1pct_price=round(tp, 2),
            rsi14=round(safe_float(d.get("rsi14"), 50.0), 2),
            vwap_price=round(safe_float(d.get("vwap_price"), ep), 4),
            prev_reg_close=round(safe_float(d.get("prev_reg_close"), ep), 4),
            pre_open_price=round(safe_float(d.get("pre_open_price"), ep), 4),
            vs_vwap_pct=round(safe_float(d.get("vs_vwap_pct"), 0.0), 2),
            vs_prev_close_pct=round(
                safe_float(d.get("vs_prev_close_pct"), 0.0), 2
            ),
            vs_pre_open_pct=round(safe_float(d.get("vs_pre_open_pct"), 0.0), 2),
            vs_scout1_pct=round(safe_float(d.get("vs_scout1_pct"), 0.0), 2),
            prior_wins_at_entry=max(
                0, safe_int(d.get("prior_wins_at_entry"), 0)
            ),
            is_bull_bar=bool(d.get("is_bull_bar", True)),
        )


def resolve_scout_wide_drop_threshold(eff_lots: int) -> Tuple[float, str]:
    """
    정찰병 10분 게이트 4단계 와이드 단차 (1~4회 -1.0% / 5~8회 -2.0% / 9~10회 -3.5% / 11회+ -5.5%)
    """
    lots = max(1, safe_int(eff_lots, 1))
    if lots <= 4:
        return -1.00, "WIDE_S1_1.0P"
    if lots <= 8:
        return -2.00, "WIDE_S2_2.0P"
    if lots <= 10:
        return -3.50, "WIDE_S3_3.5P"
    return -5.50, "WIDE_S4_5.5P"


def evaluate_10_truth_gates_signal(
    rsi_val: float,
    vs_vwap_pct: float,
    vs_prev_close_pct: float,
    vs_pre_open_pct: float,
    vs_scout1_pct: float,
    prior_wins_today: int,
    is_bull_bar: bool,
) -> Tuple[bool, str, str, bool]:
    """
    5개년(2022 ~ 2026년 · 1,197영업일) 백테스트로 입증된 10대 진성 게이트 판정기
    - 헌법 고정 5대 진성 게이트 (Gate 1 ~ Gate 5)
    - 폭락·하락장 특화 5대 추가 진성 게이트 (BearGate 1 ~ BearGate 5)
    반환값: (격발여부, 게이트코드, 게이트설명, 추세형레짐여부)
    """
    rsi = safe_float(rsi_val, 50.0)
    vwap_d = safe_float(vs_vwap_pct, 0.0)
    prev_d = safe_float(vs_prev_close_pct, 0.0)
    preo_d = safe_float(vs_pre_open_pct, 0.0)
    sc1_d = safe_float(vs_scout1_pct, 0.0)
    pwins = max(0, safe_int(prior_wins_today, 0))
    bull = bool(is_bull_bar)

    # 🏛️ A. 헌법 고정 5대 진성 게이트 (Gate 1 ~ Gate 5)
    if rsi <= 30.0 and prev_d < 0.0 and preo_d <= -1.50:
        return (
            True,
            "G1",
            "Gate 1 (RSI<=30 & 전일종가<0% & 프리장시가<=-1.5%)",
            False,
        )
    if rsi <= 45.0 and vwap_d <= -2.00:
        return (
            True,
            "G2",
            "Gate 2 (RSI<=45 & VWAP괴리율<=-2.0%)",
            True,
        )
    if rsi <= 25.0 and vwap_d <= -1.00 and pwins >= 1:
        return (
            True,
            "G3",
            "Gate 3 (RSI<=25 & VWAP<=-1.0% & 당일정찰1승후)",
            True,
        )
    if rsi <= 32.0 and vwap_d <= -0.50 and prev_d <= -1.00 and bull:
        return (
            True,
            "G4",
            "Gate 4 (RSI<=32 & VWAP<=-0.5% & 전일<=-1.0% & 양봉)",
            True,
        )
    if rsi <= 20.0 and prev_d >= 0.00:
        return (
            True,
            "G5",
            "Gate 5 (RSI<=20 & 전일종가>=0.0% 극과매도)",
            False,
        )

    # 🌋 B. 폭락·하락장 특화 5대 추가 진성 게이트 (BearGate 1 ~ BearGate 5)
    if (
        30.0 <= rsi <= 45.0
        and vwap_d <= -1.00
        and prev_d <= -6.00
        and sc1_d <= -2.00
    ):
        return (
            True,
            "BG1",
            "BearGate 1 (30<=RSI<=45 & VWAP<=-1.0% & 전일<=-6.0% & 선봉<=-2.0%)",
            True,
        )
    if rsi <= 30.0 and vwap_d <= -1.00 and prev_d <= -3.00 and preo_d <= -1.00:
        return (
            True,
            "BG2",
            "BearGate 2 (RSI<=30 & VWAP<=-1.0% & 전일<=-3.0% & 프리시가<=-1.0%)",
            False,
        )
    if rsi <= 32.0 and preo_d <= -2.50:
        return (
            True,
            "BG3",
            "BearGate 3 (RSI<=32 & 프리장시가<=-2.50%)",
            True,
        )
    if rsi <= 25.0 and vwap_d <= -0.50 and bull:
        return (
            True,
            "BG4",
            "BearGate 4 (RSI<=25 & VWAP<=-0.50% & 1분봉양봉)",
            False,
        )
    if rsi <= 45.0 and vwap_d <= -1.50 and prev_d <= -4.00 and pwins >= 1:
        return (
            True,
            "BG5",
            "BearGate 5 (RSI<=45 & VWAP<=-1.50% & 전일<=-4.0% & 당일정찰1승후)",
            True,
        )

    return False, "", "", False


# ---------------------------------------------------------------------------
# [핵심 2] 암살자 전용 3중 안전 원장 클래스 (AssassinSimLedger)
# ---------------------------------------------------------------------------
class AssassinSimLedger:
    """
    스나이퍼 원장(SoxlStratumLedger)과 완전히 분리된 암살자 전용 3중 원장 금고.
    - Dirty-Check 적용으로 상태 변경 시에만 디스크 쓰기(os.fsync) 수행 (Case 75)
    - 장중 재기동/업데이트 시에도 당일 정찰병·본대 포지션·알림 래치·누적 전적을 100% 보존 (Case 68)
    """

    def __init__(self, base_dir: Optional[str] = None) -> None:
        self.base_dir: str = get_bot_base_dir(base_dir)
        (
            self.primary_filepath,
            self.legacy_filepath,
            self.backup_filepath,
            self.folder_slug,
        ) = resolve_assassin_ledger_paths(base_dir=self.base_dir)
        self.backup_dir: str = os.path.dirname(self.backup_filepath)
        self._mem_lock = threading.RLock()
        self._data: Dict[str, Any] = {}
        self._load_sync()

    @classmethod
    def _default_state(
        cls,
        folder_slug: str = "default_bot",
        initial_seed: float = DEFAULT_INITIAL_SEED_USD,
    ) -> Dict[str, Any]:
        today_est = datetime.now(EST_TZ).strftime("%Y-%m-%d")
        clean_seed = round(max(100.0, safe_float(initial_seed, 10000.0)), 4)
        return {
            "symbol": ASSASSIN_SYMBOL,
            "folder_slug": str(folder_slug or "default_bot"),
            "execution_mode": ASSASSIN_MODE_SIMULATED,
            "is_enabled": True,
            "initial_seed_usd": clean_seed,
            "us_commission_rate": DEFAULT_US_COMMISSION_RATE,
            "round_trip_fee_rate_pct": ROUND_TRIP_FEE_RATE_PCT,
            # 당일 날짜 및 세션 상태
            "logical_date": today_est,
            "session_status": "WAITING_0407",
            "is_session_done": False,
            # 1주 독립 정찰병(Scout) 당일 상태
            "active_scouts": [],
            "all_scouts_today": [],
            "has_active_scout_l1": False,
            "scout_anchor_price": 0.0,
            "scout_day_min_buy_price": 0.0,
            "scout_ratchet_max_lots": 0,
            "scout_last_eval_b10": -1,
            "scout_last_action_ts": 0.0,
            "scout_last_sell_ts": 0.0,
            "day_scout_seq": 0,
            "prior_scout_wins_today": 0,
            "first_0407_scout_price": 0.0,
            "first_0407_scout_rsi": 50.0,
            "pre_running_high": 0.0,
            "pre_running_low": 0.0,
            "min_rsi_today": 100.0,
            "min_vs_vwap_today": 0.0,
            # 암살자 본대 당일 진입/보유/출구 상태 (SIMULATED & LIVE 공용)
            "holding_active": False,
            "buy_order_id": "",
            "sell_order_id": "",
            "client_order_id": "",
            "gate_code": "",
            "gate_desc": "",
            "is_trend_regime": False,
            "entry_hm": 0,
            "entry_ts": 0.0,
            "signal_price": 0.0,
            "entry_price": 0.0,
            "entry_rsi": 50.0,
            "entry_vs_vwap_pct": 0.0,
            "entry_vs_prev_close_pct": 0.0,
            "entry_vs_pre_open_pct": 0.0,
            "simple_held_qty": 0,
            "simple_invested_usd": 0.0,
            "comp_held_qty": 0,
            "comp_invested_usd": 0.0,
            "cap_500_price": 0.0,
            "arm_100_price": 0.0,
            "lock_130_price": 0.0,
            "cushion_075_price": 0.0,
            "trail_armed": False,
            "trail_armed_hm": 0,
            "peak_price": 0.0,
            "bear_candle_seen": False,
            "qqq_entry_price": 0.0,
            "nq_entry_bear_amp": 0.0,
            "dyn_qqq_thr_pct": STAGE3_MIN_QQQ_ADVERSE_PCT,
            "post_entry_min_price": 0.0,
            # 당일 청산 결과 요약
            "exit_hm": 0,
            "exit_price": 0.0,
            "exit_type": "",
            "hold_mins": 0,
            "today_net_rate_pct": 0.0,
            "today_simple_net_usd": 0.0,
            "today_comp_net_usd": 0.0,
            # 5대 알림 중복 방지 영구 래치
            "last_scout_alert_seq": 0,
            "no_trade_alert_sent_date": "",
            "entry_alert_sent_date": "",
            "trail_armed_alert_sent_date": "",
            "exit_alert_sent_date": "",
            # 누적 통계 (5개년 백테스트 동일 기준 단리 & 연속복리 동시 추적)
            "total_trade_days": 0,
            "total_no_trade_days": 0,
            "win_days": 0,
            "loss_days": 0,
            "pre_exit_days": 0,
            "cap5_homerun_cnt": 0,
            "ha_boost_win_cnt": 0,
            "ha_floor_1pct_cnt": 0,
            "vwap_escape_cnt": 0,
            "stage_stop_cnt": 0,
            "moc_exit_cnt": 0,
            "total_scouts_dispatched": 0,
            "total_scout_wins": 0,
            "cum_simple_gross_usd": 0.0,
            "cum_simple_fee_usd": 0.0,
            "cum_simple_net_usd": 0.0,
            "cum_comp_gross_usd": 0.0,
            "cum_comp_fee_usd": 0.0,
            "cum_comp_net_usd": 0.0,
            "comp_equity_usd": clean_seed,
            "recent_history": [],
            "updated_at": datetime.now(EST_TZ).isoformat(),
        }

    def _sanitize_state(self, raw_st: Dict[str, Any]) -> Dict[str, Any]:
        st = self._default_state(folder_slug=self.folder_slug)
        if isinstance(raw_st, dict):
            st.update(raw_st)

        st["symbol"] = ASSASSIN_SYMBOL
        st["folder_slug"] = self.folder_slug
        if ASSASSIN_LIVE_ORDER_HARD_LOCK:
            st["execution_mode"] = ASSASSIN_MODE_SIMULATED
        else:
            mode_raw = (
                str(st.get("execution_mode") or ASSASSIN_MODE_SIMULATED)
                .upper()
                .strip()
            )
            st["execution_mode"] = (
                ASSASSIN_MODE_LIVE
                if mode_raw == ASSASSIN_MODE_LIVE
                else ASSASSIN_MODE_SIMULATED
            )

        init_s = round(
            max(100.0, safe_float(st.get("initial_seed_usd"), 10000.0)), 4
        )
        st["initial_seed_usd"] = init_s
        cum_comp_net = round(safe_float(st.get("cum_comp_net_usd"), 0.0), 4)
        st["cum_comp_net_usd"] = cum_comp_net
        st["comp_equity_usd"] = round(max(100.0, init_s + cum_comp_net), 4)
        st["cum_simple_net_usd"] = round(
            safe_float(st.get("cum_simple_net_usd"), 0.0), 4
        )

        if not isinstance(st.get("active_scouts"), list):
            st["active_scouts"] = []
        if not isinstance(st.get("all_scouts_today"), list):
            st["all_scouts_today"] = []
        if not isinstance(st.get("recent_history"), list):
            st["recent_history"] = []
        else:
            st["recent_history"] = st["recent_history"][-30:]

        st["updated_at"] = datetime.now(EST_TZ).isoformat()
        return st

    @staticmethod
    def _is_materially_equal(
        a: Optional[Dict[str, Any]], b: Optional[Dict[str, Any]]
    ) -> bool:
        if not isinstance(a, dict) or not isinstance(b, dict):
            return False
        ca = {k: v for k, v in a.items() if k != "updated_at"}
        cb = {k: v for k, v in b.items() if k != "updated_at"}
        return ca == cb

    @classmethod
    def _atomic_write_sync(
        cls, target_path: str, payload: Dict[str, Any]
    ) -> bool:
        if not target_path:
            return False
        if os.path.isfile(target_path):
            try:
                with open(target_path, "r", encoding="utf-8") as rf:
                    old_d = json.load(rf)
                old_inner = (
                    old_d.get("ASSASSIN")
                    if isinstance(old_d, dict) and "ASSASSIN" in old_d
                    else old_d
                )
                new_inner = (
                    payload.get("ASSASSIN")
                    if isinstance(payload, dict) and "ASSASSIN" in payload
                    else payload
                )
                if cls._is_materially_equal(old_inner, new_inner):
                    return False
            except Exception:
                pass

        parent_d = os.path.dirname(os.path.abspath(target_path))
        base_search_d = (
            os.path.dirname(parent_d)
            if os.path.basename(parent_d) == "ledger_backups"
            else parent_d
        )

        for attempt in range(2):
            if parent_d and not os.path.isdir(parent_d):
                try:
                    os.makedirs(parent_d, exist_ok=True)
                except OSError as os_err:
                    if os_err.errno == errno.ENOSPC and attempt == 0:
                        emergency_free_disk_space_sync(
                            base_dir=base_search_d,
                            keep_backup_days=3,
                            remove_pycache=True,
                        )
                        continue
                    return False

            tmp_p = f"{target_path}.tmp.{os.getpid()}.{threading.get_ident()}"
            try:
                with open(tmp_p, "w", encoding="utf-8") as wf:
                    json.dump(payload, wf, ensure_ascii=False, indent=2)
                    wf.flush()
                    os.fsync(wf.fileno())
                os.replace(tmp_p, target_path)
                return True
            except OSError as os_err:
                try:
                    if os.path.exists(tmp_p):
                        os.remove(tmp_p)
                except Exception:
                    pass
                if os_err.errno == errno.ENOSPC and attempt == 0:
                    emergency_free_disk_space_sync(
                        base_dir=base_search_d,
                        keep_backup_days=3,
                        remove_pycache=True,
                    )
                    continue
                return False
            except Exception:
                try:
                    if os.path.exists(tmp_p):
                        os.remove(tmp_p)
                except Exception:
                    pass
                return False
        return False

    def _load_sync(self) -> None:
        with GlobalThrottle.get_file_lock(self.primary_filepath):
            with self._mem_lock:
                loaded_raw: Dict[str, Any] = {}
                for fp in (
                    self.primary_filepath,
                    self.backup_filepath,
                    self.legacy_filepath,
                ):
                    if fp and os.path.isfile(fp):
                        try:
                            with open(fp, "r", encoding="utf-8") as rf:
                                d = json.load(rf)
                            if isinstance(d, dict):
                                loaded_raw = (
                                    d["ASSASSIN"]
                                    if isinstance(d.get("ASSASSIN"), dict)
                                    else d
                                )
                                break
                        except Exception:
                            pass

                self._data = self._sanitize_state(loaded_raw)
                self._save_sync_unlocked()

    def _save_sync_unlocked(self) -> None:
        payload = {"ASSASSIN": self._data}
        self._atomic_write_sync(self.primary_filepath, payload)
        if os.path.abspath(self.legacy_filepath) != os.path.abspath(
            self.primary_filepath
        ):
            self._atomic_write_sync(self.legacy_filepath, payload)
        self._atomic_write_sync(self.backup_filepath, payload)

    def get_state(self) -> Dict[str, Any]:
        with self._mem_lock:
            return json.loads(json.dumps(self._data))

    def update_state_sync(self, **kwargs: Any) -> Dict[str, Any]:
        with GlobalThrottle.get_file_lock(self.primary_filepath):
            with self._mem_lock:
                prev_st = dict(self._data)
                cur = dict(prev_st)
                cur.update(kwargs)
                sanitized = self._sanitize_state(cur)
                if not self._is_materially_equal(prev_st, sanitized):
                    self._data = sanitized
                    self._save_sync_unlocked()
                else:
                    self._data = sanitized
                return json.loads(json.dumps(self._data))

    async def update_state(self, **kwargs: Any) -> Dict[str, Any]:
        return await asyncio.to_thread(self.update_state_sync, **kwargs)

    async def rollover_daily_session_if_needed(
        self,
        logical_date: str,
        sniper_seed_usd: float = DEFAULT_INITIAL_SEED_USD,
        us_commission_rate: float = DEFAULT_US_COMMISSION_RATE,
        round_trip_fee_rate_pct: float = ROUND_TRIP_FEE_RATE_PCT,
    ) -> Dict[str, Any]:
        st = self.get_state()
        cur_d = str(st.get("logical_date") or "")
        clean_seed = round(max(100.0, safe_float(sniper_seed_usd, 10000.0)), 4)
        if cur_d == str(logical_date):
            if abs(safe_float(st.get("initial_seed_usd"), 0.0) - clean_seed) > 0.01:
                return await self.update_state(
                    initial_seed_usd=clean_seed,
                    us_commission_rate=us_commission_rate,
                    round_trip_fee_rate_pct=round_trip_fee_rate_pct,
                )
            return st

        return await self.update_state(
            logical_date=str(logical_date),
            initial_seed_usd=clean_seed,
            us_commission_rate=us_commission_rate,
            round_trip_fee_rate_pct=round_trip_fee_rate_pct,
            session_status="WAITING_0407",
            is_session_done=False,
            active_scouts=[],
            all_scouts_today=[],
            has_active_scout_l1=False,
            scout_anchor_price=0.0,
            scout_day_min_buy_price=0.0,
            scout_ratchet_max_lots=0,
            scout_last_eval_b10=-1,
            scout_last_action_ts=0.0,
            scout_last_sell_ts=0.0,
            day_scout_seq=0,
            prior_scout_wins_today=0,
            first_0407_scout_price=0.0,
            first_0407_scout_rsi=50.0,
            pre_running_high=0.0,
            pre_running_low=0.0,
            min_rsi_today=100.0,
            min_vs_vwap_today=0.0,
            holding_active=False,
            buy_order_id="",
            sell_order_id="",
            client_order_id="",
            gate_code="",
            gate_desc="",
            is_trend_regime=False,
            entry_hm=0,
            entry_ts=0.0,
            signal_price=0.0,
            entry_price=0.0,
            entry_rsi=50.0,
            entry_vs_vwap_pct=0.0,
            entry_vs_prev_close_pct=0.0,
            entry_vs_pre_open_pct=0.0,
            simple_held_qty=0,
            simple_invested_usd=0.0,
            comp_held_qty=0,
            comp_invested_usd=0.0,
            cap_500_price=0.0,
            arm_100_price=0.0,
            lock_130_price=0.0,
            cushion_075_price=0.0,
            trail_armed=False,
            trail_armed_hm=0,
            peak_price=0.0,
            bear_candle_seen=False,
            qqq_entry_price=0.0,
            nq_entry_bear_amp=0.0,
            dyn_qqq_thr_pct=STAGE3_MIN_QQQ_ADVERSE_PCT,
            post_entry_min_price=0.0,
            exit_hm=0,
            exit_price=0.0,
            exit_type="",
            hold_mins=0,
            today_net_rate_pct=0.0,
            today_simple_net_usd=0.0,
            today_comp_net_usd=0.0,
            last_scout_alert_seq=0,
            no_trade_alert_sent_date="",
            entry_alert_sent_date="",
            trail_armed_alert_sent_date="",
            exit_alert_sent_date="",
        )

    async def reset_assassin_stats_only(
        self, sniper_seed_usd: float = DEFAULT_INITIAL_SEED_USD
    ) -> Dict[str, Any]:
        clean_seed = round(max(100.0, safe_float(sniper_seed_usd, 10000.0)), 4)
        return await self.update_state(
            initial_seed_usd=clean_seed,
            total_trade_days=0,
            total_no_trade_days=0,
            win_days=0,
            loss_days=0,
            pre_exit_days=0,
            cap5_homerun_cnt=0,
            ha_boost_win_cnt=0,
            ha_floor_1pct_cnt=0,
            vwap_escape_cnt=0,
            stage_stop_cnt=0,
            moc_exit_cnt=0,
            total_scouts_dispatched=0,
            total_scout_wins=0,
            cum_simple_gross_usd=0.0,
            cum_simple_fee_usd=0.0,
            cum_simple_net_usd=0.0,
            cum_comp_gross_usd=0.0,
            cum_comp_fee_usd=0.0,
            cum_comp_net_usd=0.0,
            comp_equity_usd=clean_seed,
            recent_history=[],
        )


def ensure_assassin_ledger(context: Any) -> AssassinSimLedger:
    """
    context 에 assassin_ledger 인스턴스가 없으면 자동 생성하여 부착한다.
    """
    existing = getattr(context, "assassin_ledger", None)
    if isinstance(existing, AssassinSimLedger):
        return existing
    base_d = getattr(context, "base_dir", None)
    ledger_obj = AssassinSimLedger(base_dir=base_d)
    try:
        setattr(context, "assassin_ledger", ledger_obj)
    except Exception:
        pass
    return ledger_obj
# -*- coding: utf-8 -*-
"""
# NEW: assassin_plugin.py (Part 2/2)
인피니트 스노우볼 (Infinite Snowball) v3.0 — 🗡️ [모의 ⇄ 실전 Dual-Ready] 암살자(Assassin) 독립 플러그인 코어 모듈
- 실시간 4대 지표 & QQQ 방향성 안전망 스냅샷 추출기
- Dual-Ready 주문 어댑터 (현재 SIMULATED 물리적 잠금 / 향후 LIVE 즉시 탈바꿈)
- 5대 라이프사이클 실시간 텔레그램 알림 발송기 (정찰병 / 무매매퇴근 / 진성포착 / +1%추적점화 / 익절퇴근)
- 상시 가동 메인 틱 엔진 (execute_simulated_assassin_tick_plugin) 및 관제 UI 포매터 (/avwap · /settlement · /assassin)
"""


# ---------------------------------------------------------------------------
# [핵심 3] 실시간 4대 지표(RSI · VWAP · 전일종가 · 프리장시가) & QQQ 안전망 스냅샷 추출기
# ---------------------------------------------------------------------------
async def _extract_live_assassin_features_and_qqq_snapshot(
    context: Any,
    live_price: float,
    now_est: datetime,
) -> Dict[str, Any]:
    """
    context.candle_metrics_cache["SOXL"] 및 ["QQQ"] 와 실시간 현재가(live_price)를 결합하여
    1) 정찰병 & 진성 게이트 4대 필수 지표 (rsi14, pre_vwap, prev_reg_close, pre_open_price)
    2) 정규장 누적 VWAP (reg_vwap) 및 실시간 1분봉/하이킨아시 양봉 여부 (is_bull_bar, is_ha_bull)
    3) 나스닥(QQQ) 방향성 인지 3단계 안전망 지표 (qqq_live_price, qqq_vel_1m, qqq_vel_3m, qqq_vel_max, nq_bear_drop_amp)
    를 O(1) 상수 시간에 산출하여 반환한다 (캐시 미워밍 시 온디맨드 1분봉 프리워밍 수행).
    """
    p_now = safe_float(live_price, 0.0)
    cache_dict = getattr(context, "candle_metrics_cache", None)
    if not isinstance(cache_dict, dict):
        cache_dict = {}

    soxl_m = cache_dict.get(ASSASSIN_SYMBOL)
    if not isinstance(soxl_m, dict) or safe_float(
        soxl_m.get("prev_bar_close"), 0.0
    ) <= 0.0:
        api = getattr(context, "api", None)
        if api is not None and hasattr(api, "get_candles_1m"):
            try:
                from quant_indicators_plugin import (
                    compute_1m_indicators_vectorized,
                )

                candles_1m = await api.get_candles_1m(
                    symbol=ASSASSIN_SYMBOL, count=200, total_count=400
                )
                if candles_1m:
                    prev_d_c = 0.0
                    if isinstance(soxl_m, dict):
                        prev_d_c = safe_float(
                            soxl_m.get("prev_day_close"), 0.0
                        )
                    soxl_m = await asyncio.to_thread(
                        compute_1m_indicators_vectorized,
                        candles_1m,
                        prev_d_c,
                    )
                    cache_dict[ASSASSIN_SYMBOL] = soxl_m
            except Exception as exc:
                logger.debug(f"⚠️ [Assassin] SOXL 1m 온디맨드 프리워밍 예외: {exc}")

    if isinstance(soxl_m, dict) and p_now > 0.0:
        refreshed = refresh_metrics_with_live_tick(soxl_m, p_now)
    else:
        refreshed = soxl_m if isinstance(soxl_m, dict) else {}

    rsi14 = round(safe_float(refreshed.get("rsi"), 50.0), 2)
    pre_vwap = safe_float(
        refreshed.get("premarket_vwap"),
        safe_float(refreshed.get("vwap"), p_now),
    )
    if pre_vwap <= 0.0:
        pre_vwap = p_now

    reg_vwap = safe_float(
        refreshed.get("regular_vwap"),
        safe_float(refreshed.get("vwap"), p_now),
    )
    if reg_vwap <= 0.0:
        reg_vwap = p_now

    prev_reg_close = safe_float(
        refreshed.get("prev_reg_close"),
        safe_float(refreshed.get("prev_day_close"), p_now),
    )
    if prev_reg_close <= 0.0:
        prev_reg_close = p_now

    pre_open_price = safe_float(refreshed.get("pre_open_price"), p_now)
    if pre_open_price <= 0.0:
        pre_open_price = p_now

    cur_bar_open = safe_float(refreshed.get("cur_bar_open"), p_now)
    if cur_bar_open <= 0.0:
        cur_bar_open = p_now
    is_bull_bar = bool(p_now >= cur_bar_open - 1e-9)

    # 실시간 하이킨 아시(Heikin-Ashi) 합성
    prev_ha_open = safe_float(refreshed.get("prev_ha_open"), cur_bar_open)
    prev_ha_close = safe_float(refreshed.get("prev_ha_close"), cur_bar_open)
    cur_bar_high = max(p_now, safe_float(refreshed.get("cur_bar_high"), p_now))
    cur_bar_low = min(
        p_now,
        safe_float(refreshed.get("cur_bar_low"), p_now)
        if safe_float(refreshed.get("cur_bar_low"), 0.0) > 0.0
        else p_now,
    )
    ha_open = 0.5 * (prev_ha_open + prev_ha_close)
    ha_close = 0.25 * (cur_bar_open + cur_bar_high + cur_bar_low + p_now)
    is_ha_bull = bool(ha_close > ha_open)

    # QQQ 스냅샷 추출 (캐시 존재 시 우선 활용, 부재 시 SOXL 1/3 레버리지 환산 폴백)
    qqq_m = cache_dict.get(MACRO_REF_SYMBOL)
    if isinstance(qqq_m, dict) and safe_float(qqq_m.get("current_price"), 0.0) > 0.0:
        qqq_live_p = safe_float(qqq_m.get("current_price"), 0.0)
        qqq_vel_1m = safe_float(qqq_m.get("vel_1m_pct"), 0.0)
        qqq_vel_3m = safe_float(qqq_m.get("vel_3m_pct"), 0.0)
        qqq_vel_max = safe_float(qqq_m.get("vel_max_3m_10m_pct"), 0.0)
        nq_bear_drop_amp = safe_float(qqq_m.get("bear_drop_amp_pct"), 0.0)
    else:
        # SOXL 3배율 수익률의 1/3 로 QQQ 등가 속도 및 하락 진폭 정밀 환산 폴백
        soxl_vel_1m = safe_float(refreshed.get("vel_1m_pct"), 0.0)
        soxl_vel_3m = safe_float(refreshed.get("vel_3m_pct"), 0.0)
        soxl_vel_10m = safe_float(refreshed.get("vel_10m_pct"), 0.0)
        qqq_vel_1m = round(soxl_vel_1m / LEVERAGE_3X_FACTOR, 4)
        qqq_vel_3m = round(soxl_vel_3m / LEVERAGE_3X_FACTOR, 4)
        qqq_vel_max = round(
            max(soxl_vel_3m, soxl_vel_10m) / LEVERAGE_3X_FACTOR, 4
        )
        soxl_drop_from_open = (
            max(0.0, ((pre_open_price - p_now) / pre_open_price) * 100.0)
            if pre_open_price > 0.0
            else 0.0
        )
        nq_bear_drop_amp = round(soxl_drop_from_open / LEVERAGE_3X_FACTOR, 4)
        soxl_rel_ret = (
            (p_now - pre_open_price) / pre_open_price
            if pre_open_price > 0.0
            else 0.0
        )
        qqq_live_p = round(
            max(1.0, 100.0 * (1.0 + (soxl_rel_ret / LEVERAGE_3X_FACTOR))), 4
        )

    vs_vwap_pct = (
        round(((p_now - pre_vwap) / pre_vwap) * 100.0, 3)
        if pre_vwap > 0.0
        else 0.0
    )
    vs_prev_close_pct = (
        round(((p_now - prev_reg_close) / prev_reg_close) * 100.0, 3)
        if prev_reg_close > 0.0
        else 0.0
    )
    vs_pre_open_pct = (
        round(((p_now - pre_open_price) / pre_open_price) * 100.0, 3)
        if pre_open_price > 0.0
        else 0.0
    )

    return {
        "live_price": round(p_now, 4),
        "rsi14": rsi14,
        "pre_vwap": round(pre_vwap, 4),
        "reg_vwap": round(reg_vwap, 4),
        "prev_reg_close": round(prev_reg_close, 4),
        "pre_open_price": round(pre_open_price, 4),
        "vs_vwap_pct": vs_vwap_pct,
        "vs_prev_close_pct": vs_prev_close_pct,
        "vs_pre_open_pct": vs_pre_open_pct,
        "cur_bar_open": round(cur_bar_open, 4),
        "is_bull_bar": is_bull_bar,
        "ha_open": round(ha_open, 4),
        "ha_close": round(ha_close, 4),
        "is_ha_bull": is_ha_bull,
        "qqq_live_price": round(qqq_live_p, 4),
        "qqq_vel_1m": round(qqq_vel_1m, 4),
        "qqq_vel_3m": round(qqq_vel_3m, 4),
        "qqq_vel_max": round(qqq_vel_max, 4),
        "nq_bear_drop_amp": round(nq_bear_drop_amp, 4),
    }


# ---------------------------------------------------------------------------
# [핵심 4] Dual-Ready 주문 어댑터 (SIMULATED 물리적 잠금 ⇄ LIVE 실전 주문 즉시 전환)
# ---------------------------------------------------------------------------
async def _dispatch_assassin_buy_order(
    context: Any,
    st_assassin: Dict[str, Any],
    order_price: float,
    order_qty: int,
) -> Tuple[bool, str, float, int]:
    """
    [Dual-Ready 매수 발주 어댑터]
    - 현재(SIMULATED): 실계좌 API 호출 없이 가상 주문 ID(SIM-ASSN-BUY-...)와 즉시 체결 결과를 반환한다.
    - 향후(LIVE): POST /api/v1/orders (LIMIT 매수) 실발주 후 체결 확인 결과를 반환한다.
    """
    clean_p = round(max(0.01, safe_float(order_price, 0.0)), 2)
    clean_q = max(1, safe_int(order_qty, 1))

    if not is_live_execution_enabled(st_assassin):
        sim_oid = f"SIM-ASSN-BUY-{int(time.time() * 1000)}"
        return True, sim_oid, clean_p, clean_q

    api = getattr(context, "api", None)
    if api is None:
        return False, "", 0.0, 0

    cid = generate_client_order_id("assn-buy")
    resp = await api.create_order(
        symbol=ASSASSIN_SYMBOL,
        side="BUY",
        quantity=clean_q,
        price=clean_p,
        order_type="LIMIT",
        client_order_id=cid,
        enforce_daymarket_block=True,
    )
    oid = str(resp.get("orderId") or "").strip() if isinstance(resp, dict) else ""
    if not oid:
        return False, "", 0.0, 0
    return True, oid, clean_p, clean_q


async def _dispatch_assassin_safe_cap_sell_order(
    context: Any,
    st_assassin: Dict[str, Any],
    cap_500_price: float,
    held_qty: int,
) -> str:
    """
    [Dual-Ready +5.00% 상단 안전 캡 지정가 매도 선장전 어댑터]
    - 현재(SIMULATED): 가상 매도 주문 ID(SIM-ASSN-CAP5-...)를 즉시 생성하여 원장에 장전한다.
    - 향후(LIVE): 매수 체결 직후 거래소에 +5.00% LIMIT 매도 주문을 선장전하여 sell_order_id 를 확보한다.
    """
    clean_cap_p = round(max(0.01, safe_float(cap_500_price, 0.0)), 2)
    clean_q = max(1, safe_int(held_qty, 1))

    if not is_live_execution_enabled(st_assassin):
        return f"SIM-ASSN-CAP5-{int(time.time() * 1000)}"

    api = getattr(context, "api", None)
    if api is None:
        return ""

    cid = generate_client_order_id("assn-cap5")
    resp = await api.create_order(
        symbol=ASSASSIN_SYMBOL,
        side="SELL",
        quantity=clean_q,
        price=clean_cap_p,
        order_type="LIMIT",
        client_order_id=cid,
        enforce_daymarket_block=False,
    )
    return (
        str(resp.get("orderId") or "").strip() if isinstance(resp, dict) else ""
    )


async def _dispatch_assassin_exit_sweep_order(
    context: Any,
    st_assassin: Dict[str, Any],
    target_exit_price: float,
    held_qty: int,
    is_moc_1559: bool = False,
) -> Tuple[bool, float, str]:
    """
    [Dual-Ready 익절/안전망/MOC 즉시 청산 스윕 어댑터]
    - 현재(SIMULATED): 실계좌 API 호출 없이 target_exit_price 로 즉시 모의 체결 완료 처리한다.
    - 향후(LIVE):
      1) 기존 선장전된 +5.00% sell_order_id 가 존재할 때:
         • 일반 트레일링/안전망 스윕: POST /api/v1/orders/{orderId}/modify (quantity 미포함)로
           기존 매도 주문 가격을 target_exit_price 로 0.1초 만에 즉시 끌어내려 체결시킨다.
         • 15:59 ~ 16:01 방탄 MOC: 1단계 선취소(cancel_order, {}) + 최대 2.0초 sellableQuantity 폴링 후
           신규 LIMIT 발사 / 만약 수량 잠김 시 2단계 modify_order 직접 정정으로 100% 무오버나이트 청산한다.
    """
    clean_p = round(max(0.01, safe_float(target_exit_price, 0.0)), 2)
    clean_q = max(1, safe_int(held_qty, 1))
    cur_sell_oid = str(st_assassin.get("sell_order_id") or "").strip()

    if not is_live_execution_enabled(st_assassin):
        sim_oid = f"SIM-ASSN-EXIT-{int(time.time() * 1000)}"
        return True, clean_p, sim_oid

    api = getattr(context, "api", None)
    if api is None:
        return False, clean_p, cur_sell_oid

    # [LIVE] 1단계: 기존 sell_order_id 가 존재하고 일반 스윕일 때 modify_order 우선 타격
    if cur_sell_oid and not is_moc_1559:
        try:
            mod_res = await api.modify_order(
                order_id=cur_sell_oid,
                price=clean_p,
                order_type="LIMIT",
                is_us_market=True,
            )
            new_oid = (
                str(mod_res.get("orderId") or cur_sell_oid).strip()
                if isinstance(mod_res, dict)
                else cur_sell_oid
            )
            return True, clean_p, new_oid
        except Exception as exc:
            logger.warning(f"⚠️ [Assassin LIVE] modify_order 폴백 전환: {exc}")

    # [LIVE] 2단계 (또는 15:59 방탄 MOC): 선취소 후 sellableQuantity 폴링 & 신규 LIMIT 발주 (잠김 시 modify 폴백)
    if cur_sell_oid:
        try:
            await api.cancel_order(cur_sell_oid)
        except Exception:
            pass

    sellable_q = 0
    t_wait_end = time.monotonic() + ASSASSIN_SELLABLE_POLL_WAIT_SEC
    while time.monotonic() < t_wait_end:
        sellable_q = safe_int(
            await api.get_sellable_quantity(ASSASSIN_SYMBOL), 0
        )
        if sellable_q >= clean_q:
            break
        await asyncio.sleep(ASSASSIN_SELLABLE_POLL_INTERVAL_SEC)

    if sellable_q > 0:
        cid = generate_client_order_id("assn-exit")
        resp = await api.create_order(
            symbol=ASSASSIN_SYMBOL,
            side="SELL",
            quantity=min(clean_q, sellable_q),
            price=clean_p,
            order_type="LIMIT",
            client_order_id=cid,
            enforce_daymarket_block=False,
        )
        oid = (
            str(resp.get("orderId") or "").strip()
            if isinstance(resp, dict)
            else ""
        )
        if oid:
            return True, clean_p, oid

    if cur_sell_oid:
        try:
            mod_res = await api.modify_order(
                order_id=cur_sell_oid,
                price=clean_p,
                order_type="LIMIT",
                is_us_market=True,
            )
            new_oid = (
                str(mod_res.get("orderId") or cur_sell_oid).strip()
                if isinstance(mod_res, dict)
                else cur_sell_oid
            )
            return True, clean_p, new_oid
        except Exception:
            pass

    return False, clean_p, cur_sell_oid


# ---------------------------------------------------------------------------
# [핵심 5] [모의] 암살자 5대 라이프사이클 실시간 텔레그램 푸시 알림 발송기
# ---------------------------------------------------------------------------
async def _send_assassin_tg_alert(context: Any, html_msg: str) -> None:
    """
    context.tg.send_slim_alert (또는 send_message) 를 통해 텔레그램 알림을 안전하게 타전한다.
    """
    tg = getattr(context, "tg", None)
    if tg is None:
        return
    try:
        if hasattr(tg, "send_slim_alert"):
            await tg.send_slim_alert(html_msg)
        elif hasattr(tg, "send_message"):
            await tg.send_message(html_msg)
    except Exception as exc:
        logger.debug(f"⚠️ [Assassin TG Alert] 발송 예외: {exc}")


async def _send_1_scout_dispatched_alert(
    context: Any,
    st: Dict[str, Any],
    scout: IndependentScoutUnit,
    newly_won_scouts_cnt: int,
    gate_matched: bool,
    gate_desc: str,
) -> None:
    """
    [알림 1️⃣] 🕵️ 정찰병 파견 시 실시간 알림 (04:07 선봉 #1 및 후속 #2, #3...)
    """
    mode_tag = (
        "🚀[실전]" if is_live_execution_enabled(st) else "🧪[모의]"
    )
    type_kor_map = {
        "01_OPEN_0407": "04:07 첫 선봉 정찰",
        "02_PULL_1PCT_NOFILT": "익절후 -1.0% 눌림정찰",
        "03_BRK_1PCT_RSI50": "익절후 +1.0% 돌파정찰(RSI<=50)",
        "04_WIDE_GRID_DIP": f"10분 와이드 추매({scout.stage_tag})",
    }
    t_kor = type_kor_map.get(scout.entry_type, scout.entry_type)
    win_note = (
        f" (직전 정찰 +{newly_won_scouts_cnt}승 달성!)"
        if newly_won_scouts_cnt > 0
        else ""
    )
    if scout.seq_in_day == 1:
        gate_line = "⏳ 1번 선봉 정찰(기준점 기록) ➔ 2번째 정찰부터 진성 게이트 10 감시"
    elif gate_matched:
        gate_line = f"🚨 <b>진성 게이트 격발! [{_esc(gate_desc)}]</b>"
    else:
        gate_line = "🛡️ 진성 게이트 10 조건 미충족 (정찰 관측 유지)"

    bull_str = "📈양봉" if scout.is_bull_bar else "📉음봉"
    lines = [
        f"🕵️ <b>{mode_tag} 암살자 정찰병 #{scout.seq_in_day} 파견{win_note}</b>",
        f"▫️ 시각/유형: <code>{scout.entry_hm:04d} EST</code> · {_esc(t_kor)} (보유 {scout.layer_no}층/선행 {scout.prior_wins_at_entry}승)",
        f"🎯 정찰단가: <b>${scout.entry_price:.2f}</b> (1주 독립) ➔ +1%목표 <b>${scout.target_1pct_price:.2f}</b>",
        f"📊 <b>[4대 기록 지표 실측]</b> ({bull_str})",
        f" ① RSI(14): <b>{scout.rsi14:.1f}</b> | ② VWAP: <b>${scout.vwap_price:.2f}</b> (<code>{_fmt_signed_pct(scout.vs_vwap_pct)}</code>)",
        f" ③ 전일종가: <b>${scout.prev_reg_close:.2f}</b> (<code>{_fmt_signed_pct(scout.vs_prev_close_pct)}</code>) | ④ 프리시가: <b>${scout.pre_open_price:.2f}</b> (<code>{_fmt_signed_pct(scout.vs_pre_open_pct)}</code>)",
        f"🧭 판정: {gate_line}",
    ]
    await _send_assassin_tg_alert(context, "\n".join(lines))


async def _send_2_no_trade_retirement_alert(
    context: Any,
    st: Dict[str, Any],
) -> None:
    """
    [알림 2️⃣] 🏠 08:15:00 EST 무매매 퇴근 알림 (진성 게이트 10 미발생 시 시드 100% 보존 퇴근)
    """
    mode_tag = (
        "🚀[실전]" if is_live_execution_enabled(st) else "🧪[모의]"
    )
    sc_cnt = safe_int(st.get("day_scout_seq"), 0)
    sc_wins = safe_int(st.get("prior_scout_wins_today"), 0)
    min_rsi = safe_float(st.get("min_rsi_today"), 50.0)
    min_vwap_d = safe_float(st.get("min_vs_vwap_today"), 0.0)
    tot_tr = safe_int(st.get("total_trade_days"), 0)
    w_d = safe_int(st.get("win_days"), 0)
    l_d = safe_int(st.get("loss_days"), 0)
    w_rate = (float(w_d) / float(max(1, tot_tr))) * 100.0 if tot_tr > 0 else 100.0
    cum_s = safe_float(st.get("cum_simple_net_usd"), 0.0)
    cum_c = safe_float(st.get("cum_comp_net_usd"), 0.0)

    lines = [
        f"🏠 <b>{mode_tag} 암살자 08:15 EST 무매매 안전 퇴근</b>",
        f"▫️ 골든타임(04:07 ~ 08:14) 정찰: 총 <b>{sc_cnt}명</b> 파견 (정찰 +1% 익절 <b>{sc_wins}회</b>)",
        f"▫️ 당일 최저지표: 최저 RSI <b>{min_rsi:.1f}</b> · 최대 VWAP괴리 <code>{_fmt_signed_pct(min_vwap_d)}</code>",
        "🛡️ <b>진성 게이트 10 조건 미도달로 시드 100% 보존 · 금일 무매매 퇴근 완료!</b>",
        f"🏆 누적전적: <b>{tot_tr}전 {w_d}승 {l_d}패 ({w_rate:.1f}%)</b> · 단리 <b>{_fmt_signed_usd(cum_s)}</b> / 복리 <b>{_fmt_signed_usd(cum_c)}</b>",
    ]
    await _send_assassin_tg_alert(context, "\n".join(lines))


async def _send_3_truth_gate_entry_alert(
    context: Any,
    st: Dict[str, Any],
) -> None:
    """
    [알림 3️⃣] 🗡️ 진성 게이트 10 조건 달성 & 암살자 본대 진입 알림
    """
    mode_tag = (
        "🚀[실전]" if is_live_execution_enabled(st) else "🧪[모의]"
    )
    g_code = str(st.get("gate_code") or "G1")
    g_desc = str(st.get("gate_desc") or g_code)
    ep = safe_float(st.get("entry_price"), 0.0)
    arm_p = safe_float(st.get("arm_100_price"), 0.0)
    cap_p = safe_float(st.get("cap_500_price"), 0.0)
    q_s = safe_int(st.get("simple_held_qty"), 0)
    inv_s = safe_float(st.get("simple_invested_usd"), 0.0)
    q_c = safe_int(st.get("comp_held_qty"), 0)
    inv_c = safe_float(st.get("comp_invested_usd"), 0.0)
    e_rsi = safe_float(st.get("entry_rsi"), 50.0)
    e_vwap_d = safe_float(st.get("entry_vs_vwap_pct"), 0.0)
    e_prev_d = safe_float(st.get("entry_vs_prev_close_pct"), 0.0)
    e_preo_d = safe_float(st.get("entry_vs_pre_open_pct"), 0.0)
    dyn_thr = safe_float(st.get("dyn_qqq_thr_pct"), 0.80)

    lines = [
        f"🗡️ <b>{mode_tag} 암살자 진성 게이트 10 포착 · 본대 출격!</b>",
        f"👑 격발게이트: <b>[{_esc(g_code)}] {_esc(g_desc)}</b>",
        f"📊 진입지표: RSI <b>{e_rsi:.1f}</b> · VWAP <code>{_fmt_signed_pct(e_vwap_d)}</code> · 전일 <code>{_fmt_signed_pct(e_prev_d)}</code> · 프리시가 <code>{_fmt_signed_pct(e_preo_d)}</code>",
        f"💵 본대진입: 단가 <b>${ep:.2f}</b> | 단리 <b>{q_s}주</b>(${inv_s:,.0f}) / 복리 <b>{q_c}주</b>(${inv_c:,.0f})",
        f"🎯 익절그물: +1%점화 <b>${arm_p:.2f}</b> (도달시 보존선 잠금 & HA트레일링) · +5%안전캡 <b>${cap_p:.2f}</b>",
        f"🛡️ 3단안전망: 안전망 상승중 손절 절대금지 · 08:15후 QQQ <code>-{dyn_thr:.2f}%</code> 하락역행 감시",
    ]
    await _send_assassin_tg_alert(context, "\n".join(lines))


async def _send_4_trail_armed_1pct_alert(
    context: Any,
    st: Dict[str, Any],
    cur_price: float,
) -> None:
    """
    [알림 4️⃣] 🔥 +1.00% 익절가 도달 & 하이킨 아시(HA) 트레일링 추적 개시 알림
    """
    mode_tag = (
        "🚀[실전]" if is_live_execution_enabled(st) else "🧪[모의]"
    )
    ep = safe_float(st.get("entry_price"), 0.0)
    arm_p = safe_float(st.get("arm_100_price"), 0.0)
    cap_p = safe_float(st.get("cap_500_price"), 0.0)
    peak_p = max(safe_float(cur_price, 0.0), safe_float(st.get("peak_price"), 0.0))
    cur_gain_pct = ((peak_p - ep) / ep) * 100.0 if ep > 0.0 else 1.00
    is_trend = bool(st.get("is_trend_regime", False))
    cb_pct = (
        ASSASSIN_CALLBACK_TREND_PB_PCT
        if is_trend
        else ASSASSIN_CALLBACK_TECH_REBOUND_PCT
    )

    lines = [
        f"🔥 <b>{mode_tag} 암살자 +1.00% 돌파 · HA 트레일링 추적 점화!</b>",
        f"▫️ 가격돌파: 진입 <b>${ep:.2f}</b> ➔ 현재 <b>${peak_p:.2f}</b> (<code>+{cur_gain_pct:.2f}%</code>)",
        f"🔒 <b>최소 +1.00% 익절 보존선(${arm_p:.2f}) 하드 잠금 완료! (무패 확정)</b>",
        f"⚡ 추적모드: 0.4초 고주파 HA 양봉 홀딩 & 고점대비 <code>-{cb_pct:.2f}%</code> 콜백 스탑 (상단캡 <b>${cap_p:.2f}</b>)",
    ]
    await _send_assassin_tg_alert(context, "\n".join(lines))


async def _send_5_exit_retirement_alert(
    context: Any,
    st: Dict[str, Any],
    fx_rate: float = KRW_PER_USD_DEFAULT,
) -> None:
    """
    [알림 5️⃣] 🎯 익절(또는 방향성 3단 안전망 / 15:00 수익권 VWAP / 15:59 방탄 MOC) 퇴근 완료 알림
    """
    mode_tag = (
        "🚀[실전]" if is_live_execution_enabled(st) else "🧪[모의]"
    )
    exit_type = str(st.get("exit_type") or "HA_TRAIL_FLOOR_1PCT")
    exit_kor_map = {
        "CAP_5PCT_HOMERUN": "👑 +5.00% 상단 안전캡 홈런 익절",
        "HA_TRAIL_BOOST_WIN": "🚀 하이킨 아시(HA) 트레일링 부스트 익절",
        "HA_BEAR_SWEEP_WIN": "⚡ 하이킨 아시(HA) 음봉전환 수익 스윕 익절",
        "HA_TRAIL_FLOOR_1PCT": "🎯 +1.00% 보존선 확정 익절",
        "FIXED_1PCT_WIN": "🎯 +1.00% 목표가 확정 익절",
        "HA_TRAIL_MOC_WIN": "🎯 15:59 장마감 트레일링 익절",
        "VWAP_ESCAPE_1500": "🛡️ 15:00 수익권 정규장 VWAP 탈출",
        "STAGE2_NQ2P_STOP": "🚨 08:15후 2차 안전망(NQ 하락과열) 방어 손절",
        "STAGE3_QQQ_STOP": "🚨 08:15후 3차 안전망(QQQ 하락역행) 방어 손절",
        "MOC_1559_EXIT": "🛡️ 15:59 무오버나이트 방탄 MOC 청산",
    }
    ex_label = exit_kor_map.get(exit_type, exit_type)
    g_code = str(st.get("gate_code") or "G1")
    ep = safe_float(st.get("entry_price"), 0.0)
    xp = safe_float(st.get("exit_price"), 0.0)
    pk_p = max(xp, safe_float(st.get("peak_price"), xp))
    h_mins = max(1, safe_int(st.get("hold_mins"), 1))
    net_rate = safe_float(st.get("today_net_rate_pct"), 0.0)
    s_net = safe_float(st.get("today_simple_net_usd"), 0.0)
    c_net = safe_float(st.get("today_comp_net_usd"), 0.0)
    s_krw = int(round(s_net * max(1000.0, safe_float(fx_rate, KRW_PER_USD_DEFAULT))))

    tot_tr = safe_int(st.get("total_trade_days"), 0)
    w_d = safe_int(st.get("win_days"), 0)
    l_d = safe_int(st.get("loss_days"), 0)
    w_rate = (float(w_d) / float(max(1, tot_tr))) * 100.0
    cum_s = safe_float(st.get("cum_simple_net_usd"), 0.0)
    cum_c = safe_float(st.get("cum_comp_net_usd"), 0.0)
    comp_eq = safe_float(st.get("comp_equity_usd"), 10000.0)

    icon_hdr = "🎯" if s_net >= 0.0 else "🛡️"
    krw_sign = "+" if s_krw >= 0 else "-"

    lines = [
        f"{icon_hdr} <b>{mode_tag} 암살자 당일 퇴근 완료! [{_esc(g_code)}]</b>",
        f"▫️ 청산유형: <b>{_esc(ex_label)}</b>",
        f"▫️ 단가/시간: 진입 <b>${ep:.2f}</b> ➔ 청산 <b>${xp:.2f}</b> (최고 ${pk_p:.2f} · {h_mins}분 소요)",
        f"💰 금일손익: <b>{_fmt_signed_pct(net_rate)}</b> | 단리 <b>{_fmt_signed_usd(s_net)}</b>({krw_sign}{abs(s_krw):,}원) | 복리 <b>{_fmt_signed_usd(c_net)}</b>",
        f"🏆 누적전적: <b>{tot_tr}전 {w_d}승 {l_d}패 (승률 {w_rate:.1f}%)</b>",
        f"💵 누적수익: 단리 <b>{_fmt_signed_usd(cum_s)}</b> | 연속복리 <b>{_fmt_signed_usd(cum_c)}</b> (복리자산 <b>${comp_eq:,.2f}</b>)",
    ]
    await _send_assassin_tg_alert(context, "\n".join(lines))


# ---------------------------------------------------------------------------
# [핵심 6] 상시 가동 [모의 ⇄ 실전 Dual-Ready] 암살자 메인 틱 실행 엔진
# ---------------------------------------------------------------------------
async def execute_simulated_assassin_tick_plugin(
    context: Any,
    now_est: Optional[datetime] = None,
) -> str:
    """
    main.py 의 main_sniper_loop() 최상단에서 스나이퍼의 ON/OFF 여부 및 보유 수량과 무관하게
    매 루프(평시 1.5초 / 트레일링 점화 시 0.4초)마다 상시 호출되는 암살자(Assassin) 독립 엔진.
    """
    if now_est is None:
        now_est = datetime.now(EST_TZ)
    else:
        now_est = now_est.astimezone(EST_TZ)

    if is_weekend_nyse_closed(now_est):
        return "SKIP_WEEKEND_CLOSED"

    hm = now_est.hour * 100 + now_est.minute
    today_str = now_est.strftime("%Y-%m-%d")

    assassin_ledger = ensure_assassin_ledger(context)

    # 스나이퍼 원장의 기준 시드머니 및 계좌 고유 수수료율 연동
    sniper_seed = DEFAULT_INITIAL_SEED_USD
    us_comm = DEFAULT_US_COMMISSION_RATE
    rt_fee_pct = ROUND_TRIP_FEE_RATE_PCT
    sniper_ledger = getattr(context, "ledger", None)
    if sniper_ledger is not None and hasattr(sniper_ledger, "get_state"):
        try:
            sp_st = sniper_ledger.get_state("SOXL")
            sniper_seed = max(
                100.0, safe_float(sp_st.get("initial_seed_usd"), 10000.0)
            )
            us_comm = safe_float(
                sp_st.get("us_commission_rate"), DEFAULT_US_COMMISSION_RATE
            )
            rt_fee_pct = resolve_effective_round_trip_fee_rate_pct(sp_st)
        except Exception:
            pass

    st = await assassin_ledger.rollover_daily_session_if_needed(
        logical_date=today_str,
        sniper_seed_usd=sniper_seed,
        us_commission_rate=us_comm,
        round_trip_fee_rate_pct=rt_fee_pct,
    )

    if not bool(st.get("is_enabled", True)):
        return "HOLD_ASSASSIN_DISABLED"

    # 04:07 EST 이전 오프닝 대기 구간 또는 16:02 EST 이후 장 마감 구간
    if hm < ASSASSIN_BUY_START_HM:
        try:
            setattr(context, "assassin_high_freq_active", False)
        except Exception:
            pass
        return "WAITING_0407_OPEN"

    if bool(st.get("is_session_done", False)) and not bool(
        st.get("holding_active", False)
    ):
        try:
            setattr(context, "assassin_high_freq_active", False)
        except Exception:
            pass
        return "HOLD_ASSASSIN_SESSION_DONE"

    if hm > ASSASSIN_MOC_END_HM and not bool(st.get("holding_active", False)):
        try:
            setattr(context, "assassin_high_freq_active", False)
        except Exception:
            pass
        return "AFTER_HOURS_IDLE"

    # 실시간 현재가 조회 (main_sniper_loop 캐시 또는 API 조회)
    api = getattr(context, "api", None)
    if api is None:
        return "SKIP_NO_API"

    live_p = safe_float(getattr(context, "last_soxl_live_price", 0.0), 0.0)
    live_ts = safe_float(getattr(context, "last_soxl_live_price_mono", 0.0), 0.0)
    if live_p <= 0.0 or (time.monotonic() - live_ts) > 2.0:
        live_p = safe_float(
            await api.get_current_price(ASSASSIN_SYMBOL, fallback_price=0.0),
            0.0,
        )
        if live_p > 0.0:
            try:
                setattr(context, "last_soxl_live_price", live_p)
                setattr(context, "last_soxl_live_price_mono", time.monotonic())
            except Exception:
                pass

    if live_p <= 0.0:
        return "SKIP_NO_LIVE_PRICE"

    snap = await _extract_live_assassin_features_and_qqq_snapshot(
        context=context, live_price=live_p, now_est=now_est
    )
    now_epoch = time.time()

    # ===================================================================
    # [PART A] 암살자 본대 포지션 보유 중일 때 출구(익절 / 안전망 / MOC) 모니터
    # ===================================================================
    if bool(st.get("holding_active", False)):
        entry_p = safe_float(st.get("entry_price"), live_p)
        entry_ts = safe_float(st.get("entry_ts"), 0.0)
        cap_500_p = safe_float(st.get("cap_500_price"), round(entry_p * 1.05, 2))
        arm_100_p = safe_float(st.get("arm_100_price"), round(entry_p * 1.01, 2))
        lock_130_p = safe_float(
            st.get("lock_130_price"), round(entry_p * 1.013, 2)
        )
        cushion_075_p = safe_float(
            st.get("cushion_075_price"), round(entry_p * 1.0075, 2)
        )
        trail_armed = bool(st.get("trail_armed", False))
        peak_p = max(
            safe_float(st.get("peak_price"), entry_p),
            live_p,
        )
        bear_seen = bool(st.get("bear_candle_seen", False))
        is_trend = bool(st.get("is_trend_regime", False))
        qqq_entry_p = safe_float(
            st.get("qqq_entry_price"), snap["qqq_live_price"]
        )
        dyn_qqq_thr = safe_float(
            st.get("dyn_qqq_thr_pct"), STAGE3_MIN_QQQ_ADVERSE_PCT
        )
        post_min_p = safe_float(st.get("post_entry_min_price"), entry_p)
        if post_min_p <= 0.0:
            post_min_p = entry_p

        # 최근 5.0초 윗꼬리 체결틱 병행 감지 (목표가 -2.50% 근접 시)
        eval_high_p = live_p
        if live_p >= arm_100_p * 0.975 and hasattr(
            api, "get_recent_wick_high_price"
        ):
            try:
                wick_p, _ = await api.get_recent_wick_high_price(
                    symbol=ASSASSIN_SYMBOL,
                    lookback_sec=5.0,
                    min_after_epoch_ts=entry_ts + 2.0,
                )
                if wick_p > eval_high_p:
                    eval_high_p = wick_p
            except Exception:
                pass

        if eval_high_p > peak_p:
            peak_p = eval_high_p

        exit_triggered = False
        exit_price_val = live_p
        exit_type_str = ""

        # 1) 상단 안전 캡(+5.00% LIMIT) 도달 시 즉시 홈런 익절
        if eval_high_p >= cap_500_p:
            exit_triggered = True
            exit_price_val = cap_500_p
            exit_type_str = "CAP_5PCT_HOMERUN"
        else:
            # 2) +1.00% 트레일링 점화 판정 및 [알림 4️⃣] 발송
            if not trail_armed and eval_high_p >= arm_100_p:
                trail_armed = True
                peak_p = max(peak_p, eval_high_p)
                bear_seen = False
                st = await assassin_ledger.update_state(
                    trail_armed=True,
                    trail_armed_hm=hm,
                    peak_price=round(peak_p, 4),
                    bear_candle_seen=False,
                    session_status="TRAIL_ARMED_1PCT",
                )
                if str(st.get("trail_armed_alert_sent_date") or "") != today_str:
                    await assassin_ledger.update_state(
                        trail_armed_alert_sent_date=today_str
                    )
                    await _send_4_trail_armed_1pct_alert(
                        context=context, st=st, cur_price=peak_p
                    )

            try:
                setattr(context, "assassin_high_freq_active", bool(trail_armed))
            except Exception:
                pass

            # 3) 점화된 하이킨 아시(HA) 트레일링 스탑 감시
            if trail_armed:
                if (not snap["is_bull_bar"]) or (not snap["is_ha_bull"]):
                    bear_seen = True

                cb_pct = (
                    ASSASSIN_CALLBACK_TREND_PB_PCT
                    if is_trend
                    else ASSASSIN_CALLBACK_TECH_REBOUND_PCT
                )
                eff_stop_p = max(
                    arm_100_p,
                    math.floor(peak_p * (1.0 - cb_pct / 100.0) * 100.0) / 100.0,
                )
                eff_ha_bear = (
                    False
                    if snap["qqq_vel_max"] >= ASSASSIN_QQQ_VEL_BYPASS_SURGE_PCT
                    else (not snap["is_ha_bull"])
                )

                if (
                    is_trend
                    and peak_p < lock_130_p
                    and (not bear_seen)
                    and snap["is_bull_bar"]
                    and snap["is_ha_bull"]
                ):
                    if live_p <= cushion_075_p:
                        exit_triggered = True
                        exit_price_val = arm_100_p
                        exit_type_str = "HA_TRAIL_FLOOR_1PCT"
                else:
                    if live_p <= eff_stop_p:
                        exit_triggered = True
                        exit_price_val = max(arm_100_p, eff_stop_p)
                        exit_type_str = (
                            "HA_TRAIL_BOOST_WIN"
                            if exit_price_val > arm_100_p + 1e-4
                            else "HA_TRAIL_FLOOR_1PCT"
                        )
                    elif eff_ha_bear and (now_epoch - entry_ts >= 30.0):
                        exit_triggered = True
                        exit_price_val = max(
                            arm_100_p, min(live_p, eff_stop_p)
                        )
                        exit_type_str = (
                            "HA_BEAR_SWEEP_WIN"
                            if exit_price_val > arm_100_p + 1e-4
                            else "HA_TRAIL_FLOOR_1PCT"
                        )

        # 4) [1️⃣] 08:15 EST 이후 순수 롱 방향성 인지 3단계 안전망 v2 검문
        #    (안전망이 상승/지지 중일 때는 절대 손절 퇴근하지 않음!)
        if (
            not exit_triggered
            and not trail_armed
            and hm >= ASSASSIN_MACRO_CUTOFF_HM
            and live_p < entry_p
        ):
            is_making_new_low = bool(live_p < post_min_p - 1e-6)
            if live_p < post_min_p:
                post_min_p = live_p

            is_safety_net_rising = bool(
                snap["is_bull_bar"]
                or snap["is_ha_bull"]
                or (snap["qqq_vel_1m"] >= 0.0)
                or (snap["qqq_vel_3m"] >= 0.0)
                or (live_p >= snap["prev_reg_close"])
                or (live_p >= snap["pre_open_price"])
                or (not is_making_new_low)
            )
            qqq_adv_pct = (
                ((qqq_entry_p - snap["qqq_live_price"]) / qqq_entry_p) * 100.0
                if qqq_entry_p > 0.0
                else 0.0
            )
            if (
                (not is_safety_net_rising)
                and ((now_epoch - entry_ts) >= STAGE3_MIN_HOLD_SEC)
                and (snap["qqq_vel_3m"] <= STAGE3_ACCEL_VEL_3M_PCT)
            ):
                if qqq_adv_pct >= STAGE2_NQ_DROP_OVERHEAT_PCT:
                    exit_triggered = True
                    exit_price_val = live_p
                    exit_type_str = "STAGE2_NQ2P_STOP"
                elif qqq_adv_pct >= dyn_qqq_thr:
                    exit_triggered = True
                    exit_price_val = live_p
                    exit_type_str = "STAGE3_QQQ_STOP"

        # 5) [3-2] 15:00 ~ 15:58 EST 미익절 물량 수익권 정규장 누적 VWAP 도달 탈출
        if (
            not exit_triggered
            and not trail_armed
            and ASSASSIN_VWAP_ESCAPE_START_HM <= hm <= ASSASSIN_VWAP_ESCAPE_END_HM
        ):
            vwap_floor_p = math.floor(snap["reg_vwap"] * 100.0) / 100.0
            min_be_p = entry_p * (1.0 + (rt_fee_pct / 100.0))
            if vwap_floor_p >= min_be_p and eval_high_p >= vwap_floor_p:
                exit_triggered = True
                exit_price_val = max(live_p, vwap_floor_p)
                exit_type_str = "VWAP_ESCAPE_1500"

        # 6) [3-3] 15:59 ~ 16:01 EST 무오버나이트 2단계 방탄 MOC 강제 청산
        if not exit_triggered and hm >= ASSASSIN_MOC_START_HM:
            exit_triggered = True
            exit_price_val = max(arm_100_p, live_p) if trail_armed else live_p
            exit_type_str = (
                "HA_TRAIL_MOC_WIN" if trail_armed else "MOC_1559_EXIT"
            )

        if not exit_triggered:
            await assassin_ledger.update_state(
                peak_price=round(peak_p, 4),
                bear_candle_seen=bear_seen,
                post_entry_min_price=round(post_min_p, 4),
            )
            return "HOLDING_ASSASSIN_MONITORING"

        # --- 출구 격발 완료 -> Dual-Ready 청산 주문 스윕 및 손익 정산 ---
        q_s = max(1, safe_int(st.get("simple_held_qty"), 1))
        inv_s = safe_float(st.get("simple_invested_usd"), round(q_s * entry_p, 4))
        q_c = max(1, safe_int(st.get("comp_held_qty"), 1))
        inv_c = safe_float(st.get("comp_invested_usd"), round(q_c * entry_p, 4))

        ok_exit, final_exit_p, exit_oid = await _dispatch_assassin_exit_sweep_order(
            context=context,
            st_assassin=st,
            target_exit_price=exit_price_val,
            held_qty=q_c,
            is_moc_1559=bool(hm >= ASSASSIN_MOC_START_HM),
        )
        if not ok_exit:
            return "HOLD_ASSASSIN_EXIT_RETRY"

        try:
            setattr(context, "assassin_high_freq_active", False)
        except Exception:
            pass

        pnl_s = calc_sell_realized_pnl(
            sell_price=final_exit_p,
            sell_qty=q_s,
            actual_cost_usd_of_sold=inv_s,
            book_invested_usd_of_sold=inv_s,
            round_trip_fee_rate_pct=rt_fee_pct,
        )
        pnl_c = calc_sell_realized_pnl(
            sell_price=final_exit_p,
            sell_qty=q_c,
            actual_cost_usd_of_sold=inv_c,
            book_invested_usd_of_sold=inv_c,
            round_trip_fee_rate_pct=rt_fee_pct,
        )

        net_s = round(safe_float(pnl_s.get("net_pnl_usd"), 0.0), 4)
        fee_s = round(safe_float(pnl_s.get("fee_usd"), 0.0), 4)
        gross_s = round(safe_float(pnl_s.get("gross_pnl_usd"), 0.0), 4)

        net_c = round(safe_float(pnl_c.get("net_pnl_usd"), 0.0), 4)
        fee_c = round(safe_float(pnl_c.get("fee_usd"), 0.0), 4)
        gross_c = round(safe_float(pnl_c.get("gross_pnl_usd"), 0.0), 4)

        net_rate_pct = round(safe_float(pnl_s.get("net_pnl_rate_pct"), 0.0), 3)
        is_win_trade = bool(net_s >= 0.0)
        hold_mins = max(1, int(round((now_epoch - entry_ts) / 60.0)))

        tot_tr = safe_int(st.get("total_trade_days"), 0) + 1
        w_days = safe_int(st.get("win_days"), 0) + (1 if is_win_trade else 0)
        l_days = safe_int(st.get("loss_days"), 0) + (0 if is_win_trade else 1)
        pre_days = safe_int(st.get("pre_exit_days"), 0) + (
            1 if hm <= 929 else 0
        )

        cap5_cnt = safe_int(st.get("cap5_homerun_cnt"), 0) + (
            1 if exit_type_str == "CAP_5PCT_HOMERUN" else 0
        )
        boost_cnt = safe_int(st.get("ha_boost_win_cnt"), 0) + (
            1
            if exit_type_str in ("HA_TRAIL_BOOST_WIN", "HA_BEAR_SWEEP_WIN")
            else 0
        )
        floor_cnt = safe_int(st.get("ha_floor_1pct_cnt"), 0) + (
            1
            if exit_type_str
            in ("HA_TRAIL_FLOOR_1PCT", "FIXED_1PCT_WIN", "HA_TRAIL_MOC_WIN")
            else 0
        )
        vwap_cnt = safe_int(st.get("vwap_escape_cnt"), 0) + (
            1 if exit_type_str == "VWAP_ESCAPE_1500" else 0
        )
        stop_cnt = safe_int(st.get("stage_stop_cnt"), 0) + (
            1
            if exit_type_str in ("STAGE2_NQ2P_STOP", "STAGE3_QQQ_STOP")
            else 0
        )
        moc_cnt = safe_int(st.get("moc_exit_cnt"), 0) + (
            1 if exit_type_str == "MOC_1559_EXIT" else 0
        )

        cum_s_gross = round(
            safe_float(st.get("cum_simple_gross_usd"), 0.0) + gross_s, 4
        )
        cum_s_fee = round(
            safe_float(st.get("cum_simple_fee_usd"), 0.0) + fee_s, 4
        )
        cum_s_net = round(
            safe_float(st.get("cum_simple_net_usd"), 0.0) + net_s, 4
        )

        cum_c_gross = round(
            safe_float(st.get("cum_comp_gross_usd"), 0.0) + gross_c, 4
        )
        cum_c_fee = round(
            safe_float(st.get("cum_comp_fee_usd"), 0.0) + fee_c, 4
        )
        cum_c_net = round(
            safe_float(st.get("cum_comp_net_usd"), 0.0) + net_c, 4
        )

        hist_list = list(st.get("recent_history") or [])
        hist_list.append(
            {
                "date": today_str,
                "gate_code": str(st.get("gate_code") or ""),
                "entry_hm": safe_int(st.get("entry_hm"), 0),
                "exit_hm": hm,
                "entry_price": round(entry_p, 2),
                "exit_price": round(final_exit_p, 2),
                "exit_type": exit_type_str,
                "net_rate_pct": net_rate_pct,
                "simple_net_usd": round(net_s, 2),
                "comp_net_usd": round(net_c, 2),
            }
        )

        st = await assassin_ledger.update_state(
            holding_active=False,
            is_session_done=True,
            session_status=f"DONE_{exit_type_str}",
            sell_order_id=exit_oid,
            peak_price=round(peak_p, 4),
            exit_hm=hm,
            exit_price=round(final_exit_p, 4),
            exit_type=exit_type_str,
            hold_mins=hold_mins,
            today_net_rate_pct=net_rate_pct,
            today_simple_net_usd=round(net_s, 2),
            today_comp_net_usd=round(net_c, 2),
            total_trade_days=tot_tr,
            win_days=w_days,
            loss_days=l_days,
            pre_exit_days=pre_days,
            cap5_homerun_cnt=cap5_cnt,
            ha_boost_win_cnt=boost_cnt,
            ha_floor_1pct_cnt=floor_cnt,
            vwap_escape_cnt=vwap_cnt,
            stage_stop_cnt=stop_cnt,
            moc_exit_cnt=moc_cnt,
            cum_simple_gross_usd=cum_s_gross,
            cum_simple_fee_usd=cum_s_fee,
            cum_simple_net_usd=cum_s_net,
            cum_comp_gross_usd=cum_c_gross,
            cum_comp_fee_usd=cum_c_fee,
            cum_comp_net_usd=cum_c_net,
            recent_history=hist_list[-30:],
            exit_alert_sent_date=today_str,
        )

        fx_r = safe_float(
            getattr(context, "last_fx_rate", KRW_PER_USD_DEFAULT),
            KRW_PER_USD_DEFAULT,
        )
        await _send_5_exit_retirement_alert(context=context, st=st, fx_rate=fx_r)
        return f"ASSASSIN_EXITED_{exit_type_str}"

    # ===================================================================
    # [PART B] 08:15:00 EST 거시지표 컷오프 도래 시 무매매 퇴근 처리 ([알림 2️⃣])
    # ===================================================================
    if hm >= ASSASSIN_MACRO_CUTOFF_HM:
        if not bool(st.get("is_session_done", False)):
            no_tr_days = safe_int(st.get("total_no_trade_days"), 0) + 1
            st = await assassin_ledger.update_state(
                is_session_done=True,
                session_status="DONE_NO_TRADE_0815",
                total_no_trade_days=no_tr_days,
            )
            if str(st.get("no_trade_alert_sent_date") or "") != today_str:
                st = await assassin_ledger.update_state(
                    no_trade_alert_sent_date=today_str
                )
                await _send_2_no_trade_retirement_alert(context=context, st=st)
        return "ASSASSIN_NO_TRADE_RETIRED_0815"

    # ===================================================================
    # [PART C] 04:07 ~ 08:14 EST 골든타임 1주 독립 정찰병 파견 & 10대 진성 게이트 감시
    # ===================================================================
    pre_hi = max(safe_float(st.get("pre_running_high"), 0.0), live_p)
    pre_lo = (
        min(safe_float(st.get("pre_running_low"), 0.0), live_p)
        if safe_float(st.get("pre_running_low"), 0.0) > 0.0
        else live_p
    )
    min_rsi_d = min(safe_float(st.get("min_rsi_today"), 100.0), snap["rsi14"])
    min_vwap_d = min(
        safe_float(st.get("min_vs_vwap_today"), 0.0), snap["vs_vwap_pct"]
    )

    raw_scouts = st.get("active_scouts") or []
    active_scouts: List[IndependentScoutUnit] = []
    for item in raw_scouts:
        sc_u = IndependentScoutUnit.from_dict(item)
        if sc_u is not None:
            active_scouts.append(sc_u)

    has_active_l1 = bool(st.get("has_active_scout_l1", False))
    anchor_p = safe_float(st.get("scout_anchor_price"), 0.0)
    day_min_buy_p = safe_float(st.get("scout_day_min_buy_price"), 0.0)
    ratchet_max_lots = safe_int(st.get("scout_ratchet_max_lots"), 0)
    last_eval_b10 = safe_int(st.get("scout_last_eval_b10"), -1)
    last_action_ts = safe_float(st.get("scout_last_action_ts"), 0.0)
    last_sell_ts = safe_float(st.get("scout_last_sell_ts"), 0.0)
    day_scout_seq = safe_int(st.get("day_scout_seq"), 0)
    prior_wins_today = safe_int(st.get("prior_scout_wins_today"), 0)
    first_0407_p = safe_float(st.get("first_0407_scout_price"), 0.0)
    first_0407_rsi = safe_float(st.get("first_0407_scout_rsi"), 50.0)
    tot_sc_disp = safe_int(st.get("total_scouts_dispatched"), 0)
    tot_sc_wins = safe_int(st.get("total_scout_wins"), 0)

    # 1) 보유 중인 독립 정찰병들의 개별 +1.00% 익절 체크 (매수 후 60초 경과분)
    newly_won_cnt = 0
    if active_scouts:
        rem_scouts: List[IndependentScoutUnit] = []
        sold_targets: List[float] = []
        sold_l1_now = False

        for idx_s, s_obj in enumerate(active_scouts):
            if (now_epoch - s_obj.buy_ts) >= SCOUT_TIME_SHIELD_SEC and live_p >= s_obj.target_1pct_price:
                sold_targets.append(s_obj.target_1pct_price)
                newly_won_cnt += 1
                prior_wins_today += 1
                tot_sc_wins += 1
                if idx_s == 0 and has_active_l1:
                    sold_l1_now = True
            else:
                rem_scouts.append(s_obj)

        if sold_targets:
            if sold_l1_now or not rem_scouts:
                has_active_l1 = False
            for idx_r, r_obj in enumerate(rem_scouts):
                r_obj.layer_no = idx_r + 1
            active_scouts = rem_scouts
            anchor_p = max(sold_targets)
            last_sell_ts = now_epoch
            last_action_ts = now_epoch
            if not active_scouts:
                ratchet_max_lots = 0

            await assassin_ledger.update_state(
                active_scouts=[x.to_dict() for x in active_scouts],
                has_active_scout_l1=has_active_l1,
                scout_anchor_price=round(anchor_p, 4),
                scout_ratchet_max_lots=ratchet_max_lots,
                scout_last_sell_ts=round(last_sell_ts, 4),
                scout_last_action_ts=round(last_action_ts, 4),
                prior_scout_wins_today=prior_wins_today,
                total_scout_wins=tot_sc_wins,
                pre_running_high=round(pre_hi, 4),
                pre_running_low=round(pre_lo, 4),
                min_rsi_today=round(min_rsi_d, 2),
                min_vs_vwap_today=round(min_vwap_d, 2),
            )
            return "SCOUT_PROFIT_1PCT_SETTLED"

    # 2) 정찰병 신규 파견 조건 판정
    b_stat = evaluate_buy_gate_bucket_status(now_est, buy_interval_min=10)
    cur_b10 = safe_int(b_stat.get("bucket_10m"), -1)

    dispatch_type = ""
    dispatch_stage = ""
    replace_l1 = False

    if day_scout_seq == 0 and hm >= ASSASSIN_BUY_START_HM:
        dispatch_type = "01_OPEN_0407"
        dispatch_stage = "OPEN_0407_L1"
        replace_l1 = False
        last_eval_b10 = cur_b10
    elif (
        (now_epoch - last_action_ts) >= SCOUT_TIME_SHIELD_SEC
        and (now_epoch - last_sell_ts) >= SCOUT_TIME_SHIELD_SEC
        and len(active_scouts) < SCOUT_MAX_LAYERS_7
    ):
        if not has_active_l1:
            can_reenter = True
            if active_scouts:
                min_up_p = min(x.entry_price for x in active_scouts)
                if live_p > min_up_p + 1e-6:
                    can_reenter = False
            if can_reenter and anchor_p > 0.0:
                chg_from_anchor = ((live_p - anchor_p) / anchor_p) * 100.0
                if chg_from_anchor <= SCOUT_PULLBACK_RELOAD_PCT:
                    dispatch_type = "02_PULL_1PCT_NOFILT"
                    dispatch_stage = f"PULL_L{len(active_scouts) + 1}"
                    replace_l1 = True
                    last_eval_b10 = cur_b10
                elif (
                    chg_from_anchor >= SCOUT_BREAKOUT_RELOAD_PCT
                    and snap["rsi14"] <= SCOUT_BREAKOUT_MAX_RSI_50 + 1e-9
                ):
                    dispatch_type = "03_BRK_1PCT_RSI50"
                    dispatch_stage = f"BRK_RSI50_L{len(active_scouts) + 1}"
                    replace_l1 = True
                    last_eval_b10 = cur_b10
        else:
            if cur_b10 >= 0 and cur_b10 != last_eval_b10:
                last_eval_b10 = cur_b10
                eff_lots = max(1, len(active_scouts), ratchet_max_lots)
                req_drop_pct, wide_tag = resolve_scout_wide_drop_threshold(
                    eff_lots
                )
                l1_p = active_scouts[0].entry_price
                cands = [
                    x for x in (l1_p, anchor_p, day_min_buy_p) if x > 0.0
                ]
                ref_static = min(cands) if cands else live_p
                chg_static = ((live_p - ref_static) / ref_static) * 100.0
                if chg_static <= req_drop_pct:
                    dispatch_type = "04_WIDE_GRID_DIP"
                    dispatch_stage = f"{wide_tag}_L{len(active_scouts) + 1}"
                    replace_l1 = False

    if not dispatch_type:
        await assassin_ledger.update_state(
            scout_last_eval_b10=last_eval_b10,
            pre_running_high=round(pre_hi, 4),
            pre_running_low=round(pre_lo, 4),
            min_rsi_today=round(min_rsi_d, 2),
            min_vs_vwap_today=round(min_vwap_d, 2),
            session_status="SCOUTING_GOLDENTIME",
        )
        return "SCOUTING_GOLDENTIME_IDLE"

    # 3) 신규 독립 정찰병 1주 등록 및 [알림 1️⃣] 발송
    day_scout_seq += 1
    tot_sc_disp += 1
    if day_scout_seq == 1:
        first_0407_p = live_p
        first_0407_rsi = snap["rsi14"]

    vs_scout1_pct = (
        round(((live_p - first_0407_p) / first_0407_p) * 100.0, 3)
        if first_0407_p > 0.0
        else 0.0
    )
    tp_1pct = round(
        math.ceil((live_p * (1.0 + SCOUT_TAKE_PROFIT_PCT / 100.0) - 1e-9) * 100.0)
        / 100.0,
        2,
    )
    new_layer_no = len(active_scouts) + 1
    new_eff_lots = (
        1
        if day_scout_seq == 1
        else max(new_layer_no, ratchet_max_lots + (0 if replace_l1 else 1))
    )

    new_scout = IndependentScoutUnit(
        scout_id=tot_sc_disp,
        seq_in_day=day_scout_seq,
        buy_ts=now_epoch,
        entry_hm=hm,
        entry_type=dispatch_type,
        stage_tag=dispatch_stage,
        layer_no=new_layer_no,
        lot_seq=new_eff_lots,
        entry_price=live_p,
        target_1pct_price=tp_1pct,
        rsi14=snap["rsi14"],
        vwap_price=snap["pre_vwap"],
        prev_reg_close=snap["prev_reg_close"],
        pre_open_price=snap["pre_open_price"],
        vs_vwap_pct=snap["vs_vwap_pct"],
        vs_prev_close_pct=snap["vs_prev_close_pct"],
        vs_pre_open_pct=snap["vs_pre_open_pct"],
        vs_scout1_pct=vs_scout1_pct,
        prior_wins_at_entry=prior_wins_today,
        is_bull_bar=snap["is_bull_bar"],
    )

    active_scouts.insert(0, new_scout)
    for idx_a, a_obj in enumerate(active_scouts):
        a_obj.layer_no = idx_a + 1

    all_scouts_today = list(st.get("all_scouts_today") or [])
    all_scouts_today.append(new_scout.to_dict())

    has_active_l1 = True
    anchor_p = live_p
    day_min_buy_p = (
        min(day_min_buy_p, live_p) if day_min_buy_p > 0.0 else live_p
    )
    ratchet_max_lots = max(ratchet_max_lots, len(active_scouts), new_eff_lots)
    last_action_ts = now_epoch

    # 4) 2번째 이후 정찰병(day_scout_seq >= 2)에서 10대 진성 게이트 판정
    ok_gate = False
    g_code = ""
    g_desc = ""
    is_trend = False
    if day_scout_seq >= 2:
        ok_gate, g_code, g_desc, is_trend = evaluate_10_truth_gates_signal(
            rsi_val=snap["rsi14"],
            vs_vwap_pct=snap["vs_vwap_pct"],
            vs_prev_close_pct=snap["vs_prev_close_pct"],
            vs_pre_open_pct=snap["vs_pre_open_pct"],
            vs_scout1_pct=vs_scout1_pct,
            prior_wins_today=prior_wins_today,
            is_bull_bar=snap["is_bull_bar"],
        )

    st = await assassin_ledger.update_state(
        session_status="SCOUTING_GOLDENTIME",
        active_scouts=[x.to_dict() for x in active_scouts],
        all_scouts_today=all_scouts_today[-25:],
        has_active_scout_l1=has_active_l1,
        scout_anchor_price=round(anchor_p, 4),
        scout_day_min_buy_price=round(day_min_buy_p, 4),
        scout_ratchet_max_lots=ratchet_max_lots,
        scout_last_eval_b10=last_eval_b10,
        scout_last_action_ts=round(last_action_ts, 4),
        day_scout_seq=day_scout_seq,
        first_0407_scout_price=round(first_0407_p, 4),
        first_0407_scout_rsi=round(first_0407_rsi, 2),
        total_scouts_dispatched=tot_sc_disp,
        pre_running_high=round(pre_hi, 4),
        pre_running_low=round(pre_lo, 4),
        min_rsi_today=round(min_rsi_d, 2),
        min_vs_vwap_today=round(min_vwap_d, 2),
        last_scout_alert_seq=day_scout_seq,
    )

    # [알림 1️⃣] 정찰병 파견 알림 발송
    await _send_1_scout_dispatched_alert(
        context=context,
        st=st,
        scout=new_scout,
        newly_won_scouts_cnt=newly_won_cnt,
        gate_matched=ok_gate,
        gate_desc=g_desc,
    )

    if not ok_gate:
        return f"SCOUT_{day_scout_seq}_DISPATCHED"

    # 5) [1차 안전망] 자유낙하 과열 검문 (음봉 & HA음봉 & 3분변화율 <= -0.35% & 하락진폭 >= 3.0%)
    is_freefall = bool(
        (not snap["is_bull_bar"])
        and (not snap["is_ha_bull"])
        and (snap["qqq_vel_3m"] <= STAGE1_FREEFALL_VEL_3M_PCT)
        and (snap["nq_bear_drop_amp"] >= STAGE1_FREEFALL_BEAR_AMP_PCT)
    )
    if is_freefall:
        return "HOLD_STAGE1_FREEFALL_BLOCKED"

    # 6) 진성 게이트 10 달성 -> 암살자 본대 즉시 진입 & +5.00% 안전캡 선장전 & [알림 3️⃣] 발송
    init_seed = max(100.0, safe_float(st.get("initial_seed_usd"), 10000.0))
    comp_eq = max(init_seed, safe_float(st.get("comp_equity_usd"), init_seed))
    unit_cost = live_p * (1.0 + (rt_fee_pct / 100.0))

    q_simple = max(1, int(math.floor((init_seed + 1e-9) / unit_cost)))
    q_comp = max(1, int(math.floor((comp_eq + 1e-9) / unit_cost)))

    ok_buy, buy_oid, fill_p, fill_q_c = await _dispatch_assassin_buy_order(
        context=context,
        st_assassin=st,
        order_price=live_p,
        order_qty=q_comp,
    )
    if not ok_buy or fill_p <= 0.0:
        return "HOLD_ASSASSIN_BUY_FAILED"

    cap_500_p = round(
        math.ceil(
            (fill_p * (1.0 + ASSASSIN_SAFE_CAP_PROFIT_PCT / 100.0) - 1e-9)
            * 100.0
        )
        / 100.0,
        2,
    )
    arm_100_p = round(
        math.ceil(
            (fill_p * (1.0 + ASSASSIN_TRAIL_ARM_PROFIT_PCT / 100.0) - 1e-9)
            * 100.0
        )
        / 100.0,
        2,
    )
    lock_130_p = round(
        math.ceil(
            (fill_p * (1.0 + ASSASSIN_PEAK_LOCK_BOOST_PCT / 100.0) - 1e-9)
            * 100.0
        )
        / 100.0,
        2,
    )
    cushion_075_p = round(
        math.ceil(
            (fill_p * (1.0 + ASSASSIN_CUSHION_FLOOR_PCT / 100.0) - 1e-9) * 100.0
        )
        / 100.0,
        2,
    )
    dyn_qqq_thr = round(
        min(
            STAGE3_MAX_QQQ_ADVERSE_PCT,
            max(
                snap["nq_bear_drop_amp"] * 0.5,
                STAGE3_MIN_QQQ_ADVERSE_PCT,
            ),
        ),
        2,
    )

    sell_cap_oid = await _dispatch_assassin_safe_cap_sell_order(
        context=context,
        st_assassin=st,
        cap_500_price=cap_500_p,
        held_qty=fill_q_c,
    )

    st = await assassin_ledger.update_state(
        holding_active=True,
        session_status=f"HOLDING_{g_code}",
        buy_order_id=buy_oid,
        sell_order_id=sell_cap_oid,
        gate_code=g_code,
        gate_desc=g_desc,
        is_trend_regime=is_trend,
        entry_hm=hm,
        entry_ts=round(now_epoch, 4),
        signal_price=round(live_p, 4),
        entry_price=round(fill_p, 4),
        entry_rsi=snap["rsi14"],
        entry_vs_vwap_pct=snap["vs_vwap_pct"],
        entry_vs_prev_close_pct=snap["vs_prev_close_pct"],
        entry_vs_pre_open_pct=snap["vs_pre_open_pct"],
        simple_held_qty=q_simple,
        simple_invested_usd=round(float(q_simple) * fill_p, 4),
        comp_held_qty=fill_q_c,
        comp_invested_usd=round(float(fill_q_c) * fill_p, 4),
        cap_500_price=cap_500_p,
        arm_100_price=arm_100_p,
        lock_130_price=lock_130_p,
        cushion_075_price=cushion_075_p,
        trail_armed=False,
        trail_armed_hm=0,
        peak_price=round(fill_p, 4),
        bear_candle_seen=False,
        qqq_entry_price=snap["qqq_live_price"],
        nq_entry_bear_amp=snap["nq_bear_drop_amp"],
        dyn_qqq_thr_pct=dyn_qqq_thr,
        post_entry_min_price=round(fill_p, 4),
        entry_alert_sent_date=today_str,
    )

    await _send_3_truth_gate_entry_alert(context=context, st=st)
    return f"ASSASSIN_ENTERED_{g_code}"


# ---------------------------------------------------------------------------
# [핵심 7] 관제 UI 연동 포매터 (/avwap · /settlement 하단 슬림 블록 & /assassin 상세 보드)
# ---------------------------------------------------------------------------
def format_assassin_slim_radar_block(
    context: Any,
    live_price: float = 0.0,
) -> str:
    """
    /avwap (스나이퍼 레이더) 및 /settlement (전술 제어반) 하단에 결합되는
    36자 칼맞춤 초슬림 🗡️ [모의] 암살자 실시간 관제 요약 블록을 생성한다.
    """
    assassin_ledger = ensure_assassin_ledger(context)
    st = assassin_ledger.get_state()
    mode_badge = (
        "🚀실전가동" if is_live_execution_enabled(st) else "🧪모의상시ON"
    )

    sc_seq = safe_int(st.get("day_scout_seq"), 0)
    sc_wins = safe_int(st.get("prior_scout_wins_today"), 0)
    tot_tr = safe_int(st.get("total_trade_days"), 0)
    w_d = safe_int(st.get("win_days"), 0)
    l_d = safe_int(st.get("loss_days"), 0)
    w_rate = (
        (float(w_d) / float(max(1, tot_tr))) * 100.0 if tot_tr > 0 else 100.0
    )
    cum_s = safe_float(st.get("cum_simple_net_usd"), 0.0)
    cum_c = safe_float(st.get("cum_comp_net_usd"), 0.0)

    if bool(st.get("holding_active", False)):
        g_code = str(st.get("gate_code") or "G1")
        ep = safe_float(st.get("entry_price"), 0.0)
        arm_p = safe_float(st.get("arm_100_price"), 0.0)
        cap_p = safe_float(st.get("cap_500_price"), 0.0)
        p_cur = safe_float(live_price, 0.0) if live_price > 0.0 else ep
        chg_p = ((p_cur - ep) / ep) * 100.0 if ep > 0.0 else 0.0
        if bool(st.get("trail_armed", False)):
            pk_p = max(p_cur, safe_float(st.get("peak_price"), p_cur))
            status_line = f"🔥 <b>본대추적[{_esc(g_code)}]</b>: ${ep:.2f}➔<b>${p_cur:.2f}</b>({_fmt_signed_pct(chg_p)}) · 최고${pk_p:.2f}/보존${arm_p:.2f}"
        else:
            status_line = f"🗡️ <b>본대보유[{_esc(g_code)}]</b>: 진입<b>${ep:.2f}</b>({chg_p:+.2f}%) ➔ +1%점화<b>${arm_p:.2f}</b> / 캡${cap_p:.2f}"
    elif bool(st.get("is_session_done", False)):
        ex_t = str(st.get("exit_type") or "")
        if ex_t:
            t_net = safe_float(st.get("today_simple_net_usd"), 0.0)
            t_rate = safe_float(st.get("today_net_rate_pct"), 0.0)
            status_line = f"🎯 <b>금일퇴근[{_esc(st.get('gate_code'))}]</b>: {_esc(ex_t)} (<b>{_fmt_signed_pct(t_rate)}</b> · 단리 <b>{_fmt_signed_usd(t_net)}</b>)"
        else:
            status_line = f"🏠 <b>금일무매매퇴근(08:15)</b>: 정찰 {sc_seq}명({sc_wins}승) · 진성미도달 시드보존"
    else:
        act_sc = st.get("active_scouts") or []
        if act_sc and isinstance(act_sc[0], dict):
            s0 = act_sc[0]
            s_ep = safe_float(s0.get("entry_price"), 0.0)
            s_tp = safe_float(s0.get("target_1pct_price"), 0.0)
            status_line = f"🕵️ <b>정찰중(#{sc_seq}명·{len(act_sc)}층·{sc_wins}승)</b>: 최근${s_ep:.2f}➔목표${s_tp:.2f} · 진성게이트10 감시"
        else:
            status_line = f"⏳ <b>정찰대기(04:07~08:14)</b>: 금일 정찰 {sc_seq}명({sc_wins}승) · 진성게이트10 대기"

    lines = [
        "━━━━━━━━━━━━━━━━━━",
        f"🗡️ <b>암살자 레이더 ({mode_badge})</b> · <code>/assassin</code>",
        status_line,
        f"🏆 모의누적: <b>{tot_tr}전 {w_d}승 {l_d}패({w_rate:.1f}%)</b> · 단리<b>{_fmt_signed_usd(cum_s)}</b> / 복리<b>{_fmt_signed_usd(cum_c)}</b>",
    ]
    return "\n".join(lines)


async def build_assassin_detail_dashboard_html(
    context: Any,
    live_price: float = 0.0,
) -> str:
    """
    /assassin 명령어 입력 시 당일 파견된 정찰병 내역, 실시간 4대 지표, 10대 진성 게이트 현황,
    그리고 [모의] 암살자 누적 성적표를 상세히 렌더링한다.
    """
    now_est = datetime.now(EST_TZ)
    assassin_ledger = ensure_assassin_ledger(context)
    st = assassin_ledger.get_state()
    api = getattr(context, "api", None)

    p_now = safe_float(live_price, 0.0)
    if p_now <= 0.0 and api is not None:
        p_now = safe_float(
            await api.get_current_price(ASSASSIN_SYMBOL, fallback_price=0.0),
            0.0,
        )
    snap = await _extract_live_assassin_features_and_qqq_snapshot(
        context=context, live_price=p_now, now_est=now_est
    )

    mode_str = (
        "🚀 실전 주문 가동 (LIVE)"
        if is_live_execution_enabled(st)
        else "🧪 모의 상시 작동 (SIMULATED · 실주문 100% 차단)"
    )
    init_seed = safe_float(st.get("initial_seed_usd"), 10000.0)
    comp_eq = safe_float(st.get("comp_equity_usd"), init_seed)
    tot_tr = safe_int(st.get("total_trade_days"), 0)
    no_tr = safe_int(st.get("total_no_trade_days"), 0)
    w_d = safe_int(st.get("win_days"), 0)
    l_d = safe_int(st.get("loss_days"), 0)
    w_rate = (
        (float(w_d) / float(max(1, tot_tr))) * 100.0 if tot_tr > 0 else 100.0
    )
    cum_s = safe_float(st.get("cum_simple_net_usd"), 0.0)
    cum_c = safe_float(st.get("cum_comp_net_usd"), 0.0)

    sc_seq = safe_int(st.get("day_scout_seq"), 0)
    sc_wins = safe_int(st.get("prior_scout_wins_today"), 0)
    all_sc = st.get("all_scouts_today") or []

    lines = [
        f"🗡️ <b>[인피니트 스노우볼 · 암살자(Assassin) 관제 보드]</b>",
        f"⚙️ 운용모드: <b>{mode_str}</b>",
        f"💵 기준시드: <b>${init_seed:,.2f}</b> | 연속복리자산: <b>${comp_eq:,.2f}</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"📊 <b>[실시간 SOXL · QQQ 4대 지표 스냅샷]</b>",
        f"• 현재가: <b>${snap['live_price']:.2f}</b> ({'📈양봉' if snap['is_bull_bar'] else '📉음봉'} / HA {'🟢양봉' if snap['is_ha_bull'] else '🔴음봉'})",
        f"① RSI(14): <b>{snap['rsi14']:.1f}</b> | ② 프리VWAP: <b>${snap['pre_vwap']:.2f}</b> (<code>{_fmt_signed_pct(snap['vs_vwap_pct'])}</code>)",
        f"③ 전일종가: <b>${snap['prev_reg_close']:.2f}</b> (<code>{_fmt_signed_pct(snap['vs_prev_close_pct'])}</code>) | ④ 프리시가: <b>${snap['pre_open_price']:.2f}</b> (<code>{_fmt_signed_pct(snap['vs_pre_open_pct'])}</code>)",
        f"🛡️ QQQ안전망: 1분 <code>{_fmt_signed_pct(snap['qqq_vel_1m'])}</code> · 3분 <code>{_fmt_signed_pct(snap['qqq_vel_3m'])}</code> · 하락진폭 <code>{snap['nq_bear_drop_amp']:.2f}%</code>",
        "━━━━━━━━━━━━━━━━━━",
        f"🕵️ <b>[금일 1주 독립 정찰병 파견 기록 (총 {sc_seq}명 · +1%익절 {sc_wins}회)]</b>",
    ]

    if not all_sc:
        lines.append("• 금일 파견된 정찰병이 아직 없습니다 (04:07 EST 첫 선봉 출격).")
    else:
        for sc_d in all_sc[-7:]:
            if not isinstance(sc_d, dict):
                continue
            seq_i = safe_int(sc_d.get("seq_in_day"), 1)
            hm_i = safe_int(sc_d.get("entry_hm"), 407)
            ep_i = safe_float(sc_d.get("entry_price"), 0.0)
            tp_i = safe_float(sc_d.get("target_1pct_price"), 0.0)
            r_i = safe_float(sc_d.get("rsi14"), 50.0)
            vw_i = safe_float(sc_d.get("vs_vwap_pct"), 0.0)
            pc_i = safe_float(sc_d.get("vs_prev_close_pct"), 0.0)
            po_i = safe_float(sc_d.get("vs_pre_open_pct"), 0.0)
            lines.append(
                f"• <b>#{seq_i}</b>(<code>{hm_i:04d}</code>): <b>${ep_i:.2f}</b>➔${tp_i:.2f} | RSI {r_i:.1f} · VWAP {vw_i:+.1f}% · 전일 {pc_i:+.1f}% · 시가 {po_i:+.1f}%"
            )

    lines.extend(
        [
            "━━━━━━━━━━━━━━━━━━",
            "🏆 <b>[[모의] 암살자 누적 성적표 (초기화: /reset_assassin)]</b>",
            f"• 총 출격일: <b>{tot_tr}일</b> ({w_d}승 {l_d}패 · 승률 <b>{w_rate:.2f}%</b>) | 무매매퇴근: {no_tr}일",
            f"• 출구분포: +5%홈런 {safe_int(st.get('cap5_homerun_cnt'), 0)}회 · HA부스트 {safe_int(st.get('ha_boost_win_cnt'), 0)}회 · +1%보존 {safe_int(st.get('ha_floor_1pct_cnt'), 0)}회 · 3단방어 {safe_int(st.get('stage_stop_cnt'), 0)}회",
            f"• 💵 단리 누적순익: <b>{_fmt_signed_usd(cum_s)}</b> (<code>{_fmt_signed_pct((cum_s / max(1.0, init_seed)) * 100.0)}</code>)",
            f"• 📈 복리 누적순익: <b>{_fmt_signed_usd(cum_c)}</b> (<code>{_fmt_signed_pct((cum_c / max(1.0, init_seed)) * 100.0)}</code>)",
        ]
    )
    return "\n".join(lines)


def run_assassin_plugin_tdd() -> None:
    """
    부팅 시 암살자 10대 진성 게이트 및 독립 정찰병 모듈 무결성 자가 검증(TDD)을 수행한다.
    """
    ok1, g1, _, _ = evaluate_10_truth_gates_signal(
        rsi_val=28.5,
        vs_vwap_pct=-1.2,
        vs_prev_close_pct=-0.8,
        vs_pre_open_pct=-1.6,
        vs_scout1_pct=-1.6,
        prior_wins_today=0,
        is_bull_bar=False,
    )
    assert ok1 and g1 == "G1", f"Assassin TDD Gate 1 failed: {ok1}, {g1}"

    ok5, g5, _, _ = evaluate_10_truth_gates_signal(
        rsi_val=19.2,
        vs_vwap_pct=-1.1,
        vs_prev_close_pct=0.5,
        vs_pre_open_pct=-1.0,
        vs_scout1_pct=-1.0,
        prior_wins_today=0,
        is_bull_bar=True,
    )
    assert ok5 and g5 == "G5", f"Assassin TDD Gate 5 failed: {ok5}, {g5}"

    ok_none, _, _, _ = evaluate_10_truth_gates_signal(
        rsi_val=55.0,
        vs_vwap_pct=0.5,
        vs_prev_close_pct=1.2,
        vs_pre_open_pct=0.8,
        vs_scout1_pct=0.8,
        prior_wins_today=0,
        is_bull_bar=True,
    )
    assert not ok_none, "Assassin TDD False-Positive check failed"
