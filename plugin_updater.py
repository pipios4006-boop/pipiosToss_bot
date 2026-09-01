# =====================================================================
# FILE: plugin_updater.py
# 목적: 깃허브 코드 다운로드 검증 및 롤백 (프리플라이트 파이썬 컴파일)
# =====================================================================

import os
import subprocess
import sys
import py_compile

def run_command(command: str) -> tuple[int, str, str]:
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate()
    return process.returncode, stdout.strip(), stderr.strip()

def main():
    code, current_hash, err = run_command("git rev-parse HEAD")
    if code != 0:
        print("🚨 해시 백업 실패. 업데이트를 중단합니다.", file=sys.stderr)
        sys.exit(1)
    
    print(f"✅ 현재 정상 해시 백업 완료: {current_hash}")

    code, pull_out, pull_err = run_command("git pull origin main")
    print(pull_out)
    
    if code != 0:
        print(f"🚨 Pull 네트워크 붕괴: {pull_err}", file=sys.stderr)
        run_command(f"git reset --hard {current_hash}")
        sys.exit(1)

    if "Already up to date." in pull_out:
        sys.exit(0)

    try:
        py_compile.compile('main.py', doraise=True)
        py_compile.compile('tg_router.py', doraise=True)
        py_compile.compile('quant_engine.py', doraise=True)
        py_compile.compile('toss_api.py', doraise=True)
        py_compile.compile('candle_recorder.py', doraise=True)
        print("✅ 프리플라이트 파이썬 컴파일 검증 통과.")
        sys.exit(0)
    except py_compile.PyCompileError as e:
        print(f"🚨 치명적 문법 에러 감지. 레스큐 롤백 즉시 가동:\n{e}", file=sys.stderr)
        reset_code, reset_out, reset_err = run_command(f"git reset --hard {current_hash}")
        if reset_code == 0:
            print("✅ 롤백 성공. 이전 정상 코드로 파일 시스템 복구 완료.", file=sys.stderr)
        else:
            print(f"🚨 롤백 실패. 시스템 권한 붕괴: {reset_err}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
