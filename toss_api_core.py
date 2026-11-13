# -*- coding: utf-8 -*-
"""
# MODIFIED: toss_api_core.py (Part 1/2 — 황금시간 07:00~07:50 RSI<=19 올인 전면 영구 소각 &
# Case 91 무제한 예비수혈 카운트 · 복리[COMP_08PCT] ➔ 단리[SIMPLE_08PCT] ➔ 바벨모드[BARBELL_60_30_10] 3단 순환 상수 및
# 별도 수익금고 격리 오프셋 vaulted_profit_locked_usd 원장 스키마 탑재)
인피니트 스노우볼 (Infinite Snowball) v3.0 — 토스증권 코어 상수 · 폴더 격리 · 디스크 자가 치유 ·
GlobalThrottle 동시성 통제 및 SOXL 7-Tier 골디락스 본 그리드(구 2층 + 구 7층 통합 중간층 재배치 & 최고 도달 회차 단차 잠금 · Case 87) /
스위치 없는 100% 기본 상시 적용(Default ON) 3-Tier 서브 그리드(4.0% 정량 · 구 1층 + 구 3층 양끝 합병 & 최대 4회분[16%] 상한 캡 & 0.5회분 보호예수 · Case 88) /
현재 사이클 단위 실현수익(cycle_realized_net_usd) 자동 추적·리셋 · 무제한 예비시드 수혈 횟수 카운트 및
자산증식형(복리 · COMP_08PCT) ➔ 인출형(단리 · SIMPLE_08PCT) ➔ 바벨모드(BARBELL_60_30_10 · SOXL 60% 코어 분리) 폴더별 3중 원장(SoxlStratumLedger) 코어 모듈
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
# [핵심 상수] 제4헌법 EST 단일 타임존 & 최종 확정 진화 챔피언 전역 상수
# ---------------------------------------------------------------------------
EST_TZ = ZoneInfo("America/New_York")
KST_TZ = ZoneInfo("Asia/Seoul")

TARGET_SYMBOL: str = "SOXL"
BARBELL_SAFE_SYMBOL: str = "SGOV"
REAL_ALLOWED_SYMBOLS: Tuple[str, ...] = ("SOXL",)
BARBELL_ALLOWED_SYMBOLS: Tuple[str, ...] = ("SOXL", "SGOV")
ALLOWED_SYMBOLS: Tuple[str, ...] = ("SOXL",)

DEFAULT_INITIAL_SEED_USD: float = 10000.0
PORTION_RATIO_LOCKED: float = 0.08
BASE_MAX_LOTS_8PCT: int = 12

# MODIFIED [Case 91 + 바벨 모드 확장 : 📈 복리(COMP_08PCT) ➔ 💵 단리(SIMPLE_08PCT) ➔ ⚖️ 바벨(BARBELL_60_30_10) 3단 순환 상수]
PORTION_MODE_COMPOUND: str = "COMP_08PCT"
PORTION_MODE_SIMPLE: str = "SIMPLE_08PCT"
PORTION_MODE_BARBELL: str = "BARBELL_60_30_10"

BARBELL_SOXL_WEIGHT: float = 0.60
BARBELL_SGOV_WEIGHT: float = 0.30
BARBELL_CASH_WEIGHT: float = 0.10

VALID_PORTION_MODES: Tuple[str, ...] = (
    "COMP_08PCT",
    "SIMPLE_08PCT",
    "BARBELL_60_30_10",
    "FIXED_800",
)

# Case 72 & Case 87: 골디락스 7-Layer (1층 공격수 + 2 ~ 7층 완충/중간합병 그리드) 상수 락온
MAX_GRID_TIERS_7: int = 7
MAX_GRID_TIERS: int = 7
MAX_GRID_TIERS_12: int = 7

# [Case 87 : 👑 06_L2L7_RATCHET_8PCT — 7층 만석 초과(8층 발생) 시 구 1층 보존 + 구 2층 + 구 7층 통합 후 평단 오름차순 중간층 재배치 모드]
DEFAULT_GRID_MERGE_MODE: str = "L2_L7_MERGE_SORT"

# [Case 88 : 🛡️ 13_SUB_L1L3_RESV05_CAP4L — 스위치 없는 100% 기본 상시 적용(Default ON) 3층 서브 그리드 상수 락온]
SUB_GRID_DEFAULT_ENABLED: bool = True
SUB_FROZEN_DAYS_TRIGGER: int = 5
SUB_PORTION_RATIO_4PCT: float = 0.04
SUB_MAX_TIERS_3: int = 3
SUB_MAX_TIERS: int = 3
SUB_MAX_TOTAL_LOTS_4: int = 4
SUB_MAX_TOTAL_LOTS: int = 4
SUB_RESERVE_MAIN_PORTIONS: float = 0.5
SUB_MERGE_MODE_L1_L3: str = "SUB_L1_L3_MERGE"
DEFAULT_SUB_MERGE_MODE: str = "SUB_L1_L3_MERGE"
SUB_UNLOCK_FROZEN_DAYS_10: int = 10
SUB_UNLOCK_DROP_FROM_L1_PCT: float = 10.0

# Case 76: 🔓 06_STEP2X_15PCT_C20 3중 안전문 기반 조건부 스텝업 저가 해금 전역 상수 락온
DEFAULT_UNLOCK_MODE: str = "STEP2X_15PCT_C20"
STEP_UP_2X_MIN_REBOUND_MULT: float = 2.0
STEP_UP_2X_MAX_TIERS: int = 2
STEP_UP_2X_MIN_CASH_RATIO: float = 0.20
STEP_UP_2X_DROP_PCT: float = 15.0

# MODIFIED [Case 77 & Case 91 : 30% 자투리 1주 승격 방지 가드(GUARD30) & 횟수 제한 없는 무제한 온디맨드 예비시드 자동 수혈 상수]
MAX_RESERVE_PORTIONS: int = 999999
MIN_DIP_BUDGET_RATIO: float = 0.30
MIN_DIP_VS_L1_RATIO: float = 0.30
RESERVE_DEPOSIT_TOLERANCE_RATIO: float = 0.95

# [Case 84 : 정규장 마감 30분 전(15:30 ~ 16:00 EST) 본·서브 0주 새 사이클 첫 1층 진입 및 상단층 보유 중 1층 공석 +1.0% 돌파 추격 동시 차단 기준 시각(HHMM)]
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
# [유틸리티] 안전한 수치 형변환 · 3단 운용 모드 판별기 및 런타임 수수료율 동기화기
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


def is_barbell_mode(portion_mode: Any) -> bool:
    """
    # NEW:
    현재 운용 모드가 ⚖️ 바벨 모드(BARBELL_60_30_10 · SOXL 60% / SGOV 30% / 현금 10% · 실현수익 별도 장부 격리)인지 판별한다.
    """
    return str(portion_mode or "").upper().strip() in (
        "BARBELL_60_30_10",
        "BARBELL",
    )


def is_simple_income_mode(portion_mode: Any) -> bool:
    """
    # [Case 91]:
    현재 운용 모드가 💵 인출형(단리 · 설정 기준시드의 8% / 서브 4% 고정 · 채굴 수익 현금 적립 및 인출)인지 판별한다.
    """
    return str(portion_mode or PORTION_MODE_COMPOUND).upper().strip() in (
        "SIMPLE_08PCT",
        "FIXED_800",
        "SIMPLE",
        "INCOME",
    )


def next_cycled_portion_mode(cur_mode: Any) -> str:
    """
    # NEW:
    운용 모드 3단 순환기:
    스나이퍼(복리 · COMP_08PCT) ➔ 스나이퍼(단리 · SIMPLE_08PCT) ➔ 바벨모드(BARBELL_60_30_10) ➔ 스나이퍼(복리 · COMP_08PCT)
    """
    if is_barbell_mode(cur_mode):
        return PORTION_MODE_COMPOUND
    if is_simple_income_mode(cur_mode):
        return PORTION_MODE_BARBELL
    return PORTION_MODE_SIMPLE


def _read_env_us_commission_rates() -> Tuple[float, float]:
    """
    # [Case 86 : 환경변수(.env) 기반 미국 주식 수수료율 폴백 로더]
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
    with _RUNTIME_FEE_LOCK:
        return _RUNTIME_US_COMMISSION_RATE


