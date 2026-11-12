# -*- coding: utf-8 -*-
"""
# MODIFIED: toss_api.py (Part 1/2 — 바벨 모드 상수/3단 순환 심볼 재익스포트 &
# Case 09 SOXS 등 제3종목 물리적 차단 유지 하에 바벨 정규장[09:30~16:00 EST] SGOV 지정가 주문 허용 확장 &
# Case 93 get_candles_1m 최대 400분봉[2페이지] 상한 하드 락온 유지)
인피니트 스노우볼 (Infinite Snowball) v3.0 — 토스증권 Open API (v1.2.14) 방탄 통신 통제소
- 역할:
  1) toss_api_core.py 의 모든 상수(바벨 모드 상수 · Case 88 서브 그리드 상수 · Case 91 3단 순환 상수 포함) · 유틸리티 · 폴더격리 · 디스크치유 ·
     GlobalThrottle · SoxlStratumLedger 심볼을 명시적으로 재익스포트(Facade Re-export)하여 타 모듈 AST 심볼 임포트 무결성 100% 보장
  2) 제1헌법 ~ 제6헌법 및 API.txt (v1.2.14) 100% 준수 TossApiClient 구현:
     - OAuth2 토큰 자동 발급 및 만료 전 선제 갱신 (POST /oauth2/token)
     - 종합매매 계좌(BROKERAGE) accountSeq 자동 락온 및 X-Tossinvest-Account 헤더 원자적 주입 (GET /api/v1/accounts)
     - 계좌별 미국 주식(US) 실제 매매 수수료율 조회·락온 및 일시 통신 실패 시 원장/런타임 수수료율 보존 폴백 (GET /api/v1/commissions · Case 86)
     - REAL_ALLOWED_SYMBOLS = ("SOXL",) 단일 롱 화이트리스트 강제 및 바벨 모드 전용 정규장 SGOV 지정가 주문(allow_barbell_sgov=True) 제한 허용 (Case 09)
     - 1분봉 윗꼬리(Upper-Wick) 슈팅 포착용 최근 5.0초 내 유효 체결 최고가 추출기 (get_recent_wick_high_price · Case 82)
     - 날짜변경선(00:00 EST) 야간 꼬리 침범을 원천 차단하는 최대 400분봉(2페이지 × 200봉) 1분봉 수집기 (get_candles_1m · Case 93) 및 일봉 수집기 (get_candles_1d)
     - 토스 CLOSED 주문 원장 역추적기 (probe_latest_manual_fill_price : 실측 수수료 commission + tax 추출 포함)
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import math
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore

from toss_api_core import (
    ALLOWED_SYMBOLS,
    AssassinLedger,
    BARBELL_ALLOWED_SYMBOLS,
    BARBELL_CASH_WEIGHT,
    BARBELL_SAFE_SYMBOL,
    BARBELL_SGOV_WEIGHT,
    BARBELL_SOXL_WEIGHT,
    BASE_MAX_LOTS_8PCT,
    DEFAULT_GRID_MERGE_MODE,
    DEFAULT_INITIAL_SEED_USD,
    DEFAULT_SUB_MERGE_MODE,
    DEFAULT_UNLOCK_MODE,
    DEFAULT_US_COMMISSION_RATE,
    EST_TZ,
    GlobalThrottle,
    KRW_PER_USD_DEFAULT,
    KST_TZ,
    LOCKED_BUY_INTERVAL_MIN,
    LOCKED_SELL_INTERVAL_MIN,
    MAX_GRID_TIERS,
    MAX_GRID_TIERS_12,
    MAX_GRID_TIERS_7,
    MAX_RESERVE_PORTIONS,
    MIN_DIP_BUDGET_RATIO,
    MIN_DIP_VS_L1_RATIO,
    NEW_CYCLE_BUY_CUTOFF_HM,
    PORTION_MODE_BARBELL,
    PORTION_MODE_COMPOUND,
    PORTION_MODE_SIMPLE,
    PORTION_RATIO_LOCKED,
    REAL_ALLOWED_SYMBOLS,
    REANCHOR_NET_BUFFER_MULT,
    RESERVE_DEPOSIT_TOLERANCE_RATIO,
    ROUND_TRIP_FEE_RATE,
    ROUND_TRIP_FEE_RATE_PCT,
    STEP_UP_2X_DROP_PCT,
    STEP_UP_2X_MAX_TIERS,
    STEP_UP_2X_MIN_CASH_RATIO,
    STEP_UP_2X_MIN_REBOUND_MULT,
    SUB_FROZEN_DAYS_TRIGGER,
    SUB_GRID_DEFAULT_ENABLED,
    SUB_MAX_TIERS,
    SUB_MAX_TIERS_3,
    SUB_MAX_TOTAL_LOTS,
    SUB_MAX_TOTAL_LOTS_4,
    SUB_MERGE_MODE_L1_L3,
    SUB_PORTION_RATIO_4PCT,
    SUB_RESERVE_MAIN_PORTIONS,
    SUB_UNLOCK_DROP_FROM_L1_PCT,
    SUB_UNLOCK_FROZEN_DAYS_10,
    SoxlStratumLedger,
    StratumLedger,
    TARGET_SYMBOL,
    TOSS_OPENAPI_BASE_URL,
    VALID_PORTION_MODES,
    _HybridFileLock,
    _NonRetryableApiError,
    _load_env_files_into_environ,
    _read_env_us_commission_rates,
    emergency_free_disk_space_sync,
    generate_client_order_id,
    get_bot_base_dir,
    get_folder_slug,
    get_runtime_round_trip_fee_rate_pct,
    get_runtime_us_commission_rate,
    is_barbell_mode,
    is_simple_income_mode,
    next_cycled_portion_mode,
    resolve_folder_isolated_ledger_paths,
    safe_float,
    safe_int,
    set_runtime_round_trip_fee_rate_pct,
)

logger = logging.getLogger("toss_sniper.toss_api")

# NEW: /dev/shm 프로세스 간 무계좌 시세·정찰 공유 버스 코어
_SHM_BUS_DIR: str = os.environ.get(
    "TOSS_SHM_BUS_DIR",
    "/dev/shm/toss_sniper_bus_v3",
)
PRICE_SHM_TTL_SEC: float = 1.15
CANDLE_1M_SHM_TTL_SEC: float = 4.20
CANDLE_1D_SHM_TTL_SEC: float = 30.0


def _resolve_shm_bus_dir_sync(
    bus_dir: Optional[str] = None,
) -> str:
    cand = str(bus_dir or _SHM_BUS_DIR).strip()
    if cand.startswith("/dev/shm/") and not (
        os.path.isdir("/dev/shm")
    ):
        cand = "/tmp/toss_sniper_bus_v3"
    if not os.path.isdir(cand):
        old_u = os.umask(0)
        try:
            os.makedirs(
                cand, mode=0o777, exist_ok=True
            )
            os.chmod(cand, 0o777)
        except Exception:
            pass
        finally:
            os.umask(old_u)
    return cand


def _open_shm_lock_fd_sync(lock_fp: str) -> int:
    try:
        return os.open(lock_fp, os.O_RDWR)
    except FileNotFoundError:
        tmp_lk = (
            f"{lock_fp}.{os.getpid()}."
            f"{threading.get_ident()}"
        )
        old_u = os.umask(0)
        try:
            fd_t = os.open(
                tmp_lk,
                os.O_CREAT | os.O_EXCL | os.O_RDWR,
                0o666,
            )
            try:
                os.fchmod(fd_t, 0o666)
            except Exception:
                pass
            os.close(fd_t)
            os.replace(tmp_lk, lock_fp)
        except Exception:
            try:
                if os.path.exists(tmp_lk):
                    os.remove(tmp_lk)
            except Exception:
                pass
        finally:
            os.umask(old_u)
        return os.open(lock_fp, os.O_RDWR)


PRICE_SHM_SNAPSHOT_TTL_SEC: float = 0.25


def _unlock_shm_fd_now(fd: int) -> None:
    if fd < 0:
        return
    try:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
    except Exception:
        pass
    try:
        os.close(fd)
    except Exception:
        pass


def _shm_read_json_sync(
    fp: str,
) -> Dict[str, Any]:
    if not fp or not os.path.isfile(fp):
        return {}
    try:
        with open(fp, "r", encoding="utf-8") as rf:
            data = json.load(rf)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _shm_write_json_sync(
    fp: str, data: Dict[str, Any]
) -> None:
    tmp_fp = (
        f"{fp}.tmp.{os.getpid()}."
        f"{threading.get_ident()}"
    )
    old_u = os.umask(0)
    try:
        with open(tmp_fp, "w", encoding="utf-8") as wf:
            json.dump(data, wf, ensure_ascii=False)
            wf.flush()
        try:
            os.chmod(tmp_fp, 0o666)
        except Exception:
            pass
        os.replace(tmp_fp, fp)
    except Exception:
        try:
            if os.path.exists(tmp_fp):
                os.remove(tmp_fp)
        except Exception:
            pass
    finally:
        os.umask(old_u)


def _shm_try_begin_prices_sync(
    sym_list: List[str],
    ttl_sec: float,
    bypass_cache: bool,
) -> Tuple[str, Dict[str, float], int]:
    try:
        bdir = _resolve_shm_bus_dir_sync()
        data_fp = os.path.join(bdir, "prices_v3.json")
        now_t = time.time()
        if not bypass_cache:
            cached = _shm_read_json_sync(data_fp)
            hit: Dict[str, float] = {}
            all_ok = True
            for s in sym_list:
                ent = cached.get(s)
                if not isinstance(ent, dict):
                    all_ok = False
                    break
                p_v = safe_float(ent.get("p"), 0.0)
                ts_v = safe_float(ent.get("ts"), 0.0)
                if p_v <= 0.0 or (now_t - ts_v) > ttl_sec:
                    all_ok = False
                    break
                hit[s] = p_v
            if all_ok and hit:
                return "HIT", hit, -1
        if bypass_cache or fcntl is None:
            return "SOLO", {}, -1
        lock_fp = os.path.join(bdir, "prices_v3.lock")
        fd = _open_shm_lock_fd_sync(lock_fp)
        try:
            fcntl.flock(
                fd, fcntl.LOCK_EX | fcntl.LOCK_NB
            )
            return "LEADER", {}, fd
        except (BlockingIOError, OSError):
            _unlock_shm_fd_now(fd)
            return "FOLLOWER", {}, -1
    except Exception:
        return "SOLO", {}, -1


def _shm_poll_follower_prices_sync(
    sym_list: List[str], min_ts: float
) -> Optional[Dict[str, float]]:
    try:
        bdir = _resolve_shm_bus_dir_sync()
        data_fp = os.path.join(bdir, "prices_v3.json")
        cached = _shm_read_json_sync(data_fp)
        hit: Dict[str, float] = {}
        for s in sym_list:
            ent = cached.get(s)
            if not isinstance(ent, dict):
                return None
            p_v = safe_float(ent.get("p"), 0.0)
            ts_v = safe_float(ent.get("ts"), 0.0)
            if p_v <= 0.0 or ts_v < min_ts:
                return None
            hit[s] = p_v
        return hit if hit else None
    except Exception:
        return None


def _shm_commit_prices_and_unlock_sync(
    fd: int, fetched: Dict[str, float]
) -> None:
    try:
        valid = {
            k: v
            for k, v in (fetched or {}).items()
            if v > 0.0
        }
        if valid:
            bdir = _resolve_shm_bus_dir_sync()
            data_fp = os.path.join(bdir, "prices_v3.json")
            cur = _shm_read_json_sync(data_fp)
            now_t = time.time()
            for k, v in valid.items():
                cur[k] = {
                    "p": round(float(v), 4),
                    "ts": now_t,
                }
            _shm_write_json_sync(data_fp, cur)
    except Exception:
        pass
    finally:
        _unlock_shm_fd_now(fd)



# ---------------------------------------------------------------------------
# [핵심] 토스증권 Open API v1.2.14 방탄 클라이언트 (TossApiClient)
# ---------------------------------------------------------------------------
class TossApiClient:
    """
    🏛️ 제1헌법 ~ 제6헌법 & API.txt (v1.2.14) 100% 완벽 구현:
    - OAuth2 토큰 자동 발급 및 만료 전 선제 갱신 (`POST /oauth2/token`)
    - 종합매매 계좌(`BROKERAGE`) `accountSeq` 자동 락온 및 `X-Tossinvest-Account` 헤더 원자적 주입 (`GET /api/v1/accounts`)
    - 계좌별 미국 주식(`US`) 매매 수수료율 조회 및 왕복 수수료율 자동 락온 (`GET /api/v1/commissions` · `Case 86`)
    - `REAL_ALLOWED_SYMBOLS = ("SOXL",)` 외 제3종목(SOXS 등) 주문 물리적 차단 및 바벨 모드 정규장 `SGOV` 제한 허용 (`Case 09`)
    """

    REAL_ALLOWED_SYMBOLS: Tuple[str, ...] = ("SOXL",)
    BARBELL_ALLOWED_SYMBOLS: Tuple[str, ...] = ("SOXL", "SGOV")
    _candles_1m_v3_patched: bool = True
    _candles_1d_v3_patched: bool = True

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

        self.us_commission_rate: float = get_runtime_us_commission_rate()
        self.round_trip_fee_rate_pct: float = (
            get_runtime_round_trip_fee_rate_pct()
        )
        self._commission_locked: bool = False
        self._commission_lock: asyncio.Lock = asyncio.Lock()
        self.last_probed_manual_fee_usd: float = 0.0

        self._fx_cache_rate: float = KRW_PER_USD_DEFAULT
        self._fx_cache_mono: float = 0.0

    def _assert_real_order_symbol(
        self, symbol: str, allow_barbell_sgov: bool = False
    ) -> str:
        sym = str(symbol or "").upper().strip()
        if allow_barbell_sgov and sym == BARBELL_SAFE_SYMBOL:
            return sym
        if sym not in self.REAL_ALLOWED_SYMBOLS:
            raise ValueError(
                f"🚨 [Case 09 물리적 주문 차단] 허용되지 않은 종목 주문 시도: {sym} (오직 SOXL 및 바벨 정규장 SGOV 만 허용)"
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
                await asyncio.to_thread(
                    _load_env_files_into_environ, self.base_dir
                )
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

            logger.warning(
                "⚠️ [AccountSeq 조회 폴백] 계좌 응답이 비어 있어 고정 락온 없이 1 임시 반환(차기 재탐색)"
            )
            return 1

    async def get_commissions(self) -> List[Dict[str, Any]]:
        try:
            res = await self._request(
                method="GET",
                path="/api/v1/commissions",
                require_account=True,
                rate_group="ORDER_INFO",
            )
            items = res.get("result") if isinstance(res, dict) else []
            if isinstance(items, list):
                return [c for c in items if isinstance(c, dict)]
        except Exception as exc:
            logger.debug("get_commissions 조회 폴백 사용: %s", exc)
        return []

    async def ensure_us_commission_rate(
        self, force_refresh: bool = False
    ) -> Tuple[float, float]:
        if not force_refresh and self._commission_locked:
            return self.us_commission_rate, self.round_trip_fee_rate_pct

        async with self._commission_lock:
            if not force_refresh and self._commission_locked:
                return self.us_commission_rate, self.round_trip_fee_rate_pct

            items = await self.get_commissions()
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
                found_us_rate = fallback_us_rate

            if found_us_rate > 0.0:
                rt_pct = round(found_us_rate * 200.0, 4)
                self.us_commission_rate = found_us_rate
                self.round_trip_fee_rate_pct = rt_pct
                self._commission_locked = True
                set_runtime_round_trip_fee_rate_pct(
                    rt_pct, us_commission_rate=found_us_rate
                )
                return self.us_commission_rate, self.round_trip_fee_rate_pct

            rt_fallback = get_runtime_round_trip_fee_rate_pct()
            one_fallback = get_runtime_us_commission_rate()
            if 0.0 < one_fallback <= 0.01 and 0.0 < rt_fallback <= 2.0:
                self.us_commission_rate = one_fallback
                self.round_trip_fee_rate_pct = rt_fallback
            return self.us_commission_rate, self.round_trip_fee_rate_pct

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
        force_token_refresh: bool = False
        for attempt in range(max_retries + 1):
            try:
                token = await self._ensure_access_token(
                    force_refresh=force_token_refresh
                )
                force_token_refresh = False
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
                    force_token_refresh = True
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
    # [Market Data 그룹] 현재가 · 호가 · 최근체결 · 윗꼬리 체결최고가 · 1분봉/일봉 차트
    # -----------------------------------------------------------------------
    async def _fetch_prices_batch_raw(
        self, symbols: Iterable[str] = (TARGET_SYMBOL,)
    ) -> Dict[str, float]:
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

    async def get_current_prices_batch(
        self,
        symbols: Iterable[str] = (TARGET_SYMBOL,),
        bypass_shm_cache: bool = False,
    ) -> Dict[str, float]:
        sym_list = list(
            dict.fromkeys(
                str(s).upper().strip()
                for s in symbols
                if str(s).strip()
            )
        ) or [TARGET_SYMBOL]
        role, hit_m, lfd = await asyncio.to_thread(
            _shm_try_begin_prices_sync,
            sym_list,
            PRICE_SHM_TTL_SEC,
            bool(bypass_shm_cache),
        )
        if role == "HIT":
            return hit_m
        if role == "FOLLOWER":
            min_t = time.time() - PRICE_SHM_TTL_SEC
            for _ in range(15):
                await asyncio.sleep(0.02)
                polled = await asyncio.to_thread(
                    _shm_poll_follower_prices_sync,
                    sym_list,
                    min_t,
                )
                if polled is not None:
                    return polled
        out: Dict[str, float] = {
            s: 0.0 for s in sym_list
        }
        try:
            out = await self._fetch_prices_batch_raw(
                sym_list
            )
            return out
        finally:
            try:
                await asyncio.to_thread(
                    _shm_commit_prices_and_unlock_sync,
                    lfd,
                    out,
                )
            except BaseException:
                _unlock_shm_fd_now(lfd)

    async def get_current_price(
        self,
        symbol: str = TARGET_SYMBOL,
        bypass_shm_cache: bool = False,
    ) -> float:
        p_map = await self.get_current_prices_batch(
            (symbol,),
            bypass_shm_cache=bypass_shm_cache,
        )
        sym_k = str(symbol).upper().strip()
        return safe_float(p_map.get(sym_k), 0.0)

    async def get_recent_trades(
        self, symbol: str = TARGET_SYMBOL, count: int = 50
    ) -> List[Dict[str, Any]]:
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

        fb_params: Dict[str, Any] = {
            "symbol": sym_clean,
            "interval": intv_clean,
            "count": min(200, q_cnt),
        }
        if before:
            fb_params["before"] = str(before).strip()
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

    @staticmethod
    def _has_today_0407_open_bar_in_candles(
        candles: List[Dict[str, Any]],
        today_est_str: str,
    ) -> bool:
        """
        # [Case 93 : 400봉(2페이지) 수집 시 당일 04:07 EST 시초봉 도달 또는 자정(00:00 EST) 경계 감지 조기 종료 판별기]
        """
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
                dt_obj = datetime.fromisoformat(
                    ts_raw.replace("Z", "+00:00")
                ).astimezone(EST_TZ)
                d_str = dt_obj.strftime("%Y-%m-%d")
                hm = dt_obj.hour * 100 + dt_obj.minute
                if d_str < today_est_str:
                    return True
                if d_str == today_est_str and 400 <= hm <= 415:
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def _shm_begin_candles_sync(
        ckey: str, req_cnt: int, ttl_s: float
    ) -> Tuple[str, List[Dict[str, Any]], int]:
        try:
            bdir = _resolve_shm_bus_dir_sync()
            dfp = os.path.join(
                bdir, f"candles_{ckey}.json"
            )
            now_t = time.time()
            cur = _shm_read_json_sync(dfp)
            ts_v = safe_float(cur.get("ts"), 0.0)
            c_req = safe_int(cur.get("req_cnt"), 0)
            items = cur.get("items")
            if (
                (now_t - ts_v) <= ttl_s
                and c_req >= req_cnt
                and isinstance(items, list)
                and items
            ):
                sliced = [
                    dict(x)
                    for x in items[-req_cnt:]
                    if isinstance(x, dict)
                ]
                if sliced:
                    return "HIT", sliced, -1
            if fcntl is None:
                return "SOLO", [], -1
            lfp = os.path.join(
                bdir, f"candles_{ckey}.lock"
            )
            fd = _open_shm_lock_fd_sync(lfp)
            try:
                fcntl.flock(
                    fd, fcntl.LOCK_EX | fcntl.LOCK_NB
                )
                return "LEADER", [], fd
            except (BlockingIOError, OSError):
                _unlock_shm_fd_now(fd)
                return "FOLLOWER", [], -1
        except Exception:
            return "SOLO", [], -1

    @staticmethod
    def _shm_poll_candles_sync(
        ckey: str, req_cnt: int, min_ts: float
    ) -> Optional[List[Dict[str, Any]]]:
        try:
            bdir = _resolve_shm_bus_dir_sync()
            dfp = os.path.join(
                bdir, f"candles_{ckey}.json"
            )
            cur = _shm_read_json_sync(dfp)
            ts_v = safe_float(cur.get("ts"), 0.0)
            c_req = safe_int(cur.get("req_cnt"), 0)
            items = cur.get("items")
            if (
                ts_v >= min_ts
                and c_req >= req_cnt
                and isinstance(items, list)
                and items
            ):
                return [
                    dict(x)
                    for x in items[-req_cnt:]
                    if isinstance(x, dict)
                ]
        except Exception:
            pass
        return None

    @staticmethod
    def _shm_end_candles_sync(
        fd: int,
        ckey: str,
        req_cnt: int,
        items: List[Dict[str, Any]],
    ) -> None:
        try:
            if items:
                bdir = _resolve_shm_bus_dir_sync()
                dfp = os.path.join(
                    bdir, f"candles_{ckey}.json"
                )
                _shm_write_json_sync(
                    dfp,
                    {
                        "ts": time.time(),
                        "req_cnt": int(req_cnt),
                        "items": items,
                    },
                )
        except Exception:
            pass
        finally:
            _unlock_shm_fd_now(fd)

    async def get_candles_1m(
        self,
        symbol: str = TARGET_SYMBOL,
        total_count: int = 400,
        count: Optional[int] = None,
        before: Optional[str] = None,
        adjusted: bool = True,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        sym_c = str(symbol or TARGET_SYMBOL).upper().strip()
        rc = max(safe_int(total_count, 0), safe_int(count, 0))
        t_cnt = max(1, min(400, rc if rc > 0 else 400))
        if before or not adjusted or kwargs.get(
            "bypass_shm_cache"
        ):
            return await self._fetch_candles_1m_raw(
                symbol=sym_c,
                total_count=t_cnt,
                count=count,
                before=before,
                adjusted=adjusted,
            )
        ckey = f"1m_{sym_c}"
        role, hit_c, lfd = await asyncio.to_thread(
            self._shm_begin_candles_sync,
            ckey,
            t_cnt,
            CANDLE_1M_SHM_TTL_SEC,
        )
        if role == "HIT":
            return hit_c
        if role == "FOLLOWER":
            min_t = time.time() - CANDLE_1M_SHM_TTL_SEC
            for _ in range(16):
                await asyncio.sleep(0.025)
                polled = await asyncio.to_thread(
                    self._shm_poll_candles_sync,
                    ckey,
                    t_cnt,
                    min_t,
                )
                if polled is not None:
                    return polled
        fetched: List[Dict[str, Any]] = []
        try:
            fetched = await self._fetch_candles_1m_raw(
                symbol=sym_c,
                total_count=t_cnt,
                count=count,
                before=None,
                adjusted=adjusted,
            )
            return fetched
        finally:
            try:
                await asyncio.to_thread(
                    self._shm_end_candles_sync,
                    lfd,
                    ckey,
                    t_cnt,
                    fetched,
                )
            except BaseException:
                _unlock_shm_fd_now(lfd)

    async def _fetch_candles_1m_raw(
        self,
        symbol: str = TARGET_SYMBOL,
        total_count: int = 400,
        count: Optional[int] = None,
        before: Optional[str] = None,
        adjusted: bool = True,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """
        # [Case 93 : count / total_count 양방향 호환 및 최대 400분봉(2페이지 × 200봉) 상한 하드 락온]
        """
        sym_clean = str(symbol or TARGET_SYMBOL).upper().strip()
        now_est = datetime.now(EST_TZ)
        today_est_str = now_est.strftime("%Y-%m-%d")

        req_cnt = max(safe_int(total_count, 0), safe_int(count, 0))
        if req_cnt <= 0:
            req_cnt = 400

        target_cnt = max(1, min(400, req_cnt))
        collected: List[Dict[str, Any]] = []
        seen_ts: Set[str] = set()
        before_cursor: Optional[str] = (
            str(before).strip() if before else None
        )
        max_pages = max(1, min(2, int(math.ceil(target_cnt / 200.0))))

        for page_idx in range(max_pages):
            rem = max(1, min(200, target_cnt - len(collected)))
            page_req_cnt = (
                200
                if (page_idx == 0 and target_cnt >= 150)
                else max(100, rem)
            )
            try:
                batch, next_b = await self.get_candles(
                    symbol=sym_clean,
                    interval="1m",
                    count=page_req_cnt,
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
                sym_clean == TARGET_SYMBOL
                and len(collected) >= min(200, target_cnt)
                and self._has_today_0407_open_bar_in_candles(
                    collected, today_est_str
                )
            ):
                break

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
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        sym_c = str(symbol or TARGET_SYMBOL).upper().strip()
        t_cnt = max(2, min(200, safe_int(count, 10)))
        ckey = f"1d_{sym_c}"
        role, hit_d, lfd = await asyncio.to_thread(
            self._shm_begin_candles_sync,
            ckey,
            t_cnt,
            CANDLE_1D_SHM_TTL_SEC,
        )
        if role == "HIT":
            return hit_d
        try:
            batch, _ = await self.get_candles(
                symbol=sym_c,
                interval="1d",
                count=t_cnt,
                adjusted=adjusted,
            )
            batch.sort(
                key=lambda x: str(
                    x.get("timestamp")
                    or x.get("date")
                    or x.get("dt")
                    or ""
                )
            )
            await asyncio.to_thread(
                self._shm_end_candles_sync,
                lfd,
                ckey,
                t_cnt,
                batch,
            )
            lfd = -1
            return batch
        except Exception as exc:
            logger.debug("get_candles_1d 조회 예외: %s", exc)
            return []
        finally:
            _unlock_shm_fd_now(lfd)

    # -----------------------------------------------------------------------
    # [Market Info 그룹] USD/KRW 환율 및 미국 장 캘린더 (API.txt v1.2.14)
    # -----------------------------------------------------------------------
    async def get_usd_krw_rate(self) -> float:
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
        out_map: Dict[str, Dict[str, Any]] = {
            TARGET_SYMBOL: self._empty_holding_dict(TARGET_SYMBOL),
            BARBELL_SAFE_SYMBOL: self._empty_holding_dict(BARBELL_SAFE_SYMBOL),
        }
        params: Dict[str, Any] = {}
        if symbol:
            sym_req = str(symbol).upper().strip()
            params["symbol"] = sym_req
            out_map.setdefault(sym_req, self._empty_holding_dict(sym_req))

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
        self,
        symbol: str = TARGET_SYMBOL,
        allow_barbell_sgov: bool = False,
    ) -> int:
        sym_clean = str(symbol or TARGET_SYMBOL).upper().strip()
        sym = self._assert_real_order_symbol(
            sym_clean,
            allow_barbell_sgov=(
                allow_barbell_sgov or sym_clean == BARBELL_SAFE_SYMBOL
            ),
        )
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
        allow_barbell_sgov: bool = False,
    ) -> Dict[str, Any]:
        """
        🎯 5 & 제5헌법 & Case 01, 09, 18, 79 + 바벨 모드 SGOV 정규장 전용 가드:
        POST /api/v1/orders
        - SOXL 지정가 주문 허용
        - allow_barbell_sgov=True 일 때 SGOV 지정가 주문을 허용하되,
          SGOV는 매수/매도 모두 반드시 평일 미국 정규장(09:30 ~ 16:00 EST)에서만 발주 허용!
        """
        sym = self._assert_real_order_symbol(
            symbol, allow_barbell_sgov=allow_barbell_sgov
        )
        clean_side = str(side or "BUY").upper().strip()
        if clean_side not in ("BUY", "SELL"):
            raise ValueError(f"유효하지 않은 주문 방향: {clean_side}")

        now_est = datetime.now(EST_TZ)
        hm = now_est.hour * 100 + now_est.minute

        if sym == BARBELL_SAFE_SYMBOL:
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
        )
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

    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        time_in_force: str = "DAY",
        client_order_id: Optional[str] = None,
        enforce_daymarket_block: bool = False,
        allow_barbell_sgov: bool = False,
    ) -> Dict[str, Any]:
        return await self.create_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            order_type="LIMIT",
            time_in_force=time_in_force,
            client_order_id=client_order_id,
            enforce_daymarket_block=enforce_daymarket_block,
            allow_barbell_sgov=allow_barbell_sgov,
        )

    async def modify_order(
        self,
        order_id: str,
        new_price: float,
        order_type: str = "LIMIT",
        **kwargs: Any,
    ) -> Dict[str, Any]:
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
            logger.debug(
                "종료 주문 목록 조회(/api/v1/orders?status=CLOSED) 예외: %s", exc
            )
        return []

    async def probe_latest_manual_fill_price(
        self,
        side: str,
        target_qty: int,
        settled_order_ids: Iterable[str] = (),
        fallback_price: float = 0.0,
        symbol: str = TARGET_SYMBOL,
    ) -> Tuple[float, List[str]]:
        target_side = str(side or "SELL").upper().strip()
        need_q = max(1, safe_int(target_qty, 1))
        settled_set: Set[str] = {
            str(x).strip() for x in (settled_order_ids or ()) if str(x).strip()
        }
        fb_p = round(max(0.0, safe_float(fallback_price, 0.0)), 4)
        self.last_probed_manual_fee_usd = 0.0

        closed_list = await self.get_closed_orders(symbol=symbol, limit=30)
        if not closed_list:
            return fb_p, []

        acc_qty = 0
        acc_val = 0.0
        acc_fee = 0.0
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

            ord_status = str(ord_item.get("status") or "").upper().strip()
            if ord_status and ord_status not in (
                "FILLED",
                "PARTIAL_FILLED",
                "CANCELED",
                "REPLACED",
                "REJECTED",
            ):
                continue

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

            f_comm = max(0.0, safe_float(exec_obj.get("commission"), 0.0))
            f_tax = max(0.0, safe_float(exec_obj.get("tax"), 0.0))
            if (f_comm + f_tax) > 0.0:
                ratio_q = float(take_q) / float(max(1, f_qty))
                acc_fee += (f_comm + f_tax) * ratio_q

            matched_ids.append(oid)
            if acc_qty >= need_q:
                break

        if acc_qty > 0 and acc_val > 0.0:
            self.last_probed_manual_fee_usd = round(acc_fee, 4)
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
