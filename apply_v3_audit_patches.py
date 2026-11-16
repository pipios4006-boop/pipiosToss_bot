#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
# NEW: apply_v3_audit_patches.py (Part 1/4 ~ 4/4)
Infinite Snowball v3.0 — 15대 코어 모듈 5단계 전수 감사(Audit) 핀포인트 원자적 패치기
- 대상 경로: /home/pipiosToss (3대 원장 JSON 및 .env 물리적 접근 0% 불가침 격리)
- 방어 규율: Exact-Once 매칭 · 100% 멱등성 · RAM 선행 컴파일 · Case 85 중괄호 검증 ·
            최상위 AST 심볼 교차 검증 · 백업/원자적 교체 · 3대 TDD 서브프로세스 검증
"""

from __future__ import annotations

import argparse
import ast
import errno
import glob
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

DEFAULT_TARGET_DIR: str = "/home/pipiosToss"

REQUIRED_CORE_MODULES: Tuple[str, ...] = (
    "toss_api_core.py",
    "toss_api.py",
    "quant_indicators_plugin.py",
    "quant_engine_core.py",
    "quant_engine.py",
    "sniper_plugin_core.py",
    "sniper_plugin.py",
    "sniper_exit_plugin.py",
    "defense_plugin.py",
    "barbell_plugin.py",
    "assassin_plugin.py",
    "tg_ui_plugin.py",
    "plugin_updater.py",
    "main_runtime.py",
    "main.py",
)

_FSTRING_BROKEN_BRACE_RE = re.compile(
    r"(\{[A-Za-z_][A-Za-z0-9_]*)>(\.[A-Za-z0-9_]+)"
)

_LOADED_PARTS: List[int] = [1]


@dataclass
class PatchItem:
    patch_id: str
    filename: str
    description: str
    old_block: str
    new_block: str


PATCH_ITEMS: List[PatchItem] = []


def register_patch(
    patch_id: str,
    filename: str,
    description: str,
    old_block: str,
    new_block: str,
) -> None:
    if filename not in REQUIRED_CORE_MODULES:
        raise ValueError(f"허용되지 않은 패치 대상 파일 차단: {filename}")
    if old_block == new_block:
        raise ValueError(f"[{patch_id}] old_block 과 new_block 이 동일합니다.")
    PATCH_ITEMS.append(
        PatchItem(
            patch_id=patch_id,
            filename=filename,
            description=description,
            old_block=old_block,
            new_block=new_block,
        )
    )


def _collect_top_level_stmts(stmts: List[ast.stmt], exported: Set[str]) -> None:
    """모듈 최상위 네임스페이스(최상위 If/Try/With 포함, 함수/클래스 내부 지역변수 배제) 심볼 추출."""
    for node in stmts:
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            exported.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    exported.add(target.id)
                elif isinstance(target, (ast.Tuple, ast.List)):
                    for elt in target.elts:
                        if isinstance(elt, ast.Name):
                            exported.add(elt.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                exported.add(node.target.id)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                exported.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    exported.add(alias.asname or alias.name)
        elif isinstance(node, ast.If):
            _collect_top_level_stmts(node.body, exported)
            _collect_top_level_stmts(node.orelse, exported)
        elif isinstance(node, ast.Try):
            _collect_top_level_stmts(node.body, exported)
            _collect_top_level_stmts(node.orelse, exported)
            _collect_top_level_stmts(node.finalbody, exported)
            for h in node.handlers:
                if isinstance(h.name, str) and h.name:
                    exported.add(h.name)
                _collect_top_level_stmts(h.body, exported)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            _collect_top_level_stmts(node.body, exported)


def extract_top_level_exported_symbols(tree: ast.Module) -> Set[str]:
    exported: Set[str] = set()
    _collect_top_level_stmts(list(tree.body), exported)
    return exported


def verify_ram_modules_integrity(
    ram_sources: Dict[str, str],
) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    ast_trees: Dict[str, ast.Module] = {}
    exported_map: Dict[str, Set[str]] = {}
    local_mod_names = {f[:-3] for f in REQUIRED_CORE_MODULES}

    for fname in REQUIRED_CORE_MODULES:
        src = ram_sources.get(fname)
        if src is None:
            errors.append(f"필수 모듈 누락: {fname}")
            continue
        if _FSTRING_BROKEN_BRACE_RE.search(src):
            errors.append(f"[Case 85 위반] 깨진 f-string 중괄호 패턴 감지: {fname}")
            continue
        mod_name = fname[:-3]
        try:
            compile(src, fname, "exec", dont_inherit=True)
            tree = ast.parse(src, filename=fname)
            ast_trees[mod_name] = tree
            exported_map[mod_name] = extract_top_level_exported_symbols(tree)
        except SyntaxError as syn_e:
            errors.append(
                f"문법 오류 [{fname}:{getattr(syn_e, 'lineno', '?')}]: {syn_e.msg}"
            )
        except Exception as exc:
            errors.append(f"AST 파싱 예외 [{fname}]: {exc}")

    if errors:
        return False, errors

    for mod_name, tree in ast_trees.items():
        fname = f"{mod_name}.py"
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module in local_mod_names
            ):
                target_exports = exported_map.get(node.module, set())
                for alias in node.names:
                    if alias.name != "*" and alias.name not in target_exports:
                        errors.append(
                            f"심볼 불일치 [{fname}]: from {node.module} import {alias.name}"
                        )
    return len(errors) == 0, errors


# ===========================================================================
# [01. toss_api_core.py 패치 등록]
# ===========================================================================
register_patch(
    patch_id="P01_A_LOCK_AND_THROTTLE",
    filename="toss_api_core.py",
    description="환경변수 수수료 보존 가드 · _HybridFileLock 스레드 비종속 재진입 · GlobalThrottle 비블로킹 슬립",
    old_block="""    env_one, env_rt = _read_env_us_commission_rates()
    set_runtime_round_trip_fee_rate_pct(env_rt, us_commission_rate=env_one)
    return target_dir


_load_env_files_into_environ()


# ---------------------------------------------------------------------------
# [제1헌법] _HybridFileLock 및 GlobalThrottle (동기/비동기 양방향 호환 중앙 통제)
# ---------------------------------------------------------------------------
class _HybridFileLock:
    def __init__(self) -> None:
        self._thread_lock = threading.RLock()

    def __enter__(self) -> "_HybridFileLock":
        self._thread_lock.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._thread_lock.release()

    async def __aenter__(self) -> "_HybridFileLock":
        await asyncio.to_thread(self._thread_lock.acquire)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._thread_lock.release()


class GlobalThrottle:
    _api_lock = threading.Lock()
    _last_call_mono: Dict[str, float] = {}
    _file_locks_guard = threading.Lock()
    _file_locks: Dict[str, _HybridFileLock] = {}

    GROUP_INTERVALS: Dict[str, float] = {
        "AUTH": 0.50,
        "ACCOUNT": 0.25,
        "ORDER": 0.18,
        "ORDER_HISTORY": 0.15,
        "ORDER_INFO": 0.15,
        "ASSET": 0.18,
        "MARKET_DATA": 0.12,
        "MARKET_DATA_CHART": 0.22,
        "MARKET_INFO": 0.25,
        "DEFAULT": 0.15,
    }

    @classmethod
    def wait_api_sync(cls, group: str = "DEFAULT") -> None:
        grp = str(group or "DEFAULT").upper().strip()
        min_gap = cls.GROUP_INTERVALS.get(
            grp, cls.GROUP_INTERVALS["DEFAULT"]
        )
        with cls._api_lock:
            now_m = time.monotonic()
            last_m = cls._last_call_mono.get(grp, 0.0)
            wait_s = min_gap - (now_m - last_m)
            if wait_s > 0.0:
                time.sleep(wait_s)
            cls._last_call_mono[grp] = time.monotonic()""",
    new_block="""    if (
        os.environ.get("US_COMMISSION_RATE") is not None
        or os.environ.get("ROUND_TRIP_FEE_RATE_PCT") is not None
    ):
        env_one, env_rt = _read_env_us_commission_rates()
        set_runtime_round_trip_fee_rate_pct(
            env_rt, us_commission_rate=env_one
        )
    return target_dir


_load_env_files_into_environ()


# ---------------------------------------------------------------------------
# [제1헌법 · MODIFIED] _HybridFileLock(스레드/태스크 비종속 재진입 안전 락) 및 GlobalThrottle
# ---------------------------------------------------------------------------
class _HybridFileLock:
    def __init__(self) -> None:
        self._cond = threading.Condition(threading.Lock())
        self._owner: Optional[Tuple[str, int]] = None
        self._count: int = 0

    def _acquire_token(self, token: Tuple[str, int]) -> None:
        with self._cond:
            while self._owner is not None and self._owner != token:
                self._cond.wait()
            self._owner = token
            self._count += 1

    def _release_token(self, token: Tuple[str, int]) -> None:
        with self._cond:
            if self._count > 0:
                self._count -= 1
            if self._count <= 0:
                self._count = 0
                self._owner = None
                self._cond.notify()

    def __enter__(self) -> "_HybridFileLock":
        self._acquire_token(("THREAD", threading.get_ident()))
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._release_token(("THREAD", threading.get_ident()))

    async def __aenter__(self) -> "_HybridFileLock":
        task = asyncio.current_task()
        tok = ("TASK", id(task) if task is not None else threading.get_ident())
        await asyncio.to_thread(self._acquire_token, tok)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        task = asyncio.current_task()
        tok = ("TASK", id(task) if task is not None else threading.get_ident())
        self._release_token(tok)


