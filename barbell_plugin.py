# -*- coding: utf-8 -*-
"""
# NEW: barbell_plugin.py (Part 1/2 — 바벨 모드 [SOXL 60% / SGOV 30% / 현금 10%] 독립 플러그인 ·
# 전용 3중 원장 BarbellLedger · SOXL 보유 중 모드 전환 분류기 · 실현수익 별도 금고 영구 격리 ·
# 0주 졸업 시 수익금고 대여금 1순위 상환 및 60/30/10 자동 리밸런싱 코어)
인피니트 스노우볼 (Infinite Snowball) v3.0 — 바벨 모드(BARBELL_60_30_10) 전담 플러그인 모듈
- 역할:
  1) 설정 기준 시드(initial_seed_usd, 예: $10,000)를 SOXL 60%($6,000) / SGOV 30%($3,000) / 현금 10%($1,000)로 배분 관리
  2) SOXL 스나이퍼 매도 시 발생하는 모든 세후 실현수익금(net_pnl_usd > 0)을 별도 장부(vault_realized_profit_usd)로
     즉시 영구 격리하여 일반 매매 및 60/30/10 리밸런싱 재원에 섞이지 않도록 원천 차단
  3) SOXL GUARD30 시드고갈 시 자동수혈 우선순위 집행:
     - 1순위: 현금 10% 버킷에서 SOXL 1회분(8% = 코어60%의 8%) 단위로 즉시 자동수혈 (약 2회분)
     - 2순위: 현금 10% 버킷이 1회분 미만으로 소진되면 정규장(09:31 ~ 15:55 EST)에서 SGOV를
              현금 10% 상당액만큼 정수 수량(소수점 내림 floor) 지정가 매도하여 현금 버킷 충전 (기본 3회 + 잔여 단주 스윕)
     - 3순위: 내부 예비자본 40%(현금 10% + SGOV 30%) 전액 소진 시 별도 장부 실현수익금고(vault_available_usd)에서
              1회분(8%) 단위로 자동수혈
     - 4순위: 계좌 내 미할당 추가 달러 현금(broker_bp_usd) 존재 시 1회분(8%) 자동수혈 (100% SOXL 보유 전환 시 즉시 대응)
  4) 지층 매도(부분 익절 · 전량 졸업 · 수동 매도) 발생 시 0주 사이클 종료를 기다리지 않고 즉시 초과 수혈원금을 환수하여
     [수익금고 대여금 원복 ➔ 현금 10% 우선 완충 ➔ SOXL > 60% 구간 포함 10% 초과분 즉시 SGOV(최대 30%) 매수 배정] 실시간 리밸런싱 수행
"""

from __future__ import annotations

import asyncio
import copy
import errno
import html
import json
import logging
import math
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from quant_engine import (
    MIN_DIP_BUDGET_RATIO,
    MIN_DIP_VS_L1_RATIO,
    buckets_from_dicts,
    calc_sell_realized_pnl,
    has_active_l1_bucket,
    resolve_effective_round_trip_fee_rate_pct,
)
from quant_indicators_plugin import is_weekend_nyse_closed
from toss_api import (
    DEFAULT_INITIAL_SEED_USD,
    EST_TZ,
    GlobalThrottle,
    KRW_PER_USD_DEFAULT,
    ROUND_TRIP_FEE_RATE_PCT,
    TARGET_SYMBOL,
    _NonRetryableApiError,
    emergency_free_disk_space_sync,
    generate_client_order_id,
    get_bot_base_dir,
    get_folder_slug,
    safe_float,
    safe_int,
)

logger = logging.getLogger("toss_sniper.barbell_plugin")

# ---------------------------------------------------------------------------
# [핵심 상수] 바벨 모드(60 / 30 / 10) 비중 · SGOV 정규장 전용 시간창 및 대기 상수
# ---------------------------------------------------------------------------
PORTION_MODE_BARBELL: str = "BARBELL_60_30_10"
BARBELL_SAFE_SYMBOL: str = "SGOV"

BARBELL_SOXL_WEIGHT: float = 0.60
BARBELL_SGOV_WEIGHT: float = 0.30
BARBELL_CASH_WEIGHT: float = 0.10

BARBELL_SOXL_PORTION_RATIO: float = 0.08
BARBELL_SUB_PORTION_RATIO: float = 0.04

# SGOV 정규장 전용 매매 시간창 (시초/마감 동시호가 스프레드 회피를 위해 평일 09:31 ~ 15:55 EST 운용)
SGOV_REG_START_HM: int = 931
SGOV_REG_END_HM: int = 1555
SGOV_ORDER_MAX_WAIT_SEC: float = 60.0
SGOV_ACTION_COOLDOWN_SEC: float = 15.0
SGOV_DEFAULT_REF_PRICE: float = 100.30


def is_barbell_mode(portion_mode: Any) -> bool:
    """현재 운용 모드가 ⚖️ 바벨 모드(BARBELL_60_30_10)인지 판별한다."""
    return str(portion_mode or "").upper().strip() in (
        "BARBELL_60_30_10",
        "BARBELL",
    )


def is_sgov_regular_trading_window(
    hm: Optional[int] = None,
    now_est: Optional[datetime] = None,
) -> bool:
    """
    SGOV 매매 허용 시간창 판별기:
    오직 평일 미국 정규장(09:31 ~ 15:55 EST) 구간에서만 True 를 반환한다.
    """
    dt = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    if is_weekend_nyse_closed(dt) or dt.weekday() >= 5:
        return False
    hm_val = (
        safe_int(hm, dt.hour * 100 + dt.minute)
        if hm is not None
        else (dt.hour * 100 + dt.minute)
    )
    return SGOV_REG_START_HM <= hm_val <= SGOV_REG_END_HM


def compute_barbell_seed_splits(
    initial_seed_usd: float = DEFAULT_INITIAL_SEED_USD,
) -> Dict[str, float]:
    """
    설정 기준 시드(initial_seed_usd)에 대한 60 / 30 / 10 목표 배분액과
    SOXL 코어(60%) 기준 본 그리드 1회분(8%) / 서브 그리드 1회분(4%) 정액 예산을 반환한다.
    """
    tot_seed = round(
        max(100.0, safe_float(initial_seed_usd, DEFAULT_INITIAL_SEED_USD)), 4
    )
    soxl_60 = round(tot_seed * BARBELL_SOXL_WEIGHT, 4)
    sgov_30 = round(tot_seed * BARBELL_SGOV_WEIGHT, 4)
    cash_10 = round(max(0.0, tot_seed - soxl_60 - sgov_30), 4)
    portion_8 = round(soxl_60 * BARBELL_SOXL_PORTION_RATIO, 4)
    sub_portion_4 = round(soxl_60 * BARBELL_SUB_PORTION_RATIO, 4)
    return {
        "total_seed_usd": tot_seed,
        "soxl_seed_60_usd": soxl_60,
        "sgov_seed_30_usd": sgov_30,
        "cash_seed_10_usd": cash_10,
        "soxl_portion_8pct_usd": portion_8,
        "soxl_sub_portion_4pct_usd": sub_portion_4,
    }


def resolve_barbell_ledger_paths(
    base_dir: Optional[str] = None,
) -> Tuple[str, str, str, str]:
    """
    스나이퍼 및 암살자 원장과 물리적으로 완전히 분리된
    바벨 모드 전용 3중 안전 원장 경로(primary, mirror, backup, folder_slug)를 반환한다.
    """
    target_dir = get_bot_base_dir(base_dir)
    slug = get_folder_slug(target_dir)
    backup_dir = os.path.join(target_dir, "ledger_backups")
    os.makedirs(backup_dir, exist_ok=True)

    primary_fp = os.path.join(target_dir, f"barbell_ledger_{slug}.json")
    mirror_fp = os.path.join(target_dir, "barbell_ledger.json")
    backup_fp = os.path.join(backup_dir, f"barbell_ledger_{slug}.bak.json")
    return primary_fp, mirror_fp, backup_fp, slug


