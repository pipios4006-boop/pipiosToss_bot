# =====================================================================
# 파일명: main.py
# 목적: 분리된 플러그인 모듈 의존성 주입 및 V-REV 4.0 (EMA-20 Shield) 데몬
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
        await asyncio.sleep(60)
        
        try:
            last_buy_price, target_qty, target_sell_price = await HAStateManager.get_state()
            now_kst = datetime.now(ZoneInfo('Asia/Seoul'))
            
            is_open, session_end_time, session_name, session_start_time = await client.is_market_open()
            if not is_open:
                continue
                
            raw_soxl_qty = await client.get_soxl_holdings()
            soxl_qty = int(math.floor(float(raw_soxl_qty)))
            
            if soxl_qty == 0 and last_buy_price > 0.0:
                await HAStateManager.save_state(price=0.0, target_sell_price=0.0)
                last_buy_price = 0.0
                target_sell_price = 0.0
                print(f"♻️ [HA 암살자] 수동 청산 팩트 교정: 오염된 장부가 0.0 강제 동기화.", flush=True)

            if session_end_time and (session_end_time - now_kst).total_seconds() <= 120:
                try:
                    open_orders = await client.get_orders(status="OPEN", symbol="SOXL")
                    if open_orders:
                        for order in open_orders:
                            await client.cancel_order(order["orderId"])
                except Exception as e:
                    print(f"⚠️ [HA 암살자] 취소망 통신 붕괴: {e}", flush=True)

                if soxl_qty >= 1:
                    orderbook = await client.get_orderbook("SOXL")
                    bids = orderbook.get("bids", [])
                    if bids:
                        bid_1_price = float(bids[0]["price"])
                        now_est_str = datetime.now(ZoneInfo('America/New_York')).strftime("%Y-%m-%d %H:%M:%S EST")
                        await client.create_order(
                            symbol="SOXL", side="SELL", order_type="LIMIT", 
                            quantity=soxl_qty, price=bid_1_price, 
                            client_order_id=f"HAZERO_{datetime.now(ZoneInfo('America/New_York')).strftime('%Y%m%d_%H%M%S')}"
                        )
                        
                        sell_amount = bid_1_price * soxl_qty
                        buy_amount = last_buy_price * soxl_qty
                        commission_usd = sell_amount * 0.002
                        
                        if last_buy_price > 0:
                            profit_usd = (sell_amount - buy_amount) - commission_usd
                            profit_rate = (profit_usd / buy_amount) * 100
                        else:
                            profit_usd = 0.0
                            profit_rate = 0.0
                            
                        ex_rate = await client.get_usd_to_krw_rate()
                        profit_krw = profit_usd * ex_rate
                        
                        msg = (
                            f"⚠️ <b>[HA 암살자] Zero-Overnight 마감 강제 청산</b>\n\n"
                            f"▫️ <b>종목</b>: SOXL\n"
                            f"▫️ <b>체결 예상 단가</b>: ${bid_1_price:.2f}\n"
                            f"▫️ <b>타격 수량</b>: {soxl_qty}주\n"
                            f"▫️ <b>총 매도 금액</b>: ${sell_amount:,.2f}\n"
                            f"▫️ <b>예상 제비용 (0.2%)</b>: -${commission_usd:,.2f}\n"
                            f"▫️ <b>순 수익률</b>: {profit_rate:+.2f}%\n"
                            f"▫️ <b>순 실현 손익</b>: {profit_usd:+.2f} USD ({profit_krw:+,.0f} KRW)\n"
                            f"▫️ <b>시각</b>: {now_est_str}"
                        )
                        await notify_tg(msg)
                        await HAStateManager.save_state(price=0.0, target_sell_price=0.0)
                    else:
                        print("⚠️ [HA 암살자] Zero-Overnight 덤핑 호가창 붕괴.", flush=True)
                continue

            candles_task = client.get_1m_candles("SOXL", count=200)
            daily_candles_task = client.get_daily_candles("SOXL", count=6)
            candles_json, daily_candles_json = await asyncio.gather(candles_task, daily_candles_task)
            
            ha_df = HeikinAshiEngine.calculate_3m_ha(candles_json)
            avg_stamina = HeikinAshiEngine.calculate_amplitude_stamina(daily_candles_json)
            
            if len(ha_df) < 3:
                continue
                
            if session_end_time is None:
                if (datetime.now(ZoneInfo('America/New_York')) - ha_df.index[-1]).total_seconds() > 300:
                    continue

            current_amp = 0.0
            session_open_price = 0.0
            if session_start_time is not None and not ha_df.empty:
                session_start_est = session_start_time.astimezone(ZoneInfo('America/New_York'))
                session_candles = ha_df[ha_df.index >= session_start_est]
                
                if not session_candles.empty:
                    s_high = session_candles['HA_High'].max()
                    s_low = session_candles['HA_Low'].min()
                    if s_low > 0:
                        current_amp = (s_high - s_low) / s_low
                    session_open_price = session_candles.iloc[0]['HA_Open']

            c1 = ha_df.iloc[-3]
            c2 = ha_df.iloc[-2]
            c0 = ha_df.iloc[-1]
            current_closed_time = c2.name
            
            is_c1_yang = c1['HA_Close'] >= c1['HA_Open']
            is_c2_yang = c2['HA_Close'] >= c2['HA_Open']
            is_c0_eum = c0['HA_Close'] < c0['HA_Open']
            is_up_trend = c2['EMA_10'] > c2['EMA_20']
            
            gap_shield_block = False
            if session_start_time:
                elapsed_sec = (now_kst - session_start_time).total_seconds()
                if elapsed_sec <= 3600:
                    if is_c0_eum or (c0['HA_Close'] < session_open_price):
                        gap_shield_block = True

            stamina_exhausted = (avg_stamina > 0.0) and (current_amp >= avg_stamina * 0.95)
            
            # MODIFIED: V-REV 4.0 - EMA 20 절대 방어선 락온 (매 캔들마다 갱신)
            if soxl_qty >= 1:
                dynamic_target = c2['EMA_20']
                if abs(target_sell_price - dynamic_target) > 0.001:
                    target_sell_price = dynamic_target
                    await HAStateManager.save_state(target_sell_price=target_sell_price)
                    print(f"🎯 [HA 암살자] EMA 20 거시 방어선 갱신: (${target_sell_price:.2f}) 락온 완료.", flush=True)

            buy_signal = False
            dynamic_sell_signal = False
            
            if last_action_candle_time != current_closed_time:
                # MODIFIED: V-REV 4.0 - Track 1 소각. 오직 2연속 양봉(Track 2)만 매수 허용
                raw_buy_signal = (is_c1_yang and is_c2_yang) and is_up_trend
                
                if raw_buy_signal:
                    if gap_shield_block:
                        print(f"🛡️ [HA 암살자] Track B&C 쉴드 가동: {session_name} 개장 직후 갭 하락 또는 0봉 음봉 감지. 유령 타점 원천 소각.", flush=True)
                    elif stamina_exhausted:
                        print(f"🛡️ [HA 암살자] Track A 방어막 가동: 현재 세션 진폭({current_amp*100:.2f}%)이 5일 평균 체력({avg_stamina*100:.2f}%)의 95% 초과 도달. 타점 소각.", flush=True)
                    else:
                        buy_signal = True

                # MODIFIED: V-REV 4.0 - 닫힌 캔들(c2)이 EMA 20을 하방 이탈할 때만 매도 (휩쏘 노이즈 100% 무시)
                if soxl_qty >= 1 and target_sell_price > 0.0:
                    if c2['HA_Close'] < target_sell_price:
                        dynamic_sell_signal = True
            
            need_current_price = buy_signal or dynamic_sell_signal or (soxl_qty >= 1 and last_buy_price <= 0.0)
            if not need_current_price:
                continue
                
            current_price = await client.get_current_price("SOXL")
            if current_price <= 0.0:
                continue
            
            if soxl_qty >= 1 and last_buy_price <= 0.0:
                last_buy_price = current_price
                await HAStateManager.save_state(price=last_buy_price)
                print(f"♻️ [HA 암살자] 유령 잔고 자가 치유: 현재가(${last_buy_price:.2f}) 앵커링 완료.", flush=True)
            
            if not (buy_signal or dynamic_sell_signal):
                continue

            open_orders = await client.get_orders(status="OPEN", symbol="SOXL")
            if open_orders:
                print("⚠️ [HA 암살자] 미체결 대기 주문 감지. 현재 루프 바이패스.", flush=True)
                continue
                
            now_est_str = datetime.now(ZoneInfo('America/New_York')).strftime("%Y-%m-%d %H:%M:%S EST")
            client_order_id_suffix = datetime.now(ZoneInfo('America/New_York')).strftime("%Y%m%d_%H%M%S")
            
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
                    quantity=actual_buy_qty, price=ask_1_price,
                    client_order_id=f"HABUY_{client_order_id_suffix}"
                )
                
                total_amount = ask_1_price * actual_buy_qty
                
                msg = (
                    f"🟢 <b>[HA 암살자] 매수 타격 완료 (상승장 돌파)</b>\n\n"
                    f"▫️ <b>종목</b>: SOXL\n"
                    f"▫️ <b>체결 단가</b>: ${ask_1_price:.2f}\n"
                    f"▫️ <b>타격 수량</b>: {actual_buy_qty}주\n"
                    f"▫️ <b>총 결제 금액</b>: ${total_amount:,.2f}\n"
                    f"▫️ <b>잔여 체력 팩트</b>: 진폭 {current_amp*100:.2f}% (Limit: {avg_stamina*100:.2f}%)\n"
                    f"▫️ <b>시각</b>: {now_est_str}"
                )
                await notify_tg(msg)
                
                await HAStateManager.save_state(price=ask_1_price)
                last_action_candle_time = current_closed_time
                print(f"🎯 [HA 암살자] 진성 시그널 및 방어막 검증 통과. 매도 1호가(${ask_1_price:.2f}) 매수 타격 완료.", flush=True)
                
            elif dynamic_sell_signal and soxl_qty >= 1:
                orderbook = await client.get_orderbook("SOXL")
                bids = orderbook.get("bids", [])
                
                if not bids:
                    continue
                    
                bid_1_price = float(bids[0]["price"])
                sell_qty = target_qty if soxl_qty >= target_qty else soxl_qty
                
                await client.create_order(
                    symbol="SOXL", side="SELL", order_type="LIMIT", 
                    quantity=sell_qty, price=bid_1_price,
                    client_order_id=f"HASELL_{client_order_id_suffix}"
                )
                
                sell_amount = bid_1_price * sell_qty
                buy_amount = last_buy_price * sell_qty
                commission_usd = sell_amount * 0.002
                
                if last_buy_price > 0:
                    profit_usd = (sell_amount - buy_amount) - commission_usd
                    profit_rate = (profit_usd / buy_amount) * 100
                else:
                    profit_usd = 0.0
                    profit_rate = 0.0
                    
                ex_rate = await client.get_usd_to_krw_rate()
                profit_krw = profit_usd * ex_rate
                
                msg = (
                    f"🔴 <b>[HA 암살자] 매도 타격 완료 (거시 추세 이탈)</b>\n\n"
                    f"▫️ <b>종목</b>: SOXL\n"
                    f"▫️ <b>체결 단가</b>: ${bid_1_price:.2f}\n"
                    f"▫️ <b>EMA 20 붕괴가</b>: ${target_sell_price:.2f}\n"
                    f"▫️ <b>타격 수량</b>: {sell_qty}주\n"
                    f"▫️ <b>총 매도 금액</b>: ${sell_amount:,.2f}\n"
                    f"▫️ <b>예상 제비용 (0.2%)</b>: -${commission_usd:,.2f}\n"
                    f"▫️ <b>순 수익률</b>: {profit_rate:+.2f}%\n"
                    f"▫️ <b>순 실현 손익</b>: {profit_usd:+.2f} USD ({profit_krw:+,.0f} KRW)\n"
                    f"▫️ <b>시각</b>: {now_est_str}"
                )
                await notify_tg(msg)
                
                await HAStateManager.save_state(price=0.0, target_sell_price=0.0)
                last_action_candle_time = current_closed_time
                print(f"🎯 [HA 암살자] EMA 20 거시 방어선 붕괴 격발 완료. 하방 돌파 요격.", flush=True)
                
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
    inject_dependencies(api_client, ADMIN_CHAT_ID)
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
