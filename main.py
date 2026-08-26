# =====================================================================
# 파일명: main.py
# 최근 업데이트:
# 1. SOXL 실시간 현재가(GET /prices) 조회 모듈 결속 (MARKET_DATA 통제)
# 2. 토스 1분봉(GET /candles) 기반 3분봉 하이킨 아시(Heikin-Ashi) 벡터화 엔진 결속
# 3. 텔레그램 /start 메인 메뉴 인라인 키보드 HA 스캔 라우터 추가
# 4. 12시간 주기 토큰 자동 갱신 스케줄러 및 401 요격 자가 치유 엔진 결속
# 5. HA 스캔 UI 리빌딩: 최대 10개 캔들 평균체결가 단일 렌더링 락온
# 6. 주문 생성 및 조회 API 래퍼 모듈 결속 (멱등성, 정수형 락온)
# 7. HA 암살자(aVWAP) 3분봉 네이티브 MARKET 주문 무한 루프 데몬 가동
# 8. 시장 운영 달력(US) 인메모리 캐싱 및 비운영 시간 선제 스킵 락온
# 9. 시장가 증거금(3% 버퍼) 부족 시 422 밴 방어용 자본 잠김 컷오프 결속
# 10. 상태 장부(ha_state.json) 원자적 읽기/쓰기 코어(HAStateManager) 결속
# 11. 세션 마감 2분 전 Zero-Overnight 강제 청산 방어막 결속
# 12. 횡보장 휩쏘 방어용 절대 이격도(0.2%) 검증 알고리즘 및 유령 잔고 자가 치유 결속
# 13. 텔레그램 Errno 104 통신 붕괴 방어용 AiohttpSession 주입
# 14. 토스 API 물리적 단절 시 3단 지수 백오프(Exponential Backoff) 무중단 Fallback 결속
# 15. [NEW] HA 예열(Warm-up) 데이터 결핍에 따른 색상 왜곡 방어용 수집량(count=200) 전격 상향 락온
# =====================================================================

import asyncio
import aiohttp
import os
import html
import sys
import math
import json
import contextlib
import pandas as pd
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.session.aiohttp import AiohttpSession

# 자격증명 및 시스템 상수 락온
TOSS_CLIENT_ID = os.getenv("TOSS_CLIENT_ID", "tsck_live_QogVVVdZPhhg3sbTo5T7hB")
TOSS_CLIENT_SECRET = os.getenv("TOSS_CLIENT_SECRET", "tssk_live_vvWo029zWfkoNLKscu8QbEoM7enrcOeNpCg98sHTeVYD")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7850532415:AAGiZg_gbUDXjBA7QOnvTbSPXii5WwFQ7wQ")
ADMIN_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "796232854"))

# 제1헌법 - 동기 I/O 비동기 격리 및 Rate Limit 중앙 통제소
class GlobalThrottle:
    _locks = {}
    _file_locks = {}
    
    @classmethod
    async def wait_api_sync(cls, group_name: str):
        if group_name not in cls._locks:
            cls._locks[group_name] = asyncio.Lock()
        async with cls._locks[group_name]:
            await asyncio.sleep(1.5)

    @classmethod
    @contextlib.asynccontextmanager
    async def get_file_lock(cls, filepath: str):
        if filepath not in cls._file_locks:
            cls._file_locks[filepath] = asyncio.Lock()
        async with cls._file_locks[filepath]:
            yield

