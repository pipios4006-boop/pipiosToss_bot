# -*- coding: utf-8 -*-
"""
# MODIFIED: toss_api.py
인피니트 스노우볼 (Infinite Snowball) v3.0 — 토스증권 Open API (v1.2.14) 방탄 통신 통제소 &
SOXL 단일 롱 7-Tier 순수 멀티 그리드(1층 공격수 + 2 ~ 6층 개별 완충층 + 통합 7층 본대) 및
황금시간대(07:00 ~ 07:50 EST & RSI <= 19.0) 독립 골든포켓(GoldenAllInPocket · 기본값 NONE[OFF]) 폴더별 3중 지층 원장(SoxlStratumLedger) 코어 모듈 (Step 01 / 09)
- 제1헌법: 모든 파일 I/O 및 네트워크 통신의 asyncio.to_thread 비동기 격리 + GlobalThrottle 중앙 통제
- 제2헌법: 기동 시 GET /api/v1/accounts 1회 호출로 BROKERAGE accountSeq 메모리 락온 및 X-Tossinvest-Account 자동 주입
- 제3헌법 ~ 제6헌법 및 Case 01 ~ 84 전수 락온:
  1) REAL_ALLOWED_SYMBOLS = ("SOXL",) 단일 롱 화이트리스트 물리적 강제 (인버스 숏 SOXS 원천 차단)
  2) get_holdings_map_with_status, get_candles_1m, get_candles_1d, get_recent_trades, get_recent_wick_high_price,
     get_current_prices_batch, get_orderbook, get_buying_power_usd, get_sellable_quantity, create_order, modify_order,
     cancel_order, get_order_detail, get_open_orders, get_closed_orders, probe_latest_manual_fill_price,
     get_usd_krw_rate 등 전 메서드 100% 정식 구현!
  3) 미국 주식 주문 정정(/modify) 시 quantity 필드 원천 배제(400 us-modify-quantity-not-supported 차단) 및
     주문 취소(/cancel) 시 빈 JSON 객체 {} 전송 강제(HTTP 415 차단)
  4) 🚨 [Case 68 폴더 위치(base_dir) 기반 멀티 봇 자동 식별 격리 & 3중 원장 금고 & 시드 $100 변조 방어]
     - "/home/pipiosToss" 고정 경로 하드코딩 100% 영구 소각 -> 오직 실행 파일이 위치한 폴더(base_dir)의 .env 만 로드
     - 폴더명(folder_slug) 기반 ① 고유 원장(soxl_stratum_ledger_<폴더명>.json), ② 호환 원장(soxl_stratum_ledger.json),
       ③ 실시간 백업 금고(ledger_backups/soxl_stratum_ledger_<폴더명>.bak.json) 3중 원자적 동기화 및 기존 데이터 무손실 자동 이관
  5) 🚨 [Case 65, Case 69, Case 70 & Case 73 양방향·주기 60초 타임쉴드 시각 영속화 및 순수 원가 무결성 강제]
     - last_buy_fill_ts, last_sell_fill_ts, last_cycle_end_ts, last_sell_gate_eval_ts, last_reentry_eval_ts 원장 영속화
  6) 🚨 [Case 19, Case 63, Case 71 ~ Case 74 : 최종 확정 챔피언 🔓 06_STEP2X_15PCT_C20 7-Layer 순수 원가 보존 및
     토스 CLOSED 주문 원장 역추적(probe_latest_manual_fill_price : CANCEL_REJECTED / REPLACE_REJECTED / REPLACED 중복 배제) &
     기정산 주문 링버퍼(last_settled_order_ids) 탑재]
  7) 🚨 [Case 75 : 클라우드 VM 디스크 고갈([Errno 28] No space left on device) 원천 차단 & 디스크 Write 90% 감축]
     - 원장 Dirty-Check(_is_state_materially_equal)를 통해 실질 상태 변경이 없을 때 불필요한 .tmp 생성 및 os.fsync() 원천 스킵
     - emergency_free_disk_space_sync() 로 고아 임시 파일(*.tmp.*, *.heal.tmp) · __pycache__ · 초과 백업 스냅샷 자동 소각 및
       ENOSPC(Errno 28) 감지 시 즉시 자가 치유 후 원자적 쓰기 재시도
  8) 🚨 [Case 76 : 🔓 06_STEP2X_15PCT_C20 3중 안전문 조건부 스텝업 저가 해금 상수 및 원장 상태 필드 탑재]
     - STEP_UP_2X_MIN_REBOUND_MULT(2.0x), STEP_UP_2X_MAX_TIERS(2), STEP_UP_2X_MIN_CASH_RATIO(0.20), STEP_UP_2X_DROP_PCT(15.0) 락온
     - unlock_mode, pending_step_up_min_price, cond_unlock_buy_events, daily_unlock_buy_events 원장 영속화 및 정규화
  9) 🚨 [Case 77 : 💉 05_RESV_6P_GUARD30 (30% 자투리 1주 승격 방지 가드 + 시드고갈 단 1회 입금 요청 알림 래치 +
     토스 실계좌 여유자금 감지 기반 최대 +6회분 온디맨드 예비시드 자동 수혈 및 0주 졸업 시 원금 자동 상환) 상수 및 원장 필드 탑재]
     - MAX_RESERVE_PORTIONS(6), MIN_DIP_BUDGET_RATIO(0.30), MIN_DIP_VS_L1_RATIO(0.30), RESERVE_DEPOSIT_TOLERANCE_RATIO(0.95) 락온
     - used_reserve_portions_cnt, injected_reserve_usd, total_reserve_injected_cnt, daily_reserve_injected_cnt,
       cumulative_reserve_repaid_usd, dust_guard_blocked_cnt, daily_dust_guard_blocked_cnt,
       waiting_reserve_deposit, waiting_reserve_deposit_alert_sent(스팸 차단 영구 래치),
       required_reserve_deposit_usd, last_reserve_check_ts 원장 영속화 및 회계 항등식 확장
  10) 🚨 [Case 67 & Case 78 : 지정가 부분 체결 후 미체결 잔량(l1_target_quota_qty) 보존 및 신규 1층 추매 발주 중 기존 1층 수량 덮어쓰기 차단]
      - l1_target_quota_qty 원장 영속화 및 0주 졸업 / 1층 익절 공석 전환 시 자동 클리어 정규화 탑재
      - 신규 1층 생성형 주문(DIP_1FL / QUOTA_L1 / REENTRY_1FL / GOLDEN_L1) 대기 중 기존 1층 수량과의 max() 오염 원천 차단
  11) 🚨 [Case 80 : 미동부 프리장 황금시간대(07:00 ~ 07:50 EST & RSI(14) <= 19.0) 가용현금 100% 전액 추가매수 &
      독립 골든포켓(golden_pocket) 분리회계 & 전술 제어반(/settlement) 3대 모드 선택기(기본값 "NONE" [OFF]) &
      1분봉 캔들 페이지네이션 방탄화(1페이지 200봉 유실 차단 및 스키마 다변화 대응) 탑재]
  12) 🚨 [Case 82 : 1분봉 윗꼬리(Upper-Wick) 슈팅 100% 포착을 위한 GET /api/v1/trades 최근 5.0초 내 유효 체결 최고가 추출기
      (get_recent_wick_high_price & _parse_iso_timestamp_to_epoch · 서버 시차 -5.0s 허용) 탑재]
  13) 🚨 [Case 83 & Case 84 : 방안 C 오버나이트 통합이평 사수 하이브리드 및 정규장 마감 30분 전(15:30 ~ 16:00 EST · NEW_CYCLE_BUY_CUTOFF_HM = 1530)
      0주 새 사이클 첫 1층 진입 및 1층 공석 +1.0% 돌파 추격 차단 상수 연동]
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
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger("toss_sniper.toss_api")

# ---------------------------------------------------------------------------
# [핵심 상수] 제4헌법 EST 단일 타임존 & 최종 확정 진화 챔피언 (Case 72 ~ 84) 전역 상수
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

# NEW [Case 84 : 정규장 마감 30분 전(15:30 ~ 16:00 EST) 0주 새 사이클 1층 진입 및 1층 공석 +1.0% 돌파 추격 차단 기준 시각(HHMM)]
NEW_CYCLE_BUY_CUTOFF_HM: int = 1530

LOCKED_BUY_INTERVAL_MIN: int = 10
LOCKED_SELL_INTERVAL_MIN: int = 1
ROUND_TRIP_FEE_RATE: float = 0.0014
ROUND_TRIP_FEE_RATE_PCT: float = 0.14
REANCHOR_NET_BUFFER_MULT: float = 0.994
KRW_PER_USD_DEFAULT: float = 1380.0

TOSS_OPENAPI_BASE_URL: str = "https://openapi.tossinvest.com"


# ---------------------------------------------------------------------------
# [유틸리티] 안전한 수치 형변환 (ZeroDivision / NaN / inf / null 방어 — Case 03, 23)
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
# [Case 68 & Case 75] 폴더 위치(base_dir) 기반 자동 식별기 · 격리 환경변수 로더 · 디스크 자가 치유기
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
    🚨 Case 68 [폴더별 3중 안전 원장 경로 결정기]:
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

    # 1) 고아 임시 파일(*.tmp.*, *.heal.tmp) 전수 청소
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

    # 2) __pycache__ 바이트코드 캐시 청소
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

    # 3) 오래된 일일 스냅샷 백업 정리 (최근 keep_backup_days 개수만 보존)
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
    🚨 Case 68:
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
# [핵심 2] SOXL 단일 롱 7-Tier 순수 멀티 그리드 및 골든포켓 폴더별 3중 안전 지층 원장 (SoxlStratumLedger — Case 68 ~ 84)
# ---------------------------------------------------------------------------
class SoxlStratumLedger:
    """
    🎯 1 ~ 🎯 5 & Case 02, 05, 06, 58 ~ 84:
    현재 봇이 위치한 폴더(`base_dir`)를 기준으로:
    ① 폴더 고유 원장(`soxl_stratum_ledger_<folder_slug>.json` — Git 덮어쓰기 100% 면역)
    ② 표준 호환 원장(`soxl_stratum_ledger.json` — 기존 코드 및 외부 도구 호환 미러)
    ③ 실시간 백업 금고(`ledger_backups/soxl_stratum_ledger_<folder_slug>.bak.json`)
    3곳에 SOXL 1 ~ 7층 순수 멀티 그리드 지층(1층 공격수 + 2 ~ 6층 개별 완충층 + 통합 7층 본대),
    황금시간대(07:00 ~ 07:50 EST & RSI <= 19.0) 선택 모드(`golden_allin_mode`, 기본값 `"NONE"` [OFF]) 및
    독립 골든포켓(`golden_pocket`), 가용 현금 시드(`free_cash_usd`), 정적 잠금/조건부 스텝업 사이클 최저 매수가(`cycle_min_buy_price`),
    STEP2X_15PCT_C20 스텝업 해금 대기 가격(`pending_step_up_min_price`) 및 해금 횟수(`cond_unlock_buy_events`),
    💉 05_RESV_6P_GUARD30 예비시드 수혈 잔액(`injected_reserve_usd`) · 사용 회분(`used_reserve_portions_cnt`) ·
    시드고갈 입금 대기 플래그(`waiting_reserve_deposit`) · 단 1회 입금 알림 영구 래치(`waiting_reserve_deposit_alert_sent`),
    🎯 Case 78 현재 1층 목표 정량 주수(`l1_target_quota_qty` — 부분 체결 시 미체결 잔량 계산 및 1.5초 모니터 재대기용),
    양방향·주기 60초 타임쉴드 시각(`last_buy_fill_ts`, `last_sell_fill_ts`, `last_cycle_end_ts`, `last_sell_gate_eval_ts`, `last_reentry_eval_ts`),
    다중 그리드 및 골든포켓 매도 대기 정보(`pending_sell_indices`, `pending_sell_pocket_qty`), 기정산 주문 ID 링버퍼(`last_settled_order_ids`),
    누적 세후 실현수익금 및 자투리 절약금을 원자적(.tmp -> os.replace)으로 동시 영속화하되,
    Case 75 Dirty-Check 를 적용하여 변경이 없을 때는 불필요한 os.fsync() 디스크 쓰기를 스킵한다.
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
        return {
            "symbol": TARGET_SYMBOL,
            "folder_slug": str(folder_slug or "default_bot"),
            "is_active": True,
            "initial_seed_usd": clean_seed,
            "seed_explicitly_set_100": False,
            "free_cash_usd": clean_seed,
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
        🚨 Case 63, Case 64, Case 67, Case 68, Case 69, Case 70, Case 71, Case 72, Case 73, Case 74, Case 76, Case 77, Case 78 & Case 80:
        1) buy_interval_min = 10, sell_interval_min = 1, max_grid_tiers = 7 (MAX_GRID_TIERS_7),
           portion_mode = "COMP_08PCT", threshold_mode = "WIDE_RUNWAY", unlock_mode = "STEP2X_15PCT_C20" 를 강제 동기화하고,
           golden_allin_mode 는 GOLDEN_ALLIN_MODES ("NONE", "POCKET_ALLIN", "GRID_L1_ALLIN") 중 하나로 검증한다(기본값 "NONE").
        2) 시드머니 결측 또는 0.0 유입 시 $100.0 으로 변조되지 않도록 _resolve_safe_initial_seed() 를 적용한다.
        3) 🛡️ [Case 69, Case 71, Case 72 & Case 80 순수 실물 원가 100% 보존 강제 (리앵커링 원가 차감 영구 폐기)]:
           - 모든 보유 지층(1층 ~ 7층) 및 독립 골든포켓(golden_pocket)의 장부 단가(book_price)와 장부 투자금(book_invested_usd)을
             순수 실물 매수 원가(actual_avg_price = ac / q, actual_cost_usd = ac)와 100% 일치시켜,
             리앵커링 차감이나 이동평균 희석으로 인한 조기 손절 착시를 물리적으로 원천 봉쇄한다!
        4) 🛡️ [Case 67, Case 73, Case 76, Case 78 & Case 80 타임쉴드 · 스텝업 대기값 · 1층 목표 정량 · 골든포켓 매도수량 정규화]
        5) 💉 [Case 77 & Case 80 온디맨드 예비시드 수혈 잔액(injected_reserve_usd) · 골든포켓 투입원금 통합 회계 항등식]:
           - 회계 항등식: free_cash_usd = round(max(0.0, (init_seed + cum_net + injected_reserve_usd) - (actual_inv_buckets + pocket_cost)), 4) 를 정밀 유지한다.
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
        # Case 76: 스텝업 해금 모드 및 카운터 정규화
        st["unlock_mode"] = DEFAULT_UNLOCK_MODE
        st["cond_unlock_buy_events"] = max(
            0, safe_int(st.get("cond_unlock_buy_events"), 0)
        )
        st["daily_unlock_buy_events"] = max(
            0, safe_int(st.get("daily_unlock_buy_events"), 0)
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

        # 기정산 주문 ID 링버퍼(최근 50개) 정규화
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
            # Case 73: 0주 상태에서는 1층 공석 재장전 타임쉴드 시각을 0.0 으로 클리어
            st["last_reentry_eval_ts"] = 0.0
            st["pending_sell_indices"] = []
            st["pending_step_up_min_price"] = 0.0
            # [Case 78 & Case 80]: 그리드 0주 상태에서 미결 그리드 매수가 없으면 l1_target_quota_qty 를 0 으로 클리어
            st["l1_target_quota_qty"] = (
                raw_target_q
                if (has_pending_buy and pending_lot_tag != "GOLDEN_POCKET")
                else 0
            )
        else:
            st["last_sell_gate_eval_ts"] = round(
                max(0.0, safe_float(st.get("last_sell_gate_eval_ts"), 0.0)), 4
            )
            # [Case 67, Case 73 & Case 78]:
            # 활성 1층 보유 중 신규 1층 추매 주문(DIP_1FL / QUOTA_L1 / REENTRY_1FL / GOLDEN_L1)이 발주 대기 중일 때,
            # 기존 1층 수량(cur_l1_q)과 max() 를 취해 신규 추매의 목표 정량(raw_target_q)을 덮어쓰는 오염을 원천 차단!
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
                # 1층이 익절되어 공석(상단 2~7층만 보유)이고 미결 그리드 매수가 없으면 l1_target_quota_qty 를 0 으로 클리어
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
        # Case 77 & Case 80 회계 항등식 확장:
        # 가용현금(free_cash_usd) = max(0.0, (초기시드 + 누적세후실현순익 + 온디맨드 예비시드 수혈잔액) - (보유지층 원금 합계 + 골든포켓 원금))
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
        나머지 모든 실질 필드(buckets, golden_pocket, free_cash_usd, 주문 ID, 타임쉴드 시각, 카운터 등)가
        100% 동일한지 판별한다.
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
        폴더 내 3개 원장 후보(고유 원장 · 실시간 백업 금고 · 호환 원장) 중
        실수로 초기화된 빈 파일 대신 실제 매매 데이터를 보유한 최적 원장을 선택하기 위한 우선순위 튜플.
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
        🚨 Case 68, Case 75, Case 80 & Case 84 [기존 soxl_stratum_ledger.json 100% 무손실 자동 이관 & 3중 금고 Dirty-Check 자가 치유]:
        1) primary_filepath (`soxl_stratum_ledger_<폴더명>.json`)
        2) backup_filepath  (`ledger_backups/soxl_stratum_ledger_<폴더명>.bak.json`)
        3) legacy_filepath  (`soxl_stratum_ledger.json`)
        3개 파일을 모두 검사하여 가장 풍부하고 유효한 상태를 가진 원장을 채택한 뒤,
        _save_sync_unlocked() 내부의 파일별 Dirty-Check 를 통해 실제로 차이가 있거나 누락된 파일에만
        원자적으로 기록한다.
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
                        "📂 [Case 68~84 폴더별 3중 7층 골디락스 그리드 원장 락온 완료] 폴더=[%s] · 채택소스=%s · 시드=$%.2f · 그리드=%d주(%d개층) · 골든포켓=%d주(모드=%s) · 예비수혈=%d/%d회분($%.2f) · 고유원장=%s",
                        self.folder_slug,
                        best_label,
                        safe_float(sanitized.get("initial_seed_usd"), 10000.0),
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
        1) force_write=False 일 때 디스크에 이미 target_path 파일이 존재하면 읽어와
           _is_state_materially_equal() 로 비교하여 실질 데이터 변경이 없을 경우
           .tmp 파일 생성과 os.fsync() 디스크 쓰기를 즉시 스킵(False 반환)한다!
        2) 쓰기 도중 OSError(errno.ENOSPC == 28, No space left on device)가 감지되면
           미완성 .tmp 파일을 즉시 삭제하고 emergency_free_disk_space_sync() 로
           고아 파일·캐시·오래된 백업을 청소한 뒤 1회 재시도하여 원장 0바이트 파손을 철벽 방어한다.
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
        """
        🚨 Case 05, Case 68 & Case 75:
        1) 폴더 고유 원장 (`soxl_stratum_ledger_<folder_slug>.json`)
        2) 호환 미러 원장 (`soxl_stratum_ledger.json`)
        3) 실시간 백업 금고 (`ledger_backups/soxl_stratum_ledger_<folder_slug>.bak.json`)
        3곳 모두 Dirty-Check 후 변경이 있을 때만 원자적(.tmp -> os.replace)으로 동시 기록한다.
        """
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
        16:00 / 17:00 EST 일일 결산 및 GC 시 고아 임시 파일과 오래된 스냅샷을 먼저 정리한 뒤,
        `ledger_backups/soxl_stratum_ledger_<folder_slug>_YYYY-MM-DD.json` 파일을 생성한다.
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
        """
        Case 68 & Case 80:
        백업 금고(`backup_filepath` 또는 최신 일일 스냅샷)에서 유효한 지층(`buckets` 또는 `golden_pocket`)이나
        시드/수익 데이터가 존재하면 읽어와 반환한다.
        """
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
                    # Case 75: 인메모리 상태가 실질적으로 변경되었을 때만 디스크 저장 호출
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
        """
        # [Case 80 : 전술 제어반(/settlement) 황금시간대(07:00 ~ 07:50 EST & RSI <= 19.0) 전액매수 모드 순환 선택기]:
        - target_mode 가 지정되면 해당 모드로 즉시 설정하고,
        - 미지정(인라인 버튼 클릭) 시 "NONE" (⚪ OFF) -> "POCKET_ALLIN" (🌟 독립 골든포켓 ON) ->
          "GRID_L1_ALLIN" (🔥 7층 그리드 1층편입 ON) -> "NONE" (⚪ OFF) 순서로 순환 전환한다.
        """
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
        """
        🚨 Case 02, Case 65, Case 69, Case 70, Case 71, Case 72, Case 73, Case 76, Case 77, Case 78 & Case 80:
        하위 호환용 지층 초기화 메서드 (텔레그램 메뉴/명령어에서는 /reset_profit 으로 대체됨):
        지층 큐(buckets), 독립 골든포켓(golden_pocket), 기준가, 기억된 최저가, 리앵커링 크레딧,
        1층 목표 정량(l1_target_quota_qty), 다중 그리드/포켓 매도 대기 정보, 스텝업 대기 기준가,
        예비시드 수혈 잔액 및 입금 대기 상태, 타임쉴드 시각, 미체결 주문 ID를 원자적으로 0점 초기화하고,
        0주 싸이클 종료 타임쉴드(last_sell_fill_ts, last_cycle_end_ts)를 각인한다.
        """
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
        """
        # [Case 74, Case 76, Case 77 & Case 80]:
        일일 카운터를 새 영업일 기준으로 0회 롤오버하되,
        시드고갈 입금 요청 알림 스팸 방지 래치(`waiting_reserve_deposit_alert_sent`)는
        일일 롤오버 시에도 절대 해제하지 않고 그대로 유지하여 날짜 변경 시 중복 알림 발송을 원천 차단한다!
        """
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


