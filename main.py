# =====================================================================
# FILE: main.py
# 목적: SOXL, SOXS 듀얼 코어 암살자 엔진 가동 (aVWAP + 제로오버나잇) - 메인 통제소
# =====================================================================

import sys
import os
import math
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
    last_moc_minute = -1
    
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

            last_buy_price, budget, last_session_id, is_session_done, is_active, overnight_on, target_sell_price, cond_order_id, session_mode = await AssassinLedger.get_state(symbol)
            buy_order_id = await AssassinLedger.get_buy_order_id(symbol)

            # 17:00 EST 가비지 컬렉션
            if now_est.hour == 17 and now_est.minute == 0:
                in_memory_ordering_lock[symbol] = False
                idempotency_keys[symbol] = {"BUY": None, "TRAP": None, "MOC": None}
                last_moc_minute = -1
                if holdings_qty == 0:
                    await AssassinLedger.save_state(symbol, buy_order_id="", cond_order_id="")
                print(f"🧹 [GC {symbol}] 17:00 EST 락 해제 및 자정 초기화 완료.", flush=True)
                await asyncio.sleep(60)
                continue
            
            # API 캘린더 통신망 (is_open 여부만 참조, 시간은 로컬 하드코딩으로 대체)
            try:
                is_open, _, _, _ = await asyncio.wait_for(client.is_market_open(), timeout=10.0)
            except Exception:
                is_open = True

            # MODIFIED: 제4헌법 100% 로컬 하드코딩 락온 (토스 API VWAP 왜곡 방어)
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

            is_day_moc = (now_est.hour == 3 and 57 <= now_est.minute <= 59)
            is_reg_moc = (now_est.hour == 16 and 5 <= now_est.minute <= 7)

            # MOC 3-Step 강제 덤핑 스윕
            if (is_day_moc or is_reg_moc) and not overnight_on and is_active:
                if holdings_qty > 0 and not in_memory_ordering_lock[symbol]:
                    if last_moc_minute != now_est.minute:
                        in_memory_ordering_lock[symbol] = True
                        try:
                            if cond_order_id:
                                try:
                                    await client.cancel_conditional_order(cond_order_id)
                                    await AssassinLedger.save_state(symbol, cond_order_id="")
                                    await asyncio.sleep(0.5)
                                except Exception as e:
                                    print(f"🚨 [조건주문 취소 방어] {e}", flush=True)

                            dump_qty = holdings_qty
                            
                            if dump_qty > 0:
                                open_orders = await client.get_orders(status="OPEN", symbol=symbol)
                                if open_orders:
                                    for order in open_orders:
                                        await client.cancel_order(order["orderId"])
                                    await asyncio.sleep(0.5)
                                    
                                orderbook = await client.get_orderbook(symbol)
                                bids = orderbook.get("bids", [])
                                current_price = await client.get_current_price(symbol)
                                
                                if bids and float(bids[0]["price"]) > 0.0:
                                    bid_1_price = float(bids[0]["price"])
                                elif current_price > 0.0:
                                    bid_1_price = current_price
                                else:
                                    bid_1_price = 0.0
                                    
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
                                    
                                    await AssassinLedger.save_state(symbol, is_session_done=True)
                                    
                                    idempotency_keys[symbol]["MOC"] = None
                                    last_moc_minute = now_est.minute
                                    
                                    tag = "03:57~59 데이장" if is_day_moc else "16:05~07 애프터장"
                                    await notify_tg(f"🔴 <b>[aVWAP {symbol}] {tag} 제로오버나이트 강제 청산 스윕 ({now_est.minute}분 타격)</b>\n▫️ 덤핑 1호가: ${bid_1_price:.2f}\n▫️ 수량: {dump_qty}주")
                        except Exception as e:
                            print(f"🚨 [MOC 방어] {e}", flush=True)
                            await notify_tg(f"🚨 <b>[MOC 에러 {symbol}]</b> {html.escape(str(e))}")
                        finally:
                            in_memory_ordering_lock[symbol] = False
                
                continue

            if not is_open:
                continue
                
            current_price = await client.get_current_price(symbol)
            if current_price <= 0.0:
                continue

            # 세션 전환 시 장부 초기화 (MODIFIED: 매수 ID 증발 방어망 결속)
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
                        await AssassinLedger.save_state(symbol, price=0.0, target_sell_price=0.0, last_session_id=current_session_id, is_session_done=False, buy_order_id="", cond_order_id="")
                        is_session_done = False
                        target_sell_price = 0.0
                        buy_order_id = ""
                        cond_order_id = ""
                else:
                    await AssassinLedger.save_state(symbol, last_session_id=current_session_id)
                last_session_id = current_session_id

            # 보유 물량 0 & 장부 잔여물 소각 (MODIFIED: 매수 ID 증발 원자적 방어)
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
                        await AssassinLedger.save_state(symbol, price=0.0, target_sell_price=0.0, buy_order_id="", cond_order_id="")
                        target_sell_price = 0.0
                        buy_order_id = ""
                        cond_order_id = ""

            candles_json = await fetch_full_session_candles(client, symbol, session_baseline_est)
            vwap_price = AVWAPEngine.calculate_vwap(candles_json, session_baseline_est)

            # 정규장 진입 시 신규 매수 권한 소각
            if est_time_int >= 930 and est_time_int < 1600:
                if not buy_order_id and not is_session_done:
                    await AssassinLedger.save_state(symbol, is_session_done=True)
                    is_session_done = True
                    print(f"🎯 [aVWAP {symbol}] 정규장 진입. 당일 신규 매수 권한 소각 완료.", flush=True)

            open_orders = await client.get_orders(status="OPEN", symbol=symbol)
            has_open_sell = any(o["side"] == "SELL" for o in open_orders)
            has_open_buy = any(o["side"] == "BUY" for o in open_orders)
            
            # 보유 물량 확인 즉시 익절 조건주문 덫 장전 (MODIFIED: 체결 100% 검증 락온)
            if holdings_qty > 0 and not has_open_sell and not has_open_buy and not cond_order_id and not in_memory_ordering_lock[symbol] and is_active:
                calculated_target = target_sell_price
                trap_qty = holdings_qty
                avg_price = last_buy_price
                is_rearm = True
                trap_tag = "" 
                
                if calculated_target <= 0.0 and buy_order_id:
                    order_detail = await client.get_order_detail(buy_order_id)
                    status = order_detail.get("status", "")
                    
                    if status in ["FILLED", "PARTIAL_FILLED", "CANCELED", "REJECTED"]:
                        filled_qty = int(math.floor(float(order_detail.get("execution", {}).get("filledQuantity", 0.0))))
                        avg_price = float(order_detail.get("execution", {}).get("averageFilledPrice", 0.0))
                        
                        if filled_qty > 0 and avg_price > 0.0:
                            trap_qty = min(holdings_qty, filled_qty)
                            if hardcoded_session == "dayMarket":
                                calculated_target = math.ceil(avg_price * 1.007 * 100) / 100.0
                                trap_tag = "+0.7%"
                            else:
                                calculated_target = math.ceil(avg_price * 1.01 * 100) / 100.0
                                trap_tag = "+1.0%"
                            is_rearm = False

                # Fallback: 기존 보유 포지션 재장전
                if calculated_target <= 0.0 and avg_price <= 0.0:
                    avg_price = float(holdings_detail.get('avg_price', 0.0))
                    if avg_price > 0.0:
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

            # 돌파/추종 매수 트리거 감시
            if not buy_order_id and not is_session_done and is_active and vwap_price > 0.0:
                is_time_shield = False
                elapsed = (now_est - session_baseline_est).total_seconds()
                if 0 <= elapsed <= 360:
                    is_time_shield = True
                
                can_enter = False
                if hardcoded_session == "preMarket" and not is_time_shield:
                    can_enter = True
                elif hardcoded_session == "dayMarket" and session_mode == "BOTH" and not is_time_shield:
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
                            print(f"🚨 [BUY 방어] {e}", flush=True)
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
