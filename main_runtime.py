# -*- coding: utf-8 -*-
"""
# MODIFIED: main_runtime.py
인피니트 스노우볼 (Infinite Snowball) v3.0 — 메인 런타임 서포트 브릿지 (메인 코드 2분할 리팩토링 Part 1 / 2 · Step 08 / 09)
- 역할:
  1) 적응형 비동기 플러그인 호출기(_call_plugin_adaptive) 및 동적 심볼 리졸버(_resolve_module_attr) (Case 13)
  2) TossApiClient 런타임 메서드 호환성 폴리필 어댑터(_install_toss_api_compatibility_patches · 보조 폴리필 5종 및 close 전수 포함)
  3) 폴더별 3중 원장 인스턴스 팩토리(_instantiate_stratum_ledger · Case 68) 및 주말 휴장 판별(_check_weekend_nyse_closed_dynamic · Case 01, 79, 83)
  4) 100% 벡터화 1분봉/일봉 지표 및 실시간 틱 Wilder's RSI(14) 무손실 직결(_compute_candle_metrics_dynamic · Case 80 RSI 50.0 고정 버그 영구 소각)
  5) 폴더 위치(base_dir) 전용 텔레그램 토큰·채팅방 ID 자동 탐색기(_discover_telegram_credentials · Case 68)
  6) 내장형 사용자 중심 초슬림 텔레그램 불사조 롱폴링/관제탑 브릿지(_AdaptiveTelegramBridge · tg_ui_plugin 단일 렌더러 직결 ·
     12대 코어 모듈 프리플라이트 안내 동기화 · /avwap 조회 시 1분봉 미확보 상태면 즉시 온디맨드 프리워밍 수행 ·
     전술 제어반 황금시간[07:00~07:50 EST & RSI <= 19.0] 전액매수 모드 선택기[기본값 NONE(OFF) ↔ POCKET_ALLIN ↔ GRID_L1_ALLIN] 완벽 지원 ·
     Case 75 httpx/httpcore INFO 로그 묵음화 & Case 81 전용 httpx.AsyncClient 자동 재생성 불사조 폴링 · 오프셋 파일 선행 영속화 · os.execv 인플레이스 자가 교체 · Case 84 실시간 EST 연동 탑재)
- 제1헌법 ~ 제6헌법 및 Case 01 ~ 84 전수 락온
"""

from __future__ import annotations

import asyncio
import html
import inspect
import json
import logging
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

