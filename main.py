# -*- coding: utf-8 -*-
"""
# MODIFIED: main.py (15대 코어 모듈 완전체 오케스트레이터 —
# ⚖️ 바벨 모드[BARBELL_60_30_10 : SOXL 60% / SGOV 30% 정규장 매매 / 현금 10% 선행수혈 / 실현수익 별도금고 격리] 결속 ·
# 🗡️ [모의 ⇄ 0주전환예약 ⇄ 실전] 암살자 분리 승격 및 실전 암살자 단독 모드 시 스나이퍼/바벨 간섭 100% 차단[SGOV 수동매도 위임] ·
# 부팅 시 3대 TDD[QuantEngine · Barbell · Assassin] 전수 검증 · Case 01 ~ Case 93 락온)
인피니트 스노우볼 (Infinite Snowball) v3.0 — 메인 오케스트레이터 코어 모듈
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import math
import signal
import sys
import time
from datetime import datetime
from typing import Any, Dict, Optional

from assassin_plugin import (
    MACRO_REF_SYMBOL,
    ensure_assassin_ledger,
    execute_simulated_assassin_tick_plugin,
    is_live_assassin_standalone_active,
    run_assassin_plugin_tdd,
)
from barbell_plugin import (
    BARBELL_SAFE_SYMBOL,
    ensure_barbell_ledger,
    execute_barbell_sgov_tick_plugin,
    initialize_or_sync_barbell_on_mode_enter,
    is_barbell_mode,
    run_barbell_plugin_tdd,
)
from defense_plugin import (
    execute_0400_premarket_stabilization_plugin,
    execute_1600_daily_closing_settlement_plugin,
    execute_daily_1700_gc_and_backup_plugin,
    reconcile_stratum_with_broker_holdings_plugin,
)
from main_runtime import (
    _AdaptiveTelegramBridge,
    _call_plugin_adaptive,
    _check_weekend_nyse_closed_dynamic,
    _compute_candle_metrics_dynamic,
    _compute_qqq_metrics_dynamic,
    _empty_holding_entry,
    _empty_soxl_holding_entry,
    _install_toss_api_compatibility_patches,
    _instantiate_stratum_ledger,
    _run_auto_update_loop_dynamic,
)
from plugin_updater import (
    arm_hard_restart_watchdog,
    perform_self_restart_execv,
    purge_deprecated_legacy_files,
    verify_all_modules_compile,
)
from quant_engine import (
    SUB_MAX_TOTAL_LOTS_4,
    buckets_from_dicts,
    has_active_l1_bucket,
    run_quant_engine_tdd,
    set_runtime_round_trip_fee_rate_pct,
)
from quant_indicators_plugin import (
    evaluate_buy_gate_bucket_status,
    is_active_buy_window,
    is_active_sell_window,
    is_extended_sell_only_window,
    refresh_metrics_with_live_tick,
)
from sniper_exit_plugin import (
    execute_1m_sniper_sell_and_reanchor_plugin,
    is_sniper_l1_trail_active,
    is_within_post_buy_time_shield,
    is_within_post_sell_time_shield,
    sync_pending_sell_order_plugin,
)
from sniper_plugin import (
    execute_seed_protected_buy_gate_plugin,
    is_within_reserve_deposit_check_shield,
    sync_pending_buy_order_plugin,
)
from toss_api import (
    DEFAULT_US_COMMISSION_RATE,
    EST_TZ,
    KRW_PER_USD_DEFAULT,
    LOCKED_BUY_INTERVAL_MIN,
    ROUND_TRIP_FEE_RATE_PCT,
    TARGET_SYMBOL,
    TossApiClient,
    get_bot_base_dir,
    resolve_folder_isolated_ledger_paths,
    safe_float,
    safe_int,
)

# ---------------------------------------------------------------------------
# 로깅 포맷 설정 (EST/KST 병기 지원 및 Case 75 저소음 고신뢰 로그)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger("toss_sniper.main")

# 메인 루프 주기 상수 (평시 1.5초 / 미체결 주문 및 암살자 트레일링 부스터 0.4초 / 장외 0주 대기 5.0초)
NORMAL_LOOP_INTERVAL_SEC: float = 1.50
FAST_SHIELD_LOOP_INTERVAL_SEC: float = 0.40
EXTENDED_ZERO_HOLD_INTERVAL_SEC: float = 5.00


# NEW: 다중 프로세스 동시 기상을 위한 Wall-Clock 정각 격자 슬립
def _wall_wait(iv: float, off: float = 0.0) -> float:
    w = time.time()
    nxt = math.ceil(((w - off) + 0.04) / iv) * iv + off
    return max(0.05, min(iv + 0.25, nxt - w))


# ---------------------------------------------------------------------------
# [핵심 1] 스나이퍼 · 바벨(60/30/10) · 암살자 전역 컨텍스트 (SniperAppContext)
# ---------------------------------------------------------------------------
class SniperAppContext:
    """
    15대 코어 모듈이 공유하는 단일 런타임 상태 컨텍스트:
    - 스나이퍼 3중 원장 (soxl_stratum_ledger_{folder_slug}.json)
    - 바벨 전용 3중 원장 (barbell_ledger_{folder_slug}.json · 별도 실현수익금고 포함)
    - 암살자 전용 3중 원장 (assassin_sim_ledger_{folder_slug}.json · 모의/0주예약/실전 상태 포함)
    """

    def __init__(self, base_dir: Optional[str] = None) -> None:
        _install_toss_api_compatibility_patches()
        self.base_dir: str = get_bot_base_dir(base_dir)
        (
            self.primary_ledger_path,
            self.ledger_path,
            self.backup_ledger_path,
            self.folder_slug,
        ) = resolve_folder_isolated_ledger_paths(base_dir=self.base_dir)

        self.api: TossApiClient = TossApiClient(base_dir=self.base_dir)
        self.ledger: Any = _instantiate_stratum_ledger(
            filepath=self.ledger_path, base_dir=self.base_dir
        )
        self.barbell_ledger: Any = ensure_barbell_ledger(self)
        self.assassin_ledger: Any = ensure_assassin_ledger(self)

        try:
            st_init = self.ledger.get_state(TARGET_SYMBOL)
            init_rt_pct = safe_float(
                st_init.get("round_trip_fee_rate_pct"), ROUND_TRIP_FEE_RATE_PCT
            )
            init_us_comm = safe_float(
                st_init.get("us_commission_rate"), DEFAULT_US_COMMISSION_RATE
            )
            set_runtime_round_trip_fee_rate_pct(
                init_rt_pct, us_commission_rate=init_us_comm
            )
        except Exception:
            pass

        self.in_memory_ordering_lock: asyncio.Lock = asyncio.Lock()
        self.dual_strike_mutex: asyncio.Lock = asyncio.Lock()
        self.wakeup_event: asyncio.Event = asyncio.Event()
        self.shutdown_event: asyncio.Event = asyncio.Event()

        self.restart_requested: bool = False
        self.restart_reason: str = ""

        self.latest_prices: Dict[str, float] = {
            TARGET_SYMBOL: 0.0,
            MACRO_REF_SYMBOL: 0.0,
            BARBELL_SAFE_SYMBOL: 0.0,
        }
        self.last_soxl_live_price: float = 0.0
        self.last_soxl_live_price_mono: float = 0.0
        self.last_qqq_live_price: float = 0.0
        self.last_fx_rate: float = KRW_PER_USD_DEFAULT
        self.assassin_high_freq_active: bool = False

        self.latest_holdings: Dict[str, Dict[str, Any]] = {
            TARGET_SYMBOL: _empty_soxl_holding_entry(),
            BARBELL_SAFE_SYMBOL: _empty_holding_entry(BARBELL_SAFE_SYMBOL),
        }
        self.holdings_fetch_ok: bool = False
        self.candle_metrics_cache: Dict[str, Dict[str, Any]] = {}
        self.exit_snapshot_cache: Dict[str, Dict[str, Any]] = {}
        self.indexing_grace_cache: Dict[str, Dict[str, Any]] = {}

        self._strike_hold_alert_ts: Dict[str, float] = {}
        self.last_0400_sync_date: str = ""
        self.fast_shield_mode: bool = False

        self.tg: _AdaptiveTelegramBridge = _AdaptiveTelegramBridge(
            context=self
        )

    async def send_slim_alert(self, title: str, body: str = "") -> bool:
        return await self.tg.send_slim_alert(title=title, body=body)

    async def send_strike_hold_alert_once(
        self,
        symbol: str,
        reason_key: str,
        message: str,
        cooldown_sec: float = 1800.0,
    ) -> None:
        r_lower = str(reason_key or "").lower()
        if any(
            k in r_lower
            for k in (
                "daymarket",
                "extended",
                "restrict",
                "no_price",
                "no_live_price",
                "hours_closed",
            )
        ):
            return
        key = f"{symbol}:{reason_key}"
        now_m = time.monotonic()
        last_m = self._strike_hold_alert_ts.get(key, 0.0)
        if (now_m - last_m) < cooldown_sec:
            return
        self._strike_hold_alert_ts[key] = now_m
        await self.send_slim_alert(
            title=f"⚠️ [{symbol} 7층 골디락스 스나이퍼 안내]",
            body=message,
        )


# ---------------------------------------------------------------------------
# [핵심 2] 백그라운드 태스크 1 : SOXL 1분봉/일봉 · Wilder's RSI(14) · 암살자 4대 지표 및 QQQ 안전망 레이더
# ---------------------------------------------------------------------------
async def candle_radar_loop(context: SniperAppContext) -> None:
    while not context.shutdown_event.is_set():
        now_est = datetime.now(EST_TZ)
        if _check_weekend_nyse_closed_dynamic(now_est):
            try:
                await asyncio.wait_for(
                    context.shutdown_event.wait(), timeout=30.0
                )
            except asyncio.TimeoutError:
                pass
            continue

        hm = now_est.hour * 100 + now_est.minute
        in_market = bool(400 <= hm <= 1605)
        sleep_sec = 5.0 if in_market else 45.0

        try:
            candles_1m = await context.api.get_candles_1m(
                symbol=TARGET_SYMBOL, total_count=(400 if in_market else 200)
            )
            candles_1d = await context.api.get_candles_1d(
                symbol=TARGET_SYMBOL, count=10
            )
            now_est = datetime.now(EST_TZ)  # NEW: HTTP 수신 직후 최신 시각 동기화
            live_p = safe_float(
                context.latest_prices.get(TARGET_SYMBOL),
                safe_float(
                    context.latest_holdings.get(TARGET_SYMBOL, {}).get(
                        "last_price"
                    ),
                    0.0,
                ),
            )
            metrics = await _compute_candle_metrics_dynamic(
                context=context,
                candles_1m=candles_1m,
                live_price=live_p,
                now_est=now_est,
                candles_1d=candles_1d,
            )
            newest_lp = safe_float(
                context.latest_prices.get(TARGET_SYMBOL), live_p
            )
            if newest_lp > 0.0:
                metrics = refresh_metrics_with_live_tick(
                    metrics,
                    newest_lp,
                    now_est=datetime.now(EST_TZ),
                    symbol=TARGET_SYMBOL,
                )
            context.candle_metrics_cache[TARGET_SYMBOL] = metrics
            if (
                newest_lp <= 0.0
                and safe_float(metrics.get("live_price"), 0.0) > 0.0
            ):
                fetched_lp = safe_float(metrics.get("live_price"), 0.0)
                context.latest_prices[TARGET_SYMBOL] = fetched_lp
                context.last_soxl_live_price = fetched_lp
                context.last_soxl_live_price_mono = time.monotonic()

            if in_market:
                try:
                    candles_qqq_1m = await context.api.get_candles_1m(
                        symbol=MACRO_REF_SYMBOL, total_count=60
                    )
                    now_est = datetime.now(EST_TZ)  # NEW: QQQ 캔들 수신 직후 최신 시각 동기화
                    qqq_live_p = safe_float(
                        context.latest_prices.get(MACRO_REF_SYMBOL), 0.0
                    )
                    qqq_metrics = await _compute_qqq_metrics_dynamic(
                        context=context,
                        candles_1m_qqq=candles_qqq_1m,
                        live_price_qqq=qqq_live_p,
                        now_est=now_est,
                    )
                    newest_qqq_p = safe_float(
                        context.latest_prices.get(MACRO_REF_SYMBOL), qqq_live_p
                    )
                    if newest_qqq_p > 0.0:
                        qqq_metrics = refresh_metrics_with_live_tick(
                            qqq_metrics,
                            newest_qqq_p,
                            now_est=datetime.now(EST_TZ),
                            symbol=MACRO_REF_SYMBOL,
                        )
                    context.candle_metrics_cache[MACRO_REF_SYMBOL] = qqq_metrics
                except Exception as qqq_exc:
                    logger.debug("QQQ 캔들 레이더 폴백(묵음): %s", qqq_exc)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.debug("SOXL 캔들 레이더 루프 폴백(묵음): %s", exc)

        try:
            await asyncio.wait_for(
                context.shutdown_event.wait(), timeout=(_wall_wait(5.0, 0.15) if in_market else sleep_sec)
            )
        except asyncio.TimeoutError:
            pass


def _evaluate_fast_shield_mode(
    context: SniperAppContext, st: Dict[str, Any]
) -> bool:
    """
    미체결 주문(SOXL · 바벨 SGOV · 실전 암살자), 매수/매도 직후 60초 타임쉴드, 또는
    🗡️ 암살자 +1.00% 트레일링 점화(assassin_high_freq_active) 시 루프를 0.40초로 가속한다.
    """
    if bool(getattr(context, "assassin_high_freq_active", False)):
        return True
    if is_sniper_l1_trail_active(context, TARGET_SYMBOL):
        return True
    if str(st.get("buy_order_id") or "").strip() or str(
        st.get("sell_order_id") or ""
    ).strip():
        return True
    if hasattr(context, "barbell_ledger"):
        try:
            bst = context.barbell_ledger.get_state()
            if str(bst.get("sgov_buy_order_id") or "").strip() or str(
                bst.get("sgov_sell_order_id") or ""
            ).strip():
                return True
        except Exception:
            pass
    in_b, _ = is_within_post_buy_time_shield(context, st, TARGET_SYMBOL)
    if in_b:
        return True
    in_s, _ = is_within_post_sell_time_shield(context, st, TARGET_SYMBOL)
    if in_s:
        return True
    return False


# ---------------------------------------------------------------------------
# [핵심 3] 백그라운드 태스크 2 : 메인 스나이퍼 · 바벨(60/30/10) · [모의/실전] 암살자 통합 루프
# ---------------------------------------------------------------------------
async def main_sniper_loop(context: SniperAppContext) -> None:
    """
    🚨 제1헌법 ~ 제6헌법 & Case 01 ~ Case 93 + 바벨(60/30/10) + [모의/실전] 암살자 분리 오케스트레이션:
    1) 평일 04:00 ~ 04:06 EST 오프닝 안정화 (실전 암살자 단독 모드 시에는 수수료/일일 롤오버만 수행하여 포지션 혼입 방지)
    2) 실시간 SOXL + QQQ 시세 배치 조회 및 1분봉 지표 O(1) 합성
    3) 🗡️ [모의 ⇄ 실전] 암살자 틱 엔진 실행:
       - 만약 현재 [실전(LIVE)] 암살자 단독 모드가 활성화된 상태(is_live_assassin_standalone_active == True)라면,
         스나이퍼(복리/단리) 및 바벨(SOXL/SGOV) 루프를 즉시 건너뛰어 100% 물리적 분리 운용을 보장한다! (SGOV는 수동 매도 위임)
    4) 스나이퍼 미결 매수/매도 선행 정산 (0주 졸업 시 예약된 실전 암살자 자동 승격 확인 포함)
    5) 주기적 브로커 실잔고 화해 (SOXL 및 바벨 SGOV 수동 잔고 무결성 동기화)
    6) ⚖️ 바벨 모드(BARBELL_60_30_10) 가동 시 정규장(09:31 ~ 15:55 EST) 전용 SGOV 10% 매도 / 30% 리밸런싱 매수 실행
    7) 평일 16:00 EST 정규장 마감 일일 결산 보고
    8) 실시간 스나이퍼 다중 익절 매도 모니터 (오팔 최우선) 및 시드보호 매수 게이트 (떨사 · 바벨 4단계 자동수혈 포함)
    """
    last_reconcile_mono: float = 0.0

    while not context.shutdown_event.is_set():
        now_est = datetime.now(EST_TZ)
        if _check_weekend_nyse_closed_dynamic(now_est):
            context.fast_shield_mode = False
            context.assassin_high_freq_active = False
            try:
                await asyncio.wait_for(
                    context.wakeup_event.wait(), timeout=15.0
                )
                context.wakeup_event.clear()
            except asyncio.TimeoutError:
                pass
            continue

        hm = now_est.hour * 100 + now_est.minute
        today_str = now_est.strftime("%Y-%m-%d")

        try:
            # ---------------------------------------------------------------
            # STEP 1: 04:00 ~ 04:06 EST 프리장 오프닝 안정화 (일 1회)
            # ---------------------------------------------------------------
            if 400 <= hm <= 406 and context.last_0400_sync_date != today_str:
                if is_live_assassin_standalone_active(context):
                    try:
                        if hasattr(
                            context.ledger, "rollover_daily_counters_if_needed"
                        ):
                            await context.ledger.rollover_daily_counters_if_needed(
                                today_str
                            )
                        await context.barbell_ledger.rollover_daily_if_needed(
                            today_str
                        )
                        await context.assassin_ledger.rollover_daily_session_if_needed(
                            today_str
                        )
                        us_c, rt_p = await context.api.ensure_us_commission_rate(
                            force_refresh=True
                        )
                        if us_c > 0.0 and rt_p > 0.0:
                            await context.ledger.update_state(
                                TARGET_SYMBOL,
                                us_commission_rate=us_c,
                                round_trip_fee_rate_pct=rt_p,
                            )
                            await context.assassin_ledger.update_state(
                                us_commission_rate=us_c,
                                round_trip_fee_rate_pct=rt_p,
                            )
                    except Exception:
                        pass
                    context.last_0400_sync_date = today_str
                else:
                    await _call_plugin_adaptive(
                        execute_0400_premarket_stabilization_plugin,
                        context=context,
                        holdings=context.latest_holdings,
                        prices=context.latest_prices,
                        now_est=now_est,
                    )
                    context.last_0400_sync_date = today_str

            # ---------------------------------------------------------------
            # STEP 2: 실시간 SOXL (및 장중 QQQ) 현재가 조회 & 1분봉 지표 O(1) 합성
            # ---------------------------------------------------------------
            query_symbols = (
                (TARGET_SYMBOL, MACRO_REF_SYMBOL)
                if (400 <= hm <= 1605)
                else (TARGET_SYMBOL,)
            )
            prices_map: Dict[str, float] = {}
            try:
                prices_map = await context.api.get_current_prices_batch(
                    query_symbols
                )
            except Exception as p_exc:
                logger.debug("현재가 배치 조회 폴백(묵음): %s", p_exc)

            live_p = safe_float(prices_map.get(TARGET_SYMBOL), 0.0)
            if live_p > 0.0:
                context.latest_prices[TARGET_SYMBOL] = live_p
                context.last_soxl_live_price = live_p
                context.last_soxl_live_price_mono = time.monotonic()
            else:
                live_p = safe_float(
                    context.latest_prices.get(TARGET_SYMBOL), 0.0
                )

            qqq_p = safe_float(prices_map.get(MACRO_REF_SYMBOL), 0.0)
            if qqq_p > 0.0:
                context.latest_prices[MACRO_REF_SYMBOL] = qqq_p
                context.last_qqq_live_price = qqq_p
                base_qqq_m = context.candle_metrics_cache.get(
                    MACRO_REF_SYMBOL, {}
                )
                if isinstance(base_qqq_m, dict):
                    context.candle_metrics_cache[MACRO_REF_SYMBOL] = (
                        refresh_metrics_with_live_tick(
                            base_qqq_m,
                            qqq_p,
                            now_est=now_est,
                            symbol=MACRO_REF_SYMBOL,
                        )
                    )

            if live_p > 0.0:
                base_soxl_m = context.candle_metrics_cache.get(
                    TARGET_SYMBOL, {}
                )
                context.candle_metrics_cache[TARGET_SYMBOL] = (
                    refresh_metrics_with_live_tick(
                        base_soxl_m,
                        live_p,
                        now_est=now_est,
                        symbol=TARGET_SYMBOL,
                    )
                )

            # ---------------------------------------------------------------
            # STEP 3: 🗡️ [모의 ⇄ 실전] 암살자 틱 엔진 실행 및 실전 단독 모드 분리 게이트
            # ---------------------------------------------------------------
            try:
                await execute_simulated_assassin_tick_plugin(
                    context=context,
                    now_est=now_est,
                )
            except asyncio.CancelledError:
                raise
            except Exception as assn_exc:
                logger.warning(
                    "⚠️ [Assassin Plugin 예외 격리 · 메인 루프 무중단 유지]: %s",
                    assn_exc,
                )

            # [핵심 분리 아키텍처] 실전 암살자(LIVE) 단독 모드일 때는 스나이퍼/바벨 신규 매매 및 화해를 100% 정지!
            if is_live_assassin_standalone_active(context):
                loop_sleep_live = (
                    FAST_SHIELD_LOOP_INTERVAL_SEC
                    if bool(getattr(context, "assassin_high_freq_active", False))
                    else NORMAL_LOOP_INTERVAL_SEC
                )
                try:
                    await asyncio.wait_for(
                        context.wakeup_event.wait(), timeout=_wall_wait(loop_sleep_live)
                    )
                    context.wakeup_event.clear()
                except asyncio.TimeoutError:
                    pass
                continue

            # ---------------------------------------------------------------
            # STEP 4: 실전 스나이퍼 미결 매수/매도 주문 선행 정산 (Case 66)
            # ---------------------------------------------------------------
            st = context.ledger.get_state(TARGET_SYMBOL)
            pending_buy_oid = str(st.get("buy_order_id") or "").strip()
            pending_sell_oid = str(st.get("sell_order_id") or "").strip()

            if pending_sell_oid:
                await _call_plugin_adaptive(
                    sync_pending_sell_order_plugin,
                    context=context,
                    holdings=context.latest_holdings,
                    prices={TARGET_SYMBOL: live_p},
                    symbol=TARGET_SYMBOL,
                    live_price=live_p,
                    now_est=now_est,
                )
                if is_live_assassin_standalone_active(context):
                    continue
                st = context.ledger.get_state(TARGET_SYMBOL)

            if pending_buy_oid:
                await _call_plugin_adaptive(
                    sync_pending_buy_order_plugin,
                    context=context,
                    holdings=context.latest_holdings,
                    prices={TARGET_SYMBOL: live_p},
                    symbol=TARGET_SYMBOL,
                    live_price=live_p,
                    now_est=now_est,
                )
                st = context.ledger.get_state(TARGET_SYMBOL)

            # ---------------------------------------------------------------
            # STEP 5: 주기적 브로커 실잔고 조회 및 무결성 화해 (SOXL + 바벨 SGOV)
            # ---------------------------------------------------------------
            now_mono = time.monotonic()
            reconcile_interval = (
                4.5 if is_active_buy_window(hm, now_est=now_est) else 15.0
            )
            if (
                not str(st.get("buy_order_id") or "").strip()
                and not str(st.get("sell_order_id") or "").strip()
                and (now_mono - last_reconcile_mono) >= reconcile_interval
            ):
                last_reconcile_mono = now_mono
                holdings_map, fetch_ok = (
                    await context.api.get_holdings_map_with_status()
                )
                if fetch_ok and isinstance(holdings_map, dict):
                    context.latest_holdings = holdings_map
                    context.holdings_fetch_ok = True
                    h_lp = safe_float(
                        holdings_map.get(TARGET_SYMBOL, {}).get("last_price"),
                        0.0,
                    )
                    if live_p <= 0.0 and h_lp > 0.0:
                        live_p = h_lp
                        context.latest_prices[TARGET_SYMBOL] = live_p
                        context.last_soxl_live_price = live_p
                        context.last_soxl_live_price_mono = now_mono
                    await _call_plugin_adaptive(
                        reconcile_stratum_with_broker_holdings_plugin,
                        context=context,
                        holdings=holdings_map,
                        prices={TARGET_SYMBOL: live_p},
                        now_est=now_est,
                        force_sync=False,
                    )
                    if is_live_assassin_standalone_active(context):
                        continue
                    st = context.ledger.get_state(TARGET_SYMBOL)

            # ---------------------------------------------------------------
            # STEP 5-B: ⚖️ 바벨 모드(BARBELL_60_30_10) 정규장 전용 SGOV 매매/체결 동기화
            # ---------------------------------------------------------------
            if is_barbell_mode(st.get("portion_mode")):
                try:
                    await execute_barbell_sgov_tick_plugin(
                        context=context,
                        now_est=now_est,
                    )
                    st = context.ledger.get_state(TARGET_SYMBOL)
                except asyncio.CancelledError:
                    raise
                except Exception as bb_exc:
                    logger.warning(
                        "⚠️ [Barbell SGOV 플러그인 예외 격리]: %s", bb_exc
                    )

            # ---------------------------------------------------------------
            # STEP 6: 평일 16:00 EST 정규장 마감 일일 결산 보고 (일 1회)
            # ---------------------------------------------------------------
            if (
                1600 <= hm <= 1659
                and str(st.get("last_closing_report_date") or "") != today_str
            ):
                await _call_plugin_adaptive(
                    execute_1600_daily_closing_settlement_plugin,
                    context=context,
                    holdings=context.latest_holdings,
                    prices={TARGET_SYMBOL: live_p},
                    now_est=now_est,
                )
                st = context.ledger.get_state(TARGET_SYMBOL)

            # ---------------------------------------------------------------
            # STEP 7: 실전 스나이퍼 작동 ON/OFF 확인 (OFF 시 실전 매매 보류)
            # ---------------------------------------------------------------
            if not bool(st.get("is_active", True)):
                context.fast_shield_mode = _evaluate_fast_shield_mode(
                    context, st
                )
                wait_off = (
                    FAST_SHIELD_LOOP_INTERVAL_SEC
                    if context.fast_shield_mode
                    else NORMAL_LOOP_INTERVAL_SEC
                )
                try:
                    await asyncio.wait_for(
                        context.wakeup_event.wait(), timeout=_wall_wait(wait_off)
                    )
                    context.wakeup_event.clear()
                except asyncio.TimeoutError:
                    pass
                continue

            # ---------------------------------------------------------------
            # STEP 8: 실시간 스나이퍼 다중 익절 매도 모니터 (오팔 최우선)
            # ---------------------------------------------------------------
            did_sell_action = False
            has_any_holdings = bool(
                st.get("buckets") or st.get("sub_buckets")
            )
            if (
                has_any_holdings
                and is_active_sell_window(hm, now_est=now_est)
                and not str(st.get("buy_order_id") or "").strip()
            ):
                sell_res = await _call_plugin_adaptive(
                    execute_1m_sniper_sell_and_reanchor_plugin,
                    context=context,
                    holdings=context.latest_holdings,
                    symbol=TARGET_SYMBOL,
                    live_price=live_p,
                    prices={TARGET_SYMBOL: live_p},
                    now_est=now_est,
                )
                if is_live_assassin_standalone_active(context):
                    continue
                st = context.ledger.get_state(TARGET_SYMBOL)
                if (
                    str(st.get("sell_order_id") or "").strip()
                    or (
                        isinstance(sell_res, dict)
                        and bool(sell_res.get("did_sell_or_ratchet"))
                    )
                    or (
                        isinstance(sell_res, str)
                        and any(
                            tag in sell_res
                            for tag in (
                                "FILLED",
                                "SUBMITTED",
                                "SETTLED",
                                "SOLD",
                            )
                        )
                    )
                ):
                    did_sell_action = True

            # ---------------------------------------------------------------
            # STEP 9: 실시간 스나이퍼 시드보호 매수 게이트 (떨사 · 평일 04:07 ~ 16:00 EST)
            # ---------------------------------------------------------------
            if (
                not did_sell_action
                and not is_live_assassin_standalone_active(context)
                and is_active_buy_window(hm, now_est=now_est)
                and not str(st.get("sell_order_id") or "").strip()
                and not str(st.get("buy_order_id") or "").strip()
            ):
                await _call_plugin_adaptive(
                    execute_seed_protected_buy_gate_plugin,
                    context=context,
                    holdings=context.latest_holdings,
                    symbol=TARGET_SYMBOL,
                    live_price=live_p,
                    prices={TARGET_SYMBOL: live_p},
                    metrics=context.candle_metrics_cache.get(
                        TARGET_SYMBOL, {}
                    ),
                    now_est=now_est,
                )
                st = context.ledger.get_state(TARGET_SYMBOL)

            # ---------------------------------------------------------------
            # STEP 10: 적응형 루프 대기 주기 산출 (0.40s / 1.50s / 장외 무포지션 5.00s)
            # ---------------------------------------------------------------
            context.fast_shield_mode = _evaluate_fast_shield_mode(context, st)
            if context.fast_shield_mode:
                loop_sleep = FAST_SHIELD_LOOP_INTERVAL_SEC
            elif (
                is_extended_sell_only_window(hm, now_est=now_est)
                and not st.get("buckets")
                and not st.get("sub_buckets")
            ):
                loop_sleep = EXTENDED_ZERO_HOLD_INTERVAL_SEC
            else:
                loop_sleep = NORMAL_LOOP_INTERVAL_SEC

        except asyncio.CancelledError:
            break
        except Exception as loop_exc:
            logger.warning(
                "⚠️ [메인 스나이퍼 루프 예외 격리(자가 치유 계속 가동)]: %s",
                loop_exc,
            )
            loop_sleep = NORMAL_LOOP_INTERVAL_SEC

        try:
            await asyncio.wait_for(
                context.wakeup_event.wait(), timeout=_wall_wait(loop_sleep)
            )
            context.wakeup_event.clear()
        except asyncio.TimeoutError:
            pass


# ---------------------------------------------------------------------------
# [핵심 4] 백그라운드 태스크 3 : 일일 17:00 EST GC · 백업 스냅샷 및 환율 갱신 루프
# ---------------------------------------------------------------------------
async def daily_gc_and_rollover_loop(context: SniperAppContext) -> None:
    last_gc_date: str = ""
    while not context.shutdown_event.is_set():
        now_est = datetime.now(EST_TZ)
        hm = now_est.hour * 100 + now_est.minute
        today_str = now_est.strftime("%Y-%m-%d")

        try:
            fx_r = safe_float(await context.api.get_usd_krw_rate(), 0.0)
            if fx_r > 500.0:
                context.last_fx_rate = fx_r
        except Exception:
            pass

        if hm >= 1700 and last_gc_date != today_str:
            try:
                await _call_plugin_adaptive(
                    execute_daily_1700_gc_and_backup_plugin,
                    context=context,
                    now_est=now_est,
                )
                last_gc_date = today_str
            except Exception as gc_exc:
                logger.debug("17:00 일일 GC 루프 예외(묵음): %s", gc_exc)

        try:
            await asyncio.wait_for(
                context.shutdown_event.wait(), timeout=300.0
            )
        except asyncio.TimeoutError:
            pass


# ---------------------------------------------------------------------------
# [핵심 5] 부팅 시퀀스 · 3대 TDD 검증 · 계좌/수수료 락온 및 5대 태스크 오케스트레이터 (async_main)
# ---------------------------------------------------------------------------
async def async_main() -> int:
    """
    🚨 제1헌법 ~ 제6헌법 & Case 01 ~ Case 93 + 바벨(60/30/10) + 실전 암살자 분리 부팅 시퀀스:
    1) 구버전 데드코드 청소 및 15대 코어 모듈(barbell_plugin.py, assassin_plugin.py 포함) 무디스크 인메모리 컴파일 검증
    2) 스나이퍼 TDD(run_quant_engine_tdd) + 바벨 60/30/10 TDD(run_barbell_plugin_tdd) + 암살자 14대 게이트 TDD(run_assassin_plugin_tdd) 실행
    3) SniperAppContext 초기화 (스나이퍼 원장 + 바벨 원장 + 암살자 원장 동시 장착)
    4) 토스 종합매매 계좌(accountSeq) 및 미국 주식 실제 수수료율(GET /api/v1/commissions · Case 86) 락온
    5) 초기 실잔고 무결성 대조(실전 암살자 단독 모드 시 제외) 및 "✅ 서버가 정상 작동 중입니다." 생존 배너 타전
    6) 5대 비동기 워커 가동 및 종료/업데이트 시 3.5초 하드 워치독 · os.execv 인플레이스 무중단 자가 교체 (Case 81)
    """
    base_dir = get_bot_base_dir()
    purge_deprecated_legacy_files(base_dir)

    ok_comp, comp_msg = verify_all_modules_compile(base_dir)
    if not ok_comp:
        logger.error("🚨 부팅 프리플라이트 검증 실패:\n%s", comp_msg)
        return 1
    logger.info("🛡️ %s", comp_msg)

    # 3대 코어 엔진 TDD 자가 검증
    run_quant_engine_tdd()
    run_barbell_plugin_tdd()
    run_assassin_plugin_tdd()
    logger.info(
        "✅ [QuantEngine TDD · Barbell 60/30/10 TDD · Assassin 10 Truth Gates TDD] 전수 검증 통과!"
    )

    context = SniperAppContext(base_dir=base_dir)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, context.shutdown_event.set)
        except Exception:
            pass

    try:
        if hasattr(context.api, "ensure_account_seq"):
            acc_res = context.api.ensure_account_seq()
            if inspect.isawaitable(acc_res):
                await acc_res
    except Exception as acc_exc:
        logger.warning("⚠️ 초기 accountSeq 확인 예외(재시도 예정): %s", acc_exc)

    try:
        if hasattr(context.api, "ensure_us_commission_rate"):
            us_c, rt_p = await context.api.ensure_us_commission_rate(
                force_refresh=True
            )
            if us_c > 0.0 and rt_p > 0.0:
                await context.ledger.update_state(
                    TARGET_SYMBOL,
                    us_commission_rate=us_c,
                    round_trip_fee_rate_pct=rt_p,
                )
                await context.assassin_ledger.update_state(
                    us_commission_rate=us_c,
                    round_trip_fee_rate_pct=rt_p,
                )
                logger.info(
                    "🏦 [Case 86 계좌별 미국 주식 수수료율 락온 완료] 편도=%.4f%% / 왕복=%.2f%%",
                    us_c * 100.0,
                    rt_p,
                )
    except Exception as comm_exc:
        logger.debug("초기 수수료율 조회 폴백(원장 보존): %s", comm_exc)

    # 초기 실잔고 및 현재가 동기화
    try:
        now_est = datetime.now(EST_TZ)
        p_map = await context.api.get_current_prices_batch(
            (TARGET_SYMBOL, MACRO_REF_SYMBOL)
        )
        init_lp = safe_float(p_map.get(TARGET_SYMBOL), 0.0)
        if init_lp > 0.0:
            context.latest_prices[TARGET_SYMBOL] = init_lp
            context.last_soxl_live_price = init_lp
            context.last_soxl_live_price_mono = time.monotonic()
        init_qqq = safe_float(p_map.get(MACRO_REF_SYMBOL), 0.0)
        if init_qqq > 0.0:
            context.latest_prices[MACRO_REF_SYMBOL] = init_qqq
            context.last_qqq_live_price = init_qqq

        holdings_map, fetch_ok = (
            await context.api.get_holdings_map_with_status()
        )
        if fetch_ok and isinstance(holdings_map, dict):
            context.latest_holdings = holdings_map
            context.holdings_fetch_ok = True
            if not is_live_assassin_standalone_active(context):
                await _call_plugin_adaptive(
                    reconcile_stratum_with_broker_holdings_plugin,
                    context=context,
                    holdings=holdings_map,
                    prices={TARGET_SYMBOL: init_lp},
                    now_est=now_est,
                    force_sync=True,
                )
                st_boot = context.ledger.get_state(TARGET_SYMBOL)
                if is_barbell_mode(st_boot.get("portion_mode")) and not bool(
                    context.barbell_ledger.get_state().get(
                        "is_initialized", False
                    )
                ):
                    await initialize_or_sync_barbell_on_mode_enter(
                        context=context, holdings_map=holdings_map
                    )
    except Exception as init_exc:
        logger.debug("부팅 초기 잔고 동기화 스킵: %s", init_exc)

    # 기동 완료 생존 신호 타전 (Case 16)
    try:
        await context.tg.send_startup_alive_banner()
    except Exception:
        pass

    tasks = [
        asyncio.create_task(
            main_sniper_loop(context), name="main_sniper_loop"
        ),
        asyncio.create_task(
            candle_radar_loop(context), name="candle_radar_loop"
        ),
        asyncio.create_task(
            daily_gc_and_rollover_loop(context),
            name="daily_gc_and_rollover_loop",
        ),
        asyncio.create_task(
            context.tg.run_polling_loop(), name="telegram_polling_loop"
        ),
        asyncio.create_task(
            _run_auto_update_loop_dynamic(context), name="auto_update_loop"
        ),
    ]

    try:
        await context.shutdown_event.wait()
    finally:
        if context.restart_requested:
            arm_hard_restart_watchdog(
                delay_sec=3.5,
                reason=str(context.restart_reason or "RESTART_REQUESTED"),
            )

        for t in tasks:
            if not t.done():
                t.cancel()
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=2.0
            )
        except Exception:
            pass

        # MODIFIED: 종료 시 텔레그램 비동기 HTTP 세션 1회 정상 회수
        try:
            if hasattr(context.tg, "close"):
                await asyncio.wait_for(context.tg.close(), timeout=1.5)
        except Exception:
            pass

        try:
            await asyncio.wait_for(context.api.close(), timeout=1.5)
        except Exception:
            pass

        if context.restart_requested:
            perform_self_restart_execv(
                reason=str(context.restart_reason or "RESTART_REQUESTED")
            )

    return 0


def main() -> int:
    try:
        return asyncio.run(async_main())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
