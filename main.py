# =====================================================================
# 파일명: main.py
# 목적: 분리된 플러그인 모듈 의존성 주입 및 상승장 필터(Up-Trend) 전용 무한 폴링 데몬 격발
# =====================================================================

import asyncio
import os
import sys
import html
import math  # NEW: 부동소수점 내림(Floor) 연산 캡핑용
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
    print("🚨 치명적 에러: 필수 자격증명 환경변수(TOSS_CLIENT_ID, TOSS_CLIENT_SECRET, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)가 누락되었습니다.", flush=True)
    print(f"💡 해결 조치: {env_path} 파일을 생성하거나 서버 환경변수에 값을 주입하십시오.", flush=True)
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
            
            is_open, session_end_time = await client.is_market_open()
            if not is_open:
                continue
                
            # MODIFIED: Case 60 하드 캡핑 - 부동소수점 더스트(0.01주 등) 원천 소각 및 정수형 0주 락온
            raw_soxl_qty = await client.get_soxl_holdings()
            soxl_qty = int(math.floor(float(raw_soxl_qty)))
            
            if soxl_qty == 0 and last_buy_price > 0.0:
                await HAStateManager.save_state(price=0.0, target_sell_price=0.0)
                last_buy_price = 0.0
                target_sell_price = 0.0
                print(f"♻️ [HA 암살자] 수동 청산 팩트 교정: 실잔고 0주 감지. 오염된 장부 매수가를 0.0으로 강제 동기화 완료.", flush=True)

            if session_end_time and (session_end_time - now_kst).total_seconds() <= 120:
                try:
                    open_orders = await client.get_orders(status="OPEN", symbol="SOXL")
                    if open_orders:
                        for order in open_orders:
                            await client.cancel_order(order["orderId"])
                            print(f"🛡️ [HA 암살자] Zero-Overnight 선제 요격: 미체결 주문({order['orderId']}) 취소 타격 완료.", flush=True)
                except Exception as e:
                    print(f"⚠️ [HA 암살자] 미체결 주문 선제 취소망 통신 붕괴: {e}", flush=True)

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
                            f"⚠️ <b>[HA 암살자] Zero-Overnight 강제 청산 완료</b>\n\n"
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
                        print(f"⚠️ [HA 암살자] 세션 마감 2분 전 컷오프. Zero-Overnight 방어막 가동 -> {soxl_qty}주 지정가(${bid_1_price:.2f}) 전량 매도 및 장부 초기화 완료.", flush=True)
                    else:
                        print("⚠️ [HA 암살자] Zero-Overnight 덤핑 시도 중 호가창 붕괴(매수 잔량 없음) 요격. 지정가 덤핑 불가.", flush=True)
                continue

            candles_json = await client.get_1m_candles("SOXL", count=200)
            ha_df = HeikinAshiEngine.calculate_3m_ha(candles_json)
            
            if len(ha_df) < 3:
                continue
                
            if session_end_time is None:
                latest_candle_time = ha_df.index[-1]
                now_est = datetime.now(ZoneInfo('America/New_York'))
                if (now_est - latest_candle_time).total_seconds() > 300:
                    print(f"🛡️ [HA 암살자] Fail-Open 섀도우 쉴드 락온: 캔들 갱신 5분 이상 지연 (물리적 휴장 진공 상태). 유령 타점 원천 소각.", flush=True)
                    continue

            c1 = ha_df.iloc[-3]
            c2 = ha_df.iloc[-2]
            c0 = ha_df.iloc[-1]
            current_closed_time = c2.name
            
            is_c1_yang = c1['HA_Close'] >= c1['HA_Open']
            is_c2_yang = c2['HA_Close'] >= c2['HA_Open']
            
            c2_body_size = abs(c2['HA_Close'] - c2['HA_Open']) / c2['HA_Open'] if c2['HA_Open'] > 0 else 0.0
            c2_shaved_bottom = ((c2['HA_Open'] - c2['HA_Low']) / c2['HA_Open'] < 0.0005) if c2['HA_Open'] > 0 else False
            
            is_up_trend = c2['EMA_10'] > c2['EMA_20']
            
            buy_signal = False
            if last_action_candle_time != current_closed_time:
                buy_signal = ((is_c2_yang and c2_shaved_bottom) or (is_c1_yang and is_c2_yang)) and is_up_trend

            if soxl_qty >= 1:
                closed_ha = ha_df.iloc[:-1]
                bulls = closed_ha[closed_ha['HA_Close'] >= closed_ha['HA_Open']]
                if not bulls.empty:
                    latest_bull = bulls.iloc[-1]
                    dynamic_target = (latest_bull['HA_Open'] + latest_bull['HA_Close']) / 2.0
                    if abs(target_sell_price - dynamic_target) > 0.001:
                        target_sell_price = dynamic_target
                        await HAStateManager.save_state(target_sell_price=target_sell_price)
                        print(f"🎯 [HA 암살자] Trailing Stop 갱신: 직전 양봉 평균값(${target_sell_price:.2f}) 락온 완료.", flush=True)
            
            is_c0_eum = c0['HA_Close'] < c0['HA_Open']
            
            need_current_price = buy_signal or (soxl_qty >= 1 and is_c0_eum and target_sell_price > 0.0)
            
            if not need_current_price:
                continue
                
            current_price = await client.get_current_price("SOXL")
            if current_price <= 0.0:
                continue
            
            if soxl_qty >= 1 and last_buy_price <= 0.0:
                last_buy_price = current_price
                await HAStateManager.save_state(price=last_buy_price)
                print(f"♻️ [HA 암살자] 유령 잔고 팩트 교정: 장부 데이터 소실 감지. 현재가(${last_buy_price:.2f}) 앵커링 완료.", flush=True)
            
            dynamic_sell_signal = False
            if soxl_qty >= 1 and is_c0_eum and target_sell_price > 0.0:
                if current_price <= target_sell_price:
                    dynamic_sell_signal = True

            if not (buy_signal or dynamic_sell_signal):
                continue

            open_orders = await client.get_orders(status="OPEN", symbol="SOXL")
            if open_orders:
                print("⚠️ [HA 암살자] 미체결 대기 주문 감지. 이중 결제 방지를 위해 현재 루프 바이패스(Bypass)합니다.", flush=True)
                continue
                
            now_est_str = datetime.now(ZoneInfo('America/New_York')).strftime("%Y-%m-%d %H:%M:%S EST")
            client_order_id_suffix = datetime.now(ZoneInfo('America/New_York')).strftime("%Y%m%d_%H%M%S")
            
            if buy_signal and soxl_qty == 0:
                orderbook = await client.get_orderbook("SOXL")
                asks = orderbook.get("asks", [])
                
                if not asks:
                    print("⚠️ [HA 암살자] 호가창 붕괴(매도 잔량 없음). 타점 소각.", flush=True)
                    continue
                    
                ask_1_price = float(asks[0]["price"])
                usd_bp = await client.get_usd_buying_power()
                
                actual_buy_qty = target_qty
                
                required_bp = ask_1_price * actual_buy_qty * 1.03
                if usd_bp < required_bp:
                    print(f"⚠️ [HA 암살자] 자본 잠김 컷오프: 매수 가능 금액(${usd_bp:.2f})이 지정가 증거금 버퍼(${required_bp:.2f})보다 부족합니다. 타점 소각.", flush=True)
                    continue
                    
                client_order_id = f"HABUY_{client_order_id_suffix}"
                
                await client.create_order(
                    symbol="SOXL", 
                    side="BUY", 
                    order_type="LIMIT", 
                    quantity=actual_buy_qty, 
                    price=ask_1_price,
                    client_order_id=client_order_id
                )
                
                total_amount = ask_1_price * actual_buy_qty
                
                msg = (
                    f"🟢 <b>[HA 암살자] 매수 타격 완료 (상승장 돌파)</b>\n\n"
                    f"▫️ <b>종목</b>: SOXL\n"
                    f"▫️ <b>체결 예상 단가</b>: ${ask_1_price:.2f}\n"
                    f"▫️ <b>타격 수량</b>: {actual_buy_qty}주\n"
                    f"▫️ <b>총 결제 금액</b>: ${total_amount:,.2f}\n"
                    f"▫️ <b>시각</b>: {now_est_str}"
                )
                await notify_tg(msg)
                
                await HAStateManager.save_state(price=ask_1_price)
                last_action_candle_time = current_closed_time
                print(f"🎯 [HA 암살자] 거시적 상승장(Up-Trend) 및 캔들 시그널 교차 검증 통과. 합성 시장가(매도 1호가) {actual_buy_qty}주 전량 매수 완료 (기록가: ${ask_1_price:.2f}).", flush=True)
                
            elif dynamic_sell_signal and soxl_qty >= 1:
                orderbook = await client.get_orderbook("SOXL")
                bids = orderbook.get("bids", [])
                
                if not bids:
                    print("⚠️ [HA 암살자] 호가창 붕괴(매수 잔량 없음). 타점 소각.", flush=True)
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
                    f"🔴 <b>[HA 암살자] 매도 타격 완료 (동적 스나이핑)</b>\n\n"
                    f"▫️ <b>종목</b>: SOXL\n"
                    f"▫️ <b>체결 예상 단가</b>: ${bid_1_price:.2f}\n"
                    f"▫️ <b>스나이핑 락온가</b>: ${target_sell_price:.2f}\n"
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
                print(f"🎯 [HA 암살자] 동적 스나이핑 격발: 진행중 음봉 포착 & 지정 락온가(${target_sell_price:.2f}) 하방 돌파. 합성 시장가(매수 1호가: ${bid_1_price:.2f}) {sell_qty}주 매도 완료.", flush=True)
                
        except Exception as e:
            error_msg = str(e)
            print(f"🚨 [HA 암살자] 감시망 루프 내부 붕괴: {error_msg}", flush=True)
            if "API 통신 붕괴" in error_msg:
                safe_error = html.escape(error_msg)
                await notify_tg(f"🚨 <b>[HA 암살자] API 런타임 붕괴 요격</b>\n<pre>{safe_error}</pre>")

