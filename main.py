# =====================================================================
# 파일명: main.py
# 목적: SOXL, SOXS 듀얼 코어 암살자 엔진 가동 (aVWAP + 제로오버나잇) - 메인 통제소
# =====================================================================

import sys
import os
import math
import asyncio
import html
import pandas as pd
from datetime import datetime
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

# Case 27 & Case 34 인메모리 락 및 멱등성 키 보존 딕셔너리
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
            # 초과 Case 28: 1.5초 폴링 제어 (동기 블로킹 방어)
            await asyncio.wait_for(wakeup_event.wait(), timeout=1.5)
            wakeup_event.clear()
        except asyncio.TimeoutError:
            pass
        
        try:
            now_est = datetime.now(ZoneInfo('America/New_York'))
            est_today_str = now_est.strftime("%Y-%m-%d")

            # Case 22: 17:00 EST 가비지 컬렉션 (GC) 파이프라인
            if now_est.hour == 17 and now_est.minute == 0:
                in_memory_ordering_lock[symbol] = False
                idempotency_keys[symbol] = {"BUY": None, "TRAP": None, "MOC": None}
                print(f"🧹 [GC {symbol}] 17:00 EST 락 해제 및 자정 초기화 완료.", flush=True)
                await asyncio.sleep(60)
                continue

            last_buy_price, budget, last_session_id, is_session_done, is_active, overnight_on, target_sell_price = await AssassinLedger.get_state(symbol)
            
            # Case 19 & 29 로컬 장부 팩트 기반 API 에러 붕괴 방어
            try:
                holdings_detail = await client.get_symbol_holdings_detail(symbol)
                holdings_qty = int(math.floor(holdings_detail['qty']))
            except Exception as e:
                await notify_tg(f"🚨 <b>[aVWAP {symbol}] 통신 붕괴 (유령 잔고 방어)</b>\n▫️ 사유: {html.escape(str(e))}")
                await asyncio.sleep(5)
                continue
            
            # Case 10 & 16: 캘린더 지연 방어 Fail-Open
            try:
                is_open, session_end_time, session_name, session_start_time = await asyncio.wait_for(client.is_market_open(), timeout=10.0)
            except Exception:
                is_open = True
                session_name = "regularMarket" if 9 <= now_est.hour < 16 else "preMarket"
                session_start_time = None
                print(f"🚨 [aVWAP {symbol}] 캘린더 응답 지연. Fail-Open 정규장 간주 진입.", flush=True)

            # 15:59 MOC 제로-오버나이트 덤핑 (시장 오픈 변수 무시하고 시간 도달 시 즉각 격발)
            if now_est.hour == 15 and now_est.minute >= 59 and not overnight_on:
                if holdings_qty > 0 and not in_memory_ordering_lock[symbol]:
                    in_memory_ordering_lock[symbol] = True
                    try:
                        open_orders = await client.get_orders(status="OPEN", symbol=symbol)
                        if open_orders:
                            for order in open_orders:
                                await client.cancel_order(order["orderId"])
                            await asyncio.sleep(0.5)
                            
                        orderbook = await client.get_orderbook(symbol)
                        bids = orderbook.get("bids", [])
                        
                        # NEW: Case 24 호가창 결측치 붕괴 방어용 현재가 폴백 하드코딩
                        if bids:
                            bid_1_price = float(bids[0]["price"])
                        else:
                            bid_1_price = await client.get_current_price(symbol)
                            
                        if bid_1_price > 0.0:
                            # Case 34: 멱등성 사수 방어망
                            client_id = idempotency_keys[symbol]["MOC"]
                            if not client_id:
                                client_id = f"MOC_{symbol}_{now_est.strftime('%Y%m%d_%H%M%S')}"
                                idempotency_keys[symbol]["MOC"] = client_id

                            await client.create_order(
                                symbol=symbol, side="SELL", order_type="LIMIT",
                                quantity=holdings_qty, price=f"{bid_1_price:.2f}",
                                client_order_id=client_id
                            )
                            # 성공 시 기억 소각
                            idempotency_keys[symbol]["MOC"] = None
                            
                            await AssassinLedger.save_state(symbol, price=0.0, target_sell_price=0.0, is_session_done=True)
                            await notify_tg(f"🔴 <b>[aVWAP {symbol}] 15:59 제로오버나이트 강제 청산</b>\n▫️ 타격가: ${bid_1_price:.2f}\n▫️ 수량: {holdings_qty}주")
                            print(f"🧹 [aVWAP {symbol}] 15:59 MOC 덤핑 스윕 완료.", flush=True)
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

            if session_start_time:
                current_session_id = f"{est_today_str}_{session_name}"
                if current_session_id != last_session_id:
                    if holdings_qty == 0:
                        await AssassinLedger.save_state(symbol, price=0.0, target_sell_price=0.0, last_session_id=current_session_id, is_session_done=False)
                        is_session_done = False
                        target_sell_price = 0.0
                    else:
                        await AssassinLedger.save_state(symbol, last_session_id=current_session_id)
                    last_session_id = current_session_id

            if holdings_qty == 0 and target_sell_price > 0.0 and not in_memory_ordering_lock[symbol]:
                await AssassinLedger.save_state(symbol, price=0.0, target_sell_price=0.0)
                target_sell_price = 0.0
            
            session_baseline_est = session_start_time.astimezone(ZoneInfo('America/New_York')) if session_start_time else now_est
            if session_name in ["regularMarket", "afterMarket"]:
                reg_start_str = f"{est_today_str} 09:30:00"
                reg_start_est = datetime.strptime(reg_start_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo('America/New_York'))
                if now_est >= reg_start_est:
                    session_baseline_est = reg_start_est

            candles_json = await fetch_full_session_candles(client, symbol, session_baseline_est)
            vwap_price = AVWAPEngine.calculate_vwap(candles_json, session_baseline_est)

            # 09:30 정규장 오픈 시 잔고 0이면 신규 진입 원천 차단 (퇴근 락온)
            if now_est.hour >= 9 and now_est.minute >= 30:
                if holdings_qty == 0 and not is_session_done:
                    await AssassinLedger.save_state(symbol, is_session_done=True)
                    is_session_done = True
                    print(f"🎯 [aVWAP {symbol}] 정규장 진입 & 무포지션 팩트 확인. 당일 신규 매수 영구 소각.", flush=True)

            open_orders = await client.get_orders(status="OPEN", symbol=symbol)
            has_open_sell = any(o["side"] == "SELL" for o in open_orders)
            
            # 보유 물량 존재 시, +1.0% 고정 익절 덫 장전
            if holdings_qty > 0 and target_sell_price <= 0.0 and not has_open_sell and not in_memory_ordering_lock[symbol]:
                avg_price = holdings_detail.get('avg_price', current_price)
                if avg_price <= 0.0: avg_price = current_price
                calculated_target = round(avg_price * 1.01, 2)
                
                in_memory_ordering_lock[symbol] = True
                try:
                    # Case 34: 멱등성 사수 방어망
                    client_id = idempotency_keys[symbol]["TRAP"]
                    if not client_id:
                        client_id = f"TRAP_{symbol}_{now_est.strftime('%Y%m%d_%H%M%S')}"
                        idempotency_keys[symbol]["TRAP"] = client_id

                    await client.create_order(
                        symbol=symbol, side="SELL", order_type="LIMIT",
                        quantity=holdings_qty, price=f"{calculated_target:.2f}",
                        client_order_id=client_id
                    )
                    idempotency_keys[symbol]["TRAP"] = None
                    
                    await AssassinLedger.save_state(symbol, price=avg_price, target_sell_price=calculated_target)
                    await notify_tg(f"🟢 <b>[aVWAP {symbol}] +1% 기계적 매도 덫 장전</b>\n▫️ 평단가: ${avg_price:.2f}\n▫️ 익절 덫: ${calculated_target:.2f}\n▫️ 수량: {holdings_qty}주")
                except Exception as e:
                    print(f"🚨 [TRAP Timeout 방어] {e}", flush=True)
                    await notify_tg(f"🚨 <b>[TRAP 에러 {symbol}]</b> {html.escape(str(e))}")
                finally:
                    in_memory_ordering_lock[symbol] = False
                continue

            # aVWAP 돌파 감시 및 매수 요격 (소프트웨어 트리거)
            if holdings_qty == 0 and not is_session_done and is_active and vwap_price > 0.0:
                is_time_shield = (now_est.hour == 4 and now_est.minute <= 6)
                if session_name == "preMarket" and not is_time_shield and current_price >= vwap_price:
                    if not in_memory_ordering_lock[symbol]:
                        in_memory_ordering_lock[symbol] = True
                        try:
                            orderbook = await client.get_orderbook(symbol)
                            asks = orderbook.get("asks", [])
                            
                            # NEW: Case 15 호가창 결측치 방어용 현재가 폴백 락온
                            if asks:
                                ask_1_price = float(asks[0]["price"])
                            else:
                                ask_1_price = current_price
                                
                            if ask_1_price > 0.0:
                                target_qty = int(math.floor(budget / ask_1_price))
                                
                                if target_qty > 0:
                                    # Case 34: 멱등성 사수 방어망
                                    client_id = idempotency_keys[symbol]["BUY"]
                                    if not client_id:
                                        client_id = f"BUY_{symbol}_{now_est.strftime('%Y%m%d_%H%M%S')}"
                                        idempotency_keys[symbol]["BUY"] = client_id

                                    await client.create_order(
                                        symbol=symbol, side="BUY", order_type="LIMIT",
                                        quantity=target_qty, price=f"{ask_1_price:.2f}",
                                        client_order_id=client_id
                                    )
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