# ---------------------------------------------------------------------------
# [핵심 1] 바벨 모드 전용 3중 원장 (BarbellLedger — 별도 실현수익금고 및 SGOV/현금버킷 영속화)
# ---------------------------------------------------------------------------
class BarbellLedger:
    """
    Dirty-Check 및 GlobalThrottle 원자적 쓰기를 준수하는 바벨 모드 전용 3중 원장 클래스:
    - 현금 10% 버킷(cash_bucket_usd)
    - SGOV 30% 안전 버킷(sgov_held_qty, sgov_invested_usd, pending_sgov_buy_budget_usd, pending_sgov_tranche_sells)
    - 별도 실현수익금고(vault_realized_profit_usd, vault_available_usd, vault_injected_to_soxl_usd)
    """

    def __init__(
        self,
        base_dir: Optional[str] = None,
        initial_seed_usd: float = DEFAULT_INITIAL_SEED_USD,
    ) -> None:
        self.base_dir: str = get_bot_base_dir(base_dir)
        (
            self.primary_filepath,
            self.mirror_filepath,
            self.backup_filepath,
            self.folder_slug,
        ) = resolve_barbell_ledger_paths(self.base_dir)
        self._lock = threading.RLock()
        self._async_lock = asyncio.Lock()
        self._last_serialized_payload: str = ""
        self._data: Dict[str, Any] = {}
        self._load_or_init_sync(initial_seed_usd=initial_seed_usd)

    def _default_state(
        self, seed_usd: float = DEFAULT_INITIAL_SEED_USD
    ) -> Dict[str, Any]:
        splits = compute_barbell_seed_splits(seed_usd)
        now_est = datetime.now(EST_TZ)
        today_str = now_est.strftime("%Y-%m-%d")
        return {
            "symbol": BARBELL_SAFE_SYMBOL,
            "folder_slug": self.folder_slug,
            "initial_seed_usd": splits["total_seed_usd"],
            "is_initialized": False,
            "logical_date": today_str,
            # 현금 10% 대기 버킷 상태
            "cash_bucket_usd": splits["cash_seed_10_usd"],
            "cash_injected_to_soxl_usd": 0.0,
            "cash_injection_count_cycle": 0,
            "cum_cash_injection_count": 0,
            # SGOV 30% 안전 버킷 상태 (정규장 전용 매매)
            "sgov_held_qty": 0,
            "sgov_avg_price": 0.0,
            "sgov_invested_usd": 0.0,
            "sgov_last_price": SGOV_DEFAULT_REF_PRICE,
            "pending_sgov_buy_budget_usd": splits["sgov_seed_30_usd"],
            "pending_sgov_tranche_sells": 0,
            "sgov_tranche_sells_done_cycle": 0,
            "cum_sgov_buy_events": 0,
            "cum_sgov_sell_events": 0,
            "sgov_buy_order_id": "",
            "sgov_sell_order_id": "",
            "sgov_client_order_id": "",
            "sgov_ordered_qty": 0,
            "sgov_order_price": 0.0,
            "sgov_order_purpose": "",
            "sgov_order_mono": 0.0,
            "last_sgov_action_mono": 0.0,
            "last_settled_sgov_order_ids": [],
            # 별도 실현수익금고 (절대 일반 매매/리밸런싱 미사용 · 40% 전액 소진 시에만 8% 수혈 후 0주 졸업 시 1순위 원복)
            "vault_realized_profit_usd": 0.0,
            "vault_available_usd": 0.0,
            "vault_injected_to_soxl_usd": 0.0,
            "vault_injection_count_cycle": 0,
            "cum_vault_injection_count": 0,
            "daily_vaulted_profit_usd": 0.0,
            "cycle_vaulted_profit_usd": 0.0,
            "last_cycle_vaulted_profit_usd": 0.0,
            "completed_barbell_cycles": 0,
            # 계좌 내 추가현금 수혈 추적 및 시드고갈 진단 플래그
            "external_injected_to_soxl_usd": 0.0,
            "barbell_seed_exhausted": False,
            "sgov_wait_alert_sent": False,
            "updated_at": now_est.isoformat(),
        }

    def _sanitize_state(
        self, raw_st: Dict[str, Any], default_seed: float
    ) -> Dict[str, Any]:
        base = self._default_state(default_seed)
        if isinstance(raw_st, dict):
            base.update(raw_st)

        init_s = safe_float(base.get("initial_seed_usd"), default_seed)
        if init_s < 100.0:
            init_s = max(100.0, default_seed)
        base["initial_seed_usd"] = round(init_s, 4)

        base["cash_bucket_usd"] = round(
            max(0.0, safe_float(base.get("cash_bucket_usd"), 0.0)), 4
        )
        base["cash_injected_to_soxl_usd"] = round(
            max(0.0, safe_float(base.get("cash_injected_to_soxl_usd"), 0.0)), 4
        )
        base["cash_injection_count_cycle"] = max(
            0, safe_int(base.get("cash_injection_count_cycle"), 0)
        )
        base["cum_cash_injection_count"] = max(
            0, safe_int(base.get("cum_cash_injection_count"), 0)
        )

        sgov_q = max(0, safe_int(base.get("sgov_held_qty"), 0))
        base["sgov_held_qty"] = sgov_q
        if sgov_q <= 0:
            base["sgov_avg_price"] = 0.0
            base["sgov_invested_usd"] = 0.0
            base["pending_sgov_tranche_sells"] = 0
        else:
            sgov_inv = max(
                0.01 * float(sgov_q),
                safe_float(
                    base.get("sgov_invested_usd"),
                    float(sgov_q)
                    * max(1.0, safe_float(base.get("sgov_avg_price"), 100.0)),
                ),
            )
            base["sgov_invested_usd"] = round(sgov_inv, 4)
            base["sgov_avg_price"] = round(sgov_inv / float(sgov_q), 4)
            base["pending_sgov_tranche_sells"] = max(
                0, safe_int(base.get("pending_sgov_tranche_sells"), 0)
            )

        sgov_lp = safe_float(
            base.get("sgov_last_price"), SGOV_DEFAULT_REF_PRICE
        )
        base["sgov_last_price"] = round(
            sgov_lp if sgov_lp > 1.0 else SGOV_DEFAULT_REF_PRICE, 4
        )
        base["pending_sgov_buy_budget_usd"] = round(
            max(0.0, safe_float(base.get("pending_sgov_buy_budget_usd"), 0.0)),
            4,
        )
        base["sgov_tranche_sells_done_cycle"] = max(
            0, safe_int(base.get("sgov_tranche_sells_done_cycle"), 0)
        )

        raw_oids = base.get("last_settled_sgov_order_ids")
        if isinstance(raw_oids, list):
            clean_oids: List[str] = []
            for x in raw_oids:
                sx = str(x or "").strip()
                if sx and sx not in clean_oids:
                    clean_oids.append(sx)
            base["last_settled_sgov_order_ids"] = clean_oids[-50:]
        else:
            base["last_settled_sgov_order_ids"] = []

        # 별도 실현수익금고 무결성 강제: vault_available + vault_injected == vault_realized_profit
        v_tot = round(
            max(0.0, safe_float(base.get("vault_realized_profit_usd"), 0.0)), 4
        )
        v_inj = round(
            min(
                v_tot,
                max(
                    0.0,
                    safe_float(base.get("vault_injected_to_soxl_usd"), 0.0),
                ),
            ),
            4,
        )
        base["vault_realized_profit_usd"] = v_tot
        base["vault_injected_to_soxl_usd"] = v_inj
        base["vault_available_usd"] = round(max(0.0, v_tot - v_inj), 4)

        base["vault_injection_count_cycle"] = max(
            0, safe_int(base.get("vault_injection_count_cycle"), 0)
        )
        base["cum_vault_injection_count"] = max(
            0, safe_int(base.get("cum_vault_injection_count"), 0)
        )
        base["daily_vaulted_profit_usd"] = round(
            max(0.0, safe_float(base.get("daily_vaulted_profit_usd"), 0.0)), 4
        )
        base["cycle_vaulted_profit_usd"] = round(
            max(0.0, safe_float(base.get("cycle_vaulted_profit_usd"), 0.0)), 4
        )
        base["last_cycle_vaulted_profit_usd"] = round(
            max(
                0.0,
                safe_float(base.get("last_cycle_vaulted_profit_usd"), 0.0),
            ),
            4,
        )
        base["completed_barbell_cycles"] = max(
            0, safe_int(base.get("completed_barbell_cycles"), 0)
        )
        base["external_injected_to_soxl_usd"] = round(
            max(
                0.0,
                safe_float(base.get("external_injected_to_soxl_usd"), 0.0),
            ),
            4,
        )
        base["barbell_seed_exhausted"] = bool(
            base.get("barbell_seed_exhausted", False)
        )
        base["sgov_wait_alert_sent"] = bool(
            base.get("sgov_wait_alert_sent", False)
        )
        return base

    def _load_or_init_sync(
        self, initial_seed_usd: float = DEFAULT_INITIAL_SEED_USD
    ) -> None:
        with self._lock:
            loaded_st: Optional[Dict[str, Any]] = None
            for fp in (
                self.primary_filepath,
                self.mirror_filepath,
                self.backup_filepath,
            ):
                if not os.path.isfile(fp):
                    continue
                try:
                    with GlobalThrottle.get_file_lock(fp):
                        with open(fp, "r", encoding="utf-8") as rf:
                            raw = json.load(rf)
                    if isinstance(raw, dict):
                        cand = (
                            raw.get("BARBELL")
                            if isinstance(raw.get("BARBELL"), dict)
                            else raw
                        )
                        if isinstance(cand, dict):
                            loaded_st = cand
                            break
                except Exception:
                    continue

            clean_st = self._sanitize_state(
                loaded_st or {}, default_seed=initial_seed_usd
            )
            self._data = {"BARBELL": clean_st}
            self._save_sync_unlocked(force=(loaded_st is None))

    def _comparable_payload_str(self) -> str:
        st_copy = copy.deepcopy(self._data.get("BARBELL", {}))
        st_copy.pop("updated_at", None)
        return json.dumps(st_copy, ensure_ascii=False, sort_keys=True)

    def _atomic_write_single_file_sync(
        self, filepath: str, serialized_json: str
    ) -> None:
        parent_d = os.path.dirname(os.path.abspath(filepath))
        with GlobalThrottle.get_file_lock(filepath):
            if os.path.isfile(filepath):
                try:
                    with open(filepath, "r", encoding="utf-8") as rf:
                        if rf.read() == serialized_json:
                            return
                except Exception:
                    pass

            for attempt in range(2):
                if parent_d and not os.path.isdir(parent_d):
                    os.makedirs(parent_d, exist_ok=True)
                tmp_fp = (
                    f"{filepath}.tmp.{os.getpid()}.{threading.get_ident()}"
                )
                try:
                    with open(tmp_fp, "w", encoding="utf-8") as wf:
                        wf.write(serialized_json)
                        wf.flush()
                        os.fsync(wf.fileno())
                    os.replace(tmp_fp, filepath)
                    break
                except OSError as os_err:
                    try:
                        if os.path.exists(tmp_fp):
                            os.remove(tmp_fp)
                    except Exception:
                        pass
                    if os_err.errno == errno.ENOSPC and attempt == 0:
                        emergency_free_disk_space_sync(
                            base_dir=self.base_dir,
                            keep_backup_days=3,
                            remove_pycache=True,
                        )
                        continue
                    break
                except Exception:
                    try:
                        if os.path.exists(tmp_fp):
                            os.remove(tmp_fp)
                    except Exception:
                        pass
                    break

    def _save_sync_unlocked(self, force: bool = False) -> None:
        comp_str = self._comparable_payload_str()
        if not force and comp_str == self._last_serialized_payload:
            return
        self._last_serialized_payload = comp_str
        self._data["BARBELL"]["updated_at"] = datetime.now(EST_TZ).isoformat()
        full_json = json.dumps(self._data, ensure_ascii=False, indent=2)
        for fp in (
            self.primary_filepath,
            self.mirror_filepath,
            self.backup_filepath,
        ):
            self._atomic_write_single_file_sync(fp, full_json)

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data.get("BARBELL", {}))

    def update_state_sync(self, **kwargs: Any) -> Dict[str, Any]:
        with self._lock:
            st = self._data.setdefault("BARBELL", self._default_state())
            for k, v in kwargs.items():
                st[k] = v
            self._data["BARBELL"] = self._sanitize_state(
                st,
                default_seed=safe_float(
                    st.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD
                ),
            )
            self._save_sync_unlocked(force=False)
            return copy.deepcopy(self._data["BARBELL"])

    async def update_state(self, **kwargs: Any) -> Dict[str, Any]:
        async with self._async_lock:
            return await asyncio.to_thread(self.update_state_sync, **kwargs)

    async def rollover_daily_if_needed(
        self, logical_date: str
    ) -> Dict[str, Any]:
        st = self.get_state()
        if str(st.get("logical_date") or "") == str(logical_date):
            return st
        return await self.update_state(
            logical_date=str(logical_date),
            daily_vaulted_profit_usd=0.0,
        )

    async def reset_vault_profit_only(self) -> Dict[str, Any]:
        """
        /reset_profit 실행 시 보유 중인 SGOV 및 SOXL 수혈 상태는 보존하고
        격리된 누적 수익금고 통계만 0점으로 초기화한다.
        """
        return await self.update_state(
            vault_realized_profit_usd=0.0,
            vault_available_usd=0.0,
            vault_injected_to_soxl_usd=0.0,
            vault_injection_count_cycle=0,
            cum_vault_injection_count=0,
            daily_vaulted_profit_usd=0.0,
            cycle_vaulted_profit_usd=0.0,
            last_cycle_vaulted_profit_usd=0.0,
            completed_barbell_cycles=0,
        )


def ensure_barbell_ledger(context: Any) -> BarbellLedger:
    """SniperAppContext 에 barbell_ledger 인스턴스가 없으면 생성 장착 후 반환한다."""
    existing = getattr(context, "barbell_ledger", None)
    if isinstance(existing, BarbellLedger):
        return existing

    base_dir = get_bot_base_dir(getattr(context, "base_dir", None))
    seed_usd = DEFAULT_INITIAL_SEED_USD
    if context is not None and hasattr(context, "ledger"):
        try:
            st_sp = context.ledger.get_state(TARGET_SYMBOL)
            seed_usd = safe_float(
                st_sp.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD
            )
        except Exception:
            pass

    b_ledger = BarbellLedger(base_dir=base_dir, initial_seed_usd=seed_usd)
    if context is not None:
        try:
            setattr(context, "barbell_ledger", b_ledger)
        except Exception:
            pass
    return b_ledger


# ---------------------------------------------------------------------------
# [핵심 2] 바벨 모드 진입/전환 분류기 · 실현수익 별도 금고 격리기 · 0주 졸업 60/30/10 리밸런싱 엔진
# ---------------------------------------------------------------------------
def classify_barbell_transition_allocation(
    initial_seed_usd: float,
    soxl_invested_usd: float,
    existing_sgov_qty: int = 0,
    existing_sgov_invested_usd: float = 0.0,
    sgov_ref_price: float = SGOV_DEFAULT_REF_PRICE,
) -> Dict[str, Any]:
    """
    SOXL 보유 중(또는 0주 상태에서) 바벨 모드로 전환/시드변경 시 자산 분류 공식:
    - 케이스 1 (soxl_invested <= 60%):
      SOXL에 60% 배정(수혈 $0) · 현금 10% 배정 · 나머지 30%(기존 SGOV 차감분) 정규장 SGOV 매수 예약
    - 케이스 2 (60% < soxl_invested < 100%):
      60% 초과분을 SOXL 기수혈분(injected_reserve_usd)으로 인식 ·
      잔여 시드에서 현금 10% 우선 확보 후 남는 금액만 SGOV 매수 예약
    - 케이스 3 (soxl_invested >= 100%):
      전체 시드가 SOXL에 투입된 바벨 시드고갈 상황으로 즉시 인식(현금버킷 $0 · SGOV 매수 $0) ·
      추매 타점 도래 시 수익금고 또는 계좌 추가현금으로 1회분(8%) 자동수혈 대기
    """
    splits = compute_barbell_seed_splits(initial_seed_usd)
    tot_seed = splits["total_seed_usd"]
    soxl_60 = splits["soxl_seed_60_usd"]
    sgov_30 = splits["sgov_seed_30_usd"]
    cash_10 = splits["cash_seed_10_usd"]
    portion_8 = splits["soxl_portion_8pct_usd"]

    inv_soxl = round(max(0.0, safe_float(soxl_invested_usd, 0.0)), 4)
    sgov_q = max(0, safe_int(existing_sgov_qty, 0))
    sgov_inv = (
        round(max(0.0, safe_float(existing_sgov_invested_usd, 0.0)), 4)
        if sgov_q > 0
        else 0.0
    )
    ref_sgov_p = max(1.0, safe_float(sgov_ref_price, SGOV_DEFAULT_REF_PRICE))

    if inv_soxl <= soxl_60 + 1e-6:
        soxl_inj = 0.0
        used_p_cnt = 0
        raw_sgov_shortfall = round(max(0.0, sgov_30 - sgov_inv), 4)
        if raw_sgov_shortfall >= (ref_sgov_p * 1.002):
            pending_sgov_buy = raw_sgov_shortfall
            cash_bucket = cash_10
        else:
            pending_sgov_buy = 0.0
            cash_bucket = round(cash_10 + raw_sgov_shortfall, 4)
        exhausted = False
    elif inv_soxl < tot_seed - 1e-6:
        soxl_inj = round(inv_soxl - soxl_60, 4)
        used_p_cnt = max(
            1, int(math.ceil((soxl_inj - 1e-9) / max(1.0, portion_8)))
        )
        rem_seed = round(max(0.0, tot_seed - inv_soxl - sgov_inv), 4)
        cash_bucket = round(min(cash_10, rem_seed), 4)
        rem_for_sgov = round(max(0.0, rem_seed - cash_bucket), 4)
        if rem_for_sgov >= (ref_sgov_p * 1.002):
            pending_sgov_buy = rem_for_sgov
        else:
            pending_sgov_buy = 0.0
            cash_bucket = round(cash_bucket + rem_for_sgov, 4)
        exhausted = bool(cash_bucket < portion_8 and sgov_q <= 0)
    else:
        soxl_inj = round(inv_soxl - soxl_60, 4)
        used_p_cnt = max(
            1, int(math.ceil((soxl_inj - 1e-9) / max(1.0, portion_8)))
        )
        cash_bucket = 0.0
        pending_sgov_buy = 0.0
        exhausted = bool(sgov_q <= 0)

    pending_sells = (
        1 if (cash_bucket < portion_8 and sgov_q > 0) else 0
    )
    return {
        "total_seed_usd": tot_seed,
        "soxl_seed_60_usd": soxl_60,
        "soxl_portion_8pct_usd": portion_8,
        "soxl_injected_reserve_usd": soxl_inj,
        "soxl_used_portions_cnt": used_p_cnt,
        "cash_bucket_usd": cash_bucket,
        "sgov_held_qty": sgov_q,
        "sgov_invested_usd": sgov_inv,
        "pending_sgov_buy_budget_usd": pending_sgov_buy,
        "pending_sgov_tranche_sells": pending_sells,
        "barbell_seed_exhausted": exhausted,
    }


