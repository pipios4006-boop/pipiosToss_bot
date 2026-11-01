# -*- coding: utf-8 -*-
"""
# NEW: toss_api_core.py
인피니트 스노우볼 (Infinite Snowball) v3.0 — 토스증권 코어 상수 · 폴더 격리 · 디스크 자가 치유 ·
GlobalThrottle 동시성 통제 및 SOXL 7-Tier 골디락스 멀티 그리드 / 독립 골든포켓 3중 원장(SoxlStratumLedger) 코어 모듈 (Part 1 / 2 · Step 01 / 11)
- 역할:
  1) 제4헌법 EST 단일 타임존 및 최종 확정 챔피언(Case 01 ~ Case 86) 전역 상수 락온
  2) 안전한 수치 형변환(safe_float, safe_int), 36자 멱등성 키 생성기(generate_client_order_id),
     4xx 비재시도 예외(_NonRetryableApiError) 및 계좌별 미국 주식 수수료율 런타임 캐시 동기화기(Case 86)
  3) 폴더 위치(base_dir) 기반 자동 식별기(get_bot_base_dir, get_folder_slug, resolve_folder_isolated_ledger_paths),
     격리 환경변수 로더(_load_env_files_into_environ) 및 클라우드 VM 디스크 고갈(Errno 28) 자가 치유기(emergency_free_disk_space_sync · Case 68, Case 75, Case 85)
  4) 제1헌법 동기/비동기 양방향 호환 _HybridFileLock 및 GlobalThrottle 중앙 통제소(Case 06, Case 20)
  5) SOXL 단일 롱 7-Tier 순수 멀티 그리드 및 독립 골든포켓(GoldenAllInPocket) 폴더별 3중 안전 지층 원장(SoxlStratumLedger · Case 58 ~ Case 86)
"""

from __future__ import annotations

import asyncio
import errno
import glob
import json
import logging
import math
import os
import re
import shutil
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger("toss_sniper.toss_api_core")

# ---------------------------------------------------------------------------
# [핵심 상수] 제4헌법 EST 단일 타임존 & 최종 확정 진화 챔피언 (Case 72 ~ 86) 전역 상수
# ---------------------------------------------------------------------------
EST_TZ = ZoneInfo("America/New_York")
KST_TZ = ZoneInfo("Asia/Seoul")

TARGET_SYMBOL: str = "SOXL"
REAL_ALLOWED_SYMBOLS: Tuple[str, ...] = ("SOXL",)
ALLOWED_SYMBOLS: Tuple[str, ...] = ("SOXL",)

DEFAULT_INITIAL_SEED_USD: float = 10000.0
PORTION_RATIO_LOCKED: float = 0.08
BASE_MAX_LOTS_8PCT: int = 12

# Case 72: 골디락스 7-Layer (1층 공격수 + 2 ~ 6층 개별 완충층 + 통합 7층 본대) 상수 락온
# (타 모듈 AST 임포트 무결성 100% 호환을 위해 MAX_GRID_TIERS_12 도 7 로 동시 매핑)
MAX_GRID_TIERS_7: int = 7
MAX_GRID_TIERS: int = 7
MAX_GRID_TIERS_12: int = 7

# Case 76: 🔓 06_STEP2X_15PCT_C20 3중 안전문 기반 조건부 스텝업 저가 해금 전역 상수 락온
DEFAULT_UNLOCK_MODE: str = "STEP2X_15PCT_C20"
STEP_UP_2X_MIN_REBOUND_MULT: float = 2.0
STEP_UP_2X_MAX_TIERS: int = 2
STEP_UP_2X_MIN_CASH_RATIO: float = 0.20
STEP_UP_2X_DROP_PCT: float = 15.0

# Case 77: 💉 05_RESV_6P_GUARD30 (30% 자투리 1주 승격 방지 가드 & 최대 +6회분 온디맨드 예비시드 자동 수혈) 상수 락온
MAX_RESERVE_PORTIONS: int = 6
MIN_DIP_BUDGET_RATIO: float = 0.30
MIN_DIP_VS_L1_RATIO: float = 0.30
RESERVE_DEPOSIT_TOLERANCE_RATIO: float = 0.95

# [Case 80 : 미동부 프리장 황금시간대(07:00 ~ 07:50 EST & RSI(14) <= 19.0) 가용시드 100% 전액 추가매수 상수]
# 기본값은 "NONE" (OFF) 으로 락온하여 QuantEngine TDD 정합성 100% 보장
GOLDEN_ALLIN_MODES: Tuple[str, ...] = (
    "NONE",
    "POCKET_ALLIN",
    "GRID_L1_ALLIN",
)
DEFAULT_GOLDEN_ALLIN_MODE: str = "NONE"
GOLDEN_WINDOW_START_HM: int = 700
GOLDEN_WINDOW_END_HM: int = 750
GOLDEN_RSI_MAX_THRESHOLD: float = 19.0
GOLDEN_POCKET_RISE_PCT: float = 1.50

# MODIFIED [Case 84 : 정규장 마감 30분 전(15:30 ~ 16:00 EST) 오직 0주 새 사이클 첫 1층 진입만 차단하는 기준 시각(HHMM)]
NEW_CYCLE_BUY_CUTOFF_HM: int = 1530

LOCKED_BUY_INTERVAL_MIN: int = 10
LOCKED_SELL_INTERVAL_MIN: int = 1
DEFAULT_US_COMMISSION_RATE: float = 0.0007
ROUND_TRIP_FEE_RATE: float = 0.0014
ROUND_TRIP_FEE_RATE_PCT: float = 0.14
REANCHOR_NET_BUFFER_MULT: float = 0.994
KRW_PER_USD_DEFAULT: float = 1380.0

TOSS_OPENAPI_BASE_URL: str = "https://openapi.tossinvest.com"

# Case 86: 계좌별 런타임 왕복 수수료율(%) 동적 캐시
_RUNTIME_FEE_LOCK = threading.RLock()
_RUNTIME_US_COMMISSION_RATE: float = DEFAULT_US_COMMISSION_RATE
_RUNTIME_ROUND_TRIP_FEE_RATE_PCT: float = ROUND_TRIP_FEE_RATE_PCT


# ---------------------------------------------------------------------------
# [유틸리티] 안전한 수치 형변환 및 런타임 수수료율 동기화기 (Case 03, 23, 86)
# ---------------------------------------------------------------------------
def safe_float(val: Any, default: float = 0.0) -> float:
    if val is None or isinstance(val, bool):
        return float(default)
    try:
        if isinstance(val, str):
            cleaned = (
                val.replace(",", "").replace("$", "").replace("%", "").strip()
            )
            if not cleaned:
                return float(default)
            f_val = float(cleaned)
        else:
            f_val = float(val)
        if math.isnan(f_val) or math.isinf(f_val):
            return float(default)
        return f_val
    except Exception:
        return float(default)


def safe_int(val: Any, default: int = 0) -> int:
    if val is None or isinstance(val, bool):
        return int(default)
    try:
        f_val = safe_float(val, float(default))
        return (
            int(round(f_val))
            if abs(f_val - round(f_val)) < 1e-6
            else int(math.floor(f_val))
        )
    except Exception:
        return int(default)


def _read_env_us_commission_rates() -> Tuple[float, float]:
    """
    # NEW [Case 86 : 환경변수(.env) 기반 미국 주식 수수료율 폴백 로더]:
    US_COMMISSION_RATE (소수 비율, 예: 0.0007 또는 0.001) 또는
    ROUND_TRIP_FEE_RATE_PCT (%, 예: 0.14 또는 0.20)가 .env 에 설정된 경우 이를 우선 폴백값으로 반환한다.
    """
    env_one = safe_float(os.environ.get("US_COMMISSION_RATE"), 0.0)
    env_rt = safe_float(os.environ.get("ROUND_TRIP_FEE_RATE_PCT"), 0.0)
    if 0.0 < env_one <= 0.01:
        one_r = round(env_one, 6)
        rt_p = (
            round(env_rt, 4)
            if (0.0 < env_rt <= 2.0)
            else round(one_r * 200.0, 4)
        )
        return one_r, rt_p
    if 0.0 < env_rt <= 2.0:
        rt_p = round(env_rt, 4)
        one_r = round((rt_p / 100.0) * 0.5, 6)
        return one_r, rt_p
    return DEFAULT_US_COMMISSION_RATE, ROUND_TRIP_FEE_RATE_PCT


def get_runtime_us_commission_rate() -> float:
    """
    현재 프로세스에 락온된 미국 주식 편도 수수료율(소수 비율, 예: 0.0007 또는 0.001)을 반환한다.
    """
    with _RUNTIME_FEE_LOCK:
        return _RUNTIME_US_COMMISSION_RATE


