# -*- coding: utf-8 -*-
"""
# MODIFIED: tg_ui_plugin.py (Part 1/2 — 🗡️ [모의] 암살자 실시간 관제 블록 연동 · /assassin & /reset_assassin 탑재 · Case 91 복리/단리 전환 · Case 92 1층 공석 돌파 RSI<=50 표출)
인피니트 스노우볼 (Infinite Snowball) v3.0 — 순수 롱(🐂 SOXL 단독) 매수 04:07 ~ 16:00 EST 제한
(정규장 마감 30분 전 15:30 ~ 16:00 EST 본·서브 0주 새 사이클 첫 1층 진입 및 상단층 보유 중 1층 공석 +1.0% 돌파 추격 동시 차단 ·
04:07 ~ 15:29 EST 1층 공석 +1.0% 돌파 시 1분봉 Wilder RSI(14) <= 50.0 필터 결합 ·
2층 단가 이하 -1.0% 눌림목 재장전 및 10분 게이트 추매/잔량보충 100% 허용 · Case 84, Case 88, Case 92) &
익절 매도 24시간 전 세션(프리마켓 + 정규장 + 애프터마켓 + 데이마켓) 확장 오버나이트 7층 골디락스 본 그리드
(👑 06_L2L7_RATCHET_8PCT : 구 1층 보존 + 구 2층 + 구 7층 통합 후 평단 오름차순 중간층 재배치 & 사이클 최고 도달 회차 단차 잠금 · Case 87) +
🛡️ 스위치 없는 100% 기본 상시 적용(Default ON) 3층 서브 그리드
(13_SUB_L1L3_RESV05_CAP4L : 본 그리드 5일 무매매 시 4.0% 정량 · 0.5회분 보호예수 · 최대 4회분[16%] 상한 캡 · 3층 초과 시 구 1층 + 구 3층 양끝 합병 · 10일/-10% 저가해금 · Case 88) +
🗡️ [모의 ⇄ 실전 Dual-Ready] 암살자(Assassin) 상시 작동 관제 연동 (assassin_plugin.py)
텔레그램 관제탑 모바일 가로폭(36자) 칼맞춤 초슬림 UI 렌더러(층별 투입자산 $ · 10칸 시드 배분 게이지 🟦🟨🟩 · 현재 사이클 단위 실현수익 vs 전체 누적 수익 · 재고 평가착시 3단 해부 · 전량졸업 예정자산 🎓 탑재) · 계좌별 수수료율(편도/왕복) 실시간 표출 · 불사조 롱폴링(Immortal Telegram Polling) 및 명령어·콜백 비동기 컨트롤러 코어 모듈 (Step 10 / 13)
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    import httpx  # type: ignore

    _HTTPX_AVAILABLE = True
except Exception:
    httpx = None  # type: ignore
    _HTTPX_AVAILABLE = False

from assassin_plugin import (
    build_assassin_detail_dashboard_html,
    ensure_assassin_ledger,
    format_assassin_slim_radar_block,
)
from defense_plugin import (
    reconcile_stratum_with_broker_holdings_plugin,
    relock_stratum_on_bot_resume,
)
from plugin_updater import (
    execute_git_pull_and_preflight,
    perform_self_restart_execv,
    read_persisted_tg_offset_sync,
    trigger_graceful_restart,
    write_persisted_tg_offset_sync,
)
from quant_engine import (
    MAX_RESERVE_PORTIONS,
    SUB_FROZEN_DAYS_TRIGGER,
    SUB_MAX_TIERS_3,
    SUB_MAX_TOTAL_LOTS_4,
    summarize_stratum_portfolio,
)
from quant_indicators_plugin import (
    compute_soxl_quant_metrics_1m,
    evaluate_buy_gate_bucket_status,
    get_market_session_label,
    is_active_buy_window,
    is_active_sell_window,
    is_extended_sell_only_window,
    is_late_regular_new_cycle_cutoff_window,
    refresh_metrics_with_live_tick,
)
from sniper_exit_plugin import (
    is_within_post_buy_time_shield,
    is_within_post_sell_time_shield,
    is_within_sell_monitor_time_shield,
)
from sniper_plugin import (
    is_within_reentry_monitor_time_shield,
    is_within_reserve_deposit_check_shield,
    is_within_sub_reentry_monitor_time_shield,
    mark_reserve_deposit_check_shield,
)
from toss_api import (
    DEFAULT_INITIAL_SEED_USD,
    EST_TZ,
    LOCKED_BUY_INTERVAL_MIN,
    TARGET_SYMBOL,
    get_bot_base_dir,
    get_folder_slug,
    safe_float,
    safe_int,
)

# [Case 75]: 매 1.5초 API 조회 및 텔레그램 폴링 시 발생하는 httpx / httpcore 의 INFO 로그 폭탄을 WARNING 으로 묵음화
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger("toss_sniper.tg_ui_plugin")

# toss_api.py 와의 AST 심볼 임포트 불일치를 원천 차단하기 위해 기본 환율 상수를 모듈 내부에 직접 정의
KRW_PER_USD_DEFAULT: float = 1380.0

# Case 68: [💵 기준 시드머니($) 설정] 버튼 클릭 후 숫자 입력을 허용하는 유효 시간(초)
SEED_INPUT_PROMPT_TIMEOUT_SEC: float = 300.0

# Case 91: 운용 정량모드 상수 (복리 COMP_08PCT vs 단리 SIMPLE_08PCT)
PORTION_MODE_COMPOUND: str = "COMP_08PCT"
PORTION_MODE_SIMPLE: str = "SIMPLE_08PCT"


# ---------------------------------------------------------------------------
# [유틸리티] HTML 이스케이프 · DST 배지 · Case 68 폴더 식별자 및 안전 시드 추출
# ---------------------------------------------------------------------------
def escape_html(val: Any) -> str:
    return html.escape(str(val if val is not None else ""), quote=False)


def _is_simple_portion_mode(st_or_mode: Any) -> bool:
    if isinstance(st_or_mode, dict):
        m = str(st_or_mode.get("portion_mode") or PORTION_MODE_COMPOUND)
    else:
        m = str(st_or_mode or PORTION_MODE_COMPOUND)
    return m.upper().strip() in ("SIMPLE_08PCT", "SIMPLE", "FIXED_800")


def _get_dst_badge(now_est: Optional[datetime] = None) -> str:
    dt = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    tz_name = dt.tzname() or "EST"
    if "EDT" in tz_name.upper():
        return "☀️서머타임 ON (EDT)"
    return "❄️서머타임 OFF (EST)"


def _resolve_display_seed(st: Dict[str, Any]) -> float:
    """
    🚨 Case 68:
    initial_seed_usd 가 0.0 또는 비정상 초기값일 때 $100.0 으로 잘못 표시되지 않도록 방어한다.
    """
    raw_s = safe_float((st or {}).get("initial_seed_usd"), 0.0)
    explicit_100 = bool((st or {}).get("seed_explicitly_set_100", False))
    if raw_s > 100.0:
        return round(raw_s, 4)
    if abs(raw_s - 100.0) < 1e-6 and explicit_100:
        return 100.0
    return DEFAULT_INITIAL_SEED_USD


def _resolve_folder_identity_badge(
    context: Optional[Any], st: Optional[Dict[str, Any]] = None
) -> Tuple[str, str]:
    """
    Case 68:
    현재 봇이 가동 중인 폴더 식별자(folder_slug)와 고유 원장 파일명을 반환한다.
    """
    slug = ""
    primary_name = ""
    if context is not None and hasattr(context, "ledger"):
        slug = str(getattr(context.ledger, "folder_slug", "") or "").strip()
        p_fp = str(
            getattr(context.ledger, "primary_filepath", "") or ""
        ).strip()
        if p_fp:
            primary_name = os.path.basename(p_fp)

    if not slug and isinstance(st, dict):
        slug = str(st.get("folder_slug") or "").strip()

    if not slug:
        base_d = (
            getattr(context, "base_dir", None) if context is not None else None
        )
        slug = get_folder_slug(base_d)

    if not primary_name:
        primary_name = f"soxl_stratum_ledger_{slug}.json"

    return slug, primary_name


def _format_case67_quota_badge(summary: Dict[str, Any]) -> str:
    """
    # [모바일 36자 가로폭 칼맞춤 & Case 67]:
    직관적인 매수 예정 주수만 간결하게 반환한다.
    """
    next_qty = safe_int(summary.get("next_target_qty"), 1)
    return f"<b>{next_qty}주</b>"


def _format_sub_quota_badge(summary: Dict[str, Any]) -> str:
    """
    # [모바일 36자 가로폭 칼맞춤 & Case 88]:
    서브 그리드 4% 정량 매수 예정 주수를 간결하게 반환한다.
    """
    sub_next_qty = safe_int(summary.get("sub_next_target_qty"), 1)
    return f"<b>{sub_next_qty}주</b>"


def _build_main_reply_keyboard() -> Dict[str, Any]:
    """
    # [4대 핵심 메뉴(2x2) 단일화]:
    사용자 중심 4대 핵심 버튼(스나이퍼 레이더 · 잔고 동기화 · 전술 제어반 · 시스템 업데이트)으로 구성한다.
    """
    return {
        "keyboard": [
            [
                {"text": "🔫 스나이퍼 레이더"},
                {"text": "🔄 잔고 동기화"},
            ],
            [
                {"text": "⚙️ 전술 제어반"},
                {"text": "🚀 시스템 업데이트"},
            ],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def _build_radar_inline_keyboard() -> Optional[Dict[str, Any]]:
    """
    하단 고정 메뉴(_build_main_reply_keyboard)와 중복되는 인라인 버튼은 생성하지 않는다.
    """
    return None


def _build_settlement_inline_keyboard(
    is_active: bool,
    *args: Any,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    # MODIFIED [Case 64, Case 88, Case 91 & 🗡️ 모의 암살자 관제 버튼]:
    1) [작동 ON / OFF 전환 버튼 (toggle_bot_active)]
    2) [📈 자산증식형(복리) ⇄ 💵 인출형(단리) 전환 버튼 (toggle_portion_mode)]
    3) [💵 기준 시드머니($) 설정 버튼 (prompt_seed_input)]
    4) [🗡️ [모의] 암살자 상세 관제 보드 (cmd_assassin)]
    """
    portion_mode = kwargs.get("portion_mode")
    if portion_mode is None and args:
        portion_mode = args[0]
    is_simple = _is_simple_portion_mode(portion_mode)

    power_label = (
        "🔴 스나이퍼 작동 OFF 로 전환"
        if is_active
        else "🟢 스나이퍼 작동 ON 으로 전환"
    )
    mode_label = (
        "🔄 현재: 💵인출형(단리) ➔ 📈복리로 전환"
        if is_simple
        else "🔄 현재: 📈자산증식형(복리) ➔ 💵인출형 전환"
    )
    return {
        "inline_keyboard": [
            [
                {"text": power_label, "callback_data": "toggle_bot_active"},
            ],
            [
                {"text": mode_label, "callback_data": "toggle_portion_mode"},
            ],
            [
                {
                    "text": "💵 기준 시드머니($) 설정",
                    "callback_data": "prompt_seed_input",
                },
            ],
            [
                {
                    "text": "🗡️ [모의] 암살자 상세 관제 (/assassin)",
                    "callback_data": "cmd_assassin",
                },
            ],
        ]
    }


# ---------------------------------------------------------------------------
# [핵심 1] 관제 보드 메시지 빌더 (모바일 36자 가로폭 1줄 수납 칼정렬 UI)
# ---------------------------------------------------------------------------
def build_start_schedule_message(
    st: Dict[str, Any],
    now_est: Optional[datetime] = None,
    context: Optional[Any] = None,
) -> str:
    """
    # [초기 /start 진입 시 4대 핵심 메뉴 + /assassin 안내]:
    """
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    dst_str = _get_dst_badge(dt_now)

    lines = [
        f"🐂 <b>[SOXL 스나이퍼 ({escape_html(dst_str)})]</b>",
        "──────────────",
        "🔫 <b>스나이퍼 레이더</b> : 타점 · 지층 · 암살자 요약",
        "🔄 <b>잔고 동기화</b> : 잔고 · 예수금 · 수익 해부",
        "⚙️ <b>전술 제어반</b> : 전원 · 복리/단리 · 시드설정",
        "🚀 <b>시스템 업데이트</b> : 최신 코드 동기화",
        "🗡️ <code>/assassin</code> : [모의] 암살자 정찰 · 진성게이트 상세",
    ]
    return "\n".join(lines)