async def initialize_or_sync_barbell_on_mode_enter(
    context: Any,
    new_seed_usd: Optional[float] = None,
    holdings_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    운용 모드가 BARBELL_60_30_10 으로 전환되거나 기준 시드가 변경되었을 때 호출되어
    현재 보유 SOXL 및 SGOV 원금을 기준으로 바벨 원장과 스나이퍼 원장을 원자적으로 동기화한다.
    """
    b_ledger = ensure_barbell_ledger(context)
    st_soxl = context.ledger.get_state(TARGET_SYMBOL)
    bst = b_ledger.get_state()

    eff_seed = (
        round(max(100.0, safe_float(new_seed_usd, 10000.0)), 4)
        if new_seed_usd is not None
        else round(
            max(
                100.0,
                safe_float(
                    st_soxl.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD
                ),
            ),
            4,
        )
    )

    buckets = buckets_from_dicts(st_soxl.get("buckets", []))
    sub_buckets = buckets_from_dicts(st_soxl.get("sub_buckets", []))
    inv_soxl = round(
        sum(b.actual_cost_usd for b in buckets)
        + sum(sb.actual_cost_usd for sb in sub_buckets),
        4,
    )

    h_map = holdings_map
    if not isinstance(h_map, dict) and hasattr(context, "api"):
        try:
            fetched_map, ok = await context.api.get_holdings_map_with_status(
                symbol=BARBELL_SAFE_SYMBOL
            )
            if ok and isinstance(fetched_map, dict):
                h_map = fetched_map
        except Exception:
            h_map = None

    sgov_q = safe_int(bst.get("sgov_held_qty"), 0)
    sgov_inv = safe_float(bst.get("sgov_invested_usd"), 0.0)
    sgov_lp = safe_float(bst.get("sgov_last_price"), SGOV_DEFAULT_REF_PRICE)

    if isinstance(h_map, dict) and isinstance(
        h_map.get(BARBELL_SAFE_SYMBOL), dict
    ):
        sg_h = h_map[BARBELL_SAFE_SYMBOL]
        sgov_q = max(0, safe_int(sg_h.get("qty"), sgov_q))
        if sgov_q > 0:
            sgov_avg = safe_float(sg_h.get("avg_price"), 0.0)
            sgov_pur = safe_float(
                sg_h.get("purchase_amount"), float(sgov_q) * sgov_avg
            )
            if sgov_pur > 0.0:
                sgov_inv = round(sgov_pur, 4)
            sg_last = safe_float(sg_h.get("last_price"), 0.0)
            if sg_last > 1.0:
                sgov_lp = sg_last
        else:
            sgov_inv = 0.0

    alloc = classify_barbell_transition_allocation(
        initial_seed_usd=eff_seed,
        soxl_invested_usd=inv_soxl,
        existing_sgov_qty=sgov_q,
        existing_sgov_invested_usd=sgov_inv,
        sgov_ref_price=sgov_lp,
    )

    v_inj = safe_float(bst.get("vault_injected_to_soxl_usd"), 0.0)
    ext_inj = safe_float(bst.get("external_injected_to_soxl_usd"), 0.0)
    cash_inj = max(
        0.0,
        round(alloc["soxl_injected_reserve_usd"] - v_inj - ext_inj, 4),
    )

    updated_bst = await b_ledger.update_state(
        initial_seed_usd=eff_seed,
        is_initialized=True,
        cash_bucket_usd=alloc["cash_bucket_usd"],
        cash_injected_to_soxl_usd=cash_inj,
        sgov_held_qty=alloc["sgov_held_qty"],
        sgov_invested_usd=alloc["sgov_invested_usd"],
        sgov_avg_price=(
            round(
                alloc["sgov_invested_usd"] / float(alloc["sgov_held_qty"]), 4
            )
            if alloc["sgov_held_qty"] > 0
            else 0.0
        ),
        sgov_last_price=sgov_lp,
        pending_sgov_buy_budget_usd=alloc["pending_sgov_buy_budget_usd"],
        pending_sgov_tranche_sells=alloc["pending_sgov_tranche_sells"],
        barbell_seed_exhausted=alloc["barbell_seed_exhausted"],
        sgov_wait_alert_sent=False,
    )

    await context.ledger.update_state(
        TARGET_SYMBOL,
        initial_seed_usd=eff_seed,
        portion_mode=PORTION_MODE_BARBELL,
        injected_reserve_usd=alloc["soxl_injected_reserve_usd"],
        used_reserve_portions_cnt=alloc["soxl_used_portions_cnt"],
        waiting_reserve_deposit=False,
        waiting_reserve_deposit_alert_sent=False,
        required_reserve_deposit_usd=0.0,
        last_reserve_check_ts=0.0,
    )
    return updated_bst


def compute_realtime_barbell_stratum_rebalance(
    initial_seed_usd: float,
    rem_soxl_invested_usd: float,
    prev_soxl_injected_usd: float,
    prev_soxl_used_portions_cnt: int = 0,
    prev_vault_injected_usd: float = 0.0,
    prev_external_injected_usd: float = 0.0,
    prev_cash_bucket_usd: float = 0.0,
    prev_pending_sgov_buy_usd: float = 0.0,
    sgov_held_qty: int = 0,
    sgov_invested_usd: float = 0.0,
    sgov_ref_price: float = SGOV_DEFAULT_REF_PRICE,
    cycle_realized_net_usd: float = 0.0,
    topup_reserve_usd: float = 0.0,
    is_graduated_zero: bool = False,
) -> Dict[str, Any]:
    """
    # NEW: 전 구간 실시간 지층 리밸런싱 순수 연산기
    SOXL 지층 매도(부분 익절 · 전량 졸업 · 수동 매도) 직후 잔여 SOXL 원금(rem_soxl_invested_usd)을 대조하여
    초과 수혈원금을 즉시 환수하고 다음 우선순위로 실시간 배분한다:
    - [0-A순위] 별도 수익금고 긴급 대여금(vault_injected_to_soxl_usd) 최우선 원복
    - [0-B순위] 계좌 내 미할당 추가현금 수혈분(external_injected_to_soxl_usd) 차감 복원
    - [1순위]   바벨 대기 현금 버킷(cash_bucket_usd)을 시드 10% 까지 우선 완충
    - [2순위]   SOXL > 60% 구간이라도 현금 10% 가 완충되면 초과분 전액을 즉시 SGOV(최대 30% 한도) 매수예약으로 배정
                (단, SGOV 1주 매수비용 미만 단주 자투리는 현금 버킷에 유보)
    """
    splits = compute_barbell_seed_splits(initial_seed_usd)
    soxl_60 = splits["soxl_seed_60_usd"]
    sgov_30 = splits["sgov_seed_30_usd"]
    cash_10 = splits["cash_seed_10_usd"]
    portion_8 = max(1.0, splits["soxl_portion_8pct_usd"])

    prev_inj = round(max(0.0, safe_float(prev_soxl_injected_usd, 0.0)), 4)
    cyc_loss_adj = min(0.0, safe_float(cycle_realized_net_usd, 0.0))

    if is_graduated_zero:
        inv_soxl = 0.0
        topup_resv = 0.0
        next_soxl_inj = 0.0
        next_used_cnt = 0
        repaid_from_soxl_usd = prev_inj
        rem_repay = round(max(0.0, prev_inj + cyc_loss_adj), 4)
        loss_spill_to_barbell = round(min(0.0, prev_inj + cyc_loss_adj), 4)
    else:
        inv_soxl = round(max(0.0, safe_float(rem_soxl_invested_usd, 0.0)), 4)
        topup_resv = round(max(0.0, safe_float(topup_reserve_usd, 0.0)), 4)
        eff_soxl_core = max(0.0, soxl_60 + cyc_loss_adj)
        req_soxl_inj = round(
            max(0.0, (inv_soxl + topup_resv) - eff_soxl_core), 4
        )
        next_soxl_inj = round(min(prev_inj, req_soxl_inj), 4)
        if next_soxl_inj <= 0.01:
            next_soxl_inj = 0.0
            next_used_cnt = 0
        else:
            est_cnt = max(
                1, int(math.ceil((next_soxl_inj - 1e-9) / portion_8))
            )
            prev_cnt = max(0, safe_int(prev_soxl_used_portions_cnt, 0))
            next_used_cnt = min(prev_cnt, est_cnt) if prev_cnt > 0 else est_cnt
        repaid_from_soxl_usd = round(max(0.0, prev_inj - next_soxl_inj), 4)
        rem_repay = repaid_from_soxl_usd
        loss_spill_to_barbell = 0.0

    v_inj_prev = round(max(0.0, safe_float(prev_vault_injected_usd, 0.0)), 4)
    ext_inj_prev = round(
        max(0.0, safe_float(prev_external_injected_usd, 0.0)), 4
    )

    # [0-A순위] 별도 수익금고 대여금 최우선 원복
    repaid_to_vault_usd = round(min(rem_repay, v_inj_prev), 4)
    rem_repay = round(max(0.0, rem_repay - repaid_to_vault_usd), 4)
    next_v_inj = (
        0.0
        if is_graduated_zero
        else round(max(0.0, v_inj_prev - repaid_to_vault_usd), 4)
    )

    # [0-B순위] 계좌 추가현금 수혈분 차감 복원
    repaid_to_ext_usd = round(min(rem_repay, ext_inj_prev), 4)
    rem_repay = round(max(0.0, rem_repay - repaid_to_ext_usd), 4)
    next_ext_inj = (
        0.0
        if is_graduated_zero
        else round(max(0.0, ext_inj_prev - repaid_to_ext_usd), 4)
    )

    next_cash_inj = (
        0.0
        if is_graduated_zero
        else round(max(0.0, next_soxl_inj - next_v_inj - next_ext_inj), 4)
    )

    sgov_q = max(0, safe_int(sgov_held_qty, 0))
    sgov_inv = (
        round(max(0.0, safe_float(sgov_invested_usd, 0.0)), 4)
        if sgov_q > 0
        else 0.0
    )
    ref_sgov_p = max(1.0, safe_float(sgov_ref_price, SGOV_DEFAULT_REF_PRICE))
    min_one_sgov_cost = ref_sgov_p * 1.002

    max_barbell_liquid_40 = round(max(0.0, (cash_10 + sgov_30) - sgov_inv), 4)
    prev_cash_b = max(0.0, safe_float(prev_cash_bucket_usd, 0.0))
    prev_pend_b = max(0.0, safe_float(prev_pending_sgov_buy_usd, 0.0))
    raw_liquid = round(
        max(0.0, prev_cash_b + prev_pend_b + rem_repay + loss_spill_to_barbell),
        4,
    )
    liquid_pool = round(min(raw_liquid, max_barbell_liquid_40), 4)

    # [1순위] 현금 10% 우선 완충 ➔ [2순위] SOXL > 60% 여부 무관 10% 초과분 즉시 SGOV(30% 한도) 배정
    base_cash = round(min(cash_10, liquid_pool), 4)
    excess_over_cash10 = round(max(0.0, liquid_pool - base_cash), 4)
    sgov_room = round(max(0.0, sgov_30 - sgov_inv), 4)
    cand_sgov_buy = round(min(excess_over_cash10, sgov_room), 4)

    if cand_sgov_buy >= min_one_sgov_cost:
        next_pending_sgov_buy = cand_sgov_buy
        next_cash_bucket = round(
            base_cash + max(0.0, excess_over_cash10 - cand_sgov_buy), 4
        )
    else:
        next_pending_sgov_buy = 0.0
        next_cash_bucket = liquid_pool

    added_sgov_buy_usd = round(
        max(0.0, next_pending_sgov_buy - prev_pend_b), 4
    )
    did_rebalance = bool(
        is_graduated_zero
        or repaid_from_soxl_usd > 0.0
        or abs(next_pending_sgov_buy - prev_pend_b) > 0.01
        or abs(next_cash_bucket - prev_cash_b) > 0.01
    )

    return {
        "total_seed_usd": splits["total_seed_usd"],
        "soxl_seed_60_usd": soxl_60,
        "sgov_seed_30_usd": sgov_30,
        "cash_seed_10_usd": cash_10,
        "soxl_portion_8pct_usd": portion_8,
        "rem_soxl_injected_usd": next_soxl_inj,
        "rem_soxl_used_portions_cnt": next_used_cnt,
        "repaid_from_soxl_usd": repaid_from_soxl_usd,
        "repaid_to_vault_usd": repaid_to_vault_usd,
        "repaid_to_ext_usd": repaid_to_ext_usd,
        "next_vault_injected_usd": next_v_inj,
        "next_external_injected_usd": next_ext_inj,
        "next_cash_injected_usd": next_cash_inj,
        "cash_bucket_usd": next_cash_bucket,
        "pending_sgov_buy_budget_usd": next_pending_sgov_buy,
        "added_sgov_buy_budget_usd": added_sgov_buy_usd,
        "did_rebalance_60_30_10": did_rebalance,
    }


async def record_barbell_realized_profit(
    context: Any,
    net_pnl_usd: float,
    is_graduated_zero: bool = False,
    prev_soxl_injected_usd: Optional[float] = None,
    prev_soxl_used_portions_cnt: Optional[int] = None,
    cycle_realized_net_override: Optional[float] = None,
) -> Dict[str, Any]:
    """
    # MODIFIED: 사이클(0주) 대기 폐기 -> 매 지층 매도 시 실시간 바벨 리밸런싱 통합 정산기
    1) 세후 실현수익금(net_pnl_usd > 0)을 별도 수익금고(vault_realized_profit_usd)로 즉시 영구 격리한다.
    2) 부분 익절이든 전량 졸업이든 잔여 SOXL 지층 원금(inv_soxl)을 즉시 대조하여 초과 수혈원금을 환수하고,
       수익금고 원복 ➔ 현금 10% 우선 완충 ➔ 10% 초과분 즉시 SGOV(30% 한도) 매수예약으로 실시간 리밸런싱한다.
    """
    b_ledger = ensure_barbell_ledger(context)
    bst = b_ledger.get_state()
    st_soxl = context.ledger.get_state(TARGET_SYMBOL)
    pnl = round(safe_float(net_pnl_usd, 0.0), 4)

    new_v_tot = safe_float(bst.get("vault_realized_profit_usd"), 0.0)
    new_day_v = safe_float(bst.get("daily_vaulted_profit_usd"), 0.0)
    new_cyc_v = safe_float(bst.get("cycle_vaulted_profit_usd"), 0.0)

    if pnl > 0.0:
        new_v_tot = round(new_v_tot + pnl, 4)
        new_day_v = round(new_day_v + pnl, 4)
        new_cyc_v = round(new_cyc_v + pnl, 4)

    init_seed = safe_float(
        st_soxl.get("initial_seed_usd"),
        safe_float(bst.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD),
    )
    rem_buckets = buckets_from_dicts(st_soxl.get("buckets", []))
    rem_sub_buckets = buckets_from_dicts(st_soxl.get("sub_buckets", []))
    rem_inv_soxl = round(
        sum(b.actual_cost_usd for b in rem_buckets)
        + sum(sb.actual_cost_usd for sb in rem_sub_buckets),
        4,
    )

    # 활성 1층 부분체결 미체결 잔량(TOPUP_1FL / SUB_TOPUP_1FL) 보충용 예약금 보호 (Case 78 호환)
    eff_rt_pct = resolve_effective_round_trip_fee_rate_pct(state_dict=st_soxl)
    fee_mult_top = 1.0 + (eff_rt_pct / 100.0)
    topup_resv_usd = 0.0
    if not is_graduated_zero:
        l1_target_q = safe_int(st_soxl.get("l1_target_quota_qty"), 0)
        if (
            rem_buckets
            and has_active_l1_bucket(rem_buckets)
            and l1_target_q > rem_buckets[0].qty
        ):
            topup_resv_usd += (
                float(l1_target_q - rem_buckets[0].qty)
                * rem_buckets[0].book_price
                * fee_mult_top
            )
        sub_target_q = safe_int(st_soxl.get("sub_l1_target_quota_qty"), 0)
        if (
            rem_sub_buckets
            and has_active_l1_bucket(rem_sub_buckets)
            and sub_target_q > rem_sub_buckets[0].qty
        ):
            topup_resv_usd += (
                float(sub_target_q - rem_sub_buckets[0].qty)
                * rem_sub_buckets[0].book_price
                * fee_mult_top
            )

    eff_prev_inj = (
        round(max(0.0, safe_float(prev_soxl_injected_usd, 0.0)), 4)
        if prev_soxl_injected_usd is not None
        else round(
            max(
                safe_float(st_soxl.get("injected_reserve_usd"), 0.0),
                safe_float(bst.get("cash_injected_to_soxl_usd"), 0.0)
                + safe_float(bst.get("vault_injected_to_soxl_usd"), 0.0)
                + safe_float(bst.get("external_injected_to_soxl_usd"), 0.0),
            ),
            4,
        )
    )
    eff_prev_cnt = (
        max(0, safe_int(prev_soxl_used_portions_cnt, 0))
        if prev_soxl_used_portions_cnt is not None
        else max(0, safe_int(st_soxl.get("used_reserve_portions_cnt"), 0))
    )
    eff_cyc_net = (
        safe_float(cycle_realized_net_override, 0.0)
        if cycle_realized_net_override is not None
        else safe_float(st_soxl.get("cycle_realized_net_usd"), 0.0)
    )

    sgov_q = max(0, safe_int(bst.get("sgov_held_qty"), 0))
    sgov_inv = (
        safe_float(bst.get("sgov_invested_usd"), 0.0) if sgov_q > 0 else 0.0
    )
    sgov_lp = max(
        1.0, safe_float(bst.get("sgov_last_price"), SGOV_DEFAULT_REF_PRICE)
    )

    reb = compute_realtime_barbell_stratum_rebalance(
        initial_seed_usd=init_seed,
        rem_soxl_invested_usd=rem_inv_soxl,
        prev_soxl_injected_usd=eff_prev_inj,
        prev_soxl_used_portions_cnt=eff_prev_cnt,
        prev_vault_injected_usd=safe_float(
            bst.get("vault_injected_to_soxl_usd"), 0.0
        ),
        prev_external_injected_usd=safe_float(
            bst.get("external_injected_to_soxl_usd"), 0.0
        ),
        prev_cash_bucket_usd=safe_float(bst.get("cash_bucket_usd"), 0.0),
        prev_pending_sgov_buy_usd=safe_float(
            bst.get("pending_sgov_buy_budget_usd"), 0.0
        ),
        sgov_held_qty=sgov_q,
        sgov_invested_usd=sgov_inv,
        sgov_ref_price=sgov_lp,
        cycle_realized_net_usd=eff_cyc_net,
        topup_reserve_usd=topup_resv_usd,
        is_graduated_zero=is_graduated_zero,
    )

    next_cash_bucket = reb["cash_bucket_usd"]
    next_pending_sgov_buy = reb["pending_sgov_buy_budget_usd"]
    next_v_inj = reb["next_vault_injected_usd"]
    next_ext_inj = reb["next_external_injected_usd"]
    next_cash_inj = reb["next_cash_injected_usd"]
    next_soxl_inj = reb["rem_soxl_injected_usd"]
    next_soxl_cnt = reb["rem_soxl_used_portions_cnt"]
    repaid_from_soxl = reb["repaid_from_soxl_usd"]
    repaid_vault_usd = reb["repaid_to_vault_usd"]
    portion_8 = reb["soxl_portion_8pct_usd"]

    new_v_avail = round(max(0.0, new_v_tot - next_v_inj), 4)
    guard_cash_floor = portion_8 * MIN_DIP_BUDGET_RATIO

    # 현금버킷이 30% 가드 이상 회복되거나 SGOV 매수예약이 잡히면 대기 중이던 SGOV 매도예약 즉시 자동 해제
    cur_pending_sells = max(
        0, safe_int(bst.get("pending_sgov_tranche_sells"), 0)
    )
    if (
        is_graduated_zero
        or next_cash_bucket >= guard_cash_floor
        or next_pending_sgov_buy > 0.0
    ):
        next_pending_sells = 0
        next_wait_alert = False
    else:
        next_pending_sells = cur_pending_sells
        next_wait_alert = bool(bst.get("sgov_wait_alert_sent", False))

    is_fully_unwound = bool(is_graduated_zero or next_soxl_inj <= 0.0)
    next_exhausted = (
        False
        if (
            is_fully_unwound
            or next_cash_bucket >= guard_cash_floor
            or sgov_q > 0
            or next_pending_sgov_buy > 0.0
        )
        else bool(bst.get("barbell_seed_exhausted", False))
    )

    comp_cycles = safe_int(bst.get("completed_barbell_cycles"), 0) + (
        1 if is_graduated_zero else 0
    )

    b_upd_kw: Dict[str, Any] = {
        "initial_seed_usd": reb["total_seed_usd"],
        "is_initialized": True,
        "cash_bucket_usd": next_cash_bucket,
        "cash_injected_to_soxl_usd": next_cash_inj,
        "pending_sgov_buy_budget_usd": next_pending_sgov_buy,
        "pending_sgov_tranche_sells": next_pending_sells,
        "vault_realized_profit_usd": new_v_tot,
        "vault_injected_to_soxl_usd": next_v_inj,
        "vault_available_usd": new_v_avail,
        "daily_vaulted_profit_usd": new_day_v,
        "external_injected_to_soxl_usd": next_ext_inj,
        "barbell_seed_exhausted": next_exhausted,
        "sgov_wait_alert_sent": next_wait_alert,
        "completed_barbell_cycles": comp_cycles,
    }
    if is_fully_unwound:
        b_upd_kw["cash_injection_count_cycle"] = 0
        b_upd_kw["vault_injection_count_cycle"] = 0
        b_upd_kw["sgov_tranche_sells_done_cycle"] = 0

    if is_graduated_zero:
        b_upd_kw["cycle_vaulted_profit_usd"] = 0.0
        b_upd_kw["last_cycle_vaulted_profit_usd"] = new_cyc_v
    else:
        b_upd_kw["cycle_vaulted_profit_usd"] = new_cyc_v

    await b_ledger.update_state(**b_upd_kw)

    cur_cum_repaid = max(
        0.0, safe_float(st_soxl.get("cumulative_reserve_repaid_usd"), 0.0)
    )
    new_cum_repaid = round(cur_cum_repaid + repaid_from_soxl, 4)

    if (
        abs(safe_float(st_soxl.get("injected_reserve_usd"), 0.0) - next_soxl_inj)
        > 1e-4
        or safe_int(st_soxl.get("used_reserve_portions_cnt"), 0)
        != next_soxl_cnt
        or repaid_from_soxl > 0.0
        or is_graduated_zero
    ):
        await context.ledger.update_state(
            TARGET_SYMBOL,
            injected_reserve_usd=next_soxl_inj,
            used_reserve_portions_cnt=next_soxl_cnt,
            cumulative_reserve_repaid_usd=new_cum_repaid,
            waiting_reserve_deposit=False,
            waiting_reserve_deposit_alert_sent=False,
            required_reserve_deposit_usd=0.0,
            last_reserve_check_ts=0.0,
        )

    if reb["did_rebalance_60_30_10"]:
        logger.info(
            "⚖️ [바벨 실시간 지층 리밸런싱 완료] SOXL잔여원금=$%.2f(잔여수혈 $%.2f · 환수 $%.2f) -> 현금버킷=$%.2f / SGOV매수예약=$%.2f(신규 +$%.2f) / 금고원복=$%.2f / 누적금고=$%.2f",
            rem_inv_soxl,
            next_soxl_inj,
            repaid_from_soxl,
            next_cash_bucket,
            next_pending_sgov_buy,
            reb["added_sgov_buy_budget_usd"],
            repaid_vault_usd,
            new_v_tot,
        )

    return {
        "vaulted_this_sell_usd": max(0.0, pnl),
        "vault_realized_profit_usd": new_v_tot,
        "vault_available_usd": new_v_avail,
        "did_rebalance_60_30_10": reb["did_rebalance_60_30_10"],
        "repaid_from_soxl_usd": repaid_from_soxl,
        "repaid_to_vault_usd": repaid_vault_usd,
        "rem_soxl_injected_usd": next_soxl_inj,
        "rem_soxl_used_portions_cnt": next_soxl_cnt,
        "pending_sgov_buy_budget_usd": next_pending_sgov_buy,
        "added_sgov_buy_budget_usd": reb["added_sgov_buy_budget_usd"],
        "cash_bucket_usd": next_cash_bucket,
    }
# -*- coding: utf-8 -*-
"""
# NEW: barbell_plugin.py (Part 2/2 — 4단계 우선순위 8% 정량 자동수혈 워터폴 ·
# 정규장[09:31~15:55 EST] 전용 SGOV 30% 매수 및 10% 소수점 내림[floor] 매도 실행기 ·
# /barbell 상세 관제 보드 · 레이더 결합용 슬림 블록 및 부팅 TDD 자가 검증기)
"""


def _esc(val: Any) -> str:
    return html.escape(str(val if val is not None else ""), quote=False)


def get_masked_soxl_buying_power_usd(
    context: Any,
    raw_bp_usd: float,
    st_soxl: Optional[Dict[str, Any]] = None,
    bst: Optional[Dict[str, Any]] = None,
) -> float:
    """
    바벨 모드 가동 중 평시 SOXL 매수(본 그리드 · 서브 그리드)가 토스 실계좌 주문가능금액(raw_bp_usd)을 조회할 때,
    ① 현금 10% 대기 버킷(cash_bucket_usd)
    ② 정규장 SGOV 매수 예약금(pending_sgov_buy_budget_usd)
    ③ 별도 장부 격리 수익금고 가용액(vault_available_usd)
    을 차감 마스킹하여 SOXL이 정식 자동수혈 절차 없이 타 버킷이나 수익금고를 침범하는 것을 원천 차단한다.
    """
    raw_bp = max(0.0, safe_float(raw_bp_usd, 0.0))
    soxl_state = (
        st_soxl
        if isinstance(st_soxl, dict)
        else (
            context.ledger.get_state(TARGET_SYMBOL)
            if hasattr(context, "ledger")
            else {}
        )
    )
    if not is_barbell_mode(soxl_state.get("portion_mode")):
        return round(raw_bp, 4)

    b_state = (
        bst
        if isinstance(bst, dict)
        else ensure_barbell_ledger(context).get_state()
    )
    protected_non_soxl_usd = (
        max(0.0, safe_float(b_state.get("cash_bucket_usd"), 0.0))
        + max(0.0, safe_float(b_state.get("pending_sgov_buy_budget_usd"), 0.0))
        + max(0.0, safe_float(b_state.get("vault_available_usd"), 0.0))
    )
    return round(max(0.0, raw_bp - protected_non_soxl_usd), 4)


def compute_sgov_10pct_sell_qty(
    initial_seed_usd: float,
    sgov_live_price: float,
    sgov_held_qty: int,
) -> int:
    """
    현금 10% 소진 시 정규장에서 매도할 SGOV 수량 산출 공식:
    - 현금 10%(initial_seed_usd * 0.10)에 해당하는 금액을 SGOV 현재가로 나누어 소수점 내림(math.floor) 정수 수량을 산출한다.
    - 보유 수량(sgov_held_qty)을 초과하지 않도록 캡핑하며, 시드가 작아 floor 값이 0일 때는 최소 1주를 보장한다.
    """
    held_q = max(0, safe_int(sgov_held_qty, 0))
    if held_q <= 0:
        return 0
    lp = max(1.0, safe_float(sgov_live_price, SGOV_DEFAULT_REF_PRICE))
    splits = compute_barbell_seed_splits(initial_seed_usd)
    cash_10_usd = splits["cash_seed_10_usd"]
    raw_floor_qty = int(math.floor((cash_10_usd + 1e-9) / lp))
    target_q = max(1, raw_floor_qty)
    return min(held_q, target_q)


# ---------------------------------------------------------------------------
# [핵심 3] 바벨 4단계 우선순위 자동수혈 워터폴 (현금 10% ➔ 정규장 SGOV 10% ➔ 수익금고 ➔ 추가현금)
# ---------------------------------------------------------------------------
async def evaluate_and_execute_barbell_guard30_or_injection(
    context: Any,
    st_now: Dict[str, Any],
    raw_bp_usd: float,
    exec_order_p: float,
    portion_budget: float,
    l1_actual_cost_usd: float,
    is_dip_promotion: bool,
    trigger_desc: str,
) -> Tuple[bool, float, float, Dict[str, Any]]:
    """
    SOXL 바벨 모드(60% 코어) 매수 직전 GUARD30 검문 및 1회분(8%) 단위 자동수혈 실행기:
    1) SOXL 가용현금(now_free_cash)이 30% 가드(min_req_cash) 이상이면 수혈 없이 즉시 정상 매수 승인.
    2) 시드 고갈(now_free_cash < min_req_cash) 감지 시 자동수혈 우선순위:
       - [1순위 : 현금 10% 버킷 (cash_bucket_usd)]
         1회분(8% = portion_budget) 단위로 즉시 수혈. 수혈 직후 잔여 현금 버킷이 30% 가드 미만으로 소진되면
         SGOV 보유 시 즉시 정규장 SGOV 10% 매도 예약(pending_sgov_tranche_sells)을 점화!
       - [2순위 : SGOV 30% 보유 중 정규장 대기]
         현금 10% 가 소진되었으나 SGOV 보유 수량(sgov_held_qty > 0)이 남아 있는 경우,
         내부 예비자본 40%가 아직 소진되지 않았으므로 수익금고를 건드리지 않고 정규장 SGOV 10% 매도 충전을 대기!
       - [3순위 : 내부 40%(현금 10% + SGOV 30%) 전액 소진 시 별도 실현수익금고 (vault_available_usd)]
         sgov_held_qty == 0 이고 현금 버킷도 소진된 경우, 별도 장부의 실현수익금고에서 1회분(8%) 단위로 자동수혈!
       - [4순위 : 토스 계좌 내 미할당 추가 달러 현금 (extra_acct_cash)]
         100% SOXL 보유 상태에서 바벨 모드로 전환했거나 계좌에 추가 입금된 달러가 있으면 1회분(8%) 단위로 자동수혈!
    """
    b_ledger = ensure_barbell_ledger(context)
    bst = b_ledger.get_state()
    if not bool(bst.get("is_initialized", False)):
        bst = await initialize_or_sync_barbell_on_mode_enter(context)
        st_now = context.ledger.get_state(TARGET_SYMBOL)

    now_free_cash = max(0.0, safe_float(st_now.get("free_cash_usd"), 0.0))
    cur_used_res = max(0, safe_int(st_now.get("used_reserve_portions_cnt"), 0))
    cur_inj_usd = max(0.0, safe_float(st_now.get("injected_reserve_usd"), 0.0))
    unit_8pct = max(1.0, safe_float(portion_budget, 480.0))

    eff_rt_pct = resolve_effective_round_trip_fee_rate_pct(state_dict=st_now)
    fee_mult = 1.0 + (eff_rt_pct / 100.0)
    one_share_cost = max(0.01, exec_order_p) * fee_mult

    if is_dip_promotion:
        min_req_cash = max(
            one_share_cost,
            unit_8pct * MIN_DIP_BUDGET_RATIO,
            max(0.0, l1_actual_cost_usd) * MIN_DIP_VS_L1_RATIO,
        )
    else:
        min_req_cash = max(one_share_cost, unit_8pct * MIN_DIP_BUDGET_RATIO)

    raw_bp = max(0.0, safe_float(raw_bp_usd, 0.0))
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
    # [1순위] 현금 10% 대기 버킷에서 1회분(8% = unit_8pct) 단위 즉시 자동수혈 (미집행 SGOV 대기현금 선행 역보충)
    # -----------------------------------------------------------------------
    splits_inj = compute_barbell_seed_splits(
        safe_float(st_now.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD)
    )
    cash_10_target = splits_inj["cash_seed_10_usd"]
    sgov_lp_ref = max(
        1.0, safe_float(bst.get("sgov_last_price"), SGOV_DEFAULT_REF_PRICE)
    )
    if pending_sgov_buy > 0.0 and cash_bucket < cash_10_target:
        pre_shift = round(
            min(pending_sgov_buy, max(0.0, cash_10_target - cash_bucket)), 4
        )
        cash_bucket = round(cash_bucket + pre_shift, 4)
        pending_sgov_buy = round(max(0.0, pending_sgov_buy - pre_shift), 4)

    usable_from_cash_bucket = min(
        cash_bucket, max(0.0, bp_excl_vault - now_free_cash)
    )
    if (
        usable_from_cash_bucket > 0.0
        and (now_free_cash + usable_from_cash_bucket) >= min_req_cash
        and raw_bp >= min_req_cash
    ):
        inj_usd = round(min(req_unit_usd, usable_from_cash_bucket), 4)
        rem_cash_raw = round(max(0.0, cash_bucket - inj_usd), 4)
        shift_from_pending = round(
            min(pending_sgov_buy, max(0.0, cash_10_target - rem_cash_raw)), 4
        )
        rem_cash_bucket = round(rem_cash_raw + shift_from_pending, 4)
        rem_pending_sgov_buy = round(
            max(0.0, pending_sgov_buy - shift_from_pending), 4
        )
        if 0.0 < rem_pending_sgov_buy < (sgov_lp_ref * 1.002):
            rem_cash_bucket = round(
                rem_cash_bucket + rem_pending_sgov_buy, 4
            )
            rem_pending_sgov_buy = 0.0

        new_cash_inj = round(
            safe_float(bst.get("cash_injected_to_soxl_usd"), 0.0) + inj_usd, 4
        )
        new_c_cnt = safe_int(bst.get("cash_injection_count_cycle"), 0) + needed_portions
        new_cum_c_cnt = safe_int(bst.get("cum_cash_injection_count"), 0) + needed_portions

        # 현금 10% 버킷과 미집행 SGOV 매수예약 현금이 모두 소진되었을 때만 정규장 SGOV 10% 매도 큐 점화!
        guard_floor_inj = max(one_share_cost, unit_8pct * MIN_DIP_BUDGET_RATIO)
        cur_pending_sells = max(
            0, safe_int(bst.get("pending_sgov_tranche_sells"), 0)
        )
        trigger_sgov_sell = bool(
            rem_cash_bucket < guard_floor_inj
            and rem_pending_sgov_buy < guard_floor_inj
            and sgov_qty > 0
        )
        next_pending_sells = (
            max(1, cur_pending_sells) if trigger_sgov_sell else cur_pending_sells
        )

        await b_ledger.update_state(
            cash_bucket_usd=rem_cash_bucket,
            pending_sgov_buy_budget_usd=rem_pending_sgov_buy,
            cash_injected_to_soxl_usd=new_cash_inj,
            cash_injection_count_cycle=new_c_cnt,
            cum_cash_injection_count=new_cum_c_cnt,
            pending_sgov_tranche_sells=next_pending_sells,
            barbell_seed_exhausted=bool(
                rem_cash_bucket < one_share_cost
                and rem_pending_sgov_buy < one_share_cost
                and sgov_qty <= 0
            ),
        )

        new_used_res = cur_used_res + needed_portions
        new_inj_usd = round(cur_inj_usd + inj_usd, 4)
        updated_st = await context.ledger.update_state(
            TARGET_SYMBOL,
            used_reserve_portions_cnt=new_used_res,
            injected_reserve_usd=new_inj_usd,
            total_reserve_injected_cnt=safe_int(
                st_now.get("total_reserve_injected_cnt"), 0
            )
            + needed_portions,
            daily_reserve_injected_cnt=safe_int(
                st_now.get("daily_reserve_injected_cnt"), 0
            )
            + needed_portions,
            waiting_reserve_deposit=False,
            waiting_reserve_deposit_alert_sent=False,
            required_reserve_deposit_usd=0.0,
            last_reserve_check_ts=0.0,
        )
        updated_free_cash = max(
            0.0,
            safe_float(updated_st.get("free_cash_usd"), now_free_cash + inj_usd),
        )
        sgov_note = (
            f" · 🔔현금10% 소진 감지 ➔ 정규장 SGOV 10% 보충매도 예약({next_pending_sells}건)"
            if trigger_sgov_sell
            else f" · 잔여 현금버킷 ${rem_cash_bucket:,.2f}"
        )
        if hasattr(context, "send_slim_alert"):
            await context.send_slim_alert(
                title=f"💉 [바벨 1순위 현금버킷 자동수혈 (+{needed_portions}회분 · +${inj_usd:,.2f})]",
                body=(
                    f"타점({trigger_desc}) 시드고갈 감지 ➔ 대기 현금(10%)에서 1회분(8% · ${inj_usd:,.2f}) 즉시 수혈 완료!{sgov_note} · "
                    f"수혈 후 SOXL 가용현금 ${updated_free_cash:,.2f}"
                ),
            )
        context.wakeup_event.set()
        return (
            True,
            updated_free_cash,
            round(min(raw_bp, updated_free_cash) * 0.998, 4),
            {
                "action": "BARBELL_CASH10_INJECTED",
                "should_proceed": True,
                "inject_usd": inj_usd,
            },
        )

    # -----------------------------------------------------------------------
    # [1순위 보조] 정규장 SGOV 매수 전 미체결 예약금(pending_sgov_buy_budget_usd)이 현금으로 남아 있을 때
    # 프리장/장중 급락 시 아직 사지 않은 SGOV 예약 현금에서 10% 트랜치를 우선 현금버킷으로 전환해 즉시 수혈!
    # -----------------------------------------------------------------------
    if (
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
    ):
        splits = compute_barbell_seed_splits(
            safe_float(st_now.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD)
        )
        pull_from_pending = round(
            min(pending_sgov_buy, max(req_unit_usd, splits["cash_seed_10_usd"])),
            4,
        )
        rem_pending_sgov = round(max(0.0, pending_sgov_buy - pull_from_pending), 4)
        pooled_cash = round(cash_bucket + pull_from_pending, 4)
        inj_usd = round(min(req_unit_usd, pooled_cash), 4)
        rem_cash_b = round(max(0.0, pooled_cash - inj_usd), 4)

        await b_ledger.update_state(
            cash_bucket_usd=rem_cash_b,
            pending_sgov_buy_budget_usd=rem_pending_sgov,
            cash_injected_to_soxl_usd=round(
                safe_float(bst.get("cash_injected_to_soxl_usd"), 0.0) + inj_usd,
                4,
            ),
            cash_injection_count_cycle=safe_int(
                bst.get("cash_injection_count_cycle"), 0
            )
            + needed_portions,
            cum_cash_injection_count=safe_int(
                bst.get("cum_cash_injection_count"), 0
            )
            + needed_portions,
        )
        updated_st = await context.ledger.update_state(
            TARGET_SYMBOL,
            used_reserve_portions_cnt=cur_used_res + needed_portions,
            injected_reserve_usd=round(cur_inj_usd + inj_usd, 4),
            total_reserve_injected_cnt=safe_int(
                st_now.get("total_reserve_injected_cnt"), 0
            )
            + needed_portions,
            daily_reserve_injected_cnt=safe_int(
                st_now.get("daily_reserve_injected_cnt"), 0
            )
            + needed_portions,
            waiting_reserve_deposit=False,
            waiting_reserve_deposit_alert_sent=False,
            required_reserve_deposit_usd=0.0,
            last_reserve_check_ts=0.0,
        )
        updated_free_cash = max(
            0.0,
            safe_float(updated_st.get("free_cash_usd"), now_free_cash + inj_usd),
        )
        if hasattr(context, "send_slim_alert"):
            await context.send_slim_alert(
                title=f"💉 [바벨 SGOV 매수대기 현금 선행 자동수혈 (+${inj_usd:,.2f})]",
                body=(
                    f"정규장 SGOV 매수 전 급락 타점({trigger_desc}) 도달 ➔ SGOV 대기현금에서 1회분(${inj_usd:,.2f}) 선행 수혈 완료! · "
                    f"잔여 SGOV 예약금 ${rem_pending_sgov:,.2f} / 현금버킷 ${rem_cash_b:,.2f}"
                ),
            )
        return (
            True,
            updated_free_cash,
            round(min(raw_bp, updated_free_cash) * 0.998, 4),
            {
                "action": "BARBELL_PENDING_SGOV_CASH_INJECTED",
                "should_proceed": True,
                "inject_usd": inj_usd,
            },
        )

    # -----------------------------------------------------------------------
    # [2순위] 현금 10% 소진 & SGOV 보유 중(sgov_held_qty > 0) ➔ 정규장 SGOV 10% 매도 충전 대기
    # -----------------------------------------------------------------------
    if sgov_qty > 0:
        next_sells = max(1, safe_int(bst.get("pending_sgov_tranche_sells"), 0))
        already_sent = bool(bst.get("sgov_wait_alert_sent", False))
        await b_ledger.update_state(
            pending_sgov_tranche_sells=next_sells,
            sgov_wait_alert_sent=True,
        )
        now_est = datetime.now(EST_TZ)
        in_reg = is_sgov_regular_trading_window(now_est=now_est)
        if in_reg:
            await execute_barbell_sgov_tick_plugin(context, now_est=now_est)
        elif not already_sent and hasattr(context, "send_slim_alert"):
            await context.send_slim_alert(
                title="⏳ [바벨 현금 10% 소진 · 정규장 SGOV 10% 현금화 예약]",
                body=(
                    f"타점({trigger_desc}) 도달 · 현금버킷(${cash_bucket:,.2f}) 소진으로 보유 SGOV({sgov_qty}주) 중 "
                    f"현금 10% 상당 정수 수량을 09:31 EST 정규장 개시 즉시 매도하여 현금화합니다. (별도 수익금고 100% 보호 유지)"
                ),
            )
        return (
            False,
            now_free_cash,
            0.0,
            {
                "action": "HOLD_BARBELL_WAIT_SGOV_LIQUIDATION",
                "should_proceed": False,
                "sgov_held_qty": sgov_qty,
                "pending_sgov_tranche_sells": next_sells,
            },
        )

    # -----------------------------------------------------------------------
    # [3순위] 내부 예비자본 40%(현금 10% + SGOV 30%) 전액 소진 시 ➔ 별도 실현수익금고에서 1회분(8%) 자동수혈!
    # -----------------------------------------------------------------------
    pooled_with_vault = cash_bucket + vault_avail
    if (
        vault_avail > 0.0
        and raw_bp >= min_req_cash
        and (now_free_cash + pooled_with_vault) >= min_req_cash
    ):
        take_from_cash = round(min(cash_bucket, req_unit_usd), 4)
        rem_need = round(max(0.0, req_unit_usd - take_from_cash), 4)
        take_from_vault = round(min(vault_avail, rem_need), 4)
        inj_usd = round(take_from_cash + take_from_vault, 4)

        v_tot = safe_float(bst.get("vault_realized_profit_usd"), 0.0)
        new_v_inj = round(
            safe_float(bst.get("vault_injected_to_soxl_usd"), 0.0)
            + take_from_vault,
            4,
        )
        new_v_avail = round(max(0.0, v_tot - new_v_inj), 4)

        await b_ledger.update_state(
            cash_bucket_usd=round(max(0.0, cash_bucket - take_from_cash), 4),
            vault_injected_to_soxl_usd=new_v_inj,
            vault_available_usd=new_v_avail,
            vault_injection_count_cycle=safe_int(
                bst.get("vault_injection_count_cycle"), 0
            )
            + needed_portions,
            cum_vault_injection_count=safe_int(
                bst.get("cum_vault_injection_count"), 0
            )
            + needed_portions,
            barbell_seed_exhausted=True,
        )
        updated_st = await context.ledger.update_state(
            TARGET_SYMBOL,
            used_reserve_portions_cnt=cur_used_res + needed_portions,
            injected_reserve_usd=round(cur_inj_usd + inj_usd, 4),
            total_reserve_injected_cnt=safe_int(
                st_now.get("total_reserve_injected_cnt"), 0
            )
            + needed_portions,
            daily_reserve_injected_cnt=safe_int(
                st_now.get("daily_reserve_injected_cnt"), 0
            )
            + needed_portions,
            waiting_reserve_deposit=False,
            waiting_reserve_deposit_alert_sent=False,
            required_reserve_deposit_usd=0.0,
            last_reserve_check_ts=0.0,
        )
        updated_free_cash = max(
            0.0,
            safe_float(updated_st.get("free_cash_usd"), now_free_cash + inj_usd),
        )
        if hasattr(context, "send_slim_alert"):
            await context.send_slim_alert(
                title=f"🏦 [바벨 40% 예비자본 소진 ➔ 별도 수익금고 1회분(8%) 자동수혈 (+${inj_usd:,.2f})]",
                body=(
                    f"현금(10%) 및 SGOV(30%) 전액 소진 후 타점({trigger_desc}) 도달 ➔ "
                    f"별도 실현수익금고에서 +${take_from_vault:,.2f} 긴급 수혈 완료! "
                    f"(잔여 금고 가용액 ${new_v_avail:,.2f} · 지층 익절 시 0순위로 금고에 즉시 원복됩니다)"
                ),
            )
        return (
            True,
            updated_free_cash,
            round(min(raw_bp, updated_free_cash) * 0.998, 4),
            {
                "action": "BARBELL_PROFIT_VAULT_INJECTED",
                "should_proceed": True,
                "inject_usd": inj_usd,
            },
        )

    # -----------------------------------------------------------------------
    # [4순위] 토스 실계좌 내 미할당 추가 달러 현금(extra_acct_cash) 존재 시 1회분(8%) 자동수혈
    # (SOXL 100% 보유 전환으로 바벨 시드고갈 상태일 때 계좌 추가현금 즉시 활용)
    # -----------------------------------------------------------------------
    extra_acct_cash = max(
        0.0,
        raw_bp - (now_free_cash + cash_bucket + pending_sgov_buy + vault_avail),
    )
    if (
        extra_acct_cash > 0.0
        and raw_bp >= min_req_cash
        and (now_free_cash + extra_acct_cash) >= min_req_cash
    ):
        inj_ext = round(min(req_unit_usd, extra_acct_cash), 4)
        new_ext_inj = round(
            safe_float(bst.get("external_injected_to_soxl_usd"), 0.0)
            + inj_ext,
            4,
        )
        await b_ledger.update_state(
            external_injected_to_soxl_usd=new_ext_inj,
            barbell_seed_exhausted=True,
        )
        updated_st = await context.ledger.update_state(
            TARGET_SYMBOL,
            used_reserve_portions_cnt=cur_used_res + needed_portions,
            injected_reserve_usd=round(cur_inj_usd + inj_ext, 4),
            total_reserve_injected_cnt=safe_int(
                st_now.get("total_reserve_injected_cnt"), 0
            )
            + needed_portions,
            daily_reserve_injected_cnt=safe_int(
                st_now.get("daily_reserve_injected_cnt"), 0
            )
            + needed_portions,
            waiting_reserve_deposit=False,
            waiting_reserve_deposit_alert_sent=False,
            required_reserve_deposit_usd=0.0,
            last_reserve_check_ts=0.0,
        )
        updated_free_cash = max(
            0.0,
            safe_float(
                updated_st.get("free_cash_usd"), now_free_cash + inj_ext
            ),
        )
        if hasattr(context, "send_slim_alert"):
            await context.send_slim_alert(
                title=f"💉 [바벨 계좌 추가현금 자동수혈 (+{needed_portions}회분 · +${inj_ext:,.2f})]",
                body=(
                    f"바벨 내부예비금 소진 상태에서 토스 계좌 추가현금 감지 ➔ 1회분(8% · ${inj_ext:,.2f}) 자동수혈 완료! · "
                    f"수혈 후 SOXL 가용현금 ${updated_free_cash:,.2f}"
                ),
            )
        return (
            True,
            updated_free_cash,
            round(min(raw_bp, updated_free_cash) * 0.998, 4),
            {
                "action": "BARBELL_EXTRA_CASH_INJECTED",
                "should_proceed": True,
                "inject_usd": inj_ext,
            },
        )

    # 모든 내부 버킷(현금 10% + SGOV 30%) · 수익금고 · 계좌 추가현금이 전부 소진된 경우: 단 1회 입금 요청 알림
    await b_ledger.update_state(barbell_seed_exhausted=True)
    alert_sent = bool(st_now.get("waiting_reserve_deposit_alert_sent", False))
    await context.ledger.update_state(
        TARGET_SYMBOL,
        waiting_reserve_deposit=True,
        waiting_reserve_deposit_alert_sent=True,
        required_reserve_deposit_usd=round(unit_8pct, 2),
        last_reserve_check_ts=time.time(),
    )
    if not alert_sent and hasattr(context, "send_slim_alert"):
        await context.send_slim_alert(
            title=f"🚨 [⚖️ 바벨 모드 전 버킷 소진 · 1회분(${unit_8pct:,.2f}) 추가 입금 요청]",
            body=(
                f"타점({trigger_desc} @ ${exec_order_p:.2f}) 도달 · "
                f"SOXL(60%) · 현금(10%) · SGOV(30%) 및 별도 수익금고(가용 ${vault_avail:,.2f})가 모두 소진되었습니다. · "
                f"토스 달러 계좌에 ${unit_8pct:,.2f} 이상 입금하시면 즉시 1회분(8%) 단위로 자동 수혈합니다."
            ),
        )
    return (
        False,
        now_free_cash,
        0.0,
        {
            "action": "BLOCK_BARBELL_ALL_EXHAUSTED",
            "should_proceed": False,
            "recommended_deposit_usd": round(unit_8pct, 2),
        },
    )


# ---------------------------------------------------------------------------
# [핵심 4] 정규장(09:31 ~ 15:55 EST) 전용 SGOV 주문 체결 동기화 및 매수/매도 실행 엔진
# ---------------------------------------------------------------------------
async def _sync_pending_sgov_orders(
    context: Any,
    b_ledger: BarbellLedger,
    bst: Dict[str, Any],
    force_settle: bool = False,
) -> Dict[str, Any]:
    buy_oid = str(bst.get("sgov_buy_order_id") or "").strip()
    sell_oid = str(bst.get("sgov_sell_order_id") or "").strip()
    if not buy_oid and not sell_oid:
        return {"status": "NO_PENDING_SGOV_ORDER"}

    oid = buy_oid or sell_oid
    is_buy = bool(buy_oid)
    ord_qty = max(1, safe_int(bst.get("sgov_ordered_qty"), 1))
    ord_p = max(1.0, safe_float(bst.get("sgov_order_price"), SGOV_DEFAULT_REF_PRICE))
    now_mono = time.monotonic()
    ord_mono = safe_float(bst.get("sgov_order_mono"), now_mono)
    if ord_mono <= 0.0 or ord_mono > now_mono:
        ord_mono = now_mono
    elapsed = now_mono - ord_mono

    settled_oids: List[str] = list(bst.get("last_settled_sgov_order_ids") or [])
    detail = await context.api.get_order_detail(oid)
    filled_q = 0
    avg_fill_p = 0.0
    ord_status = ""

    if isinstance(detail, dict):
        ord_status = str(detail.get("status") or "").upper().strip()
        exec_obj = (
            detail.get("execution")
            if isinstance(detail.get("execution"), dict)
            else {}
        )
        filled_q = safe_int(exec_obj.get("filledQuantity"), 0)
        avg_fill_p = safe_float(exec_obj.get("averageFilledPrice"), 0.0)

    is_done_fill = bool(
        ord_status == "FILLED"
        or (filled_q > 0 and ord_status in ("CANCELED", "REJECTED", "REPLACED"))
    )
    need_timeout_cancel = bool(
        not is_done_fill
        and (
            elapsed >= SGOV_ORDER_MAX_WAIT_SEC
            or force_settle
            or ord_status == "PENDING_CANCEL"
        )
    )

    if need_timeout_cancel:
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
        is_done_fill = bool(filled_q > 0)

    if is_done_fill:
        eff_q = filled_q if filled_q > 0 else ord_qty
        eff_p = round(avg_fill_p if avg_fill_p > 0.0 else ord_p, 4)
        if oid not in settled_oids:
            settled_oids.append(oid)

        if is_buy:
            spent = round(float(eff_q) * eff_p, 4)
            new_q = safe_int(bst.get("sgov_held_qty"), 0) + eff_q
            new_inv = round(
                safe_float(bst.get("sgov_invested_usd"), 0.0) + spent, 4
            )
            rem_bud = round(
                max(
                    0.0,
                    safe_float(bst.get("pending_sgov_buy_budget_usd"), 0.0)
                    - spent,
                ),
                4,
            )
            cash_b = safe_float(bst.get("cash_bucket_usd"), 0.0)
            # 1주 미만 단주 잔여 예산은 현금 10% 버킷에 자동 합산하여 유휴 사각지대 제거
            if 0.0 < rem_bud < (eff_p * 1.002):
                cash_b = round(cash_b + rem_bud, 4)
                rem_bud = 0.0

            await b_ledger.update_state(
                sgov_held_qty=new_q,
                sgov_invested_usd=new_inv,
                sgov_avg_price=round(new_inv / float(max(1, new_q)), 4),
                sgov_last_price=eff_p,
                pending_sgov_buy_budget_usd=rem_bud,
                cash_bucket_usd=cash_b,
                cum_sgov_buy_events=safe_int(bst.get("cum_sgov_buy_events"), 0)
                + 1,
                sgov_buy_order_id="",
                sgov_ordered_qty=0,
                sgov_order_price=0.0,
                sgov_order_purpose="",
                sgov_order_mono=0.0,
                last_sgov_action_mono=time.monotonic(),
                last_settled_sgov_order_ids=settled_oids[-50:],
            )
            if hasattr(context, "send_slim_alert"):
                await context.send_slim_alert(
                    title=f"🛡️ [바벨 SGOV 30% 안전버킷 매수 체결] +{eff_q}주 @ ${eff_p:.2f}",
                    body=(
                        f"실투입 ${spent:,.2f} · 현재 SGOV 보유 {new_q}주(${new_inv:,.2f}) · "
                        f"대기 현금버킷 ${cash_b:,.2f} (단주 자투리 합산 완료)"
                    ),
                )
            return {"status": "SGOV_BUY_FILLED", "qty": eff_q, "price": eff_p}

        # SGOV 10% 보충 매도 체결 정산
        old_q = max(eff_q, safe_int(bst.get("sgov_held_qty"), eff_q))
        old_inv = max(
            0.01,
            safe_float(bst.get("sgov_invested_usd"), float(old_q) * eff_p),
        )
        sold_cost = round(old_inv * (float(eff_q) / float(old_q)), 4)
        rem_q = max(0, old_q - eff_q)
        rem_inv = (
            round(max(0.0, old_inv - sold_cost), 4) if rem_q > 0 else 0.0
        )

        st_soxl = context.ledger.get_state(TARGET_SYMBOL)
        eff_rt_pct = resolve_effective_round_trip_fee_rate_pct(
            state_dict=st_soxl
        )
        pnl_info = calc_sell_realized_pnl(
            sold_qty=eff_q,
            sell_exec_price=eff_p,
            sold_actual_cost_usd=sold_cost,
            round_trip_fee_rate_pct=eff_rt_pct,
        )
        net_proceeds = round(
            max(
                0.0,
                float(eff_q) * eff_p
                - safe_float(pnl_info.get("fee_usd"), 0.0),
            ),
            4,
        )
        sgov_gain = round(max(0.0, net_proceeds - sold_cost), 4)
        add_to_cash_bucket = round(max(0.0, net_proceeds - sgov_gain), 4)

        new_cash_b = round(
            safe_float(bst.get("cash_bucket_usd"), 0.0) + add_to_cash_bucket, 4
        )
        new_v_tot = round(
            safe_float(bst.get("vault_realized_profit_usd"), 0.0) + sgov_gain, 4
        )
        v_inj = safe_float(bst.get("vault_injected_to_soxl_usd"), 0.0)
        rem_tranches = max(
            0, safe_int(bst.get("pending_sgov_tranche_sells"), 1) - 1
        )
        sells_done = safe_int(bst.get("sgov_tranche_sells_done_cycle"), 0) + 1

        await b_ledger.update_state(
            sgov_held_qty=rem_q,
            sgov_invested_usd=rem_inv,
            sgov_avg_price=(
                round(rem_inv / float(rem_q), 4) if rem_q > 0 else 0.0
            ),
            sgov_last_price=eff_p,
            cash_bucket_usd=new_cash_b,
            vault_realized_profit_usd=new_v_tot,
            vault_available_usd=round(max(0.0, new_v_tot - v_inj), 4),
            daily_vaulted_profit_usd=round(
                safe_float(bst.get("daily_vaulted_profit_usd"), 0.0)
                + sgov_gain,
                4,
            ),
            cycle_vaulted_profit_usd=round(
                safe_float(bst.get("cycle_vaulted_profit_usd"), 0.0)
                + sgov_gain,
                4,
            ),
            pending_sgov_tranche_sells=(rem_tranches if rem_q > 0 else 0),
            sgov_tranche_sells_done_cycle=sells_done,
            cum_sgov_sell_events=safe_int(bst.get("cum_sgov_sell_events"), 0)
            + 1,
            sgov_wait_alert_sent=False,
            sgov_sell_order_id="",
            sgov_ordered_qty=0,
            sgov_order_price=0.0,
            sgov_order_purpose="",
            sgov_order_mono=0.0,
            last_sgov_action_mono=time.monotonic(),
            last_settled_sgov_order_ids=settled_oids[-50:],
        )
        await context.ledger.update_state(
            TARGET_SYMBOL,
            waiting_reserve_deposit=False,
            waiting_reserve_deposit_alert_sent=False,
            required_reserve_deposit_usd=0.0,
            last_reserve_check_ts=0.0,
        )
        context.wakeup_event.set()
        if hasattr(context, "send_slim_alert"):
            gain_note = (
                f" (SGOV 차익 +${sgov_gain:.2f} 별도금고 격리)"
                if sgov_gain > 0.0
                else ""
            )
            await context.send_slim_alert(
                title=f"💵 [바벨 SGOV 10% 현금화 매도 체결 ({sells_done}회차)] -{eff_q}주 @ ${eff_p:.2f}",
                body=(
                    f"현금버킷 +${add_to_cash_bucket:,.2f} 충전 완료(현재 현금버킷 ${new_cash_b:,.2f}){gain_note} · "
                    f"잔여 SGOV {rem_q}주(${rem_inv:,.2f})"
                ),
            )
        return {"status": "SGOV_SELL_FILLED", "qty": eff_q, "price": eff_p}

    if need_timeout_cancel or ord_status in ("CANCELED", "REJECTED"):
        await b_ledger.update_state(
            sgov_buy_order_id="",
            sgov_sell_order_id="",
            sgov_ordered_qty=0,
            sgov_order_price=0.0,
            sgov_order_purpose="",
            sgov_order_mono=0.0,
            last_sgov_action_mono=time.monotonic(),
        )
        return {"status": "SGOV_ORDER_CANCELED_SAFE"}

    return {"status": "SGOV_ORDER_WAITING", "orderId": oid}


async def execute_barbell_sgov_tick_plugin(
    context: Any,
    now_est: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    main_sniper_loop 에서 매 틱 호출되는 바벨 모드 SGOV 정규장 전용 오케스트레이터:
    - 미체결 SGOV 주문 체결 확인 및 장 마감 시 안전 취소
    - 평일 정규장(09:31 ~ 15:55 EST) 구간에서:
      1순위: 현금 10% 소진에 따른 SGOV 10% 내림(floor) 정수 수량 지정가 매도
      2순위: 초기 진입 또는 0주 졸업 리밸런싱 후 SGOV 30% 지정가 매수
    """
    st_soxl = context.ledger.get_state(TARGET_SYMBOL)
    if not is_barbell_mode(st_soxl.get("portion_mode")):
        return {"status": "NOT_BARBELL_MODE"}

    dt_now = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    today_str = dt_now.strftime("%Y-%m-%d")
    b_ledger = ensure_barbell_ledger(context)
    bst = await b_ledger.rollover_daily_if_needed(today_str)

    if not bool(bst.get("is_initialized", False)):
        bst = await initialize_or_sync_barbell_on_mode_enter(context)

    in_reg = is_sgov_regular_trading_window(now_est=dt_now)

    # 1) 진행 중인 SGOV 미체결 주문 최우선 동기화
    if str(bst.get("sgov_buy_order_id") or "").strip() or str(
        bst.get("sgov_sell_order_id") or ""
    ).strip():
        return await _sync_pending_sgov_orders(
            context=context,
            b_ledger=b_ledger,
            bst=bst,
            force_settle=(not in_reg),
        )

    if not in_reg or not bool(st_soxl.get("is_active", True)):
        return {"status": "OUTSIDE_SGOV_REGULAR_WINDOW"}

    # SOXL 주문 진행 중에는 예수금 충돌 방지를 위해 SGOV 발주 대기
    if str(st_soxl.get("buy_order_id") or "").strip() or str(
        st_soxl.get("sell_order_id") or ""
    ).strip():
        return {"status": "WAIT_SOXL_ORDER_FIRST"}

    now_mono = time.monotonic()
    if (
        now_mono - safe_float(bst.get("last_sgov_action_mono"), 0.0)
    ) < SGOV_ACTION_COOLDOWN_SEC:
        return {"status": "SGOV_COOLDOWN"}

    pending_sells = max(0, safe_int(bst.get("pending_sgov_tranche_sells"), 0))
    sgov_qty = max(0, safe_int(bst.get("sgov_held_qty"), 0))
    pending_buy_bud = max(
        0.0, safe_float(bst.get("pending_sgov_buy_budget_usd"), 0.0)
    )

    if pending_sells <= 0 and pending_buy_bud <= 0.0:
        return {"status": "BARBELL_SGOV_IDLE"}

    sgov_lp = await context.api.get_current_price(BARBELL_SAFE_SYMBOL)
    if sgov_lp <= 1.0:
        return {"status": "NO_SGOV_LIVE_PRICE"}

    init_seed = safe_float(
        st_soxl.get("initial_seed_usd"),
        safe_float(bst.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD),
    )

    # 2) [1순위] SGOV 10% 상당 정수 수량(소수점 내림) 지정가 매도
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
        if sell_q > 0:
            bid_p = await context.api.get_best_bid_price(
                BARBELL_SAFE_SYMBOL, fallback_price=sgov_lp
            )
            exec_sell_p = round(
                max(
                    1.0,
                    math.floor((min(sgov_lp, bid_p) + 1e-9) * 100.0) / 100.0,
                ),
                2,
            )
            cid = generate_client_order_id(prefix="SGVSEL")
            try:
                ord_res = await context.api.create_order(
                    symbol=BARBELL_SAFE_SYMBOL,
                    side="SELL",
                    quantity=sell_q,
                    price=exec_sell_p,
                    order_type="LIMIT",
                    time_in_force="DAY",
                    client_order_id=cid,
                    enforce_daymarket_block=False,
                    allow_barbell_sgov=True,
                )
                oid = str(ord_res.get("orderId") or "").strip()
                await b_ledger.update_state(
                    sgov_last_price=round(sgov_lp, 4),
                    sgov_sell_order_id=oid,
                    sgov_client_order_id=cid,
                    sgov_ordered_qty=sell_q,
                    sgov_order_price=exec_sell_p,
                    sgov_order_purpose="REPLENISH_CASH_10PCT",
                    sgov_order_mono=time.monotonic(),
                    last_sgov_action_mono=time.monotonic(),
                )
                logger.info(
                    "💵 [바벨 정규장 SGOV 10%% 보충 매도 발주] -%d주 @ 지정가 $%.2f (보유 %d주 · orderId=%s)",
                    sell_q,
                    exec_sell_p,
                    sgov_qty,
                    oid,
                )
                return {
                    "status": "SGOV_TRANCHE_SELL_ORDERED",
                    "qty": sell_q,
                    "price": exec_sell_p,
                }
            except _NonRetryableApiError as api_err:
                await b_ledger.update_state(
                    last_sgov_action_mono=time.monotonic()
                )
                logger.warning("바벨 SGOV 매도 거절(쿨다운): %s", api_err)
                return {"status": "SGOV_SELL_REJECTED"}
            except Exception as exc:
                await b_ledger.update_state(
                    last_sgov_action_mono=time.monotonic()
                )
                logger.warning("바벨 SGOV 매도 예외: %s", exc)
                return {"status": "SGOV_SELL_ERROR"}

    # 3) [2순위] SGOV 30% 목표 예산 범위 내 지정가 매수 (현금 10% 완충 우선 확인 후 초과분만 발주)
    if (
        pending_buy_bud > 0.0
        and pending_sells == 0
        and not bool(st_soxl.get("waiting_reserve_deposit", False))
    ):
        splits_tick = compute_barbell_seed_splits(init_seed)
        cash_10_tick = splits_tick["cash_seed_10_usd"]
        cur_cash_b = max(0.0, safe_float(bst.get("cash_bucket_usd"), 0.0))
        if cur_cash_b + 0.01 < cash_10_tick:
            shift_to_cash = round(
                min(pending_buy_bud, cash_10_tick - cur_cash_b), 4
            )
            cur_cash_b = round(cur_cash_b + shift_to_cash, 4)
            pending_buy_bud = round(
                max(0.0, pending_buy_bud - shift_to_cash), 4
            )
            bst = await b_ledger.update_state(
                cash_bucket_usd=cur_cash_b,
                pending_sgov_buy_budget_usd=pending_buy_bud,
            )
            if pending_buy_bud <= 0.0:
                return {"status": "BARBELL_CASH_10PCT_PRIORITIZED"}

        ask_p = await context.api.get_best_ask_price(
            BARBELL_SAFE_SYMBOL, fallback_price=sgov_lp
        )
        exec_buy_p = round(
            max(1.0, math.ceil((max(sgov_lp, ask_p) - 1e-9) * 100.0) / 100.0),
            2,
        )
        eff_rt_pct = resolve_effective_round_trip_fee_rate_pct(
            state_dict=st_soxl
        )
        fee_mult = 1.0 + (eff_rt_pct / 100.0)

        # 예약 예산 자체가 1주 가격 미만이면 즉시 현금 10% 버킷으로 이관 종료
        if pending_buy_bud < (exec_buy_p * fee_mult):
            await b_ledger.update_state(
                cash_bucket_usd=round(
                    safe_float(bst.get("cash_bucket_usd"), 0.0)
                    + pending_buy_bud,
                    4,
                ),
                pending_sgov_buy_budget_usd=0.0,
            )
            return {"status": "SGOV_DUST_MOVED_TO_CASH_BUCKET"}

        raw_bp = await context.api.get_buying_power_usd(safety_buffer_pct=0.0)
        if raw_bp <= 0.0:
            await asyncio.sleep(0.25)
            raw_bp = await context.api.get_buying_power_usd(
                safety_buffer_pct=0.0
            )
        soxl_free = max(0.0, safe_float(st_soxl.get("free_cash_usd"), 0.0))
        cash_b = max(0.0, safe_float(bst.get("cash_bucket_usd"), 0.0))
        vault_av = max(0.0, safe_float(bst.get("vault_available_usd"), 0.0))
        avail_for_sgov = max(0.0, raw_bp - soxl_free - cash_b - vault_av)
        eff_bud = min(pending_buy_bud, avail_for_sgov)

        buy_q = int(
            math.floor((eff_bud + 1e-9) / (exec_buy_p * fee_mult))
        )
        if buy_q <= 0:
            await b_ledger.update_state(last_sgov_action_mono=time.monotonic())
            return {"status": "HOLD_SGOV_BUY_INSUFFICIENT_BP"}

        cid = generate_client_order_id(prefix="SGVBUY")
        try:
            ord_res = await context.api.create_order(
                symbol=BARBELL_SAFE_SYMBOL,
                side="BUY",
                quantity=buy_q,
                price=exec_buy_p,
                order_type="LIMIT",
                time_in_force="DAY",
                client_order_id=cid,
                enforce_daymarket_block=True,
                allow_barbell_sgov=True,
            )
            oid = str(ord_res.get("orderId") or "").strip()
            await b_ledger.update_state(
                sgov_last_price=round(sgov_lp, 4),
                sgov_buy_order_id=oid,
                sgov_client_order_id=cid,
                sgov_ordered_qty=buy_q,
                sgov_order_price=exec_buy_p,
                sgov_order_purpose="REBALANCE_SGOV_30PCT",
                sgov_order_mono=time.monotonic(),
                last_sgov_action_mono=time.monotonic(),
            )
            logger.info(
                "🛡️ [바벨 정규장 SGOV 30%% 리밸런싱 매수 발주] +%d주 @ 지정가 $%.2f (예산 $%.2f · orderId=%s)",
                buy_q,
                exec_buy_p,
                eff_bud,
                oid,
            )
            return {
                "status": "SGOV_REBALANCE_BUY_ORDERED",
                "qty": buy_q,
                "price": exec_buy_p,
            }
        except Exception as exc:
            await b_ledger.update_state(last_sgov_action_mono=time.monotonic())
            logger.warning("바벨 SGOV 매수 예외: %s", exc)
            return {"status": "SGOV_BUY_ERROR"}

    return {"status": "BARBELL_TICK_DONE"}