import defense_plugin
import plugin_updater
import quant_engine
import quant_indicators_plugin
import tg_ui_plugin
import toss_api
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
    DEFAULT_GOLDEN_ALLIN_MODE,
    GOLDEN_ALLIN_MODES,
    summarize_stratum_portfolio,
)
from quant_indicators_plugin import (
    compute_soxl_quant_metrics_1m,
    refresh_metrics_with_live_tick,
)
from sniper_plugin import mark_reserve_deposit_check_shield
from tg_ui_plugin import (
    SEED_INPUT_PROMPT_TIMEOUT_SEC,
    _build_main_reply_keyboard,
    _build_settlement_inline_keyboard,
    _format_case67_quota_badge,
    build_avwap_radar_message,
    build_settlement_control_message,
    build_start_schedule_message,
    build_sync_instruction_message,
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

# URL("https://...") 오매칭을 100% 차단하는 엄격한 텔레그램 봇 토큰 정규식
_TG_TOKEN_STRICT_RE = re.compile(r"\b(\d{8,12}:[A-Za-z0-9_-]{25,60})\b")


def _escape_html(val: Any) -> str:
    return html.escape(str(val if val is not None else ""), quote=False)


# ---------------------------------------------------------------------------
# [핵심 1] Case 13 & Case 62 : 적응형 비동기 플러그인 호출기 및 동적 심볼 리졸버
# ---------------------------------------------------------------------------
async def _call_plugin_adaptive(
    func: Callable[..., Any],
    **kwargs: Any,
) -> Any:
    """
    🚨 Case 13:
    플러그인 함수의 시그니처(인자 목록 및 **kwargs 수용 여부)를 동적으로 검사하여
    허용된 인자만 안전하게 주입하고 동기/비동기 함수를 모두 실행한다.
    """
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
    """
    주어진 모듈 목록에서 후보 심볼명을 순차 탐색하거나 조건(predicate)에 부합하는 객체를 반환한다.
    """
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
# [핵심 2] TossApiClient 런타임 메서드 호환성 폴리필 어댑터 (보조 폴리필 5종 및 close 포함)
# ---------------------------------------------------------------------------
def _empty_soxl_holding_entry() -> Dict[str, Any]:
    return {
        "symbol": TARGET_SYMBOL,
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
    pl_obj = (
        item.get("profitLoss")
        if isinstance(it_pl := item.get("profitLoss"), dict)
        else {}
    )

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
    if pur_amt > 0.0 and abs(raw_rate) < 2.0 and abs(pnl_amt / pur_amt) > 0.005:
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
        TARGET_SYMBOL: _empty_soxl_holding_entry()
    }

    if isinstance(raw_res, dict):
        if TARGET_SYMBOL in raw_res and isinstance(
            raw_res[TARGET_SYMBOL], dict
        ):
            out_map[TARGET_SYMBOL] = _normalize_single_holding_item(
                raw_res[TARGET_SYMBOL], TARGET_SYMBOL
            )
            return out_map, True

        if (
            str(raw_res.get("symbol") or "").upper().strip() == TARGET_SYMBOL
            and ("quantity" in raw_res or "qty" in raw_res)
        ):
            out_map[TARGET_SYMBOL] = _normalize_single_holding_item(
                raw_res, TARGET_SYMBOL
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
                    if sym == TARGET_SYMBOL:
                        out_map[TARGET_SYMBOL] = _normalize_single_holding_item(
                            it, TARGET_SYMBOL
                        )
            return out_map, True

        if len(raw_res) == 0:
            return out_map, True

    if isinstance(raw_res, list):
        for it in raw_res:
            if isinstance(it, dict):
                sym = str(it.get("symbol") or "").upper().strip()
                if sym == TARGET_SYMBOL:
                    out_map[TARGET_SYMBOL] = _normalize_single_holding_item(
                        it, TARGET_SYMBOL
                    )
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
    """
    # [Case 80]:
    result.candles 표준 스키마뿐만 아니라 result 직접 리스트, items, data 키 응답을 모두 파싱한다.
    """
    if isinstance(raw_res, list):
        return [c for c in raw_res if isinstance(c, dict)], None
    if isinstance(raw_res, dict):
        res_obj = raw_res.get("result") if "result" in raw_res else raw_res
        if isinstance(res_obj, list):
            return [c for c in res_obj if isinstance(c, dict)], None
        if isinstance(res_obj, dict):
            c_list = (
                res_obj.get("candles")
                if res_obj.get("candles") is not None
                else (
                    res_obj.get("items")
                    if res_obj.get("items") is not None
                    else res_obj.get("data")
                )
            )
            next_b = res_obj.get("nextBefore")
            if isinstance(c_list, list):
                return (
                    [c for c in c_list if isinstance(c, dict)],
                    str(next_b).strip() if next_b else None,
                )
    return [], None


def _install_toss_api_compatibility_patches() -> None:
    """
    TossApiClient 에 필수 메서드가 누락된 구버전 환경에서도 런타임 AttributeError 를 0건으로 차단한다.
    (보조 폴리필 5종: get_open_orders, cancel_all_open_orders, find_latest_open_order_id,
     get_buying_power_usd, get_usd_krw_rate 및 close 포함)
    """
    if not hasattr(TossApiClient, "get_holdings_map_with_status"):

        async def _poly_get_holdings_map_with_status(
            self: Any, symbol: str = TARGET_SYMBOL
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
                raw = await _invoke_raw_toss_api(
                    self,
                    method="GET",
                    path="/api/v1/holdings",
                    params={"symbol": symbol},
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

    if not hasattr(TossApiClient, "get_candles_1m"):

        async def _poly_get_candles_1m(
            self: Any,
            symbol: str = TARGET_SYMBOL,
            total_count: int = 300,
            count: Optional[int] = None,
            **kwargs: Any,
        ) -> List[Dict[str, Any]]:
            req_total = max(1, safe_int(count or total_count, 200))
            for cand_name in (
                "get_candles_paginated",
                "fetch_candles_1m",
                "get_minute_candles",
                "get_1m_candles",
                "get_candles",
                "fetch_candles",
                "get_chart_candles",
            ):
                fn = getattr(self, cand_name, None)
                if callable(fn):
                    try:
                        res = await _call_plugin_adaptive(
                            fn,
                            symbol=symbol,
                            interval="1m",
                            count=min(200, req_total),
                            total_count=req_total,
                            adjusted=True,
                        )
                        c_list, _ = _extract_candles_list(res)
                        if c_list:
                            return c_list
                    except Exception:
                        pass

            collected: List[Dict[str, Any]] = []
            seen_ts: Set[str] = set()
            before_cursor: Optional[str] = None
            pages = 2 if req_total > 200 else 1
            for page_i in range(pages):
                rem = max(1, min(200, req_total - len(collected)))
                q_params: Dict[str, Any] = {
                    "symbol": symbol,
                    "interval": "1m",
                    "count": (200 if page_i == 0 and req_total >= 100 else rem),
                    "adjusted": "true",
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
                    break
                if not page_candles:
                    break
                for c in page_candles:
                    ts_s = str(c.get("timestamp") or "").strip()
                    if ts_s and ts_s not in seen_ts:
                        seen_ts.add(ts_s)
                        collected.append(c)
                if (
                    not next_b
                    or next_b == before_cursor
                    or len(collected) >= req_total
                ):
                    break
                before_cursor = next_b
            collected.sort(key=lambda x: str(x.get("timestamp") or ""))
            return collected

        setattr(TossApiClient, "get_candles_1m", _poly_get_candles_1m)

    if not hasattr(TossApiClient, "get_candles_1d"):

        async def _poly_get_candles_1d(
            self: Any,
            symbol: str = TARGET_SYMBOL,
            count: int = 10,
            **kwargs: Any,
        ) -> List[Dict[str, Any]]:
            req_cnt = max(1, min(200, safe_int(count, 10)))
            raw = await _invoke_raw_toss_api(
                self,
                method="GET",
                path="/api/v1/candles",
                params={
                    "symbol": symbol,
                    "interval": "1d",
                    "count": req_cnt,
                    "adjusted": "true",
                },
                require_account=False,
            )
            c_list, _ = _extract_candles_list(raw)
            return c_list

        setattr(TossApiClient, "get_candles_1d", _poly_get_candles_1d)

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
    """
    🚨 Case 68:
    폴더 위치(base_dir)와 원장 경로(filepath)를 주입하여 폴더별 3중 안전 원장을 초기화한다.
    """
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
    """
    # [Case 01 & Case 79]:
    금요일 애프터마켓(16:00 ~ 19:59 EST) 익절 매도 개방을 위해 금요일 휴장 진입 시각을 20:00 EST 로 동기화한다.
    """
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
# [핵심 3] 자체 벡터화 1분봉/일봉 지표 및 Wilder's RSI(14) 산출 폴백 (Case 80 완벽 호환)
# ---------------------------------------------------------------------------
def _compute_vectorized_metrics_fallback(
    candles_1m: List[Dict[str, Any]],
    live_price: float,
    now_est: datetime,
    candles_1d: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    # [Case 80]:
    quant_indicators_plugin.compute_soxl_quant_metrics_1m() 를 최우선 호출하여
    인메모리 1분봉(_LIVE_1M_BAR_STORE) 병합 및 Wilder's RSI(14) 산출을 수행하고,
    예외 발생 시에만 ISO8601 + np.diff 기반 자체 벡터화 폴백을 수행한다.
    """
    dt_now = now_est.astimezone(EST_TZ)
    lp = safe_float(live_price, 0.0)

    try:
        res_primary = compute_soxl_quant_metrics_1m(
            candles=candles_1m,
            live_price=lp,
            now_est=dt_now,
            daily_candles=candles_1d,
        )
        if isinstance(res_primary, dict):
            return res_primary
    except Exception:
        pass

    today_str = dt_now.strftime("%Y-%m-%d")
    out: Dict[str, Any] = {
        "symbol": TARGET_SYMBOL,
        "live_price": round(lp, 4),
        "ma5_amp_pct": 6.50,
        "rsi_14": 50.0,
        "rsi_ready": False,
        "prev_bar_close": 0.0,
        "prev_avg_gain": 0.0,
        "prev_avg_loss": 0.0,
        "ha_bull": True,
        "ha_badge": "🕯️HA양봉",
        "premarket_vwap": 0.0,
        "premarket_high": 0.0,
        "premarket_low": 0.0,
        "premarket_amp_pct": 0.0,
        "premarket_est_low": 0.0,
        "premarket_est_high": 0.0,
        "regular_vwap": 0.0,
        "regular_high": 0.0,
        "regular_low": 0.0,
        "regular_amp_pct": 0.0,
        "regular_est_low": 0.0,
        "regular_est_high": 0.0,
    }

    if isinstance(candles_1d, list) and len(candles_1d) >= 2:
        try:
            df_d = pd.DataFrame(candles_1d)
            if "highPrice" in df_d.columns and "lowPrice" in df_d.columns:
                hs = pd.to_numeric(df_d["highPrice"], errors="coerce")
                ls = pd.to_numeric(df_d["lowPrice"], errors="coerce")
                valid = (hs > 0) & (ls > 0) & (hs >= ls)
                hv = (
                    hs[valid].to_numpy(dtype=float)[-6:-1]
                    if valid.sum() > 5
                    else hs[valid].to_numpy(dtype=float)[-5:]
                )
                lv = (
                    ls[valid].to_numpy(dtype=float)[-6:-1]
                    if valid.sum() > 5
                    else ls[valid].to_numpy(dtype=float)[-5:]
                )
                if len(lv) >= 1:
                    out["ma5_amp_pct"] = round(
                        float(
                            np.mean(((hv - lv) / np.maximum(0.01, lv)) * 100.0)
                        ),
                        2,
                    )
        except Exception:
            pass

    if not isinstance(candles_1m, list) or not candles_1m:
        return refresh_metrics_with_live_tick(out, lp, now_est=dt_now)

    try:
        df = pd.DataFrame(candles_1m)
        if df.empty or "timestamp" not in df.columns:
            return refresh_metrics_with_live_tick(out, lp, now_est=dt_now)

        try:
            ts_utc = pd.to_datetime(
                df["timestamp"], format="ISO8601", utc=True, errors="coerce"
            )
        except Exception:
            ts_utc = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")

        df = df.loc[ts_utc.notna()].copy()
        if df.empty:
            return refresh_metrics_with_live_tick(out, lp, now_est=dt_now)

        df["dt_est"] = ts_utc[ts_utc.notna()].dt.tz_convert(EST_TZ)
        df.sort_values("dt_est", ascending=True, inplace=True)
        df.drop_duplicates(subset=["dt_est"], keep="last", inplace=True)

        df["O"] = pd.to_numeric(
            df.get("openPrice", df.get("open")), errors="coerce"
        )
        df["H"] = pd.to_numeric(
            df.get("highPrice", df.get("high")), errors="coerce"
        )
        df["L"] = pd.to_numeric(
            df.get("lowPrice", df.get("low")), errors="coerce"
        )
        df["C"] = pd.to_numeric(
            df.get("closePrice", df.get("close")), errors="coerce"
        )
        df["V"] = pd.to_numeric(
            df.get("volume", 0.0), errors="coerce"
        ).fillna(0.0)
        df.dropna(subset=["O", "H", "L", "C"], inplace=True)
        if df.empty:
            return refresh_metrics_with_live_tick(out, lp, now_est=dt_now)

        if lp <= 0.0:
            lp = float(df["C"].iloc[-1])
            out["live_price"] = round(lp, 4)

        opens = df["O"].to_numpy(dtype=float)
        highs = df["H"].to_numpy(dtype=float)
        lows = df["L"].to_numpy(dtype=float)
        closes = df["C"].to_numpy(dtype=float)
        if lp > 0.0 and len(closes) > 0:
            closes[-1] = lp
            highs[-1] = max(highs[-1], lp)
            lows[-1] = min(lows[-1], lp)

        ha_c = (opens + highs + lows + closes) * 0.25
        shifted = np.empty(len(ha_c), dtype=float)
        shifted[0] = (opens[0] + closes[0]) * 0.5
        if len(ha_c) > 1:
            shifted[1:] = ha_c[:-1]
        ha_o = (
            pd.Series(shifted)
            .ewm(alpha=0.5, adjust=False)
            .mean()
            .to_numpy(dtype=float)
        )
        is_bull = bool(ha_c[-1] >= ha_o[-1])
        out["ha_bull"] = is_bull
        out["ha_badge"] = "🕯️HA양봉" if is_bull else "🌑HA음봉"
        out["prev_ha_open"] = round(
            float(ha_o[-2] if len(ha_o) >= 2 else ha_o[-1]), 4
        )
        out["prev_ha_close"] = round(
            float(ha_c[-2] if len(ha_c) >= 2 else ha_c[-1]), 4
        )
        out["cur_bar_open"] = round(float(opens[-1]), 4)
        out["cur_bar_high"] = round(float(highs[-1]), 4)
        out["cur_bar_low"] = round(float(lows[-1]), 4)

        # Case 80: np.diff 기반 Wilder's RSI(14) 및 직전 봉 기저값 산출
        n_c = len(closes)
        if n_c >= 2:
            deltas = np.diff(closes)
            gains = np.maximum(0.0, deltas)
            losses = np.maximum(0.0, -deltas)
            avg_gain = (
                pd.Series(gains)
                .ewm(alpha=1.0 / 14.0, min_periods=1, adjust=False)
                .mean()
                .to_numpy(dtype=float)
            )
            avg_loss = (
                pd.Series(losses)
                .ewm(alpha=1.0 / 14.0, min_periods=1, adjust=False)
                .mean()
                .to_numpy(dtype=float)
            )
            last_g = float(avg_gain[-1])
            last_l = float(avg_loss[-1])
            out["prev_bar_close"] = round(float(closes[-2]), 4)
            out["prev_avg_gain"] = round(
                float(avg_gain[-2]) if len(avg_gain) >= 2 else 0.0, 6
            )
            out["prev_avg_loss"] = round(
                float(avg_loss[-2]) if len(avg_loss) >= 2 else 0.0, 6
            )
            out["rsi_ready"] = bool(n_c >= 14)
            if last_g <= 1e-12 and last_l <= 1e-12:
                out["rsi_14"] = 50.0
            elif last_l <= 1e-12:
                out["rsi_14"] = 100.0
            else:
                rs = last_g / last_l
                out["rsi_14"] = round(100.0 - (100.0 / (1.0 + rs)), 2)

        df["Date"] = df["dt_est"].dt.strftime("%Y-%m-%d")
        df["hm"] = df["dt_est"].dt.hour * 100 + df["dt_est"].dt.minute
        t_date = (
            today_str
            if (df["Date"] == today_str).any()
            else str(df["Date"].iloc[-1])
        )
        df_t = df[df["Date"] == t_date]

        amp_ratio = max(0.01, float(out["ma5_amp_pct"]) / 100.0)
        for prefix, sub in (
            ("premarket", df_t[(df_t["hm"] >= 400) & (df_t["hm"] <= 929)]),
            ("regular", df_t[(df_t["hm"] >= 930) & (df_t["hm"] <= 1600)]),
        ):
            if not sub.empty:
                h_a = sub["H"].to_numpy(dtype=float)
                l_a = sub["L"].to_numpy(dtype=float)
                c_a = sub["C"].to_numpy(dtype=float)
                v_a = np.maximum(0.0, sub["V"].to_numpy(dtype=float))
                tp = (h_a + l_a + c_a) / 3.0
                tv = float(np.sum(v_a))
                vwap_v = (
                    float(np.sum(tp * v_a) / tv)
                    if tv > 0
                    else float(np.mean(tp))
                )
                sh = float(np.max(h_a))
                sl = float(np.min(l_a))
                out[f"{prefix}_vwap"] = round(vwap_v, 4)
                out[f"{prefix}_high"] = round(sh, 4)
                out[f"{prefix}_low"] = round(sl, 4)
                out[f"{prefix}_amp_pct"] = round(
                    ((sh - sl) / sl) * 100.0 if sl > 0 else 0.0, 2
                )
                out[f"{prefix}_est_high"] = round(
                    max(sh, sl * (1.0 + amp_ratio)), 2
                )
                out[f"{prefix}_est_low"] = round(
                    min(sl, sh / (1.0 + amp_ratio)), 2
                )
    except Exception:
        pass

    return refresh_metrics_with_live_tick(out, lp, now_est=dt_now)


async def _compute_candle_metrics_dynamic(
    context: Any,
    candles_1m: List[Dict[str, Any]],
    live_price: float,
    now_est: datetime,
    candles_1d: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    # [Case 80 : compute_soxl_quant_metrics_1m 결과 무손실 직결]:
    quant_indicators_plugin.compute_soxl_quant_metrics_1m() 가 반환한 딕셔너리를
    조건부 누락 없이 즉시 채택하여 인메모리 1분봉 합성 기저값(prev_bar_close 등)이 100% 유지되도록 보장한다.
    """
    try:
        res_direct = compute_soxl_quant_metrics_1m(
            candles=candles_1m,
            live_price=live_price,
            now_est=now_est,
            daily_candles=candles_1d,
        )
        if isinstance(res_direct, dict):
            return refresh_metrics_with_live_tick(
                res_direct, live_price, now_est=now_est
            )
    except Exception as exc:
        logger.debug("compute_soxl_quant_metrics_1m 직접 호출 폴백: %s", exc)

    return _compute_vectorized_metrics_fallback(
        candles_1m=candles_1m,
        live_price=live_price,
        now_est=now_est,
        candles_1d=candles_1d,
    )


# ---------------------------------------------------------------------------
# [핵심 4] 폴더 위치(base_dir) 전용 텔레그램 토큰·채팅방 ID 자동 탐색기 (Case 68)
# ---------------------------------------------------------------------------
def _extract_valid_tg_token(text: str) -> str:
    if not text or "://" in text:
        return ""
    m = _TG_TOKEN_STRICT_RE.search(str(text).strip())
    return m.group(1) if m else ""


def _discover_telegram_credentials(
    base_dir: str, api_obj: Any = None
) -> Tuple[str, str]:
    """
    🚨 Case 68:
    "/home/pipiosToss" 고정 경로 하드코딩을 100% 영구 제거하고, 오직 현재 봇이 위치한
    물리적 폴더(target_dir = get_bot_base_dir(base_dir))의 .env 와 설정 파일만 참조한다.
    """
    target_dir = get_bot_base_dir(base_dir)
    candidate_dirs = [target_dir]
    for d in candidate_dirs:
        if not d or not os.path.isdir(d):
            continue
        env_fp = os.path.join(d, ".env")
        if os.path.isfile(env_fp):
            try:
                with open(env_fp, "r", encoding="utf-8", errors="ignore") as f:
                    for raw_line in f:
                        line = raw_line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        if line.startswith("export "):
                            line = line[len("export ") :].strip()
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'").strip('"')
                        if k and v and k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass

    token_keys = (
        "TELEGRAM_BOT_TOKEN",
        "TG_BOT_TOKEN",
        "BOT_TOKEN",
        "TELEGRAM_TOKEN",
        "TG_TOKEN",
    )
    chat_keys = (
        "TELEGRAM_CHAT_ID",
        "TG_CHAT_ID",
        "CHAT_ID",
        "TELEGRAM_ADMIN_ID",
        "ADMIN_CHAT_ID",
        "ALLOWED_CHAT_ID",
    )

    bot_token = ""
    chat_id = ""

    for k in token_keys:
        cand = _extract_valid_tg_token(str(os.environ.get(k) or ""))
        if cand:
            bot_token = cand
            break

    if not bot_token:
        for _, v in os.environ.items():
            cand = _extract_valid_tg_token(str(v or ""))
            if cand:
                bot_token = cand
                break

    for k in chat_keys:
        v = str(os.environ.get(k) or "").strip()
        if v.lstrip("-").isdigit() and len(v.lstrip("-")) >= 5:
            chat_id = v
            break

    scan_targets: List[Any] = [tg_ui_plugin, toss_api]
    if api_obj is not None:
        scan_targets.insert(0, api_obj)

    for target in scan_targets:
        try:
            obj_dict = vars(target)
        except Exception:
            continue
        for attr_name, attr_val in obj_dict.items():
            if isinstance(attr_val, (str, int)):
                s_val = str(attr_val).strip()
                u_name = attr_name.upper()
                if not bot_token:
                    cand = _extract_valid_tg_token(s_val)
                    if cand:
                        bot_token = cand
                if not chat_id and (
                    "CHAT_ID" in u_name or "ADMIN_ID" in u_name
                ):
                    if (
                        s_val.lstrip("-").isdigit()
                        and len(s_val.lstrip("-")) >= 5
                    ):
                        chat_id = s_val

    if not bot_token or not chat_id:
        chat_re = re.compile(
            r"(?:CHAT_ID|chat_id)\s*[:=]\s*['\"]?(-?\d{6,15})['\"]?"
        )
        for d in candidate_dirs:
            if not d or not os.path.isdir(d):
                continue
            for fn in (
                ".env",
                "config.json",
                "secrets.json",
                "toss_api.py",
                "tg_ui_plugin.py",
            ):
                fp = os.path.join(d, fn)
                if not os.path.isfile(fp):
                    continue
                try:
                    with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    if not bot_token:
                        m_tok = _TG_TOKEN_STRICT_RE.search(content)
                        if m_tok:
                            bot_token = m_tok.group(1)
                    if not chat_id:
                        m_cid = chat_re.search(content)
                        if m_cid:
                            chat_id = m_cid.group(1)
                except Exception:
                    pass

    return bot_token, chat_id


# ---------------------------------------------------------------------------
# [핵심 5] 내장형 텔레그램 브릿지 (_AdaptiveTelegramBridge — tg_ui_plugin 렌더러 직결 & Case 80/81/83/84 완벽 통합)
# ---------------------------------------------------------------------------
class _AdaptiveTelegramBridge:
    """
    # MODIFIED [Case 62 ~ 84]:
    tg_ui_plugin 의 4대 관제 보드 렌더러(build_start_schedule_message, build_avwap_radar_message,
    build_sync_instruction_message, build_settlement_control_message)를 단일 소스로 재사용하여
    코드 중복을 제거하고,
    - [Case 81] 토스 API 클라이언트와 완전히 독립된 텔레그램 전용 httpx.AsyncClient 세션 운용 및
      HTTP 409 Conflict / 연속 3회 오류 시 세션 자동 재생성 불사조 롱폴링(Immortal Supervisor Wrapper)
    - [Case 81] 폴더별 오프셋 파일(.tg_update_offset_<folder_slug>.dat) + 3중 원장 + 서버 3중 선행 영속화
    - [Case 81] /update 완료 후 구버전 os._exit(0) 대신 3.5초 하드 워치독 및 perform_self_restart_execv(os.execv)로
      100% 무중단 자가 교체 수행 (12대 코어 모듈 프리플라이트 안내 동기화 포함)!
    """

    def __init__(self, context: Any) -> None:
        self.context: Any = context
        self.base_dir: str = get_bot_base_dir(
            getattr(context, "base_dir", None)
        )
        self.bot_token, self.chat_id = _discover_telegram_credentials(
            self.base_dir, getattr(context, "api", None)
        )
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
        토스 API 세션과 분리된 텔레그램 전용 httpx.AsyncClient 를 생성/반환한다.
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
        신구 프로세스 간 HTTP 409 Conflict 충돌을 원천 차단한다.
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
            "♻️ [Case 81 내장 텔레그램 전용 HTTP 세션 자가 치유 재생성] 사유=%s",
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
                    "내장 브릿지 httpx(%s) 호출 예외 -> urllib 폴백: %s",
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
        최신 update_id 를 로컬 오프셋 파일(.tg_update_offset_<folder_slug>.dat)과 3중 원장에 동시 영속화한다.
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
        if self.bot_token and target_chat:
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
                res = await self._call_tg(
                    "sendMessage", payload, timeout_sec=10.0
                )
            if bool(res.get("ok")):
                return True
        return False

    async def edit_or_send_message(
        self,
        chat_id: str,
        message_id: Optional[int],
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if self.bot_token and chat_id and message_id and message_id > 0:
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
        safe_title = _escape_html(title)
        safe_body = _escape_html(body)
        msg = (
            f"<b>{safe_title}</b>\n🔸 {safe_body}"
            if safe_body
            else f"<b>{safe_title}</b>"
        )
        return await self.send_message(
            text=msg, chat_id=self.chat_id, reply_markup=reply_markup
        )

    async def send_startup_alive_banner(self) -> None:
        """
        # 기동 완료 후 "✅ 서버가 정상 작동 중입니다." 단일 라인 생존 신호 타전 (Case 16)
        """
        text = "<b>✅ 서버가 정상 작동 중입니다.</b>"
        sent = await self.send_message(
            text=text, reply_markup=_build_main_reply_keyboard()
        )
        if not sent:
            await self.send_slim_alert(
                title="✅ 서버가 정상 작동 중입니다.",
                body="",
            )

    async def _refresh_live_price_and_metrics(
        self,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        # [Case 80 : /avwap 조회 시 1분봉 미확보 상태면 즉시 온디맨드 프리워밍 수행]:
        현재가를 최신화한 뒤, 만약 candle_metrics_cache 에 아직 prev_bar_close 가 세팅되어 있지 않다면
        그 자리에서 get_candles_1m(total_count=200)을 1회 호출하여 Wilder's RSI(14) 기저값을 생성한다.
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
        await self.edit_or_send_message(
            chat_id=chat_id,
            message_id=edit_msg_id,
            text=msg,
            reply_markup=None,
        )

    async def _render_and_send_sync(
        self, chat_id: str, edit_msg_id: Optional[int] = None
    ) -> None:
        now_est = datetime.now(EST_TZ)
        live_p, _ = await self._refresh_live_price_and_metrics()
        holdings_map, fetch_ok = (
            await self.context.api.get_holdings_map_with_status()
        )
        if fetch_ok and isinstance(holdings_map, dict):
            self.context.latest_holdings = holdings_map
            self.context.holdings_fetch_ok = True
            await _call_plugin_adaptive(
                reconcile_stratum_with_broker_holdings_plugin,
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
        await self.edit_or_send_message(
            chat_id=chat_id,
            message_id=edit_msg_id,
            text=msg,
            reply_markup=None,
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
                str(
                    st.get("golden_allin_mode") or DEFAULT_GOLDEN_ALLIN_MODE
                ),
            ),
        )

    async def _apply_new_seed_value(
        self, chat_id: str, raw_num_str: str
    ) -> None:
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
            return
        if val < 100.0 or val > 10000000.0:
            await self.send_message(
                chat_id=chat_id,
                text="⚠️ 시드머니는 <b>$100 ~ $10,000,000</b> 사이의 숫자로 입력해 주세요. (예: <code>10000</code>)",
            )
            return

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
        self.context.wakeup_event.set()
        live_p, _ = await self._refresh_live_price_and_metrics()
        summary = summarize_stratum_portfolio(
            updated_st, live_price=live_p, now_est=datetime.now(EST_TZ)
        )
        quota_badge_str = _format_case67_quota_badge(summary)
        await self.send_message(
            chat_id=chat_id,
            text=(
                "✅ <b>[기준 시드머니 설정 완료]</b>\n"
                f"🔸 새 기준 시드머니: <b>${val:,.2f}</b>\n"
                f"🔸 가용 현금시드: <b>${safe_float(summary.get('free_cash_usd'), 0.0):,.2f}</b>\n"
                f"🔸 차기 1회(8%) 예산: <b>${safe_float(summary.get('next_portion_budget'), 0.0):,.2f}</b> "
                f"➔ {quota_badge_str}"
            ),
            reply_markup=_build_settlement_inline_keyboard(
                bool(updated_st.get("is_active", True)),
                str(
                    updated_st.get("golden_allin_mode")
                    or DEFAULT_GOLDEN_ALLIN_MODE
                ),
            ),
        )

    async def _reset_realized_profit_only(self, chat_id: str) -> None:
        """
        # [Case 02, Case 74, Case 76, Case 77 & Case 80]:
        보유 중인 주식 지층(buckets) 및 독립 골든포켓(golden_pocket)과 기준 시드머니(initial_seed_usd)는 100% 보존하고,
        오직 누적/당일 세후 실현수익금 및 자투리 절약금·스텝업 해금·황금시간 통계·예비시드 통계만 0점으로 초기화한다.
        """
        mark_reserve_deposit_check_shield(
            self.context, TARGET_SYMBOL, clear_shield=True
        )
        st_cur = self.context.ledger.get_state(TARGET_SYMBOL)
        has_buckets = bool(st_cur.get("buckets"))
        gp_cur = st_cur.get("golden_pocket") or {}
        has_gp = bool(
            isinstance(gp_cur, dict) and safe_int(gp_cur.get("qty"), 0) > 0
        )
        reset_kw: Dict[str, Any] = {
            "cumulative_realized_gross_usd": 0.0,
            "cumulative_realized_fee_usd": 0.0,
            "cumulative_realized_net_usd": 0.0,
            "daily_realized_net_usd": 0.0,
            "cumulative_leftover_saved_usd": 0.0,
            "daily_leftover_saved_usd": 0.0,
            "seed_protect_pass_cnt": 0,
            "daily_seed_protect_pass_cnt": 0,
            "cond_unlock_buy_events": 0,
            "daily_unlock_buy_events": 0,
            "golden_allin_buy_events": 0,
            "daily_golden_allin_buy_events": 0,
            "golden_pocket_sell_cnt": 0,
            "daily_golden_pocket_sell_cnt": 0,
            "golden_realized_net_usd": 0.0,
            "daily_golden_realized_net_usd": 0.0,
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
        if not has_buckets and not has_gp:
            reset_kw["used_reserve_portions_cnt"] = 0
            reset_kw["injected_reserve_usd"] = 0.0

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
        summary = summarize_stratum_portfolio(
            st_reset, live_price=live_p, now_est=datetime.now(EST_TZ)
        )
        init_seed = safe_float(summary.get("initial_seed_usd"), 10000.0)
        free_cash = safe_float(summary.get("free_cash_usd"), 0.0)
        next_bud = safe_float(
            summary.get("next_portion_budget"), init_seed * 0.08
        )
        quota_badge_str = _format_case67_quota_badge(summary)
        held_sh = safe_int(summary.get("held_shares"), 0)
        gp_sh = safe_int(summary.get("golden_pocket_qty"), 0)
        held_tiers = safe_int(summary.get("held_tiers"), 0)
        held_lots = safe_int(summary.get("held_lots"), 0)
        gp_note = f"+골든포켓 {gp_sh}주" if gp_sh > 0 else ""

        await self.send_message(
            chat_id=chat_id,
            text=(
                "🧹 <b>[실현수익 0점 초기화 완료]</b>\n"
                "🔸 누적 세후실현익: <b>$0.00</b> (자투리절약 <b>$0.00</b> · 🔓해금/🌟골든통계 <b>0회</b>)\n"
                f"🔸 복귀 기준시드: <b>${init_seed:,.2f}</b> (가용현금 <b>${free_cash:,.2f}</b>)\n"
                f"🔸 차기 1회(8%) 정량: 예산 <b>${next_bud:,.2f}</b> ➔ {quota_badge_str}\n"
                f"🔸 보유 지층 보존: <b>{held_sh}주</b> ({held_tiers}개층 · {held_lots}회차{gp_note} 유지)"
            ),
        )

    async def _execute_manual_update_command(self, chat_id: str) -> None:
        """
        # MODIFIED [Case 62, Case 68, Case 75 & Case 81]:
        1) /update 수신 즉시 오프셋을 로컬 파일(.tg_update_offset_<slug>.dat), 원장, 텔레그램 서버에 선행 확정한다.
        2) execute_git_pull_and_preflight() 로 업데이트 및 12대 코어 모듈 서브프로세스 검증을 수행한다.
        3) 신규 커밋(changed == True)이 적용되었을 때는 구버전 os._exit(0) 을 제거하고,
           텔레그램 HTTP 세션을 즉시 닫은(_close_tg_http_client) 뒤 Case 81 3.5초 하드 워치독 및
           perform_self_restart_execv(os.execv + os._exit(1) 폴백)로 무중단 인플레이스 자가 재기동한다!
        """
        await self._ack_telegram_offset(self._last_update_id)
        await self.send_message(
            chat_id=chat_id,
            text=(
                "⏳ <b>[시스템 업데이트 개시]</b>\n"
                "🔸 GitHub 최신 코드 동기화 및 12대 코어 모듈 프리플라이트 검증 중..."
            ),
        )
        fn_upd = getattr(
            plugin_updater, "execute_git_pull_and_preflight", None
        )
        changed = False
        if callable(fn_upd):
            upd_res = await _call_plugin_adaptive(
                fn_upd, base_dir=self.base_dir
            )
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
                    else "✅ 12대 코어 모듈 인메모리 컴파일 및 AST 심볼 정합성 100% 통과 · 원장 보존"
                )
            else:
                ok = bool(upd_res)
                msg = "✅ 12대 코어 모듈 인메모리 컴파일 및 AST 심볼 정합성 100% 통과 · 원장 보존"
        else:
            ok, msg = verify_all_modules_compile(self.base_dir)

        await self._ack_telegram_offset(self._last_update_id)

        if not ok:
            await self.send_message(
                chat_id=chat_id,
                text=f"⚠️ <b>[업데이트 중단 · 기존 원장 안전 보존]</b>\n{_escape_html(msg)}",
            )
            return

        if not changed:
            await self.send_message(
                chat_id=chat_id,
                text=(
                    "✅ <b>[최신 버전 검증 완료 · 무중단 가동 유지]</b>\n"
                    "🔸 원격 변경사항이 없으므로 재기동 없이 현재 스나이퍼 엔진과 원장을 계속 유지합니다."
                ),
            )
            return

        await self.send_message(
            chat_id=chat_id,
            text=(
                "🚀 <b>[신규 업데이트 검증 통과]</b>\n"
                "🔸 원장 데이터 100% 보존 상태로 스나이퍼 데몬을 무중단 자가 재기동합니다..."
            ),
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

    async def _cycle_golden_mode_and_render(
        self,
        chat_id: str,
        target_mode: Optional[str] = None,
        edit_msg_id: Optional[int] = None,
    ) -> None:
        if hasattr(self.context.ledger, "cycle_golden_allin_mode"):
            await self.context.ledger.cycle_golden_allin_mode(
                target_mode=target_mode
            )
        else:
            st_cur = self.context.ledger.get_state(TARGET_SYMBOL)
            cur_m = (
                str(
                    st_cur.get("golden_allin_mode")
                    or DEFAULT_GOLDEN_ALLIN_MODE
                )
                .upper()
                .strip()
            )
            try:
                idx = GOLDEN_ALLIN_MODES.index(cur_m)
                nxt_m = GOLDEN_ALLIN_MODES[(idx + 1) % len(GOLDEN_ALLIN_MODES)]
            except ValueError:
                nxt_m = "POCKET_ALLIN"
            await self.context.ledger.update_state(
                TARGET_SYMBOL, golden_allin_mode=nxt_m
            )
        self.context.wakeup_event.set()
        await self._render_and_send_settlement(
            chat_id=chat_id, edit_msg_id=edit_msg_id
        )

    async def _handle_command_or_text(
        self, chat_id: str, raw_text: str
    ) -> None:
        text = str(raw_text or "").strip()
        if not text:
            return

        if not self.chat_id and chat_id:
            self.chat_id = str(chat_id)

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
                        "🔒 <b>[시드머니 오입력 방지 잠금 안내]</b>\n"
                        "🔸 평시 숫자 오입력으로 인해 시드머니가 변조되는 것을 막기 위해 잠금 상태입니다.\n"
                        "🔸 시드를 변경하시려면 <b>⚙️ 전술 제어반(/settlement)</b> 에서 <b>[💵 기준 시드머니($) 설정]</b> 버튼을 먼저 누르거나, "
                        f"<code>/seed {_escape_html(clean_num_check)}</code> 명령어로 입력해 주세요."
                    ),
                )
            return

        first_token = text.split()[0].lower()
        if "@" in first_token:
            first_token = first_token.split("@", 1)[0]

        if first_token in ("/start", "/menu", "/help") or text == "⬅️ 메인 메뉴":
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
            or text == "🔫 스나이퍼 레이더"
        ):
            await self._render_and_send_avwap(chat_id=chat_id)
            return

        if first_token == "/sync" or text in (
            "📜 지층 지시서",
            "🔄 잔고 동기화",
        ):
            await self._render_and_send_sync(chat_id=chat_id)
            return

        if (
            first_token in ("/settlement", "/config")
            or text == "⚙️ 전술 제어반"
        ):
            await self._render_and_send_settlement(chat_id=chat_id)
            return

        if first_token == "/golden":
            parts = text.split(maxsplit=1)
            arg_mode = parts[1].strip() if len(parts) >= 2 else None
            await self._cycle_golden_mode_and_render(
                chat_id=chat_id, target_mode=arg_mode
            )
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
                    "🔸 보유 중인 주식 지층 보호를 위해 지층 초기화 기능은 비활성화되었습니다.\n"
                    "🔸 보유 주식을 유지한 채 실현수익만 초기화하여 설정된 기준 시드로 복귀하시려면 <code>/reset_profit</code> 명령어를 입력해 주세요."
                ),
            )
            return

        if first_token == "/update" or text == "🚀 시스템 업데이트":
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
            st_cur = self.context.ledger.get_state(TARGET_SYMBOL)
            next_act = not bool(st_cur.get("is_active", True))
            await self.context.ledger.update_state(
                TARGET_SYMBOL, is_active=next_act
            )
            if next_act:
                fn_relock = getattr(
                    defense_plugin, "relock_stratum_on_bot_resume", None
                )
                if callable(fn_relock):
                    await _call_plugin_adaptive(
                        fn_relock,
                        context=self.context,
                        now_est=datetime.now(EST_TZ),
                    )
                else:
                    await _call_plugin_adaptive(
                        reconcile_stratum_with_broker_holdings_plugin,
                        context=self.context,
                        holdings=self.context.latest_holdings,
                        prices=self.context.latest_prices,
                        now_est=datetime.now(EST_TZ),
                        force_sync=True,
                    )
            self.context.wakeup_event.set()
            await self._render_and_send_settlement(
                chat_id=chat_id, edit_msg_id=msg_id
            )
        elif data == "toggle_golden_allin_mode":
            await self._cycle_golden_mode_and_render(
                chat_id=chat_id, edit_msg_id=msg_id
            )
        elif data == "prompt_seed_input":
            self._awaiting_seed_input_chats[chat_id] = time.monotonic()
            await self.send_message(
                chat_id=chat_id,
                text=(
                    "💵 <b>[기준 시드머니($) 입력 안내]</b>\n"
                    "🔸 지금부터 <b>5분 이내</b>에 운용할 기준 달러 시드머니 금액을 숫자만 채팅창에 입력해 주세요.\n"
                    "🔸 예시: <code>10000</code> 또는 <code>19000</code>"
                ),
            )
        elif data == "reset_profit_only":
            await self._reset_realized_profit_only(chat_id=chat_id)

    async def run_polling_loop(self) -> None:
        """
        🚨 [Case 81 : 내장 텔레그램 브릿지 불사조 폴링 루프 (Immortal Supervisor Wrapper)]:
        - 텔레그램 전용 httpx.AsyncClient 분리 운용 및 HTTP 409 Conflict / 연속 3회 오류 시 자동 재생성
        - 개별 명령어 처리 예외 격리 및 최상위 감독 루프를 통해 shutdown_event.is_set() 전까지
          어떠한 예외에서도 텔레그램 수신 태스크가 단독 사망하지 않도록 100% 보장한다.
        """
        if not _extract_valid_tg_token(self.bot_token):
            self.bot_token, discovered_cid = _discover_telegram_credentials(
                self.base_dir, getattr(self.context, "api", None)
            )
            if not self.chat_id and discovered_cid:
                self.chat_id = discovered_cid

        if not _extract_valid_tg_token(self.bot_token):
            logger.error(
                "🚨 유효한 텔레그램 봇 토큰(숫자:영숫자)을 찾을 수 없습니다! 현재 폴더(%s)의 .env 내 TELEGRAM_BOT_TOKEN 을 확인하세요.",
                self.base_dir,
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
                        "📡 [Case 81 불사조 텔레그램 관제탑 폴링 루프 가동 완료] (폴더=%s · chat_id=%s · last_update_id=%d)",
                        getattr(self.context, "folder_slug", "default"),
                        self.chat_id or "auto-detect",
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
                                                        == "🚀 시스템 업데이트"
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
                                                "⚠️ [Case 81 내장 브릿지 개별 메시지 처리 예외 격리(폴링 유지)]: %s",
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
                        except Exception as exc:
                            self._consecutive_poll_errors += 1
                            if self._consecutive_poll_errors >= 3:
                                await self._recreate_tg_http_client(
                                    reason=f"POLL_EXC_{type(exc).__name__}"
                                )
                                self._consecutive_poll_errors = 0
                            logger.debug(
                                "텔레그램 폴링 내부 루프 일시 예외(자가 치유): %s",
                                exc,
                            )
                            await asyncio.sleep(2.0)
                except asyncio.CancelledError:
                    break
                except Exception as sup_exc:
                    logger.warning(
                        "🛡️ [Case 81 내장 브릿지 불사조 감독 루프 재기동] 3초 후 세션 재생성 복구: %s",
                        sup_exc,
                    )
                    await self._recreate_tg_http_client(
                        reason="SUPERVISOR_RECOVERY"
                    )
                    await asyncio.sleep(3.0)
        finally:
            await self._close_tg_http_client()


async def _run_auto_update_loop_dynamic(
    context: Any, interval_sec: float = 3600.0
) -> None:
    fn = _resolve_module_attr(
        modules=(plugin_updater,),
        candidate_names=(
            "run_auto_update_loop",
            "auto_update_loop",
            "start_auto_update_loop",
            "background_auto_update_loop",
        ),
        predicate=lambda f: (
            inspect.iscoroutinefunction(f) and "loop" in f.__name__.lower()
        ),
    )
    if callable(fn):
        await _call_plugin_adaptive(
            fn, context=context, interval_sec=interval_sec
        )
        return

    while not context.shutdown_event.is_set():
        try:
            await asyncio.wait_for(
                context.shutdown_event.wait(), timeout=interval_sec
            )
        except asyncio.TimeoutError:
            pass
