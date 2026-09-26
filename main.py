# =====================================================================
# FILE: main.py
# 목적: SOXL, SOXS 듀얼 코어 암살자 엔진 가동 (aVWAP + 제로오버나잇) - 메인 통제소
# =====================================================================
# MODIFIED: 초과 Case 48 - pandas_market_calendars 영문 휴일명 한글 정밀 맵핑 주입
# MODIFIED: 수익률 3단 하향망 로직 100% 영구 소각 및 1.0% 타점 고정 하드 락온
# MODIFIED: 듀얼 종목 동시 진입 원천 차단 및 단독 트렌드 추종 배타적 진입망 결속
# MODIFIED: 초과 Case 47 - 퇴근 확증 시에만 SOXL 단독 숏 스퀴즈 실시간 모니터링 가동 및 타전망 결속
# MODIFIED: 초과 Case 47 - 숏 스퀴즈 1차 트리거 발동 최저가(min_price) 및 포착 현재가(current_price) 텔레그램 타전망 증축
# NEW: 암살자 OFF 상태(수동 오버나이트) 중 수동 청산 시 침묵(Silent) 해제 및 텔레그램 타전망 분기 결속
# MODIFIED: 초과 Case 47 - 숏 스퀴즈 가격 민감도 0.1% 하향 및 거래량 5배 상향 락온
# NEW: 초과 Case 47 - 세션 전이 거래량 왜곡 방어용 5분 타임쉴드 주입 (04:00~04:04, 09:30~09:34)
# MODIFIED: 초과 Case 51 - 암살자 신규 매수 전용 동적 타임쉴드 04:30 EST(30분) 연장 및 60초(40틱) 연속 상회 확증 알고리즘 주입
# NEW: 초과 Case 52 - 잔고 0주(퇴근) 확증 시 토스증권 API 호출을 통한 손익(PnL) 데이터 동적 추출 및 타전망 결속
# NEW: 수동 매수(개입) 원자적 식별 및 1.0% 타점 하드 락온. 수동 덫 장전 즉시 당일 자동 매수 권한 100% 영구 소각(Mutex).
# MODIFIED: 초과 Case 54 - 잔고 0주 청산 시 조건주문 생존(WATCHING) 여부 원자적 프로빙을 통한 수동 매도 허위 익절(False Positive) 판별망 결속
# NEW: 초과 Case 55 - 듀얼 휩소 동시 진입(마이크로 휩소) 방어용 180초 교차 타임쉴드 인터럽트 주입 및 락온
# MODIFIED: 초과 Case 56 - 04:07 EST 절대 타임쉴드 전면 폐기 및 04:00부터 40틱 동적 타임쉴드 즉각 가동
# MODIFIED: 휴장 알림 시각을 프리장 개장 정밀 윈도우(04:00~04:05 EST)로 락온하여 조기 발송 원천 차단
# NEW: 심야/주말 토스 API 점검 시 HTTP 500 에러 스팸 폭탄 방어용 3600초 타전 쿨다운(음소거) 파이프라인 결속
# MODIFIED: 초과 Case 62 - 토스 서버 점검(HTTP 500/503) 시 초기 기동(fetch_account_seq) 파이프라인 붕괴 방어 및 텔레그램 봇 생존 보장망 락온
# MODIFIED: 초과 Case 63 - 장기 점검 대응 무한 침묵(Infinite Silence) 파이프라인 결속 (3600초 쿨다운 소각 및 상태 전이 기반 타전망 락온)
# MODIFIED: 초과 Case 53 - 04:07 EST (7분) 프리장 개장 직후 절대 진입 금지(절대 타임쉴드) 하드 락온 복구 및 결속
# MODIFIED: MOC 청산 허위 알림(False Positive) 방어를 위한 is_moc_time 타임쉴드 윈도우 원자적 축소 락온 (15:59~16:05 EST)
# NEW: 수동 진입 상태에서 자동매매 동시 진입 충돌을 완벽 차단하기 위한 3단계 배타적 절대 락온(Global Shared Holdings + Probing) 결속
# MODIFIED: 수동 개입(잔고 존재, buy_order_id 부재) 식별 시 is_rearm = False 강제 주입으로 세션 락(is_session_done) 및 평단가 장부 기록 정상화
# MODIFIED: 잔고 보유 중(수동/자동) 추가 진입 원천 차단을 위한 매수 요격 조건식(holdings_qty == 0) 하드 락온
# NEW: 초과 Case 58 - 매크로 위험(스퀴즈 및 진폭 한계) 감지 전용 백그라운드 모니터(macro_risk_monitor) 결속 및 yfinance NQ=F 연동
# MODIFIED: 초과 Case 58 - 매크로 위험 감지 시 강제 퇴근 사유 명문화 및 비대칭 수동 진입 권고 타전망 결속 (숏 금지 로직 최저가 도달 시 무조건 격발)
# MODIFIED: 매크로 위험(스퀴즈 및 진폭 한계) 롱 차단 기준을 1.5%에서 절대헌법 1.0%로 보수적 하향 락온 적용

import sys
import os
import math
import time
import asyncio
import html
import logging
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import deque
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from dotenv import load_dotenv

from toss_api import TossApiClient
from quant_engine import AssassinLedger, AVWAPEngine
from tg_router import router, inject_dependencies
from candle_recorder import record_candles_loop

