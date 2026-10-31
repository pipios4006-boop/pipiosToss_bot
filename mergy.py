#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
# MODIFIED: /home/pipiosToss/mergy.py
인피니트 스노우볼 (Infinite Snowball) v3.0 — 12대 코어 파이썬 모듈 단일 파일 병합기
- quant_engine 2분할(quant_engine_core.py + quant_engine.py),
  sniper_plugin 2분할(sniper_plugin_core.py + sniper_plugin.py),
  main 2분할(main_runtime.py + main.py)이 반영된 12대 코어 *.py 파일을
  어디에서 실행하더라도 /home/pipiosToss 에서 아키텍처 순서대로 병합하여
  /home/pipios4006/code.txt 파일로 원자적(Atomic) 저장합니다.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import List, Set, Tuple

SOURCE_DIR: str = "/home/pipiosToss"
OUTPUT_DIR: str = "/home/pipios4006"
OUTPUT_FILE: str = os.path.join(OUTPUT_DIR, "code.txt")
SELF_FILENAME: str = "mergy.py"

# MODIFIED: sniper_plugin_core.py 를 [FILE 05 / 12] 위치에 정식 등록하여 12대 코어 모듈 순서 100% 동기화
CORE_MODULE_ORDER: Tuple[str, ...] = (
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

EXCLUDED_FILES: Set[str] = {
    SELF_FILENAME,
    "daymarket_sim_plugin.py",
    "whipsaw_plugin.py",
    "candle_recorder.py",
    "tg_router.py",
}


def collect_target_py_files(src_dir: str) -> List[str]:
    if not os.path.isdir(src_dir):
        raise FileNotFoundError(f"소스 디렉토리가 존재하지 않습니다: {src_dir}")

    existing_files = set(os.listdir(src_dir))
    ordered_targets: List[str] = []

    for core_name in CORE_MODULE_ORDER:
        if core_name in existing_files and os.path.isfile(
            os.path.join(src_dir, core_name)
        ):
            ordered_targets.append(core_name)

    extra_py = sorted(
        f
        for f in existing_files
        if f.endswith(".py")
        and f not in ordered_targets
        and f not in EXCLUDED_FILES
        and ".tmp" not in f
        and not f.endswith(".heal.tmp")
        and os.path.isfile(os.path.join(src_dir, f))
    )
    ordered_targets.extend(extra_py)
    return ordered_targets


def merge_python_files() -> int:
    try:
        target_files = collect_target_py_files(SOURCE_DIR)
    except Exception as exc:
        print(f"🚨 [병합 실패] {exc}", file=sys.stderr)
        return 1

    if not target_files:
        print(
            f"🚨 [병합 실패] {SOURCE_DIR} 내에 병합할 .py 파일이 없습니다.",
            file=sys.stderr,
        )
        return 1

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_files = len(target_files)
    total_lines = 0
    total_bytes = 0

    merged_chunks: List[str] = [
        "=" * 100,
        f"# 📦 Infinite Snowball v3.0 — Merged Python Core Code ({total_files} Files)",
        f"# 🕒 Generated At : {now_str}",
        f"# 📂 Source Dir   : {SOURCE_DIR}",
        f"# 📄 Output File  : {OUTPUT_FILE}",
        "# 📋 File List    : " + ", ".join(target_files),
        "=" * 100,
        "",
    ]

    for idx, fname in enumerate(target_files, start=1):
        fpath = os.path.join(SOURCE_DIR, fname)
        with open(fpath, "r", encoding="utf-8", errors="replace") as rf:
            content = rf.read()

        line_cnt = len(content.splitlines())
        byte_cnt = len(content.encode("utf-8"))
        total_lines += line_cnt
        total_bytes += byte_cnt

        header = (
            f"\n{'#' * 100}\n"
            f"# [FILE {idx:02d} / {total_files:02d}] {fname} "
            f"(Lines: {line_cnt:,} | Size: {byte_cnt:,} bytes)\n"
            f"# Path: {fpath}\n"
            f"{'#' * 100}\n"
        )
        merged_chunks.append(header)
        merged_chunks.append(content.rstrip() + "\n")

    footer = (
        f"\n{'=' * 100}\n"
        f"# ✅ END OF MERGED CODE — Total Files: {total_files} | "
        f"Total Lines: {total_lines:,} | Total Size: {total_bytes:,} bytes\n"
        f"{'=' * 100}\n"
    )
    merged_chunks.append(footer)
    final_text = "\n".join(merged_chunks)

    tmp_output = f"{OUTPUT_FILE}.tmp.{os.getpid()}"
    try:
        with open(tmp_output, "w", encoding="utf-8") as wf:
            wf.write(final_text)
            wf.flush()
            os.fsync(wf.fileno())
        os.replace(tmp_output, OUTPUT_FILE)
    finally:
        if os.path.exists(tmp_output):
            try:
                os.remove(tmp_output)
            except Exception:
                pass

    print(
        f"✅ [병합 완료] 총 {total_files}개 파일 ({total_lines:,}줄 · {total_bytes:,} bytes) ➔ {OUTPUT_FILE}"
    )
    for idx, fname in enumerate(target_files, start=1):
        print(f"  {idx:02d}. {fname}")
    return 0


if __name__ == "__main__":
    sys.exit(merge_python_files())