# ---------------------------------------------------------------------------
# [핵심 3] 토스증권 Open API v1.2.14 방탄 클라이언트 (TossApiClient)
# ---------------------------------------------------------------------------
class TossApiClient:
    """
    🏛️ 제1헌법 ~ 제6헌법 & API.txt (v1.2.14) 100% 완벽 구현:
    - OAuth2 토큰 자동 발급 및 만료 전 선제 갱신 (`POST /oauth2/token`)
    - 종합매매 계좌(`BROKERAGE`) `accountSeq` 자동 락온 및 `X-Tossinvest-Account` 헤더 원자적 주입 (`GET /api/v1/accounts`)
    - `REAL_ALLOWED_SYMBOLS = ("SOXL",)` 외 제3종목(SOXS 등) 주문 물리적 차단 (`Case 09`)
    - 외부 패키지(`httpx`/`aiohttp`) 유무에 영향받지 않는 표준 `urllib.request` + `asyncio.to_thread` 방탄 비동기 엔진
    """

    REAL_ALLOWED_SYMBOLS: Tuple[str, ...] = ("SOXL",)

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        base_url: Optional[str] = None,
        base_dir: Optional[str] = None,
    ) -> None:
        self.base_dir: str = _load_env_files_into_environ(base_dir=base_dir)
        self.base_url: str = (
            base_url
            or os.environ.get("TOSS_BASE_URL")
            or os.environ.get("TOSS_API_BASE_URL")
            or TOSS_OPENAPI_BASE_URL
        ).rstrip("/")

        self.client_id: str = (
            client_id
            or os.environ.get("TOSS_CLIENT_ID")
            or os.environ.get("TOSS_API_KEY")
            or os.environ.get("TOSS_APP_KEY")
            or os.environ.get("CLIENT_ID")
            or os.environ.get("APP_KEY")
            or ""
        ).strip()

        self.client_secret: str = (
            client_secret
            or os.environ.get("TOSS_CLIENT_SECRET")
            or os.environ.get("TOSS_API_SECRET")
            or os.environ.get("TOSS_APP_SECRET")
            or os.environ.get("CLIENT_SECRET")
            or os.environ.get("APP_SECRET")
            or ""
        ).strip()

        self._access_token: str = ""
        self._token_expires_mono: float = 0.0
        self._token_lock: asyncio.Lock = asyncio.Lock()

        self.account_seq: Optional[int] = None
        self._account_lock: asyncio.Lock = asyncio.Lock()

        self._fx_cache_rate: float = KRW_PER_USD_DEFAULT
        self._fx_cache_mono: float = 0.0

    def _assert_real_order_symbol(self, symbol: str) -> str:
        sym = str(symbol or "").upper().strip()
        if sym not in self.REAL_ALLOWED_SYMBOLS:
            raise ValueError(
                f"🚨 [Case 09 물리적 주문 차단] 허용되지 않은 종목 주문 시도: {sym} (오직 SOXL 만 허용)"
            )
        return sym

    # -----------------------------------------------------------------------
    # 내부 저수준 HTTP 실행기 (제1헌법: GlobalThrottle.wait_api_sync + asyncio.to_thread)
    # -----------------------------------------------------------------------
    def _execute_http_sync(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        body_bytes: Optional[bytes],
        rate_group: str,
        timeout_sec: float,
    ) -> Tuple[int, Dict[str, Any]]:
        GlobalThrottle.wait_api_sync(rate_group)
        req = urllib.request.Request(
            url=url,
            data=body_bytes,
            headers=headers,
            method=method.upper(),
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                status_code = int(resp.getcode() or 200)
                raw_bytes = resp.read()
                if not raw_bytes:
                    return status_code, {}
                text = raw_bytes.decode("utf-8", errors="replace").strip()
                if not text:
                    return status_code, {}
                return status_code, json.loads(text)
        except urllib.error.HTTPError as http_err:
            status_code = int(http_err.code or 500)
            err_payload: Dict[str, Any] = {}
            try:
                err_bytes = http_err.read()
                if err_bytes:
                    err_payload = json.loads(
                        err_bytes.decode("utf-8", errors="replace")
                    )
            except Exception:
                err_payload = {}
            return status_code, err_payload

    async def _ensure_access_token(self, force_refresh: bool = False) -> str:
        if (
            not force_refresh
            and self._access_token
            and time.monotonic() < (self._token_expires_mono - 120.0)
        ):
            return self._access_token

        async with self._token_lock:
            if (
                not force_refresh
                and self._access_token
                and time.monotonic() < (self._token_expires_mono - 120.0)
            ):
                return self._access_token

            if not self.client_id or not self.client_secret:
                _load_env_files_into_environ(base_dir=self.base_dir)
                self.client_id = (
                    os.environ.get("TOSS_CLIENT_ID")
                    or os.environ.get("TOSS_API_KEY")
                    or os.environ.get("CLIENT_ID")
                    or self.client_id
                ).strip()
                self.client_secret = (
                    os.environ.get("TOSS_CLIENT_SECRET")
                    or os.environ.get("TOSS_API_SECRET")
                    or os.environ.get("CLIENT_SECRET")
                    or self.client_secret
                ).strip()

            url = f"{self.base_url}/oauth2/token"
            form_data = urllib.parse.urlencode(
                {
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                }
            ).encode("utf-8")
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            }

            status_code, payload = await asyncio.wait_for(
                asyncio.to_thread(
                    self._execute_http_sync,
                    "POST",
                    url,
                    headers,
                    form_data,
                    "AUTH",
                    10.0,
                ),
                timeout=12.0,
            )
            if status_code != 200 or not isinstance(payload, dict):
                err_code = str(payload.get("error") or f"http-{status_code}")
                err_desc = str(
                    payload.get("error_description") or "OAuth2 토큰 발급 실패"
                )
                raise _NonRetryableApiError(
                    status_code, err_code, err_desc, payload
                )

            token = str(payload.get("access_token") or "").strip()
            expires_in = max(300, safe_int(payload.get("expires_in"), 86400))
            if not token:
                raise _NonRetryableApiError(
                    500, "empty-token", "access_token 이 비어 있습니다.", payload
                )

            self._access_token = token
            self._token_expires_mono = time.monotonic() + float(expires_in)
            return self._access_token

    async def ensure_account_seq(self) -> int:
        """
        🚨 제2헌법:
        GET /api/v1/accounts 를 호출하여 BROKERAGE(종합매매) 계좌의 accountSeq 를 메모리에 락온한다.
        """
        if self.account_seq is not None and self.account_seq > 0:
            return self.account_seq

        async with self._account_lock:
            if self.account_seq is not None and self.account_seq > 0:
                return self.account_seq

            env_seq = safe_int(os.environ.get("TOSS_ACCOUNT_SEQ"), 0)
            res = await self._request(
                method="GET",
                path="/api/v1/accounts",
                require_account=False,
                rate_group="ACCOUNT",
            )
            items = res.get("result") if isinstance(res, dict) else []
            if isinstance(items, list) and items:
                chosen_seq = 0
                for acc in items:
                    if isinstance(acc, dict):
                        acc_type = (
                            str(acc.get("accountType") or "").upper().strip()
                        )
                        seq_val = safe_int(acc.get("accountSeq"), 0)
                        if acc_type == "BROKERAGE" and seq_val > 0:
                            chosen_seq = seq_val
                            break
                if chosen_seq <= 0 and isinstance(items[0], dict):
                    chosen_seq = safe_int(items[0].get("accountSeq"), 0)
                if chosen_seq > 0:
                    self.account_seq = chosen_seq
                    return self.account_seq

            if env_seq > 0:
                self.account_seq = env_seq
                return self.account_seq

            self.account_seq = 1
            return self.account_seq

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        require_account: bool = False,
        rate_group: str = "DEFAULT",
        timeout_sec: float = 10.0,
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        """
        🚨 제1헌법, 제2헌법 & Case 20, 21:
        모든 토스 Open API 요청을 처리하는 중앙 비동기 디스패처.
        """
        clean_path = path if path.startswith("/") else f"/{path}"
        url = f"{self.base_url}{clean_path}"
        if params:
            filtered_params = {
                k: (
                    "true"
                    if v is True
                    else ("false" if v is False else str(v))
                )
                for k, v in params.items()
                if v is not None
            }
            if filtered_params:
                url = f"{url}?{urllib.parse.urlencode(filtered_params)}"

        body_bytes: Optional[bytes] = None
        if json_data is not None:
            body_bytes = json.dumps(json_data, ensure_ascii=False).encode(
                "utf-8"
            )

        last_exc: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                token = await self._ensure_access_token(
                    force_refresh=(attempt > 0 and last_exc is None)
                )
                headers: Dict[str, str] = {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                }
                if body_bytes is not None:
                    headers["Content-Type"] = "application/json"

                if require_account:
                    acc_seq = await self.ensure_account_seq()
                    headers["X-Tossinvest-Account"] = str(acc_seq)

                status_code, payload = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._execute_http_sync,
                        method,
                        url,
                        headers,
                        body_bytes,
                        rate_group,
                        timeout_sec,
                    ),
                    timeout=timeout_sec + 3.0,
                )

                if 200 <= status_code < 300:
                    return (
                        payload
                        if isinstance(payload, dict)
                        else {"result": payload}
                    )

                err_obj = (
                    payload.get("error")
                    if isinstance(payload, dict)
                    and isinstance(payload.get("error"), dict)
                    else {}
                )
                err_code = str(
                    err_obj.get("code")
                    or (
                        payload.get("error")
                        if isinstance(payload, dict)
                        else ""
                    )
                    or f"http-{status_code}"
                )
                err_msg = str(
                    err_obj.get("message")
                    or (
                        payload.get("error_description")
                        if isinstance(payload, dict)
                        else ""
                    )
                    or f"HTTP {status_code}"
                )

                if status_code == 401 and attempt < max_retries:
                    self._access_token = ""
                    last_exc = None
                    continue

                if (
                    status_code in (429, 500, 502, 503, 504)
                    and attempt < max_retries
                ):
                    await asyncio.sleep(0.35 * (attempt + 1))
                    continue

                raise _NonRetryableApiError(
                    status_code, err_code, err_msg, payload
                )

            except _NonRetryableApiError:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries:
                    await asyncio.sleep(0.30 * (attempt + 1))
                else:
                    raise

        if last_exc:
            raise last_exc
        return {}

    # -----------------------------------------------------------------------
    # [Market Data 그룹] 현재가 · 호가 · 최근체결 · 윗꼬리 체결최고가 · 1분봉/일봉 차트 (API.txt v1.2.14)
    # -----------------------------------------------------------------------
    async def get_current_prices_batch(
        self, symbols: Iterable[str] = (TARGET_SYMBOL,)
    ) -> Dict[str, float]:
        """
        GET /api/v1/prices?symbols=SOXL
        """
        sym_list = [
            str(s).upper().strip() for s in symbols if str(s).strip()
        ]
        if not sym_list:
            sym_list = [TARGET_SYMBOL]
        out: Dict[str, float] = {s: 0.0 for s in sym_list}
        try:
            res = await self._request(
                method="GET",
                path="/api/v1/prices",
                params={"symbols": ",".join(sym_list)},
                require_account=False,
                rate_group="MARKET_DATA",
            )
            items = res.get("result") if isinstance(res, dict) else []
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, dict):
                        s = str(it.get("symbol") or "").upper().strip()
                        lp = safe_float(it.get("lastPrice"), 0.0)
                        if s and lp > 0.0:
                            out[s] = lp
        except Exception as exc:
            logger.debug("get_current_prices_batch 예외: %s", exc)
        return out

    async def get_current_price(self, symbol: str = TARGET_SYMBOL) -> float:
        p_map = await self.get_current_prices_batch((symbol,))
        return safe_float(p_map.get(str(symbol).upper().strip()), 0.0)

    async def get_recent_trades(
        self, symbol: str = TARGET_SYMBOL, count: int = 50
    ) -> List[Dict[str, Any]]:
        """
        # [API.txt v1.2.14 & Case 80, Case 82]:
        GET /api/v1/trades?symbol=SOXL&count=50
        당일 최근 체결 내역(price, volume, timestamp)을 조회하여 캔들 차트 지연 시 보조 시계열 및
        1분봉 윗꼬리(Upper-Wick) 순간 체결 최고가 포착에 활용한다.
        """
        q_cnt = max(1, min(50, safe_int(count, 50)))
        try:
            res = await self._request(
                method="GET",
                path="/api/v1/trades",
                params={
                    "symbol": str(symbol or TARGET_SYMBOL).upper().strip(),
                    "count": q_cnt,
                },
                require_account=False,
                rate_group="MARKET_DATA",
            )
            items = res.get("result") if isinstance(res, dict) else []
            if isinstance(items, list):
                return [t for t in items if isinstance(t, dict)]
        except Exception as exc:
            logger.debug("get_recent_trades 예외(묵음): %s", exc)
        return []

    @staticmethod
    def _parse_iso_timestamp_to_epoch(ts_val: Any) -> float:
        """
        # [Case 82 : GET /api/v1/trades ISO 8601 체결 시각 -> UTC Epoch(float) 변환기]:
        예: "2026-03-25T22:30:42.100+09:00" 또는 "2026-10-29T06:57:02.120Z" 또는 숫자형 epoch 를
        초 단위 float 타임스탬프로 안전하게 변환한다.
        """
        if ts_val is None or isinstance(ts_val, bool):
            return 0.0
        if isinstance(ts_val, (int, float)):
            f_ts = safe_float(ts_val, 0.0)
            if f_ts > 1e12:
                return f_ts / 1000.0
            return max(0.0, f_ts)
        s = str(ts_val).strip()
        if not s:
            return 0.0
        try:
            if s.endswith("Z") or s.endswith("z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=EST_TZ)
            return float(dt.timestamp())
        except Exception:
            num_ts = safe_float(s, 0.0)
            if num_ts > 1e12:
                return num_ts / 1000.0
            return max(0.0, num_ts)

    async def get_recent_wick_high_price(
        self,
        symbol: str = TARGET_SYMBOL,
        lookback_sec: float = 5.0,
        min_after_ts: float = 0.0,
        count: int = 15,
    ) -> Tuple[float, float]:
        """
        # MODIFIED [Case 82 : 1분봉 윗꼬리(Upper-Wick) 슈팅 포착용 최근 체결 최고가 추출기 (서버 시차 -5.0s 허용)]:
        GET /api/v1/prices 는 단일 스냅샷(lastPrice)만 반환하므로 1.5 ~ 2.5초 폴링 간격 사이에
        0.3초 동안만 찍히고 내려온 $104.00 윗꼬리 체결틱을 놓칠 수 있다.
        이를 원천 보완하기 위해 GET /api/v1/trades?symbol=SOXL&count=15 를 호출하여:
        1) 체결 시각(trade_epoch)이 현재 시각 기준 최근 lookback_sec(기본 5.0초, 서버 NTP 시차 -5.0초 허용) 이내이고,
        2) 직전 매수/매도 체결 시각 및 기소모된 윗꼬리 시각(min_after_ts) 이후에 발생한 유효 체결틱 중
           가장 높은 체결가(best_price)와 해당 체결 시각(best_ts)을 (best_price, best_ts) 튜플로 반환한다.
        """
        trades = await self.get_recent_trades(
            symbol=symbol, count=max(1, min(50, safe_int(count, 15)))
        )
        if not trades:
            return 0.0, 0.0

        now_epoch = time.time()
        max_age = max(1.0, safe_float(lookback_sec, 5.0))
        after_cut = max(0.0, safe_float(min_after_ts, 0.0))

        best_price: float = 0.0
        best_ts: float = 0.0

        for t in trades:
            if not isinstance(t, dict):
                continue
            p = safe_float(t.get("price"), 0.0)
            if p <= 0.0:
                continue
            vol = safe_float(t.get("volume"), 1.0)
            if vol <= 0.0:
                continue

            t_epoch = self._parse_iso_timestamp_to_epoch(
                t.get("timestamp")
                or t.get("dt")
                or t.get("dateTime")
                or t.get("time")
            )
            if t_epoch <= 0.0:
                continue

            if after_cut > 0.0 and t_epoch <= (after_cut + 1e-6):
                continue

            age_sec = now_epoch - t_epoch
            if age_sec > max_age or age_sec < -5.0:
                continue

            if p > best_price or (
                abs(p - best_price) < 1e-9 and t_epoch > best_ts
            ):
                best_price = p
                best_ts = t_epoch

        return round(best_price, 4), round(best_ts, 4)

    async def get_orderbook(
        self, symbol: str = TARGET_SYMBOL
    ) -> Dict[str, Any]:
        """
        GET /api/v1/orderbook?symbol=SOXL
        """
        try:
            res = await self._request(
                method="GET",
                path="/api/v1/orderbook",
                params={
                    "symbol": str(symbol or TARGET_SYMBOL).upper().strip()
                },
                require_account=False,
                rate_group="MARKET_DATA",
            )
            r_obj = res.get("result") if isinstance(res, dict) else {}
            return r_obj if isinstance(r_obj, dict) else {}
        except Exception as exc:
            logger.debug("get_orderbook 예외: %s", exc)
            return {}

    async def get_best_bid_price(
        self, symbol: str = TARGET_SYMBOL, fallback_price: float = 0.0
    ) -> float:
        ob = await self.get_orderbook(symbol=symbol)
        bids = ob.get("bids") if isinstance(ob, dict) else None
        if isinstance(bids, list) and bids:
            prices = [
                safe_float(b.get("price"), 0.0)
                for b in bids
                if isinstance(b, dict)
                and safe_float(b.get("price"), 0.0) > 0.0
            ]
            if prices:
                return max(prices)
        return safe_float(fallback_price, 0.0)

    async def get_best_ask_price(
        self, symbol: str = TARGET_SYMBOL, fallback_price: float = 0.0
    ) -> float:
        ob = await self.get_orderbook(symbol=symbol)
        asks = ob.get("asks") if isinstance(ob, dict) else None
        if isinstance(asks, list) and asks:
            prices = [
                safe_float(a.get("price"), 0.0)
                for a in asks
                if isinstance(a, dict)
                and safe_float(a.get("price"), 0.0) > 0.0
            ]
            if prices:
                return min(prices)
        return safe_float(fallback_price, 0.0)

    @staticmethod
    def _parse_candle_page_result(
        res: Any,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        # [Case 80 캔들 응답 스키마 다변화 방탄 파서]:
        API 응답이 {"result": {"candles": [...], "nextBefore": ...}} 표준 형식일 때뿐만 아니라,
        {"result": [...]} 리스트 직접 반환 또는 {"candles": [...]} / {"items": [...]} / {"data": [...]}
        구조일 때도 단 1건의 누락 없이 캔들 배열과 nextBefore 커서를 추출한다.
        """
        if not isinstance(res, dict):
            if isinstance(res, list):
                return [c for c in res if isinstance(c, dict)], None
            return [], None

        r_obj = res.get("result") if "result" in res else res
        if isinstance(r_obj, list):
            return [c for c in r_obj if isinstance(c, dict)], None
        if isinstance(r_obj, dict):
            candles = (
                r_obj.get("candles")
                if r_obj.get("candles") is not None
                else (
                    r_obj.get("items")
                    if r_obj.get("items") is not None
                    else r_obj.get("data")
                )
            )
            next_before = r_obj.get("nextBefore")
            c_list = (
                [c for c in candles if isinstance(c, dict)]
                if isinstance(candles, list)
                else []
            )
            return c_list, (str(next_before).strip() if next_before else None)
        return [], None

    async def get_candles(
        self,
        symbol: str = TARGET_SYMBOL,
        interval: str = "1m",
        count: int = 200,
        before: Optional[str] = None,
        adjusted: bool = True,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        # [Case 80 : GET /api/v1/candles 방탄 폴백 탑재]:
        1) 요청된 count(최대 200) 및 adjusted 파라미터로 1차 조회한다.
        2) 만약 브로커 서버가 특정 세션에서 adjusted 또는 count=200 에 대해 에러나 빈 배열을 반환하면
           즉시 기본 파라미터(count=min(100, q_cnt), adjusted 생략)로 자동 폴백 재시도한다.
        """
        sym_clean = str(symbol or TARGET_SYMBOL).upper().strip()
        intv_clean = str(interval or "1m").strip()
        q_cnt = max(1, min(200, safe_int(count, 100)))
        params: Dict[str, Any] = {
            "symbol": sym_clean,
            "interval": intv_clean,
            "count": q_cnt,
            "adjusted": bool(adjusted),
        }
        if before:
            params["before"] = str(before).strip()

        try:
            res = await self._request(
                method="GET",
                path="/api/v1/candles",
                params=params,
                require_account=False,
                rate_group="MARKET_DATA_CHART",
            )
            c_list, next_b = self._parse_candle_page_result(res)
            if c_list:
                return c_list, next_b
        except Exception as exc:
            logger.debug(
                "get_candles 1차 호출 폴백 전환(%s, %s, before=%s): %s",
                sym_clean,
                intv_clean,
                before,
                exc,
            )

        # 폴백 재시도: before 가 없을 때 adjusted 파라미터를 생략하고 표준 기본 count(최대 100)로 재요청
        if not before:
            fb_params: Dict[str, Any] = {
                "symbol": sym_clean,
                "interval": intv_clean,
                "count": min(100, q_cnt),
            }
            try:
                res_fb = await self._request(
                    method="GET",
                    path="/api/v1/candles",
                    params=fb_params,
                    require_account=False,
                    rate_group="MARKET_DATA_CHART",
                )
                return self._parse_candle_page_result(res_fb)
            except Exception as exc2:
                logger.debug("get_candles 2차 폴백 예외(묵음): %s", exc2)

        return [], None

    async def get_candles_1m(
        self,
        symbol: str = TARGET_SYMBOL,
        total_count: int = 300,
        adjusted: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        # [Case 80 : 1분봉 다중 페이지네이션 페이지별 독립 예외 격리]:
        GET /api/v1/candles (interval="1m") 를 nextBefore 페이지네이션으로 호출하여
        최대 total_count(기본 300)개의 1분봉 리스트를 반환한다.
        - 1페이지(최신 200봉) 수신 성공 후 2페이지(before 커서) 조회에서 에러가 발생하더라도
          이미 확보한 1페이지 200봉이 절대 유실되지 않도록 페이지별로 예외를 격리한다!
        - nextBefore 커서가 직전 커서와 동일할 경우 즉시 루프를 종료하여 무한 루프를 차단한다.
        """
        target_cnt = max(1, min(600, safe_int(total_count, 300)))
        collected: List[Dict[str, Any]] = []
        seen_ts: Set[str] = set()
        before_cursor: Optional[str] = None
        max_pages = max(1, int(math.ceil(target_cnt / 200.0)) + 1)

        for page_idx in range(max_pages):
            rem = max(1, min(200, target_cnt - len(collected) + 1))
            try:
                batch, next_b = await self.get_candles(
                    symbol=symbol,
                    interval="1m",
                    count=(200 if page_idx == 0 and target_cnt >= 100 else rem),
                    before=before_cursor,
                    adjusted=adjusted,
                )
            except Exception as exc:
                logger.debug(
                    "get_candles_1m 페이지(%d) 조회 예외(기수집 %d봉 보존): %s",
                    page_idx,
                    len(collected),
                    exc,
                )
                break

            if not batch:
                break

            added_in_page = 0
            for c in batch:
                if not isinstance(c, dict):
                    continue
                ts_str = str(
                    c.get("timestamp")
                    or c.get("dt")
                    or c.get("dateTime")
                    or c.get("time")
                    or ""
                ).strip()
                if ts_str and ts_str not in seen_ts:
                    seen_ts.add(ts_str)
                    collected.append(c)
                    added_in_page += 1

            if (
                not next_b
                or next_b == before_cursor
                or added_in_page == 0
                or len(collected) >= target_cnt
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
        if len(collected) > target_cnt:
            collected = collected[-target_cnt:]
        return collected

    async def get_candles_1d(
        self,
        symbol: str = TARGET_SYMBOL,
        count: int = 10,
        adjusted: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        GET /api/v1/candles (interval="1d") 일봉 데이터를 조회한다.
        """
        try:
            batch, _ = await self.get_candles(
                symbol=symbol,
                interval="1d",
                count=max(1, min(200, safe_int(count, 10))),
                adjusted=adjusted,
            )
            batch.sort(key=lambda x: str(x.get("timestamp") or ""))
            return batch
        except Exception as exc:
            logger.debug("get_candles_1d 조회 예외: %s", exc)
            return []

    # -----------------------------------------------------------------------
    # [Market Info 그룹] USD/KRW 환율 및 미국 장 캘린더 (API.txt v1.2.14)
    # -----------------------------------------------------------------------
    async def get_usd_krw_rate(self) -> float:
        """
        GET /api/v1/exchange-rate?baseCurrency=USD&quoteCurrency=KRW (60초 캐시)
        """
        now_m = time.monotonic()
        if (
            self._fx_cache_rate > 0.0
            and (now_m - self._fx_cache_mono) < 60.0
        ):
            return self._fx_cache_rate

        try:
            res = await self._request(
                method="GET",
                path="/api/v1/exchange-rate",
                params={"baseCurrency": "USD", "quoteCurrency": "KRW"},
                require_account=False,
                rate_group="MARKET_INFO",
            )
            r_obj = res.get("result") if isinstance(res, dict) else {}
            if isinstance(r_obj, dict):
                rate_val = safe_float(
                    r_obj.get("rate") or r_obj.get("midRate"), 0.0
                )
                if rate_val > 100.0:
                    self._fx_cache_rate = rate_val
                    self._fx_cache_mono = now_m
                    return rate_val
        except Exception as exc:
            logger.debug("환율 조회 폴백 사용: %s", exc)

        return (
            self._fx_cache_rate
            if self._fx_cache_rate > 0.0
            else KRW_PER_USD_DEFAULT
        )

    async def get_us_market_calendar(
        self, date_str: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        GET /api/v1/market-calendar/US
        """
        params: Dict[str, Any] = {}
        if date_str:
            params["date"] = str(date_str)
        try:
            res = await self._request(
                method="GET",
                path="/api/v1/market-calendar/US",
                params=params,
                require_account=False,
                rate_group="MARKET_INFO",
            )
            r_obj = res.get("result") if isinstance(res, dict) else {}
            return r_obj if isinstance(r_obj, dict) else {}
        except Exception as exc:
            logger.debug("미국 장 캘린더 조회 폴백: %s", exc)
            return {}

    # -----------------------------------------------------------------------
    # [Asset & Order Info 그룹] 보유 잔고 · 매수가능금액 · 매도가능수량 (Case 03)
    # -----------------------------------------------------------------------
    @staticmethod
    def _empty_holding_dict(symbol: str = TARGET_SYMBOL) -> Dict[str, Any]:
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

    async def get_holdings_map_with_status(
        self, symbol: Optional[str] = None
    ) -> Tuple[Dict[str, Dict[str, Any]], bool]:
        """
        🚨 Case 03:
        GET /api/v1/holdings 를 호출하여 (holdings_map, fetch_ok) 튜플을 반환한다.
        """
        out_map: Dict[str, Dict[str, Any]] = {
            TARGET_SYMBOL: self._empty_holding_dict(TARGET_SYMBOL)
        }
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = str(symbol).upper().strip()

        try:
            res = await self._request(
                method="GET",
                path="/api/v1/holdings",
                params=params if params else None,
                require_account=True,
                rate_group="ASSET",
            )
            r_obj = res.get("result") if isinstance(res, dict) else None
            if not isinstance(r_obj, dict):
                return out_map, False

            items = r_obj.get("items")
            if isinstance(items, list):
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    sym = str(it.get("symbol") or "").upper().strip()
                    if not sym:
                        continue
                    qty = max(0, safe_int(it.get("quantity"), 0))
                    avg_p = round(
                        max(
                            0.0,
                            safe_float(it.get("averagePurchasePrice"), 0.0),
                        ),
                        4,
                    )
                    last_p = round(
                        max(0.0, safe_float(it.get("lastPrice"), avg_p)), 4
                    )

                    mv_obj = (
                        it.get("marketValue")
                        if isinstance(it.get("marketValue"), dict)
                        else {}
                    )
                    pl_obj = (
                        it.get("profitLoss")
                        if isinstance(it.get("profitLoss"), dict)
                        else {}
                    )

                    pur_amt = round(
                        max(
                            0.0,
                            safe_float(
                                mv_obj.get("purchaseAmount"),
                                float(qty) * avg_p,
                            ),
                        ),
                        4,
                    )
                    eval_amt = round(
                        max(
                            0.0,
                            safe_float(
                                mv_obj.get("amount"), float(qty) * last_p
                            ),
                        ),
                        4,
                    )
                    pnl_amt = round(
                        safe_float(
                            pl_obj.get("amountAfterCost")
                            if pl_obj.get("amountAfterCost") is not None
                            else pl_obj.get("amount"),
                            eval_amt - pur_amt,
                        ),
                        4,
                    )
                    raw_rate = safe_float(
                        pl_obj.get("rateAfterCost")
                        if pl_obj.get("rateAfterCost") is not None
                        else pl_obj.get("rate"),
                        0.0,
                    )
                    profit_rate_pct = round(raw_rate * 100.0, 2)

                    out_map[sym] = {
                        "symbol": sym,
                        "qty": qty,
                        "quantity": qty,
                        "avg_price": avg_p,
                        "averagePurchasePrice": avg_p,
                        "last_price": last_p,
                        "lastPrice": last_p,
                        "purchase_amount": pur_amt,
                        "eval_amount": eval_amt,
                        "profit_loss": pnl_amt,
                        "profit_rate": profit_rate_pct,
                    }
            return out_map, True
        except Exception as exc:
            logger.warning("보유 잔고 조회(/api/v1/holdings) 예외: %s", exc)
            return out_map, False

    async def get_holdings_map(
        self, symbol: Optional[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        h_map, _ = await self.get_holdings_map_with_status(symbol=symbol)
        return h_map

    async def get_holdings(
        self, symbol: Optional[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        h_map, _ = await self.get_holdings_map_with_status(symbol=symbol)
        return h_map

    async def get_buying_power_usd(
        self, safety_buffer_pct: float = 0.2
    ) -> float:
        """
        GET /api/v1/buying-power?currency=USD
        """
        try:
            res = await self._request(
                method="GET",
                path="/api/v1/buying-power",
                params={"currency": "USD"},
                require_account=True,
                rate_group="ORDER_INFO",
            )
            r_obj = res.get("result") if isinstance(res, dict) else {}
            if isinstance(r_obj, dict):
                raw_bp = max(
                    0.0, safe_float(r_obj.get("cashBuyingPower"), 0.0)
                )
                mult = max(
                    0.90,
                    min(
                        1.0,
                        1.0 - safe_float(safety_buffer_pct, 0.0) / 100.0,
                    ),
                )
                return round(raw_bp * mult, 4)
        except Exception as exc:
            logger.debug("매수가능금액 조회 예외: %s", exc)
        return 0.0

    async def get_sellable_quantity(
        self, symbol: str = TARGET_SYMBOL
    ) -> int:
        """
        GET /api/v1/sellable-quantity?symbol=SOXL
        """
        sym = self._assert_real_order_symbol(symbol)
        try:
            res = await self._request(
                method="GET",
                path="/api/v1/sellable-quantity",
                params={"symbol": sym},
                require_account=True,
                rate_group="ORDER_INFO",
            )
            r_obj = res.get("result") if isinstance(res, dict) else {}
            if isinstance(r_obj, dict):
                return max(
                    0,
                    int(
                        math.floor(
                            safe_float(r_obj.get("sellableQuantity"), 0.0)
                            + 1e-9
                        )
                    ),
                )
        except Exception as exc:
            logger.debug("매도가능수량 조회 예외: %s", exc)
        return 0

    # -----------------------------------------------------------------------
    # [Order & Order History 그룹] 주문 생성 · 정정 · 취소 · 상세/목록 조회 · 수동체결 역추적
    # -----------------------------------------------------------------------
    @staticmethod
    def _format_us_limit_price(price: float) -> str:
        p = max(0.0001, safe_float(price, 0.01))
        if p >= 1.0:
            p_trunc = math.floor((p + 1e-9) * 100.0) / 100.0
            return f"{p_trunc:.2f}"
        p_trunc = math.floor((p + 1e-9) * 10000.0) / 10000.0
        return f"{p_trunc:.4f}"

    async def create_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        order_type: str = "LIMIT",
        time_in_force: str = "DAY",
        client_order_id: Optional[str] = None,
        enforce_daymarket_block: bool = False,
    ) -> Dict[str, Any]:
        """
        🎯 5 & 제5헌법 & Case 01, 09, 18, 79:
        POST /api/v1/orders (오직 SOXL LIMIT 지정가 주문만 허용)
        - enforce_daymarket_block=True 이고 BUY 주문일 때는 주말(토·일요일) 및
          평일 04:07 ~ 16:00 EST 외 모든 매수 주문을 물리적으로 원천 차단한다.
        """
        sym = self._assert_real_order_symbol(symbol)
        clean_side = str(side or "BUY").upper().strip()
        if clean_side not in ("BUY", "SELL"):
            raise ValueError(f"유효하지 않은 주문 방향: {clean_side}")

        # [Case 01 & Case 79]: 평일 04:07 ~ 16:00 EST 외(주말 토·일요일 포함) 모든 매수 주문 물리적 차단
        if enforce_daymarket_block and clean_side == "BUY":
            now_est = datetime.now(EST_TZ)
            hm = now_est.hour * 100 + now_est.minute
            if now_est.weekday() >= 5 or not (407 <= hm <= 1600):
                raise _NonRetryableApiError(
                    422,
                    "outside-active-window",
                    f"평일 04:07 ~ 16:00 EST 외 매수 차단 (현재 요일={now_est.weekday()}, {hm:04d} EST)",
                )

        qty_int = max(1, safe_int(quantity, 1))
        cid = str(
            client_order_id or generate_client_order_id(prefix=clean_side)
        ).strip()[:36]
        price_str = self._format_us_limit_price(price)

        payload: Dict[str, Any] = {
            "clientOrderId": cid,
            "symbol": sym,
            "side": clean_side,
            "orderType": "LIMIT",
            "timeInForce": str(time_in_force or "DAY").upper().strip(),
            "quantity": str(qty_int),
            "price": price_str,
        }

        res = await self._request(
            method="POST",
            path="/api/v1/orders",
            json_data=payload,
            require_account=True,
            rate_group="ORDER",
        )
        r_obj = res.get("result") if isinstance(res, dict) else {}
        return r_obj if isinstance(r_obj, dict) else {}

    async def modify_order(
        self,
        order_id: str,
        new_price: float,
        order_type: str = "LIMIT",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        🎯 5 (토스 US 주식 정정 규격 엄수):
        POST /api/v1/orders/{orderId}/modify
        미국 주식 주문 정정 시 `quantity` 를 전달하면 `400 us-modify-quantity-not-supported` 에러가 발생하므로
        오직 `orderType` 과 `price` 만 전송한다.
        """
        oid = str(order_id or "").strip()
        if not oid:
            raise ValueError("modify_order: order_id 가 비어 있습니다.")

        payload: Dict[str, Any] = {
            "orderType": "LIMIT",
            "price": self._format_us_limit_price(new_price),
        }
        res = await self._request(
            method="POST",
            path=f"/api/v1/orders/{urllib.parse.quote(oid, safe='')}/modify",
            json_data=payload,
            require_account=True,
            rate_group="ORDER",
        )
        r_obj = res.get("result") if isinstance(res, dict) else {}
        return r_obj if isinstance(r_obj, dict) else {}

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        🎯 5 (HTTP 415 원천 방어):
        POST /api/v1/orders/{orderId}/cancel 호출 시 반드시 빈 JSON 객체 `{}` 를 전송한다.
        """
        oid = str(order_id or "").strip()
        if not oid:
            return {}
        res = await self._request(
            method="POST",
            path=f"/api/v1/orders/{urllib.parse.quote(oid, safe='')}/cancel",
            json_data={},
            require_account=True,
            rate_group="ORDER",
        )
        r_obj = res.get("result") if isinstance(res, dict) else {}
        return r_obj if isinstance(r_obj, dict) else {}

    async def get_order_detail(
        self, order_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        GET /api/v1/orders/{orderId}
        """
        oid = str(order_id or "").strip()
        if not oid:
            return None
        try:
            res = await self._request(
                method="GET",
                path=f"/api/v1/orders/{urllib.parse.quote(oid, safe='')}",
                require_account=True,
                rate_group="ORDER_HISTORY",
            )
            r_obj = res.get("result") if isinstance(res, dict) else None
            return r_obj if isinstance(r_obj, dict) else None
        except Exception as exc:
            logger.debug("주문 상세 조회(%s) 예외: %s", oid, exc)
            return None

    async def get_open_orders(
        self, symbol: str = TARGET_SYMBOL
    ) -> List[Dict[str, Any]]:
        """
        GET /api/v1/orders?status=OPEN&symbol=SOXL
        """
        params: Dict[str, Any] = {"status": "OPEN"}
        if symbol:
            params["symbol"] = str(symbol).upper().strip()
        try:
            res = await self._request(
                method="GET",
                path="/api/v1/orders",
                params=params,
                require_account=True,
                rate_group="ORDER_HISTORY",
            )
            r_obj = res.get("result") if isinstance(res, dict) else {}
            if isinstance(r_obj, dict) and isinstance(
                r_obj.get("orders"), list
            ):
                return [
                    o for o in r_obj["orders"] if isinstance(o, dict)
                ]
        except Exception as exc:
            logger.debug("미체결 주문 목록 조회 예외: %s", exc)
        return []

    async def get_closed_orders(
        self, symbol: str = TARGET_SYMBOL, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        # (API.txt v1.2.14 준수):
        GET /api/v1/orders?status=CLOSED&symbol=SOXL&limit=20
        종료된 주문(FILLED, CANCELED, REJECTED, REPLACED 등) 목록을 최신순으로 조회한다.
        """
        params: Dict[str, Any] = {
            "status": "CLOSED",
            "limit": max(1, min(100, safe_int(limit, 20))),
        }
        if symbol:
            params["symbol"] = str(symbol).upper().strip()
        try:
            res = await self._request(
                method="GET",
                path="/api/v1/orders",
                params=params,
                require_account=True,
                rate_group="ORDER_HISTORY",
            )
            r_obj = res.get("result") if isinstance(res, dict) else {}
            if isinstance(r_obj, dict) and isinstance(
                r_obj.get("orders"), list
            ):
                return [
                    o for o in r_obj["orders"] if isinstance(o, dict)
                ]
        except Exception as exc:
            logger.debug("종료 주문 목록 조회(/api/v1/orders?status=CLOSED) 예외: %s", exc)
        return []

    async def probe_latest_manual_fill_price(
        self,
        side: str,
        target_qty: int,
        settled_order_ids: Iterable[str] = (),
        fallback_price: float = 0.0,
        symbol: str = TARGET_SYMBOL,
    ) -> Tuple[float, List[str]]:
        """
        # [Case 19 & Case 63 수동 매수·매도 실체결가 역추적기 (API.txt OrderStatus 규격 엄수)]:
        GET /api/v1/orders?status=CLOSED&symbol=SOXL 응답에서:
        1) 봇이 이미 정산한 settled_order_ids 를 제외하고,
        2) CANCEL_REJECTED (취소 거부 별도 레코드), REPLACE_REJECTED (정정 거부 별도 레코드),
           REJECTED (주문 거부), REPLACED (정정 대체된 원주문) 등 중복/미체결 오인 위험 상태를 원천 배제하며,
        3) 요청된 방향(side="BUY" 또는 "SELL")의 실제 체결 완료 건(FILLED 및 부분 체결 후 종료된 PARTIAL_FILLED / CANCELED 중
           execution.filledQuantity > 0 & averageFilledPrice > 0)들을 target_qty 수량만큼 역추적하여
           수량 가중평균 체결단가와 매칭된 orderId 리스트를 반환한다.
        """
        target_side = str(side or "SELL").upper().strip()
        need_q = max(1, safe_int(target_qty, 1))
        settled_set: Set[str] = {
            str(x).strip() for x in (settled_order_ids or ()) if str(x).strip()
        }
        fb_p = round(max(0.0, safe_float(fallback_price, 0.0)), 4)

        closed_list = await self.get_closed_orders(symbol=symbol, limit=30)
        if not closed_list:
            return fb_p, []

        acc_qty = 0
        acc_val = 0.0
        matched_ids: List[str] = []

        for ord_item in closed_list:
            if not isinstance(ord_item, dict):
                continue
            oid = str(ord_item.get("orderId") or "").strip()
            if not oid or oid in settled_set:
                continue
            o_side = str(ord_item.get("side") or "").upper().strip()
            if o_side != target_side:
                continue

            # Case 19 & API.txt OrderStatus: 정정/취소 거부로 생성된 별도 레코드 및 정정 대체된 원주문(REPLACED) 배제
            ord_status = str(ord_item.get("status") or "").upper().strip()
            if ord_status and ord_status not in (
                "FILLED",
                "PARTIAL_FILLED",
                "CANCELED",
            ):
                continue

            # Case 19: 오직 실제 체결 데이터(execution.filledQuantity & averageFilledPrice)만 인정!
            exec_obj = (
                ord_item.get("execution")
                if isinstance(ord_item.get("execution"), dict)
                else {}
            )
            f_qty = safe_int(exec_obj.get("filledQuantity"), 0)
            f_avg = safe_float(exec_obj.get("averageFilledPrice"), 0.0)
            if f_qty <= 0 or f_avg <= 0.0:
                continue

            take_q = min(need_q - acc_qty, f_qty)
            if take_q <= 0:
                break
            acc_qty += take_q
            acc_val += float(take_q) * f_avg
            matched_ids.append(oid)
            if acc_qty >= need_q:
                break

        if acc_qty > 0 and acc_val > 0.0:
            return round(acc_val / float(acc_qty), 4), matched_ids
        return fb_p, []

    async def find_latest_open_order_id(
        self, symbol: str = TARGET_SYMBOL, side: Optional[str] = None
    ) -> str:
        orders = await self.get_open_orders(symbol=symbol)
        target_side = str(side or "").upper().strip()
        for o in orders:
            o_side = str(o.get("side") or "").upper().strip()
            if not target_side or o_side == target_side:
                oid = str(o.get("orderId") or "").strip()
                if oid:
                    return oid
        return ""

    async def cancel_all_open_orders(
        self, symbol: str = TARGET_SYMBOL
    ) -> int:
        orders = await self.get_open_orders(symbol=symbol)
        canceled = 0
        for o in orders:
            oid = str(o.get("orderId") or "").strip()
            if oid:
                try:
                    await self.cancel_order(oid)
                    canceled += 1
                except Exception:
                    pass
        return canceled

    async def close(self) -> None:
        return None


# 하위 호환 별칭
TossInvestApiClient = TossApiClient