def get_runtime_round_trip_fee_rate_pct() -> float:
    """
    현재 프로세스에 락온된 미국 주식 왕복 수수료율(%, 예: 0.14 또는 0.20)을 반환한다.
    """
    with _RUNTIME_FEE_LOCK:
        return _RUNTIME_ROUND_TRIP_FEE_RATE_PCT


def set_runtime_round_trip_fee_rate_pct(
    round_trip_pct: float,
    us_commission_rate: Optional[float] = None,
) -> float:
    """
    GET /api/v1/commissions 또는 원장에서 확인된 계좌별 왕복 수수료율(%)을 런타임 메모리에 동기화한다.
    """
    global _RUNTIME_US_COMMISSION_RATE, _RUNTIME_ROUND_TRIP_FEE_RATE_PCT
    clean_rt = safe_float(round_trip_pct, ROUND_TRIP_FEE_RATE_PCT)
    if clean_rt <= 0.0 or clean_rt > 2.0:
        clean_rt = ROUND_TRIP_FEE_RATE_PCT
    clean_rt = round(clean_rt, 4)

    if us_commission_rate is not None:
        clean_one = safe_float(us_commission_rate, DEFAULT_US_COMMISSION_RATE)
        if clean_one <= 0.0 or clean_one > 0.01:
            clean_one = round((clean_rt / 100.0) * 0.5, 6)
        else:
            clean_one = round(clean_one, 6)
    else:
        clean_one = round((clean_rt / 100.0) * 0.5, 6)

    with _RUNTIME_FEE_LOCK:
        _RUNTIME_US_COMMISSION_RATE = clean_one
        _RUNTIME_ROUND_TRIP_FEE_RATE_PCT = clean_rt
        return _RUNTIME_ROUND_TRIP_FEE_RATE_PCT


def generate_client_order_id(prefix: str = "SNIPER") -> str:
    """
    🚨 제5헌법:
    토스증권 주문 생성 시 최대 36자 영숫자 및 '-', '_' 로 구성된 고유 멱등성 키(clientOrderId)를 생성한다.
    """
    clean_prefix = "".join(
        ch for ch in str(prefix or "ORD").upper() if ch.isalnum()
    )[:8]
    ts_part = int(time.time() * 1000) % 100000000
    rand_part = uuid.uuid4().hex[:12]
    cid = f"{clean_prefix}-{ts_part}-{rand_part}"
    return cid[:36]


class _NonRetryableApiError(Exception):
    """
    🚨 Case 21:
    4xx 클라이언트 비즈니스 에러(400, 401, 403, 404, 409, 415, 422) 발생 시
    불필요한 재시도 없이 즉시 탈출하기 위한 전용 예외 클래스.
    """

    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        raw_body: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.status_code = int(status_code)
        self.error_code = str(error_code or "unknown-error")
        self.message = str(message or "")
        self.raw_body = raw_body or {}
        super().__init__(
            f"[HTTP {self.status_code} · {self.error_code}] {self.message}"
        )


# ---------------------------------------------------------------------------
# [Case 68, Case 75 & Case 85] 폴더 위치(base_dir) 기반 자동 식별기 · 격리 환경변수 로더 · 디스크 자가 치유기
# ("/home/pipiosToss" 고정 경로 하드코딩 100% 영구 소각)
# ---------------------------------------------------------------------------
def get_bot_base_dir(explicit_dir: Optional[str] = None) -> str:
    """
    🚨 Case 68:
    고정 경로("/home/pipiosToss")를 절대 참조하지 않고, 오직 현재 봇 스크립트가 위치한
    실제 물리적 폴더(base_dir)의 절대 경로를 반환한다.
    """
    if explicit_dir and str(explicit_dir).strip():
        cand = os.path.abspath(str(explicit_dir).strip())
        if os.path.isfile(cand):
            return os.path.dirname(cand)
        return cand
    return os.path.abspath(os.path.dirname(os.path.abspath(__file__)) or ".")


def get_folder_slug(base_dir: Optional[str] = None) -> str:
    """
    🚨 Case 68:
    현재 봇이 실행 중인 폴더명(예: /home/pipiosToss_family1 -> "pipiosToss_family1")을
    안전한 파일명 식별자(slug)로 정규화하여 반환한다.
    """
    target_dir = get_bot_base_dir(base_dir)
    raw_name = os.path.basename(os.path.normpath(target_dir)).strip()
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name).strip("._-")
    return slug if slug else "default_bot"


def resolve_folder_isolated_ledger_paths(
    base_dir: Optional[str] = None,
    explicit_filepath: Optional[str] = None,
) -> Tuple[str, str, str, str]:
    """
    🚨 Case 68 & Case 85 [폴더별 3중 안전 원장 경로 결정기]:
    단일 서버 내 여러 폴더에서 다중 봇을 운영할 때 각 폴더 위치를 기준으로:
    1) primary_path : <base_dir>/soxl_stratum_ledger_<folder_slug>.json (Git 추적 면역 폴더 고유 원장)
    2) legacy_path  : <base_dir>/soxl_stratum_ledger.json (하위 호환 미러 원장)
    3) backup_path  : <base_dir>/ledger_backups/soxl_stratum_ledger_<folder_slug>.bak.json (실시간 백업 금고)
    4) folder_slug  : 현재 폴더 식별자 문자열
    을 산출하여 반환한다.
    """
    if explicit_filepath and str(explicit_filepath).strip():
        raw_fp = str(explicit_filepath).strip()
        if os.path.isabs(raw_fp):
            target_dir = os.path.dirname(raw_fp) or get_bot_base_dir(base_dir)
        else:
            target_dir = get_bot_base_dir(base_dir)
    else:
        target_dir = get_bot_base_dir(base_dir)

    folder_slug = get_folder_slug(target_dir)
    primary_path = os.path.join(
        target_dir, f"soxl_stratum_ledger_{folder_slug}.json"
    )
    legacy_path = os.path.join(target_dir, "soxl_stratum_ledger.json")
    backup_dir = os.path.join(target_dir, "ledger_backups")
    backup_path = os.path.join(
        backup_dir, f"soxl_stratum_ledger_{folder_slug}.bak.json"
    )
    return primary_path, legacy_path, backup_path, folder_slug


def emergency_free_disk_space_sync(
    base_dir: Optional[str] = None,
    keep_backup_days: int = 7,
    remove_pycache: bool = True,
) -> int:
    """
    # [Case 75 : 디스크 고갈(Errno 28 · No space left on device) 원천 방어 및 고아 파일 자가 치유기]:
    1) target_dir 및 ledger_backups/ 내에 남아 있는 모든 고아 임시 파일
       (*.tmp.*, *.restore.tmp.*, *.ack.tmp.*, *.heal.tmp)을 즉시 삭제한다.
    2) remove_pycache=True 일 때 target_dir/__pycache__ 내의 *.pyc, *.pyo 바이트코드 캐시를 청소하여
       디스크 블록 및 Inode 고갈을 방지한다.
    3) ledger_backups/ 내 일일 스냅샷(soxl_stratum_ledger_*_20*.json)이 keep_backup_days 개수를 초과하면
       오래된 스냅샷부터 자동 정리한다.
    반환값: 삭제된 파일/디렉토리 총 개수
    """
    target_dir = get_bot_base_dir(base_dir)
    backup_dir = os.path.join(target_dir, "ledger_backups")
    removed_cnt = 0

    tmp_patterns = (
        os.path.join(target_dir, "*.tmp.*"),
        os.path.join(target_dir, ".*.tmp.*"),
        os.path.join(target_dir, "*.heal.tmp"),
        os.path.join(backup_dir, "*.tmp.*"),
        os.path.join(backup_dir, ".*.tmp.*"),
    )
    for pat in tmp_patterns:
        for fp in glob.glob(pat):
            try:
                if os.path.isfile(fp):
                    os.remove(fp)
                    removed_cnt += 1
            except Exception:
                pass

    if remove_pycache:
        pycache_dir = os.path.join(target_dir, "__pycache__")
        if os.path.isdir(pycache_dir):
            try:
                shutil.rmtree(pycache_dir, ignore_errors=True)
                removed_cnt += 1
            except Exception:
                for pyc_fp in glob.glob(os.path.join(pycache_dir, "*")):
                    try:
                        os.remove(pyc_fp)
                        removed_cnt += 1
                    except Exception:
                        pass

    if os.path.isdir(backup_dir):
        try:
            snap_pat = os.path.join(
                backup_dir, "soxl_stratum_ledger_*_20*.json"
            )
            snaps = sorted(glob.glob(snap_pat))
            keep_n = max(2, safe_int(keep_backup_days, 7))
            if len(snaps) > keep_n:
                for old_fp in snaps[: len(snaps) - keep_n]:
                    try:
                        os.remove(old_fp)
                        removed_cnt += 1
                    except Exception:
                        pass
        except Exception:
            pass

    return removed_cnt