def get_runtime_round_trip_fee_rate_pct() -> float:
    with _RUNTIME_FEE_LOCK:
        return _RUNTIME_ROUND_TRIP_FEE_RATE_PCT


def set_runtime_round_trip_fee_rate_pct(
    round_trip_pct: float,
    us_commission_rate: Optional[float] = None,
) -> float:
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
    clean_prefix = "".join(
        ch for ch in str(prefix or "ORD").upper() if ch.isalnum()
    )[:8]
    ts_part = int(time.time() * 1000) % 100000000
    rand_part = uuid.uuid4().hex[:12]
    cid = f"{clean_prefix}-{ts_part}-{rand_part}"
    return cid[:36]


class _NonRetryableApiError(Exception):
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
# ---------------------------------------------------------------------------
def get_bot_base_dir(explicit_dir: Optional[str] = None) -> str:
    if explicit_dir and str(explicit_dir).strip():
        cand = os.path.abspath(str(explicit_dir).strip())
        if os.path.isfile(cand):
            return os.path.dirname(cand)
        return cand
    return os.path.abspath(os.path.dirname(os.path.abspath(__file__)) or ".")


def get_folder_slug(base_dir: Optional[str] = None) -> str:
    target_dir = get_bot_base_dir(base_dir)
    raw_name = os.path.basename(os.path.normpath(target_dir)).strip()
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name).strip("._-")
    return slug if slug else "default_bot"


