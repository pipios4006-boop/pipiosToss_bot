# -*- coding: utf-8 -*-
"""
# MODIFIED: assassin_plugin.py (Case 93 [모의 ⇄ 실전 Dual-Ready] 암살자 독립 플러그인 · 장 마감 후 프리시가/프리VWAP 정규장 가격 오염 제거 및 원장 박제/$0.00 정합성 완비)
인피니트 스노우볼 (Infinite Snowball) v3.0 — 🗡️ [모의 ⇄ 실전 Dual-Ready] 암살자(Assassin) 독립 전술 플러그인 (Step 10 / 14)
- 제3헌법 & Case 68, Case 75, Case 85, Case 86, Case 92 & Case 93:
  1) 실전 스나이퍼 원장(soxl_stratum_ledger) 및 예수금에 단 1바이트의 간섭도 없는
     독립 전용 3중 원장(assassin_sim_ledger_{folder_slug}.json · AssassinSimLedger) 물리적 격리 아키텍처
  2) 스나이퍼 ON/OFF 여부 및 주식 보유 수량과 무관하게 24시간 상시 작동하며,
     현재는 ASSASSIN_LIVE_ORDER_HARD_LOCK = True (SIMULATED 모드)로 실계좌 주문을 물리적으로 100% 차단하되,
     내부 매수(_dispatch_assassin_buy_order) · +5.00% 안전캡 선장전(_dispatch_assassin_safe_cap_sell_order) ·
     0.40초 고주파 HA 트레일링 가격 정정(POST /api/v1/orders/{orderId}/modify, quantity 미포함) ·
     15:59 2단계 방탄 MOC 상태 머신은 토스증권 Open API v1.2.14 실전 규격과 100% 동일하게 구현된 Dual-Ready 엔진!
  3) 평일 골든타임(04:07 ~ 08:14 EST) 1주 독립 정찰병(IndependentScoutUnit · 이동평균 및 합병 100% 배제) 파견 &
     4대 핵심 지표(① 1분봉 Wilder RSI14 · ② 당일 프리장 누적 VWAP 및 괴리율% · ③ 전일 정규장 종가 및 등락률% ·
     ④ 당일 04:07 프리장 시가 및 등락률%) 실시간 계측 및 원장 영속화 박제
     - 장 마감 후(또는 오후장) 재기동으로 당일 프리장(04:07 ~ 09:29 EST) 1분봉이 API 300봉 윈도우 밖으로 밀려났을 때,
       프리장 중 원장에 박제된 진성 프리시가(today_pre_open_price)와 프리VWAP(today_pre_vwap)가 있으면 이를 보존하고,
       당일 프리장 기록이 전무할 때는 정규장 시가($48.70)나 정규VWAP($45.43)로 오염시키지 않고 정확히 $0.00 (0.00%)으로 표출!
  4) 2번째+ 정찰병 타점에서 10대 진성 게이트(헌법 G1 ~ G5 + 폭락장 BG1 ~ BG5) 포착 시 가용 시드 100% 단발 진입 &
     +5.00% 상단 안전캡 선장전 & +1.00% 도달 시 보존선 하드 잠금 및 0.40초 하이킨 아시(HA) 트레일링 스윕
  5) 08:15 EST 이후 순수 롱 방향성 인지 나스닥 100 선물/QQQ 3단계 안전망 v2 (안전망 상승/지지 중 손절 절대 금지 ·
     음봉 & 신저가 붕괴 + QQQ 3m <= -0.25% 급락 역행만 칼손절) + 15:00 ~ 15:58 수익권 정규장 VWAP 탈출 + 15:59 무오버나이트 MOC
  6) 5대 라이프사이클 실시간 텔레그램 푸시 알림(① 정찰병 파견 · ② 08:15 무매매 퇴근 · ③ 진성 게이트 10 진입 ·
     ④ +1.00% 도달 추적 개시 · ⑤ 익절/안전망/MOC 퇴근 및 누적 성적표)
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import html
import json
import logging
import math
import os
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from quant_indicators_plugin import (
    compute_1m_indicators_vectorized,
    compute_qqq_macro_metrics_1m,
    compute_realtime_synthetic_rsi,
    is_weekend_nyse_closed,
)
from toss_api import (
    DEFAULT_INITIAL_SEED_USD,
    DEFAULT_ROUND_TRIP_FEE_PCT,
    DEFAULT_US_COMMISSION_RATE,
    EST_TZ,
    GlobalThrottle,
    KST_TZ,
    LOCKED_BUY_INTERVAL_MIN,
    REAL_ALLOWED_SYMBOLS,
    TARGET_SYMBOL,
    emergency_free_disk_space_sync,
    resolve_effective_round_trip_fee_rate_pct,
    safe_float,
    safe_int,
)

logger = logging.getLogger("toss_sniper.assassin_plugin")

# ===========================================================================
# [상수 락온] 🗡️ [모의 ⇄ 실전 Dual-Ready] 암살자 핵심 파라미터 (Case 93)
# ===========================================================================
# 현재는 모의(SIMULATED) 하드 락온 (True). 향후 폭락장 종료 후 실전 복귀 시 False 로 해금하면 즉시 실주문 가동!
ASSASSIN_LIVE_ORDER_HARD_LOCK: bool = True
ASSASSIN_MODE_SIMULATED: str = "SIMULATED"
ASSASSIN_MODE_LIVE: str = "LIVE"

ASSASSIN_SCOUT_START_HM: int = 407      # 04:07 EST 첫 선봉 정찰병 출격
ASSASSIN_SCOUT_END_HM: int = 814        # 08:14 EST 정찰 및 본대 신규 진입 마감
ASSASSIN_CUTOFF_HM: int = 815           # 08:15 EST 거시지표 발표 전 무매매 안전 퇴근 컷오프
ASSASSIN_VWAP_EXIT_START_HM: int = 1500 # 15:00 ~ 15:58 EST 수익권 정규장 VWAP 탈출 구간
ASSASSIN_MOC_SWEEP_HM: int = 1559       # 15:59 ~ 16:01 EST 무오버나이트 2단계 방탄 MOC

ASSASSIN_SCOUT_MAX_TIERS: int = 7       # 1주 독립 정찰병 최대 7층
ASSASSIN_SCOUT_PROFIT_PCT: float = 1.00 # 각 정찰병 독립 익절 목표 (+1.00%)
ASSASSIN_SCOUT_PULL_PCT: float = -1.00  # 정찰병 1층 공석 눌림목 (-1.00% 무필터)
ASSASSIN_SCOUT_BRK_PCT: float = 1.00    # 정찰병 1층 공석 돌파 (+1.00% & RSI<=50)
ASSASSIN_SCOUT_BRK_MAX_RSI: float = 50.0

ASSASSIN_SAFE_CAP_PCT: float = 5.00     # 본대 진입 직후 +5.00% 상단 안전 캡 선장전
ASSASSIN_TRAIL_ARM_PCT: float = 1.00    # +1.00% 도달 시 익절 보존선(Floor) 하드 잠금 및 HA 트레일링 점화
ASSASSIN_HIGH_FREQ_LOOP_SEC: float = 0.40  # 트레일링 점화 시 0.40초 초고속 스캔 주기
ASSASSIN_POST_FILL_SHIELD_SEC: float = 60.0
ASSASSIN_HARD_STOP_FLOOR_PCT: float = -8.00


# ===========================================================================
# [데이터 모델] 1주 독립 정찰병 (이동평균 및 합병 100% 배제)
# ===========================================================================
@dataclass
class IndependentScoutUnit:
    scout_seq: int
    tier_idx: int
    entry_price: float
    target_price: float
    entry_ts: float
    entry_hm_str: str
    trigger_tag: str
    rsi_14: float = 50.0
    pre_vwap: float = 0.0
    vs_vwap_pct: float = 0.0
    prev_reg_close: float = 0.0
    vs_prev_close_pct: float = 0.0
    pre_open_price: float = 0.0
    vs_pre_open_pct: float = 0.0
    vs_scout1_pct: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scout_seq": int(self.scout_seq),
            "tier_idx": int(self.tier_idx),
            "entry_price": round(float(self.entry_price), 4),
            "target_price": round(float(self.target_price), 4),
            "entry_ts": float(self.entry_ts),
            "entry_hm_str": str(self.entry_hm_str),
            "trigger_tag": str(self.trigger_tag),
            "rsi_14": round(float(self.rsi_14), 2),
            "pre_vwap": round(float(self.pre_vwap), 4),
            "vs_vwap_pct": round(float(self.vs_vwap_pct), 2),
            "prev_reg_close": round(float(self.prev_reg_close), 4),
            "vs_prev_close_pct": round(float(self.vs_prev_close_pct), 2),
            "pre_open_price": round(float(self.pre_open_price), 4),
            "vs_pre_open_pct": round(float(self.vs_pre_open_pct), 2),
            "vs_scout1_pct": round(float(self.vs_scout1_pct), 2),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "IndependentScoutUnit":
        ep = round(max(0.01, safe_float(d.get("entry_price"), 1.0)), 4)
        tp = round(
            safe_float(
                d.get("target_price"),
                math.ceil(ep * 1.010 * 100.0 - 1e-9) / 100.0,
            ),
            2,
        )
        return cls(
            scout_seq=max(1, safe_int(d.get("scout_seq"), 1)),
            tier_idx=max(1, safe_int(d.get("tier_idx"), 1)),
            entry_price=ep,
            target_price=tp,
            entry_ts=safe_float(d.get("entry_ts"), 0.0),
            entry_hm_str=str(d.get("entry_hm_str") or "04:07"),
            trigger_tag=str(d.get("trigger_tag") or "01_OPEN_0407"),
            rsi_14=round(safe_float(d.get("rsi_14"), 50.0), 2),
            pre_vwap=round(safe_float(d.get("pre_vwap"), 0.0), 4),
            vs_vwap_pct=round(safe_float(d.get("vs_vwap_pct"), 0.0), 2),
            prev_reg_close=round(safe_float(d.get("prev_reg_close"), 0.0), 4),
            vs_prev_close_pct=round(
                safe_float(d.get("vs_prev_close_pct"), 0.0), 2
            ),
            pre_open_price=round(safe_float(d.get("pre_open_price"), 0.0), 4),
            vs_pre_open_pct=round(safe_float(d.get("vs_pre_open_pct"), 0.0), 2),
            vs_scout1_pct=round(safe_float(d.get("vs_scout1_pct"), 0.0), 2),
        )


# ===========================================================================
# [독립 3중 원장] AssassinSimLedger (스나이퍼 원장과 100% 물리적 격리 · Case 68, 75, 85, 93)
# ===========================================================================
def resolve_folder_isolated_assassin_ledger_paths(
    base_dir: Optional[str] = None,
) -> Tuple[str, str, str]:
    """
    🚨 Case 68 & Case 85:
    폴더 위치(base_dir) 기반 암살자 전용 3중 원장 경로를 반환한다.
    f-string 닫는 중괄호(}) 무결성을 100% 엄수한다.
    """
    target_dir = (
        os.path.abspath(base_dir)
        if base_dir
        else os.path.dirname(os.path.abspath(__file__))
    )
    folder_slug = os.path.basename(target_dir).strip() or "default_bot"
    backup_dir = os.path.join(target_dir, "ledger_backups")
    try:
        os.makedirs(backup_dir, exist_ok=True)
    except Exception:
        pass

    primary_path = os.path.join(
        target_dir, f"assassin_sim_ledger_{folder_slug}.json"
    )
    compat_path = os.path.join(target_dir, "assassin_sim_ledger.json")
    backup_path = os.path.join(
        backup_dir, f"assassin_sim_ledger_{folder_slug}.bak.json"
    )
    return primary_path, compat_path, backup_path


class AssassinSimLedger:
    """
    🗡️ 스나이퍼와 100% 물리적으로 분리된 암살자 전용 3중 원장 금고:
    - Dirty-Check 해시 비교를 통해 실질적인 상태 변화가 없을 때는 불필요한 디스크 쓰기(os.fsync)를 차단한다(Case 75).
    - 당일 프리장(04:07 ~ 09:29 EST) 중 계측된 실제 프리시가(today_pre_open_price)와 프리VWAP(today_pre_vwap)를
      원장에 영속화 박제하여 장 마감 후에도 보존하고, 프리장 데이터가 없는 날에는 $0.00 (0.00%)으로 표출한다.
    """

    def __init__(
        self,
        base_dir: Optional[str] = None,
        initial_seed_usd: float = DEFAULT_INITIAL_SEED_USD,
    ) -> None:
        self.base_dir = (
            os.path.abspath(base_dir)
            if base_dir
            else os.path.dirname(os.path.abspath(__file__))
        )
        (
            self.primary_path,
            self.compat_path,
            self.backup_path,
        ) = resolve_folder_isolated_assassin_ledger_paths(self.base_dir)
        self._lock = threading.RLock()
        self._last_saved_digest: str = ""
        self._state: Dict[str, Any] = self._build_default_state(
            initial_seed_usd
        )
        self._load_or_init_sync()

    def _build_default_state(
        self, initial_seed_usd: float = DEFAULT_INITIAL_SEED_USD
    ) -> Dict[str, Any]:
        seed = round(
            max(
                100.0,
                safe_float(initial_seed_usd, DEFAULT_INITIAL_SEED_USD),
            ),
            2,
        )
        now_est = datetime.now(EST_TZ)
        return {
            "version": "v11.0_ASSASSIN_DUAL_READY_CASE93",
            "execution_mode": (
                ASSASSIN_MODE_SIMULATED
                if ASSASSIN_LIVE_ORDER_HARD_LOCK
                else ASSASSIN_MODE_LIVE
            ),
            "live_order_hard_lock": bool(ASSASSIN_LIVE_ORDER_HARD_LOCK),
            "base_seed_usd": seed,
            "compound_equity_usd": seed,
            "peak_compound_equity_usd": seed,
            "max_drawdown_pct": 0.0,
            "us_commission_rate": DEFAULT_US_COMMISSION_RATE,
            "round_trip_fee_rate_pct": DEFAULT_ROUND_TRIP_FEE_PCT,
            # 일일 세션 상태
            "session_date": now_est.strftime("%Y-%m-%d"),
            "is_session_done": False,
            "session_exit_reason": "",
            "cutoff_0815_no_trade_alert_sent": False,
            # # NEW: 당일 프리장(04:07 ~ 09:29 EST) 진성 지표 박제 슬롯 (장 마감 후 정규장 가격 오염 원천 차단!)
            "today_pre_open_price": 0.0,
            "today_pre_vwap": 0.0,
            "today_prev_reg_close": 0.0,
            # 정찰병 상태 (04:07 ~ 08:14 EST)
            "active_scouts": [],
            "scout_history_today": [],
            "day_scout_seq": 0,
            "prior_scout_wins_today": 0,
            "scout_realized_pnl_today_usd": 0.0,
            "scout1_entry_price": 0.0,
            "scout_min_buy_price": 0.0,
            "scout_ratchet_max_lots": 0,
            "scout_last_exit_price": 0.0,
            "scout_last_buy_ts": 0.0,
            "scout_last_sell_ts": 0.0,
            "scout_last_reentry_eval_ts": 0.0,
            "scout_last_bucket_id": -1,
            "scout_has_active_l1": False,
            # 본대 포지션 상태
            "in_main_position": False,
            "entry_gate_code": "",
            "entry_gate_matched_list": [],
            "entry_price": 0.0,
            "entry_ts": 0.0,
            "entry_hm_str": "",
            "simple_held_qty": 0,
            "comp_held_qty": 0,
            "simple_invested_usd": 0.0,
            "comp_invested_usd": 0.0,
            "cap_500_price": 0.0,
            "arm_100_price": 0.0,
            "floor_100_price": 0.0,
            "is_trail_armed": False,
            "trail_armed_alert_sent": False,
            "peak_price": 0.0,
            "post_entry_min_price": 0.0,
            "nq_entry_price": 0.0,
            "nq_entry_bear_amp_pct": 0.80,
            "live_buy_order_id": "",
            "live_safe_cap_order_id": "",
            "last_modify_order_ts": 0.0,
            "last_modified_target_price": 0.0,
            "last_entry_snapshot": {},
            # 누적 성적표 통계
            "total_trade_days": 0,
            "win_days": 0,
            "loss_days": 0,
            "no_trade_days": 0,
            "premarket_early_win_cnt": 0,
            "cap_500_homerun_cnt": 0,
            "ha_trail_boost_cnt": 0,
            "floor_100_preserve_cnt": 0,
            "vwap_1500_exit_cnt": 0,
            "safety_net_stop_cnt": 0,
            "moc_1559_exit_cnt": 0,
            "simple_cum_net_pnl_usd": 0.0,
            "comp_cum_net_pnl_usd": 0.0,
            "simple_daily_net_pnl_usd": 0.0,
            "comp_daily_net_pnl_usd": 0.0,
            "recent_trade_logs": [],
            "updated_at": now_est.isoformat(),
        }

    def _compute_digest(self, data: Dict[str, Any]) -> str:
        clone = dict(data)
        clone.pop("updated_at", None)
        raw = json.dumps(clone, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _atomic_write_single_path_sync(
        self, filepath: str, payload_bytes: bytes
    ) -> None:
        if os.path.exists(filepath):
            try:
                with open(filepath, "rb") as rf:
                    if rf.read() == payload_bytes:
                        return
            except Exception:
                pass
        tmp_path = f"{filepath}.tmp.{os.getpid()}.{threading.get_ident()}"
        with GlobalThrottle.get_file_lock(filepath):
            try:
                with open(tmp_path, "wb") as wf:
                    wf.write(payload_bytes)
                    wf.flush()
                    os.fsync(wf.fileno())
                os.replace(tmp_path, filepath)
            except OSError as exc:
                if getattr(exc, "errno", None) == 28:
                    emergency_free_disk_space_sync(self.base_dir)
                    with open(tmp_path, "wb") as wf:
                        wf.write(payload_bytes)
                        wf.flush()
                        os.fsync(wf.fileno())
                    os.replace(tmp_path, filepath)
                else:
                    raise
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass

    def _save_sync_unlocked(self, force: bool = False) -> None:
        self._state["execution_mode"] = (
            ASSASSIN_MODE_SIMULATED
            if ASSASSIN_LIVE_ORDER_HARD_LOCK
            else ASSASSIN_MODE_LIVE
        )
        self._state["live_order_hard_lock"] = bool(
            ASSASSIN_LIVE_ORDER_HARD_LOCK
        )
        digest = self._compute_digest(self._state)
        if not force and digest == self._last_saved_digest:
            return
        self._state["updated_at"] = datetime.now(EST_TZ).isoformat()
        payload_bytes = json.dumps(
            self._state, ensure_ascii=False, indent=2
        ).encode("utf-8")
        for path in (self.primary_path, self.compat_path, self.backup_path):
            try:
                self._atomic_write_single_path_sync(path, payload_bytes)
            except Exception as exc:
                logger.warning(f"⚠️ 암살자 원장 저장 실패({path}): {exc}")
        self._last_saved_digest = digest

    def _load_or_init_sync(self) -> None:
        with self._lock:
            candidates: List[Dict[str, Any]] = []
            for p in (self.primary_path, self.compat_path, self.backup_path):
                if os.path.exists(p):
                    try:
                        with GlobalThrottle.get_file_lock(p):
                            with open(p, "r", encoding="utf-8") as rf:
                                obj = json.load(rf)
                                if isinstance(obj, dict):
                                    candidates.append(obj)
                    except Exception:
                        continue
            if candidates:
                best = max(
                    candidates,
                    key=lambda x: (
                        safe_int(x.get("total_trade_days"), 0)
                        + safe_int(x.get("no_trade_days"), 0),
                        safe_int(x.get("day_scout_seq"), 0),
                        safe_float(x.get("base_seed_usd"), 0.0) > 100.0,
                    ),
                )
                merged = self._build_default_state(
                    safe_float(
                        best.get("base_seed_usd"), DEFAULT_INITIAL_SEED_USD
                    )
                )
                merged.update(best)
                if safe_float(merged.get("base_seed_usd"), 0.0) <= 100.0:
                    merged["base_seed_usd"] = DEFAULT_INITIAL_SEED_USD
                if safe_float(merged.get("compound_equity_usd"), 0.0) <= 100.0:
                    merged["compound_equity_usd"] = merged["base_seed_usd"]
                if (
                    safe_float(merged.get("peak_compound_equity_usd"), 0.0)
                    < merged["compound_equity_usd"]
                ):
                    merged["peak_compound_equity_usd"] = merged[
                        "compound_equity_usd"
                    ]
                self._state = merged
            self._save_sync_unlocked(force=True)

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._state)

    def update_state(self, mutator_fn: Any, force_save: bool = False) -> Dict[str, Any]:
        with self._lock:
            mutator_fn(self._state)
            self._save_sync_unlocked(force=force_save)
            return copy.deepcopy(self._state)

    def update_seed_usd(self, new_seed_usd: float) -> Dict[str, Any]:
        val = round(max(100.0, safe_float(new_seed_usd, DEFAULT_INITIAL_SEED_USD)), 2)
        with self._lock:
            old_base = safe_float(self._state.get("base_seed_usd"), val)
            self._state["base_seed_usd"] = val
            if safe_int(self._state.get("total_trade_days"), 0) == 0:
                self._state["compound_equity_usd"] = val
                self._state["peak_compound_equity_usd"] = val
            else:
                diff = val - old_base
                self._state["compound_equity_usd"] = round(
                    max(100.0, safe_float(self._state.get("compound_equity_usd"), val) + diff),
                    2,
                )
                self._state["peak_compound_equity_usd"] = round(
                    max(
                        safe_float(self._state.get("peak_compound_equity_usd"), val),
                        self._state["compound_equity_usd"],
                    ),
                    2,
                )
            self._save_sync_unlocked(force=True)
            return copy.deepcopy(self._state)

    def update_commission_rate(
        self, us_comm_rate: float, rt_fee_pct: float
    ) -> None:
        with self._lock:
            if us_comm_rate > 0.0:
                self._state["us_commission_rate"] = round(float(us_comm_rate), 6)
            if rt_fee_pct > 0.0:
                self._state["round_trip_fee_rate_pct"] = round(
                    float(rt_fee_pct), 4
                )
            self._save_sync_unlocked(force=False)

    def reset_cumulative_stats(self) -> Dict[str, Any]:
        with self._lock:
            base_s = round(
                max(
                    100.0,
                    safe_float(
                        self._state.get("base_seed_usd"),
                        DEFAULT_INITIAL_SEED_USD,
                    ),
                ),
                2,
            )
            self._state["compound_equity_usd"] = base_s
            self._state["peak_compound_equity_usd"] = base_s
            self._state["max_drawdown_pct"] = 0.0
            self._state["total_trade_days"] = 0
            self._state["win_days"] = 0
            self._state["loss_days"] = 0
            self._state["no_trade_days"] = 0
            self._state["premarket_early_win_cnt"] = 0
            self._state["cap_500_homerun_cnt"] = 0
            self._state["ha_trail_boost_cnt"] = 0
            self._state["floor_100_preserve_cnt"] = 0
            self._state["vwap_1500_exit_cnt"] = 0
            self._state["safety_net_stop_cnt"] = 0
            self._state["moc_1559_exit_cnt"] = 0
            self._state["simple_cum_net_pnl_usd"] = 0.0
            self._state["comp_cum_net_pnl_usd"] = 0.0
            self._state["simple_daily_net_pnl_usd"] = 0.0
            self._state["comp_daily_net_pnl_usd"] = 0.0
            self._state["recent_trade_logs"] = []
            self._save_sync_unlocked(force=True)
            return copy.deepcopy(self._state)

    def rollover_daily_session_if_needed(
        self,
        today_str: str,
        initial_seed_fallback: Optional[float] = None,
    ) -> bool:
        with self._lock:
            if (
                initial_seed_fallback is not None
                and initial_seed_fallback > 100.0
                and safe_int(self._state.get("total_trade_days"), 0) == 0
                and abs(
                    safe_float(self._state.get("base_seed_usd"), 0.0)
                    - DEFAULT_INITIAL_SEED_USD
                )
                < 1e-3
            ):
                self._state["base_seed_usd"] = round(
                    float(initial_seed_fallback), 2
                )
                self._state["compound_equity_usd"] = round(
                    float(initial_seed_fallback), 2
                )
                self._state["peak_compound_equity_usd"] = round(
                    float(initial_seed_fallback), 2
                )

            cur_date = str(self._state.get("session_date") or "").strip()
            if cur_date == today_str:
                return False

            self._state["session_date"] = today_str
            self._state["is_session_done"] = False
            self._state["session_exit_reason"] = ""
            self._state["cutoff_0815_no_trade_alert_sent"] = False
            self._state["today_pre_open_price"] = 0.0
            self._state["today_pre_vwap"] = 0.0
            self._state["today_prev_reg_close"] = 0.0
            self._state["active_scouts"] = []
            self._state["scout_history_today"] = []
            self._state["day_scout_seq"] = 0
            self._state["prior_scout_wins_today"] = 0
            self._state["scout_realized_pnl_today_usd"] = 0.0
            self._state["scout1_entry_price"] = 0.0
            self._state["scout_min_buy_price"] = 0.0
            self._state["scout_ratchet_max_lots"] = 0
            self._state["scout_last_exit_price"] = 0.0
            self._state["scout_last_buy_ts"] = 0.0
            self._state["scout_last_sell_ts"] = 0.0
            self._state["scout_last_reentry_eval_ts"] = 0.0
            self._state["scout_last_bucket_id"] = -1
            self._state["scout_has_active_l1"] = False
            self._state["in_main_position"] = False
            self._state["entry_gate_code"] = ""
            self._state["entry_gate_matched_list"] = []
            self._state["entry_price"] = 0.0
            self._state["entry_ts"] = 0.0
            self._state["entry_hm_str"] = ""
            self._state["simple_held_qty"] = 0
            self._state["comp_held_qty"] = 0
            self._state["simple_invested_usd"] = 0.0
            self._state["comp_invested_usd"] = 0.0
            self._state["cap_500_price"] = 0.0
            self._state["arm_100_price"] = 0.0
            self._state["floor_100_price"] = 0.0
            self._state["is_trail_armed"] = False
            self._state["trail_armed_alert_sent"] = False
            self._state["peak_price"] = 0.0
            self._state["post_entry_min_price"] = 0.0
            self._state["nq_entry_price"] = 0.0
            self._state["nq_entry_bear_amp_pct"] = 0.80
            self._state["live_buy_order_id"] = ""
            self._state["live_safe_cap_order_id"] = ""
            self._state["last_modify_order_ts"] = 0.0
            self._state["last_modified_target_price"] = 0.0
            self._state["last_entry_snapshot"] = {}
            self._state["simple_daily_net_pnl_usd"] = 0.0
            self._state["comp_daily_net_pnl_usd"] = 0.0
            self._save_sync_unlocked(force=True)
            return True


def get_or_create_assassin_ledger(context: Any) -> AssassinSimLedger:
    existing = getattr(context, "assassin_ledger", None)
    if isinstance(existing, AssassinSimLedger):
        return existing

    base_dir = getattr(context, "base_dir", None)
    seed_fallback = DEFAULT_INITIAL_SEED_USD
    sniper_ledger = getattr(context, "ledger", None)
    if sniper_ledger is not None and hasattr(sniper_ledger, "get_state"):
        try:
            s_st = sniper_ledger.get_state()
            seed_fallback = safe_float(
                s_st.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD
            )
        except Exception:
            pass

    ledger = AssassinSimLedger(
        base_dir=base_dir, initial_seed_usd=seed_fallback
    )
    try:
        setattr(context, "assassin_ledger", ledger)
    except Exception:
        pass
    return ledger


def sync_assassin_seed_and_fee_from_sniper(
    context: Any, new_seed_usd: Optional[float] = None
) -> None:
    """
    전술 제어반(/settlement)에서 기준 시드머니 변경 또는 계좌 수수료율 갱신 시
    암살자 원장에도 즉시 동기화한다.
    """
    try:
        a_ledger = get_or_create_assassin_ledger(context)
        if new_seed_usd is not None and new_seed_usd > 100.0:
            a_ledger.update_seed_usd(float(new_seed_usd))
        sniper_ledger = getattr(context, "ledger", None)
        if sniper_ledger is not None and hasattr(sniper_ledger, "get_state"):
            s_st = sniper_ledger.get_state()
            us_c = safe_float(
                s_st.get("us_commission_rate"), DEFAULT_US_COMMISSION_RATE
            )
            rt_f = safe_float(
                s_st.get("round_trip_fee_rate_pct"), DEFAULT_ROUND_TRIP_FEE_PCT
            )
            a_ledger.update_commission_rate(us_c, rt_f)
    except Exception as exc:
        logger.warning(f"⚠️ sync_assassin_seed_and_fee_from_sniper 예외: {exc}")


# ===========================================================================
# [핵심 퀀트 1] 10대 진성 게이트 (헌법 G1 ~ G5 + 폭락장 BG1 ~ BG5) 판정 엔진 (Case 93)
# ===========================================================================
def evaluate_10_truth_gates_signal(
    rsi_14: float,
    vs_vwap_pct: float,
    vs_prev_close_pct: float,
    vs_pre_open_pct: float,
    vs_scout1_pct: float,
    prior_scout_wins_today: int,
    is_1m_bull: bool,
    day_scout_seq: int = 2,
) -> Tuple[bool, str, List[str], Dict[str, Any]]:
    """
    🚨 Case 93 : 2번째 이후 정찰병(day_scout_seq >= 2) 타점에서의 10대 진성 게이트(G1~G5 + BG1~BG5) 판정기:
    - G1 (헌법 1) : RSI(14) <= 30.0 AND 전일종가대비 < 0.00% AND 프리시가대비 <= -1.50%
    - G2 (헌법 2) : RSI(14) <= 45.0 AND 프리VWAP괴리율 <= -2.00%
    - G3 (헌법 3) : RSI(14) <= 25.0 AND 프리VWAP괴리율 <= -1.00% AND 당일 정찰 선행익절 >= 1회
    - G4 (헌법 4) : RSI(14) <= 32.0 AND 프리VWAP괴리율 <= -0.50% AND 전일종가대비 <= -1.00% AND 1분봉 양봉(Close >= Open)
    - G5 (헌법 5) : RSI(14) <= 20.0 AND 전일종가대비 >= 0.00%
    - BG1(폭락 1) : 30.0 <= RSI(14) <= 45.0 AND 프리VWAP괴리율 <= -1.00% AND 전일종가대비 <= -6.00% AND 04:07선봉대비 <= -2.00%
    - BG2(폭락 2) : RSI(14) <= 30.0 AND 프리VWAP괴리율 <= -1.00% AND 전일종가대비 <= -3.00% AND 프리시가대비 <= -1.00%
    - BG3(폭락 3) : RSI(14) <= 32.0 AND 프리시가대비 <= -2.50%
    - BG4(폭락 4) : RSI(14) <= 25.0 AND 프리VWAP괴리율 <= -0.50% AND 1분봉 양봉(Close >= Open)
    - BG5(폭락 5) : RSI(14) <= 45.0 AND 프리VWAP괴리율 <= -1.50% AND 전일종가대비 <= -4.00% AND 당일 정찰 선행익절 >= 1회
    """
    seq = safe_int(day_scout_seq, 1)
    if seq < 2:
        return False, "HOLD_SCOUT_SEQ_1_ANCHOR_ONLY", [], {"day_scout_seq": seq}

    rsi = safe_float(rsi_14, 50.0)
    d_vwap = safe_float(vs_vwap_pct, 0.0)
    d_prev = safe_float(vs_prev_close_pct, 0.0)
    d_open = safe_float(vs_pre_open_pct, 0.0)
    d_sc1 = safe_float(vs_scout1_pct, 0.0)
    w_cnt = safe_int(prior_scout_wins_today, 0)
    bull = bool(is_1m_bull)

    matched: List[str] = []

    if rsi <= 30.0 and d_prev < 0.0 and d_open <= -1.50:
        matched.append("G1(헌법1:RSI<=30·전일음봉·프리시가-1.5%↓)")
    if rsi <= 45.0 and d_vwap <= -2.00:
        matched.append("G2(헌법2:RSI<=45·프리VWAP-2.0%↓)")
    if rsi <= 25.0 and d_vwap <= -1.00 and w_cnt >= 1:
        matched.append("G3(헌법3:RSI<=25·VWAP-1.0%↓·선행익절1+)")
    if rsi <= 32.0 and d_vwap <= -0.50 and d_prev <= -1.00 and bull:
        matched.append("G4(헌법4:RSI<=32·VWAP-0.5%↓·전일-1%↓·양봉)")
    if rsi <= 20.0 and d_prev >= 0.0:
        matched.append("G5(헌법5:RSI<=20·전일종가이상강세눌림)")

    if 30.0 <= rsi <= 45.0 and d_vwap <= -1.00 and d_prev <= -6.00 and d_sc1 <= -2.00:
        matched.append("BG1(폭락1:RSI30~45·VWAP-1%↓·전일-6%↓·선봉-2%↓)")
    if rsi <= 30.0 and d_vwap <= -1.00 and d_prev <= -3.00 and d_open <= -1.00:
        matched.append("BG2(폭락2:RSI<=30·VWAP-1%↓·전일-3%↓·프리시가-1%↓)")
    if rsi <= 32.0 and d_open <= -2.50:
        matched.append("BG3(폭락3:RSI<=32·프리시가-2.5%↓급투매)")
    if rsi <= 25.0 and d_vwap <= -0.50 and bull:
        matched.append("BG4(폭락4:RSI<=25·VWAP-0.5%↓·양봉반전)")
    if rsi <= 45.0 and d_vwap <= -1.50 and d_prev <= -4.00 and w_cnt >= 1:
        matched.append("BG5(폭락5:RSI<=45·VWAP-1.5%↓·전일-4%↓·선행익절1+)")

    should_enter = bool(len(matched) > 0)
    primary_code = matched[0].split("(")[0] if matched else "HOLD_NO_GATE_MATCH"
    detail = {
        "rsi_14": rsi,
        "vs_vwap_pct": d_vwap,
        "vs_prev_close_pct": d_prev,
        "vs_pre_open_pct": d_open,
        "vs_scout1_pct": d_sc1,
        "prior_scout_wins_today": w_cnt,
        "is_1m_bull": bull,
        "matched_count": len(matched),
    }
    return should_enter, primary_code, matched, detail
# ===========================================================================
# [핵심 퀀트 2] 08:15 EST 이후 순수 롱 방향성 인지 나스닥 100(QQQ) 3단계 안전망 v2 (Case 93)
# ===========================================================================
def evaluate_directional_3stage_safety_net_v2(
    hm_est: int,
    live_price: float,
    entry_price: float,
    post_entry_min_price: float,
    prev_reg_close: float,
    pre_open_price: float,
    soxl_is_1m_bull: bool,
    soxl_ha_is_bull: bool,
    qqq_live_price: float,
    nq_entry_price: float,
    nq_entry_bear_amp_pct: float,
    qqq_vel_1m_pct: float,
    qqq_vel_3m_pct: float,
    qqq_is_1m_bull: bool,
    qqq_ha_is_bull: bool,
    is_trail_armed: bool = False,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    🚨 Case 93 : 순수 롱 방향성 인지 나스닥 100 선물/QQQ 3단계 안전망 v2 (안전망 상승/지지 중 손절 절대 금지!):
    - 절대 원칙:
      1) 08:15 EST 이전(프리장 골든타임)이거나 이미 +1.00% 트레일링이 점화(is_trail_armed == True)된 경우 작동하지 않는다.
      2) 현재 수익권(live_price >= entry_price)이면 손절하지 않는다.
      3) [방향성 인지 가드 (is_safety_net_rising)]:
         ① SOXL 또는 QQQ 가 현재 1분봉 양봉(is_1m_bull) 또는 하이킨 아시 양봉(ha_is_bull)이거나,
         ② QQQ 직전 1분 변화율(qqq_vel_1m_pct >= 0.0%) 또는 3분 변화율(qqq_vel_3m_pct >= 0.0%)이 양수이거나,
         ③ SOXL 현재가가 전일 정규장 종가(prev_reg_close) 또는 당일 프리장 시가(pre_open_price > 0) 이상이거나,
         ④ 진입 이후 경유 최저가(post_entry_min_price)를 하향 갱신하지 않고 반등 지지(live_price > post_entry_min_price + 1e-4) 중일 때는
         안전망이 상승/지지 중(is_safety_net_rising = True)이므로 수치 조건이 넘더라도 절대로 손절하지 않고 홀딩한다!
      4) 오직 08:15 EST 이후 미점화 손실 구간에서 안전망이 음봉 & 신저가 붕괴 진행 중(is_safety_net_rising == False)이면서:
         - [Stage 2/3 나스닥 역행 가속 칼손절]: QQQ 3분 변화율 <= -0.25% 급락 가속 &
           진입 시점 대비 QQQ 하락률 <= -dyn_qqq_thr_pct (dyn_qqq_thr_pct = min(1.00%, max(nq_entry_bear_amp * 0.5, 0.80%)))
         - [Stage 3 하드 플로어]: SOXL 진입가 대비 수익률 <= -8.00% 붕괴
         시에만 방향성 역행 칼손절을 집행한다!
    """
    hm = safe_int(hm_est, 0)
    lp = safe_float(live_price, 0.0)
    ep = max(0.01, safe_float(entry_price, lp))
    pnl_pct = round(((lp - ep) / ep) * 100.0, 3) if lp > 0.0 else 0.0

    q_lp = safe_float(qqq_live_price, 0.0)
    q_ep = safe_float(nq_entry_price, q_lp)
    qqq_drop_from_entry_pct = (
        round(((q_lp - q_ep) / q_ep) * 100.0, 3)
        if (q_lp > 0.0 and q_ep > 0.0)
        else 0.0
    )
    bear_amp = max(0.40, safe_float(nq_entry_bear_amp_pct, 0.80))
    dyn_qqq_thr_pct = round(min(1.00, max(bear_amp * 0.5, 0.80)), 3)

    if hm < ASSASSIN_CUTOFF_HM or is_trail_armed or pnl_pct >= 0.0:
        return (
            False,
            "HOLD_SAFETY_NET_INACTIVE",
            {
                "is_safety_net_rising": True,
                "pnl_pct": pnl_pct,
                "qqq_drop_from_entry_pct": qqq_drop_from_entry_pct,
                "dyn_qqq_thr_pct": dyn_qqq_thr_pct,
            },
        )

    min_p = safe_float(post_entry_min_price, lp)
    prev_c = safe_float(prev_reg_close, 0.0)
    pre_o = safe_float(pre_open_price, 0.0)
    q_v1 = safe_float(qqq_vel_1m_pct, 0.0)
    q_v3 = safe_float(qqq_vel_3m_pct, 0.0)

    cond_candle_bull = bool(
        soxl_is_1m_bull or soxl_ha_is_bull or qqq_is_1m_bull or qqq_ha_is_bull
    )
    cond_qqq_vel_pos = bool(q_v1 >= 0.0 or q_v3 >= 0.0)
    cond_above_macro_ref = bool(
        (prev_c > 0.0 and lp >= prev_c) or (pre_o > 0.0 and lp >= pre_o)
    )
    cond_holding_above_min = bool(min_p > 0.0 and lp > min_p + 0.01)

    is_safety_net_rising = bool(
        cond_candle_bull
        or cond_qqq_vel_pos
        or cond_above_macro_ref
        or cond_holding_above_min
    )

    detail = {
        "is_safety_net_rising": is_safety_net_rising,
        "cond_candle_bull": cond_candle_bull,
        "cond_qqq_vel_pos": cond_qqq_vel_pos,
        "cond_above_macro_ref": cond_above_macro_ref,
        "cond_holding_above_min": cond_holding_above_min,
        "pnl_pct": pnl_pct,
        "qqq_drop_from_entry_pct": qqq_drop_from_entry_pct,
        "dyn_qqq_thr_pct": dyn_qqq_thr_pct,
        "qqq_vel_1m_pct": q_v1,
        "qqq_vel_3m_pct": q_v3,
    }

    if is_safety_net_rising:
        return False, "HOLD_SAFETY_NET_RISING_GUARD", detail

    # 안전망이 음봉 & 신저가 하락 진행 중일 때만 역행 칼손절 판정
    if (
        q_v3 <= -0.25
        and qqq_drop_from_entry_pct <= -dyn_qqq_thr_pct
        and pnl_pct <= -1.20
    ):
        return True, "EXIT_DIR_3STAGE_QQQ_ACCEL_STOP", detail

    if pnl_pct <= ASSASSIN_HARD_STOP_FLOOR_PCT and q_v3 <= -0.25:
        return True, "EXIT_DIR_3STAGE_HARD_FLOOR_STOP", detail

    return False, "HOLD_SAFETY_NET_MONITORING", detail