# 상태 장부 영구 보존 및 원자적 쓰기 엔진
class HAStateManager:
    FILE_PATH = "ha_state.json"

    @classmethod
    async def get_state(cls) -> float:
        async with GlobalThrottle.get_file_lock(cls.FILE_PATH):
            def _read():
                if not os.path.exists(cls.FILE_PATH):
                    return 0.0
                try:
                    with open(cls.FILE_PATH, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        return float(data.get("last_buy_price", 0.0))
                except Exception:
                    return 0.0
            return await asyncio.to_thread(_read)

    @classmethod
    async def save_state(cls, price: float):
        async with GlobalThrottle.get_file_lock(cls.FILE_PATH):
            def _write():
                tmp_path = cls.FILE_PATH + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump({"last_buy_price": price}, f)
                # 원자적 덮어쓰기로 더티 리드 원천 차단 (제4헌법)
                os.replace(tmp_path, cls.FILE_PATH)
            await asyncio.to_thread(_write)

# 비동기 토스증권 API 클라이언트
class TossApiClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://openapi.tossinvest.com"
        self.token = None
        self.account_seq = None
        
        # 토큰 갱신 전역 락 및 타임스탬프 락온 (Thundering Herd 방어용)
        self._auth_lock = None
        self._last_auth_time = 0.0
        
        # 달력 API 인메모리 캐싱 파이프라인 (Case 51)
        self._calendar_cache = {}
        self._calendar_lock = None

    async def _request(self, method: str, endpoint: str, group_name: str, **kwargs) -> dict:
        url = f"{self.base_url}{endpoint}"
        max_retries = 3
        # 글로벌 타임아웃 10초 강제 락온 (네트워크 데드락 원천 방어)
        timeout = aiohttp.ClientTimeout(total=10.0)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for attempt in range(max_retries):
                await GlobalThrottle.wait_api_sync(group_name)
                
                # 401 요격 후 재시도 시 최신 갱신된 토큰 동적 주입 방어망
                if "headers" in kwargs and "Authorization" in kwargs["headers"]:
                    kwargs["headers"]["Authorization"] = f"Bearer {self.token}"
                
                try:
                    # 물리적 네트워크 단절 및 타임아웃 방어용 try-except 래핑 (Case 32)
                    async with session.request(method, url, **kwargs) as response:
                        if response.status == 200:
                            return await response.json()
                        elif response.status == 401 and group_name != "AUTH":
                            # 401 붕괴 요격 및 토큰 자가 치유 엔진 격발
                            print("⚠️ 401 Unauthorized 타격. 토큰 자가 치유 엔진 격발...")
                            await self.authenticate(force=True)
                            continue
                        elif response.status == 429:
                            retry_after = int(response.headers.get("Retry-After", 3))
                            print(f"⚠️ 429 Rate Limit 타격. {retry_after}초 지수 백오프 대기...")
                            await asyncio.sleep(retry_after)
                            continue
                        else:
                            error_text = await response.text()
                            raise ConnectionError(f"API 통신 붕괴 ({response.status}): {error_text}")
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    # 3단 지수 백오프(Exponential Backoff) 무중단 Fallback 강제 (Case 32)
                    if attempt < max_retries - 1:
                        backoff_time = 2 ** attempt  # 1초, 2초
                        print(f"⚠️ API 통신 예외 요격 ({e}). {backoff_time}초 지수 백오프 후 재시도...")
                        await asyncio.sleep(backoff_time)
                        continue
                    raise TimeoutError(f"최대 재시도 횟수 초과 즉사: {e}")

    # 토큰 갱신 전역 락온 및 병목 컷오프 모듈 결속
    async def authenticate(self, force: bool = False) -> None:
        if self._auth_lock is None:
            self._auth_lock = asyncio.Lock()
            
        async with self._auth_lock:
            current_time = asyncio.get_event_loop().time()
            
            if force and (current_time - self._last_auth_time < 10.0):
                return
            if not force and self.token:
                return

            payload = {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret
            }
            data = await self._request("POST", "/oauth2/token", "AUTH", data=payload)
            self.token = data.get("access_token")
            self._last_auth_time = current_time
            print("♻️ 토스증권 API 액세스 토큰 100% 갱신 락온 완료.")

    # 12시간 주기 선제 타격 스케줄러 엔진
    async def token_renewal_loop(self):
        while True:
            await asyncio.sleep(43200) # 12시간 대기
            try:
                print("⏳ 12시간 주기 토큰 선제 타격 엔진 가동...")
                await self.authenticate(force=True)
            except Exception as e:
                print(f"🚨 토큰 선제 타격 실패 (Fail-Safe 요격망 대기): {e}")

    def _get_headers(self, requires_account: bool = False) -> dict:
        headers = {"Authorization": f"Bearer {self.token}"}
        if requires_account:
            if not self.account_seq:
                raise ValueError("accountSeq가 누락되었습니다.")
            headers["X-Tossinvest-Account"] = str(self.account_seq)
        return headers

    async def fetch_account_seq(self) -> None:
        if not self.token:
            await self.authenticate()
            
        data = await self._request("GET", "/api/v1/accounts", "ACCOUNT", headers=self._get_headers())
        accounts = data.get("result", [])
        
        if not accounts:
            raise IndexError("조회 가능한 계좌가 없습니다.")
        
        brokerage_account = next((acc for acc in accounts if acc.get("accountType") == "BROKERAGE"), None)
        if brokerage_account:
            self.account_seq = brokerage_account.get("accountSeq")
        else:
            raise ValueError("종합매매 계좌를 찾을 수 없습니다.")

    # 토스 시장 운영 달력 인메모리 캐싱 및 종료 시간 동시 반환
    async def is_market_open(self) -> tuple[bool, datetime]:
        if not self.token:
            await self.authenticate()
            
        if self._calendar_lock is None:
            self._calendar_lock = asyncio.Lock()
            
        async with self._calendar_lock:
            now_kst = datetime.now(ZoneInfo('Asia/Seoul'))
            date_str = now_kst.strftime("%Y-%m-%d")
            
            if self._calendar_cache.get("date") != date_str:
                try:
                    endpoint = f"/api/v1/market-calendar/US?date={date_str}"
                    data = await self._request("GET", endpoint, "MARKET_INFO", headers=self._get_headers())
                    today_cal = data.get("result", {}).get("today", {})
                    
                    sessions = []
                    for session_name in ["dayMarket", "preMarket", "regularMarket", "afterMarket"]:
                        session_data = today_cal.get(session_name)
                        if session_data:
                            start_dt = datetime.fromisoformat(session_data["startTime"])
                            end_dt = datetime.fromisoformat(session_data["endTime"])
                            sessions.append((start_dt, end_dt))
                    
                    self._calendar_cache = {"date": date_str, "sessions": sessions}
                    print(f"📅 토스증권 US 시장 달력 캐싱 완료: {date_str} (총 {len(sessions)}개 세션 확보)")
                except Exception as e:
                    print(f"⚠️ [달력 API] 통신 지연 또는 파싱 오류. Fail-Open 가동 (무조건 주문 허용): {e}")
                    return True, None # 엣지 타임라인 Fail-Safe 구조화
                    
            cached_sessions = self._calendar_cache.get("sessions", [])
            
            if not cached_sessions:
                return False, None
                
            # 현재 시각이 어떠한 세션 내에 존재하면 (True, 해당 세션 종료시각) 반환
            for start_dt, end_dt in cached_sessions:
                if start_dt <= now_kst <= end_dt:
                    return True, end_dt
                    
            return False, None

    async def get_usd_buying_power(self) -> float:
        if not self.account_seq:
            await self.fetch_account_seq()
            
        data = await self._request("GET", "/api/v1/buying-power?currency=USD", "ORDER_INFO", headers=self._get_headers(requires_account=True))
        result = data.get("result", {})
        
        raw_bp = result.get("cashBuyingPower")
        return float(raw_bp) if raw_bp is not None else 0.0

    async def get_soxl_holdings(self) -> int:
        if not self.account_seq:
            await self.fetch_account_seq()
            
        data = await self._request("GET", "/api/v1/holdings?symbol=SOXL", "ASSET", headers=self._get_headers(requires_account=True))
        result = data.get("result", {})
        
        items = result.get("items", [])
        if not items:
            return 0
            
        soxl_item = next((item for item in items if item.get("symbol") == "SOXL"), None)
        if not soxl_item:
            return 0
            
        raw_qty = soxl_item.get("quantity")
        return int(float(raw_qty)) if raw_qty is not None else 0

    async def get_current_price(self, symbol: str) -> float:
        if not self.token:
            await self.authenticate()
            
        endpoint = f"/api/v1/prices?symbols={symbol}"
        data = await self._request("GET", endpoint, "MARKET_DATA", headers=self._get_headers())
        
        results = data.get("result", [])
        if not results:
            return 0.0
            
        raw_price = results[0].get("lastPrice")
        return float(raw_price) if raw_price is not None else 0.0

    async def get_1m_candles(self, symbol: str, count: int = 200) -> list:
        if not self.token:
            await self.authenticate()
            
        endpoint = f"/api/v1/candles?symbol={symbol}&interval=1m&count={count}"
        data = await self._request("GET", endpoint, "MARKET_DATA_CHART", headers=self._get_headers())
        
        return data.get("result", {}).get("candles", [])

    # 대기 주문 조회 (Case 42 - Limit-Trap 방어용 미체결 스캔)
    async def get_orders(self, status: str, symbol: str = None) -> list:
        if not self.account_seq:
            await self.fetch_account_seq()
            
        endpoint = f"/api/v1/orders?status={status}"
        if symbol:
            endpoint += f"&symbol={symbol}"
            
        data = await self._request("GET", endpoint, "ORDER_HISTORY", headers=self._get_headers(requires_account=True))
        return data.get("result", {}).get("orders", [])

    # 멱등성 보장 주문 전송 코어 엔진 (Case 60 - 정수형 락온)
    async def create_order(self, symbol: str, side: str, order_type: str, quantity: float, price: float = None, time_in_force: str = "DAY", client_order_id: str = None) -> dict:
        if not self.account_seq:
            await self.fetch_account_seq()
            
        payload = {
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "timeInForce": time_in_force
        }
        
        # 소수점 팻핑거 거절 원천 방어망 (내림 정수형 락온)
        payload["quantity"] = str(int(math.floor(quantity)))
        
        if order_type == "LIMIT" and price is not None:
            payload["price"] = str(price)
            
        if client_order_id:
            payload["clientOrderId"] = client_order_id
            
        data = await self._request("POST", "/api/v1/orders", "ORDER", headers=self._get_headers(requires_account=True), json=payload)
        return data.get("result", {})

# 3분봉 하이킨 아시 100% 벡터화 엔진
class HeikinAshiEngine:
    @staticmethod
    def calculate_3m_ha(candles_json: list) -> pd.DataFrame:
        if not candles_json:
            return pd.DataFrame()
            
        df = pd.DataFrame(candles_json)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # 제3헌법 타임존 락온 (EST 강제 변환)
        df['timestamp'] = df['timestamp'].dt.tz_convert(ZoneInfo('America/New_York'))
        df.set_index('timestamp', inplace=True)
        
        # 정밀도 락온
        for col in ['openPrice', 'highPrice', 'lowPrice', 'closePrice', 'volume']:
            df[col] = df[col].astype(float)
            
        # 3분봉 압축 및 섀도우 결측 방어 (Case 35)
        df_3m = df.resample('3min', label='left', closed='left').agg({
            'openPrice': 'first',
            'highPrice': 'max',
            'lowPrice': 'min',
            'closePrice': 'last',
            'volume': 'sum'
        }).ffill()
        
        ha_df = pd.DataFrame(index=df_3m.index)
        
        # 벡터화 HA 수식 (루프 소각)
        ha_df['HA_Close'] = (df_3m['openPrice'] + df_3m['highPrice'] + df_3m['lowPrice'] + df_3m['closePrice']) / 4.0
        
        shifted_ha_close = ha_df['HA_Close'].shift(1)
        shifted_ha_close.iloc[0] = (df_3m['openPrice'].iloc[0] + df_3m['closePrice'].iloc[0]) / 2.0
        ha_df['HA_Open'] = shifted_ha_close.ewm(alpha=0.5, adjust=False).mean()
        
        ha_df['HA_High'] = pd.concat([df_3m['highPrice'], ha_df['HA_Open'], ha_df['HA_Close']], axis=1).max(axis=1)
        ha_df['HA_Low'] = pd.concat([df_3m['lowPrice'], ha_df['HA_Open'], ha_df['HA_Close']], axis=1).min(axis=1)
        ha_df['Volume'] = df_3m['volume']
        
        return ha_df.sort_index(ascending=True)

# 텔레그램 관제탑 라우터 및 봇 초기화
router = Router()
api_client = TossApiClient(client_id=TOSS_CLIENT_ID, client_secret=TOSS_CLIENT_SECRET)

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 잔고 스캔", callback_data="scan_asset")],
        [InlineKeyboardButton(text="📈 SOXL 실시간 & 3분봉 HA 스캔", callback_data="scan_ha")]
    ])
    
    welcome_text = (
        "🤖 <b>승승장군 퀀트 관제탑 가동</b>\n\n"
        "▫️ 시스템: Toss Securities V14 / V-REV\n"
        "▫️ 상태: Online 및 API 대기 중\n\n"
        "원하시는 명령을 선택하십시오."
    )
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")

