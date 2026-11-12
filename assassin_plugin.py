# -*- coding: utf-8 -*-
"""
# MODIFIED: assassin_plugin.py (Part 1/4 — 🗡️ [모의 ⇄ 0주 전환예약 ⇄ 실전] 암살자 독립 플러그인 ·
# Case 97-A 강세장 눌림목[UG1~UG4] 및 UG 전용 즉시칼손절 영구 폐기 ➔ 순수 10대 진성 급락 게이트[G1~G5 + BG1~BG5] 단일화 ·
# Case 97-B T03_A 1분 눌림 스캔 미충족 시 60초 선잠금 버그 영구 소각[다중 봇 분봉 내 양봉전환 100% 동시 포착] ·
# Case 96 본대 1일 1회 출근 원칙 유지 + 골든타임[04:07 ~ 08:14 EST] 다회차 10대 진성게이트 [모의] 정찰병 익절 카운터[정규장 폐기] ·
# SOXL == 0주 조건부 [실전] 암살자 자동 전환 게이트[ARMED_ON_ZERO ➔ LIVE] · 당일 예산 min(설정시드, 주문가능금액) 확정 ·
# 보유 SGOV 수동매도 위임 · 출동 순간 QQQ 지수[entry_qqq_price] 고정 저장 및 08:15~ SN4×SN3 방어망 · Case 93 ~ Case 97)
인피니트 스노우볼 (Infinite Snowball) v3.0 — [모의 ⇄ 실전 Dual-Ready] 암살자(Assassin) 코어 모듈
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
    buckets_from_dicts,
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
    BARBELL_SAFE_SYMBOL,
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
# [핵심 상수 · Case 93 ~ Case 97] [모의 ⇄ 0주 예약 ⇄ 실전] 모드 상수 및 타임라인 상수
# (기본값은 SIMULATED 모의 모드이며, 승격 스위치 전환 시 SOXL == 0주 조건에서 LIVE 단독 활성화)
# ---------------------------------------------------------------------------
ASSASSIN_LIVE_ORDER_HARD_LOCK: bool = False
ASSASSIN_MODE_SIMULATED: str = "SIMULATED"
ASSASSIN_MODE_ARMED_ON_ZERO: str = "ARMED_ON_ZERO"
ASSASSIN_MODE_LIVE: str = "LIVE"
VALID_ASSASSIN_MODES: Tuple[str, ...] = (
    ASSASSIN_MODE_SIMULATED,
    ASSASSIN_MODE_ARMED_ON_ZERO,
    ASSASSIN_MODE_LIVE,
)

MACRO_REF_SYMBOL: str = "QQQ"

ASSASSIN_SCOUT_START_HM: int = 407       # 04:07 EST 첫 선봉 정찰병 출격
ASSASSIN_GOLDEN_END_HM: int = 814        # 08:14 EST 정찰 및 본대 진입 마감
ASSASSIN_MACRO_CUTOFF_HM: int = 815      # 08:15 EST 거시지표 발표 선제 컷오프 (골든타임 다회차 정찰 마감 · 정규장 폐기)
ASSASSIN_REGULAR_OPEN_HM: int = 930      # 09:30 EST 정규장 개장
ASSASSIN_VWAP_EXIT_START_HM: int = 1500  # 15:00 ~ 15:58 EST 수익권 정규장 VWAP 탈출 구간
ASSASSIN_MOC_EXIT_HM: int = 1559         # 15:59 ~ 16:01 EST 무오버나이트 2단계 방탄 MOC 강제 청산

SCOUT_MAX_INDEPENDENT_UNITS: int = 7     # 정찰병 최대 독립 보유 한도 (7명)
SCOUT_PROFIT_TARGET_PCT: float = 1.00    # 개별 정찰병 독립 익절 목표 (+1.00%)
SCOUT_PULLBACK_DROP_PCT: float = -1.00   # 정찰병 1층 공석 눌림목 (-1.00% 무필터)
SCOUT_BREAKOUT_RISE_PCT: float = 1.00    # 정찰병 1층 공석 돌파 (+1.00% & RSI<=50.0)
SCOUT_BREAKOUT_MAX_RSI: float = 50.0     # 정찰병 돌파 최대 허용 RSI(14)
SCOUT_TIME_SHIELD_SEC: float = 60.0      # 정찰병 매수/매도 후 60초 타임쉴드

# [Case 96 : 골든타임(04:07 ~ 08:14 EST) 다회차 10대 진성게이트 [모의] 정찰병 카운터 전용 상수 (정규장 폐기)]
GT_GATE_SCOUT_PROFIT_TARGET_PCT: float = 1.00
GT_GATE_SCOUT_COOLDOWN_SEC: float = 60.0
GT_GATE_SCOUT_MAX_HISTORY: int = 25

# [Case 93 & Case 97-B : T03_A_DIP10_ALL_SCOUT — #1 선봉 후 저점 대비 -1.00% 눌림 상시 스캔 (격발 시에만 분당 잠금)]
SCOUT_T03A_DIP_SCAN_DROP_PCT: float = -1.00
SCOUT_T03A_DIP_SCAN_INTERVAL_SEC: float = 60.0
_LAST_T03A_DIP_SCAN_KEY: str = ""
_LAST_T03A_DIP_SCAN_TS: float = 0.0

# NEW: /dev/shm 골든타임 정찰 및 10대 급락 게이트 공유 버스
ASSASSIN_SHM_SIGNAL_TTL_SEC: float = 15.0
_CONSUMED_SHM_GATE_KEYS: Dict[str, str] = {}
_SHM_SCOUT_SYNC_KEYS: Tuple[str, ...] = (
    "day_scout_seq",
    "prior_scout_wins_today",
    "scout_units",
    "day_scout_history",
    "scout1_open_price",
    "scout_anchor_price",
    "scout_cycle_min_buy_price",
    "scout_ratchet_max_lots",
    "scout_has_active_l1",
    "last_scout_buy_ts",
    "last_scout_sell_ts",
    "last_scout_reentry_eval_ts",
    "last_scout_bucket_10m",
    "today_pre_open_price",
    "today_pre_open_verified",
    "today_premarket_vwap",
    "today_pre_vwap_verified",
    "today_pre_high_price",
)


def _assn_shm_fp_sync() -> str:
    bdir = str(
        os.environ.get(
            "TOSS_SHM_BUS_DIR", "/dev/shm/toss_sniper_bus_v3"
        )
    ).strip()
    if bdir.startswith("/dev/shm/") and not os.path.isdir("/dev/shm"):
        bdir = "/tmp/toss_sniper_bus_v3"
    if not os.path.isdir(bdir):
        old_u = os.umask(0)
        try:
            os.makedirs(bdir, mode=0o777, exist_ok=True)
            os.chmod(bdir, 0o777)
        except Exception:
            pass
        finally:
            os.umask(old_u)
    return os.path.join(bdir, "assassin_gt_bus_v3.json")


def _assn_read_shm_bus_sync(today_str: str) -> Dict[str, Any]:
    fp = _assn_shm_fp_sync()
    if not os.path.isfile(fp):
        return {}
    try:
        with open(fp, "r", encoding="utf-8") as rf:
            d = json.load(rf)
        if isinstance(d, dict) and d.get("date") == today_str:
            return d
    except Exception:
        pass
    return {}


def _assn_write_shm_bus_sync(payload: Dict[str, Any]) -> None:
    fp = _assn_shm_fp_sync()
    tmp_p = f"{fp}.tmp.{os.getpid()}.{threading.get_ident()}"
    old_u = os.umask(0)
    try:
        with open(tmp_p, "w", encoding="utf-8") as wf:
            json.dump(payload, wf, ensure_ascii=False)
            wf.flush()
        try:
            os.chmod(tmp_p, 0o666)
        except Exception:
            pass
        os.replace(tmp_p, fp)
    except Exception:
        try:
            if os.path.exists(tmp_p):
                os.remove(tmp_p)
        except Exception:
            pass
    finally:
        os.umask(old_u)


def _assn_pub_shm_scout_sync(st: Dict[str, Any]) -> None:
    try:
        d_str = str(st.get("current_session_date") or "").strip()
        if not d_str:
            return
        cur = _assn_read_shm_bus_sync(d_str)
        prev_sc = cur.get("scout_state") or {}
        n_rk = (
            safe_int(st.get("day_scout_seq"), 0),
            safe_int(st.get("prior_scout_wins_today"), 0),
        )
        p_rk = (
            safe_int(prev_sc.get("day_scout_seq"), 0),
            safe_int(prev_sc.get("prior_scout_wins_today"), 0),
        )
        if n_rk < p_rk:
            return
        snap = {k: copy.deepcopy(st.get(k)) for k in _SHM_SCOUT_SYNC_KEYS}
        snap["bus_ts"] = time.time()
        cur["date"] = d_str
        cur["scout_state"] = snap
        _assn_write_shm_bus_sync(cur)
    except Exception:
        pass


def _assn_pub_shm_gate_sync(
    today_str: str,
    min_key: str,
    gate_id: str,
    gate_desc: str,
    trigger_mode: str,
    entry_scout_seq: int,
    feat: Dict[str, Any],
) -> None:
    try:
        cur = _assn_read_shm_bus_sync(today_str)
        cur["date"] = today_str
        cur["last_gate_signal"] = {
            "date": today_str,
            "ts": time.time(),
            "min_key": min_key,
            "gate_id": gate_id,
            "gate_desc": gate_desc,
            "trigger_mode": trigger_mode,
            "entry_scout_seq": int(entry_scout_seq),
            "rsi_14": safe_float(feat.get("rsi_14"), 50.0),
            "pre_vwap": safe_float(feat.get("pre_vwap"), 0.0),
            "vs_vwap_pct": safe_float(feat.get("vs_vwap_pct"), 0.0),
            "prev_reg_close": safe_float(feat.get("prev_reg_close"), 0.0),
            "vs_prev_close_pct": safe_float(
                feat.get("vs_prev_close_pct"), 0.0
            ),
            "pre_open_price": safe_float(feat.get("pre_open_price"), 0.0),
            "vs_pre_open_pct": safe_float(
                feat.get("vs_pre_open_pct"), 0.0
            ),
        }
        _assn_write_shm_bus_sync(cur)
    except Exception:
        pass


async def _sync_scout_from_shm_if_behind(
    assn_ledger: Any,
    st: Dict[str, Any],
    today_str: str,
    dt_now: datetime,
    now_ts: float,
) -> Dict[str, Any]:
    bus = await asyncio.to_thread(_assn_read_shm_bus_sync, today_str)
    sc = bus.get("scout_state")
    if not isinstance(sc, dict):
        return st
    b_rk = (
        safe_int(sc.get("day_scout_seq"), 0),
        safe_int(sc.get("prior_scout_wins_today"), 0),
    )
    l_rk = (
        safe_int(st.get("day_scout_seq"), 0),
        safe_int(st.get("prior_scout_wins_today"), 0),
    )
    hm = dt_now.hour * 100 + dt_now.minute
    bus_age = now_ts - safe_float(sc.get("bus_ts"), now_ts)
    if b_rk > l_rk and (
        bus_age >= 3.0 or (l_rk[0] == 0 and hm >= 408)
    ):
        upd = {k: sc[k] for k in _SHM_SCOUT_SYNC_KEYS if k in sc}
        st = await assn_ledger.update_state(**upd)
    return st


async def _consume_shm_gate_if_fresh(
    context: Any,
    assn_ledger: Any,
    st: Dict[str, Any],
    feat: Dict[str, Any],
    today_str: str,
    dt_now: datetime,
    now_ts: float,
    allow_main_force_entry: bool,
) -> Optional[str]:
    bus = await asyncio.to_thread(_assn_read_shm_bus_sync, today_str)
    sig = bus.get("last_gate_signal")
    if not isinstance(sig, dict) or sig.get("date") != today_str:
        return None
    age = now_ts - safe_float(sig.get("ts"), 0.0)
    if age < 0.0 or age > ASSASSIN_SHM_SIGNAL_TTL_SEC:
        return None
    gid = str(sig.get("gate_id") or "").strip()
    mkey = str(sig.get("min_key") or "").strip()
    if not gid or not mkey:
        return None
    skey = f"{mkey}:{gid}"
    slug = str(getattr(assn_ledger, "folder_slug", "default"))
    if _CONSUMED_SHM_GATE_KEYS.get(slug) == skey:
        return None
    s_seq = max(1, safe_int(sig.get("entry_scout_seq"), 1))
    t_mode = str(sig.get("trigger_mode") or "SHM_SYNC_10G")
    st, gt_d = await _try_dispatch_gt_multi_gate_scout(
        assn_ledger=assn_ledger,
        st=st,
        feat=feat,
        gate_id=gid,
        trigger_mode=t_mode,
        entry_scout_seq=s_seq,
        now_est=dt_now,
        now_ts=now_ts,
    )
    if not allow_main_force_entry:
        _CONSUMED_SHM_GATE_KEYS[slug] = skey
        return f"GT_SHM_SCOUT_DISPATCHED_{gid}" if gt_d else None
    res_e = await _enter_assassin_main_force_from_gate(
        context=context,
        assn_ledger=assn_ledger,
        st=st,
        feat=feat,
        gate_id=gid,
        gate_desc=str(sig.get("gate_desc") or gid),
        entry_scout_seq=s_seq,
        entry_trigger_mode=t_mode,
        now_est=dt_now,
        now_ts=now_ts,
        entry_rsi_14=safe_float(sig.get("rsi_14"), feat["rsi_14"]),
        entry_vwap=safe_float(sig.get("pre_vwap"), feat["pre_vwap"]),
        entry_vs_vwap_pct=safe_float(
            sig.get("vs_vwap_pct"), feat["vs_vwap_pct"]
        ),
        entry_prev_close=safe_float(
            sig.get("prev_reg_close"), feat["prev_reg_close"]
        ),
        entry_vs_prev_close_pct=safe_float(
            sig.get("vs_prev_close_pct"), feat["vs_prev_close_pct"]
        ),
        entry_pre_open=safe_float(
            sig.get("pre_open_price"), feat["pre_open_price"]
        ),
        entry_vs_pre_open_pct=safe_float(
            sig.get("vs_pre_open_pct"), feat["vs_pre_open_pct"]
        ),
    )
    if res_e not in ("ASSASSIN_BUY_FAILED", "ASSASSIN_BUY_NO_PRICE"):
        _CONSUMED_SHM_GATE_KEYS[slug] = skey
    return res_e

ASSASSIN_SAFE_CAP_PCT: float = 5.00      # 본대 진입 직후 상단 안전 캡 (+5.00%)
ASSASSIN_ARM_IGNITION_PCT: float = 1.00  # 트레일링 점화 및 최소 수익 보존선 (+1.00%)
ASSASSIN_BOOST_TIER2_PCT: float = 2.00   # +2.00% 이상 구간 콜백 완화 기준
ASSASSIN_CALLBACK_TIGHT_PCT: float = 0.20  # +1.00% ~ +1.99% 구간 최고가 대비 콜백 (-0.20%p)
ASSASSIN_CALLBACK_WIDE_PCT: float = 0.30   # +2.00% 이상 구간 최고가 대비 콜백 (-0.30%p)
ASSASSIN_QQQ_SURGE_BYPASS_PCT: float = 0.20  # QQQ 3m/10m 변화율 >= +0.20% 급등 시 HA 음봉 매도 보류

LIVE_BUY_ORDER_MAX_WAIT_SEC: float = 60.0

# [Case 93 & Case 97-A : 출동 순간 QQQ 지수(entry_qqq_price) 기반 08:15~ SN4×SN3 단일 방어망 상수 (UG 영구 소각)]
SAFETY_NET_MODE_DEFAULT: str = "SN4_DEEP_1000_SN3_SMART_HYBRID"
SAFETY_QQQ_BASE_AMP_PCT: float = 2.00
SAFETY_QQQ_AMP_CUT_RATIO: float = 0.50
SAFETY_DYN_QQQ_MIN_THR_PCT: float = 1.00
SAFETY_DYN_QQQ_MAX_THR_PCT: float = 1.00
SAFETY_STAGE1_HEART_STOP_PCT: float = -3.00
SAFETY_STAGE23_SOXL_LOSS_MAX_PCT: float = -1.50
SAFETY_STAGE23_QQQ_VEL3M_DROP_PCT: float = -0.25


def _is_collapsed_assassin_anchors(
    prev_c: float, pre_o: float, pre_v: float
) -> bool:
    if prev_c <= 0.0 or pre_o <= 0.0 or pre_v <= 0.0:
        return False
    return bool(
        abs(prev_c - pre_o) < 1e-6 and abs(pre_v - prev_c) < 1e-6
    )


def is_assassin_live_mode_state(st: Dict[str, Any]) -> bool:
    """암살자 원장 상태가 현재 [실전(LIVE)] 단독 운용 모드인지 판별한다."""
    if ASSASSIN_LIVE_ORDER_HARD_LOCK:
        return False
    return (
        str((st or {}).get("execution_mode") or ASSASSIN_MODE_SIMULATED)
        .upper()
        .strip()
        == ASSASSIN_MODE_LIVE
    )


# ---------------------------------------------------------------------------
# [핵심 1] 1주 가상 독립 정찰병 데이터 구조 (IndependentScoutUnit)
# ---------------------------------------------------------------------------
@dataclass
class IndependentScoutUnit:
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
# [핵심 2] 폴더 격리형 암살자 전용 3중 원장 (AssassinSimLedger — 모의/0주예약/실전 + 골든타임 다회차 10G 정찰 카운터)
# ---------------------------------------------------------------------------
def resolve_assassin_ledger_paths(
    base_dir: Optional[str] = None,
) -> Tuple[str, str, str, str]:
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
    Dirty-Check 및 3중 원자적 백업 금고를 지원하는 [모의 ⇄ 0주예약 ⇄ 실전] 암살자 전용 원장 클래스.
    - 본대(Main Force): 순수 10대 진성 급락 게이트(G1~G5 · BG1~BG5) 기반 1일 1회 출근·퇴근 원칙 엄수
    - 골든타임 다회차 게이트 정찰병(Case 96 & Case 97): 04:07 ~ 08:14 EST 구간 10대 진성 급락 게이트 조건마다 출동하여
      +1.00% 익절 퇴근 횟수만 독립 카운트 (08:15 EST 마감 잠금 · 정규장 전면 폐기)
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
            "execution_mode": ASSASSIN_MODE_SIMULATED,
            "live_order_hard_lock": bool(ASSASSIN_LIVE_ORDER_HARD_LOCK),
            "demote_to_sim_after_exit": False,
            "safety_net_mode": SAFETY_NET_MODE_DEFAULT,
            "is_enabled": True,
            "initial_seed_usd": clean_seed,
            "us_commission_rate": get_runtime_us_commission_rate(),
            "round_trip_fee_rate_pct": get_runtime_round_trip_fee_rate_pct(),
            # 당일 본대(1일 1회) 세션 상태 머신
            "current_session_date": now_est.strftime("%Y-%m-%d"),
            "session_phase": "IDLE_WAIT_0407",
            "is_session_done": False,
            "session_done_reason": "",
            # 당일 확정 4대 앵커 지표 및 일중 최고가 원장 백업
            "today_anchors_locked": False,
            "today_prev_close_verified": False,
            "today_pre_open_verified": False,
            "today_pre_vwap_verified": False,
            "today_prev_reg_close": 0.0,
            "today_pre_open_price": 0.0,
            "today_premarket_vwap": 0.0,
            "today_regular_vwap": 0.0,
            "today_pre_high_price": 0.0,
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
            # [Case 96 & Case 97]: 골든타임(04:07 ~ 08:14 EST) 다회차 10대 진성게이트 [모의] 정찰병 익절 퇴근 카운터 (정규장 폐기)
            "gt_gate_scout_done": False,
            "gt_active_gate_scout": None,
            "last_gt_gate_exit_ts": 0.0,
            "last_gt_gate_exit_price": 0.0,
            "last_gt_gate_scout_seq": 0,
            "today_gt_gate_dispatches": 0,
            "today_gt_gate_win_exits": 0,
            "today_gt_gate_stop_exits": 0,
            "today_gt_gate_cutoff_exits": 0,
            "today_gt_gate_history": [],
            "cum_gt_gate_dispatches": 0,
            "cum_gt_gate_win_exits": 0,
            "cum_gt_gate_stop_exits": 0,
            "cum_gt_gate_cutoff_exits": 0,
            "cum_gt_multi_win_days": 0,
            "max_daily_gt_gate_wins": 0,
            # 본대(Main Force) 포지션 · 실전 주문 슬롯 및 트레일링 상태
            "has_position": False,
            "is_live_position": False,
            "live_held_qty": 0,
            "live_invested_usd": 0.0,
            "live_entry_budget_usd": 0.0,
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
            "nq_entry_bear_amp_pct": 2.00,
            "dyn_qqq_stage2_thr_pct": 1.00,
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
            # Dual-Ready 실전 미체결 추적 슬롯
            "pending_buy_order_id": "",
            "pending_buy_ordered_qty": 0,
            "pending_buy_price": 0.0,
            "pending_buy_mono": 0.0,
            "pending_buy_meta": {},
            "safe_cap_sell_order_id": "",
            "pending_exit_sell_order_id": "",
            "pending_exit_code": "",
            "pending_exit_desc": "",
            "pending_exit_mono": 0.0,
            # 5대 알림 1회 발송 래치
            "alert_0815_no_trade_sent": False,
            "alert_entry_sent": False,
            "alert_arm_100_sent": False,
            "alert_exit_sent": False,
            "alert_live_bp_shortfall_sent": False,
            # 당일 체결 요약
            "today_exit_reason": "",
            "today_exit_time_est": "",
            "today_exit_price": 0.0,
            "today_gain_pct": 0.0,
            "today_simple_net_usd": 0.0,
            "today_comp_net_usd": 0.0,
            "today_live_net_usd": 0.0,
            # 누적 성적표 (단리 · 연속복리 · 실전 누적순익 동시 추적 · 구원장 호환 키 보존)
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
            "exit_ug_qqq_stop_cnt": 0,
            "exit_moc_cnt": 0,
            "simple_cum_net_usd": 0.0,
            "comp_free_cash_usd": clean_seed,
            "comp_cum_net_usd": 0.0,
            "comp_peak_equity_usd": clean_seed,
            "comp_max_dd_pct": 0.0,
            "live_cum_net_usd": 0.0,
            "live_trade_days": 0,
            "gate_hit_counts": {},
            "updated_at": now_est.isoformat(),
        }

    def _sanitize_state(
        self, raw_st: Dict[str, Any], default_seed: float
    ) -> Dict[str, Any]:
        base = self._default_symbol_state(default_seed)
        if isinstance(raw_st, dict):
            base.update(raw_st)

        raw_exec_m = (
            str(base.get("execution_mode") or ASSASSIN_MODE_SIMULATED)
            .upper()
            .strip()
        )
        if ASSASSIN_LIVE_ORDER_HARD_LOCK:
            base["execution_mode"] = ASSASSIN_MODE_SIMULATED
        elif raw_exec_m in VALID_ASSASSIN_MODES:
            base["execution_mode"] = raw_exec_m
        else:
            base["execution_mode"] = ASSASSIN_MODE_SIMULATED

        base["live_order_hard_lock"] = bool(ASSASSIN_LIVE_ORDER_HARD_LOCK)
        base["demote_to_sim_after_exit"] = bool(
            base.get("demote_to_sim_after_exit", False)
        )
        base["safety_net_mode"] = SAFETY_NET_MODE_DEFAULT

        init_s = safe_float(base.get("initial_seed_usd"), default_seed)
        if init_s < 100.0:
            init_s = max(100.0, default_seed)
        base["initial_seed_usd"] = round(init_s, 4)

        comp_net = round(safe_float(base.get("comp_cum_net_usd"), 0.0), 4)
        base["comp_cum_net_usd"] = comp_net
        base["simple_cum_net_usd"] = round(
            safe_float(base.get("simple_cum_net_usd"), 0.0), 4
        )
        base["live_cum_net_usd"] = round(
            safe_float(base.get("live_cum_net_usd"), 0.0), 4
        )
        base["live_trade_days"] = max(
            0, safe_int(base.get("live_trade_days"), 0)
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
        base["today_pre_high_price"] = round(
            max(0.0, safe_float(base.get("today_pre_high_price"), 0.0)), 4
        )
        base["exit_ug_qqq_stop_cnt"] = max(
            0, safe_int(base.get("exit_ug_qqq_stop_cnt"), 0)
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
        if not isinstance(base.get("pending_buy_meta"), dict):
            base["pending_buy_meta"] = {}

        # [Case 96 & Case 97]: 골든타임 다회차 [모의] 게이트 정찰병 필드 정규화
        base["gt_gate_scout_done"] = bool(
            base.get("gt_gate_scout_done", False)
        )
        raw_gt_act = base.get("gt_active_gate_scout")
        if (
            isinstance(raw_gt_act, dict)
            and safe_float(raw_gt_act.get("entry_price"), 0.0) > 0.0
        ):
            ep_gt = round(
                max(0.01, safe_float(raw_gt_act.get("entry_price"), 0.01)), 4
            )
            tp_gt_def = (
                math.ceil(
                    (
                        ep_gt
                        * (1.0 + GT_GATE_SCOUT_PROFIT_TARGET_PCT / 100.0)
                        - 1e-9
                    )
                    * 100.0
                )
                / 100.0
            )
            base["gt_active_gate_scout"] = {
                "round_no": max(1, safe_int(raw_gt_act.get("round_no"), 1)),
                "gate_id": str(raw_gt_act.get("gate_id") or "G1")
                .upper()
                .strip(),
                "trigger_mode": str(
                    raw_gt_act.get("trigger_mode") or "SCOUT_GATE"
                ),
                "entry_time_est": str(
                    raw_gt_act.get("entry_time_est") or "04:07:00"
                ),
                "entry_ts": max(
                    0.0, safe_float(raw_gt_act.get("entry_ts"), 0.0)
                ),
                "entry_price": ep_gt,
                "target_price": round(
                    max(
                        ep_gt,
                        safe_float(raw_gt_act.get("target_price"), tp_gt_def),
                    ),
                    2,
                ),
                "entry_qqq_price": round(
                    max(
                        0.0,
                        safe_float(raw_gt_act.get("entry_qqq_price"), 0.0),
                    ),
                    4,
                ),
                "scout_seq_at_entry": max(
                    1, safe_int(raw_gt_act.get("scout_seq_at_entry"), 1)
                ),
            }
        else:
            base["gt_active_gate_scout"] = None

        base["last_gt_gate_exit_ts"] = round(
            max(0.0, safe_float(base.get("last_gt_gate_exit_ts"), 0.0)), 4
        )
        base["last_gt_gate_exit_price"] = round(
            max(0.0, safe_float(base.get("last_gt_gate_exit_price"), 0.0)), 4
        )
        base["last_gt_gate_scout_seq"] = max(
            0, safe_int(base.get("last_gt_gate_scout_seq"), 0)
        )
        base["today_gt_gate_dispatches"] = max(
            0, safe_int(base.get("today_gt_gate_dispatches"), 0)
        )
        base["today_gt_gate_win_exits"] = max(
            0, safe_int(base.get("today_gt_gate_win_exits"), 0)
        )
        base["today_gt_gate_stop_exits"] = max(
            0, safe_int(base.get("today_gt_gate_stop_exits"), 0)
        )
        base["today_gt_gate_cutoff_exits"] = max(
            0, safe_int(base.get("today_gt_gate_cutoff_exits"), 0)
        )
        raw_gt_hist = base.get("today_gt_gate_history")
        if isinstance(raw_gt_hist, list):
            base["today_gt_gate_history"] = [
                dict(it) for it in raw_gt_hist if isinstance(it, dict)
            ][-GT_GATE_SCOUT_MAX_HISTORY:]
        else:
            base["today_gt_gate_history"] = []

        base["cum_gt_gate_dispatches"] = max(
            0, safe_int(base.get("cum_gt_gate_dispatches"), 0)
        )
        base["cum_gt_gate_win_exits"] = max(
            0, safe_int(base.get("cum_gt_gate_win_exits"), 0)
        )
        base["cum_gt_gate_stop_exits"] = max(
            0, safe_int(base.get("cum_gt_gate_stop_exits"), 0)
        )
        base["cum_gt_gate_cutoff_exits"] = max(
            0, safe_int(base.get("cum_gt_gate_cutoff_exits"), 0)
        )
        base["cum_gt_multi_win_days"] = max(
            0, safe_int(base.get("cum_gt_multi_win_days"), 0)
        )
        base["max_daily_gt_gate_wins"] = max(
            base["today_gt_gate_win_exits"],
            max(0, safe_int(base.get("max_daily_gt_gate_wins"), 0)),
        )

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

        # 실전(LIVE) 포지션이 미청산 상태로 남아 있으면 포지션 슬롯 덮어쓰기 방지
        if bool(st.get("has_position", False)) and bool(
            st.get("is_live_position", False)
        ):
            return st

        _LAST_T03A_DIP_SCAN_KEY = ""
        _LAST_T03A_DIP_SCAN_TS = 0.0

        prev_gt_done = bool(st.get("gt_gate_scout_done", False))
        prev_gt_wins = max(0, safe_int(st.get("today_gt_gate_win_exits"), 0))
        next_multi_win_days = max(
            0, safe_int(st.get("cum_gt_multi_win_days"), 0)
        )
        if not prev_gt_done and prev_gt_wins >= 2:
            next_multi_win_days += 1
        next_max_gt_wins = max(
            max(0, safe_int(st.get("max_daily_gt_gate_wins"), 0)),
            prev_gt_wins,
        )

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
            today_pre_high_price=0.0,
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
            gt_gate_scout_done=False,
            gt_active_gate_scout=None,
            last_gt_gate_exit_ts=0.0,
            last_gt_gate_exit_price=0.0,
            last_gt_gate_scout_seq=0,
            today_gt_gate_dispatches=0,
            today_gt_gate_win_exits=0,
            today_gt_gate_stop_exits=0,
            today_gt_gate_cutoff_exits=0,
            today_gt_gate_history=[],
            cum_gt_multi_win_days=next_multi_win_days,
            max_daily_gt_gate_wins=next_max_gt_wins,
            has_position=False,
            is_live_position=False,
            live_held_qty=0,
            live_invested_usd=0.0,
            live_entry_budget_usd=0.0,
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
            pending_buy_ordered_qty=0,
            pending_buy_price=0.0,
            pending_buy_mono=0.0,
            pending_buy_meta={},
            safe_cap_sell_order_id="",
            pending_exit_sell_order_id="",
            pending_exit_code="",
            pending_exit_desc="",
            pending_exit_mono=0.0,
            alert_0815_no_trade_sent=False,
            alert_entry_sent=False,
            alert_arm_100_sent=False,
            alert_exit_sent=False,
            alert_live_bp_shortfall_sent=False,
            today_exit_reason="",
            today_exit_time_est="",
            today_exit_price=0.0,
            today_gain_pct=0.0,
            today_simple_net_usd=0.0,
            today_comp_net_usd=0.0,
            today_live_net_usd=0.0,
        )

    async def reset_assassin_stats_only(
        self, sniper_seed_usd: float = DEFAULT_INITIAL_SEED_USD
    ) -> Dict[str, Any]:
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
            today_gt_gate_dispatches=0,
            today_gt_gate_win_exits=0,
            today_gt_gate_stop_exits=0,
            today_gt_gate_cutoff_exits=0,
            today_gt_gate_history=[],
            cum_gt_gate_dispatches=0,
            cum_gt_gate_win_exits=0,
            cum_gt_gate_stop_exits=0,
            cum_gt_gate_cutoff_exits=0,
            cum_gt_multi_win_days=0,
            max_daily_gt_gate_wins=0,
            exit_cap500_cnt=0,
            exit_ha_boost_cnt=0,
            exit_floor100_cnt=0,
            exit_vwap_1500_cnt=0,
            exit_safety_stage1_cnt=0,
            exit_safety_stage23_cnt=0,
            exit_ug_qqq_stop_cnt=0,
            exit_moc_cnt=0,
            simple_cum_net_usd=0.0,
            comp_free_cash_usd=eff_seed,
            comp_cum_net_usd=0.0,
            comp_peak_equity_usd=eff_seed,
            comp_max_dd_pct=0.0,
            live_cum_net_usd=0.0,
            live_trade_days=0,
            gate_hit_counts={},
        )


def ensure_assassin_ledger(context: Any) -> AssassinSimLedger:
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
# [핵심 2-B] 스나이퍼 / 바벨 모드 분리형 [실전] 암살자 전환 게이트 (SOXL == 0주 조건부 전환 · SGOV 수동매도 위임)
# ---------------------------------------------------------------------------
def is_live_assassin_standalone_active(context: Any) -> bool:
    """
    현재 암살자가 [실전(LIVE)] 단독 운용 모드로 활성화된 상태인지 반환한다.
    True 일 때 main.py 는 스나이퍼(복리/단리) 및 바벨(SGOV 포함) 신규 매매를 완전히 분리 중지하고,
    실전 암살자 단독으로 SOXL을 운용한다 (보유 SGOV는 사용자 수동 매도에 위임).
    """
    if context is None:
        return False
    st = ensure_assassin_ledger(context).get_state()
    return is_assassin_live_mode_state(st)


def is_live_assassin_armed_on_zero(context: Any) -> bool:
    """현재 SOXL 보유로 인해 0주 졸업 직후 [실전] 암살자 전환 예약(ARMED_ON_ZERO) 상태인지 반환한다."""
    if context is None:
        return False
    st = ensure_assassin_ledger(context).get_state()
    return (
        str(st.get("execution_mode") or "").upper().strip()
        == ASSASSIN_MODE_ARMED_ON_ZERO
    )


async def activate_live_assassin_on_zero_soxl_if_armed(
    context: Any,
) -> bool:
    """
    sniper_exit_plugin.py 및 defense_plugin.py 에서 스나이퍼/바벨 SOXL 전 지층이 0주가 된 직후 호출:
    - execution_mode 가 ARMED_ON_ZERO 인 경우 즉시 LIVE(실전 암살자 단독 모드)로 승격 전환한다.
    - 만약 바벨 모드에서 열린 미체결 SGOV 주문만 있으면 취소하고, 보유 SGOV 주식은 매도하지 않고 사용자 수동 매도에 위임한다.
    """
    assn_ledger = ensure_assassin_ledger(context)
    st = assn_ledger.get_state()
    if (
        str(st.get("execution_mode") or "").upper().strip()
        != ASSASSIN_MODE_ARMED_ON_ZERO
    ):
        return False

    st_sp = context.ledger.get_state(TARGET_SYMBOL)
    buckets = buckets_from_dicts(st_sp.get("buckets", []))
    sub_buckets = buckets_from_dicts(st_sp.get("sub_buckets", []))
    if (
        buckets
        or sub_buckets
        or str(st_sp.get("buy_order_id") or "").strip()
        or str(st_sp.get("sell_order_id") or "").strip()
    ):
        return False

    if hasattr(context, "api"):
        try:
            open_soxl = await context.api.get_open_orders(symbol=TARGET_SYMBOL)
            if open_soxl:
                return False
        except Exception:
            pass
        try:
            await context.api.cancel_all_open_orders(
                symbol=BARBELL_SAFE_SYMBOL
            )
            if hasattr(context, "barbell_ledger"):
                from barbell_plugin import _sync_pending_sgov_orders

                await _sync_pending_sgov_orders(
                    context=context,
                    b_ledger=context.barbell_ledger,
                    bst=context.barbell_ledger.get_state(),
                    force_settle=True,
                )
        except Exception:
            pass

    init_seed = safe_float(
        st_sp.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD
    )
    clear_sim_pos_kw: Dict[str, Any] = {}
    if bool(st.get("has_position", False)) and not bool(
        st.get("is_live_position", False)
    ):
        clear_sim_pos_kw = {
            "has_position": False,
            "is_live_position": False,
            "alert_entry_sent": False,
            "alert_arm_100_sent": False,
            "alert_exit_sent": False,
            "alert_live_bp_shortfall_sent": False,
        }
    await assn_ledger.update_state(
        execution_mode=ASSASSIN_MODE_LIVE,
        demote_to_sim_after_exit=False,
        initial_seed_usd=round(max(100.0, init_seed), 4),
        **clear_sim_pos_kw,
    )
    context.wakeup_event.set()
    logger.info(
        "🗡️ [SOXL 0주 졸업 감지 -> [실전] 암살자 단독 모드 자동 전환 완료] 설정시드=$%.2f (보유 SGOV는 사용자 수동 매도 위임)",
        init_seed,
    )
    return True


async def toggle_assassin_live_promotion(
    context: Any,
    target_live: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    전술 제어반(/settlement) 또는 /assassin_mode 명령어로 호출되는 [모의 ⇄ 실전] 암살자 승격/복귀 컨트롤러:
    1) [모의 -> 실전 승격 요청 시]:
       - 현재 스나이퍼/바벨의 SOXL 보유 수량이 0주이고 미체결 SOXL 주문도 없으면 즉시 LIVE(실전 암살자 단독 모드)로 전환!
       - 현재 SOXL > 0주 보유 중이면 ARMED_ON_ZERO(0주 졸업 시 자동 전환 예약)로 설정하여 기존 SOXL 지층 졸업 후 무충돌 인계!
       - 바벨 모드의 보유 SGOV는 자동 매도하지 않고 사용자 수동 매도로 그대로 위임!
    2) [0주 전환 예약(ARMED_ON_ZERO) -> 해제 요청 시]:
       - 즉시 예약을 취소하고 SIMULATED([모의] 암살자)로 복귀!
    3) [실전(LIVE) -> 모의(SIMULATED) 복귀 요청 시]:
       - 현재 실전 암살자가 SOXL 포지션을 보유 중이면 당일 청산 퇴근 직후 자동 복귀(demote_to_sim_after_exit=True)로 안전 예약!
       - 무포지션(0주) 상태면 즉시 SIMULATED로 복귀하고 스나이퍼/바벨 모드를 재가동!
    """
    assn_ledger = ensure_assassin_ledger(context)
    st = assn_ledger.get_state()
    cur_mode = (
        str(st.get("execution_mode") or ASSASSIN_MODE_SIMULATED)
        .upper()
        .strip()
    )

    want_live = (
        bool(target_live)
        if target_live is not None
        else (cur_mode == ASSASSIN_MODE_SIMULATED)
    )

    st_sp = context.ledger.get_state(TARGET_SYMBOL)
    init_seed = round(
        max(
            100.0,
            safe_float(
                st_sp.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD
            ),
        ),
        4,
    )

    if want_live:
        buckets = buckets_from_dicts(st_sp.get("buckets", []))
        sub_buckets = buckets_from_dicts(st_sp.get("sub_buckets", []))
        has_pending_soxl_ord = bool(
            str(st_sp.get("buy_order_id") or "").strip()
            or str(st_sp.get("sell_order_id") or "").strip()
        )
        broker_soxl_qty = 0
        holdings_verified = not hasattr(context, "api")
        if hasattr(context, "api"):
            try:
                open_soxl = await context.api.get_open_orders(
                    symbol=TARGET_SYMBOL
                )
                if open_soxl:
                    has_pending_soxl_ord = True
                h_map, ok = await context.api.get_holdings_map_with_status(
                    symbol=TARGET_SYMBOL
                )
                if ok and isinstance(h_map, dict):
                    holdings_verified = True
                    broker_soxl_qty = safe_int(
                        (h_map.get(TARGET_SYMBOL) or {}).get("qty"), 0
                    )
            except Exception:
                holdings_verified = False

        total_soxl_held = (
            sum(b.qty for b in buckets)
            + sum(sb.qty for sb in sub_buckets)
            + broker_soxl_qty
        )
        if (
            holdings_verified
            and total_soxl_held == 0
            and not has_pending_soxl_ord
        ):
            if hasattr(context, "api"):
                try:
                    await context.api.cancel_all_open_orders(
                        symbol=BARBELL_SAFE_SYMBOL
                    )
                    if hasattr(context, "barbell_ledger"):
                        from barbell_plugin import _sync_pending_sgov_orders

                        await _sync_pending_sgov_orders(
                            context=context,
                            b_ledger=context.barbell_ledger,
                            bst=context.barbell_ledger.get_state(),
                            force_settle=True,
                        )
                except Exception:
                    pass
            updated = await assn_ledger.update_state(
                execution_mode=ASSASSIN_MODE_LIVE,
                demote_to_sim_after_exit=False,
                initial_seed_usd=init_seed,
                has_position=False,
                is_live_position=False,
                alert_entry_sent=False,
                alert_arm_100_sent=False,
                alert_exit_sent=False,
                alert_live_bp_shortfall_sent=False,
            )
            context.wakeup_event.set()
            return {
                "status": "PROMOTED_LIVE_IMMEDIATELY",
                "execution_mode": updated["execution_mode"],
                "initial_seed_usd": init_seed,
            }

        updated = await assn_ledger.update_state(
            execution_mode=ASSASSIN_MODE_ARMED_ON_ZERO,
            demote_to_sim_after_exit=False,
            initial_seed_usd=init_seed,
        )
        context.wakeup_event.set()
        return {
            "status": "ARMED_LIVE_ON_ZERO_SOXL",
            "execution_mode": updated["execution_mode"],
            "soxl_held_qty": max(
                sum(b.qty for b in buckets)
                + sum(sb.qty for sb in sub_buckets),
                broker_soxl_qty,
            ),
        }

    # [모의(SIMULATED) 복귀 분기]
    has_live_active_pos = bool(
        cur_mode == ASSASSIN_MODE_LIVE
        and (
            (
                bool(st.get("has_position", False))
                and bool(st.get("is_live_position", False))
            )
            or bool(str(st.get("pending_buy_order_id") or "").strip())
            or bool(str(st.get("pending_exit_sell_order_id") or "").strip())
        )
    )
    if has_live_active_pos:
        updated = await assn_ledger.update_state(
            demote_to_sim_after_exit=True
        )
        return {
            "status": "DEMOTE_SCHEDULED_AFTER_LIVE_EXIT",
            "execution_mode": updated["execution_mode"],
        }

    updated = await assn_ledger.update_state(
        execution_mode=ASSASSIN_MODE_SIMULATED,
        demote_to_sim_after_exit=False,
    )
    context.wakeup_event.set()
    return {
        "status": "RETURNED_TO_SIMULATED",
        "execution_mode": updated["execution_mode"],
    }