# ===========================================================================
# [핵심 퀀트 3] +5% 안전캡 · +1% 점화 HA 트레일링 · 15:00 수익권 VWAP · 15:59 MOC 종합 출구 판정기
# ===========================================================================
def evaluate_assassin_exit_signal(
    hm_est: int,
    live_price: float,
    wick_high_price: float,
    entry_price: float,
    cap_500_price: float,
    arm_100_price: float,
    floor_100_price: float,
    is_trail_armed: bool,
    peak_price: float,
    post_entry_min_price: float,
    regular_vwap: float,
    prev_reg_close: float,
    pre_open_price: float,
    soxl_is_1m_bull: bool,
    soxl_ha_is_bull: bool,
    qqq_metrics: Dict[str, Any],
    nq_entry_price: float,
    nq_entry_bear_amp_pct: float,
) -> Tuple[bool, str, float, bool, float, float, Dict[str, Any]]:
    """
    반환값:
    (should_exit, exit_code, exec_exit_price, new_is_trail_armed, new_peak_price, new_min_price, detail)
    """
    hm = safe_int(hm_est, 0)
    lp = round(max(0.01, safe_float(live_price, 0.0)), 4)
    wh = round(max(lp, safe_float(wick_high_price, lp)), 4)
    ep = round(max(0.01, safe_float(entry_price, lp)), 4)
    cap_p = round(
        safe_float(
            cap_500_price, math.ceil(ep * 1.050 * 100.0 - 1e-9) / 100.0
        ),
        2,
    )
    arm_p = round(
        safe_float(
            arm_100_price, math.ceil(ep * 1.010 * 100.0 - 1e-9) / 100.0
        ),
        2,
    )
    flr_p = round(safe_float(floor_100_price, arm_p), 2)

    cur_peak = round(max(ep, safe_float(peak_price, ep), wh), 4)
    prev_min = safe_float(post_entry_min_price, ep)
    cur_min = round(min(prev_min, lp) if prev_min > 0.0 else lp, 4)
    armed = bool(is_trail_armed or wh >= arm_p)

    # 1. +5.00% 상단 안전 캡 홈런 도달 (최우선 체결)
    if wh >= cap_p:
        exec_p = round(max(cap_p, lp if lp >= cap_p else cap_p), 2)
        return (
            True,
            "EXIT_CAP_500_HOMERUN",
            exec_p,
            True,
            cur_peak,
            cur_min,
            {"exit_type": "CAP_500", "exec_price": exec_p},
        )

    # 2. +1.00% 점화 후 하이킨 아시(HA) 트레일링 & +1.00% 보존선 하드 잠금
    if armed:
        peak_gain_pct = ((cur_peak - ep) / ep) * 100.0
        cb_allow_pct = 0.30 if peak_gain_pct >= 2.00 else 0.20
        cb_trigger_p = round(cur_peak * (1.0 - cb_allow_pct / 100.0), 4)

        # (A) 현재가가 +1.00% 보존선 이하로 밀릴 때 최소 +1.00% 보존선 사수 익절
        if lp <= flr_p:
            exec_p = flr_p
            return (
                True,
                "EXIT_FLOOR_100_PRESERVE",
                exec_p,
                True,
                cur_peak,
                cur_min,
                {"exit_type": "FLOOR_100", "exec_price": exec_p},
            )

        # (B) 최고점 대비 콜백(-0.20% / -0.30%) 도달 시 익절
        if lp <= cb_trigger_p and cur_peak >= round(ep * 1.0120, 4):
            exec_p = round(max(flr_p, lp), 2)
            exit_tag = (
                "EXIT_HA_TRAIL_BOOST"
                if exec_p > flr_p + 0.01
                else "EXIT_FLOOR_100_PRESERVE"
            )
            return (
                True,
                exit_tag,
                exec_p,
                True,
                cur_peak,
                cur_min,
                {"exit_type": exit_tag, "exec_price": exec_p},
            )

        # (C) 하이킨 아시 음봉 전환 (단, QQQ 3분/10분 변화율 >= +0.20% 급등 중일 때는 바이패스 홀딩!)
        q_v3 = safe_float(qqq_metrics.get("vel_3m_pct"), 0.0)
        q_v10 = safe_float(qqq_metrics.get("vel_10m_pct"), 0.0)
        qqq_surging_bypass = bool(q_v3 >= 0.20 or q_v10 >= 0.20)
        if (
            not soxl_ha_is_bull
            and not qqq_surging_bypass
            and lp >= round(ep * 1.0115, 4)
        ):
            exec_p = round(max(flr_p, lp), 2)
            return (
                True,
                "EXIT_HA_TRAIL_BOOST",
                exec_p,
                True,
                cur_peak,
                cur_min,
                {"exit_type": "HA_BEAR_FLIP", "exec_price": exec_p},
            )

    # 3. 15:00 ~ 15:58 EST 오후장 수익권 정규장 VWAP 탈출
    reg_vwap = safe_float(regular_vwap, 0.0)
    if 1500 <= hm <= 1558 and lp > ep * 1.002 and reg_vwap > 0.0 and lp >= reg_vwap:
        exec_p = round(lp, 2)
        return (
            True,
            "EXIT_1500_REG_VWAP_PROFIT",
            exec_p,
            armed,
            cur_peak,
            cur_min,
            {"exit_type": "REG_VWAP_1500", "exec_price": exec_p},
        )

    # 4. 08:15 EST 이후 미점화 손실 구간 방향성 인지 3단계 안전망 v2 검문
    should_stop, stop_code, stop_detail = (
        evaluate_directional_3stage_safety_net_v2(
            hm_est=hm,
            live_price=lp,
            entry_price=ep,
            post_entry_min_price=prev_min,
            prev_reg_close=prev_reg_close,
            pre_open_price=pre_open_price,
            soxl_is_1m_bull=soxl_is_1m_bull,
            soxl_ha_is_bull=soxl_ha_is_bull,
            qqq_live_price=safe_float(qqq_metrics.get("qqq_live_price"), 0.0),
            nq_entry_price=nq_entry_price,
            nq_entry_bear_amp_pct=nq_entry_bear_amp_pct,
            qqq_vel_1m_pct=safe_float(qqq_metrics.get("vel_1m_pct"), 0.0),
            qqq_vel_3m_pct=safe_float(qqq_metrics.get("vel_3m_pct"), 0.0),
            qqq_is_1m_bull=bool(qqq_metrics.get("is_1m_bull", True)),
            qqq_ha_is_bull=bool(qqq_metrics.get("ha_is_bull", True)),
            is_trail_armed=armed,
        )
    )
    if should_stop:
        exec_p = round(lp, 2)
        return (
            True,
            stop_code,
            exec_p,
            armed,
            cur_peak,
            cur_min,
            stop_detail,
        )

    # 5. 15:59 ~ 16:01 EST 무오버나이트 2단계 방탄 MOC 전량 청산
    if hm >= ASSASSIN_MOC_SWEEP_HM:
        exec_p = round(lp, 2)
        return (
            True,
            "EXIT_1559_MOC_NO_OVERNIGHT",
            exec_p,
            armed,
            cur_peak,
            cur_min,
            {"exit_type": "MOC_1559", "exec_price": exec_p},
        )

    return (
        False,
        "HOLD_ASSASSIN_ACTIVE",
        lp,
        armed,
        cur_peak,
        cur_min,
        stop_detail,
    )


