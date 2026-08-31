# =====================================================================
# 파일명: tg_router.py
# 목적: SOXL, SOXS 듀얼 상태 제어 UI, 스케줄/명령어 라우팅 및 방어망 결속
# =====================================================================

import os
import html
import asyncio
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from quant_engine import AssassinLedger

router = Router()
api_client = None
ADMIN_CHAT_ID = None
wakeup_event = None

def inject_dependencies(client, admin_id, event):
    global api_client, ADMIN_CHAT_ID, wakeup_event
    api_client = client
    ADMIN_CHAT_ID = admin_id
    wakeup_event = event

class BudgetState(StatesGroup):
    waiting_for_budget = State()
    symbol = None

def get_main_menu_text() -> str:
    now_est = datetime.now(ZoneInfo('America/New_York'))
    is_dst = now_est.dst() is not None and now_est.dst().total_seconds() != 0
    dst_status_text = "🌞서머타임 ON (EDT)" if is_dst else "❄️서머타임 OFF (EST)"
    
    return (
        f"🕒 <b>[ 운영 스케줄 ({dst_status_text}) ]</b>\n"
        "🔹 19:00: ☀️ 데이장 (Day Market) 스캔 개시\n"
        "🔹 04:00: 🌅 프리장 VWAP 스캔 개시\n"
        "🔹 09:30: 🔥 정규장 VWAP 초기화 및 스캔\n"
        "🔹 15:59: 🛑 암살자 오버나이트 강제 덤핑\n"
        "🔹 16:05: 📝 정산 스캔 & 당일 사이클 졸업\n\n"
        "🛠 <b>[ 핵심 명령어 ]</b>\n"
        "▶️ /avwap : 🔫 데이 트레이딩 레이더 관제탑\n"
        "▶️ /sync : 📜 통합 지시서 및 장부 동기화\n"
        "▶️ /settlement : ⚙️ 통합 전술 제어반 (시드/OVN/가동)\n\n"
        "⚠️ /update : 🚀 깃허브 게시판 파이썬 코드 다운로드 및 구글 클라우드 서버 탑재"
    )

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    await state.clear()
    
    try:
        await message.answer(get_main_menu_text(), parse_mode="HTML")
    except Exception:
        pass

