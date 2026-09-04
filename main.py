# =====================================================================
# FILE: main.py
# 목적: SOXL, SOXS 듀얼 코어 암살자 엔진 가동 (aVWAP + 제로오버나잇) - 메인 통제소
# =====================================================================
# MODIFIED: 미국 주식시장 휴장일 사유 파싱(pandas_market_calendars 기반) 텔레그램 1회 통보망 결속 유지
# MODIFIED: 휴무 사유 텍스트 HTML 이스케이프 강제 결속 (Case 17 방어)

import sys
import os
import math
import time
import asyncio
import html
import logging
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
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

in_memory_ordering_lock = {"SOXL": False, "SOXS": False}
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

async def assassin_loop(client: TossApiClient, bot: Bot, chat_id: int, symbol: str):
    global last_holiday_notified_date
    last_moc_tick = 0.0
    moc_dump_active = False
    last_heartbeat_hour = -1
    last_logged_session = ""
    breakout_ticks = 0
    
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
            except Exception as e:
                await notify_tg(f"🚨 <b>[aVWAP {symbol}] 통신 붕괴 (유령 잔고 방어)</b>\n▫️ 사유: {html.escape(str(e))}")
                await asyncio.sleep(5)
                continue

            last_buy_price, budget, last_session_id, is_session_done, is_active, target_sell_price, cond_order_id, session_mode, entry_session, pre_first_flag, force_downgrade = await AssassinLedger.get_state(symbol)
            buy_order_id = await AssassinLedger.get_buy_order_id(symbol)

            if now_est.hour == 17 and now_est.minute == 0:
                in_memory_ordering_lock[symbol] = False
                idempotency_keys[symbol] = {"BUY": None, "TRAP": None, "MOC": None}
                last_moc_tick = 0.0
                moc_dump_active = False
                if holdings_qty == 0:
                    await AssassinLedger.save_state(symbol, buy_order_id="", cond_order_id="", entry_session="", pre_first_flag=False, force_downgrade=False)
                print(f"🧹 [GC {symbol}] 17:00 EST 락 해제 및 자정 초기화 완료.", flush=True)
                await asyncio.sleep(60)
                continue
            
            try:
                is_open, _, sess_name, _ = await asyncio.wait_for(client.is_market_open(), timeout=10.0)
            except Exception:
                is_open = True
                sess_name = "UNKNOWN"

            if sess_name and sess_name.startswith("HOLIDAY"):
                # MODIFIED: HTML 파싱 붕괴를 방어하기 위한 원자적 이스케이프 주입
                raw_reason = sess_name.split("|")[1] if "|" in sess_name else "미국 주식시장 정규 휴장"
                reason = html.escape(raw_reason)
                today_str = now_est.strftime("%Y-%m-%d")
                
                if last_holiday_notified_date != today_str:
                    async with holiday_notify_lock:
                        if last_holiday_notified_date != today_str:
                            last_holiday_notified_date = today_str
                            await notify_tg(f"🛑 <b>[시스템 대기] 미국 주식시장 휴무 안내</b>\n▫️ 사유: {reason} 사유로 인해 미국 주식시장이 휴무입니다.\n▫️ 조치: 금일 듀얼 암살자 자동매매 가동 전면 차단 및 레이더망 휴식")
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
                                        await notify_tg(f"🔴 <b>[aVWAP {symbol}] 15:59~16:01 제로오버나이트 덤핑망 결속</b>\n▫️ 1.5초 간격 체결 추적 및 매수 1호가 지속 폭격 개시")
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
                        await AssassinLedger.save_state(symbol, price=0.0, target_sell_price=0.0, last_session_id=current_session_id, is_session_done=False, buy_order_id="", cond_order_id="", entry_session="", pre_first_flag=False, force_downgrade=False)
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
                            is_take_profit_exit = bool(target_sell_price > 0.0 or cond_order_id)
                            
                            if cond_order_id:
                                try:
                                    await client.cancel_conditional_order(cond_order_id)
                                    print(f"🧹 [고아 덫 파기 {symbol}] 잔고 0주 연동. 서버단 조건주문({cond_order_id}) 파기 완료.", flush=True)
                                    await asyncio.sleep(0.5)
                                except Exception as e:
                                    print(f"🚨 [고아 덫 파기 방어 {symbol}] 404 무시(이미 취소됨) 또는 통신 오류: {e}", flush=True)

                            await AssassinLedger.save_state(symbol, price=0.0, target_sell_price=0.0, buy_order_id="", cond_order_id="", is_session_done=True, entry_session="", pre_first_flag=False, force_downgrade=False)
                            target_sell_price = 0.0
                            buy_order_id = ""
                            cond_order_id = ""
                            is_session_done = True
                            
                            if is_take_profit_exit:
                                await notify_tg(f"🎉 <b>[aVWAP {symbol}] 거래 종료 (퇴근 락온 완료)</b>\n▫️ 잔고 0주 (조건주문 체결 확인)\n▫️ 당일 신규 진입 권한 영구 소각")
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
                        
            if holdings_qty > 0 and cond_order_id and force_downgrade and is_active:
                if not in_memory_ordering_lock[symbol]:
                    in_memory_ordering_lock[symbol] = True
                    try:
                        await client.cancel_conditional_order(cond_order_id)
                        await AssassinLedger.save_state(symbol, cond_order_id="", target_sell_price=0.0, force_downgrade=False, pre_first_flag=False)
                        cond_order_id = ""
                        target_sell_price = 0.0
                        pre_first_flag = False
                        force_downgrade = False
                        await notify_tg(f"🚨 <b>[aVWAP {symbol}] 익절 덫 하향 인터럽트 발동</b>\n▫️ 사유: 프리장 듀얼 진입 시그널 감지\n▫️ 조치: +2.0% 덫 강제 파기 및 +1.0% 타점 자동 재장전")
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        print(f"🚨 [인터럽트 붕괴 방어] {e}", flush=True)
                        err_str = str(e).lower()
                        if "404" in err_str or "not-found" in err_str:
                            await AssassinLedger.save_state(symbol, cond_order_id="", target_sell_price=0.0, force_downgrade=False, pre_first_flag=False)
                            cond_order_id = ""
                            target_sell_price = 0.0
                            pre_first_flag = False
                            force_downgrade = False
                    finally:
                        in_memory_ordering_lock[symbol] = False
            
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

                    if avg_price <= 0.0:
                        avg_price = float(holdings_detail.get('avg_price', 0.0))

                    if avg_price > 0.0:
                        if entry_session == "preMarket":
                            if pre_first_flag:
                                calculated_target = math.ceil(avg_price * 1.02 * 100) / 100.0
                                trap_tag = "+2.0%"
                            else:
                                calculated_target = math.ceil(avg_price * 1.01 * 100) / 100.0
                                trap_tag = "+1.0%"
                        else:
                            calculated_target = math.ceil(avg_price * 1.01 * 100) / 100.0
                            trap_tag = "+1.0%"

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

            if not buy_order_id and not is_session_done and is_active and vwap_price > 0.0:
                is_time_shield = False
                elapsed = (now_est - session_baseline_est).total_seconds()
                
                if 0 <= elapsed < 420:
                    is_time_shield = True
                
                can_enter = False
                if hardcoded_session == "preMarket" and not is_time_shield:
                    can_enter = True
                
                if can_enter and current_price >= vwap_price:
                    breakout_ticks += 1
                else:
                    breakout_ticks = 0
                
                if can_enter and breakout_ticks >= 4:
                    if not in_memory_ordering_lock[symbol]:
                        in_memory_ordering_lock[symbol] = True
                        try:
                            orderbook = await client.get_orderbook(symbol)
                            asks = orderbook.get("asks", [])
                            
                            if asks:
                                ask_1_price = float(asks[0]["price"])
                            else:
                                ask_1_price = current_price
                                
                            if ask_1_price > 0.0:
                                target_qty = int(math.floor(budget / ask_1_price))
                                
                                if target_qty > 0:
                                    other_symbol = "SOXS" if symbol == "SOXL" else "SOXL"
                                    other_state = await AssassinLedger.get_state(other_symbol)
                                    other_buy_id = await AssassinLedger.get_buy_order_id(other_symbol)
                                    
                                    new_pre_first = False
                                    if hardcoded_session == "preMarket":
                                        other_price = other_state[0]
                                        other_is_done = other_state[3]
                                        
                                        if other_price > 0 or other_buy_id: 
                                            new_pre_first = False
                                            await AssassinLedger.save_state(other_symbol, force_downgrade=True)
                                            await notify_tg(f"⚠️ <b>[aVWAP {symbol}] 프리장 듀얼 동시 가동 포착</b>\n▫️ 타점 하향(1.0%) 소프트웨어 인터럽트 발송 완료")
                                        elif other_is_done:
                                            new_pre_first = False
                                        else:
                                            new_pre_first = True

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
                                        await AssassinLedger.save_state(symbol, buy_order_id=str(res["result"]["orderId"]), entry_session=hardcoded_session, pre_first_flag=new_pre_first)
                                    
                                    idempotency_keys[symbol]["BUY"] = None
                                    await notify_tg(f"🚀 <b>[aVWAP {symbol}] 돌파 요격 매수 (세션: {hardcoded_session})</b>\n▫️ aVWAP: ${vwap_price:.2f}\n▫️ 타격가: ${ask_1_price:.2f}\n▫️ 수량: {target_qty}주\n▫️ 확증: 타임쉴드 종속 4틱(6초) 돌파 방어망 통과")
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
    await api_client.fetch_account_seq()
    
    inject_dependencies(api_client, ADMIN_CHAT_ID, wakeup_event)
    dp.include_router(router)
    
    asyncio.create_task(api_client.token_renewal_loop())
    asyncio.create_task(assassin_loop(api_client, bot, ADMIN_CHAT_ID, "SOXL"))
    asyncio.create_task(assassin_loop(api_client, bot, ADMIN_CHAT_ID, "SOXS"))
    asyncio.create_task(record_candles_loop(api_client, "SOXL"))
    asyncio.create_task(record_candles_loop(api_client, "SOXS"))
    
    print("시스템 코어 및 듀얼 암살자(SOXL, SOXS) 방어망 결합 완료. 폴링 개시...", flush=True)
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.send_message(
            chat_id=ADMIN_CHAT_ID, 
            text="✅ <b>[시스템 기동 완료]</b>\n▫️ 서버 재부팅 및 듀얼 암살자 코어 결속\n▫️ 방어망 락온 및 폴링을 개시합니다.", 
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
