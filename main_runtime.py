# -*- coding: utf-8 -*-
"""
# MODIFIED: main_runtime.py (Part 1/2 — 바벨 모드[barbell_plugin · SGOV 잔고 정규화 및 /barbell 관제] &
# [모의 ⇄ 0주예약 ⇄ 실전] 암살자 승격 컨트롤러 결속 · get_candles_1m 최대 400분봉[2페이지] 상한 락온 유지 · Case 86 ~ 93)
인피니트 스노우볼 (Infinite Snowball) v3.0 — 메인 런타임 서포트 브릿지 (Part 1 / 2)
- 역할:
  1) 적응형 비동기 플러그인 호출기(_call_plugin_adaptive) 및 동적 심볼 리졸버(_resolve_module_attr) (Case 13)
  2) TossApiClient 런타임 메서드 호환성 폴리필 어댑터(_install_toss_api_compatibility_patches ·
     SOXL + SGOV 잔고 정규화 · get_candles_1m 최대 400분봉[2페이지] 상한 래핑 · 수수료 폴백 보존 · Case 86, Case 93)
  3) 폴더별 3중 원장 인스턴스 팩토리(_instantiate_stratum_ledger) 및 주말 휴장 판별(_check_weekend_nyse_closed_dynamic)
  4) 100% 벡터화 1분봉/일봉 지표 및 QQQ 방향성 안전망 지표 무손실 직결(_compute_candle_metrics_dynamic, _compute_qqq_metrics_dynamic)
"""

from __future__ import annotations

import asyncio
import html
import inspect
import json
import logging
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

try:
    import httpx  # type: ignore

    _HTTPX_AVAILABLE = True
except Exception:
    httpx = None  # type: ignore
    _HTTPX_AVAILABLE = False

import assassin_plugin
import barbell_plugin
import defense_plugin
import plugin_updater
import quant_engine
import quant_indicators_plugin
import tg_ui_plugin
import toss_api
from assassin_plugin import (
    ASSASSIN_MODE_SIMULATED,
    build_assassin_detail_dashboard_html,
    ensure_assassin_ledger,
    format_assassin_slim_radar_block,
    is_live_assassin_standalone_active,
    run_assassin_plugin_tdd,
    toggle_assassin_live_promotion,
)
from barbell_plugin import (
    BARBELL_SAFE_SYMBOL,
    PORTION_MODE_BARBELL,
    build_barbell_detail_dashboard_html,
    ensure_barbell_ledger,
    format_barbell_slim_radar_block,
    initialize_or_sync_barbell_on_mode_enter,
    is_barbell_mode,
    run_barbell_plugin_tdd,
)
from defense_plugin import reconcile_stratum_with_broker_holdings_plugin
from plugin_updater import (
    execute_git_pull_and_preflight,
    perform_self_restart_execv,
    read_persisted_tg_offset_sync,
    trigger_graceful_restart,
    verify_all_modules_compile,
    write_persisted_tg_offset_sync,
)
from quant_engine import (
    get_runtime_round_trip_fee_rate_pct,
    get_runtime_us_commission_rate,
    next_cycled_portion_mode,
    set_runtime_round_trip_fee_rate_pct,
    summarize_stratum_portfolio,
)
from quant_indicators_plugin import (
    compute_qqq_macro_metrics_1m,
    compute_soxl_quant_metrics_1m,
    refresh_metrics_with_live_tick,
)
from sniper_plugin import mark_reserve_deposit_check_shield
from tg_ui_plugin import (
    PORTION_MODE_COMPOUND,
    PORTION_MODE_SIMPLE,
    SEED_INPUT_PROMPT_TIMEOUT_SEC,
    _build_main_reply_keyboard,
    _build_settlement_inline_keyboard,
    _format_case67_quota_badge,
    _format_sub_quota_badge,
    _is_barbell_portion_mode,
    _is_simple_portion_mode,
    build_avwap_radar_message,
    build_settlement_control_message,
    build_start_schedule_message,
    build_sync_instruction_message,
    sanitize_telegram_html,
    strip_telegram_html,
)
from toss_api import (
    EST_TZ,
    TARGET_SYMBOL,
    TossApiClient,
    get_bot_base_dir,
    safe_float,
    safe_int,
)

# [Case 75]: 매 1.5초 시세 조회 및 폴링 시 systemd-journald 디스크 쓰기를 유발하는 httpx / httpcore INFO 로그를 WARNING 으로 고정
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger("toss_sniper.main_runtime")

KRW_PER_USD_DEFAULT: float = 1380.0

_TG_TOKEN_STRICT_RE = re.compile(r"\b(\d{7,15}:[A-Za-z0-9_-]{25,60})\b")


def _escape_html(val: Any) -> str:
    return html.escape(str(val if val is not None else ""), quote=False)


# ---------------------------------------------------------------------------
# [핵심 1] Case 13 & Case 62 : 적응형 비동기 플러그인 호출기 및 동적 심볼 리졸버
# ---------------------------------------------------------------------------
async def _call_plugin_adaptive(
    func: Callable[..., Any],
    **kwargs: Any,
) -> Any:
    sig = inspect.signature(func)
    accepts_var_kw = any(
        p.kind == inspect.Parameter.VAR_KEYWORD
        for p in sig.parameters.values()
    )
    if accepts_var_kw:
        filtered_kwargs = kwargs
    else:
        filtered_kwargs = {
            k: v for k, v in kwargs.items() if k in sig.parameters
        }

    res = func(**filtered_kwargs)
    if inspect.isawaitable(res):
        return await res
    return res


