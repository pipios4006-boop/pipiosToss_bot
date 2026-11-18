# -*- coding: utf-8 -*-
"""
# MODIFIED: plugin_updater.py (Part 1/2 — REQUIRED_CORE_MODULES 내 barbell_plugin.py 및 assassin_plugin.py 15대 코어 모듈 등록 ·
# 스나이퍼/바벨[별도수익금고]/암살자 3중 원장 스냅샷 철벽 보호 · Case 81 os.execv 자가 교체 및 Case 85 자동 치유)
인피니트 스노우볼 (Infinite Snowball) v3.0 — 15대 코어 모듈 무디스크 인메모리 프리플라이트 컴파일 ·
AST 심볼 교차 검증 · 폴더별 원장(본 그리드 + 서브 그리드 + 바벨 원장/별도수익금고 + 암살자 원장)/환경변수/오프셋 스냅샷 보존 ·
무인 Git 업데이트 및 Case 81 커널 레벨 인플레이스 프로세스 자가 교체(os.execv + 3.5초 하드 워치독) 코어 모듈
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import errno
import glob
import hashlib
import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore

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
# [핵심 상수] 15대 코어 모듈(barbell_plugin.py · assassin_plugin.py 포함) 및 영구 폐기 레거시 파일 목록 (제3헌법)
# ---------------------------------------------------------------------------
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

DEPRECATED_LEGACY_FILES: Tuple[str, ...] = (
    "daymarket_sim_plugin.py",
    "whipsaw_plugin.py",
    "candle_recorder.py",
    "tg_router.py",
    "state_SOXS.json",
    "soxs_stratum_ledger.json",
)

_TG_TOKEN_STRICT_RE = re.compile(r"\b(\d{7,15}:[A-Za-z0-9_-]{25,60})\b")


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
        return ""

# [Case 85]: f-string 내 닫는 중괄호 '}' 가 '>' 로 오기된 패턴 자동 치유 정규식
_FSTRING_BROKEN_BRACE_RE = re.compile(
    r"(\{[A-Za-z_][A-Za-z0-9_]*)>(\.[A-Za-z0-9_]+)"
)

# [Case 85]: 삼항 연산자 조건절 내 비괄호 바다코끼리 연산자(:=) 오기 패턴 선제 치유 정규식
_TERNARY_WALRUS_GLITCH_RE = re.compile(
    r"\bif\s+\(?[A-Za-z_][A-Za-z0-9_]*\s*:=\s*res_obj\.get\(\s*(['\"]items['\"])\s*\)\s*\)?"
)

# [Case 81 & Case 108]: 중복 execv 방지 · SHA-256 코드 드리프트 · /proc 좀비 헌터 · 커널 심장박동 워치독 상태
_RESTART_EXEC_LOCK = threading.Lock()
_RESTART_WATCHDOG_TIMER: Optional[threading.Timer] = None

AUTO_UPDATE_CHECK_INTERVAL_SEC: float = 600.0
FLEET_BEACON_POLL_STEP_SEC: float = 15.0
ZOMBIE_HEARTBEAT_STALL_SEC: float = 300.0

_SINGLETON_LOCK_FD: int = -1
_LAST_MAIN_HEARTBEAT_MONO: float = time.monotonic()
_KERNEL_WATCHDOG_STARTED: bool = False
_KERNEL_WATCHDOG_LOCK = threading.Lock()


def compute_core_modules_sha256_sync(base_dir: Optional[str] = None) -> str:
    target_dir = get_bot_base_dir(base_dir)
    hasher = hashlib.sha256()
    for fname in REQUIRED_CORE_MODULES:
        fpath = os.path.join(target_dir, fname)
        if not os.path.isfile(fpath):
            return ""
        try:
            with open(fpath, "rb") as rf:
                raw = rf.read().replace(b"\r\n", b"\n")
            hasher.update(fname.encode("utf-8"))
            hasher.update(b"\x00")
            hasher.update(raw)
            hasher.update(b"\x00")
        except Exception:
            return ""
    return hasher.hexdigest()


BOOT_CODE_SHA256: str = compute_core_modules_sha256_sync()


def refresh_boot_code_sha256(base_dir: Optional[str] = None) -> str:
    global BOOT_CODE_SHA256
    cur = compute_core_modules_sha256_sync(base_dir)
    if cur:
        BOOT_CODE_SHA256 = cur
    return BOOT_CODE_SHA256


def touch_bot_heartbeat() -> float:
    global _LAST_MAIN_HEARTBEAT_MONO
    now_m = time.monotonic()
    _LAST_MAIN_HEARTBEAT_MONO = now_m
    return now_m


def get_bot_heartbeat_age_sec() -> float:
    return max(0.0, time.monotonic() - _LAST_MAIN_HEARTBEAT_MONO)


def _resolve_updater_shm_dir_sync() -> str:
    bdir = str(
        os.environ.get("TOSS_SHM_BUS_DIR", "/dev/shm/toss_sniper_bus_v3")
    ).strip()
    if bdir.startswith("/dev/shm/") and not os.path.isdir("/dev/shm"):
        bdir = "/tmp/toss_sniper_bus_v3"
    if not os.path.isdir(bdir):
        old_u = os.umask(0)
        try:
            os.makedirs(bdir, mode=0o777, exist_ok=True)
            os.chmod(bdir, 0o777)
        except Exception:
            pass
        finally:
            os.umask(old_u)
    return bdir


def _read_shm_update_beacon_sync() -> Dict[str, Any]:
    fp = os.path.join(
        _resolve_updater_shm_dir_sync(), "fleet_update_beacon_v3.json"
    )
    if not os.path.isfile(fp):
        return {}
    try:
        with open(fp, "r", encoding="utf-8") as rf:
            data = json.load(rf)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_shm_update_beacon_sync(
    commit_or_sha: str, source_dir: Optional[str] = None
) -> None:
    bdir = _resolve_updater_shm_dir_sync()
    fp = os.path.join(bdir, "fleet_update_beacon_v3.json")
    tmp_fp = f"{fp}.tmp.{os.getpid()}.{threading.get_ident()}"
    payload = {
        "ts": round(time.time(), 3),
        "commit": str(commit_or_sha or "").strip(),
        "source_dir": str(source_dir or get_bot_base_dir()),
        "pid": os.getpid(),
    }
    old_u = os.umask(0)
    try:
        with open(tmp_fp, "w", encoding="utf-8") as wf:
            json.dump(payload, wf, ensure_ascii=False)
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


def _read_env_identity_pair_sync(target_dir: str) -> Tuple[str, str]:
    tg_tok = ""
    client_id = ""
    env_fp = os.path.join(target_dir, ".env")
    if not os.path.isfile(env_fp):
        return "", ""
    try:
        with open(env_fp, "r", encoding="utf-8", errors="ignore") as rf:
            for raw_line in rf:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[len("export ") :].strip()
                k, v = line.split("=", 1)
                k_u = k.strip().upper()
                v_c = v.strip().strip("'").strip('"').strip()
                if k_u in (
                    "TELEGRAM_BOT_TOKEN",
                    "TG_BOT_TOKEN",
                    "BOT_TOKEN",
                    "TELEGRAM_TOKEN",
                ) and not tg_tok:
                    m = _TG_TOKEN_STRICT_RE.search(v_c)
                    if m:
                        tg_tok = m.group(1)
                elif k_u in (
                    "TOSS_CLIENT_ID",
                    "TOSS_API_KEY",
                    "TOSS_APP_KEY",
                    "CLIENT_ID",
                ) and v_c and not client_id:
                    client_id = v_c
    except Exception:
        return "", ""
    return tg_tok, client_id


def _is_systemd_service_pid(pid: int) -> Tuple[bool, str]:
    cg_fp = f"/proc/{pid}/cgroup"
    if not os.path.isfile(cg_fp):
        return False, ""
    try:
        with open(cg_fp, "r", encoding="utf-8", errors="ignore") as rf:
            for line in rf:
                leaf = line.strip().rsplit("/", 1)[-1]
                if leaf.endswith(".service") and not leaf.startswith("user@"):
                    return True, leaf
    except Exception:
        pass
    return False, ""


def _collect_protected_family_pids(my_pid: int) -> Set[int]:
    protected: Set[int] = {1, my_pid}
    ppid_map: Dict[int, int] = {}
    if not os.path.isdir("/proc"):
        return protected
    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            p_i = int(entry)
            try:
                with open(
                    f"/proc/{p_i}/stat", "r", encoding="utf-8", errors="ignore"
                ) as sf:
                    raw_stat = sf.read()
                rpar = raw_stat.rfind(")")
                if rpar > 0:
                    fields = raw_stat[rpar + 1 :].split()
                    if len(fields) >= 2 and fields[1].isdigit():
                        ppid_map[p_i] = int(fields[1])
            except Exception:
                continue
        cur = my_pid
        for _ in range(32):
            parent = ppid_map.get(cur, 0)
            if parent <= 1 or parent in protected:
                break
            protected.add(parent)
            cur = parent
        changed = True
        while changed:
            changed = False
            for child_p, par_p in ppid_map.items():
                if par_p in protected and child_p not in protected:
                    protected.add(child_p)
                    changed = True
    except Exception:
        pass
    return protected


def _extract_python_main_script_from_cmdline(args: List[str]) -> str:
    if len(args) < 2:
        return ""
    exe_base = os.path.basename(args[0]).lower()
    if not exe_base.startswith("python"):
        return ""
    idx = 1
    while idx < len(args):
        tok = args[idx]
        if tok in ("-c", "-m"):
            return ""
        if tok in ("-W", "-X", "--check-hash-based-pycs"):
            idx += 2
            continue
        if tok.startswith("-"):
            idx += 1
            continue
        return tok
    return ""


def _discover_duplicate_bot_candidates_sync(
    base_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not os.path.isdir("/proc"):
        return []
    target_dir = os.path.realpath(get_bot_base_dir(base_dir))
    my_main_py = os.path.realpath(os.path.join(target_dir, "main.py"))
    my_pid = os.getpid()
    my_uid = os.getuid() if hasattr(os, "getuid") else -1
    protected_pids = _collect_protected_family_pids(my_pid)
    my_tg_tok, my_cid = _read_env_identity_pair_sync(target_dir)

    victims: List[Dict[str, Any]] = []
    try:
        entries = os.listdir("/proc")
    except Exception:
        return []

    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid <= 1 or pid in protected_pids:
            continue
        try:
            if my_uid > 0:
                st_p = os.stat(f"/proc/{pid}")
                if st_p.st_uid != my_uid:
                    continue
            with open(f"/proc/{pid}/cmdline", "rb") as cf:
                raw_cmd = cf.read()
            if not raw_cmd:
                continue
            args = [
                x
                for x in raw_cmd.decode("utf-8", errors="ignore").split("\x00")
                if x
            ]
            if "--verify-only" in args:
                continue
            script_arg = _extract_python_main_script_from_cmdline(args)
            if not script_arg or os.path.basename(script_arg) != "main.py":
                continue

            try:
                cand_cwd = os.path.realpath(f"/proc/{pid}/cwd")
            except Exception:
                cand_cwd = ""

            if os.path.isabs(script_arg):
                cand_main = os.path.realpath(script_arg)
            elif cand_cwd:
                cand_main = os.path.realpath(
                    os.path.join(cand_cwd, script_arg)
                )
            else:
                continue

            cand_dir = os.path.dirname(cand_main)
            cand_is_svc, cand_unit = _is_systemd_service_pid(pid)
            same_dir = bool(
                cand_dir == target_dir or cand_main == my_main_py
            )
            same_clone = False
            if not same_dir and my_tg_tok and my_cid and (not cand_is_svc):
                if os.path.isfile(
                    os.path.join(cand_dir, "sniper_plugin_core.py")
                ) and os.path.isfile(
                    os.path.join(cand_dir, "barbell_plugin.py")
                ):
                    c_tok, c_cid = _read_env_identity_pair_sync(cand_dir)
                    if c_tok == my_tg_tok and c_cid == my_cid:
                        same_clone = True

            if same_dir or same_clone:
                victims.append(
                    {
                        "pid": pid,
                        "dir": cand_dir,
                        "same_dir": same_dir,
                        "is_service": cand_is_svc,
                        "service_unit": cand_unit,
                    }
                )
        except Exception:
            continue
    return victims


def _kill_victim_pids_sync(
    victims: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    if not victims:
        return []
    reaped: List[Dict[str, Any]] = []
    for v in victims:
        v_pid = safe_int(v.get("pid"), 0)
        if v_pid <= 1:
            continue
        try:
            os.kill(v_pid, signal.SIGTERM)
            reaped.append(v)
        except ProcessLookupError:
            continue
        except Exception as exc:
            logger.debug("좀비 프로세스 SIGTERM 예외(PID=%d): %s", v_pid, exc)

    if not reaped:
        return []

    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline:
        alive_cnt = sum(
            1 for v in reaped if os.path.exists(f"/proc/{v['pid']}")
        )
        if alive_cnt == 0:
            break
        time.sleep(0.1)

    for v in reaped:
        v_pid = safe_int(v.get("pid"), 0)
        if v_pid > 1 and os.path.exists(f"/proc/{v_pid}"):
            try:
                os.kill(v_pid, signal.SIGKILL)
            except Exception:
                pass
    return reaped


def _scan_and_reap_zombies_for_preflight_sync(
    base_dir: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], bool]:
    # 프리플라이트 중 비서비스 중복 좀비는 즉시 소각하고, 정규 systemd 서비스 존재 시 재기동 인계 플래그 반환
    my_is_svc, _ = _is_systemd_service_pid(os.getpid())
    cands = _discover_duplicate_bot_candidates_sync(base_dir)
    if not cands:
        return [], False

    need_systemd_yield = False
    immediate_targets: List[Dict[str, Any]] = []
    for c in cands:
        if (not my_is_svc) and bool(c.get("same_dir")) and bool(
            c.get("is_service")
        ):
            need_systemd_yield = True
        else:
            immediate_targets.append(c)

    reaped = _kill_victim_pids_sync(immediate_targets)
    if reaped:
        logger.warning(
            "🧹 [Case 108 프리플라이트 유령 중복 좀비 %d개 즉시 소각 완료] PIDs=%s",
            len(reaped),
            [r["pid"] for r in reaped],
        )
    return reaped, need_systemd_yield


def reap_duplicate_zombie_bots_sync(
    base_dir: Optional[str] = None,
    yield_to_systemd: bool = False,
) -> List[Dict[str, Any]]:
    target_dir = os.path.realpath(get_bot_base_dir(base_dir))
    my_pid = os.getpid()
    my_is_svc, _ = _is_systemd_service_pid(my_pid)
    cands = _discover_duplicate_bot_candidates_sync(target_dir)
    if not cands:
        return []

    had_same_dir_svc = any(
        bool(c.get("same_dir")) and bool(c.get("is_service")) for c in cands
    )
    reaped = _kill_victim_pids_sync(cands)
    if reaped:
        logger.warning(
            "🧹 [Case 108 중복 좀비 봇 사살 완료] 내 PID=%d · 소각된 좀비=%s",
            my_pid,
            [(r["pid"], r.get("service_unit") or "nohup/cli") for r in reaped],
        )

    if yield_to_systemd and (not my_is_svc) and had_same_dir_svc:
        wait_until = time.monotonic() + 6.5
        while time.monotonic() < wait_until:
            time.sleep(0.25)
            post_cands = _discover_duplicate_bot_candidates_sync(target_dir)
            svc_respawned = [
                c
                for c in post_cands
                if bool(c.get("same_dir")) and bool(c.get("is_service"))
            ]
            if svc_respawned:
                new_svc = svc_respawned[0]
                logger.warning(
                    "🛡️ [Case 108 정규 systemd 서비스(%s · PID=%d) 최신 코드 부활 확인 -> 수동 중복 프로세스(PID=%d) 자진 종료]",
                    new_svc.get("service_unit") or "systemd",
                    safe_int(new_svc.get("pid"), 0),
                    my_pid,
                )
                try:
                    sys.stdout.flush()
                    sys.stderr.flush()
                except Exception:
                    pass
                os._exit(0)
    return reaped


def release_bot_singleton_lock_sync() -> None:
    global _SINGLETON_LOCK_FD
    fd = _SINGLETON_LOCK_FD
    _SINGLETON_LOCK_FD = -1
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


def acquire_bot_singleton_lock_sync(base_dir: Optional[str] = None) -> bool:
    global _SINGLETON_LOCK_FD
    target_dir = get_bot_base_dir(base_dir)
    reap_duplicate_zombie_bots_sync(target_dir, yield_to_systemd=True)
    if fcntl is None:
        return True
    if _SINGLETON_LOCK_FD >= 0:
        return True
    slug = get_folder_slug(target_dir)
    lock_fp = os.path.join(target_dir, f".sniper_singleton_{slug}.lock")
    old_u = os.umask(0)
    fd = -1
    try:
        fd = os.open(lock_fp, os.O_CREAT | os.O_RDWR, 0o666)
        for attempt in range(2):
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                os.ftruncate(fd, 0)
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, f"{os.getpid()}\n".encode("utf-8"))
                _SINGLETON_LOCK_FD = fd
                return True
            except (BlockingIOError, OSError):
                if attempt == 0:
                    reap_duplicate_zombie_bots_sync(
                        target_dir, yield_to_systemd=True
                    )
                    time.sleep(0.2)
                    continue
                break
        os.close(fd)
        return False
    except Exception:
        if fd >= 0:
            try:
                os.close(fd)
            except Exception:
                pass
        return False
    finally:
        os.umask(old_u)


# ---------------------------------------------------------------------------
# [핵심 0-A · Case 81] 커널 레벨 인플레이스 프로세스 자가 교체(os.execv) 및 3.5초 데몬 하드 워치독
# ---------------------------------------------------------------------------
def resolve_tg_offset_dat_path(base_dir: Optional[str] = None) -> str:
    """
    # [Case 81 & Case 85]:
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
    🚨 [Case 81 핵심 : 커널 레벨 인플레이스 프로세스 자가 교체기]
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

        # NEW [Case 108]: 재기동 직전 싱글톤 락 해제 · 잔존 유령 좀비 전수 사살 · __pycache__ 소각 및 '-B' 강제 주입
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
        release_bot_singleton_lock_sync()
        reap_duplicate_zombie_bots_sync(target_dir, yield_to_systemd=True)
        emergency_free_disk_space_sync(
            base_dir=target_dir, keep_backup_days=14, remove_pycache=True
        )

        python_exe = sys.executable or "/usr/bin/python3"
        raw_argv = (
            list(sys.argv)
            if sys.argv
            else [os.path.join(target_dir, "main.py")]
        )
        if not raw_argv[0] or "--verify-only" in raw_argv:
            script_path = os.path.join(target_dir, "main.py")
            exec_argv = [python_exe, "-B", script_path]
        else:
            script_arg = raw_argv[0]
            if not os.path.isabs(script_arg):
                cand_abs = os.path.join(target_dir, script_arg)
                if os.path.isfile(cand_abs):
                    script_arg = cand_abs
            tail_args = [a for a in raw_argv[1:] if a != "-B"]
            exec_argv = [python_exe, "-B", script_arg] + tail_args

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
    🚨 [Case 81 핵심 : 비동기 종료 데드락(Deaf Zombie Process) 타파용 3.5초 데몬 하드 워치독]
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
    🚨 [Case 81 : 재기동 플래그 설정 + 3.5초 하드 워치독 가동 + 이벤트 루프 즉시 깨우기 통합 점화기]
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
# [핵심 0-C] git reset --hard 실행 전후 폴더별 원장(스나이퍼 + 바벨 별도수익금고 + 암살자) · .env · 오프셋 철벽 보호기
# ---------------------------------------------------------------------------
def _snapshot_protected_local_files_sync(target_dir: str) -> Dict[str, bytes]:
    """
    🚨 Case 68, Case 75, Case 81, Case 86, Case 87, Case 88, Case 91 & 바벨 확장:
    git reset --hard 직전에 폴더 내 모든 원장(*ledger*.json : soxl_stratum_ledger*.json,
    barbell_ledger*.json, assassin_sim_ledger*.json 포함), 백업, .env, .tg_update_offset 파일을 메모리에 스냅샷 보존한다.
    """
    abs_dir = get_bot_base_dir(target_dir)
    emergency_free_disk_space_sync(
        base_dir=abs_dir, keep_backup_days=14, remove_pycache=True
    )

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

    return restored_cnt


# ---------------------------------------------------------------------------
# [핵심 1] 구버전 폐기 파일 및 고아 임시 파일 자동 청소기
# ---------------------------------------------------------------------------
def purge_deprecated_legacy_files(
    base_dir: Optional[str] = None,
) -> List[str]:
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
# -*- coding: utf-8 -*-
"""
# MODIFIED: plugin_updater.py (Part 2/2 — Case 85 자동 치유 · 15대 코어 모듈 무디스크 인메모리 AST 교차 검증 ·
# 스나이퍼/바벨[barbell_ledger.json]/암살자 원장 보호 Git 업데이트 · 장외 업데이트 시 SGOV/실전암살자 미결 주문 보호 · Case 81 무중단 자가 재기동)
"""


# ---------------------------------------------------------------------------
# [핵심 2] Case 85 f-string 닫는 중괄호 정규식 치유 & 삼항식 walrus 정규식 치유 & 4배수 선제 스냅 자동 치유기
# ---------------------------------------------------------------------------
def _auto_heal_indentation_glitches(
    filepath: str, max_passes: int = 6
) -> bool:
    if not os.path.isfile(filepath):
        return False

    fence_prefix = chr(96) * 3
    coding_marker = "# -*- coding: utf-8 -*-"
    target_dir = os.path.dirname(os.path.abspath(filepath))

    try:
        with GlobalThrottle.get_file_lock(filepath):
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                orig_src = f.read()

            src = _FSTRING_BROKEN_BRACE_RE.sub(r"\1}\2", orig_src)
            src = _TERNARY_WALRUS_GLITCH_RE.sub(
                r"if res_obj.get(\1) is not None", src
            )

            try:
                ast.parse(src, filename=filepath)
                if src == orig_src:
                    return False
            except (IndentationError, SyntaxError):
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
                src = _FSTRING_BROKEN_BRACE_RE.sub(r"\1}\2", src)
                src = _TERNARY_WALRUS_GLITCH_RE.sub(
                    r"if res_obj.get(\1) is not None", src
                )

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
                            "🔧 [Case 85 들여쓰기/f-string 중괄호 자동 정규화 완료] %s",
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
# [핵심 3] AST 최상위 익스포트 심볼 추출기 및 15대 코어 모듈 무디스크 인메모리 교차 검증기
# ---------------------------------------------------------------------------
def _collect_top_level_module_stmts(
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
    return exported


def verify_all_modules_compile(
    base_dir: Optional[str] = None,
) -> Tuple[bool, str]:
    target_dir = get_bot_base_dir(base_dir)
    emergency_free_disk_space_sync(
        base_dir=target_dir, keep_backup_days=14, remove_pycache=False
    )

    errors: List[str] = []
    ast_trees: Dict[str, ast.AST] = {}
    exported_map: Dict[str, Set[str]] = {}

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
            errors.append(
                f"문법/컴파일 오류 [{fname}]{line_info}: {syn_err.msg}"
            )
        except Exception as exc:
            errors.append(f"컴파일/AST 파싱 예외 [{fname}]: {exc}")

    if errors:
        return False, "🚨 컴파일/문법 검증 실패:\n" + "\n".join(errors)

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
# [핵심 4] 스마트 Git 동기화 · 스나이퍼/바벨/암살자 원장 및 오프셋 철벽 보존 쉴드
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
                reaped_fb, yield_fb = _scan_and_reap_zombies_for_preflight_sync(
                    target_dir
                )
                ok_local, msg_local = verify_all_modules_compile(target_dir)
                cur_sha_fb = compute_core_modules_sha256_sync(target_dir)
                drift_fb = bool(
                    ok_local
                    and (
                        yield_fb
                        or (
                            BOOT_CODE_SHA256
                            and cur_sha_fb
                            and cur_sha_fb != BOOT_CODE_SHA256
                        )
                    )
                )
                z_note_fb = (
                    f" · 🧹유령좀비 {len(reaped_fb)}개 소각" if reaped_fb else ""
                )
                return (
                    ok_local,
                    f"로컬 검증 완료 (git fetch 스킵): {msg_local}{z_note_fb}",
                    drift_fb,
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

        if remote_ahead <= 0:
            reaped_z, need_svc_yield = _scan_and_reap_zombies_for_preflight_sync(
                target_dir
            )
            purged_list = purge_deprecated_legacy_files(target_dir)
            ok_local, msg_local = verify_all_modules_compile(target_dir)
            short_hash = prev_hash[:7] if prev_hash else "local"
            purge_note = (
                f" · 폐기파일 {len(purged_list)}개 소각" if purged_list else ""
            )
            zombie_note = (
                f" · 🧹유령좀비 {len(reaped_z)}개 소각" if reaped_z else ""
            )
            if not ok_local:
                return (
                    False,
                    f"🚨 로컬 프리플라이트 검증 실패:\n{msg_local}",
                    False,
                )
            cur_disk_sha = compute_core_modules_sha256_sync(target_dir)
            code_drift = bool(
                BOOT_CODE_SHA256
                and cur_disk_sha
                and cur_disk_sha != BOOT_CODE_SHA256
            )
            should_restart_now = bool(code_drift or need_svc_yield)
            if should_restart_now:
                _flush_telegram_pending_updates_sync(target_dir)
                _write_shm_update_beacon_sync(
                    prev_hash or cur_disk_sha[:12], target_dir
                )
                return (
                    True,
                    f"디스크 패치 동기화 감지({short_hash}) · 구버전 RAM 교체 재기동 · {msg_local}{zombie_note}{purge_note}",
                    True,
                )
            return (
                True,
                f"현재 버전({short_hash}) 유지 · 원장 100% 보존 · {msg_local}{zombie_note}{purge_note}",
                False,
            )

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
        for ledger_ignore_name in (
            "soxl_stratum_ledger.json",
            "barbell_ledger.json",
            "assassin_sim_ledger.json",
        ):
            try:
                _run_cmd_sync(
                    [
                        "git",
                        "rm",
                        "--cached",
                        "--ignore-unmatch",
                        ledger_ignore_name,
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
                        ledger_ignore_name,
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

        reaped_post, need_svc_yield_post = (
            _scan_and_reap_zombies_for_preflight_sync(target_dir)
        )
        post_disk_sha = compute_core_modules_sha256_sync(target_dir)
        changed = bool(
            changed
            or need_svc_yield_post
            or (
                BOOT_CODE_SHA256
                and post_disk_sha
                and post_disk_sha != BOOT_CODE_SHA256
            )
        )
        if changed:
            _write_shm_update_beacon_sync(
                new_hash or post_disk_sha[:12], target_dir
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
        zombie_post_note = (
            f" · 🧹유령좀비 {len(reaped_post)}개 소각" if reaped_post else ""
        )
        purge_note = (
            f" · 폐기파일 {len(purged_list)}개 소각" if purged_list else ""
        )
        summary_msg = f"{status_note} · {verify_note}{zombie_post_note}{purge_note}"
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
    return await asyncio.wait_for(
        asyncio.to_thread(_execute_git_pull_and_preflight_sync, base_dir),
        timeout=60.0,
    )


# ---------------------------------------------------------------------------
# [핵심 5] 백그라운드 무인 자동 업데이트 루프 (Case 07: 장중 재기동 차단 & 미결주문 보호 & Case 81: os.execv 인플레이스 교체)
# ---------------------------------------------------------------------------
def _is_weekday_market_busy_est(now_est: Optional[datetime] = None) -> bool:
    dt = now_est.astimezone(EST_TZ) if now_est else datetime.now(EST_TZ)
    if dt.weekday() >= 5:
        return False
    hm = dt.hour * 100 + dt.minute
    return 400 <= hm <= 1605


def _has_active_orders_or_live_assn_for_update(context: Any) -> bool:
    # NEW [Case 81]: 스나이퍼 SOXL · 바벨 SGOV · 실전 암살자 미결주문/포지션 통합 검문기
    try:
        st = context.ledger.get_state("SOXL")
        if str(st.get("buy_order_id") or "").strip() or str(
            st.get("sell_order_id") or ""
        ).strip():
            return True
    except Exception:
        pass
    try:
        if hasattr(context, "barbell_ledger"):
            bst = context.barbell_ledger.get_state()
            if str(bst.get("sgov_buy_order_id") or "").strip() or str(
                bst.get("sgov_sell_order_id") or ""
            ).strip():
                return True
    except Exception:
        pass
    try:
        if hasattr(context, "assassin_ledger"):
            ast_st = context.assassin_ledger.get_state()
            if (
                bool(ast_st.get("is_live_position", False))
                or str(ast_st.get("pending_buy_order_id") or "").strip()
                or str(
                    ast_st.get("pending_exit_sell_order_id") or ""
                ).strip()
            ):
                return True
    except Exception:
        pass
    return False


def start_kernel_zombie_watchdog_thread(
    context: Any,
    stall_timeout_sec: float = ZOMBIE_HEARTBEAT_STALL_SEC,
) -> Optional[threading.Thread]:
    # NEW [Case 108]: asyncio 루프 완전 정지(Deaf Zombie) 시에도 독립 작동하는 순수 OS 커널 데몬 워치독 스레드
    global _KERNEL_WATCHDOG_STARTED
    with _KERNEL_WATCHDOG_LOCK:
        if _KERNEL_WATCHDOG_STARTED:
            return None
        _KERNEL_WATCHDOG_STARTED = True

    touch_bot_heartbeat()
    base_dir = get_bot_base_dir(getattr(context, "base_dir", None))
    max_stall = max(
        120.0, float(stall_timeout_sec or ZOMBIE_HEARTBEAT_STALL_SEC)
    )

    def _kernel_watchdog_worker() -> None:
        while True:
            time.sleep(30.0)
            try:
                ev = getattr(context, "shutdown_event", None)
                if (
                    ev is not None
                    and ev.is_set()
                    and not bool(getattr(context, "restart_requested", False))
                ):
                    return
                age_s = get_bot_heartbeat_age_sec()
                if age_s < max_stall:
                    continue
                logger.error(
                    "🚨 [Case 108 커널 스레드 워치독 격발] 메인 이벤트 루프 무응답 %.1f초(한도 %.1f초) 감지 -> 먹통 좀비 자동 부활 집행!",
                    age_s,
                    max_stall,
                )
                if not _is_weekday_market_busy_est(datetime.now(EST_TZ)):
                    try:
                        _execute_git_pull_and_preflight_sync(base_dir)
                    except Exception:
                        pass
                perform_self_restart_execv(
                    reason=f"KERNEL_WATCHDOG_STALL_{int(age_s)}S"
                )
                return
            except Exception as wd_exc:
                logger.debug("커널 워치독 점검 예외: %s", wd_exc)

    th = threading.Thread(
        target=_kernel_watchdog_worker,
        name="sniper_kernel_watchdog",
        daemon=True,
    )
    th.start()
    logger.info(
        "🛡️ [Case 108 OS 커널 스레드 좀비 부활 워치독 가동 완료] 무응답 한도=%.0f초 · 장외 업데이트 주기=%.0f초",
        max_stall,
        AUTO_UPDATE_CHECK_INTERVAL_SEC,
    )
    return th


def run_plugin_updater_zombie_guard_tdd(
    base_dir: Optional[str] = None,
) -> bool:
    t_dir = get_bot_base_dir(base_dir)
    sha_now = compute_core_modules_sha256_sync(t_dir)
    assert len(sha_now) == 64, f"Case 108 SHA-256 산출 실패: {sha_now}"
    assert (
        _extract_python_main_script_from_cmdline(
            ["/usr/bin/python3", "-B", "/home/pipiosToss/main.py"]
        )
        == "/home/pipiosToss/main.py"
    )
    assert (
        _extract_python_main_script_from_cmdline(
            ["python3", "-c", "import main"]
        )
        == ""
    )
    fam = _collect_protected_family_pids(os.getpid())
    assert os.getpid() in fam
    touch_bot_heartbeat()
    assert get_bot_heartbeat_age_sec() < 5.0
    return True


async def run_auto_update_loop(
    context: Any,
    interval_sec: float = AUTO_UPDATE_CHECK_INTERVAL_SEC,
) -> None:
    raw_iv = float(interval_sec or AUTO_UPDATE_CHECK_INTERVAL_SEC)
    if raw_iv >= 3600.0:
        raw_iv = AUTO_UPDATE_CHECK_INTERVAL_SEC
    wait_s = max(120.0, raw_iv)
    base_dir = get_bot_base_dir(getattr(context, "base_dir", None))
    # NEW [Case 81]: 미결주문 유예 시 차기 주기 재기동 신호 증발 차단용 래치
    pending_restart_msg: str = ""
    last_seen_beacon_ts: float = float(
        (_read_shm_update_beacon_sync().get("ts") or 0.0)
    )

    while not context.shutdown_event.is_set():
        eff_wait_s = 60.0 if pending_restart_msg else wait_s
        slept_s = 0.0
        while slept_s < eff_wait_s and not context.shutdown_event.is_set():
            step_s = min(FLEET_BEACON_POLL_STEP_SEC, eff_wait_s - slept_s)
            try:
                await asyncio.wait_for(
                    context.shutdown_event.wait(), timeout=step_s
                )
                break
            except asyncio.TimeoutError:
                slept_s += step_s

            if _is_weekday_market_busy_est(datetime.now(EST_TZ)):
                continue
            if _has_active_orders_or_live_assn_for_update(context):
                continue

            beacon_d = await asyncio.to_thread(_read_shm_update_beacon_sync)
            b_ts = float(beacon_d.get("ts") or 0.0)
            if b_ts > (last_seen_beacon_ts + 0.5):
                last_seen_beacon_ts = b_ts
                break

            cur_sha = await asyncio.to_thread(
                compute_core_modules_sha256_sync, base_dir
            )
            if (
                BOOT_CODE_SHA256
                and cur_sha
                and cur_sha != BOOT_CODE_SHA256
            ):
                break

        if context.shutdown_event.is_set():
            break

        now_est = datetime.now(EST_TZ)
        if _is_weekday_market_busy_est(now_est):
            continue

        if _has_active_orders_or_live_assn_for_update(context):
            continue

        try:
            if pending_restart_msg:
                ok_v, msg_v = await asyncio.to_thread(
                    verify_all_modules_compile, base_dir
                )
                if not ok_v:
                    logger.error(
                        "🚨 [Case 81 유예 재기동 취소] 로컬 코어 검증 실패: %s",
                        msg_v,
                    )
                    pending_restart_msg = ""
                    continue
                ok, msg, changed = True, pending_restart_msg, True
            else:
                ok, msg, changed = await execute_git_pull_and_preflight(
                    base_dir
                )
                if ok and changed:
                    pending_restart_msg = msg

            if ok and (changed or bool(pending_restart_msg)):
                if _is_weekday_market_busy_est(
                    datetime.now(EST_TZ)
                ) or _has_active_orders_or_live_assn_for_update(context):
                    logger.info(
                        "⏳ [Case 81 재기동 유예 래치 보존] 미결주문/장중 감지 -> 종결 후 60초 내 재기동"
                    )
                    continue
                pending_restart_msg = ""
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


# 하위 호환 별칭
auto_update_loop = run_auto_update_loop
start_auto_update_loop = run_auto_update_loop
background_auto_update_loop = run_auto_update_loop
purge_obsolete_files_sync = purge_deprecated_legacy_files


# ---------------------------------------------------------------------------
# CLI 엔트리포인트 (`--verify-only` 독립 검증 및 `systemd ExecStartPre` 호환)
# ---------------------------------------------------------------------------
def _cli_main() -> int:
    parser = argparse.ArgumentParser(
        description="Infinite Snowball v3.0 Diskless Preflight Compiler & AST Verifier"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="디스크의 15대 코어 모듈 인메모리 컴파일 및 AST 심볼 정합성만 검증하고 종료합니다.",
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
