# =====================================================================
# 파일명: tg_router.py
# 목적: 텔레그램 콜백 라우팅 및 온디맨드(On-Demand) 덫 해제 인터럽트 융합 (5분봉 및 퇴근 시스템 적용)
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
wakeup_event = None

def inject_dependencies(client, admin_id, event):
    global api_client, ADMIN_CHAT_ID, wakeup_event
    api_client = client
    ADMIN_CHAT_ID = admin_id
    wakeup_event = event

class ManualQtyState(StatesGroup):
    waiting_for_qty = State()

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
        
    await state.clear()
    
    _, _, _, _, _, is_active = await HAStateManager.get_state()
    # MODIFIED: 완전 차단 상태 텍스트 렌더링
    toggle_text = "🔴 봇 매매 정지 (현재 OFF)" if not is_active else "🟢 봇 매매 가동 (현재 ON)"
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 잔고 스캔", callback_data="scan_asset")],
        [InlineKeyboardButton(text="📈 SOXL 타점 및 방어망 스캔", callback_data="scan_ha")],
        [InlineKeyboardButton(text="⚙️ 타격 목표 수량 설정", callback_data="menu_set_qty")],
        [InlineKeyboardButton(text=toggle_text, callback_data="toggle_active")]
    ])
    
    welcome_text = (
        "🤖 <b>승승장군 퀀트 관제탑 가동</b>\n\n"
        "▫️ 시스템: Toss Securities V14 / V-REV 4.0 (EMA-10 Shield)\n"
        "▫️ 상태: Online 및 API 대기 중\n\n"
        "원하시는 명령을 선택하십시오."
    )
    
    try:
        await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        print(f"⚠️ [텔레그램 통신 붕괴 방어] 메인 메뉴 렌더링 실패: {e}")

