# -*- coding: utf-8 -*-
"""
# MODIFIED: sniper_plugin.py
순수 롱(SOXL) 전용 '04:07 ~ 16:00 EST 매도(및 0주 싸이클 종료) 후 60초 강제 타임쉴드(POST_SELL_TO_BUY_SHIELD_SEC = 60.0) &
직전 매수 후 60초 타임쉴드 · 60초 경과 후 실시간 현재가 직접 조회 및 순수 현재가 지정가(LIMIT) 매수 발주 ·
매도 1호가(Ask 1) 참조 및 10초 후 상향 추격 정정 100% 영구 소각 및 미체결 단조시계(last_modify_mono) 역전 자가 치유(Case 65) ·
최종 확정 진화 챔피언(🌟 POCKET_ALLIN / 🔥 GRID_L1_ALLIN × 💉 05_RESV_6P_GUARD30 × 🔓 06_STEP2X_15PCT_C20 · 기본값 NONE[OFF] · Case 71 ~ Case 83) :
미동부 프리장 황금시간대(07:00 ~ 07:50 EST & 14봉 이상 확보된 1분봉 Wilder RSI(14) <= 19.0) 도달 시 제어반 선택 모드(POCKET_ALLIN / GRID_L1_ALLIN)에 따른
가용 현금 시드(free_cash_usd) 100% 전액 추가매수 발주 및 독립 골든포켓(golden_pocket) 분리 정산(Case 80) ·
독립 골든포켓 가동 중 그리드 0주/보유 상태에서 불필요한 1.5초 시세 조회 차단(HOLD_ZERO_GRID_CASH_IN_GOLDEN_POCKET / 60s 쉴드 · Case 80) ·
0주 상태 60초 타임쉴드 경과 후 현재가 지정가 실물 1층(REENTRY_1FL) 산입 & 원장 0주·실잔고 시차 발생 시 buckets[0] IndexError 원천 방어 ·
활성 1층 부분 체결(buckets[0].qty < l1_target_quota_qty) 시 체결 수량 비례 자투리 정산 & 신규 1층 주문 정량(ord_q) 고유 보존 &
매수 후 60초 타임쉴드 경과 뒤 매 1.5초 실시간 모니터에서 현재가 <= 1층 단가(buckets[0].book_price) 재도래 시
토스 실계좌 예수금 0.25초 재시도 및 60초 쉴드 방어(422 무한 발주 루프 원천 차단)를 거쳐
미체결 잔량(TOPUP_1FL) 지정가 60초 재대기 발주 및 기존 1층 무승격 원자적 합산(Case 77, Case 78) ·
상단 2층 ~ 7층(GRID_L2 ~ GRID_L7) 보유 중 1층 공석 시 10분 게이트를 기다리지 않고 매 60.0초(1분) 타임쉴드 주기마다
실시간 현재가를 조회하되 현재가 <= 2층 단가(buckets[0].book_price) 상한 가드(HOLD_PREVENT_INVERSION · Case 73) 하에서
직전 익절가 대비 눌림목(-1.00%) OR 상승돌파(+1.00%) 하이브리드 독립 실물 1층(REENTRY_1FL) 즉시 재장전 ·
상승 돌파 매수 시 1회분(8%) 예산 초과 원천 차단을 위한 min(1회분 예산 상한 주수, 기준가 고정 정량) 이중 캡핑(Case 67) ·
활성 1층 보유 중 정적 기억 사이클 최저 매수가(cycle_min_buy_price) 기본 잠금 기반 10분 고정 4단 와이드 활주로 시드보호 매수 게이트(WIDE_RUNWAY :
1~4회 -1.0% / 5~8회 -2.0% / 9~10회 -3.5% / 11회+ -5.5%) 및 STEP2X_15PCT_C20 3중 안전문(2개층 이하 & 가용현금 20.0%+ & 저점대비 2.0배+ 반등 시
활성 1층 대비 -15.0% 스텝업 저가 해금 · Case 76) ·
30% 자투리 1주 승격 방지 가드(GUARD30) & 예수금 API 일시 오류(0.0 반환) 시 재시도 및 허위 시드고갈 알림 차단 &
시드고갈 시 단 1회 입금 요청 알림 영구 래치(waiting_reserve_deposit_alert_sent) & 입금 대기 중 60초 주기 중복 카운터/디스크 쓰기 원천 차단(Case 75, Case 77) &
토스 실계좌 여유자금(1회분 이상) 입금 자동 감지 기반 최대 +6회분 온디맨드 예비시드 자동 수혈(Case 77) ·
체결 시 1~7층 순수 멀티 그리드 승격·자투리 시드 귀속·기정산 주문 ID(last_settled_order_ids) 각인·양방향 인덱싱 보호(Case 69, Case 71 ~ 83)' 코어 플러그인 (Step 03 / 04)
- 제1헌법 ~ 제6헌법 및 Case 01 ~ 83 완벽 준수
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from quant_engine import (
    BASE_MAX_LOTS_8PCT,
    DEFAULT_GOLDEN_ALLIN_MODE,
    GOLDEN_ALLIN_MODES,
    GOLDEN_POCKET_RISE_PCT,
    GOLDEN_RSI_MAX_THRESHOLD,
    GoldenAllInPocket,
    MAX_GRID_TIERS_7,
    MAX_GRID_TIERS_12,
    MAX_RESERVE_PORTIONS,
    MIN_DIP_BUDGET_RATIO,
    MIN_DIP_VS_L1_RATIO,
    PORTION_RATIO_LOCKED,
    ROUND_TRIP_FEE_RATE_PCT,
    buckets_from_dicts,
    buckets_to_dicts,
    compute_golden8_quota_qty,
    compute_upper_2_to_7_moving_avg,
    compute_upper_2_to_12_moving_avg,
    evaluate_golden_allin_signal,
    evaluate_guard30_and_reserve_injection,
    evaluate_l2_only_hybrid_reentry_signal,
    evaluate_step_up_2x_dip_signal,
    get_golden8_prog_thresholds,
    get_golden_allin_mode_label,
    has_active_golden_pocket,
    has_active_l1_bucket,
    pocket_from_dict,
    pocket_to_dict,
    resolve_affordable_buy_qty,
    resolve_allin_affordable_buy_qty,
    summarize_stratum_portfolio,
    vrev_add_quota_lot_and_merge_2tier,
)
from quant_indicators_plugin import (
    evaluate_buy_gate_bucket_status,
    is_active_buy_window,
    is_active_trading_window,
    is_golden_allin_time_window,
    refresh_metrics_with_live_tick,
)
from sniper_exit_plugin import (
    POST_BUY_TO_SELL_SHIELD_SEC,
    POST_SELL_TO_BUY_SHIELD_SEC,
    is_within_post_buy_time_shield,
    is_within_post_sell_time_shield,
)
import toss_api
from toss_api import (
    DEFAULT_INITIAL_SEED_USD,
    EST_TZ,
    LOCKED_BUY_INTERVAL_MIN,
    TARGET_SYMBOL,
    generate_client_order_id,
    safe_float,
    safe_int,
)

logger = logging.getLogger("toss_sniper.sniper_plugin")

# Case 76: 🔓 06_STEP2X_15PCT_C20 스텝업 저가 해금 상수 폴백 바인딩
DEFAULT_UNLOCK_MODE: str = str(
    getattr(toss_api, "DEFAULT_UNLOCK_MODE", "STEP2X_15PCT_C20")
)
STEP_UP_2X_DROP_PCT: float = float(
    getattr(toss_api, "STEP_UP_2X_DROP_PCT", 15.0)
)
STEP_UP_2X_MIN_CASH_RATIO: float = float(
    getattr(toss_api, "STEP_UP_2X_MIN_CASH_RATIO", 0.20)
)
STEP_UP_2X_MIN_REBOUND_MULT: float = float(
    getattr(toss_api, "STEP_UP_2X_MIN_REBOUND_MULT", 2.0)
)
STEP_UP_2X_MAX_TIERS: int = int(
    getattr(toss_api, "STEP_UP_2X_MAX_TIERS", 2)
)

# 순수 현재가 지정가 매수 주문 발주 후 미체결 최대 대기 시간(초) — 상향 추격 정정 없이 60초 미체결 시 안전 취소
BUY_ORDER_MAX_WAIT_SEC: float = 60.0

# Case 61 & Case 69: 매수 또는 매도 FILLED 직후 토스 잔고 API(/api/v1/holdings) 인덱싱 시차(0.1 ~ 0.4초) 보호 그레이스 쉴드(초)
AUTO_FILL_GRACE_SHIELD_SEC: float = 15.0

# Case 73: 상단 2층 ~ 7층 보유 중 1층 공석 시 하이브리드 독립 1층(REENTRY_1FL) 재장전 모니터 주기 타임쉴드(60.0초 = 1분)
REENTRY_MONITOR_TIME_SHIELD_SEC: float = 60.0

# Case 77: 시드고갈 입금 대기(waiting_reserve_deposit == True) 상태에서 토스 계좌 입금 감지 주기 타임쉴드(60.0초 = 1분)
RESERVE_DEPOSIT_CHECK_INTERVAL_SEC: float = 60.0


# ---------------------------------------------------------------------------
# 내부 헬퍼 : 매수·매도 체결 직후 잔고 인덱싱 시차 보호 그레이스 쉴드 & 60초 타임쉴드 각인 (Case 61, 65, 69, 73, 77, 80)
# ---------------------------------------------------------------------------
def mark_auto_fill_grace_shield(
    context: Any,
    symbol: str = TARGET_SYMBOL,
    lot_type: str = "QUOTA_L1",
    fill_price: float = 0.0,
    filled_qty: int = 0,
) -> None:
    """
    🚨 Case 61, Case 65, Case 69, Case 73, Case 77 & Case 80:
    1) 매수(또는 매도) 주문이 거래소에서 FILLED 된 직후 토스 잔고 API(/api/v1/holdings) 인덱싱 시차(0.1 ~ 0.4초) 동안
       잔고 동기화 모듈(reconcile)이 시차를 수동 매매로 오판하지 않도록 15.0초 그레이스 쉴드(last_auto_fill_ts)를 각인한다.
    2) 매수 체결 시에는 last_buy_fill_mono(단조 시계)와 last_buy_fill_ts(Epoch)를 전용 키로 각인하여,
       매수 체결 후 정확히 60.0초(POST_BUY_TO_SELL_SHIELD_SEC) 동안 매도 및 중복 매수가 발사되지 않도록 타임쉴드를 건다!
    3) 그리드 매수 체결로 1층이 채워지면 1층 공석 재장전 모니터 타임쉴드(last_reentry_eval_mono / last_reentry_eval_ts) 및
       예비시드 입금 대기 타임쉴드(last_reserve_check_mono / last_reserve_check_ts)는 0.0 으로 리셋한다.
    """
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    now_mono = time.monotonic()
    now_epoch = time.time()
    tag = str(lot_type or "QUOTA_L1").upper().strip()

    guard_map = getattr(context, "indexing_grace_cache", None)
    if isinstance(guard_map, dict):
        prev = guard_map.get(sym) if isinstance(guard_map.get(sym), dict) else {}
        updated = dict(prev)
        updated["last_auto_fill_ts"] = now_mono
        updated["lot_type"] = tag
        updated["fill_price"] = safe_float(fill_price, 0.0)
        updated["filled_qty"] = safe_int(filled_qty, 0)
        if tag != "SELL_FILL":
            updated["last_buy_fill_mono"] = now_mono
            updated["last_buy_fill_ts"] = now_epoch
            if tag != "GOLDEN_POCKET":
                updated["last_reentry_eval_mono"] = 0.0
                updated["last_reentry_eval_ts"] = 0.0
            updated["last_reserve_check_mono"] = 0.0
            updated["last_reserve_check_ts"] = 0.0
        else:
            updated["last_sell_fill_mono"] = now_mono
            updated["last_sell_fill_ts"] = now_epoch
        guard_map[sym] = updated

    if tag != "SELL_FILL":
        snap_map = getattr(context, "exit_snapshot_cache", None)
        if isinstance(snap_map, dict):
            s_entry = (
                snap_map.get(sym) if isinstance(snap_map.get(sym), dict) else {}
            )
            if tag != "GOLDEN_POCKET":
                s_entry["last_reentry_eval_mono"] = 0.0
                s_entry["last_reentry_eval_ts"] = 0.0
            s_entry["last_reserve_check_mono"] = 0.0
            s_entry["last_reserve_check_ts"] = 0.0
            snap_map[sym] = s_entry


def is_within_auto_fill_grace_shield(
    context: Any, symbol: str = TARGET_SYMBOL
) -> bool:
    """
    🚨 Case 61 & Case 69 [양방향 15.0초 잔고 인덱싱 시차 보호 그레이스 쉴드]:
    최근 15.0초(AUTO_FILL_GRACE_SHIELD_SEC) 이내에 자동 매수 체결 또는 자동 매도 체결(개별 층 익절 / 골든포켓 익절 / 0주 졸업)
    이력이 존재하면 True 를 반환하여, defense_plugin.py 의 reconcile 모듈이 잔고 API 인덱싱 시차로 인해
    유령 추매(h_qty > ledger_qty)나 유령 부분매도(h_qty < ledger_qty) 또는 백업 덮어쓰기를 수행하는 것을 100% 차단한다!
    """
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    now_mono = time.monotonic()

    guard_map = getattr(context, "indexing_grace_cache", None)
    if isinstance(guard_map, dict):
        info = guard_map.get(sym)
        if isinstance(info, dict):
            last_mono = max(
                safe_float(info.get("last_auto_fill_ts"), 0.0),
                safe_float(info.get("last_buy_fill_mono"), 0.0),
                safe_float(info.get("last_sell_fill_mono"), 0.0),
                safe_float(info.get("last_cycle_end_mono"), 0.0),
            )
            if (
                last_mono > 0.0
                and 0.0 <= (now_mono - last_mono) <= AUTO_FILL_GRACE_SHIELD_SEC
            ):
                return True

    snap_map = getattr(context, "exit_snapshot_cache", None)
    if isinstance(snap_map, dict):
        s_info = snap_map.get(sym)
        if isinstance(s_info, dict):
            last_s_mono = max(
                safe_float(s_info.get("last_sell_fill_mono"), 0.0),
                safe_float(s_info.get("last_cycle_end_mono"), 0.0),
            )
            if (
                last_s_mono > 0.0
                and 0.0 <= (now_mono - last_s_mono) <= AUTO_FILL_GRACE_SHIELD_SEC
            ):
                return True

    if hasattr(context, "ledger"):
        try:
            st = context.ledger.get_state(sym)
            last_epoch = max(
                safe_float(st.get("last_buy_fill_ts"), 0.0),
                safe_float(st.get("last_sell_fill_ts"), 0.0),
                safe_float(st.get("last_cycle_end_ts"), 0.0),
            )
            if (
                last_epoch > 0.0
                and 0.0 <= (time.time() - last_epoch) <= AUTO_FILL_GRACE_SHIELD_SEC
            ):
                return True
        except Exception:
            pass

    return False


# ---------------------------------------------------------------------------
# [Case 73 & Case 77] 1층 공석 60초 재장전 타임쉴드 & 시드고갈 60초 입금 감지 타임쉴드 관리기
# ---------------------------------------------------------------------------
def mark_reentry_monitor_60s_cycle_shield(
    context: Any,
    symbol: str = TARGET_SYMBOL,
    eval_price: float = 0.0,
    clear_shield: bool = False,
) -> float:
    """
    🚨 [Case 73 : 1층 공석 60.0초(1분) 타임쉴드 주기 하이브리드 재장전 모니터 재장전기]:
    - 상단 2층 ~ 7층 보유 중 1층이 공석일 때(len(buckets) > 0 and not has_active_l1_bucket(buckets)),
      60.0초 주기 재장전 검문 결과 조건 미달(-1.00% < chg < +1.00%)이거나
      현재가 > 2층 단가로 역전 차단(HOLD_PREVENT_INVERSION)되었을 때, 또는 1층 재장전 지정가 주문이
      60.0초 미체결로 안전 취소된 직후 호출되어 인메모리 캐시(indexing_grace_cache 및 exit_snapshot_cache)에
      last_reentry_eval_mono 와 last_reentry_eval_ts 를 기록하고 현재 Epoch 시각을 반환한다.
    - 1층 재장전이 체결되어 활성 1층이 채워지거나 0주 졸업 시에는 clear_shield=True 로 호출하여 0.0 으로 리셋한다.
    """
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    now_mono = 0.0 if clear_shield else time.monotonic()
    now_epoch = 0.0 if clear_shield else time.time()

    guard_map = getattr(context, "indexing_grace_cache", None)
    if isinstance(guard_map, dict):
        g_entry = (
            guard_map.get(sym) if isinstance(guard_map.get(sym), dict) else {}
        )
        g_entry["last_reentry_eval_mono"] = now_mono
        g_entry["last_reentry_eval_ts"] = now_epoch
        if eval_price > 0.0:
            g_entry["last_reentry_eval_price"] = round(
                safe_float(eval_price, 0.0), 4
            )
        guard_map[sym] = g_entry

    snap_map = getattr(context, "exit_snapshot_cache", None)
    if isinstance(snap_map, dict):
        s_entry = (
            snap_map.get(sym) if isinstance(snap_map.get(sym), dict) else {}
        )
        s_entry["last_reentry_eval_mono"] = now_mono
        s_entry["last_reentry_eval_ts"] = now_epoch
        if eval_price > 0.0:
            s_entry["last_reentry_eval_price"] = round(
                safe_float(eval_price, 0.0), 4
            )
        snap_map[sym] = s_entry

    return now_epoch


def is_within_reentry_monitor_time_shield(
    context: Any,
    st: Optional[Dict[str, Any]] = None,
    symbol: str = TARGET_SYMBOL,
) -> Tuple[bool, float]:
    """
    🚨 [Case 73 : 1층 공석 60.0초(1분) 주기 재장전 모니터 타임쉴드 작동 여부 판별]:
    1) 먼저 직전 매도 체결 후 60.0초 타임쉴드(is_within_post_sell_time_shield) 및
       직전 매수 체결 후 60.0초 타임쉴드(is_within_post_buy_time_shield)를 확인한다.
    2) 이후 1층 공석 상태에서 직전 60.0초 재장전 모니터 검문 시각(last_reentry_eval_mono / last_reentry_eval_ts)으로부터
       60.0초(REENTRY_MONITOR_TIME_SHIELD_SEC = 60.0)가 경과하지 않았으면 True 와 잔여 초(remain_sec)를 반환한다.
    """
    in_post_sell, rem_sell = is_within_post_sell_time_shield(
        context, st, symbol
    )
    if in_post_sell:
        return True, rem_sell

    in_post_buy, rem_buy = is_within_post_buy_time_shield(context, st, symbol)
    if in_post_buy:
        return True, rem_buy

    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    now_mono = time.monotonic()

    guard_map = getattr(context, "indexing_grace_cache", None)
    if isinstance(guard_map, dict):
        g_entry = guard_map.get(sym)
        if isinstance(g_entry, dict):
            re_mono = safe_float(g_entry.get("last_reentry_eval_mono"), 0.0)
            if re_mono > 0.0:
                elapsed_g = now_mono - re_mono
                if 0.0 <= elapsed_g < REENTRY_MONITOR_TIME_SHIELD_SEC:
                    return True, round(
                        REENTRY_MONITOR_TIME_SHIELD_SEC - elapsed_g, 1
                    )

    snap_map = getattr(context, "exit_snapshot_cache", None)
    if isinstance(snap_map, dict):
        s_entry = snap_map.get(sym)
        if isinstance(s_entry, dict):
            s_re_mono = safe_float(s_entry.get("last_reentry_eval_mono"), 0.0)
            if s_re_mono > 0.0:
                elapsed_s = now_mono - s_re_mono
                if 0.0 <= elapsed_s < REENTRY_MONITOR_TIME_SHIELD_SEC:
                    return True, round(
                        REENTRY_MONITOR_TIME_SHIELD_SEC - elapsed_s, 1
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
    re_epoch = safe_float(state_obj.get("last_reentry_eval_ts"), 0.0)
    if re_epoch > 0.0:
        elapsed_epoch = time.time() - re_epoch
        if 0.0 <= elapsed_epoch < REENTRY_MONITOR_TIME_SHIELD_SEC:
            return True, round(REENTRY_MONITOR_TIME_SHIELD_SEC - elapsed_epoch, 1)

    return False, 0.0


def mark_reserve_deposit_check_shield(
    context: Any,
    symbol: str = TARGET_SYMBOL,
    clear_shield: bool = False,
) -> float:
    """
    # [Case 77 & Case 80 : 시드고갈 입금 대기 또는 골든포켓 현금 가동 중 60.0초 주기 확인 타임쉴드 기록기]:
    시드고갈(GUARD30) 또는 골든포켓 전액 투입으로 일반 매수가 보류된 상태에서
    매 1.5초마다 /api/v1/buying-power 나 시세를 과도하게 호출하지 않고
    정확히 60.0초(1분) 주기로 확인하도록 타임쉴드를 기록한다.
    """
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    now_mono = 0.0 if clear_shield else time.monotonic()
    now_epoch = 0.0 if clear_shield else time.time()

    guard_map = getattr(context, "indexing_grace_cache", None)
    if isinstance(guard_map, dict):
        g_entry = (
            guard_map.get(sym) if isinstance(guard_map.get(sym), dict) else {}
        )
        g_entry["last_reserve_check_mono"] = now_mono
        g_entry["last_reserve_check_ts"] = now_epoch
        guard_map[sym] = g_entry

    snap_map = getattr(context, "exit_snapshot_cache", None)
    if isinstance(snap_map, dict):
        s_entry = (
            snap_map.get(sym) if isinstance(snap_map.get(sym), dict) else {}
        )
        s_entry["last_reserve_check_mono"] = now_mono
        s_entry["last_reserve_check_ts"] = now_epoch
        snap_map[sym] = s_entry

    return now_epoch


def is_within_reserve_deposit_check_shield(
    context: Any,
    st: Optional[Dict[str, Any]] = None,
    symbol: str = TARGET_SYMBOL,
) -> Tuple[bool, float]:
    """
    # [Case 77 & Case 80 : 시드고갈 입금 대기 중 60.0초 타임쉴드 판별기]:
    직전 예비시드 입금(또는 골든포켓 현금 대기) 확인 시각(last_reserve_check_mono / last_reserve_check_ts)으로부터
    60.0초(RESERVE_DEPOSIT_CHECK_INTERVAL_SEC)가 경과하지 않았으면 True 와 잔여 초를 반환한다.
    """
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    now_mono = time.monotonic()

    guard_map = getattr(context, "indexing_grace_cache", None)
    if isinstance(guard_map, dict):
        g_entry = guard_map.get(sym)
        if isinstance(g_entry, dict):
            rc_mono = safe_float(g_entry.get("last_reserve_check_mono"), 0.0)
            if rc_mono > 0.0:
                elapsed_g = now_mono - rc_mono
                if 0.0 <= elapsed_g < RESERVE_DEPOSIT_CHECK_INTERVAL_SEC:
                    return True, round(
                        RESERVE_DEPOSIT_CHECK_INTERVAL_SEC - elapsed_g, 1
                    )

    snap_map = getattr(context, "exit_snapshot_cache", None)
    if isinstance(snap_map, dict):
        s_entry = snap_map.get(sym)
        if isinstance(s_entry, dict):
            s_rc_mono = safe_float(s_entry.get("last_reserve_check_mono"), 0.0)
            if s_rc_mono > 0.0:
                elapsed_s = now_mono - s_rc_mono
                if 0.0 <= elapsed_s < RESERVE_DEPOSIT_CHECK_INTERVAL_SEC:
                    return True, round(
                        RESERVE_DEPOSIT_CHECK_INTERVAL_SEC - elapsed_s, 1
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
    rc_epoch = safe_float(state_obj.get("last_reserve_check_ts"), 0.0)
    if rc_epoch > 0.0:
        elapsed_epoch = time.time() - rc_epoch
        if 0.0 <= elapsed_epoch < RESERVE_DEPOSIT_CHECK_INTERVAL_SEC:
            return True, round(
                RESERVE_DEPOSIT_CHECK_INTERVAL_SEC - elapsed_epoch, 1
            )

    return False, 0.0


def _get_live_soxl_price(
    context: Any,
    prices: Dict[str, float],
    holdings: Dict[str, Dict[str, Any]],
    now_est: datetime,
) -> float:
    """
    실시간 가격 딕셔너리(prices) -> 캔들 캐시 -> 보유 잔고 현재가 순으로 SOXL 현재가를 추출한다.
    """
    lp = safe_float((prices or {}).get(TARGET_SYMBOL), 0.0)
    if lp > 0.0:
        return lp
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
    🚨 Case 65, Case 73 & Case 80:
    60초 타임쉴드가 경과한 뒤 매수 조건 판정 및 지정가 주문 발주 직전에
    토스 Open API(/api/v1/prices)를 직접 호출하여 가장 최신의 실시간 현재가를 조회한다.
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
        logger.debug("매수 직전 실시간 현재가 재조회 폴백 사용: %s", exc)
    return safe_float(fallback_price, 0.0)


# ---------------------------------------------------------------------------
# [핵심 0-B · Case 75, Case 77 & Case 80] GUARD30 자투리 차단 · 예수금 API 일시 오류 방어 · 토스 계좌 여유자금 감지 자동 수혈 · 단 1회 입금 요청 알림 실행기
# ---------------------------------------------------------------------------
async def _check_and_execute_guard30_or_reserve_injection(
    context: Any,
    st_now: Dict[str, Any],
    exec_order_p: float,
    portion_budget: float,
    l1_actual_cost_usd: float,
    is_dip_promotion: bool,
    is_vacant_l1_reentry: bool,
    trigger_desc: str,
) -> Tuple[bool, float, float, Dict[str, Any]]:
    """
    🚨 [Case 75, Case 77 & Case 80 : 💉 05_RESV_6P_GUARD30 실행 엔진]:
    매수 주문 발주 직전(뮤텍스 내부)에 호출되어:
    0) [Case 80 골든포켓 일시 가동 중 오발동 방어 및 60초 인메모리 쉴드]:
       만약 현재 독립 골든포켓(golden_pocket.qty > 0)에 가용 현금 100%가 일시 투입되어 있어
       now_free_cash 가 부족한 상태라면, 이는 시드 고갈이 아니라 골든포켓(+1.50% 익절 대기) 가동 상태이므로
       예비시드 수혈이나 입금 요청 알림을 발송하지 않고 60초 인메모리 쉴드(mark_reserve_deposit_check_shield)를
       작동시킨 뒤 조용히 대기(HOLD_CASH_DEPLOYED_IN_GOLDEN_POCKET)한다!
    1) 토스 실계좌 주문가능 달러(`raw_bp_usd = await context.api.get_buying_power_usd(safety_buffer_pct=0.0)`)를 조회하되,
       원장 가용현금이 충분함에도(`now_free_cash >= est_min_req`) 일시 네트워크 타임아웃으로 `0.0` 이 반환되면
       `0.25초` 후 1회 재시도하고, 여전히 `0.0` 이면 허위 시드고갈 알림 발송이나 영구 래치 잠금 없이
       해당 틱만 조용히 보류(`HOLD_TRANSIENT_BP_API_ERROR`)한다!
    2) `evaluate_guard30_and_reserve_injection()` 으로 30% 자투리 가드(`min_req_cash`) 통과 여부 및
       토스 계좌 미할당 여유 입금액(`raw_bp_usd - free_cash_usd`) 기반 예비시드 수혈 가능 여부를 판정한다.
    3) [PROCEED_NORMAL] / [INJECT_AND_PROCEED] / [BLOCK_AND_ALERT_DEPOSIT] 분기 처리:
       - MODIFIED [Case 75 & Case 77]: 이미 `waiting_reserve_deposit == True` 및 `waiting_reserve_deposit_alert_sent == True` 로
         진입해 있는 상태에서 60초 주기 재확인 시 미입금이 지속될 때는 인메모리 60초 쉴드만 재장전하고
         카운터(`dust_guard_blocked_cnt`, `daily_seed_protect_pass_cnt`) 중복 증가 및 원장 디스크 쓰기를 스킵한다!
    """
    now_free_cash = max(0.0, safe_float(st_now.get("free_cash_usd"), 0.0))
    cur_used_res = max(0, safe_int(st_now.get("used_reserve_portions_cnt"), 0))
    cur_inj_usd = max(0.0, safe_float(st_now.get("injected_reserve_usd"), 0.0))

    # MODIFIED [Case 80]: 독립 골든포켓(golden_pocket)이 보유 중이어서 현금이 골든포켓에 가동 중일 때
    # 일반 그리드 매수 시도로 인해 시드고갈 알림이나 예비시드 수혈이 오발동하는 현상을 차단하고 60초 인메모리 쉴드로 API 스팸을 방지!
    gp_now = pocket_from_dict(st_now.get("golden_pocket"))
    fee_mult = 1.0 + (ROUND_TRIP_FEE_RATE_PCT / 100.0)
    est_min_req = max(
        exec_order_p * fee_mult,
        portion_budget * MIN_DIP_BUDGET_RATIO,
        (l1_actual_cost_usd * MIN_DIP_VS_L1_RATIO if is_dip_promotion else 0.0),
    )
    if gp_now.is_active and now_free_cash < est_min_req:
        mark_reserve_deposit_check_shield(
            context=context, symbol=TARGET_SYMBOL, clear_shield=False
        )
        if is_vacant_l1_reentry:
            mark_reentry_monitor_60s_cycle_shield(
                context=context, symbol=TARGET_SYMBOL, eval_price=exec_order_p
            )
        return (
            False,
            now_free_cash,
            0.0,
            {
                "action": "HOLD_CASH_DEPLOYED_IN_GOLDEN_POCKET",
                "should_proceed": False,
                "golden_pocket_qty": gp_now.qty,
                "golden_pocket_cost_usd": gp_now.actual_cost_usd,
            },
        )

    raw_bp_usd = await context.api.get_buying_power_usd(safety_buffer_pct=0.0)
    # MODIFIED [Case 77 예수금 API 일시 오류(0.0 반환) 시 허위 시드고갈 알림 원천 차단]:
    # 원장 가용현금이 충분한데(now_free_cash >= est_min_req) 브로커 API가 0.0을 반환했다면 0.25초 후 1회 재시도한다.
    if raw_bp_usd <= 0.0 and now_free_cash >= est_min_req:
        await asyncio.sleep(0.25)
        raw_bp_usd = await context.api.get_buying_power_usd(
            safety_buffer_pct=0.0
        )
        if raw_bp_usd <= 0.0:
            logger.debug(
                "🛡️ [Case 77 예수금 API 일시 조회 지연 방어] 원장 가용현금($%.2f >= 최소 $%.2f) 정상이나 예수금 API가 0.0을 반환하여 허위 시드고갈 알림 없이 다음 루프 재시도",
                now_free_cash,
                est_min_req,
            )
            return (
                False,
                now_free_cash,
                0.0,
                {
                    "action": "HOLD_TRANSIENT_BP_API_ERROR",
                    "should_proceed": False,
                    "free_cash_usd": now_free_cash,
                    "min_req_cash": round(est_min_req, 4),
                },
            )

    eff_bp_for_eval: Optional[float] = (
        raw_bp_usd if raw_bp_usd > 0.0 else 0.0
    )

    guard_eval = evaluate_guard30_and_reserve_injection(
        free_cash_usd=now_free_cash,
        broker_bp_usd=eff_bp_for_eval,
        exec_price=exec_order_p,
        portion_budget=portion_budget,
        l1_actual_cost_usd=l1_actual_cost_usd,
        is_dip_promotion=is_dip_promotion,
        used_reserve_portions_cnt=cur_used_res,
        max_reserve_portions=MAX_RESERVE_PORTIONS,
    )
    action = str(guard_eval.get("action") or "BLOCK_AND_ALERT_DEPOSIT")
    eff_bp_for_order = round(raw_bp_usd * 0.998, 4) if raw_bp_usd > 0.0 else 0.0

    # [케이스 1] 현재 가용현금 및 실계좌 예수금이 충분한 경우 -> 정상 매수 진행
    if action == "PROCEED_NORMAL":
        if bool(st_now.get("waiting_reserve_deposit")) or bool(
            st_now.get("waiting_reserve_deposit_alert_sent")
        ):
            mark_reserve_deposit_check_shield(
                context, TARGET_SYMBOL, clear_shield=True
            )
            await context.ledger.update_state(
                TARGET_SYMBOL,
                waiting_reserve_deposit=False,
                waiting_reserve_deposit_alert_sent=False,
                required_reserve_deposit_usd=0.0,
                last_reserve_check_ts=0.0,
            )
        return True, now_free_cash, eff_bp_for_order, guard_eval

    # [케이스 2] 토스 계좌에 1회분 이상 여유자금이 입금되어 있어 온디맨드 예비시드 자동 수혈 실행!
    if action == "INJECT_AND_PROCEED":
        inj_portions = max(1, safe_int(guard_eval.get("inject_portions"), 1))
        inj_usd = round(max(0.01, safe_float(guard_eval.get("inject_usd"), 0.0)), 4)
        new_used_cnt = min(MAX_RESERVE_PORTIONS, cur_used_res + inj_portions)
        new_inj_usd = round(cur_inj_usd + inj_usd, 4)
        new_tot_inj_cnt = (
            safe_int(st_now.get("total_reserve_injected_cnt"), 0) + inj_portions
        )
        new_day_inj_cnt = (
            safe_int(st_now.get("daily_reserve_injected_cnt"), 0) + inj_portions
        )
        rem_after = max(0, MAX_RESERVE_PORTIONS - new_used_cnt)

        mark_reserve_deposit_check_shield(
            context, TARGET_SYMBOL, clear_shield=True
        )
        updated_st = await context.ledger.update_state(
            TARGET_SYMBOL,
            used_reserve_portions_cnt=new_used_cnt,
            injected_reserve_usd=new_inj_usd,
            total_reserve_injected_cnt=new_tot_inj_cnt,
            daily_reserve_injected_cnt=new_day_inj_cnt,
            waiting_reserve_deposit=False,
            waiting_reserve_deposit_alert_sent=False,
            required_reserve_deposit_usd=0.0,
            last_reserve_check_ts=0.0,
        )
        updated_free_cash = max(
            0.0,
            safe_float(updated_st.get("free_cash_usd"), now_free_cash + inj_usd),
        )
        logger.info(
            "💉 [Case 77 SOXL 온디맨드 예비시드 자동 수혈 완료] +%d회분(+%.2f$) 수혈 -> 가용현금 $%.2f (사용 %d/%d회분 · 잔여한도 %d회분 · 타점=%s)",
            inj_portions,
            inj_usd,
            updated_free_cash,
            new_used_cnt,
            MAX_RESERVE_PORTIONS,
            rem_after,
            trigger_desc,
        )
        if hasattr(context, "send_slim_alert"):
            await context.send_slim_alert(
                title=f"💉 [SOXL 예비시드 자동 수혈 (+{inj_portions}회분 · +${inj_usd:,.2f})]",
                body=(
                    f"시드고갈(30% 가드) 감지 즉시 토스 계좌 여유자금에서 +{inj_portions}회분(${inj_usd:,.2f}) 자동 수혈 완료! · "
                    f"수혈 후 가용현금 ${updated_free_cash:,.2f} · "
                    f"예비시드 사용 {new_used_cnt}/{MAX_RESERVE_PORTIONS}회분(잔여 {rem_after}회분 · 누적수혈 ${new_inj_usd:,.2f} / 0주 졸업 시 자동 상환) · "
                    f"즉시 {trigger_desc} 정량 매수를 집행합니다!"
                ),
            )
        return True, updated_free_cash, eff_bp_for_order, guard_eval

    # [케이스 3] 계좌 미입금 또는 6회분 한도 소진 -> 자투리 1주 매수 차단 & 단 1회 입금 요청 알림(영구 래치)
    already_waiting_dep = bool(st_now.get("waiting_reserve_deposit", False))
    alert_already_sent = bool(
        st_now.get("waiting_reserve_deposit_alert_sent", False)
    )
    rec_dep_usd = round(
        max(
            portion_budget,
            safe_float(guard_eval.get("recommended_deposit_usd"), portion_budget),
        ),
        2,
    )
    min_req_c = safe_float(guard_eval.get("min_req_cash"), portion_budget * 0.30)
    rem_portions = safe_int(guard_eval.get("rem_portions_before"), 0)
    needed_p = max(1, safe_int(guard_eval.get("needed_portions"), 1))

    now_rc_epoch = mark_reserve_deposit_check_shield(
        context, TARGET_SYMBOL, clear_shield=False
    )
    re_epoch = safe_float(st_now.get("last_reentry_eval_ts"), 0.0)
    if is_vacant_l1_reentry:
        re_epoch = mark_reentry_monitor_60s_cycle_shield(
            context=context, symbol=TARGET_SYMBOL, eval_price=exec_order_p
        )

    # MODIFIED [Case 75 & Case 77 : 이미 시드고갈 입금 대기 상태이고 1회 알림도 발송 완료된 경우 중복 카운터 증가 및 매 60초 os.fsync 디스크 쓰기 스킵!]
    if already_waiting_dep and alert_already_sent:
        prev_req_dep = safe_float(
            st_now.get("required_reserve_deposit_usd"), 0.0
        )
        if abs(prev_req_dep - rec_dep_usd) >= 1.0:
            await context.ledger.update_state(
                TARGET_SYMBOL,
                required_reserve_deposit_usd=rec_dep_usd,
            )
        return False, now_free_cash, eff_bp_for_order, guard_eval

    is_dust_blk = bool(guard_eval.get("is_dust_blocked", False))
    dust_inc = 1 if is_dust_blk else 0
    new_dust_cnt = safe_int(st_now.get("dust_guard_blocked_cnt"), 0) + dust_inc
    new_day_dust_cnt = (
        safe_int(st_now.get("daily_dust_guard_blocked_cnt"), 0) + dust_inc
    )
    new_pass_cnt = safe_int(st_now.get("seed_protect_pass_cnt"), 0) + 1
    new_day_pass = safe_int(st_now.get("daily_seed_protect_pass_cnt"), 0) + 1

    await context.ledger.update_state(
        TARGET_SYMBOL,
        waiting_reserve_deposit=True,
        waiting_reserve_deposit_alert_sent=True,
        required_reserve_deposit_usd=rec_dep_usd,
        last_reserve_check_ts=now_rc_epoch,
        last_reentry_eval_ts=re_epoch,
        dust_guard_blocked_cnt=new_dust_cnt,
        daily_dust_guard_blocked_cnt=new_day_dust_cnt,
        seed_protect_pass_cnt=new_pass_cnt,
        daily_seed_protect_pass_cnt=new_day_pass,
    )

    # 🚨 [스팸 원천 차단 안전망]: waiting_reserve_deposit_alert_sent 가 False 였을 때만 단 1회 발송!
    if not alert_already_sent and hasattr(context, "send_slim_alert"):
        if rem_portions >= needed_p:
            title_msg = (
                f"🚨 [💉 SOXL 시드고갈 감지 · 예비시드 {needed_p}회분(${rec_dep_usd:,.2f}) 입금 요청]"
            )
            body_msg = (
                f"타점({trigger_desc} @ ${exec_order_p:.2f}) 도달 · "
                f"현재 가용현금(${now_free_cash:,.2f}) 및 토스 주문가능금액(${raw_bp_usd:,.2f})이 "
                f"30% 자투리 승격 방지 가드(${min_req_cash_str(min_req_c)}) 미만이어서 자투리 매수를 차단했습니다. · "
                f"토스 달러 계좌에 1회분 이상(권장 ${rec_dep_usd:,.2f} · 잔여 예비한도 {rem_portions}/{MAX_RESERVE_PORTIONS}회분) 입금해 주시면 "
                f"60초 내 자동 감지하여 즉시 수혈 매수합니다! (※ 스팸 방지를 위해 입금 요청 알림은 1회만 발송됩니다)"
            )
        else:
            title_msg = (
                "🚨 [🛑 SOXL 시드고갈 및 예비시드 6회분 한도 소진 안내]"
            )
            body_msg = (
                f"타점({trigger_desc} @ ${exec_order_p:.2f}) 도달했으나 "
                f"가용현금(${now_free_cash:,.2f})이 30% 가드(${min_req_cash_str(min_req_c)}) 미만이고 "
                f"온디맨드 예비시드 한도({MAX_RESERVE_PORTIONS}/{MAX_RESERVE_PORTIONS}회분)를 모두 사용하여 추매를 보류하고 반등 익절을 대기합니다. "
                f"(※ 스팸 방지를 위해 본 알림은 1회만 발송됩니다)"
            )
        await context.send_slim_alert(title=title_msg, body=body_msg)
        logger.warning(
            "🚨 [Case 77 시드고갈 단 1회 입금 요청 알림 발송 완료 & 래치 잠금] 가용=$%.2f · 토스예수금=$%.2f · 30%%가드=$%.2f · 권장입금=$%.2f · 잔여한도=%d/%d회분",
            now_free_cash,
            raw_bp_usd,
            min_req_c,
            rec_dep_usd,
            rem_portions,
            MAX_RESERVE_PORTIONS,
        )

    return False, now_free_cash, eff_bp_for_order, guard_eval


def min_req_cash_str(val: float) -> str:
    return f"{safe_float(val, 0.0):,.2f}"


# ---------------------------------------------------------------------------
# [핵심 1] 매수 체결(FILLED) 커밋 · 비례 자투리 정산(Case 78) · 독립 골든포켓/1~7층 순수 그리드 배치(Case 80) · 매수 후 60초 타임쉴드 각인
# ---------------------------------------------------------------------------
async def _commit_filled_buy_to_stratum_ledger(
    context: Any,
    filled_qty: int,
    avg_fill_price: float,
    portion_budget: float,
    lot_type: str,
    settled_order_id: str = "",
    ordered_qty: Optional[int] = None,
) -> Dict[str, Any]:
    """
    🎯 1, 🎯 3, 🎯 4 & Case 25, 46, 53, 59, 60, 61, 65, 67, 69, 71, 72, 73, 74, 76, 77, 78, 80:
    매수 주문 체결(FILLED 또는 부분 체결 후 60초 타임아웃 종료)이 확인된 즉시:
    0) 🚨 [Case 80 : POCKET_ALLIN 모드 독립 골든포켓(lot_type == "GOLDEN_POCKET") 체결 분리 정산]:
       - 기존 1층 ~ 7층 그리드(old_buckets), anchor_price, cycle_min_buy_price, l1_target_quota_qty 를
         전혀 변경하거나 승격시키지 않고 원장의 golden_pocket 에 순수 원가로 독립 기록한다!
       - 자투리 절약금은 0.0 으로 처리하여 허위 자투리 누적을 방지하고,
         매수 후 60.0초 타임쉴드 및 15.0초 인덱싱 그레이스 쉴드를 각인한 뒤 +1.50% 독립 익절 타점을 감시한다.
    1) 🚨 [Case 78 부분 체결 시 체결 수량 비례 예산 자투리 정산 (GOLDEN_L1 전액매수는 자투리 0.0 처리)]:
       - 일반 8% 정량 매수 시 전량 체결이면 eff_portion_budget = raw_portion_budget 으로 산출하고,
         부분 체결(q_int < ord_q)이면 체결 수량 비례 예산 대비 절약액만 자투리로 정산한다.
    2) vrev_add_quota_lot_and_merge_2tier() 를 호출하여 1~7층 그리드 배치/승격/합산을 수행한다.
    """
    st = context.ledger.get_state(TARGET_SYMBOL)
    old_buckets = buckets_from_dicts(st.get("buckets", []))
    old_gp = pocket_from_dict(st.get("golden_pocket"))
    today_est_str = datetime.now(EST_TZ).strftime("%Y-%m-%d")

    q_int = max(1, safe_int(filled_qty, 1))
    ord_q = max(
        q_int,
        safe_int(
            ordered_qty
            if ordered_qty is not None
            else st.get("ordered_qty"),
            q_int,
        ),
    )
    fill_p = round(max(0.01, safe_float(avg_fill_price, 0.01)), 4)
    actual_spent = round(float(q_int) * fill_p, 4)
    tag = str(lot_type or "QUOTA_L1").upper().strip()
    eff_oid = str(settled_order_id or st.get("buy_order_id") or "").strip()

    settled_oids: List[str] = list(st.get("last_settled_order_ids") or [])
    if eff_oid and eff_oid not in settled_oids:
        settled_oids.append(eff_oid)
    settled_oids = settled_oids[-50:]

    now_buy_epoch = time.time()

    # -----------------------------------------------------------------------
    # [Case 80 분기 : 독립 골든포켓(lot_type == "GOLDEN_POCKET") 체결 커밋]
    # -> 기존 1~7층 그리드(old_buckets) 및 기억저가를 전혀 건드리지 않고 golden_pocket 에만 독립 기록!
    # -----------------------------------------------------------------------
    if tag == "GOLDEN_POCKET":
        if old_gp.is_active:
            comb_gp_q = old_gp.qty + q_int
            comb_gp_cost = round(old_gp.actual_cost_usd + actual_spent, 4)
            comb_gp_p = round(comb_gp_cost / float(comb_gp_q), 4)
            new_gp = GoldenAllInPocket(
                qty=comb_gp_q,
                book_price=comb_gp_p,
                book_invested_usd=comb_gp_cost,
                actual_cost_usd=comb_gp_cost,
                entry_ts=now_buy_epoch,
                order_date=today_est_str,
            )
        else:
            new_gp = GoldenAllInPocket(
                qty=q_int,
                book_price=fill_p,
                book_invested_usd=actual_spent,
                actual_cost_usd=actual_spent,
                entry_ts=now_buy_epoch,
                order_date=today_est_str,
            )

        tot_buy_ev = safe_int(st.get("total_buy_events"), 0) + 1
        tot_buy_sh = safe_int(st.get("total_buy_shares"), 0) + q_int
        day_buy_ev = safe_int(st.get("daily_buy_events"), 0) + 1
        g_buy_ev = safe_int(st.get("golden_allin_buy_events"), 0) + 1
        day_g_buy_ev = safe_int(st.get("daily_golden_allin_buy_events"), 0) + 1

        mark_auto_fill_grace_shield(
            context=context,
            symbol=TARGET_SYMBOL,
            lot_type="GOLDEN_POCKET",
            fill_price=fill_p,
            filled_qty=q_int,
        )
        mark_reserve_deposit_check_shield(
            context=context,
            symbol=TARGET_SYMBOL,
            clear_shield=True,
        )

        updated_st = await context.ledger.update_state(
            TARGET_SYMBOL,
            golden_pocket=new_gp.to_dict(),
            last_golden_allin_date=today_est_str,
            buy_order_id="",
            ordered_qty=0,
            buy_price=0.0,
            pending_portion_budget=0.0,
            pending_lot_type="",
            pending_step_up_min_price=0.0,
            waiting_reserve_deposit=False,
            waiting_reserve_deposit_alert_sent=False,
            required_reserve_deposit_usd=0.0,
            last_reserve_check_ts=0.0,
            last_settled_order_ids=settled_oids,
            total_buy_events=tot_buy_ev,
            total_buy_shares=tot_buy_sh,
            daily_buy_events=day_buy_ev,
            golden_allin_buy_events=g_buy_ev,
            daily_golden_allin_buy_events=day_g_buy_ev,
            last_buy_fill_ts=now_buy_epoch,
        )
        context.wakeup_event.set()
        free_cash_now = safe_float(updated_st.get("free_cash_usd"), 0.0)
        gp_target_p = new_gp.target_sell_price(rise_pct=GOLDEN_POCKET_RISE_PCT)
        grid_sh = sum(b.qty for b in old_buckets)

        if hasattr(context, "send_slim_alert"):
            await context.send_slim_alert(
                title=(
                    f"🌟 [SOXL 황금시간 독립 골든포켓 100% 전액매수 체결] "
                    f"{q_int}주 @ ${fill_p:.2f}"
                ),
                body=(
                    f"실사용 ${actual_spent:,.2f} · "
                    f"🛡️60초 타임쉴드 후 골든포켓 단독 익절목표 ${gp_target_p:.2f}(+1.5%) ⚡1.5초 실시간 감시! · "
                    f"기존 그리드({len(old_buckets)}개층·{grid_sh}주) 원가·회차·기억저가 100% 비오염 보존 · "
                    f"잔여 가용현금 ${free_cash_now:,.2f}"
                ),
            )
        return {
            "status": "GOLDEN_POCKET_FILLED",
            "symbol": TARGET_SYMBOL,
            "lot_type": "GOLDEN_POCKET",
            "filled_qty": q_int,
            "ordered_qty": ord_q,
            "fill_price": fill_p,
            "actual_spent_usd": actual_spent,
            "golden_pocket_target_price": gp_target_p,
            "free_cash_usd": free_cash_now,
        }

    # -----------------------------------------------------------------------
    # [일반 8% 정량 매수(REENTRY_1FL / TOPUP_1FL / DIP_1FL) 및 GRID_L1_ALLIN(GOLDEN_L1) 커밋]
    # -----------------------------------------------------------------------
    raw_portion_budget = safe_float(portion_budget, 0.0)
    if tag == "GOLDEN_L1" or raw_portion_budget <= 0.0:
        eff_portion_budget = actual_spent
        saved_from_portion = 0.0
    elif q_int < ord_q and ord_q > 0:
        eff_portion_budget = round(
            raw_portion_budget * (float(q_int) / float(ord_q)), 4
        )
        saved_from_portion = round(
            max(0.0, eff_portion_budget - actual_spent), 4
        )
    else:
        eff_portion_budget = raw_portion_budget
        saved_from_portion = round(
            max(0.0, eff_portion_budget - actual_spent), 4
        )

    was_empty = len(old_buckets) == 0
    was_l2_only = bool(
        len(old_buckets) > 0 and not has_active_l1_bucket(old_buckets)
    )
    prev_l1_p = (
        old_buckets[0].book_price
        if (old_buckets and has_active_l1_bucket(old_buckets))
        else 0.0
    )

    new_buckets = vrev_add_quota_lot_and_merge_2tier(
        queue=old_buckets,
        buy_qty=q_int,
        buy_price=fill_p,
        actual_spent_usd=actual_spent,
        lot_type=tag,
        max_tiers=MAX_GRID_TIERS_7,
    )

    # MODIFIED [Case 67, Case 78 & Case 80 : 1층 목표 정량(l1_target_quota_qty) 보존 및 이전 층 수량 오염 차단]
    # - GOLDEN_L1 은 가용현금 100% 전액 주문이므로 부분 체결 시에도 잔량 추격(TOPUP_1FL) 없이 기체결 수량을 목표 정량으로 확정한다.
    # - TOPUP_1FL 은 기존 1층 목표 정량(raw_target_q)을 그대로 승계한다.
    # - 신규 1층 생성(REENTRY_1FL / DIP_1FL / QUOTA_L1) 시에는 이전 1층의 잔재(raw_target_q)가 아닌
    #   이번 주문의 발주 정량(ord_q)만을 목표 정량으로 고정하여 1회분(8%) 예산 초과를 원천 차단한다!
    raw_target_q = max(0, safe_int(st.get("l1_target_quota_qty"), 0))
    cur_l1_qty = new_buckets[0].qty if new_buckets else q_int
    if tag == "GOLDEN_L1":
        next_l1_target_q = cur_l1_qty
    elif tag == "TOPUP_1FL":
        next_l1_target_q = max(cur_l1_qty, raw_target_q)
    else:
        next_l1_target_q = max(cur_l1_qty, ord_q)
    rem_after_fill = max(0, next_l1_target_q - cur_l1_qty)

    # 🚨 Case 60, Case 72 & Case 76: 정적 기억 최저가 잠금 및 STEP2X_15PCT_C20 스텝업 해금 갱신!
    old_min_p = safe_float(st.get("cycle_min_buy_price"), 0.0)
    pending_step_up_p = safe_float(st.get("pending_step_up_min_price"), 0.0)
    is_step_up_unlock_fill = False

    if was_empty or old_min_p <= 0.0:
        new_cycle_min_p = fill_p
    elif pending_step_up_p > 0.0 and tag not in (
        "REENTRY_1FL",
        "TOPUP_1FL",
        "GOLDEN_L1",
    ):
        new_cycle_min_p = round(min(pending_step_up_p, fill_p), 4)
        is_step_up_unlock_fill = True
    else:
        new_cycle_min_p = round(min(old_min_p, fill_p), 4)

    new_held_lots = sum(b.lot_count for b in new_buckets)
    new_held_shares = sum(b.qty for b in new_buckets)
    new_held_tiers = len(new_buckets)

    tot_buy_ev = safe_int(st.get("total_buy_events"), 0) + 1
    tot_buy_sh = safe_int(st.get("total_buy_shares"), 0) + q_int
    day_buy_ev = safe_int(st.get("daily_buy_events"), 0) + 1
    unlock_inc = 1 if is_step_up_unlock_fill else 0
    cond_unlock_ev = safe_int(st.get("cond_unlock_buy_events"), 0) + unlock_inc
    day_unlock_ev = safe_int(st.get("daily_unlock_buy_events"), 0) + unlock_inc
    g_inc = 1 if tag == "GOLDEN_L1" else 0
    g_buy_ev = safe_int(st.get("golden_allin_buy_events"), 0) + g_inc
    day_g_buy_ev = safe_int(st.get("daily_golden_allin_buy_events"), 0) + g_inc
    last_g_date = (
        today_est_str
        if tag == "GOLDEN_L1"
        else str(st.get("last_golden_allin_date") or "")
    )
    extra_13 = safe_int(st.get("extra_13plus_buy_events"), 0) + (
        1
        if (tag != "TOPUP_1FL" and new_held_lots > BASE_MAX_LOTS_8PCT)
        else 0
    )
    cum_saved = round(
        safe_float(st.get("cumulative_leftover_saved_usd"), 0.0)
        + saved_from_portion,
        4,
    )
    day_saved = round(
        safe_float(st.get("daily_leftover_saved_usd"), 0.0)
        + saved_from_portion,
        4,
    )

    mark_auto_fill_grace_shield(
        context=context,
        symbol=TARGET_SYMBOL,
        lot_type=tag,
        fill_price=fill_p,
        filled_qty=q_int,
    )
    mark_reentry_monitor_60s_cycle_shield(
        context=context,
        symbol=TARGET_SYMBOL,
        eval_price=fill_p,
        clear_shield=True,
    )
    mark_reserve_deposit_check_shield(
        context=context,
        symbol=TARGET_SYMBOL,
        clear_shield=True,
    )

    updated_st = await context.ledger.update_state(
        TARGET_SYMBOL,
        buckets=buckets_to_dicts(new_buckets),
        anchor_price=new_buckets[0].book_price if new_buckets else fill_p,
        cycle_min_buy_price=round(new_cycle_min_p, 4),
        ratchet_anchor_price=new_buckets[0].book_price if new_buckets else fill_p,
        cycle_reanchor_credit_usd=0.0,
        l1_target_quota_qty=next_l1_target_q,
        last_golden_allin_date=last_g_date,
        buy_order_id="",
        ordered_qty=0,
        buy_price=0.0,
        pending_portion_budget=0.0,
        pending_lot_type="",
        pending_step_up_min_price=0.0,
        waiting_reserve_deposit=False,
        waiting_reserve_deposit_alert_sent=False,
        required_reserve_deposit_usd=0.0,
        last_reserve_check_ts=0.0,
        last_settled_order_ids=settled_oids,
        total_buy_events=tot_buy_ev,
        total_buy_shares=tot_buy_sh,
        daily_buy_events=day_buy_ev,
        cond_unlock_buy_events=cond_unlock_ev,
        daily_unlock_buy_events=day_unlock_ev,
        golden_allin_buy_events=g_buy_ev,
        daily_golden_allin_buy_events=day_g_buy_ev,
        extra_13plus_buy_events=extra_13,
        cumulative_leftover_saved_usd=cum_saved,
        daily_leftover_saved_usd=day_saved,
        entry_ts=now_buy_epoch,
        last_buy_fill_ts=now_buy_epoch,
        last_reentry_eval_ts=0.0,
    )

    context.wakeup_event.set()
    free_cash_now = safe_float(updated_st.get("free_cash_usd"), 0.0)
    summary = summarize_stratum_portfolio(updated_st, live_price=fill_p)
    l1_target = safe_float(summary.get("l1_target_price"), 0.0)
    u_cnt = safe_int(summary.get("upper_tier_count"), 0)
    u_qty = safe_int(summary.get("upper_qty"), 0)
    u_wma_p = safe_float(summary.get("upper_wma_price"), 0.0)
    u_wma_t = safe_float(summary.get("upper_wma_target_price"), 0.0)
    trig_buy_p = safe_float(summary.get("trigger_buy_price"), 0.0)
    drop_req_p = safe_float(summary.get("drop_buy_pct"), -1.0)
    l1_book_now = new_buckets[0].book_price if new_buckets else fill_p

    if hasattr(context, "send_slim_alert"):
        rem_quota_note = (
            f" · 🎯미체결 잔량 {rem_after_fill}주(목표 {next_l1_target_q}주 중 {cur_l1_qty}주 체결 ➔ "
            f"🛡️60초 타임쉴드 후 1.5초 모니터에서 ${l1_book_now:.2f} 이하 도래 시 잔량 60초 지정가 재대기!)"
            if rem_after_fill > 0
            else ""
        )
        if tag == "GOLDEN_L1":
            upper_note = (
                f" · 2~{new_held_tiers}층({u_cnt}개층·{u_qty}주) 순수이평 ${u_wma_p:.2f}(목표 ${u_wma_t:.2f})"
                if len(new_buckets) >= 2
                else ""
            )
            title_str = (
                f"🔥 [SOXL 황금시간 7층그리드 1층 100% 전액편입 체결] "
                f"{q_int}주 @ ${fill_p:.2f} ({new_held_tiers}개층)"
            )
            body_str = (
                f"실사용 ${actual_spent:,.2f} · "
                f"🛡️60초 타임쉴드 후 1층목표 ${l1_target:.2f}(+1.5%) 감시{upper_note} · "
                f"기억저가 ${new_cycle_min_p:.2f} · 가용현금 ${free_cash_now:,.2f} (총 {new_held_shares}주)"
            )
        elif tag == "TOPUP_1FL":
            done_badge = (
                f"정량 {next_l1_target_q}주 완수!"
                if rem_after_fill == 0
                else f"잔여 {rem_after_fill}주 추가 대기"
            )
            title_str = (
                f"🎯 [SOXL 1층 미체결 잔량 보충 체결] +{q_int}주 @ ${fill_p:.2f} "
                f"(1층 {cur_l1_qty}/{next_l1_target_q}주 합산 · {done_badge})"
            )
            body_str = (
                f"실사용 ${actual_spent:,.2f} (자투리 +${saved_from_portion:.2f} 시드보존) · "
                f"2층 승격 없이 기존 1층 합산(단가 ${l1_book_now:.2f} · 익절목표 ${l1_target:.2f}){rem_quota_note} · "
                f"가용현금 ${free_cash_now:,.2f} (총 {new_held_shares}주)"
            )
        elif was_l2_only and tag == "REENTRY_1FL" and len(new_buckets) >= 2:
            title_str = (
                f"🔥 [SOXL 현재가 지정가 1층 재장전 체결] {q_int}주 @ ${fill_p:.2f} (상단 {u_cnt}개층 비병합)"
            )
            body_str = (
                f"실사용 ${actual_spent:,.2f} (자투리 +${saved_from_portion:.2f} 시드보존) · "
                f"🛡️60초 타임쉴드 후 1층목표 ${l1_target:.2f}(+1.5%) 감시{rem_quota_note} · "
                f"2~{new_held_tiers}층({u_qty}주) 이평 ${u_wma_p:.2f}(목표 ${u_wma_t:.2f}) 유지 · "
                f"기억저가 ${new_cycle_min_p:.2f}(와이드 {drop_req_p:.1f}% 추매가 ${trig_buy_p:.2f}) · "
                f"가용현금 ${free_cash_now:,.2f}"
            )
        elif is_step_up_unlock_fill:
            reb_m = (
                prev_l1_p / max(0.01, old_min_p)
                if (prev_l1_p > 0.0 and old_min_p > 0.0)
                else 2.0
            )
            title_str = (
                f"🔓 [SOXL 스텝업 저가 해금 추매 체결 ({new_held_lots}회차/{new_held_tiers}개층)] {q_int}주 @ ${fill_p:.2f}"
            )
            body_str = (
                f"구저가 ${old_min_p:.2f}(반등 {reb_m:.2f}x) ➔ 스텝업 잠금저가 ${new_cycle_min_p:.2f} 갱신! · "
                f"실사용 ${actual_spent:,.2f} (자투리 +${saved_from_portion:.2f} 시드보존) · "
                f"🛡️60초 타임쉴드 후 1층목표 ${l1_target:.2f} & 2~{new_held_tiers}층({u_qty}주) 이평 ${u_wma_p:.2f}(목표 ${u_wma_t:.2f}) 감시{rem_quota_note} · "
                f"차기단차 {drop_req_p:.1f}%(${trig_buy_p:.2f}) · 가용현금 ${free_cash_now:,.2f}"
            )
        else:
            upper_note = ""
            if len(new_buckets) >= 2:
                upper_note = (
                    f" · 2~{new_held_tiers}층({u_cnt}개층·{u_qty}주) 순수이평 ${u_wma_p:.2f}(목표 ${u_wma_t:.2f})"
                )
            title_str = (
                f"🔵 [SOXL {new_held_lots}회차({new_held_tiers}개층) 현재가 지정가 매수 체결] {q_int}주 @ ${fill_p:.2f}"
            )
            body_str = (
                f"실사용 ${actual_spent:,.2f} (자투리 +${saved_from_portion:.2f} 시드보존) "
                f"· 🛡️60초 타임쉴드 후 1층목표 ${l1_target:.2f} 감시{upper_note}{rem_quota_note} · 차기단차 {drop_req_p:.1f}%(${trig_buy_p:.2f}) "
                f"· 가용현금 ${free_cash_now:,.2f} (총 {new_held_shares}주)"
            )
        await context.send_slim_alert(title=title_str, body=body_str)

    return {
        "status": "BUY_FILLED_AND_MERGED",
        "symbol": TARGET_SYMBOL,
        "lot_type": tag,
        "is_step_up_unlock": is_step_up_unlock_fill,
        "filled_qty": q_int,
        "ordered_qty": ord_q,
        "l1_target_quota_qty": next_l1_target_q,
        "l1_rem_quota_qty": rem_after_fill,
        "fill_price": fill_p,
        "actual_spent_usd": actual_spent,
        "saved_from_portion_usd": saved_from_portion,
        "cycle_min_buy_price": round(new_cycle_min_p, 4),
        "held_lots": new_held_lots,
        "held_tiers": new_held_tiers,
        "held_shares": new_held_shares,
        "free_cash_usd": free_cash_now,
    }


async def sync_pending_buy_order_plugin(
    context: Any,
    holdings: Dict[str, Dict[str, Any]],
    prices: Dict[str, float],
    now_est: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    🎯 1 & 🎯 5 & Case 19, 24, 59, 60, 61, 65, 71, 72, 73, 76, 77, 78, 80:
    장부에 대기 중인 미체결 매수 주문(buy_order_id)이 존재할 때:
    1) GET /api/v1/orders/{orderId} 로 실제 체결 상태(FILLED / PARTIAL_FILLED / PENDING / CANCELED)를 조회한다.
    2) FILLED(또는 부분 체결 후 취소 종료) 확인 즉시 실제 평균 체결가(execution.averageFilledPrice)와
       체결 수량(filledQuantity), 원주문 수량(ordered_qty)을 _commit_filled_buy_to_stratum_ledger() 에 전달한다.
    3) 단 1주도 체결되지 않고(filled_q == 0) 취소/거부된 경우:
       - GOLDEN_POCKET / GOLDEN_L1 주문이었으면 last_golden_allin_date 를 "" 로 원복하여
         07:00 ~ 07:50 EST 시간창 내 재타격 기회를 보존한다(Case 80).
    4) 프로세스 재기동으로 인해 last_modify_mono 단조시계가 역전(last_mod > now_mono)되었거나 0.0 인 경우
       즉시 현재 단조시계로 자가 치유하여 60.0초(BUY_ORDER_MAX_WAIT_SEC) 타임아웃 안전 취소를 100% 보장한다(Case 65).
    """
    st = context.ledger.get_state(TARGET_SYMBOL)
    buy_oid = str(st.get("buy_order_id") or "").strip()
    if not buy_oid:
        return {"status": "NO_PENDING_BUY"}

    ordered_qty = max(1, safe_int(st.get("ordered_qty"), 1))
    ord_price = safe_float(st.get("buy_price"), 0.0)
    portion_budget = safe_float(
        st.get("pending_portion_budget"), float(ordered_qty) * ord_price
    )
    lot_type = str(st.get("pending_lot_type") or "QUOTA_L1").upper().strip()
    buckets_now = buckets_from_dicts(st.get("buckets", []))
    has_active_l1_now = has_active_l1_bucket(buckets_now)
    is_vacant_l1_now = bool(len(buckets_now) > 0 and not has_active_l1_now)
    cur_target_q = max(0, safe_int(st.get("l1_target_quota_qty"), 0))
    fallback_target_q_on_zero_cancel = (
        max(buckets_now[0].qty, cur_target_q)
        if (lot_type in ("TOPUP_1FL", "GOLDEN_POCKET") and has_active_l1_now)
        else (buckets_now[0].qty if has_active_l1_now else 0)
    )
    is_golden_lot = lot_type in ("GOLDEN_POCKET", "GOLDEN_L1")

    # MODIFIED [Case 65 : 프로세스 재기동 후 단조 시계(last_modify_mono) 역전 또는 결측 시 즉시 자가 치유]
    now_mono = time.monotonic()
    last_mod = safe_float(st.get("last_modify_mono"), 0.0)
    if last_mod <= 0.0 or last_mod > now_mono:
        last_mod = now_mono
        await context.ledger.update_state(
            TARGET_SYMBOL, last_modify_mono=last_mod
        )
    elapsed_mod = max(0.0, now_mono - last_mod)

    detail = await context.api.get_order_detail(buy_oid)
    if isinstance(detail, dict):
        ord_status = str(detail.get("status") or "").upper().strip()
        exec_obj = (
            detail.get("execution")
            if isinstance(detail.get("execution"), dict)
            else {}
        )
        filled_q = safe_int(exec_obj.get("filledQuantity"), 0)
        avg_fill_p = safe_float(exec_obj.get("averageFilledPrice"), 0.0)

        # 1) 전량 체결 완료(FILLED) 또는 부분 체결 후 종료된 경우
        if ord_status == "FILLED" or (
            filled_q > 0 and ord_status in ("CANCELED", "REJECTED", "REPLACED")
        ):
            eff_q = filled_q if filled_q > 0 else ordered_qty
            eff_p = avg_fill_p if avg_fill_p > 0.0 else ord_price
            return await _commit_filled_buy_to_stratum_ledger(
                context=context,
                filled_qty=eff_q,
                avg_fill_price=eff_p,
                portion_budget=portion_budget,
                lot_type=lot_type,
                settled_order_id=buy_oid,
                ordered_qty=ordered_qty,
            )

        # 2) 부분 체결(PARTIAL_FILLED) 진행 중인 경우 -> 60.0초까지 잔량 체결 대기 후 미체결분 안전 취소 & 기체결분 반영
        if ord_status == "PARTIAL_FILLED" or filled_q > 0:
            if elapsed_mod >= BUY_ORDER_MAX_WAIT_SEC:
                try:
                    await context.api.cancel_order(buy_oid)
                except Exception:
                    pass
                final_det = await context.api.get_order_detail(buy_oid)
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
                eff_p = avg_fill_p if avg_fill_p > 0.0 else ord_price
                return await _commit_filled_buy_to_stratum_ledger(
                    context=context,
                    filled_qty=filled_q,
                    avg_fill_price=eff_p,
                    portion_budget=portion_budget,
                    lot_type=lot_type,
                    settled_order_id=buy_oid,
                    ordered_qty=ordered_qty,
                )
            return {
                "status": "BUY_PARTIAL_FILLED_WAITING",
                "filled_qty": filled_q,
                "ordered_qty": ordered_qty,
            }

        # 3) 미체결 상태로 취소/거부된 경우 장부 락 해제
        if ord_status in ("CANCELED", "REJECTED") and filled_q == 0:
            re_epoch = (
                mark_reentry_monitor_60s_cycle_shield(
                    context=context, symbol=TARGET_SYMBOL, eval_price=ord_price
                )
                if (is_vacant_l1_now and not is_golden_lot)
                else safe_float(st.get("last_reentry_eval_ts"), 0.0)
            )
            clear_kw: Dict[str, Any] = {
                "l1_target_quota_qty": fallback_target_q_on_zero_cancel,
                "buy_order_id": "",
                "ordered_qty": 0,
                "buy_price": 0.0,
                "pending_portion_budget": 0.0,
                "pending_lot_type": "",
                "pending_step_up_min_price": 0.0,
                "last_reentry_eval_ts": re_epoch,
            }
            if is_golden_lot:
                clear_kw["last_golden_allin_date"] = ""
            await context.ledger.update_state(TARGET_SYMBOL, **clear_kw)
            return {"status": f"BUY_ORDER_{ord_status}_CLEARED"}

    # 🚨 4) [Case 65, Case 73, Case 76, Case 78 & Case 80] 매도 1호가(Ask 1) 상향 추격 정정 완전 소각! (60초 대기 후 안전 취소)
    if elapsed_mod >= BUY_ORDER_MAX_WAIT_SEC:
        try:
            await context.api.cancel_order(buy_oid)
        except Exception:
            pass

        final_detail = await context.api.get_order_detail(buy_oid)
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
                return await _commit_filled_buy_to_stratum_ledger(
                    context=context,
                    filled_qty=(f_qty if f_qty > 0 else ordered_qty),
                    avg_fill_price=(f_avg if f_avg > 0.0 else ord_price),
                    portion_budget=portion_budget,
                    lot_type=lot_type,
                    settled_order_id=buy_oid,
                    ordered_qty=ordered_qty,
                )

        re_epoch = (
            mark_reentry_monitor_60s_cycle_shield(
                context=context, symbol=TARGET_SYMBOL, eval_price=ord_price
            )
            if (is_vacant_l1_now and not is_golden_lot)
            else safe_float(st.get("last_reentry_eval_ts"), 0.0)
        )
        timeout_kw: Dict[str, Any] = {
            "l1_target_quota_qty": fallback_target_q_on_zero_cancel,
            "buy_order_id": "",
            "ordered_qty": 0,
            "buy_price": 0.0,
            "pending_portion_budget": 0.0,
            "pending_lot_type": "",
            "pending_step_up_min_price": 0.0,
            "last_reentry_eval_ts": re_epoch,
        }
        if is_golden_lot:
            timeout_kw["last_golden_allin_date"] = ""
        await context.ledger.update_state(TARGET_SYMBOL, **timeout_kw)
        logger.info(
            "⏳ [SOXL 현재가 지정가 매수(%s) 60초 미체결 안전 취소] 지정가 $%.2f 유지 종료 ➔ 관망 복귀",
            lot_type,
            ord_price,
        )
        return {"status": "BUY_ORDER_UNFILLED_CANCELED_SAFE"}

    return {"status": "BUY_ORDER_PENDING", "orderId": buy_oid}