def _format_multi_grid_stratum_lines(
    summary: Dict[str, Any],
    live_price: float,
    is_ext_sell_only: bool = False,
    is_late_cutoff: bool = False,
    live_rsi_14: float = 50.0,
) -> List[str]:
    """
    # MODIFIED [📌 ① 모바일 36자 가로폭 1줄 칼맞춤 층별 투입자산($) 시각화 지층 렌더러 · Case 71 ~ 92]:
    모든 지층(1층 공격수 · 2~7층 통합이평 · 2~7층 개별/합병층)에
    주수뿐만 아니라 실제 투입된 달러 자산 규모($)를 함께 표출하며,
    1층 공석 시 +1.0% 돌파 RSI(14) <= 50.0 필터 상태(Case 92)를 직관적으로 시각화한다.
    """
    held_sh = safe_int(summary.get("held_shares"), 0)
    buckets = summary.get("buckets", [])
    lines: List[str] = []

    if held_sh <= 0 or not buckets:
        if is_ext_sell_only:
            lines.append(
                "⚪ <b>[본그리드: 0주]</b> 🔒장외 매수잠금 (04:07 해금)"
            )
        elif is_late_cutoff:
            lines.append(
                "⚪ <b>[본그리드: 0주]</b> 🔒15:30 ~ 16:00 신규진입 차단"
            )
        else:
            lines.append(
                "⚪ <b>[본그리드: 0주]</b> 60초 대기 후 1층 진입 대기"
            )
        return lines

    active_l1 = bool(summary.get("has_active_l1", True))
    rise_u_pct = safe_float(summary.get("rise_sell_l2_pct"), 1.00)
    upper_buckets = buckets[1:] if active_l1 else buckets[:]
    has_upper_tiers = bool(len(upper_buckets) > 0)

    if active_l1:
        b1 = buckets[0]
        l1_t = safe_float(summary.get("l1_target_price"), 0.0)
        l1_g = safe_float(summary.get("l1_gain_pct"), 0.0)
        g1_sign = "+" if l1_g >= 0.0 else ""
        l1_rem_q = safe_int(summary.get("l1_rem_quota_qty"), 0)
        l1_target_q = safe_int(summary.get("l1_target_quota_qty"), b1.qty)
        if l1_rem_q > 0 and l1_target_q > b1.qty:
            l1_qty_label = f"{b1.qty}/{l1_target_q}주"
        else:
            l1_qty_label = f"{b1.qty}주"

        l1_ov_lock_note = (
            "·🔒" if (is_ext_sell_only and has_upper_tiers) else ""
        )
        lines.append(
            f"⚡ <b>[1층: {l1_qty_label}·${b1.actual_cost_usd:,.0f}]</b> "
            f"<b>${b1.book_price:.2f}</b> ➔ <b>${l1_t:.2f}</b> ({g1_sign}{l1_g:.2f}%{l1_ov_lock_note})"
        )
    else:
        l2_cap = safe_float(
            summary.get("l2_ceiling_price"),
            safe_float(summary.get("min_indiv_upper_price"), 0.0),
        )
        cap_note = f" (상한 ${l2_cap:.2f})" if l2_cap > 0.0 else ""
        if is_ext_sell_only:
            lines.append(
                f"⚡ <b>[1층: 공석]</b> 🔒장외잠금 · 04:07 재장전{cap_note}"
            )
        elif is_late_cutoff:
            lines.append(
                f"⚡ <b>[1층: 공석]</b> 🛡️돌파차단 · 눌림(-1%) 감시{cap_note}"
            )
        elif live_rsi_14 > 50.0:
            lines.append(
                f"⚡ <b>[1층: 공석]</b> 눌림(-1%)/🛡️돌파과열차단(RSI {live_rsi_14:.1f}>50){cap_note}"
            )
        else:
            lines.append(
                f"⚡ <b>[1층: 공석]</b> 1분주기 눌림(-1%)/돌파(RSI<=50){cap_note}"
            )

    if upper_buckets:
        u_cnt = len(upper_buckets)
        u_qty = safe_int(
            summary.get("upper_qty"), sum(b.qty for b in upper_buckets)
        )
        u_cost = safe_float(
            summary.get("upper_actual_cost_usd"),
            sum(b.actual_cost_usd for b in upper_buckets),
        )
        u_wma_p = safe_float(summary.get("upper_wma_price"), 0.0)
        u_wma_t = safe_float(summary.get("upper_wma_target_price"), 0.0)
        u_gain = safe_float(summary.get("l2_gain_pct"), 0.0)
        ug_sign = "+" if u_gain >= 0.0 else ""
        tier_range_label = "2층" if u_cnt == 1 else f"2~{u_cnt + 1}층"
        lines.append(
            f"📦 <b>[{tier_range_label}: {u_qty}주·${u_cost:,.0f}]</b> "
            f"<b>${u_wma_p:.2f}</b> ➔ 졸업 <b>${u_wma_t:.2f}</b> ({ug_sign}{u_gain:.2f}%)"
        )

        indiv_ov_lock_note = "·🔒" if is_ext_sell_only else ""
        for idx_u, bu in enumerate(upper_buckets):
            t_no = idx_u + 2
            bu_t = (
                math.ceil(
                    (bu.book_price * (1.0 + rise_u_pct / 100.0) - 1e-9)
                    * 100.0
                )
                / 100.0
            )
            bu_g = (
                ((live_price - bu.book_price) / bu.book_price) * 100.0
                if (live_price > 0.0 and bu.book_price > 0.0)
                else 0.0
            )
            bg_s = "+" if bu_g >= 0.0 else ""
            if bu.lot_count > 1:
                tier_tag = (
                    f"{t_no}층(👑{bu.lot_count}회·${bu.actual_cost_usd:,.0f})"
                )
            else:
                tier_tag = f"{t_no}층({bu.qty}주·${bu.actual_cost_usd:,.0f})"
            lines.append(
                f"  ▫️ <b>{tier_tag}</b>: ${bu.book_price:.2f} "
                f"➔ <b>${bu_t:.2f}</b> ({bg_s}{bu_g:.2f}%{indiv_ov_lock_note})"
            )

    return lines


def _format_sub_grid_stratum_lines(
    summary: Dict[str, Any],
    live_price: float,
    is_ext_sell_only: bool = False,
    is_late_cutoff: bool = False,
) -> List[str]:
    """
    # [📌 ① & Case 88 : 3층 서브그리드 층별 투입자산($) 및 36자 가로폭 1줄 칼맞춤 렌더러]:
    """
    held_sh_main = safe_int(summary.get("held_shares"), 0)
    sub_sh = safe_int(summary.get("sub_held_shares"), 0)
    sub_inv_usd = safe_float(summary.get("actual_invested_sub_usd"), 0.0)
    sub_buckets = summary.get("sub_buckets", [])
    sub_lots = safe_int(summary.get("sub_held_lots"), 0)
    sub_ratchet_lots = safe_int(
        summary.get("sub_ratchet_max_lots"), sub_lots
    )
    sub_max_lots = safe_int(
        summary.get("sub_max_total_lots"), SUB_MAX_TOTAL_LOTS_4
    )
    sub_tiers = safe_int(summary.get("sub_held_tiers"), 0)
    main_frozen = safe_int(summary.get("main_consec_frozen_days"), 0)
    sub_comp = safe_int(summary.get("sub_completed_cycles"), 0)
    avail_idle = safe_float(summary.get("avail_idle_cash_usd"), 0.0)
    lines: List[str] = []

    if sub_sh <= 0 or not sub_buckets:
        if held_sh_main > 0 and main_frozen >= SUB_FROZEN_DAYS_TRIGGER:
            wait_note = (
                "🔒04:07 출격"
                if is_ext_sell_only
                else (
                    "🔒익일 출격"
                    if is_late_cutoff
                    else f"유휴 ${avail_idle:,.0f} 진입대기"
                )
            )
            lines.append(
                f"🛡️ <b>[서브 가동 ({main_frozen}/{SUB_FROZEN_DAYS_TRIGGER}일)]</b> {wait_note}"
            )
        else:
            grad_note = f"·졸업{sub_comp}회" if sub_comp > 0 else ""
            lines.append(
                f"🛡️ <b>[서브 대기]</b> 본그리드 5일 무매매 시 가동 ({main_frozen}/{SUB_FROZEN_DAYS_TRIGGER}일{grad_note})"
            )
        return lines

    cap_badge = "·🔒캡" if sub_lots >= sub_max_lots else ""
    lot_str = (
        f"{sub_lots}/{sub_ratchet_lots}회{cap_badge}"
        if sub_ratchet_lots > sub_lots
        else f"{sub_lots}/{sub_max_lots}회{cap_badge}"
    )
    lines.append(
        f"🛡️ <b>[서브그리드: 총 {sub_sh}주·${sub_inv_usd:,.0f}]</b> ({sub_tiers}층 · {lot_str})"
    )

    sub_active_l1 = bool(summary.get("has_sub_active_l1", True))
    sub_rise_u_pct = safe_float(summary.get("sub_rise_sell_l2_pct"), 1.00)
    sub_upper_buckets = sub_buckets[1:] if sub_active_l1 else sub_buckets[:]
    has_sub_uppers = bool(len(sub_upper_buckets) > 0)

    if sub_active_l1:
        sb1 = sub_buckets[0]
        sl1_t = safe_float(summary.get("sub_l1_target_price"), 0.0)
        sl1_g = safe_float(summary.get("sub_l1_gain_pct"), 0.0)
        sg1_s = "+" if sl1_g >= 0.0 else ""
        sub_rem_q = safe_int(summary.get("sub_l1_rem_quota_qty"), 0)
        sub_target_q = safe_int(summary.get("sub_l1_target_quota_qty"), sb1.qty)
        if sub_rem_q > 0 and sub_target_q > sb1.qty:
            sl1_label = f"{sb1.qty}/{sub_target_q}주"
        else:
            sl1_label = f"{sb1.qty}주"
        sl1_ov_note = (
            "·🔒" if (is_ext_sell_only and has_sub_uppers) else ""
        )
        lines.append(
            f"  ⚡ <b>[서브1층: {sl1_label}·${sb1.actual_cost_usd:,.0f}]</b> "
            f"<b>${sb1.book_price:.2f}</b> ➔ <b>${sl1_t:.2f}</b> ({sg1_s}{sl1_g:.2f}%{sl1_ov_note})"
        )
    else:
        sub_l2_cap = safe_float(
            summary.get("sub_l2_ceiling_price"),
            safe_float(summary.get("sub_min_indiv_upper_price"), 0.0),
        )
        s_cap_note = f" (상한 ${sub_l2_cap:.2f})" if sub_l2_cap > 0.0 else ""
        if sub_lots >= sub_max_lots:
            lines.append(
                f"  ⚡ <b>[서브1층: 공석]</b> 🔒{sub_max_lots}회 상한 도달 (익절 대기)"
            )
        elif is_ext_sell_only:
            lines.append(
                f"  ⚡ <b>[서브1층: 공석]</b> 🔒장외잠금 · 04:07 재장전{s_cap_note}"
            )
        else:
            lines.append(
                f"  ⚡ <b>[서브1층: 공석]</b> 1분주기 재장전 감시{s_cap_note}"
            )

    if sub_upper_buckets:
        su_cnt = len(sub_upper_buckets)
        su_qty = safe_int(
            summary.get("sub_upper_qty"), sum(sb.qty for sb in sub_upper_buckets)
        )
        su_cost = safe_float(
            summary.get("sub_upper_actual_cost_usd"),
            sum(sb.actual_cost_usd for sb in sub_upper_buckets),
        )
        su_wma_p = safe_float(summary.get("sub_upper_wma_price"), 0.0)
        su_wma_t = safe_float(summary.get("sub_upper_wma_target_price"), 0.0)
        su_gain = safe_float(summary.get("sub_l2_gain_pct"), 0.0)
        sug_s = "+" if su_gain >= 0.0 else ""
        s_range_lbl = "서브2층" if su_cnt == 1 else f"서브2~{su_cnt + 1}층"
        lines.append(
            f"  📦 <b>[{s_range_lbl}: {su_qty}주·${su_cost:,.0f}]</b> "
            f"<b>${su_wma_p:.2f}</b> ➔ 졸업 <b>${su_wma_t:.2f}</b> ({sug_s}{su_gain:.2f}%)"
        )

        s_indiv_ov_note = "·🔒" if is_ext_sell_only else ""
        for idx_su, sbu in enumerate(sub_upper_buckets):
            st_no = idx_su + 2
            sbu_t = (
                math.ceil(
                    (sbu.book_price * (1.0 + sub_rise_u_pct / 100.0) - 1e-9)
                    * 100.0
                )
                / 100.0
            )
            sbu_g = (
                ((live_price - sbu.book_price) / sbu.book_price) * 100.0
                if (live_price > 0.0 and sbu.book_price > 0.0)
                else 0.0
            )
            sbg_s = "+" if sbu_g >= 0.0 else ""
            if sbu.lot_count > 1:
                stier_tag = (
                    f"서브{st_no}층(🔄{sbu.lot_count}회·${sbu.actual_cost_usd:,.0f})"
                )
            else:
                stier_tag = (
                    f"서브{st_no}층({sbu.qty}주·${sbu.actual_cost_usd:,.0f})"
                )
            lines.append(
                f"    ▫️ <b>{stier_tag}</b>: ${sbu.book_price:.2f} "
                f"➔ <b>${sbu_t:.2f}</b> ({sbg_s}{sbu_g:.2f}%{s_indiv_ov_note})"
            )

    return lines