def _load_env_files_into_environ(
    base_dir: Optional[str] = None,
    override_existing: bool = False,
) -> str:
    """
    🚨 Case 68 & Case 86:
    "/home/pipiosToss" 고정 경로 폴백을 100% 폐기하고, 오직 해당 봇이 위치한 폴더(target_dir)의
    .env 및 설정 JSON 파일만 로드하여 폴더 간 환경변수 교차 오염을 원천 차단한다.
    """
    target_dir = get_bot_base_dir(base_dir)
    if not os.path.isdir(target_dir):
        return target_dir

    env_fp = os.path.join(target_dir, ".env")
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
                    if k and (override_existing or k not in os.environ):
                        os.environ[k] = v
        except Exception:
            pass

    for json_name in ("config.json", "secrets.json", "toss_config.json"):
        j_fp = os.path.join(target_dir, json_name)
        if os.path.isfile(j_fp):
            try:
                with open(j_fp, "r", encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, (str, int, float)):
                            k_str = str(k).strip()
                            if k_str and (
                                override_existing or k_str not in os.environ
                            ):
                                os.environ[k_str] = str(v)
            except Exception:
                pass

    env_one, env_rt = _read_env_us_commission_rates()
    set_runtime_round_trip_fee_rate_pct(env_rt, us_commission_rate=env_one)
    return target_dir


_load_env_files_into_environ()


# ---------------------------------------------------------------------------
# [제1헌법] _HybridFileLock 및 GlobalThrottle (동기/비동기 양방향 호환 중앙 통제)
# ---------------------------------------------------------------------------
class _HybridFileLock:
    """
    🚨 제1헌법 & Case 06:
    일반 동기 `with GlobalThrottle.get_file_lock(path):` 와
    비동기 `async with GlobalThrottle.get_file_lock(path):` 를 모두 지원하는 하이브리드 락.
    """

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
    """
    🚨 제1헌법 & Case 20:
    모든 API 호출 전 그룹별 최소 호출 간격(Rate Limit)을 강제하고,
    모든 로컬 파일 I/O 시 파일 경로별 상호 배제 Lock 을 제공한다.
    """

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
            cls._last_call_mono[grp] = time.monotonic()

    @classmethod
    async def wait_api(cls, group: str = "DEFAULT") -> None:
        await asyncio.to_thread(cls.wait_api_sync, group)

    @classmethod
    def get_file_lock(cls, filepath: str) -> _HybridFileLock:
        abs_p = os.path.abspath(str(filepath or "default.lock"))
        with cls._file_locks_guard:
            lock_obj = cls._file_locks.get(abs_p)
            if lock_obj is None:
                lock_obj = _HybridFileLock()
                cls._file_locks[abs_p] = lock_obj
            return lock_obj


