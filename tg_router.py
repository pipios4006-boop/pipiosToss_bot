# =====================================================================
# FILE: tg_router.py
# 목적: SOXL, SOXS 듀얼 상태 제어 UI, 스케줄/명령어 라우팅 및 방어망 결속
# =====================================================================
# MODIFIED: 장마감 1분 전(15:59)부터 3분간 1.5초 간격 MOC 덤핑 스케줄 텍스트 압축 (정규장 단어 소각)
# MODIFIED: 3단 하향망(0.6%) 렌더링 락온 및 Reset 시 플래그 초기화 파이프라인
# NEW: 초과 Case 50 - 5MA 기반 동적 예상 저가/고가(예상 밴드) 연산 및 팩트/예상 분리 렌더링 락온
# MODIFIED: 암살자 타임쉴드 UI 렌더링 04:07 절대쉴드, 04:30 동적쉴드(40틱)로 롤백 락온
# NEW: 3분(180초) 교차 타임쉴드 대기 상태 UI 렌더링 파이프라인 결속
# MODIFIED: /start 명령어 객체 속성 오타(fromuser -> from_user) 원자적 교체 및 AttributeError 방어
# NEW: 초과 Case 56 - 04:07 EST 절대 타임쉴드 렌더링 파이프라인 결속

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
        "➖➖➖➖➖➖➖➖➖➖➖➖➖➖\n"
        "🔹 17:00: 🧹 정산 스캔 및 시스템 대기\n"
        "🔹 04:00: 🌅 프리장 레이더 스캔 (04:07 절대쉴드, 04:30 동적쉴드)\n"
        "🔹 09:30: 🔥 정규장 VWAP 스캔 (신규 진입 셧다운)\n"
        "🔹 15:59: 🛑 MOC 덤핑 (1.5초 주기)\n\n"
        "🛠 <b>[ 핵심 명령어 ]</b>\n"
        "▶️ /avwap : 🔫 트레이딩 레이더 관제탑\n"
        "▶️ /sync : 📜 통합 지시서 및 장부 동기화\n"
        "▶️ /settlement : ⚙️ 통합 전술 제어반\n\n"
        "⚠️ /reset : 🧹 롱/숏 장부 초기화\n\n"
        "⚠️ /update : 🚀 시스템 자가 업데이트\n\n"
        "🌙 <b>오버나이트를 원할 경우 [통합 전술 제어반]에서 해당 종목 가동을 OFF 해주세요.</b>"
    )

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID: 
        return
    print(f"💬 [TG 수신] /start 명령 하달 (User: {message.from_user.id})", flush=True)
    await state.clear()
    try:
        await message.answer(get_main_menu_text(), parse_mode="HTML")
    except Exception:
        pass