def _resolve_module_attr(
    modules: Iterable[Any],
    candidate_names: Tuple[str, ...],
    predicate: Optional[Callable[[Any], bool]] = None,
) -> Any:
    for mod in modules:
        for name in candidate_names:
            obj = getattr(mod, name, None)
            if obj is not None:
                return obj
    if predicate is not None:
        for mod in modules:
            for attr_name in dir(mod):
                if attr_name.startswith("_"):
                    continue
                obj = getattr(mod, attr_name, None)
                try:
                    if predicate(obj):
                        return obj
                except Exception:
                    pass
    return None


# ---------------------------------------------------------------------------
# [핵심 2] TossApiClient 런타임 메서드 호환성 폴리필 어댑터 (SOXL + SGOV 잔고 정규화 및 400봉 락온)
# ---------------------------------------------------------------------------
def _empty_holding_entry(symbol: str = TARGET_SYMBOL) -> Dict[str, Any]:
    sym = str(symbol or TARGET_SYMBOL).upper().strip()
    return {
        "symbol": sym,
        "qty": 0,
        "quantity": 0,
        "avg_price": 0.0,
        "averagePurchasePrice": 0.0,
        "last_price": 0.0,
        "lastPrice": 0.0,
        "purchase_amount": 0.0,
        "eval_amount": 0.0,
        "profit_loss": 0.0,
        "profit_rate": 0.0,
    }


def _empty_soxl_holding_entry() -> Dict[str, Any]:
    return _empty_holding_entry(TARGET_SYMBOL)


def _normalize_single_holding_item(
    item: Dict[str, Any], symbol: str = TARGET_SYMBOL
) -> Dict[str, Any]:
    sym = str(item.get("symbol") or symbol or TARGET_SYMBOL).upper().strip()
    qty = max(
        0,
        safe_int(
            item.get("qty")
            if item.get("qty") is not None
            else item.get("quantity"),
            0,
        ),
    )
    avg_p = round(
        max(
            0.0,
            safe_float(
                item.get("avg_price")
                if item.get("avg_price") is not None
                else item.get("averagePurchasePrice"),
                0.0,
            ),
        ),
        4,
    )
    last_p = round(
        max(
            0.0,
            safe_float(
                item.get("last_price")
                if item.get("last_price") is not None
                else item.get("lastPrice"),
                avg_p,
            ),
        ),
        4,
    )

    mv_obj = (
        item.get("marketValue")
        if isinstance(item.get("marketValue"), dict)
        else {}
    )
    raw_pl_obj = item.get("profitLoss")
    pl_obj = raw_pl_obj if isinstance(raw_pl_obj, dict) else {}

    pur_amt = safe_float(
        item.get("purchase_amount")
        if item.get("purchase_amount") is not None
        else mv_obj.get("purchaseAmount"),
        round(float(qty) * avg_p, 4),
    )
    eval_amt = safe_float(
        item.get("eval_amount")
        if item.get("eval_amount") is not None
        else mv_obj.get("amount"),
        round(float(qty) * last_p, 4),
    )
    pnl_amt = safe_float(
        item.get("profit_loss")
        if item.get("profit_loss") is not None
        else (
            pl_obj.get("amountAfterCost")
            if pl_obj.get("amountAfterCost") is not None
            else pl_obj.get("amount")
        ),
        round(eval_amt - pur_amt, 4),
    )
    raw_rate = safe_float(
        item.get("profit_rate")
        if item.get("profit_rate") is not None
        else (
            pl_obj.get("rateAfterCost")
            if pl_obj.get("rateAfterCost") is not None
            else pl_obj.get("rate")
        ),
        0.0,
    )
    if item.get("profit_rate") is None and pl_obj:
        profit_rate = round(raw_rate * 100.0, 2)
    elif (
        pur_amt > 0.0
        and abs(raw_rate) < 2.0
        and abs(pnl_amt / pur_amt) > 0.005
    ):
        profit_rate = round((pnl_amt / pur_amt) * 100.0, 2)
    else:
        profit_rate = round(raw_rate, 2)

    return {
        "symbol": sym,
        "qty": qty,
        "quantity": qty,
        "avg_price": avg_p,
        "averagePurchasePrice": avg_p,
        "last_price": last_p,
        "lastPrice": last_p,
        "purchase_amount": round(pur_amt, 4),
        "eval_amount": round(eval_amt, 4),
        "profit_loss": round(pnl_amt, 4),
        "profit_rate": profit_rate,
    }


def _normalize_holdings_payload(
    raw_res: Any,
) -> Tuple[Dict[str, Dict[str, Any]], bool]:
    if raw_res is None:
        return {}, False

    if isinstance(raw_res, tuple) and len(raw_res) == 2:
        first, second = raw_res
        if isinstance(first, bool) and isinstance(second, dict):
            norm_map, _ = _normalize_holdings_payload(second)
            return norm_map, first
        if isinstance(first, dict):
            norm_map, _ = _normalize_holdings_payload(first)
            return norm_map, bool(second)

    out_map: Dict[str, Dict[str, Any]] = {
        TARGET_SYMBOL: _empty_holding_entry(TARGET_SYMBOL),
        BARBELL_SAFE_SYMBOL: _empty_holding_entry(BARBELL_SAFE_SYMBOL),
    }

    if isinstance(raw_res, dict):
        matched_direct = False
        for tracked_sym in (TARGET_SYMBOL, BARBELL_SAFE_SYMBOL):
            if tracked_sym in raw_res and isinstance(
                raw_res[tracked_sym], dict
            ):
                out_map[tracked_sym] = _normalize_single_holding_item(
                    raw_res[tracked_sym], tracked_sym
                )
                matched_direct = True
        if matched_direct:
            return out_map, True

        single_sym = str(raw_res.get("symbol") or "").upper().strip()
        if single_sym in (TARGET_SYMBOL, BARBELL_SAFE_SYMBOL) and (
            "quantity" in raw_res or "qty" in raw_res
        ):
            out_map[single_sym] = _normalize_single_holding_item(
                raw_res, single_sym
            )
            return out_map, True

        res_obj = (
            raw_res.get("result")
            if isinstance(raw_res.get("result"), dict)
            else raw_res
        )
        items = res_obj.get("items") if isinstance(res_obj, dict) else None
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict):
                    sym = str(it.get("symbol") or "").upper().strip()
                    if sym:
                        out_map[sym] = _normalize_single_holding_item(it, sym)
            return out_map, True

        if len(raw_res) == 0:
            return out_map, True

    if isinstance(raw_res, list):
        for it in raw_res:
            if isinstance(it, dict):
                sym = str(it.get("symbol") or "").upper().strip()
                if sym:
                    out_map[sym] = _normalize_single_holding_item(it, sym)
        return out_map, True

    return out_map, True