# ---------------------------------------------------------------------------
# [핵심 2] SOXL 단일 롱 7-Tier 순수 멀티 그리드 및 골든포켓 폴더별 3중 안전 지층 원장 (SoxlStratumLedger — Case 68 ~ 86)
# ---------------------------------------------------------------------------
class SoxlStratumLedger:
    """
    🎯 1 ~ 🎯 5 & Case 02, 05, 06, 58 ~ 86:
    현재 봇이 위치한 폴더(`base_dir`)를 기준으로:
    ① 폴더 고유 원장(`soxl_stratum_ledger_<folder_slug>.json` — Git 덮어쓰기 100% 면역)
    ② 표준 호환 원장(`soxl_stratum_ledger.json` — 기존 코드 및 외부 도구 호환 미러)
    ③ 실시간 백업 금고(`ledger_backups/soxl_stratum_ledger_<folder_slug>.bak.json`)
    3곳에 SOXL 1 ~ 7층 순수 멀티 그리드 지층, 황금시간대 선택 모드(`golden_allin_mode`, 기본값 `"NONE"` [OFF]) 및
    독립 골든포켓(`golden_pocket`), 가용 현금 시드(`free_cash_usd`), 계좌별 미국 주식 수수료율(`us_commission_rate`, `round_trip_fee_rate_pct`),
    정적 잠금/조건부 스텝업 사이클 최저 매수가(`cycle_min_buy_price`), STEP2X_15PCT_C20 스텝업 해금 대기 가격 및 해금 횟수,
    💉 05_RESV_6P_GUARD30 예비시드 수혈 잔액 · 사용 회분 · 시드고갈 입금 대기 플래그 · 단 1회 입금 알림 영구 래치,
    🎯 Case 78 현재 1층 목표 정량 주수(`l1_target_quota_qty`), 양방향·주기 60초 타임쉴드 시각,
    다중 그리드 및 골든포켓 매도 대기 정보, 기정산 주문 ID 링버퍼, 누적 세후 실현수익금 및 자투리 절약금을
    Dirty-Check 적용 후 원자적(.tmp -> os.replace)으로 동시 영속화한다.
    """

    ALLOWED_SYMBOLS: Tuple[str, ...] = ("SOXL",)

    def __init__(
        self,
        filepath: Optional[str] = None,
        base_dir: Optional[str] = None,
    ) -> None:
        self.base_dir: str = get_bot_base_dir(
            base_dir
            or (
                os.path.dirname(os.path.abspath(filepath))
                if filepath and os.path.isabs(str(filepath))
                else None
            )
        )
        (
            self.primary_filepath,
            self.legacy_filepath,
            self.backup_filepath,
            self.folder_slug,
        ) = resolve_folder_isolated_ledger_paths(
            base_dir=self.base_dir,
            explicit_filepath=filepath,
        )
        self.filepath: str = self.legacy_filepath
        self.backup_dir: str = os.path.dirname(self.backup_filepath)

        self._mem_lock = threading.RLock()
        self._last_known_valid_seed: float = self._read_env_initial_seed()
        self._data: Dict[str, Dict[str, Any]] = {}
        # Case 75: 기동 시 잔류 고아 .tmp 파일 선제 청소(바이트코드 캐시는 런타임 중 유지)
        emergency_free_disk_space_sync(
            base_dir=self.base_dir, keep_backup_days=14, remove_pycache=False
        )
        self._load_sync()

    @staticmethod
    def _read_env_initial_seed() -> float:
        for env_k in (
            "INITIAL_SEED_USD",
            "TOSS_INITIAL_SEED_USD",
            "SEED_USD",
            "DEFAULT_INITIAL_SEED_USD",
        ):
            val = safe_float(os.environ.get(env_k), 0.0)
            if val > 100.0:
                return round(val, 4)
        return DEFAULT_INITIAL_SEED_USD

    @staticmethod
    def _empty_golden_pocket_dict() -> Dict[str, Any]:
        return {
            "qty": 0,
            "book_price": 0.0,
            "book_invested_usd": 0.0,
            "actual_cost_usd": 0.0,
            "entry_ts": 0.0,
            "order_date": "",
        }

    @classmethod
    def _resolve_safe_initial_seed(
        cls,
        raw_st: Dict[str, Any],
        fallback_seed: float = DEFAULT_INITIAL_SEED_USD,
    ) -> float:
        """
        🚨 Case 68 [시드머니 $100 강제 변조 버그 영구 소각]:
        1) raw_seed > 100.0 이면 사용자 설정 시드로 정상 인정한다.
        2) raw_seed == 100.0 인 경우, 명시적 플래그(`seed_explicitly_set_100 == True`)가 없으면
           초기화 오류로 발생한 $100 변조로 판정하여 직전 정상 시드(fallback_seed) 또는 환경변수/기본값($10,000)으로 복구한다!
        3) raw_seed < 100.0 (0.0 또는 음수/결측)이면 즉시 fallback_seed (또는 $10,000)로 복원한다.
        """
        raw_val = (
            raw_st.get("initial_seed_usd")
            if isinstance(raw_st, dict)
            else None
        )
        raw_seed = safe_float(raw_val, 0.0)
        explicit_100 = bool(
            isinstance(raw_st, dict)
            and raw_st.get("seed_explicitly_set_100", False)
        )

        safe_fb = (
            fallback_seed
            if fallback_seed > 100.0
            else cls._read_env_initial_seed()
        )
        if safe_fb <= 100.0:
            safe_fb = DEFAULT_INITIAL_SEED_USD

        if raw_seed > 100.0:
            return round(raw_seed, 4)
        if abs(raw_seed - 100.0) < 1e-6 and explicit_100:
            return 100.0
        return round(safe_fb, 4)

    @classmethod
    def _default_symbol_state(
        cls,
        folder_slug: str = "default_bot",
        initial_seed: float = DEFAULT_INITIAL_SEED_USD,
    ) -> Dict[str, Any]:
        today_est = datetime.now(EST_TZ).strftime("%Y-%m-%d")
        clean_seed = (
            round(initial_seed, 4)
            if initial_seed >= 100.0
            else DEFAULT_INITIAL_SEED_USD
        )
        env_one_rate, env_rt_pct = _read_env_us_commission_rates()
        return {
            "symbol": TARGET_SYMBOL,
            "folder_slug": str(folder_slug or "default_bot"),
            "is_active": True,
            "initial_seed_usd": clean_seed,
            "seed_explicitly_set_100": False,
            "free_cash_usd": clean_seed,
            # MODIFIED [Case 86]: 계좌별 미국 주식 편도 수수료율(소수) 및 왕복 수수료율(%) 영속화 필드 (.env 폴백 지원)
            "us_commission_rate": env_one_rate,
            "round_trip_fee_rate_pct": env_rt_pct,
            "portion_mode": "COMP_08PCT",
            "threshold_mode": "WIDE_RUNWAY",
            "reentry_mode": "HYBRID_PULL_OR_BRK",
            # Case 76: 🔓 06_STEP2X_15PCT_C20 조건부 스텝업 저가 해금 모드 락온
            "unlock_mode": DEFAULT_UNLOCK_MODE,
            # [Case 80]: 황금시간대(07:00 ~ 07:50 EST & RSI <= 19.0) 전액매수 모드 (기본값 "NONE" [OFF])
            "golden_allin_mode": DEFAULT_GOLDEN_ALLIN_MODE,
            "golden_pocket": cls._empty_golden_pocket_dict(),
            "last_golden_allin_date": "",
            "buy_interval_min": LOCKED_BUY_INTERVAL_MIN,
            "sell_interval_min": LOCKED_SELL_INTERVAL_MIN,
            # Case 72: 7-Layer (1층 공격수 + 2 ~ 6층 개별 완충층 + 통합 7층 본대) 기본값 락온
            "max_grid_tiers": MAX_GRID_TIERS_7,
            "buckets": [],
            "anchor_price": 0.0,
            "cycle_min_buy_price": 0.0,
            "ratchet_anchor_price": 0.0,
            "cycle_reanchor_credit_usd": 0.0,
            # [Case 78 : 현재 1층의 목표 정량 주수 (부분 체결 시 미체결 잔량 계산 및 1.5초 모니터 재대기용)]
            "l1_target_quota_qty": 0,
            "buy_order_id": "",
            "sell_order_id": "",
            "client_order_id": "",
            "ordered_qty": 0,
            "buy_price": 0.0,
            "target_sell_price": 0.0,
            "pending_portion_budget": 0.0,
            "pending_lot_type": "",
            # Case 76: 스텝업 해금 추매 주문 발주 중 대기 스텝업 기준가 (체결 시 cycle_min_buy_price 갱신용)
            "pending_step_up_min_price": 0.0,
            "pending_sell_mode": "",
            "pending_sell_indices": [],
            # [Case 80]: 매도 주문 발주 중 포함된 독립 골든포켓 수량
            "pending_sell_pocket_qty": 0,
            # 봇 자동 정산 완료된 orderId 링버퍼(최근 50개) — 수동 체결 역추적 시 중복 정산 방지
            "last_settled_order_ids": [],
            "last_modify_mono": 0.0,
            "entry_ts": 0.0,
            "last_buy_fill_ts": 0.0,
            "last_sell_fill_ts": 0.0,
            "last_cycle_end_ts": 0.0,
            "last_sell_gate_eval_ts": 0.0,
            # Case 73: 상단 2~7층 보유 중 1층 공석 전용 60초(1분) 주기 재장전 타임쉴드 시각 영속화
            "last_reentry_eval_ts": 0.0,
            # Case 77: 💉 05_RESV_6P_GUARD30 온디맨드 예비시드 수혈 · 상환 · 단 1회 입금 알림 영구 래치 필드
            "used_reserve_portions_cnt": 0,
            "injected_reserve_usd": 0.0,
            "total_reserve_injected_cnt": 0,
            "daily_reserve_injected_cnt": 0,
            "cumulative_reserve_repaid_usd": 0.0,
            "dust_guard_blocked_cnt": 0,
            "daily_dust_guard_blocked_cnt": 0,
            "waiting_reserve_deposit": False,
            "waiting_reserve_deposit_alert_sent": False,
            "required_reserve_deposit_usd": 0.0,
            "last_reserve_check_ts": 0.0,
            "last_evaluated_buy_bucket_id": -1,
            "last_evaluated_date": today_est,
            "logical_date": today_est,
            "last_closing_report_date": "",
            "last_tg_update_id": 0,
            "total_buy_events": 0,
            "total_buy_shares": 0,
            "daily_buy_events": 0,
            # Case 76: STEP2X_15PCT_C20 조건부 스텝업 해금 매수 누적/당일 카운터
            "cond_unlock_buy_events": 0,
            "daily_unlock_buy_events": 0,
            # [Case 80]: 황금시간대(07:00 ~ 07:50 EST & RSI <= 19.0) 전액매수 및 골든포켓 익절/수익 통계
            "golden_allin_buy_events": 0,
            "daily_golden_allin_buy_events": 0,
            "golden_pocket_sell_cnt": 0,
            "daily_golden_pocket_sell_cnt": 0,
            "golden_realized_net_usd": 0.0,
            "daily_golden_realized_net_usd": 0.0,
            "extra_13plus_buy_events": 0,
            "seed_protect_pass_cnt": 0,
            "daily_seed_protect_pass_cnt": 0,
            "cumulative_leftover_saved_usd": 0.0,
            "daily_leftover_saved_usd": 0.0,
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
            "cumulative_realized_gross_usd": 0.0,
            "cumulative_realized_fee_usd": 0.0,
            "cumulative_realized_net_usd": 0.0,
            "daily_realized_net_usd": 0.0,
            "updated_at": datetime.now(EST_TZ).isoformat(),
        }

    @staticmethod
    def _is_upper_grid_tag(lot_type_str: str) -> bool:
        tag = str(lot_type_str or "").upper().strip()
        if tag == "MERGED_UPPER":
            return True
        if tag.startswith("GRID_L") and tag != "GRID_L1":
            return True
        return False

    @classmethod
    def _enforce_7tier_cap_on_dict_buckets(
        cls, clean_buckets: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        # [Case 72]:
        구 12-Layer 등에서 이관된 원장에 7개 층 초과 버킷이 존재할 경우,
        활성 1층과 2 ~ 6층(5개 개별 완충층)은 그대로 보존하고 7층 이상 초과분만
        '통합 7층 본대(GRID_L7)'로 무손실 가중평균 병합하여 7-Layer 규격을 100% 보장한다.
        """
        if not clean_buckets:
            return []

        has_active_l1 = not cls._is_upper_grid_tag(
            str(clean_buckets[0].get("lot_type") or "")
        )
        if has_active_l1:
            l1_list = [clean_buckets[0]]
            uppers = list(clean_buckets[1:])
        else:
            l1_list = []
            uppers = list(clean_buckets[:])

        max_upper_cnt = MAX_GRID_TIERS_7 - 1  # 6개 (GRID_L2 ~ GRID_L7)
        if len(uppers) > max_upper_cnt:
            kept = uppers[: max_upper_cnt - 1]
            overflow = uppers[max_upper_cnt - 1 :]
            tot_q = sum(safe_int(b.get("qty"), 0) for b in overflow)
            tot_ac = round(
                sum(safe_float(b.get("actual_cost_usd"), 0.0) for b in overflow),
                4,
            )
            tot_lc = sum(max(1, safe_int(b.get("lot_count"), 1)) for b in overflow)
            pure_p = round(max(0.01, tot_ac / float(max(1, tot_q))), 4)
            merged_top = {
                "qty": max(1, tot_q),
                "book_price": pure_p,
                "book_invested_usd": tot_ac,
                "actual_cost_usd": tot_ac,
                "lot_count": max(1, tot_lc),
                "lot_type": f"GRID_L{MAX_GRID_TIERS_7}",
            }
            uppers = kept + [merged_top]

        relabeled_uppers: List[Dict[str, Any]] = []
        for idx, b in enumerate(uppers):
            tier_no = min(MAX_GRID_TIERS_7, idx + 2)
            b_copy = dict(b)
            b_copy["lot_type"] = f"GRID_L{tier_no}"
            relabeled_uppers.append(b_copy)

        return l1_list + relabeled_uppers

    @classmethod
    def _sanitize_golden_pocket_dict(
        cls, raw_pocket: Any
    ) -> Dict[str, Any]:
        """
        # [Case 69, Case 71 & Case 80 : 독립 골든포켓(golden_pocket) 순수 실물 원가 정규화기]:
        golden_pocket 의 qty > 0 일 때 book_price == actual_avg_price 및
        book_invested_usd == actual_cost_usd 를 100% 일치시켜 원가 훼손을 원천 차단한다.
        """
        if not isinstance(raw_pocket, dict):
            return cls._empty_golden_pocket_dict()
        q = safe_int(raw_pocket.get("qty"), 0)
        if q <= 0:
            return cls._empty_golden_pocket_dict()
        raw_p = safe_float(
            raw_pocket.get("book_price"),
            safe_float(raw_pocket.get("buy_price"), 0.0),
        )
        raw_bi = safe_float(
            raw_pocket.get("book_invested_usd"), float(q) * max(0.0, raw_p)
        )
        ac = safe_float(raw_pocket.get("actual_cost_usd"), raw_bi)
        if ac <= 0.0 and raw_p > 0.0:
            ac = float(q) * raw_p
        if ac <= 0.0:
            return cls._empty_golden_pocket_dict()
        clean_cost = round(max(0.01 * float(q), ac), 4)
        pure_p = round(max(0.01, clean_cost / float(q)), 4)
        return {
            "qty": q,
            "book_price": pure_p,
            "book_invested_usd": clean_cost,
            "actual_cost_usd": clean_cost,
            "entry_ts": round(
                max(0.0, safe_float(raw_pocket.get("entry_ts"), 0.0)), 4
            ),
            "order_date": str(raw_pocket.get("order_date") or "").strip(),
        }

    def _sanitize_and_enforce_identity(
        self, raw_st: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        🚨 Case 63, Case 64, Case 67, Case 68, Case 69, Case 70, Case 71, Case 72, Case 73, Case 74, Case 76, Case 77, Case 78, Case 80 & Case 86:
        1) buy_interval_min = 10, sell_interval_min = 1, max_grid_tiers = 7 (MAX_GRID_TIERS_7),
           portion_mode = "COMP_08PCT", threshold_mode = "WIDE_RUNWAY", unlock_mode = "STEP2X_15PCT_C20" 를 강제 동기화하고,
           golden_allin_mode 는 GOLDEN_ALLIN_MODES ("NONE", "POCKET_ALLIN", "GRID_L1_ALLIN") 중 하나로 검증한다(기본값 "NONE").
        2) 계좌별 미국 주식 수수료율(us_commission_rate, round_trip_fee_rate_pct)을 유효 범위(왕복 0.01% ~ 2.00%)로 정규화하고
           런타임 메모리 캐시에 동기화한다.
        3) 시드머니 결측 또는 0.0 유입 시 $100.0 으로 변조되지 않도록 _resolve_safe_initial_seed() 를 적용한다.
        4) 🛡️ [Case 69, Case 71, Case 72 & Case 80 순수 실물 원가 100% 보존 강제 (리앵커링 원가 차감 영구 폐기)]
        5) 💉 [Case 77 & Case 80 온디맨드 예비시드 수혈 잔액(injected_reserve_usd) · 골든포켓 투입원금 통합 회계 항등식]
        """
        st = self._default_symbol_state(
            folder_slug=self.folder_slug,
            initial_seed=self._last_known_valid_seed,
        )
        if isinstance(raw_st, dict):
            st.update(raw_st)

        st["symbol"] = TARGET_SYMBOL
        st["folder_slug"] = self.folder_slug
        st["buy_interval_min"] = LOCKED_BUY_INTERVAL_MIN
        st["sell_interval_min"] = LOCKED_SELL_INTERVAL_MIN
        st["max_grid_tiers"] = MAX_GRID_TIERS_7
        st["portion_mode"] = "COMP_08PCT"
        st["threshold_mode"] = "WIDE_RUNWAY"
        st["reentry_mode"] = "HYBRID_PULL_OR_BRK"
        st["unlock_mode"] = DEFAULT_UNLOCK_MODE
        st["cond_unlock_buy_events"] = max(
            0, safe_int(st.get("cond_unlock_buy_events"), 0)
        )
        st["daily_unlock_buy_events"] = max(
            0, safe_int(st.get("daily_unlock_buy_events"), 0)
        )

        # MODIFIED [Case 86]: 계좌별 미국 주식 수수료율 정규화 및 런타임 캐시 동기화
        env_one_fb, env_rt_fb = _read_env_us_commission_rates()
        raw_us_comm = safe_float(st.get("us_commission_rate"), env_one_fb)
        if raw_us_comm <= 0.0 or raw_us_comm > 0.01:
            raw_us_comm = env_one_fb
        raw_rt_pct = safe_float(
            st.get("round_trip_fee_rate_pct"),
            round(raw_us_comm * 200.0, 4),
        )
        if raw_rt_pct <= 0.0 or raw_rt_pct > 2.0:
            raw_rt_pct = (
                round(raw_us_comm * 200.0, 4)
                if (0.0 < raw_us_comm <= 0.01)
                else env_rt_fb
            )
        st["us_commission_rate"] = round(raw_us_comm, 6)
        st["round_trip_fee_rate_pct"] = round(raw_rt_pct, 4)
        set_runtime_round_trip_fee_rate_pct(
            st["round_trip_fee_rate_pct"],
            us_commission_rate=st["us_commission_rate"],
        )

        # [Case 80]: 황금시간대 전액매수 모드 검증 (기본값 "NONE" [OFF]) 및 통계 정규화
        raw_g_mode = (
            str(st.get("golden_allin_mode") or DEFAULT_GOLDEN_ALLIN_MODE)
            .upper()
            .strip()
        )
        if raw_g_mode not in GOLDEN_ALLIN_MODES:
            raw_g_mode = DEFAULT_GOLDEN_ALLIN_MODE
        st["golden_allin_mode"] = raw_g_mode
        st["last_golden_allin_date"] = str(
            st.get("last_golden_allin_date") or ""
        ).strip()
        st["golden_allin_buy_events"] = max(
            0, safe_int(st.get("golden_allin_buy_events"), 0)
        )
        st["daily_golden_allin_buy_events"] = max(
            0, safe_int(st.get("daily_golden_allin_buy_events"), 0)
        )
        st["golden_pocket_sell_cnt"] = max(
            0, safe_int(st.get("golden_pocket_sell_cnt"), 0)
        )
        st["daily_golden_pocket_sell_cnt"] = max(
            0, safe_int(st.get("daily_golden_pocket_sell_cnt"), 0)
        )
        st["golden_realized_net_usd"] = round(
            safe_float(st.get("golden_realized_net_usd"), 0.0), 4
        )
        st["daily_golden_realized_net_usd"] = round(
            safe_float(st.get("daily_golden_realized_net_usd"), 0.0), 4
        )

        clean_pocket = self._sanitize_golden_pocket_dict(
            st.get("golden_pocket")
        )
        st["golden_pocket"] = clean_pocket
        pocket_qty = safe_int(clean_pocket.get("qty"), 0)
        pocket_cost = round(
            safe_float(clean_pocket.get("actual_cost_usd"), 0.0), 4
        )

        # Case 77: 예비시드 수혈·상환·자투리차단 카운터 및 단 1회 입금 알림 래치 정규화
        inj_res_usd = round(
            max(0.0, safe_float(st.get("injected_reserve_usd"), 0.0)), 4
        )
        raw_used_p = safe_int(st.get("used_reserve_portions_cnt"), 0)
        if inj_res_usd <= 0.0:
            inj_res_usd = 0.0
            used_res_p = 0
        else:
            used_res_p = max(
                1, min(MAX_RESERVE_PORTIONS, raw_used_p if raw_used_p > 0 else 1)
            )
        st["injected_reserve_usd"] = inj_res_usd
        st["used_reserve_portions_cnt"] = used_res_p
        st["total_reserve_injected_cnt"] = max(
            0, safe_int(st.get("total_reserve_injected_cnt"), 0)
        )
        st["daily_reserve_injected_cnt"] = max(
            0, safe_int(st.get("daily_reserve_injected_cnt"), 0)
        )
        st["cumulative_reserve_repaid_usd"] = round(
            max(0.0, safe_float(st.get("cumulative_reserve_repaid_usd"), 0.0)),
            4,
        )
        st["dust_guard_blocked_cnt"] = max(
            0, safe_int(st.get("dust_guard_blocked_cnt"), 0)
        )
        st["daily_dust_guard_blocked_cnt"] = max(
            0, safe_int(st.get("daily_dust_guard_blocked_cnt"), 0)
        )
        st["waiting_reserve_deposit"] = bool(
            st.get("waiting_reserve_deposit", False)
        )
        st["waiting_reserve_deposit_alert_sent"] = bool(
            st.get("waiting_reserve_deposit_alert_sent", False)
        )
        st["required_reserve_deposit_usd"] = round(
            max(0.0, safe_float(st.get("required_reserve_deposit_usd"), 0.0)),
            2,
        )
        st["last_reserve_check_ts"] = round(
            max(0.0, safe_float(st.get("last_reserve_check_ts"), 0.0)), 4
        )

        init_seed = self._resolve_safe_initial_seed(
            st, fallback_seed=self._last_known_valid_seed
        )
        st["initial_seed_usd"] = round(init_seed, 4)
        if init_seed > 100.0:
            self._last_known_valid_seed = round(init_seed, 4)

        cum_net = round(
            safe_float(st.get("cumulative_realized_net_usd"), 0.0), 4
        )
        st["cumulative_realized_net_usd"] = cum_net

        raw_buckets = st.get("buckets")
        clean_buckets: List[Dict[str, Any]] = []
        if isinstance(raw_buckets, list):
            for b in raw_buckets:
                if isinstance(b, dict) and safe_int(b.get("qty"), 0) > 0:
                    q = max(1, safe_int(b.get("qty"), 1))
                    bp_raw = round(
                        max(0.01, safe_float(b.get("book_price"), 0.01)), 4
                    )
                    bi_raw = round(
                        max(
                            0.01 * q,
                            safe_float(b.get("book_invested_usd"), q * bp_raw),
                        ),
                        4,
                    )
                    ac = round(
                        max(
                            0.01 * q,
                            safe_float(b.get("actual_cost_usd"), bi_raw),
                        ),
                        4,
                    )
                    lc = max(1, safe_int(b.get("lot_count"), 1))
                    lt = str(b.get("lot_type") or "QUOTA_L1").upper().strip()
                    pure_avg_p = round(max(0.01, ac / float(q)), 4)
                    clean_buckets.append(
                        {
                            "qty": q,
                            "book_price": pure_avg_p,
                            "book_invested_usd": round(ac, 4),
                            "actual_cost_usd": round(ac, 4),
                            "lot_count": lc,
                            "lot_type": lt,
                        }
                    )

        clean_buckets = self._enforce_7tier_cap_on_dict_buckets(clean_buckets)
        st["buckets"] = clean_buckets
        st["cycle_reanchor_credit_usd"] = 0.0

        raw_settled_ids = st.get("last_settled_order_ids")
        if isinstance(raw_settled_ids, list):
            clean_oids: List[str] = []
            for x in raw_settled_ids:
                sx = str(x or "").strip()
                if sx and sx not in clean_oids:
                    clean_oids.append(sx)
            st["last_settled_order_ids"] = clean_oids[-50:]
        else:
            st["last_settled_order_ids"] = []

        has_pending_buy = bool(str(st.get("buy_order_id") or "").strip())
        has_pending_sell = bool(str(st.get("sell_order_id") or "").strip())
        raw_target_q = max(0, safe_int(st.get("l1_target_quota_qty"), 0))
        pending_lot_tag = (
            str(st.get("pending_lot_type") or "").upper().strip()
        )

        if pocket_qty > 0 and has_pending_sell:
            st["pending_sell_pocket_qty"] = max(
                0,
                min(
                    pocket_qty,
                    safe_int(st.get("pending_sell_pocket_qty"), 0),
                ),
            )
        else:
            st["pending_sell_pocket_qty"] = 0

        if not clean_buckets:
            st["last_sell_gate_eval_ts"] = 0.0
            st["last_reentry_eval_ts"] = 0.0
            st["pending_sell_indices"] = []
            st["pending_step_up_min_price"] = 0.0
            st["l1_target_quota_qty"] = (
                raw_target_q
                if (has_pending_buy and pending_lot_tag != "GOLDEN_POCKET")
                else 0
            )
        else:
            st["last_sell_gate_eval_ts"] = round(
                max(0.0, safe_float(st.get("last_sell_gate_eval_ts"), 0.0)), 4
            )
            has_active_l1 = not self._is_upper_grid_tag(
                str(clean_buckets[0].get("lot_type") or "")
            )
            if has_active_l1:
                st["last_reentry_eval_ts"] = 0.0
                cur_l1_q = max(1, safe_int(clean_buckets[0].get("qty"), 1))
                if has_pending_buy and pending_lot_tag not in (
                    "",
                    "TOPUP_1FL",
                    "GOLDEN_POCKET",
                ):
                    ord_q_pending = max(0, safe_int(st.get("ordered_qty"), 0))
                    st["l1_target_quota_qty"] = (
                        raw_target_q
                        if raw_target_q > 0
                        else (
                            ord_q_pending if ord_q_pending > 0 else cur_l1_q
                        )
                    )
                else:
                    st["l1_target_quota_qty"] = max(cur_l1_q, raw_target_q)
            else:
                st["last_reentry_eval_ts"] = round(
                    max(0.0, safe_float(st.get("last_reentry_eval_ts"), 0.0)),
                    4,
                )
                st["l1_target_quota_qty"] = (
                    raw_target_q
                    if (has_pending_buy and pending_lot_tag != "GOLDEN_POCKET")
                    else 0
                )

            if has_pending_buy:
                st["pending_step_up_min_price"] = round(
                    max(
                        0.0,
                        safe_float(st.get("pending_step_up_min_price"), 0.0),
                    ),
                    4,
                )
            else:
                st["pending_step_up_min_price"] = 0.0

            raw_p_idx = st.get("pending_sell_indices")
            if isinstance(raw_p_idx, list):
                valid_idx = sorted(
                    {
                        safe_int(x, -1)
                        for x in raw_p_idx
                        if 0 <= safe_int(x, -1) < len(clean_buckets)
                    }
                )
                st["pending_sell_indices"] = valid_idx
            else:
                st["pending_sell_indices"] = []

        actual_inv_buckets = round(
            sum(safe_float(b["actual_cost_usd"], 0.0) for b in clean_buckets),
            4,
        )
        actual_inv_total = round(actual_inv_buckets + pocket_cost, 4)
        realized_equity = max(0.0, init_seed + cum_net)
        total_pool_equity = realized_equity + inj_res_usd
        st["free_cash_usd"] = round(
            max(0.0, total_pool_equity - actual_inv_total), 4
        )

        if not st["waiting_reserve_deposit"]:
            st["required_reserve_deposit_usd"] = 0.0

        st["updated_at"] = datetime.now(EST_TZ).isoformat()
        return st

    @staticmethod
    def _extract_raw_soxl_dict(loaded: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(loaded, dict):
            return None
        if TARGET_SYMBOL in loaded and isinstance(loaded[TARGET_SYMBOL], dict):
            return dict(loaded[TARGET_SYMBOL])
        if "buckets" in loaded or "initial_seed_usd" in loaded:
            return dict(loaded)
        return None

    @staticmethod
    def _is_state_materially_equal(
        st_a: Optional[Dict[str, Any]],
        st_b: Optional[Dict[str, Any]],
    ) -> bool:
        """
        # [Case 75 : 원장 Dirty-Check 비교기]:
        두 원장 상태 딕셔너리에서 매 호출마다 바뀌는 타임스탬프("updated_at")만 제외하고
        나머지 모든 실질 필드가 100% 동일한지 판별한다.
        """
        if not isinstance(st_a, dict) or not isinstance(st_b, dict):
            return False
        cmp_a = {k: v for k, v in st_a.items() if k != "updated_at"}
        cmp_b = {k: v for k, v in st_b.items() if k != "updated_at"}
        return cmp_a == cmp_b

    @staticmethod
    def _score_ledger_state(
        st: Dict[str, Any],
    ) -> Tuple[int, int, int, float, str]:
        """
        🚨 Case 68, Case 77 & Case 80 [다중 원장 상태 비교 자가 치유 스코어링]:
        폴더 내 3개 원장 후보 중 실제 매매 데이터를 보유한 최적 원장을 선택하기 위한 우선순위 튜플.
        """
        buckets = (
            st.get("buckets") if isinstance(st.get("buckets"), list) else []
        )
        gp = (
            st.get("golden_pocket")
            if isinstance(st.get("golden_pocket"), dict)
            else {}
        )
        total_qty = sum(
            safe_int(b.get("qty"), 0) for b in buckets if isinstance(b, dict)
        ) + max(0, safe_int(gp.get("qty"), 0))
        has_pending_ord = bool(
            str(st.get("buy_order_id") or "").strip()
            or str(st.get("sell_order_id") or "").strip()
        )
        has_active = 1 if (total_qty > 0 or has_pending_ord) else 0

        trade_cnt = (
            safe_int(st.get("total_buy_events"), 0)
            + safe_int(st.get("total_sell_events"), 0)
            + safe_int(st.get("cond_unlock_buy_events"), 0)
            + safe_int(st.get("golden_allin_buy_events"), 0)
            + safe_int(st.get("total_reserve_injected_cnt"), 0)
            + safe_int(st.get("reanchor_cnt"), 0)
        )
        seed_val = safe_float(st.get("initial_seed_usd"), 0.0)
        has_valid_seed = 1 if seed_val > 100.0 else 0

        realized_metric = round(
            abs(safe_float(st.get("cumulative_realized_net_usd"), 0.0))
            + safe_float(st.get("cumulative_leftover_saved_usd"), 0.0)
            + safe_float(st.get("injected_reserve_usd"), 0.0),
            4,
        )
        updated_str = str(st.get("updated_at") or "")
        return (
            has_active,
            trade_cnt,
            has_valid_seed,
            realized_metric,
            updated_str,
        )

    def _load_candidate_file_sync(
        self, fpath: str
    ) -> Optional[Dict[str, Any]]:
        if not fpath or not os.path.isfile(fpath):
            return None
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            return self._extract_raw_soxl_dict(loaded)
        except Exception as exc:
            logger.warning("원장 후보 파일 로드 실패(%s): %s", fpath, exc)
            return None

    def _load_sync(self) -> None:
        """
        🚨 Case 68, Case 75, Case 80, Case 85 & Case 86 [기존 soxl_stratum_ledger.json 100% 무손실 자동 이관 & 3중 금고 Dirty-Check 자가 치유]:
        """
        with GlobalThrottle.get_file_lock(self.primary_filepath):
            with GlobalThrottle.get_file_lock(self.legacy_filepath):
                with self._mem_lock:
                    candidates: List[Tuple[str, Dict[str, Any]]] = []
                    for label, fp in (
                        ("PRIMARY", self.primary_filepath),
                        ("BACKUP_VAULT", self.backup_filepath),
                        ("LEGACY_MIRROR", self.legacy_filepath),
                    ):
                        raw_d = self._load_candidate_file_sync(fp)
                        if isinstance(raw_d, dict):
                            candidates.append((label, raw_d))

                    for _, cand_d in candidates:
                        c_seed = safe_float(cand_d.get("initial_seed_usd"), 0.0)
                        if c_seed > 100.0:
                            self._last_known_valid_seed = round(c_seed, 4)
                            break

                    best_raw: Dict[str, Any] = {}
                    best_label: str = "DEFAULT_INIT"
                    if candidates:
                        priority_map = {
                            "PRIMARY": 3,
                            "BACKUP_VAULT": 2,
                            "LEGACY_MIRROR": 1,
                        }
                        ranked = sorted(
                            candidates,
                            key=lambda item: (
                                self._score_ledger_state(item[1]),
                                priority_map.get(item[0], 0),
                            ),
                            reverse=True,
                        )
                        best_label, best_raw = ranked[0]

                    sanitized = self._sanitize_and_enforce_identity(best_raw)
                    self._data[TARGET_SYMBOL] = sanitized
                    self._save_sync_unlocked()

                    held_q = sum(
                        safe_int(b.get("qty"), 0)
                        for b in sanitized.get("buckets", [])
                    )
                    gp_q = safe_int(
                        (sanitized.get("golden_pocket") or {}).get("qty"), 0
                    )
                    logger.info(
                        "📂 [Case 68~86 폴더별 3중 7층 골디락스 그리드 원장 락온 완료] 폴더=[%s] · 채택소스=%s · 시드=$%.2f · 왕복수수료=%.2f%% · 그리드=%d주(%d개층) · 골든포켓=%d주(모드=%s) · 예비수혈=%d/%d회분($%.2f) · 고유원장=%s",
                        self.folder_slug,
                        best_label,
                        safe_float(sanitized.get("initial_seed_usd"), 10000.0),
                        safe_float(
                            sanitized.get("round_trip_fee_rate_pct"),
                            ROUND_TRIP_FEE_RATE_PCT,
                        ),
                        held_q,
                        len(sanitized.get("buckets", [])),
                        gp_q,
                        str(
                            sanitized.get("golden_allin_mode")
                            or DEFAULT_GOLDEN_ALLIN_MODE
                        ),
                        safe_int(sanitized.get("used_reserve_portions_cnt"), 0),
                        MAX_RESERVE_PORTIONS,
                        safe_float(sanitized.get("injected_reserve_usd"), 0.0),
                        os.path.basename(self.primary_filepath),
                    )

    @classmethod
    def _atomic_write_json_sync(
        cls,
        target_path: str,
        payload: Dict[str, Any],
        force_write: bool = False,
    ) -> bool:
        """
        # [Case 05, Case 68 & Case 75]:
        Dirty-Check 후 실질 데이터 변경이 있을 때만 원자적(.tmp -> os.replace)으로 기록하고,
        ENOSPC(Errno 28) 감지 시 즉시 고아 파일·캐시를 청소 후 재시도한다.
        """
        if not target_path:
            return False

        new_soxl = cls._extract_raw_soxl_dict(payload)
        if (
            not force_write
            and new_soxl is not None
            and os.path.isfile(target_path)
        ):
            try:
                with open(target_path, "r", encoding="utf-8") as rf:
                    existing_loaded = json.load(rf)
                existing_soxl = cls._extract_raw_soxl_dict(existing_loaded)
                if cls._is_state_materially_equal(existing_soxl, new_soxl):
                    return False
            except Exception:
                pass

        parent_dir = os.path.dirname(os.path.abspath(target_path))
        base_search_dir = (
            os.path.dirname(parent_dir)
            if os.path.basename(parent_dir) == "ledger_backups"
            else parent_dir
        )

        for attempt in range(2):
            if parent_dir and not os.path.isdir(parent_dir):
                try:
                    os.makedirs(parent_dir, exist_ok=True)
                except OSError as os_err:
                    if os_err.errno == errno.ENOSPC and attempt == 0:
                        emergency_free_disk_space_sync(
                            base_dir=base_search_dir,
                            keep_backup_days=3,
                            remove_pycache=True,
                        )
                        continue
                    return False

            tmp_path = (
                f"{target_path}.tmp.{os.getpid()}.{threading.get_ident()}"
            )
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, target_path)
                return True
            except OSError as os_err:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass
                if os_err.errno == errno.ENOSPC and attempt == 0:
                    freed_cnt = emergency_free_disk_space_sync(
                        base_dir=base_search_dir,
                        keep_backup_days=3,
                        remove_pycache=True,
                    )
                    logger.warning(
                        "🧹 [Case 75 디스크 공간 부족(Errno 28) 감지 -> 긴급 자가 치유 실행] 삭제된 고아/캐시/구백업=%d개 · 원장 저장 재시도(%s)",
                        freed_cnt,
                        os.path.basename(target_path),
                    )
                    continue
                logger.error(
                    "원장 원자적 저장 OS 예외(%s): %s", target_path, os_err
                )
                return False
            except Exception as exc:
                logger.error("원장 원자적 저장 예외(%s): %s", target_path, exc)
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass
                return False

        return False

    def _save_sync_unlocked(self, force_write: bool = False) -> None:
        payload = {TARGET_SYMBOL: self._data[TARGET_SYMBOL]}
        self._atomic_write_json_sync(
            self.primary_filepath, payload, force_write=force_write
        )
        if os.path.abspath(self.legacy_filepath) != os.path.abspath(
            self.primary_filepath
        ):
            self._atomic_write_json_sync(
                self.legacy_filepath, payload, force_write=force_write
            )
        self._atomic_write_json_sync(
            self.backup_filepath, payload, force_write=force_write
        )

    def create_daily_backup_snapshot_sync(
        self, logical_date: Optional[str] = None, keep_days: int = 14
    ) -> str:
        """
        Case 68 & Case 75 [일일 날짜별 스냅샷 금고 보관 및 고아 파일 청소]:
        """
        emergency_free_disk_space_sync(
            base_dir=self.base_dir,
            keep_backup_days=max(3, safe_int(keep_days, 14)),
            remove_pycache=False,
        )
        dt_str = str(
            logical_date or datetime.now(EST_TZ).strftime("%Y-%m-%d")
        ).strip()
        snap_path = os.path.join(
            self.backup_dir,
            f"soxl_stratum_ledger_{self.folder_slug}_{dt_str}.json",
        )
        with GlobalThrottle.get_file_lock(self.primary_filepath):
            with self._mem_lock:
                payload = {TARGET_SYMBOL: self._data[TARGET_SYMBOL]}
                self._atomic_write_json_sync(
                    snap_path, payload, force_write=False
                )

        return snap_path

    async def create_daily_backup_snapshot(
        self, logical_date: Optional[str] = None, keep_days: int = 14
    ) -> str:
        return await asyncio.to_thread(
            self.create_daily_backup_snapshot_sync, logical_date, keep_days
        )

    def recover_from_backup_vault_sync(self) -> Optional[Dict[str, Any]]:
        cand_paths = [self.backup_filepath, self.primary_filepath]
        try:
            pattern = os.path.join(
                self.backup_dir,
                f"soxl_stratum_ledger_{self.folder_slug}_20*.json",
            )
            cand_paths.extend(sorted(glob.glob(pattern), reverse=True)[:3])
        except Exception:
            pass

        for fp in cand_paths:
            raw_d = self._load_candidate_file_sync(fp)
            if isinstance(raw_d, dict):
                b_list = raw_d.get("buckets")
                gp_obj = (
                    raw_d.get("golden_pocket")
                    if isinstance(raw_d.get("golden_pocket"), dict)
                    else {}
                )
                b_qty = (
                    sum(
                        safe_int(b.get("qty"), 0)
                        for b in b_list
                        if isinstance(b, dict)
                    )
                    if isinstance(b_list, list)
                    else 0
                )
                gp_qty = max(0, safe_int(gp_obj.get("qty"), 0))
                if (b_qty + gp_qty) > 0:
                    return self._sanitize_and_enforce_identity(raw_d)
        return None

    def _assert_allowed_symbol(self, symbol: str) -> str:
        sym = str(symbol or TARGET_SYMBOL).upper().strip()
        if sym not in self.ALLOWED_SYMBOLS:
            raise ValueError(
                f"🚨 [Case 09 위반] 허용되지 않은 종목 접근 차단: {sym} (허용: {self.ALLOWED_SYMBOLS})"
            )
        return sym

    def get_state(self, symbol: str = TARGET_SYMBOL) -> Dict[str, Any]:
        sym = self._assert_allowed_symbol(symbol)
        with self._mem_lock:
            st = self._data.get(sym)
            if not isinstance(st, dict):
                st = self._sanitize_and_enforce_identity({})
                self._data[sym] = st
            return json.loads(json.dumps(st))

    def update_state_sync(
        self, symbol: str = TARGET_SYMBOL, **kwargs: Any
    ) -> Dict[str, Any]:
        sym = self._assert_allowed_symbol(symbol)
        with GlobalThrottle.get_file_lock(self.primary_filepath):
            with GlobalThrottle.get_file_lock(self.legacy_filepath):
                with self._mem_lock:
                    prev_st = self._data.get(sym)
                    cur = dict(
                        prev_st
                        or self._default_symbol_state(
                            folder_slug=self.folder_slug,
                            initial_seed=self._last_known_valid_seed,
                        )
                    )
                    if "initial_seed_usd" in kwargs:
                        req_seed = safe_float(
                            kwargs.get("initial_seed_usd"), 0.0
                        )
                        cur["seed_explicitly_set_100"] = bool(
                            abs(req_seed - 100.0) < 1e-6
                        )
                    cur.update(kwargs)
                    sanitized = self._sanitize_and_enforce_identity(cur)
                    if not self._is_state_materially_equal(prev_st, sanitized):
                        self._data[sym] = sanitized
                        self._save_sync_unlocked(force_write=False)
                    else:
                        self._data[sym] = sanitized
                    return json.loads(json.dumps(sanitized))

    async def update_state(
        self, symbol: str = TARGET_SYMBOL, **kwargs: Any
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.update_state_sync, symbol, **kwargs
        )

    async def cycle_golden_allin_mode(
        self, target_mode: Optional[str] = None
    ) -> Dict[str, Any]:
        st = self.get_state(TARGET_SYMBOL)
        cur_m = (
            str(st.get("golden_allin_mode") or DEFAULT_GOLDEN_ALLIN_MODE)
            .upper()
            .strip()
        )
        if target_mode is not None:
            req_m = str(target_mode).upper().strip()
            if req_m in ("OFF", "NONE", "0", "FALSE"):
                next_m = "NONE"
            elif req_m in ("POCKET", "POCKET_ALLIN", "1"):
                next_m = "POCKET_ALLIN"
            elif req_m in ("GRID", "GRID_L1", "GRID_L1_ALLIN", "2"):
                next_m = "GRID_L1_ALLIN"
            elif req_m in GOLDEN_ALLIN_MODES:
                next_m = req_m
            else:
                next_m = DEFAULT_GOLDEN_ALLIN_MODE
        else:
            try:
                cur_idx = GOLDEN_ALLIN_MODES.index(cur_m)
                next_m = GOLDEN_ALLIN_MODES[
                    (cur_idx + 1) % len(GOLDEN_ALLIN_MODES)
                ]
            except ValueError:
                next_m = "POCKET_ALLIN"
        return await self.update_state(
            TARGET_SYMBOL, golden_allin_mode=next_m
        )

    async def reset_stratum_only(
        self,
        symbol: str = TARGET_SYMBOL,
        new_seed_usd: Optional[float] = None,
        preserve_realized_profit: bool = True,
    ) -> Dict[str, Any]:
        sym = self._assert_allowed_symbol(symbol)
        st = self.get_state(sym)
        if new_seed_usd is not None and safe_float(new_seed_usd, 0.0) >= 100.0:
            init_seed = safe_float(new_seed_usd, DEFAULT_INITIAL_SEED_USD)
        else:
            init_seed = self._resolve_safe_initial_seed(
                st, fallback_seed=self._last_known_valid_seed
            )
        cum_net = (
            safe_float(st.get("cumulative_realized_net_usd"), 0.0)
            if preserve_realized_profit
            else 0.0
        )
        now_reset_ts = time.time()
        return await self.update_state(
            sym,
            initial_seed_usd=round(init_seed, 4),
            cumulative_realized_net_usd=round(cum_net, 4),
            buckets=[],
            golden_pocket=self._empty_golden_pocket_dict(),
            anchor_price=0.0,
            cycle_min_buy_price=0.0,
            ratchet_anchor_price=0.0,
            cycle_reanchor_credit_usd=0.0,
            l1_target_quota_qty=0,
            used_reserve_portions_cnt=0,
            injected_reserve_usd=0.0,
            waiting_reserve_deposit=False,
            waiting_reserve_deposit_alert_sent=False,
            required_reserve_deposit_usd=0.0,
            last_reserve_check_ts=0.0,
            last_sell_fill_ts=now_reset_ts,
            last_cycle_end_ts=now_reset_ts,
            last_sell_gate_eval_ts=0.0,
            last_reentry_eval_ts=0.0,
            buy_order_id="",
            sell_order_id="",
            client_order_id="",
            ordered_qty=0,
            buy_price=0.0,
            target_sell_price=0.0,
            pending_portion_budget=0.0,
            pending_lot_type="",
            pending_step_up_min_price=0.0,
            pending_sell_mode="",
            pending_sell_indices=[],
            pending_sell_pocket_qty=0,
            last_evaluated_buy_bucket_id=-1,
        )

    async def set_initial_seed_usd(
        self, new_seed_usd: float, reset_realized_profit: bool = False
    ) -> Dict[str, Any]:
        clean_seed = round(max(100.0, safe_float(new_seed_usd, 10000.0)), 4)
        kw: Dict[str, Any] = {
            "initial_seed_usd": clean_seed,
            "seed_explicitly_set_100": bool(abs(clean_seed - 100.0) < 1e-6),
        }
        if reset_realized_profit:
            kw["cumulative_realized_net_usd"] = 0.0
            kw["cumulative_realized_gross_usd"] = 0.0
            kw["cumulative_realized_fee_usd"] = 0.0
        return await self.update_state(TARGET_SYMBOL, **kw)

    async def toggle_bot_active(
        self, active: Optional[bool] = None
    ) -> Dict[str, Any]:
        st = self.get_state(TARGET_SYMBOL)
        next_active = (
            bool(active)
            if active is not None
            else (not bool(st.get("is_active", True)))
        )
        return await self.update_state(TARGET_SYMBOL, is_active=next_active)

    async def rollover_daily_counters_if_needed(
        self, logical_date: str
    ) -> Dict[str, Any]:
        st = self.get_state(TARGET_SYMBOL)
        cur_date = str(st.get("logical_date") or "")
        if cur_date == str(logical_date):
            return st
        return await self.update_state(
            TARGET_SYMBOL,
            logical_date=str(logical_date),
            daily_buy_events=0,
            daily_unlock_buy_events=0,
            daily_golden_allin_buy_events=0,
            daily_golden_pocket_sell_cnt=0,
            daily_golden_realized_net_usd=0.0,
            daily_reserve_injected_cnt=0,
            daily_dust_guard_blocked_cnt=0,
            daily_sell_events=0,
            daily_indiv_grid_sell_cnt=0,
            daily_wma_grad_sell_cnt=0,
            daily_seed_protect_pass_cnt=0,
            daily_reanchor_cnt=0,
            daily_leftover_saved_usd=0.0,
            daily_realized_net_usd=0.0,
            last_evaluated_buy_bucket_id=-1,
            last_evaluated_date=str(logical_date),
            last_reentry_eval_ts=0.0,
        )


# 하위 호환 별칭 (타 모듈 임포트 호환 100% 보장)
StratumLedger = SoxlStratumLedger
AssassinLedger = SoxlStratumLedger