# -*- coding: utf-8 -*-
"""
# MODIFIED: assassin_plugin.py (Part 2/4 — Case 97-A 강세눌림 UG1~UG4 및 UG 전용 안전망 영구 소각 ➔
# 순수 10대 진성 급락 게이트[G1~G5 + BG1~BG5] 판정 엔진 & 출동 고정 QQQ 기반 08:15~ SN4×SN3 단일 방어망 ·
# HA 트레일링 · 4대 지표 무오염 스냅샷 추출기 · 실전 min(시드, 주문가능금액) 어댑터 · 5대 실시간 알림)
"""


# ---------------------------------------------------------------------------
# [핵심 3 · Case 97-A] 순수 10대 진성 급락 게이트 (헌법 G1~G5 + 폭락장 BG1~BG5) 단일 판정 엔진
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
    entry_type: str = "",
    dd_from_pre_high_pct: float = 0.0,
    qqq_vel_1m_pct: float = 0.0,
) -> Tuple[bool, str, str]:
    """
    Case 97-A: 5개년 1분봉 실증 검증에 따라 고점 미끼 진입 및 QQQ 베타 괴리 손절을 유발하던
    강세장 눌림목(UG1 ~ UG4)을 영구 소각하고, 오직 진성 과매도 10대 급락 게이트(G1~G5 · BG1~BG5)만 격발한다.
    """
    _ = (entry_type, dd_from_pre_high_pct, qqq_vel_1m_pct)
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

    # [헌법 Gate 1 ~ Gate 5]
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

    # [폭락장 BearGate 1 ~ BearGate 5]
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

    return False, "", "10대 진성 급락 게이트(G1~5·BG1~5) 미충족"


