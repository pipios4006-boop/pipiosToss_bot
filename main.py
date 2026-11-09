# -*- coding: utf-8 -*-
"""
# MODIFIED: main.py (Part 1/2 — 🗡️ [모의] 암살자 실주문 100% 물리적 차단 및 상시 작동 결속 · 실전 스나이퍼 STEP 1/4/6/8/9 holdings·prices 필수 인자 완비로 목표가 초과 시 미매도 TypeError 원천 소각 · STEP 6 last_closing_report_date 키 정합성 교정 · Case 01 ~ Case 93)
인피니트 스노우볼 (Infinite Snowball) v3.0 — 순수 롱(🐂 SOXL 단독) 매수 04:07 ~ 16:00 EST 제한
(정규장 마감 30분 전 15:30 ~ 16:00 EST 본·서브 0주 새 사이클 1층 진입 및 1층 공석 +1.0% 돌파 추격 차단 ·
04:07 ~ 15:29 EST 1층 공석 +1.0% 돌파 시 1분봉 Wilder RSI(14) <= 50.0 필터 결합 · Case 84, Case 88, Case 92) &
익절 매도 24시간 전 세션(프리마켓 + 정규장 + 애프터마켓 + 데이마켓 · 방안 C 오버나이트 통합이평 사수 · Case 83) 확장
오버나이트 7층 골디락스 본 그리드(👑 06_L2L7_RATCHET_8PCT · Case 87) +
🛡️ 스위치 없는 100% 기본 상시 적용(Default ON) 3층 서브 그리드(13_SUB_L1L3_RESV05_CAP4L · 최대 4회분[16%] 상한 캡 · Case 88) +
🗡️ 스나이퍼 ON/OFF 및 보유 수량과 무관하게 24시간 상시 작동하며 5대 실시간 알림을 타전하는 [모의 ⇄ 실전 Dual-Ready] 암살자(assassin_plugin.py · ASSASSIN_LIVE_ORDER_HARD_LOCK = True 실주문 100% 잠금 · Case 93)
경량화 메인 오케스트레이터 코어 모듈 (메인 코드 2분할 리팩토링 Part 2 / 2 · Step 14 / 14)
- 제1헌법 ~ 제6헌법 및 Case 01 ~ 93 전수 락온
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import signal
import sys
import time
from datetime import datetime
from typing import Any, Awaitable, Dict, Optional

from assassin_plugin import (
    MACRO_REF_SYMBOL,
    ensure_assassin_ledger,
    execute_simulated_assassin_tick_plugin,
    run_assassin_plugin_tdd,
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
# [Case 75]: 매 1.5초 시세 조회 시 systemd-journald 디스크 쓰기를 유발하는 httpx / httpcore INFO 로그 묵음화
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger("toss_sniper.main")

# 메인 루프 주기 상수 (평시 1.5초 실시간 타점 감시 / 미체결 주문 및 암살자 트레일링 부스터 0.4초 / 장외 0주 무포지션 대기 5.0초)
NORMAL_LOOP_INTERVAL_SEC: float = 1.50
FAST_SHIELD_LOOP_INTERVAL_SEC: float = 0.40
EXTENDED_ZERO_HOLD_INTERVAL_SEC: float = 5.00


# ---------------------------------------------------------------------------
# [핵심 1] 스나이퍼 & [모의] 암살자 전역 컨텍스트 (SniperAppContext — Case 68 폴더별 3중 원장 & 계좌 수수료 복원 & Case 81 자가 재기동 결속)
# ---------------------------------------------------------------------------
class SniperAppContext:
    """
    코어 모듈이 공유하는 단일 런타임 상태 컨텍스트 (Case 68 폴더 위치 기반 격리 · 계좌별 수수료율 동기화 ·
    🗡️ [모의] 암살자 독립 원장 결속 · Case 81 무중단 자가 교체 플래그 적용).
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
        # 🗡️ [모의] 암살자 전용 독립 3중 원장 초기화 및 장착 (스나이퍼 원장·예수금 간섭 0%)
        self.assassin_ledger: Any = ensure_assassin_ledger(self)

        # 원장에 저장된 계좌별 수수료율을 런타임 메모리에 선행 동기화
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

        # [Case 81]: 장외 무인 자동 업데이트 및 /update 재기동 요청 플래그
        self.restart_requested: bool = False
        self.restart_reason: str = ""

        self.latest_prices: Dict[str, float] = {
            TARGET_SYMBOL: 0.0,
            MACRO_REF_SYMBOL: 0.0,
        }
        self.last_soxl_live_price: float = 0.0
        self.last_soxl_live_price_mono: float = 0.0
        self.last_qqq_live_price: float = 0.0
        self.last_fx_rate: float = KRW_PER_USD_DEFAULT
        self.assassin_high_freq_active: bool = False

        self.latest_holdings: Dict[str, Dict[str, Any]] = {
            TARGET_SYMBOL: _empty_soxl_holding_entry()
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
        # Case 79: 데이마켓/애프터마켓 시세 결측이나 거래 제한 관련 사유는 절대 알림을 보내지 않고 100% 묵음 처리
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
# [핵심 2] 백그라운드 태스크 1 : SOXL 1분봉/일봉 · Wilder's RSI(14) · 암살자 4대 지표 및 QQQ 안전망 레이더 (candle_radar_loop)
# ---------------------------------------------------------------------------
async def candle_radar_loop(context: SniperAppContext) -> None:
    """
    # MODIFIED [Case 79, Case 92, Case 93 & 🗡️ 모의 암살자 4대 지표 · QQQ 안전망 레이더]:
    1) SOXL 1분봉(최대 400봉 상한) 및 일봉(10봉)을 수집하여 VWAP, 전일 정규장 종가(prev_reg_close),
       당일 04:07 프리장 시가(pre_open_price), 5MA 진폭, Heikin-Ashi 추세, Wilder's RSI(14) 기저값을 산출한다.
    2) 프리장·정규장(04:00 ~ 16:05 EST) 구간에서는 QQQ 1분봉도 함께 수집하여
       순수 롱 방향성 인지 안전망(vel_1m_pct, vel_3m_pct, bear_drop_amp_pct) 지표를 갱신한다.
    """
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
            context.candle_metrics_cache[TARGET_SYMBOL] = metrics
            if (
                live_p <= 0.0
                and safe_float(metrics.get("live_price"), 0.0) > 0.0
            ):
                fetched_lp = safe_float(metrics.get("live_price"), 0.0)
                context.latest_prices[TARGET_SYMBOL] = fetched_lp
                context.last_soxl_live_price = fetched_lp
                context.last_soxl_live_price_mono = time.monotonic()

            # 04:00 ~ 16:05 EST 구간에서 QQQ 1분봉 방향성 안전망 지표 갱신
            if in_market:
                try:
                    candles_qqq_1m = await context.api.get_candles_1m(
                        symbol=MACRO_REF_SYMBOL, total_count=60
                    )
                    qqq_live_p = safe_float(
                        context.latest_prices.get(MACRO_REF_SYMBOL), 0.0
                    )
                    qqq_metrics = await _compute_qqq_metrics_dynamic(
                        context=context,
                        candles_1m_qqq=candles_qqq_1m,
                        live_price_qqq=qqq_live_p,
                        now_est=now_est,
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
                context.shutdown_event.wait(), timeout=sleep_sec
            )
        except asyncio.TimeoutError:
            pass
# -*- coding: utf-8 -*-
"""
# MODIFIED: main.py (Part 2/2 — 🗡️ [모의] 암살자 상시 작동 루프 결속 · 실전 스나이퍼 STEP 1/4/6/8/9 holdings·prices 인자 100% 완비 및 STEP 6 last_closing_report_date 키 정합성 교정으로 목표가 도달 즉시 익절 매도 보장 · Case 01 ~ Case 93 완비)
"""


def _evaluate_fast_shield_mode(
    context: SniperAppContext, st: Dict[str, Any]
) -> bool:
    """
    미체결 주문 존재 시, 매수/매도 직후 60초 타임쉴드 구간, 또는
    🗡️ 암살자(Assassin) +1.00% 트레일링 점화(assassin_high_freq_active) 시
    루프 주기를 0.40초(FAST_SHIELD_LOOP_INTERVAL_SEC)로 가속한다.
    """
    if bool(getattr(context, "assassin_high_freq_active", False)):
        return True
    if str(st.get("buy_order_id") or "").strip() or str(
        st.get("sell_order_id") or ""
    ).strip():
        return True
    in_b, _ = is_within_post_buy_time_shield(context, st, TARGET_SYMBOL)
    if in_b:
        return True
    in_s, _ = is_within_post_sell_time_shield(context, st, TARGET_SYMBOL)
    if in_s:
        return True
    return False


# ---------------------------------------------------------------------------
# [핵심 3] 백그라운드 태스크 2 : 메인 스나이퍼 & 상시 가동 [모의] 암살자 루프 (main_sniper_loop)
# ---------------------------------------------------------------------------
async def main_sniper_loop(context: SniperAppContext) -> None:
    """
    🚨 제1헌법 ~ 제6헌법 & Case 01 ~ Case 93 + 🗡️ [모의] 암살자 상시 작동 루프:
    1) 평일 04:00 ~ 04:06 EST 오프닝 안정화 (미결 주문 선행 정산 · 수수료율 최신화 · 일일 카운터 롤오버)
    2) 실시간 SOXL (및 04:00 ~ 16:05 EST 구간 QQQ) 현재가 다건 조회 및 1분봉 Wilder RSI(14) · VWAP · HA O(1) 틱 합성
    3) 🗡️ [모의] 암살자 상시 실행 (execute_simulated_assassin_tick_plugin):
       실전 스나이퍼의 ON/OFF 여부 및 보유 수량과 무관하게 매 틱 독립 작동하며(실주문 100% 물리적 차단) 5대 실시간 알림을 타전한다!
    4) 실전 스나이퍼 미결 매수/매도 주문 선행 동기화 (Case 66) 및 실잔고 무결성 화해 (Case 61, 63, 69, 89)
    5) 실전 스나이퍼 매도 모니터 (매수 후 60초 타임쉴드 뒤 24시간 전 세션 1.5초 다중 익절 + 5초 윗꼬리 감지 + 방안 C 오버나이트 통합이평 사수 · Case 70, 79, 82, 83, 88, 89)
    6) 실전 스나이퍼 매수 게이트 (평일 04:07 ~ 16:00 EST · 15:30 0주/돌파 차단 · 1층 공석 돌파 RSI<=50 필터 · 10분 와이드 & STEP2X · Default-ON 3층 서브 그리드 · Case 67, 73, 76, 77, 78, 84, 87, 88, 91, 92)
    7) 평일 16:00 ~ 16:59 EST 일일 마감 결산 브리핑 (인출형 당일 실현수익 현금 인출 가이드 포함 · Case 88, 91)
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

            live_prices_dict: Dict[str, float] = {TARGET_SYMBOL: live_p}
            if qqq_p > 0.0:
                live_prices_dict[MACRO_REF_SYMBOL] = qqq_p

            # ---------------------------------------------------------------
            # STEP 3: 🗡️ [모의] 암살자 상시 가동 엔진 호출
            # (ASSASSIN_LIVE_ORDER_HARD_LOCK = True 실주문 100% 차단 · 실전 스나이퍼와 물리적 완전 격리)
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
                    "⚠️ [Assassin Plugin 예외 격리 · 실전 스나이퍼 무중단 유지]: %s",
                    assn_exc,
                )

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
                    prices=live_prices_dict,
                    symbol=TARGET_SYMBOL,
                    live_price=live_p,
                    now_est=now_est,
                )
                st = context.ledger.get_state(TARGET_SYMBOL)

            if pending_buy_oid:
                await _call_plugin_adaptive(
                    sync_pending_buy_order_plugin,
                    context=context,
                    holdings=context.latest_holdings,
                    prices=live_prices_dict,
                    symbol=TARGET_SYMBOL,
                    live_price=live_p,
                    now_est=now_est,
                )
                st = context.ledger.get_state(TARGET_SYMBOL)

            # ---------------------------------------------------------------
            # STEP 5: 주기적 브로커 실잔고 조회 및 무결성 화해 (Case 61, 63, 66, 69, 89)
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
                        live_prices_dict[TARGET_SYMBOL] = live_p
                        context.last_soxl_live_price = live_p
                        context.last_soxl_live_price_mono = now_mono
                    await _call_plugin_adaptive(
                        reconcile_stratum_with_broker_holdings_plugin,
                        context=context,
                        holdings=holdings_map,
                        prices=live_prices_dict,
                        now_est=now_est,
                        force_sync=False,
                    )
                    st = context.ledger.get_state(TARGET_SYMBOL)

            # ---------------------------------------------------------------
            # STEP 6: 평일 16:00 ~ 16:59 EST 정규장 마감 일일 결산 보고 (일 1회 · Case 88, 91)
            # ---------------------------------------------------------------
            if (
                1600 <= hm <= 1659
                and str(st.get("last_closing_report_date") or "") != today_str
            ):
                await _call_plugin_adaptive(
                    execute_1600_daily_closing_settlement_plugin,
                    context=context,
                    holdings=context.latest_holdings,
                    prices=live_prices_dict,
                    now_est=now_est,
                )
                st = context.ledger.get_state(TARGET_SYMBOL)

            # ---------------------------------------------------------------
            # STEP 7: 실전 스나이퍼 작동 ON/OFF 확인 (OFF 시 실전 매매만 보류)
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
                        context.wakeup_event.wait(), timeout=wait_off
                    )
                    context.wakeup_event.clear()
                except asyncio.TimeoutError:
                    pass
                continue

            # ---------------------------------------------------------------
            # STEP 8: 실시간 스나이퍼 다중 익절 매도 모니터 (오팔 최우선 · Case 45, 70, 79, 82, 83, 88, 89)
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
                    prices=live_prices_dict,
                    symbol=TARGET_SYMBOL,
                    live_price=live_p,
                    now_est=now_est,
                )
                st = context.ledger.get_state(TARGET_SYMBOL)
                if (
                    str(st.get("sell_order_id") or "").strip()
                    or (
                        isinstance(sell_res, dict)
                        and bool(sell_res.get("did_sell_or_ratchet", False))
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
                                "ORDERED",
                            )
                        )
                    )
                ):
                    did_sell_action = True

            # ---------------------------------------------------------------
            # STEP 9: 실시간 스나이퍼 시드보호 매수 게이트 (떨사 · 평일 04:07 ~ 16:00 EST)
            # (동일 틱에서 매도가 발생하지 않았을 때만 진입하여 자전거래 원천 차단 · Case 45)
            # ---------------------------------------------------------------
            if (
                not did_sell_action
                and is_active_buy_window(hm, now_est=now_est)
                and not str(st.get("sell_order_id") or "").strip()
                and not str(st.get("buy_order_id") or "").strip()
            ):
                await _call_plugin_adaptive(
                    execute_seed_protected_buy_gate_plugin,
                    context=context,
                    holdings=context.latest_holdings,
                    prices=live_prices_dict,
                    symbol=TARGET_SYMBOL,
                    live_price=live_p,
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
                context.wakeup_event.wait(), timeout=loop_sleep
            )
            context.wakeup_event.clear()
        except asyncio.TimeoutError:
            pass


# ---------------------------------------------------------------------------
# [핵심 4] 백그라운드 태스크 3 : 일일 17:00 EST GC · 백업 스냅샷 및 환율 갱신 루프
# ---------------------------------------------------------------------------
async def daily_gc_and_rollover_loop(context: SniperAppContext) -> None:
    """
    # [Case 22, Case 68, Case 74 & Case 75]:
    매일 17:00 EST 에 일일 가비지 컬렉션(GC) 및 원장 백업 스냅샷을 수행하고,
    주기적으로 USD/KRW 표시 환율(context.last_fx_rate)을 갱신한다.
    """
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
# [핵심 5] 부팅 시퀀스 · TDD 검증 · 계좌/수수료 락온 및 5대 태스크 오케스트레이터 (async_main)
# ---------------------------------------------------------------------------
async def async_main() -> int:
    """
    🚨 제1헌법 ~ 제6헌법 & Case 01 ~ Case 93 부팅 시퀀스:
    1) 구버전 데드코드 파일 청소 및 14대 코어 모듈(assassin_plugin.py 포함) 무디스크 인메모리 컴파일 검증
    2) 스나이퍼 퀀트 엔진 TDD(run_quant_engine_tdd) + 🗡️ 암살자 14대 진성 게이트 TDD(run_assassin_plugin_tdd) 실행
    3) SniperAppContext 초기화 (스나이퍼 3중 원장 + [모의] 암살자 전용 3중 원장 동시 장착)
    4) 토스 종합매매 계좌(accountSeq) 및 미국 주식 실제 수수료율(GET /api/v1/commissions · Case 86) 락온
    5) 초기 실잔고 무결성 대조 및 "✅ 서버가 정상 작동 중입니다." 생존 배너 타전 (Case 16)
    6) 5대 비동기 워커(main_sniper_loop · candle_radar_loop · daily_gc_and_rollover_loop · tg.run_polling_loop · _run_auto_update_loop_dynamic) 가동
    7) 종료/업데이트 시 3.5초 하드 워치독 및 os.execv 인플레이스 무중단 자가 교체 (Case 81)
    """
    base_dir = get_bot_base_dir()
    purge_deprecated_legacy_files(base_dir)

    ok_comp, comp_msg = verify_all_modules_compile(base_dir)
    if not ok_comp:
        logger.error("🚨 부팅 프리플라이트 검증 실패:\n%s", comp_msg)
        return 1
    logger.info("🛡️ %s", comp_msg)

    # 스나이퍼 코어 TDD & 암살자 플러그인 TDD 자가 검증
    run_quant_engine_tdd()
    run_assassin_plugin_tdd()
    logger.info(
        "✅ [Quant Engine TDD & Assassin 14 Truth Gates TDD] 전수 검증 통과!"
    )

    context = SniperAppContext(base_dir=base_dir)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, context.shutdown_event.set)
        except Exception:
            pass

    # 제2헌법 & Case 86: 종합매매 accountSeq 및 계좌별 미국 주식 수수료율 락온
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
            await _call_plugin_adaptive(
                reconcile_stratum_with_broker_holdings_plugin,
                context=context,
                holdings=holdings_map,
                prices={TARGET_SYMBOL: init_lp},
                now_est=now_est,
                force_sync=True,
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