# ===========================================================================
# [실시간 4대 지표 추출기] 장 마감 후 프리시가/프리VWAP 정규장 가격 오염 원천 차단
# ===========================================================================
async def _extract_live_assassin_features_and_qqq_snapshot(
    context: Any,
    now_est: Optional[datetime] = None,
    a_ledger: Optional[AssassinSimLedger] = None,
) -> Dict[str, Any]:
    """
    # MODIFIED [Case 93 프리시가/프리VWAP 무오염 정합성 보장]:
    1) SOXL 및 QQQ 실시간 현재가와 1분봉·일봉 지표를 비동기 조회·산출한다.
    2) 당일 프리장(04:07 ~ 09:29 EST) 중에 계측된 실제 pre_open_price 및 premarket_vwap 은
       암살자 원장(today_pre_open_price, today_pre_vwap)에 즉시 박제하여 정규장/장마감 후에도 보존한다.
    3) 만약 장 마감 후(또는 오후장)에 처음 기동되어 원장에도 기록이 없고 1분봉 윈도우에도
       프리장 캔들이 없을 때는, 절대로 정규장 시가($48.70)나 정규VWAP($45.43)로 덮어쓰지 않고
       정확히 0.0 ($0.00 · 0.00%)으로 유지한다!
    """
    dt = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    today_str = dt.strftime("%Y-%m-%d")
    hm = dt.hour * 100 + dt.minute

    if a_ledger is None:
        a_ledger = get_or_create_assassin_ledger(context)
    a_st = a_ledger.get_state()

    api = getattr(context, "api", None)
    soxl_live_p = 0.0
    qqq_live_p = 0.0
    soxl_1m: List[Dict[str, Any]] = []
    soxl_1d: List[Dict[str, Any]] = []
    qqq_1m: List[Dict[str, Any]] = []
    qqq_1d: List[Dict[str, Any]] = []

    if api is not None:
        try:
            prices_map = await api.get_prices([TARGET_SYMBOL, "QQQ"])
            if isinstance(prices_map, dict):
                soxl_live_p = safe_float(prices_map.get(TARGET_SYMBOL), 0.0)
                qqq_live_p = safe_float(prices_map.get("QQQ"), 0.0)
        except Exception:
            pass

        if soxl_live_p <= 0.0 and hasattr(api, "get_live_price"):
            try:
                soxl_live_p = safe_float(
                    await api.get_live_price(TARGET_SYMBOL), 0.0
                )
            except Exception:
                pass

        try:
            soxl_1m = await api.get_candles_1m(
                TARGET_SYMBOL, count=120, total_count=240
            )
        except Exception:
            soxl_1m = []
        try:
            soxl_1d = await api.get_candles_1d(TARGET_SYMBOL, count=10)
        except Exception:
            soxl_1d = []
        try:
            qqq_1m = await api.get_candles_1m("QQQ", count=60, total_count=60)
        except Exception:
            qqq_1m = []
        try:
            qqq_1d = await api.get_candles_1d("QQQ", count=5)
        except Exception:
            qqq_1d = []

    soxl_ind = await asyncio.to_thread(
        compute_1m_indicators_vectorized,
        soxl_1m,
        soxl_1d,
        dt,
        soxl_live_p,
        LOCKED_BUY_INTERVAL_MIN,
        -1,
        "",
        TARGET_SYMBOL,
    )
    qqq_ind = await asyncio.to_thread(
        compute_qqq_macro_metrics_1m,
        qqq_1m,
        qqq_1d,
        qqq_live_p,
        dt,
    )

    # context.candle_metrics_cache["SOXL"] 최신화 (Case 92 연동)
    cache_dict = getattr(context, "candle_metrics_cache", None)
    if isinstance(cache_dict, dict) and soxl_ind.get("valid"):
        cache_dict[TARGET_SYMBOL] = dict(soxl_ind)

    lp = round(safe_float(soxl_ind.get("live_price"), soxl_live_p), 4)
    rsi_14 = round(safe_float(soxl_ind.get("rsi_14"), 50.0), 2)
    if (
        lp > 0.0
        and safe_float(soxl_ind.get("prev_bar_close"), 0.0) > 0.0
    ):
        rsi_14 = compute_realtime_synthetic_rsi(
            live_price=lp,
            prev_bar_close=safe_float(soxl_ind.get("prev_bar_close"), lp),
            prev_avg_gain=safe_float(soxl_ind.get("prev_avg_gain"), 0.0),
            prev_avg_loss=safe_float(soxl_ind.get("prev_avg_loss"), 0.0),
            default_rsi=rsi_14,
        )

    raw_pre_vwap = round(safe_float(soxl_ind.get("premarket_vwap"), 0.0), 4)
    raw_reg_vwap = round(safe_float(soxl_ind.get("regular_vwap"), 0.0), 4)
    raw_prev_close = round(safe_float(soxl_ind.get("prev_reg_close"), 0.0), 4)
    raw_pre_open = round(safe_float(soxl_ind.get("pre_open_price"), 0.0), 4)

    ledger_pre_open = round(
        safe_float(a_st.get("today_pre_open_price"), 0.0), 4
    )
    ledger_pre_vwap = round(safe_float(a_st.get("today_pre_vwap"), 0.0), 4)
    ledger_prev_close = round(
        safe_float(a_st.get("today_prev_reg_close"), 0.0), 4
    )
    scout1_p = round(safe_float(a_st.get("scout1_entry_price"), 0.0), 4)

    # 당일 프리장(04:07 ~ 09:29 EST) 중 계측값 또는 선봉 정찰병(#1) 진입가가 있으면 원장에 영속 박제
    eff_pre_open = raw_pre_open
    if eff_pre_open <= 0.0:
        if ledger_pre_open > 0.0:
            eff_pre_open = ledger_pre_open
        elif scout1_p > 0.0:
            eff_pre_open = scout1_p
        elif 407 <= hm <= 929 and lp > 0.0:
            eff_pre_open = lp
        else:
            eff_pre_open = 0.0

    eff_pre_vwap = raw_pre_vwap
    if eff_pre_vwap <= 0.0:
        if ledger_pre_vwap > 0.0:
            eff_pre_vwap = ledger_pre_vwap
        elif 407 <= hm <= 929 and lp > 0.0:
            eff_pre_vwap = lp
        else:
            eff_pre_vwap = 0.0

    eff_prev_close = (
        raw_prev_close if raw_prev_close > 0.0 else ledger_prev_close
    )

    if (
        (eff_pre_open > 0.0 and abs(eff_pre_open - ledger_pre_open) > 1e-4)
        or (eff_pre_vwap > 0.0 and abs(eff_pre_vwap - ledger_pre_vwap) > 1e-4)
        or (
            eff_prev_close > 0.0
            and abs(eff_prev_close - ledger_prev_close) > 1e-4
        )
    ):
        def _latch_premarket_refs(st: Dict[str, Any]) -> None:
            if eff_pre_open > 0.0:
                st["today_pre_open_price"] = eff_pre_open
            if eff_pre_vwap > 0.0:
                st["today_pre_vwap"] = eff_pre_vwap
            if eff_prev_close > 0.0:
                st["today_prev_reg_close"] = eff_prev_close

        await asyncio.to_thread(a_ledger.update_state, _latch_premarket_refs)

    vs_vwap_pct = (
        round(((lp - eff_pre_vwap) / eff_pre_vwap) * 100.0, 2)
        if (lp > 0.0 and eff_pre_vwap > 0.0)
        else 0.0
    )
    vs_reg_vwap_pct = (
        round(((lp - raw_reg_vwap) / raw_reg_vwap) * 100.0, 2)
        if (lp > 0.0 and raw_reg_vwap > 0.0)
        else 0.0
    )
    vs_prev_close_pct = (
        round(((lp - eff_prev_close) / eff_prev_close) * 100.0, 2)
        if (lp > 0.0 and eff_prev_close > 0.0)
        else 0.0
    )
    vs_pre_open_pct = (
        round(((lp - eff_pre_open) / eff_pre_open) * 100.0, 2)
        if (lp > 0.0 and eff_pre_open > 0.0)
        else 0.0
    )
    vs_scout1_pct = (
        round(((lp - scout1_p) / scout1_p) * 100.0, 2)
        if (lp > 0.0 and scout1_p > 0.0)
        else vs_pre_open_pct
    )

    return {
        "valid": bool(lp > 0.0),
        "live_price": lp,
        "rsi_14": rsi_14,
        "pre_vwap": eff_pre_vwap,
        "vs_vwap_pct": vs_vwap_pct,
        "regular_vwap": raw_reg_vwap,
        "vs_reg_vwap_pct": vs_reg_vwap_pct,
        "prev_reg_close": eff_prev_close,
        "vs_prev_close_pct": vs_prev_close_pct,
        "pre_open_price": eff_pre_open,
        "vs_pre_open_pct": vs_pre_open_pct,
        "vs_scout1_pct": vs_scout1_pct,
        "is_1m_bull": bool(soxl_ind.get("is_1m_bull", True)),
        "ha_is_bull": bool(soxl_ind.get("ha_is_bull", True)),
        "cur_buy_bucket_id": safe_int(soxl_ind.get("cur_buy_bucket_id"), -1),
        "qqq": qqq_ind,
    }


