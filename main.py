# -*- coding: utf-8 -*-
"""
# MODIFIED: main.py
인피니트 스노우볼 (Infinite Snowball) v3.0 — 순수 롱(🐂 SOXL 단독) 매수 04:07 ~ 16:00 EST 제한
(정규장 마감 30분 전 15:30 ~ 16:00 EST 0주 새 사이클 1층 진입 및 1층 공석 +1.0% 돌파 추격 차단 · Case 84) &
익절 매도 24시간 전 세션(프리마켓 + 정규장 + 애프터마켓 + 데이마켓 · 방안 C 오버나이트 통합이평 사수 · Case 83) 확장 오버나이트 7층 골디락스 멀티 그리드 지층관리 스나이퍼
경량화 메인 오케스트레이터 코어 모듈 (메인 코드 2분할 리팩토링 Part 2 / 2 · Step 09 / 09)
- 최종 확정 진화 챔피언 (🌟 POCKET_ALLIN / 🔥 GRID_L1_ALLIN × 💉 05_RESV_6P_GUARD30 × 🔓 06_STEP2X_15PCT_C20 × 🌃 OVERNIGHT_WMA_GRAD_LOCK × 🛡️ LATE_1530_CUTOFF · 기본값 NONE[OFF] · Case 70 ~ Case 84) 100% 결속:
  1) main_runtime.py 와 역할 분리를 통해 모바일 편집기 및 유지보수에 최적화된 경량 오케스트레이터 구현
  2) 8%(12.5분할) 황금비율 정액 기반 정량제 & 온디맨드 예비시드 수혈금(injected_reserve_usd)을 제외한 순수 코어 총자산(core_equity) 기반 정량 산출 &
     min(1회분 예산 상한 주수, 기준가 고정 정량) 이중 캡핑(Case 67, Case 77) & 자투리 절약금(부분 체결 시 비례 정산 Case 78) · 세후 실현수익금 실시간 시드 풀 복리 산입
  3) 🌟 [Case 80] 미동부 프리장 황금시간대(07:00 ~ 07:50 EST & 1분봉 Wilder RSI(14) <= 19.0) 도달 시 전술 제어반(/settlement) 선택 모드
     (기본값 NONE[OFF] ↔ POCKET_ALLIN[독립 골든포켓 100%] ↔ GRID_L1_ALLIN[7층 그리드 1층편입 100%])에 따라 가용 현금 시드 100% 전액 추가매수 집행!
  4) 🎯 [Case 78] 활성 1층 지정가 부분 체결(buckets[0].qty < l1_target_quota_qty) 시 04:07 ~ 16:00 EST 구간에서 매수 후 60.0초 타임쉴드 경과 시점부터
     매 1.5초 실시간 모니터에서 현재가 <= 1층 단가(buckets[0].book_price) 재도래 시 미체결 잔량(TOPUP_1FL) 지정가 60초 재대기 및 기존 1층 무승격 원자적 합산!
  5) 🛡️ [Case 73 & Case 84] 15:30 ~ 16:00 EST 정규장 마감 30분 전 구간에서는 0주 새 사이클 첫 1층(REENTRY_1FL) 진입과
     상단 2층 ~ 7층 보유 · 1층 공석 상태의 +1.00% 상승돌파(BREAKOUT_RELOAD) 추격을 원천 차단하고,
     2층 단가 상한 가드(HOLD_PREVENT_INVERSION · Case 73) 하의 -1.00% 눌림목(PULLBACK_RELOAD) 재장전은 정상 허용!
  6) 활성 1층 보유 중 정적 기억 사이클 최저 매수가(cycle_min_buy_price) 기본 잠금 기반 10분 고정 4단 와이드 활주로 및
     STEP2X_15PCT_C20 3중 안전문(-15.0% 스텝업 해금 · Case 76) & GUARD30 / 최대 +6회분 온디맨드 예비시드 수혈 및 0주 졸업 자동 상환(Case 77)
  7) ⚡ [Case 65, Case 70, Case 71, Case 72, Case 79, Case 80, Case 82 & Case 83] 매수 직후 최초 60.0초 타임쉴드 유지 & 이후 보유 중 프리·정규·애프터·데이마켓
     24시간 전 세션(is_active_sell_window)에서 매 1.5초 실시간 4중 다중 익절 + 최근 5.0초 체결틱 윗꼬리 병행 감지 + 방안 C 오버나이트 통합이평 사수 스나이퍼 매도 모니터 가동!
  8) 🚨 [Case 66 미결 매수/매도 선행 정산 및 16:00 마감 72번 버킷 보호 후 일일 결산 실행], [Case 11 SIGTERM 0.1초 고속 안전 종료 가드],
     [Case 75 httpx/httpcore 로그 묵음화] 및 [Case 81 장외 자동 업데이트 / 수동 업데이트 직후 2.0초 태스크 타임아웃 취소 · 텔레그램 소켓 즉시 반납 · os.execv 인플레이스 무중단 자가 교체 결속]
- 제1헌법 ~ 제6헌법 및 Case 01 ~ 84 전수 락온
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
    buckets_from_dicts,
    has_active_l1_bucket,
    pocket_from_dict,
    run_quant_engine_tdd,
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
    EST_TZ,
    LOCKED_BUY_INTERVAL_MIN,
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

# 메인 루프 주기 상수 (평시 1.5초 실시간 타점 감시 / 미체결 주문 체결 확인 부스터 0.4초 / 장외 0주 무포지션 대기 5.0초)
NORMAL_LOOP_INTERVAL_SEC: float = 1.50
FAST_SHIELD_LOOP_INTERVAL_SEC: float = 0.40
EXTENDED_ZERO_HOLD_INTERVAL_SEC: float = 5.00


# ---------------------------------------------------------------------------
# [핵심 1] 스나이퍼 애플리케이션 전역 컨텍스트 (SniperAppContext — Case 68 폴더별 3중 원장 & Case 81 자가 재기동 결속)
# ---------------------------------------------------------------------------
class SniperAppContext:
    """
    코어 모듈이 공유하는 단일 런타임 상태 컨텍스트 (Case 68 폴더 위치 기반 격리 및 Case 81 무중단 자가 교체 플래그 적용).
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

        self.in_memory_ordering_lock: asyncio.Lock = asyncio.Lock()
        self.dual_strike_mutex: asyncio.Lock = asyncio.Lock()
        self.wakeup_event: asyncio.Event = asyncio.Event()
        self.shutdown_event: asyncio.Event = asyncio.Event()

        # [Case 81]: 장외 무인 자동 업데이트 및 /update 재기동 요청 플래그
        self.restart_requested: bool = False
        self.restart_reason: str = ""

        self.latest_prices: Dict[str, float] = {TARGET_SYMBOL: 0.0}
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
# [핵심 2] 백그라운드 태스크 1 : 1분봉 시계열 · Wilder's RSI(14) 및 10분 게이트 지표 레이더 (candle_radar_loop)
# ---------------------------------------------------------------------------
async def candle_radar_loop(context: SniperAppContext) -> None:
    """
    # [Case 79 & Case 80 : 주말 휴장 폴링 차단 및 장외 트래픽 최적화]:
    1분봉 및 일봉을 주기적으로 수집하여 VWAP, 5MA 진폭, Heikin-Ashi 추세, Wilder's RSI(14) 기저값을 산출한다.
    - 주말 휴장(_check_weekend_nyse_closed_dynamic) 중에는 불필요한 차트 API 호출을 스킵하고 30초 대기한다.
    - 데이마켓/애프터마켓에서 브로커가 캔들 데이터를 제공하지 않더라도 경고 로그나 알림 없이 100% 묵음 처리한다.
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
                symbol=TARGET_SYMBOL, total_count=(300 if in_market else 200)
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
                context.latest_prices[TARGET_SYMBOL] = safe_float(
                    metrics.get("live_price"), 0.0
                )
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


# ---------------------------------------------------------------------------
# [핵심 3] 백그라운드 태스크 2 : 매수(04:07 ~ 16:00 EST · Case 84) & 익절 매도(24시간 전 세션 · Case 83) 메인 지층 스나이퍼 루프 (main_sniper_loop)
# ---------------------------------------------------------------------------
def _evaluate_fast_shield_mode(
    context: SniperAppContext,
    now_est: datetime,
    live_p: float,
) -> bool:
    """
    # [Case 70, Case 78, Case 79 & Case 80]:
    - 평시 보유 중 매도 모니터, 황금시간(07:00~07:50 EST) 모니터 및 1층 미체결 잔량(TOPUP_1FL) 모니터는
      매 1.5초(NORMAL_LOOP_INTERVAL_SEC)마다 실시간 타점 감시를 수행한다.
    - 0.4초 고속 루프(FAST_SHIELD_LOOP_INTERVAL_SEC)는:
      1) 프리·정규·애프터·데이마켓 전 구간(is_active_sell_window)에서 미체결 주문(buy_order_id / sell_order_id) 체결 확인 대기 중일 때
      2) 04:07 ~ 16:00 EST 의 10분 매수 게이트 정각 오픈 경계이면서 활성 1층이 존재하고 60초 타임쉴드나 입금대기 쉴드에 막혀 있지 않을 때만 작동한다.
    """
    hm = now_est.hour * 100 + now_est.minute
    if not is_active_sell_window(hm, now_est=now_est):
        return False

    st = context.ledger.get_state(TARGET_SYMBOL)
    if not bool(st.get("is_active", True)):
        return False

    if str(st.get("buy_order_id") or "").strip() or str(
        st.get("sell_order_id") or ""
    ).strip():
        return True

    if is_active_buy_window(hm, now_est=now_est):
        in_sell_sh, _ = is_within_post_sell_time_shield(
            context, st, TARGET_SYMBOL
        )
        in_buy_sh, _ = is_within_post_buy_time_shield(
            context, st, TARGET_SYMBOL
        )
        in_res_sh, _ = is_within_reserve_deposit_check_shield(
            context, st, TARGET_SYMBOL
        )
        if in_sell_sh or in_buy_sh or in_res_sh:
            return False

        buckets = buckets_from_dicts(st.get("buckets", []))
        if not buckets or not has_active_l1_bucket(buckets):
            return False

        is_gate_open, _, _, b_info = evaluate_buy_gate_bucket_status(
            now_est=now_est,
            buy_interval_min=LOCKED_BUY_INTERVAL_MIN,
            last_evaluated_bucket_id=safe_int(
                st.get("last_evaluated_buy_bucket_id"), -1
            ),
            last_evaluated_date=str(st.get("last_evaluated_date") or ""),
        )
        if is_gate_open and bool(b_info.get("is_exact_boundary_min")):
            return True

    return False


async def main_sniper_loop(context: SniperAppContext) -> None:
    """
    # MODIFIED [Case 01, Case 65, Case 66, Case 70 ~ Case 84 (방안 C 오버나이트 통합이평 사수 & 16:00 마감 72번 버킷 보호)]:
    - 04:00 ~ 04:06 EST : 프리장 개장 초기 호가 안정화 및 직전 데이마켓 미결 주문 force_settle 선행 정산 후 잔류 미체결 취소
    - 04:07 ~ 16:00 EST : 프리장 + 정규장 (황금시간 07:00~07:50 전액매수[제어반 ON 시] + 매수 게이트[15:30~16:00 0주 새사이클/돌파 차단 Case 84 · 16:00 마감 72번 버킷 추매 보호] + ⚡1.5초 실시간 4중 다중 익절 + 윗꼬리 체결틱 병행 감지 매도 모니터 동시 가동)
    - 16:01 ~ 19:59 EST (또는 16:00:50 이후 미결 무주문 시) : 애프터마켓 진입 즉시 16:00 일일 결산 보고 단 1회 실행 후 루프 중단 없이 ⚡1.5초 방안 C 통합이평 일괄졸업 감시 연속 가동 · 개별층 및 매수 잠금
    - 20:00 ~ 03:59 EST : 데이마켓 (⚡1.5초 방안 C 통합이평 일괄졸업 감시 상시 가동 · 개별층 및 매수 잠금 · 브로커 시세 미제공/거래 제한 시 100% 묵음 대기)
    """
    while not context.shutdown_event.is_set():
        now_est = datetime.now(EST_TZ)
        hm = now_est.hour * 100 + now_est.minute
        is_ext_sell_only = False

        try:
            if _check_weekend_nyse_closed_dynamic(now_est):
                context.fast_shield_mode = False
                try:
                    await asyncio.wait_for(
                        context.shutdown_event.wait(), timeout=15.0
                    )
                except asyncio.TimeoutError:
                    pass
                continue

            is_ext_sell_only = is_extended_sell_only_window(
                hm, now_est=now_est
            )

            price_map = await context.api.get_current_prices_batch(
                (TARGET_SYMBOL,)
            )
            fresh_tick_p = safe_float(price_map.get(TARGET_SYMBOL), 0.0)
            live_p = fresh_tick_p
            if live_p > 0.0:
                context.latest_prices[TARGET_SYMBOL] = live_p

            holdings_map, fetch_ok = (
                await context.api.get_holdings_map_with_status()
            )
            context.holdings_fetch_ok = fetch_ok
            if fetch_ok and isinstance(holdings_map, dict):
                context.latest_holdings = holdings_map
                # Case 79: 프리장/정규장에서만 holdings.last_price 폴백을 허용하고,
                # 데이마켓/애프터마켓(is_ext_sell_only)에서 시세 API 가 0.0 을 반환한 날에는
                # 정적 종가(last_price)로 매도 모니터가 오발주하지 않도록 fresh_tick_p 만 신뢰한다.
                if live_p <= 0.0 and not is_ext_sell_only:
                    live_p = safe_float(
                        holdings_map.get(TARGET_SYMBOL, {}).get("last_price"),
                        0.0,
                    )
                    if live_p > 0.0:
                        context.latest_prices[TARGET_SYMBOL] = live_p

            if (
                live_p > 0.0
                and TARGET_SYMBOL in context.candle_metrics_cache
                and isinstance(
                    context.candle_metrics_cache[TARGET_SYMBOL], dict
                )
            ):
                context.candle_metrics_cache[TARGET_SYMBOL] = (
                    refresh_metrics_with_live_tick(
                        context.candle_metrics_cache[TARGET_SYMBOL],
                        live_p,
                        now_est=now_est,
                    )
                )

            prices = dict(context.latest_prices)
            # Case 79: 애프터/데이마켓에서는 실제로 방금 조회된 실시간 시세(fresh_tick_p)만 매도 모니터에 전달!
            prices_for_sell = (
                {TARGET_SYMBOL: fresh_tick_p}
                if is_ext_sell_only
                else prices
            )
            holdings = dict(context.latest_holdings)

            if 400 <= hm <= 406:
                prev_0400_date = str(
                    getattr(context, "last_0400_sync_date", "") or ""
                )
                today_0400_str = now_est.strftime("%Y-%m-%d")
                await _call_plugin_adaptive(
                    execute_0400_premarket_stabilization_plugin,
                    context=context,
                    holdings=holdings,
                    prices=prices,
                    now_est=now_est,
                )
                # 🚨 Case 74, Case 76, Case 77 & Case 80: 04:00 EST 오프닝 시점에 일일 카운터는 0회로 확실히 리셋하되, 단 1회 입금 알림 래치는 보존!
                if prev_0400_date != today_0400_str:
                    await context.ledger.update_state(
                        TARGET_SYMBOL,
                        daily_seed_protect_pass_cnt=0,
                        daily_unlock_buy_events=0,
                        daily_golden_allin_buy_events=0,
                        daily_golden_pocket_sell_cnt=0,
                        daily_golden_realized_net_usd=0.0,
                        daily_reserve_injected_cnt=0,
                        daily_dust_guard_blocked_cnt=0,
                        pending_step_up_min_price=0.0,
                        last_evaluated_buy_bucket_id=-1,
                        last_evaluated_date=today_0400_str,
                        last_reentry_eval_ts=0.0,
                        last_reserve_check_ts=0.0,
                    )

            elif is_active_sell_window(hm, now_est=now_est):
                # 🚨 [Step 3-0 · Case 66] 미결 매수/매도 주문 최우선 선행 정산
                st_pre = context.ledger.get_state(TARGET_SYMBOL)
                if str(st_pre.get("buy_order_id") or "").strip():
                    await _call_plugin_adaptive(
                        sync_pending_buy_order_plugin,
                        context=context,
                        holdings=holdings,
                        prices=prices,
                        now_est=now_est,
                    )
                if str(st_pre.get("sell_order_id") or "").strip():
                    await _call_plugin_adaptive(
                        sync_pending_sell_order_plugin,
                        context=context,
                        holdings=holdings,
                        prices=prices,
                        now_est=now_est,
                    )

                # [Step 3-1] 로컬 7층 그리드 + 독립 골든포켓 원장 ↔ 토스 실보유 잔고 무결성 화해 (24시간 전 세션 작동)
                await _call_plugin_adaptive(
                    reconcile_stratum_with_broker_holdings_plugin,
                    context=context,
                    holdings=holdings,
                    prices=prices,
                    now_est=now_est,
                )

                # ⚡ [Step 3-2 · Case 70, 71, 72, 79, 80, 82, 83] 프리·정규·애프터·데이마켓 24시간 전 세션 매 1.5초 실시간 4중 다중 익절 + 방안 C 매도 모니터
                sell_res = await _call_plugin_adaptive(
                    execute_1m_sniper_sell_and_reanchor_plugin,
                    context=context,
                    holdings=holdings,
                    prices=prices_for_sell,
                    now_est=now_est,
                )
                did_sell = bool(
                    isinstance(sell_res, dict)
                    and sell_res.get("did_sell_or_ratchet")
                )

                # 🔵 [Step 3-3 · Case 44, 78, 79, 80, 84] 매수 게이트/모니터는 오직 04:07 ~ 16:00 EST (is_active_buy_window) 구간에서만 가동!
                # (16:00 EST 마감봉 72번 버킷 평가가 일일 마감 결산보다 먼저 정상 수행되도록 순서 보장!)
                if not did_sell and is_active_buy_window(hm, now_est=now_est):
                    await _call_plugin_adaptive(
                        execute_seed_protected_buy_gate_plugin,
                        context=context,
                        holdings=holdings,
                        prices=prices,
                        now_est=now_est,
                    )

                # 🌙 [Step 3-4 · Case 01, Case 65, Case 66 & Case 79]
                # 16:00 EST 마감봉(72번 버킷) 타격 및 15:59 발주 주문의 60초 대기를 100% 보장한 뒤,
                # 16:01 ~ 16:59 EST (또는 16:00:50 EST 이후 미결 주문이 없는 상태)에서 일일 마감 결산 보고를 단 1회 실행!
                if 1600 <= hm <= 1659:
                    st_chk = context.ledger.get_state(TARGET_SYMBOL)
                    today_close_str = now_est.strftime("%Y-%m-%d")
                    if (
                        str(st_chk.get("last_closing_report_date") or "")
                        != today_close_str
                    ):
                        has_pending_1600 = bool(
                            str(st_chk.get("buy_order_id") or "").strip()
                            or str(st_chk.get("sell_order_id") or "").strip()
                        )
                        if hm >= 1601 or (
                            hm == 1600
                            and now_est.second >= 50
                            and not has_pending_1600
                        ):
                            await _call_plugin_adaptive(
                                execute_1600_daily_closing_settlement_plugin,
                                context=context,
                                holdings=holdings,
                                prices=prices,
                                now_est=now_est,
                            )

            else:
                st_idle = context.ledger.get_state(TARGET_SYMBOL)
                if str(st_idle.get("sell_order_id") or "").strip():
                    await _call_plugin_adaptive(
                        sync_pending_sell_order_plugin,
                        context=context,
                        holdings=holdings,
                        prices=prices,
                        now_est=now_est,
                    )
                if str(st_idle.get("buy_order_id") or "").strip():
                    await _call_plugin_adaptive(
                        sync_pending_buy_order_plugin,
                        context=context,
                        holdings=holdings,
                        prices=prices,
                        now_est=now_est,
                    )

            context.fast_shield_mode = _evaluate_fast_shield_mode(
                context=context,
                now_est=now_est,
                live_p=safe_float(
                    context.latest_prices.get(TARGET_SYMBOL), 0.0
                ),
            )

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error(
                "메인 7층 그리드 스나이퍼 루프 예외: %s", exc, exc_info=True
            )

        # 프리·정규장 전 구간 및 장외 주식 보유 중에는 1.5초(또는 0.4초 부스터)를 100% 유지하되,
        # 매수가 잠긴 장외(애프터·데이장)에서 보유 주식이 0주이고 미결 주문도 없을 때만 5.0초로 대기하여 네트워크 부하 절감
        if context.fast_shield_mode:
            loop_wait = FAST_SHIELD_LOOP_INTERVAL_SEC
        elif is_ext_sell_only:
            st_after = context.ledger.get_state(TARGET_SYMBOL)
            b_after = st_after.get("buckets") or []
            gp_after = pocket_from_dict(st_after.get("golden_pocket"))
            h_qty_after = safe_int(
                context.latest_holdings.get(TARGET_SYMBOL, {}).get("qty"), 0
            )
            has_pos_or_ord = bool(
                len(b_after) > 0
                or gp_after.is_active
                or h_qty_after > 0
                or str(st_after.get("buy_order_id") or "").strip()
                or str(st_after.get("sell_order_id") or "").strip()
            )
            loop_wait = (
                NORMAL_LOOP_INTERVAL_SEC
                if has_pos_or_ord
                else EXTENDED_ZERO_HOLD_INTERVAL_SEC
            )
        else:
            loop_wait = NORMAL_LOOP_INTERVAL_SEC

        context.wakeup_event.clear()
        try:
            await asyncio.wait_for(
                context.wakeup_event.wait(), timeout=loop_wait
            )
        except asyncio.TimeoutError:
            pass


# ---------------------------------------------------------------------------
# [핵심 4] 백그라운드 태스크 3 : 17:00 EST 일일 GC · 날짜별 금고 백업 및 롤오버 루프 (Case 74, 76, 77, 79, 80)
# ---------------------------------------------------------------------------
async def daily_gc_and_rollover_loop(context: SniperAppContext) -> None:
    last_gc_date = ""
    while not context.shutdown_event.is_set():
        now_est = datetime.now(EST_TZ)
        today_str = now_est.strftime("%Y-%m-%d")
        hm = now_est.hour * 100 + now_est.minute

        try:
            if hasattr(context.ledger, "rollover_daily_counters_if_needed"):
                await _call_plugin_adaptive(
                    context.ledger.rollover_daily_counters_if_needed,
                    logical_date=today_str,
                    today_str=today_str,
                )
            if hm >= 1700 and last_gc_date != today_str:
                last_gc_date = today_str
                await execute_daily_1700_gc_and_backup_plugin(
                    context=context, now_est=now_est
                )
                # 🚨 Case 74, Case 76, Case 77, Case 79 & Case 80: 17:00 EST 일일 마감 롤오버 시 일일 매수/패스/황금시간 카운터는 0회로 리셋하되
                # 단 1회 입금 요청 알림 영구 래치(waiting_reserve_deposit_alert_sent) 및 애프터장 미결 매도 주문은 보존!
                await context.ledger.update_state(
                    TARGET_SYMBOL,
                    daily_seed_protect_pass_cnt=0,
                    daily_unlock_buy_events=0,
                    daily_golden_allin_buy_events=0,
                    daily_golden_pocket_sell_cnt=0,
                    daily_golden_realized_net_usd=0.0,
                    daily_reserve_injected_cnt=0,
                    daily_dust_guard_blocked_cnt=0,
                    pending_step_up_min_price=0.0,
                    last_evaluated_buy_bucket_id=-1,
                    last_reentry_eval_ts=0.0,
                )
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("일일 GC/롤오버 루프 예외: %s", exc)

        try:
            await asyncio.wait_for(
                context.shutdown_event.wait(), timeout=30.0
            )
        except asyncio.TimeoutError:
            pass


# ---------------------------------------------------------------------------
# [핵심 5] 시스템 부트스트랩 · 프리플라이트 TDD · Case 11 시그널 0.1초 고속 종료 & Case 81 무중단 인플레이스 교체 가드
# ---------------------------------------------------------------------------
async def _run_init_step_with_cancel_guard(
    context: SniperAppContext,
    coro: Awaitable[Any],
    timeout_sec: float = 8.0,
) -> Any:
    """
    Case 11 [부팅 중 SIGTERM 0.1초 고속 종료 가드]:
    부팅 초기화 네트워크 I/O 도중 SIGTERM / SIGINT 시그널이 유입되면
    블로킹 대기 없이 0.1초 이내에 즉시 코루틴을 취소하고 탈출하여
    systemd 의 'State stop-sigterm timed out. Killing.' 현상을 100% 원천 차단한다.
    """
    if context.shutdown_event.is_set():
        try:
            coro.close()  # type: ignore[attr-defined]
        except Exception:
            pass
        return None

    work_task = asyncio.create_task(coro)
    stop_task = asyncio.create_task(context.shutdown_event.wait())
    try:
        done, _ = await asyncio.wait(
            {work_task, stop_task},
            timeout=timeout_sec,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if stop_task in done or context.shutdown_event.is_set():
            work_task.cancel()
            return None
        if work_task in done:
            return work_task.result()
        work_task.cancel()
        return None
    finally:
        if not stop_task.done():
            stop_task.cancel()
        if not work_task.done():
            work_task.cancel()


async def async_main() -> None:
    base_dir = get_bot_base_dir()

    purged = purge_deprecated_legacy_files(base_dir)
    if purged:
        logger.info("🧹 [구버전 폐기 파일 청소 완료] 삭제 목록: %s", purged)

    ok_compile, err_msg = verify_all_modules_compile(base_dir)
    if not ok_compile:
        logger.critical(
            "🚨 [프리플라이트 컴파일/심볼 검증 실패] 기동 중단: %s", err_msg
        )
        sys.exit(1)

    run_quant_engine_tdd()
    logger.info(
        "✅ [QuantEngine TDD 사전 무결성 검증 통과] 챔피언 🌟 POCKET_ALLIN / 🔥 GRID_L1_ALLIN × 💉 05_RESV_6P_GUARD30 × 🔓 06_STEP2X_15PCT_C20 & 방안 C · Case 84(기본값 OFF · Case 59~84) 검증 완료"
    )

    context = SniperAppContext(base_dir=base_dir)

    loop = asyncio.get_running_loop()

    def _on_signal() -> None:
        logger.info(
            "🛑 종료 시그널(SIGTERM/SIGINT) 수신 -> 고속 안전 종료 개시..."
        )
        context.shutdown_event.set()
        context.wakeup_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except NotImplementedError:
            pass

    if context.shutdown_event.is_set():
        logger.info("✅ [SOXL 7층 골디락스 스나이퍼 안전 종료 완료]")
        return

    try:
        acc_seq = await _run_init_step_with_cancel_guard(
            context, context.api.ensure_account_seq(), timeout_sec=8.0
        )
        if acc_seq is not None:
            logger.info(
                "🏛️ [제2헌법 AccountSeq 락온 완료 · 폴더=%s] accountSeq=%d",
                context.folder_slug,
                acc_seq,
            )
    except Exception as exc:
        logger.warning(
            "⚠️ 초기 AccountSeq 조회 지연 (루프 내 자동 재시도): %s", exc
        )

    if context.shutdown_event.is_set():
        logger.info("✅ [SOXL 7층 골디락스 스나이퍼 안전 종료 완료]")
        return

    try:
        price_map = await _run_init_step_with_cancel_guard(
            context,
            context.api.get_current_prices_batch((TARGET_SYMBOL,)),
            timeout_sec=6.0,
        )
        if (
            isinstance(price_map, dict)
            and safe_float(price_map.get(TARGET_SYMBOL), 0.0) > 0.0
        ):
            context.latest_prices[TARGET_SYMBOL] = safe_float(
                price_map.get(TARGET_SYMBOL), 0.0
            )
        h_res = await _run_init_step_with_cancel_guard(
            context,
            context.api.get_holdings_map_with_status(),
            timeout_sec=6.0,
        )
        if isinstance(h_res, tuple) and len(h_res) == 2:
            holdings_map, fetch_ok = h_res
            context.holdings_fetch_ok = bool(fetch_ok)
            if fetch_ok and isinstance(holdings_map, dict):
                context.latest_holdings = holdings_map
                await _run_init_step_with_cancel_guard(
                    context,
                    reconcile_stratum_with_broker_holdings_plugin(
                        context=context,
                        holdings=holdings_map,
                        prices=context.latest_prices,
                        now_est=datetime.now(EST_TZ),
                        force_sync=True,
                    ),
                    timeout_sec=6.0,
                )
    except Exception as exc:
        logger.warning("초기 잔고/시세 동기화 폴백: %s", exc)

    if context.shutdown_event.is_set():
        logger.info("✅ [SOXL 7층 골디락스 스나이퍼 안전 종료 완료]")
        return

    await _run_init_step_with_cancel_guard(
        context, context.tg._flush_stale_updates_on_startup(), timeout_sec=6.0
    )
    if not context.shutdown_event.is_set():
        await _run_init_step_with_cancel_guard(
            context, context.tg.send_startup_alive_banner(), timeout_sec=6.0
        )

    if context.shutdown_event.is_set():
        logger.info("✅ [SOXL 7층 골디락스 스나이퍼 안전 종료 완료]")
        return

    tasks = [
        asyncio.create_task(candle_radar_loop(context), name="candle_radar"),
        asyncio.create_task(main_sniper_loop(context), name="main_sniper"),
        asyncio.create_task(
            context.tg.run_polling_loop(), name="telegram_polling"
        ),
        asyncio.create_task(
            daily_gc_and_rollover_loop(context), name="daily_gc"
        ),
        asyncio.create_task(
            _run_auto_update_loop_dynamic(context, interval_sec=3600.0),
            name="auto_updater",
        ),
    ]

    logger.info(
        "🚀 [SOXL 7층 골디락스 멀티그리드 스나이퍼 가동 완료 · 폴더=%s] 매수 04:07~16:00 EST(15:30~16:00 0주신규/돌파차단 · 황금시간 전액매수 제어반 선택) & 익절 매도 24시간(프리·정규·애프터·데이장 · 방안 C 통합이평 사수 & 윗꼬리 즉시 체결) 확장(Case 65~84)",
        context.folder_slug,
    )

    try:
        await context.shutdown_event.wait()
    finally:
        # 🚨 Case 81: 재기동 요청 상태에서 혹시 워치독이 아직 가동되지 않았다면 즉시 3.5초 하드 워치독 장착
        if getattr(context, "restart_requested", False):
            arm_hard_restart_watchdog(
                delay_sec=3.5,
                reason=str(
                    getattr(context, "restart_reason", "AUTO_UPDATE")
                    or "AUTO_UPDATE"
                ),
            )

        for t in tasks:
            t.cancel()

        # 🚨 Case 81: 하위 태스크 취소 대기 시 2.0초 하드 타임아웃을 강제하여 무한 블로킹(Deaf Zombie) 원천 차단
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=2.0,
            )
        except Exception:
            pass

        # 🚨 Case 81: 텔레그램 전용 롱폴링 소켓 즉시 반납 (신구 프로세스 HTTP 409 충돌 방지)
        close_tg_fn = getattr(context.tg, "_close_tg_http_client", None)
        if callable(close_tg_fn):
            try:
                await asyncio.wait_for(close_tg_fn(), timeout=1.5)
            except Exception:
                pass

        close_fn = getattr(context.api, "close", None)
        if callable(close_fn):
            try:
                c_res = close_fn()
                if inspect.isawaitable(c_res):
                    await asyncio.wait_for(c_res, timeout=1.5)
            except Exception:
                pass

        # 🚨 Case 81 핵심: 업데이트 재기동 요청 시 asyncio.run() 의 shutdown_default_executor() 스레드 풀 대기 데드락에
        # 갇히기 전에 이 자리에서 즉시 os.execv 인플레이스 프로세스 자가 교체를 집행한다!
        if getattr(context, "restart_requested", False):
            perform_self_restart_execv(
                reason=str(
                    getattr(context, "restart_reason", "AUTO_UPDATE")
                    or "AUTO_UPDATE"
                )
            )

        logger.info("✅ [SOXL 7층 골디락스 스나이퍼 안전 종료 완료]")


if __name__ == "__main__":
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass
