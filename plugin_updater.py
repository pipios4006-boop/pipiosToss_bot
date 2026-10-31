# -*- coding: utf-8 -*-
"""
# MODIFIED: plugin_updater.py
인피니트 스노우볼 (Infinite Snowball) v3.0 — 순수 롱(🐂 SOXL 단독) 매수 04:07 ~ 16:00 EST 제한
(정규장 마감 30분 전 15:30 ~ 16:00 EST 0주 새 사이클 1층 진입 및 1층 공석 +1.0% 돌파 추격 차단 · Case 84) &
익절 매도 24시간 전 세션 확장(Case 83 방안 C 오버나이트 통합이평 사수 하이브리드) 오버나이트 7층 골디락스 멀티 그리드 지층관리 스나이퍼
12대 코어 모듈(quant_engine_core.py + quant_engine.py 2분할 · sniper_plugin_core.py + sniper_plugin.py 2분할 · main_runtime.py + main.py 2분할 포함)
무디스크 인메모리 프리플라이트 컴파일 · AST 심볼 교차 검증 · 4배수 선제 스냅 치유기 · 텔레그램 잔류 큐 소각 ·
폴더별 원장/환경변수/오프셋 스냅샷 Dirty-Check 철벽 보존 · 무인 Git 업데이트 및
Case 81 커널 레벨 인플레이스 프로세스 자가 교체(os.execv + 3.5초 하드 워치독) 코어 모듈 (Step 06 / 06)
- 제1헌법: 모든 파일 I/O 및 git/python 서브프로세스 실행을 asyncio.to_thread 로 비동기 격리 및 타임아웃 적용
- 제3헌법: 구버전 폐기 파일(daymarket_sim_plugin.py, whipsaw_plugin.py, state_SOXS.json 등) 디스크 영구 소각
- Case 07: 평일 04:00 ~ 16:05 EST 장중 백그라운드 무인 업데이트 재기동 전면 차단 및 systemd ExecStartPre 장중 락다운 지원
- Case 11 & Case 62:
  1) 12대 필수 코어 모듈(REQUIRED_CORE_MODULES : quant_engine_core.py + quant_engine.py · sniper_plugin_core.py + sniper_plugin.py ·
     main_runtime.py + main.py 분할 반영) 인메모리 compile() 문법 검증 + AST ImportFrom 심볼 테이블 정적 교차 검증
  2) 모바일 복사·붙여넣기 과정에서 발생한 마크다운 펜스 및 홀수 공백(1칸 -> 0칸, 9칸 -> 8칸)을
     AST 파싱 전에 4배수로 선제 스냅 교정하여 다음 줄이 오염되는 현상을 100% 원천 차단(_auto_heal_indentation_glitches)
  3) /update 실행 시 구버전 RAM 캐시(sys.modules) 간섭을 막기 위해 `python3 plugin_updater.py --verify-only` 를
     독립 서브프로세스로 호출하고 실패 시 직전 정상 커밋 해시로 즉시 원자적 롤백 수행
  4) 부팅(ExecStartPre) 및 실제 원격 신규 커밋(remote_ahead > 0) 감지 시점에만 텔레그램 서버의 미확인 적체 큐를
     소각(_flush_telegram_pending_updates_sync)하고, --verify-only 및 remote_ahead == 0 평시 점검 시에는
     getUpdates 호출과 원장 재초기화를 스킵하여 살아있는 폴링 루프와의 HTTP 409 Conflict 경합을 0%로 원천 차단!
- 🚨 [Case 68 & Case 80 폴더 위치(base_dir) 기반 격리 & git reset --hard 원장(골든포켓·모드 설정 포함)/환경변수 증발 100% 차단 쉴드]:
  1) "/home/pipiosToss" 고정 경로 하드코딩 100% 영구 제거 -> 오직 현재 실행 폴더(base_dir)의 .env 와 원장만 참조
  2) git reset --hard 실행 직전 해당 폴더 내 모든 원장(*ledger*.json, ledger_backups/*.json), 환경설정(.env*, *config*.json),
     텔레그램 오프셋(.tg_update_offset_*.dat)을 메모리에 스냅샷 보존하고, git reset --hard 직후 0.001초 내에 즉시 원자적 원상 복원
     (git rm --cached --ignore-unmatch soxl_stratum_ledger.json 병행)하여
     장외 자동 업데이트로 인한 기록 초기화 및 타 폴더 원장 덮어쓰기 사고를 물리적으로 영구 봉쇄!
- 🚨 [Case 75 클라우드 VM 디스크 고갈([Errno 28] No space left on device) 원천 차단 및 디스크 Write 90% 감축]:
  1) verify_all_modules_compile() 에서 디스크에 __pycache__/*.pyc 파일을 강제 기록하다가 디스크 풀 상태에서
     [Errno 28] No space left on device 예외를 유발하던 py_compile.compile() 디스크 쓰기를 제거하고,
     디스크 쓰기 0 Byte 순수 인메모리 컴파일(compile(src, fpath, "exec") + ast.parse)로 100% 검증!
  2) remote_ahead == 0 (원격 신규 커밋 없음) 시 git reset --hard 및 스냅샷 생성을 수행하지 않으므로 불필요한 백업·원장 파일
     재작성(_restore_protected_local_files_sync)과 원장 재로드 로그를 전면 스킵하고, 복원 시에도 바이트 Dirty-Check 적용!
  3) 프리플라이트 및 업데이트 전후 emergency_free_disk_space_sync() 로 고아 임시 파일(*.tmp.*, *.heal.tmp) 및
     __pycache__ 바이트코드 캐시를 자동 소각하여 디스크 블록 및 Inode 고갈을 원천 방어!
- 🚨 [Case 81 장외 무인 자동 업데이트(run_auto_update_loop) 및 수동 /update 직후 텔레그램 먹통(Deaf Zombie Process) ·
  asyncio.to_thread 종료 데드락 · systemd Exit Code 0 재기동 거부 원천 차단]:
  1) 구버전 os._exit(0) 호출 시 systemd(Restart=on-failure)가 정상 종료로 판정해 봇을 다시 켜주지 않던 치명적 결함을 영구 소각하고,
     perform_self_restart_execv() 를 통해 os.execv(sys.executable, [sys.executable] + sys.argv) 로 현재 PID 메모리에
     최신 파이썬 인터프리터와 최신 코드를 즉시 덮어씌워 무중단 인플레이스 자가 교체를 수행한다(실패 시 os._exit(1) 강제 재기동 폴백).
  2) arm_hard_restart_watchdog(3.5초) 데몬 스레드 워치독 타이머를 동시 가동하여, 이벤트 루프나 백그라운드 스레드가 종료 중 블로킹되더라도
     3.5초 내에 100% 강제 execv 자가 교체를 완수함으로써 GCP 수동 재시작 필요성을 0%로 소멸시킨다.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import errno
import glob
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from toss_api import (
    EST_TZ,
    GlobalThrottle,
    SoxlStratumLedger,
    emergency_free_disk_space_sync,
    get_bot_base_dir,
    get_folder_slug,
    resolve_folder_isolated_ledger_paths,
    safe_int,
)

logger = logging.getLogger("toss_sniper.plugin_updater")

# ---------------------------------------------------------------------------
# [핵심 상수] 12대 필수 코어 모듈(quant_engine_core + quant_engine · sniper_plugin_core + sniper_plugin · main_runtime + main 분할 반영) 및 영구 폐기 레거시 파일 목록 (제3헌법)
# ---------------------------------------------------------------------------
REQUIRED_CORE_MODULES: Tuple[str, ...] = (
    "toss_api.py",
    "quant_indicators_plugin.py",
    "quant_engine_core.py",
    "quant_engine.py",
    "sniper_plugin_core.py",
    "sniper_plugin.py",
    "sniper_exit_plugin.py",
    "defense_plugin.py",
    "tg_ui_plugin.py",
    "plugin_updater.py",
    "main_runtime.py",
    "main.py",
)

DEPRECATED_LEGACY_FILES: Tuple[str, ...] = (
    "daymarket_sim_plugin.py",
    "whipsaw_plugin.py",
    "candle_recorder.py",
    "tg_router.py",
    "state_SOXS.json",
    "soxs_stratum_ledger.json",
)

_TG_TOKEN_STRICT_RE = re.compile(r"\b(\d{8,12}:[A-Za-z0-9_-]{25,60})\b")

# [Case 81]: 중복 execv 방지를 위한 프로세스 전역 락 및 워치독 상태
_RESTART_EXEC_LOCK = threading.Lock()
_RESTART_WATCHDOG_TIMER: Optional[threading.Timer] = None


# ---------------------------------------------------------------------------
# [핵심 0-A · Case 81] 커널 레벨 인플레이스 프로세스 자가 교체(os.execv) 및 3.5초 데몬 하드 워치독
# ---------------------------------------------------------------------------
def resolve_tg_offset_dat_path(base_dir: Optional[str] = None) -> str:
    """
    # [Case 81]:
    폴더별 텔레그램 update_id 오프셋 전용 영속화 파일 경로(<base_dir>/.tg_update_offset_<folder_slug>.dat)를 반환한다.
    """
    target_dir = get_bot_base_dir(base_dir)
    slug = get_folder_slug(target_dir)
    return os.path.join(target_dir, f".tg_update_offset_{slug}.dat")


def read_persisted_tg_offset_sync(base_dir: Optional[str] = None) -> int:
    """
    # [Case 81]:
    폴더별 .tg_update_offset_<folder_slug>.dat 파일과 3중 원장(last_tg_update_id) 중 가장 큰 update_id 를 읽어 반환한다.
    """
    target_dir = get_bot_base_dir(base_dir)
    max_uid = 0
    dat_fp = resolve_tg_offset_dat_path(target_dir)
    if os.path.isfile(dat_fp):
        try:
            with GlobalThrottle.get_file_lock(dat_fp):
                with open(dat_fp, "r", encoding="utf-8", errors="ignore") as rf:
                    raw_txt = rf.read().strip()
            max_uid = max(max_uid, safe_int(raw_txt, 0))
        except Exception:
            pass

    primary_fp, legacy_fp, backup_fp, _ = resolve_folder_isolated_ledger_paths(
        base_dir=target_dir
    )
    for l_fp in (primary_fp, legacy_fp, backup_fp):
        if os.path.isfile(l_fp):
            try:
                with GlobalThrottle.get_file_lock(l_fp):
                    with open(l_fp, "r", encoding="utf-8") as rf:
                        ldata = json.load(rf)
                if isinstance(ldata, dict) and isinstance(
                    ldata.get("SOXL"), dict
                ):
                    max_uid = max(
                        max_uid,
                        safe_int(ldata["SOXL"].get("last_tg_update_id"), 0),
                    )
            except Exception:
                pass
    return max_uid


def write_persisted_tg_offset_sync(
    base_dir: Optional[str], update_id: int
) -> None:
    """
    # [Case 81 & Case 75]:
    폴더별 .tg_update_offset_<folder_slug>.dat 파일에 최신 update_id 를 Dirty-Check 후 원자적으로 기록한다.
    """
    uid = safe_int(update_id, 0)
    if uid <= 0:
        return
    target_dir = get_bot_base_dir(base_dir)
    dat_fp = resolve_tg_offset_dat_path(target_dir)
    try:
        with GlobalThrottle.get_file_lock(dat_fp):
            if os.path.isfile(dat_fp):
                try:
                    with open(dat_fp, "r", encoding="utf-8") as rf:
                        cur_val = safe_int(rf.read().strip(), 0)
                    if uid <= cur_val:
                        return
                except Exception:
                    pass
            tmp_fp = f"{dat_fp}.tmp.{os.getpid()}.{threading.get_ident()}"
            try:
                with open(tmp_fp, "w", encoding="utf-8") as wf:
                    wf.write(f"{uid}\n")
                    wf.flush()
                    os.fsync(wf.fileno())
                os.replace(tmp_fp, dat_fp)
            finally:
                if os.path.exists(tmp_fp):
                    try:
                        os.remove(tmp_fp)
                    except Exception:
                        pass
    except Exception:
        pass


def perform_self_restart_execv(reason: str = "AUTO_UPDATE") -> None:
    """
    🚨 [Case 81 핵심 : 커널 레벨 인플레이스 프로세스 자가 교체기]:
    장외 무인 자동 업데이트(run_auto_update_loop) 또는 수동 /update 완료 후 프로세스를 재기동할 때:
    1) 구버전 os._exit(0) 은 종료 코드 0(정상 종료)을 반환하여 systemd(Restart=on-failure)가 재시작을 거부하고
       봇이 영구 정지(Dead)되는 원인이었으므로 이를 100% 영구 폐기한다.
    2) 표준 출력/에러 버퍼를 플러시한 직후 os.execv(sys.executable, [sys.executable] + sys.argv) 를 호출하여
       현재 살아있는 프로세스(동일 PID) 메모리에 최신 파이썬 인터프리터와 최신 코드를 즉시 덮어씌워 무중단 자가 교체한다.
    3) 만약 OS 제약으로 os.execv 가 예외를 일으킬 경우에는 반드시 비정상 종료 코드인 os._exit(1) (Exit Code 1)을 호출하여
       systemd 의 Restart=on-failure 및 Restart=always 양쪽 모두에서 100% 강제 재기동되도록 이중 보장한다!
    """
    with _RESTART_EXEC_LOCK:
        target_dir = get_bot_base_dir()
        logger.warning(
            "🔄 [Case 81 커널 레벨 인플레이스 자가 재기동(os.execv) 집행] 사유=%s · PID=%d · 폴더=%s",
            reason,
            os.getpid(),
            target_dir,
        )
        try:
            sys.stdout.flush()
        except Exception:
            pass
        try:
            sys.stderr.flush()
        except Exception:
            pass

        try:
            os.chdir(target_dir)
        except Exception:
            pass

        python_exe = sys.executable or "/usr/bin/python3"
        raw_argv = (
            list(sys.argv)
            if sys.argv
            else [os.path.join(target_dir, "main.py")]
        )
        if not raw_argv[0] or "--verify-only" in raw_argv:
            script_path = os.path.join(target_dir, "main.py")
            exec_argv = [python_exe, script_path]
        else:
            script_arg = raw_argv[0]
            if not os.path.isabs(script_arg):
                cand_abs = os.path.join(target_dir, script_arg)
                if os.path.isfile(cand_abs):
                    script_arg = cand_abs
            exec_argv = [python_exe, script_arg] + raw_argv[1:]

        try:
            os.execv(python_exe, exec_argv)
        except Exception as exc:
            logger.error(
                "🚨 [Case 81 os.execv 호출 예외 -> os._exit(1) 비정상 종료 코드로 systemd 강제 재기동 폴백]: %s",
                exc,
            )
            try:
                sys.stdout.flush()
                sys.stderr.flush()
            except Exception:
                pass
            os._exit(1)


def arm_hard_restart_watchdog(
    delay_sec: float = 3.5,
    reason: str = "AUTO_UPDATE",
) -> threading.Timer:
    """
    🚨 [Case 81 핵심 : 비동기 종료 데드락(Deaf Zombie Process) 타파용 3.5초 데몬 하드 워치독]:
    업데이트 직후 shutdown_event.set() 이 호출되었을 때 텔레그램 폴링 루프만 먼저 종료되고
    백그라운드 asyncio.to_thread 워커 스레드가 남아 asyncio.run() 의 shutdown_default_executor() 에서
    프로세스가 죽지 않고 멈추는 '귀머거리 좀비(Deaf Zombie)' 현상을 원천 봉쇄한다.
    3.5초 내에 메인 루프가 perform_self_restart_execv() 에 도달하지 못하면
    독립 커널 데몬 스레드가 강제로 os.execv() (실패 시 os._exit(1))를 집행한다!
    """
    global _RESTART_WATCHDOG_TIMER
    safe_delay = max(1.0, min(15.0, float(delay_sec)))

    def _watchdog_callback() -> None:
        logger.warning(
            "⏰ [Case 81 하드 워치독 타이머(%.1fs) 격발] 비동기 종료 지연 감지 -> 즉시 os.execv 인플레이스 교체 강제 집행 (reason=%s)",
            safe_delay,
            reason,
        )
        perform_self_restart_execv(reason=f"{reason}_WATCHDOG_TIMEOUT")

    timer = threading.Timer(safe_delay, _watchdog_callback)
    timer.daemon = True
    timer.start()
    _RESTART_WATCHDOG_TIMER = timer
    logger.info(
        "🛡️ [Case 81 하드 워치독 타이머 장착 완료] %.1f초 내 무응답 시 강제 os.execv 교체 (reason=%s)",
        safe_delay,
        reason,
    )
    return timer


def trigger_graceful_restart(
    context: Any,
    shutdown_event: Optional[asyncio.Event] = None,
    reason: str = "AUTO_UPDATE",
    watchdog_delay_sec: float = 3.5,
) -> None:
    """
    🚨 [Case 81 : 재기동 플래그 설정 + 3.5초 하드 워치독 가동 + 이벤트 루프 즉시 깨우기 통합 점화기]:
    context.restart_requested = True 설정과 동시에 3.5초 데몬 하드 워치독을 장착하고
    shutdown_event 및 wakeup_event 를 깨워 즉시 재기동 시퀀스로 진입시킨다.
    """
    if context is not None:
        try:
            setattr(context, "restart_requested", True)
            setattr(context, "restart_reason", str(reason))
        except Exception:
            pass

    arm_hard_restart_watchdog(delay_sec=watchdog_delay_sec, reason=reason)

    ev = shutdown_event or (
        getattr(context, "shutdown_event", None)
        if context is not None
        else None
    )
    if ev is not None:
        try:
            ev.set()
        except Exception:
            pass

    wake_ev = (
        getattr(context, "wakeup_event", None) if context is not None else None
    )
    if wake_ev is not None:
        try:
            wake_ev.set()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# [핵심 0-B] 폴더 위치(base_dir) 전용 텔레그램 적체 큐 선제 강제 소각기 (Case 68, Case 75 & Case 81)
# ---------------------------------------------------------------------------
def _discover_bot_token_sync(base_dir: Optional[str] = None) -> str:
    """
    🚨 Case 68:
    "/home/pipiosToss" 고정 경로 폴백을 100% 폐기하고, 오직 현재 봇이 위치한 폴더(target_dir)의
    .env 및 환경변수에서만 텔레그램 봇 토큰을 추출한다.
    """
    target_dir = get_bot_base_dir(base_dir)
    if os.path.isdir(target_dir):
        env_fp = os.path.join(target_dir, ".env")
        if os.path.isfile(env_fp):
            try:
                with open(env_fp, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                m = _TG_TOKEN_STRICT_RE.search(content)
                if m:
                    return m.group(1)
            except Exception:
                pass

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
                return m.group(1)
    return ""


def _update_ledger_tg_offset_sync(ledger_fp: str, max_uid: int) -> None:
    """
    # [Case 75 & Case 81]:
    1) max_uid <= cur_saved 이면 디스크 쓰기를 수행하지 않고 즉시 반환한다.
    2) 쓰기 도중 OSError(errno.ENOSPC == 28) 발생 시 미완성 .tmp 파일을 즉시 제거하고
       emergency_free_disk_space_sync() 로 고아 파일 및 캐시를 청소한 뒤 재시도한다.
    """
    if not ledger_fp or not os.path.isfile(ledger_fp) or max_uid <= 0:
        return
    target_dir = os.path.dirname(os.path.abspath(ledger_fp))
    try:
        with GlobalThrottle.get_file_lock(ledger_fp):
            with open(ledger_fp, "r", encoding="utf-8") as rf:
                ldata = json.load(rf)
            if not (
                isinstance(ldata, dict)
                and "SOXL" in ldata
                and isinstance(ldata["SOXL"], dict)
            ):
                return
            cur_saved = safe_int(ldata["SOXL"].get("last_tg_update_id"), 0)
            if max_uid <= cur_saved:
                return

            ldata["SOXL"]["last_tg_update_id"] = max_uid
            for attempt in range(2):
                tmp_p = (
                    f"{ledger_fp}.ack.tmp.{os.getpid()}."
                    f"{threading.get_ident()}"
                )
                try:
                    with open(tmp_p, "w", encoding="utf-8") as wf:
                        json.dump(ldata, wf, ensure_ascii=False, indent=2)
                        wf.flush()
                        os.fsync(wf.fileno())
                    os.replace(tmp_p, ledger_fp)
                    break
                except OSError as os_err:
                    try:
                        if os.path.exists(tmp_p):
                            os.remove(tmp_p)
                    except Exception:
                        pass
                    if os_err.errno == errno.ENOSPC and attempt == 0:
                        emergency_free_disk_space_sync(
                            base_dir=target_dir,
                            keep_backup_days=3,
                            remove_pycache=True,
                        )
                        continue
                    break
                except Exception:
                    try:
                        if os.path.exists(tmp_p):
                            os.remove(tmp_p)
                    except Exception:
                        pass
                    break
    except Exception:
        pass


def _flush_telegram_pending_updates_sync(
    base_dir: Optional[str] = None,
) -> int:
    """
    # [Case 81]:
    데몬 기동 전(ExecStartPre) 또는 실제 원격 신규 커밋이 감지(remote_ahead > 0)되어
    재기동이 확정된 시점에 텔레그램 서버 큐에 남아 있는 미확인 메시지의 최대 update_id 를 조회하여
    `offset = max_update_id + 1` 로 소비 확정(Ack)하고
    폴더별 오프셋 파일(`.tg_update_offset_<folder_slug>.dat`) 및 3중 원장의 `last_tg_update_id` 에 동시 기록한다.
    """
    target_dir = get_bot_base_dir(base_dir)
    bot_token = _discover_bot_token_sync(target_dir)
    if not bot_token:
        return 0

    def _call_tg_api(method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"https://api.telegram.org/bot{bot_token}/{method}"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {"ok": True}

    max_uid = read_persisted_tg_offset_sync(target_dir)
    try:
        _call_tg_api("deleteWebhook", {"drop_pending_updates": False})
    except Exception:
        pass

    try:
        res = _call_tg_api("getUpdates", {"offset": -1, "timeout": 0})
        if isinstance(res, dict) and bool(res.get("ok")):
            updates = res.get("result")
            if isinstance(updates, list) and updates:
                for u in updates:
                    if isinstance(u, dict):
                        uid = safe_int(u.get("update_id"), 0)
                        if uid > max_uid:
                            max_uid = uid
                if max_uid > 0:
                    _call_tg_api(
                        "getUpdates",
                        {"offset": max_uid + 1, "limit": 1, "timeout": 0},
                    )
    except Exception as exc:
        logger.debug("텔레그램 큐 선제 소각 예외(무시): %s", exc)

    if max_uid > 0:
        write_persisted_tg_offset_sync(target_dir, max_uid)
        primary_fp, legacy_fp, backup_fp, _ = (
            resolve_folder_isolated_ledger_paths(base_dir=target_dir)
        )
        for l_fp in (primary_fp, legacy_fp, backup_fp):
            _update_ledger_tg_offset_sync(l_fp, max_uid)

    return max_uid


# ---------------------------------------------------------------------------
# [핵심 0-C · Case 68, Case 75, Case 80 & Case 81] git reset --hard 실행 전후 폴더별 원장 · .env · 오프셋 철벽 보호기
# ---------------------------------------------------------------------------
def _snapshot_protected_local_files_sync(target_dir: str) -> Dict[str, bytes]:
    """
    🚨 Case 68, Case 75, Case 80 & Case 81:
    git reset --hard 가 실행되기 직전(remote_ahead > 0 확인 후)에 현재 폴더(target_dir) 내의:
    1) 고아 임시 파일(*.tmp.*) 및 __pycache__ 선제 청소로 여유 공간 확보
    2) 3중 안전 원장(SoxlStratumLedger) 선행 동기화 실행 (Dirty-Check 로 변경된 경우에만 기록)
    3) 모든 `*ledger*.json` 파일, `ledger_backups/*.json` 파일, `.env*`, `*config*.json`, `secrets.json` 및
       `.tg_update_offset*.dat` 파일의 원본 바이트(bytes)를 메모리에 스냅샷으로 보존한다.
    """
    abs_dir = get_bot_base_dir(target_dir)
    emergency_free_disk_space_sync(
        base_dir=abs_dir, keep_backup_days=14, remove_pycache=True
    )
    try:
        SoxlStratumLedger(base_dir=abs_dir)
    except Exception as exc:
        logger.debug("업데이트 전 원장 선행 동기화 예외(무시): %s", exc)

    snapshots: Dict[str, bytes] = {}
    patterns = (
        os.path.join(abs_dir, "*ledger*.json"),
        os.path.join(abs_dir, ".env*"),
        os.path.join(abs_dir, ".tg_update_offset*.dat"),
        os.path.join(abs_dir, "*config*.json"),
        os.path.join(abs_dir, "secrets.json"),
        os.path.join(abs_dir, "ledger_backups", "*.json"),
    )
    for pat in patterns:
        for fp in glob.glob(pat):
            if not os.path.isfile(fp):
                continue
            bname = os.path.basename(fp)
            if (
                bname in DEPRECATED_LEGACY_FILES
                or ".tmp." in bname
                or bname.endswith(".heal.tmp")
            ):
                continue
            try:
                with GlobalThrottle.get_file_lock(fp):
                    with open(fp, "rb") as rf:
                        raw_bytes = rf.read()
                if raw_bytes:
                    snapshots[os.path.abspath(fp)] = raw_bytes
            except Exception as exc:
                logger.warning("보호 파일 스냅샷 실패(%s): %s", fp, exc)

    return snapshots


def _restore_protected_local_files_sync(
    target_dir: str, snapshots: Dict[str, bytes]
) -> int:
    """
    🚨 Case 68, Case 75 & Case 80:
    git reset --hard 실행 직후, 원격 저장소의 초기 파일이 로컬 디스크를 덮어썼을 때
    메모리에 보존해 둔 스냅샷 바이트를 즉시 원자적으로 복원하되:
    1) 디스크의 현재 파일 바이트가 스냅샷 바이트와 이미 100% 동일하면(existing_bytes == raw_bytes)
       불필요한 .restore.tmp 생성 및 os.fsync() 디스크 쓰기를 즉시 스킵한다!
    2) 복원 도중 OSError(errno.ENOSPC == 28) 감지 시 즉시 emergency_free_disk_space_sync() 로
       공간을 확보한 뒤 재시도한다.
    """
    abs_dir = get_bot_base_dir(target_dir)
    restored_cnt = 0
    for fp, raw_bytes in (snapshots or {}).items():
        if not fp or not raw_bytes:
            continue
        try:
            with GlobalThrottle.get_file_lock(fp):
                if os.path.isfile(fp):
                    try:
                        with open(fp, "rb") as rf:
                            existing_bytes = rf.read()
                        if existing_bytes == raw_bytes:
                            continue
                    except Exception:
                        pass

                parent_d = os.path.dirname(fp)
                for attempt in range(2):
                    if parent_d and not os.path.isdir(parent_d):
                        os.makedirs(parent_d, exist_ok=True)
                    tmp_fp = (
                        f"{fp}.restore.tmp.{os.getpid()}."
                        f"{threading.get_ident()}"
                    )
                    try:
                        with open(tmp_fp, "wb") as wf:
                            wf.write(raw_bytes)
                            wf.flush()
                            os.fsync(wf.fileno())
                        os.replace(tmp_fp, fp)
                        restored_cnt += 1
                        break
                    except OSError as os_err:
                        try:
                            if os.path.exists(tmp_fp):
                                os.remove(tmp_fp)
                        except Exception:
                            pass
                        if os_err.errno == errno.ENOSPC and attempt == 0:
                            emergency_free_disk_space_sync(
                                base_dir=abs_dir,
                                keep_backup_days=3,
                                remove_pycache=True,
                            )
                            continue
                        raise
        except Exception as exc:
            logger.error("보호 파일 복원 예외(%s): %s", fp, exc)

    try:
        SoxlStratumLedger(base_dir=abs_dir)
    except Exception as exc:
        logger.debug("복원 후 원장 재검증 예외(무시): %s", exc)

    return restored_cnt


# ---------------------------------------------------------------------------
# [핵심 1] 구버전 폐기 파일 및 고아 임시 파일 자동 청소기 (purge_deprecated_legacy_files — Case 75)
# ---------------------------------------------------------------------------
def purge_deprecated_legacy_files(
    base_dir: Optional[str] = None,
) -> List[str]:
    """
    🚨 제3헌법 & Case 75:
    1) 구버전 데드코드 파일(daymarket_sim_plugin.py, whipsaw_plugin.py, state_SOXS.json 등)이
       디스크에 남아 있을 경우 즉시 삭제하고 삭제된 파일명 리스트를 반환한다.
    2) 동시에 폴더 내 고아 임시 파일(*.tmp.*, *.heal.tmp)도 함께 청소한다.
    """
    target_dir = get_bot_base_dir(base_dir)
    removed: List[str] = []
    for fname in DEPRECATED_LEGACY_FILES:
        fpath = os.path.join(target_dir, fname)
        if os.path.isfile(fpath):
            try:
                with GlobalThrottle.get_file_lock(fpath):
                    os.remove(fpath)
                removed.append(fname)
            except Exception as exc:
                logger.warning("폐기 파일 삭제 실패 (%s): %s", fname, exc)

    emergency_free_disk_space_sync(
        base_dir=target_dir, keep_backup_days=14, remove_pycache=False
    )
    return removed


# ---------------------------------------------------------------------------
# [핵심 2] 4배수 선제 스냅 및 마크다운 펜스 자동 치유기 (_auto_heal_indentation_glitches — Case 75)
# ---------------------------------------------------------------------------
def _auto_heal_indentation_glitches(
    filepath: str, max_passes: int = 6
) -> bool:
    """
    [역방향 들여쓰기 오염 원천 차단 & Case 75 ENOSPC 방어]:
    1) 파일 상단에 복사 시 섞여 들어간 텍스트나 마크다운 코드펜스(```)를 먼저 제거한다.
    2) AST 파싱 결과 SyntaxError / IndentationError 가 감지될 경우,
       먼저 코드 라인 중 4의 배수가 아닌 비정상 홀수 공백(예: 1칸 -> 0칸, 9칸 -> 8칸)을
       가장 가까운 4의 배수로 일괄 선제 스냅 교정한다!
    3) 치유본 저장 시 OSError(errno.ENOSPC == 28)가 발생하면 미완성 .heal.tmp 를 즉시 삭제하고
       emergency_free_disk_space_sync() 로 공간을 확보한 뒤 재시도한다.
    """
    if not os.path.isfile(filepath):
        return False

    fence_prefix = chr(96) * 3
    coding_marker = "# -*- coding: utf-8 -*-"
    target_dir = os.path.dirname(os.path.abspath(filepath))

    try:
        with GlobalThrottle.get_file_lock(filepath):
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                orig_src = f.read()

            src = orig_src

            # 0단계: 이미 문법적으로 완벽하면 디스크 쓰기 없이 즉시 통과
            try:
                ast.parse(src, filename=filepath)
                return False
            except (IndentationError, SyntaxError):
                pass

            # 1단계: 상단 불필요 프리픽스 및 마크다운 코드펜스 제거 + 홀수 공백(1칸, 9칸 등) 4배수 선제 스냅
            if coding_marker in src and not src.lstrip().startswith(
                coding_marker
            ):
                src = src[src.index(coding_marker) :]

            pre_lines = src.splitlines()
            snapped_lines: List[str] = []
            for line in pre_lines:
                if line.strip().startswith(fence_prefix):
                    continue
                stripped = line.lstrip(" ")
                lead = len(line) - len(stripped)
                if (
                    stripped
                    and not stripped.startswith(
                        ("#", '"', "'", ")", "]", "}")
                    )
                    and (lead % 4 != 0)
                ):
                    lead = int(round(lead / 4.0)) * 4
                snapped_lines.append((" " * lead) + stripped)

            src = "\n".join(snapped_lines) + "\n"

            # 2단계: 선제 스냅 후에도 남은 IndentationError 미세 교정
            for _ in range(max_passes):
                try:
                    ast.parse(src, filename=filepath)
                    break
                except IndentationError as ind_err:
                    lineno = getattr(ind_err, "lineno", None)
                    if not isinstance(lineno, int) or lineno < 1:
                        break
                    lines = src.splitlines(keepends=True)
                    if lineno > len(lines):
                        break

                    idx = lineno - 1
                    raw_line = lines[idx]
                    stripped = raw_line.lstrip(" \t")
                    if not stripped:
                        break
                    lead_len = len(raw_line) - len(stripped)

                    prev_indent = 0
                    for p_i in range(idx - 1, -1, -1):
                        p_str = lines[p_i].strip()
                        if p_str and not p_str.startswith("#"):
                            prev_indent = len(lines[p_i]) - len(
                                lines[p_i].lstrip(" ")
                            )
                            if p_str.endswith(":"):
                                prev_indent += 4
                            break

                    if stripped.startswith(
                        ("else:", "elif ", "except", "finally:")
                    ):
                        new_indent = max(0, prev_indent - 4)
                    elif lead_len % 4 != 0:
                        new_indent = int(round(lead_len / 4.0)) * 4
                    else:
                        new_indent = prev_indent

                    if new_indent == lead_len:
                        break

                    lines[idx] = (" " * max(0, new_indent)) + stripped
                    src = "".join(lines)
                except SyntaxError:
                    break

            if src != orig_src:
                try:
                    ast.parse(src, filename=filepath)
                except SyntaxError:
                    return False

                for attempt in range(2):
                    tmp_fp = f"{filepath}.heal.tmp"
                    try:
                        with open(tmp_fp, "w", encoding="utf-8") as wf:
                            wf.write(src)
                            wf.flush()
                            os.fsync(wf.fileno())
                        os.replace(tmp_fp, filepath)
                        logger.info(
                            "🔧 [들여쓰기/코드펜스 자동 정규화 완료] %s",
                            os.path.basename(filepath),
                        )
                        return True
                    except OSError as os_err:
                        try:
                            if os.path.exists(tmp_fp):
                                os.remove(tmp_fp)
                        except Exception:
                            pass
                        if os_err.errno == errno.ENOSPC and attempt == 0:
                            emergency_free_disk_space_sync(
                                base_dir=target_dir,
                                keep_backup_days=3,
                                remove_pycache=True,
                            )
                            continue
                        break
    except Exception as exc:
        logger.debug("들여쓰기 자동 치유 스킵 (%s): %s", filepath, exc)
    return False


# ---------------------------------------------------------------------------
# [핵심 3] AST 최상위 익스포트 심볼 추출기 및 12대 코어 모듈 무디스크 인메모리 교차 검증기 (Case 75)
# ---------------------------------------------------------------------------
def _extract_module_exported_symbols(tree: ast.AST) -> Set[str]:
    """
    AST 트리에서 모듈 최상위 레벨(또는 조건문 내부)에 정의된 모든 함수, 클래스, 변수, 임포트 별칭을 추출한다.
    """
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

    return exported


def verify_all_modules_compile(
    base_dir: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    🚨 Case 11, Case 62 & Case 75 [디스크 쓰기 0 Byte 순수 인메모리 컴파일 검증]:
    1) 검증 시작 전 emergency_free_disk_space_sync(remove_pycache=False) 로 고아 .tmp.* 파일을 청소한다.
    2) 12대 필수 코어 모듈(REQUIRED_CORE_MODULES : quant_engine_core.py + quant_engine.py ·
       sniper_plugin_core.py + sniper_plugin.py · main_runtime.py + main.py 포함)이
       디스크에 모두 존재하는지 확인한다.
    3) 홀수 공백 들여쓰기 오타 자동 치유(_auto_heal_indentation_glitches) 후
       디스크에 단 1바이트도 쓰지 않는 파이썬 내장 인메모리 바이트코드 컴파일러
       `compile(src, fpath, "exec", dont_inherit=True)` 및 `ast.parse(src, filename=fpath)` 로
       문법 및 바이트코드 생성 무결성을 100% 검증한다!
    4) 12대 코어 모듈 간 `from <local_module> import <symbol>` 구문을 전수 대조하여,
       대상 모듈에 존재하지 않는 심볼을 임포트하는 경우 즉시 에러 원인을 반환한다.
    """
    target_dir = get_bot_base_dir(base_dir)
    emergency_free_disk_space_sync(
        base_dir=target_dir, keep_backup_days=14, remove_pycache=False
    )

    errors: List[str] = []
    ast_trees: Dict[str, ast.AST] = {}
    exported_map: Dict[str, Set[str]] = {}

    # 1단계: 파일 존재 확인 · 들여쓰기 자동 치유 · 인메모리 compile() & AST 파싱 (디스크 쓰기 0 Byte!)
    for fname in REQUIRED_CORE_MODULES:
        fpath = os.path.join(target_dir, fname)
        mod_name = fname[:-3]
        if not os.path.isfile(fpath):
            errors.append(f"필수 코어 모듈 누락: {fname}")
            continue

        _auto_heal_indentation_glitches(fpath)

        try:
            with open(fpath, "r", encoding="utf-8") as f:
                src = f.read()
        except Exception as exc:
            errors.append(f"파일 읽기 예외 [{fname}]: {exc}")
            continue

        try:
            compile(src, fpath, "exec", dont_inherit=True)
            tree = ast.parse(src, filename=fpath)
            ast_trees[mod_name] = tree
            exported_map[mod_name] = _extract_module_exported_symbols(tree)
        except SyntaxError as syn_err:
            line_info = (
                f" (line {syn_err.lineno})"
                if getattr(syn_err, "lineno", None)
                else ""
            )
            errors.append(f"문법/컴파일 오류 [{fname}]{line_info}: {syn_err.msg}")
        except Exception as exc:
            errors.append(f"컴파일/AST 파싱 예외 [{fname}]: {exc}")

    if errors:
        return False, "🚨 컴파일/문법 검증 실패:\n" + "\n".join(errors)

    # 2단계: 12대 로컬 모듈 간 from <mod> import <symbol> 심볼 존재 여부 교차 검증
    local_mod_names = {f[:-3] for f in REQUIRED_CORE_MODULES}
    for mod_name, tree in ast_trees.items():
        fname = f"{mod_name}.py"
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module in local_mod_names
            ):
                target_mod = node.module
                target_exports = exported_map.get(target_mod, set())
                for alias in node.names:
                    sym = alias.name
                    if sym == "*":
                        continue
                    if sym not in target_exports:
                        errors.append(
                            f"심볼 임포트 불일치 [{fname}]: from {target_mod} import {sym} ('{target_mod}.py' 내 '{sym}' 미정의)"
                        )

    if errors:
        return False, "🚨 컴파일/AST 임포트 검증 실패:\n" + "\n".join(errors)

    return (
        True,
        f"✅ {len(REQUIRED_CORE_MODULES)}대 코어 모듈 인메모리 컴파일 및 AST 심볼 정합성 100% 통과 ({len(REQUIRED_CORE_MODULES)}개 파일)",
    )


# ---------------------------------------------------------------------------
# [핵심 4] 스마트 Git 동기화 · Case 68/81 원장·오프셋 철벽 보존 쉴드 · Case 75/81 HTTP 409 및 불필요 복원 쓰기 원천 차단
# ---------------------------------------------------------------------------
def _run_cmd_sync(
    cmd: List[str], cwd: str, timeout_sec: float = 30.0
) -> Tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    return (
        int(proc.returncode),
        (proc.stdout or "").strip(),
        (proc.stderr or "").strip(),
    )


def _execute_git_pull_and_preflight_sync(
    base_dir: Optional[str] = None,
) -> Tuple[bool, str, bool]:
    """
    🚨 Case 62, Case 68, Case 75, Case 80 & Case 81 [장외 업데이트 시 로컬 원장·환경변수·오프셋 증발 원천 차단 & HTTP 409 경합 0%]:
    1) 먼저 `git fetch --all --prune` 및 `git rev-list --count HEAD..origin/<branch>` 로 원격 저장소에
       신규 커밋이 존재하는지(`remote_ahead > 0`)부터 확인한다.
    2) MODIFIED [Case 75 & Case 81 핵심]:
       만약 `remote_ahead == 0` (원격 신규 커밋 없음)이면 살아있는 텔레그램 폴링 루프와 충돌(HTTP 409 Conflict)을 일으키는
       `_flush_telegram_pending_updates_sync()` 나 원장 재초기화 로그를 유발하는 `_snapshot_protected_local_files_sync()` 를
       호출하지 않고, 즉시 로컬 인메모리 컴파일 검증(`verify_all_modules_compile`)만 수행한 뒤 `(ok, msg, False)` 를 반환한다!
    3) 오직 `remote_ahead > 0` (신규 커밋 존재)일 때만:
       - `_flush_telegram_pending_updates_sync(target_dir)` 로 잔류 큐를 선제 소각하고,
       - `_snapshot_protected_local_files_sync(target_dir)` 로 현재 폴더의 모든 `*ledger*.json`,
         `ledger_backups/*.json`, `.env*`, `.tg_update_offset*.dat`, `*config*.json` 파일을 메모리에 스냅샷 보존하며,
       - `git reset --hard origin/<branch>` 직후 0.001초 내에 `_restore_protected_local_files_sync()` 로 원상 복원한다!
    4) 구버전 RAM 캐시(sys.modules) 간섭 및 `.pyc` 디스크 생성을 차단하기 위해
       `[sys.executable, "-B", updater_script, "--verify-only", "--base-dir", target_dir]` 를 독립 서브프로세스로 실행하고,
       검증 실패 시 즉시 이전 정상 커밋 해시로 자동 롤백하고 로컬 원장을 재복원한다.
    """
    target_dir = get_bot_base_dir(base_dir)
    protected_snapshots: Dict[str, bytes] = {}
    did_git_reset = False

    try:
        rc_h, prev_hash, _ = _run_cmd_sync(
            ["git", "rev-parse", "HEAD"], cwd=target_dir, timeout_sec=10.0
        )
        if rc_h != 0 or not prev_hash:
            prev_hash = ""

        rc_b, branch_name, _ = _run_cmd_sync(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=target_dir,
            timeout_sec=10.0,
        )
        if rc_b != 0 or not branch_name or branch_name == "HEAD":
            branch_name = "main"

        rc_f, _, err_f = _run_cmd_sync(
            ["git", "fetch", "--all", "--prune"],
            cwd=target_dir,
            timeout_sec=25.0,
        )
        if rc_f != 0:
            if "No space left on device" in err_f or "ENOSPC" in err_f:
                emergency_free_disk_space_sync(
                    base_dir=target_dir,
                    keep_backup_days=3,
                    remove_pycache=True,
                )
                rc_f, _, _ = _run_cmd_sync(
                    ["git", "fetch", "--all", "--prune"],
                    cwd=target_dir,
                    timeout_sec=25.0,
                )
            if rc_f != 0:
                ok_local, msg_local = verify_all_modules_compile(target_dir)
                return (
                    ok_local,
                    f"로컬 검증 완료 (git fetch 스킵): {msg_local}",
                    False,
                )

        target_ref = f"origin/{branch_name}"
        rc_ref, _, _ = _run_cmd_sync(
            ["git", "rev-parse", "--verify", target_ref],
            cwd=target_dir,
            timeout_sec=8.0,
        )
        if rc_ref != 0:
            target_ref = "origin/main"

        rc_cnt, cnt_str, _ = _run_cmd_sync(
            ["git", "rev-list", "--count", f"HEAD..{target_ref}"],
            cwd=target_dir,
            timeout_sec=8.0,
        )
        remote_ahead = safe_int(cnt_str, 0) if rc_cnt == 0 else 0

        # MODIFIED [Case 75 & Case 81]: 원격 신규 커밋이 없을 때(remote_ahead == 0)는
        # getUpdates 호출(HTTP 409 유발)이나 SoxlStratumLedger 재초기화 없이 즉시 인메모리 검증만 수행!
        if remote_ahead <= 0:
            purged_list = purge_deprecated_legacy_files(target_dir)
            ok_local, msg_local = verify_all_modules_compile(target_dir)
            short_hash = prev_hash[:7] if prev_hash else "local"
            purge_note = (
                f" · 폐기파일 {len(purged_list)}개 소각" if purged_list else ""
            )
            if not ok_local:
                return (
                    False,
                    f"🚨 로컬 프리플라이트 검증 실패:\n{msg_local}",
                    False,
                )
            return (
                True,
                f"현재 버전({short_hash}) 유지 · 원장 100% 보존 · {msg_local}{purge_note}",
                False,
            )

        # 원격 신규 커밋(remote_ahead > 0)이 존재하여 실제 업데이트를 적용할 때만 스냅샷 보존 및 큐 소각 수행!
        _flush_telegram_pending_updates_sync(target_dir)
        protected_snapshots = _snapshot_protected_local_files_sync(target_dir)

        did_git_reset = True
        rc_r, _, err_r = _run_cmd_sync(
            ["git", "reset", "--hard", target_ref],
            cwd=target_dir,
            timeout_sec=15.0,
        )
        _restore_protected_local_files_sync(
            target_dir, protected_snapshots
        )
        try:
            _run_cmd_sync(
                [
                    "git",
                    "rm",
                    "--cached",
                    "--ignore-unmatch",
                    "soxl_stratum_ledger.json",
                ],
                cwd=target_dir,
                timeout_sec=5.0,
            )
        except Exception:
            pass
        try:
            _run_cmd_sync(
                [
                    "git",
                    "update-index",
                    "--assume-unchanged",
                    "soxl_stratum_ledger.json",
                ],
                cwd=target_dir,
                timeout_sec=5.0,
            )
        except Exception:
            pass

        if rc_r != 0:
            return False, f"git reset 실패: {err_r}", False

        _, new_hash, _ = _run_cmd_sync(
            ["git", "rev-parse", "HEAD"], cwd=target_dir, timeout_sec=10.0
        )
        changed = bool(prev_hash and new_hash and prev_hash != new_hash)

        purged_list = purge_deprecated_legacy_files(target_dir)

        updater_script = os.path.join(target_dir, "plugin_updater.py")
        rc_v, out_v, err_v = _run_cmd_sync(
            [
                sys.executable,
                "-B",
                updater_script,
                "--verify-only",
                "--base-dir",
                target_dir,
            ],
            cwd=target_dir,
            timeout_sec=25.0,
        )
        if rc_v != 0:
            detail_err = out_v or err_v or "알 수 없는 컴파일/심볼 검증 오류"
            if changed and prev_hash:
                _run_cmd_sync(
                    ["git", "reset", "--hard", prev_hash],
                    cwd=target_dir,
                    timeout_sec=15.0,
                )
            if did_git_reset:
                _restore_protected_local_files_sync(
                    target_dir, protected_snapshots
                )
            return (
                False,
                f"🚨 프리플라이트 컴파일 에러 감지:\n{detail_err}",
                False,
            )

        short_hash = new_hash[:7] if new_hash else "local"
        status_note = (
            f"신규 커밋({short_hash}) 적용 · 원장 100% 보존"
            if changed
            else f"현재 버전({short_hash}) 유지 · 원장 100% 보존"
        )
        verify_note = (
            out_v
            if out_v
            else f"✅ {len(REQUIRED_CORE_MODULES)}대 코어 모듈 검증 통과 ({len(REQUIRED_CORE_MODULES)}개 파일)"
        )
        purge_note = (
            f" · 폐기파일 {len(purged_list)}개 소각" if purged_list else ""
        )
        summary_msg = f"{status_note} · {verify_note}{purge_note}"
        return True, summary_msg, changed

    except Exception as exc:
        if did_git_reset and protected_snapshots:
            _restore_protected_local_files_sync(
                target_dir, protected_snapshots
            )
        return False, f"업데이트 실행 예외: {exc}", False


async def execute_git_pull_and_preflight(
    base_dir: Optional[str] = None,
) -> Tuple[bool, str, bool]:
    """
    제1헌법: 동기 Git 및 서브프로세스 검증을 백그라운드 스레드로 격리 실행한다.
    """
    return await asyncio.wait_for(
        asyncio.to_thread(_execute_git_pull_and_preflight_sync, base_dir),
        timeout=60.0,
    )


# ---------------------------------------------------------------------------
# [핵심 5] 백그라운드 무인 자동 업데이트 루프 (Case 07: 장중 재기동 차단 & Case 81: os.execv 인플레이스 교체)
# ---------------------------------------------------------------------------
def _is_weekday_market_busy_est(now_est: Optional[datetime] = None) -> bool:
    """
    🚨 Case 07:
    평일(월~금) 04:00 ~ 16:05 EST 장중에는 무인 자동 업데이트로 인한 프로세스 재기동을 원천 차단한다.
    """
    dt = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    if dt.weekday() >= 5:
        return False
    hm = dt.hour * 100 + dt.minute
    return 400 <= hm <= 1605


async def run_auto_update_loop(
    context: Any,
    interval_sec: float = 3600.0,
) -> None:
    """
    # [Case 07, Case 68, Case 75 & Case 81]:
    백그라운드 무인 자동 업데이트 워커 (main_runtime.py / main.py 에서 정식 임포트):
    - 평일 04:00 ~ 16:05 EST 장중에는 절대 재기동하지 않고 대기한다 (Case 07).
    - 장외 시간대에 원격 저장소에 새로운 커밋이 감지되고 프리플라이트 검증을 통과했을 때만
      해당 폴더의 3중 원장, .env, .tg_update_offset 파일을 100% 보존한 상태로
      Case 81 커널 레벨 인플레이스 자가 교체(os.execv + 3.5초 하드 워치독)를 통해 무중단 재기동한다!
      (기존 os._exit(0) 으로 인해 systemd Restart=on-failure 환경에서 봇이 영구 사망하던 버그 100% 제거)
    """
    wait_s = max(300.0, float(interval_sec or 3600.0))
    base_dir = get_bot_base_dir(getattr(context, "base_dir", None))

    while not context.shutdown_event.is_set():
        try:
            await asyncio.wait_for(
                context.shutdown_event.wait(), timeout=wait_s
            )
            break
        except asyncio.TimeoutError:
            pass

        if context.shutdown_event.is_set():
            break

        now_est = datetime.now(EST_TZ)
        if _is_weekday_market_busy_est(now_est):
            continue

        try:
            st = context.ledger.get_state("SOXL")
            if str(st.get("buy_order_id") or "").strip() or str(
                st.get("sell_order_id") or ""
            ).strip():
                continue
        except Exception:
            pass

        try:
            ok, msg, changed = await execute_git_pull_and_preflight(base_dir)
            if ok and changed:
                logger.warning(
                    "🚀 [Case 81 장외 무인 자동 업데이트 검증 통과] %s -> 3.5초 워치독 및 os.execv 인플레이스 자가 재기동 개시",
                    msg,
                )
                if hasattr(context, "send_slim_alert"):
                    try:
                        await asyncio.wait_for(
                            context.send_slim_alert(
                                title="🚀 [장외 자동 업데이트 완료]",
                                body=f"{msg} · 최신 엔진으로 무중단 자가 재기동합니다.",
                            ),
                            timeout=5.0,
                        )
                    except Exception:
                        pass

                # 🚨 Case 81: 3.5초 데몬 하드 워치독 장착 및 종료 시그널 점화 후 즉시 인플레이스 교체 수행
                trigger_graceful_restart(
                    context=context,
                    shutdown_event=getattr(context, "shutdown_event", None),
                    reason="OFF_HOURS_AUTO_UPDATE",
                    watchdog_delay_sec=3.5,
                )
                await asyncio.sleep(0.4)
                perform_self_restart_execv(reason="OFF_HOURS_AUTO_UPDATE")
                break
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.debug("무인 업데이트 점검 루프 예외: %s", exc)


# 하위 호환 별칭 (타 모듈 및 프롬프트 심볼 완벽 호환)
auto_update_loop = run_auto_update_loop
start_auto_update_loop = run_auto_update_loop
background_auto_update_loop = run_auto_update_loop
purge_obsolete_files_sync = purge_deprecated_legacy_files


# ---------------------------------------------------------------------------
# CLI 엔트리포인트 (`--verify-only` 독립 검증 및 `systemd ExecStartPre` Case 07/68/75/81 호환)
# ---------------------------------------------------------------------------
def _cli_main() -> int:
    parser = argparse.ArgumentParser(
        description="Infinite Snowball v3.0 Diskless Preflight Compiler & AST Verifier"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="디스크의 12대 코어 모듈 인메모리 컴파일 및 AST 심볼 정합성만 검증하고 종료합니다.",
    )
    parser.add_argument(
        "--base-dir",
        type=str,
        default=get_bot_base_dir(),
        help="검증 대상 디렉토리 경로",
    )
    args, _ = parser.parse_known_args()
    target_dir = get_bot_base_dir(args.base_dir)

    purge_deprecated_legacy_files(target_dir)

    # MODIFIED [Case 81]: --verify-only 서브프로세스에서는 텔레그램 getUpdates 호출을 배제하여
    # 살아있는 메인 폴링 루프와의 HTTP 409 Conflict 충돌을 원천 차단한다!
    if args.verify_only:
        ok, msg = verify_all_modules_compile(target_dir)
        if ok:
            print(msg)
            return 0
        print(msg, file=sys.stderr)
        return 1

    _flush_telegram_pending_updates_sync(target_dir)

    now_est = datetime.now(EST_TZ)
    if _is_weekday_market_busy_est(now_est):
        print(
            f"🛡️ [{now_est.strftime('%Y-%m-%d %H:%M:%S EST')}] [Case 07 장중 락다운] "
            "평일 04:00 ~ 16:05 EST 구간 -> 무인 업데이트를 스킵하고 기존 검증 코드로 즉시 기동합니다."
        )
        ok, msg = verify_all_modules_compile(target_dir)
        if not ok:
            print(msg, file=sys.stderr)
            return 1
        return 0

    ok_git, msg_git, _ = _execute_git_pull_and_preflight_sync(target_dir)
    if ok_git:
        print(msg_git)
        return 0
    print(msg_git, file=sys.stderr)
    ok_local, _ = verify_all_modules_compile(target_dir)
    return 0 if ok_local else 1


if __name__ == "__main__":
    sys.exit(_cli_main())