# ---------------------------------------------------------------------------
# [핵심 4 · Case 97-A] 출동 순간 QQQ 지수 기반 08:15~ SN4×SN3 단일 방어망 & HA 트레일링 판정기
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
    entry_gate_id: str = "",
) -> Tuple[bool, str, str]:
    _ = entry_gate_id
    if is_trailing_armed:
        return False, "", "안전망 비활성(+1.00% 점화 잠금 완료)"

    ep = safe_float(entry_price, 0.0)
    lp = safe_float(live_price, 0.0)
    if ep <= 0.0 or lp <= 0.0:
        return False, "", "가격 미확보"

    if safe_int(hm, 0) < ASSASSIN_MACRO_CUTOFF_HM:
        return False, "", "안전망 비활성(08:15 이전 골든타임)"

    cur_gain_pct = ((lp - ep) / ep) * 100.0
    if cur_gain_pct >= 0.0:
        return (
            False,
            "",
            f"🟢암살자 익절 상태({cur_gain_pct:+.2f}%) 유지 중(HOLD_PROFIT_ZONE·홀딩)",
        )

    eq_qqq = safe_float(entry_qqq_price, 0.0)
    cur_qqq = safe_float(qqq_live_price, 0.0)
    has_entry_qqq_ref = bool(eq_qqq > 0.0 and cur_qqq > 0.0)

    min_p = safe_float(post_entry_min_price, lp)
    if min_p <= 0.0:
        min_p = lp

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

    if has_entry_qqq_ref:
        qqq_chg_from_entry_pct = ((cur_qqq - eq_qqq) / eq_qqq) * 100.0
        if qqq_chg_from_entry_pct >= 0.0:
            return (
                False,
                "",
                f"🟢출동 QQQ(${eq_qqq:.2f}) 대비 상승/보합 중({qqq_chg_from_entry_pct:+.2f}%·홀딩)",
            )
        eff_qqq_drop_pct = max(0.0, -qqq_chg_from_entry_pct)
    else:
        qqq_chg_from_entry_pct = -abs(safe_float(qqq_bear_drop_amp_pct, 0.0))
        eff_qqq_drop_pct = max(0.0, safe_float(qqq_bear_drop_amp_pct, 0.0))

    if eff_qqq_drop_pct < dyn_thr:
        return (
            False,
            "",
            f"🛡️SN4 딥 안전망 감시 중(QQQ {qqq_chg_from_entry_pct:+.2f}% / 발동 -{dyn_thr:.2f}%)",
        )

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
    if is_safety_net_rising or cur_gain_pct > SAFETY_STAGE23_SOXL_LOSS_MAX_PCT:
        return (
            False,
            "",
            f"🟢SN3 스마트 방어 홀딩(QQQ {qqq_chg_from_entry_pct:+.2f}% · SOXL {cur_gain_pct:+.2f}% · 지지/경미조정 보호)",
        )

    if (
        cur_gain_pct <= SAFETY_STAGE1_HEART_STOP_PCT
        or has_entry_qqq_ref
        or qqq_vel_3m_pct <= SAFETY_STAGE23_QQQ_VEL3M_DROP_PCT
    ):
        if has_entry_qqq_ref:
            return (
                True,
                "STAGE23_DIR_BEAR_BREAK",
                (
                    f"🛡️SN4×SN3 안전망(-{dyn_thr:.2f}%) 진성폭락 칼손절"
                    f"(출동QQQ ${eq_qqq:.2f}➔${cur_qqq:.2f} [{qqq_chg_from_entry_pct:+.2f}%] · SOXL {cur_gain_pct:+.2f}%)"
                ),
            )
        return (
            True,
            "STAGE23_DIR_BEAR_BREAK",
            (
                f"🛡️SN4×SN3 방향성 역행 칼손절(SOXL {cur_gain_pct:+.2f}% · "
                f"QQQ 3분 {qqq_vel_3m_pct:+.2f}% · 하락진폭 {eff_qqq_drop_pct:.2f}%>={dyn_thr:.2f}%)"
            ),
        )

    return False, "", "🛡️SN4×SN3 안전망 감시 중"


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
    entry_gate_id: str = "",
) -> Dict[str, Any]:
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

    if not armed and (bh >= arm_p or lp >= arm_p):
        armed = True
        just_armed = True
        cur_peak = max(cur_peak, lp, bh, arm_p)

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
        entry_gate_id=entry_gate_id,
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


_LAST_ASSASSIN_WARMUP_MONO: float = 0.0


def _esc(val: Any) -> str:
    return html.escape(str(val if val is not None else ""), quote=False)


def compute_live_assassin_entry_budget_and_qty(
    initial_seed_usd: float,
    broker_bp_usd: float,
    exec_price: float,
    round_trip_fee_rate_pct: float = ROUND_TRIP_FEE_RATE_PCT,
) -> Tuple[int, float]:
    """
    [실전(LIVE)] 암살자 당일 매수 예산 및 수량 확정 공식:
    - 보유 SGOV는 자동 매도하지 않고 사용자 수동 매도에 위임하며,
      당일 매수 가용 예산은 min(설정한 기준시드, 토스 실계좌 달러 주문가능금액)으로 확정한다.
    반환값: (live_qty, allocated_budget_usd)
    """
    eff_seed = max(
        100.0, safe_float(initial_seed_usd, DEFAULT_INITIAL_SEED_USD)
    )
    eff_bp = max(0.0, safe_float(broker_bp_usd, 0.0))
    alloc_budget = round(min(eff_seed, eff_bp), 4)

    clean_p = max(0.01, safe_float(exec_price, 0.01))
    rt_pct = max(
        0.0, safe_float(round_trip_fee_rate_pct, ROUND_TRIP_FEE_RATE_PCT)
    )
    fee_mult = 1.0 + (rt_pct / 100.0) * 0.5
    unit_cost = clean_p * fee_mult

    if alloc_budget < unit_cost:
        return 0, alloc_budget
    qty = int(math.floor((alloc_budget + 1e-9) / unit_cost))
    return max(0, qty), alloc_budget