def parse_session_data(all_candles: list, session_start_est: datetime) -> dict:
    res = {
        "day_h": 0.0, "day_l": 0.0, "day_amp": 0.0, "day_vwap": 0.0,
        "pre_h": 0.0, "pre_l": 0.0, "pre_amp": 0.0, "pre_vwap": 0.0,
        "reg_h": 0.0, "reg_l": 0.0, "reg_amp": 0.0, "reg_vwap": 0.0
    }
    if not all_candles: return res
    
    df = pd.DataFrame(all_candles)
    if df.empty: return res
    
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601', utc=True).dt.tz_convert(ZoneInfo('America/New_York'))
    df.set_index('timestamp', inplace=True)
    df.sort_index(ascending=True, inplace=True)
    
    for col in ['openPrice', 'highPrice', 'lowPrice', 'closePrice', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            
    df = df[df.index >= session_start_est]
    if df.empty: return res
    
    day_df = df.between_time('19:00', '03:59') 
    pre_df = df.between_time('04:00', '09:29')
    reg_df = df.between_time('09:30', '16:00')
    
    def calc_metrics(sub_df):
        if sub_df.empty: return 0.0, 0.0, 0.0, 0.0
        h = float(sub_df['highPrice'].max())
        l = float(sub_df['lowPrice'].min())
        amp = ((h - l) / l * 100) if l > 0 else 0.0
        tp = (sub_df['highPrice'] + sub_df['lowPrice'] + sub_df['closePrice']) / 3.0
        pv = tp * sub_df['volume']
        vol = sub_df['volume'].sum()
        vwap = float(pv.sum() / vol) if vol > 0 else 0.0
        return h, l, float(amp), vwap

    day_h, day_l, day_amp, day_vwap = calc_metrics(day_df)
    pre_h, pre_l, pre_amp, pre_vwap = calc_metrics(pre_df)
    reg_h, reg_l, reg_amp, reg_vwap = calc_metrics(reg_df)
    
    res.update({
        "day_h": day_h, "day_l": day_l, "day_amp": day_amp, "day_vwap": day_vwap,
        "pre_h": pre_h, "pre_l": pre_l, "pre_amp": pre_amp, "pre_vwap": pre_vwap,
        "reg_h": reg_h, "reg_l": reg_l, "reg_amp": reg_amp, "reg_vwap": reg_vwap
    })
    return res

async def build_avwap_radar() -> tuple[str, InlineKeyboardMarkup]:
    now_est = datetime.now(ZoneInfo('America/New_York'))
    
    t = now_est.hour * 100 + now_est.minute
    if 400 <= t <= 929:
        session_name_ui = "preMarket"
        market_header = "🌅 프리마켓"
    elif 930 <= t <= 1559:
        session_name_ui = "regularMarket"
        market_header = "🔥 정규장"
    elif 1600 <= t <= 1859:
        session_name_ui = "afterMarket"
        market_header = "🌙 장마감"
    else:
        session_name_ui = "dayMarket"
        # MODIFIED: 데이장 이모지 독립화 (☀️ 적용)
        market_header = "☀️ 데이마켓"

    price_l = await api_client.get_current_price("SOXL")
    price_s = await api_client.get_current_price("SOXS")
    
    hold_l = await api_client.get_symbol_holdings_detail("SOXL")
    hold_s = await api_client.get_symbol_holdings_detail("SOXS")

    def calc_profit_str(hold, price):
        qty = float(hold.get('qty', 0.0))
        avg = float(hold.get('avg_price', 0.0))
        if qty > 0 and avg > 0:
            rate = (price - avg) / avg * 100
            return f"${avg:.2f}({rate:+.2f}%)"
        return "$0.00(0.00%)"

    profit_l_str = calc_profit_str(hold_l, price_l)
    profit_s_str = calc_profit_str(hold_s, price_s)

    async def fetch_5ma_amp(symbol):
        try:
            endpoint = f"/api/v1/candles?symbol={symbol}&interval=1d&count=5"
            data = await api_client._request("GET", endpoint, "MARKET_DATA_CHART", headers=api_client._get_headers())
            candles = data.get("result", {}).get("candles", [])
            amps = []
            for c in candles:
                h = float(c.get("highPrice", 0))
                l = float(c.get("lowPrice", 0))
                if l > 0: amps.append((h - l) / l * 100)
            return sum(amps) / len(amps) if amps else 0.0
        except Exception:
            return 0.0

    amp_l = await fetch_5ma_amp("SOXL")
    amp_s = await fetch_5ma_amp("SOXS")

    async def fetch_session_stats(symbol):
        all_candles = []
        before = None
        
        if now_est.hour >= 19:
            session_start_est = now_est.replace(hour=19, minute=0, second=0, microsecond=0)
        else:
            session_start_est = (now_est - timedelta(days=1)).replace(hour=19, minute=0, second=0, microsecond=0)
        
        for _ in range(10):
            try:
                data = await api_client.get_1m_candles_pagination(symbol, count=200, before=before)
                candles = data.get("candles", [])
                all_candles.extend(candles)
                if not candles: break
                oldest_time = pd.to_datetime(candles[-1]['timestamp'], utc=True).tz_convert(ZoneInfo('America/New_York'))
                if oldest_time <= session_start_est: break
                before = data.get("nextBefore")
                if not before: break
            except Exception:
                break
        return await asyncio.to_thread(parse_session_data, all_candles, session_start_est)

    sess_l = await fetch_session_stats("SOXL")
    sess_s = await fetch_session_stats("SOXS")

    _, budget_l, _, is_done_l, is_active_l, ovn_l, _ = await AssassinLedger.get_state("SOXL")
    _, budget_s, _, is_done_s, is_active_s, ovn_s, _ = await AssassinLedger.get_state("SOXS")

    def build_compact_status(symbol_short, is_active, budget, ovn, is_done, current_session, est_time):
        if not is_active:
            return f"⚠️ <b>[{symbol_short} OFF]</b> 대기 중"

        if is_done:
            state_text = "당일 타격 완료"
        else:
            if current_session == "preMarket":
                if est_time.hour == 4 and est_time.minute <= 6:
                    state_text = "04:07 타임쉴드"
                else:
                    state_text = "SW 요격 감시"
            elif current_session == "dayMarket":
                state_text = "데이장 관망"
            elif current_session == "regularMarket":
                state_text = "정규장 감시"
            else:
                state_text = "장외 대기"

        ovn_text = "🟢허용" if ovn else "🔴불가"
        return f"⚔️ <b>[{symbol_short} ON]</b> {state_text} | 💵${budget:,.0f} | 🌙{ovn_text}"

    status_l = build_compact_status("롱(SOXL)", is_active_l, budget_l, ovn_l, is_done_l, session_name_ui, now_est)
    status_s = build_compact_status("숏(SOXS)", is_active_s, budget_s, ovn_s, is_done_s, session_name_ui, now_est)
    
    # MODIFIED: 로깅 최적화를 위한 YYYY-MM-DD HH:MM:SS 풀 포맷 갱신 시간 복구
    scan_time = now_est.strftime("%Y-%m-%d %H:%M:%S")

    # MODIFIED: 줄바꿈 방어를 위한 VWAP 변수 두 줄 분리 렌더링 및 이모지(데이마켓 ☀️) 적용
    text = f"""📡 <b>[ 관제탑: {market_header} 가동중 ]</b>

🎯 <b>[ 현황: 현재가 / 5MA / 평단(수익) ]</b>
▫️ 롱(SOXL): ${price_l:.2f} / {amp_l:.2f}% / {profit_l_str}
▫️ 숏(SOXS): ${price_s:.2f} / {amp_s:.2f}% / {profit_s_str}

☀️ <b>[ 0세션 - 데이장 (19:00~03:59) ]</b>
▫️ 롱: {sess_l['day_amp']:.2f}% (${sess_l['day_l']:.2f}~${sess_l['day_h']:.2f})
▫️ VWAP: ${sess_l['day_vwap']:.2f}
▫️ 숏: {sess_s['day_amp']:.2f}% (${sess_s['day_l']:.2f}~${sess_s['day_h']:.2f})
▫️ VWAP: ${sess_s['day_vwap']:.2f}

🌅 <b>[ 1세션 - 프리장 (04:00~09:29) ]</b>
▫️ 롱: {sess_l['pre_amp']:.2f}% (${sess_l['pre_l']:.2f}~${sess_l['pre_h']:.2f})
▫️ VWAP: ${sess_l['pre_vwap']:.2f}
▫️ 숏: {sess_s['pre_amp']:.2f}% (${sess_s['pre_l']:.2f}~${sess_s['pre_h']:.2f})
▫️ VWAP: ${sess_s['pre_vwap']:.2f}

🔥 <b>[ 2세션 - 정규장 (09:30~16:00) ]</b>
▫️ 롱: {sess_l['reg_amp']:.2f}% (${sess_l['reg_l']:.2f}~${sess_l['reg_h']:.2f})
▫️ VWAP: ${sess_l['reg_vwap']:.2f}
▫️ 숏: {sess_s['reg_amp']:.2f}% (${sess_s['reg_l']:.2f}~${sess_s['reg_h']:.2f})
▫️ VWAP: ${sess_s['reg_vwap']:.2f}

{status_l}
{status_s}

⏱️ 갱신: {scan_time} (EST)"""

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ 통합 전술 제어반", callback_data="open_settlement")],
        [InlineKeyboardButton(text="🔄 레이더 갱신", callback_data="open_avwap")],
        [InlineKeyboardButton(text="🔙 메인 메뉴", callback_data="back_to_main")]
    ])
    return text, keyboard

