# =====================================================================
# 파일명: tg_router.py
# 목적: 텔레그램 메인 메뉴, 콜백, FSM 라우팅 전담 및 네트워크 예외(Errno 104) 철저 격리
# =====================================================================

import asyncio
import os
import sys
import html
from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from quant_engine import HAStateManager, HeikinAshiEngine

router = Router()

api_client = None
ADMIN_CHAT_ID = None

def inject_dependencies(client, admin_id):
    global api_client, ADMIN_CHAT_ID
    api_client = client
    ADMIN_CHAT_ID = admin_id

class ManualQtyState(StatesGroup):
    waiting_for_qty = State()

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
        
    await state.clear()
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 잔고 스캔", callback_data="scan_asset")],
        [InlineKeyboardButton(text="📈 SOXL 실시간 & 3분봉 HA 스캔", callback_data="scan_ha")],
        [InlineKeyboardButton(text="⚙️ 타격 목표 수량 설정", callback_data="menu_set_qty")]
    ])
    
    welcome_text = (
        "🤖 <b>승승장군 퀀트 관제탑 가동</b>\n\n"
        "▫️ 시스템: Toss Securities V14 / V-REV (Up-Trend Engine)\n"
        "▫️ 상태: Online 및 API 대기 중\n\n"
        "원하시는 명령을 선택하십시오."
    )
    
    try:
        await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        print(f"⚠️ [텔레그램 통신 붕괴 방어] 메인 메뉴 렌더링 실패: {e}")

@router.callback_query(F.data == "menu_set_qty")
async def process_menu_set_qty(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_CHAT_ID:
        return

    await state.clear()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1주", callback_data="set_qty_1"),
            InlineKeyboardButton(text="10주", callback_data="set_qty_10"),
            InlineKeyboardButton(text="수동", callback_data="set_qty_manual")
        ],
        [InlineKeyboardButton(text="🔙 뒤로가기", callback_data="back_to_main")]
    ])
    
    text = (
        "⚙️ <b>타격 목표 수량 설정</b>\n\n"
        "▫️ 원하시는 목표 수량을 퀵 프리셋에서 선택하십시오.\n"
        "▫️ <b>[수동]</b> 버튼을 누르시면 채팅창에서 숫자를 직접 입력할 수 있습니다."
    )
    
    try:
        await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        print(f"⚠️ [텔레그램 통신 붕괴 방어] 수량 설정 메뉴 렌더링 실패: {e}")

@router.callback_query(F.data.startswith("set_qty_"))
async def process_set_qty_action(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_CHAT_ID:
        return
    
    action = callback_query.data.split("_")[-1]
    
    if action == "manual":
        await state.set_state(ManualQtyState.waiting_for_qty)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 취소 및 뒤로가기", callback_data="menu_set_qty")]
        ])
        
        text = (
            "⌨️ <b>수동 수량 입력 모드</b>\n\n"
            "▫️ 채팅창에 원하시는 타격 수량(숫자)만 입력하여 전송해 주십시오.\n"
            "▫️ <i>예시: 15</i>"
        )
        try:
            await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as e:
            print(f"⚠️ [텔레그램 통신 붕괴 방어] 수동 입력 UI 렌더링 실패: {e}")
        return
    
    try:
        qty = int(action)
        await HAStateManager.save_state(target_qty=qty)
        try:
            await callback_query.answer(f"✅ {qty}주 타격 락온 완료. 다음 스캔부터 즉시 적용됩니다.", show_alert=False)
        except Exception as e:
            print(f"⚠️ [텔레그램 통신 붕괴 방어] 토스트 알림 실패: {e}")
            
        await process_back_to_main(callback_query, state)
        
    except Exception as e:
        error_msg = html.escape(str(e))
        try:
            await callback_query.message.edit_text(f"🚨 <b>상태 장부 기록 붕괴</b>\n\n▫️ {error_msg}", parse_mode="HTML")
        except Exception as ex:
            print(f"🚨 [텔레그램 통신 붕괴 방어] 에러 렌더링 실패: {ex}")

