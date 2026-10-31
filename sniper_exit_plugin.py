# -*- coding: utf-8 -*-
"""
# MODIFIED: sniper_exit_plugin.py
순수 롱(SOXL) 전용 '매수 체결 후 최초 60초 강제 타임쉴드(POST_BUY_TO_SELL_SHIELD_SEC = 60.0) &
매수 후 60초 경과 시점부터 프리마켓·정규장·애프터마켓(16:00 ~ 19:59 EST)·데이마켓(20:00 ~ 03:59 EST) 24시간 전 세션에서
보유 중 60초 블라인드 대기 락 없이 매 1.5초 실시간 4중 다중 익절 타점 스나이퍼 매도 모니터(Case 70, Case 71, Case 72, Case 79, Case 80, Case 82, Case 83) ·
🚨 [Case 83 방안 C 오버나이트 통합이평 사수 하이브리드] 애프터마켓·데이마켓(is_ext_sell_only == True) 구간에서 상단 2~7층 보유 시
하단 개별 층(1층 및 2~6층 개별) 쪼개 팔기를 잠가 저가 물량 이탈로 인한 2~7층 통합 이동평균(wma_2_to_7) 도망을 100% 원천 봉쇄하고,
오버나이트 중에는 통합 이동평균(+1.00%) 일괄 졸업(또는 1층 단독 보유 +1.50% / 독립 골든포켓 +1.50%)만 허용한 뒤,
04:07:00 EST 프리장 개장(is_ext_sell_only == False) 즉시 프리장 시초가로 4중 다중 익절을 전면 개방하여 시초가 갭상승 수익 극대화! ·
1.5초 실시간 감시 중 익절 조건 도래 및 최근접 유효 목표가 -2.50% 이내 근접 시 GET /api/v1/trades 최근 5.0초 체결틱 최고가(wick_high_p) 병행 감지로
1분봉 윗꼬리(Upper-Wick) 슈팅을 100% 포착하되, 다중 지층 윗꼬리 스침 시 상위층 고가 목표가 결합으로 인한 하위층 미체결 역설을 분리 차단하고
윗꼬리 타임스탬프(_LAST_CONSUMED_WICK_TRADE_TS)는 실주문 발주 성공 시에만 각인하며,
윗꼬리 최고점 박제(max(live_p, fresh_live_p)) 및 장외 재조회 매도 포기(fallback_price=0.0)를 영구 제거하여
목표 익절 하한가(min_floor_p, +0.50% 초과 대폭 갭상승 시 fresh_live_p * 0.997 마켓터블 지정가)로 직결 지정가(LIMIT) 매도 발주(Case 82) ·
연타 익절 시 장외 sellableQuantity 정산 시차 대비 폴링 대기 2.0초 확장 및 일시 0주 반환 시 쿨다운 5.0초 단축(진성 422 거래제한 시 60초 묵음 쿨다운 유지 · Case 79, Case 82) ·
매수 1호가(Bid 1) 하향 추격 정정 100% 영구 소각 및 미체결 단조시계(last_modify_mono) 역전 자가 치유(Case 65) ·
리앵커링 원가 차감 영구 폐기 및 순수 실물 원가(book_price == actual_avg_price) 100% 보존(Case 69, Case 71, Case 72, Case 80) ·
독립 골든포켓(golden_pocket) 단독 익절 시 기존 1~7층 그리드의 단가·기억저가·목표정량 100% 비오염 보존 및 원리금 복리 환원(Case 80) ·
1층 익절 후 상단 2~7층 잔존 시 1층 공석(GRID_L2 ~ GRID_L7) 보존 · l1_target_quota_qty = 0 자동 클리어 및 1층 부분 익절 시 잔여 수량 동기화(허위 TOPUP_1FL 재매수 차단 · Case 78) · 싸이클 최저가(cycle_min_buy_price) 잠금 유지(Case 59, Case 60, Case 71, Case 72, Case 73) ·
익절 매도로 가용현금 회복 시 시드고갈 입금 대기 및 단 1회 알림 래치(waiting_reserve_deposit_alert_sent) 자동 해제 &
0주 전량 졸업 시 온디맨드 예비시드 원금 자동 상환 및 6/6회분 한도 원상 복구(compute_reserve_repayment_on_zero · Case 77) ·
매도 체결(부분 익절 · 골든포켓 익절 및 0주 전량 졸업) 즉시 기정산 주문 ID(last_settled_order_ids) 등록 및
60초 매도타임쉴드(last_sell_fill_ts / last_cycle_end_ts) & 1층 공석 재장전 타임쉴드 클리어(last_reentry_eval_ts = 0.0) &
15초 잔고 인덱싱 그레이스 쉴드(last_auto_fill_ts) 동시 각인' 코어 플러그인 (Step 02 / 04)
- 제1헌법 ~ 제6헌법 및 Case 01 ~ 83 완벽 준수
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from quant_engine import (
    GOLDEN_POCKET_RISE_PCT,
    GoldenAllInPocket,
    MAX_GRID_TIERS_7,
    MAX_GRID_TIERS_12,
    MAX_RESERVE_PORTIONS,
    REANCHOR_NET_BUFFER_MULT,
    StratumBucket,
    buckets_from_dicts,
    buckets_to_dicts,
    calc_sell_realized_pnl,
    compute_reserve_repayment_on_zero,
    compute_upper_2_to_7_moving_avg,
    compute_upper_2_to_12_moving_avg,
    evaluate_multi_grid_sell_targets,
    get_golden8_prog_thresholds,
    has_active_golden_pocket,
    has_active_l1_bucket,
    pocket_from_dict,
    pocket_to_dict,
    relabel_upper_grid_tiers,
    vrev_reanchor_single_tier_quota,
)
from quant_indicators_plugin import (
    is_active_buy_window,
    is_active_sell_window,
    is_active_trading_window,
    is_extended_sell_only_window,
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
# 1) 장외 1층 체결 직후 연타 매도 시 브로커 원장 정산 시차로 sellableQuantity 가 일시 0주일 때
#    2.0초간 폴링 대기 후에도 0주면 60초 대신 5.0초만 대기 후 즉시 재타격
EXTENDED_NO_SELLABLE_RETRY_COOLDOWN_SEC: float = 5.0
SELLABLE_QTY_POLL_WAIT_SEC: float = 2.0
SELLABLE_QTY_POLL_INTERVAL_SEC: float = 0.25

# 2) GET /api/v1/trades 최근 체결틱 기반 윗꼬리(Upper-Wick) 병행 감지 파라미터
WICK_TRADE_LOOKBACK_SEC: float = 5.0
WICK_TRADE_FETCH_COUNT: int = 15
WICK_PROXIMITY_TRIGGER_RATIO: float = 0.975  # 최단 거리 익절 목표가 대비 -2.50% 이내 진입 시 체결틱 스캔
WICK_PROBE_MIN_INTERVAL_SEC: float = 1.2     # MARKET_DATA Rate Limit 보호용 최소 스캔 간격(초)

# 3) 목표 익절 하한가(min_floor_p) 직결 발주 및 대폭 갭상승(+0.50% 초과) 시 마켓터블 지정가 파라미터
MARKETABLE_GAP_UP_THRESHOLD_MULT: float = 1.005  # min_floor_p 대비 +0.50% 초과 대폭 갭상승 기준
MARKETABLE_GAP_UP_SLIPPAGE_MULT: float = 0.997   # 대폭 갭상승 시 즉시 체결용 -0.30% 마켓터블 버퍼

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
    데이마켓/애프터마켓에서 브로커가 특정 종목 거래를 제한(60초)하거나
    연속 매도 직후 원장 정산 시차로 sellableQuantity 가 일시 0주(5초)일 때,
    텔레그램 알림을 발송하지 않고 조용히 cooldown_sec 동안 재발주 시도를 보류한다.
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
    인메모리 묵음 쿨다운이 작동 중이면 (True, 잔여 초)를 반환한다.
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
    - 데이마켓/애프터마켓(allow_stale_fallback=False)에서는 브로커가 시세를 제공하지 않는 날
      정적 종가(holdings.last_price)나 과거 캔들 종가로 오발주하는 일을 막기 위해
      오직 실시간 시세 API(prices)에서 조회된 가격만 인정한다.
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
    (장외 일시 통신 지연 시에도 매도를 포기하지 않도록 fallback_price=live_p 를 안전 반환한다.)
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
) -> float:
    """
    # MODIFIED [Case 82 & Case 83 (방안 C) : 보유 지층 및 골든포켓의 유효 최단 거리 익절 목표가(nearest_target_p) 산출기]:
    - 프리장 + 정규장(is_overnight_session == False)에서는 ① 독립 골든포켓(+1.50%), ② 활성 1층(+1.50%),
      ③ 상단 2~7층 개별 층(+1.00%), ④ 상단 2~7층 통합 이동평균(+1.00%) 목표가 중
      가장 낮은(현재가에서 가장 가까운) 목표 익절가를 산출한다.
    - 🚨 [Case 83 방안 C] 오버나이트(is_overnight_session == True)이면서 상단 지층(2~7층)이 존재할 때는
      개별 층 쪼개 팔기가 잠겨 있으므로 개별 층 목표가를 후보에서 제외하고,
      오직 ① 독립 골든포켓(+1.50%) 및 ② 상단 2~7층 통합 이동평균 목표가(wma_t)만을 유효 목표가로 산출하여
      장외 불필요한 체결틱 API 호출을 원천 차단한다!
    """
    candidates: List[float] = []

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
        l1_mult = 1.0 + max(0.1, safe_float(rise_l1_pct, 1.50)) / 100.0
        up_mult = 1.0 + max(0.1, safe_float(rise_upper_pct, 1.00)) / 100.0

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

    return min(candidates) if candidates else 0.0


def _parse_trade_ts_fallback(ts_val: Any) -> float:
    """
    # [Case 82 : toss_api 구버전/모의 객체 호환용 ISO 8601 체결 시각 파서 폴백]
    """
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
    2.0 ~ 2.7초 폴링 간격 사이에 0.3초 동안만 $104.00 을 찍고 내려온 윗꼬리 체결틱을 포착하기 위해,
    최단 거리 목표가 대비 -2.50% 이내 근접 시 최근 체결 15건(직전 5.0초 이내 & min_after_ts 이후) 중
    최고 체결가(wick_high_p)와 해당 체결 시각(wick_ts)을 조회하여 반환한다.
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
                if age > max_age or age < -2.0:
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
    🚨 [Case 69, Case 71 & Case 72 진성 손익분기점(순수 매수 원가) 하한선 가드]:
    최종 확정 챔피언에서는 인위적 리앵커링 차감을 수행하지 않으므로,
    모든 그리드 지층의 기준 단가는 언제나 순수 실물 매수 평단가(actual_avg_price) 이상으로 강제된다.
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
    매수가 체결된 시점(last_buy_fill_mono 단조 시계 및 원장 last_buy_fill_ts / entry_ts)으로부터
    60.0초가 경과하기 전에는 True 와 남은 초(remain_sec)를 반환하여 일체의 매도(및 중복 매수) 시도를 차단한다.
    """
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    now_mono = time.monotonic()

    guard_map = getattr(context, "indexing_grace_cache", None)
    if isinstance(guard_map, dict):
        info = guard_map.get(sym)
        if isinstance(info, dict):
            last_buy_mono = safe_float(info.get("last_buy_fill_mono"), 0.0)
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
    보유 중 목표가 미달 시 60초간 눈을 감아 장중 윗꼬리(Upper-Wick) 익절 기회를 놓치던
    블라인드 쿨다운을 전면 해제하여, 항상 0.0(쿨다운 없음)으로 상태를 정리하고 반환한다.
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
    매수 체결 직후 최초 60.0초 호가 안정화 타임쉴드(is_within_post_buy_time_shield)만 확인하며,
    매수 후 60.0초가 경과한 뒤에는 언제나 (False, 0.0)을 반환하여 매 1.5초 실시간 타점 감시가 즉시 작동하도록 보장한다.
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
    🚨 Case 61, Case 65, Case 69, Case 70, Case 73, Case 77, Case 80 & Case 82:
    매도 체결 및 0주 싸이클 종료 후 60.0초 매수 타임쉴드 & 1층 공석/입금대기 타임쉴드 클리어 & 15.0초 잔고 인덱싱 그레이스 쉴드 동시 각인.
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
    🚨 Case 65 [매도 체결 및 0주 싸이클 종료 후 60.0초 강제 타임쉴드 판별]:
    직전 매도 체결 시각(last_sell_fill_mono / last_sell_fill_ts) 또는
    0주 싸이클 종료 시각(last_cycle_end_mono / last_cycle_end_ts)으로부터
    60.0초(POST_SELL_TO_BUY_SHIELD_SEC)가 경과하기 전에는 True 와 남은 초(remain_sec)를 반환한다.
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
        safe_float(state_obj.get("last_cycle_end_ts"), 0.0),
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
# [핵심 1] Case 24, Case 65, Case 70, Case 71, Case 72, Case 79, Case 80, Case 82 & Case 83 : 목표 하한가 직결 지정가(LIMIT) 다중 그리드/골든포켓 스나이퍼 매도 발주
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
) -> Dict[str, Any]:
    """
    🚨 Case 24, Case 65, Case 70, Case 71, Case 72, Case 79, Case 80, Case 82 & Case 83:
    1.5초 실시간 4중 다중 익절 스나이퍼 매도 발사 시:
    - 윗꼬리 꼭대기($104.00) 고점 박제로 인한 미체결을 원천 차단하기 위해,
      목표 익절 하한가(min_floor_price, 예: $103.91) 또는 대폭 갭상승 시 마켓터블 지정가(sweep_price)로
      LIMIT 매도 주문을 즉시 발주한다!
    - 매도 대상 그리드 인덱스 리스트(pending_sell_indices)와 독립 골든포켓 매도 수량(pending_sell_pocket_qty)을
      원장에 기록하여 체결 시 정확히 해당 물량만 정산한다.
    - 🛡️ [Case 82 수술 4 : 장외 sellableQuantity 대기 2.0초 확장 및 일시 0주 반환 시 쿨다운 5.0초 단축]:
      06:56 KST 1층 체결 직후 06:57 KST 2층 연타 익절 시 브로커 잔고 정산 시차로 sellableQuantity 가 순간 0주를 반환하더라도
      최대 2.0초(0.25초 주기)까지 재조회하며, 여전히 0주일 때는 60.0초가 아닌 5.0초(EXTENDED_NO_SELLABLE_RETRY_COOLDOWN_SEC)만
      짧게 대기 후 즉시 재타격한다! (실제 주문 전송 시 422 order-hours-closed / stock-restricted 거절된 경우에만 60.0초 묵음 쿨다운 유지)
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

        # [Case 82 핵심 수술 4]: 장외/정규장 모두 최대 2.0초(0.25초 주기) 동안 sellableQuantity 정산 완료를 끈질기게 대기
        sellable_q = 0
        deadline = time.monotonic() + SELLABLE_QTY_POLL_WAIT_SEC
        while time.monotonic() < deadline:
            sellable_q = await context.api.get_sellable_quantity(sym)
            if sellable_q >= target_sell_qty or sellable_q > 0:
                break
            await asyncio.sleep(SELLABLE_QTY_POLL_INTERVAL_SEC)

        # [Case 82 핵심 수술 4]: 장외에서 2.0초 대기 후에도 sellable_q == 0 이면
        # 1층 체결 직후 브로커 원장 정산 시차일 가능성이 높으므로 60.0초가 아닌 5.0초만 대기 후 즉시 재시도!
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
                pending_sell_pocket_qty=eff_pocket_q,
                last_modify_mono=time.monotonic(),
                last_sell_gate_eval_ts=0.0,
            )
            context.wakeup_event.set()
            logger.info(
                "🔥 [%s] 1.5초 실시간 타점 4중 다중익절 스나이퍼 매도 발사(%s · indices=%s · pocket=%d주) 완료: %d주 @ 지정가 $%.2f (목표하한 $%.2f · orderId=%s)",
                sym,
                reason_tag,
                clean_indices,
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
# [핵심 2] 실물 매도 FILLED 정산 · 골든포켓/그리드 분리 정산(Case 80) · 세후 순익 복리 산입 · 0주 졸업 시 예비시드 자동 상환
# ---------------------------------------------------------------------------
async def _commit_filled_sell_and_reanchor_ledger(
    context: Any,
    filled_qty: int,
    avg_fill_price: float,
    sell_mode: str,
    settled_order_id: str = "",
) -> Dict[str, Any]:
    """
    🎯 1 ~ 🎯 4 & Case 19, 59, 60, 61, 65, 69, 70, 71, 72, 73, 77, 78, 79, 80, 82, 83:
    7층 골디락스 멀티 그리드 및 독립 골든포켓 스나이퍼 매도 주문이 체결(FILLED 또는 부분 체결 후 취소 종료)되었을 때:
    1) pending_sell_pocket_qty (독립 골든포켓) 및 pending_sell_indices (1~7층 그리드)에 해당하는
       순수 매수 원금과 실제 매도 체결가(avg_fill_price)로 왕복 수수료(0.14%) 차감 후 세후 실현 순수익금을 산출한다.
    2) 🚨 [Case 80 골든포켓 단독 익절 시 7층 그리드 100% 비오염 보존]:
       - 만약 골든포켓만 단독 익절(sold_pocket_q > 0 and sold_grid_q == 0)되고 기존 그리드(rem_buckets)가 남아 있으면,
         그리드의 anchor_price, cycle_min_buy_price, l1_target_quota_qty 를 변경하지 않고 그대로 보존한다!
       - 골든포켓에서 발생한 세후 실현순익은 golden_realized_net_usd, daily_golden_realized_net_usd 및
         golden_pocket_sell_cnt, daily_golden_pocket_sell_cnt 에도 별도 누적 기록한다.
    3) 🚨 [Case 78 : 1층 부분 익절 시 l1_target_quota_qty 잔여 수량 동기화로 허위 TOPUP_1FL 재매수 원천 차단]:
       - 1층이 전량 소진되면 l1_target_quota_qty = 0 으로 클리어하고,
         1층이 일부만 부분 매도되어 rem_buckets[0].qty < buckets[0].qty 가 된 경우에는
         next_l1_target_q = rem_buckets[0].qty 로 즉시 동기화하여 익절된 물량을 미체결 매수 잔량으로 오인하지 않게 방어한다!
    4) 🚨 [Case 77 & Case 80 : 0주 전량 졸업(len(rem_buckets) == 0 and not rem_gp.is_active) 시 예비시드 자동 상환]
    """
    st = context.ledger.get_state(TARGET_SYMBOL)
    buckets = buckets_from_dicts(st.get("buckets", []))
    gp = pocket_from_dict(st.get("golden_pocket"))
    fill_p = round(max(0.01, safe_float(avg_fill_price, 0.01)), 4)
    q_filled = max(1, safe_int(filled_qty, 1))
    mode = str(
        sell_mode or st.get("pending_sell_mode") or "SELL_L1_ONLY"
    ).upper()
    eff_oid = str(settled_order_id or st.get("sell_order_id") or "").strip()

    settled_oids: List[str] = list(st.get("last_settled_order_ids") or [])
    if eff_oid and eff_oid not in settled_oids:
        settled_oids.append(eff_oid)
    settled_oids = settled_oids[-50:]

    if not buckets and not gp.is_active:
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
            l1_target_quota_qty=0,
            last_sell_fill_ts=now_empty_epoch,
            last_cycle_end_ts=now_empty_epoch,
            last_sell_gate_eval_ts=0.0,
            last_reentry_eval_ts=0.0,
            waiting_reserve_deposit=False,
            waiting_reserve_deposit_alert_sent=False,
            required_reserve_deposit_usd=0.0,
            last_reserve_check_ts=0.0,
            sell_order_id="",
            ordered_qty=0,
            target_sell_price=0.0,
            pending_sell_mode="",
            pending_sell_indices=[],
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

    # 2) 1층 ~ 7층 그리드(buckets) 매도 수량 배분 및 잔여 지층 산출
    was_active_l1 = has_active_l1_bucket(buckets)
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

    if not target_indices and rem_fill_to_alloc > 0 and buckets:
        if mode in ("SELL_ALL_GRAD", "SELL_L2_GRAD") or len(buckets) == 1:
            target_indices = list(range(len(buckets)))
        elif mode == "SELL_WMA_UPPER" and len(buckets) >= 2:
            start_i = 1 if was_active_l1 else 0
            target_indices = list(range(start_i, len(buckets)))
        elif mode != "SELL_GOLDEN_POCKET":
            target_indices = [0]

    target_set: Set[int] = set(target_indices)
    sold_l1_flag = bool(
        was_active_l1 and (0 in target_set) and rem_fill_to_alloc > 0
    )

    sold_buckets: List[StratumBucket] = []
    rem_buckets: List[StratumBucket] = []

    for idx, b in enumerate(buckets):
        if idx not in target_set or rem_fill_to_alloc <= 0:
            rem_buckets.append(b)
            continue

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

    sold_grid_q = sum(b.qty for b in sold_buckets)
    sold_grid_cost = round(sum(b.actual_cost_usd for b in sold_buckets), 4)

    # 🚨 Case 71 & Case 72: 남은 그리드 지층 라벨 정규화 (1층이 팔렸으면 남은 층들은 GRID_L2 ~ GRID_L7 로 1층 공석 유지!)
    if rem_buckets:
        if was_active_l1 and not sold_l1_flag:
            active_b1 = rem_buckets[0]
            re_uppers = relabel_upper_grid_tiers(
                rem_buckets[1:], max_tiers=MAX_GRID_TIERS_7
            )
            rem_buckets = [active_b1] + re_uppers
        else:
            rem_buckets = relabel_upper_grid_tiers(
                rem_buckets, max_tiers=MAX_GRID_TIERS_7
            )

    # MODIFIED [Case 78 & Case 80]:
    # 1) 1층이 전량 익절되었거나 그리드가 0주가 된 경우 l1_target_quota_qty = 0 클리어.
    # 2) 1층이 부분 익절(rem_buckets[0].qty < orig_l1_qty)된 경우, 방금 익절한 수량을 미체결 잔량(TOPUP_1FL)으로
    #    오인해 재매수하지 않도록 next_l1_target_q = rem_buckets[0].qty 로 즉시 동기화!
    # 3) 오직 1층 수량이 전혀 변동하지 않은 경우(예: 골든포켓 단독 익절 또는 상단 개별층 단독 익절)에만 기존 l1_target_quota_qty 보존.
    rem_has_active_l1 = has_active_l1_bucket(rem_buckets)
    if not rem_buckets or not rem_has_active_l1 or sold_l1_flag:
        next_l1_target_q = 0
    elif orig_l1_qty > 0 and rem_buckets[0].qty < orig_l1_qty:
        next_l1_target_q = rem_buckets[0].qty
    else:
        prev_target_q = max(0, safe_int(st.get("l1_target_quota_qty"), 0))
        next_l1_target_q = max(rem_buckets[0].qty, prev_target_q)

    sold_q = sold_grid_q + sold_pocket_q
    sold_actual_cost = round(sold_grid_cost + sold_pocket_cost, 4)
    pnl_info = calc_sell_realized_pnl(
        sold_qty=sold_q,
        sell_exec_price=fill_p,
        sold_actual_cost_usd=sold_actual_cost,
    )
    gross_pnl = pnl_info["gross_pnl_usd"]
    fee_usd = pnl_info["fee_usd"]
    net_pnl = pnl_info["net_pnl_usd"]
    net_rate = pnl_info["net_rate_pct"]

    pocket_net_pnl = 0.0
    if sold_pocket_q > 0:
        p_pnl_info = calc_sell_realized_pnl(
            sold_qty=sold_pocket_q,
            sell_exec_price=fill_p,
            sold_actual_cost_usd=sold_pocket_cost,
        )
        pocket_net_pnl = p_pnl_info["net_pnl_usd"]

    is_grid_empty = bool(len(rem_buckets) == 0)
    is_graduated_zero = bool(is_grid_empty and not rem_gp.is_active)
    is_pocket_only_sell = bool(sold_pocket_q > 0 and sold_grid_q == 0)

    # 🚨 Case 60 & Case 80: 골든포켓만 단독 익절되고 그리드가 남아 있으면 anchor_price 및 cycle_min_buy_price 를 원형 그대로 보존!
    old_anchor_p = safe_float(st.get("anchor_price"), fill_p)
    old_cycle_min_p = safe_float(st.get("cycle_min_buy_price"), 0.0)
    if is_pocket_only_sell and not is_grid_empty:
        next_anchor_p = old_anchor_p if old_anchor_p > 0.0 else fill_p
        next_cycle_min_p = round(old_cycle_min_p, 4)
    else:
        next_anchor_p = fill_p
        next_cycle_min_p = (
            round(old_cycle_min_p, 4) if not is_grid_empty else 0.0
        )

    tot_sell_ev = safe_int(st.get("total_sell_events"), 0) + 1
    tot_sold_sh = safe_int(st.get("total_sold_shares"), 0) + sold_q
    win_ev = safe_int(st.get("win_sell_events"), 0) + (
        1 if net_pnl > 0.0 else 0
    )
    day_sell_ev = safe_int(st.get("daily_sell_events"), 0) + 1

    # MODIFIED: 상단 지층이 실제로 전량 소진(rem_upper_cnt == 0)되었을 때만 wma_grad_sell_cnt 를 증가시키고,
    # 상단 부분 체결로 잔여 상단층이 남은 경우에는 indiv_grid_sell_cnt 로 정확히 집계한다.
    rem_upper_cnt = (
        max(0, len(rem_buckets) - (1 if rem_has_active_l1 else 0))
        if rem_buckets
        else 0
    )
    is_wma_mode = bool(
        mode == "SELL_WMA_UPPER"
        or (mode == "SELL_ALL_GRAD" and len(buckets) > 1)
    )
    wma_inc = (
        1 if (is_wma_mode and sold_grid_q > 0 and rem_upper_cnt == 0) else 0
    )
    indiv_inc = (
        1
        if (
            mode in ("SELL_GRID_INDIV", "SELL_L1_AND_GRID")
            or (is_wma_mode and sold_grid_q > 0 and rem_upper_cnt > 0)
        )
        else 0
    )
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

    # [Case 77 : 0주 전량 졸업 시 온디맨드 예비시드 원금 자동 상환 및 6/6회분 한도 원상 복구]:
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
        "golden_pocket": rem_gp.to_dict(),
        "anchor_price": next_anchor_p,
        "cycle_min_buy_price": next_cycle_min_p,
        "ratchet_anchor_price": next_anchor_p,
        "cycle_reanchor_credit_usd": 0.0,
        "l1_target_quota_qty": next_l1_target_q,
        "used_reserve_portions_cnt": next_used_res_cnt,
        "injected_reserve_usd": next_inj_res_usd,
        "cumulative_reserve_repaid_usd": cum_repaid_usd,
        # Case 77: 익절 매도로 현금이 회수되었으므로 시드고갈 입금 대기 및 단 1회 알림 래치 즉시 해제
        "waiting_reserve_deposit": False,
        "waiting_reserve_deposit_alert_sent": False,
        "required_reserve_deposit_usd": 0.0,
        "last_reserve_check_ts": 0.0,
        "last_sell_fill_ts": now_sell_epoch,
        "last_sell_gate_eval_ts": 0.0,
        "last_reentry_eval_ts": 0.0,
        "sell_order_id": "",
        "ordered_qty": 0,
        "target_sell_price": 0.0,
        "pending_sell_mode": "",
        "pending_sell_indices": [],
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
    }
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

    if hasattr(context, "send_slim_alert"):
        sign = "+" if net_pnl >= 0.0 else "-"
        r_sign = "+" if net_rate >= 0.0 else ""
        sess_tag = " · 🌃장외익절" if is_ext_sell else ""
        if is_pocket_only_sell:
            grid_sh = sum(b.qty for b in rem_buckets)
            title_msg = (
                f"🌟 [SOXL 독립 골든포켓 +1.5% 익절 체결{sess_tag}] "
                f"{sold_q}주 @ ${fill_p:.2f} ({r_sign}{net_rate:.2f}%)"
            )
            body_msg = (
                f"세후순익 {sign}${abs(net_pnl):,.2f} 시드 복리산입 및 원리금 금고 환원 완료! · "
                f"기존 7층그리드({len(rem_buckets)}개층·{grid_sh}주 · 기억저가 ${next_cycle_min_p:.2f}) 무결성 유지 · "
                f"가용현금 ${free_cash_now:,.2f}"
            )
        else:
            if is_graduated_zero:
                repay_note = ""
                if repaid_this_time > 0.0:
                    avail_p = max(0, MAX_RESERVE_PORTIONS - next_used_res_cnt)
                    repay_note = (
                        f" · 💉예비시드 원금 ${repaid_this_time:,.2f} 자동상환 완료"
                        f"(예비한도 {avail_p}/{MAX_RESERVE_PORTIONS}회분 복구!)"
                    )
                next_entry_guide = (
                    "🔒장외 매수잠금 · 04:07 EST 프리장 개시 후 첫 1층 진입 대기!"
                    if is_ext_sell
                    else "🛡️60초 타임쉴드 경과 후 현재가 조회 및 첫 1층 진입!"
                )
                note_str = (
                    f"🎓 전 지층 흑자 졸업 완료(0주 싸이클 종료{repay_note} "
                    f"➔ {next_entry_guide})"
                )
            elif is_grid_empty and rem_gp.is_active:
                note_str = (
                    f"🌟 그리드 전량 졸업 완료 · 잔여 골든포켓 {rem_gp.qty}주(@${rem_gp.book_price:.2f}) 익절 감시 지속"
                )
            else:
                wma_info = compute_upper_2_to_7_moving_avg(rem_buckets)
                u_cnt = safe_int(
                    wma_info.get("upper_tier_count"), len(rem_buckets)
                )
                u_qty = safe_int(
                    wma_info.get("upper_qty"), sum(b.qty for b in rem_buckets)
                )
                u_wma_p = safe_float(wma_info.get("upper_wma_price"), 0.0)
                u_wma_t = safe_float(
                    wma_info.get("upper_wma_target_price"), 0.0
                )
                if not rem_has_active_l1:
                    l2_cap_p = safe_float(
                        wma_info.get("min_indiv_upper_price"),
                        rem_buckets[0].book_price,
                    )
                    reload_guide = (
                        f"🔒장외 매수·개별층잠금(04:07 EST 이후 2층상한 ${l2_cap_p:.2f} 이하 1층재장전 · 기억저가 ${next_cycle_min_p:.2f} 잠금)"
                        if is_ext_sell
                        else f"🛡️60초 타임쉴드 후 1분 주기 1층재장전(2층상한 ${l2_cap_p:.2f} 이하 · 기억저가 ${next_cycle_min_p:.2f} 잠금)"
                    )
                    note_str = (
                        f"📦 잔여 2~{u_cnt + 1}층({u_cnt}개층·{u_qty}주) 순수이평 ${u_wma_p:.2f}(목표 ${u_wma_t:.2f}) 1.5초 실시간 익절감시 "
                        f"· {reload_guide}"
                    )
                else:
                    note_str = (
                        f"📦 잔여 1층+상단({len(rem_buckets)}개층) 순수이평 ${u_wma_p:.2f}(목표 ${u_wma_t:.2f}) 1.5초 실시간 익절감시 "
                        f"· 10분게이트 대기(기억저가 ${next_cycle_min_p:.2f} 잠금)"
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
        "sold_pocket_qty": sold_pocket_q,
        "fill_price": fill_p,
        "net_pnl_usd": net_pnl,
        "repaid_reserve_usd": repaid_this_time,
        "reanchor_drop_usd": 0.0,
        "remaining_tiers": len(rem_buckets),
        "remaining_pocket_qty": rem_gp.qty,
        "free_cash_usd": free_cash_now,
    }


async def sync_pending_sell_order_plugin(
    context: Any,
    holdings: Dict[str, Dict[str, Any]],
    prices: Dict[str, float],
    now_est: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    🚨 Case 19, Case 24, Case 65, Case 70, Case 71, Case 72, Case 79, Case 80 & Case 82:
    장부에 대기 중인 미체결 매도 주문(sell_order_id)이 존재할 때:
    1) GET /api/v1/orders/{orderId} 로 FILLED 여부를 조회하여 체결 완료 시
       즉시 _commit_filled_sell_and_reanchor_ledger() 로 복리 정산 및 60초 타임쉴드/15초 그레이스 쉴드 각인을 수행한다.
    2) 데이마켓/애프터마켓에서 브로커가 주문을 REJECTED(거래 제한 등) 처리하고 체결 수량이 0주인 경우,
       알림 메시지 폭탄 없이 조용히 60초 인메모리 묵음 쿨다운을 각인하고 주문 ID를 정리한다(Case 79).
    3) 발주된 지정가 매도 주문이 60.0초(SELL_ORDER_MAX_WAIT_SEC) 동안 체결되지 않으면,
       가격을 하향 추격 정정하지 않고 미체결 주문을 안전하게 취소(cancel_order)한 뒤
       기체결 수량이 있으면 정산 반영하고 0주이면 1.5초 실시간 타점 감시 상태로 즉시 복귀한다.
       (프로세스 재기동으로 인해 last_modify_mono 단조시계가 역전되었거나 0.0 인 경우 즉시 현재 단조시계로 자가 치유!)
    """
    st = context.ledger.get_state(TARGET_SYMBOL)
    sell_oid = str(st.get("sell_order_id") or "").strip()
    if not sell_oid:
        return {"status": "NO_PENDING_SELL", "did_sell_or_ratchet": False}

    ordered_qty = max(1, safe_int(st.get("ordered_qty"), 1))
    target_p = safe_float(st.get("target_sell_price"), 0.0)
    sell_mode = str(st.get("pending_sell_mode") or "SELL_L1_ONLY")

    # MODIFIED [Case 65 : 프로세스 재기동 후 단조 시계(last_modify_mono) 역전 또는 결측 시 즉시 자가 치유]
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

        # Case 19: 오직 FILLED 체결 데이터의 averageFilledPrice 와 filledQuantity 만 반영!
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
            )

        # MODIFIED [Case 65 & Case 78]: 부분 체결(PARTIAL_FILLED) 진행 중인 경우 60초까지 잔량 체결 대기 후 안전 취소 및 기체결분 정산
        if ord_status == "PARTIAL_FILLED" or filled_q > 0:
            if elapsed_mod >= SELL_ORDER_MAX_WAIT_SEC:
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
                    if f_q2 > 0:
                        filled_q = f_q2
                    if f_p2 > 0.0:
                        avg_fill_p = f_p2
                eff_p = avg_fill_p if avg_fill_p > 0.0 else target_p
                return await _commit_filled_sell_and_reanchor_ledger(
                    context=context,
                    filled_qty=filled_q,
                    avg_fill_price=eff_p,
                    sell_mode=sell_mode,
                    settled_order_id=sell_oid,
                )
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
                pending_sell_pocket_qty=0,
                last_sell_gate_eval_ts=0.0,
            )
            return {
                "status": f"SELL_ORDER_{ord_status}_CLEARED",
                "did_sell_or_ratchet": False,
            }

    if elapsed_mod >= SELL_ORDER_MAX_WAIT_SEC:
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
            if f_status == "FILLED" or f_qty > 0:
                return await _commit_filled_sell_and_reanchor_ledger(
                    context=context,
                    filled_qty=(f_qty if f_qty > 0 else ordered_qty),
                    avg_fill_price=(f_avg if f_avg > 0.0 else target_p),
                    sell_mode=sell_mode,
                    settled_order_id=sell_oid,
                )

        await context.ledger.update_state(
            TARGET_SYMBOL,
            sell_order_id="",
            ordered_qty=0,
            target_sell_price=0.0,
            pending_sell_mode="",
            pending_sell_indices=[],
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
# [핵심 3] 24시간 전 세션(프리·정규·애프터·데이마켓) 매수 후 최초 60초 타임쉴드 & 이후 보유 중 매 1.5초 실시간 4중 다중 익절 + 방안 C 오버나이트 통합이평 사수 + 윗꼬리 즉시 체결 모니터 (Case 69 ~ 83)
# ---------------------------------------------------------------------------
async def execute_1m_sniper_sell_and_reanchor_plugin(
    context: Any,
    holdings: Dict[str, Dict[str, Any]],
    prices: Dict[str, float],
    now_est: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    # MODIFIED [🎯 2 Step 2 & Case 24, 44, 46 ~ 83 (방안 C 오버나이트 통합이평 사수 하이브리드 & 윗꼬리 다중 층 역설 차단)]:
    프리마켓(04:07 ~ 09:29 EST) · 정규장(09:30 ~ 16:00 EST) · 애프터마켓(16:00 ~ 19:59 EST) · 데이마켓(20:00 ~ 03:59 EST)
    전 구간(is_active_sell_window)에서 작동하는 '매수 후 최초 60.0초 타임쉴드 + 이후 보유 중 매 1.5초 실시간 타점 + 윗꼬리 체결틱 병행 감지'
    스나이퍼 매도 모니터:
    1) 대기 중인 미체결 매도 주문(sell_order_id)이 있으면 먼저 체결 확인을 수행한다.
    2) 🛡️ [Case 79 & Case 82 장외 거래 제한/정산 시차 묵음 쿨다운 검문]
    3) 🛡️ [Case 65 매수 후 최초 60.0초 강제 타임쉴드 검문]
    4) ⚡ [Case 70 ~ 72, Case 79, Case 80, Case 82 & Case 83 방안 C : 매수 후 60.0초 경과 시점부터 매 1.5초 실시간 익절 + 윗꼬리 스캔]:
       - 프리장 + 정규장(04:07 ~ 16:00 EST, is_ext_sell_only == False)에서는 ① 독립 골든포켓(+1.50%), ② 활성 1층(+1.50%),
         ③ 2~6층 개별 및 통합 7층(+1.00%), ④ 2~7층 통합 이동평균(+1.00%) 4중 다중 익절을 전면 개방한다.
       - 🚨 [Case 83 방안 C] 오버나이트 애프터장 + 데이장(16:01 ~ 03:59 EST, is_ext_sell_only == True)에서는
         상단 2~7층 보유 시 개별 층(1층 단독 및 2~6층 개별) 쪼개 팔기를 잠가 통합 이동평균(wma_2_to_7) 도망을 원천 봉쇄하고,
         오버나이트 중에는 오직 '2~7층 통합 이동평균(+1.00%) 일괄 졸업'(또는 1층 단독 보유 +1.50% / 독립 골든포켓 +1.50%)만 허용한 뒤,
         04:07:00 EST 프리장 개장과 동시에 4중 다중 익절을 전면 개방하여 프리장 시초가 갭상승 수익을 수확한다!
       - ⑤ [Case 82 핵심 수술 3] 단일 스냅샷 현재가(live_p)가 미달이더라도 유효 최단 거리 익절 목표가(nearest_target_p) 대비
            -2.50% 이내(live_p >= nearest_target_p * 0.975)에 근접해 있으면 GET /api/v1/trades(최근 15건, 5.0초 룩백 &
            직전 매수/매도 체결 이후)에서 최고 체결가(wick_high_p)를 병행 스캔하여 0.3초짜리 윗꼬리 터치까지 100% 포착한다!
       - ⑥ [Case 82 핵심 수술 1 & 2 & 다중 층 스침 역설 차단]
            - 2차 재조회 현재가(fresh_live_p) 단독으로 달성된 지층이 있으면 이를 최우선 채택하여 즉시 Taker 체결을 보장하고,
              순수하게 윗꼬리(wick_high_p)로만 터치된 경우에는 최단 거리 목표가(nearest_target_p) 지층만 분리 발주하여
              상위 층의 높은 목표가가 하위 층 지정가를 끌어올려 미체결되는 역설을 원천 차단한다!
            - _LAST_CONSUMED_WICK_TRADE_TS 각인은 실제 매도 주문 발주가 성공(did_order == True)했을 때만 수행한다!
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

    # [Case 79]: 매도 모니터를 애프터마켓 및 데이마켓까지 전 구간 개방 (04:00~04:06 오프닝 안정화 및 주말 휴장만 제외)
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
    gp = pocket_from_dict(st.get("golden_pocket"))
    if not buckets and not gp.is_active:
        return {"status": "NO_BUCKETS_HELD", "did_sell_or_ratchet": False}

    # [Case 79 & Case 82]: 장외(데이마켓·애프터마켓) 종목 거래 제한(60s) 또는 매도가능수량 일시 정산대기(5s) 묵음 쿨다운 확인
    in_ext_cd, rem_ext_cd = is_within_extended_sell_restriction_cooldown(
        context, TARGET_SYMBOL
    )
    if in_ext_cd:
        return {
            "status": "SILENT_HOLD_EXTENDED_RESTRICT_COOLDOWN",
            "did_sell_or_ratchet": False,
            "remain_cooldown_sec": rem_ext_cd,
        }

    # 🛡️ 2) [Case 65 & Case 70] 매수 체결 직후 최초 60.0초 호가 안정화 타임쉴드 강제 검문!
    in_buy_shield, remain_buy_sec = is_within_post_buy_time_shield(
        context, st, TARGET_SYMBOL
    )
    if in_buy_shield:
        return {
            "status": "HOLD_POST_BUY_60S_TIME_SHIELD",
            "did_sell_or_ratchet": False,
            "remain_shield_sec": remain_buy_sec,
        }

    # ⚡ 3) [Case 70, Case 71, Case 72, Case 79 & Case 83] 실시간 현재가 확인 (데이마켓 시세 미제공 시 100% 묵음 스킵!)
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
    ledger_total_qty = sum(b.qty for b in buckets) + (
        gp.qty if gp.is_active else 0
    )
    h_qty = safe_int(h_info.get("qty"), ledger_total_qty)
    default_avg_p = (
        buckets[0].actual_avg_price
        if buckets
        else (gp.actual_avg_price if gp.is_active else live_p)
    )
    avg_p = safe_float(h_info.get("avg_price"), default_avg_p)
    update_exit_snapshot_on_hold(
        context, TARGET_SYMBOL, h_qty, avg_p, live_p
    )

    held_lots = max(1, sum(b.lot_count for b in buckets))
    threshold_mode = str(st.get("threshold_mode") or "WIDE_RUNWAY").upper()
    _, rise_sell_l1_pct, rise_sell_upper_pct = get_golden8_prog_thresholds(
        held_lots=held_lots, threshold_mode=threshold_mode
    )

    # 🎯 4) [Case 70 ~ 72, Case 79, Case 80, Case 82 & Case 83 방안 C] 1차 스냅샷 현재가(live_p) 기반 다중 익절 실시간 판정!
    sell_eval = evaluate_multi_grid_sell_targets(
        buckets=buckets,
        live_price=live_p,
        rise_l1_pct=rise_sell_l1_pct,
        rise_upper_pct=rise_sell_upper_pct,
        golden_pocket=gp,
        rise_pocket_pct=GOLDEN_POCKET_RISE_PCT,
        is_overnight_session=is_ext_sell_only,
    )

    # 🎯 4-B) [Case 82 핵심 수술 3 & Case 83 방안 C : GET /api/v1/trades 최근 5.0초 체결 최고가(wick_high_p) 병행 스캔]:
    # 1.5 ~ 2.7초 폴링 사이에 0.3초 동안만 윗꼬리를 찍고 내려온 경우에도,
    # live_p 가 현재 세션에서 유효한 최단 거리 목표가(nearest_target_p) 대비 -2.50% 이내이면
    # 최근 체결 내역(/api/v1/trades)을 역추적하여 윗꼬리 최고가로 매도 판정기를 즉시 격발한다!
    wick_high_p: float = 0.0
    wick_trade_ts: float = 0.0
    nearest_target_p: float = 0.0
    triggered_by_wick_only: bool = False

    if not bool(sell_eval.get("should_sell")):
        nearest_target_p = _compute_nearest_sell_target_price(
            buckets=buckets,
            golden_pocket=gp,
            rise_l1_pct=rise_sell_l1_pct,
            rise_upper_pct=rise_sell_upper_pct,
            rise_pocket_pct=GOLDEN_POCKET_RISE_PCT,
            is_overnight_session=is_ext_sell_only,
        )
        if nearest_target_p > 0.0 and live_p >= (
            nearest_target_p * WICK_PROXIMITY_TRIGGER_RATIO
        ):
            min_trade_after_ts = max(
                safe_float(st.get("last_buy_fill_ts"), 0.0),
                safe_float(st.get("last_sell_fill_ts"), 0.0),
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
                # MODIFIED [Case 82 다중 층 윗꼬리 스침 역설 차단]:
                # wick_high_p 가 상위 고가 지층까지 스치고 내려온 경우 상위 층 목표가가 결합되어 하위 층까지 미체결되는 것을 막기 위해,
                # 순수 윗꼬리 감지 시에는 최단 거리 목표가(nearest_target_p) 기준으로 먼저 매도 대상을 산출한다.
                wick_eval = evaluate_multi_grid_sell_targets(
                    buckets=buckets,
                    live_price=nearest_target_p,
                    rise_l1_pct=rise_sell_l1_pct,
                    rise_upper_pct=rise_sell_upper_pct,
                    golden_pocket=gp,
                    rise_pocket_pct=GOLDEN_POCKET_RISE_PCT,
                    is_overnight_session=is_ext_sell_only,
                )
                if not bool(wick_eval.get("should_sell")):
                    wick_eval = evaluate_multi_grid_sell_targets(
                        buckets=buckets,
                        live_price=max(live_p, wick_high_p),
                        rise_l1_pct=rise_sell_l1_pct,
                        rise_upper_pct=rise_sell_upper_pct,
                        golden_pocket=gp,
                        rise_pocket_pct=GOLDEN_POCKET_RISE_PCT,
                        is_overnight_session=is_ext_sell_only,
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
        # [Case 82 핵심 수술 2]: 장외(is_ext_sell_only)에서도 fallback_price=live_p 로 통일하여
        # 2차 재조회 일시 타임아웃 시 매도를 포기하던 SILENT_EXTENDED_NO_FRESH_LIVE_PRICE 버그 영구 소각!
        fresh_live_p = await _fetch_fresh_current_soxl_price(
            context,
            fallback_price=live_p,
        )
        if fresh_live_p <= 0.0:
            fresh_live_p = live_p

        # MODIFIED [Case 82]: 최신 현재가(fresh_live_p) 단독(또는 max(live_p, fresh_live_p))으로 달성된 지층이 있으면
        # 해당 물량들은 현재 호가에서 100% 즉시 Taker 체결 가능하므로 이를 최우선 반영한다!
        live_peak_p = max(live_p, fresh_live_p)
        fresh_only_eval = evaluate_multi_grid_sell_targets(
            buckets=buckets,
            live_price=live_peak_p,
            rise_l1_pct=rise_sell_l1_pct,
            rise_upper_pct=rise_sell_upper_pct,
            golden_pocket=gp,
            rise_pocket_pct=GOLDEN_POCKET_RISE_PCT,
            is_overnight_session=is_ext_sell_only,
        )
        if bool(fresh_only_eval.get("should_sell")):
            sell_eval = fresh_only_eval
            triggered_by_wick_only = False

        sold_indices = list(sell_eval.get("sold_indices") or [])
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

        # [Case 82 핵심 수술 1 : 고점 박제 max(live_p, fresh_live_p) 영구 제거 & 목표 하한가(min_floor_p) 직결 발주]:
        # - 일반 타점 돌파 및 1분봉 윗꼬리($104.00 터치 직후 호가가 $103.91~$103.99 에 걸려 있거나 순간 밀린 상태)에서는
        #   윗꼬리 꼭대기($104.00)로 지정가를 박제하지 않고 정확히 목표 익절 하한가(min_floor_p, 예: $103.91)로 지정가 발주한다.
        # - 오직 최신 현재가(fresh_live_p)가 목표 하한가 대비 +0.50% 초과 대폭 갭상승(fresh_live_p > min_floor_p * 1.005)한 경우에만
        #   갭상승 수익 보호를 위해 fresh_live_p * 0.997 마켓터블 지정가를 적용한다.
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
        )
        did_order = str(sweep_res.get("status") or "") in (
            "NEW_SELL_SWEEP_OK",
            "SELL_ORDER_ALREADY_ACTIVE",
        )
        # MODIFIED [Case 82]: 실제 매도 주문 발주가 성공(did_order == True)했을 때만 윗꼬리 체결 시각을 소모 각인하여,
        # 장외 sellableQuantity 일시 0주 대기(5초) 후 재시도 시 윗꼬리 신호가 증발하지 않도록 보호!
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
            "sell_pocket_qty": sell_pocket_qty,
            "qty": sell_qty,
            "sweep_price": order_limit_p,
            "min_floor_price": min_floor_p,
            "wick_high_price": wick_high_p,
            "result": sweep_res,
        }

    # ⚡ 5) [Case 70, Case 75 & Case 83 방안 C] 목표 미달(또는 장외 개별층 잠금) 시 60초 블라인드 락이나 디스크 쓰기 없이 즉시 반환 -> 1.5초 후 재감시!
    ref_b0_p = (
        buckets[0].book_price
        if buckets
        else (gp.book_price if gp.is_active else live_p)
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
manage_mechanical_profit_trap_plugin = execute_1m_sniper_sell_and_reanchor_plugin
reconcile_zero_holdings_exit_plugin = sync_pending_sell_order_plugin