async def build_sync_board() -> str:
    now_est = datetime.now(ZoneInfo('America/New_York'))
    is_dst = now_est.dst() is not None and now_est.dst().total_seconds() != 0
    dst_str = "🌞 서머타임" if is_dst else "❄️ 서머타임 OFF"
    
    t = now_est.hour * 100 + now_est.minute
    if 400 <= t <= 929:
        market_state = "🌅 프리장"
    elif 930 <= t <= 1559:
        market_state = "🔥 정규장"
    elif 1600 <= t <= 1859:
        market_state = "⛔ 장마감"
    else:
        market_state = "☀️ 데이장"

    bp = await api_client.get_usd_buying_power()
    
    exchange_rate = 1400.0
    try:
        ex_data = await api_client._request(
            "GET", 
            "/api/v1/exchange-rate?baseCurrency=USD&quoteCurrency=KRW", 
            "MARKET_INFO", 
            headers=api_client._get_headers()
        )
        exchange_rate = float(ex_data.get("result", {}).get("rate", 1400.0))
    except Exception:
        pass
    
    async def get_symbol_sync_data(symbol):
        state = await AssassinLedger.get_state(symbol)
        budget = state[1]
        
        hold = await api_client.get_symbol_holdings_detail(symbol)
        qty = hold.get('qty', 0.0)
        avg_price = hold.get('avg_price', 0.0)
        profit_usd = hold.get('profit_usd', 0.0)
        profit_rate = hold.get('profit_rate', 0.0) * 100
        
        profit_krw = profit_usd * exchange_rate
        
        try:
            data = await api_client._request("GET", f"/api/v1/candles?symbol={symbol}&interval=1d&count=2", "MARKET_DATA_CHART", headers=api_client._get_headers())
            candles = data.get("result", {}).get("candles", [])
            if len(candles) > 0:
                today_c = candles[0]
                high = float(today_c.get("highPrice", 0))
                low = float(today_c.get("lowPrice", 0))
                curr = float(today_c.get("closePrice", 0))
                prev_close = float(candles[1].get("closePrice", 0)) if len(candles) > 1 else curr
                
                high_rate = ((high - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
                low_rate = ((low - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
            else:
                high, low, curr, high_rate, low_rate = 0.0, 0.0, 0.0, 0.0, 0.0
        except Exception:
            high, low, curr, high_rate, low_rate = 0.0, 0.0, 0.0, 0.0, 0.0
            
        if curr == 0.0:
            curr = await api_client.get_current_price(symbol)
            
        return {
            "symbol": symbol,
            "budget": budget,
            "curr": curr,
            "avg_price": avg_price,
            "qty": qty,
            "high": high,
            "high_rate": high_rate,
            "low": low,
            "low_rate": low_rate,
            "profit_rate": profit_rate,
            "profit_usd": profit_usd,
            "profit_krw": profit_krw
        }

    soxl_data = await get_symbol_sync_data("SOXL")
    soxs_data = await get_symbol_sync_data("SOXS")
    
    def format_symbol(d):
        profit_sign = "+" if d['profit_usd'] >= 0 else "-"
        return (
            f"⚖️ <b>[{d['symbol']}] 암살자(aVWAP) 지시서</b>\n"
            f"💵 총 시드: ${d['budget']:,.0f}\n"
            f"💰 현재 ${d['curr']:.2f} / 평단 ${d['avg_price']:.2f} ({int(d['qty'])}주)\n"
            f"📈 금일 고가: ${d['high']:.2f} ({d['high_rate']:+.2f}%)\n"
            f"📉 금일 저가: ${d['low']:.2f} ({d['low_rate']:+.2f}%)\n"
            f"🔺 수익: {d['profit_rate']:+.2f}% ({profit_sign}${abs(d['profit_usd']):,.2f} | {profit_sign}₩{int(abs(d['profit_krw'])):,})"
        )
        
    text = (
        f"📜 <b>[ 통합 지시서 ({market_state}) ]</b>\n"
        f"📅 {dst_str} ({now_est.strftime('%H:%M')})\n"
        f"💵 주문가능금액: ${bp:,.2f}\n"
        f"➖➖➖➖➖➖➖➖➖➖➖➖\n\n"
        f"{format_symbol(soxl_data)}\n\n"
        f"{format_symbol(soxs_data)}\n\n"
        f"⛔ 장마감/애프터마켓: 주문 불가\n\n"
        f"▶️ /avwap : 🔫 데이 트레이딩 레이더 관제탑"
    )
    return text

async def build_settlement_board() -> tuple[str, InlineKeyboardMarkup]:
    _, budget_l, _, _, is_active_l, ovn_l, _ = await AssassinLedger.get_state("SOXL")
    _, budget_s, _, _, is_active_s, ovn_s, _ = await AssassinLedger.get_state("SOXS")

    text = (
        "⚙️ <b>[통합 전술 제어반]</b>\n\n"
        "▫️ <b>롱(SOXL) 전술 상태</b>\n"
        f"🔹 가동: {'🟢 ON' if is_active_l else '🔴 OFF'}\n"
        f"🔹 예산: ${budget_l:,.2f}\n"
        f"🔹 OVN: {'🟢 허용' if ovn_l else '🔴 차단'}\n\n"
        "▫️ <b>숏(SOXS) 전술 상태</b>\n"
        f"🔹 가동: {'🟢 ON' if is_active_s else '🔴 OFF'}\n"
        f"🔹 예산: ${budget_s:,.2f}\n"
        f"🔹 OVN: {'🟢 허용' if ovn_s else '🔴 차단'}"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔴 롱 정지" if is_active_l else "🟢 롱 가동", callback_data="toggle_set_act_SOXL"),
            InlineKeyboardButton(text="🔴 숏 정지" if is_active_s else "🟢 숏 가동", callback_data="toggle_set_act_SOXS")
        ],
        [
            InlineKeyboardButton(text="💵 롱 시드 설정", callback_data="set_budget_SOXL"),
            InlineKeyboardButton(text="💵 숏 시드 설정", callback_data="set_budget_SOXS")
        ],
        [
            InlineKeyboardButton(text="🌙 롱 OVN 끄기" if ovn_l else "☀️ 롱 OVN 켜기", callback_data="toggle_set_ovn_SOXL"),
            InlineKeyboardButton(text="🌙 숏 OVN 끄기" if ovn_s else "☀️ 숏 OVN 켜기", callback_data="toggle_set_ovn_SOXS")
        ],
        [InlineKeyboardButton(text="🔫 데이 트레이딩 관제탑", callback_data="open_avwap")],
        [InlineKeyboardButton(text="🔙 메인 메뉴", callback_data="back_to_main")]
    ])
    return text, keyboard

@router.message(Command("avwap"))
async def cmd_avwap(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    await state.clear()
    try:
        msg = await message.answer("📡 <b>레이더 스캔 및 데이터 동기화 중...</b>", parse_mode="HTML")
        text, keyboard = await build_avwap_radar()
        await msg.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"🚨 <b>관제탑 렌더링 실패:</b> {html.escape(str(e))}", parse_mode="HTML")

@router.callback_query(F.data == "open_avwap")
async def process_open_avwap(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        text, keyboard = await build_avwap_radar()
        await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            await callback_query.message.answer(f"🚨 <b>관제탑 갱신 실패:</b> {html.escape(str(e))}", parse_mode="HTML")
    finally:
        try:
            await callback_query.answer("레이더 갱신 완료")
        except Exception:
            pass

@router.message(Command("sync"))
async def cmd_sync(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    await state.clear()
    try:
        msg = await message.answer("📡 <b>통합 지시서 데이터 스캔 중...</b>", parse_mode="HTML")
        text = await build_sync_board()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 새로고침", callback_data="open_sync")],
            [InlineKeyboardButton(text="🔙 메인 메뉴", callback_data="back_to_main")]
        ])
        await msg.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"🚨 <b>통합 지시서 동기화 실패:</b> {html.escape(str(e))}", parse_mode="HTML")

@router.callback_query(F.data == "open_sync")
async def process_open_sync(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        text = await build_sync_board()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 새로고침", callback_data="open_sync")],
            [InlineKeyboardButton(text="🔙 메인 메뉴", callback_data="back_to_main")]
        ])
        await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            await callback_query.message.answer(f"🚨 <b>갱신 실패:</b> {html.escape(str(e))}", parse_mode="HTML")
    finally:
        try:
            await callback_query.answer("동기화 완료")
        except Exception:
            pass