# ---------------------------------------------------------------------------
# [핵심 5] 바벨 모드 관제 요약기 · 슬림 레이더 블록 · /barbell 상세 보드 및 TDD 검증기
# ---------------------------------------------------------------------------
def summarize_barbell_status(
    context: Any,
    st_soxl: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    soxl_state = (
        st_soxl
        if isinstance(st_soxl, dict)
        else (
            context.ledger.get_state(TARGET_SYMBOL)
            if (context is not None and hasattr(context, "ledger"))
            else {}
        )
    )
    b_ledger = ensure_barbell_ledger(context)
    bst = b_ledger.get_state()
    init_seed = safe_float(
        soxl_state.get("initial_seed_usd"),
        safe_float(bst.get("initial_seed_usd"), DEFAULT_INITIAL_SEED_USD),
    )
    splits = compute_barbell_seed_splits(init_seed)
    sgov_q = safe_int(bst.get("sgov_held_qty"), 0)
    sgov_lp = safe_float(bst.get("sgov_last_price"), SGOV_DEFAULT_REF_PRICE)
    sgov_eval = round(float(sgov_q) * sgov_lp, 4) if sgov_q > 0 else 0.0
    return {
        "is_barbell_active": is_barbell_mode(soxl_state.get("portion_mode")),
        **splits,
        "cash_bucket_usd": safe_float(bst.get("cash_bucket_usd"), 0.0),
        "cash_injected_to_soxl_usd": safe_float(
            bst.get("cash_injected_to_soxl_usd"), 0.0
        ),
        "sgov_held_qty": sgov_q,
        "sgov_avg_price": safe_float(bst.get("sgov_avg_price"), 0.0),
        "sgov_invested_usd": safe_float(bst.get("sgov_invested_usd"), 0.0),
        "sgov_last_price": sgov_lp,
        "sgov_eval_usd": sgov_eval,
        "pending_sgov_buy_budget_usd": safe_float(
            bst.get("pending_sgov_buy_budget_usd"), 0.0
        ),
        "pending_sgov_tranche_sells": safe_int(
            bst.get("pending_sgov_tranche_sells"), 0
        ),
        "sgov_tranche_sells_done_cycle": safe_int(
            bst.get("sgov_tranche_sells_done_cycle"), 0
        ),
        "vault_realized_profit_usd": safe_float(
            bst.get("vault_realized_profit_usd"), 0.0
        ),
        "vault_available_usd": safe_float(bst.get("vault_available_usd"), 0.0),
        "vault_injected_to_soxl_usd": safe_float(
            bst.get("vault_injected_to_soxl_usd"), 0.0
        ),
        "daily_vaulted_profit_usd": safe_float(
            bst.get("daily_vaulted_profit_usd"), 0.0
        ),
        "cycle_vaulted_profit_usd": safe_float(
            bst.get("cycle_vaulted_profit_usd"), 0.0
        ),
        "last_cycle_vaulted_profit_usd": safe_float(
            bst.get("last_cycle_vaulted_profit_usd"), 0.0
        ),
        "completed_barbell_cycles": safe_int(
            bst.get("completed_barbell_cycles"), 0
        ),
    }


def format_barbell_slim_radar_block(context: Any) -> str:
    """
    /avwap, /sync, /settlement 하단에 결합되는 36자 칼맞춤 바벨 모드 & 격리 수익금고 요약 블록.
    """
    try:
        info = summarize_barbell_status(context)
        v_tot = safe_float(info.get("vault_realized_profit_usd"), 0.0)
        if not info.get("is_barbell_active") and v_tot <= 0.0:
            return ""

        sgov_q = safe_int(info.get("sgov_held_qty"), 0)
        sgov_inv = safe_float(info.get("sgov_invested_usd"), 0.0)
        pend_b = safe_float(info.get("pending_sgov_buy_budget_usd"), 0.0)
        pend_s = safe_int(info.get("pending_sgov_tranche_sells"), 0)
        cash_b = safe_float(info.get("cash_bucket_usd"), 0.0)
        v_avail = safe_float(info.get("vault_available_usd"), 0.0)

        sgov_note = f"{sgov_q}주(${sgov_inv:,.0f})"
        if pend_s > 0:
            sgov_note += f"·매도예약{pend_s}"
        elif pend_b > 0.0:
            sgov_note += f"·매수대기${pend_b:,.0f}"

        return "\n".join(
            [
                "──────────────",
                f"⚖️ <b>[바벨 60/30/10]</b> SGOV <b>{sgov_note}</b> · 대기현금 <b>${cash_b:,.0f}</b>",
                f"🏦 별도수익금고: 누적 <b>+${v_tot:,.2f}</b> (가용 <b>${v_avail:,.2f}</b> · <code>/barbell</code>)",
            ]
        )
    except Exception:
        return ""


async def build_barbell_detail_dashboard_html(context: Any) -> str:
    """
    /barbell 명령어 호출 시 표출되는 바벨 모드 60/30/10 및 별도 수익금고 상세 관제 보드.
    """
    now_est = datetime.now(EST_TZ)
    if context is not None and hasattr(context, "api"):
        try:
            sg_p = await context.api.get_current_price(BARBELL_SAFE_SYMBOL)
            if sg_p > 1.0:
                await ensure_barbell_ledger(context).update_state(
                    sgov_last_price=round(sg_p, 4)
                )
        except Exception:
            pass

    st_soxl = (
        context.ledger.get_state(TARGET_SYMBOL)
        if (context is not None and hasattr(context, "ledger"))
        else {}
    )
    info = summarize_barbell_status(context, st_soxl=st_soxl)
    active_str = (
        "🟢 가동중 (BARBELL_60_30_10)"
        if info["is_barbell_active"]
        else "⚪ 대기중 (타 모드 운용중 · 금고 보존)"
    )
    in_reg = is_sgov_regular_trading_window(now_est=now_est)
    reg_badge = "🟢정규장 개방" if in_reg else "🔒정규장 외 대기(09:31~15:55)"

    lines = [
        "⚖️ <b>[인피니트 스노우볼 · 바벨(60/30/10) 관제 보드]</b>",
        f"⚙️ 상태: <b>{active_str}</b>",
        f"💵 설정 기준시드: <b>${info['total_seed_usd']:,.2f}</b>",
        "━━━━━━━━━━━━━━━━━━",
        "📊 <b>[60 / 30 / 10 목표 배분 및 현재 잔고]</b>",
        f"① 🐂 SOXL 코어(60%): 목표 <b>${info['soxl_seed_60_usd']:,.2f}</b> (1회분 8% = <b>${info['soxl_portion_8pct_usd']:,.2f}</b>)",
        f"② 🛡️ SGOV 버킷(30%): 보유 <b>{info['sgov_held_qty']}주</b> (원금 <b>${info['sgov_invested_usd']:,.2f}</b> · 현재가 ${info['sgov_last_price']:.2f})",
        f"   ▫️ SGOV 세션: {reg_badge} | 매수예약 <b>${info['pending_sgov_buy_budget_usd']:,.0f}</b> · 매도예약 <b>{info['pending_sgov_tranche_sells']}건</b>(금번 {info['sgov_tranche_sells_done_cycle']}/3회)",
        f"③ 💵 현금 대기(10%): 현재 <b>${info['cash_bucket_usd']:,.2f}</b> (1순위 완충/수혈 · 기수혈 ${info['cash_injected_to_soxl_usd']:,.0f} · 초과분 즉시 SGOV 전환)",
        "━━━━━━━━━━━━━━━━━━",
        "🏦 <b>[별도 실현수익금고 (일반 매매/리밸런싱 100% 사용 금지)]</b>",
        f"• 누적 격리수익: <b>+${info['vault_realized_profit_usd']:,.2f}</b> (0주졸업 {info['completed_barbell_cycles']}회 · 지층익절 실시간복원)",
        f"• 금고 가용잔액: <b>${info['vault_available_usd']:,.2f}</b> | 40%소진 긴급대여: <b>${info['vault_injected_to_soxl_usd']:,.2f}</b>",
        f"• 금일 격리수익: <b>+${info['daily_vaulted_profit_usd']:,.2f}</b> | 이번구간 격리: <b>+${info['cycle_vaulted_profit_usd']:,.2f}</b>",
        f"🕒 {now_est.strftime('%m-%d %H:%M:%S EST')}",
    ]
    return "\n".join(lines)


def run_barbell_plugin_tdd() -> bool:
    """
    부팅 시 바벨 60/30/10 시드 분할, SOXL 보유 중 모드 전환 3케이스 분류,
    SGOV 10% 내림 매도 수량 및 전 구간 실시간 지층 리밸런싱(Cash 10% 우선 -> 초과분 즉시 SGOV) 무결성을 검증한다.
    """
    sp = compute_barbell_seed_splits(10000.0)
    assert (
        abs(sp["soxl_seed_60_usd"] - 6000.0) < 1e-6
        and abs(sp["sgov_seed_30_usd"] - 3000.0) < 1e-6
        and abs(sp["cash_seed_10_usd"] - 1000.0) < 1e-6
        and abs(sp["soxl_portion_8pct_usd"] - 480.0) < 1e-6
        and abs(sp["soxl_sub_portion_4pct_usd"] - 240.0) < 1e-6
    ), f"바벨 60/30/10 분할 검증 실패: {sp}"

    # 케이스 A: SOXL $3,000(<=60%) 보유 중 전환 -> SGOV $3,000 매수예약 + 현금 $1,000 보유
    c_a = classify_barbell_transition_allocation(10000.0, 3000.0)
    assert (
        c_a["soxl_injected_reserve_usd"] == 0.0
        and abs(c_a["cash_bucket_usd"] - 1000.0) < 1e-6
        and abs(c_a["pending_sgov_buy_budget_usd"] - 3000.0) < 1e-6
        and c_a["barbell_seed_exhausted"] is False
    ), f"바벨 전환 케이스 A 검증 실패: {c_a}"

    # 케이스 B: SOXL $8,200(60%~100%) 보유 중 전환 -> 수혈 $2,200 인식 + 현금 $1,000 + SGOV $800
    c_b = classify_barbell_transition_allocation(10000.0, 8200.0)
    assert (
        abs(c_b["soxl_injected_reserve_usd"] - 2200.0) < 1e-6
        and abs(c_b["cash_bucket_usd"] - 1000.0) < 1e-6
        and abs(c_b["pending_sgov_buy_budget_usd"] - 800.0) < 1e-6
    ), f"바벨 전환 케이스 B 검증 실패: {c_b}"

    # 케이스 C: SOXL $10,000(100%) 보유 중 전환 -> 바벨 시드고갈 인식(현금 $0 · SGOV $0)
    c_c = classify_barbell_transition_allocation(10000.0, 10000.0)
    assert (
        abs(c_c["soxl_injected_reserve_usd"] - 4000.0) < 1e-6
        and c_c["cash_bucket_usd"] == 0.0
        and c_c["pending_sgov_buy_budget_usd"] == 0.0
        and c_c["barbell_seed_exhausted"] is True
    ), f"바벨 전환 케이스 C(100% SOXL 시드고갈 인식) 검증 실패: {c_c}"

    # SGOV 현금 10%($1,000) 상당 소수점 내림(floor) 정수 수량 검증 ($100.30 -> 9주)
    q_sell = compute_sgov_10pct_sell_qty(
        initial_seed_usd=10000.0, sgov_live_price=100.30, sgov_held_qty=29
    )
    assert q_sell == 9, f"SGOV 10% 내림 매도 수량 검증 실패: {q_sell}"

    # 실시간 리밸런싱 검증 1: SOXL $9,200 -> $7,000 (70% > 60% 구간) 부분 익절 시
    # 환수 $2,200 중 현금 10%($1,000) 우선 완충 후 초과분 $1,200 즉시 SGOV 매수예약 배정 검증!
    r_70 = compute_realtime_barbell_stratum_rebalance(
        initial_seed_usd=10000.0,
        rem_soxl_invested_usd=7000.0,
        prev_soxl_injected_usd=3200.0,
        prev_soxl_used_portions_cnt=7,
        prev_cash_bucket_usd=0.0,
        prev_pending_sgov_buy_usd=0.0,
        sgov_held_qty=8,
        sgov_invested_usd=800.0,
        sgov_ref_price=100.30,
        is_graduated_zero=False,
    )
    assert (
        abs(r_70["rem_soxl_injected_usd"] - 1000.0) < 1e-6
        and abs(r_70["repaid_from_soxl_usd"] - 2200.0) < 1e-6
        and abs(r_70["cash_bucket_usd"] - 1000.0) < 1e-6
        and abs(r_70["pending_sgov_buy_budget_usd"] - 1200.0) < 1e-6
    ), f"실시간 리밸런싱(>60% 구간 현금10% + 초과SGOV 배정) 검증 실패: {r_70}"

    # 실시간 리밸런싱 검증 2: SOXL $7,000 -> $5,500 (55% <= 60% 구간) 추가 익절 시
    # 잔여 수혈 $0 완납 및 기존 단주현금($96.70) 포함 전액 SGOV 30%($3,000) 한도 복원 검증!
    r_55 = compute_realtime_barbell_stratum_rebalance(
        initial_seed_usd=10000.0,
        rem_soxl_invested_usd=5500.0,
        prev_soxl_injected_usd=1000.0,
        prev_soxl_used_portions_cnt=3,
        prev_cash_bucket_usd=1096.70,
        prev_pending_sgov_buy_usd=0.0,
        sgov_held_qty=19,
        sgov_invested_usd=1903.30,
        sgov_ref_price=100.30,
        is_graduated_zero=False,
    )
    assert (
        r_55["rem_soxl_injected_usd"] == 0.0
        and r_55["rem_soxl_used_portions_cnt"] == 0
        and abs(r_55["cash_bucket_usd"] - 1000.0) < 1e-6
        and abs(r_55["pending_sgov_buy_budget_usd"] - 1096.70) < 1e-6
    ), f"실시간 리밸런싱(<=60% 구간 60/30/10 완전 복원) 검증 실패: {r_55}"

    # 실시간 리밸런싱 검증 3: 수익금고 대여($960) + 추가현금($540) 존재 시 0-A/0-B순위 원복 검증!
    r_v = compute_realtime_barbell_stratum_rebalance(
        initial_seed_usd=10000.0,
        rem_soxl_invested_usd=8800.0,
        prev_soxl_injected_usd=5500.0,
        prev_soxl_used_portions_cnt=12,
        prev_vault_injected_usd=960.0,
        prev_external_injected_usd=540.0,
        prev_cash_bucket_usd=0.0,
        prev_pending_sgov_buy_usd=0.0,
        sgov_held_qty=0,
        sgov_invested_usd=0.0,
        sgov_ref_price=100.30,
        is_graduated_zero=False,
    )
    assert (
        abs(r_v["repaid_to_vault_usd"] - 960.0) < 1e-6
        and r_v["next_vault_injected_usd"] == 0.0
        and abs(r_v["repaid_to_ext_usd"] - 540.0) < 1e-6
        and r_v["next_external_injected_usd"] == 0.0
        and abs(r_v["cash_bucket_usd"] - 1000.0) < 1e-6
        and abs(r_v["pending_sgov_buy_budget_usd"] - 200.0) < 1e-6
    ), f"실시간 리밸런싱(수익금고/외부현금 0순위 원복) 검증 실패: {r_v}"

    # 실시간 리밸런싱 검증 4: 수동 손절 0주 졸업(-$200) 시 유령현금 0% 항등식 검증!
    r_loss = compute_realtime_barbell_stratum_rebalance(
        initial_seed_usd=10000.0,
        rem_soxl_invested_usd=0.0,
        prev_soxl_injected_usd=0.0,
        prev_cash_bucket_usd=1000.0,
        prev_pending_sgov_buy_usd=0.0,
        sgov_held_qty=30,
        sgov_invested_usd=3000.0,
        sgov_ref_price=100.00,
        cycle_realized_net_usd=-200.0,
        is_graduated_zero=True,
    )
    assert (
        abs(r_loss["cash_bucket_usd"] - 800.0) < 1e-6
        and r_loss["pending_sgov_buy_budget_usd"] == 0.0
    ), f"실시간 리밸런싱(수동 손절 0주 유령현금 차단) 검증 실패: {r_loss}"

    return True