# 독립 레스큐 모듈 격발 및 원자적 롤백 통제망
@router.message(Command("update"))
async def cmd_update(message: types.Message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return

    await message.answer("⏳ <b>레스큐 모듈(plugin_updater.py) 격발. 깃허브 원장 동기화 및 프리플라이트 검증 진행 중...</b>", parse_mode="HTML")
    
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, "plugin_updater.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        out_text = stdout.decode('utf-8').strip()
        err_text = stderr.decode('utf-8').strip()
        
        safe_out = html.escape(out_text) if out_text else "출력 없음"
        safe_err = html.escape(err_text) if err_text else "에러 없음"
        
        if process.returncode == 0:
            result_msg = (
                f"✅ <b>업데이트 및 검증 통과</b>\n\n"
                f"▫️ <b>STDOUT</b>:\n<pre>{safe_out}</pre>"
            )
            await message.answer(result_msg, parse_mode="HTML")
            
            if "Already up to date." not in out_text:
                await message.answer("⚠️ <b>검증된 새 코어 코드 감지. 데몬을 즉시 재가동(Restart)합니다.</b>", parse_mode="HTML")
                await asyncio.sleep(1)
                os._exit(0)
        else:
            result_msg = (
                f"🚨 <b>치명적 에러 감지 및 레스큐 롤백 완료</b>\n\n"
                f"▫️ <b>본진 프로세스(main.py)는 죽지 않고 생존 상태를 유지합니다.</b>\n"
                f"▫️ <b>STDERR (문법 에러 원인)</b>:\n<pre>{safe_err}</pre>\n"
                f"▫️ <b>STDOUT (복구 로그)</b>:\n<pre>{safe_out}</pre>"
            )
            await message.answer(result_msg, parse_mode="HTML")
            
    except Exception as e:
        safe_error = html.escape(str(e))
        await message.answer(f"🚨 <b>관제탑 업데이트 통신 붕괴 감지</b>:\n<pre>{safe_error}</pre>", parse_mode="HTML")

# 인라인 버튼: 잔고 스캔
@router.callback_query(F.data == "scan_asset")
async def process_scan_asset(callback_query: types.CallbackQuery):
    if callback_query.from_user.id != ADMIN_CHAT_ID:
        return

    await callback_query.message.edit_text("⏳ <b>토스증권 잔고 원장 동기화 중...</b>", parse_mode="HTML")
    
    try:
        usd_bp = await api_client.get_usd_buying_power()
        soxl_qty = await api_client.get_soxl_holdings()
        
        est_now = datetime.now(ZoneInfo('America/New_York')).strftime("%Y-%m-%d %H:%M:%S")
        safe_est = html.escape(est_now)
        
        result_text = (
            f"📊 <b>계좌 자산 스캔 완료</b>\n\n"
            f"🔹 <b>기준 시각</b>: {safe_est} EST\n"
            f"🔹 <b>매수 가능 달러</b>: ${usd_bp:,.2f}\n"
            f"🔹 <b>SOXL 보유 수량</b>: {soxl_qty}주\n"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 다시 스캔하기", callback_data="scan_asset")],
            [InlineKeyboardButton(text="🔙 메인 메뉴", callback_data="back_to_main")]
        ])
        
        await callback_query.message.edit_text(result_text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        error_msg = html.escape(str(e))
        await callback_query.message.edit_text(f"🚨 <b>시스템 붕괴 감지</b>\n\n▫️ {error_msg}", parse_mode="HTML")

@router.callback_query(F.data == "scan_ha")
async def process_scan_ha(callback_query: types.CallbackQuery):
    if callback_query.from_user.id != ADMIN_CHAT_ID:
        return

    await callback_query.message.edit_text("⏳ <b>토스증권 시세 타격 및 HA 벡터 엔진 가동 중...</b>", parse_mode="HTML")
    
    try:
        current_price_task = api_client.get_current_price("SOXL")
        candles_task = api_client.get_1m_candles("SOXL", count=200)
        
        current_price, candles_json = await asyncio.gather(current_price_task, candles_task)
        
        ha_df = HeikinAshiEngine.calculate_3m_ha(candles_json)
        
        est_now = datetime.now(ZoneInfo('America/New_York')).strftime("%Y-%m-%d %H:%M:%S")
        safe_est = html.escape(est_now)
        
        if ha_df.empty:
            result_text = f"🚨 <b>캔들 데이터 붕괴 (빈 배열)</b>\n\n🔹 <b>기준 시각</b>: {safe_est} EST\n🔹 <b>실시간 종가</b>: ${current_price:.2f}"
        else:
            recent_ha = ha_df.tail(10)
            ha_history_text = ""
            
            for time_idx, row in recent_ha.iterrows():
                ha_o = row['HA_Open']
                ha_c = row['HA_Close']
                ha_time_str = time_idx.strftime("%H:%M")
                
                if ha_c >= ha_o:
                    candle_icon = "🟥 양봉"
                else:
                    candle_icon = "🟦 음봉"
                    
                ha_history_text += f"🔸 [{ha_time_str}] {candle_icon} ${ha_c:.2f}\n"
                
            result_text = (
                f"📈 <b>SOXL 시세 및 하이킨 아시 스캔 완료</b>\n\n"
                f"🔹 <b>스캔 시각</b>: {safe_est} EST\n"
                f"🔹 <b>실시간 종가 (Tick)</b>: <b>${current_price:.2f}</b>\n\n"
                f"📊 <b>최근 3분봉 HA 흐름 (최대 10개)</b>\n"
                f"{ha_history_text}"
            )
            
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 다시 스캔하기", callback_data="scan_ha")],
            [InlineKeyboardButton(text="🔙 메인 메뉴", callback_data="back_to_main")]
        ])
        
        await callback_query.message.edit_text(result_text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        error_msg = html.escape(str(e))
        await callback_query.message.edit_text(f"🚨 <b>연산 엔진 붕괴 감지</b>\n\n▫️ {error_msg}", parse_mode="HTML")

# 뒤로가기 버튼
@router.callback_query(F.data == "back_to_main")
async def process_back_to_main(callback_query: types.CallbackQuery):
    if callback_query.from_user.id != ADMIN_CHAT_ID:
        return
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 잔고 스캔", callback_data="scan_asset")],
        [InlineKeyboardButton(text="📈 SOXL 실시간 & 3분봉 HA 스캔", callback_data="scan_ha")]
    ])
    
    welcome_text = (
        "🤖 <b>승승장군 퀀트 관제탑 가동</b>\n\n"
        "▫️ 시스템: Toss Securities V14 / V-REV\n"
        "▫️ 상태: Online 및 API 대기 중\n\n"
        "원하시는 명령을 선택하십시오."
    )
    await callback_query.message.edit_text(welcome_text, reply_markup=keyboard, parse_mode="HTML")