@router.message(ManualQtyState.waiting_for_qty)
async def process_manual_qty_input(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
        
    qty_str = message.text.strip()
    
    if not qty_str.isdigit():
        try:
            await message.answer("🚨 <b>수량은 양의 정수만 입력 가능합니다.</b> 다시 숫자만 입력해 주십시오.", parse_mode="HTML")
        except Exception as e:
            print(f"⚠️ [텔레그램 통신 붕괴 방어] 예외 렌더링 실패: {e}")
        return
        
    qty = int(qty_str)
    
    if not (1 <= qty <= 1000):
        try:
            await message.answer("🚨 <b>수량은 1주에서 1,000주 사이로 캡핑되어야 합니다.</b> 다시 입력해 주십시오.", parse_mode="HTML")
        except Exception as e:
            print(f"⚠️ [텔레그램 통신 붕괴 방어] 예외 렌더링 실패: {e}")
        return
        
    try:
        await HAStateManager.save_state(target_qty=qty)
        await state.clear()
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 메인 메뉴", callback_data="back_to_main")]
        ])
        
        success_text = (
            f"✅ <b>수동 타격 수량 동기화 완료</b>\n\n"
            f"▫️ <b>변경 수량</b>: {qty}주\n"
            f"▫️ <b>적용 시점</b>: 다음 1분 스캔 주기부터 즉시 락온"
        )
        try:
            await message.answer(success_text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as e:
            print(f"⚠️ [텔레그램 통신 붕괴 방어] 성공 렌더링 실패: {e}")
    except Exception as e:
        safe_error = html.escape(str(e))
        try:
            await message.answer(f"🚨 <b>상태 장부 기록 붕괴</b>: <pre>{safe_error}</pre>", parse_mode="HTML")
        except Exception as ex:
            print(f"⚠️ [텔레그램 통신 붕괴 방어] 에러 렌더링 실패: {ex}")

@router.message(Command("update"))
async def cmd_update(message: types.Message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return

    try:
        await message.answer("⏳ <b>레스큐 모듈(plugin_updater.py) 격발. 깃허브 원장 동기화 및 프리플라이트 검증 진행 중...</b>", parse_mode="HTML")
    except Exception as e:
        print(f"⚠️ [텔레그램 통신 붕괴 방어] 업데이트 시작 알림 실패: {e}")
    
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, "plugin_updater.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        out_text = stdout.decode('utf-8').strip()
        err_text = stderr.decode('utf-8').strip()
        
        safe_out = html.escape(out_text) if out_text else "출력 없음"
        safe_err = html.escape(err_text) if err_text else "에러 없음"
        
        if process.returncode == 0:
            result_msg = (
                f"✅ <b>업데이트 및 검증 통과</b>\n\n"
                f"▫️ <b>STDOUT</b>:\n<pre>{safe_out}</pre>"
            )
            try:
                await message.answer(result_msg, parse_mode="HTML")
            except Exception as e:
                print(f"⚠️ [텔레그램 통신 붕괴 방어] 업데이트 결과 알림 실패: {e}")
            
            if "Already up to date." not in out_text:
                try:
                    await message.answer("⚠️ <b>검증된 새 코어 코드 감지. 데몬을 즉시 재가동(Restart)합니다.</b>", parse_mode="HTML")
                except Exception as e:
                    print(f"⚠️ [텔레그램 통신 붕괴 방어] 재가동 알림 실패: {e}")
                await asyncio.sleep(1)
                os._exit(0)
        else:
            result_msg = (
                f"🚨 <b>치명적 에러 감지 및 레스큐 롤백 완료</b>\n\n"
                f"▫️ <b>본진 프로세스(main.py)는 죽지 않고 생존 상태를 유지합니다.</b>\n"
                f"▫️ <b>STDERR (문법 에러 원인)</b>:\n<pre>{safe_err}</pre>\n"
                f"▫️ <b>STDOUT (복구 로그)</b>:\n<pre>{safe_out}</pre>"
            )
            try:
                await message.answer(result_msg, parse_mode="HTML")
            except Exception as e:
                print(f"⚠️ [텔레그램 통신 붕괴 방어] 롤백 알림 실패: {e}")
            
    except Exception as e:
        safe_error = html.escape(str(e))
        try:
            await message.answer(f"🚨 <b>관제탑 업데이트 통신 붕괴 감지</b>:\n<pre>{safe_error}</pre>", parse_mode="HTML")
        except Exception as ex:
            print(f"⚠️ [텔레그램 통신 붕괴 방어] 붕괴 알림 실패: {ex}")

@router.callback_query(F.data == "scan_asset")
async def process_scan_asset(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_CHAT_ID:
        return

    await state.clear()
    
    try:
        await callback_query.answer("⏳ 잔고 원장 동기화 중...", show_alert=False)
    except Exception as e:
        print(f"⚠️ [텔레그램 통신 붕괴 방어] 잔고 스캔 토스트 알림 실패 (무시 후 스캔 강행): {e}")
    
    try:
        holdings_task = api_client.get_soxl_holdings_detail()
        rate_task = api_client.get_usd_to_krw_rate()
        usd_bp_task = api_client.get_usd_buying_power()
        current_price_task = api_client.get_current_price("SOXL")
        target_qty_task = HAStateManager.get_state()
        
        holdings, ex_rate, usd_bp, current_price, state_tuple = await asyncio.gather(
            holdings_task, rate_task, usd_bp_task, current_price_task, target_qty_task
        )
        
        # MODIFIED: 2-Tier 언패킹 규격 적용 (Rule 4 소각)
        _, target_qty = state_tuple
        
        est_now = datetime.now(ZoneInfo('America/New_York')).strftime("%Y-%m-%d %H:%M:%S")
        safe_est = html.escape(est_now)
        
        krw_profit = holdings["profit_usd"] * ex_rate
        profit_rate_pct = holdings["profit_rate"] * 100
        
        result_text = (
            f"📊 <b>계좌 자산 스캔 완료</b>\n\n"
            f"🔹 <b>기준 시각</b>: {safe_est} EST\n"
            f"🔹 <b>매수 가능 달러</b>: ${usd_bp:,.2f}\n"
            f"🔹 <b>SOXL 보유 수량</b>: {holdings['qty']:,.2f}주\n"
            f"🔹 <b>SOXL 타격 목표 수량</b>: {target_qty}주 (EMA 필터 가동 중)\n"
            f"🔹 <b>총 평단가</b>: ${holdings['avg_price']:,.2f}\n"
            f"🔹 <b>실시간 종가</b>: ${current_price:,.2f}\n"
            f"🔹 <b>수익률</b>: {profit_rate_pct:+,.2f}% (${holdings['profit_usd']:+,.2f} / ₩{krw_profit:+,.0f})\n"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 다시 스캔하기", callback_data="scan_asset")],
            [InlineKeyboardButton(text="🔙 메인 메뉴", callback_data="back_to_main")]
        ])
        
        try:
            await callback_query.message.edit_text(result_text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as e:
            print(f"⚠️ [텔레그램 통신 붕괴 방어] 잔고 스캔 UI 렌더링 실패: {e}")
        
    except Exception as e:
        error_msg = html.escape(str(e))
        try:
            await callback_query.message.edit_text(f"🚨 <b>시스템 붕괴 감지</b>\n\n▫️ {error_msg}", parse_mode="HTML")
        except Exception as ex:
            print(f"🚨 [텔레그램 통신 붕괴 방어] 잔고 스캔 에러 렌더링 실패: {ex}")

@router.callback_query(F.data == "scan_ha")
async def process_scan_ha(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_CHAT_ID:
        return

    await state.clear()
    
    try:
        await callback_query.answer("⏳ 시세 타격 및 HA 벡터 엔진 가동 중...", show_alert=False)
    except Exception as e:
        print(f"⚠️ [텔레그램 통신 붕괴 방어] HA 스캔 토스트 알림 실패 (무시 후 스캔 강행): {e}")
    
    try:
        current_price_task = api_client.get_current_price("SOXL")
        candles_task = api_client.get_1m_candles("SOXL", count=200)
        
        current_price, candles_json = await asyncio.gather(current_price_task, candles_task)
        
        ha_df = HeikinAshiEngine.calculate_3m_ha(candles_json)
        
        est_now = datetime.now(ZoneInfo('America/New_York')).strftime("%Y-%m-%d %H:%M:%S")
        safe_est = html.escape(est_now)
        
        if ha_df.empty:
            result_text = f"🚨 <b>캔들 데이터 붕괴 (빈 배열)</b>\n\n🔹 <b>기준 시각</b>: {safe_est} EST\n🔹 <b>실시간 종가</b>: ${current_price:.2f}"
        else:
            recent_ha = ha_df.tail(10)
            ha_history_text = ""
            
            for time_idx, row in recent_ha.iterrows():
                ha_o = row['HA_Open']
                ha_c = row['HA_Close']
                ha_time_str = time_idx.strftime("%H:%M")
                
                if ha_c >= ha_o:
                    candle_icon = "🟥 양봉"
                else:
                    candle_icon = "🟦 음봉"
                    
                ha_history_text += f"🔸 [{ha_time_str}] {candle_icon} ${ha_c:.2f}\n"
                
            result_text = (
                f"📈 <b>SOXL 시세 및 하이킨 아시 스캔 완료</b>\n\n"
                f"🔹 <b>스캔 시각</b>: {safe_est} EST\n"
                f"🔹 <b>실시간 종가 (Tick)</b>: <b>${current_price:.2f}</b>\n\n"
                f"📊 <b>최근 3분봉 HA 흐름 (최대 10개)</b>\n"
                f"{ha_history_text}"
            )
            
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 다시 스캔하기", callback_data="scan_ha")],
            [InlineKeyboardButton(text="🔙 메인 메뉴", callback_data="back_to_main")]
        ])
        
        try:
            await callback_query.message.edit_text(result_text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as e:
            print(f"⚠️ [텔레그램 통신 붕괴 방어] HA 스캔 UI 렌더링 실패: {e}")
        
    except Exception as e:
        error_msg = html.escape(str(e))
        try:
            await callback_query.message.edit_text(f"🚨 <b>연산 엔진 붕괴 감지</b>\n\n▫️ {error_msg}", parse_mode="HTML")
        except Exception as ex:
            print(f"🚨 [텔레그램 통신 붕괴 방어] HA 스캔 에러 렌더링 실패: {ex}")

@router.callback_query(F.data == "back_to_main")
async def process_back_to_main(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_CHAT_ID:
        return
        
    await state.clear()
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 잔고 스캔", callback_data="scan_asset")],
        [InlineKeyboardButton(text="📈 SOXL 실시간 & 3분봉 HA 스캔", callback_data="scan_ha")],
        [InlineKeyboardButton(text="⚙️ 타격 목표 수량 설정", callback_data="menu_set_qty")]
    ])
    
    welcome_text = (
        "🤖 <b>승승장군 퀀트 관제탑 가동</b>\n\n"
        "▫️ 시스템: Toss Securities V14 / V-REV (Up-Trend Engine)\n"
        "▫️ 상태: Online 및 API 대기 중\n\n"
        "원하시는 명령을 선택하십시오."
    )
    
    try:
        await callback_query.message.edit_text(welcome_text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        print(f"⚠️ [텔레그램 통신 붕괴 방어] 메인 메뉴 복귀 UI 렌더링 실패: {e}")
