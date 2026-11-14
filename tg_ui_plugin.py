# -*- coding: utf-8 -*-
"""
# MODIFIED: tg_ui_plugin.py (Part 1/2 — 3단 운용모드 순환[스나이퍼(복리) ➔ 스나이퍼(단리) ➔ 바벨모드(60/30/10)] ·
# [모의 ⇄ 0주전환예약 ⇄ 실전] 암살자 분리 승격 스위치 · /barbell 및 /assassin_mode 관제 탑재 ·
# 스나이퍼 레이더[/avwap] 바벨 SGOV/현금버킷/별도수익금고 및 암살자 슬림 블록 결합 · Case 81 ~ 93)
인피니트 스노우볼 (Infinite Snowball) v3.0 — 텔레그램 관제탑 모바일 가로폭(36자) 칼맞춤 초슬림 UI 렌더러 및 불사조 폴링 컨트롤러
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import math
import os
import re
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
    ASSASSIN_MODE_ARMED_ON_ZERO,
    ASSASSIN_MODE_LIVE,
    ASSASSIN_MODE_SIMULATED,
    build_assassin_detail_dashboard_html,
    ensure_assassin_ledger,
    format_assassin_slim_radar_block,
    is_live_assassin_armed_on_zero,
    is_live_assassin_standalone_active,
    toggle_assassin_live_promotion,
)
from barbell_plugin import (
    PORTION_MODE_BARBELL,
    build_barbell_detail_dashboard_html,
    ensure_barbell_ledger,
    format_barbell_slim_radar_block,
    initialize_or_sync_barbell_on_mode_enter,
    is_barbell_mode,
    summarize_barbell_status,
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
    SNIPER_L1_TRAIL_ENABLED,
    SUB_FROZEN_DAYS_TRIGGER,
    SUB_MAX_TIERS_3,
    SUB_MAX_TOTAL_LOTS_4,
    next_cycled_portion_mode,
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
    get_sniper_l1_trail_ui_snapshot,
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

KRW_PER_USD_DEFAULT: float = 1380.0
SEED_INPUT_PROMPT_TIMEOUT_SEC: float = 300.0

# 3단 운용 정량모드 상수 (복리 COMP_08PCT ➔ 단리 SIMPLE_08PCT ➔ 바벨 BARBELL_60_30_10)
PORTION_MODE_COMPOUND: str = "COMP_08PCT"
PORTION_MODE_SIMPLE: str = "SIMPLE_08PCT"


# ---------------------------------------------------------------------------
# [유틸리티] HTML 이스케이프 · 3단 모드 판별 · DST 배지 · 폴더 식별자 및 안전 시드 추출
# ---------------------------------------------------------------------------
_VALID_TG_HTML_TAG_RE = re.compile(
    r"(</?(?:b|strong|i|em|u|ins|s|strike|del|code|pre)>"
    r"|<a\s+href=['\"][^'\"]+['\"]>|</a>)",
    re.IGNORECASE,
)
_RAW_AMP_RE = re.compile(
    r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)"
)


def escape_html(val: Any) -> str:
    return html.escape(str(val if val is not None else ""), quote=False)


def sanitize_telegram_html(text: Any) -> str:
    raw = str(text if text is not None else "")
    if not raw:
        return ""
    parts = _VALID_TG_HTML_TAG_RE.split(raw)
    out: List[str] = []
    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            out.append(part)
        else:
            cleaned = _RAW_AMP_RE.sub("&amp;", part)
            cleaned = cleaned.replace("<", "&lt;").replace(">", "&gt;")
            out.append(cleaned)
    return "".join(out)


def strip_telegram_html(text: Any) -> str:
    raw = str(text if text is not None else "")
    if not raw:
        return ""
    return html.unescape(_VALID_TG_HTML_TAG_RE.sub("", raw))


def _is_barbell_portion_mode(st_or_mode: Any) -> bool:
    if isinstance(st_or_mode, dict):
        m = str(st_or_mode.get("portion_mode") or PORTION_MODE_COMPOUND)
    else:
        m = str(st_or_mode or PORTION_MODE_COMPOUND)
    return is_barbell_mode(m)


def _is_simple_portion_mode(st_or_mode: Any) -> bool:
    if _is_barbell_portion_mode(st_or_mode):
        return False
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
    next_qty = safe_int(summary.get("next_target_qty"), 1)
    return f"<b>{next_qty}주</b>"


def _format_sub_quota_badge(summary: Dict[str, Any]) -> str:
    sub_next_qty = safe_int(summary.get("sub_next_target_qty"), 1)
    return f"<b>{sub_next_qty}주</b>"


def _build_main_reply_keyboard() -> Dict[str, Any]:
    """하단 4대 핵심 고정 메뉴(2x2) 단일화 유지"""
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
    return None


def _build_settlement_inline_keyboard(
    is_active: bool,
    *args: Any,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    # MODIFIED [3단 모드 순환(복리 ➔ 단리 ➔ 바벨) + [모의 ⇄ 실전] 암살자 분리 전환 스위치]:
    1) [스나이퍼 작동 ON / OFF 전환 (toggle_bot_active)]
    2) [스나이퍼(복리) ➔ 스나이퍼(단리) ➔ 바벨모드(60/30/10) 3단 순환 (toggle_portion_mode)]
    3) [[모의] 암살자 ⇄ [실전] 암살자 승격 분리 전환 (toggle_assassin_live · SOXL 0주 시 자동 전환)]
    4) [💵 기준 시드머니($) 설정 (prompt_seed_input)]
    5) [⚖️ 바벨 관제 (/barbell) | 🗡️ 암살자 관제 (/assassin)]
    """
    portion_mode = kwargs.get("portion_mode")
    if portion_mode is None and args:
        portion_mode = args[0]

    assassin_exec_mode = str(
        kwargs.get("assassin_exec_mode") or ASSASSIN_MODE_SIMULATED
    ).upper()

    is_barbell = _is_barbell_portion_mode(portion_mode)
    is_simple = _is_simple_portion_mode(portion_mode)

    power_label = (
        "🔴 스나이퍼 작동 OFF 로 전환"
        if is_active
        else "🟢 스나이퍼 작동 ON 으로 전환"
    )

    if is_barbell:
        mode_label = "🔄 현재: ⚖️바벨모드(60/30/10) ➔ 📈스나이퍼(복리)"
    elif is_simple:
        mode_label = "🔄 현재: 💵스나이퍼(단리) ➔ ⚖️바벨모드(60/30/10)"
    else:
        mode_label = "🔄 현재: 📈스나이퍼(복리) ➔ 💵스나이퍼(단리)"

    if assassin_exec_mode == ASSASSIN_MODE_LIVE:
        assn_toggle_label = "🔥 암살자: [실전] 단독가동중 ➔ 🧪[모의] 복귀"
    elif assassin_exec_mode == ASSASSIN_MODE_ARMED_ON_ZERO:
        assn_toggle_label = "⏳ 암살자: SOXL 0주 전환예약 ➔ 🧪예약 취소"
    else:
        assn_toggle_label = "🗡️ 암살자: 🧪[모의] ➔ 🔥[실전] 승격(0주시 전환)"

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
                    "text": assn_toggle_label,
                    "callback_data": "toggle_assassin_live",
                },
            ],
            [
                {
                    "text": "💵 기준 시드머니($) 설정",
                    "callback_data": "prompt_seed_input",
                },
            ],
            [
                {
                    "text": "⚖️ 바벨 관제 (/barbell)",
                    "callback_data": "cmd_barbell",
                },
                {
                    "text": "🗡️ 암살자 관제 (/assassin)",
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
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    dst_str = _get_dst_badge(dt_now)

    lines = [
        f"🐂 <b>[SOXL 스나이퍼 · 바벨 · 암살자 ({escape_html(dst_str)})]</b>",
        "──────────────",
        "🔫 <b>스나이퍼 레이더</b> : 타점 · 지층 · 바벨 · 암살자 요약",
        "🔄 <b>잔고 동기화</b> : 잔고 · 예수금 · 수익금고 해부",
        "⚙️ <b>전술 제어반</b> : 전원 · 복리/단리/바벨 · 암살자승격",
        "🚀 <b>시스템 업데이트</b> : 최신 코드 무중단 동기화",
        "⚖️ <code>/barbell</code> : 바벨(60/30/10) &amp; 별도수익금고 상세",
        "🗡️ <code>/assassin</code> : [모의/실전] 암살자 순수 10G 상세",
    ]
    return "\n".join(lines)


def _format_multi_grid_stratum_lines(
    summary: Dict[str, Any],
    live_price: float,
    is_ext_sell_only: bool = False,
    is_late_cutoff: bool = False,
    live_rsi_14: float = 50.0,
    live_assassin_active: bool = False,
    main_trail_ui: Optional[Dict[str, Any]] = None,
    closed_ha_ok: bool = True,
    pull_ha_badge: str = "",
) -> List[str]:
    held_sh = safe_int(summary.get("held_shares"), 0)
    buckets = summary.get("buckets", [])
    lines: List[str] = []

    if held_sh <= 0 or not buckets:
        if live_assassin_active:
            lines.append(
                "⚪ <b>[본그리드: 0주]</b> 🔥실전 암살자 단독모드 위임중"
            )
        elif is_ext_sell_only:
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

        if SNIPER_L1_TRAIL_ENABLED and not is_ext_sell_only:
            tr_m = main_trail_ui if isinstance(main_trail_ui, dict) else {}
            l1_ign_p = safe_float(summary.get("l1_ignite_100_price"), l1_t)
            if bool(tr_m.get("armed")):
                st_p = safe_float(tr_m.get("active_stop_p"), 0.0)
                if bool(tr_m.get("stepped_125")) and st_p > 0.0:
                    lines.append(
                        f"⚡ <b>[1층: {l1_qty_label}·${b1.actual_cost_usd:,.0f}]</b> "
                        f"<b>${b1.book_price:.2f}</b> ➔ 스탑 <b>${st_p:.2f}</b> ({g1_sign}{l1_g:.2f}%·👑1.40%락)"
                    )
                else:
                    lk_m_p = safe_float(
                        tr_m.get("lock_125_p"),
                        safe_float(summary.get("l1_lock_125_price"), l1_ign_p),
                    )
                    lines.append(
                        f"⚡ <b>[1층: {l1_qty_label}·${b1.actual_cost_usd:,.0f}]</b> "
                        f"<b>${b1.book_price:.2f}</b> ➔ <b>1분HA추적</b>(락${lk_m_p:.2f}) ({g1_sign}{l1_g:.2f}%·🔥무스탑)"
                    )
            else:
                fg_c = safe_int(tr_m.get("forgive_count"), 0)
                fg_b = f"·💡용서{fg_c}" if fg_c > 0 else "·점화1.25%"
                lines.append(
                    f"⚡ <b>[1층: {l1_qty_label}·${b1.actual_cost_usd:,.0f}]</b> "
                    f"<b>${b1.book_price:.2f}</b> ➔ <b>${l1_ign_p:.2f}</b> ({g1_sign}{l1_g:.2f}%{fg_b})"
                )
        else:
            l1_ov_lock_note = "·장외+1.5%" if is_ext_sell_only else ""
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
        ha_tag = pull_ha_badge or (
            "🕯️1분HA양봉OK" if closed_ha_ok else "🌑무머리HA음봉패스"
        )
        pull_ha_wait = bool(
            summary.get("reentry_signal_type")
            == "HOLD_PULLBACK_SHAVED_HA_BEAR"
        )
        if is_ext_sell_only:
            lines.append(
                f"⚡ <b>[1층: 공석]</b> 🔒장외잠금 · 04:07 재장전{cap_note}"
            )
        elif pull_ha_wait:
            lines.append(
                f"⚡ <b>[1층: 공석]</b> 🌑눌림(-1%) 무머리1분HA음봉 패스(다음1분 대기){cap_note}"
            )
        elif is_late_cutoff:
            lines.append(
                f"⚡ <b>[1층: 공석]</b> 🛡️돌파차단 · 눌림(-1%·{ha_tag}) 감시{cap_note}"
            )
        elif live_rsi_14 > 50.0:
            lines.append(
                f"⚡ <b>[1층: 공석]</b> 눌림(-1%·{ha_tag})/🛡️돌파차단(RSI {live_rsi_14:.1f}&gt;50){cap_note}"
            )
        else:
            lines.append(
                f"⚡ <b>[1층: 공석]</b> 눌림(-1%·{ha_tag})/돌파(RSI&lt;=50){cap_note}"
            )

    act_l2 = bool(summary.get("has_active_l2", False))
    vac_l2 = bool(summary.get("is_l2_vacant", False))
    i37_b = list(summary.get("inv_3_7_buckets") or [])

    if act_l2 and upper_buckets:
        b2 = upper_buckets[0]
        mul_u = 1.0 + rise_u_pct / 100.0
        fb_t2 = math.ceil((b2.book_price * mul_u - 1e-9) * 100.0) / 100.0
        raw_t2 = safe_float(summary.get("l2_raw_target_price"), fb_t2)
        eff_t2 = safe_float(summary.get("l2_eff_target_price"), raw_t2)
        tm = main_trail_ui if isinstance(main_trail_ui, dict) else {}
        if (
            active_l1
            and SNIPER_L1_TRAIL_ENABLED
            and (not is_ext_sell_only)
            and bool(tm.get("armed"))
        ):
            stp = safe_float(tm.get("active_stop_p"), 0.0)
            if stp > eff_t2:
                eff_t2 = stp
        inv2 = bool(
            active_l1
            and (
                bool(summary.get("l2_is_inverted_with_l1", False))
                or eff_t2 > raw_t2 + 1e-6
            )
        )
        g2 = safe_float(summary.get("l2_indiv_gain_pct"), 0.0)
        s2 = "+" if g2 >= 0.0 else ""
        q2 = f"👑{b2.lot_count}회" if b2.lot_count > 1 else f"{b2.qty}주"
        ib = "·🤝1층동반" if inv2 else ""
        lines.append(
            f"🗡️ <b>[2층: {q2}·${b2.actual_cost_usd:,.0f}]</b> "
            f"<b>${b2.book_price:.2f}</b> ➔ <b>${eff_t2:.2f}</b> "
            f"({s2}{g2:.2f}%{ib})"
        )
    elif vac_l2:
        lines.append("🗡️ <b>[2층: 공석]</b> 채굴완료 · 공석활주로 개방")

    if i37_b:
        ic = len(i37_b)
        iq = safe_int(summary.get("inv_3_7_qty"), 0)
        ia = safe_float(summary.get("inv_3_7_cost_usd"), 0.0)
        iwp = safe_float(summary.get("inv_3_7_wma_price"), 0.0)
        iwt = safe_float(summary.get("inv_3_7_wma_target_price"), 0.0)
        ig = safe_float(summary.get("inv_3_7_gain_pct"), 0.0)
        igs = "+" if ig >= 0.0 else ""
        rl = "3층" if ic == 1 else f"3~{ic + 2}층"
        lines.append(
            f"📦 <b>[{rl}: {iq}주·${ia:,.0f}]</b> "
            f"<b>${iwp:.2f}</b> ➔ 졸업 <b>${iwt:.2f}</b> ({igs}{ig:.2f}%)"
        )
        for idx_i, bu in enumerate(i37_b):
            t_no = idx_i + 3
            bu_g = (
                ((live_price - bu.book_price) / bu.book_price) * 100.0
                if (live_price > 0.0 and bu.book_price > 0.0)
                else 0.0
            )
            bg_s = "+" if bu_g >= 0.0 else ""
            tt = (
                f"{t_no}층(👑{bu.lot_count}회·${bu.actual_cost_usd:,.0f})"
                if bu.lot_count > 1
                else f"{t_no}층({bu.qty}주·${bu.actual_cost_usd:,.0f})"
            )
            lines.append(
                f"  ▫️ <b>{tt}</b>: ${bu.book_price:.2f} "
                f"({bg_s}{bu_g:.2f}%·이평졸업)"
            )

    return lines


def _format_sub_grid_stratum_lines(
    summary: Dict[str, Any],
    live_price: float,
    is_ext_sell_only: bool = False,
    is_late_cutoff: bool = False,
    live_rsi_14: float = 50.0,
    sub_trail_ui: Optional[Dict[str, Any]] = None,
    closed_ha_ok: bool = True,
    pull_ha_badge: str = "",
) -> List[str]:
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
        if SNIPER_L1_TRAIL_ENABLED and not is_ext_sell_only:
            tr_s = sub_trail_ui if isinstance(sub_trail_ui, dict) else {}
            sl1_ign_p = safe_float(
                summary.get("sub_l1_ignite_100_price"), sl1_t
            )
            if bool(tr_s.get("armed")):
                sst_p = safe_float(tr_s.get("active_stop_p"), 0.0)
                if bool(tr_s.get("stepped_125")) and sst_p > 0.0:
                    lines.append(
                        f"  ⚡ <b>[서브1층: {sl1_label}·${sb1.actual_cost_usd:,.0f}]</b> "
                        f"<b>${sb1.book_price:.2f}</b> ➔ 스탑 <b>${sst_p:.2f}</b> ({sg1_s}{sl1_g:.2f}%·👑1.25%락)"
                    )
                else:
                    slk_p = safe_float(
                        tr_s.get("lock_125_p"),
                        safe_float(
                            summary.get("sub_l1_lock_125_price"), sl1_ign_p
                        ),
                    )
                    lines.append(
                        f"  ⚡ <b>[서브1층: {sl1_label}·${sb1.actual_cost_usd:,.0f}]</b> "
                        f"<b>${sb1.book_price:.2f}</b> ➔ <b>1분HA추적</b>(락${slk_p:.2f}) ({sg1_s}{sl1_g:.2f}%·🔥무스탑)"
                    )
            else:
                sfg_c = safe_int(tr_s.get("forgive_count"), 0)
                sfg_b = f"·💡용서{sfg_c}" if sfg_c > 0 else "·점화1%"
                lines.append(
                    f"  ⚡ <b>[서브1층: {sl1_label}·${sb1.actual_cost_usd:,.0f}]</b> "
                    f"<b>${sb1.book_price:.2f}</b> ➔ <b>${sl1_ign_p:.2f}</b> ({sg1_s}{sl1_g:.2f}%{sfg_b})"
                )
        else:
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
        s_ha_tag = pull_ha_badge or (
            "🕯️1분HA양봉OK" if closed_ha_ok else "🌑무머리HA음봉패스"
        )
        sub_pull_ha_wait = bool(
            summary.get("sub_reentry_signal_type")
            == "HOLD_PULLBACK_SHAVED_HA_BEAR"
        )
        if sub_lots >= sub_max_lots:
            lines.append(
                f"  ⚡ <b>[서브1층: 공석]</b> 🔒{sub_max_lots}회 상한 도달 (익절 대기)"
            )
        elif is_ext_sell_only:
            lines.append(
                f"  ⚡ <b>[서브1층: 공석]</b> 🔒장외잠금 · 04:07 재장전{s_cap_note}"
            )
        elif sub_pull_ha_wait:
            lines.append(
                f"  ⚡ <b>[서브1층: 공석]</b> 🌑눌림(-1%) 무머리1분HA음봉 패스(다음1분 대기){s_cap_note}"
            )
        elif is_late_cutoff:
            lines.append(
                f"  ⚡ <b>[서브1층: 공석]</b> 🛡️돌파차단 · 눌림(-1%·{s_ha_tag}) 감시{s_cap_note}"
            )
        elif live_rsi_14 > 50.0:
            lines.append(
                f"  ⚡ <b>[서브1층: 공석]</b> 눌림(-1%·{s_ha_tag})/🛡️돌파차단(RSI {live_rsi_14:.1f}&gt;50){s_cap_note}"
            )
        else:
            lines.append(
                f"  ⚡ <b>[서브1층: 공석]</b> 눌림(-1%·{s_ha_tag})/돌파(RSI&lt;=50){s_cap_note}"
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
    closed_ha_shaved_bear = bool(met.get("closed_ha_shaved_bear", False))
    closed_ha_bull = bool(met.get("closed_ha_bull", True))
    closed_ha_ready = bool(met.get("closed_ha_ready", True))
    closed_ha_ok = bool(closed_ha_ready and (not closed_ha_shaved_bear))
    if not closed_ha_ok:
        pull_ha_badge = "🌑무머리HA음봉패스"
    elif closed_ha_bull:
        pull_ha_badge = "🕯️1분HA양봉OK"
    else:
        pull_ha_badge = "🕯️윗꼬리HA음봉OK"

    summary = summarize_stratum_portfolio(
        st,
        live_price=lp,
        now_est=dt_now,
        rsi_14=rsi_14,
        closed_ha_shaved_bear=closed_ha_shaved_bear,
        closed_ha_bull=closed_ha_bull,
        closed_ha_ready=closed_ha_ready,
    )
    is_active = bool(st.get("is_active", True))
    is_barbell = _is_barbell_portion_mode(st)
    is_simple = _is_simple_portion_mode(st)

    live_assn_active = (
        is_live_assassin_standalone_active(context)
        if context is not None
        else False
    )
    armed_assn = (
        is_live_assassin_armed_on_zero(context)
        if context is not None
        else False
    )

    if is_barbell:
        p_mode_short = "⚖️바벨(60/30/10)"
    elif is_simple:
        p_mode_short = "💵인출형"
    else:
        p_mode_short = "📈복리형"

    active_badge = (
        "🔥실전암살자단독"
        if live_assn_active
        else ("🟢 가동중" if is_active else "🔴 정지중")
    )
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
        context, st, TARGET_SYMBOL, now_est=dt_now
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
    if live_assn_active:
        shield_line = "🗡️ <b>[실전 암살자 단독모드]</b> 스나이퍼/바벨 신규매수 분리잠금"
    elif armed_assn:
        shield_line = "⏳ <b>[암살자 전환 예약]</b> 현 사이클 0주 졸업 즉시 실전암살자 전환"
    elif in_buy_shield:
        shield_line = (
            f"🛡️ <b>[매수 보호대기]</b> <b>{rem_buy_sec:.0f}초</b> 후 익절감시 개시"
        )
    elif waiting_dep:
        shield_line = (
            f"🚨 <b>[시드고갈 대기]</b> 권장입금 <b>${req_dep_usd:,.0f}</b> (잔여 {avail_res_cnt}/{max_res_cnt}회)"
        )
    elif is_ext_sell_only:
        c37 = safe_int(summary.get("inv_3_7_tier_count"), 0)
        t37 = safe_float(summary.get("inv_3_7_wma_target_price"), 0.0)
        if c37 > 0 and t37 > 0.0:
            shield_line = (
                f"🌃 <b>[장외 1·2층채굴 · 3~7층졸업]</b> "
                f"이평 <b>${t37:.2f}</b> (매수잠금)"
            )
        elif held_sh > 0:
            shield_line = (
                "🌃 <b>[장외 1·2층 개별채굴]</b> 목표가 즉시 익절 (04:07 매수해금)"
            )
        elif sub_upper_tier_cnt > 0:
            swt = safe_float(summary.get("sub_upper_wma_target_price"), 0.0)
            swn = f"${swt:.2f}" if swt > 0.0 else "+1.0%"
            shield_line = (
                f"🌃 <b>[장외 서브통합졸업 감시]</b> 목표 <b>{swn}</b> (매수잠금)"
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

    trail_ui_snap = (
        get_sniper_l1_trail_ui_snapshot(context, symbol=TARGET_SYMBOL)
        if context is not None
        else {"main": {}, "sub": {}}
    )
    main_tr_ui = trail_ui_snap.get("main") or {}
    sub_tr_ui = trail_ui_snap.get("sub") or {}
    if not shield_line and (
        bool(main_tr_ui.get("armed")) or bool(sub_tr_ui.get("armed"))
    ):
        shield_line = "🔥 <b>[1층 스텝트레일링 0.4s 추적중]</b> 하드보존·완결HA·용서 가동"

    stratum_lines = _format_multi_grid_stratum_lines(
        summary,
        lp,
        is_ext_sell_only=is_ext_sell_only,
        is_late_cutoff=is_late_cutoff,
        live_rsi_14=rsi_14,
        live_assassin_active=live_assn_active,
        main_trail_ui=main_tr_ui,
        closed_ha_ok=closed_ha_ok,
        pull_ha_badge=pull_ha_badge,
    )
    sub_stratum_lines = _format_sub_grid_stratum_lines(
        summary,
        lp,
        is_ext_sell_only=is_ext_sell_only,
        is_late_cutoff=is_late_cutoff,
        live_rsi_14=rsi_14,
        sub_trail_ui=sub_tr_ui,
        closed_ha_ok=closed_ha_ok,
        pull_ha_badge=pull_ha_badge,
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
    if live_assn_active:
        gate_header_line = "🎯 <b>[다음 매수 타점 · 실전 암살자 위임]</b>"
        gate_cond_lines.append(
            "▫️ 04:07 ~ 08:14 EST 순수 10대 급락 게이트 포착 시 단발 타격"
        )
    elif held_sh <= 0:
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
            brk_str = f"돌파차단(RSI {rsi_14:.1f}&gt;50)"
        else:
            brk_str = f"돌파 <b>${brk_p:.2f}</b>(RSI&lt;=50)"
        cap_str = f" · 상한 ${l2_cap_p:.2f}" if l2_cap_p > 0.0 else ""
        gate_cond_lines.append(
            f"▫️ 눌림 <b>${pull_p:.2f}</b>({pull_ha_badge}) / {brk_str} 시 {quota_badge_str} 매수"
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
    if sub_sh > 0 and not live_assn_active:
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

    cash_title = "SOXL현금(60%)" if is_barbell else "가용현금"

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
        # MODIFIED [Case 102]: 바벨 미졸업 환수현금 보존 및 0주 졸업 시 SGOV 일괄 원복 표기
        repay_timing_lbl = (
            "환수현금보존·0주SGOV" if is_barbell else "졸업시 원복"
        )
        lines.append(
            f"💉 자동수혈: <b>{used_res_cnt}회분</b> 사용 (${inj_res_usd:,.2f} · {repay_timing_lbl})"
        )
    lines.extend(
        [
            cycle_profit_line,
            f"💰 전체누적 실현익: <b>{n_sign}${abs(cum_net):,.2f}</b> (졸업 {comp_cycles}회 · {n_sign}{abs(real_roi):.1f}%)",
            f"💵 {cash_title}: <b>${free_cash:,.2f}</b> · 현재평가: <b>${mark_eq:,.0f}</b> ({m_sign}{mark_roi:.1f}%)",
            f"🎓 전량졸업예정: <b>${proj_grad_eq:,.2f}</b> ({pg_sign}{proj_grad_roi:.2f}% 확정예정)",
        ]
    )

    if context is not None:
        try:
            b_block = format_barbell_slim_radar_block(context=context)
            if b_block:
                lines.append(b_block)
        except Exception:
            pass
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
# MODIFIED: tg_ui_plugin.py (Part 2/2 — /sync · /settlement · /barbell · /assassin · /assassin_mode · /mode 3단 순환 및 불사조 폴링 컨트롤러)
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
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    h_info = (holdings or {}).get(TARGET_SYMBOL, {})
    lp = safe_float(
        live_price,
        safe_float(
            h_info.get("last_price"), safe_float(st.get("anchor_price"), 0.0)
        ),
    )
    summary = summarize_stratum_portfolio(st, live_price=lp, now_est=dt_now)
    is_barbell = _is_barbell_portion_mode(st)
    is_simple = _is_simple_portion_mode(st)
    if is_barbell:
        mode_title = "⚖️바벨모드(60/30/10)"
    elif is_simple:
        mode_title = "💵인출형(단리)"
    else:
        mode_title = "📈자산증식형(복리)"

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

    base_portion_unit = max(
        1.0, safe_float(summary.get("next_portion_budget"), init_seed * 0.08)
    )
    withdrawable_surplus_usd = safe_float(
        summary.get("withdrawable_surplus_usd"), 0.0
    )
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

    cash_row_label = "SOXL가용현금" if is_barbell else "가용현금"

    lines = [
        f"🔄 <b>[잔고 동기화 · {mode_title}]</b>",
        "──────────────",
        "📊 <b>[시드 배분 및 층별 자산 시각화]</b>",
        f"{gauge_bar} (주식 {stock_alloc_pct:.0f}% : 현금 {cash_alloc_pct:.0f}%)",
        f"▫️ 🟦본그리드: <b>${inv_main:,.0f}</b> ({main_alloc_pct:.0f}% · {held_tiers}개층 {held_sh}주)",
        f"▫️ 🟨서브그리드: <b>${inv_sub:,.0f}</b> ({sub_alloc_pct:.0f}% · {sub_tiers}개층 {sub_sh}주)",
        f"▫️ 🟩{cash_row_label}: <b>${free_cash:,.0f}</b> ({cash_alloc_pct:.0f}% · 서브가용 ${avail_idle:,.0f})",
        "──────────────",
        "🔄 <b>[현재 사이클 vs 전체 누적 수익]</b>",
        f"▫️ 설정 기준시드: <b>${init_seed:,.2f}</b> ({mode_title})",
        f"▫️ 금일 확정수익: <b>{d_sign}${abs(day_net):,.2f}</b> ({d_sign}{abs(day_krw):,}원)",
        f"▫️ 이번사이클익: <b>{cyc_sign}${abs(cyc_net):,.2f}</b> ({cyc_ev}회 익절 · 서브 {cyc_sub_sign}${abs(cyc_sub_net):,.2f})",
        f"▫️ 직전졸업수익: <b>{last_c_sign}${abs(last_cyc_net):,.2f}</b> (총 {comp_cycles}회 사이클 졸업)",
        f"▫️ 전체누적수익: <b>{n_sign}${abs(cum_net):,.2f}</b> ({n_sign}{abs(real_roi):.2f}% 현금확정!)",
    ]
    if is_barbell and context is not None:
        b_info = summarize_barbell_status(context, st_soxl=st)
        lines.append(
            f"▫️ 🏦별도수익금고: 누적 <b>+${b_info['vault_realized_profit_usd']:,.2f}</b> (가용 <b>${b_info['vault_available_usd']:,.2f}</b> · 영구격리)"
        )
        lines.append(
            f"▫️ 🛡️SGOV/대기현금: <b>{b_info['sgov_held_qty']}주</b>(${b_info['sgov_invested_usd']:,.0f}) / 현금버킷 <b>${b_info['cash_bucket_usd']:,.0f}</b>"
        )
    elif is_simple:
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
            "🏦 <b>[자동수혈 및 수수료 현황]</b>",
            f"▫️ 토스 주문가능: <b>${broker_bp_usd:,.2f}</b> (미할당 +${unalloc_dep_usd:,.2f})",
            f"▫️ 자동수혈 사용: 현재 <b>{used_res_cnt}회분</b>(${inj_res_usd:,.2f} · 누적 {tot_res_cnt}회)",
            f"▫️ 적용 수수료: 편도 {us_comm_pct:.3g}% / 왕복 <b>{rt_fee_pct:.2f}%</b>",
        ]
    )

    if context is not None:
        try:
            b_block = format_barbell_slim_radar_block(context=context)
            if b_block:
                lines.append(b_block)
        except Exception:
            pass
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
    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    lp = safe_float(live_price, safe_float(st.get("anchor_price"), 100.0))
    summary = summarize_stratum_portfolio(st, live_price=lp, now_est=dt_now)

    is_active = bool(st.get("is_active", True))
    is_barbell = _is_barbell_portion_mode(st)
    is_simple = _is_simple_portion_mode(st)

    assn_exec_m = ASSASSIN_MODE_SIMULATED
    if context is not None:
        try:
            assn_exec_m = str(
                ensure_assassin_ledger(context)
                .get_state()
                .get("execution_mode")
                or ASSASSIN_MODE_SIMULATED
            ).upper()
        except Exception:
            assn_exec_m = ASSASSIN_MODE_SIMULATED

    power_str = "🟢 가동 중 (ON)" if is_active else "🔴 일시정지 (OFF)"
    if is_barbell:
        p_mode_str = "⚖️ 바벨모드 (60/30/10 · 수익금고 격리)"
    elif is_simple:
        p_mode_str = "💵 스나이퍼 (단리 · 시드 8%/4% 고정)"
    else:
        p_mode_str = "📈 스나이퍼 (복리 · 코어자산 8%/4%)"

    if assn_exec_m == ASSASSIN_MODE_LIVE:
        assn_mode_str = "🔥 [실전] 단독 가동중 (스나이퍼/바벨 정지)"
    elif assn_exec_m == ASSASSIN_MODE_ARMED_ON_ZERO:
        assn_mode_str = "⏳ SOXL 0주 졸업 시 [실전] 자동전환 예약"
    else:
        assn_mode_str = "🧪 [모의] 백그라운드 상시 관제중"

    init_seed = safe_float(summary.get("initial_seed_usd"), 10000.0)
    real_eq = safe_float(summary.get("realized_equity_usd"), init_seed)
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

    withdrawable_surplus_usd = safe_float(
        summary.get("withdrawable_surplus_usd"), 0.0
    )
    self_reserve_portions = safe_float(
        summary.get("self_reserve_portions"), 0.0
    )

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
        f"3️⃣ 암살자 승격: <b>{assn_mode_str}</b> (<code>/assassin_mode</code>)",
        f"4️⃣ 기준 시드: <b>${init_seed:,.2f}</b> (확정자산 ${real_eq:,.2f})",
        f"   ▫️ 이번사이클익: <b>{cyc_sign}${abs(cyc_net):,.2f}</b> ({cyc_ev}회 익절 · 졸업 {comp_cycles}회)",
        f"   ▫️ 1회 정량: 본 ${next_bud:,.0f}({quota_badge_str}) · 서브 ${sub_bud:,.0f}({sub_quota_badge})",
        f"   ▫️ 격리/잉여금: <b>${withdrawable_surplus_usd:,.0f}</b> (탄창 <b>+{self_reserve_portions:.1f}회분</b>)",
        f"5️⃣ 보유/자동수혈: 본 <b>{held_sh}주</b>({held_tiers}층·{lot_ctrl_str}) · 수혈 <b>{used_res_cnt}회분</b>(${inj_res_usd:,.0f})",
        f"   ▫️ 서브(상시): <b>{sub_sh}주</b>({sub_lots}/{sub_max_lots}회) · 동결 {main_frozen}/{SUB_FROZEN_DAYS_TRIGGER}일 · 졸업 {sub_comp}회",
        "──────────────",
        "🧹 <code>/reset_profit</code> : 수익/금고 0점 초기화 (주식·시드 보존)",
        "⚖️ <code>/barbell</code> : 바벨 60/30/10 상세 · 🗡️ <code>/assassin</code> : 암살자 상세",
    ]

    if context is not None:
        try:
            b_block = format_barbell_slim_radar_block(context=context)
            if b_block:
                lines.append(b_block)
        except Exception:
            pass
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
# [핵심 2] 텔레그램 명령어 및 콜백 비동기 컨트롤러 (TelegramCommandController)
# ---------------------------------------------------------------------------
class TelegramCommandController:
    def __init__(
        self,
        context: Any,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> None:
        self.context: Any = context
        self.base_dir: str = get_bot_base_dir(
            getattr(context, "base_dir", None)
        )
        self.bot_token: str = str(
            bot_token
            or os.environ.get("TELEGRAM_BOT_TOKEN")
            or os.environ.get("TG_BOT_TOKEN")
            or os.environ.get("BOT_TOKEN")
            or ""
        ).strip()
        self.chat_id: str = str(
            chat_id
            or os.environ.get("TELEGRAM_CHAT_ID")
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
        async with self._tg_client_lock:
            client = self._tg_http_client
            self._tg_http_client = None
            if client is not None:
                try:
                    await asyncio.wait_for(client.aclose(), timeout=2.0)
                except Exception:
                    pass

    async def _recreate_tg_http_client(self, reason: str = "ERROR") -> None:
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
        is_html = str(parse_mode or "").upper().strip() == "HTML"
        clean_text = (
            sanitize_telegram_html(text) if is_html else str(text or "")
        )
        payload: Dict[str, Any] = {
            "chat_id": target_chat,
            "text": clean_text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        res = await self._call_tg("sendMessage", payload, timeout_sec=10.0)
        if not bool(res.get("ok")):
            payload.pop("parse_mode", None)
            payload["text"] = strip_telegram_html(clean_text)
            res = await self._call_tg("sendMessage", payload, timeout_sec=10.0)
        return bool(res.get("ok"))

    async def edit_or_send_message(
        self,
        chat_id: str,
        message_id: Optional[int],
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> bool:
        clean_text = sanitize_telegram_html(text)
        if message_id is not None and message_id > 0:
            payload: Dict[str, Any] = {
                "chat_id": str(chat_id),
                "message_id": int(message_id),
                "text": clean_text,
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
            text=clean_text, chat_id=chat_id, reply_markup=reply_markup
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
        text = "<b>✅ 서버가 정상 작동 중입니다.</b>"
        return await self.send_message(
            text=text, reply_markup=_build_main_reply_keyboard()
        )

    def _current_assassin_exec_mode(self) -> str:
        try:
            return str(
                ensure_assassin_ledger(self.context)
                .get_state()
                .get("execution_mode")
                or ASSASSIN_MODE_SIMULATED
            ).upper()
        except Exception:
            return ASSASSIN_MODE_SIMULATED

    async def _refresh_live_price_and_metrics(
        self,
    ) -> Tuple[float, Dict[str, Any]]:
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
            or not bool(base_met.get("anchors_ready", False))
            or not bool(base_met.get("closed_ha_ready", False))
            or safe_float(base_met.get("prev_bar_close"), 0.0) <= 0.0
        ):
            try:
                c_1m = await self.context.api.get_candles_1m(
                    symbol=TARGET_SYMBOL, total_count=400
                )
                c_1d = await self.context.api.get_candles_1d(
                    symbol=TARGET_SYMBOL, count=10
                )
                if c_1m or c_1d:
                    base_met = await asyncio.to_thread(
                        compute_soxl_quant_metrics_1m,
                        c_1m or [],
                        live_p,
                        now_est,
                        c_1d or [],
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
            if not is_live_assassin_standalone_active(self.context):
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
                assassin_exec_mode=self._current_assassin_exec_mode(),
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

    async def _render_and_send_barbell_dashboard(
        self, chat_id: str, edit_msg_id: Optional[int] = None
    ) -> None:
        msg = await build_barbell_detail_dashboard_html(context=self.context)
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
        """
        3단 운용 모드 순환 실행기:
        스나이퍼(복리 · COMP_08PCT) ➔ 스나이퍼(단리 · SIMPLE_08PCT) ➔ 바벨모드(BARBELL_60_30_10) ➔ 스나이퍼(복리)
        """
        st_cur = self.context.ledger.get_state(TARGET_SYMBOL)
        next_m = next_cycled_portion_mode(st_cur.get("portion_mode"))
        updated_st = await self.context.ledger.update_state(
            TARGET_SYMBOL, portion_mode=next_m
        )

        # 바벨 모드 진입 시 동기화 (단, 실전 암살자 단독 가동 중에는 복귀 첫 틱까지 유예)
        if is_barbell_mode(next_m):
            if is_live_assassin_standalone_active(self.context):
                await ensure_barbell_ledger(self.context).update_state(
                    is_initialized=False
                )
            else:
                await initialize_or_sync_barbell_on_mode_enter(self.context)
                updated_st = self.context.ledger.get_state(TARGET_SYMBOL)

        self.context.wakeup_event.set()
        if edit_msg_id is not None and edit_msg_id > 0:
            await self._render_and_send_settlement(
                chat_id=chat_id, edit_msg_id=edit_msg_id
            )
            return

        live_p, _ = await self._refresh_live_price_and_metrics()
        summary = summarize_stratum_portfolio(updated_st, live_price=live_p)
        if _is_barbell_portion_mode(updated_st):
            m_lbl = "⚖️ 바벨모드 (60/30/10 · 수익금고 영구격리)"
        elif _is_simple_portion_mode(updated_st):
            m_lbl = "💵 스나이퍼 (단리 · SIMPLE_08PCT)"
        else:
            m_lbl = "📈 스나이퍼 (복리 · COMP_08PCT)"

        next_bud = safe_float(summary.get("next_portion_budget"), 800.0)
        sub_bud = safe_float(summary.get("sub_next_portion_budget"), 400.0)
        await self.send_message(
            chat_id=chat_id,
            text=(
                "🔄 <b>[3단 운용 정량모드 순환 완료]</b>\n"
                f"▫️ 현재 모드: <b>{m_lbl}</b>\n"
                f"▫️ 본그리드 1회(8%): <b>${next_bud:,.2f}</b> ({_format_case67_quota_badge(summary)})\n"
                f"▫️ 서브그리드 1회(4%): <b>${sub_bud:,.2f}</b> ({_format_sub_quota_badge(summary)})"
            ),
            reply_markup=_build_main_reply_keyboard(),
        )

    async def _toggle_assassin_live_command(
        self, chat_id: str, edit_msg_id: Optional[int] = None
    ) -> None:
        res = await toggle_assassin_live_promotion(self.context)
        st_code = str(res.get("status") or "")

        if st_code == "PROMOTED_LIVE_IMMEDIATELY":
            note_txt = (
                "🔥 <b>[[실전] 암살자 단독 모드 즉시 전환 완료!]</b>\n"
                "🔸 현재 SOXL 0주 상태가 확인되어 즉시 실전 암살자 모드로 전환되었습니다.\n"
                "🔸 스나이퍼/바벨 신규 매수는 분리 잠금되며, 당일 매수 금액은 <b>min(설정한 시드, 계좌 주문가능금액)</b> 으로 집행됩니다. (보유 SGOV는 수동 매도 위임)"
            )
        elif st_code == "ARMED_LIVE_ON_ZERO_SOXL":
            held_q = safe_int(res.get("soxl_held_qty"), 0)
            note_txt = (
                "⏳ <b>[SOXL 0주 졸업 시 [실전] 암살자 전환 예약 완료]</b>\n"
                f"🔸 현재 SOXL <b>{held_q}주</b> 보유 중이므로 기존 사이클이 전량 익절(0주)되는 즉시 스나이퍼/바벨을 멈추고 <b>[실전] 암살자</b> 모드로 자동 전환합니다."
            )
        elif st_code == "DEMOTE_SCHEDULED_AFTER_LIVE_EXIT":
            note_txt = (
                "⏳ <b>[실전 암살자 당일 청산 후 [모의] 복귀 예약]</b>\n"
                "🔸 현재 실전 암살자 포지션 가동 중이므로 금일 청산 퇴근 직후 [모의] 모드로 안전 복귀합니다."
            )
        else:
            note_txt = (
                "🧪 <b>[[모의] 암살자 모드로 복귀 완료]</b>\n"
                "🔸 스나이퍼/바벨 모드가 정상 가동되며 암살자는 모의 관제 모드로 작동합니다."
            )

        if edit_msg_id is not None and edit_msg_id > 0:
            await self._render_and_send_settlement(
                chat_id=chat_id, edit_msg_id=edit_msg_id
            )
        await self.send_message(
            chat_id=chat_id,
            text=note_txt,
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

        try:
            if _is_barbell_portion_mode(
                updated_st
            ) and not is_live_assassin_standalone_active(self.context):
                await initialize_or_sync_barbell_on_mode_enter(
                    self.context, new_seed_usd=round(val, 4)
                )
                updated_st = self.context.ledger.get_state(TARGET_SYMBOL)
            else:
                b_led = ensure_barbell_ledger(self.context)
                keep_init = (
                    False
                    if is_live_assassin_standalone_active(self.context)
                    else bool(b_led.get_state().get("is_initialized", False))
                )
                await b_led.update_state(
                    initial_seed_usd=round(val, 4),
                    is_initialized=keep_init,
                )
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
                f"▫️ 기준 시드: <b>${val:,.2f}</b> (스나이퍼 · 바벨 · 암살자 동시 적용)\n"
                f"▫️ 가용 현금: <b>${safe_float(summary.get('free_cash_usd'), 0.0):,.2f}</b>\n"
                f"▫️ 본그리드(8%): <b>${safe_float(summary.get('next_portion_budget'), 0.0):,.0f}</b> ({quota_badge_str})\n"
                f"▫️ 서브그리드(4%): <b>${safe_float(summary.get('sub_next_portion_budget'), 0.0):,.0f}</b> ({sub_quota_badge})"
            ),
            reply_markup=_build_settlement_inline_keyboard(
                bool(updated_st.get("is_active", True)),
                portion_mode=updated_st.get("portion_mode"),
                assassin_exec_mode=self._current_assassin_exec_mode(),
            ),
        )
        return True

    async def _reset_realized_profit_only(self, chat_id: str) -> None:
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
            "vaulted_profit_locked_usd": 0.0,
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
        try:
            await ensure_barbell_ledger(self.context).reset_vault_profit_only()
        except Exception:
            pass

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
                "🧹 <b>[스나이퍼 &amp; 바벨 수익금고 0점 초기화 완료]</b>\n"
                "▫️ 이번사이클 / 누적 실현익 / 별도금고: <b>$0.00</b>\n"
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
                "🧹 <b>[암살자 누적 전적 초기화 완료]</b>\n"
                f"▫️ 기준 시드: <b>${init_seed:,.2f}</b>\n"
                "▫️ 누적 출격일 / 모의·실전 실현익이 0점으로 초기화되었습니다."
            ),
            reply_markup=_build_main_reply_keyboard(),
        )

    async def _execute_manual_update_command(self, chat_id: str) -> None:
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
    # 메시지 및 콜백 디스패처
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

        if first_token == "/barbell" or text == "⚖️ 바벨 관제":
            await self._render_and_send_barbell_dashboard(chat_id=chat_id)
            return

        if first_token == "/assassin" or text in (
            "🗡️ 모의 암살자",
            "🗡️ 암살자 레이더",
        ):
            await self._render_and_send_assassin_dashboard(chat_id=chat_id)
            return

        if first_token in ("/assassin_mode", "/assassin_live"):
            await self._toggle_assassin_live_command(chat_id=chat_id)
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
        elif data == "cmd_barbell":
            await self._render_and_send_barbell_dashboard(
                chat_id=chat_id, edit_msg_id=None
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
            if now_active and not is_live_assassin_standalone_active(
                self.context
            ):
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
        elif data == "toggle_assassin_live":
            await self._toggle_assassin_live_command(
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
    tg_obj = getattr(context, "tg", None)
    if tg_obj is not None and hasattr(tg_obj, "run_polling_loop"):
        await tg_obj.run_polling_loop()
        return
    ctrl = TelegramCommandController(context)
    await ctrl.run_polling_loop()


# 하위 호환 별칭
TelegramBotController = TelegramCommandController
TelegramUiController = TelegramCommandController
SniperTelegramController = TelegramCommandController