# ---------------------------------------------------------------------------
# [핵심 2] 진화 챔피언 (🌟 POCKET_ALLIN / 🔥 GRID_L1_ALLIN × 💉 05_RESV_6P_GUARD30 × 🔓 06_STEP2X_15PCT_C20) : 비대칭 매수 타격 엔진
#  - 분기 G   : 07:00 ~ 07:50 EST & RSI(14) <= 19.0 황금시간 가용시드 100% 전액 추가매수 (제어반 ON 시 · Case 80)
#  - 분기 A   : 그리드 0주 상태 -> 0주 종료 후 60초 타임쉴드 경과 뒤 현재가 지정가 첫 1층(REENTRY_1FL) 산입
#  - 분기 B-0 : 활성 1층 부분체결 미체결 잔량(rem_quota_qty > 0) -> 60초 타임쉴드 후 매 1.5초 모니터에서 현재가 <= 1층 단가 도래 시 잔량(TOPUP_1FL) 지정가 60초 재대기(Case 78)
#  - 분기 B-1 : 상단 2~7층 보유 중 1층 공석 -> 매 60.0초(1분) 타임쉴드 주기 재장전 모니터 & 2층 단가 상한(Case 73) & GUARD30/예비수혈(Case 77)
#  - 분기 B-2 : 활성 1층 보유 중 -> 10분 고정 게이트 & 정적 기억저가 4단 와이드 신저가 OR STEP2X_15PCT_C20 스텝업 추매(Case 76) & GUARD30/예비수혈(Case 77)
# ---------------------------------------------------------------------------
async def execute_seed_protected_buy_gate_plugin(
    context: Any,
    holdings: Dict[str, Dict[str, Any]],
    prices: Dict[str, float],
    now_est: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    🎯 1, 🎯 2, 🎯 4 & Case 25 ~ 83 (챔피언 : 🌟 POCKET_ALLIN / 🔥 GRID_L1_ALLIN × 💉 05_RESV_6P_GUARD30 × 🔓 06_STEP2X_15PCT_C20):
    04:07:00 ~ 16:00:00 EST 운용 구간에서 작동하는 비대칭 매수 타격 엔진.
    """
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    hm = dt_now.hour * 100 + dt_now.minute
    today_est_str = dt_now.strftime("%Y-%m-%d")

    # 1) 미체결 매수 주문이 있으면 먼저 체결 확인 수행
    st = context.ledger.get_state(TARGET_SYMBOL)
    if str(st.get("buy_order_id") or "").strip():
        return await sync_pending_buy_order_plugin(
            context=context,
            holdings=holdings,
            prices=prices,
            now_est=dt_now,
        )

    # 2) 04:07 ~ 16:00 EST 운용 시간대 및 마스터 전원(is_active) 확인
    if not is_active_buy_window(hm, now_est=dt_now):
        return {"status": "OUTSIDE_TRADING_WINDOW"}

    if not bool(st.get("is_active", True)):
        return {"status": "BOT_INACTIVE"}

    # 미체결 매도 주문이 진행 중이면 매도 완료까지 대기 (동일 틱 자전거래 방지, Case 44)
    if str(st.get("sell_order_id") or "").strip():
        return {"status": "SELL_ORDER_IN_PROGRESS"}

    # 🛡️ 3) [Case 65 핵심] 매도(및 0주 싸이클 종료) 후 60.0초 타임쉴드 & 직전 매수 후 60.0초 타임쉴드 최우선 강제 검문!
    in_sell_shield, remain_sell_sec = is_within_post_sell_time_shield(
        context, st, TARGET_SYMBOL
    )
    if in_sell_shield:
        return {
            "status": "HOLD_POST_SELL_60S_TIME_SHIELD",
            "remain_shield_sec": remain_sell_sec,
        }

    in_buy_shield, remain_buy_sec = is_within_post_buy_time_shield(
        context, st, TARGET_SYMBOL
    )
    if in_buy_shield:
        return {
            "status": "HOLD_POST_BUY_60S_TIME_SHIELD",
            "remain_shield_sec": remain_buy_sec,
        }

    # 🛡️ 3-B) [Case 77 & Case 80] 시드고갈 입금 대기 또는 골든포켓 현금 가동 중일 때 60.0초 감지 타임쉴드 검문
    in_res_sh, rem_res_sec = is_within_reserve_deposit_check_shield(
        context, st, TARGET_SYMBOL
    )
    if in_res_sh:
        return {
            "status": "HOLD_WAITING_RESERVE_DEPOSIT_60S_SHIELD",
            "remain_shield_sec": rem_res_sec,
            "required_reserve_deposit_usd": safe_float(
                st.get("required_reserve_deposit_usd"), 0.0
            ),
        }

    live_p = _get_live_soxl_price(context, prices, holdings, dt_now)
    if live_p <= 0.0:
        return {"status": "NO_LIVE_PRICE"}

    buckets = buckets_from_dicts(st.get("buckets", []))
    gp = pocket_from_dict(st.get("golden_pocket"))
    h_qty = safe_int((holdings or {}).get(TARGET_SYMBOL, {}).get("qty"), 0)

    init_seed = max(
        100.0,
        safe_float(st.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD),
    )
    cum_realized = safe_float(st.get("cumulative_realized_net_usd"), 0.0)
    injected_reserve_usd = max(
        0.0, safe_float(st.get("injected_reserve_usd"), 0.0)
    )
    realized_equity = max(100.0, init_seed + cum_realized)
    free_cash = max(0.0, safe_float(st.get("free_cash_usd"), 0.0))
    actual_invested = sum(b.actual_cost_usd for b in buckets) + (
        gp.actual_cost_usd if gp.is_active else 0.0
    )
    # Case 77 & Case 80: 온디맨드 예비시드 수혈금(injected_reserve_usd)을 제외한 순수 코어 총자산(core_equity) 산출
    core_equity = max(
        init_seed, (free_cash + actual_invested) - injected_reserve_usd
    )
    portion_mode = str(st.get("portion_mode") or "COMP_08PCT").upper()
    threshold_mode = str(st.get("threshold_mode") or "WIDE_RUNWAY").upper()
    unlock_mode = str(
        st.get("unlock_mode") or DEFAULT_UNLOCK_MODE
    ).upper()
    golden_allin_mode = (
        str(st.get("golden_allin_mode") or DEFAULT_GOLDEN_ALLIN_MODE)
        .upper()
        .strip()
    )
    if golden_allin_mode not in GOLDEN_ALLIN_MODES:
        golden_allin_mode = DEFAULT_GOLDEN_ALLIN_MODE
    buy_interval_min = LOCKED_BUY_INTERVAL_MIN

    # -----------------------------------------------------------------------
    # [분기 G · Case 80 : 미동부 프리장 황금시간대(07:00 ~ 07:50 EST & RSI(14) <= 19.0) 가용현금 100% 전액 추가매수]
    # -> 전술 제어반에서 POCKET_ALLIN 또는 GRID_L1_ALLIN 이 선택된 경우에만 작동(기본값 "NONE" [OFF])!
    # -----------------------------------------------------------------------
    if golden_allin_mode != "NONE" and is_golden_allin_time_window(
        hm, now_est=dt_now
    ):
        raw_cache = getattr(context, "candle_metrics_cache", {})
        base_met = (
            raw_cache.get(TARGET_SYMBOL)
            if isinstance(raw_cache, dict)
            else None
        )
        met = refresh_metrics_with_live_tick(base_met, live_p, now_est=dt_now)
        rsi_val = safe_float(met.get("rsi_14"), 50.0)
        # MODIFIED [Case 80]: 최소 14개 이상의 1분봉이 확보된 rsi_ready == True 만 엄격히 신뢰!
        rsi_ready = bool(met.get("rsi_ready", False))

        golden_sig = evaluate_golden_allin_signal(
            hm=hm,
            rsi_14=rsi_val,
            live_price=live_p,
            golden_allin_mode=golden_allin_mode,
            today_str=today_est_str,
            last_golden_allin_date=str(st.get("last_golden_allin_date") or ""),
            golden_pocket=gp,
            rsi_ready=rsi_ready,
        )
        if bool(golden_sig.get("should_buy")):
            async with context.in_memory_ordering_lock:
                async with context.dual_strike_mutex:
                    st_now = context.ledger.get_state(TARGET_SYMBOL)
                    if str(st_now.get("buy_order_id") or "").strip() or str(
                        st_now.get("sell_order_id") or ""
                    ).strip():
                        return {"status": "ALREADY_ORDERING_IN_MUTEX"}

                    in_s_sh, _ = is_within_post_sell_time_shield(
                        context, st_now, TARGET_SYMBOL
                    )
                    in_b_sh, _ = is_within_post_buy_time_shield(
                        context, st_now, TARGET_SYMBOL
                    )
                    if in_s_sh or in_b_sh:
                        return {"status": "HOLD_60S_TIME_SHIELD_IN_MUTEX"}

                    fresh_live_p = await _fetch_fresh_current_soxl_price(
                        context, fallback_price=live_p
                    )
                    if fresh_live_p <= 0.0:
                        return {"status": "NO_FRESH_LIVE_PRICE"}

                    met_fresh = refresh_metrics_with_live_tick(
                        base_met, fresh_live_p, now_est=dt_now
                    )
                    fresh_rsi = safe_float(met_fresh.get("rsi_14"), rsi_val)
                    fresh_rsi_ready = bool(
                        met_fresh.get("rsi_ready", rsi_ready)
                    )
                    now_gp = pocket_from_dict(st_now.get("golden_pocket"))
                    now_g_mode = (
                        str(
                            st_now.get("golden_allin_mode")
                            or DEFAULT_GOLDEN_ALLIN_MODE
                        )
                        .upper()
                        .strip()
                    )

                    re_g_sig = evaluate_golden_allin_signal(
                        hm=hm,
                        rsi_14=fresh_rsi,
                        live_price=fresh_live_p,
                        golden_allin_mode=now_g_mode,
                        today_str=today_est_str,
                        last_golden_allin_date=str(
                            st_now.get("last_golden_allin_date") or ""
                        ),
                        golden_pocket=now_gp,
                        rsi_ready=fresh_rsi_ready,
                    )
                    if bool(re_g_sig.get("should_buy")):
                        exec_order_p = max(
                            0.01,
                            math.floor((fresh_live_p + 1e-9) * 100.0) / 100.0,
                        )
                        now_buckets = buckets_from_dicts(
                            st_now.get("buckets", [])
                        )
                        now_free_cash = max(
                            0.0, safe_float(st_now.get("free_cash_usd"), 0.0)
                        )
                        now_init_seed = max(
                            100.0,
                            safe_float(
                                st_now.get("initial_seed_usd"),
                                DEFAULT_INITIAL_SEED_USD,
                            ),
                        )
                        now_inj_res = max(
                            0.0,
                            safe_float(st_now.get("injected_reserve_usd"), 0.0),
                        )
                        now_inv_tot = sum(
                            b.actual_cost_usd for b in now_buckets
                        ) + (now_gp.actual_cost_usd if now_gp.is_active else 0.0)
                        now_core_eq = max(
                            now_init_seed,
                            (now_free_cash + now_inv_tot) - now_inj_res,
                        )
                        _, portion_budget_g = compute_golden8_quota_qty(
                            anchor_price=exec_order_p,
                            current_total_equity=now_core_eq,
                            initial_seed_usd=now_init_seed,
                            portion_mode=portion_mode,
                            exec_price=exec_order_p,
                        )

                        (
                            can_proceed_g,
                            eff_free_cash_g,
                            bp_usd_g,
                            guard_res_g,
                        ) = await _check_and_execute_guard30_or_reserve_injection(
                            context=context,
                            st_now=st_now,
                            exec_order_p=exec_order_p,
                            portion_budget=portion_budget_g,
                            l1_actual_cost_usd=0.0,
                            is_dip_promotion=False,
                            is_vacant_l1_reentry=False,
                            trigger_desc=(
                                f"황금시간({now_g_mode} · RSI {fresh_rsi:.1f}) 전액매수"
                            ),
                        )
                        if not can_proceed_g:
                            return {
                                "status": "HOLD_GOLDEN_GUARD30_WAITING_DEPOSIT",
                                "guard_eval": guard_res_g,
                            }

                        buy_qty_g, est_spent_g = (
                            resolve_allin_affordable_buy_qty(
                                price_t=exec_order_p,
                                free_cash_usd=eff_free_cash_g,
                                broker_buying_power_usd=(
                                    bp_usd_g if bp_usd_g > 0.0 else None
                                ),
                            )
                        )
                        if buy_qty_g > 0:
                            g_lot_type = str(
                                re_g_sig.get("lot_type") or "GOLDEN_POCKET"
                            )
                            cid_prefix = (
                                "GLDPKT"
                                if g_lot_type == "GOLDEN_POCKET"
                                else "GLDL1"
                            )
                            cid = generate_client_order_id(prefix=cid_prefix)
                            try:
                                ord_res = await context.api.create_order(
                                    symbol=TARGET_SYMBOL,
                                    side="BUY",
                                    quantity=buy_qty_g,
                                    price=exec_order_p,
                                    order_type="LIMIT",
                                    time_in_force="DAY",
                                    client_order_id=cid,
                                    enforce_daymarket_block=True,
                                )
                                oid = str(
                                    ord_res.get("orderId") or ""
                                ).strip()
                                # MODIFIED [Case 78 & Case 80]:
                                # 이미 활성 1층이 존재하는 상태에서 GOLDEN_L1 이 발주될 때는 기존 1층의 l1_target_quota_qty 를 유지하고
                                # 실제 체결 커밋 시점에 체결 수량으로 확정하여, 0주 미체결 취소 시 기존 1층 정량이 오염되지 않게 보호!
                                has_l1_g = has_active_l1_bucket(now_buckets)
                                prev_target_q_g = safe_int(
                                    st_now.get("l1_target_quota_qty"), 0
                                )
                                if (
                                    g_lot_type == "GOLDEN_POCKET"
                                    or has_l1_g
                                ):
                                    next_target_q_g = prev_target_q_g
                                else:
                                    next_target_q_g = buy_qty_g
                                await context.ledger.update_state(
                                    TARGET_SYMBOL,
                                    l1_target_quota_qty=next_target_q_g,
                                    last_golden_allin_date=today_est_str,
                                    buy_order_id=oid,
                                    client_order_id=cid,
                                    ordered_qty=buy_qty_g,
                                    buy_price=exec_order_p,
                                    pending_portion_budget=est_spent_g,
                                    pending_lot_type=g_lot_type,
                                    pending_step_up_min_price=0.0,
                                    last_modify_mono=time.monotonic(),
                                )
                                context.wakeup_event.set()
                                logger.info(
                                    "🌟 [Case 80 SOXL 황금시간(07:00~07:50 EST) RSI %.2f <= 19.0 가용시드 100%% 전액매수(%s) 발주] %d주 @ 지정가 $%.2f (예상원금 $%.2f · orderId=%s)",
                                    fresh_rsi,
                                    g_lot_type,
                                    buy_qty_g,
                                    exec_order_p,
                                    est_spent_g,
                                    oid,
                                )
                                return {
                                    "status": "GOLDEN_ALLIN_BUY_ORDERED",
                                    "mode": now_g_mode,
                                    "lot_type": g_lot_type,
                                    "rsi_14": fresh_rsi,
                                    "orderId": oid,
                                    "qty": buy_qty_g,
                                    "price": exec_order_p,
                                }
                            except Exception as exc:
                                logger.warning(
                                    "Case 80 황금시간 전액매수(%s) 주문 발주 예외: %s",
                                    g_lot_type,
                                    exc,
                                )
                                return {
                                    "status": "GOLDEN_ORDER_ERROR",
                                    "error": str(exc),
                                }

    is_zero_shares = bool(len(buckets) == 0 and (h_qty == 0 or h_qty == gp.qty))
    has_active_l1 = has_active_l1_bucket(buckets)
    # 🚨 Case 71, Case 72 & Case 73: 상단에 2층 ~ 7층 그리드(GRID_L2 ~ GRID_L7)가 남아 있고 1층이 익절되어 공석인 상태!
    is_l2_only_vacant_l1 = bool(len(buckets) > 0 and not has_active_l1)

    # -----------------------------------------------------------------------
    # [분기 A : 그리드 보유 잔고 0주 상태 (is_zero_shares)]
    # -> 0주 싸이클 종료 후 60.0초 타임쉴드 경과 확인 완료 뒤 실시간 현재가를 직접 조회하여 '현재가 지정가(LIMIT)'로 1층 산입!
    # -----------------------------------------------------------------------
    if is_zero_shares:
        # MODIFIED [Case 80]: 그리드가 0주인데 독립 골든포켓(gp.is_active)에 가용 현금 100%가 투입되어 있는 동안에는
        # 매 1.5초마다 불필요하게 시세 API를 재조회하지 않고 골든포켓(+1.50%) 익절로 현금이 환원될 때까지 조용히 대기한다!
        min_req_0sh_guard = max(
            live_p * (1.0 + ROUND_TRIP_FEE_RATE_PCT / 100.0),
            (core_equity * PORTION_RATIO_LOCKED) * MIN_DIP_BUDGET_RATIO,
        )
        if gp.is_active and free_cash < min_req_0sh_guard:
            return {
                "status": "HOLD_ZERO_GRID_CASH_IN_GOLDEN_POCKET",
                "golden_pocket_qty": gp.qty,
                "free_cash_usd": free_cash,
            }

        async with context.in_memory_ordering_lock:
            async with context.dual_strike_mutex:
                st_now = context.ledger.get_state(TARGET_SYMBOL)
                if str(st_now.get("buy_order_id") or "").strip() or str(
                    st_now.get("sell_order_id") or ""
                ).strip():
                    return {"status": "ALREADY_ORDERING_IN_MUTEX"}

                now_buckets = buckets_from_dicts(st_now.get("buckets", []))
                if len(now_buckets) > 0:
                    return {"status": "L1_ALREADY_FILLED_IN_MUTEX"}

                in_s_sh, rem_s = is_within_post_sell_time_shield(
                    context, st_now, TARGET_SYMBOL
                )
                if in_s_sh:
                    return {
                        "status": "HOLD_POST_SELL_60S_TIME_SHIELD_IN_MUTEX",
                        "remain_shield_sec": rem_s,
                    }

                in_b_sh, rem_b = is_within_post_buy_time_shield(
                    context, st_now, TARGET_SYMBOL
                )
                if in_b_sh:
                    return {
                        "status": "HOLD_POST_BUY_60S_TIME_SHIELD_IN_MUTEX",
                        "remain_shield_sec": rem_b,
                    }

                fresh_live_p = await _fetch_fresh_current_soxl_price(
                    context, fallback_price=live_p
                )
                if fresh_live_p <= 0.0:
                    return {"status": "NO_FRESH_LIVE_PRICE"}

                exec_order_p = max(
                    0.01, math.floor((fresh_live_p + 1e-9) * 100.0) / 100.0
                )

                # 🚨 Case 67 & Case 77: 0주 진입 시 순수 코어 총자산 기준 min(1회분 상한, 기준가 정량) 적용
                prev_anchor_p = safe_float(st_now.get("anchor_price"), 0.0)
                ref_zero_anchor = (
                    prev_anchor_p if prev_anchor_p > 0.0 else exec_order_p
                )
                target_qty, portion_budget = compute_golden8_quota_qty(
                    anchor_price=ref_zero_anchor,
                    current_total_equity=core_equity,
                    initial_seed_usd=init_seed,
                    portion_mode=portion_mode,
                    exec_price=exec_order_p,
                )

                (
                    can_proceed_0sh,
                    eff_free_cash_0sh,
                    bp_usd_0sh,
                    guard_res_0sh,
                ) = await _check_and_execute_guard30_or_reserve_injection(
                    context=context,
                    st_now=st_now,
                    exec_order_p=exec_order_p,
                    portion_budget=portion_budget,
                    l1_actual_cost_usd=0.0,
                    is_dip_promotion=False,
                    is_vacant_l1_reentry=False,
                    trigger_desc="0주 첫 1층 진입",
                )
                if not can_proceed_0sh:
                    return {
                        "status": "HOLD_GUARD30_WAITING_RESERVE_DEPOSIT",
                        "guard_eval": guard_res_0sh,
                    }

                buy_qty, _est_spent = resolve_affordable_buy_qty(
                    target_qty=target_qty,
                    price_t=exec_order_p,
                    free_cash_usd=eff_free_cash_0sh,
                    broker_buying_power_usd=(
                        bp_usd_0sh if bp_usd_0sh > 0.0 else None
                    ),
                    max_portion_budget_usd=portion_budget,
                )

                if buy_qty <= 0:
                    return {"status": "INSUFFICIENT_CASH_FOR_0SH_ENTRY"}

                _, cur_bucket_id, today_str, _ = evaluate_buy_gate_bucket_status(
                    now_est=dt_now,
                    buy_interval_min=buy_interval_min,
                    last_evaluated_bucket_id=safe_int(
                        st_now.get("last_evaluated_buy_bucket_id"), -1
                    ),
                    last_evaluated_date=str(
                        st_now.get("last_evaluated_date") or ""
                    ),
                )

                cid = generate_client_order_id(prefix="INI1FL")
                try:
                    ord_res = await context.api.create_order(
                        symbol=TARGET_SYMBOL,
                        side="BUY",
                        quantity=buy_qty,
                        price=exec_order_p,
                        order_type="LIMIT",
                        time_in_force="DAY",
                        client_order_id=cid,
                        enforce_daymarket_block=True,
                    )
                except Exception as exc:
                    logger.warning(
                        "0주 현재가 지정가 실물 1층(REENTRY_1FL) 매수 주문 예외: %s",
                        exc,
                    )
                    return {"status": "ORDER_ERROR", "error": str(exc)}

                oid = str(ord_res.get("orderId") or "").strip()
                await context.ledger.update_state(
                    TARGET_SYMBOL,
                    l1_target_quota_qty=buy_qty,
                    buy_order_id=oid,
                    client_order_id=cid,
                    ordered_qty=buy_qty,
                    buy_price=exec_order_p,
                    pending_portion_budget=portion_budget,
                    pending_lot_type="REENTRY_1FL",
                    pending_step_up_min_price=0.0,
                    last_evaluated_buy_bucket_id=cur_bucket_id,
                    last_evaluated_date=today_str,
                    last_modify_mono=time.monotonic(),
                    last_reentry_eval_ts=0.0,
                )
                context.wakeup_event.set()
                logger.info(
                    "🔵 [SOXL 0주 60초 타임쉴드 완료 후 현재가 지정가 1층 매수 발주] %d주 @ 지정가 $%.2f (1회예산 $%.2f · orderId=%s)",
                    buy_qty,
                    exec_order_p,
                    portion_budget,
                    oid,
                )
                return {
                    "status": "ZERO_SHARES_IMMEDIATE_1FL_ORDERED",
                    "orderId": oid,
                    "qty": buy_qty,
                    "price": exec_order_p,
                }

    # -----------------------------------------------------------------------
    # [분기 B-1 · Case 73 & Case 77 : 상단 그리드(2층 ~ 7층)만 보유 중 (1층 공석, is_l2_only_vacant_l1 == True)]
    # -----------------------------------------------------------------------
    if is_l2_only_vacant_l1:
        in_re_shield, rem_re_sec = is_within_reentry_monitor_time_shield(
            context, st, TARGET_SYMBOL
        )
        if in_re_shield:
            return {
                "status": "HOLD_REENTRY_60S_TIME_SHIELD",
                "remain_shield_sec": rem_re_sec,
            }

        fresh_live_p = await _fetch_fresh_current_soxl_price(
            context, fallback_price=live_p
        )
        if fresh_live_p <= 0.0:
            return {"status": "NO_FRESH_LIVE_PRICE"}

        # 상단 최하단 층인 2층의 순수 매수 단가(min_upper_tier_price) 추출
        min_upper_tier_p = min(b.book_price for b in buckets)
        wma_info = compute_upper_2_to_7_moving_avg(buckets)
        upper_wma_p = safe_float(
            wma_info.get("upper_wma_price"), min_upper_tier_p
        )
        anchor_p = safe_float(st.get("anchor_price"), min_upper_tier_p)

        reentry_sig = evaluate_l2_only_hybrid_reentry_signal(
            live_price=fresh_live_p,
            anchor_price=anchor_p,
            l2_book_price=min_upper_tier_p,
            min_upper_tier_price=min_upper_tier_p,
        )
        sig_type = str(reentry_sig.get("signal_type") or "HOLD_WAIT_GATE")

        if not bool(reentry_sig.get("should_buy")):
            new_pass_cnt = safe_int(st.get("seed_protect_pass_cnt"), 0) + 1
            new_day_pass = (
                safe_int(st.get("daily_seed_protect_pass_cnt"), 0) + 1
            )
            re_eval_epoch = mark_reentry_monitor_60s_cycle_shield(
                context=context,
                symbol=TARGET_SYMBOL,
                eval_price=fresh_live_p,
            )
            await context.ledger.update_state(
                TARGET_SYMBOL,
                last_reentry_eval_ts=re_eval_epoch,
                seed_protect_pass_cnt=new_pass_cnt,
                daily_seed_protect_pass_cnt=new_day_pass,
            )
            if sig_type == "HOLD_PREVENT_INVERSION":
                logger.info(
                    "🛡️ [Case 73 1층>2층 단가역전 원천 차단] 현재가 $%.2f > 2층단가 상한 $%.2f (직전익절 $%.2f 대비 %+.2f%%) -> 매수 패스 & 60초 타임쉴드 재장전",
                    fresh_live_p,
                    min_upper_tier_p,
                    safe_float(reentry_sig.get("ref_anchor"), anchor_p),
                    safe_float(reentry_sig.get("chg_from_exit_pct"), 0.0),
                )
                return {
                    "status": "L2_ONLY_REENTRY_INVERSION_BLOCKED",
                    "signal_type": sig_type,
                    "live_price": fresh_live_p,
                    "l2_ceiling_price": min_upper_tier_p,
                    "ref_anchor": reentry_sig.get("ref_anchor"),
                    "chg_from_exit_pct": reentry_sig.get("chg_from_exit_pct"),
                    "seed_protect_pass_cnt": new_day_pass,
                    "next_reentry_check_sec": REENTRY_MONITOR_TIME_SHIELD_SEC,
                }
            return {
                "status": "L2_ONLY_REENTRY_HOLD_PASSED",
                "signal_type": sig_type,
                "ref_anchor": reentry_sig.get("ref_anchor"),
                "l2_ceiling_price": min_upper_tier_p,
                "chg_from_exit_pct": reentry_sig.get("chg_from_exit_pct"),
                "seed_protect_pass_cnt": new_day_pass,
                "next_reentry_check_sec": REENTRY_MONITOR_TIME_SHIELD_SEC,
            }

        async with context.in_memory_ordering_lock:
            async with context.dual_strike_mutex:
                st_now = context.ledger.get_state(TARGET_SYMBOL)
                if str(st_now.get("buy_order_id") or "").strip() or str(
                    st_now.get("sell_order_id") or ""
                ).strip():
                    return {"status": "ALREADY_ORDERING_IN_MUTEX"}

                now_buckets = buckets_from_dicts(st_now.get("buckets", []))
                if not now_buckets or has_active_l1_bucket(now_buckets):
                    return {"status": "L1_STATE_CHANGED_IN_MUTEX"}

                in_re_m, _ = is_within_reentry_monitor_time_shield(
                    context, st_now, TARGET_SYMBOL
                )
                if in_re_m:
                    return {"status": "HOLD_60S_REENTRY_TIME_SHIELD_IN_MUTEX"}

                min_upper_tier_p = min(b.book_price for b in now_buckets)
                exec_order_p = max(
                    0.01, math.floor((fresh_live_p + 1e-9) * 100.0) / 100.0
                )
                if min_upper_tier_p > 0.0 and exec_order_p > (
                    min_upper_tier_p + 1e-6
                ):
                    new_pass_cnt = (
                        safe_int(st_now.get("seed_protect_pass_cnt"), 0) + 1
                    )
                    new_day_pass = (
                        safe_int(st_now.get("daily_seed_protect_pass_cnt"), 0)
                        + 1
                    )
                    re_eval_epoch = mark_reentry_monitor_60s_cycle_shield(
                        context=context,
                        symbol=TARGET_SYMBOL,
                        eval_price=fresh_live_p,
                    )
                    await context.ledger.update_state(
                        TARGET_SYMBOL,
                        last_reentry_eval_ts=re_eval_epoch,
                        seed_protect_pass_cnt=new_pass_cnt,
                        daily_seed_protect_pass_cnt=new_day_pass,
                    )
                    return {
                        "status": "L2_ONLY_REENTRY_INVERSION_BLOCKED",
                        "signal_type": "HOLD_PREVENT_INVERSION",
                        "live_price": fresh_live_p,
                        "l2_ceiling_price": min_upper_tier_p,
                        "seed_protect_pass_cnt": new_day_pass,
                    }

                now_gp = pocket_from_dict(st_now.get("golden_pocket"))
                now_free_cash = max(
                    0.0, safe_float(st_now.get("free_cash_usd"), 0.0)
                )
                now_init_seed = max(
                    100.0,
                    safe_float(
                        st_now.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD
                    ),
                )
                now_inj_res = max(
                    0.0, safe_float(st_now.get("injected_reserve_usd"), 0.0)
                )
                now_inv_tot = sum(b.actual_cost_usd for b in now_buckets) + (
                    now_gp.actual_cost_usd if now_gp.is_active else 0.0
                )
                now_core_eq = max(
                    now_init_seed,
                    (now_free_cash + now_inv_tot) - now_inj_res,
                )

                quota_ref_p = max(
                    0.01,
                    safe_float(
                        reentry_sig.get("ref_anchor"),
                        anchor_p if anchor_p > 0.0 else exec_order_p,
                    ),
                )
                target_qty, portion_budget = compute_golden8_quota_qty(
                    anchor_price=quota_ref_p,
                    current_total_equity=now_core_eq,
                    initial_seed_usd=now_init_seed,
                    portion_mode=portion_mode,
                    exec_price=exec_order_p,
                )

                (
                    can_proceed_re,
                    eff_free_cash_re,
                    bp_usd_re,
                    guard_res_re,
                ) = await _check_and_execute_guard30_or_reserve_injection(
                    context=context,
                    st_now=st_now,
                    exec_order_p=exec_order_p,
                    portion_budget=portion_budget,
                    l1_actual_cost_usd=0.0,
                    is_dip_promotion=False,
                    is_vacant_l1_reentry=True,
                    trigger_desc=f"1층 공석 재장전({sig_type})",
                )
                if not can_proceed_re:
                    return {
                        "status": "HOLD_L2_ONLY_GUARD30_WAITING_RESERVE_DEPOSIT",
                        "signal_type": sig_type,
                        "guard_eval": guard_res_re,
                    }

                buy_qty, _est_spent = resolve_affordable_buy_qty(
                    target_qty=target_qty,
                    price_t=exec_order_p,
                    free_cash_usd=eff_free_cash_re,
                    broker_buying_power_usd=(
                        bp_usd_re if bp_usd_re > 0.0 else None
                    ),
                    max_portion_budget_usd=portion_budget,
                )

                if buy_qty <= 0:
                    re_eval_epoch = mark_reentry_monitor_60s_cycle_shield(
                        context=context,
                        symbol=TARGET_SYMBOL,
                        eval_price=fresh_live_p,
                    )
                    await context.ledger.update_state(
                        TARGET_SYMBOL,
                        last_reentry_eval_ts=re_eval_epoch,
                    )
                    return {"status": "HOLD_L2_ONLY_NO_CASH_FOR_REENTRY"}

                re_eval_epoch = mark_reentry_monitor_60s_cycle_shield(
                    context=context,
                    symbol=TARGET_SYMBOL,
                    eval_price=exec_order_p,
                )
                cid = generate_client_order_id(prefix="RE1FL")
                try:
                    ord_res = await context.api.create_order(
                        symbol=TARGET_SYMBOL,
                        side="BUY",
                        quantity=buy_qty,
                        price=exec_order_p,
                        order_type="LIMIT",
                        time_in_force="DAY",
                        client_order_id=cid,
                        enforce_daymarket_block=True,
                    )
                except Exception as exc:
                    await context.ledger.update_state(
                        TARGET_SYMBOL, last_reentry_eval_ts=re_eval_epoch
                    )
                    logger.warning(
                        "상단 그리드 보유 중 60초 주기 현재가 지정가 1층(REENTRY_1FL) 재장전 주문 예외: %s",
                        exc,
                    )
                    return {"status": "ORDER_ERROR", "error": str(exc)}

                oid = str(ord_res.get("orderId") or "").strip()
                await context.ledger.update_state(
                    TARGET_SYMBOL,
                    l1_target_quota_qty=buy_qty,
                    buy_order_id=oid,
                    client_order_id=cid,
                    ordered_qty=buy_qty,
                    buy_price=exec_order_p,
                    pending_portion_budget=portion_budget,
                    pending_lot_type="REENTRY_1FL",
                    pending_step_up_min_price=0.0,
                    last_modify_mono=time.monotonic(),
                    last_reentry_eval_ts=re_eval_epoch,
                )
                context.wakeup_event.set()
                logger.info(
                    "🔥 [SOXL 상단 %d개층 보유 중 60초 주기 현재가 지정가 1층 재장전(%s) 발주] %d주 @ 지정가 $%.2f <= 2층상한 $%.2f (1회예산 $%.2f · 직전익절 $%.2f · 이평 $%.2f · orderId=%s)",
                    len(now_buckets),
                    sig_type,
                    buy_qty,
                    exec_order_p,
                    min_upper_tier_p,
                    portion_budget,
                    quota_ref_p,
                    upper_wma_p,
                    oid,
                )
                return {
                    "status": "L2_HELD_HYBRID_REAL_1FL_ORDERED",
                    "signal_type": sig_type,
                    "orderId": oid,
                    "qty": buy_qty,
                    "price": exec_order_p,
                    "l2_ceiling_price": min_upper_tier_p,
                }

    # MODIFIED: 원장 그리드가 비어 있으나(len(buckets) == 0) 실계좌 잔고(h_qty)와 일시 시차가 존재하는 경우 IndexError 원천 차단
    if not buckets or not has_active_l1:
        return {
            "status": "WAIT_HOLDINGS_RECONCILE_SYNC",
            "ledger_grid_qty": len(buckets),
            "broker_qty": h_qty,
            "pocket_qty": gp.qty,
        }

    # -----------------------------------------------------------------------
    # [분기 B-0 · Case 77, Case 78 & Case 80 : 활성 1층 부분 체결 미체결 잔량(rem_quota_qty > 0) 존재 시]
    # -----------------------------------------------------------------------
    l1_target_q = max(
        buckets[0].qty, safe_int(st.get("l1_target_quota_qty"), 0)
    )
    rem_quota_qty = max(0, l1_target_q - buckets[0].qty)
    l1_book_p = round(buckets[0].book_price, 2)

    if rem_quota_qty > 0 and live_p <= (l1_book_p + 1e-6):
        async with context.in_memory_ordering_lock:
            async with context.dual_strike_mutex:
                st_now = context.ledger.get_state(TARGET_SYMBOL)
                if str(st_now.get("buy_order_id") or "").strip() or str(
                    st_now.get("sell_order_id") or ""
                ).strip():
                    return {"status": "ALREADY_ORDERING_IN_MUTEX"}

                now_buckets = buckets_from_dicts(st_now.get("buckets", []))
                if not now_buckets or not has_active_l1_bucket(now_buckets):
                    return {"status": "L1_STATE_CHANGED_IN_MUTEX"}

                in_s_sh, _ = is_within_post_sell_time_shield(
                    context, st_now, TARGET_SYMBOL
                )
                in_b_sh, _ = is_within_post_buy_time_shield(
                    context, st_now, TARGET_SYMBOL
                )
                if in_s_sh or in_b_sh:
                    return {"status": "HOLD_60S_TIME_SHIELD_IN_MUTEX"}

                now_target_q = max(
                    now_buckets[0].qty,
                    safe_int(st_now.get("l1_target_quota_qty"), 0),
                )
                now_rem_qty = max(0, now_target_q - now_buckets[0].qty)
                now_l1_book_p = round(now_buckets[0].book_price, 2)

                if now_rem_qty > 0:
                    fresh_live_p = await _fetch_fresh_current_soxl_price(
                        context, fallback_price=live_p
                    )
                    if fresh_live_p > 0.0 and fresh_live_p <= (
                        now_l1_book_p + 1e-6
                    ):
                        cur_lim_p = (
                            math.floor((fresh_live_p + 1e-9) * 100.0) / 100.0
                        )
                        exec_order_p = max(
                            0.01, min(cur_lim_p, now_l1_book_p)
                        )
                        topup_budget = round(
                            float(now_rem_qty) * now_l1_book_p, 4
                        )
                        now_free_cash = max(
                            0.0, safe_float(st_now.get("free_cash_usd"), 0.0)
                        )
                        one_share_top_cost = exec_order_p * (
                            1.0 + ROUND_TRIP_FEE_RATE_PCT / 100.0
                        )
                        now_gp_top = pocket_from_dict(
                            st_now.get("golden_pocket")
                        )
                        if (
                            now_gp_top.is_active
                            and now_free_cash < one_share_top_cost
                        ):
                            mark_reserve_deposit_check_shield(
                                context=context,
                                symbol=TARGET_SYMBOL,
                                clear_shield=False,
                            )
                            return {
                                "status": "HOLD_TOPUP_CASH_IN_GOLDEN_POCKET",
                                "golden_pocket_qty": now_gp_top.qty,
                            }

                        # MODIFIED [Case 77 & Case 78 : 예수금 API 0.0 반환 시 0.25초 재시도 및 None 우회 422 루프 원천 차단]:
                        raw_bp_top = await context.api.get_buying_power_usd(
                            safety_buffer_pct=0.2
                        )
                        if (
                            raw_bp_top <= 0.0
                            and now_free_cash >= one_share_top_cost
                        ):
                            await asyncio.sleep(0.25)
                            raw_bp_top = await context.api.get_buying_power_usd(
                                safety_buffer_pct=0.2
                            )

                        if raw_bp_top < one_share_top_cost:
                            mark_reserve_deposit_check_shield(
                                context=context,
                                symbol=TARGET_SYMBOL,
                                clear_shield=False,
                            )
                            return {
                                "status": "HOLD_TOPUP_INSUFFICIENT_BROKER_BP",
                                "broker_bp_usd": raw_bp_top,
                                "free_cash_usd": now_free_cash,
                            }

                        buy_qty_top, _ = resolve_affordable_buy_qty(
                            target_qty=now_rem_qty,
                            price_t=exec_order_p,
                            free_cash_usd=now_free_cash,
                            broker_buying_power_usd=raw_bp_top,
                            max_portion_budget_usd=topup_budget,
                        )
                        if buy_qty_top > 0:
                            eff_topup_budget = round(
                                float(buy_qty_top) * now_l1_book_p, 4
                            )
                            cid = generate_client_order_id(prefix="TOP1FL")
                            try:
                                ord_res = await context.api.create_order(
                                    symbol=TARGET_SYMBOL,
                                    side="BUY",
                                    quantity=buy_qty_top,
                                    price=exec_order_p,
                                    order_type="LIMIT",
                                    time_in_force="DAY",
                                    client_order_id=cid,
                                    enforce_daymarket_block=True,
                                )
                                oid = str(
                                    ord_res.get("orderId") or ""
                                ).strip()
                                await context.ledger.update_state(
                                    TARGET_SYMBOL,
                                    l1_target_quota_qty=now_target_q,
                                    buy_order_id=oid,
                                    client_order_id=cid,
                                    ordered_qty=buy_qty_top,
                                    buy_price=exec_order_p,
                                    pending_portion_budget=eff_topup_budget,
                                    pending_lot_type="TOPUP_1FL",
                                    pending_step_up_min_price=0.0,
                                    last_modify_mono=time.monotonic(),
                                )
                                context.wakeup_event.set()
                                logger.info(
                                    "🎯 [Case 78 SOXL 1.5초 모니터 1층 단가($%.2f) 재도래 포착 -> 미체결 잔량(TOPUP_1FL) 지정가 발주] +%d주 @ 지정가 $%.2f (기보유 %d주 / 목표 %d주 · 60초 지정가 대기 개시 · orderId=%s)",
                                    now_l1_book_p,
                                    buy_qty_top,
                                    exec_order_p,
                                    now_buckets[0].qty,
                                    now_target_q,
                                    oid,
                                )
                                return {
                                    "status": "L1_PARTIAL_TOPUP_ORDERED",
                                    "orderId": oid,
                                    "qty": buy_qty_top,
                                    "price": exec_order_p,
                                    "l1_cur_qty": now_buckets[0].qty,
                                    "l1_target_quota_qty": now_target_q,
                                }
                            except Exception as exc:
                                mark_reserve_deposit_check_shield(
                                    context=context,
                                    symbol=TARGET_SYMBOL,
                                    clear_shield=False,
                                )
                                logger.warning(
                                    "Case 78 1층 미체결 잔량(TOPUP_1FL) 지정가 주문 예외(60초 쿨다운): %s",
                                    exc,
                                )
                                return {
                                    "status": "TOPUP_ORDER_ERROR",
                                    "error": str(exc),
                                }

    # -----------------------------------------------------------------------
    # [분기 B-2 : 활성 1층 보유 중 (has_active_l1_bucket(buckets) == True)]
    # -> 04:07 EST 기점 10분 고정 매수 게이트 신규 버킷 도래 시 정적 기억 최저가 4단 와이드 OR STEP2X_15PCT_C20 스텝업 추매 판정!
    # -----------------------------------------------------------------------
    is_gate_open, cur_bucket_id, today_str, b_info = (
        evaluate_buy_gate_bucket_status(
            now_est=dt_now,
            buy_interval_min=buy_interval_min,
            last_evaluated_bucket_id=safe_int(
                st.get("last_evaluated_buy_bucket_id"), -1
            ),
            last_evaluated_date=str(st.get("last_evaluated_date") or ""),
        )
    )

    if not is_gate_open:
        if rem_quota_qty > 0:
            return {
                "status": "MONITORING_1_5S_L1_TOPUP_PRICE",
                "l1_cur_qty": buckets[0].qty,
                "l1_target_quota_qty": l1_target_q,
                "l1_rem_quota_qty": rem_quota_qty,
                "l1_book_price": l1_book_p,
                "live_price": live_p,
            }
        return {
            "status": "WAIT_NEXT_BUY_GATE",
            "next_gate": b_info.get("next_gate_hm_str", ""),
        }

    fresh_live_p = await _fetch_fresh_current_soxl_price(
        context, fallback_price=live_p
    )
    if fresh_live_p <= 0.0:
        return {"status": "NO_FRESH_LIVE_PRICE"}

    held_lots = sum(b.lot_count for b in buckets)
    drop_buy_pct, _, _ = get_golden8_prog_thresholds(
        held_lots=held_lots, threshold_mode=threshold_mode
    )

    anchor_p = safe_float(st.get("anchor_price"), buckets[0].book_price)
    cycle_min_p = safe_float(st.get("cycle_min_buy_price"), anchor_p)
    eff_step_drop = (
        0.0 if unlock_mode in ("STATIC", "NONE", "OFF") else STEP_UP_2X_DROP_PCT
    )

    dip_eval = evaluate_step_up_2x_dip_signal(
        live_price=fresh_live_p,
        buckets=buckets,
        anchor_price=anchor_p,
        cycle_min_buy_price=cycle_min_p,
        drop_buy_pct=drop_buy_pct,
        free_cash_usd=free_cash,
        realized_equity_usd=realized_equity,
        step_up_drop_pct=eff_step_drop,
        min_cash_ratio=STEP_UP_2X_MIN_CASH_RATIO,
        min_rebound_mult=STEP_UP_2X_MIN_REBOUND_MULT,
        max_tiers_for_unlock=STEP_UP_2X_MAX_TIERS,
    )
    ref_buy_anchor = safe_float(
        dip_eval.get("ref_static_anchor"), buckets[0].book_price
    )
    chg_for_buy_pct = safe_float(dip_eval.get("chg_static_pct"), 0.0)
    lot_tag = "DIP_1FL"

    if not bool(dip_eval.get("should_buy")):
        # MODIFIED [Case 75 & Case 77]:
        # 이미 시드고갈 입금 대기(waiting_reserve_deposit == True) 상태에서 60초 주기로 깨어났는데
        # 가격이 일시 반등해 있는 경우에는 10분 버킷(last_evaluated_buy_bucket_id)을 소모하거나
        # 매 60초마다 패스 카운터를 디스크에 기록하지 않고 인메모리 60초 입금 감시 쉴드만 재장전한다!
        if bool(st.get("waiting_reserve_deposit", False)):
            mark_reserve_deposit_check_shield(
                context=context, symbol=TARGET_SYMBOL, clear_shield=False
            )
            return {
                "status": "HOLD_WAITING_RESERVE_DEPOSIT_PRICE_REBOUND",
                "trigger_tag": dip_eval.get("trigger_tag", "HOLD"),
                "ref_buy_anchor": round(ref_buy_anchor, 4),
                "chg_pct": round(chg_for_buy_pct, 2),
                "required_drop_pct": drop_buy_pct,
            }

        new_pass_cnt = safe_int(st.get("seed_protect_pass_cnt"), 0) + 1
        new_day_pass = safe_int(st.get("daily_seed_protect_pass_cnt"), 0) + 1
        await context.ledger.update_state(
            TARGET_SYMBOL,
            last_evaluated_buy_bucket_id=cur_bucket_id,
            last_evaluated_date=today_str,
            seed_protect_pass_cnt=new_pass_cnt,
            daily_seed_protect_pass_cnt=new_day_pass,
        )
        return {
            "status": "SEED_PROTECT_PASSED",
            "trigger_tag": dip_eval.get("trigger_tag", "HOLD"),
            "ref_buy_anchor": round(ref_buy_anchor, 4),
            "chg_pct": round(chg_for_buy_pct, 2),
            "required_drop_pct": drop_buy_pct,
            "step_up_eligible": bool(dip_eval.get("step_up_eligible", False)),
            "stepped_min_price": safe_float(
                dip_eval.get("stepped_min_price"), 0.0
            ),
            "seed_protect_pass_cnt": new_day_pass,
        }

    async with context.in_memory_ordering_lock:
        async with context.dual_strike_mutex:
            st_now = context.ledger.get_state(TARGET_SYMBOL)
            if str(st_now.get("buy_order_id") or "").strip() or str(
                st_now.get("sell_order_id") or ""
            ).strip():
                return {"status": "ALREADY_ORDERING_IN_MUTEX"}

            now_buckets = buckets_from_dicts(st_now.get("buckets", []))
            if not now_buckets or not has_active_l1_bucket(now_buckets):
                return {"status": "L1_STATE_CHANGED_IN_MUTEX"}

            gate_open_m, _, _, _ = evaluate_buy_gate_bucket_status(
                now_est=dt_now,
                buy_interval_min=buy_interval_min,
                last_evaluated_bucket_id=safe_int(
                    st_now.get("last_evaluated_buy_bucket_id"), -1
                ),
                last_evaluated_date=str(
                    st_now.get("last_evaluated_date") or ""
                ),
            )
            if not gate_open_m:
                return {"status": "BUCKET_ALREADY_EVALUATED_IN_MUTEX"}

            in_s_sh, _ = is_within_post_sell_time_shield(
                context, st_now, TARGET_SYMBOL
            )
            in_b_sh, _ = is_within_post_buy_time_shield(
                context, st_now, TARGET_SYMBOL
            )
            if in_s_sh or in_b_sh:
                return {"status": "HOLD_60S_TIME_SHIELD_IN_MUTEX"}

            now_held_lots = sum(b.lot_count for b in now_buckets)
            now_drop_pct, _, _ = get_golden8_prog_thresholds(
                held_lots=now_held_lots, threshold_mode=threshold_mode
            )
            now_gp = pocket_from_dict(st_now.get("golden_pocket"))
            now_free_cash = max(0.0, safe_float(st_now.get("free_cash_usd"), 0.0))
            now_init_seed = max(
                100.0,
                safe_float(
                    st_now.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD
                ),
            )
            now_cum_net = safe_float(
                st_now.get("cumulative_realized_net_usd"), 0.0
            )
            now_inj_res = max(
                0.0, safe_float(st_now.get("injected_reserve_usd"), 0.0)
            )
            now_real_eq = max(100.0, now_init_seed + now_cum_net)
            now_inv_tot = sum(b.actual_cost_usd for b in now_buckets) + (
                now_gp.actual_cost_usd if now_gp.is_active else 0.0
            )
            now_core_eq = max(
                now_init_seed,
                (now_free_cash + now_inv_tot) - now_inj_res,
            )

            now_dip_eval = evaluate_step_up_2x_dip_signal(
                live_price=fresh_live_p,
                buckets=now_buckets,
                anchor_price=safe_float(
                    st_now.get("anchor_price"), now_buckets[0].book_price
                ),
                cycle_min_buy_price=safe_float(
                    st_now.get("cycle_min_buy_price"), 0.0
                ),
                drop_buy_pct=now_drop_pct,
                free_cash_usd=now_free_cash,
                realized_equity_usd=now_real_eq,
                step_up_drop_pct=eff_step_drop,
                min_cash_ratio=STEP_UP_2X_MIN_CASH_RATIO,
                min_rebound_mult=STEP_UP_2X_MIN_REBOUND_MULT,
                max_tiers_for_unlock=STEP_UP_2X_MAX_TIERS,
            )
            if not bool(now_dip_eval.get("should_buy")):
                return {"status": "DIP_SIGNAL_CHANGED_IN_MUTEX"}

            is_step_up_unlock = bool(
                now_dip_eval.get("is_step_up_unlock", False)
            )
            trigger_tag = str(
                now_dip_eval.get("trigger_tag") or "STATIC_NEW_LOW"
            )
            quota_ref_p = max(
                0.01,
                safe_float(
                    now_dip_eval.get("quota_ref_price"), ref_buy_anchor
                ),
            )
            stepped_min_p = safe_float(
                now_dip_eval.get("stepped_min_price"), 0.0
            )

            if is_step_up_unlock and stepped_min_p > 0.0:
                max_trigger_p = (
                    math.floor((stepped_min_p + 1e-9) * 100.0) / 100.0
                )
            else:
                max_trigger_p = (
                    math.floor(
                        (
                            ref_buy_anchor * (1.0 + now_drop_pct / 100.0)
                            + 1e-9
                        )
                        * 100.0
                    )
                    / 100.0
                )
            cur_limit_p = (
                math.floor((fresh_live_p + 1e-9) * 100.0) / 100.0
            )
            exec_order_p = max(0.01, min(cur_limit_p, max_trigger_p))

            target_qty, portion_budget = compute_golden8_quota_qty(
                anchor_price=quota_ref_p,
                current_total_equity=now_core_eq,
                initial_seed_usd=now_init_seed,
                portion_mode=portion_mode,
                exec_price=exec_order_p,
            )

            (
                can_proceed_dip,
                eff_free_cash_dip,
                bp_usd_dip,
                guard_res_dip,
            ) = await _check_and_execute_guard30_or_reserve_injection(
                context=context,
                st_now=st_now,
                exec_order_p=exec_order_p,
                portion_budget=portion_budget,
                l1_actual_cost_usd=now_buckets[0].actual_cost_usd,
                is_dip_promotion=True,
                is_vacant_l1_reentry=False,
                trigger_desc=f"{now_held_lots + 1}회차 추매({trigger_tag})",
            )
            if not can_proceed_dip:
                return {
                    "status": "HOLD_DIP_GUARD30_WAITING_RESERVE_DEPOSIT",
                    "trigger_tag": trigger_tag,
                    "guard_eval": guard_res_dip,
                }

            buy_qty, _est_spent = resolve_affordable_buy_qty(
                target_qty=target_qty,
                price_t=exec_order_p,
                free_cash_usd=eff_free_cash_dip,
                broker_buying_power_usd=(
                    bp_usd_dip if bp_usd_dip > 0.0 else None
                ),
                max_portion_budget_usd=portion_budget,
            )

            if buy_qty <= 0:
                return {"status": "CASH_EXHAUSTED_SKIP"}

            cid_prefix = (
                f"U{now_held_lots + 1}L"
                if is_step_up_unlock
                else f"B{now_held_lots + 1}L"
            )
            cid = generate_client_order_id(prefix=cid_prefix)
            try:
                ord_res = await context.api.create_order(
                    symbol=TARGET_SYMBOL,
                    side="BUY",
                    quantity=buy_qty,
                    price=exec_order_p,
                    order_type="LIMIT",
                    time_in_force="DAY",
                    client_order_id=cid,
                    enforce_daymarket_block=True,
                )
            except Exception as exc:
                logger.error(
                    "SOXL 10분 게이트(%s) 현재가 지정가 그리드 추매 주문 발사 예외: %s",
                    trigger_tag,
                    exc,
                )
                return {"status": "BUY_ORDER_ERROR", "error": str(exc)}

            oid = str(ord_res.get("orderId") or "").strip()
            await context.ledger.update_state(
                TARGET_SYMBOL,
                l1_target_quota_qty=buy_qty,
                buy_order_id=oid,
                client_order_id=cid,
                ordered_qty=buy_qty,
                buy_price=exec_order_p,
                pending_portion_budget=portion_budget,
                pending_lot_type=lot_tag,
                pending_step_up_min_price=(
                    round(stepped_min_p, 4) if is_step_up_unlock else 0.0
                ),
                last_evaluated_buy_bucket_id=cur_bucket_id,
                last_evaluated_date=today_str,
                last_modify_mono=time.monotonic(),
            )
            context.wakeup_event.set()
            if is_step_up_unlock:
                logger.info(
                    "🔓 [Case 76 SOXL 스텝업 저가 해금(%s) 추매 발주] %d주 @ 지정가 $%.2f (1층 $%.2f 대비 -15%% 해금가 $%.2f · 구저가 $%.2f[%.2fx] · 현금비중 %.1f%% · orderId=%s)",
                    trigger_tag,
                    buy_qty,
                    exec_order_p,
                    now_buckets[0].book_price,
                    stepped_min_p,
                    ref_buy_anchor,
                    safe_float(now_dip_eval.get("rebound_mult"), 2.0),
                    safe_float(now_dip_eval.get("cash_ratio_pct"), 20.0),
                    oid,
                )
            else:
                logger.info(
                    "🔵 [SOXL %d회차 현재가 지정가 그리드 추매 발주] %d주 @ 지정가 $%.2f (기억저가 $%.2f 대비 %.2f%% · orderId=%s)",
                    now_held_lots + 1,
                    buy_qty,
                    exec_order_p,
                    ref_buy_anchor,
                    chg_for_buy_pct,
                    oid,
                )
            return {
                "status": "QUOTA_DIP_BUY_ORDERED",
                "trigger_tag": trigger_tag,
                "is_step_up_unlock": is_step_up_unlock,
                "orderId": oid,
                "qty": buy_qty,
                "price": exec_order_p,
                "ref_buy_anchor": round(quota_ref_p, 4),
                "chg_pct": round(chg_for_buy_pct, 2),
                "drop_threshold_pct": now_drop_pct,
            }


# 하위 호환 별칭 (외부 모듈에서 구 함수명으로 호출하더라도 신규 게이트 엔진으로 안전 직결)
execute_premarket_vwap_sniper_plugin = execute_seed_protected_buy_gate_plugin
sync_dynamic_vwap_buy_order_modify = sync_pending_buy_order_plugin
