# -*- coding: utf-8 -*-
"""
# MODIFIED: sniper_exit_plugin.py
순수 롱(SOXL) 전용 '매수 체결 후 최초 60초 강제 타임쉴드(POST_BUY_TO_SELL_SHIELD_SEC = 60.0) &
매수 후 60초 경과 시점부터 프리마켓·정규장·애프터마켓(16:00 ~ 19:59 EST)·데이마켓(20:00 ~ 03:59 EST) 24시간 전 세션에서
보유 중 60초 블라인드 대기 락 없이 매 1.5초 실시간 다중 익절(7층 본 그리드 + Default-ON 3층 서브 그리드 + 독립 골든포켓) 타점 스나이퍼 매도 모니터(Case 70, Case 71, Case 72, Case 79, Case 80, Case 82, Case 83, Case 84, Case 87, Case 88) ·
🚨 [Case 83 방안 C 오버나이트 통합이평 사수 하이브리드 & Case 88 & 상단 순수 통합이평 +1.00% 도달 시 1층 무조건 동일 가격 포함 전량 매도 사이클 종료]
애프터마켓·데이마켓(is_ext_sell_only == True) 구간에서 상단 지층(본 2 ~ 7층 / 서브 2 ~ 3층) 보유 시
하단 개별 층(1층 및 상단 개별/합병층) 쪼개 팔기를 잠가 저가 물량 이탈로 인한 통합 이동평균(wma_2_to_7 / sub_wma_2_to_3) 도망을 100% 원천 봉쇄하고,
2층 ~ 7층(서브 2층 ~ 3층) 순수 이동평균(1층 매수 가격 100% 배제) 대비 +1.00% 목표가 도달 시에는
1층 매수 가격과 무관하게 1층 물량까지 동일한 가격에 조건 없이 전량 포함 매도(SELL_ALL_GRAD / SELL_SUB_ALL_GRAD)하여 즉시 0주 사이클을 종료시키며,
04:07:00 EST 프리장 개장(is_ext_sell_only == False) 즉시 프리장 시초가로 본·서브·골든포켓 다중 익절을 전면 개방하여 시초가 갭상승 수익 극대화! ·
🔄 [현재 사이클 단위 실현수익(cycle_realized_net_usd) 자동 추적 및 0주 졸업 시 직전 사이클 수익(last_cycle_realized_net_usd) 박제 후 $0.00 리셋]
부분 익절 시에는 현재 진행 사이클의 실현순익(cycle_realized_net_usd)과 익절 횟수(cycle_sell_events)를 누적하고,
전 지층 0주 졸업(is_graduated_zero == True) 순간 이번 사이클 총 확정수익을 졸업 알림에 브리핑한 뒤 last_cycle_realized_net_usd 에 박제하고
새 사이클을 위해 cycle_realized_net_usd = 0.0 으로 자동 리셋! ·
🛡️ [Case 84 : 정규장 마감 30분 전(15:30 ~ 16:00 EST) 0주 새 사이클 첫 1층 진입 및 1층 공석 +1.0% 돌파 추격 동시 차단 알림 연동]
15:29:01 ~ 16:00:00 EST 구간에 0주 전량 졸업 달성 시 60초 타임쉴드 직후 15:30 EST 이상이 되어 새 사이클 1층 진입이 자동 차단되므로
익일 04:07 EST 프리장 진입 대기 안내를 표출하고, 1층 익절 후 상단층 잔존(1층 공석) 시에는 +1.0% 돌파 차단 및 2층 상한 이하 -1.0% 눌림목 재장전 감시 안내를 표출! ·
👑 [Case 87 : 06_L2L7_RATCHET_8PCT] & 🛡️ [Case 88 : 13_SUB_L1L3_RESV05_CAP4L] 본 그리드 중간 합병층 또는 서브 그리드 양끝 합병층 익절 체결 시
잔여 지층이 존재하는 동안에는 사이클 최고 도달 회차(cycle_ratchet_max_lots / sub_ratchet_max_lots) 잠금을 그대로 유지하고 해당 그리드 0주 졸업 시에만 0으로 리셋! ·
1.5초 실시간 감시 중 익절 조건 도래 및 최근접 유효 목표가 -2.50% 이내 근접 시 GET /api/v1/trades 최근 5.0초 체결틱 최고가(wick_high_p) 병행 감지로
1분봉 윗꼬리(Upper-Wick) 슈팅을 100% 포착하되, 2차 재조회 시 max(live_p, fresh_live_p) 고점 박제를 배제하고 순수 fresh_live_p 기준으로 즉시 체결 가능한 하위 지층을 분리 보호하며
윗꼬리 타임스탬프(_LAST_CONSUMED_WICK_TRADE_TS)는 실주문 발주 성공 시에만 각인하고
목표 익절 하한가(min_floor_p, +0.50% 초과 대폭 갭상승 시 fresh_live_p * 0.997 마켓터블 지정가)로 직결 지정가(LIMIT) 매도 발주(Case 82) ·
연타 익절 시 장외 sellableQuantity 정산 시차 대비 폴링 대기 2.0초 정량 확인(sellable_q >= target_sell_qty) 및 일시 0주 반환 시 쿨다운 5.0초 단축(진성 422 거래제한 시 60초 묵음 쿨다운 유지 · Case 79, Case 82) ·
매수 1호가(Bid 1) 하향 추격 정정 100% 영구 소각 및 미체결 단조시계(last_modify_mono) 역전 자가 치유 · 세션 경계 force_settle 강제 정산(Case 65, Case 66) ·
리앵커링 원가 차감 영구 폐기 및 순수 실물 원가(book_price == actual_avg_price) 100% 보존(Case 69, Case 71, Case 72, Case 80, Case 88) ·
💰 [Case 86] 매도 FILLED 정산 시 토스 execution.commission / tax 실측 수수료 및 계좌별 고유 왕복 수수료율(0.14% / 0.20%) 자동 반영 ·
독립 골든포켓(golden_pocket) 및 3층 서브 그리드(sub_buckets) 단독/동시 익절 시 기존 본 그리드(buckets)의 단가·기억저가·최고회차·목표정량 100% 비오염 보존 및 원리금 복리 환원(Case 80, Case 87, Case 88) ·
1층 익절 후 상단층 잔존 시 1층 공석 보존 · 상단 익절 후 1층 단독 잔류 시 알림 정밀 표출 ·
l1_target_quota_qty / sub_l1_target_quota_qty = 0 자동 클리어 및 1층 부분 익절 시 잔여 수량 동기화(허위 TOPUP_1FL 재매수 차단 · Case 78) ·
익절 매도로 가용현금 회복 시 시드고갈 입금 대기 및 단 1회 알림 래치(waiting_reserve_deposit_alert_sent) 자동 해제 &
본·서브·포켓 모두 0주 전량 졸업 시 온디맨드 예비시드 원금 자동 상환 및 6/6회분 한도 원상 복구(compute_reserve_repayment_on_zero · Case 77, Case 88) ·
매도 체결 즉시 기정산 주문 ID(last_settled_order_ids) 등록 및
60초 매도타임쉴드(last_sell_fill_ts / last_cycle_end_ts) & 1층 공석 재장전 타임쉴드 클리어(last_reentry_eval_ts / last_sub_reentry_eval_ts = 0.0) &
15초 잔고 인덱싱 그레이스 쉴드(last_auto_fill_ts) 동시 각인' 코어 플러그인 (Step 08 / 13)
- 제1헌법 ~ 제6헌법 및 Case 01 ~ 89 완벽 준수
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from quant_engine import (
    DEFAULT_GRID_MERGE_MODE,
    GOLDEN_POCKET_RISE_PCT,
    GoldenAllInPocket,
    MAX_GRID_TIERS_7,
    MAX_GRID_TIERS_12,
    MAX_RESERVE_PORTIONS,
    REANCHOR_NET_BUFFER_MULT,
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
    has_active_golden_pocket,
    has_active_l1_bucket,
    pocket_from_dict,
    pocket_to_dict,
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
# (SELL_MONITOR_TIME_SHIELD_SEC 는 AST 하위호환을 위해 유지하되 보유 중 블라인드 락은 0.0초로 해제)
POST_BUY_TO_SELL_SHIELD_SEC: float = 60.0
SELL_MONITOR_TIME_SHIELD_SEC: float = 0.0
POST_SELL_TO_BUY_SHIELD_SEC: float = 60.0

# 지정가 매도 주문 발주 후 미체결 최대 대기 시간(초) — 하향 추격 정정 없이 60초 미체결 시 안전 취소
SELL_ORDER_MAX_WAIT_SEC: float = 60.0

# [Case 79]: 데이마켓/애프터마켓 종목 집중 거래 제한 또는 세션 공백(422 order-hours-closed / stock-restricted 등) 시
# 알림 메시지 폭탄 없이 조용히 대기하는 인메모리 묵음 쿨다운 시간(초)
EXTENDED_SELL_RESTRICTION_COOLDOWN_SEC: float = 60.0

# [Case 82 : 윗꼬리($104.00) 슈팅 100% 즉시 체결을 위한 4대 핀포인트 상수 및 인메모리 상태]:
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


# ---------------------------------------------------------------------------
# 내부 헬퍼 : 실시간 SOXL 현재가 조회 · 윗꼬리 체결틱 역추적 · 장외 묵음 쿨다운 · 매수/매도 후 60초 타임쉴드 판별
# ---------------------------------------------------------------------------
def mark_extended_sell_restriction_cooldown(
    context: Any,
    symbol: str = TARGET_SYMBOL,
    cooldown_sec: float = EXTENDED_SELL_RESTRICTION_COOLDOWN_SEC,
    reason: str = "EXTENDED_RESTRICTED",
) -> None:
    """
    # [Case 79 & Case 82 : 데이마켓·애프터마켓 거래 제한/정산 시차 시 100% 묵음(Silent) 인메모리 쿨다운 각인]:
    """
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    c_sec = max(0.0, safe_float(cooldown_sec, 60.0))
    until_mono = (time.monotonic() + c_sec) if c_sec > 0.0 else 0.0
    snap_map = getattr(context, "exit_snapshot_cache", None)
    if isinstance(snap_map, dict):
        entry = snap_map.get(sym) if isinstance(snap_map.get(sym), dict) else {}
        entry["ext_sell_restrict_until_mono"] = until_mono
        entry["ext_sell_restrict_reason"] = str(reason or "EXTENDED_RESTRICTED")
        snap_map[sym] = entry


def is_within_extended_sell_restriction_cooldown(
    context: Any,
    symbol: str = TARGET_SYMBOL,
) -> Tuple[bool, float]:
    """
    # [Case 79 : 데이마켓·애프터마켓 거래 제한 묵음 쿨다운 작동 여부 판별]:
    """
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
    """
    # [Case 79]:
    - 프리장/정규장(allow_stale_fallback=True)에서는 prices -> 캔들 캐시 -> 보유 잔고 last_price 순으로 폴백한다.
    - 데이마켓/애프터마켓(allow_stale_fallback=False)에서는 오직 실시간 시세 API(prices)에서 조회된 가격만 인정한다.
    """
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
    """
    🚨 Case 65, Case 70, Case 79 & Case 82:
    1.5초 실시간 매도 모니터에서 익절 타점 도달이 감지된 직후(또는 가격 폴백 필요 시)
    토스 Open API(/api/v1/prices)를 직접 호출하여 가장 최신의 실시간 현재가를 확인한다.
    """
    try:
        fresh_map = await context.api.get_current_prices_batch((TARGET_SYMBOL,))
        fresh_p = safe_float((fresh_map or {}).get(TARGET_SYMBOL), 0.0)
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
    golden_pocket: Optional[GoldenAllInPocket],
    rise_l1_pct: float = 1.50,
    rise_upper_pct: float = 1.00,
    rise_pocket_pct: float = GOLDEN_POCKET_RISE_PCT,
    is_overnight_session: bool = False,
    sub_buckets: Optional[Sequence[StratumBucket]] = None,
) -> float:
    """
    # MODIFIED [Case 82, Case 83 (방안 C) & Case 88 : 본 그리드 + 3층 서브 그리드 + 골든포켓의 유효 최단 거리 익절 목표가(nearest_target_p) 산출기]:
    """
    candidates: List[float] = []
    l1_mult = 1.0 + max(0.1, safe_float(rise_l1_pct, 1.50)) / 100.0
    up_mult = 1.0 + max(0.1, safe_float(rise_upper_pct, 1.00)) / 100.0

    if (
        golden_pocket is not None
        and golden_pocket.is_active
        and golden_pocket.qty > 0
    ):
        gp_raw = golden_pocket.book_price * (
            1.0 + max(0.1, safe_float(rise_pocket_pct, 1.50)) / 100.0
        )
        gp_target = max(0.01, math.ceil((gp_raw - 1e-9) * 100.0) / 100.0)
        candidates.append(gp_target)

    if buckets:
        active_l1 = has_active_l1_bucket(buckets)
        wma_info = compute_upper_2_to_7_moving_avg(
            buckets, rise_upper_pct=rise_upper_pct
        )
        upper_cnt = safe_int(wma_info.get("upper_tier_count"), 0)

        # Case 83 방안 C: 프리/정규장이거나 상단 지층 없이 1층 단독 보유 시에만 개별 층 목표가를 후보에 추가
        if not (is_overnight_session and upper_cnt > 0):
            for idx, b in enumerate(buckets):
                if b.qty <= 0:
                    continue
                pure_bp = max(0.01, b.actual_avg_price, b.book_price)
                if idx == 0 and active_l1:
                    t_p = max(
                        0.01,
                        math.ceil((pure_bp * l1_mult - 1e-9) * 100.0) / 100.0,
                    )
                else:
                    t_p = max(
                        0.01,
                        math.ceil((pure_bp * up_mult - 1e-9) * 100.0) / 100.0,
                    )
                candidates.append(t_p)

        if upper_cnt > 0:
            wma_t = safe_float(wma_info.get("upper_wma_target_price"), 0.0)
            if wma_t > 0.0:
                candidates.append(wma_t)

    # NEW [Case 88 : 3층 서브 그리드 유효 익절 목표가 스캔]
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
                        math.ceil((pure_sbp * l1_mult - 1e-9) * 100.0)
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
    """
    # [Case 82 핵심 수술 3 : GET /api/v1/trades 최근 체결 내역 기반 1분봉 윗꼬리(Upper-Wick) 포착기]:
    """
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
    """
    🚨 [Case 69, Case 71, Case 72 & Case 88 진성 손익분기점(순수 매수 원가) 하한선 가드]:
    """
    if bucket.qty <= 0:
        return max(0.01, bucket.book_price)
    return round(max(0.01, bucket.actual_avg_price, bucket.book_price), 4)


def is_within_post_buy_time_shield(
    context: Any,
    st: Optional[Dict[str, Any]] = None,
    symbol: str = TARGET_SYMBOL,
) -> Tuple[bool, float]:
    """
    🚨 Case 65 [매수 체결 직후 최초 60.0초 강제 타임쉴드]:
    """
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
    """
    # [Case 70 & Case 75 : 보유 중 60초 블라인드 매도 대기 락 영구 해제 및 AST 심볼 호환 유지]:
    """
    sym = str(symbol or TARGET_SYMBOL).upper().strip()

    snap_map = getattr(context, "exit_snapshot_cache", None)
    if isinstance(snap_map, dict):
        entry = snap_map.get(sym) if isinstance(snap_map.get(sym), dict) else {}
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
    """
    # [Case 70 : 매수 직후 최초 60.0초 타임쉴드만 검문 & 이후 보유 중 1.5초 상시 실시간 감시 허용]:
    """
    return is_within_post_buy_time_shield(context, st, symbol)


def mark_post_sell_time_shield(
    context: Any,
    symbol: str = TARGET_SYMBOL,
    fill_price: float = 0.0,
    sold_qty: int = 0,
    is_cycle_end: bool = False,
) -> None:
    """
    🚨 Case 61, Case 65, Case 69, Case 70, Case 73, Case 77, Case 80, Case 82 & Case 88:
    매도 체결 및 0주 싸이클 종료 후 60.0초 매수 타임쉴드 & 본/서브 1층 공석/입금대기 타임쉴드 클리어 & 15.0초 잔고 인덱싱 그레이스 쉴드 동시 각인.
    """
    global _LAST_CONSUMED_WICK_TRADE_TS

    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    now_mono = time.monotonic()
    now_epoch = time.time()
    _LAST_CONSUMED_WICK_TRADE_TS = max(_LAST_CONSUMED_WICK_TRADE_TS, now_epoch)

    snap_map = getattr(context, "exit_snapshot_cache", None)
    if isinstance(snap_map, dict):
        entry = snap_map.get(sym) if isinstance(snap_map.get(sym), dict) else {}
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
    """
    🚨 Case 65 & Case 88 [매도 체결 및 0주 싸이클 종료 후 60.0초 강제 타임쉴드 판별]:
    """
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
    """
    Case 19 & Case 70: 보유 중 exit_snapshot_cache["SOXL"] 에 실보유 수량과 평단가,
    현재가를 백업하되 기존의 타임쉴드 시각을 안전하게 보존한다.
    """
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
# [핵심 1] Case 24, Case 65, Case 70, Case 71, Case 72, Case 79, Case 80, Case 82, Case 83 & Case 88 : 목표 하한가 직결 지정가(LIMIT) 다중 그리드(본+서브)/골든포켓 스나이퍼 매도 발주
# ---------------------------------------------------------------------------
async def execute_bulletproof_sell_sweep(
    context: Any,
    symbol: str = TARGET_SYMBOL,
    holdings_qty: int = 1,
    sweep_price: float = 0.0,
    min_floor_price: float = 0.0,
    reason_tag: str = "SELL_L1_ONLY",
    pending_sell_indices: Optional[Sequence[int]] = None,
    pending_sell_pocket_qty: int = 0,
    pending_sub_sell_indices: Optional[Sequence[int]] = None,
) -> Dict[str, Any]:
    """
    🚨 Case 24, Case 65, Case 70, Case 71, Case 72, Case 79, Case 80, Case 82, Case 83 & Case 88:
    1.5초 실시간 다중 익절(본 그리드 + 서브 그리드 + 골든포켓) 스나이퍼 매도 발사 시 목표 익절 하한가(min_floor_price) 또는
    대폭 갭상승 시 마켓터블 지정가(sweep_price)로 LIMIT 매도 주문을 즉시 발주한다.
    """
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
    clean_pocket_q = max(0, safe_int(pending_sell_pocket_qty, 0))

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

        # MODIFIED [Case 82 & Case 88 : 목표 매도 수량(target_sell_qty) 전량 반영까지 최대 2.0초 정량 폴링 대기]
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
        eff_pocket_q = min(clean_pocket_q, final_qty)
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
                pending_sell_pocket_qty=eff_pocket_q,
                last_modify_mono=time.monotonic(),
                last_sell_gate_eval_ts=0.0,
            )
            context.wakeup_event.set()
            logger.info(
                "🔥 [%s] 1.5초 실시간 타점 다중익절 스나이퍼 매도 발사(%s · main=%s · sub=%s · pocket=%d주) 완료: %d주 @ 지정가 $%.2f (목표하한 $%.2f · orderId=%s)",
                sym,
                reason_tag,
                clean_indices,
                clean_sub_indices,
                eff_pocket_q,
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
                "sell_pocket_qty": eff_pocket_q,
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
# [핵심 2] 실물 매도 FILLED 정산 · 골든포켓/서브그리드/본그리드 분리 정산(Case 80, 88) · 최고도달회차 잠금 유지(Case 87, 88) · 현재 사이클 단위 실현수익 누적 및 0주 졸업 시 자동 리셋(📌 ③) · 실측/동적 수수료 차감 세후 순익 복리 산입 · 0주 졸업 시 예비시드 자동 상환
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
    # MODIFIED [🎯 1 ~ 🎯 4 & Case 19, 59 ~ 89 & 본/서브 최고 도달 회차 잠금 유지 · Default-ON 3층 서브 그리드 분리 정산 · 현재 사이클 단위 실현수익(cycle_realized_net_usd) 누적 및 0주 전량 졸업 시 직전 사이클 수익(last_cycle_realized_net_usd) 박제 후 $0.00 자동 리셋(📌 ③) · 상단 순수 통합이평 +1.00% 도달 시 1층 포함 전량 매도 사이클 종료 · 본+서브/서브+포켓 동시익절 통계/알림 보강 · Case 84 알림 연동]:
    7층 골디락스 본 그리드, Default-ON 3층 서브 그리드 및 독립 골든포켓 스나이퍼 매도 주문이 체결(FILLED 또는 부분 체결 후 취소 종료)되었을 때:
    1) pending_sell_pocket_qty, pending_sub_sell_indices, pending_sell_indices 에 해당하는 순수 매수 원금과 실제 매도 체결가(avg_fill_price)에 대해,
       토스 execution.commission + tax 실측값(actual_sell_fee_usd) 및 계좌별 왕복 수수료율(eff_rt_pct : 0.14% 또는 0.20%)을 적용하여
       세후 실현 순수익금(net_pnl_usd)을 정밀 산출한다.
    2) 🚨 [Case 80 & Case 88 : 골든포켓 또는 서브 그리드 단독/동시 익절 시 7층 본 그리드 100% 비오염 보존]
    3) 👑 [Case 87 & Case 88 : 부분 익절 시 잔여 지층이 존재하는 동안에는 cycle_ratchet_max_lots / sub_ratchet_max_lots 잠금을 그대로 유지하고,
       해당 그리드가 0주 졸업했을 때만 0으로 리셋!]
    4) 🚨 [Case 78 : 본·서브 1층 부분 익절 시 l1_target_quota_qty / sub_l1_target_quota_qty 잔여 수량 동기화로 허위 TOPUP_1FL 재매수 원천 차단]
    5) 🚨 [Case 77, Case 80 & Case 88 : 본·서브·골든포켓 모두 0주 전량 졸업 시 예비시드 자동 상환]
    6) 🔄 [📌 ③ 현재 사이클 단위 수익 추적 및 0주 졸업 시 자동 리셋 : 부분 익절 시에는 cycle_realized_net_usd 에 누적하고,
       is_graduated_zero == True 순간 이번 사이클 최종 확정수익을 last_cycle_realized_net_usd 에 박제한 뒤 cycle_realized_net_usd = 0.0 으로 자동 리셋!]
    """
    st = context.ledger.get_state(TARGET_SYMBOL)
    buckets = buckets_from_dicts(st.get("buckets", []))
    sub_buckets = buckets_from_dicts(st.get("sub_buckets", []))
    gp = pocket_from_dict(st.get("golden_pocket"))
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

    settled_oids: List[str] = list(st.get("last_settled_order_ids") or [])
    if eff_oid and eff_oid not in settled_oids:
        settled_oids.append(eff_oid)
    settled_oids = settled_oids[-50:]

    if not buckets and not sub_buckets and not gp.is_active:
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
            pending_sell_pocket_qty=0,
            last_settled_order_ids=settled_oids,
        )
        return {"status": "NO_BUCKETS_TO_SETTLE"}

    rem_fill_to_alloc = q_filled
    raw_pending_pocket_q = max(
        0, safe_int(st.get("pending_sell_pocket_qty"), 0)
    )
    if raw_pending_pocket_q <= 0 and gp.is_active and mode in (
        "SELL_GOLDEN_POCKET",
        "SELL_POCKET_AND_GRID",
        "SELL_SUB_AND_POCKET",
    ):
        raw_pending_pocket_q = gp.qty

    # 1) 독립 골든포켓(golden_pocket) 매도 수량 우선 배분 및 잔여 포켓 산출 (Case 80)
    sold_pocket_q = 0
    sold_pocket_cost = 0.0
    rem_gp = pocket_from_dict(gp.to_dict())

    if rem_gp.is_active and raw_pending_pocket_q > 0 and rem_fill_to_alloc > 0:
        alloc_p_q = min(rem_gp.qty, raw_pending_pocket_q, rem_fill_to_alloc)
        if alloc_p_q >= rem_gp.qty:
            sold_pocket_q = rem_gp.qty
            sold_pocket_cost = round(rem_gp.actual_cost_usd, 4)
            rem_gp = GoldenAllInPocket()
        else:
            sold_pocket_q = alloc_p_q
            unit_gp_p = rem_gp.actual_avg_price
            sold_pocket_cost = round(float(sold_pocket_q) * unit_gp_p, 4)
            keep_gp_q = rem_gp.qty - sold_pocket_q
            keep_gp_cost = round(
                max(
                    0.01 * float(keep_gp_q),
                    rem_gp.actual_cost_usd - sold_pocket_cost,
                ),
                4,
            )
            rem_gp = GoldenAllInPocket(
                qty=keep_gp_q,
                book_price=round(keep_gp_cost / float(keep_gp_q), 4),
                book_invested_usd=keep_gp_cost,
                actual_cost_usd=keep_gp_cost,
                entry_ts=rem_gp.entry_ts,
                order_date=rem_gp.order_date,
            )
        rem_fill_to_alloc -= sold_pocket_q

    # 2) Default-ON 3층 서브 그리드(sub_buckets) 매도 수량 배분 및 잔여 서브 지층 산출 (Case 88)
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

    # MODIFIED: 서브 그리드 상단 통합이평 졸업 시 서브 1층(index 0)도 무조건 포함하여 전량 졸업
    if not sub_target_indices and rem_fill_to_alloc > 0 and sub_buckets:
        if mode in (
            "SELL_SUB_ALL_GRAD",
            "SELL_SUB_WMA_UPPER",
            "SELL_SUB_AND_POCKET",
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

    # 3) 1층 ~ 7층 본 그리드(buckets) 매도 수량 배분 및 잔여 지층 산출
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

    # MODIFIED: 본 그리드 2~7층 통합이평 졸업 시 1층(index 0)도 무조건 포함하여 전량 졸업(사이클 완전 종료)
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
        elif mode != "SELL_GOLDEN_POCKET":
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

    # 잔여 미배분 체결 수량이 남아 있을 경우 서브 -> 본 그리드 -> 포켓 순 폴백 배분
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

    if rem_fill_to_alloc > 0 and rem_gp.is_active:
        alloc_extra_gp = min(rem_gp.qty, rem_fill_to_alloc)
        if alloc_extra_gp >= rem_gp.qty:
            sold_pocket_q += rem_gp.qty
            sold_pocket_cost = round(
                sold_pocket_cost + rem_gp.actual_cost_usd, 4
            )
            rem_gp = GoldenAllInPocket()
        else:
            unit_gp_p = rem_gp.actual_avg_price
            extra_cost = round(float(alloc_extra_gp) * unit_gp_p, 4)
            keep_gp_q = rem_gp.qty - alloc_extra_gp
            keep_gp_cost = round(
                max(0.01 * float(keep_gp_q), rem_gp.actual_cost_usd - extra_cost),
                4,
            )
            sold_pocket_q += alloc_extra_gp
            sold_pocket_cost = round(sold_pocket_cost + extra_cost, 4)
            rem_gp = GoldenAllInPocket(
                qty=keep_gp_q,
                book_price=round(keep_gp_cost / float(keep_gp_q), 4),
                book_invested_usd=keep_gp_cost,
                actual_cost_usd=keep_gp_cost,
                entry_ts=rem_gp.entry_ts,
                order_date=rem_gp.order_date,
            )
        rem_fill_to_alloc -= alloc_extra_gp

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

    sold_q = sold_grid_q + sold_sub_q + sold_pocket_q
    sold_actual_cost = round(
        sold_grid_cost + sold_sub_cost + sold_pocket_cost, 4
    )
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

    pocket_net_pnl = 0.0
    if sold_pocket_q > 0:
        pocket_sell_fee: Optional[float] = None
        if (
            actual_sell_fee_usd is not None
            and safe_float(actual_sell_fee_usd, 0.0) > 0.0
            and sold_q > 0
        ):
            pocket_sell_fee = round(
                safe_float(actual_sell_fee_usd, 0.0)
                * (float(sold_pocket_q) / float(sold_q)),
                4,
            )
        p_pnl_info = calc_sell_realized_pnl(
            sold_qty=sold_pocket_q,
            sell_exec_price=fill_p,
            sold_actual_cost_usd=sold_pocket_cost,
            round_trip_fee_rate_pct=eff_rt_pct,
            actual_sell_fee_usd=pocket_sell_fee,
        )
        pocket_net_pnl = p_pnl_info["net_pnl_usd"]

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
    is_graduated_zero = bool(
        is_grid_empty and is_sub_empty and not rem_gp.is_active
    )
    is_pocket_only_sell = bool(
        sold_pocket_q > 0 and sold_grid_q == 0 and sold_sub_q == 0
    )
    is_sub_without_main_sell = bool(
        sold_sub_q > 0 and sold_grid_q == 0
    )

    # [Case 87 & Case 88 : 부분 익절 시 본/서브 최고 도달 회차 잠금 유지 및 해당 그리드 0주 졸업 시 리셋]
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

    # 서브 그리드 통계 및 동결일 갱신 (Case 88)
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

    # MODIFIED [Case 87 & Case 88 : 본 그리드와 서브 그리드/골든포켓 동시 매도(SELL_MAIN_AND_SUB 등) 시에도 본 그리드 상단 실제 소진 여부로 wma_inc / indiv_inc 정밀 집계]
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

    gp_sell_inc = 1 if sold_pocket_q > 0 else 0

    indiv_cnt = safe_int(st.get("indiv_grid_sell_cnt"), 0) + indiv_inc
    day_indiv_cnt = (
        safe_int(st.get("daily_indiv_grid_sell_cnt"), 0) + indiv_inc
    )
    wma_cnt = safe_int(st.get("wma_grad_sell_cnt"), 0) + wma_inc
    day_wma_cnt = safe_int(st.get("daily_wma_grad_sell_cnt"), 0) + wma_inc
    gp_sell_cnt = safe_int(st.get("golden_pocket_sell_cnt"), 0) + gp_sell_inc
    day_gp_sell_cnt = (
        safe_int(st.get("daily_golden_pocket_sell_cnt"), 0) + gp_sell_inc
    )
    gp_net_cum = round(
        safe_float(st.get("golden_realized_net_usd"), 0.0) + pocket_net_pnl, 4
    )
    gp_net_day = round(
        safe_float(st.get("daily_golden_realized_net_usd"), 0.0)
        + pocket_net_pnl,
        4,
    )

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

    # NEW [📌 ③ 현재 사이클 단위 실현수익 누적 및 0주 졸업(is_graduated_zero) 시 직전 사이클 박제 후 $0.00 자동 리셋]
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

    if is_graduated_zero and cur_inj_res_usd > 0.0:
        repay_info = compute_reserve_repayment_on_zero(
            initial_seed_usd=init_seed,
            cumulative_realized_net_usd=cum_net,
            injected_reserve_usd=cur_inj_res_usd,
            used_reserve_portions_cnt=cur_used_res_cnt,
            max_reserve_portions=MAX_RESERVE_PORTIONS,
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
                "🎓 [Case 77 0주 졸업 온디맨드 예비시드 자동 상환 완료] 상환액=$%.2f · 잔여수혈잔액=$%.2f · 예비한도 복구=%d/%d회분",
                repaid_this_time,
                next_inj_res_usd,
                MAX_RESERVE_PORTIONS - next_used_res_cnt,
                MAX_RESERVE_PORTIONS,
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
        "golden_pocket": rem_gp.to_dict(),
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
        "pending_sell_pocket_qty": 0,
        "last_settled_order_ids": settled_oids,
        "total_sell_events": tot_sell_ev,
        "total_sold_shares": tot_sold_sh,
        "win_sell_events": win_ev,
        "daily_sell_events": day_sell_ev,
        "indiv_grid_sell_cnt": indiv_cnt,
        "daily_indiv_grid_sell_cnt": day_indiv_cnt,
        "wma_grad_sell_cnt": wma_cnt,
        "daily_wma_grad_sell_cnt": day_wma_cnt,
        "golden_pocket_sell_cnt": gp_sell_cnt,
        "daily_golden_pocket_sell_cnt": day_gp_sell_cnt,
        "golden_realized_net_usd": gp_net_cum,
        "daily_golden_realized_net_usd": gp_net_day,
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
        if is_pocket_only_sell:
            grid_sh = sum(b.qty for b in rem_buckets)
            sub_sh = sum(sb.qty for sb in rem_sub_buckets)
            sub_p_note = f"+서브 {sub_sh}주" if sub_sh > 0 else ""
            title_msg = (
                f"🌟 [SOXL 독립 골든포켓 +1.5% 익절 체결{sess_tag}] "
                f"{sold_q}주 @ ${fill_p:.2f} ({r_sign}{net_rate:.2f}%)"
            )
            body_msg = (
                f"세후순익 {sign}${abs(net_pnl):,.2f} 시드 복리산입! · "
                f"🔄이번사이클 누적: {cyc_sign}${abs(cur_cyc_net):,.2f}({cur_cyc_ev}회) · "
                f"기존 본그리드({len(rem_buckets)}개층·{grid_sh}주{sub_p_note} · 기억저가 ${next_cycle_min_p:.2f}{ratchet_lock_note}) 무결성 유지 · "
                f"가용현금 ${free_cash_now:,.2f}"
            )
        elif is_sub_without_main_sell:
            grid_sh = sum(b.qty for b in rem_buckets)
            sub_sh = sum(sb.qty for sb in rem_sub_buckets)
            gp_co_note = (
                f"(서브 {sold_sub_q}주 + 골든포켓 {sold_pocket_q}주 동시익절) · "
                if sold_pocket_q > 0
                else ""
            )
            if is_sub_empty:
                sub_state_note = (
                    f"{gp_co_note}🎓 서브그리드 전량 졸업 완료(누적 {sub_comp_cycles}회 졸업 · 서브누적순익 +${sub_net_cum:,.2f})"
                )
            else:
                sub_state_note = (
                    f"{gp_co_note}📦 잔여 서브그리드 {len(rem_sub_buckets)}개층({sub_sh}주 · {rem_sub_held_lots}/{SUB_MAX_TOTAL_LOTS_4}회분) 감시 지속"
                )
            title_msg = (
                f"🛡️ [SOXL 3층 서브그리드 지정가 익절 체결 ({mode}{sess_tag})] "
                f"{sold_q}주 @ ${fill_p:.2f} ({r_sign}{net_rate:.2f}%)"
            )
            body_msg = (
                f"세후순익 {sign}${abs(net_pnl):,.2f} 시드 복리산입! · "
                f"🔄이번사이클 누적: {cyc_sign}${abs(cur_cyc_net):,.2f}({cur_cyc_ev}회) · "
                f"{sub_state_note} · 본그리드({len(rem_buckets)}개층·{grid_sh}주) 무결성 유지 · "
                f"가용현금 ${free_cash_now:,.2f}"
            )
        else:
            co_sold_parts: List[str] = []
            if sold_sub_q > 0:
                co_sold_parts.append(f"서브 {sold_sub_q}주")
            if sold_pocket_q > 0:
                co_sold_parts.append(f"골든포켓 {sold_pocket_q}주")
            co_sold_note = (
                f"(본 {sold_grid_q}주 + {' + '.join(co_sold_parts)} 동시익절) · "
                if co_sold_parts
                else ""
            )

            if is_graduated_zero:
                repay_note = ""
                if repaid_this_time > 0.0:
                    avail_p = max(0, MAX_RESERVE_PORTIONS - next_used_res_cnt)
                    repay_note = (
                        f" · 💉예비시드 원금 ${repaid_this_time:,.2f} 자동상환 완료"
                        f"(예비한도 {avail_p}/{MAX_RESERVE_PORTIONS}회분 복구!)"
                    )
                if is_ext_sell:
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
            elif is_grid_empty and (rem_gp.is_active or not is_sub_empty):
                rem_sub_sh = sum(sb.qty for sb in rem_sub_buckets)
                note_str = (
                    f"🔄이번사이클 누적: {cyc_sign}${abs(cur_cyc_net):,.2f}({cur_cyc_ev}회) · "
                    f"{co_sold_note}🌟 본그리드 전량 졸업 완료 · 잔여 서브({rem_sub_sh}주)/골든포켓({rem_gp.qty}주) 익절 감시 지속"
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
                            f"🔒장외 매수·개별층잠금(04:07 EST 이후 2층상한 ${l2_cap_p:.2f} 이하 1층재장전 · 기억저가 ${next_cycle_min_p:.2f}{ratchet_lock_note} 잠금)"
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
                f"세후순익 {sign}${abs(net_pnl):,.2f} 시드 복리산입! · "
                f"{note_str} · 가용현금 ${free_cash_now:,.2f}"
            )
        await context.send_slim_alert(title=title_msg, body=body_msg)

    return {
        "status": "SELL_FILLED_AND_SETTLED",
        "did_sell_or_ratchet": True,
        "sold_qty": sold_q,
        "sold_sub_qty": sold_sub_q,
        "sold_pocket_qty": sold_pocket_q,
        "fill_price": fill_p,
        "net_pnl_usd": net_pnl,
        "sub_net_pnl_usd": sub_net_pnl,
        "cycle_realized_net_usd": next_cyc_net,
        "last_cycle_realized_net_usd": next_last_cyc_net,
        "completed_main_cycles": next_comp_main_cycles,
        "repaid_reserve_usd": repaid_this_time,
        "reanchor_drop_usd": 0.0,
        "remaining_tiers": len(rem_buckets),
        "remaining_sub_tiers": len(rem_sub_buckets),
        "remaining_pocket_qty": rem_gp.qty,
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
    """
    # [🚨 Case 19, Case 24, Case 65, Case 66, Case 70, Case 71, Case 72, Case 78, Case 79, Case 80, Case 82, Case 86 & Case 88 실측 수수료 및 서브 그리드 연동]:
    장부에 대기 중인 미체결 매도 주문(sell_order_id)이 존재할 때:
    1) GET /api/v1/orders/{orderId} 로 FILLED 여부를 조회하여 체결 완료 시
       execution.commission + tax 실측값과 함께 _commit_filled_sell_and_reanchor_ledger() 로 복리 정산을 수행한다.
    2) 🚨 [Case 66 & Case 78 세션 경계 force_settle=True 강제 정산]
    3) 발주 후 60.0초 미체결 시 하향 추격 정정 없이 안전 취소 후 1.5초 실시간 타점 감시로 복귀한다.
    """
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
                if isinstance(final_det, dict):
                    f_ex = (
                        final_det.get("execution")
                        if isinstance(final_det.get("execution"), dict)
                        else {}
                    )
                    f_q2 = safe_int(f_ex.get("filledQuantity"), filled_q)
                    f_p2 = safe_float(
                        f_ex.get("averageFilledPrice"), avg_fill_p
                    )
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

        if ord_status in ("CANCELED", "REJECTED") and filled_q == 0:
            if ord_status == "REJECTED":
                mark_extended_sell_restriction_cooldown(
                    context,
                    symbol=TARGET_SYMBOL,
                    cooldown_sec=EXTENDED_SELL_RESTRICTION_COOLDOWN_SEC,
                    reason="SELL_ORDER_REJECTED",
                )
            await context.ledger.update_state(
                TARGET_SYMBOL,
                sell_order_id="",
                ordered_qty=0,
                target_sell_price=0.0,
                pending_sell_mode="",
                pending_sell_indices=[],
                pending_sub_sell_indices=[],
                pending_sell_pocket_qty=0,
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
        if isinstance(final_detail, dict):
            f_status = str(final_detail.get("status") or "").upper().strip()
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

        await context.ledger.update_state(
            TARGET_SYMBOL,
            sell_order_id="",
            ordered_qty=0,
            target_sell_price=0.0,
            pending_sell_mode="",
            pending_sell_indices=[],
            pending_sub_sell_indices=[],
            pending_sell_pocket_qty=0,
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


# ---------------------------------------------------------------------------
# [핵심 3] 24시간 전 세션(프리·정규·애프터·데이마켓) 매수 후 최초 60초 타임쉴드 & 이후 보유 중 매 1.5초 실시간 다중 익절(본+서브+포켓) + 방안 C 오버나이트 통합이평 사수 + 윗꼬리 즉시 체결 모니터 (Case 69 ~ 88)
# ---------------------------------------------------------------------------
async def execute_1m_sniper_sell_and_reanchor_plugin(
    context: Any,
    holdings: Dict[str, Dict[str, Any]],
    prices: Dict[str, float],
    now_est: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    # MODIFIED [🎯 2 Step 2 & Case 24, 44, 46 ~ 88 (방안 C 오버나이트 통합이평 사수 하이브리드 & 2~7층 순수 통합이평 +1.00% 도달 시 1층 물량 무조건 동일 가격 포함 전량 매도 & 본+서브+포켓 다중 익절 & 2차 재조회 시 순수 fresh_live_p 우선 평가)]:
    """
    global _LAST_CONSUMED_WICK_TRADE_TS

    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    hm = dt_now.hour * 100 + dt_now.minute

    st = context.ledger.get_state(TARGET_SYMBOL)

    # 1) 미체결 매도 주문이 있으면 먼저 체결 확인 수행
    if str(st.get("sell_order_id") or "").strip():
        return await sync_pending_sell_order_plugin(
            context=context,
            holdings=holdings,
            prices=prices,
            now_est=dt_now,
        )

    if not is_active_sell_window(hm, now_est=dt_now):
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
    gp = pocket_from_dict(st.get("golden_pocket"))
    if not buckets and not sub_buckets and not gp.is_active:
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
    ledger_total_qty = (
        sum(b.qty for b in buckets)
        + sum(sb.qty for sb in sub_buckets)
        + (gp.qty if gp.is_active else 0)
    )
    h_qty = safe_int(h_info.get("qty"), ledger_total_qty)
    default_avg_p = (
        buckets[0].actual_avg_price
        if buckets
        else (
            sub_buckets[0].actual_avg_price
            if sub_buckets
            else (gp.actual_avg_price if gp.is_active else live_p)
        )
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

    sell_eval = evaluate_multi_grid_sell_targets(
        buckets=buckets,
        live_price=live_p,
        rise_l1_pct=rise_sell_l1_pct,
        rise_upper_pct=rise_sell_upper_pct,
        golden_pocket=gp,
        rise_pocket_pct=GOLDEN_POCKET_RISE_PCT,
        is_overnight_session=is_ext_sell_only,
        sub_buckets=sub_buckets,
    )

    wick_high_p: float = 0.0
    wick_trade_ts: float = 0.0
    nearest_target_p: float = _compute_nearest_sell_target_price(
        buckets=buckets,
        golden_pocket=gp,
        rise_l1_pct=rise_sell_l1_pct,
        rise_upper_pct=rise_sell_upper_pct,
        rise_pocket_pct=GOLDEN_POCKET_RISE_PCT,
        is_overnight_session=is_ext_sell_only,
        sub_buckets=sub_buckets,
    )
    triggered_by_wick_only: bool = False

    if not bool(sell_eval.get("should_sell")):
        if nearest_target_p > 0.0 and live_p >= (
            nearest_target_p * WICK_PROXIMITY_TRIGGER_RATIO
        ):
            min_trade_after_ts = max(
                safe_float(st.get("last_buy_fill_ts"), 0.0),
                safe_float(st.get("last_sub_buy_fill_ts"), 0.0),
                safe_float(st.get("last_sell_fill_ts"), 0.0),
                safe_float(st.get("last_sub_sell_fill_ts"), 0.0),
                safe_float(st.get("entry_ts"), 0.0),
                safe_float((gp.entry_ts if gp.is_active else 0.0), 0.0),
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
            if wick_high_p >= nearest_target_p and wick_high_p > live_p:
                wick_eval = evaluate_multi_grid_sell_targets(
                    buckets=buckets,
                    live_price=nearest_target_p,
                    rise_l1_pct=rise_sell_l1_pct,
                    rise_upper_pct=rise_sell_upper_pct,
                    golden_pocket=gp,
                    rise_pocket_pct=GOLDEN_POCKET_RISE_PCT,
                    is_overnight_session=is_ext_sell_only,
                    sub_buckets=sub_buckets,
                )
                if not bool(wick_eval.get("should_sell")):
                    wick_eval = evaluate_multi_grid_sell_targets(
                        buckets=buckets,
                        live_price=wick_high_p,
                        rise_l1_pct=rise_sell_l1_pct,
                        rise_upper_pct=rise_sell_upper_pct,
                        golden_pocket=gp,
                        rise_pocket_pct=GOLDEN_POCKET_RISE_PCT,
                        is_overnight_session=is_ext_sell_only,
                        sub_buckets=sub_buckets,
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

    if bool(sell_eval.get("should_sell")):
        fresh_live_p = await _fetch_fresh_current_soxl_price(
            context,
            fallback_price=live_p,
        )
        if fresh_live_p <= 0.0:
            fresh_live_p = live_p

        # MODIFIED [Case 82 핵심 : max(live_p, fresh_live_p) 고점 박제 영구 배제 & 순수 fresh_live_p 기준 우선 재평가로 하위 지층 즉시 체결 보장]
        fresh_only_eval = evaluate_multi_grid_sell_targets(
            buckets=buckets,
            live_price=fresh_live_p,
            rise_l1_pct=rise_sell_l1_pct,
            rise_upper_pct=rise_sell_upper_pct,
            golden_pocket=gp,
            rise_pocket_pct=GOLDEN_POCKET_RISE_PCT,
            is_overnight_session=is_ext_sell_only,
            sub_buckets=sub_buckets,
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
                golden_pocket=gp,
                rise_pocket_pct=GOLDEN_POCKET_RISE_PCT,
                is_overnight_session=is_ext_sell_only,
                sub_buckets=sub_buckets,
            )
            if bool(lowest_tier_eval.get("should_sell")):
                sell_eval = lowest_tier_eval

        sold_indices = list(sell_eval.get("sold_indices") or [])
        sub_sold_indices = list(sell_eval.get("sub_sold_indices") or [])
        sell_pocket_qty = max(
            0, safe_int(sell_eval.get("sell_pocket_qty"), 0)
        )
        sell_qty = max(1, safe_int(sell_eval.get("sell_qty"), 1))
        min_floor_p = max(
            0.01,
            math.ceil(
                (safe_float(sell_eval.get("min_floor_price"), live_p) - 1e-9)
                * 100.0
            )
            / 100.0,
        )
        reason_tag = str(sell_eval.get("reason_tag") or "SELL_L1_ONLY")

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
            pending_sell_pocket_qty=sell_pocket_qty,
            pending_sub_sell_indices=sub_sold_indices,
        )
        did_order = str(sweep_res.get("status") or "") in (
            "NEW_SELL_SWEEP_OK",
            "SELL_ORDER_ALREADY_ACTIVE",
        )
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
            "sell_pocket_qty": sell_pocket_qty,
            "qty": sell_qty,
            "sweep_price": order_limit_p,
            "min_floor_price": min_floor_p,
            "wick_high_price": wick_high_p,
            "result": sweep_res,
        }

    ref_b0_p = (
        buckets[0].book_price
        if buckets
        else (
            sub_buckets[0].book_price
            if sub_buckets
            else (gp.book_price if gp.is_active else live_p)
        )
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