@router.message(Command("reset"))
async def cmd_reset(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID:
        return

    try:
        await HAStateManager.save_state(price=0.0, target_sell_price=0.0, is_session_done=False)
        reset_text = (
            "✅ <b>로컬 장부 원자적 덮어쓰기 완료</b>\n\n"
            "▫️ <b>조치</b>: 포지션 단가, 방어선 강제 0.0 동기화 및 금일 퇴근 상태 해제\n"
            "▫️ <b>목적</b>: 과거 상태 오염 소각 및 신규 타점 스캔 락아웃 해제"
        )
        await message.answer(reset_text, parse_mode="HTML")
    except Exception as e:
        try:
            await message.answer(f"🚨 <b>장부 초기화 붕괴</b>: <pre>{html.escape(str(e))}</pre>", parse_mode="HTML")
        except Exception:
            pass

@router.callback_query(F.data == "toggle_active")
async def process_toggle_active(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_CHAT_ID:
        return
        
    try:
        _, _, _, _, _, is_active = await HAStateManager.get_state()
        new_state = not is_active
        await HAStateManager.save_state(is_active=new_state)
        
        if wakeup_event:
            wakeup_event.set()
            
        # MODIFIED: 완전 차단 상태 텍스트 렌더링
        status_text = "🟢 가동 재개 (매수/매도 전면 허용 락온)" if new_state else "🔴 수면 모드 (매수 및 매도 전면 차단 / 관망 모드 락온)"
        try:
            await callback_query.answer(f"✅ 상태 전환 완료: {status_text}", show_alert=False)
        except Exception:
            pass
            
        await process_back_to_main(callback_query, state)
    except Exception as e:
        try:
            await callback_query.message.edit_text(f"🚨 <b>상태 장부 기록 붕괴</b>\n\n▫️ {html.escape(str(e))}", parse_mode="HTML")
        except Exception:
            pass

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
        pass

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
        except Exception:
            pass
        return
    
    try:
        qty = int(action)
        await HAStateManager.save_state(target_qty=qty)
        try:
            await callback_query.answer(f"✅ {qty}주 타격 락온 완료. 다음 스캔부터 즉시 적용됩니다.", show_alert=False)
        except Exception:
            pass
            
        await process_back_to_main(callback_query, state)
    except Exception as e:
        try:
            await callback_query.message.edit_text(f"🚨 <b>상태 장부 기록 붕괴</b>\n\n▫️ {html.escape(str(e))}", parse_mode="HTML")
        except Exception:
            pass

@router.message(ManualQtyState.waiting_for_qty)
async def process_manual_qty_input(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
        
    qty_str = message.text.strip()
    
    if not qty_str.isdigit():
        try:
            await message.answer("🚨 <b>수량은 양의 정수만 입력 가능합니다.</b> 다시 숫자만 입력해 주십시오.", parse_mode="HTML")
        except Exception:
            pass
        return
        
    qty = int(qty_str)
    
    if not (1 <= qty <= 1000):
        try:
            await message.answer("🚨 <b>수량은 1주에서 1,000주 사이로 캡핑되어야 합니다.</b> 다시 입력해 주십시오.", parse_mode="HTML")
        except Exception:
            pass
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
        except Exception:
            pass
    except Exception as e:
        try:
            await message.answer(f"🚨 <b>상태 장부 기록 붕괴</b>: <pre>{html.escape(str(e))}</pre>", parse_mode="HTML")
        except Exception:
            pass

@router.message(Command("update"))
async def cmd_update(message: types.Message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return

    try:
        await message.answer("⏳ <b>레스큐 모듈(plugin_updater.py) 격발. 깃허브 원장 동기화 및 프리플라이트 검증 진행 중...</b>", parse_mode="HTML")
        
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
            await message.answer(result_msg, parse_mode="HTML")
            
            if "Already up to date." not in out_text:
                await message.answer("⚠️ <b>검증된 새 코어 코드 감지. 데몬을 즉시 재가동(Restart)합니다.</b>", parse_mode="HTML")
                await asyncio.sleep(1)
                os._exit(0)
        else:
            result_msg = (
                f"🚨 <b>치명적 에러 감지 및 레스큐 롤백 완료</b>\n\n"
                f"▫️ <b>본진 프로세스(main.py)는 죽지 않고 생존 상태를 유지합니다.</b>\n"
                f"▫️ <b>STDERR (문법 에러 원인)</b>:\n<pre>{safe_err}</pre>\n"
                f"▫️ <b>STDOUT (복구 로그)</b>:\n<pre>{safe_out}</pre>"
            )
            await message.answer(result_msg, parse_mode="HTML")
            
    except Exception as e:
        try:
            await message.answer(f"🚨 <b>관제탑 업데이트 통신 붕괴 감지</b>:\n<pre>{html.escape(str(e))}</pre>", parse_mode="HTML")
        except Exception:
            pass

@router.callback_query(F.data == "scan_asset")
async def process_scan_asset(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_CHAT_ID:
        return

    await state.clear()
    
    try:
        open_orders = await api_client.get_orders(status="OPEN", symbol="SOXL")
        if open_orders:
            for order in open_orders:
                await api_client.cancel_order(order["orderId"])
            if wakeup_event:
                wakeup_event.set()
                await callback_query.answer("🧹 Limit-Trap 감지 및 강제 해제! 즉각 재타격을 스캔합니다.", show_alert=False)
            return
        else:
            await callback_query.answer("⏳ 잔고 원장 동기화 중...", show_alert=False)
    except Exception:
        pass
    
    try:
        holdings_task = api_client.get_soxl_holdings_detail()
        rate_task = api_client.get_usd_to_krw_rate()
        usd_bp_task = api_client.get_usd_buying_power()
        current_price_task = api_client.get_current_price("SOXL")
        target_qty_task = HAStateManager.get_state()
        
        holdings, ex_rate, usd_bp, current_price, state_tuple = await asyncio.gather(
            holdings_task, rate_task, usd_bp_task, current_price_task, target_qty_task
        )
        
        _, target_qty, target_sell_price, _, is_session_done, is_active = state_tuple
        
        est_now = datetime.now(ZoneInfo('America/New_York')).strftime("%Y-%m-%d %H:%M:%S")
        
        krw_profit = holdings["profit_usd"] * ex_rate
        profit_rate_pct = holdings["profit_rate"] * 100
        
        # MODIFIED: 완전 차단 상태 텍스트 렌더링
        result_text = (
            f"📊 <b>계좌 자산 스캔 완료</b>\n\n"
            f"🔹 <b>기준 시각</b>: {html.escape(est_now)} EST\n"
            f"🔹 <b>봇 매매 상태</b>: {'🟢 ON (매매 허용)' if is_active else '🔴 OFF (매수 및 매도 전면 차단)'}\n"
            f"🔹 <b>금일 퇴근 여부</b>: {'🔴 업무 종료 (수익 달성)' if is_session_done else '🟢 영업 중'}\n"
            f"🔹 <b>매수 가능 달러</b>: ${usd_bp:,.2f}\n"
            f"🔹 <b>SOXL 보유 수량</b>: {holdings['qty']:,.2f}주\n"
            f"🔹 <b>SOXL 타격 목표 수량</b>: {target_qty}주\n"
            f"🔹 <b>거시 추세 방어선</b>: ${target_sell_price:,.2f} (EMA 10 락온)\n"
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
        except Exception:
            pass
        
    except Exception as e:
        try:
            await callback_query.message.edit_text(f"🚨 <b>시스템 붕괴 감지</b>\n\n▫️ {html.escape(str(e))}", parse_mode="HTML")
        except Exception:
            pass

@router.callback_query(F.data == "scan_ha")
async def process_scan_ha(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_CHAT_ID:
        return

    await state.clear()
    
    try:
        open_orders = await api_client.get_orders(status="OPEN", symbol="SOXL")
        if open_orders:
            for order in open_orders:
                await api_client.cancel_order(order["orderId"])
            if wakeup_event:
                wakeup_event.set()
                await callback_query.answer("🧹 Limit-Trap 감지 및 강제 해제! 즉각 재타격을 스캔합니다.", show_alert=False)
            return
        else:
            await callback_query.answer("⏳ 시세 타격 및 HA 벡터 엔진 가동 중...", show_alert=False)
    except Exception:
        pass
    
    try:
        is_open_task = api_client.is_market_open()
        current_price_task = api_client.get_current_price("SOXL")
        candles_task = api_client.get_1m_candles("SOXL", count=200)
        daily_candles_task = api_client.get_daily_candles("SOXL", count=6)
        
        is_open_tuple, current_price, candles_json, daily_candles_json = await asyncio.gather(
            is_open_task, current_price_task, candles_task, daily_candles_task
        )
        
        is_open, session_end_time, session_name, session_start_time = is_open_tuple
        ha_df = HeikinAshiEngine.calculate_5m_ha(candles_json)
        avg_stamina = HeikinAshiEngine.calculate_amplitude_stamina(daily_candles_json)
        
        now_est = datetime.now(ZoneInfo('America/New_York'))
        est_now_str = now_est.strftime("%Y-%m-%d %H:%M:%S")
        
        if len(ha_df) < 4:
            result_text = f"🚨 <b>캔들 데이터 붕괴 (최소 4배열 미달)</b>\n\n🔹 <b>기준 시각</b>: {html.escape(est_now_str)} EST\n🔹 <b>실시간 종가</b>: ${current_price:.2f}"
        else:
            current_amp = 0.0
            gap_shield_active = False
            shield_status_text = "🔴 해제됨 (개장 60분 경과 혹은 진행장 아님)"
            stamina_status_text = "🟢 정상 (진입 가능)"
            
            session_map = {
                "dayMarket": "데이마켓 (Day Market)",
                "preMarket": "프리마켓 (Pre Market)",
                "regularMarket": "정규장 (Regular Market)",
                "afterMarket": "애프터마켓 (After Market)"
            }
            session_display = session_map.get(session_name, "알 수 없음") if is_open else "휴장 (Closed)"
            
            trend_text = "➖ 횡보장 (Neutral)"
            c2_ema5 = ha_df.iloc[-2]['EMA_5']
            c2_ema10 = ha_df.iloc[-2]['EMA_10']
            if c2_ema5 > c2_ema10:
                trend_text = "📈 상승장 (Up-Trend)"
            elif c2_ema5 < c2_ema10:
                trend_text = "📉 하락장 (Down-Trend)"
            
            if is_open and session_start_time is not None:
                session_start_est = session_start_time.astimezone(ZoneInfo('America/New_York'))
                session_candles = ha_df[ha_df.index >= session_start_est]
                
                if not session_candles.empty:
                    current_amp = await HeikinAshiEngine.get_dynamic_session_amp(session_start_est, session_name, session_candles)
                    
                    elapsed_sec = (now_est - session_start_est).total_seconds()
                    if elapsed_sec <= 3600:
                        c0 = session_candles.iloc[-1]
                        session_open_price = session_candles.iloc[0]['HA_Open']
                        
                        if (c0['HA_Close'] < c0['HA_Open']) or (c0['HA_Close'] < session_open_price):
                            gap_shield_active = True
                            shield_status_text = "🟢 가동 중 (음봉 하락 팩트 감지. 타점 소각)"
                        else:
                            shield_status_text = "🟡 대기 중 (상승 팩트 도출)"
                            
            if (avg_stamina > 0.0) and (current_amp >= avg_stamina * 0.95):
                stamina_status_text = "🔴 체력 소진 (타점 소각)"
            
            recent_ha = ha_df.tail(10)
            ha_history_text = ""
            for time_idx, row in recent_ha.iterrows():
                ha_o = row['HA_Open']
                ha_c = row['HA_Close']
                ha_time_str = time_idx.strftime("%H:%M")
                candle_icon = "🟥 양봉" if ha_c >= ha_o else "🟦 음봉"
                ha_history_text += f"🔸 [{ha_time_str}] {candle_icon} ${ha_c:.2f}\n"
                
            result_text = (
                f"📈 <b>SOXL 퀀트 타점 및 체력 스캔 완료</b>\n\n"
                f"🔹 <b>스캔 시각</b>: {html.escape(est_now_str)} EST\n"
                f"🔹 <b>실시간 종가 (Tick)</b>: <b>${current_price:.2f}</b>\n"
                f"🔹 <b>진행 세션</b>: {session_display}\n"
                f"🔹 <b>거시 장세 (EMA)</b>: {trend_text}\n\n"
                f"🛡️ <b>[HA 암살자 엣지 방어망 상태]</b>\n"
                f"🔸 <b>5일 평균 진폭 (체력 한계)</b>: {avg_stamina*100:.2f}%\n"
                f"🔸 <b>현재 세션 진폭 (소진 체력)</b>: {current_amp*100:.2f}%\n"
                f"🔸 <b>체력 고갈 여부</b>: {stamina_status_text}\n"
                f"🔸 <b>세션 경계 갭 쉴드</b>: {shield_status_text}\n\n"
                f"📊 <b>최근 5분봉 HA 흐름 (최대 10개)</b>\n"
                f"{ha_history_text}"
            )
            
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 다시 스캔하기", callback_data="scan_ha")],
            [InlineKeyboardButton(text="🔙 메인 메뉴", callback_data="back_to_main")]
        ])
        
        try:
            await callback_query.message.edit_text(result_text, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            pass
        
    except Exception as e:
        try:
            await callback_query.message.edit_text(f"🚨 <b>연산 엔진 붕괴 감지</b>\n\n▫️ {html.escape(str(e))}", parse_mode="HTML")
        except Exception:
            pass

@router.callback_query(F.data == "back_to_main")
async def process_back_to_main(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_CHAT_ID:
        return
        
    await state.clear()
    
    _, _, _, _, _, is_active = await HAStateManager.get_state()
    # MODIFIED: 완전 차단 상태 텍스트 렌더링
    toggle_text = "🔴 봇 매매 정지 (현재 OFF)" if not is_active else "🟢 봇 매매 가동 (현재 ON)"
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 잔고 스캔", callback_data="scan_asset")],
        [InlineKeyboardButton(text="📈 SOXL 타점 및 방어망 스캔", callback_data="scan_ha")],
        [InlineKeyboardButton(text="⚙️ 타격 목표 수량 설정", callback_data="menu_set_qty")],
        [InlineKeyboardButton(text=toggle_text, callback_data="toggle_active")]
    ])
    
    welcome_text = (
        "🤖 <b>승승장군 퀀트 관제탑 가동</b>\n\n"
        "▫️ 시스템: Toss Securities V14 / V-REV 4.0 (EMA-10 Shield)\n"
        "▫️ 상태: Online 및 API 대기 중\n\n"
        "원하시는 명령을 선택하십시오."
    )
    
    try:
        await callback_query.message.edit_text(welcome_text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        pass
