#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
# MODIFIED: /home/pipiosToss/mergy.py
인피니트 스노우볼 (Infinite Snowball) v3.0 — 15대 코어 파이썬 모듈 단일 파일 병합기
(바벨 모드 barbell_plugin.py · [모의 ⇄ 0주전환예약 ⇄ 실전] 암살자 assassin_plugin.py · Case 01 ~ Case 93 반영)
- toss_api 2분할(toss_api_core.py + toss_api.py),
  quant_engine 2분할(quant_engine_core.py + quant_engine.py),
  sniper_plugin 2분할(sniper_plugin_core.py + sniper_plugin.py),
  ⚖️ 바벨 60/30/10 및 별도 수익금고 플러그인(barbell_plugin.py),
  🗡️ [모의 ⇄ 0주전환예약 ⇄ 실전] 암살자 독립 플러그인(assassin_plugin.py),
  main 2분할(main_runtime.py + main.py)이 반영된 15대 코어 *.py 파일을
  어디에서 실행하더라도 /home/pipiosToss 에서 아키텍처 순서대로
  디스크 쓰기 0 Byte 인메모리 문법 · f-string 중괄호(Case 85) · AST 심볼 교차 검증 후 병합하여
  /home/pipios4006/code.txt 파일로 원자적(Atomic) 저장합니다.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from datetime import datetime
from typing import Dict, List, Set, Tuple

SOURCE_DIR: str = "/home/pipiosToss"
OUTPUT_DIR: str = "/home/pipios4006"
OUTPUT_FILE: str = os.path.join(OUTPUT_DIR, "code.txt")
SELF_FILENAME: str = "mergy.py"

