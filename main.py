# =====================================================================
# 파일명: main.py
# 목적: 분리된 플러그인 모듈 의존성 주입 및 +1% 도달 후 EMA 10 덤핑 가동 (Activation Trailing Mode)
# =====================================================================

import asyncio
import os
import sys
import html
import math
from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from dotenv import load_dotenv

from toss_api import TossApiClient
from quant_engine import HAStateManager, HeikinAshiEngine
from tg_router import router, inject_dependencies

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(dotenv_path=env_path)

TOSS_CLIENT_ID = os.getenv("TOSS_CLIENT_ID")
TOSS_CLIENT_SECRET = os.getenv("TOSS_CLIENT_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
_telegram_chat_id_str = os.getenv("TELEGRAM_CHAT_ID")

if not all([TOSS_CLIENT_ID, TOSS_CLIENT_SECRET, TELEGRAM_BOT_TOKEN, _telegram_chat_id_str]):
    print("🚨 치명적 에러: 필수 자격증명 환경변수 누락.", flush=True)
    sys.exit(1)

ADMIN_CHAT_ID = int(_telegram_chat_id_str)
wakeup_event = asyncio.Event()

async def ha_assassin_loop(client: TossApiClient, bot: Bot, chat_id: int):
    last_action_candle_time = None
    
    async def notify_tg(text: str):
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        except Exception as e:
            print(f"🚨 [텔레그램 전송 붕괴 방어] {e}", flush=True)

    try:
        await client.fetch_account_seq()
    except Exception as e:
        print(f"🚨 [HA 암살자] 초기 계좌 정보 로드 실패: {e}", flush=True)
        
    while True:
        try:
            await asyncio.wait_for(wakeup_event.wait(), timeout=60.0)
            wakeup_event.clear()
            print("⚡ [HA 암살자] 관제탑 실시간 인터럽트 수신. 60초 대기 스킵 및 즉시 타점 스캔 가동.", flush=True)
        except asyncio.TimeoutError:
            pass
        
        try:
            last_buy_price, target_qty, target_sell_price, last_session_id, is_session_done, is_active, is_trailing_active = await HAStateManager.get_state()
            now_est = datetime.now(ZoneInfo('America/New_York'))
            
            is_open, session_end_time, session_name, session_start_time = await client.is_market_open()
            if not is_open:
                continue
                
            raw_soxl_qty = await client.get_soxl_holdings()
            soxl_qty = int(math.floor(float(raw_soxl_qty)))

            if session_start_time:
                current_session_id = f"{session_start_time.strftime('%Y%m%d')}_{session_name}"
                if current_session_id != last_session_id:
                    if soxl_qty == 0:
                        await HAStateManager.save_state(price=0.0, target_sell_price=0.0, last_session_id=current_session_id, is_session_done=False, is_trailing_active=False)
                        last_buy_price = 0.0
                        target_sell_price = 0.0
                        is_trailing_active = False
                        print(f"♻️ [HA 암살자] 새 세션({session_name}) 진입. 상태 제로화 및 영업 개시.", flush=True)
                    else:
                        await HAStateManager.save_state(last_session_id=current_session_id, is_session_done=False)
                        print(f"♻️ [HA 암살자] 새 세션({session_name}) 진입. 오버나이트 물량 및 평단가 보존 개시.", flush=True)
                    last_session_id = current_session_id
                    is_session_done = False
            
            if soxl_qty == 0 and last_buy_price > 0.0:
                await HAStateManager.save_state(price=0.0, target_sell_price=0.0, is_trailing_active=False)
                last_buy_price = 0.0
                target_sell_price = 0.0
                is_trailing_active = False
                print(f"♻️ [HA 암살자] 수동 청산 팩트 교정: 오염된 장부가 0.0 강제 동기화.", flush=True)

            if session_end_time and (session_end_time - now_est).total_seconds() <= 120:
                try:
                    open_orders = await client.get_orders(status="OPEN", symbol="SOXL")
                    if open_orders:
                        for order in open_orders:
                            await client.cancel_order(order["orderId"])
                            print(f"🧹 [HA 암살자] 세션 마감 2분 전 미체결 덫({order['orderId']}) 안전 취소 완료.", flush=True)
                except Exception as e:
                    pass
                continue
            
            current_price = await client.get_current_price("SOXL")
            if current_price <= 0.0:
                continue

            # NEW: 1% 수익 도달 시 EMA 10 방어망 기상(Wake-up) 로직
            if soxl_qty >= 1 and last_buy_price > 0.0:
                if not is_trailing_active:
                    activation_price = last_buy_price * 1.01
                    if current_price >= activation_price:
                        is_trailing_active = True
                        await HAStateManager.save_state(is_trailing_active=True)
                        print(f"🚀 [HA 암살자] +1% 수익 라인(${activation_price:.2f}) 터치 팩트! 즉시 EMA 10 매도 방어망 기상 락온.", flush=True)
                        await notify_tg("🚀 <b>[HA 암살자] +1% 안전권 도달 확정</b>\n\n▫️ <b>방어망 상태</b>: 🟢 EMA 10 매도 추적 가동\n▫️ <b>종목</b>: SOXL\n▫️ <b>현재가</b>: ${:.2f}".format(current_price))

            candles_task = client.get_1m_candles("SOXL", count=200)
            daily_candles_task = client.get_daily_candles("SOXL", count=6)
            candles_json, daily_candles_json = await asyncio.gather(candles_task, daily_candles_task)
            
            ha_df = HeikinAshiEngine.calculate_5m_ha(candles_json)
            avg_stamina = HeikinAshiEngine.calculate_amplitude_stamina(daily_candles_json)
            
            if len(ha_df) < 4:
                continue
                
            if session_end_time is None:
                if (now_est - ha_df.index[-1]).total_seconds() > 300:
                    continue

            current_amp = 0.0
            session_open_price = 0.0
            if session_start_time is not None and not ha_df.empty:
                session_start_est = session_start_time.astimezone(ZoneInfo('America/New_York'))
                session_candles = ha_df[ha_df.index >= session_start_est]
                
                if not session_candles.empty:
                    session_open_price = session_candles.iloc[0]['HA_Open']
                    current_amp = await HeikinAshiEngine.get_dynamic_session_amp(session_start_est, session_name, session_candles)

            c3 = ha_df.iloc[-4]
            c1 = ha_df.iloc[-3]
            c2 = ha_df.iloc[-2]
            c0 = ha_df.iloc[-1]
            current_closed_time = c2.name
            
            is_c1_yang = c1['HA_Close'] >= c1['HA_Open']
            is_c2_yang = c2['HA_Close'] >= c2['HA_Open']
            is_c0_eum = c0['HA_Close'] < c0['HA_Open']
            
            c2_shaved_bottom = ((c2['HA_Open'] - c2['HA_Low']) / c2['HA_Open'] < 0.0005) if c2['HA_Open'] > 0 else False
            
            is_up_trend = c2['EMA_5'] > c2['EMA_10']
            
            gap_shield_block = False
            if session_start_time:
                elapsed_sec = (now_est - session_start_time).total_seconds()
                if elapsed_sec <= 3600:
                    if is_c0_eum or (c0['HA_Close'] < session_open_price):
                        gap_shield_block = True

            stamina_exhausted = (avg_stamina > 0.0) and (current_amp >= avg_stamina * 0.95)
            
            # MODIFIED: target_sell_price에는 1% 고정가가 아닌, 3분마다 갱신되는 EMA 10 지표가 지속 락온됨
            if soxl_qty >= 1:
                dynamic_target = c2['EMA_10']
                if abs(target_sell_price - dynamic_target) > 0.001:
                    target_sell_price = dynamic_target
                    await HAStateManager.save_state(target_sell_price=target_sell_price)

            buy_signal = False
            dynamic_sell_signal = False
            
            if last_action_candle_time != current_closed_time:
                raw_buy_signal = ((is_c2_yang and c2_shaved_bottom) or (is_c1_yang and is_c2_yang)) and is_up_trend
                
                if raw_buy_signal:
                    if gap_shield_block:
                        print(f"🛡️ [HA 암살자] Track B&C 쉴드 가동: {session_name} 개장 직후 갭 하락 감지. 유령 타점 소각.", flush=True)
                    elif stamina_exhausted:
                        print(f"🛡️ [HA 암살자] Track A 방어막 가동: 체력({avg_stamina*100:.2f}%) 고갈. 타점 소각.", flush=True)
                    elif is_session_done:
                        print(f"🛡️ [HA 암살자] Track D 퇴근 방어막 가동: 금일 매매 종료 락다운 상태. 매수 원천 차단.", flush=True)
                    elif not is_active:
                        print(f"🛡️ [HA 암살자] Track E 수면 방어막 가동: 관제탑 OFF 상태. 신규 매수 전면 락다운.", flush=True)
                    elif session_name != "preMarket":
                        print(f"🛡️ [HA 암살자] Track F 세션 쉴드 가동: 현재 세션({session_name}) 매수 불가 (오직 preMarket 한정).", flush=True)
                    else:
                        buy_signal = True

                # MODIFIED: 매도 조건. 방어망(is_trailing_active)이 켜져 있을 때만 EMA 10 하향 이탈을 판별하여 덤핑
                if soxl_qty >= 1 and target_sell_price > 0.0:
                    if c2['HA_Close'] < target_sell_price:
                        if not is_active:
                            print(f"🛡️ [HA 암살자] 수면 모드(OFF) 가동 중. 방어선 이탈 시에도 매도 타격 100% 락다운.", flush=True)
                        elif not is_trailing_active:
                            pass # 1% 미도달 상태이므로 EMA 10이 깨져도 관망 (Hold) 유지
                        else:
                            dynamic_sell_signal = True

            # 정규장 진입 시 무포지션이면 당일 100% 퇴근 락온
            if soxl_qty == 0 and session_name in ["regularMarket", "afterMarket"] and not is_session_done:
                await HAStateManager.save_state(is_session_done=True)
                is_session_done = True
                print(f"🎯 [HA 암살자] 프리마켓 스나이핑 기회 소멸. 무포지션 팩트 확인으로 당일 즉시 퇴근 락온.", flush=True)
            
            need_action = buy_signal or dynamic_sell_signal or (soxl_qty >= 1 and last_buy_price <= 0.0)
            if not need_action:
                continue
            
            if soxl_qty >= 1 and last_buy_price <= 0.0:
                last_buy_price = current_price
                await HAStateManager.save_state(price=last_buy_price)
                print(f"♻️ [HA 암살자] 유령 잔고 자가 치유: 현재가(${last_buy_price:.2f}) 앵커링 완료.", flush=True)
            
            if not (buy_signal or dynamic_sell_signal):
                continue

            open_orders = await client.get_orders(status="OPEN", symbol="SOXL")
            if open_orders:
                print("⚠️ [HA 암살자] 미체결 대기 주문(Limit-Trap) 감지. 스위퍼 자동 가동.", flush=True)
                for order in open_orders:
                    try:
                        await client.cancel_order(order["orderId"])
                        print(f"🧹 [HA 암살자] 덫 자동 해제: 지연 주문({order['orderId']}) 강제 취소 타격.", flush=True)
                    except Exception as e:
                        pass
                continue
                
            now_est_str = now_est.strftime("%Y-%m-%d %H:%M:%S EST")
            client_order_id_suffix = now_est.strftime("%Y%m%d_%H%M%S")
            
            if buy_signal and soxl_qty == 0:
                orderbook = await client.get_orderbook("SOXL")
                asks = orderbook.get("asks", [])
                
                if not asks:
                    continue
                    
                ask_1_price = float(asks[0]["price"])
                usd_bp = await client.get_usd_buying_power()
                actual_buy_qty = target_qty
                
                required_bp = ask_1_price * actual_buy_qty * 1.03
                if usd_bp < required_bp:
                    print(f"⚠️ [HA 암살자] 자본 잠김 컷오프: 증거금 버퍼(${required_bp:.2f}) 부족. 타점 소각.", flush=True)
                    continue
                    
                await client.create_order(
                    symbol="SOXL", side="BUY", order_type="LIMIT", 
                    quantity=actual_buy_qty, price=f"{ask_1_price:.2f}",
                    client_order_id=f"HABUY_{client_order_id_suffix}"
                )
                
                total_amount = ask_1_price * actual_buy_qty
                
                dynamic_target_lock = c2['EMA_10']
                await HAStateManager.save_state(price=ask_1_price, target_sell_price=dynamic_target_lock, is_trailing_active=False)
                last_action_candle_time = current_closed_time
                
                msg = (
                    f"🟢 <b>[HA 암살자] 프리마켓 스나이핑 매수 체결</b>\n\n"
                    f"▫️ <b>종목</b>: SOXL\n"
                    f"▫️ <b>체결 단가</b>: ${ask_1_price:.2f}\n"
                    f"▫️ <b>+1% 기상선</b>: ${ask_1_price * 1.01:.2f}\n"
                    f"▫️ <b>타격 수량</b>: {actual_buy_qty}주\n"
                    f"▫️ <b>총 결제 금액</b>: ${total_amount:,.2f}\n"
                    f"▫️ <b>잔여 체력 팩트</b>: 진폭 {current_amp*100:.2f}% (Limit: {avg_stamina*100:.2f}%)\n"
                    f"▫️ <b>시각</b>: {now_est_str}"
                )
                await notify_tg(msg)
                print(f"🎯 [HA 암살자] 프리마켓 진입 완료. +1% 도달 전까지 전면 관망(Hold) 스탠스 돌입.", flush=True)
                
            elif dynamic_sell_signal and soxl_qty >= 1:
                orderbook = await client.get_orderbook("SOXL")
                bids = orderbook.get("bids", [])
                
                if not bids:
                    continue
                    
                bid_1_price = float(bids[0]["price"])
                sell_qty = target_qty if soxl_qty >= target_qty else soxl_qty
                
                await client.create_order(
                    symbol="SOXL", side="SELL", order_type="LIMIT", 
                    quantity=sell_qty, price=f"{bid_1_price:.2f}",
                    client_order_id=f"HASELL_{client_order_id_suffix}"
                )
                
                sell_amount = bid_1_price * sell_qty
                buy_amount = last_buy_price * sell_qty
                commission_usd = sell_amount * 0.002
                
                is_profit = False
                if last_buy_price > 0:
                    profit_usd = (sell_amount - buy_amount) - commission_usd
                    profit_rate = (profit_usd / buy_amount) * 100
                    if profit_usd > 0:
                        is_profit = True
                else:
                    profit_usd = 0.0
                    profit_rate = 0.0
                    
                ex_rate = await client.get_usd_to_krw_rate()
                profit_krw = profit_usd * ex_rate
                
                msg = (
                    f"🔴 <b>[HA 암살자] EMA 10 추적 손절매 타격 완료</b>\n\n"
                    f"▫️ <b>종목</b>: SOXL\n"
                    f"▫️ <b>체결 단가</b>: ${bid_1_price:.2f}\n"
                    f"▫️ <b>붕괴 방어선</b>: ${target_sell_price:.2f}\n"
                    f"▫️ <b>타격 수량</b>: {sell_qty}주\n"
                    f"▫️ <b>총 매도 금액</b>: ${sell_amount:,.2f}\n"
                    f"▫️ <b>예상 제비용 (0.2%)</b>: -${commission_usd:,.2f}\n"
                    f"▫️ <b>순 수익률</b>: {profit_rate:+.2f}%\n"
                    f"▫️ <b>순 실현 손익</b>: {profit_usd:+.2f} USD ({profit_krw:+,.0f} KRW)\n"
                    f"▫️ <b>시각</b>: {now_est_str}"
                )
                await notify_tg(msg)
                
                await HAStateManager.save_state(price=0.0, target_sell_price=0.0, is_session_done=True, is_trailing_active=False)
                print(f"🎯 [HA 암살자] 1사이클 매매 완료 및 잔고 소각. 금일 완벽한 영업 종료(퇴근) 락온.", flush=True)
                    
                last_action_candle_time = current_closed_time
                
        except Exception as e:
            error_msg = str(e)
            print(f"🚨 [HA 암살자] 감시망 루프 붕괴: {error_msg}", flush=True)
            if "API 통신 붕괴" in error_msg:
                await notify_tg(f"🚨 <b>[HA 암살자] API 런타임 붕괴 요격</b>\n<pre>{html.escape(error_msg)}</pre>")

async def main():
    session = AiohttpSession(timeout=60.0)
    bot = Bot(token=TELEGRAM_BOT_TOKEN, session=session)
    dp = Dispatcher()
    
    api_client = TossApiClient(client_id=TOSS_CLIENT_ID, client_secret=TOSS_CLIENT_SECRET)
    
    inject_dependencies(api_client, ADMIN_CHAT_ID, wakeup_event)
    dp.include_router(router)
    
    asyncio.create_task(api_client.token_renewal_loop())
    asyncio.create_task(ha_assassin_loop(api_client, bot, ADMIN_CHAT_ID))
    
    print("시스템 코어 및 Track 방어망 결합 완료. 롱 폴링 개시...", flush=True)
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass
        
    while True:
        try:
            await dp.start_polling(bot)
        except Exception as e:
            print(f"🚨 [통신 붕괴 방어] 폴링 즉사. 5초 후 치유 재가동: {e}", flush=True)
            await asyncio.sleep(5)
        else:
            break

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