def parse_session_data(all_candles: list, session_start_est: datetime) -> dict:
    res = {
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

    pre_h, pre_l, pre_amp, pre_vwap = calc_metrics(pre_df)
    reg_h, reg_l, reg_amp, reg_vwap = calc_metrics(reg_df)
    
    res.update({
        "pre_h": pre_h, "pre_l": pre_l, "pre_amp": pre_amp, "pre_vwap": pre_vwap,
        "reg_h": reg_h, "reg_l": reg_l, "reg_amp": reg_amp, "reg_vwap": reg_vwap
    })
    return res

async def build_avwap_radar() -> tuple[str, InlineKeyboardMarkup]:
    now_est = datetime.now(ZoneInfo('America/New_York'))
    
    t = now_est.hour * 100 + now_est.minute
    if 400 <= t <= 929:
        session_name_ui = "preMarket"
        market_header = "( <b>🌅 PRE_MARKET</b> )"
    elif 930 <= t <= 1559:
        session_name_ui = "regularMarket"
        market_header = "( <b>🔥 REG_MARKET</b> )"
    elif 1600 <= t <= 1659:
        session_name_ui = "afterMarket"
        market_header = "( <b>🛑 AFT_MARKET</b> )"
    else:
        session_name_ui = "dayMarket"
        market_header = "( <b>🌙 시스템 대기</b> )"

    price_l = await api_client.get_current_price("SOXL")
    price_s = await api_client.get_current_price("SOXS")
    
    hold_l = await api_client.get_symbol_holdings_detail("SOXL")
    hold_s = await api_client.get_symbol_holdings_detail("SOXS")

    async def fetch_5ma_amp(symbol):
        try:
            endpoint = f"/api/v1/candles?symbol={symbol}&interval=1d&count=6"
            data = await api_client._request("GET", endpoint, "MARKET_DATA_CHART", headers=api_client._get_headers())
            candles = data.get("result", {}).get("candles", [])
            amps = []
            
            for c in candles[1:6]:
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
        
        if now_est.hour >= 4:
            session_start_est = now_est.replace(hour=4, minute=0, second=0, microsecond=0)
        else:
            session_start_est = (now_est - timedelta(days=1)).replace(hour=4, minute=0, second=0, microsecond=0)
        
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

    if session_name_ui == "dayMarket":
        sess_l = {"pre_h": 0.0, "pre_l": 0.0, "pre_amp": 0.0, "pre_vwap": 0.0, "reg_h": 0.0, "reg_l": 0.0, "reg_amp": 0.0, "reg_vwap": 0.0}
        sess_s = {"pre_h": 0.0, "pre_l": 0.0, "pre_amp": 0.0, "pre_vwap": 0.0, "reg_h": 0.0, "reg_l": 0.0, "reg_amp": 0.0, "reg_vwap": 0.0}
    else:
        sess_l = await fetch_session_stats("SOXL")
        sess_s = await fetch_session_stats("SOXS")

    pre_exp_l_l = sess_l['pre_h'] * (1 - amp_l / 100) if sess_l['pre_h'] > 0 else 0.0
    pre_exp_h_l = sess_l['pre_l'] * (1 + amp_l / 100) if sess_l['pre_l'] > 0 else 0.0
    reg_exp_l_l = sess_l['reg_h'] * (1 - amp_l / 100) if sess_l['reg_h'] > 0 else 0.0
    reg_exp_h_l = sess_l['reg_l'] * (1 + amp_l / 100) if sess_l['reg_l'] > 0 else 0.0

    pre_exp_l_s = sess_s['pre_h'] * (1 - amp_s / 100) if sess_s['pre_h'] > 0 else 0.0
    pre_exp_h_s = sess_s['pre_l'] * (1 + amp_s / 100) if sess_s['pre_l'] > 0 else 0.0
    reg_exp_l_s = sess_s['reg_h'] * (1 - amp_s / 100) if sess_s['reg_h'] > 0 else 0.0
    reg_exp_h_s = sess_s['reg_l'] * (1 + amp_s / 100) if sess_s['reg_l'] > 0 else 0.0

    _, budget_l, _, is_done_l, is_active_l, _, _, _, entry_l, first_l, _, _, is_st3_l, entry_time_l = await AssassinLedger.get_state("SOXL")
    _, budget_s, _, is_done_s, is_active_s, _, _, _, entry_s, first_s, _, _, is_st3_s, entry_time_s = await AssassinLedger.get_state("SOXS")

    def build_compact_status(symbol_short, is_active, budget, is_done, current_session, est_time, qty, entry_session, pre_first_flag, is_stage_3, my_entry_time, other_entry_time):
        state_flag = "ON" if is_active else "OFF"
        
        if not is_active:
            state_text = "대기"
        elif qty > 0:
            if is_stage_3:
                state_text = "보유(+0.6%)"
            elif pre_first_flag:
                state_text = "보유(+2%)"
            else:
                state_text = "보유(+1%)"
        elif is_done:
            state_text = "타격완료"
        else:
            if current_session == "preMarket":
                import time
                current_time_for_ui = time.time()
                # MODIFIED: 동적쉴드 적용 시간 04:07 절대쉴드, 04:30 동적쉴드 확장 렌더링 락온
                if est_time.hour == 4:
                    if est_time.minute < 7:
                        state_text = "절대쉴드"
                    elif est_time.minute < 30:
                        state_text = "동적쉴드"
                    elif other_entry_time > 0 and current_time_for_ui - other_entry_time < 180.0:
                        state_text = "교차쉴드"
                    else:
                        state_text = "PRE대기"
                else:
                    state_text = "PRE대기"
            elif current_session == "dayMarket":
                state_text = "장외대기"
            elif current_session == "regularMarket":
                state_text = "REG대기"
            else:
                state_text = "장외대기"

        emoji = "🐂" if symbol_short == "SOXL" else "🐻"
        return f"{emoji} <b>{symbol_short}</b> <code>[{state_flag}]</code> {state_text} | <code>${budget:.0f}</code>"

    status_l = build_compact_status("SOXL", is_active_l, budget_l, is_done_l, session_name_ui, now_est, hold_l['qty'], entry_l, first_l, is_st3_l, entry_time_l, entry_time_s)
    status_s = build_compact_status("SOXS", is_active_s, budget_s, is_done_s, session_name_ui, now_est, hold_s['qty'], entry_s, first_s, is_st3_s, entry_time_s, entry_time_l)
    
    scan_time = now_est.strftime("%m-%d %H:%M:%S")

    text = f"""📡 <b>[aVWAP 레이더]</b> {market_header}
➖➖➖➖➖➖➖➖➖➖➖➖➖➖
📊 <b>현재가 & 5MA</b>
🐂 <b>SOXL</b> <code>${price_l:.2f}</code> | <code>{amp_l:.1f}%</code>
🐻 <b>SOXS</b> <code>${price_s:.2f}</code> | <code>{amp_s:.1f}%</code>

🌅 <b>프리장</b> (04:00~09:29)
🐂 <b>SOXL</b> <code>[VWAP] ${sess_l['pre_vwap']:.2f}</code>
  ⤷ 팩트: <code>${sess_l['pre_l']:.2f}~${sess_l['pre_h']:.2f} ({sess_l['pre_amp']:.1f}%)</code>
  ⤷ 예상: <code>${pre_exp_l_l:.2f}~${pre_exp_h_l:.2f}</code>
🐻 <b>SOXS</b> <code>[VWAP] ${sess_s['pre_vwap']:.2f}</code>
  ⤷ 팩트: <code>${sess_s['pre_l']:.2f}~${sess_s['pre_h']:.2f} ({sess_s['pre_amp']:.1f}%)</code>
  ⤷ 예상: <code>${pre_exp_l_s:.2f}~${pre_exp_h_s:.2f}</code>

🔥 <b>정규장</b> (09:30~16:00)
🐂 <b>SOXL</b> <code>[VWAP] ${sess_l['reg_vwap']:.2f}</code>
  ⤷ 팩트: <code>${sess_l['reg_l']:.2f}~${sess_l['reg_h']:.2f} ({sess_l['reg_amp']:.1f}%)</code>
  ⤷ 예상: <code>${reg_exp_l_l:.2f}~${reg_exp_h_l:.2f}</code>
🐻 <b>SOXS</b> <code>[VWAP] ${sess_s['reg_vwap']:.2f}</code>
  ⤷ 팩트: <code>${sess_s['reg_l']:.2f}~${sess_s['reg_h']:.2f} ({sess_s['reg_amp']:.1f}%)</code>
  ⤷ 예상: <code>${reg_exp_l_s:.2f}~${reg_exp_h_s:.2f}</code>
➖➖➖➖➖➖➖➖➖➖➖➖➖➖
{status_l}
{status_s}

⏱️ 갱신: <code>{scan_time} EST</code>"""

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
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
    elif 1600 <= t <= 1659:
        market_state = "⛔ 장마감"
    else:
        market_state = "🌙 시스템 대기"

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
        entry_session = state[8]
        pre_first_flag = state[9]
        is_stage_3 = state[12]
        
        hold = await api_client.get_symbol_holdings_detail(symbol)
        qty = hold.get('qty', 0.0)
        avg_price = hold.get('avg_price', 0.0)
        profit_usd = hold.get('profit_usd', 0.0)
        profit_rate = hold.get('profit_rate', 0.0) * 100
        profit_krw = profit_usd * exchange_rate
        
        curr = await api_client.get_current_price(symbol)
        prev_close = curr
        
        try:
            data_1d = await api_client._request("GET", f"/api/v1/candles?symbol={symbol}&interval=1d&count=2", "MARKET_DATA_CHART", headers=api_client._get_headers())
            candles_1d = data_1d.get("result", {}).get("candles", [])
            if len(candles_1d) > 1:
                prev_close = float(candles_1d[1].get("closePrice", 0))
            elif len(candles_1d) == 1:
                prev_close = float(candles_1d[0].get("closePrice", 0))
        except Exception:
            pass

        if market_state == "🌙 시스템 대기":
            high = 0.0
            low = 0.0
            high_rate = 0.0
            low_rate = 0.0
        else:
            if now_est.hour >= 4:
                session_start_est = now_est.replace(hour=4, minute=0, second=0, microsecond=0)
            else:
                session_start_est = (now_est - timedelta(days=1)).replace(hour=4, minute=0, second=0, microsecond=0)
                
            all_candles = []
            before = None
            for _ in range(10):
                try:
                    c_data = await api_client.get_1m_candles_pagination(symbol, count=200, before=before)
                    c_list = c_data.get("candles", [])
                    all_candles.extend(c_list)
                    if not c_list: break
                    oldest_time = pd.to_datetime(c_list[-1]['timestamp'], utc=True).tz_convert(ZoneInfo('America/New_York'))
                    if oldest_time <= session_start_est: break
                    before = c_data.get("nextBefore")
                    if not before: break
                except Exception:
                    break
                    
            high, low = 0.0, 0.0
            if all_candles:
                df = pd.DataFrame(all_candles)
                if not df.empty:
                    df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601', utc=True).dt.tz_convert(ZoneInfo('America/New_York'))
                    df.set_index('timestamp', inplace=True)
                    df = df[df.index >= session_start_est]
                    if not df.empty:
                        df['highPrice'] = pd.to_numeric(df['highPrice'], errors='coerce').fillna(0.0)
                        df['lowPrice'] = pd.to_numeric(df['lowPrice'], errors='coerce').fillna(0.0)
                        h_max = float(df['highPrice'].max())
                        l_min = float(df['lowPrice'].min())
                        if h_max > 0: high = h_max
                        if l_min > 0: low = l_min
                        
            if high == 0.0: high = curr
            if low == 0.0: low = curr

            high_rate = ((high - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
            low_rate = ((low - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
            
        return {
            "symbol": symbol,
            "budget": budget,
            "entry_session": entry_session,
            "pre_first_flag": pre_first_flag,
            "is_stage_3": is_stage_3,
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
        
        flag_str = "⏳ 대기"
        if d['qty'] > 0:
            if d['is_stage_3']:
                flag_str = "🌅 [PRE 잔류: +0.6%]"
            elif d['pre_first_flag']:
                flag_str = "🌅 [PRE 1타점: +2.0%]"
            else:
                flag_str = "🌅 [PRE 듀얼: +1.0%]"

        emoji = "🐂" if d['symbol'] == "SOXL" else "🐻"
        return (
            f"⚖️ <b>[{d['symbol']}] 암살자(aVWAP) 지시서</b>\n"
            f"💵 총 시드: ${d['budget']:,.0f} | 🎯 {flag_str}\n"
            f"💰 현재 ${d['curr']:.2f} / 평단 ${d['avg_price']:.2f} ({int(d['qty'])}주)\n"
            f"📈 금일 고가: ${d['high']:.2f} ({d['high_rate']:+.2f}%)\n"
            f"📉 금일 저가: ${d['low']:.2f} ({d['low_rate']:+.2f}%)\n"
            f"🔺 수익: {d['profit_rate']:+.2f}% ({profit_sign}${abs(d['profit_usd']):,.2f} | {profit_sign}₩{int(abs(d['profit_krw'])):,})"
        )
        
    text = (
        f"📜 <b>[ 통합 지시서 ({market_state}) ]</b>\n"
        f"📅 {dst_str} ({now_est.strftime('%H:%M')})\n"
        f"💵 주문가능금액: ${bp:,.2f}\n"
        f"➖➖➖➖➖➖➖➖➖➖➖➖➖➖\n\n"
        f"{format_symbol(soxl_data)}\n\n"
        f"{format_symbol(soxs_data)}\n\n"
        f"▶️ /avwap : 🔫 트레이딩 레이더 관제탑"
    )
    return text

async def build_settlement_board() -> tuple[str, InlineKeyboardMarkup]:
    _, budget_l, _, _, is_active_l, _, _, _, _, _, _, _, _, _ = await AssassinLedger.get_state("SOXL")
    _, budget_s, _, _, is_active_s, _, _, _, _, _, _, _, _, _ = await AssassinLedger.get_state("SOXS")

    state_l_str = "🟢 ON" if is_active_l else "🔴 OFF"
    state_s_str = "🟢 ON" if is_active_s else "🔴 OFF"

    text = (
        "⚙️ <b>[전술 코어 제어반]</b>\n"
        "➖➖➖➖➖➖➖➖➖➖➖➖➖➖\n"
        "🐂 <b>SOXL (LONG)</b>\n"
        f"▫️ <b>상태:</b> <code>{state_l_str}</code>\n"
        f"▫️ <b>예산:</b> <code>${budget_l:,.2f}</code>\n\n"
        "🐻 <b>SOXS (SHORT)</b>\n"
        f"▫️ <b>상태:</b> <code>{state_s_str}</code>\n"
        f"▫️ <b>예산:</b> <code>${budget_s:,.2f}</code>"
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
        [InlineKeyboardButton(text="🔫 트레이딩 레이더", callback_data="open_avwap")],
        [InlineKeyboardButton(text="🔙 메인 메뉴", callback_data="back_to_main")]
    ])
    return text, keyboard

@router.message(Command("avwap"))
async def cmd_avwap(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    print(f"💬 [TG 수신] /avwap 명령 하달 (User: {message.from_user.id})", flush=True)
    await state.clear()
    try:
        msg = await message.answer("📡 <b>레이더 스캔 및 데이터 동기화 중...</b>", parse_mode="HTML")
        text, keyboard = await build_avwap_radar()
        await msg.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"🚨 <b>관제탑 렌더링 실패:</b> {html.escape(str(e))}", parse_mode="HTML")

@router.callback_query(F.data == "open_avwap")
async def process_open_avwap(callback_query: types.CallbackQuery, state: FSMContext):
    print(f"💬 [TG 콜백 수신] open_avwap (User: {callback_query.from_user.id})", flush=True)
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
    print(f"💬 [TG 수신] /sync 명령 하달 (User: {message.from_user.id})", flush=True)
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
    print(f"💬 [TG 콜백 수신] open_sync (User: {callback_query.from_user.id})", flush=True)
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
    print(f"💬 [TG 수신] /settlement 명령 하달 (User: {message.from_user.id})", flush=True)
    await state.clear()
    text, keyboard = await build_settlement_board()
    try:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        pass

@router.callback_query(F.data == "open_settlement")
async def process_open_settlement(callback_query: types.CallbackQuery, state: FSMContext):
    print(f"💬 [TG 콜백 수신] open_settlement (User: {callback_query.from_user.id})", flush=True)
    await state.clear()
    try:
        text, keyboard = await build_settlement_board()
        await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        pass

@router.callback_query(F.data.startswith("toggle_set_act_"))
async def process_toggle_set_act(callback_query: types.CallbackQuery, state: FSMContext):
    symbol = callback_query.data.split("_")[3].upper()
    print(f"💬 [TG 콜백 수신] toggle_set_act_{symbol} (User: {callback_query.from_user.id})", flush=True)
    state_data = await AssassinLedger.get_state(symbol)
    await AssassinLedger.save_state(symbol, is_active=not state_data[4])
    text, keyboard = await build_settlement_board()
    try:
        await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        pass

@router.callback_query(F.data.startswith("set_budget_"))
async def process_set_budget(callback_query: types.CallbackQuery, state: FSMContext):
    symbol = callback_query.data.split("_")[2].upper()
    print(f"💬 [TG 콜백 수신] set_budget_{symbol} (User: {callback_query.from_user.id})", flush=True)
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
    print(f"💬 [TG 상태 수신] {symbol} 예산 입력 접수: {message.text.strip()} (User: {message.from_user.id})", flush=True)
    try:
        budget = float(message.text.strip())
        await AssassinLedger.save_state(symbol, budget=budget)
        await state.clear()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 제어반으로", callback_data="open_settlement")]])
        await message.answer(f"✅ <b>{html.escape(symbol)} 예산 ${budget:,.2f} 락온 완료.</b>", reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await message.answer("🚨 유효한 숫자를 입력하세요.", parse_mode="HTML")

@router.message(Command("reset"))
async def cmd_reset(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    print(f"💬 [TG 수신] /reset 명령 하달 (User: {message.from_user.id})", flush=True)
    await state.clear()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ 동시 초기화 진행", callback_data="execute_dual_reset")],
        [InlineKeyboardButton(text="🔙 취소", callback_data="back_to_main")]
    ])
    text = (
        "⚠️ <b>[듀얼 장부 동시 초기화]</b>\n\n"
        "경고: SOXL 및 SOXS의 로컬 장부(평단가, 목표가, 주문 ID, 세션 락)를 100% 영구 소각하고 0점으로 원자적 초기화를 수행합니다.\n"
        "진행하시겠습니까?"
    )
    try:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        pass

@router.callback_query(F.data == "execute_dual_reset")
async def process_execute_dual_reset(callback_query: types.CallbackQuery, state: FSMContext):
    print(f"💬 [TG 콜백 수신] execute_dual_reset (User: {callback_query.from_user.id})", flush=True)
    await state.clear()
    try:
        await AssassinLedger.save_state("SOXL", price=0.0, target_sell_price=0.0, buy_order_id="", cond_order_id="", is_session_done=False, entry_session="", pre_first_flag=False, force_downgrade=False, force_downgrade_0_6=False, is_stage_3=False, entry_time=0.0)
        await AssassinLedger.save_state("SOXS", price=0.0, target_sell_price=0.0, buy_order_id="", cond_order_id="", is_session_done=False, entry_session="", pre_first_flag=False, force_downgrade=False, force_downgrade_0_6=False, is_stage_3=False, entry_time=0.0)
        
        await callback_query.answer("✅ 듀얼 장부 영구 소각 완료", show_alert=True)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 메인 메뉴", callback_data="back_to_main")]
        ])
        await callback_query.message.edit_text("✅ <b>[듀얼 장부 영구 소각 완료]</b>\n▫️ SOXL, SOXS 장부가 0점으로 초기화되었습니다.", reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            try:
                await callback_query.message.answer(f"🚨 <b>초기화 실패:</b> {html.escape(str(e))}", parse_mode="HTML")
            except Exception:
                pass

@router.message(Command("update"))
async def cmd_update(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    print(f"💬 [TG 수신] /update 명령 하달 (User: {message.from_user.id})", flush=True)
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
    print(f"💬 [TG 콜백 수신] execute_update (User: {callback_query.from_user.id})", flush=True)
    await state.clear()
    try:
        await callback_query.message.edit_text("🔄 <b>GitHub 파이썬 코드를 다운로드 및 구글 클라우드 서버 탑재 검증 중...</b>", parse_mode="HTML")

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
                    return -1, "", "Subprocess Timeout Expired"
            
            code, current_hash, err = run_cmd("git rev-parse HEAD")
            if code != 0:
                return False, f"해시 백업 실패: {err}"
            
            code, fetch_out, fetch_err = run_cmd("git fetch origin main")
            if code != 0:
                return False, f"Fetch 실패:\n{fetch_err}"
                
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
                py_compile.compile('candle_recorder.py', doraise=True)
            except Exception as e:
                run_cmd(f"git reset --hard {current_hash}")
                return False, f"문법 에러 감지. 롤백 완료:\n{str(e)}"
                
            return True, f"업데이트 성공:\n{reset_out}"

        success, msg = await asyncio.to_thread(_run_git_update)
        
        if success:
            if "Already up to date." in msg:
                await callback_query.message.edit_text("✅ <b>서버 탑재 완료</b>\n▫️ 구글 클라우드 서버가 이미 최신 버전입니다.", parse_mode="HTML")
            else:
                await callback_query.message.edit_text(f"🚀 <b>탑재 성공. 구글 클라우드 코어 재기동(os._exit) 격발.</b>\n<pre>{html.escape(msg)}</pre>", parse_mode="HTML")
                await asyncio.sleep(1.0)
                os._exit(0)
        else:
            await callback_query.message.edit_text(f"🚨 <b>업데이트 실패 (롤백됨)</b>\n<pre>{html.escape(msg)}</pre>", parse_mode="HTML")

    except Exception as e:
        await callback_query.message.edit_text(f"🚨 <b>서버 탑재 붕괴 방어:</b> {html.escape(str(e))}", parse_mode="HTML")

@router.callback_query(F.data == "back_to_main")
async def process_back_to_main(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_CHAT_ID:
        return
    print(f"💬 [TG 콜백 수신] back_to_main (User: {callback_query.from_user.id})", flush=True)
    await state.clear()
    try:
        await callback_query.answer()
        await callback_query.message.edit_text(get_main_menu_text(), reply_markup=None, parse_mode="HTML")
    except Exception:
        pass