@router.message(Command("settlement"))
async def cmd_settlement(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    await state.clear()
    text, keyboard = await build_settlement_board()
    try:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        pass

@router.callback_query(F.data == "open_settlement")
async def process_open_settlement(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        text, keyboard = await build_settlement_board()
        await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        pass

@router.callback_query(F.data.startswith("toggle_set_act_"))
async def process_toggle_set_act(callback_query: types.CallbackQuery, state: FSMContext):
    symbol = callback_query.data.split("_")[3].upper()
    _, _, _, _, is_active, _, _ = await AssassinLedger.get_state(symbol)
    await AssassinLedger.save_state(symbol, is_active=not is_active)
    text, keyboard = await build_settlement_board()
    try:
        await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        pass

@router.callback_query(F.data.startswith("toggle_set_ovn_"))
async def process_toggle_set_ovn(callback_query: types.CallbackQuery, state: FSMContext):
    symbol = callback_query.data.split("_")[3].upper()
    _, _, _, _, _, overnight_on, _ = await AssassinLedger.get_state(symbol)
    await AssassinLedger.save_state(symbol, overnight_on=not overnight_on)
    text, keyboard = await build_settlement_board()
    try:
        await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        pass

@router.callback_query(F.data.startswith("set_budget_"))
async def process_set_budget(callback_query: types.CallbackQuery, state: FSMContext):
    symbol = callback_query.data.split("_")[2].upper()
    await state.set_state(BudgetState.waiting_for_budget)
    BudgetState.symbol = symbol
    text = f"⌨️ <b>{html.escape(symbol)} 예산 입력 (USD)</b>\n\n▫️ 투입할 달러 예산을 숫자로 전송하십시오."
    try:
        await callback_query.message.edit_text(text, parse_mode="HTML")
    except Exception:
        pass

@router.message(BudgetState.waiting_for_budget)
async def process_budget_input(message: types.Message, state: FSMContext):
    symbol = BudgetState.symbol
    try:
        budget = float(message.text.strip())
        await AssassinLedger.save_state(symbol, budget=budget)
        await state.clear()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 제어반으로", callback_data="open_settlement")]])
        await message.answer(f"✅ <b>{html.escape(symbol)} 예산 ${budget:,.2f} 락온 완료.</b>", reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await message.answer("🚨 유효한 숫자를 입력하세요.", parse_mode="HTML")

@router.message(Command("update"))
async def cmd_update(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    await state.clear()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 구글 클라우드 서버 탑재", callback_data="execute_update")],
        [InlineKeyboardButton(text="🔙 취소", callback_data="back_to_main")]
    ])
    text = (
        "⚠️ <b>[시스템 자가 업데이트]</b>\n\n"
        "경고: 깃허브 게시판(main)에 탑재되어 있는 파이썬 코드를 다운로드 받아 구글 클라우드 서버에 강제 탑재(동기화)하고 시스템을 하드 킬(os._exit)합니다.\n"
        "진행하시겠습니까?"
    )
    try:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        pass

@router.callback_query(F.data == "execute_update")
async def process_execute_update(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback_query.message.edit_text("🔄 <b>GitHub 파이썬 코드 다운로드 및 구글 클라우드 서버 탑재 검증 중...</b>", parse_mode="HTML")

        def _run_git_update():
            import subprocess
            import py_compile
            
            def run_cmd(cmd):
                proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    out, err = proc.communicate(timeout=20)
                    return proc.returncode, out.strip(), err.strip()
                except subprocess.TimeoutExpired:
                    proc.kill()
                    return -1, "", "Subprocess Timeout Expired (Git Credential Prompt 락다운 의심)"
            
            code, current_hash, err = run_cmd("git rev-parse HEAD")
            if code != 0:
                return False, f"해시 백업 실패: {err}"
            
            code, fetch_out, fetch_err = run_cmd("git fetch origin main")
            if code != 0:
                return False, f"Fetch 실패 (권한/네트워크/토큰 만료 확인 요망):\n{fetch_err}"
                
            code, local_hash, _ = run_cmd("git rev-parse HEAD")
            code, remote_hash, _ = run_cmd("git rev-parse origin/main")
            
            if local_hash == remote_hash:
                return True, "Already up to date."
            
            code, reset_out, reset_err = run_cmd("git reset --hard origin/main")
            if code != 0:
                run_cmd(f"git reset --hard {current_hash}")
                return False, f"Hard Reset 붕괴 (원상 복구됨):\n{reset_err}"
                
            try:
                py_compile.compile('main.py', doraise=True)
                py_compile.compile('tg_router.py', doraise=True)
                py_compile.compile('quant_engine.py', doraise=True)
                py_compile.compile('toss_api.py', doraise=True)
            except Exception as e:
                run_cmd(f"git reset --hard {current_hash}")
                return False, f"문법 에러 감지. 롤백 완료:\n{str(e)}"
                
            return True, f"업데이트 성공:\n{reset_out}"

        success, msg = await asyncio.to_thread(_run_git_update)
        
        if success:
            if "Already up to date." in msg:
                await callback_query.message.edit_text(f"✅ <b>서버 탑재 완료</b>\n▫️ 구글 클라우드 서버가 이미 최신 버전입니다.", parse_mode="HTML")
            else:
                await callback_query.message.edit_text(f"🚀 <b>탑재 성공. 구글 클라우드 코어 재기동(os._exit) 격발.</b>\n<pre>{html.escape(msg)}</pre>", parse_mode="HTML")
                await asyncio.sleep(1.0)
                os._exit(0)
        else:
            await callback_query.message.edit_text(f"🚨 <b>업데이트 실패 (롤백됨)</b>\n<pre>{html.escape(msg)}</pre>\n\n⚠️ <b>관리자 조치 요망</b>:\n▫️ 서버 터미널에서 Git 권한(PAT 토큰 만료 또는 SSH)을 확인하십시오.", parse_mode="HTML")

    except Exception as e:
        await callback_query.message.edit_text(f"🚨 <b>서버 탑재 붕괴 방어:</b> {html.escape(str(e))}", parse_mode="HTML")

@router.callback_query(F.data == "back_to_main")
async def process_back_to_main(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_CHAT_ID:
        return
    await state.clear()
    try:
        await callback_query.answer()
        await callback_query.message.edit_text(get_main_menu_text(), reply_markup=None, parse_mode="HTML")
    except Exception:
        pass