async def main():
    session = AiohttpSession(timeout=60.0)
    bot = Bot(token=TELEGRAM_BOT_TOKEN, session=session)
    dp = Dispatcher()
    
    api_client = TossApiClient(client_id=TOSS_CLIENT_ID, client_secret=TOSS_CLIENT_SECRET)
    
    inject_dependencies(api_client, ADMIN_CHAT_ID)
    dp.include_router(router)
    
    asyncio.create_task(api_client.token_renewal_loop())
    asyncio.create_task(ha_assassin_loop(api_client, bot, ADMIN_CHAT_ID))
    
    print("시스템 코어 로드 및 모듈 결합 완료. 텔레그램 롱 폴링(Long-Polling) 개시...", flush=True)
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        print(f"⚠️ [텔레그램 통신 붕괴 방어] 웹훅 해제 실패 (무시 후 강행): {e}", flush=True)
        
    while True:
        try:
            await dp.start_polling(bot)
        except Exception as e:
            print(f"🚨 [텔레그램 통신 붕괴 방어] 롱 폴링 루프 즉사 감지. 5초 후 내부 자가 치유(Self-Healing) 재가동: {e}", flush=True)
            await asyncio.sleep(5)
        else:
            print("🛑 관제탑 롱 폴링 정상 셧다운 완료.", flush=True)
            break

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("관제탑 프로세스 완전 종료.", flush=True)