class GlobalThrottle:
    _api_lock = threading.Lock()
    _last_call_mono: Dict[str, float] = {}
    _file_locks_guard = threading.Lock()
    _file_locks: Dict[str, _HybridFileLock] = {}

    GROUP_INTERVALS: Dict[str, float] = {
        "AUTH": 0.50,
        "ACCOUNT": 0.25,
        "ORDER": 0.18,
        "ORDER_HISTORY": 0.15,
        "ORDER_INFO": 0.15,
        "ASSET": 0.18,
        "MARKET_DATA": 0.12,
        "MARKET_DATA_CHART": 0.22,
        "MARKET_INFO": 0.25,
        "DEFAULT": 0.15,
    }

    @classmethod
    def wait_api_sync(cls, group: str = "DEFAULT") -> None:
        grp = str(group or "DEFAULT").upper().strip()
        min_gap = cls.GROUP_INTERVALS.get(
            grp, cls.GROUP_INTERVALS["DEFAULT"]
        )
        with cls._api_lock:
            now_m = time.monotonic()
            last_m = cls._last_call_mono.get(grp, 0.0)
            target_m = max(now_m, last_m + min_gap)
            wait_s = target_m - now_m
            cls._last_call_mono[grp] = target_m
        if wait_s > 0.0:
            time.sleep(wait_s)""",
)

register_patch(
    patch_id="P01_B1_ATOMIC_WRITE_FILE_LOCK",
    filename="toss_api_core.py",
    description="SoxlStratumLedger._atomic_write_json_sync 대상 파일별 GlobalThrottle 파일락 적용",
    old_block="""    @classmethod
    def _atomic_write_json_sync(
        cls,
        target_path: str,
        payload: Dict[str, Any],
        force_write: bool = False,
    ) -> bool:
        if not target_path:
            return False

        new_soxl = cls._extract_raw_soxl_dict(payload)""",
    new_block="""    @classmethod
    def _atomic_write_json_sync(
        cls,
        target_path: str,
        payload: Dict[str, Any],
        force_write: bool = False,
    ) -> bool:
        if not target_path:
            return False
        with GlobalThrottle.get_file_lock(target_path):
            return cls._atomic_write_json_body_sync(
                target_path=target_path,
                payload=payload,
                force_write=force_write,
            )

    @classmethod
    def _atomic_write_json_body_sync(
        cls,
        target_path: str,
        payload: Dict[str, Any],
        force_write: bool = False,
    ) -> bool:
        if not target_path:
            return False

        new_soxl = cls._extract_raw_soxl_dict(payload)""",
)

register_patch(
    patch_id="P01_B2_UPDATE_STATE_WAIT_FOR",
    filename="toss_api_core.py",
    description="SoxlStratumLedger.update_state 비동기 wait_for(10.0s) 타임아웃 족쇄 추가",
    old_block="""    async def update_state(
        self, symbol: str = TARGET_SYMBOL, **kwargs: Any
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.update_state_sync, symbol, **kwargs
        )""",
    new_block="""    async def update_state(
        self, symbol: str = TARGET_SYMBOL, **kwargs: Any
    ) -> Dict[str, Any]:
        return await asyncio.wait_for(
            asyncio.to_thread(self.update_state_sync, symbol, **kwargs),
            timeout=10.0,
        )""",
)


# ===========================================================================
# [02. toss_api.py 패치 등록]
# ===========================================================================
register_patch(
    patch_id="P02_A1_TOKEN_ENV_TO_THREAD",
    filename="toss_api.py",
    description="_ensure_access_token 내 동기 파일 환경변수 로더 asyncio.to_thread 격리",
    old_block="""            if not self.client_id or not self.client_secret:
                _load_env_files_into_environ(base_dir=self.base_dir)
                self.client_id = (""",
    new_block="""            if not self.client_id or not self.client_secret:
                await asyncio.to_thread(
                    _load_env_files_into_environ, self.base_dir
                )
                self.client_id = (""",
)

register_patch(
    patch_id="P02_A2_ACCOUNT_SEQ_NO_FAKE_LOCK",
    filename="toss_api.py",
    description="일시 조회 지연 시 미검증 accountSeq=1 영구 캐싱 방지",
    old_block="""            if env_seq > 0:
                self.account_seq = env_seq
                return self.account_seq

            self.account_seq = 1
            return self.account_seq""",
    new_block="""            if env_seq > 0:
                self.account_seq = env_seq
                return self.account_seq

            logger.warning(
                "⚠️ [AccountSeq 조회 폴백] 계좌 응답이 비어 있어 고정 락온 없이 1 임시 반환(차기 재탐색)"
            )
            return 1""",
)

register_patch(
    patch_id="P02_A3_COMMISSION_DATE_FILTER",
    filename="toss_api.py",
    description="Case 86 미국 주식 수수료율 조회 시 KST 유효기간(startDate/endDate) 만료 항목 필터링",
    old_block="""            items = await self.get_commissions()
            found_us_rate = 0.0
            for it in items:
                mkt = str(it.get("marketCountry") or "").upper().strip()
                if mkt == "US":
                    r_val = safe_float(it.get("commissionRate"), 0.0)
                    if 0.0 < r_val <= 0.01:
                        found_us_rate = round(r_val, 6)
                        break""",
    new_block="""            items = await self.get_commissions()
            today_kst = datetime.now(KST_TZ).strftime("%Y-%m-%d")
            found_us_rate = 0.0
            fallback_us_rate = 0.0
            for it in items:
                mkt = str(it.get("marketCountry") or "").upper().strip()
                if mkt == "US":
                    r_val = safe_float(it.get("commissionRate"), 0.0)
                    if not (0.0 < r_val <= 0.01):
                        continue
                    s_dt = str(it.get("startDate") or "").strip()[:10]
                    e_dt = str(it.get("endDate") or "").strip()[:10]
                    if s_dt and len(s_dt) == 10 and today_kst < s_dt:
                        continue
                    if e_dt and len(e_dt) == 10 and today_kst > e_dt:
                        if fallback_us_rate <= 0.0:
                            fallback_us_rate = round(r_val, 6)
                        continue
                    found_us_rate = round(r_val, 6)
                    break
            if found_us_rate <= 0.0 and fallback_us_rate > 0.0:
                found_us_rate = fallback_us_rate""",
)

register_patch(
    patch_id="P02_A4_REQUEST_TOKEN_REFRESH_INIT",
    filename="toss_api.py",
    description="_request 내 429/5xx 재시도 시 유효 OAuth2 토큰 강제 무효화 버그 제거(1/2)",
    old_block="""        last_exc: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                token = await self._ensure_access_token(
                    force_refresh=(attempt > 0 and last_exc is None)
                )
                headers: Dict[str, str] = {""",
    new_block="""        last_exc: Optional[Exception] = None
        force_token_refresh: bool = False
        for attempt in range(max_retries + 1):
            try:
                token = await self._ensure_access_token(
                    force_refresh=force_token_refresh
                )
                force_token_refresh = False
                headers: Dict[str, str] = {""",
)

register_patch(
    patch_id="P02_A5_REQUEST_TOKEN_REFRESH_ON_401",
    filename="toss_api.py",
    description="_request 내 오직 HTTP 401 응답 시에만 토큰 강제 재발급 플래그 점화(2/2)",
    old_block="""                if status_code == 401 and attempt < max_retries:
                    self._access_token = ""
                    last_exc = None
                    continue""",
    new_block="""                if status_code == 401 and attempt < max_retries:
                    self._access_token = ""
                    force_token_refresh = True
                    last_exc = None
                    continue""",
)

register_patch(
    patch_id="P02_B1_SGOV_WINDOW_AND_CID_REGEX",
    filename="toss_api.py",
    description="Case 94 SGOV 정규장 전용 가드(09:31 ~ 15:55 EST) 일치화 및 clientOrderId 36자 정규식 정제",
    old_block="""        if sym == BARBELL_SAFE_SYMBOL:
            if now_est.weekday() >= 5 or not (930 <= hm <= 1600):
                raise _NonRetryableApiError(
                    422,
                    "sgov-regular-hours-only",
                    f"바벨 SGOV 주문은 평일 정규장(09:30 ~ 16:00 EST)에만 허용됩니다 (현재 요일={now_est.weekday()}, {hm:04d} EST)",
                )
        elif enforce_daymarket_block and clean_side == "BUY":
            if now_est.weekday() >= 5 or not (407 <= hm <= 1600):
                raise _NonRetryableApiError(
                    422,
                    "outside-active-window",
                    f"평일 04:07 ~ 16:00 EST 외 매수 차단 (현재 요일={now_est.weekday()}, {hm:04d} EST)",
                )

        qty_int = max(1, safe_int(quantity, 1))
        cid = str(
            client_order_id or generate_client_order_id(prefix=clean_side)
        ).strip()[:36]""",
    new_block="""        if sym == BARBELL_SAFE_SYMBOL:
            if now_est.weekday() >= 5 or not (931 <= hm <= 1555):
                raise _NonRetryableApiError(
                    422,
                    "sgov-regular-hours-only",
                    f"바벨 SGOV 주문은 평일 정규장(09:31 ~ 15:55 EST)에만 허용됩니다 (현재 요일={now_est.weekday()}, {hm:04d} EST)",
                )
        elif enforce_daymarket_block and clean_side == "BUY":
            if now_est.weekday() >= 5 or not (407 <= hm <= 1600):
                raise _NonRetryableApiError(
                    422,
                    "outside-active-window",
                    f"평일 04:07 ~ 16:00 EST 외 매수 차단 (현재 요일={now_est.weekday()}, {hm:04d} EST)",
                )

        qty_int = max(1, safe_int(quantity, 1))
        raw_cid = str(
            client_order_id or generate_client_order_id(prefix=clean_side)
        ).strip()
        clean_cid = "".join(
            ch for ch in raw_cid if (ch.isalnum() or ch in ("-", "_"))
        )[:36]
        cid = (
            clean_cid
            if clean_cid
            else generate_client_order_id(prefix=clean_side)
        )""",
)

register_patch(
    patch_id="P02_B2_MANUAL_PROBE_REPLACED_STATUS",
    filename="toss_api.py",
    description="Case 19/63 수동 체결 역추적 시 REPLACED/REJECTED 원주문의 기체결(filledQuantity>0) 수량 회수",
    old_block="""            ord_status = str(ord_item.get("status") or "").upper().strip()
            if ord_status and ord_status not in (
                "FILLED",
                "PARTIAL_FILLED",
                "CANCELED",
            ):
                continue""",
    new_block="""            ord_status = str(ord_item.get("status") or "").upper().strip()
            if ord_status and ord_status not in (
                "FILLED",
                "PARTIAL_FILLED",
                "CANCELED",
                "REPLACED",
                "REJECTED",
            ):
                continue""",
)

_LOADED_PARTS.append(2)

# ===========================================================================
# [03. quant_indicators_plugin.py 패치 등록]
# ===========================================================================
register_patch(
    patch_id="P03_A1_SYNTHETIC_BAR_ZERO_VOL",
    filename="quant_indicators_plugin.py",
    description="실시간 합성 1분봉 초기 거래량 0.0 유지로 공식 API 0거래량 분봉 VWAP 왜곡 차단(1/2)",
    old_block="""                    "openPrice": lp,
                    "highPrice": lp,
                    "lowPrice": lp,
                    "closePrice": lp,
                    "volume": 1.0,
                    "currency": "USD",""",
    new_block="""                    "openPrice": lp,
                    "highPrice": lp,
                    "lowPrice": lp,
                    "closePrice": lp,
                    "volume": 0.0,
                    "currency": "USD",""",
)

register_patch(
    patch_id="P03_A2_SYNC_STORE_ZERO_VOL",
    filename="quant_indicators_plugin.py",
    description="API 1분봉 인메모리 동기화 시 실제 0거래량 분봉 보존(2/2)",
    old_block="""                    "openPrice": round(float(o_v), 4),
                    "highPrice": round(float(h_v), 4),
                    "lowPrice": round(float(l_v), 4),
                    "closePrice": round(float(c_v), 4),
                    "volume": round(max(1.0, float(v_v)), 2),
                    "currency": "USD",""",
    new_block="""                    "openPrice": round(float(o_v), 4),
                    "highPrice": round(float(h_v), 4),
                    "lowPrice": round(float(l_v), 4),
                    "closePrice": round(float(c_v), 4),
                    "volume": round(max(0.0, float(v_v)), 2),
                    "currency": "USD",""",
)

register_patch(
    patch_id="P03_B1_SYNTHETIC_RSI_NO_HISTORY_GUARD",
    filename="quant_indicators_plugin.py",
    description="Case 92/93 이전 등락 평균이 없는 무이력 상태에서 합성 RSI 극단치(0/100) 오격발 차단",
    old_block="""    if prev_g <= 1e-12 and prev_l <= 1e-12:
        live_g = cur_g / p_len
        live_l = cur_l / p_len
    else:
        live_g = (prev_g * (p_len - 1.0) + cur_g) / p_len
        live_l = (prev_l * (p_len - 1.0) + cur_l) / p_len""",
    new_block="""    if prev_g <= 1e-12 and prev_l <= 1e-12:
        return 50.0
    live_g = (prev_g * (p_len - 1.0) + cur_g) / p_len
    live_l = (prev_l * (p_len - 1.0) + cur_l) / p_len""",
)

register_patch(
    patch_id="P03_B2_DAILY_5MA_SORT_AND_VECTOR_RSI_15BARS",
    filename="quant_indicators_plugin.py",
    description="일봉 5MA 날짜 오름차순 정렬 및 Wilder RSI(14) 최소 15봉(14변화량) 미만 웜업 중립 50.0 가드",
    old_block="""    if isinstance(daily_candles, list) and len(daily_candles) >= 2:
        try:
            df_d = pd.DataFrame(daily_candles)""",
    new_block="""    if isinstance(daily_candles, list) and len(daily_candles) >= 2:
        try:
            sorted_dc = sorted(
                [c for c in daily_candles if isinstance(c, dict)],
                key=lambda x: str(
                    x.get("timestamp") or x.get("date") or x.get("dt") or ""
                )[:10],
            )
            df_d = pd.DataFrame(sorted_dc)""",
)

register_patch(
    patch_id="P03_B3_VECTOR_RSI_MIN_15_BARS",
    filename="quant_indicators_plugin.py",
    description="캔들 미수신 초기 2~14개 합성 분봉 구간 RSI 0.0/100.0 왜곡 원천 차단",
    old_block="""    rsi_val = 50.0
    prev_avg_g = 0.0
    prev_avg_l = 0.0

    if n >= 2:
        deltas = np.diff(closes)""",
    new_block="""    rsi_val = 50.0
    prev_avg_g = 0.0
    prev_avg_l = 0.0

    if n >= 15:
        deltas = np.diff(closes)""",
)

register_patch(
    patch_id="P03_B4_VECTOR_RSI_READY_FLAG",
    filename="quant_indicators_plugin.py",
    description="rsi_ready 판정 기준을 Wilder RSI(14) 최소 15봉(14델타)으로 일치화",
    old_block="""    clean_rsi = round(rsi_val, 2)
    return {
        "rsi_14": clean_rsi,
        "rsi": clean_rsi,
        "rsi_ready": bool(n >= 14),""",
    new_block="""    clean_rsi = round(rsi_val, 2)
    return {
        "rsi_14": clean_rsi,
        "rsi": clean_rsi,
        "rsi_ready": bool(n >= 15),""",
)

register_patch(
    patch_id="P03_C1_PRE_OPEN_WINDOW_REACH_VERIFY",
    filename="quant_indicators_plugin.py",
    description="Case 93 부분 1분봉 윈도우가 04:07 시초 구간에 도달했을 때만 진성 프리시가로 채택",
    old_block="""        df_today_api = df_api_all[df_api_all["Date"] == target_date]
        if not df_today_api.empty:
            pre_0407 = df_today_api[
                (df_today_api["hm"] >= 407) & (df_today_api["hm"] <= 929)
            ]
            if not pre_0407.empty:
                pre_open_p = float(pre_0407["O"].iloc[0])
                found_true_pre_open = True
            else:
                pre_0400 = df_today_api[
                    (df_today_api["hm"] >= 400) & (df_today_api["hm"] <= 929)
                ]
                if not pre_0400.empty:
                    pre_open_p = float(pre_0400["O"].iloc[0])
                    found_true_pre_open = True""",
    new_block="""        df_today_api = df_api_all[df_api_all["Date"] == target_date]
        if not df_today_api.empty and not df_api_all.empty:
            oldest_api_d = str(df_api_all["Date"].iloc[0])
            oldest_api_hm = int(df_api_all["hm"].iloc[0])
            window_reached_open = bool(
                oldest_api_d < target_date
                or (oldest_api_d == target_date and oldest_api_hm <= 415)
            )
            if window_reached_open:
                pre_0407 = df_today_api[
                    (df_today_api["hm"] >= 407) & (df_today_api["hm"] <= 929)
                ]
                if not pre_0407.empty:
                    pre_open_p = float(pre_0407["O"].iloc[0])
                    found_true_pre_open = True
                else:
                    pre_0400 = df_today_api[
                        (df_today_api["hm"] >= 400)
                        & (df_today_api["hm"] <= 929)
                    ]
                    if not pre_0400.empty:
                        pre_open_p = float(pre_0400["O"].iloc[0])
                        found_true_pre_open = True""",
)

register_patch(
    patch_id="P03_C2_PRESERVE_FULL_PRE_VWAP_LATCH",
    filename="quant_indicators_plugin.py",
    description="Case 93 정규장 진입 후 400봉 윈도우 이동으로 프리장 초반 봉 이탈 시 기존 전구간 프리VWAP 래치 보존",
    old_block="""        pre_stats = _calc_session_vwap_and_bands(df_pre, ma5_amp)
        found_true_pre_vwap = bool(pre_stats["vwap"] > 0.0)

        if found_true_pre_vwap:
            _update_daily_anchor_latch(
                symbol=sym,
                target_date=target_date,
                pre_stats=pre_stats,
                verified_distinct=bool(
                    found_true_prev_close
                    and found_true_pre_open
                    and not _is_collapsed_anchor_triplet(
                        prev_reg_c, pre_open_p, pre_stats["vwap"]
                    )
                ),
            )
        else:
            latched_info = _get_daily_anchor_latch(sym, target_date)
            latched_pre_stats = latched_info.get("pre_stats")
            if isinstance(latched_pre_stats, dict) and safe_float(
                latched_pre_stats.get("vwap"), 0.0
            ) > 0.0:
                pre_stats = dict(latched_pre_stats)
                found_true_pre_vwap = True""",
    new_block="""        df_api_chk = (
            df[~df["is_synthetic"]] if "is_synthetic" in df.columns else df
        )
        reached_full_pre = bool(
            not df_api_chk.empty
            and (
                str(df_api_chk["Date"].iloc[0]) < target_date
                or (
                    str(df_api_chk["Date"].iloc[0]) == target_date
                    and int(df_api_chk["hm"].iloc[0]) <= 415
                )
            )
        )
        latched_info = _get_daily_anchor_latch(sym, target_date)
        latched_pre_stats = latched_info.get("pre_stats")
        has_latched_pre_v = bool(
            isinstance(latched_pre_stats, dict)
            and safe_float(latched_pre_stats.get("vwap"), 0.0) > 0.0
        )

        pre_stats = _calc_session_vwap_and_bands(df_pre, ma5_amp)
        if hm_now > 929 and not reached_full_pre and has_latched_pre_v:
            pre_stats = dict(latched_pre_stats)
            found_true_pre_vwap = True
        elif pre_stats["vwap"] > 0.0 and (hm_now <= 929 or reached_full_pre):
            found_true_pre_vwap = True
            _update_daily_anchor_latch(
                symbol=sym,
                target_date=target_date,
                pre_stats=pre_stats,
                verified_distinct=bool(
                    found_true_prev_close
                    and found_true_pre_open
                    and not _is_collapsed_anchor_triplet(
                        prev_reg_c, pre_open_p, pre_stats["vwap"]
                    )
                ),
            )
        elif has_latched_pre_v:
            pre_stats = dict(latched_pre_stats)
            found_true_pre_vwap = True
        else:
            found_true_pre_vwap = False""",
)

register_patch(
    patch_id="P03_C3_LIVE_TICK_NO_FAKE_ANCHOR_LATCH",
    filename="quant_indicators_plugin.py",
    description="Case 93 프리장 중도 재기동 시 실시간 틱 현재가가 04:07 프리시가/프리VWAP 진성 래치를 덮어쓰는 버그 차단",
    old_block="""        if prev_b_close > 0.0:
            live_rsi = compute_realtime_synthetic_rsi(
                live_price=lp,
                prev_bar_close=prev_b_close,
                prev_avg_gain=prev_avg_g,
                prev_avg_loss=prev_avg_l,
                period=14,
            )
            met["rsi_14"] = live_rsi
            met["rsi"] = live_rsi
            met["vel_1m_pct"] = round(
                ((lp - prev_b_close) / prev_b_close) * 100.0, 4
            )

        c_3m = safe_float(met.get("close_3m_ago"), prev_b_close)
        c_5m = safe_float(met.get("close_5m_ago"), c_3m)
        c_10m = safe_float(met.get("close_10m_ago"), c_5m)
        if c_3m > 0.0:
            met["vel_3m_pct"] = round(((lp - c_3m) / c_3m) * 100.0, 4)
        if c_5m > 0.0:
            met["vel_5m_pct"] = round(((lp - c_5m) / c_5m) * 100.0, 4)
        if c_10m > 0.0:
            met["vel_10m_pct"] = round(((lp - c_10m) / c_10m) * 100.0, 4)
        met["vel_max_3m_10m_pct"] = round(
            max(
                safe_float(met.get("vel_3m_pct"), 0.0),
                safe_float(met.get("vel_10m_pct"), 0.0),
            ),
            4,
        )

        # 🚨 [Case 93 무오염 패치 : 프리장(04:07 ~ 09:29 EST) 외 구간에서는 미확보된 pre_open_price(0.0)를 현재가로 덮어쓰지 않음!]
        pre_open_p = safe_float(met.get("pre_open_price"), 0.0)
        if pre_open_p <= 0.0 and (407 <= hm <= 929):
            pre_open_p = round(lp, 4)
            met["pre_open_price"] = pre_open_p
            met["found_true_pre_open"] = True
            _update_daily_anchor_latch(
                symbol=sym,
                target_date=today_str,
                pre_open_price=pre_open_p,
            )

        if pre_open_p > 0.0:
            met["bear_drop_amp_pct"] = round(
                max(0.0, ((pre_open_p - lp) / pre_open_p) * 100.0), 4
            )
        else:
            met["pre_open_price"] = 0.0
            met["bear_drop_amp_pct"] = 0.0

        if safe_float(met.get("prev_reg_close"), 0.0) <= 0.0:
            met["prev_reg_close"] = round(
                safe_float(
                    met.get("prev_day_close"),
                    pre_open_p if pre_open_p > 0.0 else lp,
                ),
                4,
            )
        if safe_float(met.get("prev_day_close"), 0.0) <= 0.0:
            met["prev_day_close"] = met["prev_reg_close"]

        if not bool(met.get("rsi_ready", False)) and mem_bar_cnt >= 14:
            met["rsi_ready"] = True

    if lp > 0.0 and 400 <= hm <= 929:
        ph = max(safe_float(met.get("premarket_high"), 0.0), lp)
        pl_prev = safe_float(met.get("premarket_low"), 0.0)
        pl = min(pl_prev, lp) if pl_prev > 0.0 else lp
        p_amp = ((ph - pl) / pl) * 100.0 if pl > 0.0 else 0.0
        met["premarket_high"] = round(ph, 4)
        met["premarket_low"] = round(pl, 4)
        met["premarket_amp_pct"] = round(p_amp, 2)
        met["premarket_est_high"] = round(max(ph, pl * (1.0 + amp_ratio)), 2)
        met["premarket_est_low"] = round(min(pl, ph / (1.0 + amp_ratio)), 2)
        if safe_float(met.get("premarket_vwap"), 0.0) <= 0.0:
            met["premarket_vwap"] = round(lp, 4)
            met["found_true_pre_vwap"] = True""",
    new_block="""        if prev_b_close > 0.0:
            if bool(met.get("rsi_ready", False)) and (
                prev_avg_g > 1e-12 or prev_avg_l > 1e-12
            ):
                live_rsi = compute_realtime_synthetic_rsi(
                    live_price=lp,
                    prev_bar_close=prev_b_close,
                    prev_avg_gain=prev_avg_g,
                    prev_avg_loss=prev_avg_l,
                    period=14,
                )
                met["rsi_14"] = live_rsi
                met["rsi"] = live_rsi
            met["vel_1m_pct"] = round(
                ((lp - prev_b_close) / prev_b_close) * 100.0, 4
            )

        c_3m = safe_float(met.get("close_3m_ago"), prev_b_close)
        c_5m = safe_float(met.get("close_5m_ago"), c_3m)
        c_10m = safe_float(met.get("close_10m_ago"), c_5m)
        if c_3m > 0.0:
            met["vel_3m_pct"] = round(((lp - c_3m) / c_3m) * 100.0, 4)
        if c_5m > 0.0:
            met["vel_5m_pct"] = round(((lp - c_5m) / c_5m) * 100.0, 4)
        if c_10m > 0.0:
            met["vel_10m_pct"] = round(((lp - c_10m) / c_10m) * 100.0, 4)
        met["vel_max_3m_10m_pct"] = round(
            max(
                safe_float(met.get("vel_3m_pct"), 0.0),
                safe_float(met.get("vel_10m_pct"), 0.0),
            ),
            4,
        )

        # 🚨 [Case 93 무오염 패치 : 중도 재기동 시 현재가를 진성 래치로 박제하지 않으며 04:07 정각에만 임시 반영]
        pre_open_p = safe_float(met.get("pre_open_price"), 0.0)
        if pre_open_p <= 0.0 and hm == 407:
            pre_open_p = round(lp, 4)
            met["pre_open_price"] = pre_open_p

        if pre_open_p > 0.0:
            met["bear_drop_amp_pct"] = round(
                max(0.0, ((pre_open_p - lp) / pre_open_p) * 100.0), 4
            )
        else:
            met["pre_open_price"] = 0.0
            met["bear_drop_amp_pct"] = 0.0

        if safe_float(met.get("prev_reg_close"), 0.0) <= 0.0:
            met["prev_reg_close"] = round(
                safe_float(
                    met.get("prev_day_close"),
                    pre_open_p if pre_open_p > 0.0 else lp,
                ),
                4,
            )
        if safe_float(met.get("prev_day_close"), 0.0) <= 0.0:
            met["prev_day_close"] = met["prev_reg_close"]

        if not bool(met.get("rsi_ready", False)) and mem_bar_cnt >= 15:
            met["rsi_ready"] = True

    if lp > 0.0 and 400 <= hm <= 929:
        ph = max(safe_float(met.get("premarket_high"), 0.0), lp)
        pl_prev = safe_float(met.get("premarket_low"), 0.0)
        pl = min(pl_prev, lp) if pl_prev > 0.0 else lp
        p_amp = ((ph - pl) / pl) * 100.0 if pl > 0.0 else 0.0
        met["premarket_high"] = round(ph, 4)
        met["premarket_low"] = round(pl, 4)
        met["premarket_amp_pct"] = round(p_amp, 2)
        met["premarket_est_high"] = round(max(ph, pl * (1.0 + amp_ratio)), 2)
        met["premarket_est_low"] = round(min(pl, ph / (1.0 + amp_ratio)), 2)
        if safe_float(met.get("premarket_vwap"), 0.0) <= 0.0:
            met["premarket_vwap"] = round(lp, 4) if hm == 407 else 0.0""",
)


# ===========================================================================
# [05. quant_engine.py 패치 등록]
# ===========================================================================
register_patch(
    patch_id="P05_A_VACANT_L1_MANUAL_BUY_NO_PROMOTE",
    filename="quant_engine.py",
    description="Case 63/71/73 1층 공석 중 2층 단가 초과 수동 매수 시 기존 2층의 1층 강제 승격 차단",
    old_block="""    if not has_active_l1_bucket(existing) and tag in (
        "REENTRY_1FL",
        "TOPUP_1FL",
    ):
        preserved_uppers = relabel_upper_grid_tiers(
            existing, max_tiers=eff_max_tiers, merge_mode=eff_merge_mode
        )
        return [new_l1] + preserved_uppers""",
    new_block="""    if not has_active_l1_bucket(existing):
        if tag in ("REENTRY_1FL", "TOPUP_1FL") or (
            pure_p <= existing[0].book_price + 1e-6
        ):
            preserved_uppers = relabel_upper_grid_tiers(
                existing, max_tiers=eff_max_tiers, merge_mode=eff_merge_mode
            )
            return [new_l1] + preserved_uppers
        combined_uppers = list(existing) + [new_l1]
        combined_uppers.sort(key=lambda b: round(b.book_price, 4))
        return relabel_upper_grid_tiers(
            combined_uppers,
            max_tiers=eff_max_tiers,
            merge_mode=eff_merge_mode,
        )""",
)

register_patch(
    patch_id="P05_B_BARBELL_MARK_EQUITY_AND_GRAD_PROJ",
    filename="quant_engine.py",
    description="Case 74/89/94 바벨 전환 시 기확정 비격리 수익 평가자산 항등 일치 및 동반졸업 단가 정밀화",
    old_block="""    if is_barbell:
        soxl_mark_net = (free_cash + market_eval_usd) - injected_reserve_usd
        gross_mark_equity_usd = round(
            free_cash + market_eval_usd + barbell_non_soxl_seed_usd + vaulted_profit_locked_usd,
            4,
        )
        total_mark_equity_usd = round(
            max(
                0.0,
                soxl_mark_net
                + barbell_non_soxl_seed_usd
                + vaulted_profit_locked_usd,
            ),
            4,
        )
    else:
        gross_mark_equity_usd = round(
            free_cash + market_eval_usd + vaulted_profit_locked_usd, 4
        )
        total_mark_equity_usd = round(
            max(0.0, gross_mark_equity_usd - injected_reserve_usd), 4
        )
    total_net_pnl_usd = round(cum_realized + unrealized_pnl_usd, 4)
    total_roi_pct = round((total_net_pnl_usd / init_seed) * 100.0, 2)

    (
        allocation_gauge_bar,
        main_alloc_pct,
        sub_alloc_pct,
        stock_alloc_pct,
        cash_alloc_pct,
    ) = _build_10block_allocation_gauge(
        main_cost=actual_invested_buckets,
        sub_cost=actual_invested_sub,
        free_cash=free_cash,
    )

    proj_main_l1_net = 0.0
    if active_l1 and buckets and l1_target_price > 0.0:
        proj_main_l1_net = calc_sell_realized_pnl(
            sold_qty=buckets[0].qty,
            sell_exec_price=l1_target_price,
            sold_actual_cost_usd=buckets[0].actual_cost_usd,
            round_trip_fee_rate_pct=eff_rt_fee_pct,
        )["net_pnl_usd"]

    proj_main_upper_net = 0.0
    if upper_qty > 0 and upper_wma_target_price > 0.0:
        proj_main_upper_net = calc_sell_realized_pnl(
            sold_qty=upper_qty,
            sell_exec_price=upper_wma_target_price,
            sold_actual_cost_usd=upper_actual_cost_usd,
            round_trip_fee_rate_pct=eff_rt_fee_pct,
        )["net_pnl_usd"]

    proj_sub_l1_net = 0.0
    if sub_active_l1 and sub_buckets and sub_l1_target_price > 0.0:
        proj_sub_l1_net = calc_sell_realized_pnl(
            sold_qty=sub_buckets[0].qty,
            sell_exec_price=sub_l1_target_price,
            sold_actual_cost_usd=sub_buckets[0].actual_cost_usd,
            round_trip_fee_rate_pct=eff_rt_fee_pct,
        )["net_pnl_usd"]""",
    new_block="""    if is_barbell:
        soxl_mark_net = (free_cash + market_eval_usd) - injected_reserve_usd
        cyc_loss_ref = min(
            0.0, safe_float(st.get("cycle_realized_net_usd"), 0.0)
        )
        prior_unvaulted_adj = (
            cum_realized - vaulted_profit_locked_usd
        ) - cyc_loss_ref
        gross_mark_equity_usd = round(
            free_cash
            + market_eval_usd
            + barbell_non_soxl_seed_usd
            + vaulted_profit_locked_usd
            + prior_unvaulted_adj,
            4,
        )
        total_mark_equity_usd = round(
            max(
                0.0,
                soxl_mark_net
                + barbell_non_soxl_seed_usd
                + vaulted_profit_locked_usd
                + prior_unvaulted_adj,
            ),
            4,
        )
    else:
        gross_mark_equity_usd = round(
            free_cash + market_eval_usd + vaulted_profit_locked_usd, 4
        )
        total_mark_equity_usd = round(
            max(0.0, gross_mark_equity_usd - injected_reserve_usd), 4
        )
    total_net_pnl_usd = round(cum_realized + unrealized_pnl_usd, 4)
    total_roi_pct = round((total_net_pnl_usd / init_seed) * 100.0, 2)

    (
        allocation_gauge_bar,
        main_alloc_pct,
        sub_alloc_pct,
        stock_alloc_pct,
        cash_alloc_pct,
    ) = _build_10block_allocation_gauge(
        main_cost=actual_invested_buckets,
        sub_cost=actual_invested_sub,
        free_cash=free_cash,
    )

    proj_main_l1_net = 0.0
    if active_l1 and buckets and l1_target_price > 0.0:
        eff_main_l1_grad_p = (
            min(l1_target_price, upper_wma_target_price)
            if (upper_qty > 0 and upper_wma_target_price > 0.0)
            else l1_target_price
        )
        proj_main_l1_net = calc_sell_realized_pnl(
            sold_qty=buckets[0].qty,
            sell_exec_price=eff_main_l1_grad_p,
            sold_actual_cost_usd=buckets[0].actual_cost_usd,
            round_trip_fee_rate_pct=eff_rt_fee_pct,
        )["net_pnl_usd"]

    proj_main_upper_net = 0.0
    if upper_qty > 0 and upper_wma_target_price > 0.0:
        proj_main_upper_net = calc_sell_realized_pnl(
            sold_qty=upper_qty,
            sell_exec_price=upper_wma_target_price,
            sold_actual_cost_usd=upper_actual_cost_usd,
            round_trip_fee_rate_pct=eff_rt_fee_pct,
        )["net_pnl_usd"]

    proj_sub_l1_net = 0.0
    if sub_active_l1 and sub_buckets and sub_l1_target_price > 0.0:
        eff_sub_l1_grad_p = (
            min(sub_l1_target_price, sub_upper_wma_target_price)
            if (sub_upper_qty > 0 and sub_upper_wma_target_price > 0.0)
            else sub_l1_target_price
        )
        proj_sub_l1_net = calc_sell_realized_pnl(
            sold_qty=sub_buckets[0].qty,
            sell_exec_price=eff_sub_l1_grad_p,
            sold_actual_cost_usd=sub_buckets[0].actual_cost_usd,
            round_trip_fee_rate_pct=eff_rt_fee_pct,
        )["net_pnl_usd"]""",
)


# ===========================================================================
# [06. sniper_plugin_core.py 패치 등록]
# ===========================================================================
register_patch(
    patch_id="P06_A_RSI_PREWARM_400_AND_1D",
    filename="sniper_plugin_core.py",
    description="Case 92/93 RSI(14) 온디맨드 프리워밍 시 400분봉+10일봉 조회로 중도 100봉 앵커 오염 차단",
    old_block="""    if (
        not isinstance(base_met, dict)
        or safe_float(base_met.get("prev_bar_close"), 0.0) <= 0.0
    ):
        api_obj = getattr(context, "api", None)
        if api_obj is not None and hasattr(api_obj, "get_candles_1m"):
            try:
                c_1m = await api_obj.get_candles_1m(
                    symbol=TARGET_SYMBOL, total_count=100
                )
                if c_1m:
                    base_met = compute_soxl_quant_metrics_1m(
                        candles=c_1m,
                        live_price=lp,
                        now_est=dt_now,
                    )
            except Exception as exc:
                logger.debug("RSI(14) 온디맨드 1분봉 프리워밍 폴백: %s", exc)""",
    new_block="""    last_warm_m = safe_float(getattr(context, "_last_rsi_warm_mono", 0.0), 0.0)
    if (
        not isinstance(base_met, dict)
        or not bool(base_met.get("rsi_ready", False))
        or safe_float(base_met.get("prev_bar_close"), 0.0) <= 0.0
    ) and (time.monotonic() - last_warm_m) >= 10.0:
        if context is not None:
            setattr(context, "_last_rsi_warm_mono", time.monotonic())
        api_obj = getattr(context, "api", None)
        if api_obj is not None and hasattr(api_obj, "get_candles_1m"):
            try:
                c_1m = await api_obj.get_candles_1m(
                    symbol=TARGET_SYMBOL, total_count=400
                )
                c_1d = (
                    await api_obj.get_candles_1d(
                        symbol=TARGET_SYMBOL, count=10
                    )
                    if hasattr(api_obj, "get_candles_1d")
                    else []
                )
                if c_1m or c_1d:
                    base_met = await asyncio.to_thread(
                        compute_soxl_quant_metrics_1m,
                        c_1m or [],
                        lp,
                        dt_now,
                        c_1d or [],
                    )
            except Exception as exc:
                logger.debug("RSI(14) 온디맨드 400봉 프리워밍 폴백: %s", exc)""",
)

register_patch(
    patch_id="P06_B_SYNC_BUY_CANCEL_VERIFY_TERMINAL",
    filename="sniper_plugin_core.py",
    description="Case 19/66/78 미결 매수 취소 시 브로커 종료 상태 확인 후에만 buy_order_id 소거 및 1층 목표정량 보존",
    old_block="""    cur_target_q = max(0, safe_int(st.get("l1_target_quota_qty"), 0))
    fallback_target_q_on_zero_cancel = (
        max(buckets_now[0].qty, cur_target_q)
        if ((lot_type == "TOPUP_1FL" or is_sub_lot) and has_active_l1_now)
        else (buckets_now[0].qty if has_active_l1_now else 0)
    )

    sub_buckets_now = buckets_from_dicts(st.get("sub_buckets", []))
    has_sub_active_l1_now = has_active_l1_bucket(sub_buckets_now)
    is_sub_vacant_l1_now = bool(
        len(sub_buckets_now) > 0 and not has_sub_active_l1_now
    )
    cur_sub_target_q = max(0, safe_int(st.get("sub_l1_target_quota_qty"), 0))
    fallback_sub_target_q_on_zero_cancel = (
        max(sub_buckets_now[0].qty, cur_sub_target_q)
        if (
            (lot_type == "SUB_TOPUP_1FL" or not is_sub_lot)
            and has_sub_active_l1_now
        )
        else (sub_buckets_now[0].qty if has_sub_active_l1_now else 0)
    )""",
    new_block="""    cur_target_q = max(0, safe_int(st.get("l1_target_quota_qty"), 0))
    fallback_target_q_on_zero_cancel = (
        max(buckets_now[0].qty, cur_target_q) if has_active_l1_now else 0
    )

    sub_buckets_now = buckets_from_dicts(st.get("sub_buckets", []))
    has_sub_active_l1_now = has_active_l1_bucket(sub_buckets_now)
    is_sub_vacant_l1_now = bool(
        len(sub_buckets_now) > 0 and not has_sub_active_l1_now
    )
    cur_sub_target_q = max(0, safe_int(st.get("sub_l1_target_quota_qty"), 0))
    fallback_sub_target_q_on_zero_cancel = (
        max(sub_buckets_now[0].qty, cur_sub_target_q)
        if has_sub_active_l1_now
        else 0
    )""",
)

register_patch(
    patch_id="P06_C_SYNC_BUY_TIMEOUT_SAFE_CLEAR",
    filename="sniper_plugin_core.py",
    description="Case 66 부분 체결 취소 및 60초 타임아웃 취소 시 PENDING_CANCEL/None 상태 조기 소거 원천 차단",
    old_block="""                try:
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
                if filled_q > 0:
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
            else:
                return {
                    "status": "BUY_PARTIAL_FILLED_WAITING",
                    "filled_qty": filled_q,
                    "ordered_qty": ordered_qty,
                }

        if ord_status in ("CANCELED", "REJECTED") and filled_q == 0:
            re_epoch = (
                mark_reentry_monitor_60s_cycle_shield(
                    context=context, symbol=TARGET_SYMBOL, eval_price=ord_price
                )
                if (is_vacant_l1_now and not is_sub_lot)
                else safe_float(st.get("last_reentry_eval_ts"), 0.0)
            )
            sub_re_epoch = (
                mark_sub_reentry_monitor_60s_cycle_shield(
                    context=context, symbol=TARGET_SYMBOL, eval_price=ord_price
                )
                if (is_sub_vacant_l1_now and is_sub_lot)
                else safe_float(st.get("last_sub_reentry_eval_ts"), 0.0)
            )
            clear_kw: Dict[str, Any] = {
                "l1_target_quota_qty": fallback_target_q_on_zero_cancel,
                "sub_l1_target_quota_qty": fallback_sub_target_q_on_zero_cancel,
                "buy_order_id": "",
                "ordered_qty": 0,
                "buy_price": 0.0,
                "pending_portion_budget": 0.0,
                "pending_lot_type": "",
                "pending_step_up_min_price": 0.0,
                "pending_sub_step_up_min_price": 0.0,
                "last_reentry_eval_ts": re_epoch,
                "last_sub_reentry_eval_ts": sub_re_epoch,
            }
            await context.ledger.update_state(TARGET_SYMBOL, **clear_kw)
            return {"status": f"BUY_ORDER_{ord_status}_CLEARED"}

    if (
        elapsed_mod >= BUY_ORDER_MAX_WAIT_SEC
        or force_settle
        or should_abort_late_cutoff
    ):
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
                )""",
    new_block="""                try:
                    await context.api.cancel_order(buy_oid)
                except Exception:
                    pass
                final_det = await context.api.get_order_detail(buy_oid)
                f_st2 = (
                    str(final_det.get("status") or "").upper().strip()
                    if isinstance(final_det, dict)
                    else ""
                )
                if not isinstance(final_det, dict) or f_st2 in (
                    "PENDING",
                    "PARTIAL_FILLED",
                    "PENDING_CANCEL",
                    "PENDING_REPLACE",
                ):
                    await asyncio.sleep(0.35)
                    final_det = await context.api.get_order_detail(buy_oid)
                    f_st2 = (
                        str(final_det.get("status") or "").upper().strip()
                        if isinstance(final_det, dict)
                        else ""
                    )
                if not isinstance(final_det, dict) or f_st2 in (
                    "PENDING",
                    "PARTIAL_FILLED",
                    "PENDING_CANCEL",
                    "PENDING_REPLACE",
                ):
                    return {
                        "status": "BUY_PARTIAL_CANCEL_CONFIRMING",
                        "orderId": buy_oid,
                        "filled_qty": filled_q,
                    }
                f_ex = (
                    final_det.get("execution")
                    if isinstance(final_det.get("execution"), dict)
                    else {}
                )
                f_q2 = safe_int(f_ex.get("filledQuantity"), filled_q)
                f_p2 = safe_float(f_ex.get("averageFilledPrice"), avg_fill_p)
                if f_q2 > 0:
                    filled_q = f_q2
                if f_p2 > 0.0:
                    avg_fill_p = f_p2
                if filled_q > 0:
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
            else:
                return {
                    "status": "BUY_PARTIAL_FILLED_WAITING",
                    "filled_qty": filled_q,
                    "ordered_qty": ordered_qty,
                }

        if ord_status in ("CANCELED", "REJECTED", "REPLACED") and filled_q == 0:
            re_epoch = (
                mark_reentry_monitor_60s_cycle_shield(
                    context=context, symbol=TARGET_SYMBOL, eval_price=ord_price
                )
                if (is_vacant_l1_now and not is_sub_lot)
                else safe_float(st.get("last_reentry_eval_ts"), 0.0)
            )
            sub_re_epoch = (
                mark_sub_reentry_monitor_60s_cycle_shield(
                    context=context, symbol=TARGET_SYMBOL, eval_price=ord_price
                )
                if (is_sub_vacant_l1_now and is_sub_lot)
                else safe_float(st.get("last_sub_reentry_eval_ts"), 0.0)
            )
            clear_kw: Dict[str, Any] = {
                "l1_target_quota_qty": fallback_target_q_on_zero_cancel,
                "sub_l1_target_quota_qty": fallback_sub_target_q_on_zero_cancel,
                "buy_order_id": "",
                "ordered_qty": 0,
                "buy_price": 0.0,
                "pending_portion_budget": 0.0,
                "pending_lot_type": "",
                "pending_step_up_min_price": 0.0,
                "pending_sub_step_up_min_price": 0.0,
                "last_reentry_eval_ts": re_epoch,
                "last_sub_reentry_eval_ts": sub_re_epoch,
            }
            await context.ledger.update_state(TARGET_SYMBOL, **clear_kw)
            return {"status": f"BUY_ORDER_{ord_status}_CLEARED"}

    if (
        elapsed_mod >= BUY_ORDER_MAX_WAIT_SEC
        or force_settle
        or should_abort_late_cutoff
    ):
        try:
            await context.api.cancel_order(buy_oid)
        except Exception:
            pass

        final_detail = await context.api.get_order_detail(buy_oid)
        f_status = (
            str(final_detail.get("status") or "").upper().strip()
            if isinstance(final_detail, dict)
            else ""
        )
        if not isinstance(final_detail, dict) or f_status in (
            "PENDING",
            "PARTIAL_FILLED",
            "PENDING_CANCEL",
            "PENDING_REPLACE",
        ):
            await asyncio.sleep(0.35)
            final_detail = await context.api.get_order_detail(buy_oid)
            f_status = (
                str(final_detail.get("status") or "").upper().strip()
                if isinstance(final_detail, dict)
                else ""
            )

        if not isinstance(final_detail, dict) and elapsed_mod >= (
            BUY_ORDER_MAX_WAIT_SEC + 15.0
        ):
            closed_cands = await context.api.get_closed_orders(
                symbol=TARGET_SYMBOL, limit=25
            )
            for c_item in closed_cands:
                if str(c_item.get("orderId") or "").strip() == buy_oid:
                    final_detail = c_item
                    f_status = (
                        str(c_item.get("status") or "").upper().strip()
                    )
                    break

        if isinstance(final_detail, dict):
            if f_status in (
                "PENDING",
                "PARTIAL_FILLED",
                "PENDING_CANCEL",
                "PENDING_REPLACE",
            ):
                return {
                    "status": "BUY_CANCEL_IN_FLIGHT",
                    "orderId": buy_oid,
                }
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
        elif elapsed_mod < (BUY_ORDER_MAX_WAIT_SEC + 30.0):
            return {
                "status": "BUY_CANCEL_VERIFY_RETRY",
                "orderId": buy_oid,
            }""",
)


# ===========================================================================
# [07. sniper_plugin.py 패치 등록]
# ===========================================================================
register_patch(
    patch_id="P07_A_MASKED_BP_HELPER",
    filename="sniper_plugin.py",
    description="Case 77/94 서브그리드 및 TOPUP_1FL 전용 바벨 보호버킷/별도수익금고 마스킹 헬퍼 장착",
    old_block="""from toss_api import (
    DEFAULT_INITIAL_SEED_USD,
    EST_TZ,
    LOCKED_BUY_INTERVAL_MIN,
    TARGET_SYMBOL,
    generate_client_order_id,
    safe_float,
    safe_int,
)

logger = logging.getLogger("toss_sniper.sniper_plugin")""",
    new_block="""from barbell_plugin import (
    get_masked_soxl_buying_power_usd,
    is_barbell_mode,
)
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


def _resolve_masked_bp_for_soxl_sub_or_topup(
    context: Any,
    st_soxl: Dict[str, Any],
    raw_bp_usd: float,
) -> float:
    raw_bp = max(0.0, safe_float(raw_bp_usd, 0.0))
    if raw_bp <= 0.0:
        return 0.0
    if is_barbell_mode(st_soxl.get("portion_mode")):
        return get_masked_soxl_buying_power_usd(
            context=context, raw_bp_usd=raw_bp, st_soxl=st_soxl
        )
    vault_locked = max(
        0.0, safe_float(st_soxl.get("vaulted_profit_locked_usd"), 0.0)
    )
    return round(max(0.0, raw_bp - vault_locked), 4)""",
)

register_patch(
    patch_id="P07_B1_SUB_SA_MASK_AND_TRANSIENT_BP",
    filename="sniper_plugin.py",
    description="서브 0주(S-A) 예수금 마스킹 적용 및 예수금 API 일시 0.0 오류 시 60초 오잠금 차단",
    old_block="""                raw_bp_sub = await context.api.get_buying_power_usd(
                    safety_buffer_pct=0.2
                )
                if raw_bp_sub <= 0.0 and now_free_cash >= (
                    exec_order_p * fee_mult_m
                ):
                    await asyncio.sleep(0.25)
                    raw_bp_sub = await context.api.get_buying_power_usd(
                        safety_buffer_pct=0.2
                    )

                idle_m = compute_sub_grid_available_idle_cash(
                    free_cash_usd=now_free_cash,
                    core_equity_usd=now_core_eq,
                    broker_buying_power_usd=(
                        raw_bp_sub if raw_bp_sub > 0.0 else 0.0
                    ),""",
    new_block="""                raw_bp_sub = await context.api.get_buying_power_usd(
                    safety_buffer_pct=0.2
                )
                if raw_bp_sub <= 0.0 and now_free_cash >= (
                    exec_order_p * fee_mult_m
                ):
                    await asyncio.sleep(0.25)
                    raw_bp_sub = await context.api.get_buying_power_usd(
                        safety_buffer_pct=0.2
                    )
                    if raw_bp_sub <= 0.0:
                        return {"status": "HOLD_SUB_TRANSIENT_BP_API_ERROR"}

                masked_bp_sub = _resolve_masked_bp_for_soxl_sub_or_topup(
                    context, st_now, raw_bp_sub
                )
                idle_m = compute_sub_grid_available_idle_cash(
                    free_cash_usd=now_free_cash,
                    core_equity_usd=now_core_eq,
                    broker_buying_power_usd=masked_bp_sub,""",
)

register_patch(
    patch_id="P07_B2_SUB_SB1_MASK_AND_TRANSIENT_BP",
    filename="sniper_plugin.py",
    description="서브 1층 공석(S-B1) 예수금 마스킹 적용 및 일시 예수금 오류 방어",
    old_block="""                raw_bp_re = await context.api.get_buying_power_usd(
                    safety_buffer_pct=0.2
                )
                if raw_bp_re <= 0.0 and now_free_cash >= (
                    exec_order_p * fee_mult_re
                ):
                    await asyncio.sleep(0.25)
                    raw_bp_re = await context.api.get_buying_power_usd(
                        safety_buffer_pct=0.2
                    )

                idle_re = compute_sub_grid_available_idle_cash(
                    free_cash_usd=now_free_cash,
                    core_equity_usd=now_core_eq,
                    broker_buying_power_usd=(
                        raw_bp_re if raw_bp_re > 0.0 else 0.0
                    ),""",
    new_block="""                raw_bp_re = await context.api.get_buying_power_usd(
                    safety_buffer_pct=0.2
                )
                if raw_bp_re <= 0.0 and now_free_cash >= (
                    exec_order_p * fee_mult_re
                ):
                    await asyncio.sleep(0.25)
                    raw_bp_re = await context.api.get_buying_power_usd(
                        safety_buffer_pct=0.2
                    )
                    if raw_bp_re <= 0.0:
                        return {"status": "HOLD_SUB_TRANSIENT_BP_API_ERROR"}

                masked_bp_re = _resolve_masked_bp_for_soxl_sub_or_topup(
                    context, st_now, raw_bp_re
                )
                idle_re = compute_sub_grid_available_idle_cash(
                    free_cash_usd=now_free_cash,
                    core_equity_usd=now_core_eq,
                    broker_buying_power_usd=masked_bp_re,""",
)

register_patch(
    patch_id="P07_B3_SUB_SB0_MASK_AND_TRANSIENT_BP",
    filename="sniper_plugin.py",
    description="서브 1층 잔량보충(S-B0) 예수금 마스킹 적용 및 일시 예수금 오류 방어",
    old_block="""                            raw_bp_top = await context.api.get_buying_power_usd(
                                safety_buffer_pct=0.2
                            )
                            if raw_bp_top <= 0.0 and now_free_cash >= (
                                exec_order_p * fee_mult_top
                            ):
                                await asyncio.sleep(0.25)
                                raw_bp_top = (
                                    await context.api.get_buying_power_usd(
                                        safety_buffer_pct=0.2
                                    )
                                )
                            idle_top = compute_sub_grid_available_idle_cash(
                                free_cash_usd=now_free_cash,
                                core_equity_usd=now_core_eq,
                                broker_buying_power_usd=(
                                    raw_bp_top if raw_bp_top > 0.0 else 0.0
                                ),""",
    new_block="""                            raw_bp_top = await context.api.get_buying_power_usd(
                                safety_buffer_pct=0.2
                            )
                            if raw_bp_top <= 0.0 and now_free_cash >= (
                                exec_order_p * fee_mult_top
                            ):
                                await asyncio.sleep(0.25)
                                raw_bp_top = (
                                    await context.api.get_buying_power_usd(
                                        safety_buffer_pct=0.2
                                    )
                                )
                                if raw_bp_top <= 0.0:
                                    return {
                                        "status": "HOLD_SUB_TRANSIENT_BP_API_ERROR"
                                    }
                            masked_bp_top = (
                                _resolve_masked_bp_for_soxl_sub_or_topup(
                                    context, st_now, raw_bp_top
                                )
                            )
                            idle_top = compute_sub_grid_available_idle_cash(
                                free_cash_usd=now_free_cash,
                                core_equity_usd=now_core_eq,
                                broker_buying_power_usd=masked_bp_top,""",
)

register_patch(
    patch_id="P07_B4_SUB_SB2_MASK_AND_KEEP_QUOTA",
    filename="sniper_plugin.py",
    description="서브 10분 게이트(S-B2) 예수금 마스킹·일시오류 시 버킷보존·미체결 시 기존 잔량목표 보존",
    old_block="""            raw_bp_dip = await context.api.get_buying_power_usd(
                safety_buffer_pct=0.2
            )
            if raw_bp_dip <= 0.0 and now_free_cash >= (
                exec_order_p * fee_mult_dip
            ):
                await asyncio.sleep(0.25)
                raw_bp_dip = await context.api.get_buying_power_usd(
                    safety_buffer_pct=0.2
                )

            idle_dip = compute_sub_grid_available_idle_cash(
                free_cash_usd=now_free_cash,
                core_equity_usd=now_core_eq,
                broker_buying_power_usd=(
                    raw_bp_dip if raw_bp_dip > 0.0 else 0.0
                ),""",
    new_block="""            raw_bp_dip = await context.api.get_buying_power_usd(
                safety_buffer_pct=0.2
            )
            if raw_bp_dip <= 0.0 and now_free_cash >= (
                exec_order_p * fee_mult_dip
            ):
                await asyncio.sleep(0.25)
                raw_bp_dip = await context.api.get_buying_power_usd(
                    safety_buffer_pct=0.2
                )
                if raw_bp_dip <= 0.0:
                    return {"status": "HOLD_SUB_TRANSIENT_BP_API_ERROR"}

            masked_bp_dip = _resolve_masked_bp_for_soxl_sub_or_topup(
                context, st_now, raw_bp_dip
            )
            idle_dip = compute_sub_grid_available_idle_cash(
                free_cash_usd=now_free_cash,
                core_equity_usd=now_core_eq,
                broker_buying_power_usd=masked_bp_dip,""",
)

register_patch(
    patch_id="P07_B5_SUB_DIP_KEEP_TARGET_UNTIL_FILL",
    filename="sniper_plugin.py",
    description="Case 78/88 서브 추매 발주 시 체결 전까지 기존 서브 1층 잔량 목표 보존",
    old_block="""            oid = str(ord_res.get("orderId") or "").strip()
            await context.ledger.update_state(
                TARGET_SYMBOL,
                sub_l1_target_quota_qty=buy_qty_sub,
                buy_order_id=oid,
                client_order_id=cid,
                ordered_qty=buy_qty_sub,
                buy_price=exec_order_p,
                pending_portion_budget=sub_p_bud,
                pending_lot_type="SUB_DIP_1FL",""",
    new_block="""            oid = str(ord_res.get("orderId") or "").strip()
            await context.ledger.update_state(
                TARGET_SYMBOL,
                buy_order_id=oid,
                client_order_id=cid,
                ordered_qty=buy_qty_sub,
                buy_price=exec_order_p,
                pending_portion_budget=sub_p_bud,
                pending_lot_type="SUB_DIP_1FL",""",
)

register_patch(
    patch_id="P07_C1_MAIN_TOPUP_MASK_AND_TRANSIENT_BP",
    filename="sniper_plugin.py",
    description="Case 77/78/94 본그리드 잔량보충(TOPUP_1FL) 예수금 마스킹 및 일시 예수금 오류 방어",
    old_block="""                        raw_bp_top = await context.api.get_buying_power_usd(
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
                            broker_buying_power_usd=raw_bp_top,""",
    new_block="""                        raw_bp_top = await context.api.get_buying_power_usd(
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
                            if raw_bp_top <= 0.0:
                                return {
                                    "status": "HOLD_TOPUP_TRANSIENT_BP_ERROR"
                                }

                        masked_bp_main_top = (
                            _resolve_masked_bp_for_soxl_sub_or_topup(
                                context, st_now, raw_bp_top
                            )
                        )
                        if masked_bp_main_top < one_share_top_cost:
                            mark_reserve_deposit_check_shield(
                                context=context,
                                symbol=TARGET_SYMBOL,
                                clear_shield=False,
                            )
                            return {
                                "status": "HOLD_TOPUP_INSUFFICIENT_BROKER_BP",
                                "broker_bp_usd": masked_bp_main_top,
                                "free_cash_usd": now_free_cash,
                            }

                        buy_qty_top, _ = resolve_affordable_buy_qty(
                            target_qty=now_rem_qty,
                            price_t=exec_order_p,
                            free_cash_usd=now_free_cash,
                            broker_buying_power_usd=masked_bp_main_top,""",
)

register_patch(
    patch_id="P07_C2_MAIN_DIP_KEEP_TARGET_UNTIL_FILL",
    filename="sniper_plugin.py",
    description="Case 78 본그리드 추매(DIP_1FL) 발주 시 체결 전까지 기존 1층 잔량 목표 정량 보존",
    old_block="""            oid = str(ord_res.get("orderId") or "").strip()
            await context.ledger.update_state(
                TARGET_SYMBOL,
                l1_target_quota_qty=buy_qty,
                buy_order_id=oid,
                client_order_id=cid,
                ordered_qty=buy_qty,
                buy_price=exec_order_p,
                pending_portion_budget=portion_budget,
                pending_lot_type=lot_tag,""",
    new_block="""            oid = str(ord_res.get("orderId") or "").strip()
            await context.ledger.update_state(
                TARGET_SYMBOL,
                buy_order_id=oid,
                client_order_id=cid,
                ordered_qty=buy_qty,
                buy_price=exec_order_p,
                pending_portion_budget=portion_budget,
                pending_lot_type=lot_tag,""",
)

_LOADED_PARTS.append(3)

# ===========================================================================
# [08. sniper_exit_plugin.py 패치 등록]
# ===========================================================================
register_patch(
    patch_id="P08_A_SUB_ZERO_GRAD_ALERT",
    filename="sniper_exit_plugin.py",
    description="본 그리드 0주 상태에서 서브 단독 익절로 전체 0주 졸업 시 졸업/리밸런싱/암살자인계 알림 정상 표출",
    old_block=r'''        if is_sub_without_main_sell:
            grid_sh = sum(b.qty for b in rem_buckets)
            sub_sh = sum(sb.qty for sb in rem_sub_buckets)''',
    new_block=r'''        if is_sub_without_main_sell and not is_graduated_zero:
            grid_sh = sum(b.qty for b in rem_buckets)
            sub_sh = sum(sb.qty for sb in rem_sub_buckets)''',
)

register_patch(
    patch_id="P08_B_SYNC_SELL_SAFE_CANCEL",
    filename="sniper_exit_plugin.py",
    description="Case 19/66 매도 60초 타임아웃 취소 시 브로커 종료 상태 확인 후에만 sell_order_id 소거",
    old_block=r'''                try:
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
                )''',
    new_block=r'''                try:
                    await context.api.cancel_order(sell_oid)
                except Exception:
                    pass
                final_det = await context.api.get_order_detail(sell_oid)
                f_st2 = (
                    str(final_det.get("status") or "").upper().strip()
                    if isinstance(final_det, dict)
                    else ""
                )
                if not isinstance(final_det, dict) or f_st2 in (
                    "PENDING",
                    "PARTIAL_FILLED",
                    "PENDING_CANCEL",
                    "PENDING_REPLACE",
                ):
                    await asyncio.sleep(0.35)
                    final_det = await context.api.get_order_detail(sell_oid)
                    f_st2 = (
                        str(final_det.get("status") or "").upper().strip()
                        if isinstance(final_det, dict)
                        else ""
                    )
                if not isinstance(final_det, dict) or f_st2 in (
                    "PENDING",
                    "PARTIAL_FILLED",
                    "PENDING_CANCEL",
                    "PENDING_REPLACE",
                ):
                    return {
                        "status": "SELL_PARTIAL_CANCEL_CONFIRMING",
                        "did_sell_or_ratchet": True,
                        "orderId": sell_oid,
                    }
                f_ex = (
                    final_det.get("execution")
                    if isinstance(final_det.get("execution"), dict)
                    else {}
                )
                f_q2 = safe_int(f_ex.get("filledQuantity"), filled_q)
                f_p2 = safe_float(f_ex.get("averageFilledPrice"), avg_fill_p)
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

        if (
            ord_status in ("CANCELED", "REJECTED", "REPLACED")
            and filled_q == 0
        ):
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
        f_status = (
            str(final_detail.get("status") or "").upper().strip()
            if isinstance(final_detail, dict)
            else ""
        )
        if not isinstance(final_detail, dict) or f_status in (
            "PENDING",
            "PARTIAL_FILLED",
            "PENDING_CANCEL",
            "PENDING_REPLACE",
        ):
            await asyncio.sleep(0.35)
            final_detail = await context.api.get_order_detail(sell_oid)
            f_status = (
                str(final_detail.get("status") or "").upper().strip()
                if isinstance(final_detail, dict)
                else ""
            )

        if not isinstance(final_detail, dict) and elapsed_mod >= (
            SELL_ORDER_MAX_WAIT_SEC + 15.0
        ):
            closed_cands = await context.api.get_closed_orders(
                symbol=TARGET_SYMBOL, limit=25
            )
            for c_item in closed_cands:
                if str(c_item.get("orderId") or "").strip() == sell_oid:
                    final_detail = c_item
                    f_status = (
                        str(c_item.get("status") or "").upper().strip()
                    )
                    break

        if isinstance(final_detail, dict):
            if f_status in (
                "PENDING",
                "PARTIAL_FILLED",
                "PENDING_CANCEL",
                "PENDING_REPLACE",
            ):
                return {
                    "status": "SELL_CANCEL_IN_FLIGHT",
                    "did_sell_or_ratchet": True,
                    "orderId": sell_oid,
                }
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
        elif elapsed_mod < (SELL_ORDER_MAX_WAIT_SEC + 30.0):
            return {
                "status": "SELL_CANCEL_VERIFY_RETRY",
                "did_sell_or_ratchet": True,
                "orderId": sell_oid,
            }''',
)


# ===========================================================================
# [09. defense_plugin.py 패치 등록]
# ===========================================================================
register_patch(
    patch_id="P09_A1_VAULT_BUCKET_RECOVERY_GUARD",
    filename="defense_plugin.py",
    description="Case 69 0주 정상 졸업 이력이 있는 원장에 과거 백업 스냅샷 지층이 역류 복원되는 현상 차단",
    old_block=r'''            if vault_qty == h_qty and (
                len(vault_buckets) > 0 or len(vault_sub_buckets) > 0
            ):''',
    new_block=r'''            is_fresh_empty_ledger = bool(
                safe_int(st.get("total_buy_events"), 0) == 0
                and safe_int(st.get("total_sell_events"), 0) == 0
                and safe_int(st.get("completed_main_cycles"), 0) == 0
                and safe_float(st.get("last_cycle_end_ts"), 0.0) <= 0.0
            )
            vault_not_older = bool(
                safe_int(vault_st.get("total_sell_events"), 0)
                >= safe_int(st.get("total_sell_events"), 0)
                and safe_int(vault_st.get("completed_main_cycles"), 0)
                >= safe_int(st.get("completed_main_cycles"), 0)
            )
            if (
                (is_fresh_empty_ledger or vault_not_older)
                and vault_qty == h_qty
                and (len(vault_buckets) > 0 or len(vault_sub_buckets) > 0)
            ):''',
)

register_patch(
    patch_id="P09_A2_VAULT_STAT_NO_PHANTOM_RESERVE",
    filename="defense_plugin.py",
    description="Case 68/69/80 0주 졸업 후 수동 매수 시 과거 백업 스냅샷의 구 수혈금/사이클익 역류(유령현금) 원천 차단",
    old_block=r'''        if isinstance(vault_st, dict):
            for stat_k in (
                "portion_mode",
                "vaulted_profit_locked_usd",
                "us_commission_rate",
                "round_trip_fee_rate_pct",
                "cumulative_realized_net_usd",
                "cumulative_realized_gross_usd",
                "cumulative_realized_fee_usd",
                "cumulative_leftover_saved_usd",
                "cumulative_reanchor_drop_usd",
                "cycle_realized_gross_usd",
                "cycle_realized_fee_usd",
                "cycle_realized_net_usd",
                "cycle_sub_realized_net_usd",
                "cycle_sell_events",
                "cycle_leftover_saved_usd",
                "last_cycle_realized_net_usd",
                "last_cycle_sell_events",
                "completed_main_cycles",
                "reanchor_cnt",
                "indiv_grid_sell_cnt",
                "wma_grad_sell_cnt",
                "seed_protect_pass_cnt",
                "daily_seed_protect_pass_cnt",
                "cond_unlock_buy_events",
                "daily_unlock_buy_events",
                "sub_buy_events",
                "sub_buy_shares",
                "sub_sell_events",
                "sub_sold_shares",
                "sub_merge_events",
                "sub_merged_indiv_escape_cnt",
                "sub_unlock_events",
                "sub_completed_cycles",
                "sub_realized_gross_usd",
                "sub_realized_fee_usd",
                "sub_realized_net_usd",
                "used_reserve_portions_cnt",
                "injected_reserve_usd",
                "total_reserve_injected_cnt",
                "daily_reserve_injected_cnt",
                "cumulative_reserve_repaid_usd",
                "dust_guard_blocked_cnt",
                "daily_dust_guard_blocked_cnt",
                "extra_13plus_buy_events",
                "total_buy_events",
                "total_sell_events",
                "win_sell_events",
            ):
                if stat_k == "portion_mode":
                    if vault_st.get("portion_mode"):
                        update_kw["portion_mode"] = vault_st["portion_mode"]
                elif safe_float(st.get(stat_k), 0.0) == 0.0 and safe_float(
                    vault_st.get(stat_k), 0.0
                ) != 0.0:
                    update_kw[stat_k] = vault_st[stat_k]''',
    new_block=r'''        is_ledger_brand_new = bool(
            safe_int(st.get("total_buy_events"), 0) == 0
            and safe_int(st.get("total_sell_events"), 0) == 0
            and safe_int(st.get("completed_main_cycles"), 0) == 0
            and safe_float(st.get("last_cycle_end_ts"), 0.0) <= 0.0
        )
        if isinstance(vault_st, dict) and is_ledger_brand_new:
            for stat_k in (
                "vaulted_profit_locked_usd",
                "us_commission_rate",
                "round_trip_fee_rate_pct",
                "cumulative_realized_net_usd",
                "cumulative_realized_gross_usd",
                "cumulative_realized_fee_usd",
                "cumulative_leftover_saved_usd",
                "cumulative_reanchor_drop_usd",
                "last_cycle_realized_net_usd",
                "last_cycle_sell_events",
                "completed_main_cycles",
                "reanchor_cnt",
                "indiv_grid_sell_cnt",
                "wma_grad_sell_cnt",
                "seed_protect_pass_cnt",
                "cond_unlock_buy_events",
                "sub_buy_events",
                "sub_buy_shares",
                "sub_sell_events",
                "sub_sold_shares",
                "sub_merge_events",
                "sub_merged_indiv_escape_cnt",
                "sub_unlock_events",
                "sub_completed_cycles",
                "sub_realized_gross_usd",
                "sub_realized_fee_usd",
                "sub_realized_net_usd",
                "total_reserve_injected_cnt",
                "cumulative_reserve_repaid_usd",
                "dust_guard_blocked_cnt",
                "extra_13plus_buy_events",
                "total_buy_events",
                "total_sell_events",
                "win_sell_events",
            ):
                if safe_float(st.get(stat_k), 0.0) == 0.0 and safe_float(
                    vault_st.get(stat_k), 0.0
                ) != 0.0:
                    update_kw[stat_k] = vault_st[stat_k]''',
)

register_patch(
    patch_id="P09_B1_0400_SAFE_ORDER_CLEAR",
    filename="defense_plugin.py",
    description="04:00 EST 오프닝 안정화 시 후정산이 완료된 주문 슬롯만 조건부 해제",
    old_block=r'''    await context.ledger.update_state(
        TARGET_SYMBOL,
        us_commission_rate=us_comm_r,
        round_trip_fee_rate_pct=rt_fee_pct,
        buy_order_id="",
        sell_order_id="",
        ordered_qty=0,
        target_sell_price=0.0,
        pending_sell_mode="",
        pending_sell_indices=[],
        pending_sub_sell_indices=[],
        pending_lot_type="",
        pending_step_up_min_price=0.0,
        pending_sub_step_up_min_price=0.0,''',
    new_block=r'''    st_post_0400 = context.ledger.get_state(TARGET_SYMBOL)
    has_rem_0400_ord = bool(
        str(st_post_0400.get("buy_order_id") or "").strip()
        or str(st_post_0400.get("sell_order_id") or "").strip()
    )
    clear_0400_ord_kw: Dict[str, Any] = (
        {}
        if has_rem_0400_ord
        else {
            "buy_order_id": "",
            "sell_order_id": "",
            "ordered_qty": 0,
            "target_sell_price": 0.0,
            "pending_sell_mode": "",
            "pending_sell_indices": [],
            "pending_sub_sell_indices": [],
            "pending_lot_type": "",
            "pending_step_up_min_price": 0.0,
            "pending_sub_step_up_min_price": 0.0,
        }
    )
    await context.ledger.update_state(
        TARGET_SYMBOL,
        us_commission_rate=us_comm_r,
        round_trip_fee_rate_pct=rt_fee_pct,
        **clear_0400_ord_kw,''',
)

register_patch(
    patch_id="P09_B2_1600_SAFE_ORDER_CLEAR",
    filename="defense_plugin.py",
    description="16:00 EST 마감 결산 시 후정산이 완료된 주문 슬롯만 조건부 해제",
    old_block=r'''    updated_st = await context.ledger.update_state(
        TARGET_SYMBOL,
        main_consec_frozen_days=next_main_frozen,
        sub_consec_frozen_days=next_sub_frozen,
        last_frozen_eval_date=today_str,
        buy_order_id="",
        sell_order_id="",
        ordered_qty=0,
        target_sell_price=0.0,
        pending_sell_mode="",
        pending_sell_indices=[],
        pending_sub_sell_indices=[],
        pending_lot_type="",
        pending_step_up_min_price=0.0,
        pending_sub_step_up_min_price=0.0,
        last_closing_report_date=today_str,
    )''',
    new_block=r'''    has_rem_1600_ord = bool(
        str(st_final.get("buy_order_id") or "").strip()
        or str(st_final.get("sell_order_id") or "").strip()
    )
    clear_1600_ord_kw: Dict[str, Any] = (
        {}
        if has_rem_1600_ord
        else {
            "buy_order_id": "",
            "sell_order_id": "",
            "ordered_qty": 0,
            "target_sell_price": 0.0,
            "pending_sell_mode": "",
            "pending_sell_indices": [],
            "pending_sub_sell_indices": [],
            "pending_lot_type": "",
            "pending_step_up_min_price": 0.0,
            "pending_sub_step_up_min_price": 0.0,
        }
    )
    updated_st = await context.ledger.update_state(
        TARGET_SYMBOL,
        main_consec_frozen_days=next_main_frozen,
        sub_consec_frozen_days=next_sub_frozen,
        last_frozen_eval_date=today_str,
        last_closing_report_date=today_str,
        **clear_1600_ord_kw,
    )''',
)

register_patch(
    patch_id="P09_B3_1700_GC_PRESERVE_DAILY",
    filename="defense_plugin.py",
    description="Case 74 17:00 EST GC 실행 시 당일 카운터 반쪽 소거 제거(애프터/데이장 /sync 일관성 유지)",
    old_block=r'''    await context.ledger.update_state(
        TARGET_SYMBOL,
        daily_seed_protect_pass_cnt=0,
        daily_unlock_buy_events=0,
        daily_sub_buy_cnt=0,
        daily_sub_buy_events=0,
        daily_sub_sell_cnt=0,
        daily_sub_sell_events=0,
        daily_sub_unlock_events=0,
        daily_sub_realized_net_usd=0.0,
        daily_main_buy_cnt=0,
        daily_main_sell_cnt=0,
        daily_reserve_injected_cnt=0,
        daily_dust_guard_blocked_cnt=0,
        pending_step_up_min_price=0.0,
        pending_sub_step_up_min_price=0.0,
        last_evaluated_buy_bucket_id=-1,
        sub_last_evaluated_buy_bucket_id=-1,
        last_reentry_eval_ts=0.0,
        last_sub_reentry_eval_ts=0.0,
    )''',
    new_block=r'''    st_gc = context.ledger.get_state(TARGET_SYMBOL)
    if not str(st_gc.get("buy_order_id") or "").strip():
        await context.ledger.update_state(
            TARGET_SYMBOL,
            pending_step_up_min_price=0.0,
            pending_sub_step_up_min_price=0.0,
            last_evaluated_buy_bucket_id=-1,
            sub_last_evaluated_buy_bucket_id=-1,
            last_reentry_eval_ts=0.0,
            last_sub_reentry_eval_ts=0.0,
        )''',
)


# ===========================================================================
# [10. barbell_plugin.py 패치 등록]
# ===========================================================================
register_patch(
    patch_id="P10_A1_MASKED_BP_AND_CASH10",
    filename="barbell_plugin.py",
    description="Case 94 바벨 평시 매수 별도수익금고 마스킹 무력화(if False 데드코드 포함) 교정 및 1순위 수혈 보호",
    old_block=r'''    raw_bp = max(0.0, safe_float(raw_bp_usd, 0.0))
    masked_bp = get_masked_soxl_buying_power_usd(
        context=context, raw_bp_usd=raw_bp, st_now_override=None, st_soxl=st_now, bst=bst
    ) if False else get_masked_soxl_buying_power_usd(
        context=context, raw_bp_usd=raw_bp, st_soxl=st_now, bst=bst
    )

    # [정상 통과] SOXL 60% 코어 가용현금이 충분한 경우
    if now_free_cash >= min_req_cash and raw_bp >= min_req_cash:
        eff_bp_order = round(
            min(raw_bp, max(now_free_cash, masked_bp)) * 0.998, 4
        )
        return (
            True,
            now_free_cash,
            eff_bp_order,
            {
                "action": "PROCEED_NORMAL",
                "should_proceed": True,
                "min_req_cash": round(min_req_cash, 4),
            },
        )

    shortfall = max(0.0, min_req_cash - now_free_cash)
    needed_portions = max(1, int(math.ceil((shortfall - 1e-9) / unit_8pct)))
    req_unit_usd = round(float(needed_portions) * unit_8pct, 4)

    cash_bucket = max(0.0, safe_float(bst.get("cash_bucket_usd"), 0.0))
    sgov_qty = max(0, safe_int(bst.get("sgov_held_qty"), 0))
    vault_avail = max(0.0, safe_float(bst.get("vault_available_usd"), 0.0))
    pending_sgov_buy = max(
        0.0, safe_float(bst.get("pending_sgov_buy_budget_usd"), 0.0)
    )

    # -----------------------------------------------------------------------
    # [1순위] 현금 10% 대기 버킷에서 1회분(8% = unit_8pct) 단위 즉시 자동수혈
    # -----------------------------------------------------------------------
    usable_from_cash_bucket = min(
        cash_bucket, max(0.0, raw_bp - now_free_cash)
    )''',
    new_block=r'''    raw_bp = max(0.0, safe_float(raw_bp_usd, 0.0))
    vault_avail = max(0.0, safe_float(bst.get("vault_available_usd"), 0.0))
    bp_excl_vault = round(max(0.0, raw_bp - vault_avail), 4)
    masked_bp = get_masked_soxl_buying_power_usd(
        context=context, raw_bp_usd=raw_bp, st_soxl=st_now, bst=bst
    )

    # [정상 통과] SOXL 60% 코어 가용현금 및 별도수익금고 제외 예수금이 충분한 경우
    if now_free_cash >= min_req_cash and bp_excl_vault >= min_req_cash:
        eff_cap_bp = (
            min(now_free_cash, masked_bp)
            if masked_bp >= min_req_cash
            else min(now_free_cash, bp_excl_vault)
        )
        eff_bp_order = round(eff_cap_bp * 0.998, 4)
        return (
            True,
            now_free_cash,
            eff_bp_order,
            {
                "action": "PROCEED_NORMAL",
                "should_proceed": True,
                "min_req_cash": round(min_req_cash, 4),
            },
        )

    shortfall = max(0.0, min_req_cash - now_free_cash)
    needed_portions = max(1, int(math.ceil((shortfall - 1e-9) / unit_8pct)))
    req_unit_usd = round(float(needed_portions) * unit_8pct, 4)

    cash_bucket = max(0.0, safe_float(bst.get("cash_bucket_usd"), 0.0))
    sgov_qty = max(0, safe_int(bst.get("sgov_held_qty"), 0))
    pending_sgov_buy = max(
        0.0, safe_float(bst.get("pending_sgov_buy_budget_usd"), 0.0)
    )

    # -----------------------------------------------------------------------
    # [1순위] 현금 10% 대기 버킷에서 1회분(8% = unit_8pct) 단위 즉시 자동수혈 (수익금고 차감 보호)
    # -----------------------------------------------------------------------
    usable_from_cash_bucket = min(
        cash_bucket, max(0.0, bp_excl_vault - now_free_cash)
    )''',
)

register_patch(
    patch_id="P10_A2_PENDING_SGOV_AUX_CASH",
    filename="barbell_plugin.py",
    description="Case 94 SGOV 기보유 여부와 무관하게 미집행 SGOV 매수예약 현금을 수혈 재원으로 개방(Dead Money 제거)",
    old_block=r'''    if (
        sgov_qty <= 0
        and pending_sgov_buy > 0.0
        and raw_bp >= min_req_cash
        and (now_free_cash + cash_bucket + pending_sgov_buy) >= min_req_cash
    ):''',
    new_block=r'''    if (
        pending_sgov_buy > 0.0
        and bp_excl_vault >= min_req_cash
        and (
            now_free_cash
            + min(
                cash_bucket + pending_sgov_buy,
                max(0.0, bp_excl_vault - now_free_cash),
            )
        )
        >= min_req_cash
    ):''',
)

register_patch(
    patch_id="P10_B1_SGOV_SYNC_TERMINAL_CHECK",
    filename="barbell_plugin.py",
    description="Case 66/94 SGOV 주문 타임아웃 취소 시 브로커 종료 상태 확인 후에만 주문 ID 소거",
    old_block=r'''    if need_timeout_cancel:
        try:
            await context.api.cancel_order(oid)
        except Exception:
            pass
        det2 = await context.api.get_order_detail(oid)
        if isinstance(det2, dict):
            ord_status = str(det2.get("status") or ord_status).upper().strip()
            ex2 = (
                det2.get("execution")
                if isinstance(det2.get("execution"), dict)
                else {}
            )
            filled_q = max(filled_q, safe_int(ex2.get("filledQuantity"), 0))
            p2 = safe_float(ex2.get("averageFilledPrice"), 0.0)
            if p2 > 0.0:
                avg_fill_p = p2
        is_done_fill = bool(filled_q > 0)''',
    new_block=r'''    if need_timeout_cancel:
        try:
            await context.api.cancel_order(oid)
        except Exception:
            pass
        det2 = await context.api.get_order_detail(oid)
        st2 = (
            str(det2.get("status") or "").upper().strip()
            if isinstance(det2, dict)
            else ""
        )
        if not isinstance(det2, dict) or st2 in (
            "PENDING",
            "PARTIAL_FILLED",
            "PENDING_CANCEL",
            "PENDING_REPLACE",
        ):
            await asyncio.sleep(0.35)
            det2 = await context.api.get_order_detail(oid)
        if isinstance(det2, dict):
            ord_status = str(det2.get("status") or ord_status).upper().strip()
            ex2 = (
                det2.get("execution")
                if isinstance(det2.get("execution"), dict)
                else {}
            )
            filled_q = max(filled_q, safe_int(ex2.get("filledQuantity"), 0))
            p2 = safe_float(ex2.get("averageFilledPrice"), 0.0)
            if p2 > 0.0:
                avg_fill_p = p2
            if ord_status in (
                "PENDING",
                "PARTIAL_FILLED",
                "PENDING_CANCEL",
                "PENDING_REPLACE",
            ):
                return {"status": "SGOV_CANCEL_IN_FLIGHT", "orderId": oid}
        elif not force_settle and elapsed < (SGOV_ORDER_MAX_WAIT_SEC + 30.0):
            return {"status": "SGOV_CANCEL_VERIFY_RETRY", "orderId": oid}
        is_done_fill = bool(filled_q > 0)''',
)

register_patch(
    patch_id="P10_B2_SGOV_SELLABLE_AND_60_100_BUY_UNLOCK",
    filename="barbell_plugin.py",
    description="Case 94 SGOV 매도 전 sellableQuantity 캡핑",
    old_block=r'''    # 2) [1순위] SGOV 10% 상당 정수 수량(소수점 내림) 지정가 매도
    if pending_sells > 0 and sgov_qty > 0:
        sell_q = compute_sgov_10pct_sell_qty(
            initial_seed_usd=init_seed,
            sgov_live_price=sgov_lp,
            sgov_held_qty=sgov_qty,
        )
        if sell_q > 0:''',
    new_block=r'''    # 2) [1순위] SGOV 10% 상당 정수 수량(소수점 내림) 지정가 매도
    if pending_sells > 0 and sgov_qty > 0:
        sellable_sgov = await context.api.get_sellable_quantity(
            BARBELL_SAFE_SYMBOL, allow_barbell_sgov=True
        )
        eff_held_sgov = (
            min(sgov_qty, sellable_sgov) if sellable_sgov > 0 else sgov_qty
        )
        sell_q = (
            compute_sgov_10pct_sell_qty(
                initial_seed_usd=init_seed,
                sgov_live_price=sgov_lp,
                sgov_held_qty=eff_held_sgov,
            )
            if sellable_sgov > 0
            else 0
        )
        if sell_q > 0:''',
)

register_patch(
    patch_id="P10_B3_SGOV_BUY_UNLOCK_WHEN_INJECTED",
    filename="barbell_plugin.py",
    description="Case 94 SOXL 60%~100% 비중 전환 및 선행 수혈 후 잔여 SGOV 매수예약금 정상 집행",
    old_block=r'''    # 3) [2순위] SGOV 30% 목표 예산 범위 내 지정가 매수 (수혈 진행 중이 아닐 때만 실행)
    if (
        pending_buy_bud > 0.0
        and pending_sells == 0
        and safe_float(bst.get("cash_injected_to_soxl_usd"), 0.0) <= 0.0
    ):''',
    new_block=r'''    # 3) [2순위] SGOV 30% 목표 예산 범위 내 지정가 매수 (SGOV 매도 대기나 시드고갈 대기가 아닐 때 실행)
    if (
        pending_buy_bud > 0.0
        and pending_sells == 0
        and not bool(st_soxl.get("waiting_reserve_deposit", False))
    ):''',
)

# ===========================================================================
# [11. assassin_plugin.py 패치 등록]
# ===========================================================================
register_patch(
    patch_id="P11_A1_ACTIVATE_ZERO_SOXL_GUARDS",
    filename="assassin_plugin.py",
    description="Case 95 스나이퍼 미결 주문 대기 중 조기 LIVE 승격 차단 · 바벨 미결 SGOV 정리 · 알림래치 초기화",
    old_block=r'''    st_sp = context.ledger.get_state(TARGET_SYMBOL)
    buckets = buckets_from_dicts(st_sp.get("buckets", []))
    sub_buckets = buckets_from_dicts(st_sp.get("sub_buckets", []))
    if buckets or sub_buckets:
        return False

    if hasattr(context, "api"):
        try:
            await context.api.cancel_all_open_orders(
                symbol=BARBELL_SAFE_SYMBOL
            )
        except Exception:
            pass

    init_seed = safe_float(
        st_sp.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD
    )
    await assn_ledger.update_state(
        execution_mode=ASSASSIN_MODE_LIVE,
        demote_to_sim_after_exit=False,
        initial_seed_usd=round(max(100.0, init_seed), 4),
    )''',
    new_block=r'''    st_sp = context.ledger.get_state(TARGET_SYMBOL)
    buckets = buckets_from_dicts(st_sp.get("buckets", []))
    sub_buckets = buckets_from_dicts(st_sp.get("sub_buckets", []))
    if (
        buckets
        or sub_buckets
        or str(st_sp.get("buy_order_id") or "").strip()
        or str(st_sp.get("sell_order_id") or "").strip()
    ):
        return False

    if hasattr(context, "api"):
        try:
            open_soxl = await context.api.get_open_orders(symbol=TARGET_SYMBOL)
            if open_soxl:
                return False
        except Exception:
            pass
        try:
            await context.api.cancel_all_open_orders(
                symbol=BARBELL_SAFE_SYMBOL
            )
            if hasattr(context, "barbell_ledger"):
                from barbell_plugin import _sync_pending_sgov_orders

                await _sync_pending_sgov_orders(
                    context=context,
                    b_ledger=context.barbell_ledger,
                    bst=context.barbell_ledger.get_state(),
                    force_settle=True,
                )
        except Exception:
            pass

    init_seed = safe_float(
        st_sp.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD
    )
    clear_sim_pos_kw: Dict[str, Any] = {}
    if bool(st.get("has_position", False)) and not bool(
        st.get("is_live_position", False)
    ):
        clear_sim_pos_kw = {
            "has_position": False,
            "is_live_position": False,
            "alert_entry_sent": False,
            "alert_arm_100_sent": False,
            "alert_exit_sent": False,
            "alert_live_bp_shortfall_sent": False,
        }
    await assn_ledger.update_state(
        execution_mode=ASSASSIN_MODE_LIVE,
        demote_to_sim_after_exit=False,
        initial_seed_usd=round(max(100.0, init_seed), 4),
        **clear_sim_pos_kw,
    )''',
)

register_patch(
    patch_id="P11_A2_TOGGLE_PROMOTE_VERIFY_HOLDINGS",
    filename="assassin_plugin.py",
    description="Case 95 수동 실전 승격 요청 시 브로커 잔고 조회 성공 확인 및 미결 주문 부재 이중 검문",
    old_block=r'''    if want_live:
        buckets = buckets_from_dicts(st_sp.get("buckets", []))
        sub_buckets = buckets_from_dicts(st_sp.get("sub_buckets", []))
        has_pending_soxl_ord = bool(
            str(st_sp.get("buy_order_id") or "").strip()
            or str(st_sp.get("sell_order_id") or "").strip()
        )
        broker_soxl_qty = 0
        if hasattr(context, "api"):
            try:
                h_map, ok = await context.api.get_holdings_map_with_status(
                    symbol=TARGET_SYMBOL
                )
                if ok and isinstance(h_map, dict):
                    broker_soxl_qty = safe_int(
                        (h_map.get(TARGET_SYMBOL) or {}).get("qty"), 0
                    )
            except Exception:
                broker_soxl_qty = 0

        total_soxl_held = (
            sum(b.qty for b in buckets)
            + sum(sb.qty for sb in sub_buckets)
            + broker_soxl_qty
        )
        if total_soxl_held == 0 and not has_pending_soxl_ord:
            if hasattr(context, "api"):
                try:
                    await context.api.cancel_all_open_orders(
                        symbol=BARBELL_SAFE_SYMBOL
                    )
                except Exception:
                    pass
            updated = await assn_ledger.update_state(
                execution_mode=ASSASSIN_MODE_LIVE,
                demote_to_sim_after_exit=False,
                initial_seed_usd=init_seed,
                has_position=False,
                is_live_position=False,
            )''',
    new_block=r'''    if want_live:
        buckets = buckets_from_dicts(st_sp.get("buckets", []))
        sub_buckets = buckets_from_dicts(st_sp.get("sub_buckets", []))
        has_pending_soxl_ord = bool(
            str(st_sp.get("buy_order_id") or "").strip()
            or str(st_sp.get("sell_order_id") or "").strip()
        )
        broker_soxl_qty = 0
        holdings_verified = not hasattr(context, "api")
        if hasattr(context, "api"):
            try:
                open_soxl = await context.api.get_open_orders(
                    symbol=TARGET_SYMBOL
                )
                if open_soxl:
                    has_pending_soxl_ord = True
                h_map, ok = await context.api.get_holdings_map_with_status(
                    symbol=TARGET_SYMBOL
                )
                if ok and isinstance(h_map, dict):
                    holdings_verified = True
                    broker_soxl_qty = safe_int(
                        (h_map.get(TARGET_SYMBOL) or {}).get("qty"), 0
                    )
            except Exception:
                holdings_verified = False

        total_soxl_held = (
            sum(b.qty for b in buckets)
            + sum(sb.qty for sb in sub_buckets)
            + broker_soxl_qty
        )
        if (
            holdings_verified
            and total_soxl_held == 0
            and not has_pending_soxl_ord
        ):
            if hasattr(context, "api"):
                try:
                    await context.api.cancel_all_open_orders(
                        symbol=BARBELL_SAFE_SYMBOL
                    )
                    if hasattr(context, "barbell_ledger"):
                        from barbell_plugin import _sync_pending_sgov_orders

                        await _sync_pending_sgov_orders(
                            context=context,
                            b_ledger=context.barbell_ledger,
                            bst=context.barbell_ledger.get_state(),
                            force_settle=True,
                        )
                except Exception:
                    pass
            updated = await assn_ledger.update_state(
                execution_mode=ASSASSIN_MODE_LIVE,
                demote_to_sim_after_exit=False,
                initial_seed_usd=init_seed,
                has_position=False,
                is_live_position=False,
                alert_entry_sent=False,
                alert_arm_100_sent=False,
                alert_exit_sent=False,
                alert_live_bp_shortfall_sent=False,
            )''',
)

register_patch(
    patch_id="P11_B_SETTLE_FEE_SHIELD_AND_EXIT_SYNC",
    filename="assassin_plugin.py",
    description="Case 61/65/86/95 실전 암살자 실측 수수료 반영 및 모의 복귀 시 스나이퍼 60초 타임쉴드 각인",
    old_block=r'''async def _settle_assassin_exit_to_ledger(
    context: Any,
    assn_ledger: AssassinSimLedger,
    st: Dict[str, Any],
    exec_xp: float,
    exit_code: str,
    exit_desc: str,
    entry_qqq_p: float,
    cur_qqq_chg_pct: float,
    new_armed: bool,
    peak_p: float,
    min_p: float,
    dt_now: datetime,
) -> str:
    ep = safe_float(st.get("entry_price"), exec_xp)
    rt_fee = safe_float(
        st.get("round_trip_fee_rate_pct"), ROUND_TRIP_FEE_RATE_PCT
    )
    was_live_pos = bool(st.get("is_live_position", False))

    s_qty = max(1, safe_int(st.get("simple_held_qty"), 1))
    c_qty = max(1, safe_int(st.get("comp_held_qty"), 1))
    s_inv = safe_float(st.get("simple_invested_usd"), float(s_qty) * ep)
    c_inv = safe_float(st.get("comp_invested_usd"), float(c_qty) * ep)

    s_pnl_info = calc_sell_realized_pnl(
        sold_qty=s_qty,
        sell_exec_price=exec_xp,
        sold_actual_cost_usd=s_inv,
        round_trip_fee_rate_pct=rt_fee,
    )
    c_pnl_info = calc_sell_realized_pnl(
        sold_qty=c_qty,
        sell_exec_price=exec_xp,
        sold_actual_cost_usd=c_inv,
        round_trip_fee_rate_pct=rt_fee,
    )
    s_net = safe_float(s_pnl_info.get("net_pnl_usd"), 0.0)
    c_net = safe_float(c_pnl_info.get("net_pnl_usd"), 0.0)

    l_net = 0.0
    if was_live_pos:
        l_qty = max(1, safe_int(st.get("live_held_qty"), 1))
        l_inv = safe_float(st.get("live_invested_usd"), float(l_qty) * ep)
        l_pnl_info = calc_sell_realized_pnl(
            sold_qty=l_qty,
            sell_exec_price=exec_xp,
            sold_actual_cost_usd=l_inv,
            round_trip_fee_rate_pct=rt_fee,
        )
        l_net = safe_float(l_pnl_info.get("net_pnl_usd"), 0.0)''',
    new_block=r'''async def _settle_assassin_exit_to_ledger(
    context: Any,
    assn_ledger: AssassinSimLedger,
    st: Dict[str, Any],
    exec_xp: float,
    exit_code: str,
    exit_desc: str,
    entry_qqq_p: float,
    cur_qqq_chg_pct: float,
    new_armed: bool,
    peak_p: float,
    min_p: float,
    dt_now: datetime,
    actual_sell_fee_usd: Optional[float] = None,
) -> str:
    ep = safe_float(st.get("entry_price"), exec_xp)
    rt_fee = safe_float(
        st.get("round_trip_fee_rate_pct"), ROUND_TRIP_FEE_RATE_PCT
    )
    was_live_pos = bool(st.get("is_live_position", False))

    s_qty = max(1, safe_int(st.get("simple_held_qty"), 1))
    c_qty = max(1, safe_int(st.get("comp_held_qty"), 1))
    s_inv = safe_float(st.get("simple_invested_usd"), float(s_qty) * ep)
    c_inv = safe_float(st.get("comp_invested_usd"), float(c_qty) * ep)

    s_pnl_info = calc_sell_realized_pnl(
        sold_qty=s_qty,
        sell_exec_price=exec_xp,
        sold_actual_cost_usd=s_inv,
        round_trip_fee_rate_pct=rt_fee,
    )
    c_pnl_info = calc_sell_realized_pnl(
        sold_qty=c_qty,
        sell_exec_price=exec_xp,
        sold_actual_cost_usd=c_inv,
        round_trip_fee_rate_pct=rt_fee,
    )
    s_net = safe_float(s_pnl_info.get("net_pnl_usd"), 0.0)
    c_net = safe_float(c_pnl_info.get("net_pnl_usd"), 0.0)

    l_net = 0.0
    if was_live_pos:
        l_qty = max(1, safe_int(st.get("live_held_qty"), 1))
        l_inv = safe_float(st.get("live_invested_usd"), float(l_qty) * ep)
        l_pnl_info = calc_sell_realized_pnl(
            sold_qty=l_qty,
            sell_exec_price=exec_xp,
            sold_actual_cost_usd=l_inv,
            round_trip_fee_rate_pct=rt_fee,
            actual_sell_fee_usd=actual_sell_fee_usd,
        )
        l_net = safe_float(l_pnl_info.get("net_pnl_usd"), 0.0)
        if context is not None:
            now_m_sh = time.monotonic()
            now_e_sh = time.time()
            for cache_attr in ("exit_snapshot_cache", "indexing_grace_cache"):
                c_map = getattr(context, cache_attr, None)
                if isinstance(c_map, dict):
                    c_ent = dict(c_map.get(TARGET_SYMBOL) or {})
                    c_ent["last_auto_fill_ts"] = now_m_sh
                    c_ent["last_sell_fill_mono"] = now_m_sh
                    c_ent["last_cycle_end_mono"] = now_m_sh
                    c_ent["last_sell_fill_ts"] = now_e_sh
                    c_ent["last_cycle_end_ts"] = now_e_sh
                    c_ent["lot_type"] = "SELL_FILL"
                    c_map[TARGET_SYMBOL] = c_ent
            if hasattr(context, "ledger"):
                try:
                    await context.ledger.update_state(
                        TARGET_SYMBOL,
                        last_sell_fill_ts=now_e_sh,
                        last_cycle_end_ts=now_e_sh,
                    )
                except Exception:
                    pass''',
)

register_patch(
    patch_id="P11_B2_SYNC_LIVE_EXIT_DEADLOCK_AND_MOC",
    filename="assassin_plugin.py",
    description="Case 19/93/95 부분 체결 후 CANCELED/REPLACED 시 409 데드락 해결 및 15:59 2단계 급강하 스윕",
    old_block=r'''    if st_ord == "FILLED":
        return await _settle_assassin_exit_to_ledger(
            context=context,
            assn_ledger=assn_ledger,
            st=st,
            exec_xp=fp,
            exit_code=str(st.get("pending_exit_code") or "EXIT"),
            exit_desc=str(st.get("pending_exit_desc") or "실전 청산 체결"),
            entry_qqq_p=eq_qqq,
            cur_qqq_chg_pct=q_chg,
            new_armed=bool(st.get("is_trailing_armed", False)),
            peak_p=safe_float(st.get("peak_price"), fp),
            min_p=safe_float(st.get("post_entry_min_price"), fp),
            dt_now=dt_now,
        )

    elapsed = time.monotonic() - safe_float(
        st.get("pending_exit_mono"), time.monotonic()
    )
    if elapsed >= 5.0 and lp > 0.0:
        chase_p = round(max(0.01, lp * 0.996), 2)
        try:
            mod_r = await context.api.modify_order(
                order_id=sell_oid, new_price=chase_p
            )
            new_oid = str((mod_r or {}).get("orderId") or sell_oid).strip()
            await assn_ledger.update_state(
                pending_exit_sell_order_id=new_oid,
                pending_exit_mono=time.monotonic(),
            )
        except Exception:
            if st_ord in ("CANCELED", "REJECTED") and fq <= 0:
                await assn_ledger.update_state(
                    pending_exit_sell_order_id="",
                    pending_exit_code="",
                    pending_exit_desc="",
                    pending_exit_mono=0.0,
                )
    context.assassin_high_freq_active = True
    return "ASSASSIN_LIVE_EXIT_WAITING"''',
    new_block=r'''    actual_fee: Optional[float] = None
    if isinstance(det, dict) and isinstance(det.get("execution"), dict):
        ex_f = det["execution"]
        f_tot = round(
            max(0.0, safe_float(ex_f.get("commission"), 0.0))
            + max(0.0, safe_float(ex_f.get("tax"), 0.0)),
            4,
        )
        if f_tot > 0.0:
            actual_fee = f_tot

    if st_ord == "FILLED":
        return await _settle_assassin_exit_to_ledger(
            context=context,
            assn_ledger=assn_ledger,
            st=st,
            exec_xp=fp,
            exit_code=str(st.get("pending_exit_code") or "EXIT"),
            exit_desc=str(st.get("pending_exit_desc") or "실전 청산 체결"),
            entry_qqq_p=eq_qqq,
            cur_qqq_chg_pct=q_chg,
            new_armed=bool(st.get("is_trailing_armed", False)),
            peak_p=safe_float(st.get("peak_price"), fp),
            min_p=safe_float(st.get("post_entry_min_price"), fp),
            dt_now=dt_now,
            actual_sell_fee_usd=actual_fee,
        )

    if st_ord in ("CANCELED", "REJECTED", "REPLACED"):
        h_map_chk, h_ok_chk = await context.api.get_holdings_map_with_status(
            symbol=TARGET_SYMBOL
        )
        rem_broker_q = (
            safe_int((h_map_chk.get(TARGET_SYMBOL) or {}).get("qty"), 0)
            if (h_ok_chk and isinstance(h_map_chk, dict))
            else max(0, safe_int(st.get("live_held_qty"), 1) - fq)
        )
        if h_ok_chk and rem_broker_q <= 0:
            eff_p_end = fp
            if fq <= 0 and hasattr(context.api, "probe_latest_manual_fill_price"):
                probed_p, _ = await context.api.probe_latest_manual_fill_price(
                    side="SELL",
                    target_qty=max(1, safe_int(st.get("live_held_qty"), 1)),
                    fallback_price=lp,
                    symbol=TARGET_SYMBOL,
                )
                if probed_p > 0.0:
                    eff_p_end = probed_p
            return await _settle_assassin_exit_to_ledger(
                context=context,
                assn_ledger=assn_ledger,
                st=st,
                exec_xp=eff_p_end,
                exit_code=str(st.get("pending_exit_code") or "EXIT"),
                exit_desc=str(st.get("pending_exit_desc") or "실전 청산 체결"),
                entry_qqq_p=eq_qqq,
                cur_qqq_chg_pct=q_chg,
                new_armed=bool(st.get("is_trailing_armed", False)),
                peak_p=safe_float(st.get("peak_price"), eff_p_end),
                min_p=safe_float(st.get("post_entry_min_price"), eff_p_end),
                dt_now=dt_now,
                actual_sell_fee_usd=actual_fee,
            )
        old_lq = max(1, safe_int(st.get("live_held_qty"), 1))
        new_lq = max(1, rem_broker_q if h_ok_chk else max(1, old_lq - fq))
        ep_cur = safe_float(st.get("entry_price"), lp)
        await assn_ledger.update_state(
            live_held_qty=new_lq,
            live_invested_usd=round(float(new_lq) * ep_cur, 4),
            safe_cap_sell_order_id="",
            pending_exit_sell_order_id="",
            pending_exit_code="",
            pending_exit_desc="",
            pending_exit_mono=0.0,
        )
        context.assassin_high_freq_active = True
        return "ASSASSIN_LIVE_EXIT_RE_SWEEP_ARMED"

    elapsed = time.monotonic() - safe_float(
        st.get("pending_exit_mono"), time.monotonic()
    )
    hm_chk = dt_now.hour * 100 + dt_now.minute
    wait_thr = 3.0 if hm_chk >= ASSASSIN_MOC_EXIT_HM else 5.0
    if elapsed >= wait_thr and lp > 0.0:
        if hm_chk >= ASSASSIN_MOC_EXIT_HM:
            bid_p = await context.api.get_best_bid_price(
                TARGET_SYMBOL, fallback_price=lp
            )
            ref_m_p = min(lp, bid_p) if bid_p > 0.0 else lp
            chase_p = round(max(0.01, ref_m_p * 0.985), 2)
        else:
            chase_p = round(max(0.01, lp * 0.996), 2)
        try:
            mod_r = await context.api.modify_order(
                order_id=sell_oid, new_price=chase_p
            )
            new_oid = str((mod_r or {}).get("orderId") or sell_oid).strip()
            await assn_ledger.update_state(
                pending_exit_sell_order_id=new_oid,
                pending_exit_mono=time.monotonic(),
            )
        except Exception:
            pass
    context.assassin_high_freq_active = True
    return "ASSASSIN_LIVE_EXIT_WAITING"''',
)

register_patch(
    patch_id="P11_C1_ARMED_ZERO_PENDING_ORD_GUARD",
    filename="assassin_plugin.py",
    description="Case 95 스나이퍼 0주 미체결 주문 존재 시 ARMED_ON_ZERO 조기 승격 호출 차단",
    old_block=r'''            if (
                str(
                    ensure_assassin_ledger(context)
                    .get_state()
                    .get("execution_mode")
                    or ""
                )
                == ASSASSIN_MODE_ARMED_ON_ZERO
                and not st_sp.get("buckets")
                and not st_sp.get("sub_buckets")
            ):
                await activate_live_assassin_on_zero_soxl_if_armed(context)''',
    new_block=r'''            if (
                str(
                    ensure_assassin_ledger(context)
                    .get_state()
                    .get("execution_mode")
                    or ""
                )
                == ASSASSIN_MODE_ARMED_ON_ZERO
                and not st_sp.get("buckets")
                and not st_sp.get("sub_buckets")
                and not str(st_sp.get("buy_order_id") or "").strip()
                and not str(st_sp.get("sell_order_id") or "").strip()
            ):
                await activate_live_assassin_on_zero_soxl_if_armed(context)''',
)

register_patch(
    patch_id="P11_C2_SAME_MIN_HIGH_AND_MANUAL_LIVE_SYNC",
    filename="assassin_plugin.py",
    description="Case 58/82/93/95 본대 진입 동일분봉 과거고가 점화 차단 및 실전 암살자 중 앱 수동매도 감지 정산",
    old_block=r'''        exit_eval = evaluate_assassin_ha_trailing_and_exits(
            hm=hm,
            entry_price=safe_float(st.get("entry_price"), lp),
            live_price=lp,
            bar_high_price=safe_float(feat.get("cur_bar_high"), lp),''',
    new_block=r'''        if (
            is_live_pos
            and hasattr(context, "api")
            and (now_ts - safe_float(st.get("entry_ts"), 0.0)) >= 15.0
            and (
                now_ts
                - safe_float(getattr(context, "_last_assn_h_chk_ts", 0.0), 0.0)
            )
            >= 6.0
        ):
            setattr(context, "_last_assn_h_chk_ts", now_ts)
            try:
                h_m_live, h_ok_live = (
                    await context.api.get_holdings_map_with_status(
                        symbol=TARGET_SYMBOL
                    )
                )
                if (
                    h_ok_live
                    and isinstance(h_m_live, dict)
                    and safe_int(
                        (h_m_live.get(TARGET_SYMBOL) or {}).get("qty"), 0
                    )
                    <= 0
                ):
                    if cap_oid_now:
                        try:
                            await context.api.cancel_order(cap_oid_now)
                        except Exception:
                            pass
                    man_p = lp
                    man_fee: Optional[float] = None
                    if hasattr(context.api, "probe_latest_manual_fill_price"):
                        man_p, _ = (
                            await context.api.probe_latest_manual_fill_price(
                                side="SELL",
                                target_qty=max(
                                    1, safe_int(st.get("live_held_qty"), 1)
                                ),
                                fallback_price=lp,
                                symbol=TARGET_SYMBOL,
                            )
                        )
                        f_probe = safe_float(
                            getattr(
                                context.api, "last_probed_manual_fee_usd", 0.0
                            ),
                            0.0,
                        )
                        if f_probe > 0.0:
                            man_fee = f_probe
                    return await _settle_assassin_exit_to_ledger(
                        context=context,
                        assn_ledger=assn_ledger,
                        st=st,
                        exec_xp=(man_p if man_p > 0.0 else lp),
                        exit_code="MANUAL_EXIT_SYNC",
                        exit_desc=f"🧹 실전 보유분 수동 전량청산 동기화(${man_p if man_p > 0.0 else lp:.2f})",
                        entry_qqq_p=entry_qqq_p,
                        cur_qqq_chg_pct=cur_qqq_chg_pct,
                        new_armed=bool(st.get("is_trailing_armed", False)),
                        peak_p=max(safe_float(st.get("peak_price"), lp), lp),
                        min_p=safe_float(st.get("post_entry_min_price"), lp),
                        dt_now=dt_now,
                        actual_sell_fee_usd=man_fee,
                    )
            except Exception:
                pass

        entry_hm_prefix = str(st.get("entry_time_est") or "")[:5]
        same_entry_min = bool(
            entry_hm_prefix and dt_now.strftime("%H:%M") == entry_hm_prefix
        )
        eff_bar_high = (
            lp
            if same_entry_min
            else max(lp, safe_float(feat.get("cur_bar_high"), lp))
        )

        exit_eval = evaluate_assassin_ha_trailing_and_exits(
            hm=hm,
            entry_price=safe_float(st.get("entry_price"), lp),
            live_price=lp,
            bar_high_price=eff_bar_high,''',
)

register_patch(
    patch_id="P11_C3_LIVE_EXIT_FAIL_NO_FAKE_SETTLE",
    filename="assassin_plugin.py",
    description="P0 치명 결함 봉쇄: 실전(LIVE) 청산 발주 실패(ok_ex==False) 시 폴스루 허위 퇴근 차단 및 0.4s 즉시 재시도",
    old_block=r'''        if is_live_pos and ok_ex and not imm_ex_filled and active_sell_oid:
            await assn_ledger.update_state(
                pending_exit_sell_order_id=active_sell_oid,
                pending_exit_code=exit_code,
                pending_exit_desc=exit_desc,
                pending_exit_mono=time.monotonic(),
                is_trailing_armed=new_armed,
                peak_price=safe_float(exit_eval.get("peak_price"), lp),
                post_entry_min_price=safe_float(
                    exit_eval.get("post_entry_min_price"), lp
                ),
            )
            context.assassin_high_freq_active = True
            return f"ASSASSIN_LIVE_EXIT_PENDING_{exit_code}"

        return await _settle_assassin_exit_to_ledger(''',
    new_block=r'''        if is_live_pos:
            if not ok_ex:
                if hasattr(context, "api"):
                    try:
                        open_chk = await context.api.get_open_orders(
                            symbol=TARGET_SYMBOL
                        )
                        h_chk, h_ok2 = (
                            await context.api.get_holdings_map_with_status(
                                symbol=TARGET_SYMBOL
                            )
                        )
                        if (
                            not open_chk
                            and h_ok2
                            and safe_int(
                                (h_chk.get(TARGET_SYMBOL) or {}).get("qty"), 0
                            )
                            <= 0
                        ):
                            p_man, _ = (
                                await context.api.probe_latest_manual_fill_price(
                                    side="SELL",
                                    target_qty=eff_sell_q,
                                    fallback_price=lp,
                                    symbol=TARGET_SYMBOL,
                                )
                            )
                            return await _settle_assassin_exit_to_ledger(
                                context=context,
                                assn_ledger=assn_ledger,
                                st=st,
                                exec_xp=(p_man if p_man > 0.0 else lp),
                                exit_code=exit_code,
                                exit_desc=exit_desc,
                                entry_qqq_p=entry_qqq_p,
                                cur_qqq_chg_pct=cur_qqq_chg_pct,
                                new_armed=new_armed,
                                peak_p=safe_float(
                                    exit_eval.get("peak_price"), lp
                                ),
                                min_p=safe_float(
                                    exit_eval.get("post_entry_min_price"), lp
                                ),
                                dt_now=dt_now,
                            )
                    except Exception:
                        pass
                await assn_ledger.update_state(
                    safe_cap_sell_order_id=active_sell_oid,
                    is_trailing_armed=new_armed,
                    peak_price=safe_float(exit_eval.get("peak_price"), lp),
                    post_entry_min_price=safe_float(
                        exit_eval.get("post_entry_min_price"), lp
                    ),
                )
                if context is not None:
                    context.assassin_high_freq_active = True
                logger.warning(
                    "⚠️ [Case 95 실전 암살자 청산 스윕 일시 실패 -> 퇴근 보류 및 0.4s 즉시 재시도] code=%s",
                    exit_code,
                )
                return f"ASSASSIN_LIVE_EXIT_RETRY_{exit_code}"

            if not imm_ex_filled and active_sell_oid:
                await assn_ledger.update_state(
                    pending_exit_sell_order_id=active_sell_oid,
                    pending_exit_code=exit_code,
                    pending_exit_desc=exit_desc,
                    pending_exit_mono=time.monotonic(),
                    is_trailing_armed=new_armed,
                    peak_price=safe_float(exit_eval.get("peak_price"), lp),
                    post_entry_min_price=safe_float(
                        exit_eval.get("post_entry_min_price"), lp
                    ),
                )
                if context is not None:
                    context.assassin_high_freq_active = True
                return f"ASSASSIN_LIVE_EXIT_PENDING_{exit_code}"

        return await _settle_assassin_exit_to_ledger(''',
)

_LOADED_PARTS.append(4)

# ===========================================================================
# [11. assassin_plugin.py 추가 마감 패치 등록]
# ===========================================================================
register_patch(
    patch_id="P11_D_RESET_TODAY_GT_WINS",
    filename="assassin_plugin.py",
    description="Case 96 /reset_assassin 실행 시 당일 다회차 정찰 카운터 동시 초기화로 일최다 기록 역복원 차단",
    old_block=r'''            total_scouts_dispatched=0,
            total_scout_win_exits=0,
            cum_gt_gate_dispatches=0,
            cum_gt_gate_win_exits=0,
            cum_gt_gate_stop_exits=0,
            cum_gt_gate_cutoff_exits=0,
            cum_gt_multi_win_days=0,
            max_daily_gt_gate_wins=0,''',
    new_block=r'''            total_scouts_dispatched=0,
            total_scout_win_exits=0,
            today_gt_gate_dispatches=0,
            today_gt_gate_win_exits=0,
            today_gt_gate_stop_exits=0,
            today_gt_gate_cutoff_exits=0,
            today_gt_gate_history=[],
            cum_gt_gate_dispatches=0,
            cum_gt_gate_win_exits=0,
            cum_gt_gate_stop_exits=0,
            cum_gt_gate_cutoff_exits=0,
            cum_gt_multi_win_days=0,
            max_daily_gt_gate_wins=0,''',
)


# ===========================================================================
# [12. tg_ui_plugin.py 패치 등록]
# ===========================================================================
register_patch(
    patch_id="P12_A1_START_MSG_10G",
    filename="tg_ui_plugin.py",
    description="Case 97-A /start 안내 문구의 순수 10대 급락 게이트(10G) 표기 통일",
    old_block=r'''        "⚖️ <code>/barbell</code> : 바벨(60/30/10) & 별도수익금고 상세",
        "🗡️ <code>/assassin</code> : [모의/실전] 암살자 14대게이트 상세",
    ]''',
    new_block=r'''        "⚖️ <code>/barbell</code> : 바벨(60/30/10) & 별도수익금고 상세",
        "🗡️ <code>/assassin</code> : [모의/실전] 암살자 순수 10G 상세",
    ]''',
)

register_patch(
    patch_id="P12_A2_SUB_VACANT_L1_SIG",
    filename="tg_ui_plugin.py",
    description="Case 84/88/92 서브그리드 1층 공석 렌더링 시 실시간 RSI(14) 인자 수신(1/2)",
    old_block=r'''def _format_sub_grid_stratum_lines(
    summary: Dict[str, Any],
    live_price: float,
    is_ext_sell_only: bool = False,
    is_late_cutoff: bool = False,
) -> List[str]:''',
    new_block=r'''def _format_sub_grid_stratum_lines(
    summary: Dict[str, Any],
    live_price: float,
    is_ext_sell_only: bool = False,
    is_late_cutoff: bool = False,
    live_rsi_14: float = 50.0,
) -> List[str]:''',
)

register_patch(
    patch_id="P12_A3_SUB_VACANT_L1_BADGES",
    filename="tg_ui_plugin.py",
    description="Case 84/88/92 서브그리드 1층 공석 시 15:30 돌파차단 및 RSI>50 과열차단 상태 배지 표출(2/2)",
    old_block=r'''        elif is_ext_sell_only:
            lines.append(
                f"  ⚡ <b>[서브1층: 공석]</b> 🔒장외잠금 · 04:07 재장전{s_cap_note}"
            )
        else:
            lines.append(
                f"  ⚡ <b>[서브1층: 공석]</b> 1분주기 재장전 감시{s_cap_note}"
            )''',
    new_block=r'''        elif is_ext_sell_only:
            lines.append(
                f"  ⚡ <b>[서브1층: 공석]</b> 🔒장외잠금 · 04:07 재장전{s_cap_note}"
            )
        elif is_late_cutoff:
            lines.append(
                f"  ⚡ <b>[서브1층: 공석]</b> 🛡️돌파차단 · 눌림(-1%) 감시{s_cap_note}"
            )
        elif live_rsi_14 > 50.0:
            lines.append(
                f"  ⚡ <b>[서브1층: 공석]</b> 눌림(-1%)/🛡️돌파차단(RSI {live_rsi_14:.1f}>50){s_cap_note}"
            )
        else:
            lines.append(
                f"  ⚡ <b>[서브1층: 공석]</b> 1분주기 눌림(-1%)/돌파(RSI<=50){s_cap_note}"
            )''',
)

register_patch(
    patch_id="P12_B1_RADAR_PASS_RSI14",
    filename="tg_ui_plugin.py",
    description="Case 92 /avwap 스나이퍼 레이더 요약 산출 시 실시간 rsi_14 전달 동기화",
    old_block=r'''    rsi_14 = safe_float(met.get("rsi_14"), 50.0)

    summary = summarize_stratum_portfolio(st, live_price=lp, now_est=dt_now)''',
    new_block=r'''    rsi_14 = safe_float(met.get("rsi_14"), 50.0)

    summary = summarize_stratum_portfolio(
        st, live_price=lp, now_est=dt_now, rsi_14=rsi_14
    )''',
)

register_patch(
    patch_id="P12_B2_RADAR_SUB_RSI_AND_10G_TEXT",
    filename="tg_ui_plugin.py",
    description="Case 92/97-A 서브 지층 live_rsi_14 전달 동기화",
    old_block=r'''    sub_stratum_lines = _format_sub_grid_stratum_lines(
        summary,
        lp,
        is_ext_sell_only=is_ext_sell_only,
        is_late_cutoff=is_late_cutoff,
    )''',
    new_block=r'''    sub_stratum_lines = _format_sub_grid_stratum_lines(
        summary,
        lp,
        is_ext_sell_only=is_ext_sell_only,
        is_late_cutoff=is_late_cutoff,
        live_rsi_14=rsi_14,
    )''',
)

register_patch(
    patch_id="P12_B3_RADAR_ASSN_10G_LABEL",
    filename="tg_ui_plugin.py",
    description="Case 97-A 레이더 타점 안내 문구의 순수 10대 급락 게이트 표기 통일",
    old_block=r'''    if live_assn_active:
        gate_header_line = "🎯 <b>[다음 매수 타점 · 실전 암살자 위임]</b>"
        gate_cond_lines.append(
            "▫️ 04:07 ~ 08:14 EST 14대 진성 게이트 포착 시 단발 타격"
        )''',
    new_block=r'''    if live_assn_active:
        gate_header_line = "🎯 <b>[다음 매수 타점 · 실전 암살자 위임]</b>"
        gate_cond_lines.append(
            "▫️ 04:07 ~ 08:14 EST 순수 10대 급락 게이트 포착 시 단발 타격"
        )''',
)

register_patch(
    patch_id="P12_C1_CTRL_INIT_AND_400_WARMUP",
    filename="tg_ui_plugin.py",
    description="제1헌법/Case 93 TelegramCommandController 생성자 확장",
    old_block=r'''class TelegramCommandController:
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
        ).strip()''',
    new_block=r'''class TelegramCommandController:
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
        ).strip()''',
)

register_patch(
    patch_id="P12_C2_REFRESH_METRICS_400_ASYNC",
    filename="tg_ui_plugin.py",
    description="제1헌법/Case 93 UI 시세 갱신 시 400분봉+10일봉 to_thread 격리 연산으로 앵커 오염 차단",
    old_block=r'''        base_met = self.context.candle_metrics_cache.get(TARGET_SYMBOL, {})
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
                pass''',
    new_block=r'''        base_met = self.context.candle_metrics_cache.get(TARGET_SYMBOL, {})
        if (
            not isinstance(base_met, dict)
            or not bool(base_met.get("anchors_ready", False))
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
                pass''',
)

register_patch(
    patch_id="P12_C3_LIVE_ASSN_BARBELL_MODE_DEFER",
    filename="tg_ui_plugin.py",
    description="Case 94/95 실전 암살자(LIVE) 단독 가동 중 바벨 모드 전환 시 초기화 유예로 오분류 차단",
    old_block=r'''        # 바벨 모드로 진입한 즉시 현재 보유 SOXL 원금(<=60% / 60~100% / >=100%)을 자동 분류 동기화!
        if is_barbell_mode(next_m):
            await initialize_or_sync_barbell_on_mode_enter(self.context)
            updated_st = self.context.ledger.get_state(TARGET_SYMBOL)''',
    new_block=r'''        # 바벨 모드 진입 시 동기화 (단, 실전 암살자 단독 가동 중에는 복귀 첫 틱까지 유예)
        if is_barbell_mode(next_m):
            if is_live_assassin_standalone_active(self.context):
                await ensure_barbell_ledger(self.context).update_state(
                    is_initialized=False
                )
            else:
                await initialize_or_sync_barbell_on_mode_enter(self.context)
                updated_st = self.context.ledger.get_state(TARGET_SYMBOL)''',
)

register_patch(
    patch_id="P12_C4_LIVE_ASSN_SEED_BARBELL_DEFER",
    filename="tg_ui_plugin.py",
    description="Case 94/95 실전 암살자(LIVE) 가동 중 시드머니 변경 시 바벨 원장 초기화 유예 보호",
    old_block=r'''        try:
            if _is_barbell_portion_mode(updated_st):
                await initialize_or_sync_barbell_on_mode_enter(
                    self.context, new_seed_usd=round(val, 4)
                )
                updated_st = self.context.ledger.get_state(TARGET_SYMBOL)
            else:
                await ensure_barbell_ledger(self.context).update_state(
                    initial_seed_usd=round(val, 4)
                )
        except Exception:
            pass''',
    new_block=r'''        try:
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
            pass''',
)


# ===========================================================================
# [13. plugin_updater.py 패치 등록]
# ===========================================================================
register_patch(
    patch_id="P13_A_TOKEN_REGEX_AND_SNAPSHOT_GUARD",
    filename="plugin_updater.py",
    description="Case 68/81 수동 /update 도중 체결된 최신 디스크 원장이 구 스냅샷에 덮어써지는 경합 원천 차단",
    old_block=r'''_TG_TOKEN_STRICT_RE = re.compile(r"\b(\d{8,12}:[A-Za-z0-9_-]{25,60})\b")''',
    new_block=r'''_TG_TOKEN_STRICT_RE = re.compile(r"\b(\d{7,15}:[A-Za-z0-9_-]{25,60})\b")


def _extract_ledger_updated_at_bytes(raw_bytes: bytes) -> str:
    try:
        parsed = json.loads(raw_bytes.decode("utf-8"))
        if not isinstance(parsed, dict):
            return ""
        for k in ("SOXL", "BARBELL"):
            sub = parsed.get(k)
            if isinstance(sub, dict) and sub.get("updated_at"):
                return str(sub.get("updated_at") or "")
        return str(parsed.get("updated_at") or "")
    except Exception:
        return ""''',
)

register_patch(
    patch_id="P13_A2_SNAPSHOT_NO_DUP_LEDGER_INIT",
    filename="plugin_updater.py",
    description="스냅샷 시 임시 SoxlStratumLedger 중복 생성 제거",
    old_block=r'''    abs_dir = get_bot_base_dir(target_dir)
    emergency_free_disk_space_sync(
        base_dir=abs_dir, keep_backup_days=14, remove_pycache=True
    )
    try:
        SoxlStratumLedger(base_dir=abs_dir)
    except Exception as exc:
        logger.debug("업데이트 전 원장 선행 동기화 예외(무시): %s", exc)''',
    new_block=r'''    abs_dir = get_bot_base_dir(target_dir)
    emergency_free_disk_space_sync(
        base_dir=abs_dir, keep_backup_days=14, remove_pycache=True
    )''',
)

register_patch(
    patch_id="P13_A3_RESTORE_NEWER_LEDGER_CHECK",
    filename="plugin_updater.py",
    description="복원 시 디스크 원장의 updated_at 이 스냅샷보다 최신이면 덮어쓰기 스킵",
    old_block=r'''        try:
            with GlobalThrottle.get_file_lock(fp):
                if os.path.isfile(fp):
                    try:
                        with open(fp, "rb") as rf:
                            existing_bytes = rf.read()
                        if existing_bytes == raw_bytes:
                            continue
                    except Exception:
                        pass''',
    new_block=r'''        try:
            with GlobalThrottle.get_file_lock(fp):
                if os.path.isfile(fp):
                    try:
                        with open(fp, "rb") as rf:
                            existing_bytes = rf.read()
                        if existing_bytes == raw_bytes:
                            continue
                        bname_l = os.path.basename(fp).lower()
                        if "ledger" in bname_l and bname_l.endswith(".json"):
                            disk_ts = _extract_ledger_updated_at_bytes(
                                existing_bytes
                            )
                            snap_ts = _extract_ledger_updated_at_bytes(
                                raw_bytes
                            )
                            if disk_ts and snap_ts and disk_ts > snap_ts:
                                continue
                    except Exception:
                        pass''',
)

register_patch(
    patch_id="P13_A4_RESTORE_TAIL_CLEAN",
    filename="plugin_updater.py",
    description="복원 완료 후 불필요한 임시 원장 재생성 제거",
    old_block=r'''    try:
        SoxlStratumLedger(base_dir=abs_dir)
    except Exception as exc:
        logger.debug("복원 후 원장 재검증 예외(무시): %s", exc)

    return restored_cnt''',
    new_block=r'''    return restored_cnt''',
)

register_patch(
    patch_id="P13_B_TOP_LEVEL_AST_SYMBOLS",
    filename="plugin_updater.py",
    description="Case 10/62 함수 내부 지역변수 오수집을 막기 위해 모듈 최상위(tree.body) 심볼만 정밀 추출",
    old_block=r'''def _extract_module_exported_symbols(tree: ast.AST) -> Set[str]:
    exported: Set[str] = set()

    for node in ast.walk(tree):
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            exported.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    exported.add(target.id)
                elif isinstance(target, (ast.Tuple, ast.List)):
                    for elt in target.elts:
                        if isinstance(elt, ast.Name):
                            exported.add(elt.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                exported.add(node.target.id)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                exported.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    exported.add(alias.asname or alias.name)

    return exported''',
    new_block=r'''def _collect_top_level_module_stmts(
    stmts: List[ast.stmt], exported: Set[str]
) -> None:
    for node in stmts:
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            exported.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    exported.add(target.id)
                elif isinstance(target, (ast.Tuple, ast.List)):
                    for elt in target.elts:
                        if isinstance(elt, ast.Name):
                            exported.add(elt.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                exported.add(node.target.id)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                exported.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    exported.add(alias.asname or alias.name)
        elif isinstance(node, ast.If):
            _collect_top_level_module_stmts(node.body, exported)
            _collect_top_level_module_stmts(node.orelse, exported)
        elif isinstance(node, ast.Try):
            _collect_top_level_module_stmts(node.body, exported)
            _collect_top_level_module_stmts(node.orelse, exported)
            _collect_top_level_module_stmts(node.finalbody, exported)
            for h in node.handlers:
                if isinstance(h.name, str) and h.name:
                    exported.add(h.name)
                _collect_top_level_module_stmts(h.body, exported)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            _collect_top_level_module_stmts(node.body, exported)


def _extract_module_exported_symbols(tree: ast.AST) -> Set[str]:
    exported: Set[str] = set()
    body_list = getattr(tree, "body", None)
    if isinstance(body_list, list):
        _collect_top_level_module_stmts(body_list, exported)
    return exported''',
)

register_patch(
    patch_id="P13_C_AUTO_UPDATE_RECHECK_ORDERS",
    filename="plugin_updater.py",
    description="Case 81 장외 무인 업데이트 프리플라이트 완료 직후 execv 직전 미결주문 2차 재검문",
    old_block=r'''        try:
            ok, msg, changed = await execute_git_pull_and_preflight(base_dir)
            if ok and changed:
                logger.warning(
                    "🚀 [Case 81 장외 무인 자동 업데이트 검증 통과] %s -> 3.5초 워치독 및 os.execv 인플레이스 자가 재기동 개시",
                    msg,
                )''',
    new_block=r'''        try:
            ok, msg, changed = await execute_git_pull_and_preflight(base_dir)
            if ok and changed:
                st_chk = context.ledger.get_state("SOXL")
                if str(st_chk.get("buy_order_id") or "").strip() or str(
                    st_chk.get("sell_order_id") or ""
                ).strip():
                    logger.info(
                        "⏳ [Case 81 재기동 유예] 업데이트 도중 신규 SOXL 미결주문 감지 -> 정산 완료 후 차기 주기 재기동"
                    )
                    continue
                logger.warning(
                    "🚀 [Case 81 장외 무인 자동 업데이트 검증 통과] %s -> 3.5초 워치독 및 os.execv 인플레이스 자가 재기동 개시",
                    msg,
                )''',
)


# ===========================================================================
# [14. main_runtime.py 패치 등록]
# ===========================================================================
register_patch(
    patch_id="P14_A_TOKEN_WALRUS_AND_PROFIT_RATE",
    filename="main_runtime.py",
    description="텔레그램 봇 토큰 ID 자릿수(7~15자리) 호환 확장",
    old_block=r'''_TG_TOKEN_STRICT_RE = re.compile(r"\b(\d{8,12}:[A-Za-z0-9_-]{25,60})\b")''',
    new_block=r'''_TG_TOKEN_STRICT_RE = re.compile(r"\b(\d{7,15}:[A-Za-z0-9_-]{25,60})\b")''',
)

register_patch(
    patch_id="P14_A2_HOLDING_WALRUS_REMOVE",
    filename="main_runtime.py",
    description="Case 85 _normalize_single_holding_item 삼항식 내부 바다코끼리 연산자(:=) 평문 분리",
    old_block=r'''    mv_obj = (
        item.get("marketValue")
        if isinstance(item.get("marketValue"), dict)
        else {}
    )
    pl_obj = (
        item.get("profitLoss")
        if isinstance(it_pl := item.get("profitLoss"), dict)
        else {}
    )
    _ = it_pl''',
    new_block=r'''    mv_obj = (
        item.get("marketValue")
        if isinstance(item.get("marketValue"), dict)
        else {}
    )
    raw_pl_obj = item.get("profitLoss")
    pl_obj = raw_pl_obj if isinstance(raw_pl_obj, dict) else {}''',
)

register_patch(
    patch_id="P14_A3_HOLDING_DECIMAL_RATE",
    filename="main_runtime.py",
    description="API.txt HoldingsItem.profitLoss 소수 비율(0.0042 = 0.42%) 미소 손익률 절삭 방지",
    old_block=r'''    if pur_amt > 0.0 and abs(raw_rate) < 2.0 and abs(pnl_amt / pur_amt) > 0.005:
        profit_rate = round((pnl_amt / pur_amt) * 100.0, 2)
    else:
        profit_rate = round(raw_rate, 2)''',
    new_block=r'''    if item.get("profit_rate") is None and pl_obj:
        profit_rate = round(raw_rate * 100.0, 2)
    elif (
        pur_amt > 0.0
        and abs(raw_rate) < 2.0
        and abs(pnl_amt / pur_amt) > 0.005
    ):
        profit_rate = round((pnl_amt / pur_amt) * 100.0, 2)
    else:
        profit_rate = round(raw_rate, 2)''',
)

register_patch(
    patch_id="P14_B1_BRIDGE_SHARED_CTRL_INIT",
    filename="main_runtime.py",
    description="Case 75/81 _AdaptiveTelegramBridge 내 단일 공유 TelegramCommandController 슬롯 장착(세션 누수 제거)",
    old_block=r'''        self._awaiting_seed_input_chats: Dict[str, float] = {}
        self._tg_http_client: Optional[Any] = None
        self._tg_client_lock: asyncio.Lock = asyncio.Lock()
        self._consecutive_poll_errors: int = 0''',
    new_block=r'''        self._awaiting_seed_input_chats: Dict[str, float] = {}
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
        await self._close_tg_http_client()''',
)

register_patch(
    patch_id="P14_B2_BRIDGE_LIVE_BARBELL_GUARDS",
    filename="main_runtime.py",
    description="Case 94/95 브릿지 내 LIVE 중 바벨 유예 가드",
    old_block=r'''        if is_barbell_mode(next_m):
            await initialize_or_sync_barbell_on_mode_enter(self.context)
            updated_st = self.context.ledger.get_state(TARGET_SYMBOL)''',
    new_block=r'''        if is_barbell_mode(next_m):
            if is_live_assassin_standalone_active(self.context):
                await ensure_barbell_ledger(self.context).update_state(
                    is_initialized=False
                )
            else:
                await initialize_or_sync_barbell_on_mode_enter(self.context)
                updated_st = self.context.ledger.get_state(TARGET_SYMBOL)''',
)

register_patch(
    patch_id="P14_B3_BRIDGE_DELEGATE_REUSE",
    filename="main_runtime.py",
    description="Case 75/81/95 브릿지 내 일회용 컨트롤러 중복 생성 제거",
    old_block=r'''    async def _toggle_assassin_live_command(
        self, chat_id: str, edit_msg_id: Optional[int] = None
    ) -> None:
        ctrl = tg_ui_plugin.TelegramCommandController(self.context)
        await ctrl._toggle_assassin_live_command(
            chat_id=chat_id, edit_msg_id=edit_msg_id
        )''',
    new_block=r'''    async def _toggle_assassin_live_command(
        self, chat_id: str, edit_msg_id: Optional[int] = None
    ) -> None:
        ctrl = self._get_shared_ctrl()
        await ctrl._toggle_assassin_live_command(
            chat_id=chat_id, edit_msg_id=edit_msg_id
        )''',
)

register_patch(
    patch_id="P14_B4_BRIDGE_SEED_AND_POLL_UNIFY",
    filename="main_runtime.py",
    description="브릿지 시드 변경 LIVE 유예 보호",
    old_block=r'''        try:
            if _is_barbell_portion_mode(updated_st):
                await initialize_or_sync_barbell_on_mode_enter(
                    self.context, new_seed_usd=round(val, 4)
                )
                updated_st = self.context.ledger.get_state(TARGET_SYMBOL)
            else:
                await ensure_barbell_ledger(self.context).update_state(
                    initial_seed_usd=round(val, 4)
                )
        except Exception:
            pass''',
    new_block=r'''        try:
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
            pass''',
)

register_patch(
    patch_id="P14_B5_BRIDGE_POLL_TAIL_UNIFY",
    filename="main_runtime.py",
    description="콜백/리셋/수동업데이트/폴링 루프 단일 _get_shared_ctrl() 연결로 HTTP 세션 누수 영구 제거",
    old_block=r'''        if first_token == "/reset_profit":
            ctrl = tg_ui_plugin.TelegramCommandController(self.context)
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
            ctrl = tg_ui_plugin.TelegramCommandController(self.context)
            ctrl._last_update_id = self._last_update_id
            await ctrl._execute_manual_update_command(chat_id=chat_id)
            return

    async def _handle_callback_query(self, cb: Dict[str, Any]) -> None:
        ctrl = tg_ui_plugin.TelegramCommandController(self.context)
        ctrl._last_update_id = self._last_update_id
        ctrl._awaiting_seed_input_chats = self._awaiting_seed_input_chats
        await ctrl._handle_callback_query(cb)

    async def run_polling_loop(self) -> None:
        ctrl = tg_ui_plugin.TelegramCommandController(self.context)
        await ctrl.run_polling_loop()''',
    new_block=r'''        if first_token == "/reset_profit":
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
        await ctrl.run_polling_loop()''',
)


# ===========================================================================
# [15. main.py 패치 등록]
# ===========================================================================
register_patch(
    patch_id="P15_A1_CANDLE_RADAR_FRESH_TICK_SYNC",
    filename="main.py",
    description="Case 82/92/93 캔들 레이더 연산 완료 시 캐시 저장 직전 최신 실시간 틱 재합성으로 시세 역행 방지",
    old_block=r'''            metrics = await _compute_candle_metrics_dynamic(
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
                    context.candle_metrics_cache[MACRO_REF_SYMBOL] = qqq_metrics''',
    new_block=r'''            metrics = await _compute_candle_metrics_dynamic(
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
                    context.candle_metrics_cache[MACRO_REF_SYMBOL] = qqq_metrics''',
)

register_patch(
    patch_id="P15_A2_LIVE_ASSN_0400_DAILY_ROLLOVER",
    filename="main.py",
    description="Case 01/95 실전 암살자(LIVE) 단독 모드 시 04:00 EST 무간섭 3대 원장 일일 롤오버 수행",
    old_block=r'''            if 400 <= hm <= 406 and context.last_0400_sync_date != today_str:
                if is_live_assassin_standalone_active(context):
                    try:
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
                    context.last_0400_sync_date = today_str''',
    new_block=r'''            if 400 <= hm <= 406 and context.last_0400_sync_date != today_str:
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
                    context.last_0400_sync_date = today_str''',
)

register_patch(
    patch_id="P15_B1_TDD_LOG_10_TRUTH_GATES",
    filename="main.py",
    description="Case 97-A 부팅 3대 TDD 통과 로그의 순수 10대 진성 급락 게이트(10 Truth Gates) 표기 통일",
    old_block=r'''    logger.info(
        "✅ [QuantEngine TDD · Barbell 60/30/10 TDD · Assassin 14 Truth Gates TDD] 전수 검증 통과!"
    )''',
    new_block=r'''    logger.info(
        "✅ [QuantEngine TDD · Barbell 60/30/10 TDD · Assassin 10 Truth Gates TDD] 전수 검증 통과!"
    )''',
)

register_patch(
    patch_id="P15_B2_SHUTDOWN_CLOSE_TG_CLIENT",
    filename="main.py",
    description="종료 및 재기동 직전 텔레그램 비동기 HTTP 세션 정상 회수",
    old_block=r'''        try:
            await asyncio.wait_for(context.api.close(), timeout=1.5)
        except Exception:
            pass''',
    new_block=r'''        try:
            if hasattr(context.tg, "close"):
                await asyncio.wait_for(context.tg.close(), timeout=1.5)
        except Exception:
            pass

        try:
            await asyncio.wait_for(context.api.close(), timeout=1.5)
        except Exception:
            pass''',
)

_LOADED_PARTS.append(5)


# ===========================================================================
# [원자적 트랜잭션 패치 실행기 · 백업/롤백 · 서브프로세스 3대 TDD 검증 엔진]
# ===========================================================================
def verify_parts_assembled() -> Tuple[bool, str]:
    expected = [1, 2, 3, 4, 5]
    if _LOADED_PARTS != expected:
        return (
            False,
            f"패치 스크립트 분할 조립 순서 불일치: 현재={_LOADED_PARTS} != 정상={expected}",
        )
    return (
        True,
        f"전 5개 분할 블록 조립 무결성 확인 (총 {len(PATCH_ITEMS)}개 패치 항목)",
    )


def load_disk_core_modules(base_dir: str) -> Tuple[bool, Dict[str, str], str]:
    sources: Dict[str, str] = {}
    for fname in REQUIRED_CORE_MODULES:
        fpath = os.path.join(base_dir, fname)
        if not os.path.isfile(fpath):
            return False, {}, f"필수 코어 파일 누락: {fpath}"
        try:
            with open(fpath, "r", encoding="utf-8") as rf:
                sources[fname] = rf.read()
        except Exception as exc:
            return False, {}, f"파일 읽기 실패 ({fpath}): {exc}"
    return True, sources, "OK"


# NEW: Case 99 · Case 100 및 Step 1~3 진화 정본 상위 호환 시그니처 맵
_EVOLVED_SUPERSEDED_MARKERS: Dict[str, Tuple[str, ...]] = {
    "P02_A3_COMMISSION_DATE_FILTER": (
        'today_kst = datetime.now(KST_TZ).strftime("%Y-%m-%d")',
        "if e_dt and len(e_dt) == 10 and today_kst > e_dt:",
    ),
    "P13_C_AUTO_UPDATE_RECHECK_ORDERS": (
        "def _has_active_orders_or_live_assn_for_update(",
        "pending_restart_msg",
    ),
    "P08_B_SYNC_SELL_SAFE_CANCEL": (
        "SELL_PARTIAL_CANCEL_CONFIRMING",
        "SELL_CANCEL_IN_FLIGHT",
        "reset_sniper_l1_trail_slots",
    ),
    "P10_A1_MASKED_BP_AND_CASH10": (
        "BARBELL_100PCT_FULL_PORTION_TOPUP",
        "bp_excl_vault_safe",
        "usable_from_shield",
    ),
    "P10_A2_PENDING_SGOV_AUX_CASH": (
        "need_in_cash_b = max(cash_10_target, topup_shortfall)",
        "pre_shift = round(",
    ),
    "P10_B3_SGOV_BUY_UNLOCK_WHEN_INJECTED": (
        'not bool(st_soxl.get("waiting_reserve_deposit", False))',
        "BARBELL_CASH_10PCT_PRIORITIZED",
    ),
    "P11_B2_SYNC_LIVE_EXIT_DEADLOCK_AND_MOC": (
        "ASSASSIN_LIVE_EXIT_RE_SWEEP_ARMED",
        "wait_thr = 3.0 if hm_chk >= ASSASSIN_MOC_EXIT_HM else 5.0",
    ),
    "P11_D_RESET_TODAY_GT_WINS": (
        "today_gt_gate_dispatches=0,",
        "today_gt_gate_history=[],",
    ),
    "P12_A1_START_MSG_10G": (
        "바벨(60/30/10) &amp; 별도수익금고 상세",
        "[모의/실전] 암살자 순수 10G 상세",
    ),
    "P12_A2_SUB_VACANT_L1_SIG": (
        "def _format_sub_grid_stratum_lines(",
        "live_rsi_14: float = 50.0,",
        "sub_trail_ui: Optional[Dict[str, Any]] = None,",
    ),
    "P12_A3_SUB_VACANT_L1_BADGES": (
        "[서브1층: 공석]</b> 🛡️돌파차단 · 눌림(-1%",
        "돌파(RSI&lt;=50)",
    ),
    "P05_B_BARBELL_MARK_EQUITY_AND_GRAD_PROJ": (
        'reentry_pullback_ha_blocked',
        'sub_reentry_pullback_ha_blocked',
        'HOLD_PULLBACK_SHAVED_HA_BEAR',
    ),
    "P06_A_RSI_PREWARM_400_AND_1D": (
        'async def _get_live_soxl_reentry_snapshot(',
        'def mark_pullback_ha_bear_minute_wait(',
    ),
    "P12_B1_RADAR_PASS_RSI14": (
        'HOLD_PULLBACK_SHAVED_HA_BEAR',
        '무머리1분HA음봉 패스(다음1분 대기)',
        'closed_ha_ok: bool = True,',
    ),
    "P12_C2_REFRESH_METRICS_400_ASYNC": (
        'HOLD_PULLBACK_SHAVED_HA_BEAR',
        '무머리1분HA음봉 패스(다음1분 대기)',
        'closed_ha_ok: bool = True,',
    ),
    "P12_B2_RADAR_SUB_RSI_AND_10G_TEXT": (
        "sub_stratum_lines = _format_sub_grid_stratum_lines(",
        "live_rsi_14=rsi_14,",
    ),
    "P15_A1_CANDLE_RADAR_FRESH_TICK_SYNC": (
        "newest_lp = safe_float(",
        "newest_qqq_p = safe_float(",
    ),
    "P07_A_MASKED_BP_HELPER": (
        "def _resolve_masked_bp_for_soxl_sub_or_topup(",
        "get_masked_soxl_buying_power_usd",
    ),
    "P14_B1_BRIDGE_SHARED_CTRL_INIT": (
        "def _get_shared_ctrl(self)",
        "self._shared_ctrl = None",
    ),
    "P15_B2_SHUTDOWN_CLOSE_TG_CLIENT": (
        'if hasattr(context.tg, "close"):',
        "await asyncio.wait_for(context.tg.close(), timeout=1.5)",
    ),
}


def build_patched_ram_sources(
    disk_sources: Dict[str, str],
) -> Tuple[bool, Dict[str, str], List[str], int, int]:
    ram_sources: Dict[str, str] = dict(disk_sources)
    logs: List[str] = []
    applied_cnt = 0
    already_cnt = 0

    for item in PATCH_ITEMS:
        cur_src = ram_sources[item.filename]
        match_cnt = cur_src.count(item.old_block)
        sup_markers = _EVOLVED_SUPERSEDED_MARKERS.get(item.patch_id)
        # MODIFIED: new_block 내부에 old_block 이 포함된 패치의 무한 중복 주입 원천 차단
        if item.new_block in cur_src:
            already_cnt += 1
            logs.append(
                f"  ⏭️ [SKIP · 기적용] {item.patch_id:<26} ({item.filename})"
            )
        elif sup_markers and all(m in cur_src for m in sup_markers):
            already_cnt += 1
            logs.append(
                f"  ⏭️ [SKIP · 상위정본] {item.patch_id:<24} ({item.filename})"
            )
        elif match_cnt == 1:
            ram_sources[item.filename] = cur_src.replace(
                item.old_block, item.new_block, 1
            )
            applied_cnt += 1
            logs.append(
                f"  ✅ [APPLY] {item.patch_id:<34} ({item.filename}) — {item.description}"
            )
        else:
            logs.append(
                f"  ❌ [MISMATCH] {item.patch_id} ({item.filename}): "
                f"old_block 매칭 횟수={match_cnt} (기대값=1)"
            )
            return False, ram_sources, logs, applied_cnt, already_cnt

    return True, ram_sources, logs, applied_cnt, already_cnt


def _atomic_write_text_file(target_path: str, content: str) -> None:
    parent_d = os.path.dirname(os.path.abspath(target_path))
    if parent_d and not os.path.isdir(parent_d):
        os.makedirs(parent_d, exist_ok=True)
    st_mode = (
        os.stat(target_path).st_mode if os.path.isfile(target_path) else None
    )
    tmp_path = f"{target_path}.audit_patch.tmp.{os.getpid()}"
    try:
        with open(tmp_path, "w", encoding="utf-8") as wf:
            wf.write(content)
            wf.flush()
            os.fsync(wf.fileno())
        if st_mode is not None:
            os.chmod(tmp_path, st_mode)
        os.replace(tmp_path, target_path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        raise


def create_py_backup_snapshot(base_dir: str) -> str:
    backup_root = os.path.join(base_dir, "patch_backups")
    ts_slug = datetime.now().strftime("v3_audit_%Y%m%d_%H%M%S")
    snap_dir = os.path.join(backup_root, ts_slug)
    os.makedirs(snap_dir, exist_ok=True)

    for fname in REQUIRED_CORE_MODULES:
        src_fp = os.path.join(base_dir, fname)
        dst_fp = os.path.join(snap_dir, fname)
        shutil.copy2(src_fp, dst_fp)

    latest_ptr = os.path.join(backup_root, "LATEST_BACKUP.txt")
    _atomic_write_text_file(latest_ptr, f"{snap_dir}\n")
    return snap_dir


def restore_from_backup_dir(base_dir: str, snap_dir: str) -> Tuple[bool, str]:
    if not snap_dir or not os.path.isdir(snap_dir):
        return False, f"백업 디렉토리를 찾을 수 없습니다: {snap_dir}"
    restored = 0
    for fname in REQUIRED_CORE_MODULES:
        bak_fp = os.path.join(snap_dir, fname)
        if not os.path.isfile(bak_fp):
            return False, f"백업 파일 누락: {bak_fp}"
    for fname in REQUIRED_CORE_MODULES:
        bak_fp = os.path.join(snap_dir, fname)
        dst_fp = os.path.join(base_dir, fname)
        with open(bak_fp, "r", encoding="utf-8") as rf:
            orig_txt = rf.read()
        _atomic_write_text_file(dst_fp, orig_txt)
        restored += 1
    return True, f"백업 원복 완료 ({restored}개 코어 파일 복원 <- {snap_dir})"


def resolve_latest_backup_dir(base_dir: str) -> str:
    backup_root = os.path.join(base_dir, "patch_backups")
    ptr_fp = os.path.join(backup_root, "LATEST_BACKUP.txt")
    if os.path.isfile(ptr_fp):
        try:
            with open(ptr_fp, "r", encoding="utf-8") as rf:
                cand = rf.read().strip()
            if cand and os.path.isdir(cand):
                return cand
        except Exception:
            pass
    cands = sorted(glob.glob(os.path.join(backup_root, "v3_audit_*")))
    return cands[-1] if cands else ""


def run_post_apply_subprocess_tdd(base_dir: str) -> Tuple[bool, str]:
    updater_fp = os.path.join(base_dir, "plugin_updater.py")
    p1 = subprocess.run(
        [
            sys.executable,
            "-B",
            updater_fp,
            "--verify-only",
            "--base-dir",
            base_dir,
        ],
        cwd=base_dir,
        capture_output=True,
        text=True,
        timeout=30.0,
    )
    if p1.returncode != 0:
        err_msg = (p1.stdout or "") + "\n" + (p1.stderr or "")
        return False, f"plugin_updater --verify-only 실패:\n{err_msg.strip()}"

    regression_code = (
        "import asyncio\n"
        "from datetime import datetime\n"
        "import numpy as np\n"
        "from toss_api_core import EST_TZ, GlobalThrottle\n"
        "from quant_indicators_plugin import (\n"
        "    _compute_vectorized_heikin_ashi_and_rsi,\n"
        "    refresh_metrics_with_live_tick,\n"
        ")\n"
        "from quant_engine import (\n"
        "    StratumBucket,\n"
        "    has_active_l1_bucket,\n"
        "    run_quant_engine_tdd,\n"
        "    summarize_stratum_portfolio,\n"
        "    vrev_add_quota_lot_and_merge_2tier,\n"
        ")\n"
        "from barbell_plugin import run_barbell_plugin_tdd\n"
        "from assassin_plugin import run_assassin_plugin_tdd\n"
        "assert run_quant_engine_tdd() is True\n"
        "assert run_barbell_plugin_tdd() is True\n"
        "assert run_assassin_plugin_tdd() is True\n"
        "async def _chk_lock():\n"
        "    lk = GlobalThrottle.get_file_lock('/tmp/v3_audit_lock_test.lock')\n"
        "    async with lk:\n"
        "        pass\n"
        "    with lk:\n"
        "        with lk:\n"
        "            pass\n"
        "asyncio.run(_chk_lock())\n"
        "arr = np.array([50.0, 49.9, 49.8], dtype=float)\n"
        "r_info = _compute_vectorized_heikin_ashi_and_rsi(arr, arr, arr, arr)\n"
        "assert r_info['rsi_14'] == 50.0 and r_info['rsi_ready'] is False\n"
        "m_tick = refresh_metrics_with_live_tick(\n"
        "    {}, 52.0, now_est=datetime(2026, 11, 11, 7, 30, tzinfo=EST_TZ)\n"
        ")\n"
        "assert m_tick['pre_open_price'] == 0.0\n"
        "assert not bool(m_tick.get('found_true_pre_open', False))\n"
        "up_q = [\n"
        "    StratumBucket(10, 50.0, 500.0, 500.0, 1, 'GRID_L2'),\n"
        "    StratumBucket(10, 55.0, 550.0, 550.0, 1, 'GRID_L3'),\n"
        "]\n"
        "res_m = vrev_add_quota_lot_and_merge_2tier(\n"
        "    up_q, 10, 52.0, 520.0, 'MANUAL_SYNC_L1'\n"
        ")\n"
        "assert has_active_l1_bucket(res_m) is False\n"
        "assert [b.book_price for b in res_m] == [50.0, 52.0, 55.0]\n"
        "s_bb = summarize_stratum_portfolio({\n"
        "    'buckets': [], 'sub_buckets': [], 'initial_seed_usd': 10000.0,\n"
        "    'portion_mode': 'BARBELL_60_30_10',\n"
        "    'cumulative_realized_net_usd': 1250.0,\n"
        "    'vaulted_profit_locked_usd': 250.0,\n"
        "}, live_price=50.0)\n"
        "assert abs(s_bb['mark_equity_usd'] - 11250.0) < 1e-4\n"
        "import inspect, tempfile, time\n"
        "import quant_indicators_plugin as qi\n"
        "import barbell_plugin as bp\n"
        "import assassin_plugin as ap\n"
        "tmp_d = tempfile.mkdtemp()\n"
        "bl = bp.BarbellLedger(base_dir=tmp_d)\n"
        "bst = bl.update_state_sync(last_sgov_action_mono=time.monotonic() + 9e8)\n"
        "assert bst['last_sgov_action_mono'] == 0.0\n"
        "c102_mid = bp.compute_realtime_barbell_stratum_rebalance(10000.0, 6500.0, 2500.0, 6, is_graduated_zero=False)\n"
        "assert c102_mid['pending_sgov_buy_budget_usd'] == 0.0 and abs(c102_mid['cash_bucket_usd'] - 2000.0) < 1e-6\n"
        "c102_end = bp.compute_realtime_barbell_stratum_rebalance(10000.0, 0.0, 0.0, 0, prev_cash_bucket_usd=2000.0, sgov_held_qty=10, sgov_invested_usd=1000.0, is_graduated_zero=True)\n"
        "assert abs(c102_end['cash_bucket_usd'] - 1000.0) < 1e-6 and abs(c102_end['pending_sgov_buy_budget_usd'] - 1000.0) < 1e-6\n"
        "al = ap.AssassinSimLedger(base_dir=tmp_d)\n"
        "ast_m = al.update_state_sync(\n"
        "    pending_buy_mono=time.monotonic() + 9e8,\n"
        "    gt_active_gate_scout={'round_no': 1, 'entry_price': 50.0},\n"
        ")\n"
        "assert ast_m['pending_buy_mono'] <= time.monotonic() + 1.0\n"
        "ast_r = asyncio.run(al.reset_assassin_stats_only(10000.0))\n"
        "assert ast_r['gt_active_gate_scout'] is None\n"
        "assert 'REPLACE_REJECTED' in inspect.getsource(ap._sync_live_pending_exit_order)\n"
        "qi._LIVE_1M_BAR_STORE['AUDIT_T'] = []\n"
        "qi._record_live_tick_to_memory_bar('AUDIT_T', 50.0, datetime(2026, 11, 13, 9, 34, 58, tzinfo=EST_TZ))\n"
        "qi._record_live_tick_to_memory_bar('AUDIT_T', 51.0, datetime(2026, 11, 13, 9, 35, 1, tzinfo=EST_TZ))\n"
        "mk_a, cnt_a = qi._record_live_tick_to_memory_bar('AUDIT_T', 52.0, datetime(2026, 11, 13, 9, 34, 59, tzinfo=EST_TZ))\n"
        "assert mk_a == '2026-11-13 09:35' and cnt_a == 2\n"
        "qi._LIVE_1M_BAR_STORE.pop('AUDIT_T', None)\n"
        "print('ALL_SUBPROCESS_TDD_AND_AUDIT_REGRESSIONS_PASSED')\n"
    )
    p2 = subprocess.run(
        [sys.executable, "-B", "-c", regression_code],
        cwd=base_dir,
        capture_output=True,
        text=True,
        timeout=30.0,
    )
    if p2.returncode != 0:
        err_msg2 = (p2.stdout or "") + "\n" + (p2.stderr or "")
        return False, f"3대 코어 TDD / 회귀 검증 실패:\n{err_msg2.strip()}"

    return True, f"{(p1.stdout or '').strip()} | {(p2.stdout or '').strip()}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Infinite Snowball v3.0 — 5단계 감사 결함 원자적 패치기"
    )
    parser.add_argument(
        "--base-dir",
        type=str,
        default=DEFAULT_TARGET_DIR,
        help="대상 봇 디렉토리 (기본값: /home/pipiosToss)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="디스크 수정 없이 매칭·컴파일·Case 85·AST 검증만 수행",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="백업 생성 후 원자적 패치 적용 및 3대 TDD 서브프로세스 검증 실행",
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="직전 백업 스냅샷으로 15대 코어 모듈 즉시 원복",
    )
    parser.add_argument(
        "--backup-dir",
        type=str,
        default="",
        help="--rollback 시 특정 백업 폴더 지정 (미지정 시 최신 백업 선택)",
    )
    args = parser.parse_args()
    base_dir = os.path.abspath(args.base_dir)

    print("=" * 88)
    print(
        f"🐂 Infinite Snowball v3.0 — Audit Patch Engine (Target: {base_dir})"
    )
    print("=" * 88)

    ok_parts, parts_msg = verify_parts_assembled()
    if not ok_parts:
        print(f"🚨 {parts_msg}", file=sys.stderr)
        return 1
    print(f"📦 {parts_msg}")

    if args.rollback:
        target_bak = args.backup_dir or resolve_latest_backup_dir(base_dir)
        ok_rb, rb_msg = restore_from_backup_dir(base_dir, target_bak)
        if not ok_rb:
            print(f"🚨 롤백 실패: {rb_msg}", file=sys.stderr)
            return 1
        print(f"♻️ {rb_msg}")
        ok_v, v_msg = run_post_apply_subprocess_tdd(base_dir)
        print(f"🔍 롤백 후 검증: {v_msg}")
        return 0 if ok_v else 1

    ok_load, disk_sources, load_msg = load_disk_core_modules(base_dir)
    if not ok_load:
        print(f"🚨 {load_msg}", file=sys.stderr)
        return 1

    ok_match, ram_sources, patch_logs, applied_cnt, already_cnt = (
        build_patched_ram_sources(disk_sources)
    )
    for line in patch_logs:
        print(line)

    if not ok_match:
        print(
            "\n🚨 [중단] 매칭 불일치 항목이 있어 디스크 파일을 1 Byte도 수정하지 않았습니다.",
            file=sys.stderr,
        )
        return 1

    ok_ram, ram_errors = verify_ram_modules_integrity(ram_sources)
    if not ok_ram:
        print(
            "\n🚨 [중단] RAM 선행 컴파일 / AST 교차 검증 실패:",
            file=sys.stderr,
        )
        for err in ram_errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    changed_files = [
        fn
        for fn in REQUIRED_CORE_MODULES
        if ram_sources[fn] != disk_sources[fn]
    ]
    print("-" * 88)
    print(
        f"🛡️ RAM 인메모리 선행 검증 통과! "
        f"(신규적용={applied_cnt}건 · 기적용={already_cnt}건 · 변경파일={len(changed_files)}개)"
    )

    if not args.apply:
        print(
            "💡 현재 모의 점검(--dry-run) 모드입니다. 실제 반영하려면 아래 명령을 실행하세요:"
        )
        print(
            f"   python3 {os.path.abspath(__file__)} --apply --base-dir {base_dir}"
        )
        return 0

    if not changed_files:
        print(
            "✅ 모든 패치가 이미 적용되어 있습니다. 추가 디스크 쓰기 없이 TDD만 검증합니다."
        )
        ok_tdd, tdd_msg = run_post_apply_subprocess_tdd(base_dir)
        print(
            f"🏆 검증 결과: {tdd_msg}" if ok_tdd else f"🚨 검증 실패: {tdd_msg}"
        )
        return 0 if ok_tdd else 1

    snap_dir = create_py_backup_snapshot(base_dir)
    print(f"💾 원본 15대 코어 모듈 스냅샷 백업 완료: {snap_dir}")

    try:
        for fn in changed_files:
            target_fp = os.path.join(base_dir, fn)
            _atomic_write_text_file(target_fp, ram_sources[fn])
    except Exception as write_exc:
        print(
            f"🚨 파일 교체 중 예외 발생 -> 즉시 자동 롤백 실행: {write_exc}",
            file=sys.stderr,
        )
        restore_from_backup_dir(base_dir, snap_dir)
        return 1

    ok_tdd, tdd_msg = run_post_apply_subprocess_tdd(base_dir)
    if not ok_tdd:
        print(
            f"🚨 사후 서브프로세스 TDD 검증 실패 -> 즉시 원본 백업 자동 롤백:\n{tdd_msg}",
            file=sys.stderr,
        )
        restore_from_backup_dir(base_dir, snap_dir)
        return 1

    print("=" * 88)
    print(
        f"🏆 패치 원자적 반영 및 3대 TDD + 감사 회귀 검증 100% 통과! "
        f"({len(changed_files)}개 파일 업데이트)"
    )
    print(f"   {tdd_msg}")
    print(
        "   (※ 3대 원장 JSON 및 .env 파일은 0 Byte 불변 상태로 100% 보호되었습니다)"
    )
    print("=" * 88)
    return 0


if __name__ == "__main__":
    sys.exit(main())