logging.getLogger("aiogram").setLevel(logging.CRITICAL)
logging.getLogger("aiohttp").setLevel(logging.CRITICAL)

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(dotenv_path=env_path)

TOSS_CLIENT_ID = os.getenv("TOSS_CLIENT_ID")
TOSS_CLIENT_SECRET = os.getenv("TOSS_CLIENT_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
_telegram_chat_id_str = os.getenv("TELEGRAM_CHAT_ID")

if not all([TOSS_CLIENT_ID, TOSS_CLIENT_SECRET, TELEGRAM_BOT_TOKEN, _telegram_chat_id_str]):
    print("🚨 치명적 에러: 필수 환경변수 누락.", flush=True)
    sys.exit(1)

ADMIN_CHAT_ID = int(_telegram_chat_id_str)
wakeup_event = asyncio.Event()

HOLIDAY_TRANSLATIONS = {
    "New Year's Day": "신정 (New Year's Day)",
    "Martin Luther King Jr. Day": "마틴 루터 킹 주니어 탄생일 (MLK Day)",
    "Washington's Birthday": "대통령의 날 (Presidents' Day)",
    "Good Friday": "성금요일 (Good Friday)",
    "Memorial Day": "메모리얼 데이 (Memorial Day)",
    "Juneteenth National Independence Day": "노예해방기념일 (Juneteenth)",
    "Independence Day": "독립기념일 (Independence Day)",
    "Labor Day": "노동절 (Labor Day)",
    "Thanksgiving Day": "추수감사절 (Thanksgiving Day)",
    "Christmas": "크리스마스 (Christmas Day)",
    "Christmas Day": "크리스마스 (Christmas Day)",
    "주말 (Weekend)": "주말 (Weekend)"
}

in_memory_ordering_lock = {"SOXL": False, "SOXS": False}
shared_holdings = {"SOXL": 0, "SOXS": 0}

idempotency_keys = {
    "SOXL": {"BUY": None, "TRAP": None, "MOC": None},
    "SOXS": {"BUY": None, "TRAP": None, "MOC": None}
}

holiday_notify_lock = asyncio.Lock()
last_holiday_notified_date = ""

async def fetch_full_session_candles(client: TossApiClient, symbol: str, session_start_est: datetime) -> list:
    all_candles = []
    before = None
    
    for _ in range(6): 
        try:
            candles_page = await client.get_1m_candles_pagination(symbol, count=200, before=before)
            candles = candles_page.get("candles", [])
            all_candles.extend(candles)
            
            if not candles: break
            oldest_time = pd.to_datetime(candles[-1]['timestamp'], utc=True).tz_convert(ZoneInfo('America/New_York'))
            if oldest_time <= session_start_est: break
            
            before = candles_page.get("nextBefore")
            if not before: break
        except Exception:
            break
            
    return all_candles

async def macro_risk_monitor(bot: Bot, chat_id: int):
    while True:
        try:
            now_est = datetime.now(ZoneInfo('America/New_York'))
            if now_est.hour >= 19 or now_est.hour < 4:
                await asyncio.sleep(60.0)
                continue

            state_l = await AssassinLedger.get_state("SOXL")
            state_s = await AssassinLedger.get_state("SOXS")
            
            if state_l[3] and state_s[3]: 
                await asyncio.sleep(60.0)
                continue

            def _get_nq():
                tkr = yf.Ticker("NQ=F")
                df = tkr.history(period="1d", interval="1m")
                if df.empty: return 0.0, 0.0, 0.0
                return float(df['High'].max()), float(df['Low'].min()), float(df['Close'].iloc[-1])

            try:
                h, l, c = await asyncio.wait_for(asyncio.to_thread(_get_nq), timeout=10.0)
            except Exception as e:
                print(f"🚨 [yfinance NQ=F 통신 방어] {e}", flush=True)
                h, l, c = 0.0, 0.0, 0.0

            if h > 0 and l > 0 and c > 0 and h > l:
                daily_amp = (h - l) / l * 100.0
                
                # MODIFIED: 1.5 -> 1.0 절대헌법에 따른 잔여 체력 임계값 하향 락온
                long_exhausted = ((c * 1.002 - l) / l * 100.0) > 1.0
                short_exhausted = (daily_amp > 0.3) and (((c - l) / l * 100.0) <= 0.1)

                if long_exhausted or short_exhausted:
                    await AssassinLedger.save_state("SOXL", is_session_done=True, entry_session="MACRO_BLOCKED")
                    await AssassinLedger.save_state("SOXS", is_session_done=True, entry_session="MACRO_BLOCKED")
                    
                    if long_exhausted and short_exhausted:
                        reason_msg = "▫️ 사유: NQ=F 상/하방 진폭 체력이 모두 한계치에 도달함 (극심한 방향성 상실)\n▫️ 권고: 방향성 확립 시까지 <b>전면 관망</b>을 유지하십시오."
                    elif long_exhausted:
                        # MODIFIED: 1.5% -> 1.0% 타전 팩트 동기화 락온
                        reason_msg = "▫️ 사유: NQ=F 최고가 부근 도달 및 롱(SOXL) 1% 익절을 위한 추가 상승 체력(1.0% 한계) 100% 고갈\n▫️ 권고: <b>숏(SOXS)에 수동으로 진입하세요.</b>"
                    elif short_exhausted:
                        reason_msg = "▫️ 사유: NQ=F 현재 지수가 당일 최저가(저점) 부근에 도달함 (대세 상승 반전 위험)\n▫️ 권고: <b>롱(SOXL)에 수동으로 진입 하세요.</b>"

                    try:
                        await bot.send_message(
                            chat_id=chat_id,
                            text="🚨 <b>[매크로 위험 감지] 금일 암살자 자동 진입 전면 차단 및 강제 퇴근 처리</b>\n"
                                 f"{reason_msg}\n"
                                 f"▫️ 현재 지수: {c:.2f} (고가: {h:.2f} / 저가: {l:.2f})\n"
                                 "▫️ 조치: SOXL/SOXS 양방향 신규 진입 권한 100% 영구 소각",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
                    print(f"🛑 [매크로 위험 감지] NQ=F 한계 도달. 롱 차단 조건: {long_exhausted}, 숏 차단 조건: {short_exhausted}. 양방향 퇴근 락온 완료.", flush=True)

        except Exception as e:
            print(f"🚨 [매크로 모니터망 붕괴 방어] {e}", flush=True)

        await asyncio.sleep(60.0)

async def assassin_loop(client: TossApiClient, bot: Bot, chat_id: int, symbol: str):
    global last_holiday_notified_date
    last_moc_tick = 0.0
    moc_dump_active = False
    last_heartbeat_hour = -1
    last_logged_session = ""
    breakout_ticks = 0
    prev_is_active = None 
    
    price_window = deque(maxlen=40)
    last_squeeze_alert_time = 0.0
    
    last_error_msg = ""
    
    async def notify_tg(text: str):
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        except Exception as e:
            print(f"🚨 [텔레그램 전송 붕괴 방어] {e}", flush=True)

    while True:
        try:
            await asyncio.wait_for(wakeup_event.wait(), timeout=1.5)
            wakeup_event.clear()
        except asyncio.TimeoutError:
            pass
        
        try:
            now_est = datetime.now(ZoneInfo('America/New_York'))
            est_time_int = now_est.hour * 100 + now_est.minute

            try:
                holdings_detail = await client.get_symbol_holdings_detail(symbol)
                holdings_qty = int(math.floor(holdings_detail['qty']))
                shared_holdings[symbol] = holdings_qty
                
                if last_error_msg != "":
                    last_error_msg = ""
            except Exception as e:
                err_str = str(e)
                
                if err_str != last_error_msg:
                    await notify_tg(f"🚨 <b>[aVWAP {symbol}] 통신 붕괴 (유령 잔고 방어)</b>\n▫️ 사유: {html.escape(err_str)}")
                    last_error_msg = err_str
                else:
                    print(f"🔇 [알람 무한 침묵 {symbol}] 동일 통신 에러 타전 영구 억제 중: {err_str}", flush=True)
                    
                await asyncio.sleep(5)
                continue

            (last_buy_price, budget, last_session_id, is_session_done, is_active, 
             target_sell_price, cond_order_id, session_mode, entry_session, entry_time) = await AssassinLedger.get_state(symbol)
            
            buy_order_id = await AssassinLedger.get_buy_order_id(symbol)

            if prev_is_active is None:
                prev_is_active = is_active
            just_turned_off = (prev_is_active is True and is_active is False)
            prev_is_active = is_active

            if now_est.hour == 17 and now_est.minute == 0:
                in_memory_ordering_lock[symbol] = False
                idempotency_keys[symbol] = {"BUY": None, "TRAP": None, "MOC": None}
                last_moc_tick = 0.0
                moc_dump_active = False
                price_window.clear()
                if holdings_qty == 0:
                    await AssassinLedger.save_state(symbol, buy_order_id="", cond_order_id="", entry_session="", entry_time=0.0)
                print(f"🧹 [GC {symbol}] 17:00 EST 락 해제 및 자정 초기화 완료.", flush=True)
                await asyncio.sleep(60)
                continue
            
            try:
                is_open, _, sess_name, _ = await asyncio.wait_for(client.is_market_open(), timeout=10.0)
            except Exception:
                is_open = True
                sess_name = "UNKNOWN"

            if not is_open and (sess_name and (sess_name.startswith("HOLIDAY") or sess_name in ["CLOSED", "UNKNOWN"])):
                if sess_name.startswith("HOLIDAY"):
                    raw_reason = sess_name.split("|")[1] if "|" in sess_name else "미국 주식시장 정규 휴장"
                    translated_reason = HOLIDAY_TRANSLATIONS.get(raw_reason, raw_reason)
                    reason = html.escape(translated_reason)
                    today_str = now_est.strftime("%Y-%m-%d")
                    
                    if last_holiday_notified_date != today_str:
                        if 400 <= est_time_int <= 405:
                            async with holiday_notify_lock:
                                if last_holiday_notified_date != today_str:
                                    last_holiday_notified_date = today_str
                                    await notify_tg(f"🛑 <b>[시스템 대기] 미국 주식시장 휴무 안내</b>\n▫️ 사유: {reason}\n▫️ 조치: 금일 듀얼 암살자 전술 가동 전면 차단 및 레이더망 휴식")
                                    print(f"🛑 [휴장 감지] {today_str} {reason} - 시스템 대기.", flush=True)
                await asyncio.sleep(60.0)
                continue

            if 400 <= est_time_int < 930:
                hardcoded_session = "preMarket"
                base_h, base_m = 4, 0
                base_date = now_est
            elif 930 <= est_time_int < 1600:
                hardcoded_session = "regularMarket"
                base_h, base_m = 9, 30
                base_date = now_est
            elif 1600 <= est_time_int <= 1859:
                hardcoded_session = "afterMarket"
                base_h, base_m = 16, 0
                base_date = now_est
            else:
                hardcoded_session = "dayMarket"
                base_h, base_m = 19, 0
                base_date = now_est if now_est.hour >= 19 else now_est - timedelta(days=1)
                
            session_baseline_est = base_date.replace(hour=base_h, minute=base_m, second=0, microsecond=0)
            current_session_id = f"{session_baseline_est.strftime('%Y%m%d_%H%M')}_{hardcoded_session}"

            if hardcoded_session != last_logged_session:
                if last_logged_session:
                    print(f"🔄 [세션 전이 {symbol}] {last_logged_session} ➡️ {hardcoded_session} 진입 완료.", flush=True)
                last_logged_session = hardcoded_session

            if now_est.hour != last_heartbeat_hour:
                print(f"💓 [맥박 {symbol}] 논리 시계: {now_est.strftime('%Y-%m-%d %H:%M:%S')} EST | 세션: {hardcoded_session} | 활성: {is_active} | 잔고: {holdings_qty}주", flush=True)
                last_heartbeat_hour = now_est.hour

            is_reg_moc = ((now_est.hour == 15 and now_est.minute == 59) or (now_est.hour == 16 and 0 <= now_est.minute <= 1))

            if is_reg_moc and is_active:
                if holdings_qty > 0 and not in_memory_ordering_lock[symbol]:
                    current_time = time.time()
                    if current_time - last_moc_tick >= 1.5:
                        in_memory_ordering_lock[symbol] = True
                        try:
                            if cond_order_id:
                                try:
                                    await client.cancel_conditional_order(cond_order_id)
                                    await AssassinLedger.save_state(symbol, cond_order_id="")
                                except Exception as e:
                                    print(f"🚨 [조건주문 취소 방어] {e}", flush=True)

                            open_orders = await client.get_orders(status="OPEN", symbol=symbol)
                            cancel_issued = False
                            if open_orders:
                                for order in open_orders:
                                    await client.cancel_order(order["orderId"])
                                    cancel_issued = True
                            
                            if cancel_issued:
                                await asyncio.sleep(0.5)
                                
                            holdings_detail_moc = await client.get_symbol_holdings_detail(symbol)
                            dump_qty = int(math.floor(holdings_detail_moc['qty']))
                            
                            if dump_qty > 0:
                                orderbook = await client.get_orderbook(symbol)
                                bids = orderbook.get("bids", [])
                                current_price = await client.get_current_price(symbol)
                                
                                bid_1_price = float(bids[0]["price"]) if bids and float(bids[0]["price"]) > 0.0 else current_price
                                
                                if bid_1_price > 0.0:
                                    client_id = f"MOC_{symbol}_{now_est.strftime('%H%M%S_%f')}"[:36]
                                    
                                    await client.create_order(
                                        symbol=symbol, side="SELL", order_type="LIMIT",
                                        quantity=dump_qty, price=f"{bid_1_price:.2f}",
                                        client_order_id=client_id
                                    )
                                    
                                    print(f"🔴 [매도 덤핑 스윕 {symbol}] 1.5초 주기 타격! 수량: {dump_qty}주 | 단가: ${bid_1_price:.2f}", flush=True)
                                    await AssassinLedger.save_state(symbol, is_session_done=True)
                                    
                                    if not moc_dump_active:
                                        moc_dump_active = True
                                        await notify_tg(f"🔴 <b>[aVWAP {symbol}] 15:59~16:01 제로오버나이트 덤핑망 결속</b>\n▫️ 1.5초 간격 체결 추 추적 및 매수 1호가 지속 폭격 개시")
                        except Exception as e:
                            print(f"🚨 [MOC 방어] {e}", flush=True)
                        finally:
                            last_moc_tick = time.time()
                            in_memory_ordering_lock[symbol] = False
                continue
            else:
                moc_dump_active = False

            if not is_open:
                continue
                
            current_price = await client.get_current_price(symbol)
            if current_price <= 0.0:
                continue

            if symbol == "SOXL" and hardcoded_session in ["preMarket", "regularMarket"]:
                if holdings_qty == 0 and is_session_done:
                    is_squeeze_shield_active = (400 <= est_time_int <= 404) or (930 <= est_time_int <= 934)
                    
                    if is_squeeze_shield_active:
                        if len(price_window) > 0:
                            price_window.clear()
                    else:
                        price_window.append(current_price)
                        
                        if len(price_window) >= 2:
                            min_price = min(price_window)
                            if min_price > 0 and current_price >= min_price * 1.001:
                                current_time_sec = time.time()
                                
                                if current_time_sec - last_squeeze_alert_time >= 180.0:
                                    try:
                                        c_data = await client.get_1m_candles_pagination(symbol, count=6)
                                        c_list = c_data.get("candles", [])
                                        
                                        if len(c_list) >= 6:
                                            curr_vol = float(c_list[0].get("volume", 0.0))
                                            vol_5ma = sum(float(c.get("volume", 0.0)) for c in c_list[1:6]) / 5.0
                                            
                                            if vol_5ma > 0 and curr_vol >= vol_5ma * 5.0:
                                                last_squeeze_alert_time = current_time_sec
                                                price_window.clear()
                                                
                                                up_rate = ((current_price / min_price) - 1.0) * 100
                                                vol_multi = curr_vol / vol_5ma
                                                
                                                await notify_tg(
                                                    f"🚨 <b>숏 커버링 으로 롱(SOXL) 가격 상승 중</b>\n"
                                                    f"▫️ 발동 최저가: ${min_price:.2f}\n"
                                                    f"▫️ 포착 현재가: ${current_price:.2f}\n"
                                                    f"▫️ 가격 상승률: +{up_rate:.3f}%\n"
                                                    f"▫️ 거래량 증폭: {vol_multi:.2f}배"
                                                )
                                                print(f"🔥 [스퀴즈 모니터 {symbol}] +{up_rate:.3f}% 단기 반등 (${min_price:.2f} -> ${current_price:.2f}) / 거래량 {vol_multi:.2f}배 폭발. 타전 완료.", flush=True)
                                    except Exception as e:
                                        print(f"🚨 [스퀴즈 캔들 방어 {symbol}] {e}", flush=True)
                else:
                    if len(price_window) > 0:
                        price_window.clear()

            if current_session_id != last_session_id:
                if holdings_qty == 0:
                    can_reset = True
                    if buy_order_id:
                        try:
                            od = await client.get_order_detail(buy_order_id)
                            if od.get("status") in ["PENDING", "PARTIAL_FILLED"]:
                                can_reset = False
                        except Exception:
                            can_reset = False
                            
                    if can_reset:
                        await AssassinLedger.save_state(symbol, price=0.0, target_sell_price=0.0, last_session_id=current_session_id, is_session_done=False, buy_order_id="", cond_order_id="", entry_session="", entry_time=0.0)
                        is_session_done = False
                        target_sell_price = 0.0
                        buy_order_id = ""
                        cond_order_id = ""
                else:
                    await AssassinLedger.save_state(symbol, last_session_id=current_session_id)
                last_session_id = current_session_id

            if holdings_qty == 0 and (target_sell_price > 0.0 or buy_order_id or cond_order_id):
                if not in_memory_ordering_lock[symbol]:
                    can_clear = True
                    if buy_order_id:
                        try:
                            od = await client.get_order_detail(buy_order_id)
                            st = od.get("status", "")
                            if st in ["PENDING", "PARTIAL_FILLED", "PENDING_CANCEL", "PENDING_REPLACE"]:
                                can_clear = False
                        except Exception:
                            can_clear = False
                            
                    if can_clear:
                        in_memory_ordering_lock[symbol] = True
                        try:
                            exit_price, filled_qty = 0.0, 0.0
                            try:
                                orders = await client.get_orders(status="CLOSED", symbol=symbol)
                                for o in orders:
                                    if o.get("side") == "SELL" and o.get("status") in ["FILLED", "PARTIAL_FILLED"]:
                                        exec_info = o.get("execution", {})
                                        avg_p = float(exec_info.get("averageFilledPrice") or 0.0)
                                        f_qty = float(exec_info.get("filledQuantity") or 0.0)
                                        if avg_p > 0 and f_qty > 0:
                                            exit_price, filled_qty = avg_p, f_qty
                                            break
                            except Exception as e:
                                print(f"🚨 [매도 정보 추출 방어] {e}", flush=True)

                            entry_price = last_buy_price
                            pnl_str = ""
                            if entry_price > 0 and exit_price > 0 and filled_qty > 0:
                                principal = entry_price * filled_qty
                                gross = exit_price * filled_qty
                                pnl_amt = gross - principal
                                pnl_rate = (exit_price / entry_price - 1.0) * 100.0
                                sign = "+" if pnl_amt > 0 else ""
                                pnl_str = f"\n▫️ 타점: 매수 ${entry_price:.2f} ➡️ 매도 ${exit_price:.2f}\n▫️ 손익: {sign}{pnl_rate:.2f}% ({sign}${pnl_amt:.2f})"
                            else:
                                pnl_str = "\n▫️ 타점: 체결 데이터 추출 지연 (장부 참조 요망)"

                            now_est_check = datetime.now(ZoneInfo('America/New_York'))
                            is_moc_time = ((now_est_check.hour == 15 and now_est_check.minute >= 59) or (now_est_check.hour == 16 and 0 <= now_est_check.minute <= 5))
                            
                            is_trap_survived = False
                            if cond_order_id:
                                try:
                                    cond_detail = await client.get_conditional_order_detail(cond_order_id)
                                    if cond_detail.get("status") in ["WATCHING", "PAUSED"]:
                                        is_trap_survived = True
                                    await client.cancel_conditional_order(cond_order_id)
                                    print(f"🧹 [고아 덫 파기 {symbol}] 잔고 0주 연동. 서버단 조건주문({cond_order_id}) 파기 완료.", flush=True)
                                    await asyncio.sleep(0.5)
                                except Exception as e:
                                    print(f"🚨 [고아 덫 파기 방어 {symbol}] 404 무시(이미 취소/실행됨) 또는 통신 오류: {e}", flush=True)

                            is_take_profit_exit = bool(target_sell_price > 0.0 or cond_order_id) and not is_moc_time and not is_trap_survived
                            is_manual_exit = not is_take_profit_exit and not is_moc_time
                            is_moc_exit = is_moc_time

                            await AssassinLedger.save_state(symbol, price=0.0, target_sell_price=0.0, buy_order_id="", cond_order_id="", is_session_done=True, entry_session="", entry_time=0.0)
                            target_sell_price = 0.0
                            buy_order_id = ""
                            cond_order_id = ""
                            is_session_done = True
                            
                            if is_moc_exit:
                                await notify_tg(f"🛑 <b>[aVWAP {symbol}] MOC 강제 덤핑 청산 완료</b>\n▫️ 잔고 0주 (제로-오버나이트 락온){pnl_str}")
                            elif is_take_profit_exit:
                                await notify_tg(f"🎉 <b>[aVWAP {symbol}] 거래 종료 (퇴근 락온 완료)</b>\n▫️ 잔고 0주 (조건주문 체결 확인){pnl_str}\n▫️ 당일 신규 진입 권한 영구 소각")
                            elif is_manual_exit:
                                await notify_tg(f"🛑 <b>[aVWAP {symbol}] 수동 매도 청산 감지 (퇴근 락온 완료)</b>\n▫️ 잔고 0주 (오프라인 등 수동 청산 식별){pnl_str}\n▫️ 당일 신규 진입 권한 영구 소각 완료")
                        finally:
                            in_memory_ordering_lock[symbol] = False

            if hardcoded_session == "dayMarket":
                vwap_price = 0.0
            else:
                candles_json = await fetch_full_session_candles(client, symbol, session_baseline_est)
                vwap_price = AVWAPEngine.calculate_vwap(candles_json, session_baseline_est)

            if est_time_int >= 930 and est_time_int < 1600:
                if not buy_order_id and not is_session_done:
                    await AssassinLedger.save_state(symbol, is_session_done=True)
                    is_session_done = True
                    print(f"🎯 [aVWAP {symbol}] 정규장 진입. 당일 신규 매수 권한 소각 완료.", flush=True)

            open_orders = await client.get_orders(status="OPEN", symbol=symbol)
            has_open_sell = any(o["side"] == "SELL" for o in open_orders)
            has_open_buy = any(o["side"] == "BUY" for o in open_orders)
            
            if not is_active:
                if cond_order_id:
                    if not in_memory_ordering_lock[symbol]:
                        in_memory_ordering_lock[symbol] = True
                        try:
                            await client.cancel_conditional_order(cond_order_id)
                            await AssassinLedger.save_state(symbol, cond_order_id="", target_sell_price=0.0)
                            print(f"🛑 [수동 오버나이트 {symbol}] 가동 OFF 감지. 익절 조건주문({cond_order_id}) 파기 완료.", flush=True)
                            await notify_tg(f"🛑 <b>[aVWAP {symbol}] 수동 오버나이트(가동 OFF) 전환</b>\n▫️ 조치: 기장전된 익절 조건주문 안전 파기 완료")
                            cond_order_id = ""
                            target_sell_price = 0.0
                            await asyncio.sleep(0.5)
                        except Exception as e:
                            err_str = str(e).lower()
                            if "404" in err_str or "not-found" in err_str:
                                await AssassinLedger.save_state(symbol, cond_order_id="", target_sell_price=0.0)
                                cond_order_id = ""
                                target_sell_price = 0.0
                                await notify_tg(f"🛑 <b>[aVWAP {symbol}] 수동 오버나이트(가동 OFF) 전환</b>\n▫️ 조치: 로컬 덫 장부 초기화 완료 (서버단 이미 증발)")
                            print(f"🚨 [수동 OFF 덫 파기 방어 {symbol}] {e}", flush=True)
                        finally:
                            in_memory_ordering_lock[symbol] = False
                elif just_turned_off:
                    await notify_tg(f"🛑 <b>[aVWAP {symbol}] 수동 오버나이트(가동 OFF) 전환</b>\n▫️ 조치: 파기할 조건주문 부재 확인. 시스템 대기 모드로 안전 전환 완료")
            
            if holdings_qty > 0 and cond_order_id and is_active:
                try:
                    cond_detail = await client.get_conditional_order_detail(cond_order_id)
                    cond_status = cond_detail.get("status", "")
                    if cond_status in ["EXPIRED", "CANCELED", "REJECTED"]:
                        await notify_tg(f"🚨 <b>[aVWAP {symbol}] 유령 덫 증발 감지</b>\n▫️ 사유: 상태 변이({cond_status})\n▫️ 조치: 덫 파기 및 자동 재장전 가동")
                        await AssassinLedger.save_state(symbol, cond_order_id="")
                        cond_order_id = ""
                except Exception as e:
                    err_str = str(e).lower()
                    if "404" in err_str or "not-found" in err_str:
                        await notify_tg(f"🚨 <b>[aVWAP {symbol}] 유령 덫 증발 감지</b>\n▫️ 사유: 서버 404 (수동 취소 추정)\n▫️ 조치: 덫 파기 및 자동 재장전 가동")
                        await AssassinLedger.save_state(symbol, cond_order_id="")
                        cond_order_id = ""
            
            if holdings_qty > 0 and not has_open_sell and not has_open_buy and not cond_order_id and not in_memory_ordering_lock[symbol] and is_active:
                calculated_target = target_sell_price
                trap_qty = holdings_qty
                avg_price = last_buy_price
                is_rearm = True
                trap_tag = "" 
                
                if calculated_target <= 0.0:
                    if buy_order_id:
                        try:
                            order_detail = await client.get_order_detail(buy_order_id)
                            status = order_detail.get("status", "")
                            
                            if status in ["FILLED", "PARTIAL_FILLED", "CANCELED", "REJECTED"]:
                                filled_qty = int(math.floor(float(order_detail.get("execution", {}).get("filledQuantity", 0.0))))
                                exec_price = float(order_detail.get("execution", {}).get("averageFilledPrice", 0.0))
                                
                                if filled_qty > 0 and exec_price > 0.0:
                                    trap_qty = min(holdings_qty, filled_qty)
                                    avg_price = exec_price
                                    is_rearm = False
                        except Exception:
                            pass
                    else:
                        is_rearm = False

                    if avg_price <= 0.0:
                        avg_price = float(holdings_detail.get('avg_price', 0.0))

                    if avg_price > 0.0:
                        calculated_target = math.ceil(avg_price * 1.01 * 100) / 100.0
                        trap_tag = "+1.0%" if entry_session == "preMarket" and buy_order_id else "수동개입(+1.0%)"

                if calculated_target > 0.0 and trap_qty > 0:
                    in_memory_ordering_lock[symbol] = True
                    try:
                        client_id = idempotency_keys[symbol]["TRAP"]
                        if not client_id:
                            client_id = f"TRAP_{symbol}_{now_est.strftime('%Y%m%d_%H%M%S')}"
                            idempotency_keys[symbol]["TRAP"] = client_id

                        expire_date = (now_est + timedelta(days=30)).strftime("%Y-%m-%d")
                        res = await client.create_conditional_order(
                            symbol=symbol, quantity=trap_qty, price=f"{calculated_target:.2f}",
                            client_order_id=client_id, expire_date=expire_date
                        )
                        
                        print(f"🟢 [익절 덫 장전 {symbol}] 기계적 조건주문 서버 위임 완료. 수량: {trap_qty}주 | 덫 단가: ${calculated_target:.2f}", flush=True)
                        
                        new_cond_id = ""
                        if res and isinstance(res, dict) and res.get("result", {}).get("conditionalOrderId"):
                            new_cond_id = str(res["result"]["conditionalOrderId"])
                        
                        if not is_rearm:
                            if not buy_order_id:
                                await AssassinLedger.save_state(symbol, price=avg_price, target_sell_price=calculated_target, cond_order_id=new_cond_id, is_session_done=True, entry_session="MANUAL")
                                is_session_done = True
                            else:
                                await AssassinLedger.save_state(symbol, price=avg_price, target_sell_price=calculated_target, cond_order_id=new_cond_id)
                            await notify_tg(f"🟢 <b>[aVWAP {symbol}] {trap_tag} 기계적 조건주문 덫 장전</b>\n▫️ 팩트 평단가: ${avg_price:.2f}\n▫️ 익절 덫: ${calculated_target:.2f}\n▫️ 수량: {trap_qty}주")
                        else:
                            await AssassinLedger.save_state(symbol, cond_order_id=new_cond_id)
                            await notify_tg(f"🟢 <b>[aVWAP {symbol}] 포지션 조건주문 덫 재장전</b>\n▫️ 유지 평단가: ${avg_price:.2f}\n▫️ 익절 덫: ${calculated_target:.2f}\n▫️ 수량: {trap_qty}주")
                        
                        idempotency_keys[symbol]["TRAP"] = None
                    except Exception as e:
                        print(f"🚨 [TRAP 방어] {e}", flush=True)
                        await notify_tg(f"🚨 <b>[TRAP 에러 {symbol}]</b> {html.escape(str(e))}")
                    finally:
                        in_memory_ordering_lock[symbol] = False
                continue

            if holdings_qty == 0 and not buy_order_id and not is_session_done and is_active and vwap_price > 0.0:
                elapsed = (now_est - session_baseline_est).total_seconds()
                
                can_enter = False
                if hardcoded_session == "preMarket":
                    if 400 <= est_time_int <= 406:
                        can_enter = False
                    else:
                        can_enter = True
                
                required_ticks = 4
                if hardcoded_session == "preMarket" and elapsed < 1800:
                    required_ticks = 40
                
                if can_enter and current_price >= vwap_price:
                    other_symbol_for_shield = "SOXS" if symbol == "SOXL" else "SOXL"
                    other_state_for_shield = await AssassinLedger.get_state(other_symbol_for_shield)
                    other_buy_price = other_state_for_shield[0]
                    other_is_done = other_state_for_shield[3]
                    other_entry_time = other_state_for_shield[9] 
                    other_buy_id = await AssassinLedger.get_buy_order_id(other_symbol_for_shield)
                    other_qty = shared_holdings.get(other_symbol_for_shield, 0)
                    
                    current_time_for_shield = time.time()
                    
                    if other_buy_price > 0 or other_buy_id or other_is_done or (other_entry_time > 0 and current_time_for_shield - other_entry_time < 180.0) or other_qty > 0:
                        breakout_ticks = 0
                    else:
                        breakout_ticks += 1
                else:
                    breakout_ticks = 0
                
                if can_enter and breakout_ticks >= required_ticks:
                    if not in_memory_ordering_lock[symbol]:
                        in_memory_ordering_lock[symbol] = True
                        try:
                            other_symbol_for_lock = "SOXS" if symbol == "SOXL" else "SOXL"
                            other_hold_check = await client.get_symbol_holdings_detail(other_symbol_for_lock)
                            other_hold_qty_check = int(math.floor(other_hold_check.get('qty', 0.0)))
                            
                            if other_hold_qty_check > 0:
                                breakout_ticks = 0
                                await AssassinLedger.save_state(other_symbol_for_lock, is_session_done=True)
                                print(f"🚨 [듀얼 절대 쉴드 락온] {symbol} 돌파 확증되었으나 반대 종목({other_symbol_for_lock}) 수동/자동 잔고 포착! 요격 원천 차단.", flush=True)
                                continue

                            orderbook = await client.get_orderbook(symbol)
                            asks = orderbook.get("asks", [])
                            
                            if asks:
                                ask_1_price = float(asks[0]["price"])
                            else:
                                ask_1_price = current_price
                                
                            if ask_1_price > 0.0:
                                target_qty = int(math.floor(budget / ask_1_price))
                                
                                if target_qty > 0:
                                    client_id = idempotency_keys[symbol]["BUY"]
                                    if not client_id:
                                        client_id = f"BUY_{symbol}_{now_est.strftime('%Y%m%d_%H%M%S')}"
                                        idempotency_keys[symbol]["BUY"] = client_id

                                    res = await client.create_order(
                                        symbol=symbol, side="BUY", order_type="LIMIT",
                                        quantity=target_qty, price=f"{ask_1_price:.2f}",
                                        client_order_id=client_id
                                    )
                                    
                                    print(f"🚀 [매수 집행 {symbol}] 돌파 요격 매수 발사 완료. 수량: {target_qty}주 | 타격가: ${ask_1_price:.2f}", flush=True)
                                    
                                    if res and isinstance(res, dict) and res.get("result", {}).get("orderId"):
                                        await AssassinLedger.save_state(symbol, buy_order_id=str(res["result"]["orderId"]), entry_session=hardcoded_session, entry_time=time.time())
                                    
                                    idempotency_keys[symbol]["BUY"] = None
                                    
                                    lock_msg = f"VWAP 연속 돌파 방어망 통과 ({required_ticks}틱)"
                                    await notify_tg(f"🚀 <b>[aVWAP {symbol}] 단독 돌파 요격 매수 (세션: {hardcoded_session})</b>\n▫️ aVWAP: ${vwap_price:.2f}\n▫️ 타격가: ${ask_1_price:.2f}\n▫️ 수량: {target_qty}주\n▫️ 확증: {lock_msg}")
                        except Exception as e:
                            print(f"🚨 [BUY 방어] {e}", flush=True)
                            await notify_tg(f"🚨 <b>[BUY 에러 {symbol}]</b> {html.escape(str(e))}")
                        finally:
                            in_memory_ordering_lock[symbol] = False
            else:
                breakout_ticks = 0

        except Exception as e:
            print(f"🚨 [aVWAP {symbol}] 감시망 붕괴 방어: {e}", flush=True)

async def main():
    session = AiohttpSession(timeout=10.0)
    bot = Bot(token=TELEGRAM_BOT_TOKEN, session=session)
    dp = Dispatcher()
    
    api_client = TossApiClient(client_id=TOSS_CLIENT_ID, client_secret=TOSS_CLIENT_SECRET)
    
    try:
        await api_client.fetch_account_seq()
    except Exception as e:
        print(f"🚨 [초기 기동 방어] 토스 API 서버 점검 또는 통신 장애로 계좌 연동 지연 (자동 재시도 예정): {e}", flush=True)
    
    inject_dependencies(api_client, ADMIN_CHAT_ID, wakeup_event)
    dp.include_router(router)
    
    asyncio.create_task(api_client.token_renewal_loop())
    asyncio.create_task(macro_risk_monitor(bot, ADMIN_CHAT_ID))
    asyncio.create_task(assassin_loop(api_client, bot, ADMIN_CHAT_ID, "SOXL"))
    asyncio.create_task(assassin_loop(api_client, bot, ADMIN_CHAT_ID, "SOXS"))
    asyncio.create_task(record_candles_loop(api_client, "SOXL"))
    asyncio.create_task(record_candles_loop(api_client, "SOXS"))
    
    print("시스템 코어 및 듀얼 암살자(SOXL, SOXS) 방어망 결합 완료. 폴링 개시...", flush=True)
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.send_message(
            chat_id=ADMIN_CHAT_ID, 
            text="✅ <b>[시스템 기동 완료]</b>\n▫️ 서버 재부팅 및 단독 암살자(트렌드 추종형) 코어 결속\n▫️ 1.0% 타점 고정 및 배타적 동시 진입 차단 락온 완료.", 
            parse_mode="HTML"
        )
    except Exception:
        pass
        
    while True:
        try:
            await dp.start_polling(bot)
        except Exception as e:
            print(f"🚨 [통신 붕괴 방어] 5초 후 치유 재가동: {e}", flush=True)
            await asyncio.sleep(5)
        else:
            break

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