def build_avwap_radar_message(
    context: Any,
    st: Dict[str, Any],
    metrics: Dict[str, Any],
    live_price: float,
    now_est: Optional[datetime] = None,
) -> str:
    """
    # MODIFIED [📌 ① 모바일 36자 가로폭 1줄 칼맞춤 스나이퍼 레이더 (/avwap) · 층별 자산($)·10칸 배분 게이지(🟦🟨🟩)·이번사이클 수익·전량졸업 예정자산(🎓)·🗡️ [모의] 암살자 실시간 관제 요약 결합 · Case 65, Case 70 ~ 92]:
    """
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    hm_now = dt_now.hour * 100 + dt_now.minute
    is_ext_sell_only = is_extended_sell_only_window(hm_now, now_est=dt_now)
    is_late_cutoff = is_late_regular_new_cycle_cutoff_window(
        hm_now, now_est=dt_now
    )

    met = refresh_metrics_with_live_tick(metrics, live_price, now_est=dt_now)
    lp = safe_float(
        live_price,
        safe_float(
            met.get("live_price"), safe_float(st.get("anchor_price"), 0.0)
        ),
    )
    rsi_14 = safe_float(met.get("rsi_14"), 50.0)

    summary = summarize_stratum_portfolio(st, live_price=lp, now_est=dt_now)
    is_active = bool(st.get("is_active", True))
    is_simple = _is_simple_portion_mode(st)
    p_mode_short = "💵인출형" if is_simple else "📈복리형"
    active_badge = "🟢 가동중" if is_active else "🔴 정지중"
    mode_badge = (
        f"🌃장외감시·{p_mode_short}"
        if is_ext_sell_only
        else f"⚡실시간·{p_mode_short}"
    )

    held_sh = safe_int(summary.get("held_shares"), 0)
    sub_sh = safe_int(summary.get("sub_held_shares"), 0)
    total_held_sh = safe_int(
        summary.get("total_held_shares"), held_sh + sub_sh
    )
    held_lots = safe_int(summary.get("held_lots"), 0)
    ratchet_lots = safe_int(
        summary.get("cycle_ratchet_max_lots"), held_lots
    )
    eff_lots = safe_int(
        summary.get("eff_lots"), max(1, held_lots, ratchet_lots)
    )
    upper_tier_cnt = safe_int(summary.get("upper_tier_count"), 0)
    sub_upper_tier_cnt = safe_int(summary.get("sub_upper_tier_count"), 0)
    upper_wma_t = safe_float(summary.get("upper_wma_target_price"), 0.0)
    is_l2_only = bool(summary.get("is_l2_only_anti_bloat"))
    l1_rem_q = safe_int(summary.get("l1_rem_quota_qty"), 0)
    buckets_list = summary.get("buckets", [])
    l1_book_p = buckets_list[0].book_price if buckets_list else lp

    actual_inv = safe_float(summary.get("actual_invested_usd"), 0.0)
    gauge_bar = str(summary.get("allocation_gauge_bar") or ("🟩" * 10))
    main_alloc_pct = safe_float(summary.get("main_alloc_pct"), 0.0)
    sub_alloc_pct = safe_float(summary.get("sub_alloc_pct"), 0.0)
    stock_alloc_pct = safe_float(summary.get("stock_alloc_pct"), 0.0)
    cash_alloc_pct = safe_float(summary.get("cash_alloc_pct"), 100.0)

    in_buy_shield, rem_buy_sec = is_within_post_buy_time_shield(
        context, st, TARGET_SYMBOL
    )
    in_sell_shield, rem_sell_sec = is_within_post_sell_time_shield(
        context, st, TARGET_SYMBOL
    )
    in_re_shield, rem_re_sec = is_within_reentry_monitor_time_shield(
        context, st, TARGET_SYMBOL
    )
    waiting_dep = bool(summary.get("waiting_reserve_deposit", False))
    req_dep_usd = safe_float(summary.get("required_reserve_deposit_usd"), 0.0)
    used_res_cnt = safe_int(summary.get("used_reserve_portions_cnt"), 0)
    avail_res_cnt = safe_int(
        summary.get("avail_reserve_portions"), MAX_RESERVE_PORTIONS
    )
    max_res_cnt = safe_int(
        summary.get("max_reserve_portions"), MAX_RESERVE_PORTIONS
    )
    inj_res_usd = safe_float(summary.get("injected_reserve_usd"), 0.0)

    shield_line = ""
    if in_buy_shield:
        shield_line = (
            f"🛡️ <b>[매수 보호대기]</b> <b>{rem_buy_sec:.0f}초</b> 후 익절감시 개시"
        )
    elif waiting_dep:
        shield_line = (
            f"🚨 <b>[시드고갈 대기]</b> 권장입금 <b>${req_dep_usd:,.0f}</b> (잔여 {avail_res_cnt}/{max_res_cnt}회)"
        )
    elif is_ext_sell_only:
        if upper_tier_cnt > 0 or sub_upper_tier_cnt > 0:
            wma_note = f"${upper_wma_t:.2f}" if upper_wma_t > 0.0 else "+1.0%"
            shield_line = (
                f"🌃 <b>[장외 통합졸업 감시]</b> 목표 <b>{wma_note}</b> (개별·매수 잠금)"
            )
        else:
            shield_line = (
                "🌃 <b>[장외 익절감시]</b> 목표가 즉시 익절 (04:07 매수해금)"
            )
    elif held_sh <= 0 and is_late_cutoff:
        shield_line = (
            "🛡️ <b>[15:30 ~ 16:00 신규차단]</b> 익일 04:07 첫 1층 진입 대기"
        )
    elif in_sell_shield:
        shield_line = (
            f"🛡️ <b>[매도 보호대기]</b> <b>{rem_sell_sec:.0f}초</b> 후 매수감시 개시"
        )
    elif l1_rem_q > 0 and not is_l2_only:
        shield_line = (
            f"🎯 <b>[1층 잔량 {l1_rem_q}주 대기]</b> <b>${l1_book_p:.2f}</b> 이하 시 매수"
        )

    stratum_lines = _format_multi_grid_stratum_lines(
        summary,
        lp,
        is_ext_sell_only=is_ext_sell_only,
        is_late_cutoff=is_late_cutoff,
        live_rsi_14=rsi_14,
    )
    sub_stratum_lines = _format_sub_grid_stratum_lines(
        summary,
        lp,
        is_ext_sell_only=is_ext_sell_only,
        is_late_cutoff=is_late_cutoff,
    )

    _, _, _, gate_info = evaluate_buy_gate_bucket_status(
        now_est=dt_now,
        buy_interval_min=LOCKED_BUY_INTERVAL_MIN,
        last_evaluated_bucket_id=safe_int(
            st.get("last_evaluated_buy_bucket_id"), -1
        ),
        last_evaluated_date=str(st.get("last_evaluated_date") or ""),
    )
    next_gate_str = str(gate_info.get("next_gate_hm_str") or "04:07 EST")
    next_bud = safe_float(summary.get("next_portion_budget"), 800.0)
    quota_badge_str = _format_case67_quota_badge(summary)
    ref_anchor = safe_float(summary.get("ref_buy_anchor"), lp)
    chg_anchor = safe_float(summary.get("chg_from_buy_anchor_pct"), 0.0)
    c_sign = "+" if chg_anchor >= 0.0 else ""

    gate_cond_lines: List[str] = []
    if held_sh <= 0:
        gate_header_line = "🎯 <b>[다음 매수 타점 · 0주 첫 진입]</b>"
        if is_late_cutoff:
            gate_cond_lines.append(
                "▫️ 15:30 ~ 16:00 고점방어 (익일 04:07 진입)"
            )
        else:
            gate_cond_lines.append(
                f"▫️ 본그리드(8%): 현재가 <b>${lp:.2f}</b> 기준 {quota_badge_str} (${next_bud:,.0f})"
            )
    elif is_l2_only:
        pull_p = safe_float(summary.get("reentry_pullback_price"), 0.0)
        brk_p = safe_float(summary.get("reentry_breakout_price"), 0.0)
        l2_cap_p = safe_float(
            summary.get("l2_ceiling_price"),
            safe_float(summary.get("min_indiv_upper_price"), 0.0),
        )
        rem_re_note = f" (잔여 {rem_re_sec:.0f}초)" if in_re_shield else ""
        gate_header_line = f"🎯 <b>[다음 매수 타점 · 1층 재장전{rem_re_note}]</b>"
        if is_late_cutoff:
            brk_str = "돌파차단(15:30~)"
        elif rsi_14 > 50.0:
            brk_str = f"돌파차단(RSI {rsi_14:.1f}>50)"
        else:
            brk_str = f"돌파 <b>${brk_p:.2f}</b>(RSI<=50)"
        cap_str = f" · 상한 ${l2_cap_p:.2f}" if l2_cap_p > 0.0 else ""
        gate_cond_lines.append(
            f"▫️ 눌림 <b>${pull_p:.2f}</b> / {brk_str} 시 {quota_badge_str} 매수"
        )
        gate_cond_lines.append(
            f"▫️ 기준 ${ref_anchor:.2f} 대비 {c_sign}{chg_anchor:.2f}%{cap_str}"
        )
    else:
        drop_req = safe_float(summary.get("drop_buy_pct"), -1.0)
        trig_p = safe_float(summary.get("trigger_buy_price"), 0.0)
        step_eligible = bool(summary.get("step_up_eligible", False))
        step_trig_p = safe_float(summary.get("stepped_trigger_price"), 0.0)
        gate_header_line = (
            f"🎯 <b>[다음 매수 타점]</b> (차기 검문: {escape_html(next_gate_str)})"
        )
        step_note = (
            f" · 🔓스텝업 <b>${step_trig_p:.2f}</b>"
            if (step_eligible and step_trig_p > 0.0)
            else ""
        )
        eff_lot_tag = (
            f"·잠금{eff_lots}회" if ratchet_lots > held_lots else ""
        )
        gate_cond_lines.append(
            f"▫️ 추매타점(8%): <b>${trig_p:.2f}</b> 이하 시 {quota_badge_str} 매수{step_note}"
        )
        gate_cond_lines.append(
            f"▫️ 현재위치: 저가 ${ref_anchor:.2f} 대비 {c_sign}{chg_anchor:.2f}% (목표 {drop_req:.1f}%{eff_lot_tag})"
        )

    sub_lots = safe_int(summary.get("sub_held_lots"), 0)
    sub_max_lots = safe_int(
        summary.get("sub_max_total_lots"), SUB_MAX_TOTAL_LOTS_4
    )
    sub_trig_p = safe_float(summary.get("sub_trigger_buy_price"), 0.0)
    sub_quota_badge = _format_sub_quota_badge(summary)
    if sub_sh > 0:
        if sub_lots >= sub_max_lots:
            gate_cond_lines.append(
                f"▫️ 서브(4%): 🔒<b>{sub_lots}/{sub_max_lots}회 상한 도달</b> (추매잠금)"
            )
        else:
            gate_cond_lines.append(
                f"▫️ 서브타점(4%): <b>${sub_trig_p:.2f}</b> 이하 시 {sub_quota_badge} 추매"
            )

    cyc_net = safe_float(summary.get("cycle_realized_net_usd"), 0.0)
    cyc_ev = safe_int(summary.get("cycle_sell_events"), 0)
    last_cyc_net = safe_float(summary.get("last_cycle_realized_net_usd"), 0.0)
    comp_cycles = safe_int(summary.get("completed_main_cycles"), 0)

    cum_net = safe_float(summary.get("cumulative_realized_net_usd"), 0.0)
    real_roi = safe_float(summary.get("realized_roi_pct"), 0.0)
    free_cash = safe_float(summary.get("free_cash_usd"), 0.0)
    mark_eq = safe_float(summary.get("mark_equity_usd"), 0.0)
    mark_roi = safe_float(summary.get("mark_roi_pct"), 0.0)
    proj_grad_eq = safe_float(
        summary.get("projected_graduation_equity_usd"), mark_eq
    )
    proj_grad_roi = safe_float(
        summary.get("projected_graduation_roi_pct"), real_roi
    )

    cyc_sign = "+" if cyc_net >= 0.0 else "-"
    last_c_sign = "+" if last_cyc_net >= 0.0 else "-"
    n_sign = "+" if cum_net >= 0.0 else "-"
    m_sign = "+" if mark_roi >= 0.0 else ""
    pg_sign = "+" if proj_grad_roi >= 0.0 else ""

    if total_held_sh > 0:
        stratum_header = (
            f"🏛️ <b>[보유 지층 : 총 {total_held_sh}주]</b> "
            f"(${actual_inv:,.0f} · 비중 {stock_alloc_pct:.0f}%)"
        )
        if sub_sh > 0:
            gauge_line = (
                f"{gauge_bar} (본{main_alloc_pct:.0f}%·서브{sub_alloc_pct:.0f}%·현금{cash_alloc_pct:.0f}%)"
            )
        else:
            gauge_line = (
                f"{gauge_bar} (주식{stock_alloc_pct:.0f}%·현금{cash_alloc_pct:.0f}%)"
            )
    else:
        stratum_header = "🏛️ <b>[보유 지층 : 총 0주]</b> ($0 · 현금 100%)"
        gauge_line = f"{gauge_bar} (현금 100%)"

    if total_held_sh > 0 or cyc_ev > 0 or abs(cyc_net) > 1e-6:
        cycle_profit_line = (
            f"🔄 이번사이클 수익: <b>{cyc_sign}${abs(cyc_net):,.2f}</b> "
            f"(익절 {cyc_ev}회 · 진행중)"
        )
    else:
        cycle_profit_line = (
            f"🔄 이번사이클 수익: <b>$0.00</b> "
            f"(직전졸업 {last_c_sign}${abs(last_cyc_net):,.2f} · 대기중)"
        )

    lines = [
        f"📡 <b>[스나이퍼 레이더]</b> ({active_badge} · {mode_badge})",
        f"🐂 <b>SOXL</b> 현재가 <b>${lp:.2f}</b> · RSI <b>{rsi_14:.1f}</b>",
    ]
    if shield_line:
        lines.append(shield_line)

    lines.extend(
        [
            "──────────────",
            stratum_header,
            gauge_line,
            *stratum_lines,
            *sub_stratum_lines,
            "──────────────",
            gate_header_line,
            *gate_cond_lines,
            "──────────────",
        ]
    )
    if used_res_cnt > 0:
        lines.append(
            f"💉 예비시드: <b>{used_res_cnt}회분</b> 사용 (${inj_res_usd:,.2f} · 자동상환)"
        )
    lines.extend(
        [
            cycle_profit_line,
            f"💰 전체누적 실현익: <b>{n_sign}${abs(cum_net):,.2f}</b> (졸업 {comp_cycles}회 · {n_sign}{abs(real_roi):.1f}%)",
            f"💵 가용현금: <b>${free_cash:,.2f}</b> · 현재평가: <b>${mark_eq:,.0f}</b> ({m_sign}{mark_roi:.1f}%)",
            f"🎓 전량졸업예정: <b>${proj_grad_eq:,.2f}</b> ({pg_sign}{proj_grad_roi:.2f}% 확정예정)",
        ]
    )

    if context is not None:
        try:
            assn_block = format_assassin_slim_radar_block(
                context=context, live_price=lp
            )
            if assn_block:
                lines.append(assn_block)
        except Exception:
            pass

    lines.append(f"🕒 {dt_now.strftime('%m-%d %H:%M:%S EST')}")
    return "\n".join(lines)