def resolve_folder_isolated_ledger_paths(
    base_dir: Optional[str] = None,
    explicit_filepath: Optional[str] = None,
) -> Tuple[str, str, str, str]:
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
        keep_n = max(2, safe_int(keep_backup_days, 7))
        for snap_prefix in (
            "soxl_stratum_ledger_*_20*.json",
            "barbell_ledger_*_20*.json",
        ):
            try:
                snap_pat = os.path.join(backup_dir, snap_prefix)
                snaps = sorted(glob.glob(snap_pat))
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

    if (
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
            time.sleep(wait_s)

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
# [핵심 2] SOXL 단일 롱 7-Tier 본 그리드 · Default-ON 3-Tier 서브 그리드 · 3단 운용모드(복리/단리/바벨) 폴더별 3중 안전 지층 원장 (SoxlStratumLedger)
# ---------------------------------------------------------------------------
class SoxlStratumLedger:
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

    @classmethod
    def _resolve_safe_initial_seed(
        cls,
        raw_st: Dict[str, Any],
        fallback_seed: float = DEFAULT_INITIAL_SEED_USD,
    ) -> float:
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
            "us_commission_rate": env_one_rate,
            "round_trip_fee_rate_pct": env_rt_pct,
            # [Case 91 + 바벨 확장]: COMP_08PCT / SIMPLE_08PCT / BARBELL_60_30_10 및 격리 수익금 오프셋
            "portion_mode": PORTION_MODE_COMPOUND,
            "vaulted_profit_locked_usd": 0.0,
            "threshold_mode": "WIDE_RUNWAY",
            "reentry_mode": "HYBRID_PULL_OR_BRK",
            "grid_merge_mode": DEFAULT_GRID_MERGE_MODE,
            "sub_grid_enabled": SUB_GRID_DEFAULT_ENABLED,
            "sub_merge_mode": SUB_MERGE_MODE_L1_L3,
            "sub_max_tiers": SUB_MAX_TIERS_3,
            "sub_max_total_lots": SUB_MAX_TOTAL_LOTS_4,
            "sub_buckets": [],
            "sub_anchor_price": 0.0,
            "sub_cycle_min_buy_price": 0.0,
            "sub_ratchet_max_lots": 0,
            "sub_l1_target_quota_qty": 0,
            "main_consec_frozen_days": 0,
            "sub_consec_frozen_days": 0,
            "last_frozen_eval_date": "",
            "sub_last_evaluated_buy_bucket_id": -1,
            "sub_last_evaluated_date": today_est,
            "last_sub_reentry_eval_ts": 0.0,
            "last_sub_buy_fill_ts": 0.0,
            "last_sub_sell_fill_ts": 0.0,
            "last_sub_cycle_end_ts": 0.0,
            "pending_sub_sell_indices": [],
            "pending_sub_step_up_min_price": 0.0,
            "sub_buy_events": 0,
            "sub_buy_shares": 0,
            "daily_sub_buy_cnt": 0,
            "daily_sub_buy_events": 0,
            "sub_sell_events": 0,
            "sub_sold_shares": 0,
            "daily_sub_sell_cnt": 0,
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
            "daily_main_buy_cnt": 0,
            "daily_main_sell_cnt": 0,
            "unlock_mode": DEFAULT_UNLOCK_MODE,
            "buy_interval_min": LOCKED_BUY_INTERVAL_MIN,
            "sell_interval_min": LOCKED_SELL_INTERVAL_MIN,
            "max_grid_tiers": MAX_GRID_TIERS_7,
            "buckets": [],
            "anchor_price": 0.0,
            "cycle_min_buy_price": 0.0,
            "cycle_ratchet_max_lots": 0,
            "ratchet_anchor_price": 0.0,
            "cycle_reanchor_credit_usd": 0.0,
            "l1_target_quota_qty": 0,
            "buy_order_id": "",
            "sell_order_id": "",
            "client_order_id": "",
            "ordered_qty": 0,
            "buy_price": 0.0,
            "target_sell_price": 0.0,
            "pending_portion_budget": 0.0,
            "pending_lot_type": "",
            "pending_step_up_min_price": 0.0,
            "pending_sell_mode": "",
            "pending_sell_indices": [],
            "last_settled_order_ids": [],
            "last_modify_mono": 0.0,
            "entry_ts": 0.0,
            "last_buy_fill_ts": 0.0,
            "last_sell_fill_ts": 0.0,
            "last_cycle_end_ts": 0.0,
            "last_sell_gate_eval_ts": 0.0,
            "last_reentry_eval_ts": 0.0,
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
            "cond_unlock_buy_events": 0,
            "daily_unlock_buy_events": 0,
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
            "cycle_realized_gross_usd": 0.0,
            "cycle_realized_fee_usd": 0.0,
            "cycle_realized_net_usd": 0.0,
            "cycle_sub_realized_net_usd": 0.0,
            "cycle_sell_events": 0,
            "cycle_leftover_saved_usd": 0.0,
            "last_cycle_realized_net_usd": 0.0,
            "last_cycle_sell_events": 0,
            "completed_main_cycles": 0,
            "updated_at": datetime.now(EST_TZ).isoformat(),
        }

    @staticmethod
    def _is_upper_grid_tag(lot_type_str: str) -> bool:
        tag = str(lot_type_str or "").upper().strip()
        if tag in ("MERGED_UPPER", "SUB_MERGED"):
            return True
        if tag.startswith("GRID_L") and tag != "GRID_L1":
            return True
        if tag.startswith("SUB_L") and tag != "SUB_L1":
            return True
        return False

    @classmethod
    def _enforce_7tier_cap_on_dict_buckets(
        cls,
        clean_buckets: List[Dict[str, Any]],
        merge_mode: str = DEFAULT_GRID_MERGE_MODE,
    ) -> List[Dict[str, Any]]:
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

        # MODIFIED: 2층 개별 익절 후 [2층 공석] (GRID_L3~L7 시작) 슬롯 보존
        first_up_tag = (
            str(uppers[0].get("lot_type") or "").upper().strip()
            if uppers
            else ""
        )
        start_tier_no = (
            3
            if first_up_tag
            in ("GRID_L3", "GRID_L4", "GRID_L5", "GRID_L6", "GRID_L7")
            else 2
        )
        max_upper_cnt = max(1, MAX_GRID_TIERS_7 - (start_tier_no - 1))
        m_mode = str(merge_mode or DEFAULT_GRID_MERGE_MODE).upper().strip()

        while len(uppers) > max_upper_cnt:
            if m_mode == "L2_L7_MERGE_SORT" and len(uppers) >= 3:
                kept_lowest_upper = [uppers[0]]
                low_b = uppers[1]
                high_b = uppers[-1]
                middle_rest = uppers[2:-1]

                q_low = max(1, safe_int(low_b.get("qty"), 1))
                q_high = max(1, safe_int(high_b.get("qty"), 1))
                tot_q = q_low + q_high
                tot_ac = round(
                    safe_float(low_b.get("actual_cost_usd"), 0.0)
                    + safe_float(high_b.get("actual_cost_usd"), 0.0),
                    4,
                )
                tot_lc = max(1, safe_int(low_b.get("lot_count"), 1)) + max(
                    1, safe_int(high_b.get("lot_count"), 1)
                )
                overall_book_avg = (
                    float(q_low) * safe_float(low_b.get("book_price"), 0.0)
                    + float(q_high) * safe_float(high_b.get("book_price"), 0.0)
                ) / float(max(1, tot_q))
                raw_p = max(0.01, tot_ac / float(max(1, tot_q)))
                pure_p = round(
                    min(raw_p, overall_book_avg)
                    if overall_book_avg > 0.0
                    else raw_p,
                    4,
                )
                merged_b = {
                    "qty": max(1, tot_q),
                    "book_price": pure_p,
                    "book_invested_usd": tot_ac,
                    "actual_cost_usd": tot_ac,
                    "lot_count": max(1, tot_lc),
                    "lot_type": f"GRID_L{MAX_GRID_TIERS_7}",
                }
                uppers = kept_lowest_upper + middle_rest + [merged_b]
                uppers.sort(
                    key=lambda b: round(safe_float(b.get("book_price"), 0.0), 4)
                )
            else:
                kept = uppers[: max_upper_cnt - 1]
                overflow = uppers[max_upper_cnt - 1 :]
                tot_q = sum(safe_int(b.get("qty"), 0) for b in overflow)
                tot_ac = round(
                    sum(
                        safe_float(b.get("actual_cost_usd"), 0.0)
                        for b in overflow
                    ),
                    4,
                )
                tot_lc = sum(
                    max(1, safe_int(b.get("lot_count"), 1)) for b in overflow
                )
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
            tier_no = min(MAX_GRID_TIERS_7, idx + start_tier_no)
            b_copy = dict(b)
            b_copy["lot_type"] = f"GRID_L{tier_no}"
            relabeled_uppers.append(b_copy)

        return l1_list + relabeled_uppers

    @classmethod
    def _enforce_sub_3tier_cap_on_dict_buckets(
        cls,
        clean_sub_buckets: List[Dict[str, Any]],
        merge_mode: str = SUB_MERGE_MODE_L1_L3,
    ) -> List[Dict[str, Any]]:
        if not clean_sub_buckets:
            return []

        has_active_l1 = not cls._is_upper_grid_tag(
            str(clean_sub_buckets[0].get("lot_type") or "")
        )
        if has_active_l1:
            l1_list = [clean_sub_buckets[0]]
            uppers = list(clean_sub_buckets[1:])
        else:
            l1_list = []
            uppers = list(clean_sub_buckets[:])

        max_upper_cnt = SUB_MAX_TIERS_3 - 1
        m_mode = str(merge_mode or SUB_MERGE_MODE_L1_L3).upper().strip()

        while len(uppers) > max_upper_cnt:
            if m_mode == "SUB_L1_L3_MERGE" and len(uppers) >= 3:
                low_b = uppers[0]
                high_b = uppers[-1]
                middle_rest = uppers[1:-1]

                q_low = max(1, safe_int(low_b.get("qty"), 1))
                q_high = max(1, safe_int(high_b.get("qty"), 1))
                tot_q = q_low + q_high
                tot_ac = round(
                    safe_float(low_b.get("actual_cost_usd"), 0.0)
                    + safe_float(high_b.get("actual_cost_usd"), 0.0),
                    4,
                )
                tot_lc = max(1, safe_int(low_b.get("lot_count"), 1)) + max(
                    1, safe_int(high_b.get("lot_count"), 1)
                )
                overall_book_avg = (
                    float(q_low) * safe_float(low_b.get("book_price"), 0.0)
                    + float(q_high) * safe_float(high_b.get("book_price"), 0.0)
                ) / float(max(1, tot_q))
                raw_p = max(0.01, tot_ac / float(max(1, tot_q)))
                pure_p = round(
                    min(raw_p, overall_book_avg)
                    if overall_book_avg > 0.0
                    else raw_p,
                    4,
                )
                merged_b = {
                    "qty": max(1, tot_q),
                    "book_price": pure_p,
                    "book_invested_usd": tot_ac,
                    "actual_cost_usd": tot_ac,
                    "lot_count": max(1, tot_lc),
                    "lot_type": f"GRID_L{SUB_MAX_TIERS_3}",
                }
                uppers = middle_rest + [merged_b]
                uppers.sort(
                    key=lambda b: round(safe_float(b.get("book_price"), 0.0), 4)
                )
            else:
                kept = uppers[: max_upper_cnt - 1]
                overflow = uppers[max_upper_cnt - 1 :]
                tot_q = sum(safe_int(b.get("qty"), 0) for b in overflow)
                tot_ac = round(
                    sum(
                        safe_float(b.get("actual_cost_usd"), 0.0)
                        for b in overflow
                    ),
                    4,
                )
                tot_lc = sum(
                    max(1, safe_int(b.get("lot_count"), 1)) for b in overflow
                )
                pure_p = round(max(0.01, tot_ac / float(max(1, tot_q))), 4)
                merged_top = {
                    "qty": max(1, tot_q),
                    "book_price": pure_p,
                    "book_invested_usd": tot_ac,
                    "actual_cost_usd": tot_ac,
                    "lot_count": max(1, tot_lc),
                    "lot_type": f"GRID_L{SUB_MAX_TIERS_3}",
                }
                uppers = kept + [merged_top]

        relabeled_uppers: List[Dict[str, Any]] = []
        for idx, b in enumerate(uppers):
            tier_no = min(SUB_MAX_TIERS_3, idx + 2)
            b_copy = dict(b)
            b_copy["lot_type"] = f"GRID_L{tier_no}"
            relabeled_uppers.append(b_copy)

        return l1_list + relabeled_uppers
    def _sanitize_and_enforce_identity(
        self, raw_st: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        🚨 Case 63 ~ Case 91 + 바벨 모드(BARBELL_60_30_10) 회계 항등식 확장:
        1) portion_mode = COMP_08PCT(복리) / SIMPLE_08PCT(단리) / BARBELL_60_30_10(바벨) 3단 모드 보존
        2) 바벨 모드 가동 시 SOXL 코어 시드를 initial_seed_usd 의 60% 로 분리 산출하여
           실현수익이 SOXL 가용현금(free_cash_usd)에 섞이지 않도록 물리적 차단
        3) 별도 수익금고 격리 누적액(vaulted_profit_locked_usd) 보존으로 모드 간 수익금 침범 원천 봉쇄
        """
        st = self._default_symbol_state(
            folder_slug=self.folder_slug,
            initial_seed=self._last_known_valid_seed,
        )
        if isinstance(raw_st, dict):
            st.update(raw_st)

        for obsolete_k in (
            "golden_allin_mode",
            "golden_pocket",
            "last_golden_allin_date",
            "pending_sell_pocket_qty",
            "golden_allin_buy_events",
            "daily_golden_allin_buy_events",
            "golden_pocket_sell_cnt",
            "daily_golden_pocket_sell_cnt",
            "golden_realized_net_usd",
            "daily_golden_realized_net_usd",
        ):
            st.pop(obsolete_k, None)

        st["symbol"] = TARGET_SYMBOL
        st["folder_slug"] = self.folder_slug
        st["buy_interval_min"] = LOCKED_BUY_INTERVAL_MIN
        st["sell_interval_min"] = LOCKED_SELL_INTERVAL_MIN
        st["max_grid_tiers"] = MAX_GRID_TIERS_7

        # MODIFIED [Case 91 + 바벨 모드 3단 보존]
        raw_p_mode = (
            str(st.get("portion_mode") or PORTION_MODE_COMPOUND)
            .upper()
            .strip()
        )
        if is_barbell_mode(raw_p_mode):
            st["portion_mode"] = PORTION_MODE_BARBELL
        elif is_simple_income_mode(raw_p_mode):
            st["portion_mode"] = PORTION_MODE_SIMPLE
        else:
            st["portion_mode"] = PORTION_MODE_COMPOUND

        st["vaulted_profit_locked_usd"] = round(
            max(0.0, safe_float(st.get("vaulted_profit_locked_usd"), 0.0)), 4
        )

        st["threshold_mode"] = "WIDE_RUNWAY"
        st["reentry_mode"] = "HYBRID_PULL_OR_BRK"
        st["grid_merge_mode"] = DEFAULT_GRID_MERGE_MODE
        st["unlock_mode"] = DEFAULT_UNLOCK_MODE
        st["sub_grid_enabled"] = True
        st["sub_merge_mode"] = SUB_MERGE_MODE_L1_L3
        st["sub_max_tiers"] = SUB_MAX_TIERS_3
        st["sub_max_total_lots"] = SUB_MAX_TOTAL_LOTS_4

        st["cond_unlock_buy_events"] = max(
            0, safe_int(st.get("cond_unlock_buy_events"), 0)
        )
        st["daily_unlock_buy_events"] = max(
            0, safe_int(st.get("daily_unlock_buy_events"), 0)
        )

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

        inj_res_usd = round(
            max(0.0, safe_float(st.get("injected_reserve_usd"), 0.0)), 4
        )
        raw_used_p = safe_int(st.get("used_reserve_portions_cnt"), 0)
        if inj_res_usd <= 0.0:
            inj_res_usd = 0.0
            used_res_p = 0
        else:
            used_res_p = max(1, raw_used_p if raw_used_p > 0 else 1)
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

        clean_buckets = self._enforce_7tier_cap_on_dict_buckets(
            clean_buckets, merge_mode=st["grid_merge_mode"]
        )
        st["buckets"] = clean_buckets
        st["cycle_reanchor_credit_usd"] = 0.0

        raw_sub_buckets = st.get("sub_buckets")
        clean_sub_buckets: List[Dict[str, Any]] = []
        if isinstance(raw_sub_buckets, list):
            for sb in raw_sub_buckets:
                if isinstance(sb, dict) and safe_int(sb.get("qty"), 0) > 0:
                    sq = max(1, safe_int(sb.get("qty"), 1))
                    sbp_raw = round(
                        max(0.01, safe_float(sb.get("book_price"), 0.01)), 4
                    )
                    sbi_raw = round(
                        max(
                            0.01 * sq,
                            safe_float(
                                sb.get("book_invested_usd"), sq * sbp_raw
                            ),
                        ),
                        4,
                    )
                    sac = round(
                        max(
                            0.01 * sq,
                            safe_float(sb.get("actual_cost_usd"), sbi_raw),
                        ),
                        4,
                    )
                    slc = max(1, safe_int(sb.get("lot_count"), 1))
                    slt = (
                        str(sb.get("lot_type") or "SUB_REENTRY_1FL")
                        .upper()
                        .strip()
                    )
                    spure_avg_p = round(max(0.01, sac / float(sq)), 4)
                    clean_sub_buckets.append(
                        {
                            "qty": sq,
                            "book_price": spure_avg_p,
                            "book_invested_usd": round(sac, 4),
                            "actual_cost_usd": round(sac, 4),
                            "lot_count": slc,
                            "lot_type": slt,
                        }
                    )

        clean_sub_buckets = self._enforce_sub_3tier_cap_on_dict_buckets(
            clean_sub_buckets, merge_mode=st["sub_merge_mode"]
        )
        st["sub_buckets"] = clean_sub_buckets

        held_lots_now = sum(
            max(1, safe_int(b.get("lot_count"), 1)) for b in clean_buckets
        )
        raw_ratchet_lots = max(
            0, safe_int(st.get("cycle_ratchet_max_lots"), 0)
        )

        sub_held_lots_now = sum(
            max(1, safe_int(sb.get("lot_count"), 1))
            for sb in clean_sub_buckets
        )
        raw_sub_ratchet_lots = max(
            0, safe_int(st.get("sub_ratchet_max_lots"), 0)
        )

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
        raw_target_q = max(0, safe_int(st.get("l1_target_quota_qty"), 0))
        raw_sub_target_q = max(
            0, safe_int(st.get("sub_l1_target_quota_qty"), 0)
        )
        pending_lot_tag = (
            str(st.get("pending_lot_type") or "").upper().strip()
        )
        is_pending_sub_buy = pending_lot_tag.startswith("SUB_")

        if not clean_buckets:
            st["cycle_ratchet_max_lots"] = 0
            st["cycle_min_buy_price"] = 0.0
            st["main_consec_frozen_days"] = 0
            st["last_sell_gate_eval_ts"] = 0.0
            st["last_reentry_eval_ts"] = 0.0
            st["pending_sell_indices"] = []
            st["pending_step_up_min_price"] = 0.0
            st["l1_target_quota_qty"] = (
                raw_target_q
                if (has_pending_buy and not is_pending_sub_buy)
                else 0
            )
        else:
            st["cycle_ratchet_max_lots"] = max(held_lots_now, raw_ratchet_lots)
            st["main_consec_frozen_days"] = max(
                0, safe_int(st.get("main_consec_frozen_days"), 0)
            )
            st["last_sell_gate_eval_ts"] = round(
                max(0.0, safe_float(st.get("last_sell_gate_eval_ts"), 0.0)), 4
            )
            has_active_l1 = not self._is_upper_grid_tag(
                str(clean_buckets[0].get("lot_type") or "")
            )
            if has_active_l1:
                st["last_reentry_eval_ts"] = 0.0
                cur_l1_q = max(1, safe_int(clean_buckets[0].get("qty"), 1))
                if (
                    has_pending_buy
                    and not is_pending_sub_buy
                    and pending_lot_tag not in ("", "TOPUP_1FL")
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
                    if (has_pending_buy and not is_pending_sub_buy)
                    else 0
                )

            if has_pending_buy and not is_pending_sub_buy:
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

        if not clean_sub_buckets:
            st["sub_ratchet_max_lots"] = 0
            st["sub_cycle_min_buy_price"] = 0.0
            st["sub_consec_frozen_days"] = 0
            st["last_sub_reentry_eval_ts"] = 0.0
            st["pending_sub_sell_indices"] = []
            st["pending_sub_step_up_min_price"] = 0.0
            st["sub_l1_target_quota_qty"] = (
                raw_sub_target_q if (has_pending_buy and is_pending_sub_buy) else 0
            )
        else:
            st["sub_ratchet_max_lots"] = max(
                sub_held_lots_now, raw_sub_ratchet_lots
            )
            st["sub_consec_frozen_days"] = max(
                0, safe_int(st.get("sub_consec_frozen_days"), 0)
            )
            has_sub_active_l1 = not self._is_upper_grid_tag(
                str(clean_sub_buckets[0].get("lot_type") or "")
            )
            if has_sub_active_l1:
                st["last_sub_reentry_eval_ts"] = 0.0
                cur_sub_l1_q = max(
                    1, safe_int(clean_sub_buckets[0].get("qty"), 1)
                )
                if (
                    has_pending_buy
                    and is_pending_sub_buy
                    and pending_lot_tag != "SUB_TOPUP_1FL"
                ):
                    ord_q_pending = max(0, safe_int(st.get("ordered_qty"), 0))
                    st["sub_l1_target_quota_qty"] = (
                        raw_sub_target_q
                        if raw_sub_target_q > 0
                        else (
                            ord_q_pending
                            if ord_q_pending > 0
                            else cur_sub_l1_q
                        )
                    )
                else:
                    st["sub_l1_target_quota_qty"] = max(
                        cur_sub_l1_q, raw_sub_target_q
                    )
            else:
                st["last_sub_reentry_eval_ts"] = round(
                    max(
                        0.0,
                        safe_float(st.get("last_sub_reentry_eval_ts"), 0.0),
                    ),
                    4,
                )
                st["sub_l1_target_quota_qty"] = (
                    raw_sub_target_q
                    if (has_pending_buy and is_pending_sub_buy)
                    else 0
                )

            if has_pending_buy and is_pending_sub_buy:
                st["pending_sub_step_up_min_price"] = round(
                    max(
                        0.0,
                        safe_float(
                            st.get("pending_sub_step_up_min_price"), 0.0
                        ),
                    ),
                    4,
                )
            else:
                st["pending_sub_step_up_min_price"] = 0.0

            raw_sub_p_idx = st.get("pending_sub_sell_indices")
            if isinstance(raw_sub_p_idx, list):
                valid_sub_idx = sorted(
                    {
                        safe_int(x, -1)
                        for x in raw_sub_p_idx
                        if 0 <= safe_int(x, -1) < len(clean_sub_buckets)
                    }
                )
                st["pending_sub_sell_indices"] = valid_sub_idx
            else:
                st["pending_sub_sell_indices"] = []

        st["sub_buy_events"] = max(0, safe_int(st.get("sub_buy_events"), 0))
        st["sub_buy_shares"] = max(0, safe_int(st.get("sub_buy_shares"), 0))
        st["daily_sub_buy_cnt"] = max(
            0, safe_int(st.get("daily_sub_buy_cnt"), 0)
        )
        st["daily_sub_buy_events"] = max(
            0, safe_int(st.get("daily_sub_buy_events"), 0)
        )
        st["sub_sell_events"] = max(0, safe_int(st.get("sub_sell_events"), 0))
        st["sub_sold_shares"] = max(0, safe_int(st.get("sub_sold_shares"), 0))
        st["daily_sub_sell_cnt"] = max(
            0, safe_int(st.get("daily_sub_sell_cnt"), 0)
        )
        st["daily_sub_sell_events"] = max(
            0, safe_int(st.get("daily_sub_sell_events"), 0)
        )
        st["sub_merge_events"] = max(
            0, safe_int(st.get("sub_merge_events"), 0)
        )
        st["sub_merged_indiv_escape_cnt"] = max(
            0, safe_int(st.get("sub_merged_indiv_escape_cnt"), 0)
        )
        st["sub_unlock_events"] = max(
            0, safe_int(st.get("sub_unlock_events"), 0)
        )
        st["daily_sub_unlock_events"] = max(
            0, safe_int(st.get("daily_sub_unlock_events"), 0)
        )
        st["sub_completed_cycles"] = max(
            0, safe_int(st.get("sub_completed_cycles"), 0)
        )
        st["sub_realized_gross_usd"] = round(
            safe_float(st.get("sub_realized_gross_usd"), 0.0), 4
        )
        st["sub_realized_fee_usd"] = round(
            safe_float(st.get("sub_realized_fee_usd"), 0.0), 4
        )
        st["sub_realized_net_usd"] = round(
            safe_float(st.get("sub_realized_net_usd"), 0.0), 4
        )
        st["daily_sub_realized_net_usd"] = round(
            safe_float(st.get("daily_sub_realized_net_usd"), 0.0), 4
        )
        st["daily_main_buy_cnt"] = max(
            0, safe_int(st.get("daily_main_buy_cnt"), 0)
        )
        st["daily_main_sell_cnt"] = max(
            0, safe_int(st.get("daily_main_sell_cnt"), 0)
        )

        st["last_cycle_realized_net_usd"] = round(
            safe_float(st.get("last_cycle_realized_net_usd"), 0.0), 4
        )
        st["last_cycle_sell_events"] = max(
            0, safe_int(st.get("last_cycle_sell_events"), 0)
        )
        st["completed_main_cycles"] = max(
            0, safe_int(st.get("completed_main_cycles"), 0)
        )

        if not clean_buckets and not clean_sub_buckets:
            st["cycle_realized_gross_usd"] = 0.0
            st["cycle_realized_fee_usd"] = 0.0
            st["cycle_realized_net_usd"] = 0.0
            st["cycle_sub_realized_net_usd"] = 0.0
            st["cycle_sell_events"] = 0
            st["cycle_leftover_saved_usd"] = 0.0
        else:
            st["cycle_realized_gross_usd"] = round(
                safe_float(st.get("cycle_realized_gross_usd"), 0.0), 4
            )
            st["cycle_realized_fee_usd"] = round(
                safe_float(st.get("cycle_realized_fee_usd"), 0.0), 4
            )
            st["cycle_realized_net_usd"] = round(
                safe_float(st.get("cycle_realized_net_usd"), 0.0), 4
            )
            st["cycle_sub_realized_net_usd"] = round(
                safe_float(st.get("cycle_sub_realized_net_usd"), 0.0), 4
            )
            st["cycle_sell_events"] = max(
                0, safe_int(st.get("cycle_sell_events"), 0)
            )
            st["cycle_leftover_saved_usd"] = round(
                safe_float(st.get("cycle_leftover_saved_usd"), 0.0), 4
            )

        # 🚨 [Case 77, Case 88, Case 91 & 바벨 모드(60% SOXL 분리 · 별도 수익금고 격리) 통합 회계 항등식 강제]
        actual_inv_buckets = round(
            sum(safe_float(b["actual_cost_usd"], 0.0) for b in clean_buckets),
            4,
        )
        actual_inv_sub = round(
            sum(
                safe_float(sb["actual_cost_usd"], 0.0)
                for sb in clean_sub_buckets
            ),
            4,
        )
        actual_inv_total = round(actual_inv_buckets + actual_inv_sub, 4)
        vault_locked = st["vaulted_profit_locked_usd"]

        if is_barbell_mode(st["portion_mode"]):
            soxl_core_60 = round(init_seed * BARBELL_SOXL_WEIGHT, 4)
            cyc_loss_adj = min(
                0.0, safe_float(st.get("cycle_realized_net_usd"), 0.0)
            )
            total_pool_equity = (
                max(0.0, soxl_core_60 + cyc_loss_adj) + inj_res_usd
            )
        else:
            realized_equity = max(0.0, init_seed + cum_net - vault_locked)
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
        if (
            "buckets" in loaded
            or "sub_buckets" in loaded
            or "initial_seed_usd" in loaded
        ):
            return dict(loaded)
        return None

    @staticmethod
    def _is_state_materially_equal(
        st_a: Optional[Dict[str, Any]],
        st_b: Optional[Dict[str, Any]],
    ) -> bool:
        if not isinstance(st_a, dict) or not isinstance(st_b, dict):
            return False
        cmp_a = {k: v for k, v in st_a.items() if k != "updated_at"}
        cmp_b = {k: v for k, v in st_b.items() if k != "updated_at"}
        return cmp_a == cmp_b

    @staticmethod
    def _score_ledger_state(
        st: Dict[str, Any],
    ) -> Tuple[int, int, int, float, str]:
        buckets = (
            st.get("buckets") if isinstance(st.get("buckets"), list) else []
        )
        sub_buckets = (
            st.get("sub_buckets")
            if isinstance(st.get("sub_buckets"), list)
            else []
        )
        total_qty = sum(
            safe_int(b.get("qty"), 0)
            for b in buckets
            if isinstance(b, dict)
        ) + sum(
            safe_int(sb.get("qty"), 0)
            for sb in sub_buckets
            if isinstance(sb, dict)
        )
        has_pending_ord = bool(
            str(st.get("buy_order_id") or "").strip()
            or str(st.get("sell_order_id") or "").strip()
        )
        has_active = 1 if (total_qty > 0 or has_pending_ord) else 0

        trade_cnt = (
            safe_int(st.get("total_buy_events"), 0)
            + safe_int(st.get("total_sell_events"), 0)
            + safe_int(st.get("sub_buy_events"), 0)
            + safe_int(st.get("sub_sell_events"), 0)
            + safe_int(st.get("cond_unlock_buy_events"), 0)
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
                    held_l = sum(
                        max(1, safe_int(b.get("lot_count"), 1))
                        for b in sanitized.get("buckets", [])
                    )
                    ratchet_l = safe_int(
                        sanitized.get("cycle_ratchet_max_lots"), 0
                    )
                    sub_q = sum(
                        safe_int(sb.get("qty"), 0)
                        for sb in sanitized.get("sub_buckets", [])
                    )
                    sub_l = sum(
                        max(1, safe_int(sb.get("lot_count"), 1))
                        for sb in sanitized.get("sub_buckets", [])
                    )
                    if is_barbell_mode(sanitized.get("portion_mode")):
                        p_mode_lbl = "⚖️바벨모드(60/30/10)"
                    elif is_simple_income_mode(sanitized.get("portion_mode")):
                        p_mode_lbl = "💵인출형(단리)"
                    else:
                        p_mode_lbl = "📈자산증식형(복리)"

                    logger.info(
                        "📂 [폴더별 3중 원장 락온 완료] 폴더=[%s] · 채택소스=%s · 시드=$%.2f · 모드=%s · 왕복수수료=%.2f%% · 본그리드=%d주(%d개층·보유%d/잠금%d회차) · 서브그리드=%d주(%d개층·%d/%d회분) · 이번사이클순익=$%.2f · 예비수혈=%d회(누적%d회·$%.2f) · 고유원장=%s",
                        self.folder_slug,
                        best_label,
                        safe_float(sanitized.get("initial_seed_usd"), 10000.0),
                        p_mode_lbl,
                        safe_float(
                            sanitized.get("round_trip_fee_rate_pct"),
                            ROUND_TRIP_FEE_RATE_PCT,
                        ),
                        held_q,
                        len(sanitized.get("buckets", [])),
                        held_l,
                        ratchet_l,
                        sub_q,
                        len(sanitized.get("sub_buckets", [])),
                        sub_l,
                        SUB_MAX_TOTAL_LOTS_4,
                        safe_float(
                            sanitized.get("cycle_realized_net_usd"), 0.0
                        ),
                        safe_int(sanitized.get("used_reserve_portions_cnt"), 0),
                        safe_int(
                            sanitized.get("total_reserve_injected_cnt"), 0
                        ),
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
                sub_list = raw_d.get("sub_buckets")
                b_qty = (
                    sum(
                        safe_int(b.get("qty"), 0)
                        for b in b_list
                        if isinstance(b, dict)
                    )
                    if isinstance(b_list, list)
                    else 0
                )
                sub_qty = (
                    sum(
                        safe_int(sb.get("qty"), 0)
                        for sb in sub_list
                        if isinstance(sb, dict)
                    )
                    if isinstance(sub_list, list)
                    else 0
                )
                if (b_qty + sub_qty) > 0:
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
        return await asyncio.wait_for(
            asyncio.to_thread(self.update_state_sync, symbol, **kwargs),
            timeout=10.0,
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
        v_locked = (
            safe_float(st.get("vaulted_profit_locked_usd"), 0.0)
            if preserve_realized_profit
            else 0.0
        )
        now_reset_ts = time.time()
        return await self.update_state(
            sym,
            initial_seed_usd=round(init_seed, 4),
            cumulative_realized_net_usd=round(cum_net, 4),
            vaulted_profit_locked_usd=round(v_locked, 4),
            cycle_realized_gross_usd=0.0,
            cycle_realized_fee_usd=0.0,
            cycle_realized_net_usd=0.0,
            cycle_sub_realized_net_usd=0.0,
            cycle_sell_events=0,
            cycle_leftover_saved_usd=0.0,
            buckets=[],
            sub_buckets=[],
            anchor_price=0.0,
            cycle_min_buy_price=0.0,
            cycle_ratchet_max_lots=0,
            ratchet_anchor_price=0.0,
            cycle_reanchor_credit_usd=0.0,
            l1_target_quota_qty=0,
            sub_anchor_price=0.0,
            sub_cycle_min_buy_price=0.0,
            sub_ratchet_max_lots=0,
            sub_l1_target_quota_qty=0,
            main_consec_frozen_days=0,
            sub_consec_frozen_days=0,
            used_reserve_portions_cnt=0,
            injected_reserve_usd=0.0,
            waiting_reserve_deposit=False,
            waiting_reserve_deposit_alert_sent=False,
            required_reserve_deposit_usd=0.0,
            last_reserve_check_ts=0.0,
            last_sell_fill_ts=now_reset_ts,
            last_cycle_end_ts=now_reset_ts,
            last_sub_sell_fill_ts=now_reset_ts,
            last_sub_cycle_end_ts=now_reset_ts,
            last_sell_gate_eval_ts=0.0,
            last_reentry_eval_ts=0.0,
            last_sub_reentry_eval_ts=0.0,
            buy_order_id="",
            sell_order_id="",
            client_order_id="",
            ordered_qty=0,
            buy_price=0.0,
            target_sell_price=0.0,
            pending_portion_budget=0.0,
            pending_lot_type="",
            pending_step_up_min_price=0.0,
            pending_sub_step_up_min_price=0.0,
            pending_sell_mode="",
            pending_sell_indices=[],
            pending_sub_sell_indices=[],
            last_evaluated_buy_bucket_id=-1,
            sub_last_evaluated_buy_bucket_id=-1,
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
            kw["vaulted_profit_locked_usd"] = 0.0
            kw["cycle_realized_gross_usd"] = 0.0
            kw["cycle_realized_fee_usd"] = 0.0
            kw["cycle_realized_net_usd"] = 0.0
            kw["cycle_sub_realized_net_usd"] = 0.0
            kw["cycle_sell_events"] = 0
            kw["cycle_leftover_saved_usd"] = 0.0
            kw["last_cycle_realized_net_usd"] = 0.0
            kw["last_cycle_sell_events"] = 0
            kw["completed_main_cycles"] = 0
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

    async def toggle_portion_mode(
        self, target_mode: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        # MODIFIED [Case 91 + 바벨 확장 : 📈 복리(COMP_08PCT) ➔ 💵 단리(SIMPLE_08PCT) ➔ ⚖️ 바벨(BARBELL_60_30_10) 3단 순환 모드 전환기]:
        """
        st = self.get_state(TARGET_SYMBOL)
        cur_mode = (
            str(st.get("portion_mode") or PORTION_MODE_COMPOUND)
            .upper()
            .strip()
        )
        if target_mode is not None and str(target_mode).strip():
            if is_barbell_mode(target_mode):
                next_mode = PORTION_MODE_BARBELL
            elif is_simple_income_mode(target_mode):
                next_mode = PORTION_MODE_SIMPLE
            else:
                next_mode = PORTION_MODE_COMPOUND
        else:
            next_mode = next_cycled_portion_mode(cur_mode)
        return await self.update_state(TARGET_SYMBOL, portion_mode=next_mode)

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
            daily_sell_events=0,
            daily_indiv_grid_sell_cnt=0,
            daily_wma_grad_sell_cnt=0,
            daily_seed_protect_pass_cnt=0,
            daily_reanchor_cnt=0,
            daily_leftover_saved_usd=0.0,
            daily_realized_net_usd=0.0,
            last_evaluated_buy_bucket_id=-1,
            last_evaluated_date=str(logical_date),
            sub_last_evaluated_buy_bucket_id=-1,
            sub_last_evaluated_date=str(logical_date),
            last_reentry_eval_ts=0.0,
            last_sub_reentry_eval_ts=0.0,
        )


# 하위 호환 별칭 (타 모듈 임포트 호환 100% 보장)
StratumLedger = SoxlStratumLedger
AssassinLedger = SoxlStratumLedger
