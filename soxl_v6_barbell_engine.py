# -*- coding: utf-8 -*-
"""
# MODIFIED: Case 114 — SOXL Sniper Ultimate v6.0 바벨 전용 상태머신 (전 계좌 통일 배포 정본)
절대 규율:
  1) 각 실행 폴더(pipiosToss · wonToss · 외부 GitHub 서버) 동적 격리 운용 (/home/pipios4006 마스터 데이터 쓰기만 영구 차단)
  2) 순수현금 모드 영구 폐기 — 오직 60/30/10 바벨(코어 19.0% = 전체 시드 11.4%)만 운용
  3) 기본값 BARBELL_SIMPLE(단리·수익금고 영구 격리) ⇄ 토글 BARBELL_COMPOUND(0주 졸업 시 60:30:10 복리 재투자)
  4) T-1h(14:59 / 조기폐장 11:59 EST) 일 1회 단발 판정 · 시간외 +4.0% 스윕 · L2+L7 병합 · COND_SMA120 5중 게이트
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

EST_TZ = ZoneInfo("America/New_York")

PIPIOS_ONLY_ROOT: str = "/home/pipiosToss"
READONLY_MASTER_SOXL_NPZ: str = "/home/pipios4006/SOXL_1min_2022_2026.npz"

BARBELL_MODE_SIMPLE: str = "BARBELL_SIMPLE"
BARBELL_MODE_COMPOUND: str = "BARBELL_COMPOUND"
VALID_BARBELL_MODES: Tuple[str, str] = (BARBELL_MODE_SIMPLE, BARBELL_MODE_COMPOUND)

V6_CORE_PCT: float = 19.0
V6_BARBELL_CORE_WEIGHT: float = 0.60
V6_BARBELL_SGOV_WEIGHT: float = 0.30
V6_BARBELL_RESERVE_WEIGHT: float = 0.10
V6_SEED_RATIO: float = V6_BARBELL_CORE_WEIGHT * (V6_CORE_PCT / 100.0)  # 0.114 (11.4%)
V6_EXT_TP_PCT: float = 4.0
V6_RTH_T1H_TP_RATIO: float = 0.01
V6_IDLE_TRIGGER_DAYS: int = 5
V6_PROG_STEPS: Tuple[float, ...] = (
    0.0,
    -0.01,
    -0.02,
    -0.03,
    -0.04,
    -0.05,
    -0.06,
    -0.08,
)
DEFAULT_SGOV_NOMINAL_PX: float = 100.30


# MODIFIED [Case 114]: 전 배포 계좌(배우자·외부 서버·TDD 임시폴더) 허용 및 /home/pipios4006 마스터 경로 쓰기 영구 차단
def assert_pipios_only_path(
    file_path: str, allowed_root: Optional[str] = None
) -> str:
    import tempfile as _v6_tf

    raw = str(file_path or "").strip()
    if not raw:
        raise PermissionError("[V6_PATH_GUARD] 빈 파일 경로는 허용되지 않습니다.")
    real_p = os.path.realpath(os.path.abspath(raw))
    if real_p == "/home/pipios4006" or real_p.startswith("/home/pipios4006/"):
        raise PermissionError(
            f"[V6_PATH_GUARD] 마스터 데이터 보호 경로 쓰기 차단: {real_p}"
        )
    bot_root = os.path.realpath(
        os.path.abspath(
            allowed_root
            if (isinstance(allowed_root, str) and allowed_root.strip())
            else (os.path.dirname(os.path.abspath(__file__)) or ".")
        )
    )
    tmp_root = os.path.realpath(os.path.abspath(_v6_tf.gettempdir()))
    if not (
        real_p == bot_root
        or real_p.startswith(bot_root + os.sep)
        or real_p == tmp_root
        or real_p.startswith(tmp_root + os.sep)
        or real_p.startswith("/tmp/")
    ):
        raise PermissionError(
            f"[V6_PATH_GUARD] 현재 봇 폴더({bot_root}) 외부 경로 쓰기 차단: {real_p}"
        )
    return real_p


def normalize_barbell_mode(raw_mode: Optional[str]) -> str:
    m = str(raw_mode or "").upper().strip()
    if m in (BARBELL_MODE_COMPOUND, "COMPOUND", "BARBELL_COMP", "V6_BARBELL_COMP"):
        return BARBELL_MODE_COMPOUND
    return BARBELL_MODE_SIMPLE


def format_barbell_mode_ko(mode_str: str) -> str:
    norm = normalize_barbell_mode(mode_str)
    if norm == BARBELL_MODE_COMPOUND:
        return "바벨(복리·재투자)"
    return "바벨(단리·금고분리)"


def _is_v6_full_holiday(d_obj: dt.date) -> bool:
    try:
        from toss_api import is_nyse_full_holiday_date

        return bool(is_nyse_full_holiday_date(d_obj))
    except Exception:
        return False


def is_nyse_early_close_date(d_obj: dt.date, last_rth_hm: int = 1559) -> bool:
    if last_rth_hm <= 1315:
        return True
    if _is_v6_full_holiday(d_obj):
        return False
    try:
        from toss_api import is_nyse_early_close_calendar_date

        return bool(is_nyse_early_close_calendar_date(d_obj, last_rth_hm=last_rth_hm))
    except Exception:
        pass
    yr, mo, dy = d_obj.year, d_obj.month, d_obj.day
    if mo == 11:
        nov1 = dt.date(yr, 11, 1)
        off_thu = (3 - nov1.weekday()) % 7
        thanksgiving = nov1 + dt.timedelta(days=off_thu + 21)
        if d_obj == thanksgiving + dt.timedelta(days=1):
            return True
    if mo == 12 and dy == 24 and d_obj.weekday() < 5:
        return True
    if mo == 7 and dy == 3 and dt.date(yr, 7, 4).weekday() in (1, 2, 3, 4):
        return True
    return False


def get_session_windows_est(
    now_est: dt.datetime, early_close_override: Optional[bool] = None
) -> Dict[str, Any]:
    d_obj = now_est.date()
    wd = d_obj.weekday()
    hm = now_est.hour * 100 + now_est.minute
    is_hol = _is_v6_full_holiday(d_obj)
    is_early = (
        False
        if is_hol
        else (
            bool(early_close_override)
            if early_close_override is not None
            else is_nyse_early_close_date(d_obj)
        )
    )
    t1h_start_hm = 1159 if is_early else 1459
    rth_end_hm = 1259 if is_early else 1559
    sgov_end_hm = 1255 if is_early else 1555

    is_weekend_closed = (
        (wd == 4 and hm >= 2000)
        or (wd == 5)
        or (wd == 6 and hm < 1800)
    )
    is_toss_open_blackout = 400 <= hm <= 406
    is_ext_tradable = (
        (not is_weekend_closed)
        and (not is_hol)
        and (not is_toss_open_blackout)
        and (hm < 930 or hm > rth_end_hm)
    )
    is_rth_watch = (not is_hol) and (wd < 5) and (930 <= hm < t1h_start_hm)
    is_t1h_window = (not is_hol) and (wd < 5) and (t1h_start_hm <= hm <= rth_end_hm)
    is_sgov_window = (not is_hol) and (wd < 5) and (931 <= hm <= sgov_end_hm)

    return {
        "date_ymd": d_obj.year * 10000 + d_obj.month * 100 + d_obj.day,
        "weekday": wd,
        "hm": hm,
        "is_holiday_closed": is_hol,
        "is_early_close": is_early,
        "t1h_start_hm": t1h_start_hm,
        "rth_end_hm": rth_end_hm,
        "sgov_end_hm": sgov_end_hm,
        "is_ext_tradable": is_ext_tradable,
        "is_rth_watch": is_rth_watch,
        "is_t1h_window": is_t1h_window,
        "is_sgov_window": is_sgov_window,
    }


def compute_cent_grid_heikin_ashi_flags(
    ohlc_bars: Sequence[Tuple[float, float, float, float]]
) -> Tuple[bool, bool, float, float]:
    if not ohlc_bars:
        return False, False, 0.0, 0.0
    o0, h0, l0, c0 = ohlc_bars[0]
    ha_o = 0.5 * (float(o0) + float(c0))
    ha_c = 0.25 * (float(o0) + float(h0) + float(l0) + float(c0))
    last_h = float(h0)
    last_l = float(l0)

    for k in range(1, len(ohlc_bars)):
        ok, hk, lk, ck = ohlc_bars[k]
        ha_o = 0.5 * (ha_o + ha_c)
        ha_c = 0.25 * (float(ok) + float(hk) + float(lk) + float(ck))
        last_h = float(hk)
        last_l = float(lk)

    ho_r = round(ha_o, 2)
    hc_r = round(ha_c, 2)
    hh_r = round(max(last_h, ha_o, ha_c), 2)
    hl_r = round(min(last_l, ha_o, ha_c), 2)
    shaved_bear = bool((hc_r < ho_r) and (hh_r <= ho_r))
    shaved_bull = bool((hc_r > ho_r) and (hl_r >= ho_r))
    return shaved_bear, shaved_bull, ho_r, hc_r


@dataclass
class LayerSlot:
    p: float          # 수수료 제외 순수 매수(또는 병합 가중평균) 단가
    q: int            # 보유 정수 주식 수 (q >= 1)
    c: float          # 편도 매수 수수료 포함 실제 투입 현금 원가
    merges: int = 0   # 누적 L2 + L7 병합 횟수
    buy_ts: int = 0   # 체결 Unix 초 또는 분봉 타임키 (동일 분봉 즉시 매도 착시 차단)


class SOXLSniperBarbellV6Engine:
    """
    Case 114 실전 운용 전용 바벨 상태머신:
      - 기본값: BARBELL_SIMPLE (0주 졸업 시 초과수익을 separated_profit_cash 금고로 영구 분리)
      - 토글값: BARBELL_COMPOUND (기격리 금고는 보존하고, 향후 졸업 수익을 60:30:10 복리 재투자)
    """

    def __init__(
        self,
        user_seed: float = 20000.0,
        barbell_mode: str = BARBELL_MODE_SIMPLE,
        roundtrip_fee: float = 0.0014,
        enable_sma120_vacuum: bool = True,
        sgov_share_px: float = DEFAULT_SGOV_NOMINAL_PX,
    ) -> None:
        self.user_seed: float = max(100.0, float(user_seed))
        self.barbell_mode: str = normalize_barbell_mode(barbell_mode)
        self.roundtrip_fee: float = max(0.0, float(roundtrip_fee))
        self.side_fee: float = self.roundtrip_fee / 2.0
        self.enable_sma120_vacuum: bool = bool(enable_sma120_vacuum)
        self.sgov_share_px: float = max(1.0, float(sgov_share_px))

        self.active_seed: float = self.user_seed
        self.separated_profit_cash: float = 0.0
        self.cycle_realized_pnl_usd: float = 0.0
        self.vault_shortfall_warning_usd: float = 0.0

        target_sgov = V6_BARBELL_SGOV_WEIGHT * self.active_seed
        init_sh = int(target_sgov // (self.sgov_share_px * (1.0 + self.side_fee)))
        sgov_cost = float(init_sh) * self.sgov_share_px * (1.0 + self.side_fee)
        self.sgov_shares: int = init_sh
        self.sgov_val: float = float(init_sh) * self.sgov_share_px
        rem_cash = max(0.0, self.active_seed - sgov_cost)
        self.soxl_cash: float = min(rem_cash, V6_BARBELL_CORE_WEIGHT * self.active_seed)
        self.reserve_cash: float = max(0.0, rem_cash - self.soxl_cash)
        self.pending_sgov_target_usd: Optional[float] = None

        self.tranche_stock: float = self.active_seed * V6_SEED_RATIO
        self.tranche_req_cash: float = self.tranche_stock * (1.0 + self.roundtrip_fee)

        self.stack: List[LayerSlot] = []
        self.last_partial_sell_p: Optional[float] = None
        self.prev_t1h_px: Optional[float] = None
        self.consecutive_no_trade_days: int = 0
        self.past_rth_closes: List[float] = []
        self.traded_on_cur_rth_day: bool = False
        self.last_eod_ymd: int = 0

        self.t1h_eval_date_ymd: int = 0
        self.t1h_wait_state: str = "NONE"
        self.today_t1h_raw_px: Optional[float] = None
        self.pending_ref_px: float = 0.0
        self.pending_eff_buy_ref: float = 0.0
        self.pending_eff_drop: float = 0.0
        self.pending_is_vac: bool = False

        self.depletion_blocks: int = 0
        self.vacuum_buys: int = 0
        self.total_merges: int = 0
        self.total_buys: int = 0
        self.total_sells: int = 0
        self.completed_cycles: int = 0

    @property
    def is_simple_mode(self) -> bool:
        return self.barbell_mode == BARBELL_MODE_SIMPLE

    @property
    def is_compound_mode(self) -> bool:
        return self.barbell_mode == BARBELL_MODE_COMPOUND

    def get_current_sma120(self) -> Optional[float]:
        if len(self.past_rth_closes) < 120:
            return None
        return float(sum(self.past_rth_closes[-120:])) / 120.0

    def bootstrap_market_history(
        self,
        completed_daily_closes: Optional[Sequence[float]] = None,
        prev_t1h_px: Optional[float] = None,
        allow_readonly_npz_fallback: bool = True,
    ) -> int:
        """
        패치 직후 첫날부터 COND_SMA120 진공탈출 스위치가 즉시 작동하도록
        당일 이전 완결된 정규장 일봉 종가(최소 120개)와 직전 T-1h 가격을 시드 적재한다.
        """
        if completed_daily_closes:
            clean = [float(x) for x in completed_daily_closes if float(x) > 0.0]
            if len(clean) >= len(self.past_rth_closes):
                self.past_rth_closes = clean[-260:]

        if prev_t1h_px is not None and float(prev_t1h_px) > 0.0:
            self.prev_t1h_px = float(prev_t1h_px)

        if (
            allow_readonly_npz_fallback
            and len(self.past_rth_closes) < 120
            and os.path.isfile(READONLY_MASTER_SOXL_NPZ)
        ):
            try:
                import numpy as np

                with np.load(
                    READONLY_MASTER_SOXL_NPZ, mmap_mode="r", allow_pickle=False
                ) as z:
                    ep_k = "epoch_sec" if "epoch_sec" in z.files else "ts"
                    c_k = "close" if "close" in z.files else "c"
                    tail_n = min(int(z[c_k].shape[0]), 220000)
                    ep = np.array(z[ep_k][-tail_n:], dtype=np.int64)
                    cl = np.array(z[c_k][-tail_n:], dtype=np.float64)
                    if ep.size > 0 and np.any(ep > 10_000_000_000):
                        ep = np.where(ep > 10_000_000_000, ep // 1000, ep)

                    daily_rth_last: Dict[int, float] = {}
                    daily_t1h_first: Dict[int, float] = {}
                    today_ymd = int(dt.datetime.now(tz=EST_TZ).strftime("%Y%m%d"))
                    for ts_v, px_v in zip(ep.tolist(), cl.tolist()):
                        if px_v <= 0.0:
                            continue
                        d_est = dt.datetime.fromtimestamp(int(ts_v), tz=EST_TZ)
                        if d_est.weekday() >= 5 or _is_v6_full_holiday(d_est.date()):
                            continue
                        ymd = d_est.year * 10000 + d_est.month * 100 + d_est.day
                        if ymd >= today_ymd:
                            continue
                        hm = d_est.hour * 100 + d_est.minute
                        early = is_nyse_early_close_date(d_est.date())
                        end_hm = 1259 if early else 1559
                        t1h_hm = 1159 if early else 1459
                        if 930 <= hm <= end_hm:
                            daily_rth_last[ymd] = float(px_v)
                            if hm >= t1h_hm and ymd not in daily_t1h_first:
                                daily_t1h_first[ymd] = float(px_v)

                    sorted_ymds = sorted(daily_rth_last.keys())
                    if len(sorted_ymds) >= 120:
                        self.past_rth_closes = [
                            daily_rth_last[d] for d in sorted_ymds[-260:]
                        ]
                        if self.prev_t1h_px is None and sorted_ymds:
                            last_d = sorted_ymds[-1]
                            self.prev_t1h_px = daily_t1h_first.get(
                                last_d, daily_rth_last[last_d]
                            )
            except Exception:
                pass
        return len(self.past_rth_closes)

    def toggle_barbell_mode(self, can_trade_sgov_now: bool = False) -> str:
        if self.barbell_mode == BARBELL_MODE_SIMPLE:
            self.barbell_mode = BARBELL_MODE_COMPOUND
        else:
            self.barbell_mode = BARBELL_MODE_SIMPLE
            if len(self.stack) == 0:
                self._rebalance_on_zero_shares(can_trade_sgov_now=can_trade_sgov_now)
        return self.barbell_mode

    def set_barbell_mode(self, mode_str: str, can_trade_sgov_now: bool = False) -> str:
        target = normalize_barbell_mode(mode_str)
        if target != self.barbell_mode:
            return self.toggle_barbell_mode(can_trade_sgov_now=can_trade_sgov_now)
        return self.barbell_mode

    # MODIFIED: 기준시드 변경 시 손실 오판 방지 · 분리금고 불변 보호 · 11.4% 타격액 즉시 재산출
    def update_user_seed(
        self, new_seed_usd: float, can_trade_sgov_now: bool = False
    ) -> None:
        old_seed = self.user_seed
        clean_s = max(100.0, float(new_seed_usd))
        comp_gain = (
            max(0.0, self.active_seed - old_seed)
            if self.is_compound_mode
            else 0.0
        )
        self.user_seed = clean_s
        self.active_seed = clean_s + comp_gain
        self.tranche_stock = self.active_seed * V6_SEED_RATIO
        self.tranche_req_cash = self.tranche_stock * (1.0 + self.roundtrip_fee)

        inv_c = sum(s.c for s in self.stack)
        g_cur = float(self.sgov_shares) * self.sgov_share_px
        oper_cash = max(0.0, self.active_seed - inv_c - g_cur)
        core_cap = max(0.0, V6_BARBELL_CORE_WEIGHT * self.active_seed - inv_c)
        self.soxl_cash = min(oper_cash, core_cap)
        self.reserve_cash = max(0.0, oper_cash - self.soxl_cash)

        if len(self.stack) == 0:
            target_sgov_usd = V6_BARBELL_SGOV_WEIGHT * self.active_seed
            if abs(target_sgov_usd - g_cur) >= self.sgov_share_px:
                self.pending_sgov_target_usd = target_sgov_usd
            else:
                self.pending_sgov_target_usd = None
            if can_trade_sgov_now and self.pending_sgov_target_usd is not None:
                delta_sh = self.compute_pending_sgov_rebalance_delta_shares()
                self.apply_sgov_fill(delta_sh, self.sgov_share_px)

    def update_roundtrip_fee(self, new_roundtrip_fee: float) -> None:
        self.roundtrip_fee = max(0.0, float(new_roundtrip_fee))
        self.side_fee = self.roundtrip_fee / 2.0
        if len(self.stack) == 0:
            self.tranche_req_cash = self.tranche_stock * (1.0 + self.roundtrip_fee)

    def record_vault_withdrawal(self, withdrawn_usd: float) -> float:
        amt = max(0.0, min(float(withdrawn_usd), self.separated_profit_cash))
        self.separated_profit_cash -= amt
        return self.separated_profit_cash

    def assert_reconciled_with_broker(self, broker_soxl_qty: int) -> None:
        ledger_qty = sum(slot.q for slot in self.stack)
        if ledger_qty != int(broker_soxl_qty):
            raise RuntimeError(
                f"[RECONCILE_MISMATCH] 내부원장={ledger_qty}주 != 토스잔고={int(broker_soxl_qty)}주"
            )

    def sync_with_broker_snapshot(
        self,
        broker_usd_cash: float,
        broker_sgov_shares: int,
        broker_sgov_px: float = DEFAULT_SGOV_NOMINAL_PX,
    ) -> Dict[str, float]:
        if broker_sgov_px > 1.0:
            self.sgov_share_px = float(broker_sgov_px)
        self.sgov_shares = max(0, int(broker_sgov_shares))
        self.sgov_val = float(self.sgov_shares) * self.sgov_share_px

        raw_cash = max(0.0, float(broker_usd_cash))
        if raw_cash + 1e-6 < self.separated_profit_cash:
            self.vault_shortfall_warning_usd = self.separated_profit_cash - raw_cash
            oper_cash = 0.0
        else:
            self.vault_shortfall_warning_usd = 0.0
            oper_cash = raw_cash - self.separated_profit_cash

        # MODIFIED [Case 114]: SOXL 보유 중 유령 SGOV 매수예약 소거 & 0주 SGOV 재매수 수수료 보호
        if len(self.stack) > 0:
            self.pending_sgov_target_usd = None
        invested_c = sum(s.c for s in self.stack)
        sgov_fee_resv = 0.0
        if len(self.stack) == 0 and self.pending_sgov_target_usd is not None:
            t_sh = int(float(self.pending_sgov_target_usd) // self.sgov_share_px)
            need_sh = max(0, t_sh - self.sgov_shares)
            sgov_fee_resv = float(need_sh) * self.sgov_share_px * self.side_fee
        max_bot_eq = max(
            0.0, self.active_seed + self.cycle_realized_pnl_usd + sgov_fee_resv
        )
        bot_oper_cap = max(0.0, max_bot_eq - invested_c - self.sgov_val)
        eff_oper_cash = min(oper_cash, bot_oper_cap)
        core_rem_cap = max(
            0.0, V6_BARBELL_CORE_WEIGHT * self.active_seed - invested_c
        )
        self.soxl_cash = min(eff_oper_cash, core_rem_cap)
        self.reserve_cash = max(0.0, eff_oper_cash - self.soxl_cash)

        return {
            "oper_cash": eff_oper_cash,
            "unallocated_cash": max(0.0, oper_cash - eff_oper_cash),
            "soxl_cash": self.soxl_cash,
            "reserve_cash": self.reserve_cash,
            "fenced_vault_cash": self.separated_profit_cash,
            "sgov_val": self.sgov_val,
        }

    def get_req_drop(self) -> float:
        k = min(len(self.stack), 7)
        return V6_PROG_STEPS[k]

    def calc_sgov_sell_shares_needed(self) -> int:
        avail_cash = self.soxl_cash + self.reserve_cash
        if avail_cash + 1e-9 >= self.tranche_req_cash or self.sgov_shares <= 0:
            return 0
        need = self.tranche_req_cash - avail_cash
        net_per_sh = self.sgov_share_px * (1.0 - self.side_fee)
        return min(
            self.sgov_shares, max(1, int(math.ceil((need - 1e-12) / net_per_sh)))
        )

    def compute_pending_sgov_rebalance_delta_shares(self) -> int:
        if self.pending_sgov_target_usd is None:
            return 0
        target_sh = int(float(self.pending_sgov_target_usd) // self.sgov_share_px)
        diff = target_sh - self.sgov_shares
        if diff > 0:
            c_tot = self.soxl_cash + self.reserve_cash
            unit_cost = self.sgov_share_px * (1.0 + self.side_fee)
            max_buy = int(c_tot // unit_cost)
            return max(0, min(diff, max_buy))
        return diff

    def apply_sgov_fill(self, signed_shares: int, exec_px: float) -> None:
        px = float(exec_px) if exec_px > 1.0 else self.sgov_share_px
        self.sgov_share_px = px
        c_tot = self.soxl_cash + self.reserve_cash

        if signed_shares > 0:
            cost = float(signed_shares) * px * (1.0 + self.side_fee)
            c_tot = max(0.0, c_tot - cost)
            self.sgov_shares += int(signed_shares)
        elif signed_shares < 0:
            sell_sh = min(self.sgov_shares, abs(int(signed_shares)))
            net_in = float(sell_sh) * px * (1.0 - self.side_fee)
            c_tot += net_in
            self.sgov_shares -= sell_sh

        self.sgov_val = float(self.sgov_shares) * self.sgov_share_px
        self.pending_sgov_target_usd = None

        if len(self.stack) == 0 and self.is_simple_mode:
            keep_cash = max(0.0, self.user_seed - self.sgov_val)
            if c_tot > keep_cash + 1e-9:
                extra = c_tot - keep_cash
                self.separated_profit_cash += extra
                c_tot = keep_cash

        invested_c = sum(s.c for s in self.stack)
        core_cap = max(0.0, V6_BARBELL_CORE_WEIGHT * self.active_seed - invested_c)
        self.soxl_cash = min(c_tot, max(core_cap, self.tranche_req_cash))
        self.reserve_cash = max(0.0, c_tot - self.soxl_cash)

    def plan_buy_order_qty(
        self, ref_px: float, cur_px: float, can_trade_sgov_now: bool = True
    ) -> Tuple[int, int]:
        if ref_px <= 0.0 or cur_px <= 0.0:
            return 0, 0
        q_fixed = min(
            int(self.tranche_stock // float(ref_px)),
            int(self.tranche_stock // float(cur_px)),
        )
        sgov_liq = (
            float(self.sgov_shares) * self.sgov_share_px * (1.0 - self.side_fee)
            if can_trade_sgov_now
            else 0.0
        )
        max_avail = self.soxl_cash + self.reserve_cash + sgov_liq
        if q_fixed < 1 or (max_avail + 1e-9 < self.tranche_req_cash):
            self.depletion_blocks += 1
            return 0, 0
        sgov_sell_sh = self.calc_sgov_sell_shares_needed() if can_trade_sgov_now else 0
        if (not can_trade_sgov_now) and (
            self.soxl_cash + self.reserve_cash + 1e-9 < self.tranche_req_cash
        ):
            self.depletion_blocks += 1
            return 0, 0
        return q_fixed, sgov_sell_sh

    def commit_buy_fill(
        self,
        q_filled: int,
        exec_px: float,
        exec_ts: int,
        is_vac: bool = False,
    ) -> None:
        if q_filled < 1:
            return
        if self.soxl_cash < self.tranche_req_cash and self.reserve_cash > 0.0:
            pulled = min(self.tranche_req_cash - self.soxl_cash, self.reserve_cash)
            self.reserve_cash -= pulled
            self.soxl_cash += pulled

        total_out = float(q_filled) * float(exec_px) * (1.0 + self.side_fee)
        if self.soxl_cash >= self.tranche_req_cash:
            self.soxl_cash -= self.tranche_req_cash
            returned = max(0.0, self.tranche_req_cash - total_out)
            self.soxl_cash += returned
        else:
            rem_need = max(0.0, total_out - self.soxl_cash)
            self.soxl_cash = 0.0
            self.reserve_cash = max(0.0, self.reserve_cash - rem_need)

        if self.soxl_cash < self.tranche_req_cash and self.reserve_cash > 0.0:
            imm_pull = min(self.tranche_req_cash - self.soxl_cash, self.reserve_cash)
            self.reserve_cash -= imm_pull
            self.soxl_cash += imm_pull

        self.last_partial_sell_p = None
        self.pending_sgov_target_usd = None
        new_slot = LayerSlot(
            p=float(exec_px),
            q=int(q_filled),
            c=float(total_out),
            merges=0,
            buy_ts=int(exec_ts),
        )
        if len(self.stack) < 7:
            self.stack.insert(0, new_slot)
        else:
            old_l1 = self.stack[0]
            old_l2 = self.stack[1]
            old_3_6 = self.stack[2:6]
            old_l7 = self.stack[6]
            mq = old_l2.q + old_l7.q
            mc = old_l2.c + old_l7.c
            mp = (old_l2.p * old_l2.q + old_l7.p * old_l7.q) / float(mq)
            m_cnt = old_l2.merges + old_l7.merges + 1
            m_ts = min(old_l2.buy_ts, old_l7.buy_ts)
            merged_slot = LayerSlot(
                p=mp, q=mq, c=mc, merges=m_cnt, buy_ts=m_ts
            )
            self.stack = [new_slot, old_l1] + sorted(
                old_3_6 + [merged_slot], key=lambda s: s.p
            )
            self.total_merges += 1

        self.total_buys += 1
        self.traded_on_cur_rth_day = True
        if is_vac:
            self.vacuum_buys += 1

    def _rebalance_on_zero_shares(self, can_trade_sgov_now: bool = False) -> None:
        # MODIFIED: 0주 졸업 시 외부 추가수혈 원금은 미할당 예수금으로 선행 상환하고 순수익만 금고/복리 반영
        cyc_gain = max(0.0, self.cycle_realized_pnl_usd)
        self.last_partial_sell_p = None
        self.cycle_realized_pnl_usd = 0.0
        c_tot = self.soxl_cash + self.reserve_cash
        g_cur = float(self.sgov_shares) * self.sgov_share_px
        max_valid_oper_eq = self.active_seed + cyc_gain
        if (c_tot + g_cur) > (max_valid_oper_eq + 1e-6):
            ext_repay = (c_tot + g_cur) - max_valid_oper_eq
            c_tot = max(0.0, c_tot - ext_repay)

        if self.is_simple_mode:
            total_oper_eq = c_tot + g_cur
            if total_oper_eq > self.user_seed:
                self.active_seed = self.user_seed
                target_sgov_usd = V6_BARBELL_SGOV_WEIGHT * self.user_seed
                target_sh = int(target_sgov_usd // self.sgov_share_px)
                if not can_trade_sgov_now:
                    need_buy_sh = max(0, target_sh - self.sgov_shares)
                    keep_cash = max(
                        0.0,
                        (self.user_seed - min(g_cur, float(target_sh) * self.sgov_share_px))
                        + float(need_buy_sh) * self.sgov_share_px * self.side_fee,
                    )
                    if c_tot > keep_cash + 1e-9:
                        lockable = c_tot - keep_cash
                        self.separated_profit_cash += lockable
                        c_tot = keep_cash
            else:
                self.active_seed = max(100.0, total_oper_eq)
                target_sgov_usd = V6_BARBELL_SGOV_WEIGHT * self.active_seed
        else:
            e_pre = c_tot + g_cur
            if V6_BARBELL_SGOV_WEIGHT * e_pre >= g_cur:
                s_new = (c_tot + g_cur * (1.0 + self.side_fee)) / (
                    1.0 + V6_BARBELL_SGOV_WEIGHT * self.side_fee
                )
            else:
                s_new = (c_tot + g_cur * (1.0 - self.side_fee)) / (
                    1.0 - V6_BARBELL_SGOV_WEIGHT * self.side_fee
                )
            self.active_seed = max(100.0, s_new)
            target_sgov_usd = V6_BARBELL_SGOV_WEIGHT * self.active_seed

        self.tranche_stock = self.active_seed * V6_SEED_RATIO
        self.tranche_req_cash = self.tranche_stock * (1.0 + self.roundtrip_fee)

        self.soxl_cash = min(
            c_tot, max(V6_BARBELL_CORE_WEIGHT * self.active_seed, self.tranche_req_cash)
        )
        self.reserve_cash = max(0.0, c_tot - self.soxl_cash)
        self.pending_sgov_target_usd = target_sgov_usd

        if can_trade_sgov_now:
            delta_sh = self.compute_pending_sgov_rebalance_delta_shares()
            self.apply_sgov_fill(delta_sh, self.sgov_share_px)

    def get_sweep_sellable_qty(
        self, cur_px: float, min_gain_ratio: float, cur_ts: int
    ) -> int:
        if not self.stack:
            return 0
        thr = 1.0 + float(min_gain_ratio)
        return sum(
            s.q
            for s in self.stack
            if s.buy_ts < int(cur_ts) and float(cur_px) >= s.p * thr
        )

    # NEW: 다층 동시 스윕 시 최상위 스윕 지층 목표가를 하한선(min_floor)으로 반환하여 목표 미달 체결 원천 차단
    def get_sweep_sellable_plan(
        self, cur_px: float, min_gain_ratio: float, cur_ts: int
    ) -> Tuple[int, float]:
        if not self.stack:
            return 0, 0.0
        thr = 1.0 + float(min_gain_ratio)
        eligible = [
            s
            for s in self.stack
            if s.buy_ts < int(cur_ts) and float(cur_px) >= s.p * thr
        ]
        if not eligible:
            return 0, 0.0
        tot_q = sum(s.q for s in eligible)
        max_swept_p = max(s.p for s in eligible)
        min_floor = round(
            math.ceil((max_swept_p * thr - 1e-9) * 100.0) / 100.0, 2
        )
        return int(tot_q), float(min_floor)

    def commit_sweep_sell_fill(
        self,
        exec_px: float,
        min_gain_ratio: float,
        cur_ts: int,
        can_trade_sgov_now: bool = False,
    ) -> int:
        if not self.stack:
            return 0
        thr = 1.0 + float(min_gain_ratio)
        rem_stack: List[LayerSlot] = []
        sold_qty = 0

        for slot in self.stack:
            if slot.buy_ts < int(cur_ts) and float(exec_px) >= slot.p * thr:
                net_in = float(slot.q) * float(exec_px) * (1.0 - self.side_fee)
                self.soxl_cash += net_in
                self.cycle_realized_pnl_usd += net_in - slot.c
                sold_qty += slot.q
            else:
                rem_stack.append(slot)

        if sold_qty == 0:
            return 0

        self.stack = rem_stack
        self.total_sells += 1
        self.traded_on_cur_rth_day = True

        if len(self.stack) > 0:
            self.last_partial_sell_p = float(exec_px)
        else:
            self.completed_cycles += 1
            self._rebalance_on_zero_shares(can_trade_sgov_now=can_trade_sgov_now)
        return sold_qty

    # NEW: 실전 브로커 체결 수량(부분체결·슬리피지 포함) 1:1 정밀 차감 및 실현손익 정산기
    def commit_broker_sell_fill(
        self,
        filled_qty: int,
        exec_px: float,
        can_trade_sgov_now: bool = False,
    ) -> Dict[str, Any]:
        req_q = max(0, int(filled_qty))
        px = float(exec_px)
        if not self.stack or req_q <= 0 or px <= 0.0:
            return {
                "sold_qty": 0,
                "gross_pnl_usd": 0.0,
                "fee_usd": 0.0,
                "net_pnl_usd": 0.0,
                "graduated_zero": False,
                "cycle_final_net_usd": 0.0,
            }

        rem_q_to_cut = req_q
        rem_stack: List[LayerSlot] = []
        sold_qty = 0
        gross_pnl = 0.0
        total_fee = 0.0
        net_pnl = 0.0

        for slot in self.stack:
            if rem_q_to_cut <= 0:
                rem_stack.append(slot)
                continue
            if rem_q_to_cut >= slot.q:
                take_q = slot.q
                proceeds = float(take_q) * px
                sell_fee = proceeds * self.side_fee
                net_in = proceeds - sell_fee
                buy_fee_est = max(0.0, slot.c - float(take_q) * slot.p)
                self.soxl_cash += net_in
                gross_pnl += proceeds - (float(take_q) * slot.p)
                total_fee += buy_fee_est + sell_fee
                net_pnl += net_in - slot.c
                sold_qty += take_q
                rem_q_to_cut -= take_q
            else:
                take_q = rem_q_to_cut
                keep_q = slot.q - take_q
                ratio = float(take_q) / float(slot.q)
                part_c = slot.c * ratio
                keep_c = max(0.0, slot.c - part_c)
                proceeds = float(take_q) * px
                sell_fee = proceeds * self.side_fee
                net_in = proceeds - sell_fee
                buy_fee_est = max(0.0, part_c - float(take_q) * slot.p)
                self.soxl_cash += net_in
                gross_pnl += proceeds - (float(take_q) * slot.p)
                total_fee += buy_fee_est + sell_fee
                net_pnl += net_in - part_c
                rem_stack.append(
                    LayerSlot(
                        p=slot.p,
                        q=keep_q,
                        c=keep_c,
                        merges=slot.merges,
                        buy_ts=slot.buy_ts,
                    )
                )
                sold_qty += take_q
                rem_q_to_cut = 0

        if sold_qty <= 0:
            return {
                "sold_qty": 0,
                "gross_pnl_usd": 0.0,
                "fee_usd": 0.0,
                "net_pnl_usd": 0.0,
                "graduated_zero": False,
                "cycle_final_net_usd": 0.0,
            }

        self.stack = rem_stack
        self.total_sells += 1
        self.traded_on_cur_rth_day = True
        self.cycle_realized_pnl_usd += net_pnl
        cyc_final = self.cycle_realized_pnl_usd
        grad_zero = len(self.stack) == 0

        if not grad_zero:
            self.last_partial_sell_p = px
        else:
            self.completed_cycles += 1
            self._rebalance_on_zero_shares(can_trade_sgov_now=can_trade_sgov_now)

        return {
            "sold_qty": int(sold_qty),
            "gross_pnl_usd": round(gross_pnl, 4),
            "fee_usd": round(total_fee, 4),
            "net_pnl_usd": round(net_pnl, 4),
            "graduated_zero": bool(grad_zero),
            "cycle_final_net_usd": round(cyc_final, 4),
        }

    def evaluate_t1h_bar(
        self,
        date_ymd: int,
        px: float,
        shaved_bear: bool,
        shaved_bull: bool,
    ) -> Dict[str, Any]:
        if self.t1h_eval_date_ymd != int(date_ymd):
            self.t1h_eval_date_ymd = int(date_ymd)
            self.t1h_wait_state = "NONE"
            self.today_t1h_raw_px = float(px)

        if self.t1h_wait_state in ("IDLE", "DONE"):
            return {"action": "ALREADY_DONE_OR_IDLE", "state": self.t1h_wait_state}

        sma120_opt = self.get_current_sma120()
        sma120_val = float(sma120_opt) if sma120_opt is not None else -1.0

        if self.t1h_wait_state == "NONE":
            if len(self.stack) == 0:
                self.pending_ref_px = float(px)
                self.pending_is_vac = False
                if not shaved_bear:
                    self.t1h_wait_state = "DONE"
                    return {
                        "action": "BUY",
                        "ref_px": self.pending_ref_px,
                        "is_vac": False,
                        "reason": "T1H_INIT_BUY",
                    }
                self.t1h_wait_state = "WAIT_T1H_INIT_BUY"
                return {"action": "WAIT", "state": self.t1h_wait_state}

            l1_p = self.stack[0].p
            std_buy_ref = (
                l1_p
                if self.last_partial_sell_p is None
                else min(l1_p, self.last_partial_sell_p)
            )
            req_drop = self.get_req_drop()

            if float(px) >= l1_p * (1.0 + V6_RTH_T1H_TP_RATIO):
                if not shaved_bull:
                    self.t1h_wait_state = "DONE"
                    return {
                        "action": "SELL",
                        "min_gain_ratio": V6_RTH_T1H_TP_RATIO,
                        "reason": "T1H_SWEEP_SELL",
                    }
                self.t1h_wait_state = "WAIT_T1H_SELL"
                return {"action": "WAIT", "state": self.t1h_wait_state}

            if float(px) <= std_buy_ref * (1.0 + req_drop):
                self.pending_ref_px = std_buy_ref
                self.pending_eff_buy_ref = std_buy_ref
                self.pending_eff_drop = req_drop
                self.pending_is_vac = False
                if not shaved_bear:
                    self.t1h_wait_state = "DONE"
                    return {
                        "action": "BUY",
                        "ref_px": self.pending_ref_px,
                        "is_vac": False,
                        "reason": f"T1H_DIP_BUY({req_drop*100:.1f}%)",
                    }
                self.t1h_wait_state = "WAIT_T1H_BUY"
                return {"action": "WAIT", "state": self.t1h_wait_state}

            core_cash_ok = self.soxl_cash >= self.tranche_req_cash
            r_t = l1_p if self.prev_t1h_px is None else self.prev_t1h_px
            vac_ok = (
                self.enable_sma120_vacuum
                and (self.consecutive_no_trade_days >= V6_IDLE_TRIGGER_DAYS)
                and (sma120_val > 0.0 and float(px) > sma120_val)
                and core_cash_ok
                and ((float(px) - r_t) / r_t <= -0.01)
                and (float(px) <= l1_p * 0.99)
            )
            if vac_ok:
                self.pending_ref_px = min(r_t, l1_p)
                self.pending_eff_buy_ref = r_t
                self.pending_eff_drop = -0.01
                self.pending_is_vac = True
                if not shaved_bear:
                    self.t1h_wait_state = "DONE"
                    return {
                        "action": "BUY",
                        "ref_px": self.pending_ref_px,
                        "is_vac": True,
                        "reason": "T1H_VACUUM_SMA120_BUY",
                    }
                self.t1h_wait_state = "WAIT_T1H_BUY"
                return {"action": "WAIT", "state": self.t1h_wait_state}

            self.t1h_wait_state = "IDLE"
            return {"action": "ALREADY_DONE_OR_IDLE", "state": "IDLE"}

        if self.t1h_wait_state == "WAIT_T1H_INIT_BUY":
            if not shaved_bear:
                self.t1h_wait_state = "DONE"
                return {
                    "action": "BUY",
                    "ref_px": self.pending_ref_px,
                    "is_vac": False,
                    "reason": "T1H_INIT_BUY_HA_RELEASE",
                }
            return {"action": "WAIT", "state": self.t1h_wait_state}

        if self.t1h_wait_state == "WAIT_T1H_BUY":
            if not shaved_bear:
                self.t1h_wait_state = "DONE"
                if (
                    self.stack
                    and float(px) <= self.pending_eff_buy_ref * (1.0 + self.pending_eff_drop)
                    and float(px) <= self.stack[0].p * 0.99
                ):
                    return {
                        "action": "BUY",
                        "ref_px": self.pending_ref_px,
                        "is_vac": self.pending_is_vac,
                        "reason": "T1H_DIP_BUY_HA_RELEASE",
                    }
                return {"action": "ALREADY_DONE_OR_IDLE", "state": "CANCELLED_REBOUND"}
            return {"action": "WAIT", "state": self.t1h_wait_state}

        if self.t1h_wait_state == "WAIT_T1H_SELL":
            if not shaved_bull:
                self.t1h_wait_state = "DONE"
                if self.stack and float(px) >= self.stack[0].p * (
                    1.0 + V6_RTH_T1H_TP_RATIO
                ):
                    return {
                        "action": "SELL",
                        "min_gain_ratio": V6_RTH_T1H_TP_RATIO,
                        "reason": "T1H_SWEEP_SELL_HA_RELEASE",
                    }
                return {"action": "ALREADY_DONE_OR_IDLE", "state": "CANCELLED_PULLBACK"}
            return {"action": "WAIT", "state": self.t1h_wait_state}

        return {"action": "ALREADY_DONE_OR_IDLE", "state": self.t1h_wait_state}

    def finalize_rth_end_of_day(self, date_ymd: int, rth_close_px: float) -> None:
        if self.last_eod_ymd == int(date_ymd):
            return
        self.last_eod_ymd = int(date_ymd)
        if self.today_t1h_raw_px is not None:
            self.prev_t1h_px = float(self.today_t1h_raw_px)
        if self.traded_on_cur_rth_day:
            self.consecutive_no_trade_days = 0
        else:
            self.consecutive_no_trade_days += 1
        self.traded_on_cur_rth_day = False
        if rth_close_px > 0.0:
            self.past_rth_closes.append(float(rth_close_px))
            if len(self.past_rth_closes) > 260:
                self.past_rth_closes = self.past_rth_closes[-260:]

    def total_wealth_at(self, soxl_px: float) -> float:
        stock_val = sum(float(s.q) * float(soxl_px) for s in self.stack)
        sgov_v = float(self.sgov_shares) * self.sgov_share_px
        return (
            self.soxl_cash
            + self.reserve_cash
            + sgov_v
            + stock_val
            + self.separated_profit_cash
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": "CASE114_V6_BARBELL_ONLY",
            "user_seed": self.user_seed,
            "barbell_mode": self.barbell_mode,
            "roundtrip_fee": self.roundtrip_fee,
            "enable_sma120_vacuum": self.enable_sma120_vacuum,
            "sgov_share_px": self.sgov_share_px,
            "active_seed": self.active_seed,
            "separated_profit_cash": self.separated_profit_cash,
            "cycle_realized_pnl_usd": self.cycle_realized_pnl_usd,
            "sgov_shares": self.sgov_shares,
            "sgov_val": self.sgov_val,
            "soxl_cash": self.soxl_cash,
            "reserve_cash": self.reserve_cash,
            "pending_sgov_target_usd": self.pending_sgov_target_usd,
            "tranche_stock": self.tranche_stock,
            "tranche_req_cash": self.tranche_req_cash,
            "stack": [asdict(s) for s in self.stack],
            "last_partial_sell_p": self.last_partial_sell_p,
            "prev_t1h_px": self.prev_t1h_px,
            "consecutive_no_trade_days": self.consecutive_no_trade_days,
            "past_rth_closes": list(self.past_rth_closes[-260:]),
            "traded_on_cur_rth_day": self.traded_on_cur_rth_day,
            "last_eod_ymd": self.last_eod_ymd,
            "t1h_eval_date_ymd": self.t1h_eval_date_ymd,
            "t1h_wait_state": self.t1h_wait_state,
            "today_t1h_raw_px": self.today_t1h_raw_px,
            "pending_ref_px": self.pending_ref_px,
            "pending_eff_buy_ref": self.pending_eff_buy_ref,
            "pending_eff_drop": self.pending_eff_drop,
            "pending_is_vac": self.pending_is_vac,
            "depletion_blocks": self.depletion_blocks,
            "vacuum_buys": self.vacuum_buys,
            "total_merges": self.total_merges,
            "total_buys": self.total_buys,
            "total_sells": self.total_sells,
            "completed_cycles": self.completed_cycles,
            "updated_at": dt.datetime.now(tz=EST_TZ).isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SOXLSniperBarbellV6Engine":
        eng = cls(
            user_seed=float(
                data.get("user_seed", data.get("initial_seed_usd", 20000.0))
            ),
            barbell_mode=normalize_barbell_mode(
                data.get("barbell_mode", data.get("portion_mode", BARBELL_MODE_SIMPLE))
            ),
            roundtrip_fee=float(data.get("roundtrip_fee", 0.0014)),
            enable_sma120_vacuum=bool(data.get("enable_sma120_vacuum", True)),
            sgov_share_px=float(data.get("sgov_share_px", DEFAULT_SGOV_NOMINAL_PX)),
        )
        eng.active_seed = float(data.get("active_seed", eng.user_seed))
        eng.separated_profit_cash = max(
            0.0,
            float(
                data.get(
                    "separated_profit_cash",
                    data.get("vault_realized_profit_usd", 0.0),
                )
            ),
        )
        eng.cycle_realized_pnl_usd = float(data.get("cycle_realized_pnl_usd", 0.0))
        eng.sgov_shares = max(0, int(data.get("sgov_shares", eng.sgov_shares)))
        eng.sgov_val = float(eng.sgov_shares) * eng.sgov_share_px
        eng.soxl_cash = max(0.0, float(data.get("soxl_cash", eng.soxl_cash)))
        eng.reserve_cash = max(0.0, float(data.get("reserve_cash", eng.reserve_cash)))
        raw_pend = data.get("pending_sgov_target_usd", None)
        eng.pending_sgov_target_usd = float(raw_pend) if raw_pend is not None else None

        eng.tranche_stock = eng.active_seed * V6_SEED_RATIO
        eng.tranche_req_cash = eng.tranche_stock * (1.0 + eng.roundtrip_fee)

        raw_stack = data.get("stack", [])
        parsed_slots: List[LayerSlot] = []
        for item in raw_stack:
            q_v = int(item.get("q", item.get("qty", 0)))
            p_v = float(item.get("p", item.get("price", 0.0)))
            if q_v >= 1 and p_v > 0.0:
                c_v = float(
                    item.get("c", float(q_v) * p_v * (1.0 + eng.side_fee))
                )
                parsed_slots.append(
                    LayerSlot(
                        p=p_v,
                        q=q_v,
                        c=c_v,
                        merges=int(item.get("merges", 0)),
                        buy_ts=int(item.get("buy_ts", 0)),
                    )
                )
        parsed_slots.sort(key=lambda s: s.p)
        while len(parsed_slots) > 7:
            old_l1 = parsed_slots[0]
            old_l2 = parsed_slots[1]
            old_mid = parsed_slots[2:-1]
            old_last = parsed_slots[-1]
            mq = old_l2.q + old_last.q
            mc = old_l2.c + old_last.c
            mp = (old_l2.p * old_l2.q + old_last.p * old_last.q) / float(mq)
            merged = LayerSlot(
                p=mp,
                q=mq,
                c=mc,
                merges=old_l2.merges + old_last.merges + 1,
                buy_ts=min(old_l2.buy_ts, old_last.buy_ts),
            )
            parsed_slots = [old_l1] + sorted(old_mid + [merged], key=lambda s: s.p)
        eng.stack = parsed_slots
        if len(eng.stack) > 0:
            eng.pending_sgov_target_usd = None

        lp = data.get("last_partial_sell_p", None)
        eng.last_partial_sell_p = float(lp) if lp is not None else None
        pt = data.get("prev_t1h_px", None)
        eng.prev_t1h_px = float(pt) if pt is not None else None
        eng.consecutive_no_trade_days = max(
            0, int(data.get("consecutive_no_trade_days", 0))
        )
        eng.past_rth_closes = [
            float(x) for x in data.get("past_rth_closes", []) if float(x) > 0.0
        ][-260:]
        eng.traded_on_cur_rth_day = bool(data.get("traded_on_cur_rth_day", False))
        eng.last_eod_ymd = int(data.get("last_eod_ymd", 0))

        eng.t1h_eval_date_ymd = int(data.get("t1h_eval_date_ymd", 0))
        eng.t1h_wait_state = str(data.get("t1h_wait_state", "NONE"))
        tt = data.get("today_t1h_raw_px", None)
        eng.today_t1h_raw_px = float(tt) if tt is not None else None
        eng.pending_ref_px = float(data.get("pending_ref_px", 0.0))
        eng.pending_eff_buy_ref = float(data.get("pending_eff_buy_ref", 0.0))
        eng.pending_eff_drop = float(data.get("pending_eff_drop", 0.0))
        eng.pending_is_vac = bool(data.get("pending_is_vac", False))

        eng.depletion_blocks = int(data.get("depletion_blocks", 0))
        eng.vacuum_buys = int(data.get("vacuum_buys", 0))
        eng.total_merges = int(data.get("total_merges", 0))
        eng.total_buys = int(data.get("total_buys", 0))
        eng.total_sells = int(data.get("total_sells", 0))
        eng.completed_cycles = int(data.get("completed_cycles", 0))
        return eng

    @classmethod
    def migrate_from_case113_state(
        cls,
        legacy_state: Dict[str, Any],
        legacy_barbell_state: Optional[Dict[str, Any]] = None,
    ) -> "SOXLSniperBarbellV6Engine":
        # MODIFIED: 타 사용자 기존 원장의 book_price · sub_buckets · sgov_held_qty · vaulted_profit_locked_usd 무손실 이관
        bb = legacy_barbell_state or {}
        seed = float(
            legacy_state.get(
                "initial_seed_usd",
                bb.get(
                    "initial_seed_usd", legacy_state.get("user_seed", 20000.0)
                ),
            )
            or 20000.0
        )
        vault_p = max(
            0.0,
            float(bb.get("vault_realized_profit_usd") or 0.0),
            float(legacy_state.get("vaulted_profit_locked_usd") or 0.0),
            float(legacy_state.get("vault_realized_profit_usd") or 0.0),
        )
        sgov_sh = max(
            0,
            int(
                float(
                    bb.get("sgov_held_qty")
                    or bb.get("sgov_shares")
                    or legacy_state.get("sgov_held_qty")
                    or legacy_state.get("sgov_shares")
                    or 0
                )
            ),
        )

        raw_buckets = list(
            legacy_state.get("buckets", legacy_state.get("layers", [])) or []
        ) + list(legacy_state.get("sub_buckets", []) or [])
        slot_dicts: List[Dict[str, Any]] = []
        for b in raw_buckets:
            if not isinstance(b, dict):
                continue
            q_v = int(float(b.get("qty") or b.get("q") or 0))
            p_v = float(
                b.get("book_price")
                or b.get("avg_price")
                or b.get("buy_price")
                or b.get("p")
                or 0.0
            )
            if q_v >= 1 and p_v > 0.0:
                lots = max(1, int(float(b.get("lot_count") or 1)))
                slot_dicts.append(
                    {
                        "p": p_v,
                        "q": q_v,
                        "merges": max(0, lots - 1),
                        "buy_ts": int(float(b.get("buy_ts") or 0)),
                    }
                )

        migrated = {
            "user_seed": max(100.0, seed),
            "barbell_mode": BARBELL_MODE_SIMPLE,
            "separated_profit_cash": max(0.0, vault_p),
            "sgov_shares": max(0, sgov_sh),
            "stack": slot_dicts,
        }
        eng = cls.from_dict(migrated)
        eng.bootstrap_market_history(allow_readonly_npz_fallback=True)
        return eng

    # MODIFIED: 제1헌법 GlobalThrottle 파일락 · PID 격리 임시파일 · 외부 사용자 allowed_root 호환
    def save_json_atomic(
        self, ledger_path: str, allowed_root: Optional[str] = None
    ) -> str:
        from toss_api_core import GlobalThrottle

        safe_target = assert_pipios_only_path(
            ledger_path, allowed_root=allowed_root
        )
        tmp_path = assert_pipios_only_path(
            f"{safe_target}.tmp.{os.getpid()}", allowed_root=allowed_root
        )
        payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        with GlobalThrottle.get_file_lock(safe_target):
            try:
                with open(tmp_path, "w", encoding="utf-8") as wf:
                    wf.write(payload)
                    wf.flush()
                    os.fsync(wf.fileno())
                os.replace(tmp_path, safe_target)
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
        return safe_target


# [CASE114_LEGACY_MIRROR_BRIDGE]
import asyncio
import re as _v6_re
import time
import uuid


def resolve_v6_ledger_path(base_dir_or_ctx: Any = None) -> str:
    raw_d = (
        getattr(base_dir_or_ctx, "base_dir", None)
        if (base_dir_or_ctx is not None and not isinstance(base_dir_or_ctx, str))
        else base_dir_or_ctx
    )
    t_dir = (
        os.path.abspath(str(raw_d).strip())
        if (isinstance(raw_d, str) and str(raw_d).strip())
        else os.path.abspath(os.path.dirname(os.path.abspath(__file__)) or ".")
    )
    raw_name = os.path.basename(os.path.normpath(t_dir)).strip()
    slug = _v6_re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name).strip("._-") or "default_bot"
    return os.path.join(t_dir, f"v6_barbell_ledger_{slug}.json")


DEFAULT_V6_LEDGER_PATH: str = resolve_v6_ledger_path()

V6_MIRROR_SOXL_KEYS: Tuple[str, ...] = (
    "portion_mode",
    "barbell_mode",
    "initial_seed_usd",
    "active_seed_usd",
    "buckets",
    "sub_buckets",
    "total_qty",
    "avg_price",
    "anchor_price",
    "cycle_min_buy_price",
    "cycle_ratchet_max_lots",
    "l1_target_quota_qty",
    "sub_l1_target_quota_qty",
    "free_cash_usd",
    "injected_reserve_usd",
    "used_reserve_portions_cnt",
    "vaulted_profit_locked_usd",
    "vault_realized_profit_usd",
    "v6_consecutive_no_trade_days",
    "v6_prev_t1h_px",
    "v6_sma120_px",
    "v6_t1h_wait_state",
    "v6_last_partial_sell_p",
)


def sync_v6_to_legacy_state_dicts(
    eng: SOXLSniperBarbellV6Engine,
    st_soxl: Dict[str, Any],
    bb_dict: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    # MODIFIED: SoxlStratumLedger 회계 항등식(cyc_loss_adj · sub_buckets=[] · injected_reserve_usd) 및 BarbellLedger 완전 일치화
    st = dict(st_soxl or {})
    bb = dict(bb_dict or {})

    mirrored_buckets: List[Dict[str, Any]] = []
    for idx, slot in enumerate(eng.stack):
        if idx == 0:
            role = "L1"
            label_ko = "본 1층(최저가 공격수)"
        elif idx == 1:
            role = "L2"
            label_ko = "본 2층(보조공격수)"
        else:
            role = f"GRID_L{idx + 1}"
            label_ko = f"본 {idx + 1}층(스윕대기)"

        pure_cost = round(float(slot.q) * float(slot.p), 4)
        mirrored_buckets.append(
            {
                "stratum_id": idx + 1,
                "tier_role": role,
                "lot_type": ("REENTRY_1FL" if idx == 0 else f"GRID_L{idx + 1}"),
                "label": label_ko,
                "qty": int(slot.q),
                "book_price": round(float(slot.p), 4),
                "book_invested_usd": pure_cost,
                "avg_price": round(float(slot.p), 4),
                "actual_cost_usd": pure_cost,
                "lot_count": int(slot.merges) + 1,
                "merges": int(slot.merges),
                "buy_ts": int(slot.buy_ts),
                "is_sub_grid": False,
            }
        )

    tot_q = sum(s.q for s in eng.stack)
    tot_pure_cost = round(sum(float(s.q) * float(s.p) for s in eng.stack), 4)
    w_avg = (tot_pure_cost / float(tot_q)) if tot_q > 0 else 0.0

    eff_b_seed_u = (
        max(eng.user_seed, eng.active_seed)
        if eng.barbell_mode == BARBELL_MODE_COMPOUND
        else eng.user_seed
    )
    core_60_u = round(eff_b_seed_u * V6_BARBELL_CORE_WEIGHT, 4)
    cyc_loss_adj_u = min(
        0.0,
        float(st.get("cycle_realized_net_usd") or 0.0)
        - max(0.0, float(st.get("cycle_vaulted_locked_usd") or 0.0)),
    )
    eff_core_base_u = max(0.0, core_60_u + cyc_loss_adj_u)
    req_inj_u = (
        round(max(0.0, (tot_pure_cost + eng.soxl_cash) - eff_core_base_u), 4)
        if tot_q > 0
        else 0.0
    )
    used_cnt_u = (
        max(1, int(math.ceil((req_inj_u - 1e-9) / max(1.0, eng.tranche_stock))))
        if req_inj_u > 0.01
        else 0
    )

    st["portion_mode"] = eng.barbell_mode
    st["barbell_mode"] = eng.barbell_mode
    st["initial_seed_usd"] = round(eng.user_seed, 2)
    st["active_seed_usd"] = round(eng.active_seed, 2)
    st["buckets"] = mirrored_buckets
    st["sub_buckets"] = []
    st["total_qty"] = int(tot_q)
    st["avg_price"] = round(w_avg, 4)
    st["free_cash_usd"] = round(eng.soxl_cash, 2)
    st["injected_reserve_usd"] = req_inj_u
    st["used_reserve_portions_cnt"] = used_cnt_u
    st["vaulted_profit_locked_usd"] = round(eng.separated_profit_cash, 4)
    st["vault_realized_profit_usd"] = round(eng.separated_profit_cash, 2)
    st["v6_consecutive_no_trade_days"] = int(eng.consecutive_no_trade_days)
    st["v6_prev_t1h_px"] = eng.prev_t1h_px
    st["v6_sma120_px"] = eng.get_current_sma120()
    st["v6_t1h_wait_state"] = eng.t1h_wait_state
    st["v6_last_partial_sell_p"] = eng.last_partial_sell_p
    st["sub_l1_target_quota_qty"] = 0

    if eng.stack:
        l1_p = eng.stack[0].p
        prev_cmin = float(st.get("cycle_min_buy_price") or 0.0)
        held_lots_u = sum(int(s.merges) + 1 for s in eng.stack)
        st["anchor_price"] = round(
            min(l1_p, eng.last_partial_sell_p)
            if eng.last_partial_sell_p is not None
            else l1_p,
            4,
        )
        st["cycle_min_buy_price"] = round(
            min(prev_cmin, l1_p) if prev_cmin > 0.0 else l1_p, 4
        )
        st["cycle_ratchet_max_lots"] = max(
            held_lots_u, int(st.get("cycle_ratchet_max_lots") or 0)
        )
        st["l1_target_quota_qty"] = int(eng.stack[0].q)
    else:
        st["anchor_price"] = 0.0
        st["cycle_min_buy_price"] = 0.0
        st["cycle_ratchet_max_lots"] = 0
        st["l1_target_quota_qty"] = 0

    # MODIFIED [Case 114]:
    # 1) SOXL 보유 중(tot_q > 0) SGOV 매수대기 $0 강제 (Case 102 / v6 0주 졸업 시에만 SGOV 매수)
    # 2) 0주 상태에서도 cash_bucket_usd + pending_sgov_buy_budget_usd == eng.reserve_cash 항등식으로 이중계상 원천 차단
    # 3) 기수혈(cash_injected_to_soxl_usd) 및 격리금고(daily/cycle_vaulted_profit_usd) 잔재 수치 정밀 일치화
    sgov_inv_u = round(float(eng.sgov_shares) * eng.sgov_share_px, 4)
    reserve_pool_u = round(max(0.0, float(eng.reserve_cash)), 4)
    if tot_q <= 0 and eng.pending_sgov_target_usd is not None:
        want_sgov_u = max(0.0, float(eng.pending_sgov_target_usd) - sgov_inv_u)
        if want_sgov_u >= (eng.sgov_share_px * (1.0 + eng.side_fee)):
            pend_sgov_u = round(min(reserve_pool_u, want_sgov_u), 2)
        else:
            pend_sgov_u = 0.0
    else:
        pend_sgov_u = 0.0
    cash_bucket_u = round(max(0.0, reserve_pool_u - pend_sgov_u), 2)
    need_sgov_sell_flag = (
        1
        if (
            tot_q > 0
            and eng.sgov_shares > 0
            and (eng.soxl_cash + eng.reserve_cash + 1e-6 < eng.tranche_req_cash)
        )
        else 0
    )
    sep_vault_u = round(max(0.0, float(eng.separated_profit_cash)), 4)

    bb["is_initialized"] = True
    bb["portion_mode"] = eng.barbell_mode
    bb["initial_seed_usd"] = round(eng.user_seed, 2)
    bb["active_seed_usd"] = round(eng.active_seed, 2)
    bb["soxl_core_cash_usd"] = round(eng.soxl_cash, 2)
    bb["cash_bucket_usd"] = cash_bucket_u
    bb["cash_injected_to_soxl_usd"] = req_inj_u
    bb["external_injected_to_soxl_usd"] = 0.0
    bb["sgov_held_qty"] = int(eng.sgov_shares)
    bb["sgov_shares"] = int(eng.sgov_shares)
    bb["sgov_invested_usd"] = sgov_inv_u
    bb["sgov_avg_price"] = (
        round(eng.sgov_share_px, 4) if eng.sgov_shares > 0 else 0.0
    )
    bb["sgov_last_price"] = round(eng.sgov_share_px, 4)
    bb["sgov_eval_usd"] = round(sgov_inv_u, 2)
    bb["pending_sgov_buy_budget_usd"] = pend_sgov_u
    bb["pending_sgov_rebuy"] = bool(pend_sgov_u > 0.0)
    bb["pending_sgov_tranche_sells"] = need_sgov_sell_flag
    bb["barbell_seed_exhausted"] = bool(
        tot_q > 0
        and (eng.soxl_cash + eng.reserve_cash + 1e-6 < eng.tranche_req_cash)
        and eng.sgov_shares <= 0
    )
    bb["vault_injected_to_soxl_usd"] = 0.0
    bb["vault_realized_profit_usd"] = sep_vault_u
    bb["vault_available_usd"] = sep_vault_u
    bb["separated_profit_cash"] = round(sep_vault_u, 2)
    if sep_vault_u <= 1e-4:
        bb["daily_vaulted_profit_usd"] = 0.0
        bb["cycle_vaulted_profit_usd"] = 0.0
        bb["last_cycle_vaulted_profit_usd"] = 0.0
    else:
        bb["daily_vaulted_profit_usd"] = round(
            min(sep_vault_u, max(0.0, float(bb.get("daily_vaulted_profit_usd") or 0.0))),
            4,
        )
        bb["cycle_vaulted_profit_usd"] = round(
            min(sep_vault_u, max(0.0, float(bb.get("cycle_vaulted_profit_usd") or 0.0))),
            4,
        )
    return st, bb


def load_or_migrate_pipios_v6_engine(
    legacy_st: Optional[Dict[str, Any]] = None,
    legacy_bb: Optional[Dict[str, Any]] = None,
    ledger_path: Optional[str] = None,
    allowed_root: Optional[str] = None,
) -> SOXLSniperBarbellV6Engine:
    eff_lp = ledger_path or resolve_v6_ledger_path(allowed_root)
    safe_lp = assert_pipios_only_path(eff_lp, allowed_root=allowed_root)
    if os.path.isfile(safe_lp):
        with open(safe_lp, "r", encoding="utf-8") as rf:
            d = json.load(rf)
        eng = SOXLSniperBarbellV6Engine.from_dict(d)
        if len(eng.past_rth_closes) < 120:
            eng.bootstrap_market_history(allow_readonly_npz_fallback=True)
        return eng

    eng = SOXLSniperBarbellV6Engine.migrate_from_case113_state(
        legacy_st or {}, legacy_bb or {}
    )
    eng.save_json_atomic(safe_lp, allowed_root=allowed_root)
    return eng


# [C114_SNG_V2]
def get_shared_pipios_v6_engine(context=None, legacy_st=None, legacy_bb=None):
    eng = getattr(context, "_case114_v6_engine", None) if context is not None else None
    if isinstance(eng, SOXLSniperBarbellV6Engine):
        return eng
    ctx_dir = getattr(context, "base_dir", None) if context is not None else None
    dyn_lp = resolve_v6_ledger_path(context)
    eng = load_or_migrate_pipios_v6_engine(
        legacy_st=legacy_st,
        legacy_bb=legacy_bb,
        ledger_path=dyn_lp,
        allowed_root=ctx_dir,
    )
    if context is not None:
        try:
            setattr(context, "_case114_v6_engine", eng)
        except Exception:
            pass
    return eng


# NEW [Case 114]: 브로커 공식 수정주가 일봉(1d) 기반 전 계좌 실측 SMA120 일일 동기화기 ($139.08 왜곡 교정 & 외부 서버 즉시 해금)
async def ensure_v6_sma120_from_broker_1d(
    context: Any,
    eng: Optional[SOXLSniperBarbellV6Engine] = None,
    force: bool = False,
) -> Optional[float]:
    target_eng = eng or get_shared_pipios_v6_engine(context)
    if context is None or not hasattr(context, "api"):
        return target_eng.get_current_sma120()
    today_s = dt.datetime.now(tz=EST_TZ).strftime("%Y-%m-%d")
    if (
        (not force)
        and getattr(context, "_v6_1d_synced_date", "") == today_s
        and len(target_eng.past_rth_closes) >= 120
    ):
        return target_eng.get_current_sma120()

    by_date: Dict[str, float] = {}
    try:
        if hasattr(context.api, "get_candles_1d"):
            c_1d = await context.api.get_candles_1d(
                symbol="SOXL", count=180, adjusted=True
            )
            for row in c_1d or []:
                if not isinstance(row, dict):
                    continue
                ds = str(
                    row.get("timestamp") or row.get("date") or row.get("dt") or ""
                ).strip()[:10]
                cp = float(row.get("closePrice") or row.get("close") or 0.0)
                if len(ds) == 10 and ds < today_s and cp > 0.0:
                    by_date[ds] = cp

        if len(by_date) < 120 and hasattr(context.api, "get_candles"):
            before_cur: Optional[str] = None
            for _ in range(3):
                batch, next_b = await context.api.get_candles(
                    symbol="SOXL",
                    interval="1d",
                    count=100,
                    before=before_cur,
                    adjusted=True,
                )
                if not batch:
                    break
                for row in batch:
                    if not isinstance(row, dict):
                        continue
                    ds = str(
                        row.get("timestamp")
                        or row.get("date")
                        or row.get("dt")
                        or ""
                    ).strip()[:10]
                    cp = float(row.get("closePrice") or row.get("close") or 0.0)
                    if len(ds) == 10 and ds < today_s and cp > 0.0:
                        by_date[ds] = cp
                if len(by_date) >= 135 or (not next_b) or next_b == before_cur:
                    break
                before_cur = next_b
    except Exception:
        return target_eng.get_current_sma120()

    if len(by_date) >= 120:
        sorted_ds = sorted(by_date.keys())
        clean_closes = [round(by_date[d], 4) for d in sorted_ds[-260:]]
        prev_sma = target_eng.get_current_sma120()
        target_eng.past_rth_closes = clean_closes
        last_c = clean_closes[-1]
        if target_eng.prev_t1h_px is None or (
            last_c > 0.0
            and (
                target_eng.prev_t1h_px > last_c * 2.2
                or target_eng.prev_t1h_px < last_c * 0.3
            )
        ):
            target_eng.prev_t1h_px = last_c
        setattr(context, "_v6_1d_synced_date", today_s)
        new_sma = target_eng.get_current_sma120()
        if prev_sma is None or (new_sma is not None and abs(prev_sma - new_sma) > 0.05):
            ctx_dir = getattr(context, "base_dir", None)
            try:
                await asyncio.to_thread(
                    target_eng.save_json_atomic,
                    resolve_v6_ledger_path(context),
                    ctx_dir,
                )
            except Exception:
                pass
    return target_eng.get_current_sma120()


# NEW: v6 원장 저장 + SoxlStratumLedger + BarbellLedger 3중 원자적 일괄 미러링 헬퍼
async def apply_v6_mirror_to_legacy_ledgers(
    context: Any,
    eng: SOXLSniperBarbellV6Engine,
    extra_soxl_kw: Optional[Dict[str, Any]] = None,
    extra_bb_kw: Optional[Dict[str, Any]] = None,
    save_v6_disk: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    ctx_dir = getattr(context, "base_dir", None) if context is not None else None
    if save_v6_disk:
        dyn_lp = resolve_v6_ledger_path(context)
        await asyncio.to_thread(eng.save_json_atomic, dyn_lp, ctx_dir)

    st_cur = context.ledger.get_state("SOXL")
    bb_ledger = getattr(context, "barbell_ledger", None)
    bb_cur = (
        bb_ledger.get_state()
        if (bb_ledger is not None and hasattr(bb_ledger, "get_state"))
        else {}
    )
    if extra_soxl_kw:
        st_cur = dict(st_cur)
        st_cur.update(extra_soxl_kw)

    st_sync, bb_sync = sync_v6_to_legacy_state_dicts(eng, st_cur, bb_cur)
    soxl_upd = {k: st_sync[k] for k in V6_MIRROR_SOXL_KEYS if k in st_sync}
    if extra_soxl_kw:
        soxl_upd.update(extra_soxl_kw)
        for k_re in (
            "free_cash_usd",
            "injected_reserve_usd",
            "used_reserve_portions_cnt",
        ):
            if k_re not in extra_soxl_kw and k_re in st_sync:
                soxl_upd[k_re] = st_sync[k_re]

    updated_st = await context.ledger.update_state("SOXL", **soxl_upd)
    if extra_bb_kw:
        bb_sync.update(extra_bb_kw)
    updated_bb = bb_sync
    if bb_ledger is not None and hasattr(bb_ledger, "update_state"):
        updated_bb = await bb_ledger.update_state(**bb_sync)
    return updated_st, updated_bb


# NEW: /sync · 부팅 화해 · 수동 매매 감지 시 레거시 원장 ➔ v6 엔진(eng.stack) 역동기화 브릿지
async def sync_v6_engine_from_reconciled_ledgers(
    context: Any,
    holdings_map: Optional[Dict[str, Any]] = None,
    broker_bp_usd: Optional[float] = None,
) -> SOXLSniperBarbellV6Engine:
    st_soxl = context.ledger.get_state("SOXL")
    bb_ledger = getattr(context, "barbell_ledger", None)
    bb_cur = (
        bb_ledger.get_state()
        if (bb_ledger is not None and hasattr(bb_ledger, "get_state"))
        else {}
    )
    eng = get_shared_pipios_v6_engine(
        context, legacy_st=st_soxl, legacy_bb=bb_cur
    )

    pend = st_soxl.get("v6_pending_order")
    if isinstance(pend, dict) and str(pend.get("order_id") or "").strip():
        return eng

    req_mode = str(st_soxl.get("portion_mode") or "").upper().strip()
    if req_mode in VALID_BARBELL_MODES:
        eng.barbell_mode = req_mode

    st_seed = float(st_soxl.get("initial_seed_usd") or 0.0)
    if st_seed >= 100.0:
        eng.user_seed = st_seed

    rt_pct = float(st_soxl.get("round_trip_fee_rate_pct") or 0.0)
    if rt_pct > 0.0:
        eng.roundtrip_fee = rt_pct / 100.0
        eng.side_fee = eng.roundtrip_fee / 2.0

    # 기존 eng.stack 슬롯 중 (수량, 단가) 일치 항목은 원가(c)와 buy_ts 보존
    old_pool: List[LayerSlot] = list(eng.stack)
    raw_buckets = list(st_soxl.get("buckets") or []) + list(
        st_soxl.get("sub_buckets") or []
    )
    new_slots: List[LayerSlot] = []
    for b in raw_buckets:
        if not isinstance(b, dict):
            continue
        q_v = int(float(b.get("qty") or b.get("q") or 0))
        p_v = float(
            b.get("book_price")
            or b.get("avg_price")
            or b.get("buy_price")
            or b.get("p")
            or 0.0
        )
        if q_v < 1 or p_v <= 0.0:
            continue
        matched_idx = -1
        for idx_o, o_slot in enumerate(old_pool):
            if o_slot.q == q_v and abs(o_slot.p - p_v) < 1e-3:
                matched_idx = idx_o
                break
        if matched_idx >= 0:
            kept = old_pool.pop(matched_idx)
            new_slots.append(kept)
        else:
            lots = max(1, int(float(b.get("lot_count") or 1)))
            new_slots.append(
                LayerSlot(
                    p=round(p_v, 4),
                    q=q_v,
                    c=round(float(q_v) * p_v * (1.0 + eng.side_fee), 4),
                    merges=max(0, lots - 1),
                    buy_ts=int(float(b.get("buy_ts") or 0)),
                )
            )

    new_slots.sort(key=lambda s: s.p)
    while len(new_slots) > 7:
        old_l1 = new_slots[0]
        old_l2 = new_slots[1]
        old_mid = new_slots[2:-1]
        old_last = new_slots[-1]
        mq = old_l2.q + old_last.q
        mc = old_l2.c + old_last.c
        mp = (old_l2.p * old_l2.q + old_last.p * old_last.q) / float(mq)
        merged = LayerSlot(
            p=mp,
            q=mq,
            c=mc,
            merges=old_l2.merges + old_last.merges + 1,
            buy_ts=min(old_l2.buy_ts, old_last.buy_ts),
        )
        new_slots = [old_l1] + sorted(old_mid + [merged], key=lambda s: s.p)
    eng.stack = new_slots

    eng.separated_profit_cash = round(
        max(0.0, float(st_soxl.get("vaulted_profit_locked_usd") or 0.0)), 4
    )

    sgov_q = int(
        float(bb_cur.get("sgov_held_qty") or bb_cur.get("sgov_shares") or eng.sgov_shares)
    )
    sgov_lp = float(bb_cur.get("sgov_last_price") or eng.sgov_share_px)
    if isinstance(holdings_map, dict) and isinstance(holdings_map.get("SGOV"), dict):
        sg_h = holdings_map["SGOV"]
        sgov_q = max(0, int(float(sg_h.get("qty", sg_h.get("quantity", sgov_q)) or 0)))
        h_sg_lp = float(sg_h.get("last_price") or 0.0)
        if h_sg_lp > 1.0:
            sgov_lp = h_sg_lp

    if sgov_lp > 1.0:
        eng.sgov_share_px = sgov_lp
    eng.sgov_shares = max(0, sgov_q)
    eng.sgov_val = float(eng.sgov_shares) * eng.sgov_share_px

    if len(eng.stack) == 0:
        eng.last_partial_sell_p = None
        eng.cycle_realized_pnl_usd = 0.0
        if eng.is_simple_mode:
            eng.active_seed = eng.user_seed
        else:
            eng.active_seed = max(
                eng.user_seed,
                float(st_soxl.get("active_seed_usd") or eng.active_seed),
            )
    else:
        eng.pending_sgov_target_usd = None
        if eng.is_simple_mode:
            eng.active_seed = eng.user_seed
        else:
            eng.active_seed = max(eng.user_seed, eng.active_seed)

    eng.tranche_stock = eng.active_seed * V6_SEED_RATIO
    eng.tranche_req_cash = eng.tranche_stock * (1.0 + eng.roundtrip_fee)

    if broker_bp_usd is not None and (
        float(broker_bp_usd) > 0.0 or isinstance(holdings_map, dict)
    ):
        eng.sync_with_broker_snapshot(
            max(0.0, float(broker_bp_usd)), eng.sgov_shares, eng.sgov_share_px
        )
    else:
        tot_pure_c = sum(float(s.q) * float(s.p) for s in eng.stack)
        core_cap = max(0.0, V6_BARBELL_CORE_WEIGHT * eng.active_seed - tot_pure_c)
        eng.soxl_cash = core_cap
        if len(eng.stack) == 0:
            eng.reserve_cash = max(
                0.0, eng.active_seed - eng.soxl_cash - eng.sgov_val
            )

    await ensure_v6_sma120_from_broker_1d(context, eng)
    await apply_v6_mirror_to_legacy_ledgers(context, eng, save_v6_disk=True)
    return eng


# NEW: /seed 변경 시 v6 엔진 기준시드·운용시드·타격액 즉시 동기화기
async def sync_v6_on_seed_change(
    context: Any, new_seed_usd: float
) -> SOXLSniperBarbellV6Engine:
    st_soxl = context.ledger.get_state("SOXL")
    bb_ledger = getattr(context, "barbell_ledger", None)
    bb_cur = (
        bb_ledger.get_state()
        if (bb_ledger is not None and hasattr(bb_ledger, "get_state"))
        else {}
    )
    eng = get_shared_pipios_v6_engine(
        context, legacy_st=st_soxl, legacy_bb=bb_cur
    )
    eng.update_user_seed(max(100.0, float(new_seed_usd)), can_trade_sgov_now=False)
    await apply_v6_mirror_to_legacy_ledgers(context, eng, save_v6_disk=True)
    return eng


# NEW: /reset_profit 실행 시 v6 분리 수익금고 및 누적 카운터 0점 초기화기
async def reset_v6_profit_vault(context: Any) -> SOXLSniperBarbellV6Engine:
    st_soxl = context.ledger.get_state("SOXL")
    bb_ledger = getattr(context, "barbell_ledger", None)
    bb_cur = (
        bb_ledger.get_state()
        if (bb_ledger is not None and hasattr(bb_ledger, "get_state"))
        else {}
    )
    eng = get_shared_pipios_v6_engine(
        context, legacy_st=st_soxl, legacy_bb=bb_cur
    )
    eng.separated_profit_cash = 0.0
    eng.cycle_realized_pnl_usd = 0.0
    eng.vault_shortfall_warning_usd = 0.0
    eng.completed_cycles = 0
    eng.total_buys = 0
    eng.total_sells = 0
    eng.total_merges = 0
    eng.vacuum_buys = 0
    eng.depletion_blocks = 0
    await apply_v6_mirror_to_legacy_ledgers(context, eng, save_v6_disk=True)
    return eng


# [CASE114_LIVE_BROKER_TICK_EXECUTOR]
def _gen_c114_cid(prefix: str = "V6B") -> str:
    return f"{prefix}{uuid.uuid4().hex[:24]}"[:32]


def _extract_order_fill_info(det: Dict[str, Any]) -> Tuple[str, int, float]:
    if not isinstance(det, dict):
        return "UNKNOWN", 0, 0.0
    status = str(det.get("status") or det.get("orderStatus") or "").upper().strip()
    ex = det.get("execution") if isinstance(det.get("execution"), dict) else {}
    filled_q = int(
        float(
            ex.get("filledQuantity")
            or det.get("filledQuantity")
            or ex.get("executedQuantity")
            or det.get("executedQuantity")
            or 0
        )
    )
    avg_p = float(
        ex.get("averageFilledPrice")
        or det.get("averageFilledPrice")
        or det.get("avgFilledPrice")
        or det.get("price")
        or 0.0
    )
    return status, filled_q, avg_p


async def _fetch_live_px_bypass_shm(
    api: Any, sym: str, fallback_px: float
) -> float:
    try:
        if hasattr(api, "get_current_price"):
            p = await api.get_current_price(sym, bypass_shm_cache=True)
            if p and float(p) > 0.0:
                return float(p)
    except TypeError:
        try:
            p = await api.get_current_price(sym)
            if p and float(p) > 0.0:
                return float(p)
        except Exception:
            pass
    except Exception:
        pass
    return float(fallback_px)


# MODIFIED [Case 114]: 토스 1분봉(openPrice~closePrice) 및 진행봉 자동 배제 $0.01 센트격자 하이킨아시 직결 연산기
def _extract_closed_1m_ha_flags(
    metrics: Dict[str, Any],
    candles_raw: Any = None,
    now_est: Optional[dt.datetime] = None,
) -> Tuple[bool, bool, int]:
    if isinstance(candles_raw, (list, tuple)) and len(candles_raw) >= 5:
        cur_dt = now_est.astimezone(EST_TZ) if now_est else dt.datetime.now(tz=EST_TZ)
        cur_mk = cur_dt.strftime("%Y-%m-%d %H:%M")
        parsed_rows: List[Tuple[str, int, float, float, float, float]] = []
        for row in candles_raw[-300:]:
            if isinstance(row, dict):
                o_v = float(
                    row.get("openPrice")
                    or row.get("open")
                    or row.get("o")
                    or 0.0
                )
                h_v = float(
                    row.get("highPrice")
                    or row.get("high")
                    or row.get("h")
                    or 0.0
                )
                l_v = float(
                    row.get("lowPrice")
                    or row.get("low")
                    or row.get("l")
                    or 0.0
                )
                c_v = float(
                    row.get("closePrice")
                    or row.get("close")
                    or row.get("c")
                    or 0.0
                )
                ts_raw = (
                    row.get("timestamp")
                    or row.get("dt")
                    or row.get("dateTime")
                    or row.get("time")
                    or row.get("ts")
                    or row.get("epoch_sec")
                )
                mk_s = ""
                ep_s = 0
                if isinstance(ts_raw, (int, float)):
                    ep_s = int(ts_raw // 1000) if ts_raw > 1e12 else int(ts_raw)
                    if ep_s > 0:
                        mk_s = dt.datetime.fromtimestamp(ep_s, tz=EST_TZ).strftime(
                            "%Y-%m-%d %H:%M"
                        )
                elif isinstance(ts_raw, str) and ts_raw.strip():
                    s_c = ts_raw.strip()
                    try:
                        d_p = dt.datetime.fromisoformat(
                            s_c.replace("Z", "+00:00")
                        ).astimezone(EST_TZ)
                        mk_s = d_p.strftime("%Y-%m-%d %H:%M")
                        ep_s = int(d_p.timestamp())
                    except Exception:
                        mk_s = s_c[:16]
            elif isinstance(row, (list, tuple)) and len(row) >= 5:
                ep_s = int(float(row[0]))
                mk_s = (
                    dt.datetime.fromtimestamp(ep_s, tz=EST_TZ).strftime(
                        "%Y-%m-%d %H:%M"
                    )
                    if ep_s > 0
                    else ""
                )
                o_v, h_v, l_v, c_v = (
                    float(row[1]),
                    float(row[2]),
                    float(row[3]),
                    float(row[4]),
                )
            else:
                continue
            if o_v > 0.0 and h_v > 0.0 and l_v > 0.0 and c_v > 0.0:
                parsed_rows.append((mk_s, ep_s, o_v, h_v, l_v, c_v))

        if len(parsed_rows) >= 2:
            if all(r[0] for r in parsed_rows):
                parsed_rows.sort(key=lambda r: r[0])
                last_mk = parsed_rows[-1][0]
                bound_mk = last_mk if last_mk > cur_mk else cur_mk
                closed_rows = [r for r in parsed_rows if r[0] < bound_mk]
                if not closed_rows:
                    closed_rows = parsed_rows[:-1]
            else:
                closed_rows = parsed_rows[:-1]
            if closed_rows:
                bars = [(r[2], r[3], r[4], r[5]) for r in closed_rows[-240:]]
                last_ts = closed_rows[-1][1]
                sbear, sbull, _, _ = compute_cent_grid_heikin_ashi_flags(bars)
                return sbear, sbull, last_ts

    m = metrics if isinstance(metrics, dict) else {}
    sbear = bool(m.get("closed_ha_shaved_bear", False))
    sbull = bool(m.get("closed_ha_shaved_bull", False))
    mk = int(float(m.get("closed_minute_key", m.get("last_closed_ts", 0)) or 0))
    return sbear, sbull, mk


_TERMINAL_ORDER_STATUSES: Tuple[str, ...] = (
    "FILLED",
    "COMPLETED",
    "CLOSED",
    "CANCELED",
    "CANCELLED",
    "REJECTED",
    "REPLACED",
    "EXPIRED",
)


async def execute_case114_v6_barbell_tick(
    context: Any,
    live_p: float,
    now_est: dt.datetime,
    logger: Any = None,
) -> None:
    st_cur = context.ledger.get_state("SOXL")
    bb_ledger = getattr(context, "barbell_ledger", None)
    bb_cur = (
        bb_ledger.get_state()
        if (bb_ledger is not None and hasattr(bb_ledger, "get_state"))
        else {}
    )

    eng = get_shared_pipios_v6_engine(context, legacy_st=st_cur, legacy_bb=bb_cur)
    ctx_dir = getattr(context, "base_dir", None)
    await ensure_v6_sma120_from_broker_1d(context, eng)

    sm = str(st_cur.get("portion_mode") or "").upper().strip()
    if sm in VALID_BARBELL_MODES and sm != eng.barbell_mode:
        eng.set_barbell_mode(sm, can_trade_sgov_now=False)
        await asyncio.to_thread(
            eng.save_json_atomic, resolve_v6_ledger_path(context), ctx_dir
        )

    st_seed = float(st_cur.get("initial_seed_usd") or 0.0)
    if st_seed >= 100.0 and abs(st_seed - eng.user_seed) > 1.0:
        eng.update_user_seed(st_seed, can_trade_sgov_now=False)
    rt_pct = float(st_cur.get("round_trip_fee_rate_pct") or 0.0)
    if rt_pct > 0.0:
        eng.update_roundtrip_fee(rt_pct / 100.0)

    win = get_session_windows_est(now_est)
    ymd = int(win["date_ymd"])
    hm = int(win["hm"])
    can_sgov = bool(win["is_sgov_window"])
    now_ts = int(now_est.timestamp())
    cur_min_epoch = (now_ts // 60) * 60
    now_mono = time.monotonic()

    # 1) 미결 주문(v6_pending_order) 선행 정산 (IN_FLIGHT 보호 + PnL/주문ID/알림/암살자 인계 완결)
    pend = st_cur.get("v6_pending_order")
    if isinstance(pend, dict) and str(pend.get("order_id") or "").strip():
        oid = str(pend["order_id"]).strip()
        p_sym = str(pend.get("symbol") or "SOXL").upper()
        p_side = str(pend.get("side") or "BUY").upper()
        p_mono = float(pend.get("submitted_mono") or 0.0)
        try:
            det = await context.api.get_order_detail(oid)
            status, filled_q, avg_px = _extract_order_fill_info(det)
            is_terminal = status in _TERMINAL_ORDER_STATUSES

            if (not is_terminal) and p_mono > 0.0 and (now_mono - p_mono) >= 25.0:
                try:
                    await context.api.cancel_order(oid)
                except Exception:
                    pass
                det = await context.api.get_order_detail(oid)
                status, filled_q, avg_px = _extract_order_fill_info(det)
                if status not in _TERMINAL_ORDER_STATUSES:
                    await asyncio.sleep(0.35)
                    det = await context.api.get_order_detail(oid)
                    status, filled_q, avg_px = _extract_order_fill_info(det)
                is_terminal = bool(
                    status in _TERMINAL_ORDER_STATUSES
                    or (now_mono - p_mono) >= 55.0
                )

            if not is_terminal:
                return

            fill_px = (
                avg_px
                if avg_px > 0.0
                else float(pend.get("limit_price") or live_p)
            )
            extra_soxl: Dict[str, Any] = {
                "v6_pending_order": None,
                "buy_order_id": "",
                "sell_order_id": "",
                "ordered_qty": 0,
            }
            extra_bb: Dict[str, Any] = {}
            alert_title = ""
            alert_body = ""
            graduated_zero_now = False

            if filled_q >= 1 and fill_px > 0.0:
                context._v6_last_fill_mono = time.monotonic()
                if p_sym == "SGOV":
                    signed_sh = filled_q if p_side == "BUY" else (-filled_q)
                    eng.apply_sgov_fill(signed_sh, fill_px)
                    sg_oids = list(bb_cur.get("last_settled_sgov_order_ids") or [])
                    if oid not in sg_oids:
                        sg_oids.append(oid)
                    extra_bb["last_settled_sgov_order_ids"] = sg_oids[-50:]

                    # NEW [Case 114]: 온디맨드 SGOV 매도 체결 완료 직후 후속 SOXL 매수 체인 즉시 발주
                    chained_b = pend.get("chained_soxl_buy")
                    if p_side == "SELL" and isinstance(chained_b, dict):
                        px_cb = await _fetch_live_px_bypass_shm(
                            context.api, "SOXL", live_p
                        )
                        c_ref = float(chained_b.get("ref_px") or px_cb)
                        c_vac = bool(chained_b.get("is_vac", False))
                        cb_q, _ = eng.plan_buy_order_qty(
                            c_ref, px_cb, can_trade_sgov_now=False
                        )
                        if cb_q < 1 and px_cb > 0.0:
                            avail_cb = eng.soxl_cash + eng.reserve_cash
                            unit_cb = px_cb * (1.0 + eng.roundtrip_fee)
                            if avail_cb >= unit_cb:
                                cb_q = min(
                                    max(1, int(eng.tranche_stock // max(0.01, c_ref))),
                                    int(avail_cb // unit_cb),
                                )
                        if cb_q >= 1 and px_cb > 0.0:
                            lim_cb = round(px_cb * 1.0030, 2)
                            max_lim_cb = round(
                                math.floor((eng.tranche_stock / float(cb_q)) * 100.0)
                                / 100.0,
                                2,
                            )
                            if max_lim_cb > 0.0:
                                lim_cb = min(lim_cb, max_lim_cb)
                            cid_cb = _gen_c114_cid("V6CHNB")
                            try:
                                ord_cb = await context.api.create_order(
                                    symbol="SOXL",
                                    side="BUY",
                                    quantity=cb_q,
                                    price=lim_cb,
                                    order_type="LIMIT",
                                    time_in_force="DAY",
                                    client_order_id=cid_cb,
                                    enforce_daymarket_block=False,
                                )
                                oid_cb = str(ord_cb.get("orderId") or "").strip()
                                if oid_cb:
                                    extra_soxl["buy_order_id"] = oid_cb
                                    extra_soxl["v6_pending_order"] = {
                                        "order_id": oid_cb,
                                        "symbol": "SOXL",
                                        "side": "BUY",
                                        "qty": cb_q,
                                        "limit_price": lim_cb,
                                        "is_vac": c_vac,
                                        "from_t1h": True,
                                        "submitted_mono": time.monotonic(),
                                    }
                            except Exception as cb_e:
                                if logger:
                                    logger.warning(
                                        "⚠️ [Case 114 SGOV 체결 후 SOXL 체인매수 재시도 예약]: %s",
                                        cb_e,
                                    )
                                if win["is_t1h_window"]:
                                    eng.t1h_wait_state = "NONE"
                elif p_sym == "SOXL":
                    settled_oids = list(st_cur.get("last_settled_order_ids") or [])
                    if oid not in settled_oids:
                        settled_oids.append(oid)
                    extra_soxl["last_settled_order_ids"] = settled_oids[-50:]
                    now_epoch = time.time()

                    if p_side == "BUY":
                        is_vac_b = bool(pend.get("is_vac", False))
                        eng.commit_buy_fill(
                            filled_q,
                            fill_px,
                            exec_ts=cur_min_epoch,
                            is_vac=is_vac_b,
                        )
                        extra_soxl.update(
                            {
                                "total_buy_events": int(st_cur.get("total_buy_events") or 0) + 1,
                                "total_buy_shares": int(st_cur.get("total_buy_shares") or 0) + filled_q,
                                "daily_buy_events": int(st_cur.get("daily_buy_events") or 0) + 1,
                                "daily_main_buy_cnt": int(st_cur.get("daily_main_buy_cnt") or 0) + 1,
                                "main_consec_frozen_days": 0,
                                "entry_ts": now_epoch,
                                "last_buy_fill_ts": now_epoch,
                            }
                        )
                        vac_tag = " · ⚡SMA120진공탈출" if is_vac_b else ""
                        alert_title = f"🔵 [SOXL v6 바벨 매수 체결 ({len(eng.stack)}/7층{vac_tag})] {filled_q}주 @ ${fill_px:.2f}"
                        alert_body = (
                            f"코어현금 ${eng.soxl_cash:,.2f} · 대기현금 ${eng.reserve_cash:,.2f} · "
                            f"보유 총 {sum(s.q for s in eng.stack)}주"
                        )
                    else:
                        prev_vault = eng.separated_profit_cash
                        sell_res = eng.commit_broker_sell_fill(
                            filled_q,
                            fill_px,
                            can_trade_sgov_now=False,
                        )
                        sold_q_eff = int(sell_res["sold_qty"])
                        net_pnl_d = float(sell_res["net_pnl_usd"])
                        gross_pnl_d = float(sell_res["gross_pnl_usd"])
                        fee_d = float(sell_res["fee_usd"])
                        graduated_zero_now = bool(sell_res["graduated_zero"])
                        cyc_final_d = float(sell_res["cycle_final_net_usd"])
                        vault_added = max(0.0, eng.separated_profit_cash - prev_vault)

                        prev_cyc_net = float(st_cur.get("cycle_realized_net_usd") or 0.0)
                        prev_cyc_ev = int(st_cur.get("cycle_sell_events") or 0)
                        extra_soxl.update(
                            {
                                "total_sell_events": int(st_cur.get("total_sell_events") or 0) + 1,
                                "total_sold_shares": int(st_cur.get("total_sold_shares") or 0) + sold_q_eff,
                                "win_sell_events": int(st_cur.get("win_sell_events") or 0) + (1 if net_pnl_d > 0.0 else 0),
                                "daily_sell_events": int(st_cur.get("daily_sell_events") or 0) + 1,
                                "daily_main_sell_cnt": int(st_cur.get("daily_main_sell_cnt") or 0) + 1,
                                "cumulative_realized_gross_usd": round(float(st_cur.get("cumulative_realized_gross_usd") or 0.0) + gross_pnl_d, 4),
                                "cumulative_realized_fee_usd": round(float(st_cur.get("cumulative_realized_fee_usd") or 0.0) + fee_d, 4),
                                "cumulative_realized_net_usd": round(float(st_cur.get("cumulative_realized_net_usd") or 0.0) + net_pnl_d, 4),
                                "daily_realized_net_usd": round(float(st_cur.get("daily_realized_net_usd") or 0.0) + net_pnl_d, 4),
                                "last_sell_fill_ts": now_epoch,
                            }
                        )
                        if graduated_zero_now:
                            extra_soxl.update(
                                {
                                    "main_consec_frozen_days": 0,
                                    "cycle_realized_gross_usd": 0.0,
                                    "cycle_realized_fee_usd": 0.0,
                                    "cycle_realized_net_usd": 0.0,
                                    "cycle_sell_events": 0,
                                    "cycle_vaulted_locked_usd": 0.0,
                                    "last_cycle_realized_net_usd": round(cyc_final_d, 4),
                                    "last_cycle_sell_events": prev_cyc_ev + 1,
                                    "completed_main_cycles": int(st_cur.get("completed_main_cycles") or 0) + 1,
                                    "last_cycle_end_ts": now_epoch,
                                }
                            )
                            extra_bb.update(
                                {
                                    "daily_vaulted_profit_usd": round(float(bb_cur.get("daily_vaulted_profit_usd") or 0.0) + vault_added, 4),
                                    "cycle_vaulted_profit_usd": 0.0,
                                    "last_cycle_vaulted_profit_usd": round(max(0.0, cyc_final_d), 4),
                                    "completed_barbell_cycles": int(bb_cur.get("completed_barbell_cycles") or 0) + 1,
                                }
                            )
                        else:
                            extra_soxl.update(
                                {
                                    "cycle_realized_gross_usd": round(float(st_cur.get("cycle_realized_gross_usd") or 0.0) + gross_pnl_d, 4),
                                    "cycle_realized_fee_usd": round(float(st_cur.get("cycle_realized_fee_usd") or 0.0) + fee_d, 4),
                                    "cycle_realized_net_usd": round(prev_cyc_net + net_pnl_d, 4),
                                    "cycle_sell_events": prev_cyc_ev + 1,
                                }
                            )
                        p_sign = "+" if net_pnl_d >= 0.0 else "-"
                        grad_tag = " · 🎓0주 전량졸업!" if graduated_zero_now else f" · 잔여 {len(eng.stack)}개층"
                        alert_title = f"🔴 [SOXL v6 바벨 스윕 익절 체결] {sold_q_eff}주 @ ${fill_px:.2f}"
                        alert_body = (
                            f"세후순익 {p_sign}${abs(net_pnl_d):,.2f}{grad_tag} · "
                            f"분리금고 ${eng.separated_profit_cash:,.2f} · 운용시드 ${eng.active_seed:,.2f}"
                        )

            if (
                filled_q <= 0
                and p_sym == "SGOV"
                and p_side == "SELL"
                and isinstance(pend.get("chained_soxl_buy"), dict)
                and win["is_t1h_window"]
            ):
                retry_key = f"_v6_t1h_retry_{ymd}"
                r_cnt = int(getattr(context, retry_key, 0) or 0)
                if r_cnt < 2:
                    setattr(context, retry_key, r_cnt + 1)
                    eng.t1h_wait_state = "NONE"

            await apply_v6_mirror_to_legacy_ledgers(
                context,
                eng,
                extra_soxl_kw=extra_soxl,
                extra_bb_kw=extra_bb,
                save_v6_disk=True,
            )
            if graduated_zero_now:
                try:
                    from assassin_plugin import activate_live_assassin_on_zero_soxl_if_armed

                    await activate_live_assassin_on_zero_soxl_if_armed(context)
                except Exception:
                    pass
            if alert_title and hasattr(context, "send_slim_alert"):
                try:
                    await context.send_slim_alert(title=alert_title, body=alert_body)
                except Exception:
                    pass
            return
        except Exception as ord_e:
            if logger:
                logger.warning("⚠️ [Case 114 미결주문 조회 지연]: %s", ord_e)
            return

    # 2) 브로커 실잔고 대사 · 수동매매 자가화해 및 30초 주기 예수금 안전 동기화
    holdings = getattr(context, "latest_holdings", None)
    last_fill_m = float(getattr(context, "_v6_last_fill_mono", 0.0) or 0.0)
    in_fill_grace = bool(last_fill_m > 0.0 and 0.0 <= (now_mono - last_fill_m) < 15.0)

    if isinstance(holdings, dict) and getattr(context, "holdings_fetch_ok", False):
        soxl_h = holdings.get("SOXL") or {}
        sgov_h = holdings.get("SGOV") or {}
        broker_soxl_q = int(float(soxl_h.get("qty", soxl_h.get("quantity", 0)) or 0))
        broker_sgov_q = int(float(sgov_h.get("qty", sgov_h.get("quantity", 0)) or 0))
        sgov_lp = float(sgov_h.get("last_price") or eng.sgov_share_px)

        ledger_soxl_q = sum(s.q for s in eng.stack)
        if ledger_soxl_q != broker_soxl_q:
            if in_fill_grace:
                return
            last_autorec_m = float(getattr(context, "_v6_last_autorec_mono", 0.0) or 0.0)
            if (now_mono - last_autorec_m) >= 15.0:
                context._v6_last_autorec_mono = now_mono
                try:
                    from defense_plugin import reconcile_stratum_with_broker_holdings_plugin

                    eff_lp_rec = live_p if live_p > 0.0 else float(soxl_h.get("last_price") or 0.0)
                    await reconcile_stratum_with_broker_holdings_plugin(
                        context=context,
                        holdings=holdings,
                        prices={"SOXL": eff_lp_rec},
                        now_est=now_est,
                        force_sync=False,
                    )
                    bp_rec = None
                    if hasattr(context.api, "get_buying_power_usd"):
                        raw_bp_r = float(await context.api.get_buying_power_usd(safety_buffer_pct=0.0) or 0.0)
                        if raw_bp_r > 0.0:
                            bp_rec = raw_bp_r
                    eng = await sync_v6_engine_from_reconciled_ledgers(
                        context, holdings_map=holdings, broker_bp_usd=bp_rec
                    )
                    st_cur = context.ledger.get_state("SOXL")
                except Exception as rec_e:
                    if logger:
                        logger.warning("⚠️ [Case 114 수동잔고 자가화해 유예]: %s", rec_e)

            if sum(s.q for s in eng.stack) != broker_soxl_q:
                last_mm_log = float(getattr(context, "_v6_last_mm_log_mono", 0.0) or 0.0)
                if logger and (now_mono - last_mm_log) >= 60.0:
                    context._v6_last_mm_log_mono = now_mono
                    logger.error(
                        "🚨 [Case 114 RECONCILE_MISMATCH 오발주 차단] 내부원장=%d주 != 브로커=%d주 (미체결 수동주문 종료 또는 /sync 대기)",
                        sum(s.q for s in eng.stack),
                        broker_soxl_q,
                    )
                return

        last_bp_m = float(getattr(context, "_v6_last_bp_sync_mono", 0.0) or 0.0)
        if (not in_fill_grace) and (now_mono - last_bp_m) >= 30.0:
            context._v6_last_bp_sync_mono = now_mono
            try:
                if hasattr(context.api, "get_buying_power_usd"):
                    usd_avail = float(
                        await context.api.get_buying_power_usd(safety_buffer_pct=0.0) or 0.0
                    )
                    prev_tot_cash = eng.soxl_cash + eng.reserve_cash + eng.separated_profit_cash
                    if usd_avail > 0.0 or prev_tot_cash <= 1.0:
                        eng.sync_with_broker_snapshot(usd_avail, broker_sgov_q, sgov_lp)
            except Exception:
                pass

    # 3) EOD(16:00 / 조기폐장 13:00 EST) 일일 마감 기록 (전면 휴장일 무매매일·SMA120 오염 차단)
    if (
        (not win.get("is_holiday_closed", False))
        and win["weekday"] < 5
        and hm >= (int(win["rth_end_hm"]) + 1)
        and eng.last_eod_ymd != ymd
    ):
        if live_p > 0.0:
            eng.finalize_rth_end_of_day(ymd, live_p)
            await asyncio.to_thread(
                eng.save_json_atomic, resolve_v6_ledger_path(context), ctx_dir
            )

    # 4) 정규장(09:31 ~ 15:55 EST) 0주 상태 SGOV 목표 비중(30%) 자동 매수/리밸런싱
    if can_sgov and len(eng.stack) == 0:
        if eng.pending_sgov_target_usd is None:
            want_30_sh = int((V6_BARBELL_SGOV_WEIGHT * eng.active_seed) // eng.sgov_share_px)
            if eng.sgov_shares < want_30_sh and (eng.soxl_cash + eng.reserve_cash) > (
                V6_BARBELL_CORE_WEIGHT * eng.active_seed + eng.sgov_share_px * 1.01
            ):
                eng.pending_sgov_target_usd = V6_BARBELL_SGOV_WEIGHT * eng.active_seed

        if eng.pending_sgov_target_usd is not None:
            delta_sgov = eng.compute_pending_sgov_rebalance_delta_shares()
            if delta_sgov == 0:
                eng.pending_sgov_target_usd = None
                await asyncio.to_thread(
                    eng.save_json_atomic, resolve_v6_ledger_path(context), ctx_dir
                )
            else:
                sgov_px_now = await _fetch_live_px_bypass_shm(
                    context.api, "SGOV", eng.sgov_share_px
                )
                side_s = "BUY" if delta_sgov > 0 else "SELL"
                qty_s = abs(int(delta_sgov))
                lim_s = (
                    round(sgov_px_now + 0.03, 2)
                    if side_s == "BUY"
                    else round(max(1.0, sgov_px_now - 0.03), 2)
                )
                cid_s = _gen_c114_cid("V6SGV")
                try:
                    res_s = await context.api.create_order(
                        symbol="SGOV",
                        side=side_s,
                        quantity=qty_s,
                        price=lim_s,
                        order_type="LIMIT",
                        time_in_force="DAY",
                        client_order_id=cid_s,
                        enforce_daymarket_block=False,
                        allow_barbell_sgov=True,
                    )
                    oid_s = str(res_s.get("orderId") or "").strip()
                    if oid_s:
                        await context.ledger.update_state(
                            "SOXL",
                            v6_pending_order={
                                "order_id": oid_s,
                                "symbol": "SGOV",
                                "side": side_s,
                                "qty": qty_s,
                                "limit_price": lim_s,
                                "submitted_mono": time.monotonic(),
                            },
                        )
                        return
                except Exception as sg_e:
                    if logger:
                        logger.warning("⚠️ [Case 114 SGOV 리밸런싱 주문 유예]: %s", sg_e)

    # 5) 장외(pre_ext / post_ext) +4.0% 다층 스윕 익절 감시 (최상위 스윕 지층 min_floor 보호)
    ext_cooldown_until = float(getattr(context, "v6_ext_cooldown_mono", 0.0) or 0.0)
    if (
        live_p > 0.0
        and win["is_ext_tradable"]
        and eng.stack
        and time.monotonic() >= ext_cooldown_until
    ):
        ext_ratio = V6_EXT_TP_PCT / 100.0
        sweep_q, _ = eng.get_sweep_sellable_plan(live_p, ext_ratio, cur_min_epoch)
        if sweep_q >= 1:
            px_2nd = await _fetch_live_px_bypass_shm(context.api, "SOXL", live_p)
            sweep_q2, min_floor = eng.get_sweep_sellable_plan(
                px_2nd, ext_ratio, cur_min_epoch
            )
            if sweep_q2 >= 1 and min_floor > 0.0:
                lim_sell = round(max(min_floor, px_2nd * 0.9975), 2)
                cid_x = _gen_c114_cid("V6EXTS")
                try:
                    ord_x = await context.api.create_order(
                        symbol="SOXL",
                        side="SELL",
                        quantity=sweep_q2,
                        price=lim_sell,
                        order_type="LIMIT",
                        time_in_force="DAY",
                        client_order_id=cid_x,
                        enforce_daymarket_block=False,
                    )
                    oid_x = str(ord_x.get("orderId") or "").strip()
                    if oid_x:
                        await context.ledger.update_state(
                            "SOXL",
                            sell_order_id=oid_x,
                            v6_pending_order={
                                "order_id": oid_x,
                                "symbol": "SOXL",
                                "side": "SELL",
                                "qty": sweep_q2,
                                "limit_price": lim_sell,
                                "min_gain_ratio": ext_ratio,
                                "submitted_mono": time.monotonic(),
                            },
                        )
                        return
                except Exception as ext_e:
                    context.v6_ext_cooldown_mono = time.monotonic() + 60.0
                    if logger:
                        logger.debug("장외 +4%% 스윕 묵음 쿨다운(60s): %s", ext_e)

    # 6) 정규장 T-1h (14:59 ~ 15:59 / 조기폐장 11:59 ~ 12:59 EST) 단방향 1회 평가 & $0.01 센트격자 HA 패스
    if live_p > 0.0 and win["is_t1h_window"]:
        last_eval_min = int(getattr(context, "v6_last_t1h_min_epoch", 0) or 0)
        need_t1h_check = bool(
            eng.t1h_eval_date_ymd != ymd
            or (
                cur_min_epoch > last_eval_min
                and eng.t1h_wait_state not in ("IDLE", "DONE")
            )
        )
        if need_t1h_check:
            candles_t1h = None
            if hasattr(context.api, "get_candles_1m"):
                try:
                    candles_t1h = await context.api.get_candles_1m(
                        symbol="SOXL", total_count=240
                    )
                except Exception:
                    candles_t1h = None
            metrics_m = getattr(context, "candle_metrics_cache", {}).get("SOXL", {})
            sbear, sbull, _ = _extract_closed_1m_ha_flags(
                metrics_m, candles_raw=candles_t1h, now_est=now_est
            )
            px_t1h = await _fetch_live_px_bypass_shm(context.api, "SOXL", live_p)
            prev_wait_state = eng.t1h_wait_state
            sig = eng.evaluate_t1h_bar(
                date_ymd=ymd,
                px=px_t1h,
                shaved_bear=sbear,
                shaved_bull=sbull,
            )
            context.v6_last_t1h_min_epoch = cur_min_epoch
            await asyncio.to_thread(
                eng.save_json_atomic, resolve_v6_ledger_path(context), ctx_dir
            )

            retry_key = f"_v6_t1h_retry_{ymd}"
            cur_retries = int(getattr(context, retry_key, 0) or 0)
            act = str(sig.get("action") or "")

            if act == "SELL":
                sell_q, floor_p = eng.get_sweep_sellable_plan(
                    px_t1h, V6_RTH_T1H_TP_RATIO, cur_min_epoch
                )
                if sell_q >= 1 and floor_p > 0.0:
                    lim_p = round(max(floor_p, px_t1h * 0.9975), 2)
                    cid_ts = _gen_c114_cid("V6T1HS")
                    try:
                        ord_ts = await context.api.create_order(
                            symbol="SOXL",
                            side="SELL",
                            quantity=sell_q,
                            price=lim_p,
                            order_type="LIMIT",
                            time_in_force="DAY",
                            client_order_id=cid_ts,
                            enforce_daymarket_block=False,
                        )
                        oid_ts = str(ord_ts.get("orderId") or "").strip()
                        if oid_ts:
                            await context.ledger.update_state(
                                "SOXL",
                                sell_order_id=oid_ts,
                                v6_pending_order={
                                    "order_id": oid_ts,
                                    "symbol": "SOXL",
                                    "side": "SELL",
                                    "qty": sell_q,
                                    "limit_price": lim_p,
                                    "min_gain_ratio": V6_RTH_T1H_TP_RATIO,
                                    "from_t1h": True,
                                    "submitted_mono": time.monotonic(),
                                },
                            )
                            return
                    except Exception as ts_e:
                        if logger:
                            logger.warning("⚠️ [Case 114 T-1h 매도 발주 예외]: %s", ts_e)
                        if cur_retries < 2:
                            setattr(context, retry_key, cur_retries + 1)
                            eng.t1h_wait_state = prev_wait_state
                            await asyncio.to_thread(
                                eng.save_json_atomic,
                                resolve_v6_ledger_path(context),
                                ctx_dir,
                            )

            elif act == "BUY":
                ref_px = float(sig.get("ref_px") or px_t1h)
                is_vac = bool(sig.get("is_vac", False))
                buy_q, need_sgov_sell = eng.plan_buy_order_qty(
                    ref_px, px_t1h, can_trade_sgov_now=can_sgov
                )
                if buy_q >= 1:
                    if need_sgov_sell > 0 and can_sgov:
                        sg_px = await _fetch_live_px_bypass_shm(
                            context.api, "SGOV", eng.sgov_share_px
                        )
                        sg_lim = round(max(1.0, sg_px - 0.05), 2)
                        cid_sg = _gen_c114_cid("V6ONSG")
                        try:
                            ord_sg = await context.api.create_order(
                                symbol="SGOV",
                                side="SELL",
                                quantity=need_sgov_sell,
                                price=sg_lim,
                                order_type="LIMIT",
                                time_in_force="DAY",
                                client_order_id=cid_sg,
                                enforce_daymarket_block=False,
                                allow_barbell_sgov=True,
                            )
                            oid_sg = str(ord_sg.get("orderId") or "").strip()
                        except Exception as sg_ord_e:
                            if logger:
                                logger.warning(
                                    "⚠️ [Case 114 온디맨드 SGOV 매도 발주 예외]: %s",
                                    sg_ord_e,
                                )
                            if cur_retries < 2:
                                setattr(context, retry_key, cur_retries + 1)
                                eng.t1h_wait_state = prev_wait_state
                                await asyncio.to_thread(
                                    eng.save_json_atomic,
                                    resolve_v6_ledger_path(context),
                                    ctx_dir,
                                )
                            return

                        if oid_sg:
                            sg_term = False
                            f_sg_q = 0
                            f_sg_p = 0.0
                            for _ in range(4):
                                await asyncio.sleep(0.45)
                                det_sg = await context.api.get_order_detail(oid_sg)
                                st_sg, f_sg_q, f_sg_p = _extract_order_fill_info(det_sg)
                                if st_sg in _TERMINAL_ORDER_STATUSES:
                                    sg_term = True
                                    break
                            if not sg_term:
                                # SGOV 미체결 대기 중 -> 0.4s 루프에서 체결 즉시 후속 SOXL 매수를 발주하도록 체인 위임
                                await context.ledger.update_state(
                                    "SOXL",
                                    v6_pending_order={
                                        "order_id": oid_sg,
                                        "symbol": "SGOV",
                                        "side": "SELL",
                                        "qty": need_sgov_sell,
                                        "limit_price": sg_lim,
                                        "submitted_mono": time.monotonic(),
                                        "chained_soxl_buy": {
                                            "ref_px": ref_px,
                                            "is_vac": is_vac,
                                            "date_ymd": ymd,
                                        },
                                    },
                                )
                                return
                            if f_sg_q > 0:
                                eng.apply_sgov_fill(
                                    -f_sg_q, f_sg_p if f_sg_p > 0.0 else sg_lim
                                )
                                await asyncio.to_thread(
                                    eng.save_json_atomic,
                                    resolve_v6_ledger_path(context),
                                    ctx_dir,
                                )
                                buy_q, _ = eng.plan_buy_order_qty(
                                    ref_px, px_t1h, can_trade_sgov_now=False
                                )
                            else:
                                if cur_retries < 2:
                                    setattr(context, retry_key, cur_retries + 1)
                                    eng.t1h_wait_state = prev_wait_state
                                    await asyncio.to_thread(
                                        eng.save_json_atomic,
                                        resolve_v6_ledger_path(context),
                                        ctx_dir,
                                    )
                                return

                    if buy_q >= 1:
                        lim_buy = round(px_t1h * 1.0030, 2)
                        max_lim = round(
                            math.floor((eng.tranche_stock / float(buy_q)) * 100.0)
                            / 100.0,
                            2,
                        )
                        if max_lim > 0.0:
                            lim_buy = min(lim_buy, max_lim)
                        cid_tb = _gen_c114_cid("V6T1HB")
                        try:
                            ord_tb = await context.api.create_order(
                                symbol="SOXL",
                                side="BUY",
                                quantity=buy_q,
                                price=lim_buy,
                                order_type="LIMIT",
                                time_in_force="DAY",
                                client_order_id=cid_tb,
                                enforce_daymarket_block=False,
                            )
                            oid_tb = str(ord_tb.get("orderId") or "").strip()
                            if oid_tb:
                                await context.ledger.update_state(
                                    "SOXL",
                                    buy_order_id=oid_tb,
                                    v6_pending_order={
                                        "order_id": oid_tb,
                                        "symbol": "SOXL",
                                        "side": "BUY",
                                        "qty": buy_q,
                                        "limit_price": lim_buy,
                                        "is_vac": is_vac,
                                        "from_t1h": True,
                                        "submitted_mono": time.monotonic(),
                                    },
                                )
                                return
                        except Exception as tb_e:
                            if logger:
                                logger.warning(
                                    "⚠️ [Case 114 T-1h 매수 발주 예외]: %s", tb_e
                                )
                            if cur_retries < 2:
                                setattr(context, retry_key, cur_retries + 1)
                                eng.t1h_wait_state = prev_wait_state
                                await asyncio.to_thread(
                                    eng.save_json_atomic,
                                    resolve_v6_ledger_path(context),
                                    ctx_dir,
                                )

    # 7) UI 및 암살자 0주 판정용 미러링 상시 정합성 동기화 (유령 매수대기·기수혈·금고 잔재 즉시 치유)
    st_sync, bb_sync = sync_v6_to_legacy_state_dicts(eng, st_cur, bb_cur)
    need_mirror = bool(
        st_cur.get("portion_mode") != eng.barbell_mode
        or int(st_cur.get("total_qty") or 0) != st_sync["total_qty"]
        or bool(st_cur.get("sub_buckets"))
        or abs(float(st_cur.get("injected_reserve_usd") or 0.0) - st_sync["injected_reserve_usd"]) > 0.05
        or abs(float(st_cur.get("vaulted_profit_locked_usd") or 0.0) - st_sync["vaulted_profit_locked_usd"]) > 0.05
        or int(st_cur.get("v6_consecutive_no_trade_days") or 0) != st_sync["v6_consecutive_no_trade_days"]
        or int(bb_cur.get("sgov_held_qty") or -1) != bb_sync["sgov_held_qty"]
        or abs(float(bb_cur.get("cash_bucket_usd") or -1.0) - bb_sync["cash_bucket_usd"]) > 0.05
        or abs(float(bb_cur.get("pending_sgov_buy_budget_usd") or 0.0) - bb_sync["pending_sgov_buy_budget_usd"]) > 0.05
        or abs(float(bb_cur.get("cash_injected_to_soxl_usd") or 0.0) - bb_sync["cash_injected_to_soxl_usd"]) > 0.05
        or abs(float(bb_cur.get("cycle_vaulted_profit_usd") or 0.0) - bb_sync["cycle_vaulted_profit_usd"]) > 0.05
    )
    if need_mirror:
        await apply_v6_mirror_to_legacy_ledgers(
            context, eng, save_v6_disk=False
        )