async def _invoke_raw_toss_api(
    api: Any,
    method: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    require_account: bool = False,
) -> Any:
    for req_name in (
        "_request",
        "request",
        "_api_request",
        "_call_api",
        "_fetch_json",
    ):
        req_fn = getattr(api, req_name, None)
        if callable(req_fn):
            sig = inspect.signature(req_fn)
            kw: Dict[str, Any] = {}
            accepts_var_kw = any(
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in sig.parameters.values()
            )
            for p_name in sig.parameters:
                if p_name in ("method", "http_method"):
                    kw[p_name] = method
                elif p_name in ("path", "endpoint", "url", "uri"):
                    kw[p_name] = path
                elif p_name in ("params", "query", "query_params"):
                    kw[p_name] = params
                elif p_name in ("json_data", "json", "body", "data", "payload"):
                    kw[p_name] = json_data
                elif p_name in (
                    "require_account",
                    "use_account",
                    "account_required",
                    "with_account",
                    "need_account",
                ):
                    kw[p_name] = require_account
                elif p_name in ("rate_group", "group"):
                    kw[p_name] = (
                        "MARKET_DATA_CHART"
                        if "candles" in path
                        else ("ASSET" if "holdings" in path else "MARKET_DATA")
                    )
            if accepts_var_kw:
                if "params" not in kw and params is not None:
                    kw["params"] = params
                if "json_data" not in kw and json_data is not None:
                    kw["json_data"] = json_data
            try:
                res = req_fn(**kw)
                if inspect.isawaitable(res):
                    return await res
                return res
            except TypeError:
                res = req_fn(method, path, params=params)
                if inspect.isawaitable(res):
                    return await res
                return res
    return None


