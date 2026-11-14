# -*- coding: utf-8 -*-
"""
# MODIFIED: sniper_exit_plugin.py (Part 1/2 — 황금시간 07:00~07:50 RSI<=19 올인 전면 영구 소각 &
# 바벨 모드[BARBELL_60_30_10] 매도 시 세후 실현수익 별도 금고 즉시 영구 격리 및 0주 졸업 시 60/30/10 자동 리밸런싱 결속 &
# SOXL 0주 달성 순간 [실전] 암살자 전환 예약[ARMED_LIVE_ON_ZERO] 자동 승격 인계 훅 탑재)
순수 롱(SOXL) 전용 '매수 체결 후 최초 60초 강제 타임쉴드(POST_BUY_TO_SELL_SHIELD_SEC = 60.0) &
매수 후 60초 경과 시점부터 프리마켓·정규장·애프터마켓(16:00 ~ 19:59 EST)·데이마켓(20:00 ~ 03:59 EST) 24시간 전 세션에서
매 1.5초 실시간 다중 익절(7층 본 그리드 + Default-ON 3층 서브 그리드) + 최근 5.0초 윗꼬리 체결틱 포착 + 방안 C 오버나이트 통합이평 사수 스나이퍼 매도 모니터' 코어 플러그인
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import assassin_plugin
from barbell_plugin import (
    ensure_barbell_ledger,
    is_barbell_mode,
    record_barbell_realized_profit,
)
from quant_engine import (
    DEFAULT_GRID_MERGE_MODE,
    MAX_GRID_TIERS_7,
    MAX_GRID_TIERS_12,
    MAX_RESERVE_PORTIONS,
    PORTION_MODE_BARBELL,
    PORTION_MODE_COMPOUND,
    PORTION_MODE_SIMPLE,
    REANCHOR_NET_BUFFER_MULT,
    SNIPER_L1_TRAIL_BOOST_TIER2_PCT,
    SNIPER_L1_TRAIL_CB_TIGHT_PCT,
    SNIPER_L1_TRAIL_CB_WIDE_PCT,
    SNIPER_L1_TRAIL_ENABLED,
    SNIPER_L1_TRAIL_IGNITE_PCT,
    SNIPER_L1_TRAIL_QQQ_BYPASS_PCT,
    SNIPER_L1_TRAIL_SAFE_CAP_PCT,
    SNIPER_L1_TRAIL_STEP_LOCK_PCT,
    SNIPER_L1_TRAIL_STEP_TRIG_PCT,
    SUB_SNIPER_L1_TRAIL_IGNITE_PCT,
    SUB_SNIPER_L1_TRAIL_STEP_LOCK_PCT,
    SUB_SNIPER_L1_TRAIL_STEP_TRIG_PCT,
    SUB_MAX_TIERS_3,
    SUB_MAX_TOTAL_LOTS_4,
    SUB_MERGE_MODE_L1_L3,
    StratumBucket,
    buckets_from_dicts,
    buckets_to_dicts,
    calc_sell_realized_pnl,
    compute_reserve_repayment_on_zero,
    compute_sub_upper_2_to_3_moving_avg,
    compute_upper_2_to_7_moving_avg,
    compute_upper_2_to_12_moving_avg,
    evaluate_multi_grid_sell_targets,
    get_golden8_prog_thresholds,
    has_active_l1_bucket,
    has_active_l2_bucket,
    is_simple_income_mode,
    relabel_sub_upper_grid_tiers,
    relabel_upper_grid_tiers,
    resolve_effective_round_trip_fee_rate_pct,
    vrev_reanchor_single_tier_quota,
)
from quant_indicators_plugin import (
    NEW_CYCLE_BUY_CUTOFF_HM,
    is_active_buy_window,
    is_active_sell_window,
    is_active_trading_window,
    is_extended_sell_only_window,
    is_late_regular_new_cycle_cutoff_window,
    refresh_metrics_with_live_tick,
)
from toss_api import (
    DEFAULT_INITIAL_SEED_USD,
    EST_TZ,
    TARGET_SYMBOL,
    _NonRetryableApiError,
    generate_client_order_id,
    safe_float,
    safe_int,
)

logger = logging.getLogger("toss_sniper.sniper_exit_plugin")

# Case 65 & Case 70: 매수 직후 최초 60.0초 타임쉴드 · 매도(및 0주 종료) 후 60.0초 타임쉴드 상수
POST_BUY_TO_SELL_SHIELD_SEC: float = 60.0
SELL_MONITOR_TIME_SHIELD_SEC: float = 0.0
POST_SELL_TO_BUY_SHIELD_SEC: float = 60.0

# 지정가 매도 주문 발주 후 미체결 최대 대기 시간(초) — 하향 추격 정정 없이 60초 미체결 시 안전 취소
SELL_ORDER_MAX_WAIT_SEC: float = 60.0

# [Case 79]: 데이마켓/애프터마켓 거래 제한 시 묵음 쿨다운 시간(초)
EXTENDED_SELL_RESTRICTION_COOLDOWN_SEC: float = 60.0

# [Case 82 : 윗꼬리 슈팅 100% 즉시 체결을 위한 4대 핀포인트 상수 및 인메모리 상태]
EXTENDED_NO_SELLABLE_RETRY_COOLDOWN_SEC: float = 5.0
SELLABLE_QTY_POLL_WAIT_SEC: float = 2.0
SELLABLE_QTY_POLL_INTERVAL_SEC: float = 0.25

WICK_TRADE_LOOKBACK_SEC: float = 5.0
WICK_TRADE_FETCH_COUNT: int = 15
WICK_PROXIMITY_TRIGGER_RATIO: float = 0.975
WICK_PROBE_MIN_INTERVAL_SEC: float = 1.2

MARKETABLE_GAP_UP_THRESHOLD_MULT: float = 1.005
MARKETABLE_GAP_UP_SLIPPAGE_MULT: float = 0.997

_LAST_CONSUMED_WICK_TRADE_TS: float = 0.0
_LAST_WICK_PROBE_MONO: float = 0.0
_LAST_EXIT_CANDLE_WARM_MONO: float = 0.0


# ---------------------------------------------------------------------------
# [NEW · Case 99] 스나이퍼 본 1층 / 서브 1층 인메모리 스텝 락온 & "허락보다 용서를" 상태 슬롯
# ---------------------------------------------------------------------------
@dataclass
class SniperL1TrailSlot:
    grid_kind: str = "MAIN"
    qty: int = 0
    ref_cost: float = 0.0
    arm_100_p: float = 0.0
    step_trig_145_p: float = 0.0
    lock_125_p: float = 0.0
    cap_500_p: float = 0.0
    armed: bool = False
    stepped_125: bool = False
    armed_minute_key: str = ""
    forgiven_ha_minute_key: str = ""
    forgive_count: int = 0
    peak_p: float = 0.0
    lock_floor_p: float = 0.0
    active_stop_p: float = 0.0

    def full_reset(self) -> None:
        self.qty = 0
        self.ref_cost = 0.0
        self.arm_100_p = 0.0
        self.step_trig_145_p = 0.0
        self.lock_125_p = 0.0
        self.cap_500_p = 0.0
        self.armed = False
        self.stepped_125 = False
        self.armed_minute_key = ""
        self.forgiven_ha_minute_key = ""
        self.forgive_count = 0
        self.peak_p = 0.0
        self.lock_floor_p = 0.0
        self.active_stop_p = 0.0

    def sync_fingerprint(self, qty: int, book_price: float) -> None:
        q_clean = max(0, safe_int(qty, 0))
        bp_clean = round(max(0.0, safe_float(book_price, 0.0)), 4)
        if q_clean <= 0 or bp_clean <= 0.0:
            self.full_reset()
            return
        if self.qty != q_clean or abs(self.ref_cost - bp_clean) > 1e-4:
            self.full_reset()
            self.qty = q_clean
            self.ref_cost = bp_clean
            is_sub_slot = str(self.grid_kind or "").upper().strip() == "SUB"
            ign_pct = (
                SUB_SNIPER_L1_TRAIL_IGNITE_PCT
                if is_sub_slot
                else SNIPER_L1_TRAIL_IGNITE_PCT
            )
            trig_pct = (
                SUB_SNIPER_L1_TRAIL_STEP_TRIG_PCT
                if is_sub_slot
                else SNIPER_L1_TRAIL_STEP_TRIG_PCT
            )
            lock_pct = (
                SUB_SNIPER_L1_TRAIL_STEP_LOCK_PCT
                if is_sub_slot
                else SNIPER_L1_TRAIL_STEP_LOCK_PCT
            )
            self.arm_100_p = (
                math.ceil((bp_clean * (1.0 + ign_pct / 100.0) - 1e-9) * 100.0)
                / 100.0
            )
            self.step_trig_145_p = round(
                bp_clean * (1.0 + trig_pct / 100.0), 4
            )
            self.lock_125_p = (
                math.ceil((bp_clean * (1.0 + lock_pct / 100.0) - 1e-9) * 100.0)
                / 100.0
            )
            self.cap_500_p = round(
                bp_clean * (1.0 + SNIPER_L1_TRAIL_SAFE_CAP_PCT / 100.0), 2
            )

    def refresh_stop_price(self) -> float:
        # MODIFIED: 스텝 돌파 전 무스탑(0.0) 순수 1분봉 HA 추종 · 돌파 후 보존선/+2% 여유콜백 잠금
        if not self.armed or self.ref_cost <= 0.0:
            self.active_stop_p = 0.0
            return 0.0
        if (not self.stepped_125) and (
            self.peak_p >= self.step_trig_145_p - 1e-9
        ):
            self.stepped_125 = True
            self.lock_floor_p = self.lock_125_p
        if not self.stepped_125:
            self.active_stop_p = 0.0
            return 0.0
        pk_gain = ((self.peak_p - self.ref_cost) / self.ref_cost) * 100.0
        if pk_gain >= SNIPER_L1_TRAIL_BOOST_TIER2_PCT:
            cb_raw = round(
                self.peak_p * (1.0 - SNIPER_L1_TRAIL_CB_WIDE_PCT / 100.0), 2
            )
            self.active_stop_p = round(max(self.lock_floor_p, cb_raw), 2)
        else:
            self.active_stop_p = round(self.lock_floor_p, 2)
        return self.active_stop_p

    def release_forgive(self, bad_ha_minute_key: str = "") -> None:
        self.armed = False
        self.stepped_125 = False
        self.armed_minute_key = ""
        self.peak_p = 0.0
        self.lock_floor_p = 0.0
        self.active_stop_p = 0.0
        if bad_ha_minute_key:
            self.forgiven_ha_minute_key = str(bad_ha_minute_key).strip()
        self.forgive_count += 1

    def release_overnight(self) -> None:
        if self.armed:
            self.armed = False
            self.stepped_125 = False
            self.armed_minute_key = ""
            self.peak_p = 0.0
            self.lock_floor_p = 0.0
            self.active_stop_p = 0.0

    def to_ui_dict(self) -> Dict[str, Any]:
        return {
            "armed": bool(self.armed),
            "stepped_125": bool(self.stepped_125),
            "arm_100_p": round(self.arm_100_p, 2),
            "lock_125_p": round(self.lock_125_p, 2),
            "peak_p": round(self.peak_p, 2),
            "lock_floor_p": round(self.lock_floor_p, 2),
            "active_stop_p": round(self.active_stop_p, 2),
            "forgiven_ha_minute_key": self.forgiven_ha_minute_key,
            "forgive_count": int(self.forgive_count),
        }


def get_sniper_l1_trail_slots(
    context: Any,
    symbol: str = TARGET_SYMBOL,
) -> Tuple[SniperL1TrailSlot, SniperL1TrailSlot]:
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    snap_map = getattr(context, "exit_snapshot_cache", None)
    if not isinstance(snap_map, dict):
        return SniperL1TrailSlot("MAIN"), SniperL1TrailSlot("SUB")
    entry = snap_map.get(sym)
    if not isinstance(entry, dict):
        entry = {}
        snap_map[sym] = entry
    main_slot = entry.get("main_l1_trail")
    if not isinstance(main_slot, SniperL1TrailSlot):
        main_slot = SniperL1TrailSlot("MAIN")
        entry["main_l1_trail"] = main_slot
    sub_slot = entry.get("sub_l1_trail")
    if not isinstance(sub_slot, SniperL1TrailSlot):
        sub_slot = SniperL1TrailSlot("SUB")
        entry["sub_l1_trail"] = sub_slot
    return main_slot, sub_slot


def reset_sniper_l1_trail_slots(
    context: Any,
    grid_kind: str = "ALL",
    symbol: str = TARGET_SYMBOL,
) -> None:
    if context is None:
        return
    main_slot, sub_slot = get_sniper_l1_trail_slots(context, symbol=symbol)
    kind_u = str(grid_kind or "ALL").upper().strip()
    if kind_u in ("ALL", "MAIN"):
        main_slot.full_reset()
    if kind_u in ("ALL", "SUB"):
        sub_slot.full_reset()


def is_sniper_l1_trail_active(
    context: Any,
    symbol: str = TARGET_SYMBOL,
) -> bool:
    if context is None or not SNIPER_L1_TRAIL_ENABLED:
        return False
    main_slot, sub_slot = get_sniper_l1_trail_slots(context, symbol=symbol)
    return bool(main_slot.armed or sub_slot.armed)


def get_sniper_l1_trail_ui_snapshot(
    context: Any,
    symbol: str = TARGET_SYMBOL,
) -> Dict[str, Dict[str, Any]]:
    main_slot, sub_slot = get_sniper_l1_trail_slots(context, symbol=symbol)
    return {
        "main": main_slot.to_ui_dict(),
        "sub": sub_slot.to_ui_dict(),
    }


# ---------------------------------------------------------------------------
# 내부 헬퍼 : 실시간 SOXL 현재가 조회 · 윗꼬리 체결틱 역추적 · 장외 묵음 쿨다운 · 매수/매도 후 60초 타임쉴드 판별
# ---------------------------------------------------------------------------
def mark_extended_sell_restriction_cooldown(
    context: Any,
    symbol: str = TARGET_SYMBOL,
    cooldown_sec: float = EXTENDED_SELL_RESTRICTION_COOLDOWN_SEC,
    reason: str = "EXTENDED_RESTRICTED",
) -> None:
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    c_sec = max(0.0, safe_float(cooldown_sec, 60.0))
    until_mono = (time.monotonic() + c_sec) if c_sec > 0.0 else 0.0
    snap_map = getattr(context, "exit_snapshot_cache", None)
    if isinstance(snap_map, dict):
        entry = (
            snap_map.get(sym) if isinstance(snap_map.get(sym), dict) else {}
        )
        entry["ext_sell_restrict_until_mono"] = until_mono
        entry["ext_sell_restrict_reason"] = str(
            reason or "EXTENDED_RESTRICTED"
        )
        snap_map[sym] = entry


def is_within_extended_sell_restriction_cooldown(
    context: Any,
    symbol: str = TARGET_SYMBOL,
) -> Tuple[bool, float]:
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    snap_map = getattr(context, "exit_snapshot_cache", None)
    if isinstance(snap_map, dict):
        entry = snap_map.get(sym)
        if isinstance(entry, dict):
            until_m = safe_float(entry.get("ext_sell_restrict_until_mono"), 0.0)
            rem = until_m - time.monotonic()
            if rem > 0.0:
                return True, round(rem, 1)
    return False, 0.0


def _get_live_soxl_price(
    context: Any,
    prices: Dict[str, float],
    holdings: Dict[str, Dict[str, Any]],
    now_est: datetime,
    allow_stale_fallback: bool = True,
) -> float:
    lp = safe_float((prices or {}).get(TARGET_SYMBOL), 0.0)
    if lp > 0.0:
        return lp
    if not allow_stale_fallback:
        return 0.0

    raw_cache = getattr(context, "candle_metrics_cache", {})
    base_met = (
        raw_cache.get(TARGET_SYMBOL) if isinstance(raw_cache, dict) else None
    )
    if isinstance(base_met, dict):
        met = refresh_metrics_with_live_tick(base_met, 0.0, now_est=now_est)
        lp = safe_float(met.get("live_price"), 0.0)
        if lp > 0.0:
            return lp
    h_info = (holdings or {}).get(TARGET_SYMBOL, {})
    return safe_float(h_info.get("last_price"), 0.0)


async def _fetch_fresh_current_soxl_price(
    context: Any,
    fallback_price: float = 0.0,
) -> float:
    try:
        try:
            fresh_map = (
                await context.api.get_current_prices_batch(
                    (TARGET_SYMBOL,),
                    bypass_shm_cache=True,
                )
            )
        except TypeError:
            fresh_map = (
                await context.api.get_current_prices_batch(
                    (TARGET_SYMBOL,)
                )
            )
        fresh_p = safe_float(
            (fresh_map or {}).get(TARGET_SYMBOL), 0.0
        )
        if fresh_p > 0.0:
            if isinstance(getattr(context, "latest_prices", None), dict):
                context.latest_prices[TARGET_SYMBOL] = fresh_p
            if isinstance(getattr(context, "candle_metrics_cache", None), dict):
                base_met = context.candle_metrics_cache.get(TARGET_SYMBOL)
                if isinstance(base_met, dict):
                    context.candle_metrics_cache[TARGET_SYMBOL] = (
                        refresh_metrics_with_live_tick(base_met, fresh_p)
                    )
            return fresh_p
    except Exception as exc:
        logger.debug("실시간 현재가 재조회 폴백 사용(묵음): %s", exc)
    return safe_float(fallback_price, 0.0)


def _compute_nearest_sell_target_price(
    buckets: Sequence[StratumBucket],
    rise_l1_pct: float = 1.50,
    rise_upper_pct: float = 1.00,
    is_overnight_session: bool = False,
    sub_buckets: Optional[Sequence[StratumBucket]] = None,
) -> float:
    candidates: List[float] = []
    eff_l1_pct = (
        SNIPER_L1_TRAIL_IGNITE_PCT
        if (SNIPER_L1_TRAIL_ENABLED and not is_overnight_session)
        else safe_float(rise_l1_pct, 1.50)
    )
    l1_mult = 1.0 + max(0.1, eff_l1_pct) / 100.0
    up_mult = 1.0 + max(0.1, safe_float(rise_upper_pct, 1.00)) / 100.0

    if buckets:
        active_l1 = has_active_l1_bucket(buckets)
        wma_info = compute_upper_2_to_7_moving_avg(
            buckets, rise_upper_pct=rise_upper_pct
        )
        t_l1 = 0.0
        if active_l1 and buckets[0].qty > 0:
            pure_bp1 = max(
                0.01, buckets[0].actual_avg_price, buckets[0].book_price
            )
            t_l1 = max(
                0.01,
                math.ceil((pure_bp1 * l1_mult - 1e-9) * 100.0) / 100.0,
            )
            candidates.append(t_l1)

        b_l2 = wma_info.get("l2_bucket")
        if bool(wma_info.get("has_active_l2")) and isinstance(
            b_l2, StratumBucket
        ):
            pure_bp2 = max(0.01, b_l2.actual_avg_price, b_l2.book_price)
            raw_t_l2 = max(
                0.01,
                math.ceil((pure_bp2 * up_mult - 1e-9) * 100.0) / 100.0,
            )
            eff_t_l2 = (
                max(raw_t_l2, t_l1) if (active_l1 and t_l1 > 0.0) else raw_t_l2
            )
            candidates.append(eff_t_l2)

        inv_3_7_t = safe_float(wma_info.get("inv_3_7_wma_target_price"), 0.0)
        if inv_3_7_t > 0.0:
            candidates.append(inv_3_7_t)

    sub_eff_l1_pct = (
        SUB_SNIPER_L1_TRAIL_IGNITE_PCT
        if (SNIPER_L1_TRAIL_ENABLED and not is_overnight_session)
        else safe_float(rise_l1_pct, 1.50)
    )
    sub_l1_mult = 1.0 + max(0.1, sub_eff_l1_pct) / 100.0

    valid_sub = [
        sb
        for sb in (sub_buckets or [])
        if isinstance(sb, StratumBucket) and sb.qty > 0
    ]
    if valid_sub:
        sub_active_l1 = has_active_l1_bucket(valid_sub)
        sub_wma_info = compute_sub_upper_2_to_3_moving_avg(
            valid_sub, rise_upper_pct=rise_upper_pct
        )
        sub_upper_cnt = safe_int(sub_wma_info.get("upper_tier_count"), 0)

        if not (is_overnight_session and sub_upper_cnt > 0):
            for s_idx, sb in enumerate(valid_sub):
                if sb.qty <= 0:
                    continue
                pure_sbp = max(0.01, sb.actual_avg_price, sb.book_price)
                if s_idx == 0 and sub_active_l1:
                    st_p = max(
                        0.01,
                        math.ceil((pure_sbp * sub_l1_mult - 1e-9) * 100.0)
                        / 100.0,
                    )
                else:
                    st_p = max(
                        0.01,
                        math.ceil((pure_sbp * up_mult - 1e-9) * 100.0)
                        / 100.0,
                    )
                candidates.append(st_p)

        if sub_upper_cnt > 0:
            sub_wma_t = safe_float(
                sub_wma_info.get("upper_wma_target_price"), 0.0
            )
            if sub_wma_t > 0.0:
                candidates.append(sub_wma_t)

    return min(candidates) if candidates else 0.0


def _parse_trade_ts_fallback(ts_val: Any) -> float:
    if ts_val is None or isinstance(ts_val, bool):
        return 0.0
    if isinstance(ts_val, (int, float)):
        f_ts = safe_float(ts_val, 0.0)
        return (f_ts / 1000.0) if f_ts > 1e12 else max(0.0, f_ts)
    s = str(ts_val).strip()
    if not s:
        return 0.0
    try:
        if s.endswith("Z") or s.endswith("z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=EST_TZ)
        return float(dt.timestamp())
    except Exception:
        num_ts = safe_float(s, 0.0)
        return (num_ts / 1000.0) if num_ts > 1e12 else max(0.0, num_ts)


async def _probe_recent_trade_wick_high_soxl(
    context: Any,
    min_after_ts: float = 0.0,
    lookback_sec: float = WICK_TRADE_LOOKBACK_SEC,
    count: int = WICK_TRADE_FETCH_COUNT,
) -> Tuple[float, float]:
    global _LAST_WICK_PROBE_MONO

    now_mono = time.monotonic()
    if (now_mono - _LAST_WICK_PROBE_MONO) < WICK_PROBE_MIN_INTERVAL_SEC:
        return 0.0, 0.0
    _LAST_WICK_PROBE_MONO = now_mono

    api_obj = getattr(context, "api", None)
    if api_obj is None:
        return 0.0, 0.0

    eff_after_ts = max(
        0.0,
        safe_float(min_after_ts, 0.0),
        _LAST_CONSUMED_WICK_TRADE_TS,
    )

    try:
        if hasattr(api_obj, "get_recent_wick_high_price"):
            w_p, w_ts = await api_obj.get_recent_wick_high_price(
                symbol=TARGET_SYMBOL,
                lookback_sec=lookback_sec,
                min_after_ts=eff_after_ts,
                count=count,
            )
            return safe_float(w_p, 0.0), safe_float(w_ts, 0.0)

        if hasattr(api_obj, "get_recent_trades"):
            trades = await api_obj.get_recent_trades(
                symbol=TARGET_SYMBOL, count=count
            )
            if not isinstance(trades, list) or not trades:
                return 0.0, 0.0
            now_epoch = time.time()
            max_age = max(1.0, safe_float(lookback_sec, 5.0))
            best_p = 0.0
            best_ts = 0.0
            for t in trades:
                if not isinstance(t, dict):
                    continue
                p = safe_float(t.get("price"), 0.0)
                v = safe_float(t.get("volume"), 1.0)
                if p <= 0.0 or v <= 0.0:
                    continue
                t_ts = _parse_trade_ts_fallback(
                    t.get("timestamp")
                    or t.get("dt")
                    or t.get("dateTime")
                    or t.get("time")
                )
                if t_ts <= 0.0:
                    continue
                if eff_after_ts > 0.0 and t_ts <= (eff_after_ts + 1e-6):
                    continue
                age = now_epoch - t_ts
                if age > max_age or age < -5.0:
                    continue
                if p > best_p or (abs(p - best_p) < 1e-9 and t_ts > best_ts):
                    best_p = p
                    best_ts = t_ts
            return round(best_p, 4), round(best_ts, 4)
    except Exception as exc:
        logger.debug("_probe_recent_trade_wick_high_soxl 예외(묵음): %s", exc)

    return 0.0, 0.0


def _resolve_safe_l2_book_price(
    bucket: StratumBucket,
    st: Optional[Dict[str, Any]] = None,
) -> float:
    if bucket.qty <= 0:
        return max(0.01, bucket.book_price)
    return round(max(0.01, bucket.actual_avg_price, bucket.book_price), 4)


def is_within_post_buy_time_shield(
    context: Any,
    st: Optional[Dict[str, Any]] = None,
    symbol: str = TARGET_SYMBOL,
) -> Tuple[bool, float]:
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    now_mono = time.monotonic()

    guard_map = getattr(context, "indexing_grace_cache", None)
    if isinstance(guard_map, dict):
        info = guard_map.get(sym)
        if isinstance(info, dict):
            last_buy_mono = max(
                safe_float(info.get("last_buy_fill_mono"), 0.0),
                safe_float(info.get("last_sub_buy_fill_mono"), 0.0),
            )
            if (
                last_buy_mono <= 0.0
                and str(info.get("lot_type") or "") != "SELL_FILL"
            ):
                last_buy_mono = safe_float(info.get("last_auto_fill_ts"), 0.0)
            if last_buy_mono > 0.0:
                elapsed_mono = now_mono - last_buy_mono
                if 0.0 <= elapsed_mono < POST_BUY_TO_SELL_SHIELD_SEC:
                    return True, round(
                        POST_BUY_TO_SELL_SHIELD_SEC - elapsed_mono, 1
                    )

    state_obj = (
        st
        if isinstance(st, dict)
        else (
            context.ledger.get_state(sym)
            if hasattr(context, "ledger")
            else {}
        )
    )
    last_buy_epoch = max(
        safe_float(state_obj.get("last_buy_fill_ts"), 0.0),
        safe_float(state_obj.get("last_sub_buy_fill_ts"), 0.0),
        safe_float(state_obj.get("entry_ts"), 0.0),
    )
    if last_buy_epoch > 0.0:
        elapsed_epoch = time.time() - last_buy_epoch
        if 0.0 <= elapsed_epoch < POST_BUY_TO_SELL_SHIELD_SEC:
            return True, round(POST_BUY_TO_SELL_SHIELD_SEC - elapsed_epoch, 1)

    return False, 0.0


def mark_sell_monitor_60s_cycle_shield(
    context: Any,
    symbol: str = TARGET_SYMBOL,
    eval_price: float = 0.0,
    clear_shield: bool = False,
) -> float:
    sym = str(symbol or TARGET_SYMBOL).upper().strip()

    snap_map = getattr(context, "exit_snapshot_cache", None)
    if isinstance(snap_map, dict):
        entry = (
            snap_map.get(sym) if isinstance(snap_map.get(sym), dict) else {}
        )
        entry["last_sell_gate_eval_mono"] = 0.0
        entry["last_sell_gate_eval_ts"] = 0.0
        if eval_price > 0.0:
            entry["last_sell_gate_eval_price"] = round(
                safe_float(eval_price, 0.0), 4
            )
        snap_map[sym] = entry

    guard_map = getattr(context, "indexing_grace_cache", None)
    if isinstance(guard_map, dict):
        g_entry = (
            guard_map.get(sym) if isinstance(guard_map.get(sym), dict) else {}
        )
        g_entry["last_sell_gate_eval_mono"] = 0.0
        g_entry["last_sell_gate_eval_ts"] = 0.0
        guard_map[sym] = g_entry

    return 0.0


def is_within_sell_monitor_time_shield(
    context: Any,
    st: Optional[Dict[str, Any]] = None,
    symbol: str = TARGET_SYMBOL,
) -> Tuple[bool, float]:
    return is_within_post_buy_time_shield(context, st, symbol)


def mark_post_sell_time_shield(
    context: Any,
    symbol: str = TARGET_SYMBOL,
    fill_price: float = 0.0,
    sold_qty: int = 0,
    is_cycle_end: bool = False,
) -> None:
    global _LAST_CONSUMED_WICK_TRADE_TS

    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    reset_sniper_l1_trail_slots(context, grid_kind="ALL", symbol=sym)
    now_mono = time.monotonic()
    now_epoch = time.time()
    _LAST_CONSUMED_WICK_TRADE_TS = max(_LAST_CONSUMED_WICK_TRADE_TS, now_epoch)

    snap_map = getattr(context, "exit_snapshot_cache", None)
    if isinstance(snap_map, dict):
        entry = (
            snap_map.get(sym) if isinstance(snap_map.get(sym), dict) else {}
        )
        entry["last_sell_fill_mono"] = now_mono
        entry["last_sell_fill_ts"] = now_epoch
        entry["last_reentry_eval_mono"] = 0.0
        entry["last_reentry_eval_ts"] = 0.0
        entry["last_sub_reentry_eval_mono"] = 0.0
        entry["last_sub_reentry_eval_ts"] = 0.0
        entry["last_reserve_check_mono"] = 0.0
        entry["last_reserve_check_ts"] = 0.0
        entry["last_sell_gate_eval_mono"] = 0.0
        entry["last_sell_gate_eval_ts"] = 0.0
        entry["ext_sell_restrict_until_mono"] = 0.0
        if is_cycle_end:
            entry["last_cycle_end_mono"] = now_mono
            entry["last_cycle_end_ts"] = now_epoch
        entry["last_sell_price"] = safe_float(fill_price, 0.0)
        entry["last_sold_qty"] = safe_int(sold_qty, 0)
        snap_map[sym] = entry

    guard_map = getattr(context, "indexing_grace_cache", None)
    if isinstance(guard_map, dict):
        g_entry = (
            guard_map.get(sym) if isinstance(guard_map.get(sym), dict) else {}
        )
        prev_lot_type = str(g_entry.get("lot_type") or "")
        if (
            prev_lot_type != "SELL_FILL"
            and safe_float(g_entry.get("last_auto_fill_ts"), 0.0) > 0.0
        ):
            g_entry["last_buy_fill_mono"] = safe_float(
                g_entry.get("last_auto_fill_ts"), 0.0
            )
        g_entry["last_auto_fill_ts"] = now_mono
        g_entry["last_sell_fill_mono"] = now_mono
        g_entry["last_sell_fill_ts"] = now_epoch
        g_entry["last_reentry_eval_mono"] = 0.0
        g_entry["last_reentry_eval_ts"] = 0.0
        g_entry["last_sub_reentry_eval_mono"] = 0.0
        g_entry["last_sub_reentry_eval_ts"] = 0.0
        g_entry["last_reserve_check_mono"] = 0.0
        g_entry["last_reserve_check_ts"] = 0.0
        g_entry["last_sell_gate_eval_mono"] = 0.0
        g_entry["last_sell_gate_eval_ts"] = 0.0
        if is_cycle_end:
            g_entry["last_cycle_end_mono"] = now_mono
            g_entry["last_cycle_end_ts"] = now_epoch
        g_entry["lot_type"] = "SELL_FILL"
        g_entry["fill_price"] = safe_float(fill_price, 0.0)
        g_entry["filled_qty"] = safe_int(sold_qty, 0)
        guard_map[sym] = g_entry


def is_within_post_sell_time_shield(
    context: Any,
    st: Optional[Dict[str, Any]] = None,
    symbol: str = TARGET_SYMBOL,
) -> Tuple[bool, float]:
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    now_mono = time.monotonic()

    snap_map = getattr(context, "exit_snapshot_cache", None)
    if isinstance(snap_map, dict):
        entry = snap_map.get(sym)
        if isinstance(entry, dict):
            last_sell_mono = max(
                safe_float(entry.get("last_sell_fill_mono"), 0.0),
                safe_float(entry.get("last_cycle_end_mono"), 0.0),
            )
            if last_sell_mono > 0.0:
                elapsed_mono = now_mono - last_sell_mono
                if 0.0 <= elapsed_mono < POST_SELL_TO_BUY_SHIELD_SEC:
                    return True, round(
                        POST_SELL_TO_BUY_SHIELD_SEC - elapsed_mono, 1
                    )

    guard_map = getattr(context, "indexing_grace_cache", None)
    if isinstance(guard_map, dict):
        g_entry = guard_map.get(sym)
        if isinstance(g_entry, dict):
            g_sell_mono = max(
                safe_float(g_entry.get("last_sell_fill_mono"), 0.0),
                safe_float(g_entry.get("last_cycle_end_mono"), 0.0),
            )
            if g_sell_mono > 0.0:
                elapsed_g = now_mono - g_sell_mono
                if 0.0 <= elapsed_g < POST_SELL_TO_BUY_SHIELD_SEC:
                    return True, round(
                        POST_SELL_TO_BUY_SHIELD_SEC - elapsed_g, 1
                    )

    state_obj = (
        st
        if isinstance(st, dict)
        else (
            context.ledger.get_state(sym)
            if hasattr(context, "ledger")
            else {}
        )
    )
    last_sell_epoch = max(
        safe_float(state_obj.get("last_sell_fill_ts"), 0.0),
        safe_float(state_obj.get("last_sub_sell_fill_ts"), 0.0),
        safe_float(state_obj.get("last_cycle_end_ts"), 0.0),
        safe_float(state_obj.get("last_sub_cycle_end_ts"), 0.0),
    )
    if last_sell_epoch > 0.0:
        elapsed_epoch = time.time() - last_sell_epoch
        if 0.0 <= elapsed_epoch < POST_SELL_TO_BUY_SHIELD_SEC:
            return True, round(POST_SELL_TO_BUY_SHIELD_SEC - elapsed_epoch, 1)

    return False, 0.0


def update_exit_snapshot_on_hold(
    context: Any,
    symbol: str = TARGET_SYMBOL,
    holdings_qty: int = 0,
    avg_price: float = 0.0,
    live_price: float = 0.0,
) -> Dict[str, Any]:
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    snap_map: Dict[str, Dict[str, Any]] = getattr(
        context, "exit_snapshot_cache", {}
    )
    prev = snap_map.get(sym) if isinstance(snap_map.get(sym), dict) else {}

    lp = safe_float(live_price, 0.0)
    ap = safe_float(avg_price, safe_float(prev.get("last_avg_price"), 0.0))
    qty = max(
        0, safe_int(holdings_qty, safe_int(prev.get("last_holdings_qty"), 0))
    )

    updated = dict(prev)
    updated.update(
        {
            "symbol": sym,
            "last_holdings_qty": qty,
            "last_avg_price": ap,
            "last_live_price": (
                lp if lp > 0.0 else safe_float(prev.get("last_live_price"), ap)
            ),
            "last_sweep_price": safe_float(prev.get("last_sweep_price"), 0.0),
            "last_sweep_reason": str(prev.get("last_sweep_reason") or ""),
            "updated_ts": time.time(),
        }
    )
    if isinstance(snap_map, dict):
        snap_map[sym] = updated
    return updated


# ---------------------------------------------------------------------------
# [핵심 1] 목표 하한가 직결 지정가(LIMIT) 다중 그리드(본+서브) 스나이퍼 매도 발주
# ---------------------------------------------------------------------------
async def execute_bulletproof_sell_sweep(
    context: Any,
    symbol: str = TARGET_SYMBOL,
    holdings_qty: int = 1,
    sweep_price: float = 0.0,
    min_floor_price: float = 0.0,
    reason_tag: str = "SELL_L1_ONLY",
    pending_sell_indices: Optional[Sequence[int]] = None,
    pending_sub_sell_indices: Optional[Sequence[int]] = None,
) -> Dict[str, Any]:
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    target_sell_qty = max(1, safe_int(holdings_qty, 1))
    floor_p = max(
        0.01,
        math.ceil((safe_float(min_floor_price, 0.0) - 1e-9) * 100.0) / 100.0,
    )
    raw_sp = max(
        0.01,
        math.floor((safe_float(sweep_price, 0.0) + 1e-9) * 100.0) / 100.0,
    )
    sp = max(floor_p, raw_sp)
    clean_indices = sorted(
        {
            safe_int(x, -1)
            for x in (pending_sell_indices or [])
            if safe_int(x, -1) >= 0
        }
    )
    clean_sub_indices = sorted(
        {
            safe_int(x, -1)
            for x in (pending_sub_sell_indices or [])
            if safe_int(x, -1) >= 0
        }
    )

    now_est = datetime.now(EST_TZ)
    hm_now = now_est.hour * 100 + now_est.minute
    is_ext_session = is_extended_sell_only_window(hm_now, now_est=now_est)

    snap_map: Dict[str, Dict[str, Any]] = getattr(
        context, "exit_snapshot_cache", {}
    )
    if isinstance(snap_map, dict):
        snap_entry = (
            snap_map.get(sym) if isinstance(snap_map.get(sym), dict) else {}
        )
        snap_entry["last_sweep_price"] = sp
        snap_entry["last_sweep_reason"] = str(reason_tag or "SELL_L1_ONLY")
        snap_entry["last_holdings_qty"] = target_sell_qty
        snap_map[sym] = snap_entry

    async with context.in_memory_ordering_lock:
        st = context.ledger.get_state(sym)
        sell_oid = str(st.get("sell_order_id") or "").strip()

        if sell_oid:
            return {
                "status": "SELL_ORDER_ALREADY_ACTIVE",
                "symbol": sym,
                "orderId": sell_oid,
                "sweep_price": safe_float(st.get("target_sell_price"), sp),
                "qty": target_sell_qty,
                "reason": reason_tag,
            }

        latest_open = await context.api.find_latest_open_order_id(
            sym, side="SELL"
        )
        if latest_open:
            try:
                await context.api.cancel_order(latest_open)
            except Exception:
                pass

        sellable_q = 0
        deadline = time.monotonic() + SELLABLE_QTY_POLL_WAIT_SEC
        while time.monotonic() < deadline:
            sellable_q = await context.api.get_sellable_quantity(sym)
            if sellable_q >= target_sell_qty:
                break
            await asyncio.sleep(SELLABLE_QTY_POLL_INTERVAL_SEC)

        if is_ext_session and sellable_q <= 0:
            mark_extended_sell_restriction_cooldown(
                context,
                symbol=sym,
                cooldown_sec=EXTENDED_NO_SELLABLE_RETRY_COOLDOWN_SEC,
                reason="EXTENDED_SELLABLE_ZERO_RETRY_5S",
            )
            logger.debug(
                "🔇 [%s] 장외(데이/애프터) 매도가능수량 일시 0주 감지 -> 60초 잠금 대신 %.1f초 후 즉시 재타격 대기",
                sym,
                EXTENDED_NO_SELLABLE_RETRY_COOLDOWN_SEC,
            )
            return {
                "status": "SILENT_EXTENDED_SELL_RESTRICTED",
                "symbol": sym,
                "reason": "EXTENDED_SELLABLE_ZERO_RETRY_5S",
                "retry_after_sec": EXTENDED_NO_SELLABLE_RETRY_COOLDOWN_SEC,
            }

        final_qty = (
            min(target_sell_qty, sellable_q)
            if sellable_q > 0
            else target_sell_qty
        )
        cid = generate_client_order_id(prefix="S1M")
        try:
            ord_res = await context.api.create_order(
                symbol=sym,
                side="SELL",
                quantity=final_qty,
                price=sp,
                order_type="LIMIT",
                time_in_force="DAY",
                client_order_id=cid,
                enforce_daymarket_block=False,
            )
            new_oid = str(ord_res.get("orderId") or "").strip()
            await context.ledger.update_state(
                sym,
                sell_order_id=new_oid,
                client_order_id=cid,
                ordered_qty=final_qty,
                target_sell_price=sp,
                pending_sell_mode=str(reason_tag or "SELL_L1_ONLY"),
                pending_sell_indices=clean_indices,
                pending_sub_sell_indices=clean_sub_indices,
                last_modify_mono=time.monotonic(),
                last_sell_gate_eval_ts=0.0,
            )
            context.wakeup_event.set()
            logger.info(
                "🔥 [%s] 1.5초 실시간 타점 다중익절 스나이퍼 매도 발사(%s · main=%s · sub=%s) 완료: %d주 @ 지정가 $%.2f (목표하한 $%.2f · orderId=%s)",
                sym,
                reason_tag,
                clean_indices,
                clean_sub_indices,
                final_qty,
                sp,
                floor_p,
                new_oid,
            )
            return {
                "status": "NEW_SELL_SWEEP_OK",
                "symbol": sym,
                "orderId": new_oid,
                "sweep_price": sp,
                "qty": final_qty,
                "reason": reason_tag,
                "sold_indices": clean_indices,
                "sub_sold_indices": clean_sub_indices,
            }
        except _NonRetryableApiError as api_err:
            err_code_l = str(getattr(api_err, "error_code", "") or "").lower()
            is_restrict_or_closed = any(
                k in err_code_l
                for k in (
                    "order-hours-closed",
                    "stock-restricted",
                    "market-closed",
                    "order-type-not-allowed",
                    "market-not-supported",
                    "maintenance",
                    "internal-error",
                )
            )
            if is_ext_session or is_restrict_or_closed:
                mark_extended_sell_restriction_cooldown(
                    context,
                    symbol=sym,
                    cooldown_sec=EXTENDED_SELL_RESTRICTION_COOLDOWN_SEC,
                    reason=err_code_l or "EXTENDED_API_RESTRICTED",
                )
                logger.debug(
                    "🔇 [%s] 장외/종목제한 매도 보류(묵음 쿨다운 60초): %s",
                    sym,
                    api_err,
                )
                return {
                    "status": "SILENT_EXTENDED_SELL_RESTRICTED",
                    "symbol": sym,
                    "error_code": err_code_l,
                }
            logger.error(
                "🚨 [%s] 스나이퍼 매도 발사(%s) 실패: %s",
                sym,
                reason_tag,
                api_err,
            )
            return {
                "status": "SWEEP_FAILED",
                "symbol": sym,
                "error": str(api_err),
            }
        except Exception as exc:
            if is_ext_session:
                mark_extended_sell_restriction_cooldown(
                    context,
                    symbol=sym,
                    cooldown_sec=EXTENDED_NO_SELLABLE_RETRY_COOLDOWN_SEC,
                    reason="EXTENDED_TRANSIENT_EXCEPTION_5S",
                )
                logger.debug(
                    "🔇 [%s] 장외 매도 일시 통신 예외(묵음 쿨다운 %.1f초): %s",
                    sym,
                    EXTENDED_NO_SELLABLE_RETRY_COOLDOWN_SEC,
                    exc,
                )
                return {
                    "status": "SILENT_EXTENDED_SELL_RESTRICTED",
                    "symbol": sym,
                    "error": str(exc),
                }
            logger.error(
                "🚨 [%s] 스나이퍼 매도 발사(%s) 실패: %s",
                sym,
                reason_tag,
                exc,
            )
            return {"status": "SWEEP_FAILED", "symbol": sym, "error": str(exc)}
# ---------------------------------------------------------------------------
# [핵심 2] 실물 매도 FILLED 정산 · 서브/본그리드 분리 정산(Case 88) · 최고도달회차 잠금 유지(Case 87) · 사이클 수익 추적 및 0주 리셋 · 바벨 모드 별도 수익금고 격리 & 60/30/10 리밸런싱 · 0주 달성 시 실전 암살자 자동 승격 인계
# ---------------------------------------------------------------------------
async def _commit_filled_sell_and_reanchor_ledger(
    context: Any,
    filled_qty: int,
    avg_fill_price: float,
    sell_mode: str,
    settled_order_id: str = "",
    actual_sell_fee_usd: Optional[float] = None,
) -> Dict[str, Any]:
    """
    # MODIFIED [🎯 1 ~ 🎯 4 & Case 19, 59 ~ 91 + 바벨 모드(실현수익 별도 금고 영구 격리 및 0주 졸업 60/30/10 리밸런싱) + 실전 암살자 0주 인계]:
    """
    st = context.ledger.get_state(TARGET_SYMBOL)
    buckets = buckets_from_dicts(st.get("buckets", []))
    sub_buckets = buckets_from_dicts(st.get("sub_buckets", []))
    fill_p = round(max(0.01, safe_float(avg_fill_price, 0.01)), 4)
    q_filled = max(1, safe_int(filled_qty, 1))
    mode = str(
        sell_mode or st.get("pending_sell_mode") or "SELL_L1_ONLY"
    ).upper()
    eff_oid = str(settled_order_id or st.get("sell_order_id") or "").strip()
    eff_rt_pct = resolve_effective_round_trip_fee_rate_pct(state_dict=st)
    eff_merge_mode = str(
        st.get("grid_merge_mode") or DEFAULT_GRID_MERGE_MODE
    ).upper()
    eff_sub_merge_mode = str(
        st.get("sub_merge_mode") or SUB_MERGE_MODE_L1_L3
    ).upper()
    portion_mode = (
        str(st.get("portion_mode") or PORTION_MODE_COMPOUND).upper().strip()
    )
    is_barbell = is_barbell_mode(portion_mode)
    is_simple_mode = (not is_barbell) and is_simple_income_mode(portion_mode)

    settled_oids: List[str] = list(st.get("last_settled_order_ids") or [])
    if eff_oid and eff_oid not in settled_oids:
        settled_oids.append(eff_oid)
    settled_oids = settled_oids[-50:]

    if not buckets and not sub_buckets:
        now_empty_epoch = time.time()
        mark_post_sell_time_shield(
            context=context,
            symbol=TARGET_SYMBOL,
            fill_price=fill_p,
            sold_qty=q_filled,
            is_cycle_end=True,
        )
        await context.ledger.update_state(
            TARGET_SYMBOL,
            cycle_ratchet_max_lots=0,
            sub_ratchet_max_lots=0,
            l1_target_quota_qty=0,
            sub_l1_target_quota_qty=0,
            cycle_realized_gross_usd=0.0,
            cycle_realized_fee_usd=0.0,
            cycle_realized_net_usd=0.0,
            cycle_sub_realized_net_usd=0.0,
            cycle_sell_events=0,
            cycle_leftover_saved_usd=0.0,
            last_sell_fill_ts=now_empty_epoch,
            last_cycle_end_ts=now_empty_epoch,
            last_sub_sell_fill_ts=now_empty_epoch,
            last_sub_cycle_end_ts=now_empty_epoch,
            last_sell_gate_eval_ts=0.0,
            last_reentry_eval_ts=0.0,
            last_sub_reentry_eval_ts=0.0,
            waiting_reserve_deposit=False,
            waiting_reserve_deposit_alert_sent=False,
            required_reserve_deposit_usd=0.0,
            last_reserve_check_ts=0.0,
            sell_order_id="",
            ordered_qty=0,
            target_sell_price=0.0,
            pending_sell_mode="",
            pending_sell_indices=[],
            pending_sub_sell_indices=[],
            last_settled_order_ids=settled_oids,
        )
        return {"status": "NO_BUCKETS_TO_SETTLE"}

    rem_fill_to_alloc = q_filled

    # 1) Default-ON 3층 서브 그리드(sub_buckets) 매도 수량 배분 및 잔여 서브 지층 산출 (Case 88)
    was_sub_non_empty = bool(len(sub_buckets) > 0)
    was_sub_active_l1 = has_active_l1_bucket(sub_buckets)
    orig_sub_l1_qty = (
        sub_buckets[0].qty if (was_sub_active_l1 and sub_buckets) else 0
    )
    raw_sub_p_indices = st.get("pending_sub_sell_indices")
    sub_target_indices: List[int] = []
    if isinstance(raw_sub_p_indices, list) and raw_sub_p_indices:
        sub_target_indices = sorted(
            {
                safe_int(idx, -1)
                for idx in raw_sub_p_indices
                if 0 <= safe_int(idx, -1) < len(sub_buckets)
            }
        )

    if not sub_target_indices and rem_fill_to_alloc > 0 and sub_buckets:
        if mode in (
            "SELL_SUB_ALL_GRAD",
            "SELL_SUB_WMA_UPPER",
        ) or (mode.startswith("SELL_SUB_") and len(sub_buckets) == 1):
            sub_target_indices = list(range(len(sub_buckets)))
        elif mode in ("SELL_SUB_L1_ONLY", "SELL_SUB_L1_AND_GRID"):
            sub_target_indices = [0]

    sub_target_set: Set[int] = set(sub_target_indices)
    sold_sub_l1_flag = bool(
        was_sub_active_l1 and (0 in sub_target_set) and rem_fill_to_alloc > 0
    )

    sold_sub_buckets: List[StratumBucket] = []
    rem_sub_buckets: List[StratumBucket] = []
    sold_sub_merged_bucket_flag = False

    for s_idx, sb in enumerate(sub_buckets):
        if s_idx not in sub_target_set or rem_fill_to_alloc <= 0:
            rem_sub_buckets.append(sb)
            continue

        if rem_fill_to_alloc >= sb.qty:
            sold_sub_buckets.append(sb)
            rem_fill_to_alloc -= sb.qty
            if max(1, sb.lot_count) > 1:
                sold_sub_merged_bucket_flag = True
        else:
            part_sq = rem_fill_to_alloc
            rem_fill_to_alloc = 0
            s_ratio = min(1.0, float(part_sq) / float(sb.qty))
            sold_scost_part = round(sb.actual_cost_usd * s_ratio, 4)
            rem_sq = sb.qty - part_sq
            rem_scost_part = round(
                max(0.01 * float(rem_sq), sb.actual_cost_usd - sold_scost_part),
                4,
            )
            sold_sub_buckets.append(
                StratumBucket(
                    qty=part_sq,
                    book_price=sb.book_price,
                    book_invested_usd=sold_scost_part,
                    actual_cost_usd=sold_scost_part,
                    lot_count=1,
                    lot_type=sb.lot_type,
                )
            )
            rem_sub_buckets.append(
                StratumBucket(
                    qty=rem_sq,
                    book_price=sb.book_price,
                    book_invested_usd=rem_scost_part,
                    actual_cost_usd=rem_scost_part,
                    lot_count=max(1, sb.lot_count),
                    lot_type=sb.lot_type,
                )
            )
            if s_idx == 0 and was_sub_active_l1:
                sold_sub_l1_flag = False

    # 2) 1층 ~ 7층 본 그리드(buckets) 매도 수량 배분 및 잔여 지층 산출
    was_active_l1 = has_active_l1_bucket(buckets)
    main_upper_start_idx = 1 if was_active_l1 else 0
    orig_l1_qty = buckets[0].qty if (was_active_l1 and buckets) else 0
    raw_p_indices = st.get("pending_sell_indices")
    target_indices: List[int] = []
    if isinstance(raw_p_indices, list) and raw_p_indices:
        target_indices = sorted(
            {
                safe_int(idx, -1)
                for idx in raw_p_indices
                if 0 <= safe_int(idx, -1) < len(buckets)
            }
        )

    if (
        not target_indices
        and not sub_target_indices
        and rem_fill_to_alloc > 0
        and buckets
        and not mode.startswith("SELL_SUB_")
    ):
        if (
            mode in ("SELL_ALL_GRAD", "SELL_L2_GRAD", "SELL_WMA_UPPER")
            or len(buckets) == 1
        ):
            target_indices = list(range(len(buckets)))
        else:
            target_indices = [0]

    target_set: Set[int] = set(target_indices)
    sold_l1_flag = bool(
        was_active_l1 and (0 in target_set) and rem_fill_to_alloc > 0
    )
    sold_main_upper_flag = False

    sold_buckets: List[StratumBucket] = []
    rem_buckets: List[StratumBucket] = []

    for idx, b in enumerate(buckets):
        if idx not in target_set or rem_fill_to_alloc <= 0:
            rem_buckets.append(b)
            continue

        if idx >= main_upper_start_idx:
            sold_main_upper_flag = True

        if rem_fill_to_alloc >= b.qty:
            sold_buckets.append(b)
            rem_fill_to_alloc -= b.qty
        else:
            part_q = rem_fill_to_alloc
            rem_fill_to_alloc = 0
            ratio = min(1.0, float(part_q) / float(b.qty))
            sold_cost_part = round(b.actual_cost_usd * ratio, 4)
            rem_q = b.qty - part_q
            rem_cost_part = round(
                max(0.01 * float(rem_q), b.actual_cost_usd - sold_cost_part), 4
            )
            sold_buckets.append(
                StratumBucket(
                    qty=part_q,
                    book_price=b.book_price,
                    book_invested_usd=sold_cost_part,
                    actual_cost_usd=sold_cost_part,
                    lot_count=1,
                    lot_type=b.lot_type,
                )
            )
            rem_buckets.append(
                StratumBucket(
                    qty=rem_q,
                    book_price=b.book_price,
                    book_invested_usd=rem_cost_part,
                    actual_cost_usd=rem_cost_part,
                    lot_count=max(1, b.lot_count),
                    lot_type=b.lot_type,
                )
            )
            if idx == 0 and was_active_l1:
                sold_l1_flag = False

    if rem_fill_to_alloc > 0 and rem_sub_buckets:
        fb_rem_sub: List[StratumBucket] = []
        for idx_sf, sbf in enumerate(rem_sub_buckets):
            if rem_fill_to_alloc <= 0:
                fb_rem_sub.append(sbf)
                continue
            if rem_fill_to_alloc >= sbf.qty:
                sold_sub_buckets.append(sbf)
                rem_fill_to_alloc -= sbf.qty
                if idx_sf == 0 and was_sub_active_l1 and not sold_sub_l1_flag:
                    sold_sub_l1_flag = True
                if max(1, sbf.lot_count) > 1:
                    sold_sub_merged_bucket_flag = True
            else:
                part_sq = rem_fill_to_alloc
                rem_fill_to_alloc = 0
                s_ratio = min(1.0, float(part_sq) / float(sbf.qty))
                sold_scost_part = round(sbf.actual_cost_usd * s_ratio, 4)
                rem_sq = sbf.qty - part_sq
                rem_scost_part = round(
                    max(
                        0.01 * float(rem_sq),
                        sbf.actual_cost_usd - sold_scost_part,
                    ),
                    4,
                )
                sold_sub_buckets.append(
                    StratumBucket(
                        qty=part_sq,
                        book_price=sbf.book_price,
                        book_invested_usd=sold_scost_part,
                        actual_cost_usd=sold_scost_part,
                        lot_count=1,
                        lot_type=sbf.lot_type,
                    )
                )
                fb_rem_sub.append(
                    StratumBucket(
                        qty=rem_sq,
                        book_price=sbf.book_price,
                        book_invested_usd=rem_scost_part,
                        actual_cost_usd=rem_scost_part,
                        lot_count=max(1, sbf.lot_count),
                        lot_type=sbf.lot_type,
                    )
                )
        rem_sub_buckets = fb_rem_sub

    if rem_fill_to_alloc > 0 and rem_buckets:
        fallback_rem: List[StratumBucket] = []
        for idx_f, bf in enumerate(rem_buckets):
            if rem_fill_to_alloc <= 0:
                fallback_rem.append(bf)
                continue
            if rem_fill_to_alloc >= bf.qty:
                sold_buckets.append(bf)
                rem_fill_to_alloc -= bf.qty
                if idx_f == 0 and was_active_l1 and not sold_l1_flag:
                    sold_l1_flag = True
                else:
                    sold_main_upper_flag = True
            else:
                part_q = rem_fill_to_alloc
                rem_fill_to_alloc = 0
                ratio = min(1.0, float(part_q) / float(bf.qty))
                sold_cost_part = round(bf.actual_cost_usd * ratio, 4)
                rem_q = bf.qty - part_q
                rem_cost_part = round(
                    max(
                        0.01 * float(rem_q),
                        bf.actual_cost_usd - sold_cost_part,
                    ),
                    4,
                )
                sold_buckets.append(
                    StratumBucket(
                        qty=part_q,
                        book_price=bf.book_price,
                        book_invested_usd=sold_cost_part,
                        actual_cost_usd=sold_cost_part,
                        lot_count=1,
                        lot_type=bf.lot_type,
                    )
                )
                fallback_rem.append(
                    StratumBucket(
                        qty=rem_q,
                        book_price=bf.book_price,
                        book_invested_usd=rem_cost_part,
                        actual_cost_usd=rem_cost_part,
                        lot_count=max(1, bf.lot_count),
                        lot_type=bf.lot_type,
                    )
                )
                if not (idx_f == 0 and was_active_l1):
                    sold_main_upper_flag = True
        rem_buckets = fallback_rem

    sold_grid_q = sum(b.qty for b in sold_buckets)
    sold_grid_cost = round(sum(b.actual_cost_usd for b in sold_buckets), 4)
    sold_sub_q = sum(sb.qty for sb in sold_sub_buckets)
    sold_sub_cost = round(sum(sb.actual_cost_usd for sb in sold_sub_buckets), 4)

    if rem_buckets:
        if was_active_l1 and not sold_l1_flag:
            active_b1 = rem_buckets[0]
            re_uppers = relabel_upper_grid_tiers(
                rem_buckets[1:],
                max_tiers=MAX_GRID_TIERS_7,
                merge_mode=eff_merge_mode,
            )
            rem_buckets = [active_b1] + re_uppers
        else:
            rem_buckets = relabel_upper_grid_tiers(
                rem_buckets,
                max_tiers=MAX_GRID_TIERS_7,
                merge_mode=eff_merge_mode,
            )

    if rem_sub_buckets:
        if was_sub_active_l1 and not sold_sub_l1_flag:
            active_sb1 = rem_sub_buckets[0]
            re_sub_uppers = relabel_sub_upper_grid_tiers(
                rem_sub_buckets[1:],
                max_tiers=SUB_MAX_TIERS_3,
                merge_mode=eff_sub_merge_mode,
            )
            rem_sub_buckets = [active_sb1] + re_sub_uppers
        else:
            rem_sub_buckets = relabel_sub_upper_grid_tiers(
                rem_sub_buckets,
                max_tiers=SUB_MAX_TIERS_3,
                merge_mode=eff_sub_merge_mode,
            )

    rem_has_active_l1 = has_active_l1_bucket(rem_buckets)
    if not rem_buckets or not rem_has_active_l1 or sold_l1_flag:
        next_l1_target_q = 0
    elif orig_l1_qty > 0 and rem_buckets[0].qty < orig_l1_qty:
        next_l1_target_q = rem_buckets[0].qty
    else:
        prev_target_q = max(0, safe_int(st.get("l1_target_quota_qty"), 0))
        next_l1_target_q = max(rem_buckets[0].qty, prev_target_q)

    rem_sub_has_active_l1 = has_active_l1_bucket(rem_sub_buckets)
    if not rem_sub_buckets or not rem_sub_has_active_l1 or sold_sub_l1_flag:
        next_sub_l1_target_q = 0
    elif orig_sub_l1_qty > 0 and rem_sub_buckets[0].qty < orig_sub_l1_qty:
        next_sub_l1_target_q = rem_sub_buckets[0].qty
    else:
        prev_sub_target_q = max(
            0, safe_int(st.get("sub_l1_target_quota_qty"), 0)
        )
        next_sub_l1_target_q = max(rem_sub_buckets[0].qty, prev_sub_target_q)

    sold_q = sold_grid_q + sold_sub_q
    sold_actual_cost = round(sold_grid_cost + sold_sub_cost, 4)
    pnl_info = calc_sell_realized_pnl(
        sold_qty=sold_q,
        sell_exec_price=fill_p,
        sold_actual_cost_usd=sold_actual_cost,
        round_trip_fee_rate_pct=eff_rt_pct,
        actual_sell_fee_usd=actual_sell_fee_usd,
    )
    gross_pnl = pnl_info["gross_pnl_usd"]
    fee_usd = pnl_info["fee_usd"]
    net_pnl = pnl_info["net_pnl_usd"]
    net_rate = pnl_info["net_rate_pct"]

    sub_gross_pnl = 0.0
    sub_fee_usd = 0.0
    sub_net_pnl = 0.0
    if sold_sub_q > 0:
        sub_sell_fee: Optional[float] = None
        if (
            actual_sell_fee_usd is not None
            and safe_float(actual_sell_fee_usd, 0.0) > 0.0
            and sold_q > 0
        ):
            sub_sell_fee = round(
                safe_float(actual_sell_fee_usd, 0.0)
                * (float(sold_sub_q) / float(sold_q)),
                4,
            )
        s_pnl_info = calc_sell_realized_pnl(
            sold_qty=sold_sub_q,
            sell_exec_price=fill_p,
            sold_actual_cost_usd=sold_sub_cost,
            round_trip_fee_rate_pct=eff_rt_pct,
            actual_sell_fee_usd=sub_sell_fee,
        )
        sub_gross_pnl = s_pnl_info["gross_pnl_usd"]
        sub_fee_usd = s_pnl_info["fee_usd"]
        sub_net_pnl = s_pnl_info["net_pnl_usd"]

    is_grid_empty = bool(len(rem_buckets) == 0)
    is_sub_empty = bool(len(rem_sub_buckets) == 0)
    is_graduated_zero = bool(is_grid_empty and is_sub_empty)
    is_sub_without_main_sell = bool(
        sold_sub_q > 0 and sold_grid_q == 0
    )

    prev_ratchet_lots = max(0, safe_int(st.get("cycle_ratchet_max_lots"), 0))
    rem_held_lots = sum(max(1, b.lot_count) for b in rem_buckets)
    next_ratchet_max_lots = (
        0 if is_grid_empty else max(rem_held_lots, prev_ratchet_lots)
    )

    prev_sub_ratchet_lots = max(0, safe_int(st.get("sub_ratchet_max_lots"), 0))
    rem_sub_held_lots = sum(max(1, sb.lot_count) for sb in rem_sub_buckets)
    next_sub_ratchet_max_lots = (
        0 if is_sub_empty else max(rem_sub_held_lots, prev_sub_ratchet_lots)
    )

    old_anchor_p = safe_float(st.get("anchor_price"), fill_p)
    old_cycle_min_p = safe_float(st.get("cycle_min_buy_price"), 0.0)
    if sold_grid_q > 0 or is_grid_empty:
        next_anchor_p = fill_p
        next_cycle_min_p = (
            round(old_cycle_min_p, 4) if not is_grid_empty else 0.0
        )
    else:
        next_anchor_p = old_anchor_p if old_anchor_p > 0.0 else fill_p
        next_cycle_min_p = round(old_cycle_min_p, 4)

    old_sub_anchor_p = safe_float(st.get("sub_anchor_price"), fill_p)
    old_sub_cycle_min_p = safe_float(st.get("sub_cycle_min_buy_price"), 0.0)
    if sold_sub_q > 0 or is_sub_empty:
        next_sub_anchor_p = fill_p
        next_sub_cycle_min_p = (
            round(old_sub_cycle_min_p, 4) if not is_sub_empty else 0.0
        )
    else:
        next_sub_anchor_p = (
            old_sub_anchor_p if old_sub_anchor_p > 0.0 else fill_p
        )
        next_sub_cycle_min_p = round(old_sub_cycle_min_p, 4)

    tot_sell_ev = safe_int(st.get("total_sell_events"), 0) + 1
    tot_sold_sh = safe_int(st.get("total_sold_shares"), 0) + sold_q
    win_ev = safe_int(st.get("win_sell_events"), 0) + (
        1 if net_pnl > 0.0 else 0
    )
    day_sell_ev = safe_int(st.get("daily_sell_events"), 0) + 1
    day_main_sell_cnt = safe_int(st.get("daily_main_sell_cnt"), 0) + (
        1 if sold_grid_q > 0 else 0
    )
    next_main_frozen_d = (
        0
        if (sold_grid_q > 0 or is_grid_empty)
        else max(0, safe_int(st.get("main_consec_frozen_days"), 0))
    )

    sub_sell_inc = 1 if sold_sub_q > 0 else 0
    sub_sell_ev = safe_int(st.get("sub_sell_events"), 0) + sub_sell_inc
    sub_sold_sh = safe_int(st.get("sub_sold_shares"), 0) + sold_sub_q
    day_sub_sell_cnt = (
        safe_int(st.get("daily_sub_sell_cnt"), 0) + sub_sell_inc
    )
    day_sub_sell_ev = (
        safe_int(st.get("daily_sub_sell_events"), 0) + sub_sell_inc
    )
    sub_comp_inc = 1 if (was_sub_non_empty and is_sub_empty) else 0
    sub_comp_cycles = (
        safe_int(st.get("sub_completed_cycles"), 0) + sub_comp_inc
    )
    sub_m_esc_inc = (
        1 if (sold_sub_merged_bucket_flag and not is_sub_empty) else 0
    )
    sub_m_esc_cnt = (
        safe_int(st.get("sub_merged_indiv_escape_cnt"), 0) + sub_m_esc_inc
    )
    sub_gross_cum = round(
        safe_float(st.get("sub_realized_gross_usd"), 0.0) + sub_gross_pnl, 4
    )
    sub_fee_cum = round(
        safe_float(st.get("sub_realized_fee_usd"), 0.0) + sub_fee_usd, 4
    )
    sub_net_cum = round(
        safe_float(st.get("sub_realized_net_usd"), 0.0) + sub_net_pnl, 4
    )
    sub_net_day = round(
        safe_float(st.get("daily_sub_realized_net_usd"), 0.0) + sub_net_pnl, 4
    )
    next_sub_frozen_d = (
        0
        if (sold_sub_q > 0 or is_sub_empty)
        else max(0, safe_int(st.get("sub_consec_frozen_days"), 0))
    )

    rem_upper_cnt = (
        max(0, len(rem_buckets) - (1 if rem_has_active_l1 else 0))
        if rem_buckets
        else 0
    )
    if sold_main_upper_flag and sold_grid_q > 0:
        if rem_upper_cnt == 0:
            wma_inc = 1
            indiv_inc = 0
        else:
            wma_inc = 0
            indiv_inc = 1
    else:
        wma_inc = 0
        indiv_inc = 0

    indiv_cnt = safe_int(st.get("indiv_grid_sell_cnt"), 0) + indiv_inc
    day_indiv_cnt = (
        safe_int(st.get("daily_indiv_grid_sell_cnt"), 0) + indiv_inc
    )
    wma_cnt = safe_int(st.get("wma_grad_sell_cnt"), 0) + wma_inc
    day_wma_cnt = safe_int(st.get("daily_wma_grad_sell_cnt"), 0) + wma_inc

    cum_gross = round(
        safe_float(st.get("cumulative_realized_gross_usd"), 0.0) + gross_pnl, 4
    )
    cum_fee = round(
        safe_float(st.get("cumulative_realized_fee_usd"), 0.0) + fee_usd, 4
    )
    cum_net = round(
        safe_float(st.get("cumulative_realized_net_usd"), 0.0) + net_pnl, 4
    )
    day_net = round(
        safe_float(st.get("daily_realized_net_usd"), 0.0) + net_pnl, 4
    )

    # MODIFIED: 수동 부분손절(prev_cyc_net < 0) 후 익절 시 코어 결손 우선 보전 후 순흑자만 금고 격리
    prev_cyc_net_b = safe_float(st.get("cycle_realized_net_usd"), 0.0)
    vault_delta_pnl = round(
        max(0.0, net_pnl + min(0.0, prev_cyc_net_b)), 4
    )
    prev_vault_locked = max(
        0.0, safe_float(st.get("vaulted_profit_locked_usd"), 0.0)
    )
    next_vault_locked = (
        round(prev_vault_locked + vault_delta_pnl, 4)
        if is_barbell
        else prev_vault_locked
    )

    cur_cyc_gross = round(
        safe_float(st.get("cycle_realized_gross_usd"), 0.0) + gross_pnl, 4
    )
    cur_cyc_fee = round(
        safe_float(st.get("cycle_realized_fee_usd"), 0.0) + fee_usd, 4
    )
    cur_cyc_net = round(
        safe_float(st.get("cycle_realized_net_usd"), 0.0) + net_pnl, 4
    )
    cur_cyc_sub_net = round(
        safe_float(st.get("cycle_sub_realized_net_usd"), 0.0) + sub_net_pnl, 4
    )
    cur_cyc_ev = max(0, safe_int(st.get("cycle_sell_events"), 0)) + 1
    prev_cyc_saved = round(
        safe_float(st.get("cycle_leftover_saved_usd"), 0.0), 4
    )
    prev_last_cyc_net = round(
        safe_float(st.get("last_cycle_realized_net_usd"), 0.0), 4
    )
    prev_last_cyc_ev = max(0, safe_int(st.get("last_cycle_sell_events"), 0))
    prev_comp_main_cycles = max(
        0, safe_int(st.get("completed_main_cycles"), 0)
    )

    if is_graduated_zero:
        next_last_cyc_net = cur_cyc_net
        next_last_cyc_ev = cur_cyc_ev
        next_comp_main_cycles = prev_comp_main_cycles + 1
        next_cyc_gross = 0.0
        next_cyc_fee = 0.0
        next_cyc_net = 0.0
        next_cyc_sub_net = 0.0
        next_cyc_ev = 0
        next_cyc_saved = 0.0
    else:
        next_last_cyc_net = prev_last_cyc_net
        next_last_cyc_ev = prev_last_cyc_ev
        next_comp_main_cycles = prev_comp_main_cycles
        next_cyc_gross = cur_cyc_gross
        next_cyc_fee = cur_cyc_fee
        next_cyc_net = cur_cyc_net
        next_cyc_sub_net = cur_cyc_sub_net
        next_cyc_ev = cur_cyc_ev
        next_cyc_saved = prev_cyc_saved

    init_seed = max(
        100.0, safe_float(st.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD)
    )
    cur_inj_res_usd = max(
        0.0, safe_float(st.get("injected_reserve_usd"), 0.0)
    )
    cur_used_res_cnt = max(
        0, safe_int(st.get("used_reserve_portions_cnt"), 0)
    )
    cum_repaid_usd = max(
        0.0, safe_float(st.get("cumulative_reserve_repaid_usd"), 0.0)
    )
    repaid_this_time = 0.0
    next_inj_res_usd = cur_inj_res_usd
    next_used_res_cnt = cur_used_res_cnt

    if (not is_barbell) and is_graduated_zero and cur_inj_res_usd > 0.0:
        repay_info = compute_reserve_repayment_on_zero(
            initial_seed_usd=init_seed,
            cumulative_realized_net_usd=cum_net,
            injected_reserve_usd=cur_inj_res_usd,
            used_reserve_portions_cnt=cur_used_res_cnt,
            max_reserve_portions=MAX_RESERVE_PORTIONS,
            portion_mode=portion_mode,
            vaulted_profit_locked_usd=next_vault_locked,
        )
        if bool(repay_info.get("did_repay")):
            repaid_this_time = round(
                safe_float(repay_info.get("repaid_usd"), 0.0), 4
            )
            next_inj_res_usd = round(
                safe_float(repay_info.get("rem_injected_reserve_usd"), 0.0), 4
            )
            next_used_res_cnt = max(
                0,
                safe_int(
                    repay_info.get("rem_used_reserve_portions_cnt"), 0
                ),
            )
            cum_repaid_usd = round(cum_repaid_usd + repaid_this_time, 4)
            logger.info(
                "🎓 [0주 졸업 예비시드 자동 상환 완료] 상환액=$%.2f · 잔여수혈잔액=$%.2f · 잔여수혈=%d회분",
                repaid_this_time,
                next_inj_res_usd,
                next_used_res_cnt,
            )

    now_sell_epoch = time.time()
    mark_post_sell_time_shield(
        context=context,
        symbol=TARGET_SYMBOL,
        fill_price=fill_p,
        sold_qty=sold_q,
        is_cycle_end=is_graduated_zero,
    )

    update_kwargs: Dict[str, Any] = {
        "buckets": buckets_to_dicts(rem_buckets),
        "sub_buckets": buckets_to_dicts(rem_sub_buckets),
        "anchor_price": next_anchor_p,
        "cycle_min_buy_price": next_cycle_min_p,
        "cycle_ratchet_max_lots": next_ratchet_max_lots,
        "ratchet_anchor_price": next_anchor_p,
        "cycle_reanchor_credit_usd": 0.0,
        "l1_target_quota_qty": next_l1_target_q,
        "sub_anchor_price": next_sub_anchor_p,
        "sub_cycle_min_buy_price": next_sub_cycle_min_p,
        "sub_ratchet_max_lots": next_sub_ratchet_max_lots,
        "sub_l1_target_quota_qty": next_sub_l1_target_q,
        "main_consec_frozen_days": next_main_frozen_d,
        "sub_consec_frozen_days": next_sub_frozen_d,
        "daily_main_sell_cnt": day_main_sell_cnt,
        "sub_sell_events": sub_sell_ev,
        "sub_sold_shares": sub_sold_sh,
        "daily_sub_sell_cnt": day_sub_sell_cnt,
        "daily_sub_sell_events": day_sub_sell_ev,
        "sub_completed_cycles": sub_comp_cycles,
        "sub_merged_indiv_escape_cnt": sub_m_esc_cnt,
        "sub_realized_gross_usd": sub_gross_cum,
        "sub_realized_fee_usd": sub_fee_cum,
        "sub_realized_net_usd": sub_net_cum,
        "daily_sub_realized_net_usd": sub_net_day,
        "used_reserve_portions_cnt": next_used_res_cnt,
        "injected_reserve_usd": next_inj_res_usd,
        "cumulative_reserve_repaid_usd": cum_repaid_usd,
        "vaulted_profit_locked_usd": next_vault_locked,
        "waiting_reserve_deposit": False,
        "waiting_reserve_deposit_alert_sent": False,
        "required_reserve_deposit_usd": 0.0,
        "last_reserve_check_ts": 0.0,
        "last_sell_fill_ts": now_sell_epoch,
        "last_sell_gate_eval_ts": 0.0,
        "last_reentry_eval_ts": 0.0,
        "last_sub_reentry_eval_ts": 0.0,
        "sell_order_id": "",
        "ordered_qty": 0,
        "target_sell_price": 0.0,
        "pending_sell_mode": "",
        "pending_sell_indices": [],
        "pending_sub_sell_indices": [],
        "last_settled_order_ids": settled_oids,
        "total_sell_events": tot_sell_ev,
        "total_sold_shares": tot_sold_sh,
        "win_sell_events": win_ev,
        "daily_sell_events": day_sell_ev,
        "indiv_grid_sell_cnt": indiv_cnt,
        "daily_indiv_grid_sell_cnt": day_indiv_cnt,
        "wma_grad_sell_cnt": wma_cnt,
        "daily_wma_grad_sell_cnt": day_wma_cnt,
        "cumulative_realized_gross_usd": cum_gross,
        "cumulative_realized_fee_usd": cum_fee,
        "cumulative_realized_net_usd": cum_net,
        "daily_realized_net_usd": day_net,
        "cycle_realized_gross_usd": next_cyc_gross,
        "cycle_realized_fee_usd": next_cyc_fee,
        "cycle_realized_net_usd": next_cyc_net,
        "cycle_sub_realized_net_usd": next_cyc_sub_net,
        "cycle_sell_events": next_cyc_ev,
        "cycle_leftover_saved_usd": next_cyc_saved,
        "last_cycle_realized_net_usd": next_last_cyc_net,
        "last_cycle_sell_events": next_last_cyc_ev,
        "completed_main_cycles": next_comp_main_cycles,
    }
    if sold_sub_q > 0:
        update_kwargs["last_sub_sell_fill_ts"] = now_sell_epoch
    if was_sub_non_empty and is_sub_empty:
        update_kwargs["last_sub_cycle_end_ts"] = now_sell_epoch
    if is_graduated_zero:
        update_kwargs["last_cycle_end_ts"] = now_sell_epoch

    updated_st = await context.ledger.update_state(
        TARGET_SYMBOL, **update_kwargs
    )

    # [바벨 모드 전용 훅] 별도 수익금고 영구 격리 및 전 구간(부분 익절 · 0주 졸업) 실시간 60/30/10 리밸런싱 실행
    barbell_vault_total = next_vault_locked
    repaid_to_vault_usd = 0.0
    pending_sgov_reb_usd = 0.0
    added_sgov_reb_usd = 0.0
    barbell_cash_b_usd = 0.0
    if is_barbell:
        barbell_rec = await record_barbell_realized_profit(
            context=context,
            net_pnl_usd=vault_delta_pnl,  # MODIFIED: 유령현금 이중계상 차단
            is_graduated_zero=is_graduated_zero,
            prev_soxl_injected_usd=cur_inj_res_usd,
            prev_soxl_used_portions_cnt=cur_used_res_cnt,
            cycle_realized_net_override=cur_cyc_net,
        )
        barbell_vault_total = safe_float(
            barbell_rec.get("vault_realized_profit_usd"), next_vault_locked
        )
        repaid_this_time = safe_float(
            barbell_rec.get("repaid_from_soxl_usd"), 0.0
        )
        next_inj_res_usd = safe_float(
            barbell_rec.get("rem_soxl_injected_usd"), 0.0
        )
        next_used_res_cnt = safe_int(
            barbell_rec.get("rem_soxl_used_portions_cnt"), 0
        )
        repaid_to_vault_usd = safe_float(
            barbell_rec.get("repaid_to_vault_usd"), 0.0
        )
        pending_sgov_reb_usd = safe_float(
            barbell_rec.get("pending_sgov_buy_budget_usd"), 0.0
        )
        added_sgov_reb_usd = safe_float(
            barbell_rec.get("added_sgov_buy_budget_usd"), 0.0
        )
        barbell_cash_b_usd = safe_float(
            barbell_rec.get("cash_bucket_usd"), 0.0
        )
        updated_st = context.ledger.get_state(TARGET_SYMBOL)

    # [실전 암살자 분리 전환 훅] SOXL == 0주 졸업 달성 시 예약된 [실전] 암살자 모드로 즉시 자동 인계!
    switched_to_live_assassin = False
    if is_graduated_zero:
        activate_fn = getattr(
            assassin_plugin, "activate_live_assassin_on_zero_soxl_if_armed", None
        )
        if callable(activate_fn):
            try:
                switched_to_live_assassin = bool(await activate_fn(context))
            except Exception as exc:
                logger.warning(
                    "0주 졸업 후 실전 암살자 자동 인계 훅 예외: %s", exc
                )

    context.wakeup_event.set()
    free_cash_now = safe_float(updated_st.get("free_cash_usd"), 0.0)

    now_est_dt = datetime.now(EST_TZ)
    hm_now = now_est_dt.hour * 100 + now_est_dt.minute
    is_ext_sell = is_extended_sell_only_window(hm_now, now_est=now_est_dt)
    is_late_cutoff_now = is_late_regular_new_cycle_cutoff_window(
        hm_now, now_est=now_est_dt
    )
    will_hit_late_cutoff_after_shield = bool(
        is_late_cutoff_now
        or (
            now_est_dt.weekday() < 5
            and hm_now == (NEW_CYCLE_BUY_CUTOFF_HM - 1)
            and now_est_dt.second >= 1
        )
    )
    ratchet_lock_note = (
        f" · 단차잠금 {next_ratchet_max_lots}회차"
        if next_ratchet_max_lots > rem_held_lots
        else ""
    )

    if hasattr(context, "send_slim_alert"):
        sign = "+" if net_pnl >= 0.0 else "-"
        r_sign = "+" if net_rate >= 0.0 else ""
        cyc_sign = "+" if cur_cyc_net >= 0.0 else "-"
        cum_sign = "+" if cum_net >= 0.0 else "-"
        sess_tag = " · 🌃장외익절" if is_ext_sell else ""

        if is_barbell:
            # MODIFIED [Case 102]: 미졸업 부분익절 환수금은 보호 현금버킷에 보존 후 0주 졸업 시 일괄 SGOV 원복
            rt_reb_note = ""
            if not is_graduated_zero and repaid_this_time > 0.0:
                vault_rep_note = (
                    f"·금고원복 ${repaid_to_vault_usd:,.0f}"
                    if repaid_to_vault_usd > 0.0
                    else ""
                )
                rt_reb_note = (
                    f" · ⚡실시간환수 ${repaid_this_time:,.0f}"
                    f"(보호현금버킷 ${barbell_cash_b_usd:,.0f} 보존{vault_rep_note}➔0주 SGOV원복)"
                )
            credit_mode_desc = (
                f"별도 수익금고 영구격리!(⚖️바벨 · 누적금고 +${barbell_vault_total:,.2f}){rt_reb_note}"
            )
            cash_lbl = "바벨SOXL현금"
        elif is_simple_mode:
            credit_mode_desc = (
                f"현금금고 적립(💵인출형 · 당일실현 +${max(0.0, day_net):,.2f} 인출가능!)"
            )
            cash_lbl = "가용현금"
        else:
            credit_mode_desc = "시드 복리산입!"
            cash_lbl = "가용현금"

        if is_sub_without_main_sell and not is_graduated_zero:
            grid_sh = sum(b.qty for b in rem_buckets)
            sub_sh = sum(sb.qty for sb in rem_sub_buckets)
            if is_sub_empty:
                sub_state_note = (
                    f"🎓 서브그리드 전량 졸업 완료(누적 {sub_comp_cycles}회 졸업 · 서브누적순익 +${sub_net_cum:,.2f})"
                )
            else:
                sub_state_note = (
                    f"📦 잔여 서브그리드 {len(rem_sub_buckets)}개층({sub_sh}주 · {rem_sub_held_lots}/{SUB_MAX_TOTAL_LOTS_4}회분) 감시 지속"
                )
            title_msg = (
                f"🛡️ [SOXL 3층 서브그리드 지정가 익절 체결 ({mode}{sess_tag})] "
                f"{sold_q}주 @ ${fill_p:.2f} ({r_sign}{net_rate:.2f}%)"
            )
            body_msg = (
                f"세후순익 {sign}${abs(net_pnl):,.2f} {credit_mode_desc} · "
                f"🔄이번사이클 누적: {cyc_sign}${abs(cur_cyc_net):,.2f}({cur_cyc_ev}회) · "
                f"{sub_state_note} · 본그리드({len(rem_buckets)}개층·{grid_sh}주) 무결성 유지 · "
                f"{cash_lbl} ${free_cash_now:,.2f}"
            )
        else:
            co_sold_note = (
                f"(본 {sold_grid_q}주 + 서브 {sold_sub_q}주 동시익절) · "
                if sold_sub_q > 0
                else ""
            )

            if is_graduated_zero:
                repay_note = ""
                if is_barbell:
                    if repaid_to_vault_usd > 0.0:
                        repay_note = (
                            f" · 🏦수익금고 대여금 ${repaid_to_vault_usd:,.2f} 1순위 원복 & "
                            f"⚖️60/30/10 리밸런싱 완료(SGOV 매수예약 ${pending_sgov_reb_usd:,.0f})"
                        )
                    else:
                        repay_note = (
                            f" · ⚖️시드 60/30/10 리밸런싱 완료"
                            f"(SGOV 매수예약 ${pending_sgov_reb_usd:,.0f} · 별도금고 +${barbell_vault_total:,.2f} 보존)"
                        )
                elif repaid_this_time > 0.0:
                    repay_note = (
                        f" · 💉예비시드 원금 ${repaid_this_time:,.2f} 자동상환 완료"
                        f"(잔여수혈 {next_used_res_cnt}회분 · ${next_inj_res_usd:,.2f}!)"
                    )

                if switched_to_live_assassin:
                    next_entry_guide = (
                        "🗡️[실전 암살자 모드 자동 전환 완료! 스나이퍼/바벨 신규매수 잠금 · 보유 SGOV는 수동매도 위임]"
                    )
                elif is_ext_sell:
                    next_entry_guide = "🔒장외 매수잠금 · 04:07 EST 프리장 개시 후 첫 1층 진입 대기!"
                elif will_hit_late_cutoff_after_shield:
                    next_entry_guide = (
                        "🔒장마감 30분전(15:30 ~ 16:00) 새 사이클 진입 차단(고점 오버나이트 방어) · "
                        "익일 04:07 EST 프리장 첫 1층 진입 대기!"
                    )
                else:
                    next_entry_guide = (
                        "🛡️60초 타임쉴드 경과 후 현재가 조회 및 첫 1층 진입!"
                    )
                note_str = (
                    f"🏆이번 사이클 최종 확정수익: {cyc_sign}${abs(cur_cyc_net):,.2f} (총 {cur_cyc_ev}회 익절 완수 ➔ 새 사이클 $0.00 리셋!) · "
                    f"💰전체 누적실현익: {cum_sign}${abs(cum_net):,.2f} (누적 {next_comp_main_cycles}회 졸업) · "
                    f"{co_sold_note}🎓전 지층 흑자 졸업 완료(0주 싸이클 종료{repay_note} "
                    f"➔ {next_entry_guide})"
                )
            elif is_grid_empty and not is_sub_empty:
                rem_sub_sh = sum(sb.qty for sb in rem_sub_buckets)
                note_str = (
                    f"🔄이번사이클 누적: {cyc_sign}${abs(cur_cyc_net):,.2f}({cur_cyc_ev}회) · "
                    f"{co_sold_note}🌟 본그리드 전량 졸업 완료 · 잔여 서브({rem_sub_sh}주) 익절 감시 지속"
                )
            else:
                wma_info = compute_upper_2_to_7_moving_avg(rem_buckets)
                u_cnt = safe_int(wma_info.get("upper_tier_count"), 0)
                u_qty = safe_int(wma_info.get("upper_qty"), 0)
                u_wma_p = safe_float(wma_info.get("upper_wma_price"), 0.0)
                u_wma_t = safe_float(
                    wma_info.get("upper_wma_target_price"), 0.0
                )
                if not rem_has_active_l1:
                    l2_cap_p = safe_float(
                        wma_info.get("min_indiv_upper_price"),
                        rem_buckets[0].book_price,
                    )
                    if is_ext_sell:
                        reload_guide = (
                            f"🔒장외 매수잠금·1~2층채굴개방(04:07 EST 이후 상한 ${l2_cap_p:.2f} 이하 1층재장전 · 기억저가 ${next_cycle_min_p:.2f}{ratchet_lock_note} 잠금)"
                        )
                    elif will_hit_late_cutoff_after_shield:
                        reload_guide = (
                            f"🛡️60초 타임쉴드 후 장마감 30분전(15:30 ~ 16:00) +1.0% 돌파차단 · "
                            f"2층상한 ${l2_cap_p:.2f} 이하 -1.0% 눌림목만 1분 주기 재장전 감시(기억저가 ${next_cycle_min_p:.2f}{ratchet_lock_note} 잠금)"
                        )
                    else:
                        reload_guide = (
                            f"🛡️60초 타임쉴드 후 1분 주기 1층재장전(2층상한 ${l2_cap_p:.2f} 이하 · 기억저가 ${next_cycle_min_p:.2f}{ratchet_lock_note} 잠금)"
                        )
                    note_str = (
                        f"🔄이번사이클 누적: {cyc_sign}${abs(cur_cyc_net):,.2f}({cur_cyc_ev}회) · "
                        f"{co_sold_note}📦 잔여 2~{u_cnt + 1}층({u_cnt}개층·{u_qty}주) 순수이평 ${u_wma_p:.2f}(목표 ${u_wma_t:.2f}) 1.5초 실시간 익절감시 "
                        f"· {reload_guide}"
                    )
                elif u_cnt > 0:
                    note_str = (
                        f"🔄이번사이클 누적: {cyc_sign}${abs(cur_cyc_net):,.2f}({cur_cyc_ev}회) · "
                        f"{co_sold_note}📦 잔여 1층+상단({len(rem_buckets)}개층) 순수이평 ${u_wma_p:.2f}(목표 ${u_wma_t:.2f}) 1.5초 실시간 익절감시 "
                        f"· 10분게이트 대기(기억저가 ${next_cycle_min_p:.2f}{ratchet_lock_note} 잠금)"
                    )
                else:
                    b1_rem = rem_buckets[0]
                    b1_rem_target = (
                        math.ceil((b1_rem.book_price * 1.015 - 1e-9) * 100.0)
                        / 100.0
                    )
                    note_str = (
                        f"🔄이번사이클 누적: {cyc_sign}${abs(cur_cyc_net):,.2f}({cur_cyc_ev}회) · "
                        f"{co_sold_note}📦 잔여 1층 단독({b1_rem.qty}주 · 단가 ${b1_rem.book_price:.2f} ➔ 목표 ${b1_rem_target:.2f}) 1.5초 실시간 익절감시 "
                        f"· 10분게이트 대기(기억저가 ${next_cycle_min_p:.2f}{ratchet_lock_note} 잠금)"
                    )
            title_msg = (
                f"🔴 [SOXL 지정가 익절 체결 ({mode}{sess_tag})] "
                f"{sold_q}주 @ ${fill_p:.2f} ({r_sign}{net_rate:.2f}%)"
            )
            body_msg = (
                f"세후순익 {sign}${abs(net_pnl):,.2f} {credit_mode_desc} · "
                f"{note_str} · {cash_lbl} ${free_cash_now:,.2f}"
            )
        await context.send_slim_alert(title=title_msg, body=body_msg)

    return {
        "status": "SELL_FILLED_AND_SETTLED",
        "did_sell_or_ratchet": True,
        "sold_qty": sold_q,
        "sold_sub_qty": sold_sub_q,
        "fill_price": fill_p,
        "net_pnl_usd": net_pnl,
        "sub_net_pnl_usd": sub_net_pnl,
        "cycle_realized_net_usd": next_cyc_net,
        "last_cycle_realized_net_usd": next_last_cyc_net,
        "completed_main_cycles": next_comp_main_cycles,
        "repaid_reserve_usd": repaid_this_time,
        "switched_to_live_assassin": switched_to_live_assassin,
        "reanchor_drop_usd": 0.0,
        "remaining_tiers": len(rem_buckets),
        "remaining_sub_tiers": len(rem_sub_buckets),
        "cycle_ratchet_max_lots": next_ratchet_max_lots,
        "sub_ratchet_max_lots": next_sub_ratchet_max_lots,
        "free_cash_usd": free_cash_now,
    }


def _extract_actual_sell_fee_from_exec(
    exec_obj: Dict[str, Any]
) -> Optional[float]:
    if not isinstance(exec_obj, dict):
        return None
    f_comm = max(0.0, safe_float(exec_obj.get("commission"), 0.0))
    f_tax = max(0.0, safe_float(exec_obj.get("tax"), 0.0))
    tot_f = round(f_comm + f_tax, 4)
    return tot_f if tot_f > 0.0 else None


async def sync_pending_sell_order_plugin(
    context: Any,
    holdings: Dict[str, Dict[str, Any]],
    prices: Dict[str, float],
    now_est: Optional[datetime] = None,
    force_settle: bool = False,
) -> Dict[str, Any]:
    st = context.ledger.get_state(TARGET_SYMBOL)
    sell_oid = str(st.get("sell_order_id") or "").strip()
    if not sell_oid:
        return {"status": "NO_PENDING_SELL", "did_sell_or_ratchet": False}

    ordered_qty = max(1, safe_int(st.get("ordered_qty"), 1))
    target_p = safe_float(st.get("target_sell_price"), 0.0)
    sell_mode = str(st.get("pending_sell_mode") or "SELL_L1_ONLY")

    now_mono = time.monotonic()
    last_mod = safe_float(st.get("last_modify_mono"), 0.0)
    if last_mod <= 0.0 or last_mod > now_mono:
        last_mod = now_mono
        await context.ledger.update_state(
            TARGET_SYMBOL, last_modify_mono=last_mod
        )
    elapsed_mod = max(0.0, now_mono - last_mod)

    detail = await context.api.get_order_detail(sell_oid)
    if isinstance(detail, dict):
        ord_status = str(detail.get("status") or "").upper().strip()
        exec_obj = (
            detail.get("execution")
            if isinstance(detail.get("execution"), dict)
            else {}
        )
        filled_q = safe_int(exec_obj.get("filledQuantity"), 0)
        avg_fill_p = safe_float(exec_obj.get("averageFilledPrice"), 0.0)
        actual_fee_val = _extract_actual_sell_fee_from_exec(exec_obj)

        if ord_status == "FILLED" or (
            filled_q > 0 and ord_status in ("CANCELED", "REPLACED", "REJECTED")
        ):
            eff_q = filled_q if filled_q > 0 else ordered_qty
            eff_p = avg_fill_p if avg_fill_p > 0.0 else target_p
            return await _commit_filled_sell_and_reanchor_ledger(
                context=context,
                filled_qty=eff_q,
                avg_fill_price=eff_p,
                sell_mode=sell_mode,
                settled_order_id=sell_oid,
                actual_sell_fee_usd=actual_fee_val,
            )

        if (
            ord_status in ("PARTIAL_FILLED", "PENDING_CANCEL")
            or filled_q > 0
        ):
            if (
                elapsed_mod >= SELL_ORDER_MAX_WAIT_SEC
                or force_settle
                or ord_status == "PENDING_CANCEL"
            ):
                try:
                    await context.api.cancel_order(sell_oid)
                except Exception:
                    pass
                final_det = await context.api.get_order_detail(sell_oid)
                f_st2 = (
                    str(final_det.get("status") or "").upper().strip()
                    if isinstance(final_det, dict)
                    else ""
                )
                if not isinstance(final_det, dict) or f_st2 in (
                    "PENDING",
                    "PARTIAL_FILLED",
                    "PENDING_CANCEL",
                    "PENDING_REPLACE",
                ):
                    await asyncio.sleep(0.35)
                    final_det = await context.api.get_order_detail(sell_oid)
                    f_st2 = (
                        str(final_det.get("status") or "").upper().strip()
                        if isinstance(final_det, dict)
                        else ""
                    )
                if not isinstance(final_det, dict) or f_st2 in (
                    "PENDING",
                    "PARTIAL_FILLED",
                    "PENDING_CANCEL",
                    "PENDING_REPLACE",
                ):
                    return {
                        "status": "SELL_PARTIAL_CANCEL_CONFIRMING",
                        "did_sell_or_ratchet": True,
                        "orderId": sell_oid,
                    }
                f_ex = (
                    final_det.get("execution")
                    if isinstance(final_det.get("execution"), dict)
                    else {}
                )
                f_q2 = safe_int(f_ex.get("filledQuantity"), filled_q)
                f_p2 = safe_float(f_ex.get("averageFilledPrice"), avg_fill_p)
                f_fee2 = _extract_actual_sell_fee_from_exec(f_ex)
                if f_q2 > 0:
                    filled_q = f_q2
                if f_p2 > 0.0:
                    avg_fill_p = f_p2
                if f_fee2 is not None:
                    actual_fee_val = f_fee2
                if filled_q > 0:
                    eff_p = avg_fill_p if avg_fill_p > 0.0 else target_p
                    return await _commit_filled_sell_and_reanchor_ledger(
                        context=context,
                        filled_qty=filled_q,
                        avg_fill_price=eff_p,
                        sell_mode=sell_mode,
                        settled_order_id=sell_oid,
                        actual_sell_fee_usd=actual_fee_val,
                    )
            else:
                return {
                    "status": "SELL_PARTIAL_FILLED_WAITING",
                    "did_sell_or_ratchet": True,
                    "filled_qty": filled_q,
                    "ordered_qty": ordered_qty,
                }

        if (
            ord_status in ("CANCELED", "REJECTED", "REPLACED")
            and filled_q == 0
        ):
            if ord_status == "REJECTED":
                mark_extended_sell_restriction_cooldown(
                    context,
                    symbol=TARGET_SYMBOL,
                    cooldown_sec=EXTENDED_SELL_RESTRICTION_COOLDOWN_SEC,
                    reason="SELL_ORDER_REJECTED",
                )
            reset_sniper_l1_trail_slots(
                context, grid_kind="ALL", symbol=TARGET_SYMBOL
            )
            await context.ledger.update_state(
                TARGET_SYMBOL,
                sell_order_id="",
                ordered_qty=0,
                target_sell_price=0.0,
                pending_sell_mode="",
                pending_sell_indices=[],
                pending_sub_sell_indices=[],
                last_sell_gate_eval_ts=0.0,
            )
            return {
                "status": f"SELL_ORDER_{ord_status}_CLEARED",
                "did_sell_or_ratchet": False,
            }

    if elapsed_mod >= SELL_ORDER_MAX_WAIT_SEC or force_settle:
        try:
            await context.api.cancel_order(sell_oid)
        except Exception:
            pass

        final_detail = await context.api.get_order_detail(sell_oid)
        f_status = (
            str(final_detail.get("status") or "").upper().strip()
            if isinstance(final_detail, dict)
            else ""
        )
        if not isinstance(final_detail, dict) or f_status in (
            "PENDING",
            "PARTIAL_FILLED",
            "PENDING_CANCEL",
            "PENDING_REPLACE",
        ):
            await asyncio.sleep(0.35)
            final_detail = await context.api.get_order_detail(sell_oid)
            f_status = (
                str(final_detail.get("status") or "").upper().strip()
                if isinstance(final_detail, dict)
                else ""
            )

        if not isinstance(final_detail, dict) and elapsed_mod >= (
            SELL_ORDER_MAX_WAIT_SEC + 15.0
        ):
            closed_cands = await context.api.get_closed_orders(
                symbol=TARGET_SYMBOL, limit=25
            )
            for c_item in closed_cands:
                if str(c_item.get("orderId") or "").strip() == sell_oid:
                    final_detail = c_item
                    f_status = (
                        str(c_item.get("status") or "").upper().strip()
                    )
                    break

        if isinstance(final_detail, dict):
            if f_status in (
                "PENDING",
                "PARTIAL_FILLED",
                "PENDING_CANCEL",
                "PENDING_REPLACE",
            ):
                return {
                    "status": "SELL_CANCEL_IN_FLIGHT",
                    "did_sell_or_ratchet": True,
                    "orderId": sell_oid,
                }
            f_exec = (
                final_detail.get("execution")
                if isinstance(final_detail.get("execution"), dict)
                else {}
            )
            f_qty = safe_int(f_exec.get("filledQuantity"), 0)
            f_avg = safe_float(f_exec.get("averageFilledPrice"), 0.0)
            f_fee = _extract_actual_sell_fee_from_exec(f_exec)
            if f_status == "FILLED" or f_qty > 0:
                return await _commit_filled_sell_and_reanchor_ledger(
                    context=context,
                    filled_qty=(f_qty if f_qty > 0 else ordered_qty),
                    avg_fill_price=(f_avg if f_avg > 0.0 else target_p),
                    sell_mode=sell_mode,
                    settled_order_id=sell_oid,
                    actual_sell_fee_usd=f_fee,
                )
        elif elapsed_mod < (SELL_ORDER_MAX_WAIT_SEC + 30.0):
            return {
                "status": "SELL_CANCEL_VERIFY_RETRY",
                "did_sell_or_ratchet": True,
                "orderId": sell_oid,
            }

        reset_sniper_l1_trail_slots(
            context, grid_kind="ALL", symbol=TARGET_SYMBOL
        )
        await context.ledger.update_state(
            TARGET_SYMBOL,
            sell_order_id="",
            ordered_qty=0,
            target_sell_price=0.0,
            pending_sell_mode="",
            pending_sell_indices=[],
            pending_sub_sell_indices=[],
            last_sell_gate_eval_ts=0.0,
        )
        logger.info(
            "⏳ [SOXL 지정가 매도 60초 미체결 안전 취소] 지정가 $%.2f 유지 종료 ➔ ⚡1.5초 실시간 타점 감시 복귀",
            target_p,
        )
        return {
            "status": "SELL_ORDER_UNFILLED_CANCELED_SAFE",
            "did_sell_or_ratchet": False,
        }

    return {
        "status": "SELL_ORDER_PENDING",
        "did_sell_or_ratchet": True,
        "orderId": sell_oid,
    }


async def _get_closed_1m_ha_and_qqq_snapshot(
    context: Any,
    live_p: float,
    dt_now: datetime,
) -> Tuple[str, bool, bool, float]:
    """
    # NEW [Case 99 : 완결 1분봉(closed_bar_minute_key) 확정 HA 음봉 여부 및 QQQ 단기 변화율 추출기]
    반환값: (closed_bar_minute_key, closed_ha_ready, closed_ha_bull, qqq_vel_max_pct)
    """
    global _LAST_EXIT_CANDLE_WARM_MONO
    raw_cache = getattr(context, "candle_metrics_cache", None)
    soxl_met = (
        raw_cache.get(TARGET_SYMBOL) if isinstance(raw_cache, dict) else None
    )
    now_m = time.monotonic()

    if (
        (
            not isinstance(soxl_met, dict)
            or not bool(soxl_met.get("closed_ha_ready", False))
        )
        and (now_m - _LAST_EXIT_CANDLE_WARM_MONO) >= 10.0
        and hasattr(context, "api")
    ):
        _LAST_EXIT_CANDLE_WARM_MONO = now_m
        try:
            from quant_indicators_plugin import compute_soxl_quant_metrics_1m

            # MODIFIED: 400분봉 + 10일봉 표준 워밍업 통일 (SHM req_cnt 축소 오염 차단)
            c_1m = await context.api.get_candles_1m(
                symbol=TARGET_SYMBOL, total_count=400
            )
            c_1d = (
                await context.api.get_candles_1d(
                    symbol=TARGET_SYMBOL, count=10
                )
                if hasattr(context.api, "get_candles_1d")
                else []
            )
            if c_1m or c_1d:
                soxl_met = await asyncio.to_thread(
                    compute_soxl_quant_metrics_1m,
                    c_1m or [],
                    live_p,
                    dt_now,
                    c_1d or [],
                )
                if isinstance(raw_cache, dict):
                    raw_cache[TARGET_SYMBOL] = soxl_met
        except Exception:
            pass

    if isinstance(soxl_met, dict) and live_p > 0.0:
        soxl_met = refresh_metrics_with_live_tick(
            soxl_met, live_p, now_est=dt_now, symbol=TARGET_SYMBOL
        )
        if isinstance(raw_cache, dict):
            raw_cache[TARGET_SYMBOL] = soxl_met

    closed_mk = (
        str(soxl_met.get("closed_bar_minute_key") or "").strip()
        if isinstance(soxl_met, dict)
        else ""
    )
    closed_ready = (
        bool(soxl_met.get("closed_ha_ready", False))
        if isinstance(soxl_met, dict)
        else False
    )
    closed_bull = (
        bool(soxl_met.get("closed_ha_bull", True))
        if isinstance(soxl_met, dict)
        else True
    )
    closed_shaved_bull = (
        bool(
            closed_bull
            and bool(soxl_met.get("closed_ha_shaved_bull", False))
        )
        if isinstance(soxl_met, dict) and "closed_ha_shaved_bull" in soxl_met
        else closed_bull
    )
    qqq_met = (
        raw_cache.get("QQQ") if isinstance(raw_cache, dict) else None
    )
    qqq_vel_max = (
        safe_float(qqq_met.get("vel_max_3m_10m_pct"), 0.0)
        if isinstance(qqq_met, dict)
        else 0.0
    )
    return (
        closed_mk,
        closed_ready,
        closed_bull,
        closed_shaved_bull,
        qqq_vel_max,
    )


def _step_l1_trail_slot_candidate(
    slot: SniperL1TrailSlot,
    live_p: float,
    wick_high_p: float,
    cur_min_key: str,
    closed_min_key: str,
    closed_ha_ready: bool,
    closed_ha_bull: bool,
    qqq_vel_max: float,
    closed_ha_shaved_bull: Optional[bool] = None,
) -> Tuple[str, bool]:
    """
    # NEW [Case 99 : 🛡️ ⑥ 하드보존(1%➔1.25%) + 완결 1분봉 HA 음봉 + 콜백 1차 후보 판정기]
    반환값: (trigger_code, just_ignited)
    """
    if slot.qty <= 0 or slot.ref_cost <= 0.0 or live_p <= 0.0:
        return "", False

    probe_h = max(live_p, safe_float(wick_high_p, 0.0))

    if not slot.armed:
        if probe_h < slot.arm_100_p - 1e-9:
            return "", False
        if probe_h >= slot.cap_500_p - 1e-9:
            slot.armed = True
            slot.armed_minute_key = cur_min_key
            slot.peak_p = probe_h
            slot.stepped_125 = True
            slot.lock_floor_p = slot.lock_125_p
            slot.refresh_stop_price()
            return "TRAIL_CAP_500", True

        # MODIFIED: 점화 시 lock_floor_p=0.0 무스탑 시작 및 엄격 미만(<) 판정으로 자기격발 원천 차단
        slot.armed = True
        slot.armed_minute_key = cur_min_key
        slot.peak_p = max(probe_h, slot.arm_100_p)
        slot.lock_floor_p = 0.0
        slot.stepped_125 = False
        stop_now = slot.refresh_stop_price()
        if stop_now > 0.0 and wick_high_p > live_p and live_p < stop_now - 1e-9:
            return "TRAIL_CB_STOP", True
        return "", True

    slot.peak_p = max(slot.peak_p, probe_h)
    stop_now = slot.refresh_stop_price()

    if probe_h >= slot.cap_500_p - 1e-9:
        return "TRAIL_CAP_500", False

    if stop_now > 0.0 and live_p < stop_now - 1e-9:
        return "TRAIL_CB_STOP", False

    # MODIFIED [Case 103]: 완결 1분봉이 무밑꼬리 강세 HA양봉(eff_shaved_bull)일 때만 패스(홀딩)
    eff_shaved_bull = (
        bool(closed_ha_bull and closed_ha_shaved_bull)
        if closed_ha_shaved_bull is not None
        else bool(closed_ha_bull)
    )
    if (
        closed_ha_ready
        and (not eff_shaved_bull)
        and bool(closed_min_key)
        and bool(slot.armed_minute_key)
        and (closed_min_key >= slot.armed_minute_key)
        and (closed_min_key != slot.forgiven_ha_minute_key)
        and (qqq_vel_max < SNIPER_L1_TRAIL_QQQ_BYPASS_PCT)
    ):
        return "TRAIL_CLOSED_HA_RED", False

    return "", False


# ---------------------------------------------------------------------------
# [핵심 3] 24시간 전 세션 매수 후 최초 60초 타임쉴드 & 주간 1층 챔피언 ⑥ 트레일링(하드보존+완결1분HA+용서·망각) + 방안 C 오버나이트 통합이평 사수 모니터
# ---------------------------------------------------------------------------
async def execute_1m_sniper_sell_and_reanchor_plugin(
    context: Any,
    holdings: Dict[str, Dict[str, Any]],
    prices: Dict[str, float],
    now_est: Optional[datetime] = None,
) -> Dict[str, Any]:
    global _LAST_CONSUMED_WICK_TRADE_TS

    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    hm = dt_now.hour * 100 + dt_now.minute
    cur_min_key = dt_now.strftime("%Y-%m-%d %H:%M")

    st = context.ledger.get_state(TARGET_SYMBOL)
    main_slot, sub_slot = get_sniper_l1_trail_slots(
        context, symbol=TARGET_SYMBOL
    )

    if str(st.get("sell_order_id") or "").strip():
        return await sync_pending_sell_order_plugin(
            context=context,
            holdings=holdings,
            prices=prices,
            now_est=dt_now,
        )

    if not is_active_sell_window(hm, now_est=dt_now):
        main_slot.release_overnight()
        sub_slot.release_overnight()
        return {
            "status": "OUTSIDE_TRADING_WINDOW",
            "did_sell_or_ratchet": False,
        }

    if not bool(st.get("is_active", True)):
        return {"status": "BOT_INACTIVE", "did_sell_or_ratchet": False}

    if str(st.get("buy_order_id") or "").strip():
        return {
            "status": "BUY_ORDER_IN_PROGRESS",
            "did_sell_or_ratchet": False,
        }

    buckets = buckets_from_dicts(st.get("buckets", []))
    sub_buckets = buckets_from_dicts(st.get("sub_buckets", []))
    if not buckets and not sub_buckets:
        main_slot.full_reset()
        sub_slot.full_reset()
        return {"status": "NO_BUCKETS_HELD", "did_sell_or_ratchet": False}

    in_ext_cd, rem_ext_cd = is_within_extended_sell_restriction_cooldown(
        context, TARGET_SYMBOL
    )
    if in_ext_cd:
        return {
            "status": "SILENT_HOLD_EXTENDED_RESTRICT_COOLDOWN",
            "did_sell_or_ratchet": False,
            "remain_cooldown_sec": rem_ext_cd,
        }

    in_buy_shield, remain_buy_sec = is_within_post_buy_time_shield(
        context, st, TARGET_SYMBOL
    )
    if in_buy_shield:
        return {
            "status": "HOLD_POST_BUY_60S_TIME_SHIELD",
            "did_sell_or_ratchet": False,
            "remain_shield_sec": remain_buy_sec,
        }

    is_ext_sell_only = is_extended_sell_only_window(hm, now_est=dt_now)
    use_daytime_l1_trail = bool(
        SNIPER_L1_TRAIL_ENABLED and (not is_ext_sell_only)
    )
    if is_ext_sell_only:
        main_slot.release_overnight()
        sub_slot.release_overnight()

    if buckets and has_active_l1_bucket(buckets):
        main_slot.sync_fingerprint(buckets[0].qty, buckets[0].book_price)
    else:
        main_slot.full_reset()

    if sub_buckets and has_active_l1_bucket(sub_buckets):
        sub_slot.sync_fingerprint(
            sub_buckets[0].qty, sub_buckets[0].book_price
        )
    else:
        sub_slot.full_reset()

    live_p = _get_live_soxl_price(
        context,
        prices,
        holdings,
        dt_now,
        allow_stale_fallback=(not is_ext_sell_only),
    )
    if live_p <= 0.0 and not is_ext_sell_only:
        live_p = await _fetch_fresh_current_soxl_price(
            context, fallback_price=0.0
        )
    if live_p <= 0.0:
        return {
            "status": (
                "SILENT_EXTENDED_NO_LIVE_PRICE"
                if is_ext_sell_only
                else "NO_LIVE_PRICE"
            ),
            "did_sell_or_ratchet": False,
        }

    h_info = (holdings or {}).get(TARGET_SYMBOL, {})
    ledger_total_qty = sum(b.qty for b in buckets) + sum(
        sb.qty for sb in sub_buckets
    )
    h_qty = safe_int(h_info.get("qty"), ledger_total_qty)
    default_avg_p = (
        buckets[0].actual_avg_price
        if buckets
        else (sub_buckets[0].actual_avg_price if sub_buckets else live_p)
    )
    avg_p = safe_float(h_info.get("avg_price"), default_avg_p)
    update_exit_snapshot_on_hold(
        context, TARGET_SYMBOL, h_qty, avg_p, live_p
    )

    held_lots = max(1, sum(b.lot_count for b in buckets))
    ratchet_max_lots = max(
        held_lots, safe_int(st.get("cycle_ratchet_max_lots"), 0)
    )
    threshold_mode = str(st.get("threshold_mode") or "WIDE_RUNWAY").upper()
    _, rise_sell_l1_pct, rise_sell_upper_pct = get_golden8_prog_thresholds(
        held_lots=held_lots,
        threshold_mode=threshold_mode,
        cycle_ratchet_max_lots=ratchet_max_lots,
    )

    # [1순위 & 3순위] 상단 2~7층(서브 2~3층) 통합이평 전량 졸업 및 개별 상단층 판정
    sell_eval = evaluate_multi_grid_sell_targets(
        buckets=buckets,
        live_price=live_p,
        rise_l1_pct=rise_sell_l1_pct,
        rise_upper_pct=rise_sell_upper_pct,
        is_overnight_session=is_ext_sell_only,
        sub_buckets=sub_buckets,
        exclude_daytime_l1=use_daytime_l1_trail,
    )

    wick_high_p: float = 0.0
    wick_trade_ts: float = 0.0
    nearest_target_p: float = _compute_nearest_sell_target_price(
        buckets=buckets,
        rise_l1_pct=rise_sell_l1_pct,
        rise_upper_pct=rise_sell_upper_pct,
        is_overnight_session=is_ext_sell_only,
        sub_buckets=sub_buckets,
    )
    triggered_by_wick_only: bool = False

    need_wick_probe = bool(
        not bool(sell_eval.get("should_sell"))
        and nearest_target_p > 0.0
        and live_p >= (nearest_target_p * WICK_PROXIMITY_TRIGGER_RATIO)
    )
    if (
        not need_wick_probe
        and use_daytime_l1_trail
        and (
            (
                main_slot.armed
                and not main_slot.stepped_125
                and live_p
                >= main_slot.step_trig_145_p * WICK_PROXIMITY_TRIGGER_RATIO
            )
            or (
                sub_slot.armed
                and not sub_slot.stepped_125
                and live_p
                >= sub_slot.step_trig_145_p * WICK_PROXIMITY_TRIGGER_RATIO
            )
        )
    ):
        need_wick_probe = True

    if need_wick_probe:
        min_trade_after_ts = max(
            safe_float(st.get("last_buy_fill_ts"), 0.0),
            safe_float(st.get("last_sub_buy_fill_ts"), 0.0),
            safe_float(st.get("last_sell_fill_ts"), 0.0),
            safe_float(st.get("last_sub_sell_fill_ts"), 0.0),
            safe_float(st.get("entry_ts"), 0.0),
            _LAST_CONSUMED_WICK_TRADE_TS,
        )
        wick_high_p, wick_trade_ts = (
            await _probe_recent_trade_wick_high_soxl(
                context=context,
                min_after_ts=min_trade_after_ts,
                lookback_sec=WICK_TRADE_LOOKBACK_SEC,
                count=WICK_TRADE_FETCH_COUNT,
            )
        )
        if (
            not bool(sell_eval.get("should_sell"))
            and nearest_target_p > 0.0
            and wick_high_p >= nearest_target_p
            and wick_high_p > live_p
        ):
            wick_eval = evaluate_multi_grid_sell_targets(
                buckets=buckets,
                live_price=nearest_target_p,
                rise_l1_pct=rise_sell_l1_pct,
                rise_upper_pct=rise_sell_upper_pct,
                is_overnight_session=is_ext_sell_only,
                sub_buckets=sub_buckets,
                exclude_daytime_l1=use_daytime_l1_trail,
            )
            if not bool(wick_eval.get("should_sell")):
                wick_eval = evaluate_multi_grid_sell_targets(
                    buckets=buckets,
                    live_price=wick_high_p,
                    rise_l1_pct=rise_sell_l1_pct,
                    rise_upper_pct=rise_sell_upper_pct,
                    is_overnight_session=is_ext_sell_only,
                    sub_buckets=sub_buckets,
                    exclude_daytime_l1=use_daytime_l1_trail,
                )
            if bool(wick_eval.get("should_sell")):
                sell_eval = wick_eval
                triggered_by_wick_only = True
                logger.info(
                    "⚡ [Case 82 1분봉 윗꼬리 체결틱 포착!] 스냅샷현재가=$%.2f < 목표가($%.2f) 이나 최근 %.1f초 내 체결최고가=$%.2f 감지 -> 즉시 목표하한가로 지정가 매도 격발!",
                    live_p,
                    nearest_target_p,
                    WICK_TRADE_LOOKBACK_SEC,
                    wick_high_p,
                )

    # [2순위 · Case 99] 평일 04:07 ~ 16:00 EST 본 1층 · 서브 1층 스텝 락온 트레일링 & "허락보다 용서를" 평가
    main_trail_trig = ""
    sub_trail_trig = ""
    just_ignited_any = False
    forgiven_any = False

    if use_daytime_l1_trail:
        (
            closed_mk,
            closed_ready,
            closed_bull,
            closed_shaved_bull,
            qqq_vel_max,
        ) = await _get_closed_1m_ha_and_qqq_snapshot(context, live_p, dt_now)
        if bool(sell_eval.get("hit_wma_grad")):
            main_slot.full_reset()
        elif main_slot.qty > 0:
            main_trail_trig, ign_m = _step_l1_trail_slot_candidate(
                slot=main_slot,
                live_p=live_p,
                wick_high_p=wick_high_p,
                cur_min_key=cur_min_key,
                closed_min_key=closed_mk,
                closed_ha_ready=closed_ready,
                closed_ha_bull=closed_bull,
                qqq_vel_max=qqq_vel_max,
                closed_ha_shaved_bull=closed_shaved_bull,
            )
            if ign_m:
                just_ignited_any = True
                logger.info(
                    "🔥 [SOXL 본 1층 완결1분HA 트레일링 점화] 단가=$%.2f ➔ 점화가=$%.2f(스텝락=$%.2f) · 점화분=%s · 강세HA양봉 홀딩 추적 개시",
                    main_slot.ref_cost,
                    main_slot.arm_100_p,
                    main_slot.lock_125_p,
                    main_slot.armed_minute_key,
                )

        if bool(sell_eval.get("hit_sub_wma_grad")):
            sub_slot.full_reset()
        elif sub_slot.qty > 0:
            sub_trail_trig, ign_s = _step_l1_trail_slot_candidate(
                slot=sub_slot,
                live_p=live_p,
                wick_high_p=wick_high_p,
                cur_min_key=cur_min_key,
                closed_min_key=closed_mk,
                closed_ha_ready=closed_ready,
                closed_ha_bull=closed_bull,
                qqq_vel_max=qqq_vel_max,
                closed_ha_shaved_bull=closed_shaved_bull,
            )
            if ign_s:
                just_ignited_any = True
                logger.info(
                    "🔥 [SOXL 서브 1층 완결1분HA 트레일링 점화] 단가=$%.2f ➔ 점화가=$%.2f(스텝락=$%.2f) · 점화분=%s · 강세HA양봉 홀딩 추적 개시",
                    sub_slot.ref_cost,
                    sub_slot.arm_100_p,
                    sub_slot.lock_125_p,
                    sub_slot.armed_minute_key,
                )
        _ = just_ignited_any
    else:
        closed_mk = ""
        closed_ready = False
        closed_bull = True
        closed_shaved_bull = True

    if (
        bool(sell_eval.get("should_sell"))
        or bool(main_trail_trig)
        or bool(sub_trail_trig)
    ):
        fresh_live_p = await _fetch_fresh_current_soxl_price(
            context,
            fallback_price=live_p,
        )
        if fresh_live_p <= 0.0:
            fresh_live_p = live_p

        if bool(sell_eval.get("should_sell")):
            fresh_only_eval = evaluate_multi_grid_sell_targets(
                buckets=buckets,
                live_price=fresh_live_p,
                rise_l1_pct=rise_sell_l1_pct,
                rise_upper_pct=rise_sell_upper_pct,
                is_overnight_session=is_ext_sell_only,
                sub_buckets=sub_buckets,
                exclude_daytime_l1=use_daytime_l1_trail,
            )
            if bool(fresh_only_eval.get("should_sell")):
                sell_eval = fresh_only_eval
                triggered_by_wick_only = False
            elif nearest_target_p > 0.0:
                lowest_tier_eval = evaluate_multi_grid_sell_targets(
                    buckets=buckets,
                    live_price=nearest_target_p,
                    rise_l1_pct=rise_sell_l1_pct,
                    rise_upper_pct=rise_sell_upper_pct,
                    is_overnight_session=is_ext_sell_only,
                    sub_buckets=sub_buckets,
                    exclude_daytime_l1=use_daytime_l1_trail,
                )
                if bool(lowest_tier_eval.get("should_sell")):
                    sell_eval = lowest_tier_eval

        sold_idx_set: Set[int] = set(sell_eval.get("sold_indices") or [])
        sub_sold_idx_set: Set[int] = set(
            sell_eval.get("sub_sold_indices") or []
        )
        floor_cands: List[float] = []
        if bool(sell_eval.get("should_sell")) and safe_float(
            sell_eval.get("min_floor_price"), 0.0
        ) > 0.0:
            floor_cands.append(
                safe_float(sell_eval.get("min_floor_price"), 0.0)
            )

        bad_ha_mk = (
            closed_mk
            if (closed_ready and (not closed_shaved_bull) and bool(closed_mk))
            else ""
        )
        fired_main_trail = False
        fired_sub_trail = False

        # [본 1층 2차 실호가 검문 · '허락보다 용서를' 릴리스 및 2층 역전 동반 졸업]
        if (
            main_trail_trig
            and not bool(sell_eval.get("hit_wma_grad"))
            and buckets
            and has_active_l1_bucket(buckets)
        ):
            main_slot.peak_p = max(main_slot.peak_p, fresh_live_p)
            m_stop = main_slot.refresh_stop_price()
            if fresh_live_p < main_slot.arm_100_p - 1e-9:
                main_slot.release_forgive(bad_ha_minute_key=bad_ha_mk)
                forgiven_any = True
                logger.info(
                    "💡 [옵션 1-B 본 1층 '허락보다 용서를' 릴리스 & 기존 HA 망각] 실호가=$%.2f < +1.25%%($%.2f) -> 허공주문 차단 · 망각봉=%s",
                    fresh_live_p,
                    main_slot.arm_100_p,
                    bad_ha_mk or "-",
                )
            elif main_trail_trig == "TRAIL_CB_STOP" and (
                m_stop <= 0.0 or fresh_live_p >= m_stop - 1e-9
            ):
                pass
            else:
                eff_m_lock = (
                    main_slot.lock_floor_p
                    if main_slot.lock_floor_p > 0.0
                    else main_slot.arm_100_p
                )
                if (
                    main_trail_trig == "TRAIL_CAP_500"
                    and fresh_live_p >= main_slot.cap_500_p - 1e-9
                ):
                    m_eff_fl = main_slot.cap_500_p
                elif fresh_live_p >= eff_m_lock - 1e-9:
                    mkt_fl = (
                        math.floor((fresh_live_p * 0.998 + 1e-9) * 100.0)
                        / 100.0
                    )
                    m_eff_fl = max(eff_m_lock, mkt_fl)
                else:
                    mkt_fl = math.floor((fresh_live_p + 1e-9) * 100.0) / 100.0
                    m_eff_fl = max(main_slot.arm_100_p, mkt_fl)
                sold_idx_set.add(0)
                floor_cands.append(m_eff_fl)
                fired_main_trail = True

                # NEW: 주간 활성 2층(GRID_L2) 목표가가 1층 점화가/스탑가 이하로 역전(또는 동시 돌파) 시 1층 청산가로 2층 동반 졸업
                if len(buckets) >= 2 and has_active_l2_bucket(buckets):
                    b2_day = buckets[1]
                    raw_l2_day_t = (
                        math.ceil(
                            (
                                b2_day.book_price
                                * (1.0 + rise_sell_upper_pct / 100.0)
                                - 1e-9
                            )
                            * 100.0
                        )
                        / 100.0
                    )
                    l1_inv_ref = max(
                        main_slot.arm_100_p,
                        m_stop,
                        m_eff_fl,
                    )
                    if raw_l2_day_t <= l1_inv_ref + 1e-9:
                        sold_idx_set.add(1)
                    elif fresh_live_p >= raw_l2_day_t - 1e-9:
                        sold_idx_set.add(1)
                        floor_cands.append(raw_l2_day_t)

        # [서브 1층 2차 실호가 검문 및 "허락보다 용서를" 분기]
        if (
            sub_trail_trig
            and not bool(sell_eval.get("hit_sub_wma_grad"))
            and sub_buckets
            and has_active_l1_bucket(sub_buckets)
        ):
            sub_slot.peak_p = max(sub_slot.peak_p, fresh_live_p)
            s_stop = sub_slot.refresh_stop_price()
            if fresh_live_p < sub_slot.arm_100_p - 1e-9:
                sub_slot.release_forgive(bad_ha_minute_key=bad_ha_mk)
                forgiven_any = True
                logger.info(
                    "💡 [Case 99 서브 1층 '허락보다 용서를' 릴리스 & 기존 HA 망각] 실호가=$%.2f < +1.00%%($%.2f) -> 허공주문 차단 · 망각봉=%s",
                    fresh_live_p,
                    sub_slot.arm_100_p,
                    bad_ha_mk or "-",
                )
            elif sub_trail_trig == "TRAIL_CB_STOP" and (
                s_stop <= 0.0 or fresh_live_p >= s_stop - 1e-9
            ):
                pass
            else:
                eff_s_lock = (
                    sub_slot.lock_floor_p
                    if sub_slot.lock_floor_p > 0.0
                    else sub_slot.arm_100_p
                )
                if (
                    sub_trail_trig == "TRAIL_CAP_500"
                    and fresh_live_p >= sub_slot.cap_500_p - 1e-9
                ):
                    s_eff_fl = sub_slot.cap_500_p
                elif fresh_live_p >= eff_s_lock - 1e-9:
                    s_mkt_fl = (
                        math.floor((fresh_live_p * 0.998 + 1e-9) * 100.0)
                        / 100.0
                    )
                    s_eff_fl = max(eff_s_lock, s_mkt_fl)
                else:
                    s_mkt_fl = (
                        math.floor((fresh_live_p + 1e-9) * 100.0) / 100.0
                    )
                    s_eff_fl = max(sub_slot.arm_100_p, s_mkt_fl)
                sub_sold_idx_set.add(0)
                floor_cands.append(s_eff_fl)
                fired_sub_trail = True

        if not sold_idx_set and not sub_sold_idx_set:
            return {
                "status": (
                    "MONITORING_RELEASED_FORGIVEN"
                    if forgiven_any
                    else "MONITORING_0_4S_L1_STEP_TRAIL"
                ),
                "did_sell_or_ratchet": False,
                "forgiven_release": forgiven_any,
            }

        sold_indices = sorted(sold_idx_set)
        sub_sold_indices = sorted(sub_sold_idx_set)
        sell_qty = max(
            1,
            sum(buckets[i].qty for i in sold_indices if i < len(buckets))
            + sum(
                sub_buckets[si].qty
                for si in sub_sold_indices
                if si < len(sub_buckets)
            ),
        )
        raw_min_fl = max(floor_cands) if floor_cands else fresh_live_p
        min_floor_p = max(
            0.01,
            math.ceil((raw_min_fl - 1e-9) * 100.0) / 100.0,
        )

        if bool(sell_eval.get("should_sell")):
            base_tag = str(sell_eval.get("reason_tag") or "SELL_L1_ONLY")
            if (fired_main_trail or fired_sub_trail) and base_tag in (
                "SELL_GRID_INDIV",
                "SELL_SUB_GRID_INDIV",
            ):
                reason_tag = (
                    "SELL_SUB_L1_AND_GRID"
                    if (sub_sold_indices and not sold_indices)
                    else "SELL_L1_AND_GRID"
                )
            else:
                reason_tag = base_tag
        elif fired_sub_trail and not fired_main_trail:
            reason_tag = (
                "SELL_SUB_ALL_GRAD"
                if len(sub_sold_indices) == len(sub_buckets)
                and len(sub_buckets) > 1
                else "SELL_SUB_L1_ONLY"
            )
        elif fired_main_trail and fired_sub_trail:
            reason_tag = "SELL_MAIN_AND_SUB"
        elif fired_main_trail and len(sold_indices) > 1:
            reason_tag = (
                "SELL_ALL_GRAD"
                if len(sold_indices) == len(buckets)
                else "SELL_L1_AND_GRID"
            )
        else:
            reason_tag = "SELL_L1_ONLY" 

        if fresh_live_p > (min_floor_p * MARKETABLE_GAP_UP_THRESHOLD_MULT):
            gap_exec_p = max(
                min_floor_p, fresh_live_p * MARKETABLE_GAP_UP_SLIPPAGE_MULT
            )
            order_limit_p = max(
                min_floor_p,
                math.floor((gap_exec_p + 1e-9) * 100.0) / 100.0,
            )
        else:
            order_limit_p = min_floor_p

        sweep_res = await execute_bulletproof_sell_sweep(
            context=context,
            symbol=TARGET_SYMBOL,
            holdings_qty=sell_qty,
            sweep_price=order_limit_p,
            min_floor_price=min_floor_p,
            reason_tag=reason_tag,
            pending_sell_indices=sold_indices,
            pending_sub_sell_indices=sub_sold_indices,
        )
        did_order = str(sweep_res.get("status") or "") in (
            "NEW_SELL_SWEEP_OK",
            "SELL_ORDER_ALREADY_ACTIVE",
        )
        if did_order:
            if 0 in sold_indices or bool(sell_eval.get("hit_wma_grad")):
                main_slot.full_reset()
            if 0 in sub_sold_indices or bool(
                sell_eval.get("hit_sub_wma_grad")
            ):
                sub_slot.full_reset()
        if did_order and (triggered_by_wick_only or wick_trade_ts > 0.0):
            _LAST_CONSUMED_WICK_TRADE_TS = max(
                _LAST_CONSUMED_WICK_TRADE_TS,
                wick_trade_ts if wick_trade_ts > 0.0 else time.time(),
            )
        return {
            "status": (
                "SNIPER_MULTI_GRID_SELL_ORDERED"
                if did_order
                else str(sweep_res.get("status") or "SILENT_EXTENDED_HOLD")
            ),
            "did_sell_or_ratchet": did_order,
            "sell_mode": reason_tag,
            "sold_indices": sold_indices,
            "sub_sold_indices": sub_sold_indices,
            "qty": sell_qty,
            "sweep_price": order_limit_p,
            "min_floor_price": min_floor_p,
            "wick_high_price": wick_high_p,
            "result": sweep_res,
        }

    ref_b0_p = (
        buckets[0].book_price
        if buckets
        else (sub_buckets[0].book_price if sub_buckets else live_p)
    )
    chg_now_pct = (
        ((live_p - ref_b0_p) / ref_b0_p) * 100.0 if ref_b0_p > 0.0 else 0.0
    )
    is_ov_locked = bool(sell_eval.get("overnight_indiv_locked", False))
    return {
        "status": (
            "HOLD_OVERNIGHT_WMA_LOCK"
            if is_ov_locked
            else "MONITORING_1_5S_REALTIME_SNIPER_SELL"
        ),
        "did_sell_or_ratchet": False,
        "overnight_indiv_locked": is_ov_locked,
        "chg_from_first_tier_pct": round(chg_now_pct, 2),
        "target_l1_pct": rise_sell_l1_pct,
    }


# 하위 호환 별칭 (타 모듈에서 호출 시 안전 직결)
execute_sniper_exit_plugin = execute_1m_sniper_sell_and_reanchor_plugin
manage_mechanical_profit_trap_plugin = execute_1m_sniper_sell_and_reanchor_plugin
reconcile_zero_holdings_exit_plugin = sync_pending_sell_order_plugin