# MODIFIED: plugin_updater.py 의 REQUIRED_CORE_MODULES 와 100% 동일한 15대 코어 모듈 아키텍처 순서 락온
# - [FILE 10 / 15] barbell_plugin.py (바벨 60/30/10 · 별도 실현수익금고 · 정규장 SGOV 집행)
# - [FILE 11 / 15] assassin_plugin.py ([모의 ⇄ 0주전환예약 ⇄ 실전] 암살자 14대 진성 게이트)
CORE_MODULE_ORDER: Tuple[str, ...] = (
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

EXCLUDED_FILES: Set[str] = {
    SELF_FILENAME,
    "daymarket_sim_plugin.py",
    "whipsaw_plugin.py",
    "candle_recorder.py",
    "tg_router.py",
}

# NEW [Case 85]: f-string 내 닫는 중괄호 '}' 가 '>' 로 오기된 패턴 탐지 정규식
_FSTRING_BROKEN_BRACE_RE = re.compile(
    r"(\{[A-Za-z_][A-Za-z0-9_]*)>(\.[A-Za-z0-9_]+)"
)


def _extract_module_exported_symbols(tree: ast.AST) -> Set[str]:
    """AST 트리에서 모듈이 외부로 노출하는 함수·클래스·변수·재익스포트 심볼 집합을 추출한다."""
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


def collect_target_py_files(
    src_dir: str, strict_core_only: bool = False
) -> Tuple[List[str], List[str]]:
    if not os.path.isdir(src_dir):
        raise FileNotFoundError(f"소스 디렉토리가 존재하지 않습니다: {src_dir}")

    existing_files = set(os.listdir(src_dir))
    ordered_targets: List[str] = []
    missing_core: List[str] = []

    for core_name in CORE_MODULE_ORDER:
        full_p = os.path.join(src_dir, core_name)
        if core_name in existing_files and os.path.isfile(full_p):
            ordered_targets.append(core_name)
        else:
            missing_core.append(core_name)

    if not strict_core_only:
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

    return ordered_targets, missing_core


def merge_python_files(
    src_dir: str = SOURCE_DIR,
    out_file: str = OUTPUT_FILE,
    allow_partial: bool = False,
    strict_core_only: bool = False,
) -> int:
    try:
        target_files, missing_core = collect_target_py_files(
            src_dir=src_dir, strict_core_only=strict_core_only
        )
    except Exception as exc:
        print(f"🚨 [병합 실패] {exc}", file=sys.stderr)
        return 1

    if missing_core and not allow_partial:
        print(
            f"🚨 [병합 중단] 필수 15대 코어 모듈 중 {len(missing_core)}개 파일이 누락되었습니다:",
            file=sys.stderr,
        )
        for m_name in missing_core:
            print(f"  - {os.path.join(src_dir, m_name)}", file=sys.stderr)
        return 1

    if not target_files:
        print(
            f"🚨 [병합 실패] {src_dir} 내에 병합할 .py 파일이 없습니다.",
            file=sys.stderr,
        )
        return 1

    out_dir = os.path.dirname(os.path.abspath(out_file))
    os.makedirs(out_dir, exist_ok=True)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_files = len(target_files)
    total_lines = 0
    total_bytes = 0

    syntax_errors: List[str] = []
    import_errors: List[str] = []
    ast_trees: Dict[str, ast.AST] = {}
    exported_map: Dict[str, Set[str]] = {}

    merged_chunks: List[str] = [
        "=" * 100,
        f"# 📦 Infinite Snowball v3.0 — Merged Python Core Code ({total_files} Files)",
        f"# 🕒 Generated At : {now_str}",
        f"# 📂 Source Dir   : {src_dir}",
        f"# 📄 Output File  : {out_file}",
        "# 📋 File List    : " + ", ".join(target_files),
        "=" * 100,
        "",
    ]

    for idx, fname in enumerate(target_files, start=1):
        fpath = os.path.join(src_dir, fname)
        mod_name = fname[:-3]
        with open(fpath, "r", encoding="utf-8", errors="replace") as rf:
            content = rf.read()

        # [Case 85]: f-string 닫는 중괄호('>' 오기) 선제 탐지
        broken_m = _FSTRING_BROKEN_BRACE_RE.search(content)
        if broken_m:
            syntax_errors.append(
                f"{fname}: Case 85 f-string 닫는 중괄호('>' 오기) 패턴 감지 ({broken_m.group(0)})"
            )

        # [Case 75, Case 85 & Case 93]: 디스크 쓰기 0 Byte 인메모리 컴파일 & AST 파싱 검증
        try:
            compile(content, fpath, "exec", dont_inherit=True)
            tree = ast.parse(content, filename=fpath)
            ast_trees[mod_name] = tree
            exported_map[mod_name] = _extract_module_exported_symbols(tree)
        except SyntaxError as syn_err:
            syntax_errors.append(
                f"{fname} (line {syn_err.lineno}): {syn_err.msg}"
            )
        except Exception as exc:
            syntax_errors.append(f"{fname}: 컴파일/AST 파싱 예외 ({exc})")

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

    # NEW: 15대 코어 모듈 간 from ... import ... 심볼 정합성 교차 검증 (plugin_updater.py 동일 규격)
    local_core_mods = {f[:-3] for f in CORE_MODULE_ORDER}
    for mod_name, tree in ast_trees.items():
        if mod_name not in local_core_mods:
            continue
        fname = f"{mod_name}.py"
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module in local_core_mods
                and node.module in exported_map
            ):
                target_mod = node.module
                target_exports = exported_map[target_mod]
                for alias in node.names:
                    sym = alias.name
                    if sym != "*" and sym not in target_exports:
                        import_errors.append(
                            f"{fname}: from {target_mod} import {sym} ('{target_mod}.py' 내 '{sym}' 미정의)"
                        )

    if (syntax_errors or import_errors) and not allow_partial:
        if syntax_errors:
            print(
                "\n🚨 [문법 검증 실패] 아래 파일에서 문법 오류가 감지되어 code.txt 덮어쓰기를 차단했습니다:",
                file=sys.stderr,
            )
            for err in syntax_errors:
                print(f"  - {err}", file=sys.stderr)
        if import_errors:
            print(
                "\n🚨 [AST 심볼 임포트 불일치] 코어 모듈 간 미정의 심볼 참조가 감지되어 code.txt 덮어쓰기를 차단했습니다:",
                file=sys.stderr,
            )
            for i_err in import_errors:
                print(f"  - {i_err}", file=sys.stderr)
        return 1

    footer = (
        f"\n{'=' * 100}\n"
        f"# ✅ END OF MERGED CODE — Total Files: {total_files} | "
        f"Total Lines: {total_lines:,} | Total Size: {total_bytes:,} bytes\n"
        f"{'=' * 100}\n"
    )
    merged_chunks.append(footer)
    final_text = "\n".join(merged_chunks)

    tmp_output = f"{out_file}.tmp.{os.getpid()}"
    try:
        with open(tmp_output, "w", encoding="utf-8") as wf:
            wf.write(final_text)
            wf.flush()
            os.fsync(wf.fileno())
        os.replace(tmp_output, out_file)
    finally:
        if os.path.exists(tmp_output):
            try:
                os.remove(tmp_output)
            except Exception:
                pass

    print(
        f"✅ [병합 및 AST 검증 완료] 총 {total_files}개 파일 ({total_lines:,}줄 · {total_bytes:,} bytes) ➔ {out_file}"
    )
    for idx, fname in enumerate(target_files, start=1):
        tag = "CORE" if fname in CORE_MODULE_ORDER else "EXTRA"
        print(f"  {idx:02d}. [{tag}] {fname}")

    return 0


def _parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Infinite Snowball v3.0 — 15 Core Python Modules Atomic Merger & AST Verifier"
    )
    parser.add_argument(
        "--src-dir",
        type=str,
        default=SOURCE_DIR,
        help=f"병합할 파이썬 소스 디렉토리 (기본값: {SOURCE_DIR})",
    )
    parser.add_argument(
        "--out-file",
        type=str,
        default=OUTPUT_FILE,
        help=f"병합 출력 파일 경로 (기본값: {OUTPUT_FILE})",
    )
    parser.add_argument(
        "--strict-core",
        action="store_true",
        help="15대 필수 코어 모듈만 엄격하게 병합하고 기타 .py 파일은 제외합니다.",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="누락 파일이나 문법 경고가 있어도 강제로 병합 파일을 생성합니다 (디버깅용).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    cli_args = _parse_cli_args()
    sys.exit(
        merge_python_files(
            src_dir=cli_args.src_dir,
            out_file=cli_args.out_file,
            allow_partial=cli_args.allow_partial,
            strict_core_only=cli_args.strict_core,
        )
    )