# -*- coding: utf-8 -*-
"""
# MODIFIED: tg_ui_plugin.py (Part 2/2 — /sync · /settlement · /assassin · /reset_assassin · /mode 및 불사조 폴링 컨트롤러)
"""


def build_sync_instruction_message(
    st: Dict[str, Any],
    holdings: Dict[str, Dict[str, Any]],
    live_price: float,
    broker_bp_usd: float,
    fx_rate: float,
    now_est: Optional[datetime] = None,
    context: Optional[Any] = None,
) -> str:
    """
    # MODIFIED [📌 ② 모바일 36자 가로폭 1줄 칼맞춤 잔고 동기화 (/sync) 보드 · 시드 배분 게이지(🟦🟨🟩) · 현재 사이클 vs 전체 누적 수익 · Case 91 인출형 당일 인출가능익/자체수혈 탄창 · 재고 평가착시 3단 해부 · 전량졸업 예정자산(🎓) · 🗡️ [모의] 암살자 요약 탑재 · Case 77, 78, 86, 87, 88, 91]:
    """
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    h_info = (holdings or {}).get(TARGET_SYMBOL, {})
    lp = safe_float(
        live_price,
        safe_float(
            h_info.get("last_price"), safe_float(st.get("anchor_price"), 0.0)
        ),
    )
    summary = summarize_stratum_portfolio(st, live_price=lp, now_est=dt_now)
    is_simple = _is_simple_portion_mode(st)
    mode_title = "💵인출형(단리)" if is_simple else "📈자산증식형(복리)"

    init_seed = safe_float(summary.get("initial_seed_usd"), 10000.0)
    cum_net = safe_float(summary.get("cumulative_realized_net_usd"), 0.0)
    day_net = safe_float(st.get("daily_realized_net_usd"), 0.0)
    eff_fx = max(1000.0, safe_float(fx_rate, KRW_PER_USD_DEFAULT))
    day_krw = int(round(day_net * eff_fx))

    real_roi = safe_float(summary.get("realized_roi_pct"), 0.0)
    real_eq = safe_float(
        summary.get("realized_equity_usd"), init_seed + cum_net
    )
    unreal_pnl = safe_float(summary.get("unrealized_pnl_usd"), 0.0)
    mark_eq = safe_float(summary.get("mark_equity_usd"), 0.0)
    mark_roi = safe_float(summary.get("mark_roi_pct"), 0.0)
    proj_grad_eq = safe_float(
        summary.get("projected_graduation_equity_usd"), real_eq
    )
    proj_grad_roi = safe_float(
        summary.get("projected_graduation_roi_pct"), real_roi
    )

    free_cash = safe_float(summary.get("free_cash_usd"), 0.0)
    avail_idle = safe_float(summary.get("avail_idle_cash_usd"), 0.0)
    inv_main = safe_float(summary.get("actual_invested_buckets_usd"), 0.0)
    inv_sub = safe_float(summary.get("actual_invested_sub_usd"), 0.0)

    gauge_bar = str(summary.get("allocation_gauge_bar") or ("🟩" * 10))
    main_alloc_pct = safe_float(summary.get("main_alloc_pct"), 0.0)
    sub_alloc_pct = safe_float(summary.get("sub_alloc_pct"), 0.0)
    stock_alloc_pct = safe_float(summary.get("stock_alloc_pct"), 0.0)
    cash_alloc_pct = safe_float(summary.get("cash_alloc_pct"), 100.0)

    cyc_net = safe_float(summary.get("cycle_realized_net_usd"), 0.0)
    cyc_sub_net = safe_float(summary.get("cycle_sub_realized_net_usd"), 0.0)
    cyc_ev = safe_int(summary.get("cycle_sell_events"), 0)
    last_cyc_net = safe_float(summary.get("last_cycle_realized_net_usd"), 0.0)
    comp_cycles = safe_int(summary.get("completed_main_cycles"), 0)

    us_comm_pct = safe_float(summary.get("us_commission_rate"), 0.0007) * 100.0
    rt_fee_pct = safe_float(summary.get("round_trip_fee_rate_pct"), 0.14)

    held_sh = safe_int(summary.get("held_shares"), 0)
    sub_sh = safe_int(summary.get("sub_held_shares"), 0)
    sub_tiers = safe_int(summary.get("sub_held_tiers"), 0)
    held_tiers = safe_int(summary.get("held_tiers"), 0)

    used_res_cnt = safe_int(summary.get("used_reserve_portions_cnt"), 0)
    tot_res_cnt = safe_int(summary.get("total_reserve_injected_cnt"), 0)
    inj_res_usd = safe_float(summary.get("injected_reserve_usd"), 0.0)
    unalloc_dep_usd = max(0.0, safe_float(broker_bp_usd, 0.0) - free_cash)

    # Case 91: 미인출 잉여현금 자체수혈 탄창(+N.N회분) 산출
    base_portion_unit = max(1.0, init_seed * 0.08)
    withdrawable_surplus_usd = max(0.0, free_cash - init_seed - inj_res_usd)
    self_reserve_portions = withdrawable_surplus_usd / base_portion_unit

    cyc_sign = "+" if cyc_net >= 0.0 else "-"
    cyc_sub_sign = "+" if cyc_sub_net >= 0.0 else "-"
    last_c_sign = "+" if last_cyc_net >= 0.0 else "-"
    n_sign = "+" if cum_net >= 0.0 else "-"
    d_sign = "+" if day_net >= 0.0 else "-"
    u_sign = "+" if unreal_pnl >= 0.0 else "-"
    m_sign = "+" if mark_roi >= 0.0 else ""
    pg_sign = "+" if proj_grad_roi >= 0.0 else ""

    if mark_roi < 0.0:
        anatomy_header = (
            f"💰 <b>[왜 평가자산이 {m_sign}{mark_roi:.1f}%인가? (재고해부)]</b>"
        )
        anatomy_tip_1 = "💡 현재 마이너스는 보유주식의 일시 평가감이며"
        anatomy_tip_2 = (
            f"   반등 졸업시 <b>${proj_grad_eq:,.0f}({pg_sign}{proj_grad_roi:.2f}%)</b>로 수익 확정!"
        )
    else:
        anatomy_header = "💰 <b>[현재 자산 및 재고 평가 3단 해부]</b>"
        anatomy_tip_1 = "💡 확정 원리금에 보유주식 수익이 더해진 상태이며"
        anatomy_tip_2 = (
            f"   전량 졸업시 <b>${proj_grad_eq:,.0f}({pg_sign}{proj_grad_roi:.2f}%)</b>로 수익 확정!"
        )

    lines = [
        f"🔄 <b>[잔고 동기화 · {mode_title}]</b>",
        "──────────────",
        "📊 <b>[시드 배분 및 층별 자산 시각화]</b>",
        f"{gauge_bar} (주식 {stock_alloc_pct:.0f}% : 현금 {cash_alloc_pct:.0f}%)",
        f"▫️ 🟦본그리드: <b>${inv_main:,.0f}</b> ({main_alloc_pct:.0f}% · {held_tiers}개층 {held_sh}주)",
        f"▫️ 🟨서브그리드: <b>${inv_sub:,.0f}</b> ({sub_alloc_pct:.0f}% · {sub_tiers}개층 {sub_sh}주)",
        f"▫️ 🟩가용현금: <b>${free_cash:,.0f}</b> ({cash_alloc_pct:.0f}% · 서브가용 ${avail_idle:,.0f})",
        "──────────────",
        "🔄 <b>[현재 사이클 vs 전체 누적 수익]</b>",
        f"▫️ 설정 기준시드: <b>${init_seed:,.2f}</b> ({mode_title})",
        f"▫️ 금일 확정수익: <b>{d_sign}${abs(day_net):,.2f}</b> ({d_sign}{abs(day_krw):,}원)",
        f"▫️ 이번사이클익: <b>{cyc_sign}${abs(cyc_net):,.2f}</b> ({cyc_ev}회 익절 · 서브 {cyc_sub_sign}${abs(cyc_sub_net):,.2f})",
        f"▫️ 직전졸업수익: <b>{last_c_sign}${abs(last_cyc_net):,.2f}</b> (총 {comp_cycles}회 사이클 졸업)",
        f"▫️ 전체누적수익: <b>{n_sign}${abs(cum_net):,.2f}</b> ({n_sign}{abs(real_roi):.2f}% 현금확정!)",
    ]
    if is_simple:
        lines.append(
            f"▫️ 자체수혈탄창: 미인출잉여 <b>${withdrawable_surplus_usd:,.2f}</b> (<b>+{self_reserve_portions:.1f}회분</b> 방어)"
        )
        if day_net > 0.0:
            lines.append(
                f"💵 <b>오늘 확정된 실현수익 +${day_net:,.2f}(약 +{day_krw:,}원)는 지금 현금 인출 가능!</b>"
            )

    lines.extend(
        [
            "──────────────",
            anatomy_header,
            f"▫️ 확정 원리금계: <b>${real_eq:,.2f}</b> (시드 + 전체누적익)",
            f"▫️ 일시 재고평가: <b>{u_sign}${abs(unreal_pnl):,.2f}</b> (보유주식 일시평가)",
            f"▫️ 현재 평가자산: <b>${mark_eq:,.2f}</b> ({m_sign}{mark_roi:.2f}% · 재고반영)",
            f"🎓 전량졸업 예정: <b>${proj_grad_eq:,.2f}</b> ({pg_sign}{proj_grad_roi:.2f}% 확정예정!)",
            anatomy_tip_1,
            anatomy_tip_2,
            "──────────────",
            "🏦 <b>[예비시드 및 수수료 현황]</b>",
            f"▫️ 토스 주문가능: <b>${broker_bp_usd:,.2f}</b> (미할당 +${unalloc_dep_usd:,.2f})",
            f"▫️ 예비시드 수혈: 현재 <b>{used_res_cnt}회분</b>(${inj_res_usd:,.2f} · 누적 {tot_res_cnt}회 · 무제한)",
            f"▫️ 적용 수수료: 편도 {us_comm_pct:.3g}% / 왕복 <b>{rt_fee_pct:.2f}%</b>",
        ]
    )

    if context is not None:
        try:
            assn_block = format_assassin_slim_radar_block(
                context=context, live_price=lp
            )
            if assn_block:
                lines.append(assn_block)
        except Exception:
            pass

    lines.append(f"🕒 동기화: {dt_now.strftime('%m-%d %H:%M:%S EST')}")
    return "\n".join(lines)