def _extract_candles_list(
    raw_res: Any,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    if isinstance(raw_res, tuple) and len(raw_res) == 2:
        c_part, nb_part = raw_res
        if isinstance(c_part, list):
            return (
                [c for c in c_part if isinstance(c, dict)],
                str(nb_part).strip() if nb_part else None,
            )
    if isinstance(raw_res, list):
        return [c for c in raw_res if isinstance(c, dict)], None
    if isinstance(raw_res, dict):
        res_obj = raw_res.get("result") if "result" in raw_res else raw_res
        if isinstance(res_obj, list):
            return [c for c in res_obj if isinstance(c, dict)], None
        if isinstance(res_obj, dict):
            if res_obj.get("candles") is not None:
                c_list = res_obj.get("candles")
            elif res_obj.get("items") is not None:
                c_list = res_obj.get("items")
            else:
                c_list = res_obj.get("data")
            next_b = res_obj.get("nextBefore")
            if isinstance(c_list, list):
                return (
                    [c for c in c_list if isinstance(c, dict)],
                    str(next_b).strip() if next_b else None,
                )
    return [], None


def _has_today_0407_open_bar_in_candles(
    candles: List[Dict[str, Any]], today_est_str: str
) -> bool:
    if not candles:
        return False
    for c in candles:
        ts_raw = str(
            c.get("timestamp")
            or c.get("dt")
            or c.get("dateTime")
            or c.get("time")
            or ""
        ).strip()
        if not ts_raw:
            continue
        try:
            dt_est = datetime.fromisoformat(
                ts_raw.replace("Z", "+00:00")
            ).astimezone(EST_TZ)
            d_str = dt_est.strftime("%Y-%m-%d")
            hm = dt_est.hour * 100 + dt_est.minute
            if d_str < today_est_str:
                return True
            if d_str == today_est_str and 400 <= hm <= 415:
                return True
        except Exception:
            continue
    return False


def _install_toss_api_compatibility_patches() -> None:
    if not hasattr(TossApiClient, "get_commissions"):

        async def _poly_get_commissions(self: Any) -> List[Dict[str, Any]]:
            try:
                raw = await _invoke_raw_toss_api(
                    self,
                    method="GET",
                    path="/api/v1/commissions",
                    require_account=True,
                )
                if isinstance(raw, dict):
                    items = raw.get("result")
                    if isinstance(items, list):
                        return [c for c in items if isinstance(c, dict)]
            except Exception:
                pass
            return []

        setattr(TossApiClient, "get_commissions", _poly_get_commissions)

    if not hasattr(TossApiClient, "ensure_us_commission_rate"):

        async def _poly_ensure_us_commission_rate(
            self: Any, force_refresh: bool = False
        ) -> Tuple[float, float]:
            fb_one = get_runtime_us_commission_rate()
            fb_rt = get_runtime_round_trip_fee_rate_pct()
            cur_one = safe_float(
                getattr(self, "us_commission_rate", fb_one), fb_one
            )
            cur_rt = safe_float(
                getattr(self, "round_trip_fee_rate_pct", fb_rt), fb_rt
            )
            if not force_refresh and getattr(
                self, "_commission_locked", False
            ):
                return cur_one, cur_rt
            try:
                items = await self.get_commissions()
                for it in items:
                    mkt = str(it.get("marketCountry") or "").upper().strip()
                    if mkt == "US":
                        r_val = safe_float(it.get("commissionRate"), 0.0)
                        if 0.0 < r_val <= 0.01:
                            cur_one = round(r_val, 6)
                            cur_rt = round(cur_one * 200.0, 4)
                            setattr(self, "us_commission_rate", cur_one)
                            setattr(self, "round_trip_fee_rate_pct", cur_rt)
                            setattr(self, "_commission_locked", True)
                            set_runtime_round_trip_fee_rate_pct(
                                cur_rt, us_commission_rate=cur_one
                            )
                            return cur_one, cur_rt
            except Exception:
                pass
            if 0.0 < fb_one <= 0.01 and 0.0 < fb_rt <= 2.0:
                cur_one = fb_one
                cur_rt = fb_rt
                setattr(self, "us_commission_rate", cur_one)
                setattr(self, "round_trip_fee_rate_pct", cur_rt)
            return cur_one, cur_rt

        setattr(
            TossApiClient,
            "ensure_us_commission_rate",
            _poly_ensure_us_commission_rate,
        )

    if not hasattr(TossApiClient, "get_holdings_map_with_status"):

        async def _poly_get_holdings_map_with_status(
            self: Any, symbol: Optional[str] = None
        ) -> Tuple[Dict[str, Dict[str, Any]], bool]:
            for cand_name in (
                "get_holdings_map",
                "get_holdings",
                "fetch_holdings_map",
                "fetch_holdings",
                "get_account_holdings",
                "get_broker_holdings",
                "get_positions",
            ):
                fn = getattr(self, cand_name, None)
                if callable(fn):
                    try:
                        res = await _call_plugin_adaptive(fn, symbol=symbol)
                        return _normalize_holdings_payload(res)
                    except Exception as exc:
                        logger.warning(
                            "TossApiClient.%s 호출 예외: %s", cand_name, exc
                        )
                        return {}, False

            try:
                q_params = {"symbol": symbol} if symbol else None
                raw = await _invoke_raw_toss_api(
                    self,
                    method="GET",
                    path="/api/v1/holdings",
                    params=q_params,
                    require_account=True,
                )
                return _normalize_holdings_payload(raw)
            except Exception as exc:
                logger.warning("GET /api/v1/holdings 폴백 호출 예외: %s", exc)
                return {}, False

        setattr(
            TossApiClient,
            "get_holdings_map_with_status",
            _poly_get_holdings_map_with_status,
        )

    if not getattr(TossApiClient, "_candles_1m_v3_patched", False):
        _orig_get_candles_1m = getattr(TossApiClient, "get_candles_1m", None)

        async def _upgraded_get_candles_1m(
            self: Any,
            symbol: str = TARGET_SYMBOL,
            total_count: Optional[int] = None,
            count: Optional[int] = None,
            before: Optional[str] = None,
            adjusted: bool = True,
            **kwargs: Any,
        ) -> List[Dict[str, Any]]:
            now_est = datetime.now(EST_TZ)
            today_est_str = now_est.strftime("%Y-%m-%d")
            sym_clean = str(symbol or TARGET_SYMBOL).upper().strip()

            explicit_req = max(
                safe_int(total_count, 0),
                safe_int(count, 0),
            )
            req_total = 400 if explicit_req <= 0 else explicit_req
            req_total = max(1, min(400, req_total))
            max_pages = max(1, min(2, int(math.ceil(req_total / 200.0))))

            collected: List[Dict[str, Any]] = []
            seen_ts: Set[str] = set()
            before_cursor: Optional[str] = (
                str(before).strip() if before else None
            )

            for page_i in range(max_pages):
                rem = max(1, min(200, req_total - len(collected)))
                page_cnt = (
                    200
                    if (page_i == 0 and req_total >= 150)
                    else max(100, rem)
                )

                page_candles: List[Dict[str, Any]] = []
                next_b: Optional[str] = None

                if hasattr(self, "get_candles") and callable(self.get_candles):
                    try:
                        c_res = await self.get_candles(
                            symbol=sym_clean,
                            interval="1m",
                            count=page_cnt,
                            before=before_cursor,
                            adjusted=adjusted,
                        )
                        page_candles, next_b = _extract_candles_list(c_res)
                    except Exception:
                        page_candles, next_b = [], None

                if not page_candles:
                    q_params: Dict[str, Any] = {
                        "symbol": sym_clean,
                        "interval": "1m",
                        "count": page_cnt,
                        "adjusted": "true" if adjusted else "false",
                    }
                    if before_cursor:
                        q_params["before"] = before_cursor
                    try:
                        raw = await _invoke_raw_toss_api(
                            self,
                            method="GET",
                            path="/api/v1/candles",
                            params=q_params,
                            require_account=False,
                        )
                        page_candles, next_b = _extract_candles_list(raw)
                    except Exception:
                        page_candles, next_b = [], None

                if (
                    not page_candles
                    and page_i == 0
                    and callable(_orig_get_candles_1m)
                ):
                    try:
                        fallback_res = await _call_plugin_adaptive(
                            _orig_get_candles_1m,
                            self=self,
                            symbol=sym_clean,
                            count=min(200, req_total),
                            total_count=req_total,
                            before=before_cursor,
                            adjusted=adjusted,
                        )
                        page_candles, next_b = _extract_candles_list(
                            fallback_res
                        )
                    except Exception:
                        pass

                if not page_candles:
                    break

                added_in_page = 0
                for c in page_candles:
                    ts_s = str(
                        c.get("timestamp")
                        or c.get("dt")
                        or c.get("dateTime")
                        or c.get("time")
                        or ""
                    ).strip()
                    if ts_s and ts_s not in seen_ts:
                        seen_ts.add(ts_s)
                        collected.append(c)
                        added_in_page += 1

                if added_in_page == 0:
                    break

                if (
                    sym_clean == TARGET_SYMBOL
                    and len(collected) >= min(200, req_total)
                    and _has_today_0407_open_bar_in_candles(
                        collected, today_est_str
                    )
                ):
                    break

                if (
                    not next_b
                    or next_b == before_cursor
                    or len(collected) >= req_total
                ):
                    break
                before_cursor = next_b

            collected.sort(
                key=lambda x: str(
                    x.get("timestamp")
                    or x.get("dt")
                    or x.get("dateTime")
                    or x.get("time")
                    or ""
                )
            )
            if len(collected) > req_total:
                collected = collected[-req_total:]
            return collected

        setattr(TossApiClient, "get_candles_1m", _upgraded_get_candles_1m)
        setattr(TossApiClient, "_candles_1m_v3_patched", True)

    if not getattr(TossApiClient, "_candles_1d_v3_patched", False):
        _orig_get_candles_1d = getattr(TossApiClient, "get_candles_1d", None)

        async def _upgraded_get_candles_1d(
            self: Any,
            symbol: str = TARGET_SYMBOL,
            count: int = 10,
            adjusted: bool = True,
            **kwargs: Any,
        ) -> List[Dict[str, Any]]:
            req_cnt = max(2, min(200, safe_int(count, 10)))
            sym_clean = str(symbol or TARGET_SYMBOL).upper().strip()

            if hasattr(self, "get_candles") and callable(self.get_candles):
                try:
                    c_res = await self.get_candles(
                        symbol=sym_clean,
                        interval="1d",
                        count=req_cnt,
                        adjusted=adjusted,
                    )
                    c_list, _ = _extract_candles_list(c_res)
                    if c_list:
                        c_list.sort(
                            key=lambda x: str(
                                x.get("timestamp")
                                or x.get("date")
                                or x.get("dt")
                                or ""
                            )
                        )
                        return c_list
                except Exception:
                    pass

            try:
                raw = await _invoke_raw_toss_api(
                    self,
                    method="GET",
                    path="/api/v1/candles",
                    params={
                        "symbol": sym_clean,
                        "interval": "1d",
                        "count": req_cnt,
                        "adjusted": "true" if adjusted else "false",
                    },
                    require_account=False,
                )
                c_list, _ = _extract_candles_list(raw)
                if c_list:
                    c_list.sort(
                        key=lambda x: str(
                            x.get("timestamp")
                            or x.get("date")
                            or x.get("dt")
                            or ""
                        )
                    )
                    return c_list
            except Exception:
                pass

            if callable(_orig_get_candles_1d):
                try:
                    res = await _call_plugin_adaptive(
                        _orig_get_candles_1d,
                        self=self,
                        symbol=sym_clean,
                        count=req_cnt,
                    )
                    c_list, _ = _extract_candles_list(res)
                    if c_list:
                        c_list.sort(
                            key=lambda x: str(
                                x.get("timestamp")
                                or x.get("date")
                                or x.get("dt")
                                or ""
                            )
                        )
                        return c_list
                except Exception:
                    pass
            return []

        setattr(TossApiClient, "get_candles_1d", _upgraded_get_candles_1d)
        setattr(TossApiClient, "_candles_1d_v3_patched", True)

    if not hasattr(TossApiClient, "get_open_orders"):

        async def _poly_get_open_orders(
            self: Any, symbol: str = TARGET_SYMBOL
        ) -> List[Dict[str, Any]]:
            raw = await _invoke_raw_toss_api(
                self,
                method="GET",
                path="/api/v1/orders",
                params={"status": "OPEN", "symbol": symbol},
                require_account=True,
            )
            if isinstance(raw, dict):
                res_obj = (
                    raw.get("result")
                    if isinstance(raw.get("result"), dict)
                    else raw
                )
                orders = (
                    res_obj.get("orders")
                    if isinstance(res_obj, dict)
                    else None
                )
                if isinstance(orders, list):
                    return [o for o in orders if isinstance(o, dict)]
            return []

        setattr(TossApiClient, "get_open_orders", _poly_get_open_orders)

    if not hasattr(TossApiClient, "cancel_all_open_orders"):

        async def _poly_cancel_all_open_orders(
            self: Any, symbol: str = TARGET_SYMBOL
        ) -> int:
            open_list = await self.get_open_orders(symbol=symbol)
            cnt = 0
            for o in open_list:
                oid = str(o.get("orderId") or "").strip()
                if oid and hasattr(self, "cancel_order"):
                    try:
                        await self.cancel_order(oid)
                        cnt += 1
                    except Exception:
                        pass
            return cnt

        setattr(
            TossApiClient,
            "cancel_all_open_orders",
            _poly_cancel_all_open_orders,
        )

    if not hasattr(TossApiClient, "find_latest_open_order_id"):

        async def _poly_find_latest_open_order_id(
            self: Any,
            symbol: str = TARGET_SYMBOL,
            side: Optional[str] = None,
        ) -> str:
            open_list = await self.get_open_orders(symbol=symbol)
            target_s = str(side or "").upper().strip()
            for o in open_list:
                o_s = str(o.get("side") or "").upper().strip()
                if not target_s or o_s == target_s:
                    oid = str(o.get("orderId") or "").strip()
                    if oid:
                        return oid
            return ""

        setattr(
            TossApiClient,
            "find_latest_open_order_id",
            _poly_find_latest_open_order_id,
        )

    if not hasattr(TossApiClient, "get_buying_power_usd"):

        async def _poly_get_buying_power_usd(
            self: Any, safety_buffer_pct: float = 0.2
        ) -> float:
            raw = await _invoke_raw_toss_api(
                self,
                method="GET",
                path="/api/v1/buying-power",
                params={"currency": "USD"},
                require_account=True,
            )
            if isinstance(raw, dict):
                res_obj = (
                    raw.get("result")
                    if isinstance(raw.get("result"), dict)
                    else raw
                )
                bp = safe_float(
                    res_obj.get("cashBuyingPower")
                    if isinstance(res_obj, dict)
                    else 0.0,
                    0.0,
                )
                return round(
                    max(
                        0.0,
                        bp
                        * (
                            1.0
                            - max(0.0, safe_float(safety_buffer_pct, 0.2))
                            / 100.0
                        ),
                    ),
                    4,
                )
            return 0.0

        setattr(
            TossApiClient, "get_buying_power_usd", _poly_get_buying_power_usd
        )

    if not hasattr(TossApiClient, "get_usd_krw_rate"):

        async def _poly_get_usd_krw_rate(self: Any) -> float:
            try:
                raw = await _invoke_raw_toss_api(
                    self,
                    method="GET",
                    path="/api/v1/exchange-rate",
                    params={"baseCurrency": "USD", "quoteCurrency": "KRW"},
                    require_account=False,
                )
                if isinstance(raw, dict):
                    res_obj = (
                        raw.get("result")
                        if isinstance(raw.get("result"), dict)
                        else raw
                    )
                    r = safe_float(
                        res_obj.get("rate")
                        if isinstance(res_obj, dict)
                        else 0.0,
                        KRW_PER_USD_DEFAULT,
                    )
                    return r if r > 100.0 else KRW_PER_USD_DEFAULT
            except Exception:
                pass
            return KRW_PER_USD_DEFAULT

        setattr(TossApiClient, "get_usd_krw_rate", _poly_get_usd_krw_rate)

    if not hasattr(TossApiClient, "close"):

        async def _poly_close(self: Any) -> None:
            for sess_attr in ("_session", "session", "_client", "client"):
                s_obj = getattr(self, sess_attr, None)
                if s_obj is not None and hasattr(s_obj, "close"):
                    try:
                        c_res = s_obj.close()
                        if inspect.isawaitable(c_res):
                            await c_res
                    except Exception:
                        pass
            return None

        setattr(TossApiClient, "close", _poly_close)


_install_toss_api_compatibility_patches()


def _instantiate_stratum_ledger(
    filepath: str, base_dir: Optional[str] = None
) -> Any:
    ledger_cls = _resolve_module_attr(
        modules=(toss_api, quant_engine),
        candidate_names=(
            "SoxlStratumLedger",
            "StratumLedger",
            "AssassinLedger",
            "TossStratumLedger",
            "SoxlLedger",
        ),
        predicate=lambda c: (
            inspect.isclass(c)
            and hasattr(c, "get_state")
            and hasattr(c, "update_state")
        ),
    )
    if ledger_cls is None:
        raise RuntimeError(
            "원장 클래스(get_state/update_state 보유)를 찾을 수 없습니다."
        )

    try:
        sig = inspect.signature(ledger_cls.__init__)
        kw: Dict[str, Any] = {}
        if "filepath" in sig.parameters:
            kw["filepath"] = filepath
        if "base_dir" in sig.parameters and base_dir:
            kw["base_dir"] = base_dir
        if kw:
            return ledger_cls(**kw)
        if len(sig.parameters) >= 2:
            return ledger_cls(filepath)
        return ledger_cls()
    except Exception:
        return ledger_cls(filepath)


def _check_weekend_nyse_closed_dynamic(now_est: datetime) -> bool:
    fn = _resolve_module_attr(
        modules=(quant_indicators_plugin, toss_api),
        candidate_names=(
            "is_weekend_nyse_closed",
            "is_weekend_closed",
            "is_nyse_weekend_closed",
        ),
    )
    if callable(fn):
        try:
            return bool(fn(now_est))
        except Exception:
            pass

    dt = now_est.astimezone(EST_TZ)
    wd = dt.weekday()
    hm = dt.hour * 100 + dt.minute
    if wd == 4 and hm >= 2000:
        return True
    if wd == 5:
        return True
    if wd == 6 and hm < 1800:
        return True
    return False


# ---------------------------------------------------------------------------
# [핵심 3] 자체 벡터화 1분봉/일봉 지표 및 Wilder's RSI(14) · QQQ 안전망 지표 산출기
# ---------------------------------------------------------------------------
async def _compute_candle_metrics_dynamic(
    context: Any,
    candles_1m: List[Dict[str, Any]],
    live_price: float,
    now_est: datetime,
    candles_1d: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    eff_candles_1d = candles_1d if isinstance(candles_1d, list) else []
    if not eff_candles_1d and context is not None and hasattr(context, "api"):
        try:
            eff_candles_1d = await context.api.get_candles_1d(
                symbol=TARGET_SYMBOL, count=10
            )
        except Exception:
            eff_candles_1d = []

    try:
        res_direct = await asyncio.to_thread(
            compute_soxl_quant_metrics_1m,
            candles_1m,
            live_price,
            now_est,
            eff_candles_1d,
        )
        if isinstance(res_direct, dict):
            return refresh_metrics_with_live_tick(
                res_direct, live_price, now_est=now_est, symbol=TARGET_SYMBOL
            )
    except Exception as exc:
        logger.debug("compute_soxl_quant_metrics_1m 직접 호출 폴백: %s", exc)

    return refresh_metrics_with_live_tick(
        {}, live_price, now_est=now_est, symbol=TARGET_SYMBOL
    )


async def _compute_qqq_metrics_dynamic(
    context: Any,
    candles_1m_qqq: List[Dict[str, Any]],
    live_price_qqq: float,
    now_est: datetime,
) -> Dict[str, Any]:
    try:
        res_qqq = await asyncio.to_thread(
            compute_qqq_macro_metrics_1m,
            candles_1m_qqq,
            live_price_qqq,
            now_est,
        )
        if isinstance(res_qqq, dict):
            return refresh_metrics_with_live_tick(
                res_qqq, live_price_qqq, now_est=now_est, symbol="QQQ"
            )
    except Exception as exc:
        logger.debug("compute_qqq_macro_metrics_1m 호출 폴백: %s", exc)

    return refresh_metrics_with_live_tick(
        {}, live_price_qqq, now_est=now_est, symbol="QQQ"
    )
# -*- coding: utf-8 -*-
"""
# MODIFIED: main_runtime.py (Part 2/2 — 폴더별 텔레그램 자격증명 탐색기 ·
# _AdaptiveTelegramBridge 내 3단 모드 순환[/mode] · 바벨 관제[/barbell] · 실전 암살자 승격[/assassin_mode] 및
# 실전 암살자 단독 가동 시 스나이퍼 잔고 화해 간섭 차단 연동)
"""


# ---------------------------------------------------------------------------
# [핵심 4] 폴더 위치(base_dir) 전용 텔레그램 자격증명 탐색기 (Case 68)
# ---------------------------------------------------------------------------
def _discover_telegram_credentials(
    base_dir: Optional[str] = None,
) -> Tuple[str, str]:
    """
    🚨 Case 68:
    고정 경로("/home/pipiosToss") 참조를 100% 폐기하고, 오직 현재 봇이 실행 중인 폴더(target_dir)의
    .env 파일과 프로세스 환경변수에서만 TELEGRAM_BOT_TOKEN 과 TELEGRAM_CHAT_ID 를 탐색한다.
    """
    target_dir = get_bot_base_dir(base_dir)
    bot_token = ""
    chat_id = ""

    env_candidates = (
        os.path.join(target_dir, ".env"),
        os.path.join(target_dir, ".env.local"),
    )
    for env_fp in env_candidates:
        if not os.path.isfile(env_fp):
            continue
        try:
            with open(env_fp, "r", encoding="utf-8", errors="ignore") as rf:
                for raw_line in rf:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k_clean = k.strip().upper()
                    v_clean = v.strip().strip("'").strip('"').strip()
                    if k_clean in (
                        "TELEGRAM_BOT_TOKEN",
                        "TG_BOT_TOKEN",
                        "BOT_TOKEN",
                        "TELEGRAM_TOKEN",
                        "TG_TOKEN",
                    ):
                        m = _TG_TOKEN_STRICT_RE.search(v_clean)
                        if m and not bot_token:
                            bot_token = m.group(1)
                    elif k_clean in (
                        "TELEGRAM_CHAT_ID",
                        "TG_CHAT_ID",
                        "CHAT_ID",
                    ):
                        if v_clean and not chat_id:
                            chat_id = v_clean
        except Exception:
            pass

    if not bot_token:
        for k in (
            "TELEGRAM_BOT_TOKEN",
            "TG_BOT_TOKEN",
            "BOT_TOKEN",
            "TELEGRAM_TOKEN",
            "TG_TOKEN",
        ):
            val = str(os.environ.get(k) or "").strip()
            if "://" not in val:
                m = _TG_TOKEN_STRICT_RE.search(val)
                if m:
                    bot_token = m.group(1)
                    break

    if not chat_id:
        for k in ("TELEGRAM_CHAT_ID", "TG_CHAT_ID", "CHAT_ID"):
            val = str(os.environ.get(k) or "").strip()
            if val:
                chat_id = val
                break

    if bot_token:
        os.environ["TELEGRAM_BOT_TOKEN"] = bot_token
    if chat_id:
        os.environ["TELEGRAM_CHAT_ID"] = chat_id

    return bot_token, chat_id


# ---------------------------------------------------------------------------
# [핵심 5] 내장형 적응형 텔레그램 브릿지 (_AdaptiveTelegramBridge — 3단 순환 · 바벨 · 실전암살자 연동)
# ---------------------------------------------------------------------------
class _AdaptiveTelegramBridge:
    """
    🚨 Case 02, 15, 16, 62, 64, 65, 66, 67, 68, 70 ~ 93 + ⚖️ 바벨모드 + 🗡️ [모의/실전] 암살자 완벽 호환:
    tg_ui_plugin.TelegramCommandController 와 동일한 인터페이스 및 4버튼 단일 메뉴,
    /avwap · /sync · /settlement · /barbell · /assassin · /assassin_mode · /reset_assassin · /mode 명령어와
    5대 실시간 암살자/바벨 알림을 제공한다.
    """

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
        disc_token, disc_chat = _discover_telegram_credentials(self.base_dir)
        self.bot_token: str = str(bot_token or disc_token or "").strip()
        self.chat_id: str = str(chat_id or disc_chat or "").strip()

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
        self._shared_ctrl: Optional[tg_ui_plugin.TelegramCommandController] = (
            None
        )

    def _get_shared_ctrl(self) -> tg_ui_plugin.TelegramCommandController:
        if self._shared_ctrl is None:
            self._shared_ctrl = tg_ui_plugin.TelegramCommandController(
                self.context,
                bot_token=self.bot_token,
                chat_id=self.chat_id,
            )
            self._shared_ctrl._awaiting_seed_input_chats = (
                self._awaiting_seed_input_chats
            )
        return self._shared_ctrl

    async def close(self) -> None:
        if self._shared_ctrl is not None:
            try:
                await self._shared_ctrl._close_tg_http_client()
            except Exception:
                pass
        await self._close_tg_http_client()

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
            "♻️ [Case 81 브릿지 텔레그램 HTTP 세션 재생성] 사유=%s", reason
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
            except Exception:
                pass

        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    self._post_tg_sync, method, payload, timeout_sec
                ),
                timeout=timeout_sec + 3.0,
            )
        except Exception as exc:
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
        except Exception:
            pass

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
        safe_title = _escape_html(title)
        safe_body = _escape_html(body)
        msg = (
            f"<b>{safe_title}</b>\n🔸 {safe_body}"
            if safe_body
            else f"<b>{safe_title}</b>"
        )
        return await self.send_message(text=msg, reply_markup=reply_markup)

    async def send_startup_alive_banner(self) -> bool:
        return await self.send_message(
            text="<b>✅ 서버가 정상 작동 중입니다.</b>",
            reply_markup=_build_main_reply_keyboard(),
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
        qqq_p = safe_float(
            self.context.latest_prices.get("QQQ"), 0.0
        )
        try:
            p_map = await self.context.api.get_current_prices_batch(
                (TARGET_SYMBOL, "QQQ")
            )
            fetched_p = safe_float(p_map.get(TARGET_SYMBOL), 0.0)
            if fetched_p > 0.0:
                live_p = fetched_p
                self.context.latest_prices[TARGET_SYMBOL] = live_p
                self.context.last_soxl_live_price = live_p
                self.context.last_soxl_live_price_mono = time.monotonic()
            fetched_q = safe_float(p_map.get("QQQ"), 0.0)
            if fetched_q > 0.0:
                qqq_p = fetched_q
                self.context.latest_prices["QQQ"] = qqq_p
                self.context.last_qqq_live_price = qqq_p
        except Exception:
            pass

        base_met = self.context.candle_metrics_cache.get(TARGET_SYMBOL, {})
        b_prev_c = safe_float(
            base_met.get("prev_reg_close")
            if isinstance(base_met, dict)
            else 0.0,
            0.0,
        )
        b_pre_o = safe_float(
            base_met.get("pre_open_price")
            if isinstance(base_met, dict)
            else 0.0,
            0.0,
        )
        b_pre_v = safe_float(
            base_met.get("premarket_vwap")
            if isinstance(base_met, dict)
            else 0.0,
            0.0,
        )
        is_collapsed_pos = bool(
            b_prev_c > 0.0
            and b_pre_o > 0.0
            and b_pre_v > 0.0
            and abs(b_prev_c - b_pre_o) < 1e-6
            and abs(b_pre_v - b_prev_c) < 1e-6
        )

        need_soxl_warm = bool(
            not isinstance(base_met, dict)
            or not bool(base_met.get("anchors_ready", False))
            or safe_float(base_met.get("prev_bar_close"), 0.0) <= 0.0
            or safe_float(base_met.get("candle_count"), 0) < 15
            or is_collapsed_pos
        )
        if need_soxl_warm:
            try:
                c_1m = await self.context.api.get_candles_1m(
                    symbol=TARGET_SYMBOL, count=200, total_count=400
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
            except Exception as exc:
                logger.debug("SOXL 온디맨드 400봉 1m+1d 워밍업 폴백: %s", exc)

        qqq_met = self.context.candle_metrics_cache.get("QQQ", {})
        if (
            not isinstance(qqq_met, dict)
            or safe_float(qqq_met.get("prev_bar_close"), 0.0) <= 0.0
        ):
            try:
                q_1m = await self.context.api.get_candles_1m(
                    symbol="QQQ", count=60, total_count=60
                )
                if q_1m:
                    qqq_met = await asyncio.to_thread(
                        compute_qqq_macro_metrics_1m,
                        q_1m,
                        qqq_p,
                        now_est,
                    )
                    self.context.candle_metrics_cache["QQQ"] = qqq_met
            except Exception:
                pass
        elif qqq_p > 0.0:
            self.context.candle_metrics_cache["QQQ"] = (
                refresh_metrics_with_live_tick(
                    qqq_met, qqq_p, now_est=now_est, symbol="QQQ"
                )
            )

        met = refresh_metrics_with_live_tick(
            base_met, live_p, now_est=now_est, symbol=TARGET_SYMBOL
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
        next_m = next_cycled_portion_mode(st_cur.get("portion_mode"))
        updated_st = await self.context.ledger.update_state(
            TARGET_SYMBOL, portion_mode=next_m
        )
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
        ctrl = self._get_shared_ctrl()
        await ctrl._toggle_assassin_live_command(
            chat_id=chat_id, edit_msg_id=edit_msg_id
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
                        f"<code>/seed {_escape_html(clean_num_check)}</code> 명령어로 입력해 주세요."
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
            ctrl = self._get_shared_ctrl()
            await ctrl._reset_realized_profit_only(chat_id=chat_id)
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
            ctrl = self._get_shared_ctrl()
            ctrl._last_update_id = max(
                ctrl._last_update_id, self._last_update_id
            )
            await self._close_tg_http_client()
            await ctrl._execute_manual_update_command(chat_id=chat_id)
            return

    async def _handle_callback_query(self, cb: Dict[str, Any]) -> None:
        ctrl = self._get_shared_ctrl()
        ctrl._last_update_id = max(ctrl._last_update_id, self._last_update_id)
        await ctrl._handle_callback_query(cb)

    async def run_polling_loop(self) -> None:
        ctrl = self._get_shared_ctrl()
        await ctrl.run_polling_loop()


async def _run_auto_update_loop_dynamic(context: Any) -> None:
    fn = _resolve_module_attr(
        modules=(plugin_updater,),
        candidate_names=(
            "run_auto_update_loop",
            "auto_update_loop",
            "start_auto_update_loop",
            "background_auto_update_loop",
        ),
    )
    if callable(fn):
        await _call_plugin_adaptive(
            fn, context=context, interval_sec=3600.0
        )