# HA 암살자 무한 폴링 루프 (데이장 ~ 애프터장 상시 가동)
async def ha_assassin_loop(client: TossApiClient):
    last_action_candle_time = None
    
    # 안전망: 서버 재기동 시 계좌 정보 선행 적재
    try:
        await client.fetch_account_seq()
    except Exception as e:
        print(f"🚨 [HA 암살자] 초기 계좌 정보 로드 실패: {e}")
        
    while True:
        # 1분 주기 스캔: 파이썬 밀림(Drift) 현상 방어를 위해 1분 주기 순회 후 3분 캔들 완성 여부 교차 검증 (Case 43)
        await asyncio.sleep(60)
        
        try:
            now_kst = datetime.now(ZoneInfo('Asia/Seoul'))
            
            # 시장 운영 시간 선제적 검증 및 세션 종료 시각 반환 락온
            is_open, session_end_time = await client.is_market_open()
            if not is_open:
                continue
                
            soxl_qty = await client.get_soxl_holdings()
            
            # 세션 마감 2분 전(Zero-Overnight) 강제 전량 매도 방어막 격발 (Case 09 & 23)
            if session_end_time and (session_end_time - now_kst).total_seconds() <= 120:
                if soxl_qty >= 1:
                    now_est_str = datetime.now(ZoneInfo('America/New_York')).strftime("%Y%m%d%H%M%S")
                    await client.create_order(
                        symbol="SOXL", 
                        side="SELL", 
                        order_type="MARKET", 
                        quantity=soxl_qty, # 전량 덤핑 팩트 보장
                        client_order_id=f"HAZERO_{now_est_str}"
                    )
                    await HAStateManager.save_state(0.0) # 장부 초기화
                    print(f"⚠️ [HA 암살자] 세션 마감 2분 전 컷오프. Zero-Overnight 방어막 가동 -> {soxl_qty}주 시장가 전량 매도 및 장부 초기화 완료.")
                continue # 정규 타점 로직 진입 원천 차단 (Bypass)

            # MODIFIED: HA 예열(Warm-up) 데이터 결핍에 따른 색상 왜곡 오판 방어 및 관제탑 동기화를 위해 count 200으로 상향 락온
            candles_json = await client.get_1m_candles("SOXL", count=200)
            ha_df = HeikinAshiEngine.calculate_3m_ha(candles_json)
            
            if len(ha_df) < 3:
                continue
                
            # Repainting 방어를 위해 닫힌(Closed) 직전 2개의 캔들만 팩트 검증
            c1 = ha_df.iloc[-3]
            c2 = ha_df.iloc[-2]
            current_closed_time = c2.name
            
            # 동일 3분 캔들 구간 내 이중 타격 원천 차단
            if last_action_candle_time == current_closed_time:
                continue
                
            is_c1_yang = c1['HA_Close'] >= c1['HA_Open']
            is_c2_yang = c2['HA_Close'] >= c2['HA_Open']
            
            is_c1_eum = c1['HA_Close'] < c1['HA_Open']
            is_c2_eum = c2['HA_Close'] < c2['HA_Open']
            
            # 2연속 양봉 또는 2연속 음봉이 아닌 경우 캔들 추적만 하고 관망
            if not ((is_c1_yang and is_c2_yang) or (is_c1_eum and is_c2_eum)):
                continue

            # Limit-Trap 및 이중 결제 대참사 100% 방어망 (미체결 주문 스캔)
            open_orders = await client.get_orders(status="OPEN", symbol="SOXL")
            if open_orders:
                print("⚠️ [HA 암살자] 미체결 대기 주문 감지. 이중 결제 방지를 위해 현재 루프 바이패스(Bypass)합니다.")
                continue
                
            # 타격 전 지연 평가(Lazy Load)로 시세 팩트 스캔
            current_price = await client.get_current_price("SOXL")
            if current_price <= 0.0:
                continue
                
            # 상태 장부에서 1주 매수 단가 동기화
            last_buy_price = await HAStateManager.get_state()
            
            # 유령 잔고 자가 치유(Self-Healing) - 실잔고는 있으나 장부 기록이 소실된 엣지 케이스 방어
            if soxl_qty >= 1 and last_buy_price <= 0.0:
                last_buy_price = current_price
                await HAStateManager.save_state(last_buy_price)
                print(f"♻️ [HA 암살자] 유령 잔고 팩트 교정: 장부 데이터 소실 감지. 현재가(${last_buy_price:.2f}) 앵커링 완료.")
                
            now_est_str = datetime.now(ZoneInfo('America/New_York')).strftime("%Y%m%d%H%M%S")
            
            # [타점 1] 0주 상태 & 2연속 양봉 -> 시장가 매수 1주 격발
            if is_c1_yang and is_c2_yang and soxl_qty == 0:
                usd_bp = await client.get_usd_buying_power()
                
                # 자본 잠김(422 Error) 방어망 (3% 버퍼)
                if usd_bp < (current_price * 1.03):
                    print(f"⚠️ [HA 암살자] 자본 잠김 컷오프: 매수 가능 금액(${usd_bp:.2f})이 시장가 증거금 버퍼(${current_price * 1.03:.2f})보다 부족합니다. 타점 소각.")
                    continue
                    
                client_order_id = f"HABUY_{now_est_str}"
                await client.create_order(
                    symbol="SOXL", 
                    side="BUY", 
                    order_type="MARKET", 
                    quantity=1, 
                    client_order_id=client_order_id
                )
                
                # 원자적 쓰기로 장부에 체결가 락온
                await HAStateManager.save_state(current_price)
                last_action_candle_time = current_closed_time
                print(f"🎯 [HA 암살자] 2연속 양봉 포착 및 자본 검증 통과. 시장가 1주 매수 완료 (기록가: ${current_price:.2f}).")
                
            # [타점 2] 1주 이상 상태 & 2연속 음봉 -> 절대 이격도 0.2% 검증 후 시장가 매도 1주 격발
            elif is_c1_eum and is_c2_eum and soxl_qty >= 1:
                # 횡보장 휩쏘 방어망 (절대 이격도 0.2% 검증 로직)
                deviation = abs(current_price - last_buy_price) / last_buy_price
                
                if deviation >= 0.002: # 0.2% 이상 이탈 확인 시 타격
                    client_order_id = f"HASELL_{now_est_str}"
                    await client.create_order(
                        symbol="SOXL", 
                        side="SELL", 
                        order_type="MARKET", 
                        quantity=1, 
                        client_order_id=client_order_id
                    )
                    
                    # 매도 성공 시 장부 영구 초기화
                    await HAStateManager.save_state(0.0)
                    last_action_candle_time = current_closed_time
                    print(f"🎯 [HA 암살자] 2연속 음봉 포착 & 절대 이격도({deviation*100:.2f}%) 0.2% 돌파 팩트 확인. 시장가 1주 매도 완료.")
                else:
                    print(f"🛡️ [HA 암살자] 횡보장 휩쏘 방어 컷오프: 2연속 음봉이나 절대 이격도({deviation*100:.2f}%)가 0.2%에 미달합니다. 타점 소각 후 관망 유지.")
                
        except Exception as e:
            print(f"🚨 [HA 암살자] 감시망 루프 내부 붕괴: {e}")


# 시스템 심장부 및 비동기 데몬 격발
async def main():
    # 텔레그램 네트워크 단절(Errno 104) 완화용 세션 타임아웃 주입
    session = AiohttpSession(timeout=60.0)
    bot = Bot(token=TELEGRAM_BOT_TOKEN, session=session)
    dp = Dispatcher()
    dp.include_router(router)
    
    # 12시간 선제 타격 토큰 갱신 스케줄러 백그라운드 데몬 격발
    asyncio.create_task(api_client.token_renewal_loop())
    
    # HA 암살자 무한 매매 폴링 루프 백그라운드 데몬 격발
    asyncio.create_task(ha_assassin_loop(api_client))
    
    print("시스템 코어 로드 완료. 텔레그램 롱 폴링(Long-Polling) 개시...")
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("관제탑 셧다운 완료.")