# ---------------------------------------------------------------------------
# [핵심 5] 4대 핵심 지표(RSI14 · 프리/정규VWAP · 전일종가 · 04:07프리시가) 및 QQQ 안전망 스냅샷 추출기
# ---------------------------------------------------------------------------
async def _extract_live_assassin_features_and_qqq_snapshot(
    context: Any,
    live_price_override: float = 0.0,
    now_est: Optional[datetime] = None,
    force_warmup: bool = False,
) -> Dict[str, Any]:
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
            logger.debug(
                "Assassin SOXL 400봉 1m+1d 온디맨드 워밍업 폴백: %s", exc
            )

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

    cur_bar_open = safe_float(soxl_met.get("cur_bar_open"), lp)
    cur_bar_high = max(lp, safe_float(soxl_met.get("cur_bar_high"), lp))
    cur_bar_low_raw = safe_float(soxl_met.get("cur_bar_low"), 0.0)
    cur_bar_low = min(lp, cur_bar_low_raw) if cur_bar_low_raw > 0.0 else lp

    saved_pre_h = safe_float(st_assn.get("today_pre_high_price"), 0.0)
    met_pre_h = max(
        safe_float(soxl_met.get("premarket_high"), 0.0),
        safe_float(soxl_met.get("pre_high_price"), 0.0),
        safe_float(soxl_met.get("day_high"), 0.0),
    )
    hist_list = st_assn.get("day_scout_history") or []
    max_scout_p = 0.0
    for h_item in hist_list:
        if isinstance(h_item, dict):
            ep_h = safe_float(h_item.get("entry_price"), 0.0)
            if ep_h > max_scout_p:
                max_scout_p = ep_h
    sc_anc_p = safe_float(st_assn.get("scout_anchor_price"), 0.0)
    sc1_p = safe_float(st_assn.get("scout1_open_price"), 0.0)

    eff_pre_high = max(
        saved_pre_h,
        met_pre_h,
        max_scout_p,
        sc_anc_p,
        sc1_p,
        pre_open_price if found_true_pre_o else 0.0,
        cur_bar_high if hm_now <= 929 else 0.0,
        lp if hm_now <= 929 else 0.0,
    )

    is_now_valid_distinct = not _is_collapsed_assassin_anchors(
        prev_reg_close, pre_open_price, pre_vwap
    )
    need_save_pre_high = bool(
        hm_now <= 929
        and eff_pre_high > 0.0
        and (eff_pre_high - saved_pre_h) > 1e-4
    )
    if (
        (
            (found_true_prev_c or found_true_pre_o or found_true_pre_v)
            and is_now_valid_distinct
        )
        or need_save_pre_high
    ):
        need_save_anchors = bool(
            need_save_pre_high
            or (
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
            if eff_pre_high > 0.0:
                upd_anchor_kw["today_pre_high_price"] = round(eff_pre_high, 4)
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

    if sc1_p <= 0.0:
        sc1_p = pre_open_price if pre_open_price > 0.0 else 0.0
    vs_scout1_pct = (
        ((lp - sc1_p) / sc1_p) * 100.0 if (lp > 0.0 and sc1_p > 0.0) else 0.0
    )

    dd_from_pre_high_pct = (
        ((lp - eff_pre_high) / eff_pre_high) * 100.0
        if (lp > 0.0 and eff_pre_high > 0.0)
        else 0.0
    )

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
        "pre_high_price": (
            round(eff_pre_high, 4) if eff_pre_high > 0.0 else round(lp, 4)
        ),
        "dd_from_pre_high_pct": round(dd_from_pre_high_pct, 2),
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
# [핵심 6] [모의 ⇄ 실전 Dual-Ready] 주문 실행 어댑터 및 실전 체결 동기화기
# ---------------------------------------------------------------------------
async def _dispatch_assassin_buy_order(
    context: Any,
    qty: int,
    price: float,
    is_live: bool = False,
    tag: str = "ASSN_BUY",
) -> Tuple[bool, str, float, int, bool]:
    """
    반환값: (ok, order_id, fill_or_order_price, filled_qty, is_immediately_filled)
    """
    clean_p = round(max(0.01, float(price)), 2)
    clean_q = max(1, int(qty))
    if not is_live or ASSASSIN_LIVE_ORDER_HARD_LOCK:
        sim_oid = f"SIM-{tag}-{int(time.time() * 1000)}"
        return True, sim_oid, clean_p, clean_q, True

    if context is None or not hasattr(context, "api"):
        return False, "", 0.0, 0, False

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
        oid = str((res or {}).get("orderId") or "").strip()
        if not oid:
            return False, "", 0.0, 0, False

        for _ in range(3):
            await asyncio.sleep(0.4)
            det = await context.api.get_order_detail(oid)
            if isinstance(det, dict):
                st_ord = str(det.get("status") or "").upper().strip()
                ex = (
                    det.get("execution")
                    if isinstance(det.get("execution"), dict)
                    else {}
                )
                fq = safe_int(ex.get("filledQuantity"), 0)
                fp = safe_float(ex.get("averageFilledPrice"), clean_p)
                if st_ord == "FILLED" or (
                    fq > 0 and st_ord in ("CANCELED", "REJECTED")
                ):
                    eff_q = fq if fq > 0 else clean_q
                    return (
                        True,
                        oid,
                        round(fp if fp > 0.0 else clean_p, 4),
                        eff_q,
                        True,
                    )
        return True, oid, clean_p, 0, False
    except Exception as exc:
        logger.warning("Assassin 실전 매수 발주 예외: %s", exc)
        return False, "", 0.0, 0, False


async def _dispatch_assassin_safe_cap_sell_order(
    context: Any,
    qty: int,
    cap_price: float,
    is_live: bool = False,
) -> Tuple[bool, str]:
    clean_p = round(max(0.01, float(cap_price)), 2)
    clean_q = max(1, int(qty))
    if not is_live or ASSASSIN_LIVE_ORDER_HARD_LOCK:
        return True, f"SIM-CAP500-{int(time.time() * 1000)}"

    if context is None or not hasattr(context, "api"):
        return False, ""
    try:
        sellable_q = 0
        for _ in range(8):
            sellable_q = await context.api.get_sellable_quantity(TARGET_SYMBOL)
            if sellable_q >= clean_q:
                break
            await asyncio.sleep(0.25)
        eff_q = min(clean_q, sellable_q) if sellable_q > 0 else clean_q
        cid = generate_client_order_id(prefix="assnc")
        res = await context.api.place_limit_order(
            symbol=TARGET_SYMBOL,
            side="SELL",
            quantity=eff_q,
            price=clean_p,
            client_order_id=cid,
            enforce_daymarket_block=False,
        )
        oid = str((res or {}).get("orderId") or "").strip()
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
    is_live: bool = False,
) -> Tuple[bool, float, str, bool]:
    """
    반환값: (ok, exec_or_order_price, active_sell_order_id, is_immediately_filled)
    """
    clean_p = round(max(0.01, float(target_exit_price)), 2)
    clean_q = max(1, int(qty))
    if not is_live or ASSASSIN_LIVE_ORDER_HARD_LOCK:
        return True, clean_p, "", True

    if context is None or not hasattr(context, "api"):
        return False, clean_p, "", False

    sweep_p = (
        round(max(0.01, clean_p * 0.995), 2) if is_moc_1559 else clean_p
    )
    active_oid = str(existing_cap_order_id or "").strip()

    try:
        if active_oid:
            det_cap = await context.api.get_order_detail(active_oid)
            if isinstance(det_cap, dict):
                st_cap = str(det_cap.get("status") or "").upper().strip()
                ex_cap = (
                    det_cap.get("execution")
                    if isinstance(det_cap.get("execution"), dict)
                    else {}
                )
                fp_cap = safe_float(ex_cap.get("averageFilledPrice"), clean_p)
                if st_cap == "FILLED":
                    return (
                        True,
                        round(fp_cap if fp_cap > 0.0 else clean_p, 4),
                        active_oid,
                        True,
                    )

            try:
                mod_res = await context.api.modify_order(
                    order_id=active_oid,
                    new_price=sweep_p,
                )
                active_oid = str(
                    (mod_res or {}).get("orderId") or active_oid
                ).strip()
            except Exception:
                try:
                    await context.api.cancel_order(active_oid)
                except Exception:
                    pass
                active_oid = ""

        if not active_oid:
            await context.api.cancel_all_open_orders(symbol=TARGET_SYMBOL)
            sellable_q = 0
            for _ in range(8):
                sellable_q = await context.api.get_sellable_quantity(
                    TARGET_SYMBOL
                )
                if sellable_q >= clean_q:
                    break
                await asyncio.sleep(0.25)
            eff_q = min(clean_q, sellable_q) if sellable_q > 0 else clean_q
            cid = generate_client_order_id(prefix="assnx")
            ord_res = await context.api.place_limit_order(
                symbol=TARGET_SYMBOL,
                side="SELL",
                quantity=eff_q,
                price=sweep_p,
                client_order_id=cid,
                enforce_daymarket_block=False,
            )
            active_oid = str((ord_res or {}).get("orderId") or "").strip()

        if active_oid:
            for _ in range(3):
                await asyncio.sleep(0.4)
                det = await context.api.get_order_detail(active_oid)
                if isinstance(det, dict):
                    st_ord = str(det.get("status") or "").upper().strip()
                    ex = (
                        det.get("execution")
                        if isinstance(det.get("execution"), dict)
                        else {}
                    )
                    fq = safe_int(ex.get("filledQuantity"), 0)
                    fp = safe_float(ex.get("averageFilledPrice"), sweep_p)
                    if st_ord == "FILLED" or (
                        fq > 0 and st_ord in ("CANCELED", "REJECTED")
                    ):
                        return (
                            True,
                            round(fp if fp > 0.0 else sweep_p, 4),
                            active_oid,
                            True,
                        )
            return True, sweep_p, active_oid, False
    except Exception as exc:
        logger.warning("Assassin 실전 출구 스윕 예외: %s", exc)
    return False, sweep_p, active_oid, False


# ---------------------------------------------------------------------------
# [핵심 7] 5대 라이프사이클 실시간 텔레그램 푸시 알림 발송기 ([모의] / [실전] 자동 표기 + 다회차 카운트 요약)
# ---------------------------------------------------------------------------
def _mode_badge(st: Dict[str, Any]) -> str:
    return "[실전]" if is_assassin_live_mode_state(st) else "[모의]"


async def _send_1_scout_dispatched_alert(
    context: Any,
    st: Dict[str, Any],
    scout: IndependentScoutUnit,
    total_active_scouts: int,
    prior_wins: int,
    gate_eval_note: str,
) -> None:
    if context is None or not hasattr(context, "send_slim_alert"):
        return
    m_tag = _mode_badge(st)
    bar_badge = "📈1분양봉" if scout.is_bull_bar else "📉1분음봉"
    foot_note = (
        "실전 타점 정찰(정찰병은 가상 1주)"
        if m_tag == "[실전]"
        else "실주문 100% 차단"
    )
    lines = [
        f"🕵️ <b>[{m_tag} 암살자 정찰병 #{scout.scout_id} 파견]</b> ({_esc(scout.entry_type)})",
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
        f"🕒 {scout.entry_time_est} EST ({foot_note})",
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
    m_tag = _mode_badge(st)
    scouts_cnt = safe_int(st.get("day_scout_seq"), 0)
    scout_wins = safe_int(st.get("prior_scout_wins_today"), 0)
    no_tr_days = safe_int(st.get("no_trade_days"), 0)
    tot_days = safe_int(st.get("total_trade_days"), 0)
    win_days = safe_int(st.get("win_days"), 0)
    win_rate = (
        (float(win_days) / float(tot_days)) * 100.0 if tot_days > 0 else 100.0
    )
    cum_gt_disp = safe_int(st.get("cum_gt_gate_dispatches"), 0)
    cum_gt_wins = safe_int(st.get("cum_gt_gate_win_exits"), 0)
    lines = [
        f"🏠 <b>[{m_tag} 암살자 08:15 거시지표 컷오프 · 무매매 안전 퇴근]</b>",
        "──────────────",
        f"▫️ 금일정찰: 총 <b>{scouts_cnt}명</b> 파견 (+1% 독립익절 <b>{scout_wins}회</b>)",
        "▫️ 퇴근사유: 04:07 ~ 08:14 EST 구간 10대 진성 급락 게이트(G1~5·BG1~5) 미충족 (현금 100% 보존)",
        f"▫️ 08:15 지표: 현재가 <b>${feat['live_price']:.2f}</b> · RSI <b>{feat['rsi_14']:.1f}</b> · VWAP <b>${feat['pre_vwap']:.2f}</b>({feat['vs_vwap_pct']:+.2f}%)",
        f"🏆 누적전적: 출격 <b>{tot_days}일</b>({win_days}승 · 승률 <b>{win_rate:.1f}%</b>) · 무매매퇴근 <b>{no_tr_days}일</b>",
        f"🕵️ GT다회차누적: 10G출동 <b>{cum_gt_disp}회</b> ➔ 익절퇴근 <b>{cum_gt_wins}회</b> (정규장 폐기)",
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
    m_tag = _mode_badge(st)
    is_live_pos = bool(st.get("is_live_position", False))
    gate_id = str(st.get("entry_gate_id") or "")
    gate_desc = str(st.get("entry_gate_desc") or "")
    trig_mode = str(st.get("entry_trigger_mode") or "")
    ep = safe_float(st.get("entry_price"), 0.0)
    eq_qqq = safe_float(
        st.get("entry_qqq_price"), safe_float(feat.get("qqq_live_price"), 0.0)
    )
    arm_p = safe_float(st.get("arm_100_price"), 0.0)
    cap_p = safe_float(st.get("cap_500_price"), 0.0)
    dyn_thr = safe_float(
        st.get("dyn_qqq_stage2_thr_pct"), SAFETY_DYN_QQQ_MIN_THR_PCT
    )
    seq_no = max(1, safe_int(st.get("entry_scout_seq"), 1))
    trig_label = (
        f"T03_A 1분 눌림 스캔(정찰 #{seq_no} 이후)"
        if trig_mode.startswith("T03A_")
        else f"정찰병 #{seq_no} 파견 타점"
    )
    safety_line = (
        f"🛡️ 안전망(SN4×SN3): 08:15~ 출동QQQ(<b>${eq_qqq:.2f}</b>) 대비 "
        f"<b>-{dyn_thr:.2f}%</b> 딥안전망(지지붕괴 진성폭락만 손절)"
    )

    if is_live_pos:
        l_qty = safe_int(st.get("live_held_qty"), 0)
        l_inv = safe_float(st.get("live_invested_usd"), 0.0)
        l_bud = safe_float(st.get("live_entry_budget_usd"), l_inv)
        size_line = (
            f"🔥 실전투입: <b>{l_qty}주</b> (<b>${l_inv:,.2f}</b> / 확정예산 min(시드,예수금)=<b>${l_bud:,.2f}</b>)"
        )
    else:
        s_qty = safe_int(st.get("simple_held_qty"), 0)
        s_inv = safe_float(st.get("simple_invested_usd"), 0.0)
        c_qty = safe_int(st.get("comp_held_qty"), 0)
        c_inv = safe_float(st.get("comp_invested_usd"), 0.0)
        size_line = (
            f"💵 단리투입: <b>{s_qty}주</b> (${s_inv:,.2f}) | 📈 복리투입: <b>{c_qty}주</b> (${c_inv:,.2f})"
        )

    lines = [
        f"🗡️ <b>[{m_tag} 암살자 진성 급락 게이트 [{_esc(gate_id)}] 포착 · 본대 전격 진입!]</b>",
        "──────────────",
        f"🎯 격발게이트: <b>{_esc(gate_desc)}</b>",
        f"⚡ 진입단가: <b>${ep:.2f}</b> · 고정QQQ: <b>${eq_qqq:.2f}</b> ({_esc(trig_label)})",
        size_line,
        "──────────────",
        "📊 <b>[본대 진입 시점 4대 지표 박제]</b>",
        f"① RSI(14): <b>{safe_float(st.get('entry_rsi_14'), feat['rsi_14']):.1f}</b> | ② 프리VWAP: <b>${safe_float(st.get('entry_vwap'), feat['pre_vwap']):.2f}</b> ({safe_float(st.get('entry_vs_vwap_pct'), feat['vs_vwap_pct']):+.2f}%)",
        f"③ 전일종가: <b>${safe_float(st.get('entry_prev_close'), feat['prev_reg_close']):.2f}</b> ({safe_float(st.get('entry_vs_prev_close_pct'), feat['vs_prev_close_pct']):+.2f}%) | ④ 프리시가: <b>${safe_float(st.get('entry_pre_open'), feat['pre_open_price']):.2f}</b> ({safe_float(st.get('entry_vs_pre_open_pct'), feat['vs_pre_open_pct']):+.2f}%)",
        "──────────────",
        f"👑 상단안전캡(+5.0%): <b>${cap_p:.2f}</b> 선장전 완료",
        f"🔥 트레일링점화(+1.0%): <b>${arm_p:.2f}</b> 도달 시 보존선 잠금 & 0.4초 추적",
        safety_line,
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
    m_tag = _mode_badge(st)
    ep = safe_float(st.get("entry_price"), 0.0)
    arm_p = safe_float(st.get("arm_100_price"), 0.0)
    cap_p = safe_float(st.get("cap_500_price"), 0.0)
    cur_g = ((live_price - ep) / ep) * 100.0 if ep > 0.0 else 1.0
    lines = [
        f"🔥 <b>[{m_tag} 암살자 +1.00% 도달 · HA 트레일링 고주파(0.4s) 추적 개시!]</b>",
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
    was_live_pos: bool,
    now_est: datetime,
) -> None:
    if context is None or not hasattr(context, "send_slim_alert"):
        return
    m_tag = "[실전]" if was_live_pos else "[모의]"
    ep = safe_float(st.get("entry_price"), 0.0)
    xp = safe_float(st.get("today_exit_price"), 0.0)
    gain_pct = safe_float(st.get("today_gain_pct"), 0.0)
    s_net = safe_float(st.get("today_simple_net_usd"), 0.0)
    c_net = safe_float(st.get("today_comp_net_usd"), 0.0)
    l_net = safe_float(st.get("today_live_net_usd"), 0.0)
    s_cum = safe_float(st.get("simple_cum_net_usd"), 0.0)
    c_cum = safe_float(st.get("comp_cum_net_usd"), 0.0)
    l_cum = safe_float(st.get("live_cum_net_usd"), 0.0)
    init_s = max(100.0, safe_float(st.get("initial_seed_usd"), 10000.0))
    s_roi = (s_cum / init_s) * 100.0
    c_roi = (c_cum / init_s) * 100.0

    tot_d = safe_int(st.get("total_trade_days"), 0)
    win_d = safe_int(st.get("win_days"), 0)
    loss_d = safe_int(st.get("loss_days"), 0)
    wr = (float(win_d) / float(tot_d)) * 100.0 if tot_d > 0 else 100.0
    ref_pnl = l_net if was_live_pos else s_net
    header_icon = "🎯" if ref_pnl >= 0.0 else "🛡️"
    safety_tot = (
        safe_int(st.get("exit_safety_stage1_cnt"), 0)
        + safe_int(st.get("exit_safety_stage23_cnt"), 0)
        + safe_int(st.get("exit_ug_qqq_stop_cnt"), 0)
    )

    td_gt_disp = safe_int(st.get("today_gt_gate_dispatches"), 0)
    td_gt_wins = safe_int(st.get("today_gt_gate_win_exits"), 0)
    cum_gt_disp = safe_int(st.get("cum_gt_gate_dispatches"), 0)
    cum_gt_wins = safe_int(st.get("cum_gt_gate_win_exits"), 0)
    hm_exit = now_est.hour * 100 + now_est.minute
    gt_status_tail = (
        "08:14까지 무소음 카운트 지속"
        if hm_exit < ASSASSIN_MACRO_CUTOFF_HM
        else "08:15 마감 완료"
    )

    pnl_line = (
        f"🔥 금일 실전확정손익: <b>{l_net:+,.2f}$</b> (실전누적 <b>{l_cum:+,.2f}$</b>)"
        if was_live_pos
        else f"💵 금일 단리손익: <b>{s_net:+,.2f}$</b> | 📈 금일 복리손익: <b>{c_net:+,.2f}$</b>"
    )
    lines = [
        f"{header_icon} <b>[{m_tag} 암살자 당일 매매 종료 및 퇴근 결산]</b>",
        "──────────────",
        f"▫️ 출구사유: <b>{_esc(st.get('today_exit_reason'))}</b>",
        f"▫️ 체결내역: 진입 <b>${ep:.2f}</b> ➔ 청산 <b>${xp:.2f}</b> (<b>{gain_pct:+.2f}%</b>)",
        pnl_line,
        f"🕵️ GT다회차정찰: 금일 익절 <b>{td_gt_wins}/{td_gt_disp}회</b> · 누적 <b>{cum_gt_wins}/{cum_gt_disp}회</b> ({gt_status_tail})",
        "──────────────",
        f"🏆 <b>[{m_tag} 암살자 누적 성적표]</b>",
        f"▫️ 누적전적: <b>{tot_d}일</b> 출격 (<b>{win_d}승 {loss_d}패</b> · 승률 <b>{wr:.2f}%</b>)",
        f"▫️ 출구분포: +5%홈런 <b>{safe_int(st.get('exit_cap500_cnt'), 0)}</b> · HA부스트 <b>{safe_int(st.get('exit_ha_boost_cnt'), 0)}</b> · +1%보존 <b>{safe_int(st.get('exit_floor100_cnt'), 0)}</b> · 안전망방어 <b>{safety_tot}</b>",
        f"💵 단리 누적순익: <b>{s_cum:+,.2f}$</b> ({s_roi:+.2f}%)",
        f"📈 복리 누적순익: <b>{c_cum:+,.2f}$</b> ({c_roi:+.2f}% · 자산 <b>${safe_float(st.get('comp_free_cash_usd'), init_s):,.2f}</b>)",
        f"🕒 {now_est.strftime('%m-%d %H:%M:%S EST')} (본대 1일 1회 퇴근 완료)",
    ]
    await context.send_slim_alert("\n".join(lines))
# -*- coding: utf-8 -*-
"""
# MODIFIED: assassin_plugin.py (Part 3/4 — Case 96 & Case 97-A 골든타임[04:07 ~ 08:14 EST] 다회차
# 순수 10대 진성 급락 게이트 [모의] 정찰병 무소음 출동·익절 퇴근 카운터[08:15 EST 정규장 폐기 잠금 · UG 분기 소각] 및
# 본대[1일 1회 출근 원칙] 포지션 진입 · 실전 미체결 매수/출구 동기화 · 청산 결산기)
"""


# ---------------------------------------------------------------------------
# [핵심 7-B · Case 96 & Case 97-A] 골든타임(04:07 ~ 08:14 EST) 다회차 10대 진성게이트 [모의] 정찰병 카운터 (정규장 폐기)
# ---------------------------------------------------------------------------
def _update_gt_history_round_entry(
    history_raw: Any,
    round_no: int,
    exit_time_est: str,
    exit_price: float,
    ep_fallback: float,
    status_code: str,
) -> List[Dict[str, Any]]:
    hist: List[Dict[str, Any]] = [
        dict(it)
        for it in (history_raw if isinstance(history_raw, list) else [])
        if isinstance(it, dict)
    ]
    matched = False
    for item in reversed(hist):
        if safe_int(item.get("round_no"), -1) == round_no:
            ep_h = max(0.01, safe_float(item.get("entry_price"), ep_fallback))
            g_pct = ((exit_price - ep_h) / ep_h) * 100.0 if ep_h > 0.0 else 0.0
            item["exit_time_est"] = exit_time_est
            item["exit_price"] = round(exit_price, 2)
            item["gain_pct"] = round(g_pct, 2)
            item["status"] = status_code
            matched = True
            break

    if not matched:
        ep_eff = max(0.01, ep_fallback)
        g_pct = ((exit_price - ep_eff) / ep_eff) * 100.0
        hist.append(
            {
                "round_no": round_no,
                "gate_id": "G1",
                "trigger_mode": "SCOUT_GATE",
                "entry_time_est": exit_time_est,
                "entry_price": round(ep_eff, 4),
                "target_price": round(
                    math.ceil((ep_eff * 1.010 - 1e-9) * 100.0) / 100.0, 2
                ),
                "exit_time_est": exit_time_est,
                "exit_price": round(exit_price, 2),
                "gain_pct": round(g_pct, 2),
                "status": status_code,
            }
        )
    return hist[-GT_GATE_SCOUT_MAX_HISTORY:]


async def _try_dispatch_gt_multi_gate_scout(
    assn_ledger: AssassinSimLedger,
    st: Dict[str, Any],
    feat: Dict[str, Any],
    gate_id: str,
    trigger_mode: str,
    entry_scout_seq: int,
    now_est: datetime,
    now_ts: float,
) -> Tuple[Dict[str, Any], bool]:
    """
    04:07 ~ 08:14 EST 골든타임 내 10대 진성 급락 게이트 조건 충족 시 호출:
    - 현재 출동 중인 다회차 [모의] 게이트 정찰병이 없고(순차 라운드),
      직전 라운드 퇴근 후 60.0초 쿨다운이 경과했으면 무소음으로 신규 라운드 정찰병을 출동시킨다.
    - 08:15 EST 이후(정규장 포함)에는 절대 출동하지 않는다.
    """
    hm = now_est.hour * 100 + now_est.minute
    if (
        hm < ASSASSIN_SCOUT_START_HM
        or hm >= ASSASSIN_MACRO_CUTOFF_HM
        or bool(st.get("gt_gate_scout_done", False))
    ):
        return st, False

    if isinstance(st.get("gt_active_gate_scout"), dict):
        return st, False

    last_exit_ts = safe_float(st.get("last_gt_gate_exit_ts"), 0.0)
    if (
        last_exit_ts > 0.0
        and (now_ts - last_exit_ts) < GT_GATE_SCOUT_COOLDOWN_SEC
    ):
        return st, False

    lp = safe_float(feat.get("live_price"), 0.0)
    if lp <= 0.0:
        return st, False

    clean_gid = str(gate_id or "G1").upper().strip()
    tp = (
        math.ceil(
            (lp * (1.0 + GT_GATE_SCOUT_PROFIT_TARGET_PCT / 100.0) - 1e-9)
            * 100.0
        )
        / 100.0
    )
    new_round = safe_int(st.get("today_gt_gate_dispatches"), 0) + 1
    new_cum_disp = safe_int(st.get("cum_gt_gate_dispatches"), 0) + 1
    eq_qqq = round(safe_float(feat.get("qqq_live_price"), 0.0), 4)
    time_str = now_est.strftime("%H:%M:%S")

    active_unit: Dict[str, Any] = {
        "round_no": new_round,
        "gate_id": clean_gid,
        "trigger_mode": str(trigger_mode or "SCOUT_GATE"),
        "entry_time_est": time_str,
        "entry_ts": now_ts,
        "entry_price": round(lp, 4),
        "target_price": round(tp, 2),
        "entry_qqq_price": eq_qqq,
        "scout_seq_at_entry": max(1, safe_int(entry_scout_seq, 1)),
    }

    hist = [
        dict(it)
        for it in (st.get("today_gt_gate_history") or [])
        if isinstance(it, dict)
    ]
    hist.append(
        {
            "round_no": new_round,
            "gate_id": clean_gid,
            "trigger_mode": str(trigger_mode or "SCOUT_GATE"),
            "entry_time_est": time_str,
            "entry_price": round(lp, 4),
            "target_price": round(tp, 2),
            "exit_time_est": "",
            "exit_price": 0.0,
            "gain_pct": 0.0,
            "status": "ACTIVE",
        }
    )

    st = await assn_ledger.update_state(
        gt_active_gate_scout=active_unit,
        last_gt_gate_scout_seq=max(1, safe_int(entry_scout_seq, 1)),
        today_gt_gate_dispatches=new_round,
        cum_gt_gate_dispatches=new_cum_disp,
        today_gt_gate_history=hist[-GT_GATE_SCOUT_MAX_HISTORY:],
    )
    logger.info(
        "🕵️ [Case 96 골든타임 다회차 10G 정찰병 #%d 출동] 게이트=%s · 진입=$%.2f ➔ 목표=$%.2f(+1.00%%) · 무소음 카운트 추적",
        new_round,
        clean_gid,
        lp,
        tp,
    )
    return st, True


async def _update_gt_multi_gate_scout_on_tick(
    assn_ledger: AssassinSimLedger,
    st: Dict[str, Any],
    feat: Dict[str, Any],
    hm: int,
    now_est: datetime,
    now_ts: float,
) -> Dict[str, Any]:
    """
    매 틱 호출되어 골든타임(04:07 ~ 08:14 EST) 다회차 [모의] 게이트 정찰병의
    1) +1.00% 도달 익절 퇴근 카운트(+1)
    2) 골든타임 중 -3.00% 급락 시 슬롯 해제(역행 해제 카운트)
    3) 08:15 EST 도래 시 당일 골든타임 정찰 즉시 마감 및 영구 잠금(정규장 폐기)
    을 무소음으로 정산한다.
    """
    if bool(st.get("gt_gate_scout_done", False)):
        return st

    lp = safe_float(feat.get("live_price"), 0.0)
    bh = max(lp, safe_float(feat.get("cur_bar_high"), lp))
    time_str = now_est.strftime("%H:%M:%S")

    active_gs = st.get("gt_active_gate_scout")
    if isinstance(active_gs, dict) and lp > 0.0:
        r_no = max(1, safe_int(active_gs.get("round_no"), 1))
        gid = str(active_gs.get("gate_id") or "G1").upper().strip()
        ep = max(0.01, safe_float(active_gs.get("entry_price"), lp))
        tp_def = (
            math.ceil(
                (ep * (1.0 + GT_GATE_SCOUT_PROFIT_TARGET_PCT / 100.0) - 1e-9)
                * 100.0
            )
            / 100.0
        )
        tp = max(ep, safe_float(active_gs.get("target_price"), tp_def))
        entry_ts = safe_float(active_gs.get("entry_ts"), 0.0)
        entry_hm = str(active_gs.get("entry_time_est") or "")[:5]
        same_min = bool(entry_hm and now_est.strftime("%H:%M") == entry_hm)
        eff_high = lp if same_min else bh

        # 1) +1.00% 익절 목표 도달 시 즉시 익절 퇴근 카운트!
        if (now_ts - entry_ts) >= 1.0 and eff_high >= tp:
            exec_p = round(max(tp, lp) if lp >= tp else tp, 2)
            new_td_wins = safe_int(st.get("today_gt_gate_win_exits"), 0) + 1
            new_cum_wins = safe_int(st.get("cum_gt_gate_win_exits"), 0) + 1
            new_max_wins = max(
                safe_int(st.get("max_daily_gt_gate_wins"), 0), new_td_wins
            )
            upd_hist = _update_gt_history_round_entry(
                st.get("today_gt_gate_history"),
                round_no=r_no,
                exit_time_est=time_str,
                exit_price=exec_p,
                ep_fallback=ep,
                status_code="WIN_100",
            )
            st = await assn_ledger.update_state(
                gt_active_gate_scout=None,
                last_gt_gate_exit_ts=now_ts,
                last_gt_gate_exit_price=exec_p,
                today_gt_gate_win_exits=new_td_wins,
                cum_gt_gate_win_exits=new_cum_wins,
                max_daily_gt_gate_wins=new_max_wins,
                today_gt_gate_history=upd_hist,
            )
            logger.info(
                "✅ [Case 96 골든타임 다회차 10G 정찰병 #%d 익절 퇴근!] 게이트=%s · $%.2f ➔ $%.2f · 금일익절=%d/%d회 (누적 %d회)",
                r_no,
                gid,
                ep,
                exec_p,
                new_td_wins,
                safe_int(st.get("today_gt_gate_dispatches"), new_td_wins),
                new_cum_wins,
            )
            active_gs = None

        # 2) 골든타임 진행 중 -3.00% 급락 도달 시 슬롯 해제 판정
        elif hm < ASSASSIN_MACRO_CUTOFF_HM and (now_ts - entry_ts) >= 1.0:
            cur_gain_pct = ((lp - ep) / ep) * 100.0
            if cur_gain_pct <= SAFETY_STAGE1_HEART_STOP_PCT:
                exec_sp = round(lp, 2)
                new_td_stops = (
                    safe_int(st.get("today_gt_gate_stop_exits"), 0) + 1
                )
                new_cum_stops = (
                    safe_int(st.get("cum_gt_gate_stop_exits"), 0) + 1
                )
                upd_hist = _update_gt_history_round_entry(
                    st.get("today_gt_gate_history"),
                    round_no=r_no,
                    exit_time_est=time_str,
                    exit_price=exec_sp,
                    ep_fallback=ep,
                    status_code="STOP_3PCT",
                )
                st = await assn_ledger.update_state(
                    gt_active_gate_scout=None,
                    last_gt_gate_exit_ts=now_ts,
                    last_gt_gate_exit_price=exec_sp,
                    today_gt_gate_stop_exits=new_td_stops,
                    cum_gt_gate_stop_exits=new_cum_stops,
                    today_gt_gate_history=upd_hist,
                )
                active_gs = None

    # 3) 08:15 EST 도래 시 : 정규장 폐기 원칙에 따라 다회차 게이트 정찰 즉시 마감 잠금!
    if hm >= ASSASSIN_MACRO_CUTOFF_HM:
        upd_cut_kw: Dict[str, Any] = {
            "gt_gate_scout_done": True,
            "gt_active_gate_scout": None,
        }
        if isinstance(active_gs, dict):
            r_no_c = max(1, safe_int(active_gs.get("round_no"), 1))
            ep_c = max(0.01, safe_float(active_gs.get("entry_price"), lp))
            exec_cp = round(lp if lp > 0.0 else ep_c, 2)
            upd_cut_kw["today_gt_gate_cutoff_exits"] = (
                safe_int(st.get("today_gt_gate_cutoff_exits"), 0) + 1
            )
            upd_cut_kw["cum_gt_gate_cutoff_exits"] = (
                safe_int(st.get("cum_gt_gate_cutoff_exits"), 0) + 1
            )
            upd_cut_kw["today_gt_gate_history"] = (
                _update_gt_history_round_entry(
                    st.get("today_gt_gate_history"),
                    round_no=r_no_c,
                    exit_time_est=time_str,
                    exit_price=exec_cp,
                    ep_fallback=ep_c,
                    status_code="CUTOFF_0815",
                )
            )

        td_wins_final = safe_int(st.get("today_gt_gate_win_exits"), 0)
        if td_wins_final >= 2:
            upd_cut_kw["cum_gt_multi_win_days"] = (
                safe_int(st.get("cum_gt_multi_win_days"), 0) + 1
            )
        upd_cut_kw["max_daily_gt_gate_wins"] = max(
            safe_int(st.get("max_daily_gt_gate_wins"), 0), td_wins_final
        )
        if bool(st.get("is_session_done", False)) or bool(
            st.get("has_position", False)
        ):
            upd_cut_kw["scout_units"] = []
            upd_cut_kw["scout_has_active_l1"] = False

        st = await assn_ledger.update_state(**upd_cut_kw)

    return st


# ---------------------------------------------------------------------------
# [핵심 8] 본대(Main Force · 1일 1회 출근 원칙) 진입 확정 · 실전 미체결 동기화 및 청산 결산기
# ---------------------------------------------------------------------------
async def _finalize_assassin_position_entry(
    context: Any,
    assn_ledger: AssassinSimLedger,
    st: Dict[str, Any],
    feat: Dict[str, Any],
    fill_p: float,
    filled_live_qty: int,
    live_budget_usd: float,
    is_live: bool,
    buy_oid: str,
    meta: Dict[str, Any],
    now_est: datetime,
) -> str:
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

    simple_qty = max(1, int(math.floor(init_seed / (fill_p * fee_mult))))
    comp_qty = max(1, int(math.floor(comp_cash / (fill_p * fee_mult))))
    eff_cap_qty = filled_live_qty if is_live else comp_qty

    arm_p = (
        math.ceil(
            (fill_p * (1.0 + ASSASSIN_ARM_IGNITION_PCT / 100.0) - 1e-9)
            * 100.0
        )
        / 100.0
    )
    cap_p = round(fill_p * (1.0 + ASSASSIN_SAFE_CAP_PCT / 100.0), 2)
    _, cap_oid = await _dispatch_assassin_safe_cap_sell_order(
        context=context,
        qty=eff_cap_qty,
        cap_price=cap_p,
        is_live=is_live,
    )

    gate_id = str(meta.get("gate_id") or "G1")
    gate_counts = dict(st.get("gate_hit_counts") or {})
    gate_counts[gate_id] = safe_int(gate_counts.get(gate_id), 0) + 1

    state_kw: Dict[str, Any] = {
        "session_phase": "MAIN_FORCE_ACTIVE",
        "has_position": True,
        "is_live_position": bool(is_live),
        "live_held_qty": (filled_live_qty if is_live else 0),
        "live_invested_usd": (
            round(float(filled_live_qty) * fill_p, 4) if is_live else 0.0
        ),
        "live_entry_budget_usd": (
            round(live_budget_usd, 4) if is_live else 0.0
        ),
        "entry_gate_id": gate_id,
        "entry_gate_desc": str(meta.get("gate_desc") or gate_id),
        "entry_trigger_mode": str(
            meta.get("entry_trigger_mode") or "SCOUT_GATE"
        ),
        "entry_time_est": now_est.strftime("%H:%M:%S"),
        "entry_ts": time.time(),
        "entry_price": round(fill_p, 4),
        "entry_qqq_price": round(
            safe_float(
                meta.get("entry_qqq_price"),
                safe_float(feat.get("qqq_live_price"), 0.0),
            ),
            4,
        ),
        "qqq_chg_from_entry_pct": 0.0,
        "entry_scout_seq": max(1, safe_int(meta.get("entry_scout_seq"), 1)),
        "entry_rsi_14": round(safe_float(meta.get("entry_rsi_14"), 50.0), 2),
        "entry_vwap": round(safe_float(meta.get("entry_vwap"), 0.0), 4),
        "entry_vs_vwap_pct": round(
            safe_float(meta.get("entry_vs_vwap_pct"), 0.0), 2
        ),
        "entry_prev_close": round(
            safe_float(meta.get("entry_prev_close"), fill_p), 4
        ),
        "entry_vs_prev_close_pct": round(
            safe_float(meta.get("entry_vs_prev_close_pct"), 0.0), 2
        ),
        "entry_pre_open": round(
            safe_float(meta.get("entry_pre_open"), 0.0), 4
        ),
        "entry_vs_pre_open_pct": round(
            safe_float(meta.get("entry_vs_pre_open_pct"), 0.0), 2
        ),
        "nq_entry_bear_amp_pct": round(
            safe_float(meta.get("nq_bear_amp"), SAFETY_QQQ_BASE_AMP_PCT), 3
        ),
        "dyn_qqq_stage2_thr_pct": round(
            safe_float(meta.get("dyn_qqq_thr"), SAFETY_DYN_QQQ_MIN_THR_PCT), 2
        ),
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
        "pending_buy_order_id": "",
        "pending_buy_ordered_qty": 0,
        "pending_buy_price": 0.0,
        "pending_buy_mono": 0.0,
        "pending_buy_meta": {},
        "safe_cap_sell_order_id": cap_oid,
        "alert_entry_sent": True,
        "gate_hit_counts": gate_counts,
    }
    extra_u = meta.get("extra_state_updates")
    if isinstance(extra_u, dict) and extra_u:
        state_kw.update(extra_u)

    st = await assn_ledger.update_state(**state_kw)
    await _send_3_truth_gate_entry_alert(
        context=context, st=st, feat=feat, now_est=now_est
    )
    return f"ASSASSIN_MAIN_FORCE_ENTERED_{gate_id}"


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
    _ = now_ts
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
    is_live = is_assassin_live_mode_state(st)

    live_budget_usd = 0.0
    if is_live:
        raw_bp = await context.api.get_buying_power_usd(safety_buffer_pct=0.2)
        if raw_bp <= 0.0:
            await asyncio.sleep(0.25)
            raw_bp = await context.api.get_buying_power_usd(
                safety_buffer_pct=0.2
            )
        order_qty, live_budget_usd = compute_live_assassin_entry_budget_and_qty(
            initial_seed_usd=init_seed,
            broker_bp_usd=raw_bp,
            exec_price=lp,
            round_trip_fee_rate_pct=rt_fee_pct,
        )
        if order_qty <= 0:
            if not bool(st.get("alert_live_bp_shortfall_sent", False)):
                await assn_ledger.update_state(
                    alert_live_bp_shortfall_sent=True
                )
                if hasattr(context, "send_slim_alert"):
                    await context.send_slim_alert(
                        title="⚠️ [[실전] 암살자 주문가능금액 부족 보류]",
                        body=(
                            f"게이트[{gate_id}] 포착(@ ${lp:.2f}) 되었으나 계좌 주문가능금액(${raw_bp:,.2f})이 "
                            f"1주 매수 비용 미만이어서 진입을 보류했습니다. (보유 SGOV 수동 매도 또는 달러 예수금 확인 요망)"
                        ),
                    )
            return "ASSASSIN_LIVE_INSUFFICIENT_BP"
    else:
        order_qty = max(1, int(math.floor(comp_cash / (lp * fee_mult))))

    entry_qqq_p = round(safe_float(feat.get("qqq_live_price"), 0.0), 4)
    raw_nq_amp = safe_float(feat.get("qqq_bear_drop_amp_pct"), 0.0)
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

    meta: Dict[str, Any] = {
        "gate_id": gate_id,
        "gate_desc": gate_desc,
        "entry_scout_seq": entry_scout_seq,
        "entry_trigger_mode": entry_trigger_mode,
        "entry_qqq_price": entry_qqq_p,
        "entry_rsi_14": entry_rsi_14,
        "entry_vwap": entry_vwap,
        "entry_vs_vwap_pct": entry_vs_vwap_pct,
        "entry_prev_close": entry_prev_close,
        "entry_vs_prev_close_pct": entry_vs_prev_close_pct,
        "entry_pre_open": entry_pre_open,
        "entry_vs_pre_open_pct": entry_vs_pre_open_pct,
        "nq_bear_amp": nq_bear_amp,
        "dyn_qqq_thr": dyn_qqq_thr,
        "live_budget_usd": live_budget_usd,
        "extra_state_updates": extra_state_updates or {},
    }

    ok_buy, buy_oid, fill_p, filled_q, imm_filled = (
        await _dispatch_assassin_buy_order(
            context=context,
            qty=order_qty,
            price=lp,
            is_live=is_live,
            tag=f"GATE_{gate_id}",
        )
    )
    if not ok_buy:
        return "ASSASSIN_BUY_FAILED"

    if not imm_filled and is_live:
        await assn_ledger.update_state(
            pending_buy_order_id=buy_oid,
            pending_buy_ordered_qty=order_qty,
            pending_buy_price=fill_p,
            pending_buy_mono=time.monotonic(),
            pending_buy_meta=meta,
        )
        context.assassin_high_freq_active = True
        if context is not None and hasattr(context, "send_slim_alert"):
            await context.send_slim_alert(
                title=(
                    f"📡 [[실전] 암살자 [{gate_id}] "                    "지정가 매수 접수]"
                ),
                body=(
                    f"{order_qty}주 @ 지정가 ${fill_p:.2f} "                    f"(예산 ${live_budget_usd:,.2f} · "                    f"60초 체결대기 · ID={buy_oid})"
                ),
            )
        return f"ASSASSIN_LIVE_BUY_PENDING_{gate_id}"

    return await _finalize_assassin_position_entry(
        context=context,
        assn_ledger=assn_ledger,
        st=st,
        feat=feat,
        fill_p=fill_p,
        filled_live_qty=(filled_q if filled_q > 0 else order_qty),
        live_budget_usd=live_budget_usd,
        is_live=is_live,
        buy_oid=buy_oid,
        meta=meta,
        now_est=now_est,
    )


async def _sync_live_pending_buy_order(
    context: Any,
    assn_ledger: AssassinSimLedger,
    st: Dict[str, Any],
    feat: Dict[str, Any],
    hm: int,
    now_est: datetime,
) -> str:
    buy_oid = str(st.get("pending_buy_order_id") or "").strip()
    if not buy_oid:
        return "NO_PENDING_BUY"

    ord_q = max(1, safe_int(st.get("pending_buy_ordered_qty"), 1))
    ord_p = max(
        0.01, safe_float(st.get("pending_buy_price"), feat["live_price"])
    )
    meta = dict(st.get("pending_buy_meta") or {})
    elapsed = time.monotonic() - safe_float(
        st.get("pending_buy_mono"), time.monotonic()
    )

    det = await context.api.get_order_detail(buy_oid)
    fq = 0
    fp = ord_p
    st_ord = ""
    if isinstance(det, dict):
        st_ord = str(det.get("status") or "").upper().strip()
        ex = (
            det.get("execution")
            if isinstance(det.get("execution"), dict)
            else {}
        )
        fq = safe_int(ex.get("filledQuantity"), 0)
        avg_p = safe_float(ex.get("averageFilledPrice"), 0.0)
        if avg_p > 0.0:
            fp = avg_p

    if st_ord == "FILLED" or (
        fq > 0 and st_ord in ("CANCELED", "REJECTED", "REPLACED")
    ):
        return await _finalize_assassin_position_entry(
            context=context,
            assn_ledger=assn_ledger,
            st=st,
            feat=feat,
            fill_p=fp,
            filled_live_qty=(fq if fq > 0 else ord_q),
            live_budget_usd=safe_float(meta.get("live_budget_usd"), 0.0),
            is_live=True,
            buy_oid=buy_oid,
            meta=meta,
            now_est=now_est,
        )

    if elapsed >= LIVE_BUY_ORDER_MAX_WAIT_SEC or hm >= ASSASSIN_MACRO_CUTOFF_HM:
        try:
            await context.api.cancel_order(buy_oid)
        except Exception:
            pass
        det2 = await context.api.get_order_detail(buy_oid)
        if isinstance(det2, dict):
            ex2 = (
                det2.get("execution")
                if isinstance(det2.get("execution"), dict)
                else {}
            )
            fq = max(fq, safe_int(ex2.get("filledQuantity"), 0))
            avg_p2 = safe_float(ex2.get("averageFilledPrice"), 0.0)
            if avg_p2 > 0.0:
                fp = avg_p2
        if fq > 0:
            return await _finalize_assassin_position_entry(
                context=context,
                assn_ledger=assn_ledger,
                st=st,
                feat=feat,
                fill_p=fp,
                filled_live_qty=fq,
                live_budget_usd=safe_float(meta.get("live_budget_usd"), 0.0),
                is_live=True,
                buy_oid=buy_oid,
                meta=meta,
                now_est=now_est,
            )
        await assn_ledger.update_state(
            pending_buy_order_id="",
            pending_buy_ordered_qty=0,
            pending_buy_price=0.0,
            pending_buy_mono=0.0,
            pending_buy_meta={},
        )
        context.assassin_high_freq_active = False
        if context is not None and hasattr(context, "send_slim_alert"):
            c_gid = str(meta.get("gate_id") or "10G")
            c_why = (
                "08:15 컷오프 도래"
                if hm >= ASSASSIN_MACRO_CUTOFF_HM
                else "60초 급반등 미체결"
            )
            await context.send_slim_alert(
                title=(
                    f"⏳ [[실전] 암살자 [{c_gid}] "                    "매수 미체결 안전취소]"
                ),
                body=(
                    f"주문 {ord_q}주 @ ${ord_p:.2f} "                    f"(현재 ${feat['live_price']:.2f}) · "                    f"사유: {c_why} -> 추격매수 차단"
                ),
            )
        return "ASSASSIN_LIVE_BUY_CANCELED_SAFE"

    context.assassin_high_freq_active = True
    return "ASSASSIN_LIVE_BUY_WAITING"


async def _settle_assassin_exit_to_ledger(
    context: Any,
    assn_ledger: AssassinSimLedger,
    st: Dict[str, Any],
    exec_xp: float,
    exit_code: str,
    exit_desc: str,
    entry_qqq_p: float,
    cur_qqq_chg_pct: float,
    new_armed: bool,
    peak_p: float,
    min_p: float,
    dt_now: datetime,
    actual_sell_fee_usd: Optional[float] = None,
) -> str:
    ep = safe_float(st.get("entry_price"), exec_xp)
    rt_fee = safe_float(
        st.get("round_trip_fee_rate_pct"), ROUND_TRIP_FEE_RATE_PCT
    )
    was_live_pos = bool(st.get("is_live_position", False))

    s_qty = max(1, safe_int(st.get("simple_held_qty"), 1))
    c_qty = max(1, safe_int(st.get("comp_held_qty"), 1))
    s_inv = safe_float(st.get("simple_invested_usd"), float(s_qty) * ep)
    c_inv = safe_float(st.get("comp_invested_usd"), float(c_qty) * ep)

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

    l_net = 0.0
    if was_live_pos:
        l_qty = max(1, safe_int(st.get("live_held_qty"), 1))
        l_inv = safe_float(st.get("live_invested_usd"), float(l_qty) * ep)
        l_pnl_info = calc_sell_realized_pnl(
            sold_qty=l_qty,
            sell_exec_price=exec_xp,
            sold_actual_cost_usd=l_inv,
            round_trip_fee_rate_pct=rt_fee,
            actual_sell_fee_usd=actual_sell_fee_usd,
        )
        l_net = safe_float(l_pnl_info.get("net_pnl_usd"), 0.0)
        if context is not None:
            now_m_sh = time.monotonic()
            now_e_sh = time.time()
            for cache_attr in ("exit_snapshot_cache", "indexing_grace_cache"):
                c_map = getattr(context, cache_attr, None)
                if isinstance(c_map, dict):
                    c_ent = dict(c_map.get(TARGET_SYMBOL) or {})
                    c_ent["last_auto_fill_ts"] = now_m_sh
                    c_ent["last_sell_fill_mono"] = now_m_sh
                    c_ent["last_cycle_end_mono"] = now_m_sh
                    c_ent["last_sell_fill_ts"] = now_e_sh
                    c_ent["last_cycle_end_ts"] = now_e_sh
                    c_ent["lot_type"] = "SELL_FILL"
                    c_map[TARGET_SYMBOL] = c_ent
            if hasattr(context, "ledger"):
                try:
                    await context.ledger.update_state(
                        TARGET_SYMBOL,
                        last_sell_fill_ts=now_e_sh,
                        last_cycle_end_ts=now_e_sh,
                    )
                except Exception:
                    pass

    gain_pct = ((exec_xp - ep) / ep) * 100.0 if ep > 0.0 else 0.0
    init_s = max(
        100.0,
        safe_float(st.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD),
    )
    new_s_cum = round(safe_float(st.get("simple_cum_net_usd"), 0.0) + s_net, 4)
    new_c_cum = round(safe_float(st.get("comp_cum_net_usd"), 0.0) + c_net, 4)
    new_l_cum = round(
        safe_float(st.get("live_cum_net_usd"), 0.0) + l_net, 4
    )
    new_c_cash = round(max(100.0, init_s + new_c_cum), 4)
    new_c_peak = round(
        max(safe_float(st.get("comp_peak_equity_usd"), init_s), new_c_cash),
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

    is_win = bool((l_net if was_live_pos else s_net) >= 0.0)
    next_exec_mode = (
        ASSASSIN_MODE_SIMULATED
        if bool(st.get("demote_to_sim_after_exit", False))
        else str(st.get("execution_mode") or ASSASSIN_MODE_SIMULATED)
    )

    upd_exit: Dict[str, Any] = {
        "execution_mode": next_exec_mode,
        "demote_to_sim_after_exit": False,
        "session_phase": "OFFWORK_DONE",
        "is_session_done": True,
        "session_done_reason": exit_code,
        "has_position": False,
        "is_live_position": False,
        "live_held_qty": 0,
        "live_invested_usd": 0.0,
        "safe_cap_sell_order_id": "",
        "pending_exit_sell_order_id": "",
        "pending_exit_code": "",
        "pending_exit_desc": "",
        "pending_exit_mono": 0.0,
        "entry_qqq_price": entry_qqq_p,
        "qqq_chg_from_entry_pct": cur_qqq_chg_pct,
        "is_trailing_armed": new_armed,
        "peak_price": peak_p,
        "post_entry_min_price": min_p,
        "today_exit_reason": exit_desc,
        "today_exit_time_est": dt_now.strftime("%H:%M:%S"),
        "today_exit_price": round(exec_xp, 2),
        "today_gain_pct": round(gain_pct, 2),
        "today_simple_net_usd": round(s_net, 2),
        "today_comp_net_usd": round(c_net, 2),
        "today_live_net_usd": round(l_net, 2),
        "total_trade_days": safe_int(st.get("total_trade_days"), 0) + 1,
        "live_trade_days": safe_int(st.get("live_trade_days"), 0)
        + (1 if was_live_pos else 0),
        "win_days": safe_int(st.get("win_days"), 0) + (1 if is_win else 0),
        "loss_days": safe_int(st.get("loss_days"), 0) + (0 if is_win else 1),
        "simple_cum_net_usd": new_s_cum,
        "comp_cum_net_usd": new_c_cum,
        "live_cum_net_usd": new_l_cum,
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
        context=context, st=st, was_live_pos=was_live_pos, now_est=dt_now
    )
    return f"ASSASSIN_EXITED_{exit_code}"


async def _sync_live_pending_exit_order(
    context: Any,
    assn_ledger: AssassinSimLedger,
    st: Dict[str, Any],
    lp: float,
    qqq_lp: float,
    dt_now: datetime,
) -> str:
    sell_oid = str(st.get("pending_exit_sell_order_id") or "").strip()
    if not sell_oid:
        return "NO_PENDING_EXIT"

    det = await context.api.get_order_detail(sell_oid)
    fq = 0
    fp = lp
    st_ord = ""
    if isinstance(det, dict):
        st_ord = str(det.get("status") or "").upper().strip()
        ex = (
            det.get("execution")
            if isinstance(det.get("execution"), dict)
            else {}
        )
        fq = safe_int(ex.get("filledQuantity"), 0)
        avg_p = safe_float(ex.get("averageFilledPrice"), 0.0)
        if avg_p > 0.0:
            fp = avg_p

    eq_qqq = safe_float(st.get("entry_qqq_price"), qqq_lp)
    q_chg = (
        round(((qqq_lp - eq_qqq) / eq_qqq) * 100.0, 3)
        if (eq_qqq > 0.0 and qqq_lp > 0.0)
        else 0.0
    )

    actual_fee: Optional[float] = None
    if isinstance(det, dict) and isinstance(det.get("execution"), dict):
        ex_f = det["execution"]
        f_tot = round(
            max(0.0, safe_float(ex_f.get("commission"), 0.0))
            + max(0.0, safe_float(ex_f.get("tax"), 0.0)),
            4,
        )
        if f_tot > 0.0:
            actual_fee = f_tot

    if st_ord == "FILLED":
        return await _settle_assassin_exit_to_ledger(
            context=context,
            assn_ledger=assn_ledger,
            st=st,
            exec_xp=fp,
            exit_code=str(st.get("pending_exit_code") or "EXIT"),
            exit_desc=str(st.get("pending_exit_desc") or "실전 청산 체결"),
            entry_qqq_p=eq_qqq,
            cur_qqq_chg_pct=q_chg,
            new_armed=bool(st.get("is_trailing_armed", False)),
            peak_p=safe_float(st.get("peak_price"), fp),
            min_p=safe_float(st.get("post_entry_min_price"), fp),
            dt_now=dt_now,
            actual_sell_fee_usd=actual_fee,
        )

    if st_ord in ("CANCELED", "REJECTED", "REPLACED"):
        h_map_chk, h_ok_chk = await context.api.get_holdings_map_with_status(
            symbol=TARGET_SYMBOL
        )
        rem_broker_q = (
            safe_int((h_map_chk.get(TARGET_SYMBOL) or {}).get("qty"), 0)
            if (h_ok_chk and isinstance(h_map_chk, dict))
            else max(0, safe_int(st.get("live_held_qty"), 1) - fq)
        )
        if h_ok_chk and rem_broker_q <= 0:
            eff_p_end = fp
            if fq <= 0 and hasattr(context.api, "probe_latest_manual_fill_price"):
                probed_p, _ = await context.api.probe_latest_manual_fill_price(
                    side="SELL",
                    target_qty=max(1, safe_int(st.get("live_held_qty"), 1)),
                    fallback_price=lp,
                    symbol=TARGET_SYMBOL,
                )
                if probed_p > 0.0:
                    eff_p_end = probed_p
            return await _settle_assassin_exit_to_ledger(
                context=context,
                assn_ledger=assn_ledger,
                st=st,
                exec_xp=eff_p_end,
                exit_code=str(st.get("pending_exit_code") or "EXIT"),
                exit_desc=str(st.get("pending_exit_desc") or "실전 청산 체결"),
                entry_qqq_p=eq_qqq,
                cur_qqq_chg_pct=q_chg,
                new_armed=bool(st.get("is_trailing_armed", False)),
                peak_p=safe_float(st.get("peak_price"), eff_p_end),
                min_p=safe_float(st.get("post_entry_min_price"), eff_p_end),
                dt_now=dt_now,
                actual_sell_fee_usd=actual_fee,
            )
        old_lq = max(1, safe_int(st.get("live_held_qty"), 1))
        new_lq = max(1, rem_broker_q if h_ok_chk else max(1, old_lq - fq))
        ep_cur = safe_float(st.get("entry_price"), lp)
        await assn_ledger.update_state(
            live_held_qty=new_lq,
            live_invested_usd=round(float(new_lq) * ep_cur, 4),
            safe_cap_sell_order_id="",
            pending_exit_sell_order_id="",
            pending_exit_code="",
            pending_exit_desc="",
            pending_exit_mono=0.0,
        )
        context.assassin_high_freq_active = True
        return "ASSASSIN_LIVE_EXIT_RE_SWEEP_ARMED"

    elapsed = time.monotonic() - safe_float(
        st.get("pending_exit_mono"), time.monotonic()
    )
    hm_chk = dt_now.hour * 100 + dt_now.minute
    wait_thr = 3.0 if hm_chk >= ASSASSIN_MOC_EXIT_HM else 5.0
    if elapsed >= wait_thr and lp > 0.0:
        if hm_chk >= ASSASSIN_MOC_EXIT_HM:
            bid_p = await context.api.get_best_bid_price(
                TARGET_SYMBOL, fallback_price=lp
            )
            ref_m_p = min(lp, bid_p) if bid_p > 0.0 else lp
            chase_p = round(max(0.01, ref_m_p * 0.985), 2)
        else:
            chase_p = round(max(0.01, lp * 0.996), 2)
        try:
            mod_r = await context.api.modify_order(
                order_id=sell_oid, new_price=chase_p
            )
            new_oid = str((mod_r or {}).get("orderId") or sell_oid).strip()
            await assn_ledger.update_state(
                pending_exit_sell_order_id=new_oid,
                pending_exit_mono=time.monotonic(),
            )
        except Exception:
            pass
    context.assassin_high_freq_active = True
    return "ASSASSIN_LIVE_EXIT_WAITING"
# -*- coding: utf-8 -*-
"""
# MODIFIED: assassin_plugin.py (Part 4/4 — Case 97-B T03_A 미충족 선잠금 버그 제거[격발 시에만 분당 잠금] ·
# 골든타임 무소음 백그라운드 정찰 · 본대 1일 1회 퇴근 + 04:07 ~ 08:14 EST 다회차 10G 정찰 카운터[08:15 정규장 폐기] 통합 상태 머신 ·
# /avwap 슬림 블록 & /assassin 순수 10G 상세 관제 보드 · Case 93 ~ Case 97 부팅 TDD 검증기)
"""


async def _dispatch_new_scout_unit_and_check_gates(
    context: Any,
    assn_ledger: AssassinSimLedger,
    st: Dict[str, Any],
    feat: Dict[str, Any],
    entry_type: str,
    now_est: datetime,
    cur_bucket_10m: int,
    allow_main_force_entry: bool = True,
    silent_scout_alert: bool = False,
) -> str:
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

    prev_pre_high = max(
        safe_float(st.get("today_pre_high_price"), 0.0),
        safe_float(feat.get("pre_high_price"), 0.0),
        safe_float(st.get("scout_anchor_price"), 0.0),
        sc1_p,
    )
    new_pre_high = round(max(prev_pre_high, lp), 4)

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
        entry_type=entry_type,
    )

    if gate_hit:
        _LAST_T03A_DIP_SCAN_KEY = now_est.strftime("%Y-%m-%d %H:%M")
        _LAST_T03A_DIP_SCAN_TS = now_ts

    upd_kw: Dict[str, Any] = {
        "scout_units": [u.to_dict() for u in units],
        "day_scout_history": history_list[-30:],
        "day_scout_seq": new_seq,
        "scout1_open_price": round(sc1_p, 4),
        "today_pre_open_price": round(eff_pre_open, 4),
        "today_pre_open_verified": True,
        "today_premarket_vwap": round(eff_pre_vwap, 4),
        "today_pre_vwap_verified": True,
        "today_pre_high_price": new_pre_high,
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
    if allow_main_force_entry:
        upd_kw["session_phase"] = "SCOUTING_0407_0814"
    if cur_bucket_10m >= 0:
        upd_kw["last_scout_bucket_10m"] = cur_bucket_10m

    st = await assn_ledger.update_state(**upd_kw)
    await asyncio.to_thread(_assn_pub_shm_scout_sync, st)
    if gate_hit:
        mkey_g = now_est.strftime('%Y-%m-%d %H:%M')
        _CONSUMED_SHM_GATE_KEYS[assn_ledger.folder_slug] = (
            f"{mkey_g}:{gate_id}"
        )
        await asyncio.to_thread(
            _assn_pub_shm_gate_sync,
            now_est.strftime('%Y-%m-%d'),
            mkey_g,
            gate_id,
            gate_desc,
            f"SCOUT_#{new_seq}_{entry_type}",
            new_seq,
            feat,
        )
    if not silent_scout_alert:
        await _send_1_scout_dispatched_alert(
            context=context,
            st=st,
            scout=new_scout,
            total_active_scouts=len(units),
            prior_wins=prior_wins,
            gate_eval_note=(
                f"🔥 [{gate_id}] 격발!" if gate_hit else gate_desc
            ),
        )

    if not gate_hit:
        return f"SCOUT_DISPATCHED_#{new_seq}"

    trig_label = f"SCOUT_#{new_seq}_{entry_type}"
    # [Case 96 & Case 97]: 골든타임(04:07 ~ 08:14 EST) 다회차 [모의] 10G 정찰병 출동 카운트 기록
    st, gt_dispatched = await _try_dispatch_gt_multi_gate_scout(
        assn_ledger=assn_ledger,
        st=st,
        feat=feat,
        gate_id=gate_id,
        trigger_mode=trig_label,
        entry_scout_seq=new_seq,
        now_est=now_est,
        now_ts=now_ts,
    )

    if not allow_main_force_entry:
        return (
            f"GT_MULTI_SCOUT_DISPATCHED_{gate_id}"
            if gt_dispatched
            else f"BG_SCOUT_DISPATCHED_#{new_seq}"
        )

    return await _enter_assassin_main_force_from_gate(
        context=context,
        assn_ledger=assn_ledger,
        st=st,
        feat=feat,
        gate_id=gate_id,
        gate_desc=gate_desc,
        entry_scout_seq=new_seq,
        entry_trigger_mode=trig_label,
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
    allow_main_force_entry: bool = True,
) -> Optional[str]:
    """
    [Case 93 & Case 97-B 핵심 패치]:
    - 선봉 정찰병(#1) 파견 후 60초 타임쉴드 경과 뒤 정찰 기준 저점 대비 -1.00% 이하 눌림 구간에서
      순수 10대 진성 급락 게이트(G1~G5 · BG1~BG5)를 상시 검문한다.
    - 게이트 미충족(gate_hit == False) 틱에서는 절대 분당 60초 잠금을 걸지 않고,
      실제 게이트 격발(gate_hit == True)로 집행이 이루어진 순간에만 잠금을 기록하여
      동일 분봉 내 음봉 ➔ 양봉 전환 타점(예: 04:11:00 음봉 ➔ 04:11:01 양봉 G4)을 전 봇이 100% 포착하도록 보장한다!
    """
    global _LAST_T03A_DIP_SCAN_KEY, _LAST_T03A_DIP_SCAN_TS

    cur_seq = safe_int(st.get("day_scout_seq"), 0)
    if cur_seq < 1:
        return None
    # MODIFIED: 본대 T03_A 감시 60초 타임쉴드 제거 -> 매 1.5초 상시 스캔

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
        and (now_ts - _LAST_T03A_DIP_SCAN_TS)
        < SCOUT_T03A_DIP_SCAN_INTERVAL_SEC
    ):
        return None

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
        entry_type="T03A_DIP_SCAN",
    )
    if not gate_hit:
        return None

    new_min_p = round(min(ref_dip_low, lp), 4)
    trig_mode_str = (
        f"T03A_1M_DIP_SCAN(저점${ref_dip_low:.2f}대비{chg_from_dip_low:+.2f}%)"
    )
    _CONSUMED_SHM_GATE_KEYS[assn_ledger.folder_slug] = (
        f"{cur_min_key}:{gate_id}"
    )
    await asyncio.to_thread(
        _assn_pub_shm_gate_sync,
        now_est.strftime('%Y-%m-%d'),
        cur_min_key,
        gate_id,
        gate_desc,
        trig_mode_str,
        cur_seq,
        feat,
    )

    # [Case 96]: T03_A 눌림 스캔에서도 다회차 [모의] 10G 정찰병 출동 카운트 반영
    st, gt_dispatched = await _try_dispatch_gt_multi_gate_scout(
        assn_ledger=assn_ledger,
        st=st,
        feat=feat,
        gate_id=gate_id,
        trigger_mode=trig_mode_str,
        entry_scout_seq=cur_seq,
        now_est=now_est,
        now_ts=now_ts,
    )

    if allow_main_force_entry or gt_dispatched:
        _LAST_T03A_DIP_SCAN_KEY = cur_min_key
        _LAST_T03A_DIP_SCAN_TS = now_ts

    if not allow_main_force_entry:
        if new_min_p < safe_float(
            st.get("scout_cycle_min_buy_price"), ref_dip_low
        ):
            await assn_ledger.update_state(scout_cycle_min_buy_price=new_min_p)
        return f"GT_T03A_SCOUT_DISPATCHED_{gate_id}" if gt_dispatched else None

    return await _enter_assassin_main_force_from_gate(
        context=context,
        assn_ledger=assn_ledger,
        st=st,
        feat=feat,
        gate_id=gate_id,
        gate_desc=gate_desc,
        entry_scout_seq=cur_seq,
        entry_trigger_mode=trig_mode_str,
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


async def _run_golden_time_scouting_and_gates_step(
    context: Any,
    assn_ledger: AssassinSimLedger,
    st: Dict[str, Any],
    feat: Dict[str, Any],
    dt_now: datetime,
    now_ts: float,
    allow_main_force_entry: bool = True,
    silent_scout_alert: bool = False,
) -> str:
    """
    04:07 ~ 08:14 EST 골든타임 1주 가상 독립 정찰병 파견 · 독립 익절 · T03_A 1분 눌림 상시 스캔 실행기:
    - 본대 진입 전(allow_main_force_entry=True): 정상 알림 발송 및 최초 10대 게이트 포착 시 본대 1회 진입 집행
    - 본대 보유 중 또는 본대 조기 퇴근 후(allow_main_force_entry=False, silent_scout_alert=True):
      본대 주문/알림 간섭 없이 무소음으로 정찰 흐름을 유지하며 다회차 10G 정찰병 출동 카운트만 수행
    """
    today_str = dt_now.strftime("%Y-%m-%d")
    st = await _sync_scout_from_shm_if_behind(
        assn_ledger, st, today_str, dt_now, now_ts
    )
    shm_res = await _consume_shm_gate_if_fresh(
        context,
        assn_ledger,
        st,
        feat,
        today_str,
        dt_now,
        now_ts,
        allow_main_force_entry,
    )
    if shm_res is not None:
        return shm_res
    lp = safe_float(feat.get("live_price"), 0.0)
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
            cur_pre_h = max(
                safe_float(st.get("today_pre_high_price"), 0.0),
                lp,
            )
            st = await assn_ledger.update_state(
                scout_units=[u.to_dict() for u in kept_units],
                scout_has_active_l1=new_has_l1,
                scout_anchor_price=round(lp, 4),
                today_pre_high_price=round(cur_pre_h, 4),
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
            await asyncio.to_thread(_assn_pub_shm_scout_sync, st)
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
    hold_status = "SCOUTING_ACTIVE"

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
                allow_main_force_entry=allow_main_force_entry,
                silent_scout_alert=silent_scout_alert,
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
                allow_main_force_entry=allow_main_force_entry,
                silent_scout_alert=silent_scout_alert,
            )
        hold_status = "HOLD_SCOUT_60S_SHIELD"
    elif in_60s_shield:
        hold_status = "HOLD_SCOUT_60S_SHIELD"
    elif len(units) >= SCOUT_MAX_INDEPENDENT_UNITS:
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
                            allow_main_force_entry=allow_main_force_entry,
                            silent_scout_alert=silent_scout_alert,
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
                                    allow_main_force_entry=allow_main_force_entry,
                                    silent_scout_alert=silent_scout_alert,
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
                    allow_main_force_entry=allow_main_force_entry,
                    silent_scout_alert=silent_scout_alert,
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
        allow_main_force_entry=allow_main_force_entry,
    )
    if t03a_res is not None:
        return t03a_res

    return hold_status


async def execute_simulated_assassin_tick_plugin(
    context: Any,
    now_est: Optional[datetime] = None,
) -> str:
    """
    main.py 의 main_sniper_loop() 최상단에서 매 틱 호출되는 [모의 ⇄ 실전] 암살자 통합 상태 머신:
    - 본대(Main Force): 순수 10대 급락 게이트(G1~5·BG1~5) 기반 1일 1회 출근·퇴근 원칙 100% 유지
    - 골든타임 다회차 10G 정찰병(Case 96 & Case 97): 04:07 ~ 08:14 EST 구간 동안 본대 조기 퇴근/보유 여부와 무관하게
      10대 진성 게이트 조건마다 무소음 출동하여 +1.00% 익절 퇴근 횟수를 카운트하며, 08:15 EST 도래 시 즉시 종료(정규장 폐기)한다.
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
            if (
                str(
                    ensure_assassin_ledger(context)
                    .get_state()
                    .get("execution_mode")
                    or ""
                )
                == ASSASSIN_MODE_ARMED_ON_ZERO
                and not st_sp.get("buckets")
                and not st_sp.get("sub_buckets")
                and not str(st_sp.get("buy_order_id") or "").strip()
                and not str(st_sp.get("sell_order_id") or "").strip()
            ):
                await activate_live_assassin_on_zero_soxl_if_armed(context)
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

    # 본대(1일 1회) 퇴근 완료 & 골든타임 다회차 정찰 마감(08:15 이후) 상태면 API/캔들 조회 없이 즉시 반환!
    if bool(st.get("is_session_done", False)) and bool(
        st.get("gt_gate_scout_done", False)
    ):
        if context is not None:
            context.assassin_high_freq_active = False
        return str(st.get("session_done_reason") or "SESSION_DONE")

    feat = await _extract_live_assassin_features_and_qqq_snapshot(
        context=context, now_est=dt_now
    )
    lp = safe_float(feat.get("live_price"), 0.0)
    if lp <= 0.0:
        return "NO_LIVE_PRICE"

    # 실전(LIVE) 미체결 매수 / 출구 주문 진행 중 최우선 동기화
    if str(st.get("pending_buy_order_id") or "").strip():
        return await _sync_live_pending_buy_order(
            context=context,
            assn_ledger=assn_ledger,
            st=st,
            feat=feat,
            hm=hm,
            now_est=dt_now,
        )
    if str(st.get("pending_exit_sell_order_id") or "").strip():
        return await _sync_live_pending_exit_order(
            context=context,
            assn_ledger=assn_ledger,
            st=st,
            lp=lp,
            qqq_lp=safe_float(feat.get("qqq_live_price"), 0.0),
            dt_now=dt_now,
        )

    now_ts = time.time()

    # [Case 96]: 매 틱 골든타임(04:07 ~ 08:14 EST) 다회차 10G 정찰병 익절 퇴근 및 08:15 마감 잠금 판정
    st = await _update_gt_multi_gate_scout_on_tick(
        assn_ledger=assn_ledger,
        st=st,
        feat=feat,
        hm=hm,
        now_est=dt_now,
        now_ts=now_ts,
    )

    # 본대가 이미 당일 1회 매매를 마치고 조기 퇴근(is_session_done == True)한 경우:
    # 08:14 EST 까지는 무소음으로 골든타임 다회차 10G 정찰 카운트만 수행하고, 08:15 EST 이후에는 완전 종료!
    if bool(st.get("is_session_done", False)):
        if context is not None:
            context.assassin_high_freq_active = False
        if hm < ASSASSIN_MACRO_CUTOFF_HM and not bool(
            st.get("gt_gate_scout_done", False)
        ):
            try:
                await _run_golden_time_scouting_and_gates_step(
                    context=context,
                    assn_ledger=assn_ledger,
                    st=st,
                    feat=feat,
                    dt_now=dt_now,
                    now_ts=now_ts,
                    allow_main_force_entry=False,
                    silent_scout_alert=True,
                )
            except Exception as bg_exc:
                logger.debug("골든타임 다회차 백그라운드 정찰 스킵: %s", bg_exc)
        return str(st.get("session_done_reason") or "SESSION_DONE")

    # [PHASE A] 본대(Main Force) 포지션 보유 중 -> 상단 안전캡 체결 확인 및 출구 감시
    if bool(st.get("has_position", False)):
        is_live_pos = bool(st.get("is_live_position", False))
        qqq_lp = safe_float(feat.get("qqq_live_price"), 0.0)
        entry_qqq_p = safe_float(st.get("entry_qqq_price"), 0.0)
        if entry_qqq_p <= 0.0 and qqq_lp > 0.0:
            entry_qqq_p = round(qqq_lp, 4)

        cur_qqq_chg_pct = (
            round(((qqq_lp - entry_qqq_p) / entry_qqq_p) * 100.0, 3)
            if (entry_qqq_p > 0.0 and qqq_lp > 0.0)
            else 0.0
        )

        # 실전 포지션 보유 중 선장전된 +5% 안전캡 주문이 이미 거래소에서 체결되었는지 선행 확인
        cap_oid_now = str(st.get("safe_cap_sell_order_id") or "").strip()
        if is_live_pos and cap_oid_now and hasattr(context, "api"):
            try:
                det_c = await context.api.get_order_detail(cap_oid_now)
                if (
                    isinstance(det_c, dict)
                    and str(det_c.get("status") or "").upper().strip()
                    == "FILLED"
                ):
                    ex_c = (
                        det_c.get("execution")
                        if isinstance(det_c.get("execution"), dict)
                        else {}
                    )
                    fp_c = safe_float(
                        ex_c.get("averageFilledPrice"),
                        safe_float(st.get("cap_500_price"), lp),
                    )
                    return await _settle_assassin_exit_to_ledger(
                        context=context,
                        assn_ledger=assn_ledger,
                        st=st,
                        exec_xp=fp_c,
                        exit_code="CAP_500_HOMERUN",
                        exit_desc=f"👑 +5.00% 상단 안전 캡 실전 체결(${fp_c:.2f})",
                        entry_qqq_p=entry_qqq_p,
                        cur_qqq_chg_pct=cur_qqq_chg_pct,
                        new_armed=True,
                        peak_p=max(
                            safe_float(st.get("peak_price"), fp_c), fp_c
                        ),
                        min_p=safe_float(st.get("post_entry_min_price"), lp),
                        dt_now=dt_now,
                    )
            except Exception:
                pass

        if (
            is_live_pos
            and hasattr(context, "api")
            and (now_ts - safe_float(st.get("entry_ts"), 0.0)) >= 15.0
            and (
                now_ts
                - safe_float(getattr(context, "_last_assn_h_chk_ts", 0.0), 0.0)
            )
            >= 6.0
        ):
            setattr(context, "_last_assn_h_chk_ts", now_ts)
            try:
                h_m_live, h_ok_live = (
                    await context.api.get_holdings_map_with_status(
                        symbol=TARGET_SYMBOL
                    )
                )
                if (
                    h_ok_live
                    and isinstance(h_m_live, dict)
                    and safe_int(
                        (h_m_live.get(TARGET_SYMBOL) or {}).get("qty"), 0
                    )
                    <= 0
                ):
                    if cap_oid_now:
                        try:
                            await context.api.cancel_order(cap_oid_now)
                        except Exception:
                            pass
                    man_p = lp
                    man_fee: Optional[float] = None
                    if hasattr(context.api, "probe_latest_manual_fill_price"):
                        man_p, _ = (
                            await context.api.probe_latest_manual_fill_price(
                                side="SELL",
                                target_qty=max(
                                    1, safe_int(st.get("live_held_qty"), 1)
                                ),
                                fallback_price=lp,
                                symbol=TARGET_SYMBOL,
                            )
                        )
                        f_probe = safe_float(
                            getattr(
                                context.api, "last_probed_manual_fee_usd", 0.0
                            ),
                            0.0,
                        )
                        if f_probe > 0.0:
                            man_fee = f_probe
                    return await _settle_assassin_exit_to_ledger(
                        context=context,
                        assn_ledger=assn_ledger,
                        st=st,
                        exec_xp=(man_p if man_p > 0.0 else lp),
                        exit_code="MANUAL_EXIT_SYNC",
                        exit_desc=f"🧹 실전 보유분 수동 전량청산 동기화(${man_p if man_p > 0.0 else lp:.2f})",
                        entry_qqq_p=entry_qqq_p,
                        cur_qqq_chg_pct=cur_qqq_chg_pct,
                        new_armed=bool(st.get("is_trailing_armed", False)),
                        peak_p=max(safe_float(st.get("peak_price"), lp), lp),
                        min_p=safe_float(st.get("post_entry_min_price"), lp),
                        dt_now=dt_now,
                        actual_sell_fee_usd=man_fee,
                    )
            except Exception:
                pass

        entry_hm_prefix = str(st.get("entry_time_est") or "")[:5]
        same_entry_min = bool(
            entry_hm_prefix and dt_now.strftime("%H:%M") == entry_hm_prefix
        )
        eff_bar_high = (
            lp
            if same_entry_min
            else max(lp, safe_float(feat.get("cur_bar_high"), lp))
        )

        exit_eval = evaluate_assassin_ha_trailing_and_exits(
            hm=hm,
            entry_price=safe_float(st.get("entry_price"), lp),
            live_price=lp,
            bar_high_price=eff_bar_high,
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
            entry_gate_id=str(st.get("entry_gate_id") or ""),
        )

        new_armed = bool(exit_eval.get("is_trailing_armed", False))
        if context is not None:
            context.assassin_high_freq_active = new_armed

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
            if hm < ASSASSIN_MACRO_CUTOFF_HM and not bool(
                st.get("gt_gate_scout_done", False)
            ):
                try:
                    await _run_golden_time_scouting_and_gates_step(
                        context=context,
                        assn_ledger=assn_ledger,
                        st=st,
                        feat=feat,
                        dt_now=dt_now,
                        now_ts=now_ts,
                        allow_main_force_entry=False,
                        silent_scout_alert=True,
                    )
                except Exception:
                    pass
            return "ASSASSIN_TRAILING_ARMED"

        if not bool(exit_eval.get("should_exit", False)):
            st = await assn_ledger.update_state(
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
            if hm < ASSASSIN_MACRO_CUTOFF_HM and not bool(
                st.get("gt_gate_scout_done", False)
            ):
                try:
                    await _run_golden_time_scouting_and_gates_step(
                        context=context,
                        assn_ledger=assn_ledger,
                        st=st,
                        feat=feat,
                        dt_now=dt_now,
                        now_ts=now_ts,
                        allow_main_force_entry=False,
                        silent_scout_alert=True,
                    )
                except Exception:
                    pass
            return str(exit_eval.get("exit_code") or "HOLD_POSITION")

        exit_code = str(exit_eval.get("exit_code") or "EXIT")
        exit_desc = str(exit_eval.get("exit_desc") or exit_code)
        target_xp = safe_float(exit_eval.get("exit_price"), lp)
        eff_sell_q = (
            safe_int(st.get("live_held_qty"), 1)
            if is_live_pos
            else safe_int(st.get("comp_held_qty"), 1)
        )

        ok_ex, exec_xp, active_sell_oid, imm_ex_filled = (
            await _dispatch_assassin_exit_sweep_order(
                context=context,
                qty=eff_sell_q,
                target_exit_price=target_xp,
                existing_cap_order_id=cap_oid_now,
                is_moc_1559=("MOC" in exit_code),
                is_live=is_live_pos,
            )
        )

        if is_live_pos:
            if not ok_ex:
                if hasattr(context, "api"):
                    try:
                        open_chk = await context.api.get_open_orders(
                            symbol=TARGET_SYMBOL
                        )
                        h_chk, h_ok2 = (
                            await context.api.get_holdings_map_with_status(
                                symbol=TARGET_SYMBOL
                            )
                        )
                        if (
                            not open_chk
                            and h_ok2
                            and safe_int(
                                (h_chk.get(TARGET_SYMBOL) or {}).get("qty"), 0
                            )
                            <= 0
                        ):
                            p_man, _ = (
                                await context.api.probe_latest_manual_fill_price(
                                    side="SELL",
                                    target_qty=eff_sell_q,
                                    fallback_price=lp,
                                    symbol=TARGET_SYMBOL,
                                )
                            )
                            return await _settle_assassin_exit_to_ledger(
                                context=context,
                                assn_ledger=assn_ledger,
                                st=st,
                                exec_xp=(p_man if p_man > 0.0 else lp),
                                exit_code=exit_code,
                                exit_desc=exit_desc,
                                entry_qqq_p=entry_qqq_p,
                                cur_qqq_chg_pct=cur_qqq_chg_pct,
                                new_armed=new_armed,
                                peak_p=safe_float(
                                    exit_eval.get("peak_price"), lp
                                ),
                                min_p=safe_float(
                                    exit_eval.get("post_entry_min_price"), lp
                                ),
                                dt_now=dt_now,
                            )
                    except Exception:
                        pass
                await assn_ledger.update_state(
                    safe_cap_sell_order_id=active_sell_oid,
                    is_trailing_armed=new_armed,
                    peak_price=safe_float(exit_eval.get("peak_price"), lp),
                    post_entry_min_price=safe_float(
                        exit_eval.get("post_entry_min_price"), lp
                    ),
                )
                if context is not None:
                    context.assassin_high_freq_active = True
                logger.warning(
                    "⚠️ [Case 95 실전 암살자 청산 스윕 일시 실패 -> 퇴근 보류 및 0.4s 즉시 재시도] code=%s",
                    exit_code,
                )
                return f"ASSASSIN_LIVE_EXIT_RETRY_{exit_code}"

            if not imm_ex_filled and active_sell_oid:
                await assn_ledger.update_state(
                    pending_exit_sell_order_id=active_sell_oid,
                    pending_exit_code=exit_code,
                    pending_exit_desc=exit_desc,
                    pending_exit_mono=time.monotonic(),
                    is_trailing_armed=new_armed,
                    peak_price=safe_float(exit_eval.get("peak_price"), lp),
                    post_entry_min_price=safe_float(
                        exit_eval.get("post_entry_min_price"), lp
                    ),
                )
                if context is not None:
                    context.assassin_high_freq_active = True
                return f"ASSASSIN_LIVE_EXIT_PENDING_{exit_code}"

        return await _settle_assassin_exit_to_ledger(
            context=context,
            assn_ledger=assn_ledger,
            st=st,
            exec_xp=exec_xp,
            exit_code=exit_code,
            exit_desc=exit_desc,
            entry_qqq_p=entry_qqq_p,
            cur_qqq_chg_pct=cur_qqq_chg_pct,
            new_armed=new_armed,
            peak_p=safe_float(exit_eval.get("peak_price"), exec_xp),
            min_p=safe_float(exit_eval.get("post_entry_min_price"), exec_xp),
            dt_now=dt_now,
        )

    # [PHASE B] 08:15 EST 도래 시 본대 미진입이면 즉시 무매매 안전 퇴근 (다회차 정찰도 동시 잠금)
    if hm >= ASSASSIN_MACRO_CUTOFF_HM:
        if context is not None:
            context.assassin_high_freq_active = False
        had_scouts_today = bool(safe_int(st.get("day_scout_seq"), 0) > 0)
        already_sent = bool(st.get("alert_0815_no_trade_sent", False))
        st = await assn_ledger.update_state(
            session_phase="NO_TRADE_OFFWORK_0815",
            is_session_done=True,
            session_done_reason="NO_TRADE_CUTOFF_0815",
            gt_gate_scout_done=True,
            gt_active_gate_scout=None,
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

    # [PHASE C] 04:07 ~ 08:14 EST 골든타임 본대 진입 전 정상 정찰 및 10대 진성 급락 게이트 스캔
    return await _run_golden_time_scouting_and_gates_step(
        context=context,
        assn_ledger=assn_ledger,
        st=st,
        feat=feat,
        dt_now=dt_now,
        now_ts=now_ts,
        allow_main_force_entry=True,
        silent_scout_alert=False,
    )


execute_assassin_tick_plugin = execute_simulated_assassin_tick_plugin


# ---------------------------------------------------------------------------
# [핵심 9] 스나이퍼 레이더 결합용 슬림 블록 & /assassin 상세 관제 보드 (순수 10G + 다회차 카운트 표출)
# ---------------------------------------------------------------------------
def format_assassin_slim_radar_block(
    context: Any, live_price: float = 0.0
) -> str:
    try:
        assn_ledger = ensure_assassin_ledger(context)
        st = assn_ledger.get_state()
        lp = safe_float(
            live_price,
            safe_float(
                getattr(context, "latest_prices", {}).get(TARGET_SYMBOL), 0.0
            ),
        )
        exec_m = str(
            st.get("execution_mode") or ASSASSIN_MODE_SIMULATED
        ).upper()
        if exec_m == ASSASSIN_MODE_LIVE:
            m_lbl = "[실전] 암살자"
        elif exec_m == ASSASSIN_MODE_ARMED_ON_ZERO:
            m_lbl = "[0주전환예약] 암살자"
        else:
            m_lbl = "[모의] 암살자"

        phase = str(st.get("session_phase") or "IDLE_WAIT_0407")
        has_pos = bool(st.get("has_position", False))
        scouts_cnt = len(st.get("scout_units") or [])
        day_seq = safe_int(st.get("day_scout_seq"), 0)
        tot_d = safe_int(st.get("total_trade_days"), 0)
        win_d = safe_int(st.get("win_days"), 0)
        loss_d = safe_int(st.get("loss_days"), 0)
        s_cum = safe_float(st.get("simple_cum_net_usd"), 0.0)
        c_cum = safe_float(st.get("comp_cum_net_usd"), 0.0)

        td_gt_disp = safe_int(st.get("today_gt_gate_dispatches"), 0)
        td_gt_wins = safe_int(st.get("today_gt_gate_win_exits"), 0)
        cum_gt_disp = safe_int(st.get("cum_gt_gate_dispatches"), 0)
        cum_gt_wins = safe_int(st.get("cum_gt_gate_win_exits"), 0)
        gt_act_badge = (
            "·출동중"
            if isinstance(st.get("gt_active_gate_scout"), dict)
            else ""
        )

        if has_pos:
            ep = safe_float(st.get("entry_price"), lp)
            cur_g = (
                ((lp - ep) / ep) * 100.0 if (lp > 0.0 and ep > 0.0) else 0.0
            )
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
                f"🕵️정찰중(현 {scouts_cnt}명·누적 {day_seq}명·10G×T03_A)"
            )
        else:
            status_line = "⏳04:07 정찰대기 (10G×T03_A 상시ON)"

        return "\n".join(
            [
                "──────────────",
                f"🗡️ <b>[{m_lbl}]</b> {status_line}",
                f"▫️ 전적: <b>{tot_d}전 {win_d}승 {loss_d}패</b> · 단리 <b>{s_cum:+,.0f}$</b> / 복리 <b>{c_cum:+,.0f}$</b> (<code>/assassin</code>)",
                f"🕵️ GT다회차(10G): 금일익절 <b>{td_gt_wins}/{td_gt_disp}회</b>{gt_act_badge} · 누적 <b>{cum_gt_wins}/{cum_gt_disp}회</b>",
            ]
        )
    except Exception:
        return ""


async def build_assassin_detail_dashboard_html(
    context: Any, live_price: float = 0.0
) -> str:
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

    exec_m = str(st.get("execution_mode") or ASSASSIN_MODE_SIMULATED).upper()
    if exec_m == ASSASSIN_MODE_LIVE:
        bp_now = (
            await context.api.get_buying_power_usd(safety_buffer_pct=0.2)
            if (context is not None and hasattr(context, "api"))
            else init_s
        )
        eff_live_bud = min(init_s, bp_now)
        mode_desc_line = (
            f"🔥 <b>[실전 단독 작동 (LIVE · 1일 1회)]</b> 당일예산 min(시드,예수금)=<b>${eff_live_bud:,.2f}</b> (SGOV 수동매도 위임)"
        )
    elif exec_m == ASSASSIN_MODE_ARMED_ON_ZERO:
        mode_desc_line = (
            "⏳ <b>[SOXL 0주 졸업 시 실전 자동전환 예약 (ARMED_ON_ZERO)]</b> (현재는 모의 관제)"
        )
    else:
        mode_desc_line = (
            "🧪 <b>[모의 상시 작동 (SIMULATED · 본대 1일 1회 원칙)]</b> (스나이퍼/바벨 분리 독립 가동)"
        )

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
        f"🔍 10G×T03_A스캔: 정찰저점 <b>${ref_dip_low:.2f}</b> ➔ <b>${t03a_trig_p:.2f}</b>(-1.0%) 이하 상시검문(UG 영구폐기)"
        if ref_dip_low > 0.0
        else "🔍 10G×T03_A스캔: 순수 10대 급락(G1~5·BG1~5) · 선봉(#1) 후 저점 -1.0% 상시검문"
    )

    lines: List[str] = [
        "🗡️ <b>[인피니트 스노우볼 · 암살자(Assassin) 관제 보드]</b>",
        f"⚙️ 운용상태: {mode_desc_line}",
        f"💵 설정시드: <b>${init_s:,.2f}</b> | 모의복리자산: <b>${comp_eq:,.2f}</b> (전환: <code>/assassin_mode</code>)",
        "━━━━━━━━━━━━━━━━━━",
        "📊 <b>[실시간 SOXL · QQQ 4대 지표 스냅샷]</b>",
        f"• 현재가: <b>${lp:.2f}</b> ({bar_str} / HA {ha_str}) · QQQ: <b>${qqq_lp:.2f}</b>",
        vwap_line,
        f"③ 전일종가: <b>${feat['prev_reg_close']:.2f}</b> ({feat['vs_prev_close_pct']:+.2f}%) | ④ 프리시가: <b>${feat['pre_open_price']:.2f}</b> ({feat['vs_pre_open_pct']:+.2f}%)",
        t03a_scan_line,
        f"🛡️ 단일안전망: QQQ 1분 <b>{feat['qqq_vel_1m_pct']:+.2f}%</b> · 08:15~ 출동 고정QQQ 대비 <b>SN4×SN3(-1.0%)</b> 방어",
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
        gid_str = str(st.get("entry_gate_id") or "")
        sn_badge = f"08:15~ SN4×SN3 -{dyn_thr:.2f}%"
        qty_str = (
            f"실전 <b>{safe_int(st.get('live_held_qty'), 0)}주</b>(${safe_float(st.get('live_invested_usd'), 0.0):,.0f})"
            if bool(st.get("is_live_position", False))
            else f"단리 <b>{safe_int(st.get('simple_held_qty'), 0)}주</b> / 복리 <b>{safe_int(st.get('comp_held_qty'), 0)}주</b>"
        )
        lines.extend(
            [
                f"🔥 <b>[금일 본대 포지션 가동 중 (1일 1회) · 게이트 {_esc(gid_str)}]</b>",
                f"• 진입단가: <b>${ep:.2f}</b> ({_esc(st.get('entry_time_est'))} EST · {_esc(trig_m)}) ➔ 현재 <b>{cur_g:+.2f}%</b>",
                f"• 고정QQQ: <b>${eq_qqq:.2f}</b> ➔ 현재 <b>${qqq_lp:.2f}</b> (<b>{qqq_chg:+.2f}%</b> / {sn_badge})",
                f"• 보유수량: {qty_str}",
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
                    "🏠 <b>[금일 본대 상태 : 08:15 EST 무매매 안전 퇴근 완료]</b>",
                    "• 04:07 ~ 08:14 EST 구간 10대 진성 급락 게이트 미충족 (익일 04:07 EST 재출격)",
                    "━━━━━━━━━━━━━━━━━━",
                ]
            )
        else:
            lines.extend(
                [
                    f"🎯 <b>[금일 본대 상태 : 1일 1회 매매 퇴근 ({_esc(st.get('today_exit_time_est'))} EST)]</b>",
                    f"• 청산사유: {_esc(reason_str)}",
                    f"• 금일성과: 수익률 <b>{safe_float(st.get('today_gain_pct'), 0.0):+.2f}%</b> (단리 <b>{safe_float(st.get('today_simple_net_usd'), 0.0):+,.2f}$</b> / 실전 <b>{safe_float(st.get('today_live_net_usd'), 0.0):+,.2f}$</b>)",
                    "━━━━━━━━━━━━━━━━━━",
                ]
            )

    # [Case 96 & Case 97]: 골든타임(04:07 ~ 08:14 EST) 다회차 순수 10대 게이트 [모의] 정찰병 카운터 보드
    td_gt_disp = safe_int(st.get("today_gt_gate_dispatches"), 0)
    td_gt_wins = safe_int(st.get("today_gt_gate_win_exits"), 0)
    td_gt_stops = safe_int(st.get("today_gt_gate_stop_exits"), 0)
    td_gt_cuts = safe_int(st.get("today_gt_gate_cutoff_exits"), 0)
    cum_gt_disp = safe_int(st.get("cum_gt_gate_dispatches"), 0)
    cum_gt_wins = safe_int(st.get("cum_gt_gate_win_exits"), 0)
    cum_gt_multi_d = safe_int(st.get("cum_gt_multi_win_days"), 0)
    max_gt_wins = safe_int(st.get("max_daily_gt_gate_wins"), 0)
    cum_gt_wr = (
        (float(cum_gt_wins) / float(cum_gt_disp)) * 100.0
        if cum_gt_disp > 0
        else 100.0
    )

    active_gs = st.get("gt_active_gate_scout")
    if isinstance(active_gs, dict):
        gs_r = safe_int(active_gs.get("round_no"), 1)
        gs_gid = str(active_gs.get("gate_id") or "G1")
        gs_ep = safe_float(active_gs.get("entry_price"), lp)
        gs_tp = safe_float(active_gs.get("target_price"), gs_ep)
        gs_g = ((lp - gs_ep) / gs_ep) * 100.0 if gs_ep > 0.0 else 0.0
        gt_state_str = (
            f"🔥 <b>#{gs_r}회차({_esc(gs_gid)}) 출동중</b> : <b>${gs_ep:.2f}</b> ➔ 목표 <b>${gs_tp:.2f}</b> (현 {gs_g:+.2f}%)"
        )
    elif (
        bool(st.get("gt_gate_scout_done", False))
        or hm_now >= ASSASSIN_MACRO_CUTOFF_HM
    ):
        gt_state_str = "🔒 <b>08:15 골든타임 마감 완료</b> (정규장 출동 영구 폐기)"
    elif hm_now < ASSASSIN_SCOUT_START_HM:
        gt_state_str = "⏳ 04:07 EST 골든타임 개시 대기"
    else:
        gt_state_str = (
            "🔍 04:07 ~ 08:14 EST 순수 10대 급락 게이트 다회차 감시 중"
        )

    lines.extend(
        [
            "🕵️ <b>[골든타임(04:07 ~ 08:14) 다회차 10G 모의정찰 카운터]</b>",
            f"• 현재상태: {gt_state_str}",
            f"• 금일집계: 출동 <b>{td_gt_disp}회</b> ➔ +1%익절퇴근 <b>{td_gt_wins}회</b> (-3%해제 {td_gt_stops} · 08:15마감 {td_gt_cuts})",
            f"• 누적집계: 출동 <b>{cum_gt_disp}회</b> ➔ +1%익절퇴근 <b>{cum_gt_wins}회</b> (성공률 <b>{cum_gt_wr:.1f}%</b> · 2회+다승일 <b>{cum_gt_multi_d}일</b> · 일최다 <b>{max_gt_wins}회</b>)",
        ]
    )
    gt_hist_list = st.get("today_gt_gate_history") or []
    for gh in gt_hist_list[-6:]:
        if not isinstance(gh, dict):
            continue
        r_n = safe_int(gh.get("round_no"), 1)
        g_id = _esc(gh.get("gate_id") or "G1")
        e_tm = str(gh.get("entry_time_est") or "")[:5]
        e_pr = safe_float(gh.get("entry_price"), 0.0)
        x_pr = safe_float(gh.get("exit_price"), 0.0)
        st_c = str(gh.get("status") or "ACTIVE")
        if st_c == "WIN_100":
            res_b = f"➔ <b>${x_pr:.2f}</b> ✅익절퇴근"
        elif st_c == "ACTIVE":
            res_b = f"➔ 목표 ${safe_float(gh.get('target_price'), 0.0):.2f} 🔥추적중"
        elif st_c == "CUTOFF_0815":
            res_b = f"➔ ${x_pr:.2f} 🔒08:15마감"
        else:
            res_b = f"➔ ${x_pr:.2f} 🛡️급락해제"
        lines.append(
            f"  ▫️ <b>R{r_n}[{g_id}]</b>({e_tm}) <b>${e_pr:.2f}</b> {res_b}"
        )
    lines.append("━━━━━━━━━━━━━━━━━━")

    hist_list = st.get("day_scout_history") or []
    prior_wins = safe_int(st.get("prior_scout_wins_today"), 0)
    lines.append(
        f"🕵️ <b>[금일 기초 1주 가상 정찰병 기록 (총 {len(hist_list)}명 · +1%익절 {prior_wins}회)]</b>"
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
    l_cum = safe_float(st.get("live_cum_net_usd"), 0.0)
    s_roi = (s_cum / init_s) * 100.0
    c_roi = (c_cum / init_s) * 100.0
    safety_tot = (
        safe_int(st.get("exit_safety_stage1_cnt"), 0)
        + safe_int(st.get("exit_safety_stage23_cnt"), 0)
        + safe_int(st.get("exit_ug_qqq_stop_cnt"), 0)
    )

    lines.extend(
        [
            "━━━━━━━━━━━━━━━━━━",
            "🏆 <b>[암살자 본대 누적 성적표 (초기화: /reset_assassin)]</b>",
            f"• 총 출격일: <b>{tot_d}일</b> (<b>{win_d}승 {loss_d}패</b> · 승률 <b>{wr:.2f}%</b>) | 무매매퇴근: <b>{no_tr_d}일</b>",
            f"• 출구분포: +5%홈런 <b>{safe_int(st.get('exit_cap500_cnt'), 0)}회</b> · HA부스트 <b>{safe_int(st.get('exit_ha_boost_cnt'), 0)}회</b> · +1%보존 <b>{safe_int(st.get('exit_floor100_cnt'), 0)}회</b> · 안전망방어 <b>{safety_tot}회</b>",
            f"• 🔥 실전 누적순익: <b>{l_cum:+,.2f}$</b> (실전출격 {safe_int(st.get('live_trade_days'), 0)}일)",
            f"• 💵 모의단리 순익: <b>{s_cum:+,.2f}$</b> (<b>{s_roi:+.2f}%</b>)",
            f"• 📈 모의복리 순익: <b>{c_cum:+,.2f}$</b> (<b>{c_roi:+.2f}%</b> · MDD <b>{safe_float(st.get('comp_max_dd_pct'), 0.0):.2f}%</b>)",
        ]
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# [핵심 10] 부팅 시 암살자 순수 10대 급락 게이트 · UG 영구차단 · SN4×SN3 방어망 · 다회차 카운터 TDD 검증기
# ---------------------------------------------------------------------------
def run_assassin_plugin_tdd() -> bool:
    import tempfile

    assert SAFETY_NET_MODE_DEFAULT == "SN4_DEEP_1000_SN3_SMART_HYBRID"

    # 1) 실전 min(설정한 시드, 주문가능금액) 산출 검증
    q_sgov_held, bud_sgov_held = compute_live_assassin_entry_budget_and_qty(
        initial_seed_usd=10000.0,
        broker_bp_usd=7000.0,
        exec_price=50.0,
        round_trip_fee_rate_pct=0.14,
    )
    q_full_bp, bud_full_bp = compute_live_assassin_entry_budget_and_qty(
        initial_seed_usd=10000.0,
        broker_bp_usd=12500.0,
        exec_price=50.0,
        round_trip_fee_rate_pct=0.14,
    )
    assert (
        abs(bud_sgov_held - 7000.0) < 1e-6
        and q_sgov_held == 139
        and abs(bud_full_bp - 10000.0) < 1e-6
        and q_full_bp == 199
    ), f"실전 암살자 min(시드, 주문가능금액) 검증 실패: {bud_sgov_held}, {bud_full_bp}"

    # 2) 선봉 정찰병(#1) 파견 순간 본대 진입 원천 차단 검증
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
    assert not hit_1

    # 3) T03_A 1분 눌림 스캔 헌법 G4 진바닥 격발 검증 (11/10 $54.79 승리 케이스)
    hit_t03a_g4, gid_t03a_g4, _ = evaluate_10_truth_gates_signal(
        day_scout_seq=1,
        rsi_14=31.8,
        vs_vwap_pct=-0.74,
        vs_prev_close_pct=-2.51,
        vs_pre_open_pct=-1.24,
        vs_scout1_pct=-1.05,
        prior_scout_wins_today=0,
        is_bull_bar=True,
        allow_sc1_dip_scan=True,
    )
    assert hit_t03a_g4 and gid_t03a_g4 == "G4"

    # 4) [Case 97-A] 구 강세장 눌림목 UG1~UG4 타점 영구 차단 검증 (11/10 $55.71 손절 케이스 100% 차단)
    hit_ug_blocked, gid_ug_blocked, _ = evaluate_10_truth_gates_signal(
        day_scout_seq=3,
        rsi_14=33.6,
        vs_vwap_pct=-0.23,
        vs_prev_close_pct=-0.87,
        vs_pre_open_pct=0.41,
        vs_scout1_pct=0.61,
        prior_scout_wins_today=2,
        is_bull_bar=True,
        allow_sc1_dip_scan=True,
        entry_type="T03A_DIP_SCAN",
        dd_from_pre_high_pct=-1.99,
        qqq_vel_1m_pct=0.08,
    )
    assert (
        not hit_ug_blocked and gid_ug_blocked == ""
    ), f"Case 97-A UG 게이트 영구 소각 검증 실패: {gid_ug_blocked}"

    # 5) 08:15 이전 안전망 비활성 & 08:15 이후 SN4×SN3 6대 지지 보호 및 진성 폭락 손절 검증
    trig_pre0815, _, _ = evaluate_directional_3stage_safety_net_v2(
        hm=810,
        is_trailing_armed=False,
        entry_price=55.00,
        live_price=52.00,
        post_entry_min_price=52.00,
        soxl_is_bull_bar=False,
        soxl_is_ha_bull=False,
        soxl_prev_reg_close=56.00,
        soxl_pre_open_price=55.50,
        qqq_vel_1m_pct=-0.30,
        qqq_vel_3m_pct=-0.60,
        qqq_bear_drop_amp_pct=2.00,
        nq_entry_bear_amp_pct=2.00,
        entry_qqq_price=675.00,
        qqq_live_price=665.00,
        entry_gate_id="G4",
    )
    assert not trig_pre0815

    trig_sn3_hold, _, _ = evaluate_directional_3stage_safety_net_v2(
        hm=833,
        is_trailing_armed=False,
        entry_price=54.79,
        live_price=53.50,
        post_entry_min_price=53.20,
        soxl_is_bull_bar=True,
        soxl_is_ha_bull=False,
        soxl_prev_reg_close=56.20,
        soxl_pre_open_price=55.48,
        qqq_vel_1m_pct=-0.20,
        qqq_vel_3m_pct=-0.40,
        qqq_bear_drop_amp_pct=1.50,
        nq_entry_bear_amp_pct=2.00,
        entry_qqq_price=675.72,
        qqq_live_price=668.50,
        entry_gate_id="G4",
    )
    assert not trig_sn3_hold

    trig_sn3_cut, sn3_code, _ = evaluate_directional_3stage_safety_net_v2(
        hm=946,
        is_trailing_armed=False,
        entry_price=54.79,
        live_price=52.80,
        post_entry_min_price=52.80,
        soxl_is_bull_bar=False,
        soxl_is_ha_bull=False,
        soxl_prev_reg_close=56.20,
        soxl_pre_open_price=55.48,
        qqq_vel_1m_pct=-0.25,
        qqq_vel_3m_pct=-0.45,
        qqq_bear_drop_amp_pct=1.80,
        nq_entry_bear_amp_pct=2.00,
        entry_qqq_price=675.72,
        qqq_live_price=667.00,
        entry_gate_id="G4",
    )
    assert trig_sn3_cut and sn3_code == "STAGE23_DIR_BEAR_BREAK"

    # 6) [Case 96] 골든타임 다회차 10G [모의] 정찰 카운터 원장 영속화 검증
    with tempfile.TemporaryDirectory() as tmp_d:
        t_ledger = AssassinSimLedger(base_dir=tmp_d, sniper_seed_usd=10000.0)
        st_gt = t_ledger.update_state_sync(
            gt_active_gate_scout={
                "round_no": 1,
                "gate_id": "G4",
                "trigger_mode": "T03A_1M_DIP_SCAN",
                "entry_time_est": "04:11:01",
                "entry_ts": 1000.0,
                "entry_price": 54.79,
                "target_price": 55.34,
                "entry_qqq_price": 675.72,
                "scout_seq_at_entry": 1,
            },
            today_gt_gate_dispatches=1,
            cum_gt_gate_dispatches=1,
            today_gt_gate_history=[
                {
                    "round_no": 1,
                    "gate_id": "G4",
                    "entry_time_est": "04:11:01",
                    "entry_price": 54.79,
                    "target_price": 55.34,
                    "status": "ACTIVE",
                }
            ],
        )
        assert isinstance(st_gt["gt_active_gate_scout"], dict)
        assert abs(st_gt["gt_active_gate_scout"]["target_price"] - 55.34) < 1e-6

        upd_h = _update_gt_history_round_entry(
            st_gt["today_gt_gate_history"],
            round_no=1,
            exit_time_est="04:13:18",
            exit_price=55.34,
            ep_fallback=54.79,
            status_code="WIN_100",
        )
        st_gt2 = t_ledger.update_state_sync(
            gt_active_gate_scout=None,
            today_gt_gate_win_exits=2,
            cum_gt_gate_win_exits=2,
            today_gt_gate_history=upd_h,
        )
        assert (
            st_gt2["gt_active_gate_scout"] is None
            and st_gt2["today_gt_gate_win_exits"] == 2
            and st_gt2["max_daily_gt_gate_wins"] == 2
            and st_gt2["today_gt_gate_history"][0]["status"] == "WIN_100"
        ), f"Case 96 다회차 10G 정찰 카운터 검증 실패: {st_gt2}"

    return True
