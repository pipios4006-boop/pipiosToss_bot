# =====================================================================
# FILE: main.py
# 목적: SOXL, SOXS 듀얼 코어 암살자 엔진 가동 (aVWAP + 제로오버나잇) - 메인 통제소
# =====================================================================

import sys
import os
import math
import asyncio
import html
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from dotenv import load_dotenv

from toss_api import TossApiClient
from quant_engine import AssassinLedger, AVWAPEngine
from tg_router import router, inject_dependencies

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

async def fetch_full_session_candles(client: TossApiClient, symbol: str, session_start_est: datetime) -> list:
    all_candles = []
    before = None
    
    for _ in range(5): 
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

            # MODIFIED: session_mode 확장 추출
            last_buy_price, budget, last_session_id, is_session_done, is_active, overnight_on, target_sell_price, cond_order_id, session_mode = await AssassinLedger.get_state(symbol)
            buy_order_id = await AssassinLedger.get_buy_order_id(symbol)

            # Case 22: 17:00 EST 가비지 컬렉션 (GC) 파이프라인
            if now_est.hour == 17 and now_est.minute == 0:
                in_memory_ordering_lock[symbol] = False
                idempotency_keys[symbol] = {"BUY": None, "TRAP": None, "MOC": None}
                if holdings_qty == 0:
                    await AssassinLedger.save_state(symbol, buy_order_id="", cond_order_id="")
                print(f"🧹 [GC {symbol}] 17:00 EST 락 해제 및 자정 초기화 완료.", flush=True)
                await asyncio.sleep(60)
                continue
            
            try:
                is_open, session_end_time, session_name, session_start_time = await asyncio.wait_for(client.is_market_open(), timeout=10.0)
            except Exception:
                is_open = True
                session_name = "regularMarket" if 930 <= est_time_int < 1600 else "preMarket"
                session_start_time = None
                print(f"🚨 [aVWAP {symbol}] 캘린더 응답 지연. Fail-Open 정규장 간주 진입.", flush=True)

            # MODIFIED: 03:59(Day) 및 15:59(Reg) 듀얼 MOC 제로-오버나이트 덤핑 사수
            is_day_moc = (now_est.hour == 3 and now_est.minute >= 59)
            is_reg_moc = (now_est.hour == 15 and now_est.minute >= 59)

            if (is_day_moc or is_reg_moc) and not overnight_on and is_active:
                if buy_order_id and not in_memory_ordering_lock[symbol]:
                    in_memory_ordering_lock[symbol] = True
                    try:
                        # 🚨 덤핑 격발 전 로컬 장부에 기록된 조건주문을 선취소 (공통)
                        if cond_order_id:
                            try:
                                await client.cancel_conditional_order(cond_order_id)
                                await asyncio.sleep(0.5)
                            except Exception as e:
                                print(f"🚨 [조건주문 취소 붕괴 방어] {e}", flush=True)

                        order_detail = await client.get_order_detail(buy_order_id)
                        filled_qty = int(math.floor(float(order_detail.get("execution", {}).get("filledQuantity", 0.0))))
                        
                        dump_qty = min(holdings_qty, filled_qty) if holdings_qty > 0 else 0
                        
                        if dump_qty > 0:
                            open_orders = await client.get_orders(status="OPEN", symbol=symbol)
                            if open_orders:
                                for order in open_orders:
                                    await client.cancel_order(order["orderId"])
                                await asyncio.sleep(0.5)
                                
                            orderbook = await client.get_orderbook(symbol)
                            bids = orderbook.get("bids", [])
                            
                            if bids:
                                bid_1_price = float(bids[0]["price"])
                            else:
                                bid_1_price = await client.get_current_price(symbol)
                                
                            if bid_1_price > 0.0:
                                client_id = idempotency_keys[symbol]["MOC"]
                                if not client_id:
                                    client_id = f"MOC_{symbol}_{now_est.strftime('%Y%m%d_%H%M%S')}"
                                    idempotency_keys[symbol]["MOC"] = client_id

                                await client.create_order(
                                    symbol=symbol, side="SELL", order_type="LIMIT",
                                    quantity=dump_qty, price=f"{bid_1_price:.2f}",
                                    client_order_id=client_id
                                )
                                
                                await AssassinLedger.save_state(symbol, price=0.0, target_sell_price=0.0, is_session_done=True, buy_order_id="", cond_order_id="")
                                idempotency_keys[symbol]["MOC"] = None
                                
                                tag = "03:59 데이장" if is_day_moc else "15:59 정규장"
                                await notify_tg(f"🔴 <b>[aVWAP {symbol}] {tag} 제로오버나이트 강제 청산</b>\n▫️ 타격가: ${bid_1_price:.2f}\n▫️ 수량: {dump_qty}주")
                                print(f"🧹 [aVWAP {symbol}] {tag} MOC 덤핑 스윕 완료.", flush=True)
                    except Exception as e:
                        print(f"🚨 [MOC Timeout 방어] {e}", flush=True)
                        await notify_tg(f"🚨 <b>[MOC 에러 {symbol}]</b> {html.escape(str(e))}")
                    finally:
                        in_memory_ordering_lock[symbol] = False
                continue

            if not is_open:
                continue
                
            current_price = await client.get_current_price(symbol)
            if current_price <= 0.0:
                continue

            # MODIFIED: Midnight Crossover 방어를 위해 session_start_time 기반 절대 세션 ID 생성
            if session_start_time:
                session_start_est = session_start_time.astimezone(ZoneInfo('America/New_York'))
                current_session_id = f"{session_start_est.strftime('%Y%m%d_%H%M')}_{session_name}"
                if current_session_id != last_session_id:
                    if holdings_qty == 0:
                        await AssassinLedger.save_state(symbol, price=0.0, target_sell_price=0.0, last_session_id=current_session_id, is_session_done=False, buy_order_id="", cond_order_id="")
                        is_session_done = False
                        target_sell_price = 0.0
                        buy_order_id = ""
                        cond_order_id = ""
                    else:
                        await AssassinLedger.save_state(symbol, last_session_id=current_session_id)
                    last_session_id = current_session_id

            if holdings_qty == 0 and (target_sell_price > 0.0 or buy_order_id or cond_order_id):
                if not in_memory_ordering_lock[symbol]:
                    await AssassinLedger.save_state(symbol, price=0.0, target_sell_price=0.0, buy_order_id="", cond_order_id="")
                    target_sell_price = 0.0
                    buy_order_id = ""
                    cond_order_id = ""
            
            session_baseline_est = session_start_time.astimezone(ZoneInfo('America/New_York')) if session_start_time else now_est
            if session_name in ["regularMarket", "afterMarket"]:
                reg_start_str = f"{now_est.strftime('%Y-%m-%d')} 09:30:00"
                reg_start_est = datetime.strptime(reg_start_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo('America/New_York'))
                if now_est >= reg_start_est:
                    session_baseline_est = reg_start_est

            candles_json = await fetch_full_session_candles(client, symbol, session_baseline_est)
            vwap_price = AVWAPEngine.calculate_vwap(candles_json, session_baseline_est)

            # 정규장 신규 진입 원천 소각 (100% 락온)
            if est_time_int >= 930 and est_time_int < 1600:
                if not buy_order_id and not is_session_done:
                    await AssassinLedger.save_state(symbol, is_session_done=True)
                    is_session_done = True
                    print(f"🎯 [aVWAP {symbol}] 정규장 진입 & 무포지션 팩트 확인. 당일 신규 매수 영구 소각.", flush=True)

            open_orders = await client.get_orders(status="OPEN", symbol=symbol)
            has_open_sell = any(o["side"] == "SELL" for o in open_orders)
            
            if holdings_qty > 0 and not has_open_sell and not cond_order_id and not in_memory_ordering_lock[symbol] and is_active:
                calculated_target = target_sell_price
                trap_qty = holdings_qty
                avg_price = last_buy_price
                is_rearm = True
                
                if calculated_target <= 0.0 and buy_order_id:
                    order_detail = await client.get_order_detail(buy_order_id)
                    status = order_detail.get("status", "")
                    
                    if status in ["FILLED", "PARTIAL_FILLED", "CANCELED", "REJECTED"]:
                        filled_qty = int(math.floor(float(order_detail.get("execution", {}).get("filledQuantity", 0.0))))
                        avg_price = float(order_detail.get("execution", {}).get("averageFilledPrice", 0.0))
                        
                        if filled_qty > 0 and avg_price > 0.0:
                            trap_qty = min(holdings_qty, filled_qty)
                            calculated_target = math.ceil(avg_price * 1.01 * 100) / 100.0
                            is_rearm = False

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
                        
                        new_cond_id = ""
                        if res and isinstance(res, dict) and res.get("result", {}).get("conditionalOrderId"):
                            new_cond_id = str(res["result"]["conditionalOrderId"])
                        
                        if not is_rearm:
                            await AssassinLedger.save_state(symbol, price=avg_price, target_sell_price=calculated_target, cond_order_id=new_cond_id)
                            await notify_tg(f"🟢 <b>[aVWAP {symbol}] +1% 기계적 조건주문 덫 장전</b>\n▫️ 팩트 평단가: ${avg_price:.2f}\n▫️ 익절 덫: ${calculated_target:.2f}\n▫️ 수량: {trap_qty}주")
                        else:
                            await AssassinLedger.save_state(symbol, cond_order_id=new_cond_id)
                            await notify_tg(f"🟢 <b>[aVWAP {symbol}] 오버나이트 조건주문 덫 재장전</b>\n▫️ 유지 평단가: ${avg_price:.2f}\n▫️ 익절 덫: ${calculated_target:.2f}\n▫️ 수량: {trap_qty}주")
                            
                        idempotency_keys[symbol]["TRAP"] = None
                    except Exception as e:
                        print(f"🚨 [TRAP Timeout 방어] {e}", flush=True)
                        await notify_tg(f"🚨 <b>[TRAP 에러 {symbol}]</b> {html.escape(str(e))}")
                    finally:
                        in_memory_ordering_lock[symbol] = False
                continue

            if not buy_order_id and not is_session_done and is_active and vwap_price > 0.0:
                
                # MODIFIED: DST 변동을 무시하는 Dynamic Time Shield (+6분 절대 방어막)
                is_time_shield = False
                if session_start_time:
                    session_start_est_check = session_start_time.astimezone(ZoneInfo('America/New_York'))
                    elapsed = (now_est - session_start_est_check).total_seconds()
                    if 0 <= elapsed <= 360:
                        is_time_shield = True
                
                # MODIFIED: 세션 진입 조건 확장 (session_mode 연동)
                can_enter = False
                if session_name == "preMarket" and not is_time_shield:
                    can_enter = True
                elif session_name == "dayMarket" and session_mode == "BOTH" and not is_time_shield:
                    can_enter = True
                
                if can_enter and current_price >= vwap_price:
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
                                    client_id = idempotency_keys[symbol]["BUY"]
                                    if not client_id:
                                        client_id = f"BUY_{symbol}_{now_est.strftime('%Y%m%d_%H%M%S')}"
                                        idempotency_keys[symbol]["BUY"] = client_id

                                    res = await client.create_order(
                                        symbol=symbol, side="BUY", order_type="LIMIT",
                                        quantity=target_qty, price=f"{ask_1_price:.2f}",
                                        client_order_id=client_id
                                    )
                                    
                                    if res and isinstance(res, dict) and res.get("result", {}).get("orderId"):
                                        await AssassinLedger.save_state(symbol, buy_order_id=str(res["result"]["orderId"]))
                                    
                                    idempotency_keys[symbol]["BUY"] = None
                                    await notify_tg(f"🚀 <b>[aVWAP {symbol}] 돌파 요격 매수</b>\n▫️ aVWAP: ${vwap_price:.2f}\n▫️ 타격가: ${ask_1_price:.2f}\n▫️ 수량: {target_qty}주")
                        except Exception as e:
                            print(f"🚨 [BUY Timeout 방어] {e}", flush=True)
                            await notify_tg(f"🚨 <b>[BUY 에러 {symbol}]</b> {html.escape(str(e))}")
                        finally:
                            in_memory_ordering_lock[symbol] = False

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