def build_settlement_control_message(
    st: Dict[str, Any],
    live_price: float = 0.0,
    now_est: Optional[datetime] = None,
    context: Optional[Any] = None,
) -> str:
    """
    # MODIFIED [모바일 36자 가로폭 1줄 칼맞춤 전술 제어반 (/settlement) & Case 91 복리/단리 전환 & /reset_profit & 🗡️ [모의] 암살자 요약 탑재 · Case 02, 64, 86, 87, 88, 91]:
    """
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    lp = safe_float(live_price, safe_float(st.get("anchor_price"), 100.0))
    summary = summarize_stratum_portfolio(st, live_price=lp, now_est=dt_now)

    is_active = bool(st.get("is_active", True))
    is_simple = _is_simple_portion_mode(st)
    power_str = "🟢 가동 중 (ON)" if is_active else "🔴 일시정지 (OFF)"
    p_mode_str = (
        "💵 인출형 (단리 · 시드 8%/4% 고정)"
        if is_simple
        else "📈 자산증식형 (복리 · 코어자산 8%/4%)"
    )

    init_seed = safe_float(summary.get("initial_seed_usd"), 10000.0)
    real_eq = safe_float(summary.get("realized_equity_usd"), init_seed)
    free_cash = safe_float(summary.get("free_cash_usd"), 0.0)
    cyc_net = safe_float(summary.get("cycle_realized_net_usd"), 0.0)
    cyc_ev = safe_int(summary.get("cycle_sell_events"), 0)
    comp_cycles = safe_int(summary.get("completed_main_cycles"), 0)
    rt_fee_pct = safe_float(summary.get("round_trip_fee_rate_pct"), 0.14)
    next_bud = safe_float(
        summary.get("next_portion_budget"), init_seed * 0.08
    )
    quota_badge_str = _format_case67_quota_badge(summary)
    sub_bud = safe_float(
        summary.get("sub_next_portion_budget"), init_seed * 0.04
    )
    sub_quota_badge = _format_sub_quota_badge(summary)

    held_sh = safe_int(summary.get("held_shares"), 0)
    sub_sh = safe_int(summary.get("sub_held_shares"), 0)
    sub_lots = safe_int(summary.get("sub_held_lots"), 0)
    sub_max_lots = safe_int(
        summary.get("sub_max_total_lots"), SUB_MAX_TOTAL_LOTS_4
    )
    sub_comp = safe_int(summary.get("sub_completed_cycles"), 0)
    main_frozen = safe_int(summary.get("main_consec_frozen_days"), 0)

    held_tiers = safe_int(summary.get("held_tiers"), 0)
    held_lots = safe_int(summary.get("held_lots"), 0)
    ratchet_lots = safe_int(
        summary.get("cycle_ratchet_max_lots"), held_lots
    )
    used_res_cnt = safe_int(summary.get("used_reserve_portions_cnt"), 0)
    inj_res_usd = safe_float(summary.get("injected_reserve_usd"), 0.0)

    base_portion_unit = max(1.0, init_seed * 0.08)
    withdrawable_surplus_usd = max(0.0, free_cash - init_seed - inj_res_usd)
    self_reserve_portions = withdrawable_surplus_usd / base_portion_unit

    lot_ctrl_str = (
        f"{held_lots}/{ratchet_lots}회"
        if ratchet_lots > held_lots
        else f"{held_lots}회"
    )
    cyc_sign = "+" if cyc_net >= 0.0 else "-"

    lines = [
        "⚙️ <b>[전술 제어반]</b>",
        "──────────────",
        f"1️⃣ 스나이퍼 전원: <b>{power_str}</b> (수수료 {rt_fee_pct:.2f}%)",
        f"2️⃣ 운용 정량모드: <b>{p_mode_str}</b> (<code>/mode</code>)",
        f"3️⃣ 기준 시드: <b>${init_seed:,.2f}</b> (확정자산 ${real_eq:,.2f})",
        f"   ▫️ 이번사이클익: <b>{cyc_sign}${abs(cyc_net):,.2f}</b> ({cyc_ev}회 익절 · 졸업 {comp_cycles}회)",
        f"   ▫️ 1회 정량: 본 ${next_bud:,.0f}({quota_badge_str}) · 서브 ${sub_bud:,.0f}({sub_quota_badge})",
        f"   ▫️ 자체수혈탄창: 미인출잉여 <b>${withdrawable_surplus_usd:,.0f}</b> (<b>+{self_reserve_portions:.1f}회분</b>)",
        f"4️⃣ 보유/예비수혈: 본 <b>{held_sh}주</b>({held_tiers}층·{lot_ctrl_str}) · 예비 <b>{used_res_cnt}회분</b>(${inj_res_usd:,.0f})",
        f"   ▫️ 서브(상시): <b>{sub_sh}주</b>({sub_lots}/{sub_max_lots}회) · 동결 {main_frozen}/{SUB_FROZEN_DAYS_TRIGGER}일 · 졸업 {sub_comp}회",
        "──────────────",
        "🧹 <code>/reset_profit</code> : 스나이퍼 수익 0점 초기화 (주식·시드 보존)",
        "🗡️ <code>/assassin</code> : [모의] 암살자 상세 관제 · <code>/reset_assassin</code> : 모의전적 초기화",
    ]

    if context is not None:
        try:
            assn_block = format_assassin_slim_radar_block(
                context=context, live_price=lp
            )
            if assn_block:
                lines.append(assn_block)
        except Exception:
            pass

    lines.append(f"🕒 기준 시각: {dt_now.strftime('%m-%d %H:%M:%S EST')}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# [핵심 2] 텔레그램 명령어 및 콜백 비동기 컨트롤러 (TelegramCommandController — Case 81 불사조 폴링 & Case 88 서브그리드 & Case 91 복리/단리 & 🗡️ 모의 암살자 연동)
# ---------------------------------------------------------------------------
class TelegramCommandController:
    """
    🚨 제1헌법 & Case 02, 15, 16, 62, 64, 65, 66, 67, 68, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 81, 83, 84, 85, 86, 87, 88, 91, 92:
    main.py 의 SniperAppContext 와 정식 결속되는 텔레그램 봇 컨트롤러.
    """

    def __init__(self, context: Any) -> None:
        self.context: Any = context
        self.base_dir: str = get_bot_base_dir(
            getattr(context, "base_dir", None)
        )
        self.bot_token: str = (
            os.environ.get("TELEGRAM_BOT_TOKEN")
            or os.environ.get("TG_BOT_TOKEN")
            or os.environ.get("BOT_TOKEN")
            or ""
        ).strip()
        self.chat_id: str = str(
            os.environ.get("TELEGRAM_CHAT_ID")
            or os.environ.get("TG_CHAT_ID")
            or os.environ.get("CHAT_ID")
            or ""
        ).strip()

        self._boot_epoch: float = time.time()
        self._last_update_id: int = 0
        try:
            persisted_uid = read_persisted_tg_offset_sync(self.base_dir)
            st_init = self.context.ledger.get_state(TARGET_SYMBOL)
            ledger_uid = safe_int(st_init.get("last_tg_update_id"), 0)
            self._last_update_id = max(0, persisted_uid, ledger_uid)
        except Exception:
            self._last_update_id = 0

        self._awaiting_seed_input_chats: Dict[str, float] = {}
        self._tg_http_client: Optional[Any] = None
        self._tg_client_lock: asyncio.Lock = asyncio.Lock()
        self._consecutive_poll_errors: int = 0

    def _api_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}/{method}"

    async def _ensure_tg_http_client(self) -> Optional[Any]:
        """
        # [Case 81]:
        토스 API 클라이언트와 완전히 독립된 텔레그램 전용 httpx.AsyncClient 세션을 생성/반환한다.
        """
        if not _HTTPX_AVAILABLE or httpx is None:
            return None
        async with self._tg_client_lock:
            if self._tg_http_client is None or getattr(
                self._tg_http_client, "is_closed", False
            ):
                self._tg_http_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(25.0, connect=8.0)
                )
            return self._tg_http_client

    async def _close_tg_http_client(self) -> None:
        """
        # [Case 81]:
        종료/재기동 직전 또는 연속 오류 발생 시 열린 텔레그램 롱폴링 소켓을 즉시 닫아
        신구 프로세스 간 HTTP 409 Conflict 충돌을 0%로 원천 차단한다.
        """
        async with self._tg_client_lock:
            client = self._tg_http_client
            self._tg_http_client = None
            if client is not None:
                try:
                    await asyncio.wait_for(client.aclose(), timeout=2.0)
                except Exception:
                    pass

    async def _recreate_tg_http_client(self, reason: str = "ERROR") -> None:
        """
        # [Case 81]:
        HTTP 409 Conflict 또는 연속 3회 이상 폴링 오류 감지 시 기존 소켓 풀을 폐기하고 새 세션을 구축한다.
        """
        logger.info(
            "♻️ [Case 81 텔레그램 전용 HTTP 세션 자가 치유 재생성] 사유=%s",
            reason,
        )
        await self._close_tg_http_client()
        await self._ensure_tg_http_client()

    def _post_tg_sync(
        self,
        method: str,
        payload: Dict[str, Any],
        timeout_sec: float = 15.0,
    ) -> Dict[str, Any]:
        if not self.bot_token:
            return {"ok": False, "description": "missing-bot-token"}
        url = self._api_url(method)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url=url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {"ok": True}
        except urllib.error.HTTPError as he:
            try:
                err_raw = he.read().decode("utf-8", errors="replace")
                parsed = json.loads(err_raw)
                if isinstance(parsed, dict):
                    parsed.setdefault("error_code", he.code)
                    return parsed
                return {"ok": False, "error_code": he.code}
            except Exception:
                return {"ok": False, "error_code": he.code}
        except Exception as exc:
            return {"ok": False, "description": str(exc)}

    async def _call_tg(
        self,
        method: str,
        payload: Dict[str, Any],
        timeout_sec: float = 15.0,
    ) -> Dict[str, Any]:
        """
        # [Case 81]:
        텔레그램 전용 httpx.AsyncClient 가 가용하면 비동기 커넥션 풀로 직접 호출하고,
        예외 또는 미설치 환경에서는 asyncio.to_thread(_post_tg_sync) 로 안전 폴백한다.
        """
        if not self.bot_token:
            return {"ok": False, "description": "missing-bot-token"}

        if _HTTPX_AVAILABLE and httpx is not None:
            try:
                client = await self._ensure_tg_http_client()
                if client is not None:
                    resp = await asyncio.wait_for(
                        client.post(
                            self._api_url(method),
                            json=payload,
                            timeout=timeout_sec,
                        ),
                        timeout=timeout_sec + 3.0,
                    )
                    try:
                        data = resp.json()
                    except Exception:
                        data = {"ok": resp.status_code == 200}
                    if isinstance(data, dict):
                        if resp.status_code >= 400:
                            data.setdefault("error_code", resp.status_code)
                        return data
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug(
                    "텔레그램 httpx(%s) 호출 예외 -> urllib 폴백: %s",
                    method,
                    exc,
                )

        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    self._post_tg_sync, method, payload, timeout_sec
                ),
                timeout=timeout_sec + 3.0,
            )
        except Exception as exc:
            logger.debug("텔레그램 API(%s) 호출 예외: %s", method, exc)
            return {"ok": False, "description": str(exc)}

    async def _persist_offset_locally(self, target_update_id: int) -> None:
        """
        # [Case 81]:
        최신 update_id 를 로컬 오프셋 파일(.tg_update_offset_<folder_slug>.dat)과 3중 원장에 비동기 영속화한다.
        """
        uid = max(self._last_update_id, safe_int(target_update_id, 0))
        if uid <= 0:
            return
        self._last_update_id = uid
        try:
            await asyncio.to_thread(
                write_persisted_tg_offset_sync, self.base_dir, uid
            )
        except Exception:
            pass
        try:
            await self.context.ledger.update_state(
                TARGET_SYMBOL, last_tg_update_id=uid
            )
        except Exception:
            pass

    async def _ack_telegram_offset(self, target_update_id: int) -> None:
        """
        # [Case 81]:
        로컬 오프셋 파일(.tg_update_offset_<folder_slug>.dat) + 3중 원장 + 텔레그램 서버(getUpdates offset=uid+1)
        3곳에 오프셋을 즉시 확정 커밋하여 프로세스 재기동 직후 이전 명령어가 재실행되는 현상을 100% 차단한다.
        """
        uid = max(self._last_update_id, safe_int(target_update_id, 0))
        if uid <= 0:
            return
        await self._persist_offset_locally(uid)
        try:
            await self._call_tg(
                "getUpdates",
                {"offset": uid + 1, "limit": 1, "timeout": 0},
                timeout_sec=5.0,
            )
        except Exception:
            pass

    async def _flush_stale_updates_on_startup(self) -> None:
        try:
            res = await self._call_tg(
                "getUpdates",
                {"offset": -1, "timeout": 0},
                timeout_sec=6.0,
            )
            if not (isinstance(res, dict) and bool(res.get("ok"))):
                return
            updates = res.get("result")
            if not isinstance(updates, list) or not updates:
                return

            max_stale_uid = self._last_update_id
            for upd in updates:
                if isinstance(upd, dict):
                    uid = safe_int(upd.get("update_id"), 0)
                    if uid > max_stale_uid:
                        max_stale_uid = uid

            if max_stale_uid > 0:
                await self._ack_telegram_offset(max_stale_uid)
                logger.info(
                    "🧹 [텔레그램 부팅 전 적체 큐 전량 소각 완료] last_update_id=%d",
                    max_stale_uid,
                )
        except Exception as exc:
            logger.debug("부팅 시 텔레그램 큐 플러시 스킵: %s", exc)

    async def send_message(
        self,
        text: str,
        chat_id: Optional[str] = None,
        reply_markup: Optional[Dict[str, Any]] = None,
        parse_mode: str = "HTML",
    ) -> bool:
        target_chat = str(chat_id or self.chat_id or "").strip()
        if not self.bot_token or not target_chat:
            return False
        payload: Dict[str, Any] = {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        res = await self._call_tg("sendMessage", payload, timeout_sec=10.0)
        if not bool(res.get("ok")):
            payload.pop("parse_mode", None)
            res = await self._call_tg("sendMessage", payload, timeout_sec=10.0)
        return bool(res.get("ok"))

    async def edit_or_send_message(
        self,
        chat_id: str,
        message_id: Optional[int],
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if message_id is not None and message_id > 0:
            payload: Dict[str, Any] = {
                "chat_id": str(chat_id),
                "message_id": int(message_id),
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            if reply_markup is not None:
                payload["reply_markup"] = reply_markup
            res = await self._call_tg(
                "editMessageText", payload, timeout_sec=10.0
            )
            if bool(res.get("ok")) or "message is not modified" in str(
                res.get("description") or ""
            ):
                return True
        return await self.send_message(
            text=text, chat_id=chat_id, reply_markup=reply_markup
        )

    async def send_slim_alert(
        self,
        title: str,
        body: str = "",
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if not body:
            return await self.send_message(
                text=str(title), reply_markup=reply_markup
            )
        safe_title = escape_html(title)
        safe_body = escape_html(body)
        msg = (
            f"<b>{safe_title}</b>\n🔸 {safe_body}"
            if safe_body
            else f"<b>{safe_title}</b>"
        )
        return await self.send_message(text=msg, reply_markup=reply_markup)

    async def send_startup_alive_banner(self) -> bool:
        """
        # 기동 완료 후 "✅ 서버가 정상 작동 중입니다." 단일 라인 생존 신호 타전 및 4버튼 하단 키보드 활성화 (Case 16)
        """
        text = "<b>✅ 서버가 정상 작동 중입니다.</b>"
        return await self.send_message(
            text=text, reply_markup=_build_main_reply_keyboard()
        )

    # -----------------------------------------------------------------------
    # 실시간 시세/잔고 최신화 후 각 관제 보드 렌더링
    # -----------------------------------------------------------------------
    async def _refresh_live_price_and_metrics(
        self,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        /avwap 조회 시 1분봉 미확보 상태면 즉시 온디맨드 프리워밍 수행:
        """
        now_est = datetime.now(EST_TZ)
        live_p = safe_float(
            self.context.latest_prices.get(TARGET_SYMBOL), 0.0
        )
        try:
            p_map = await self.context.api.get_current_prices_batch(
                (TARGET_SYMBOL,)
            )
            fetched_p = safe_float(p_map.get(TARGET_SYMBOL), 0.0)
            if fetched_p > 0.0:
                live_p = fetched_p
                self.context.latest_prices[TARGET_SYMBOL] = live_p
        except Exception:
            pass

        base_met = self.context.candle_metrics_cache.get(TARGET_SYMBOL, {})
        if (
            not isinstance(base_met, dict)
            or safe_float(base_met.get("prev_bar_close"), 0.0) <= 0.0
        ):
            try:
                c_1m = await self.context.api.get_candles_1m(
                    symbol=TARGET_SYMBOL, total_count=200
                )
                if c_1m:
                    base_met = compute_soxl_quant_metrics_1m(
                        candles=c_1m,
                        live_price=live_p,
                        now_est=now_est,
                    )
            except Exception:
                pass

        met = refresh_metrics_with_live_tick(
            base_met, live_p, now_est=now_est
        )
        self.context.candle_metrics_cache[TARGET_SYMBOL] = met
        if live_p <= 0.0:
            live_p = safe_float(met.get("live_price"), 0.0)
        return live_p, met

    async def _render_and_send_avwap(
        self, chat_id: str, edit_msg_id: Optional[int] = None
    ) -> None:
        live_p, met = await self._refresh_live_price_and_metrics()
        st = self.context.ledger.get_state(TARGET_SYMBOL)
        msg = build_avwap_radar_message(
            context=self.context,
            st=st,
            metrics=met,
            live_price=live_p,
            now_est=datetime.now(EST_TZ),
        )
        kb = (
            None
            if (edit_msg_id is not None and edit_msg_id > 0)
            else _build_main_reply_keyboard()
        )
        await self.edit_or_send_message(
            chat_id=chat_id,
            message_id=edit_msg_id,
            text=msg,
            reply_markup=kb,
        )

    async def _render_and_send_sync(
        self, chat_id: str, edit_msg_id: Optional[int] = None
    ) -> None:
        now_est = datetime.now(EST_TZ)
        live_p, _ = await self._refresh_live_price_and_metrics()

        # [Case 86]: /sync 호출 시 계좌별 미국 주식 수수료율(GET /api/v1/commissions) 동기화 확인
        ensure_comm_fn = getattr(
            self.context.api, "ensure_us_commission_rate", None
        )
        if callable(ensure_comm_fn):
            try:
                c_res = await ensure_comm_fn()
                if isinstance(c_res, tuple) and len(c_res) == 2:
                    us_c = safe_float(c_res[0], 0.0)
                    rt_p = safe_float(c_res[1], 0.0)
                    if us_c > 0.0 and rt_p > 0.0:
                        await self.context.ledger.update_state(
                            TARGET_SYMBOL,
                            us_commission_rate=us_c,
                            round_trip_fee_rate_pct=rt_p,
                        )
            except Exception:
                pass

        holdings_map, fetch_ok = (
            await self.context.api.get_holdings_map_with_status()
        )
        if fetch_ok and isinstance(holdings_map, dict):
            self.context.latest_holdings = holdings_map
            self.context.holdings_fetch_ok = True
            await reconcile_stratum_with_broker_holdings_plugin(
                context=self.context,
                holdings=holdings_map,
                prices={TARGET_SYMBOL: live_p},
                now_est=now_est,
                force_sync=False,
            )
        else:
            holdings_map = self.context.latest_holdings

        bp_usd = await self.context.api.get_buying_power_usd(
            safety_buffer_pct=0.0
        )
        fx_rate = await self.context.api.get_usd_krw_rate()
        st = self.context.ledger.get_state(TARGET_SYMBOL)

        if bool(st.get("waiting_reserve_deposit", False)):
            mark_reserve_deposit_check_shield(
                self.context, TARGET_SYMBOL, clear_shield=True
            )
            st = await self.context.ledger.update_state(
                TARGET_SYMBOL, last_reserve_check_ts=0.0
            )
            self.context.wakeup_event.set()

        msg = build_sync_instruction_message(
            st=st,
            holdings=holdings_map,
            live_price=live_p,
            broker_bp_usd=bp_usd,
            fx_rate=fx_rate,
            now_est=now_est,
            context=self.context,
        )
        kb = (
            None
            if (edit_msg_id is not None and edit_msg_id > 0)
            else _build_main_reply_keyboard()
        )
        await self.edit_or_send_message(
            chat_id=chat_id,
            message_id=edit_msg_id,
            text=msg,
            reply_markup=kb,
        )

    async def _render_and_send_settlement(
        self, chat_id: str, edit_msg_id: Optional[int] = None
    ) -> None:
        live_p, _ = await self._refresh_live_price_and_metrics()
        st = self.context.ledger.get_state(TARGET_SYMBOL)
        msg = build_settlement_control_message(
            st=st,
            live_price=live_p,
            now_est=datetime.now(EST_TZ),
            context=self.context,
        )
        await self.edit_or_send_message(
            chat_id=chat_id,
            message_id=edit_msg_id,
            text=msg,
            reply_markup=_build_settlement_inline_keyboard(
                bool(st.get("is_active", True)),
                portion_mode=st.get("portion_mode"),
            ),
        )

    async def _render_and_send_assassin_dashboard(
        self, chat_id: str, edit_msg_id: Optional[int] = None
    ) -> None:
        live_p, _ = await self._refresh_live_price_and_metrics()
        msg = await build_assassin_detail_dashboard_html(
            context=self.context, live_price=live_p
        )
        kb = (
            None
            if (edit_msg_id is not None and edit_msg_id > 0)
            else _build_main_reply_keyboard()
        )
        await self.edit_or_send_message(
            chat_id=chat_id,
            message_id=edit_msg_id,
            text=msg,
            reply_markup=kb,
        )

    async def _toggle_portion_mode_command(
        self, chat_id: str, edit_msg_id: Optional[int] = None
    ) -> None:
        st_cur = self.context.ledger.get_state(TARGET_SYMBOL)
        if hasattr(self.context.ledger, "toggle_portion_mode"):
            updated_st = await self.context.ledger.toggle_portion_mode()
        else:
            next_m = (
                PORTION_MODE_COMPOUND
                if _is_simple_portion_mode(st_cur)
                else PORTION_MODE_SIMPLE
            )
            updated_st = await self.context.ledger.update_state(
                TARGET_SYMBOL, portion_mode=next_m
            )
        self.context.wakeup_event.set()
        if edit_msg_id is not None and edit_msg_id > 0:
            await self._render_and_send_settlement(
                chat_id=chat_id, edit_msg_id=edit_msg_id
            )
            return

        live_p, _ = await self._refresh_live_price_and_metrics()
        summary = summarize_stratum_portfolio(updated_st, live_price=live_p)
        is_s = _is_simple_portion_mode(updated_st)
        m_lbl = (
            "💵 인출형 (단리 · SIMPLE_08PCT)"
            if is_s
            else "📈 자산증식형 (복리 · COMP_08PCT)"
        )
        next_bud = safe_float(summary.get("next_portion_budget"), 800.0)
        sub_bud = safe_float(summary.get("sub_next_portion_budget"), 400.0)
        await self.send_message(
            chat_id=chat_id,
            text=(
                f"🔄 <b>[운용 정량모드 전환 완료]</b>\n"
                f"▫️ 현재 모드: <b>{m_lbl}</b>\n"
                f"▫️ 본그리드 1회(8%): <b>${next_bud:,.2f}</b> ({_format_case67_quota_badge(summary)})\n"
                f"▫️ 서브그리드 1회(4%): <b>${sub_bud:,.2f}</b> ({_format_sub_quota_badge(summary)})"
            ),
            reply_markup=_build_main_reply_keyboard(),
        )

    async def _apply_new_seed_value(
        self, chat_id: str, raw_num_str: str
    ) -> bool:
        cleaned = (
            str(raw_num_str)
            .replace(",", "")
            .replace("$", "")
            .replace("불", "")
            .replace("달러", "")
            .strip()
        )
        try:
            val = float(cleaned)
        except Exception:
            return False
        if val < 100.0 or val > 10000000.0:
            await self.send_message(
                chat_id=chat_id,
                text="⚠️ 시드머니는 <b>$100 ~ $10,000,000</b> 사이의 숫자로 입력해 주세요. (예: <code>10000</code>)",
            )
            return True

        mark_reserve_deposit_check_shield(
            self.context, TARGET_SYMBOL, clear_shield=True
        )
        updated_st = await self.context.ledger.update_state(
            TARGET_SYMBOL,
            initial_seed_usd=round(val, 4),
            seed_explicitly_set_100=bool(abs(val - 100.0) < 1e-6),
            waiting_reserve_deposit=False,
            waiting_reserve_deposit_alert_sent=False,
            required_reserve_deposit_usd=0.0,
            last_reserve_check_ts=0.0,
        )
        try:
            assn_ledger = ensure_assassin_ledger(self.context)
            await assn_ledger.update_state(initial_seed_usd=round(val, 4))
        except Exception:
            pass

        self.context.wakeup_event.set()
        live_p, _ = await self._refresh_live_price_and_metrics()
        summary = summarize_stratum_portfolio(updated_st, live_price=live_p)
        quota_badge_str = _format_case67_quota_badge(summary)
        sub_quota_badge = _format_sub_quota_badge(summary)
        await self.send_message(
            chat_id=chat_id,
            text=(
                "✅ <b>[기준 시드머니 설정 완료]</b>\n"
                f"▫️ 기준 시드: <b>${val:,.2f}</b> (스나이퍼 & 모의암살자 동시 적용)\n"
                f"▫️ 가용 현금: <b>${safe_float(summary.get('free_cash_usd'), 0.0):,.2f}</b>\n"
                f"▫️ 본그리드(8%): <b>${safe_float(summary.get('next_portion_budget'), 0.0):,.0f}</b> ({quota_badge_str})\n"
                f"▫️ 서브그리드(4%): <b>${safe_float(summary.get('sub_next_portion_budget'), 0.0):,.0f}</b> ({sub_quota_badge})"
            ),
            reply_markup=_build_settlement_inline_keyboard(
                bool(updated_st.get("is_active", True)),
                portion_mode=updated_st.get("portion_mode"),
            ),
        )
        return True

    async def _reset_realized_profit_only(self, chat_id: str) -> None:
        """
        # MODIFIED [Case 02, Case 74, Case 76, Case 77, Case 86, Case 87, Case 88, Case 91]:
        """
        mark_reserve_deposit_check_shield(
            self.context, TARGET_SYMBOL, clear_shield=True
        )
        st_cur = self.context.ledger.get_state(TARGET_SYMBOL)
        has_buckets = bool(st_cur.get("buckets"))
        has_sub_buckets = bool(st_cur.get("sub_buckets"))
        reset_kw: Dict[str, Any] = {
            "cumulative_realized_gross_usd": 0.0,
            "cumulative_realized_fee_usd": 0.0,
            "cumulative_realized_net_usd": 0.0,
            "daily_realized_net_usd": 0.0,
            "cycle_realized_gross_usd": 0.0,
            "cycle_realized_fee_usd": 0.0,
            "cycle_realized_net_usd": 0.0,
            "cycle_sub_realized_net_usd": 0.0,
            "cycle_sell_events": 0,
            "cycle_leftover_saved_usd": 0.0,
            "last_cycle_realized_net_usd": 0.0,
            "last_cycle_sell_events": 0,
            "completed_main_cycles": 0,
            "cumulative_leftover_saved_usd": 0.0,
            "daily_leftover_saved_usd": 0.0,
            "seed_protect_pass_cnt": 0,
            "daily_seed_protect_pass_cnt": 0,
            "cond_unlock_buy_events": 0,
            "daily_unlock_buy_events": 0,
            "sub_buy_events": 0,
            "sub_buy_shares": 0,
            "daily_sub_buy_events": 0,
            "sub_sell_events": 0,
            "sub_sold_shares": 0,
            "daily_sub_sell_events": 0,
            "sub_merge_events": 0,
            "sub_merged_indiv_escape_cnt": 0,
            "sub_unlock_events": 0,
            "daily_sub_unlock_events": 0,
            "sub_completed_cycles": 0,
            "sub_realized_gross_usd": 0.0,
            "sub_realized_fee_usd": 0.0,
            "sub_realized_net_usd": 0.0,
            "daily_sub_realized_net_usd": 0.0,
            "total_reserve_injected_cnt": 0,
            "daily_reserve_injected_cnt": 0,
            "cumulative_reserve_repaid_usd": 0.0,
            "dust_guard_blocked_cnt": 0,
            "daily_dust_guard_blocked_cnt": 0,
            "waiting_reserve_deposit": False,
            "waiting_reserve_deposit_alert_sent": False,
            "required_reserve_deposit_usd": 0.0,
            "last_reserve_check_ts": 0.0,
            "extra_13plus_buy_events": 0,
            "total_buy_events": 0,
            "daily_buy_events": 0,
            "total_sell_events": 0,
            "total_sold_shares": 0,
            "win_sell_events": 0,
            "daily_sell_events": 0,
            "indiv_grid_sell_cnt": 0,
            "daily_indiv_grid_sell_cnt": 0,
            "wma_grad_sell_cnt": 0,
            "daily_wma_grad_sell_cnt": 0,
            "reanchor_cnt": 0,
            "daily_reanchor_cnt": 0,
            "cumulative_reanchor_drop_usd": 0.0,
        }
        if not has_buckets:
            reset_kw["daily_main_buy_cnt"] = 0
            reset_kw["daily_main_sell_cnt"] = 0
        if not has_sub_buckets:
            reset_kw["daily_sub_buy_cnt"] = 0
            reset_kw["daily_sub_sell_cnt"] = 0
        if not has_buckets and not has_sub_buckets:
            reset_kw["used_reserve_portions_cnt"] = 0
            reset_kw["injected_reserve_usd"] = 0.0
            reset_kw["cycle_ratchet_max_lots"] = 0
            reset_kw["sub_ratchet_max_lots"] = 0

        st_reset = await self.context.ledger.update_state(
            TARGET_SYMBOL, **reset_kw
        )
        snap_fn = getattr(
            self.context.ledger, "create_daily_backup_snapshot", None
        )
        if callable(snap_fn):
            try:
                await snap_fn()
            except Exception:
                pass

        self.context.wakeup_event.set()
        live_p, _ = await self._refresh_live_price_and_metrics()
        summary = summarize_stratum_portfolio(st_reset, live_price=live_p)
        init_seed = safe_float(summary.get("initial_seed_usd"), 10000.0)
        free_cash = safe_float(summary.get("free_cash_usd"), 0.0)
        next_bud = safe_float(
            summary.get("next_portion_budget"), init_seed * 0.08
        )
        quota_badge_str = _format_case67_quota_badge(summary)
        held_sh = safe_int(summary.get("held_shares"), 0)
        sub_sh = safe_int(summary.get("sub_held_shares"), 0)
        held_tiers = safe_int(summary.get("held_tiers"), 0)
        held_lots = safe_int(summary.get("held_lots"), 0)
        ratchet_lots = safe_int(
            summary.get("cycle_ratchet_max_lots"), held_lots
        )
        sub_note = f"+서브{sub_sh}주" if sub_sh > 0 else ""
        lot_keep_str = (
            f"{held_lots}/{ratchet_lots}회"
            if ratchet_lots > held_lots
            else f"{held_lots}회차"
        )

        await self.send_message(
            chat_id=chat_id,
            text=(
                "🧹 <b>[스나이퍼 실현수익 0점 초기화 완료]</b>\n"
                "▫️ 이번사이클 / 누적 실현익: <b>$0.00</b>\n"
                f"▫️ 복귀 기준시드: <b>${init_seed:,.2f}</b>\n"
                f"▫️ 현재 가용현금: <b>${free_cash:,.2f}</b>\n"
                f"▫️ 차기 1회(8%): <b>${next_bud:,.0f}</b> ({quota_badge_str})\n"
                f"▫️ 보유지층 보존: 본 <b>{held_sh}주</b>({held_tiers}층·{lot_keep_str}{sub_note})"
            ),
            reply_markup=_build_main_reply_keyboard(),
        )

    async def _reset_assassin_stats_command(self, chat_id: str) -> None:
        st_sp = self.context.ledger.get_state(TARGET_SYMBOL)
        init_seed = safe_float(st_sp.get("initial_seed_usd"), 10000.0)
        assn_ledger = ensure_assassin_ledger(self.context)
        await assn_ledger.reset_assassin_stats_only(sniper_seed_usd=init_seed)
        await self.send_message(
            chat_id=chat_id,
            text=(
                "🧹 <b>[[모의] 암살자 누적 전적 초기화 완료]</b>\n"
                f"▫️ 기준 시드: <b>${init_seed:,.2f}</b>\n"
                "▫️ 누적 출격일 / 단리·복리 실현익이 0점으로 초기화되었습니다."
            ),
            reply_markup=_build_main_reply_keyboard(),
        )

    async def _execute_manual_update_command(self, chat_id: str) -> None:
        """
        # [Case 62, Case 68, Case 75 & Case 81]:
        """
        await self._ack_telegram_offset(self._last_update_id)
        await self.send_message(
            chat_id=chat_id,
            text=(
                "⏳ <b>[시스템 업데이트 개시]</b>\n"
                "🔸 최신 코드 동기화 및 프리플라이트 검증 중..."
            ),
            reply_markup=_build_main_reply_keyboard(),
        )
        upd_res = await execute_git_pull_and_preflight(self.base_dir)
        changed = False
        if isinstance(upd_res, tuple):
            ok = bool(upd_res[0]) if len(upd_res) >= 1 else False
            if len(upd_res) >= 3 and isinstance(upd_res[2], bool):
                changed = bool(upd_res[2])
            str_parts = [
                str(x).strip()
                for x in upd_res[1:]
                if isinstance(x, str) and str(x).strip()
            ]
            msg = (
                " · ".join(str_parts)
                if str_parts
                else "✅ 코어 모듈 검증 통과 · 원장 100% 보존"
            )
        else:
            ok = bool(upd_res)
            msg = "✅ 코어 모듈 검증 통과 · 원장 100% 보존"

        await self._ack_telegram_offset(self._last_update_id)

        if not ok:
            await self.send_message(
                chat_id=chat_id,
                text=f"⚠️ <b>[업데이트 중단 · 원장 보존]</b>\n{escape_html(msg)}",
                reply_markup=_build_main_reply_keyboard(),
            )
            return

        if not changed:
            await self.send_message(
                chat_id=chat_id,
                text=(
                    "✅ <b>[최신 버전 확인 · 무중단 가동]</b>\n"
                    "🔸 변경사항이 없어 현재 엔진을 그대로 유지합니다."
                ),
                reply_markup=_build_main_reply_keyboard(),
            )
            return

        await self.send_message(
            chat_id=chat_id,
            text=(
                "🚀 <b>[신규 업데이트 검증 통과]</b>\n"
                "🔸 원장 100% 보존 상태로 무중단 재기동합니다..."
            ),
            reply_markup=_build_main_reply_keyboard(),
        )
        await self._close_tg_http_client()
        trigger_graceful_restart(
            context=self.context,
            shutdown_event=getattr(self.context, "shutdown_event", None),
            reason="MANUAL_TELEGRAM_UPDATE",
            watchdog_delay_sec=3.5,
        )
        await asyncio.sleep(0.3)
        perform_self_restart_execv(reason="MANUAL_TELEGRAM_UPDATE")

    # -----------------------------------------------------------------------
    # 메시지 및 콜백 디스패처 (4대 메뉴 체제 & /assassin · /reset_assassin · /mode 지원)
    # -----------------------------------------------------------------------
    async def _handle_command_or_text(
        self, chat_id: str, raw_text: str
    ) -> None:
        text = str(raw_text or "").strip()
        if not text:
            return

        clean_num_check = (
            text.replace(",", "").replace("$", "").replace(".", "").strip()
        )
        if clean_num_check.isdigit():
            prompt_ts = safe_float(
                self._awaiting_seed_input_chats.get(chat_id), 0.0
            )
            if (
                prompt_ts > 0.0
                and (time.monotonic() - prompt_ts)
                <= SEED_INPUT_PROMPT_TIMEOUT_SEC
            ):
                self._awaiting_seed_input_chats.pop(chat_id, None)
                await self._apply_new_seed_value(chat_id, text)
            else:
                self._awaiting_seed_input_chats.pop(chat_id, None)
                await self.send_message(
                    chat_id=chat_id,
                    text=(
                        "🔒 <b>[시드머니 오입력 방지 잠금]</b>\n"
                        "🔸 <b>⚙️ 전술 제어반</b>에서 <b>[💵 기준 시드머니 설정]</b> 버튼을 먼저 누르거나,\n"
                        f"<code>/seed {escape_html(clean_num_check)}</code> 명령어로 입력해 주세요."
                    ),
                    reply_markup=_build_main_reply_keyboard(),
                )
            return

        first_token = text.split()[0].lower()
        if "@" in first_token:
            first_token = first_token.split("@", 1)[0]

        if (
            first_token in ("/start", "/menu", "/help")
            or text == "⬅️ 메인 메뉴"
        ):
            st = self.context.ledger.get_state(TARGET_SYMBOL)
            msg = build_start_schedule_message(
                st, now_est=datetime.now(EST_TZ), context=self.context
            )
            await self.send_message(
                chat_id=chat_id,
                text=msg,
                reply_markup=_build_main_reply_keyboard(),
            )
            return

        if (
            first_token in ("/avwap", "/status", "/radar")
            or text in ("🔫 스나이퍼 레이더", "📡 스나이퍼 레이더")
        ):
            await self._render_and_send_avwap(chat_id=chat_id)
            return

        if first_token == "/sync" or text in (
            "🔄 잔고 동기화",
            "📜 지층 지시서",
            "💼 내 계좌 · 동기화",
        ):
            await self._render_and_send_sync(chat_id=chat_id)
            return

        if (
            first_token in ("/settlement", "/config")
            or text == "⚙️ 전술 제어반"
        ):
            await self._render_and_send_settlement(chat_id=chat_id)
            return

        if first_token == "/assassin" or text in (
            "🗡️ 모의 암살자",
            "🗡️ 암살자 레이더",
        ):
            await self._render_and_send_assassin_dashboard(chat_id=chat_id)
            return

        if first_token == "/reset_assassin":
            await self._reset_assassin_stats_command(chat_id=chat_id)
            return

        if first_token == "/mode":
            await self._toggle_portion_mode_command(chat_id=chat_id)
            return

        if first_token == "/seed":
            parts = text.split(maxsplit=1)
            if len(parts) >= 2:
                self._awaiting_seed_input_chats.pop(chat_id, None)
                await self._apply_new_seed_value(chat_id, parts[1])
            else:
                self._awaiting_seed_input_chats[chat_id] = time.monotonic()
                await self._render_and_send_settlement(chat_id=chat_id)
            return

        if first_token == "/reset_profit":
            await self._reset_realized_profit_only(chat_id=chat_id)
            return

        if first_token in ("/reset", "/reset_seed"):
            await self.send_message(
                chat_id=chat_id,
                text=(
                    "🔒 <b>[지층 리셋 영구 차단 안내]</b>\n"
                    "🔸 보유 지층 보호를 위해 리셋은 비활성화되었습니다.\n"
                    "🔸 수익만 0점 초기화하시려면 <code>/reset_profit</code> 을 입력해 주세요."
                ),
                reply_markup=_build_main_reply_keyboard(),
            )
            return

        if first_token == "/update" or text in (
            "🚀 시스템 업데이트",
            "🚀 업데이트",
        ):
            await self._execute_manual_update_command(chat_id=chat_id)
            return

    async def _handle_callback_query(self, cb: Dict[str, Any]) -> None:
        cb_id = str(cb.get("id") or "").strip()
        data = str(cb.get("data") or "").strip()
        msg_obj = (
            cb.get("message") if isinstance(cb.get("message"), dict) else {}
        )
        chat_obj = (
            msg_obj.get("chat") if isinstance(msg_obj.get("chat"), dict) else {}
        )
        chat_id = str(chat_obj.get("id") or self.chat_id or "").strip()
        msg_id = safe_int(msg_obj.get("message_id"), 0)

        if cb_id:
            await self._call_tg(
                "answerCallbackQuery",
                {"callback_query_id": cb_id},
                timeout_sec=5.0,
            )

        if not chat_id:
            return

        if data == "cmd_avwap":
            await self._render_and_send_avwap(
                chat_id=chat_id, edit_msg_id=msg_id
            )
        elif data == "cmd_sync":
            await self._render_and_send_sync(
                chat_id=chat_id, edit_msg_id=msg_id
            )
        elif data == "cmd_settlement":
            await self._render_and_send_settlement(
                chat_id=chat_id, edit_msg_id=msg_id
            )
        elif data == "cmd_assassin":
            await self._render_and_send_assassin_dashboard(
                chat_id=chat_id, edit_msg_id=None
            )
        elif data == "cmd_start":
            st = self.context.ledger.get_state(TARGET_SYMBOL)
            msg = build_start_schedule_message(
                st, now_est=datetime.now(EST_TZ), context=self.context
            )
            await self.edit_or_send_message(
                chat_id=chat_id,
                message_id=msg_id,
                text=msg,
                reply_markup=None,
            )
        elif data == "toggle_bot_active":
            updated_st = await self.context.ledger.toggle_bot_active()
            now_active = bool(updated_st.get("is_active", True))
            if now_active:
                await relock_stratum_on_bot_resume(
                    context=self.context, now_est=datetime.now(EST_TZ)
                )
            self.context.wakeup_event.set()
            await self._render_and_send_settlement(
                chat_id=chat_id, edit_msg_id=msg_id
            )
        elif data == "toggle_portion_mode":
            await self._toggle_portion_mode_command(
                chat_id=chat_id, edit_msg_id=msg_id
            )
        elif data == "prompt_seed_input":
            self._awaiting_seed_input_chats[chat_id] = time.monotonic()
            await self.send_message(
                chat_id=chat_id,
                text=(
                    "💵 <b>[기준 시드머니($) 입력 안내]</b>\n"
                    "🔸 <b>5분 이내</b>에 기준 시드 금액(숫자)을 입력해 주세요.\n"
                    "🔸 예시: <code>10000</code> 또는 <code>20000</code>"
                ),
                reply_markup=_build_main_reply_keyboard(),
            )
        elif data == "reset_profit_only":
            await self._reset_realized_profit_only(chat_id=chat_id)

    async def run_polling_loop(self) -> None:
        """
        🚨 [Case 81 : 텔레그램 전용 클라이언트 불사조 폴링 루프 (Immortal Supervisor Wrapper)]:
        """
        if not self.bot_token:
            logger.warning(
                "TELEGRAM_BOT_TOKEN 이 설정되지 않아 텔레그램 폴링 대기 모드로 전환합니다."
            )
            while not self.context.shutdown_event.is_set():
                await asyncio.sleep(10.0)
            return

        try:
            while not self.context.shutdown_event.is_set():
                try:
                    await self._ensure_tg_http_client()
                    await self._call_tg(
                        "deleteWebhook",
                        {"drop_pending_updates": False},
                        timeout_sec=8.0,
                    )
                    await self._flush_stale_updates_on_startup()
                    logger.info(
                        "📡 [Case 81 불사조 텔레그램 관제탑 폴링 루프 가동 완료] (last_update_id=%d)",
                        self._last_update_id,
                    )

                    while not self.context.shutdown_event.is_set():
                        try:
                            payload: Dict[str, Any] = {
                                "offset": self._last_update_id + 1,
                                "timeout": 15,
                                "allowed_updates": [
                                    "message",
                                    "callback_query",
                                ],
                            }
                            res = await self._call_tg(
                                "getUpdates", payload, timeout_sec=20.0
                            )
                            if isinstance(res, dict) and bool(res.get("ok")):
                                self._consecutive_poll_errors = 0
                                updates = res.get("result")
                                if isinstance(updates, list):
                                    for upd in updates:
                                        if self.context.shutdown_event.is_set():
                                            break
                                        if not isinstance(upd, dict):
                                            continue
                                        uid = safe_int(upd.get("update_id"), 0)
                                        if uid > self._last_update_id:
                                            await self._persist_offset_locally(
                                                uid
                                            )

                                        try:
                                            if isinstance(
                                                upd.get("callback_query"), dict
                                            ):
                                                await self._handle_callback_query(
                                                    upd["callback_query"]
                                                )
                                            elif isinstance(
                                                upd.get("message"), dict
                                            ):
                                                m_obj = upd["message"]
                                                c_obj = (
                                                    m_obj.get("chat")
                                                    if isinstance(
                                                        m_obj.get("chat"), dict
                                                    )
                                                    else {}
                                                )
                                                cid = str(
                                                    c_obj.get("id")
                                                    or self.chat_id
                                                    or ""
                                                ).strip()
                                                if (
                                                    self.chat_id
                                                    and cid
                                                    and cid != self.chat_id
                                                ):
                                                    continue
                                                txt = str(
                                                    m_obj.get("text") or ""
                                                ).strip()
                                                msg_date = safe_float(
                                                    m_obj.get("date"), 0.0
                                                )
                                                if (
                                                    msg_date > 0.0
                                                    and msg_date
                                                    < (self._boot_epoch - 1.0)
                                                    and (
                                                        txt.lower().startswith(
                                                            "/update"
                                                        )
                                                        or txt
                                                        in (
                                                            "🚀 시스템 업데이트",
                                                            "🚀 업데이트",
                                                        )
                                                    )
                                                ):
                                                    await self._ack_telegram_offset(
                                                        uid
                                                    )
                                                    continue
                                                if txt:
                                                    await self._handle_command_or_text(
                                                        chat_id=cid,
                                                        raw_text=txt,
                                                    )
                                        except asyncio.CancelledError:
                                            raise
                                        except Exception as disp_exc:
                                            logger.warning(
                                                "⚠️ [Case 81 텔레그램 개별 메시지 처리 예외 격리(폴링 유지)]: %s",
                                                disp_exc,
                                            )
                            else:
                                self._consecutive_poll_errors += 1
                                err_code = (
                                    safe_int(res.get("error_code"), 0)
                                    if isinstance(res, dict)
                                    else 0
                                )
                                if (
                                    err_code == 409
                                    or self._consecutive_poll_errors >= 3
                                ):
                                    await self._recreate_tg_http_client(
                                        reason=f"POLL_FAIL_CODE_{err_code}_CNT_{self._consecutive_poll_errors}"
                                    )
                                    self._consecutive_poll_errors = 0
                                    await asyncio.sleep(3.0)
                                else:
                                    await asyncio.sleep(1.5)
                        except asyncio.CancelledError:
                            raise
                        except Exception as inner_exc:
                            self._consecutive_poll_errors += 1
                            if self._consecutive_poll_errors >= 3:
                                await self._recreate_tg_http_client(
                                    reason=f"INNER_EXC_{type(inner_exc).__name__}"
                                )
                                self._consecutive_poll_errors = 0
                            logger.debug(
                                "텔레그램 폴링 내부 루프 일시 예외(자가 치유): %s",
                                inner_exc,
                            )
                            await asyncio.sleep(2.0)
                except asyncio.CancelledError:
                    break
                except Exception as sup_exc:
                    logger.warning(
                        "🛡️ [Case 81 불사조 감독 루프 재기동] 텔레그램 폴링 치명 예외 감지 -> 3초 후 세션 재생성 복구: %s",
                        sup_exc,
                    )
                    await self._recreate_tg_http_client(
                        reason="SUPERVISOR_RECOVERY"
                    )
                    await asyncio.sleep(3.0)
        finally:
            await self._close_tg_http_client()


async def telegram_polling_loop(
    context: Any, shutdown_event: Optional[asyncio.Event] = None
) -> None:
    """
    # [Case 81 호환 최상위 폴링 엔트리 함수]:
    """
    tg_obj = getattr(context, "tg", None)
    if tg_obj is not None and hasattr(tg_obj, "run_polling_loop"):
        await tg_obj.run_polling_loop()
        return
    ctrl = TelegramCommandController(context)
    await ctrl.run_polling_loop()


# 하위 호환 별칭 (타 모듈 임포트 호환 100% 보장)
TelegramBotController = TelegramCommandController
TelegramUiController = TelegramCommandController
SniperTelegramController = TelegramCommandController