# ===========================================================================
# [Dual-Ready 주문 어댑터] ASSASSIN_LIVE_ORDER_HARD_LOCK == True 시 모의 체결, False 시 토스 Open API 실전 발주
# ===========================================================================
async def _dispatch_assassin_buy_order(
    context: Any,
    qty: int,
    limit_price: float,
) -> Tuple[bool, str, float, int]:
    order_p = round(max(1.0, float(limit_price)), 2)
    order_q = max(1, int(qty))
    if ASSASSIN_LIVE_ORDER_HARD_LOCK:
        sim_oid = f"SIM-BUY-{uuid.uuid4().hex[:12].upper()}"
        return True, sim_oid, order_p, order_q

    api = getattr(context, "api", None)
    if api is None or TARGET_SYMBOL not in REAL_ALLOWED_SYMBOLS:
        return False, "", order_p, 0
    client_oid = f"ASN-B-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"[:36]
    res = await api.create_order(
        symbol=TARGET_SYMBOL,
        side="BUY",
        order_type="LIMIT",
        quantity=order_q,
        price=order_p,
        client_order_id=client_oid,
        enforce_daymarket_block=True,
    )
    oid = str((res or {}).get("orderId") or "").strip()
    return bool(oid), oid, order_p, order_q


async def _dispatch_assassin_safe_cap_sell_order(
    context: Any,
    qty: int,
    cap_price: float,
) -> Tuple[bool, str]:
    order_p = round(max(1.0, float(cap_price)), 2)
    order_q = max(1, int(qty))
    if ASSASSIN_LIVE_ORDER_HARD_LOCK:
        sim_oid = f"SIM-CAP-{uuid.uuid4().hex[:12].upper()}"
        return True, sim_oid

    api = getattr(context, "api", None)
    if api is None:
        return False, ""
    client_oid = f"ASN-C-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"[:36]
    res = await api.create_order(
        symbol=TARGET_SYMBOL,
        side="SELL",
        order_type="LIMIT",
        quantity=order_q,
        price=order_p,
        client_order_id=client_oid,
        enforce_daymarket_block=False,
    )
    oid = str((res or {}).get("orderId") or "").strip()
    return bool(oid), oid


