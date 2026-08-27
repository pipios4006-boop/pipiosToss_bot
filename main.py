# =====================================================================
# 파일명: main.py
# 목적: 분리된 플러그인 모듈 의존성 주입 및 무한 폴링 데몬 격발
# =====================================================================

import asyncio
import os
import sys
import html
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
    print("🚨 치명적 에러: 필수 자격증명 환경변수(TOSS_CLIENT_ID, TOSS_CLIENT_SECRET, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)가 누락되었습니다.")
    print(f"💡 해결 조치: {env_path} 파일을 생성하거나 서버 환경변수에 값을 주입하십시오.")
    sys.exit(1)

ADMIN_CHAT_ID = int(_telegram_chat_id_str)

# NEW: HA 암살자 무한 폴링 루프 (본진 스케줄러)
async def ha_assassin_loop(client: TossApiClient, bot: Bot, chat_id: int):
    last_action_candle_time = None
    
    async def notify_tg(text: str):
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        except Exception as e:
            print(f"🚨 [텔레그램 전송 붕괴 방어] {e}")

    try:
        await client.fetch_account_seq()
    except Exception as e:
        print(f"🚨 [HA 암살자] 초기 계좌 정보 로드 실패: {e}")
        
    while True:
        await asyncio.sleep(60)
        
        try:
            last_buy_price, target_qty = await HAStateManager.get_state()
            
            now_kst = datetime.now(ZoneInfo('Asia/Seoul'))
            
            is_open, session_end_time = await client.is_market_open()
            if not is_open:
                continue
                
            soxl_qty = await client.get_soxl_holdings()
            
            if soxl_qty == 0 and last_buy_price > 0.0:
                await HAStateManager.save_state(price=0.0)
                last_buy_price = 0.0
                print(f"♻️ [HA 암살자] 수동 청산 팩트 교정: 실잔고 0주 감지. 오염된 장부 매수가를 0.0으로 강제 동기화 완료.")

            if session_end_time and (session_end_time - now_kst).total_seconds() <= 120:
                try:
                    open_orders = await client.get_orders(status="OPEN", symbol="SOXL")
                    if open_orders:
                        for order in open_orders:
                            await client.cancel_order(order["orderId"])
                            print(f"🛡️ [HA 암살자] Zero-Overnight 선제 요격: 미체결 주문({order['orderId']}) 취소 타격 완료.")
                except Exception as e:
                    print(f"⚠️ [HA 암살자] 미체결 주문 선제 취소망 통신 붕괴: {e}")

                if soxl_qty >= 1:
                    orderbook = await client.get_orderbook("SOXL")
                    bids = orderbook.get("bids", [])
                    if bids:
                        bid_1_price = float(bids[0]["price"])
                        now_est_str = datetime.now(ZoneInfo('America/New_York')).strftime("%Y-%m-%d %H:%M:%S EST")
                        await client.create_order(
                            symbol="SOXL", 
                            side="SELL", 
                            order_type="LIMIT", 
                            quantity=soxl_qty, 
                            price=bid_1_price, 
                            client_order_id=f"HAZERO_{datetime.now(ZoneInfo('America/New_York')).strftime('%Y%m%d_%H%M%S')}"
                        )
                        
                        profit_usd = (bid_1_price - last_buy_price) * soxl_qty if last_buy_price > 0 else 0.0
                        ex_rate = await client.get_usd_to_krw_rate()
                        profit_krw = profit_usd * ex_rate
                        profit_rate = ((bid_1_price - last_buy_price) / last_buy_price * 100) if last_buy_price > 0 else 0.0
                        
                        msg = (
                            f"⚠️ <b>[HA 암살자] Zero-Overnight 강제 청산 완료</b>\n\n"
                            f"▫️ <b>종목</b>: SOXL\n"
                            f"▫️ <b>체결 예상 단가</b>: ${bid_1_price:.2f}\n"
                            f"▫️ <b>타격 수량</b>: {soxl_qty}주\n"
                            f"▫️ <b>총 매도 금액</b>: ${bid_1_price * soxl_qty:,.2f}\n"
                            f"▫️ <b>수익률</b>: {profit_rate:+.2f}%\n"
                            f"▫️ <b>실현 손익</b>: {profit_usd:+.2f} USD ({profit_krw:+,.0f} KRW)\n"
                            f"▫️ <b>시각</b>: {now_est_str}"
                        )
                        await notify_tg(msg)
                        
                        await HAStateManager.save_state(price=0.0)
                        print(f"⚠️ [HA 암살자] 세션 마감 2분 전 컷오프. Zero-Overnight 방어막 가동 -> {soxl_qty}주 지정가(${bid_1_price:.2f}) 전량 매도 및 장부 초기화 완료.")
                    else:
                        print("⚠️ [HA 암살자] Zero-Overnight 덤핑 시도 중 호가창 붕괴(매수 잔량 없음) 요격. 지정가 덤핑 불가.")
                continue

            candles_json = await client.get_1m_candles("SOXL", count=200)
            ha_df = HeikinAshiEngine.calculate_3m_ha(candles_json)
            
            if len(ha_df) < 3:
                continue
                
            if session_end_time is None:
                latest_candle_time = ha_df.index[-1]
                now_est = datetime.now(ZoneInfo('America/New_York'))
                if (now_est - latest_candle_time).total_seconds() > 300:
                    print(f"🛡️ [HA 암살자] Fail-Open 섀도우 쉴드 락온: 캔들 갱신 5분 이상 지연 (물리적 휴장 진공 상태). 유령 타점 원천 소각.")
                    continue

            c1 = ha_df.iloc[-3]
            c2 = ha_df.iloc[-2]
            current_closed_time = c2.name
            
            if last_action_candle_time == current_closed_time:
                continue
                
            is_c1_yang = c1['HA_Close'] >= c1['HA_Open']
            is_c2_yang = c2['HA_Close'] >= c2['HA_Open']
            
            is_c1_eum = c1['HA_Close'] < c1['HA_Open']
            is_c2_eum = c2['HA_Close'] < c2['HA_Open']
            
            c2_body_size = abs(c2['HA_Close'] - c2['HA_Open']) / c2['HA_Open'] if c2['HA_Open'] > 0 else 0.0
            c2_shaved_bottom = ((c2['HA_Open'] - c2['HA_Low']) / c2['HA_Open'] < 0.0005) if c2['HA_Open'] > 0 else False
            
            buy_signal = (is_c2_yang and c2_shaved_bottom and c2_body_size >= 0.003) or (is_c1_yang and is_c2_yang and c2_shaved_bottom)
            sell_signal = (is_c2_eum and c2_body_size >= 0.003) or (is_c1_eum and is_c2_eum)

            if not (buy_signal or sell_signal):
                continue

            open_orders = await client.get_orders(status="OPEN", symbol="SOXL")
            if open_orders:
                print("⚠️ [HA 암살자] 미체결 대기 주문 감지. 이중 결제 방지를 위해 현재 루프 바이패스(Bypass)합니다.")
                continue
                
            current_price = await client.get_current_price("SOXL")
            if current_price <= 0.0:
                continue
            
            if soxl_qty >= 1 and last_buy_price <= 0.0:
                last_buy_price = current_price
                await HAStateManager.save_state(price=last_buy_price)
                print(f"♻️ [HA 암살자] 유령 잔고 팩트 교정: 장부 데이터 소실 감지. 현재가(${last_buy_price:.2f}) 앵커링 완료.")
                
            now_est_str = datetime.now(ZoneInfo('America/New_York')).strftime("%Y-%m-%d %H:%M:%S EST")
            client_order_id_suffix = datetime.now(ZoneInfo('America/New_York')).strftime("%Y%m%d_%H%M%S")
            
            if buy_signal and soxl_qty == 0:
                orderbook = await client.get_orderbook("SOXL")
                asks = orderbook.get("asks", [])
                
                if not asks:
                    print("⚠️ [HA 암살자] 호가창 붕괴(매도 잔량 없음). 타점 소각.")
                    continue
                    
                ask_1_price = float(asks[0]["price"])
                usd_bp = await client.get_usd_buying_power()
                
                required_bp = ask_1_price * target_qty * 1.03
                if usd_bp < required_bp:
                    print(f"⚠️ [HA 암살자] 자본 잠김 컷오프: 매수 가능 금액(${usd_bp:.2f})이 지정가 증거금 버퍼(${required_bp:.2f})보다 부족합니다. 타점 소각.")
                    continue
                    
                client_order_id = f"HABUY_{client_order_id_suffix}"
                
                await client.create_order(
                    symbol="SOXL", 
                    side="BUY", 
                    order_type="LIMIT", 
                    quantity=target_qty, 
                    price=ask_1_price,
                    client_order_id=client_order_id
                )
                
                total_amount = ask_1_price * target_qty
                msg = (
                    f"🟢 <b>[HA 암살자] 매수 타격 완료</b>\n\n"
                    f"▫️ <b>종목</b>: SOXL\n"
                    f"▫️ <b>체결 예상 단가</b>: ${ask_1_price:.2f}\n"
                    f"▫️ <b>타격 수량</b>: {target_qty}주\n"
                    f"▫️ <b>총 결제 금액</b>: ${total_amount:,.2f}\n"
                    f"▫️ <b>시각</b>: {now_est_str}"
                )
                await notify_tg(msg)
                
                await HAStateManager.save_state(price=ask_1_price)
                last_action_candle_time = current_closed_time
                print(f"🎯 [HA 암살자] 매수 타점 포착 (Track 1/2 통과) 및 자본 검증 통과. 합성 시장가(매도 1호가) {target_qty}주 매수 완료 (기록가: ${ask_1_price:.2f}).")
                
            elif sell_signal and soxl_qty >= 1:
                deviation = abs(current_price - last_buy_price) / last_buy_price if last_buy_price > 0 else 0.0
                
                if deviation >= 0.002:
                    orderbook = await client.get_orderbook("SOXL")
                    bids = orderbook.get("bids", [])
                    
                    if not bids:
                        print("⚠️ [HA 암살자] 호가창 붕괴(매수 잔량 없음). 타점 소각.")
                        continue
                        
                    bid_1_price = float(bids[0]["price"])
                    client_order_id = f"HASELL_{client_order_id_suffix}"
                    
                    sell_qty = target_qty if soxl_qty >= target_qty else soxl_qty
                    
                    await client.create_order(
                        symbol="SOXL", 
                        side="SELL", 
                        order_type="LIMIT", 
                        quantity=sell_qty, 
                        price=bid_1_price,
                        client_order_id=client_order_id
                    )
                    
                    profit_usd = (bid_1_price - last_buy_price) * sell_qty
                    ex_rate = await client.get_usd_to_krw_rate()
                    profit_krw = profit_usd * ex_rate
                    profit_rate = ((bid_1_price - last_buy_price) / last_buy_price * 100) if last_buy_price > 0 else 0.0
                    
                    msg = (
                        f"🔴 <b>[HA 암살자] 매도 타격 완료</b>\n\n"
                        f"▫️ <b>종목</b>: SOXL\n"
                        f"▫️ <b>체결 예상 단가</b>: ${bid_1_price:.2f}\n"
                        f"▫️ <b>타격 수량</b>: {sell_qty}주\n"
                        f"▫️ <b>총 매도 금액</b>: ${bid_1_price * sell_qty:,.2f}\n"
                        f"▫️ <b>수익률</b>: {profit_rate:+.2f}%\n"
                        f"▫️ <b>실현 손익</b>: {profit_usd:+.2f} USD ({profit_krw:+,.0f} KRW)\n"
                        f"▫️ <b>시각</b>: {now_est_str}"
                    )
                    await notify_tg(msg)
                    
                    await HAStateManager.save_state(price=0.0)
                    last_action_candle_time = current_closed_time
                    print(f"🎯 [HA 암살자] 매도 타점 포착 & 절대 이격도({deviation*100:.2f}%) 0.2% 돌파 팩트 확인. 합성 시장가(매수 1호가: ${bid_1_price:.2f}) {sell_qty}주 매도 완료.")
                else:
                    print(f"🛡️ [HA 암살자] 횡보장 휩쏘 방어 컷오프: 매도 시그널(Track 1/2) 발생했으나 절대 이격도({deviation*100:.2f}%)가 0.2%에 미달합니다. 타점 소각 후 관망 유지.")
                
        except Exception as e:
            error_msg = str(e)
            print(f"🚨 [HA 암살자] 감시망 루프 내부 붕괴: {error_msg}")
            if "API 통신 붕괴" in error_msg:
                safe_error = html.escape(error_msg)
                await notify_tg(f"🚨 <b>[HA 암살자] API 런타임 붕괴 요격</b>\n<pre>{safe_error}</pre>")

# 시스템 심장부 및 비동기 데몬 격발
async def main():
    session = AiohttpSession(timeout=60.0)
    bot = Bot(token=TELEGRAM_BOT_TOKEN, session=session)
    dp = Dispatcher()
    
    api_client = TossApiClient(client_id=TOSS_CLIENT_ID, client_secret=TOSS_CLIENT_SECRET)
    
    # MODIFIED: 분리된 텔레그램 라우터에 의존성 주입 후 연결
    inject_dependencies(api_client, ADMIN_CHAT_ID)
    dp.include_router(router)
    
    asyncio.create_task(api_client.token_renewal_loop())
    asyncio.create_task(ha_assassin_loop(api_client, bot, ADMIN_CHAT_ID))
    
    print("시스템 코어 로드 및 모듈 결합 완료. 텔레그램 롱 폴링(Long-Polling) 개시...")
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("관제탑 셧다운 완료.")