async def _dispatch_assassin_exit_sweep_order(
    context: Any,
    existing_cap_order_id: str,
    qty: int,
    target_exit_price: float,
    is_moc: bool = False,
) -> Tuple[bool, str, float]:
    """
    실전(LIVE) 모드 시 선장전된 +5% 안전캡 매도 주문을 POST /api/v1/orders/{orderId}/modify
    (US 주식 규격: quantity 필드 미포함, {"orderType": "LIMIT", "price": str(new_price)})로 즉시 가격 정정 스윕하거나,
    15:59 MOC 시 선취소 후 즉시 체결 지정가로 2단계 방탄 청산한다.
    """
    sweep_p = round(max(1.0, float(target_exit_price)), 2)
    if ASSASSIN_LIVE_ORDER_HARD_LOCK:
        sim_oid = f"SIM-EXIT-{uuid.uuid4().hex[:10].upper()}"
        return True, sim_oid, sweep_p

    api = getattr(context, "api", None)
    if api is None:
        return False, "", sweep_p

    if existing_cap_order_id and not is_moc:
        try:
            mod_res = await api.modify_order(
                order_id=existing_cap_order_id,
                new_price=sweep_p,
                order_type="LIMIT",
            )
            new_oid = str(
                (mod_res or {}).get("orderId") or existing_cap_order_id
            ).strip()
            return True, new_oid, sweep_p
        except Exception as exc:
            logger.warning(f"⚠️ 암살자 modify_order 폴백 전환: {exc}")

    if existing_cap_order_id:
        try:
            await api.cancel_order(existing_cap_order_id)
            await asyncio.sleep(0.20)
        except Exception:
            pass

    client_oid = f"ASN-X-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"[:36]
    res = await api.create_order(
        symbol=TARGET_SYMBOL,
        side="SELL",
        order_type="LIMIT",
        quantity=max(1, int(qty)),
        price=sweep_p,
        client_order_id=client_oid,
        enforce_daymarket_block=False,
    )
    oid = str((res or {}).get("orderId") or "").strip()
    return bool(oid), oid, sweep_p


# ===========================================================================
# [5대 라이프사이클 실시간 텔레그램 푸시 알림] (_send_1 ~ _send_5)
# ===========================================================================
async def _send_assassin_telegram_push(context: Any, text: str) -> None:
    send_fn = getattr(context, "send_telegram_message", None)
    if callable(send_fn):
        try:
            await send_fn(text)
            return
        except Exception:
            pass
    tg_ui = getattr(context, "tg_ui", None)
    if tg_ui is not None and hasattr(tg_ui, "send_slim_alert"):
        try:
            await tg_ui.send_slim_alert(text)
        except Exception:
            pass


async def _send_1_scout_dispatched_alert(
    context: Any,
    scout: IndependentScoutUnit,
    active_tier_cnt: int,
    prior_wins: int,
    gate_eval_msg: str,
) -> None:
    pre_v_str = (
        f"${scout.pre_vwap:.2f}({scout.vs_vwap_pct:+.2f}%)"
        if scout.pre_vwap > 0.0
        else "$0.00(0.00%)"
    )
    pre_o_str = (
        f"${scout.pre_open_price:.2f}({scout.vs_pre_open_pct:+.2f}%)"
        if scout.pre_open_price > 0.0
        else "$0.00(0.00%)"
    )
    msg = (
        f"🕵️ <b>[[모의] 암살자 정찰병 #{scout.scout_seq} 파견 ({scout.entry_hm_str} EST)]</b>\n"
        f"• 타점사유: <code>{html.escape(scout.trigger_tag)}</code> (정찰 {active_tier_cnt}/{ASSASSIN_SCOUT_MAX_TIERS}층 · 선행익절 {prior_wins}회)\n"
        f"• 정찰매수: <b>1주 @ ${scout.entry_price:.2f}</b> ➔ 목표(+1.0%): <b>${scout.target_price:.2f}</b>\n"
        f"📊 <b>[정찰 시점 4대 핵심 지표]</b>\n"
        f"① RSI(14): <b>{scout.rsi_14:.1f}</b> | ② 프리VWAP: <b>{pre_v_str}</b>\n"
        f"③ 전일종가: <b>${scout.prev_reg_close:.2f}({scout.vs_prev_close_pct:+.2f}%)</b> | ④ 프리시가: <b>{pre_o_str}</b>\n"
        f"• 게이트판정: <code>{html.escape(gate_eval_msg)}</code>"
    )
    await _send_assassin_telegram_push(context, msg)


async def _send_2_cutoff_0815_no_trade_alert(
    context: Any, a_st: Dict[str, Any]
) -> None:
    sc_cnt = safe_int(a_st.get("day_scout_seq"), 0)
    sc_wins = safe_int(a_st.get("prior_scout_wins_today"), 0)
    msg = (
        f"🏠 <b>[[모의] 암살자 08:15 EST 무매매 안전 퇴근]</b>\n"
        f"• 04:07 ~ 08:14 EST 골든타임 동안 총 <b>{sc_cnt}명</b> 정찰(선행익절 {sc_wins}회)을 수행했으나,\n"
        f"  <b>10대 진성 게이트(G1~G5 · BG1~BG5)</b> 조건에 도달하지 않아 거시지표 리스크 회피를 위해 무매매 퇴근합니다.\n"
        f"• 익일 04:07 EST 프리장 개장 시 선봉 정찰병(#1)이 자동 재출격합니다."
    )
    await _send_assassin_telegram_push(context, msg)


async def _send_3_truth_gate_entry_alert(
    context: Any,
    a_st: Dict[str, Any],
    matched_gates: List[str],
    feat: Dict[str, Any],
) -> None:
    ep = safe_float(a_st.get("entry_price"), 0.0)
    cap_p = safe_float(a_st.get("cap_500_price"), 0.0)
    arm_p = safe_float(a_st.get("arm_100_price"), 0.0)
    s_qty = safe_int(a_st.get("simple_held_qty"), 0)
    c_qty = safe_int(a_st.get("comp_held_qty"), 0)
    gates_str = " · ".join(matched_gates)
    msg = (
        f"🗡️ <b>[[모의] 암살자 진성 게이트 포착 & 본대 100% 진입!]</b>\n"
        f"• 격발게이트: <b>{html.escape(gates_str)}</b>\n"
        f"• 진입단가: <b>${ep:.2f}</b> (단리 <b>{s_qty}주</b> / 복리 <b>{c_qty}주</b>)\n"
        f"• 선장전 안전캡(+5.0%): <b>${cap_p:.2f}</b> | 트레일링 점화가(+1.0%): <b>${arm_p:.2f}</b>\n"
        f"📊 <b>[진입 스냅샷]</b> RSI <b>{safe_float(feat.get('rsi_14'), 50.0):.1f}</b> · "
        f"프리VWAP <b>{safe_float(feat.get('vs_vwap_pct'), 0.0):+.2f}%</b> · "
        f"전일대비 <b>{safe_float(feat.get('vs_prev_close_pct'), 0.0):+.2f}%</b> · "
        f"프리시가대비 <b>{safe_float(feat.get('vs_pre_open_pct'), 0.0):+.2f}%</b>"
    )
    await _send_assassin_telegram_push(context, msg)


async def _send_4_trail_armed_alert(
    context: Any, a_st: Dict[str, Any], live_p: float
) -> None:
    ep = safe_float(a_st.get("entry_price"), 0.0)
    flr_p = safe_float(a_st.get("floor_100_price"), 0.0)
    cap_p = safe_float(a_st.get("cap_500_price"), 0.0)
    gain_pct = ((live_p - ep) / max(0.01, ep)) * 100.0
    msg = (
        f"🔥 <b>[[모의] 암살자 +1.00% 도달 & 0.40초 HA 트레일링 점화!]</b>\n"
        f"• 진입가: <b>${ep:.2f}</b> ➔ 현재가: <b>${live_p:.2f} ({gain_pct:+.2f}%)</b>\n"
        f"• 최소 익절 보존선: <b>${flr_p:.2f} (+1.00% 하드 잠금 완료)</b> | 상단캡: <b>${cap_p:.2f}</b>\n"
        f"• 하이킨 아시(HA) 양봉 추종 고주파(0.40s) 스윕 모드로 전환되었습니다."
    )
    await _send_assassin_telegram_push(context, msg)


async def _send_5_exit_complete_alert(
    context: Any,
    a_st: Dict[str, Any],
    exit_code: str,
    exit_price: float,
    simple_net_pnl: float,
    comp_net_pnl: float,
    pnl_pct: float,
) -> None:
    ep = safe_float(a_st.get("entry_price"), 0.0)
    gate_c = str(a_st.get("entry_gate_code") or "G")
    tot_days = safe_int(a_st.get("total_trade_days"), 0)
    wins = safe_int(a_st.get("win_days"), 0)
    losses = safe_int(a_st.get("loss_days"), 0)
    win_rate = (wins / tot_days * 100.0) if tot_days > 0 else 100.0
    s_cum = safe_float(a_st.get("simple_cum_net_pnl_usd"), 0.0)
    c_cum = safe_float(a_st.get("comp_cum_net_pnl_usd"), 0.0)
    c_eq = safe_float(a_st.get("compound_equity_usd"), 0.0)
    mdd = safe_float(a_st.get("max_drawdown_pct"), 0.0)

    msg = (
        f"🎯 <b>[[모의] 암살자 당일 청산 퇴근 완료 ({html.escape(exit_code)})]</b>\n"
        f"• 진입({html.escape(gate_c)}): <b>${ep:.2f}</b> ➔ 청산: <b>${exit_price:.2f} ({pnl_pct:+.2f}%)</b>\n"
        f"• 금일 세후손익: 단리 <b>{simple_net_pnl:+.2f}$</b> | 복리 <b>{comp_net_pnl:+.2f}$</b> (오버나이트 0주)\n"
        f"🏆 <b>[[모의] 암살자 누적 성적표]</b>\n"
        f"• 전적: <b>{tot_days}전 {wins}승 {losses}패 (승률 {win_rate:.2f}%)</b>\n"
        f"• 💵 단리 누적순익: <b>{s_cum:+.2f}$</b>\n"
        f"• 📈 복리 누적순익: <b>{c_cum:+.2f}$</b> (복리자산 <b>${c_eq:,.2f}</b> · MDD <b>{mdd:.2f}%</b>)"
    )
    await _send_assassin_telegram_push(context, msg)


# ===========================================================================
# [메인 틱 오케스트레이터] 스나이퍼 ON/OFF 및 보유 수량과 무관하게 상시 가동 (Case 93)
# ===========================================================================
async def execute_simulated_assassin_tick_plugin(
    context: Any,
    now_est: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    main.py 의 main_sniper_loop() 최상단에서 매 틱 호출된다.
    - 평일 04:07 ~ 16:01 EST 구간에서 작동하며, 주말 휴장이나 당일 세션 퇴근 완료(is_session_done == True) 시 즉시 반환한다.
    """
    dt = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    if is_weekend_nyse_closed(dt) or dt.weekday() >= 5:
        setattr(context, "assassin_high_freq_active", False)
        return {"status": "WEEKEND_CLOSED"}

    today_str = dt.strftime("%Y-%m-%d")
    hm = dt.hour * 100 + dt.minute
    now_ts = time.time()

    a_ledger = get_or_create_assassin_ledger(context)
    await asyncio.to_thread(
        a_ledger.rollover_daily_session_if_needed, today_str
    )

    if hm < ASSASSIN_SCOUT_START_HM or hm > 1605:
        setattr(context, "assassin_high_freq_active", False)
        return {"status": "OUTSIDE_ASSASSIN_HOURS", "hm": hm}

    a_st = a_ledger.get_state()
    if bool(a_st.get("is_session_done", False)):
        setattr(context, "assassin_high_freq_active", False)
        return {
            "status": "SESSION_ALREADY_DONE",
            "reason": a_st.get("session_exit_reason", ""),
        }

    feat = await _extract_live_assassin_features_and_qqq_snapshot(
        context, dt, a_ledger
    )
    lp = safe_float(feat.get("live_price"), 0.0)
    if lp <= 0.0:
        return {"status": "NO_LIVE_PRICE"}

    # ------------------------------------------------------------------
    # 분기 A: 본대 포지션 보유 중 (in_main_position == True) ➔ 익절/안전망/MOC 감시
    # ------------------------------------------------------------------
    if bool(a_st.get("in_main_position", False)):
        entry_ts = safe_float(a_st.get("entry_ts"), 0.0)
        if (now_ts - entry_ts) < ASSASSIN_POST_FILL_SHIELD_SEC and hm < ASSASSIN_MOC_SWEEP_HM:
            return {"status": "HOLD_POST_BUY_60S_SHIELD"}

        wick_high_p = lp
        api = getattr(context, "api", None)
        arm_p = safe_float(a_st.get("arm_100_price"), lp * 1.01)
        if (
            api is not None
            and hasattr(api, "get_recent_wick_high_price")
            and lp >= arm_p * 0.975
        ):
            try:
                wh_val, _ = await api.get_recent_wick_high_price(
                    symbol=TARGET_SYMBOL,
                    lookback_sec=5.0,
                    min_after_ts=entry_ts,
                )
                if wh_val > wick_high_p:
                    wick_high_p = wh_val
            except Exception:
                pass

        (
            should_exit,
            exit_code,
            exec_exit_p,
            new_armed,
            new_peak,
            new_min,
            exit_detail,
        ) = evaluate_assassin_exit_signal(
            hm_est=hm,
            live_price=lp,
            wick_high_price=wick_high_p,
            entry_price=safe_float(a_st.get("entry_price"), lp),
            cap_500_price=safe_float(a_st.get("cap_500_price"), lp * 1.05),
            arm_100_price=arm_p,
            floor_100_price=safe_float(a_st.get("floor_100_price"), arm_p),
            is_trail_armed=bool(a_st.get("is_trail_armed", False)),
            peak_price=safe_float(a_st.get("peak_price"), lp),
            post_entry_min_price=safe_float(
                a_st.get("post_entry_min_price"), lp
            ),
            regular_vwap=safe_float(feat.get("regular_vwap"), 0.0),
            prev_reg_close=safe_float(feat.get("prev_reg_close"), 0.0),
            pre_open_price=safe_float(feat.get("pre_open_price"), 0.0),
            soxl_is_1m_bull=bool(feat.get("is_1m_bull", True)),
            soxl_ha_is_bull=bool(feat.get("ha_is_bull", True)),
            qqq_metrics=feat.get("qqq", {}),
            nq_entry_price=safe_float(a_st.get("nq_entry_price"), 0.0),
            nq_entry_bear_amp_pct=safe_float(
                a_st.get("nq_entry_bear_amp_pct"), 0.80
            ),
        )

        setattr(context, "assassin_high_freq_active", bool(new_armed and not should_exit))

        # +1.00% 최초 점화 시 알림 ④ 발송
        if (
            new_armed
            and not bool(a_st.get("trail_armed_alert_sent", False))
            and not should_exit
        ):
            def _mark_armed(st: Dict[str, Any]) -> None:
                st["is_trail_armed"] = True
                st["trail_armed_alert_sent"] = True
                st["peak_price"] = new_peak
                st["post_entry_min_price"] = new_min

            updated_st = await asyncio.to_thread(
                a_ledger.update_state, _mark_armed, True
            )
            await _send_4_trail_armed_alert(context, updated_st, max(lp, wick_high_p))
            return {"status": "TRAIL_ARMED", "peak_price": new_peak}

        if not should_exit:
            def _upd_track(st: Dict[str, Any]) -> None:
                st["is_trail_armed"] = bool(new_armed)
                st["peak_price"] = new_peak
                st["post_entry_min_price"] = new_min

            await asyncio.to_thread(a_ledger.update_state, _upd_track, False)
            return {"status": "HOLD_MAIN_POSITION", "peak_price": new_peak}

        # 출구 조건 도달 ➔ 청산 스윕 및 성적표 커밋 후 알림 ⑤ 발송
        is_moc_flag = bool("MOC" in exit_code)
        _, _, final_exit_p = await _dispatch_assassin_exit_sweep_order(
            context=context,
            existing_cap_order_id=str(
                a_st.get("live_safe_cap_order_id") or ""
            ),
            qty=safe_int(a_st.get("comp_held_qty"), 1),
            target_exit_price=exec_exit_p,
            is_moc=is_moc_flag,
        )

        rt_fee_pct = resolve_effective_round_trip_fee_rate_pct(
            safe_float(
                a_st.get("round_trip_fee_rate_pct"), DEFAULT_ROUND_TRIP_FEE_PCT
            )
        )
        fee_ratio = rt_fee_pct / 100.0
        ep_val = max(0.01, safe_float(a_st.get("entry_price"), final_exit_p))
        s_qty = max(1, safe_int(a_st.get("simple_held_qty"), 1))
        c_qty = max(1, safe_int(a_st.get("comp_held_qty"), 1))

        s_gross = (final_exit_p - ep_val) * s_qty
        s_fee = (ep_val * s_qty + final_exit_p * s_qty) * (fee_ratio * 0.5)
        s_net = round(s_gross - s_fee, 2)

        c_gross = (final_exit_p - ep_val) * c_qty
        c_fee = (ep_val * c_qty + final_exit_p * c_qty) * (fee_ratio * 0.5)
        c_net = round(c_gross - c_fee, 2)
        pnl_pct = round(((final_exit_p - ep_val) / ep_val) * 100.0, 2)

        def _commit_exit(st: Dict[str, Any]) -> None:
            st["in_main_position"] = False
            st["is_session_done"] = True
            st["session_exit_reason"] = exit_code
            st["total_trade_days"] = safe_int(st.get("total_trade_days"), 0) + 1
            if s_net >= 0.0:
                st["win_days"] = safe_int(st.get("win_days"), 0) + 1
            else:
                st["loss_days"] = safe_int(st.get("loss_days"), 0) + 1

            if hm < ASSASSIN_CUTOFF_HM and s_net > 0.0:
                st["premarket_early_win_cnt"] = (
                    safe_int(st.get("premarket_early_win_cnt"), 0) + 1
                )

            if "CAP_500" in exit_code:
                st["cap_500_homerun_cnt"] = (
                    safe_int(st.get("cap_500_homerun_cnt"), 0) + 1
                )
            elif "HA_TRAIL_BOOST" in exit_code:
                st["ha_trail_boost_cnt"] = (
                    safe_int(st.get("ha_trail_boost_cnt"), 0) + 1
                )
            elif "FLOOR_100" in exit_code:
                st["floor_100_preserve_cnt"] = (
                    safe_int(st.get("floor_100_preserve_cnt"), 0) + 1
                )
            elif "REG_VWAP" in exit_code:
                st["vwap_1500_exit_cnt"] = (
                    safe_int(st.get("vwap_1500_exit_cnt"), 0) + 1
                )
            elif "DIR_3STAGE" in exit_code:
                st["safety_net_stop_cnt"] = (
                    safe_int(st.get("safety_net_stop_cnt"), 0) + 1
                )
            elif "MOC" in exit_code:
                st["moc_1559_exit_cnt"] = (
                    safe_int(st.get("moc_1559_exit_cnt"), 0) + 1
                )

            st["simple_daily_net_pnl_usd"] = s_net
            st["comp_daily_net_pnl_usd"] = c_net
            st["simple_cum_net_pnl_usd"] = round(
                safe_float(st.get("simple_cum_net_pnl_usd"), 0.0) + s_net, 2
            )
            st["comp_cum_net_pnl_usd"] = round(
                safe_float(st.get("comp_cum_net_pnl_usd"), 0.0) + c_net, 2
            )
            new_comp_eq = round(
                max(
                    100.0,
                    safe_float(
                        st.get("compound_equity_usd"),
                        safe_float(st.get("base_seed_usd"), DEFAULT_INITIAL_SEED_USD),
                    )
                    + c_net,
                ),
                2,
            )
            st["compound_equity_usd"] = new_comp_eq
            peak_eq = max(
                safe_float(st.get("peak_compound_equity_usd"), new_comp_eq),
                new_comp_eq,
            )
            st["peak_compound_equity_usd"] = round(peak_eq, 2)
            if peak_eq > 0.0:
                dd_pct = round(((new_comp_eq - peak_eq) / peak_eq) * 100.0, 2)
                st["max_drawdown_pct"] = round(
                    min(safe_float(st.get("max_drawdown_pct"), 0.0), dd_pct), 2
                )

            logs = list(st.get("recent_trade_logs") or [])
            logs.append(
                {
                    "date": today_str,
                    "gate": st.get("entry_gate_code", ""),
                    "entry_price": ep_val,
                    "exit_price": final_exit_p,
                    "exit_code": exit_code,
                    "pnl_pct": pnl_pct,
                    "simple_net_usd": s_net,
                    "comp_net_usd": c_net,
                }
            )
            st["recent_trade_logs"] = logs[-30:]

        setattr(context, "assassin_high_freq_active", False)
        final_st = await asyncio.to_thread(
            a_ledger.update_state, _commit_exit, True
        )
        await _send_5_exit_complete_alert(
            context,
            final_st,
            exit_code,
            final_exit_p,
            s_net,
            c_net,
            pnl_pct,
        )
        return {"status": "EXITED_AND_DONE", "exit_code": exit_code}

    # ------------------------------------------------------------------
    # 분기 B: 본대 미진입 상태에서 08:15 EST 도달 ➔ 무매매 안전 퇴근 (알림 ②)
    # ------------------------------------------------------------------
    if hm >= ASSASSIN_CUTOFF_HM:
        setattr(context, "assassin_high_freq_active", False)
        already_sent = bool(a_st.get("cutoff_0815_no_trade_alert_sent", False))

        def _mark_no_trade_done(st: Dict[str, Any]) -> None:
            st["is_session_done"] = True
            st["session_exit_reason"] = "0815_NO_TRADE_SAFE_OFFWORK"
            st["cutoff_0815_no_trade_alert_sent"] = True
            st["active_scouts"] = []
            st["no_trade_days"] = safe_int(st.get("no_trade_days"), 0) + 1

        updated_st = await asyncio.to_thread(
            a_ledger.update_state, _mark_no_trade_done, True
        )
        # 실제 정찰을 수행하다가 08:15 EST 에 도달한 경우에만 무매매 퇴근 푸시 발송
        if not already_sent and safe_int(updated_st.get("day_scout_seq"), 0) > 0:
            await _send_2_cutoff_0815_no_trade_alert(context, updated_st)
        return {"status": "CUTOFF_0815_NO_TRADE_OFFWORK"}

    # ------------------------------------------------------------------
    # 분기 C: 04:07 ~ 08:14 EST 프리장 골든타임 ➔ 1주 독립 정찰병 운용 & 10대 진성 게이트 스캔
    # ------------------------------------------------------------------
    raw_scouts = list(a_st.get("active_scouts") or [])
    scouts: List[IndependentScoutUnit] = [
        IndependentScoutUnit.from_dict(x)
        for x in raw_scouts
        if isinstance(x, dict)
    ]
    day_seq = safe_int(a_st.get("day_scout_seq"), 0)
    prior_wins = safe_int(a_st.get("prior_scout_wins_today"), 0)
    has_l1 = bool(a_st.get("scout_has_active_l1", False)) and len(scouts) > 0
    last_buy_ts = safe_float(a_st.get("scout_last_buy_ts"), 0.0)
    last_sell_ts = safe_float(a_st.get("scout_last_sell_ts"), 0.0)

    # C-1. 보유 중인 독립 정찰병들의 개별 +1.00% 익절 스캔 (매수 후 60초 타임쉴드 적용)
    if scouts and (now_ts - last_buy_ts) >= ASSASSIN_POST_FILL_SHIELD_SEC:
        rem_scouts: List[IndependentScoutUnit] = []
        sold_any = False
        sold_l1 = False
        last_exit_p = safe_float(a_st.get("scout_last_exit_price"), lp)
        pnl_add = 0.0

        for idx_s, sc in enumerate(scouts):
            if (now_ts - sc.entry_ts) >= ASSASSIN_POST_FILL_SHIELD_SEC and lp >= sc.target_price:
                sold_any = True
                if idx_s == 0 and has_l1:
                    sold_l1 = True
                prior_wins += 1
                last_exit_p = lp
                pnl_add += round(lp - sc.entry_price, 4)
            else:
                rem_scouts.append(sc)

        if sold_any:
            for idx_r, r_sc in enumerate(rem_scouts):
                r_sc.tier_idx = idx_r + 1

            def _commit_scout_sell(st: Dict[str, Any]) -> None:
                st["active_scouts"] = [x.to_dict() for x in rem_scouts]
                st["prior_scout_wins_today"] = prior_wins
                st["scout_realized_pnl_today_usd"] = round(
                    safe_float(st.get("scout_realized_pnl_today_usd"), 0.0)
                    + pnl_add,
                    4,
                )
                st["scout_last_exit_price"] = round(last_exit_p, 4)
                st["scout_last_sell_ts"] = now_ts
                if len(rem_scouts) == 0:
                    st["scout_has_active_l1"] = False
                    st["scout_min_buy_price"] = 0.0
                    st["scout_ratchet_max_lots"] = 0
                elif sold_l1:
                    st["scout_has_active_l1"] = False

            await asyncio.to_thread(
                a_ledger.update_state, _commit_scout_sell, True
            )
            return {"status": "SCOUT_PROFIT_TAKEN", "prior_wins": prior_wins}

    # C-2. 신규/후속 정찰병 파견 조건 판정
    if (now_ts - max(last_buy_ts, last_sell_ts)) < ASSASSIN_POST_FILL_SHIELD_SEC:
        return {"status": "HOLD_SCOUT_60S_SHIELD"}

    should_dispatch_scout = False
    scout_trigger_tag = ""
    cur_bucket_id = safe_int(feat.get("cur_buy_bucket_id"), -1)
    last_bucket_id = safe_int(a_st.get("scout_last_bucket_id"), -1)

    if day_seq == 0:
        should_dispatch_scout = True
        scout_trigger_tag = "01_OPEN_0407"
    elif len(scouts) == 0:
        should_dispatch_scout = True
        scout_trigger_tag = "01_REENTRY_ZERO_1FL"
    elif not has_l1:
        # 1층 공석 시 60초 주기 -1.00% 무필터 눌림목 / +1.00% & RSI<=50 돌파 (2층 단가 이하 역전 차단)
        last_re_ts = safe_float(a_st.get("scout_last_reentry_eval_ts"), 0.0)
        if (now_ts - last_re_ts) >= ASSASSIN_POST_FILL_SHIELD_SEC:
            l2_p = scouts[0].entry_price
            ref_exit_p = max(
                0.01, safe_float(a_st.get("scout_last_exit_price"), l2_p)
            )
            chg_exit = ((lp - ref_exit_p) / ref_exit_p) * 100.0
            if lp <= l2_p + 1e-6:
                if chg_exit <= ASSASSIN_SCOUT_PULL_PCT:
                    should_dispatch_scout = True
                    scout_trigger_tag = "02_PULL_1PCT_NOFILT"
                elif (
                    chg_exit >= ASSASSIN_SCOUT_BRK_PCT
                    and safe_float(feat.get("rsi_14"), 50.0)
                    <= ASSASSIN_SCOUT_BRK_MAX_RSI
                ):
                    should_dispatch_scout = True
                    scout_trigger_tag = "03_BRK_1PCT_RSI50"
            if not should_dispatch_scout:
                await asyncio.to_thread(
                    a_ledger.update_state,
                    lambda s: s.__setitem__("scout_last_reentry_eval_ts", now_ts),
                    False,
                )
    elif (
        has_l1
        and len(scouts) < ASSASSIN_SCOUT_MAX_TIERS
        and cur_bucket_id > last_bucket_id
    ):
        # 활성 1층 보유 중 10분 게이트 4단 와이드 신저가 추매
        eff_lots = max(
            len(scouts), safe_int(a_st.get("scout_ratchet_max_lots"), len(scouts))
        )
        if eff_lots <= 4:
            req_drop = -1.00
        elif eff_lots <= 8:
            req_drop = -2.00
        elif eff_lots <= 10:
            req_drop = -3.50
        else:
            req_drop = -5.50
        min_buy_p = max(
            0.01,
            safe_float(a_st.get("scout_min_buy_price"), scouts[0].entry_price),
        )
        chg_min = ((lp - min_buy_p) / min_buy_p) * 100.0
        if chg_min <= req_drop:
            should_dispatch_scout = True
            scout_trigger_tag = f"04_WIDE_GRID_DIP({req_drop:.1f}%)"
        else:
            await asyncio.to_thread(
                a_ledger.update_state,
                lambda s: s.__setitem__("scout_last_bucket_id", cur_bucket_id),
                False,
            )

    if not should_dispatch_scout:
        return {"status": "SCOUT_MONITORING"}

    # C-3. 정찰병 파견 실행 & 4대 지표 기록 + 2번째 이후 정찰병 타점 10대 진성 게이트 검문
    new_seq = day_seq + 1
    hm_str = dt.strftime("%H:%M")
    target_100_p = round(math.ceil(lp * 1.010 * 100.0 - 1e-9) / 100.0, 2)
    scout1_ref = (
        lp
        if new_seq == 1
        else max(0.01, safe_float(a_st.get("scout1_entry_price"), lp))
    )
    vs_sc1_pct = round(((lp - scout1_ref) / scout1_ref) * 100.0, 2)

    new_scout = IndependentScoutUnit(
        scout_seq=new_seq,
        tier_idx=1,
        entry_price=lp,
        target_price=target_100_p,
        entry_ts=now_ts,
        entry_hm_str=hm_str,
        trigger_tag=scout_trigger_tag,
        rsi_14=safe_float(feat.get("rsi_14"), 50.0),
        pre_vwap=safe_float(feat.get("pre_vwap"), 0.0),
        vs_vwap_pct=safe_float(feat.get("vs_vwap_pct"), 0.0),
        prev_reg_close=safe_float(feat.get("prev_reg_close"), 0.0),
        vs_prev_close_pct=safe_float(feat.get("vs_prev_close_pct"), 0.0),
        pre_open_price=safe_float(feat.get("pre_open_price"), 0.0),
        vs_pre_open_pct=safe_float(feat.get("vs_pre_open_pct"), 0.0),
        vs_scout1_pct=vs_sc1_pct,
    )

    updated_scouts = [new_scout] + scouts
    for idx_u, u_sc in enumerate(updated_scouts[:ASSASSIN_SCOUT_MAX_TIERS]):
        u_sc.tier_idx = idx_u + 1
    updated_scouts = updated_scouts[:ASSASSIN_SCOUT_MAX_TIERS]

    should_enter_main, primary_gate, matched_gates, _ = (
        evaluate_10_truth_gates_signal(
            rsi_14=new_scout.rsi_14,
            vs_vwap_pct=new_scout.vs_vwap_pct,
            vs_prev_close_pct=new_scout.vs_prev_close_pct,
            vs_pre_open_pct=new_scout.vs_pre_open_pct,
            vs_scout1_pct=new_scout.vs_scout1_pct,
            prior_scout_wins_today=prior_wins,
            is_1m_bull=bool(feat.get("is_1m_bull", True)),
            day_scout_seq=new_seq,
        )
    )

    gate_eval_msg = (
        f"🗡️ 격발({', '.join(matched_gates)})"
        if should_enter_main
        else (
            "기준점 수립 전용(#1 선봉)"
            if new_seq == 1
            else "10대 진성 게이트 미충족 (정찰 계속)"
        )
    )

    def _commit_scout_dispatch(st: Dict[str, Any]) -> None:
        st["day_scout_seq"] = new_seq
        if new_seq == 1:
            st["scout1_entry_price"] = lp
            if safe_float(st.get("today_pre_open_price"), 0.0) <= 0.0:
                st["today_pre_open_price"] = lp
        prev_min_b = safe_float(st.get("scout_min_buy_price"), 0.0)
        st["scout_min_buy_price"] = (
            round(min(prev_min_b, lp), 4) if prev_min_b > 0.0 else lp
        )
        st["scout_ratchet_max_lots"] = max(
            safe_int(st.get("scout_ratchet_max_lots"), 0), len(updated_scouts)
        )
        st["scout_last_buy_ts"] = now_ts
        st["scout_last_reentry_eval_ts"] = now_ts
        st["scout_last_bucket_id"] = cur_bucket_id
        st["scout_has_active_l1"] = True
        st["active_scouts"] = [x.to_dict() for x in updated_scouts]
        hist = list(st.get("scout_history_today") or [])
        hist.append(new_scout.to_dict())
        st["scout_history_today"] = hist[-25:]

    await asyncio.to_thread(
        a_ledger.update_state, _commit_scout_dispatch, True
    )
    await _send_1_scout_dispatched_alert(
        context, new_scout, len(updated_scouts), prior_wins, gate_eval_msg
    )

    # C-4. 2번째+ 정찰병에서 10대 진성 게이트 포착 시 ➔ 본대 100% 즉시 진입 & +5% 안전캡 선장전 (알림 ③)
    if should_enter_main:
        base_seed = max(
            100.0,
            safe_float(a_st.get("base_seed_usd"), DEFAULT_INITIAL_SEED_USD),
        )
        comp_eq = max(
            100.0, safe_float(a_st.get("compound_equity_usd"), base_seed)
        )
        rt_fee = resolve_effective_round_trip_fee_rate_pct(
            safe_float(
                a_st.get("round_trip_fee_rate_pct"), DEFAULT_ROUND_TRIP_FEE_PCT
            )
        )
        fee_mult = 1.0 + (rt_fee / 100.0) * 0.5

        s_qty = max(1, int(math.floor(base_seed / max(0.01, lp * fee_mult))))
        c_qty = max(1, int(math.floor(comp_eq / max(0.01, lp * fee_mult))))

        ok_buy, buy_oid, fill_p, _ = await _dispatch_assassin_buy_order(
            context, c_qty, lp
        )
        if ok_buy:
            cap_500_p = round(
                math.ceil(fill_p * 1.050 * 100.0 - 1e-9) / 100.0, 2
            )
            arm_100_p = round(
                math.ceil(fill_p * 1.010 * 100.0 - 1e-9) / 100.0, 2
            )
            _, cap_oid = await _dispatch_assassin_safe_cap_sell_order(
                context, c_qty, cap_500_p
            )
            qqq_info = feat.get("qqq", {})

            def _commit_main_entry(st: Dict[str, Any]) -> None:
                st["in_main_position"] = True
                st["entry_gate_code"] = primary_gate
                st["entry_gate_matched_list"] = matched_gates
                st["entry_price"] = fill_p
                st["entry_ts"] = now_ts
                st["entry_hm_str"] = hm_str
                st["simple_held_qty"] = s_qty
                st["comp_held_qty"] = c_qty
                st["simple_invested_usd"] = round(fill_p * s_qty, 2)
                st["comp_invested_usd"] = round(fill_p * c_qty, 2)
                st["cap_500_price"] = cap_500_p
                st["arm_100_price"] = arm_100_p
                st["floor_100_price"] = arm_100_p
                st["is_trail_armed"] = False
                st["trail_armed_alert_sent"] = False
                st["peak_price"] = fill_p
                st["post_entry_min_price"] = fill_p
                st["nq_entry_price"] = safe_float(
                    qqq_info.get("qqq_live_price"), 0.0
                )
                st["nq_entry_bear_amp_pct"] = max(
                    0.40, safe_float(qqq_info.get("bear_drop_amp_pct"), 0.80)
                )
                st["live_buy_order_id"] = buy_oid
                st["live_safe_cap_order_id"] = cap_oid
                st["last_entry_snapshot"] = {
                    "rsi_14": new_scout.rsi_14,
                    "pre_vwap": new_scout.pre_vwap,
                    "vs_vwap_pct": new_scout.vs_vwap_pct,
                    "prev_reg_close": new_scout.prev_reg_close,
                    "vs_prev_close_pct": new_scout.vs_prev_close_pct,
                    "pre_open_price": new_scout.pre_open_price,
                    "vs_pre_open_pct": new_scout.vs_pre_open_pct,
                }

            entry_st = await asyncio.to_thread(
                a_ledger.update_state, _commit_main_entry, True
            )
            await _send_3_truth_gate_entry_alert(
                context, entry_st, matched_gates, feat
            )
            return {
                "status": "MAIN_POSITION_ENTERED",
                "gate": primary_gate,
                "entry_price": fill_p,
            }

    return {"status": "SCOUT_DISPATCHED", "scout_seq": new_seq}


# ===========================================================================
# [텔레그램 관제 UI 포맷터] /avwap · /sync 요약 블록 & /assassin 상세 관제 보드
# ===========================================================================
def format_assassin_slim_radar_block(
    context: Any, live_price: float = 0.0
) -> str:
    """
    /avwap, /sync, /settlement 하단에 결합되는 초슬림 36자 칼맞춤 요약 블록
    """
    a_ledger = get_or_create_assassin_ledger(context)
    a_st = a_ledger.get_state()
    mode_badge = "🧪모의" if ASSASSIN_LIVE_ORDER_HARD_LOCK else "⚡실전"
    tot = safe_int(a_st.get("total_trade_days"), 0)
    wins = safe_int(a_st.get("win_days"), 0)
    losses = safe_int(a_st.get("loss_days"), 0)
    wr = (wins / tot * 100.0) if tot > 0 else 100.0
    s_cum = safe_float(a_st.get("simple_cum_net_pnl_usd"), 0.0)
    c_cum = safe_float(a_st.get("comp_cum_net_pnl_usd"), 0.0)

    if bool(a_st.get("in_main_position", False)):
        ep = safe_float(a_st.get("entry_price"), live_price)
        lp = live_price if live_price > 0.0 else ep
        chg = ((lp - ep) / max(0.01, ep)) * 100.0 if ep > 0.0 else 0.0
        armed_str = "🔥HA추적중" if a_st.get("is_trail_armed") else "🛡️3단안전망"
        status_line = f"🗡️본대보유({a_st.get('entry_gate_code')}): ${ep:.2f}({chg:+.2f}%·{armed_str})"
    elif bool(a_st.get("is_session_done", False)):
        reason = str(a_st.get("session_exit_reason") or "퇴근완료")
        status_line = f"🏠금일퇴근({reason[:18]})"
    else:
        sc_cnt = len(a_st.get("active_scouts") or [])
        seq = safe_int(a_st.get("day_scout_seq"), 0)
        status_line = f"🕵️정찰감시: 금일 {seq}명 파견(보유 {sc_cnt}/7층)"

    return (
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🗡️ <b>[{mode_badge} 암살자 (상시독립 · /assassin)]</b>\n"
        f"• 상태: {html.escape(status_line)}\n"
        f"• 전적: <b>{tot}전 {wins}승 {losses}패({wr:.1f}%)</b>\n"
        f"• 누적: 단리 <b>{s_cum:+.0f}$</b> | 복리 <b>{c_cum:+.0f}$</b>"
    )


async def format_assassin_control_board(
    context: Any, live_price: float = 0.0
) -> str:
    """
    /assassin 명령어 및 전술 제어반 [🗡️ [모의] 암살자 상세 관제] 버튼 전용 상세 보드:
    - 프리장 데이터가 없는 날 장 마감 후 조회 시 프리시가와 프리VWAP를 정규장 값으로 오염시키지 않고
      정확히 $0.00 (0.00%)으로 표출한다!
    """
    dt = datetime.now(EST_TZ)
    a_ledger = get_or_create_assassin_ledger(context)
    await asyncio.to_thread(
        a_ledger.rollover_daily_session_if_needed, dt.strftime("%Y-%m-%d")
    )
    feat = await _extract_live_assassin_features_and_qqq_snapshot(
        context, dt, a_ledger
    )
    a_st = a_ledger.get_state()

    lp = safe_float(feat.get("live_price"), live_price)
    rsi_14 = safe_float(feat.get("rsi_14"), 50.0)
    pre_vwap = safe_float(feat.get("pre_vwap"), 0.0)
    vs_vwap_pct = safe_float(feat.get("vs_vwap_pct"), 0.0)
    reg_vwap = safe_float(feat.get("regular_vwap"), 0.0)
    vs_reg_vwap_pct = safe_float(feat.get("vs_reg_vwap_pct"), 0.0)
    prev_close = safe_float(feat.get("prev_reg_close"), 0.0)
    vs_prev_pct = safe_float(feat.get("vs_prev_close_pct"), 0.0)
    pre_open = safe_float(feat.get("pre_open_price"), 0.0)
    vs_pre_open_pct = safe_float(feat.get("vs_pre_open_pct"), 0.0)

    c_bull = "📈양봉" if feat.get("is_1m_bull", True) else "📉음봉"
    ha_bull = "🟢양봉" if feat.get("ha_is_bull", True) else "🔴음봉"

    # # MODIFIED: 프리VWAP 및 프리시가가 미확보(0.0)일 때는 정규장 값 복사 없이 정확히 $0.00 (0.00%) 표출!
    pre_vwap_str = (
        f"${pre_vwap:.2f} ({vs_vwap_pct:+.2f}%)"
        if pre_vwap > 0.0
        else "$0.00 (0.00%)"
    )
    reg_vwap_str = (
        f"${reg_vwap:.2f} ({vs_reg_vwap_pct:+.2f}%)"
        if reg_vwap > 0.0
        else "$0.00 (0.00%)"
    )
    prev_close_str = (
        f"${prev_close:.2f} ({vs_prev_pct:+.2f}%)"
        if prev_close > 0.0
        else "$0.00 (0.00%)"
    )
    pre_open_str = (
        f"${pre_open:.2f} ({vs_pre_open_pct:+.2f}%)"
        if pre_open > 0.0
        else "$0.00 (0.00%)"
    )

    q_info = feat.get("qqq", {})
    q_v1 = safe_float(q_info.get("vel_1m_pct"), 0.0)
    q_v3 = safe_float(q_info.get("vel_3m_pct"), 0.0)
    q_amp = safe_float(q_info.get("bear_drop_amp_pct"), 0.80)

    base_seed = safe_float(a_st.get("base_seed_usd"), DEFAULT_INITIAL_SEED_USD)
    comp_eq = safe_float(a_st.get("compound_equity_usd"), base_seed)
    mode_str = (
        "🧪 모의 상시 작동 (SIMULATED · 실주문 100% 차단)"
        if ASSASSIN_LIVE_ORDER_HARD_LOCK
        else "⚡ 실전 가동 (LIVE · 토스 OpenAPI 직결)"
    )

    if bool(a_st.get("in_main_position", False)):
        ep = safe_float(a_st.get("entry_price"), lp)
        cap_p = safe_float(a_st.get("cap_500_price"), ep * 1.05)
        flr_p = safe_float(a_st.get("floor_100_price"), ep * 1.01)
        s_q = safe_int(a_st.get("simple_held_qty"), 0)
        c_q = safe_int(a_st.get("comp_held_qty"), 0)
        chg = ((lp - ep) / max(0.01, ep)) * 100.0 if ep > 0.0 else 0.0
        trail_badge = (
            "🔥 +1.0% 보존선 잠금 & 0.40s HA 트레일링 추적 중"
            if a_st.get("is_trail_armed")
            else "🛡️ 08:15후 방향성 인지 3단 안전망 감시 중"
        )
        session_block = (
            f"🗡️ <b>[금일 세션 상태 : 본대 진입 보유 중 ({html.escape(str(a_st.get('entry_gate_code') or ''))})]</b>\n"
            f"• 진입가: <b>${ep:.2f}</b> ➔ 현재 수익률: <b>{chg:+.2f}%</b> (단리 {s_q}주 / 복리 {c_q}주)\n"
            f"• 안전캡(+5%): <b>${cap_p:.2f}</b> | 보존선(+1%): <b>${flr_p:.2f}</b>\n"
            f"• 방어상태: {trail_badge}"
        )
    elif bool(a_st.get("is_session_done", False)):
        reason = str(a_st.get("session_exit_reason") or "")
        if "0815_NO_TRADE" in reason:
            session_block = (
                f"🏠 <b>[금일 세션 상태 : 08:15 EST 무매매 안전 퇴근 완료]</b>\n"
                f"• 04:07 ~ 08:14 EST 구간 10대 진성 게이트 미충족 (익일 04:07 EST 재출격)"
            )
        else:
            s_day = safe_float(a_st.get("simple_daily_net_pnl_usd"), 0.0)
            c_day = safe_float(a_st.get("comp_daily_net_pnl_usd"), 0.0)
            session_block = (
                f"🎯 <b>[금일 세션 상태 : 당일 청산 퇴근 완료 ({html.escape(reason)})]</b>\n"
                f"• 금일 확정손익: 단리 <b>{s_day:+.2f}$</b> | 복리 <b>{c_day:+.2f}$</b> (오버나이트 0주)"
            )
    else:
        session_block = (
            f"🔫 <b>[금일 세션 상태 : 04:07 ~ 08:14 EST 정찰 & 10대 게이트 탐색 중]</b>\n"
            f"• 2번째+ 정찰병 타점에서 10대 진성 게이트(G1~G5 · BG1~BG5) 포착 시 즉시 진입"
        )

    hist_scouts = list(a_st.get("scout_history_today") or [])
    sc_wins = safe_int(a_st.get("prior_scout_wins_today"), 0)
    if hist_scouts:
        sc_lines: List[str] = []
        for s_item in hist_scouts[-5:]:
            if not isinstance(s_item, dict):
                continue
            sq = safe_int(s_item.get("scout_seq"), 1)
            shm = str(s_item.get("entry_hm_str") or "04:07")
            sep = safe_float(s_item.get("entry_price"), 0.0)
            srsi = safe_float(s_item.get("rsi_14"), 50.0)
            svw = safe_float(s_item.get("vs_vwap_pct"), 0.0)
            spr = safe_float(s_item.get("vs_prev_close_pct"), 0.0)
            spo = safe_float(s_item.get("vs_pre_open_pct"), 0.0)
            sc_lines.append(
                f"• #{sq}({shm}) <b>${sep:.2f}</b> | RSI {srsi:.1f} · VWAP {svw:+.1f}% · 전일 {spr:+.1f}% · 시가 {spo:+.1f}%"
            )
        scout_block = "\n".join(sc_lines)
    else:
        scout_block = "• 금일 파견된 정찰병이 아직 없습니다 (04:07 EST 첫 선봉 출격)."

    tot = safe_int(a_st.get("total_trade_days"), 0)
    wins = safe_int(a_st.get("win_days"), 0)
    losses = safe_int(a_st.get("loss_days"), 0)
    no_tr = safe_int(a_st.get("no_trade_days"), 0)
    wr = (wins / tot * 100.0) if tot > 0 else 100.0
    hr_cnt = safe_int(a_st.get("cap_500_homerun_cnt"), 0)
    ha_cnt = safe_int(a_st.get("ha_trail_boost_cnt"), 0)
    fl_cnt = safe_int(a_st.get("floor_100_preserve_cnt"), 0)
    st_cnt = safe_int(a_st.get("safety_net_stop_cnt"), 0)
    s_cum = safe_float(a_st.get("simple_cum_net_pnl_usd"), 0.0)
    c_cum = safe_float(a_st.get("comp_cum_net_pnl_usd"), 0.0)
    s_roi = (s_cum / max(100.0, base_seed)) * 100.0
    c_roi = (c_cum / max(100.0, base_seed)) * 100.0
    mdd = safe_float(a_st.get("max_drawdown_pct"), 0.0)

    return (
        f"🗡️ <b>[인피니트 스노우볼 · 암살자(Assassin) 관제 보드]</b>\n"
        f"⚙️ 운용모드: <b>{mode_str}</b>\n"
        f"💵 기준시드: <b>${base_seed:,.2f}</b> | 연속복리자산: <b>${comp_eq:,.2f}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>[실시간 SOXL · QQQ 4대 지표 스냅샷]</b>\n"
        f"• 현재가: <b>${lp:.2f}</b> ({c_bull} / HA {ha_bull})\n"
        f"① RSI(14): <b>{rsi_14:.1f}</b> | ② 프리VWAP: <b>{pre_vwap_str}</b> · 정규VWAP: <b>{reg_vwap_str}</b>\n"
        f"③ 전일종가: <b>{prev_close_str}</b> | ④ 프리시가: <b>{pre_open_str}</b>\n"
        f"🛡️ QQQ안전망: 1분 <b>{q_v1:+.2f}%</b> · 3분 <b>{q_v3:+.2f}%</b> · 하락진폭 <b>{q_amp:.2f}%</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{session_block}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🕵️ <b>[금일 1주 독립 정찰병 파견 기록 (총 {len(hist_scouts)}명 · +1%익절 {sc_wins}회)]</b>\n"
        f"{scout_block}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🏆 <b>[[모의] 암살자 누적 성적표 (초기화: /reset_assassin)]</b>\n"
        f"• 총 출격일: <b>{tot}일 ({wins}승 {losses}패 · 승률 {wr:.2f}%)</b> | 무매매퇴근: <b>{no_tr}일</b>\n"
        f"• 출구분포: +5%홈런 <b>{hr_cnt}회</b> · HA부스트 <b>{ha_cnt}회</b> · +1%보존 <b>{fl_cnt}회</b> · 3단방어 <b>{st_cnt}회</b>\n"
        f"• 💵 단리 누적순익: <b>{s_cum:+.2f}$ ({s_roi:+.2f}%)</b>\n"
        f"• 📈 복리 누적순익: <b>{c_cum:+.2f}$ ({c_roi:+.2f}% · MDD {mdd:.2f}%)</b>"
    )


# ===========================================================================
# [TDD 자체 검증 슈트] Case 93 10대 진성 게이트 · 방향성 3단 안전망 v2 · 프리시가 $0.00 정합성 검증
# ===========================================================================
def run_assassin_plugin_tdd() -> None:
    """
    🛠️ [TDD 검증]:
    1) 선봉 정찰병(#1, day_scout_seq == 1)에서는 조건이 맞아도 본대 진입이 차단되는지 검증
    2) 2번째 정찰병(#2, day_scout_seq == 2)에서 G1 ~ G5 및 BG1 ~ BG5 10대 진성 게이트 판정 정합성 검증
    3) 방향성 인지 3단계 안전망 v2: 양봉이거나 상승/지지 중일 때는 손절이 100% 금지되고,
       음봉 & 신저가 붕괴 + QQQ 3분 급락(-0.25% 이하) 시에만 역행 칼손절이 격발되는지 검증
    """
    # 1. 선봉 #1 진입 차단 검증
    ok_seq1, code_seq1, _, _ = evaluate_10_truth_gates_signal(
        rsi_14=18.0,
        vs_vwap_pct=-3.0,
        vs_prev_close_pct=-5.0,
        vs_pre_open_pct=-3.0,
        vs_scout1_pct=0.0,
        prior_scout_wins_today=1,
        is_1m_bull=True,
        day_scout_seq=1,
    )
    assert ok_seq1 is False and code_seq1 == "HOLD_SCOUT_SEQ_1_ANCHOR_ONLY"

    # 2. 2번째 정찰병(#2) G2 & BG2 동시 포착 검증
    ok_seq2, code_seq2, matched_2, _ = evaluate_10_truth_gates_signal(
        rsi_14=28.5,
        vs_vwap_pct=-2.20,
        vs_prev_close_pct=-3.50,
        vs_pre_open_pct=-1.60,
        vs_scout1_pct=-1.60,
        prior_scout_wins_today=1,
        is_1m_bull=True,
        day_scout_seq=2,
    )
    assert ok_seq2 is True and len(matched_2) >= 2

    # 3. 안전망 상승 중(양봉 또는 QQQ 속도 양수) 손절 절대 금지 검증
    stop_rising, stop_code_r, _ = evaluate_directional_3stage_safety_net_v2(
        hm_est=835,
        live_price=42.0,
        entry_price=45.0,
        post_entry_min_price=41.5,
        prev_reg_close=46.0,
        pre_open_price=45.5,
        soxl_is_1m_bull=True,
        soxl_ha_is_bull=False,
        qqq_live_price=480.0,
        nq_entry_price=490.0,
        nq_entry_bear_amp_pct=1.20,
        qqq_vel_1m_pct=0.05,
        qqq_vel_3m_pct=-0.40,
        qqq_is_1m_bull=True,
        qqq_ha_is_bull=False,
        is_trail_armed=False,
    )
    assert (
        stop_rising is False and stop_code_r == "HOLD_SAFETY_NET_RISING_GUARD"
    )

    # 4. 안전망 음봉 & 신저가 붕괴 + QQQ 3m <= -0.25% 급락 역행 시 칼손절 격발 검증
    stop_falling, stop_code_f, _ = evaluate_directional_3stage_safety_net_v2(
        hm_est=935,
        live_price=43.0,
        entry_price=45.0,
        post_entry_min_price=43.0,
        prev_reg_close=46.0,
        pre_open_price=45.5,
        soxl_is_1m_bull=False,
        soxl_ha_is_bull=False,
        qqq_live_price=484.0,
        nq_entry_price=490.0,
        nq_entry_bear_amp_pct=1.20,
        qqq_vel_1m_pct=-0.18,
        qqq_vel_3m_pct=-0.35,
        qqq_is_1m_bull=False,
        qqq_ha_is_bull=False,
        is_trail_armed=False,
    )
    assert (
        stop_falling is True
        and stop_code_f == "EXIT_DIR_3STAGE_QQQ_ACCEL_STOP"
    )


if __name__ == "__main__":
    run_assassin_plugin_tdd()
    print("✅ [assassin_plugin.py] TDD Self-Test Passed!")
