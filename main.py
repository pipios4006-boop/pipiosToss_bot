# =====================================================================
# 파일명: main.py
# 최근 업데이트:
# 1. SOXL 실시간 현재가(GET /prices) 조회 모듈 결속 (MARKET_DATA 통제)
# 2. 토스 1분봉(GET /candles) 기반 3분봉 하이킨 아시(Heikin-Ashi) 벡터화 엔진 결속
# 3. 12시간 주기 토큰 자동 갱신 스케줄러 및 401 요격 자가 치유 엔진 결속
# 4. 주문 생성 및 조회 API 래퍼 모듈 결속 (멱등성, 정수형 락온)
# 5. HA 암살자(aVWAP) 3분봉 네이티브 MARKET 주문 무한 루프 데몬 가동
# 6. 시장 운영 달력(US) 인메모리 캐싱 및 비운영 시간 선제 스킵 락온
# 7. 시장가 증거금(3% 버퍼) 부족 시 422 밴 방어용 자본 잠김 컷오프 결속
# 8. 세션 마감 2분 전 Zero-Overnight 강제 청산 방어막 결속
# 9. 횡보장 휩쏘 방어용 절대 이격도(0.2%) 검증 알고리즘 및 유령 잔고 자가 치유 결속
# 10. 텔레그램 Errno 104 통신 붕괴 방어용 AiohttpSession 주입
# 11. 토스 API 물리적 단절 시 3단 지수 백오프(Exponential Backoff) 무중단 Fallback 결속
# 12. HA 예열(Warm-up) 데이터 결핍에 따른 색상 왜곡 방어용 수집량(count=200) 전격 상향 락온
# 13. US 달력 API 쿼리 파라미터 오염(KST->EST) 교정 및 락온 (제3헌법 및 Case 51)
# 14. 토스증권 미국 주식 MARKET 주문 제한 패러독스 방어용 '합성 시장가(LIMIT)' 전면 전환 락온
# 15. 수동 전량 매도(Hit & Cut) 개입에 따른 0주 상태 파편화 100% 방어막 결속 (Case 46)
# 16. 폐기된 HA 스캔 UI 영구 소각 및 텔레그램 메인 메뉴 다이내믹 인터페이스 리빌딩
# 17. 상태 장부(ha_state.json) 2-Tier 마이그레이션 및 SOXL/GDXU 다중 종목 병렬 타격망 결속
# 18. 전역 디폴트 상태 비활성(False) 유지 및 베이스라인 타격 수량 1주 하향 락온
# 19. 다건 시세 병렬 추출(get_current_prices) UI 결속
# 20. [NEW] FSM(유한 상태 머신) 기반 텍스트 동적 수량 입력 및 팻핑거 원천 방어 락온 (Case 60)
# 21. [NEW] 관제탑 자산 스캔 시 렌더링 과부하 방지를 위한 타겟 종목(TARGET_SYMBOLS) 필터링 결속
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
# NEW: 텍스트 입력을 위한 FSM 모듈 결속
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# 자격증명 및 시스템 상수 락온
TOSS_CLIENT_ID = os.getenv("TOSS_CLIENT_ID", "tsck_live_QogVVVdZPhhg3sbTo5T7hB")
TOSS_CLIENT_SECRET = os.getenv("TOSS_CLIENT_SECRET", "tssk_live_vvWo029zWfkoNLKscu8QbEoM7enrcOeNpCg98sHTeVYD")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7850532415:AAGiZg_gbUDXjBA7QOnvTbSPXii5WwFQ7wQ")
ADMIN_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "796232854"))

# 감시 대상 글로벌 유니버스 락온
TARGET_SYMBOLS = ["SOXL", "GDXU"]

# NEW: FSM 상태 클래스 정의
class QuantityInputState(StatesGroup):
    waiting_for_qty = State()

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

# 다중 종목 2-Tier 상태 장부 영구 보존 및 자동 마이그레이션 코어
class HAStateManager:
    FILE_PATH = "ha_state.json"

    @classmethod
    async def get_state(cls) -> dict:
        async with GlobalThrottle.get_file_lock(cls.FILE_PATH):
            def _read():
                # 참조 오염(Shallow Copy) 방지용 딥 다이브 인메모리 딕셔너리 강제 할당 (디폴트 1주)
                default_state = {
                    "SOXL": {"active": False, "qty": 1, "last_buy_price": 0.0},
                    "GDXU": {"active": False, "qty": 1, "last_buy_price": 0.0}
                }
                
                if not os.path.exists(cls.FILE_PATH):
                    return default_state
                try:
                    with open(cls.FILE_PATH, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        # V1 단일 구조 자동 마이그레이션 방어망 (Backward Compatibility)
                        if "SOXL" not in data:
                            migrated = default_state
                            migrated["SOXL"]["last_buy_price"] = float(data.get("last_buy_price", 0.0))
                            return migrated
                        return data
                except Exception:
                    return default_state
            return await asyncio.to_thread(_read)

    @classmethod
    async def save_state(cls, state_dict: dict):
        async with GlobalThrottle.get_file_lock(cls.FILE_PATH):
            def _write():
                tmp_path = cls.FILE_PATH + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(state_dict, f)
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
            # 텔레그램 표출 및 응답 파싱용 기준 시각 (KST)
            now_kst = datetime.now(ZoneInfo('Asia/Seoul'))
            
            # 제3헌법 및 Case 01 준수 - 토스 API 쿼리 파라미터는 반드시 EST 기준 날짜를 전송하여 오염 차단
            est_today_str = datetime.now(ZoneInfo('America/New_York')).strftime("%Y-%m-%d")
            
            if self._calendar_cache.get("date") != est_today_str:
                try:
                    endpoint = f"/api/v1/market-calendar/US?date={est_today_str}"
                    data = await self._request("GET", endpoint, "MARKET_INFO", headers=self._get_headers())
                    today_cal = data.get("result", {}).get("today", {})
                    
                    sessions = []
                    for session_name in ["dayMarket", "preMarket", "regularMarket", "afterMarket"]:
                        session_data = today_cal.get(session_name)
                        if session_data:
                            # 토스 응답의 startTime/endTime은 KST(+09:00) 기준 ISO 8601 문자열
                            start_dt = datetime.fromisoformat(session_data["startTime"])
                            end_dt = datetime.fromisoformat(session_data["endTime"])
                            sessions.append((start_dt, end_dt))
                    
                    self._calendar_cache = {"date": est_today_str, "sessions": sessions}
                    print(f"📅 토스증권 US 시장 달력 캐싱 완료: {est_today_str} (총 {len(sessions)}개 세션 확보)")
                except Exception as e:
                    print(f"⚠️ [달력 API] 통신 지연 또는 파싱 오류. Fail-Open 가동 (무조건 주문 허용): {e}")
                    return True, None # 엣지 타임라인 Fail-Safe 구조화
                    
            cached_sessions = self._calendar_cache.get("sessions", [])
            
            if not cached_sessions:
                return False, None
                
            # 현재 KST 시각이 어떠한 세션 내에 존재하면 (True, 해당 세션 종료시각) 반환
            for start_dt, end_dt in cached_sessions:
                if start_dt <= now_kst <= end_dt:
                    return True, end_dt
                    
            return False, None

    # 환율 조회 모듈 결속 (원화 수익금 연산용)
    async def get_usd_to_krw_rate(self) -> float:
        if not self.token:
            await self.authenticate()
            
        endpoint = "/api/v1/exchange-rate?baseCurrency=USD&quoteCurrency=KRW"
        data = await self._request("GET", endpoint, "MARKET_INFO", headers=self._get_headers())
        
        rate = data.get("result", {}).get("rate", "0")
        return float(rate) if rate else 0.0

    async def get_usd_buying_power(self) -> float:
        if not self.account_seq:
            await self.fetch_account_seq()
            
        data = await self._request("GET", "/api/v1/buying-power?currency=USD", "ORDER_INFO", headers=self._get_headers(requires_account=True))
        result = data.get("result", {})
        
        raw_bp = result.get("cashBuyingPower")
        return float(raw_bp) if raw_bp is not None else 0.0

    # 다중 종목 코어 매매 로직 전용 수량 조회 (정수형 내림 락온 보존)
    async def get_symbol_holdings(self, symbol: str) -> int:
        if not self.account_seq:
            await self.fetch_account_seq()
            
        data = await self._request("GET", f"/api/v1/holdings?symbol={symbol}", "ASSET", headers=self._get_headers(requires_account=True))
        items = data.get("result", {}).get("items", [])
        
        if not items:
            return 0
            
        raw_qty = items[0].get("quantity")
        return int(float(raw_qty)) if raw_qty is not None else 0

    # 통합 자산 스캔 전용 전체 종목 상세 조회
    async def get_all_holdings_detail(self) -> list:
        if not self.account_seq:
            await self.fetch_account_seq()
            
        data = await self._request("GET", "/api/v1/holdings", "ASSET", headers=self._get_headers(requires_account=True))
        return data.get("result", {}).get("items", [])

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

    # 다건 시세 병렬 추출 모듈 (관제탑 블라인드 방어용)
    async def get_current_prices(self, symbols: list) -> dict:
        if not self.token:
            await self.authenticate()
            
        symbols_str = ",".join(symbols)
        endpoint = f"/api/v1/prices?symbols={symbols_str}"
        data = await self._request("GET", endpoint, "MARKET_DATA", headers=self._get_headers())
        
        results = data.get("result", [])
        # 종목별 현재가를 딕셔너리로 추출 (결측 방어 포함)
        return {item.get("symbol"): float(item.get("lastPrice", 0.0)) for item in results}

    # 호가장부 조회 모듈 (합성 시장가 LIMIT 타격 및 1호가 추적용)
    async def get_orderbook(self, symbol: str) -> dict:
        if not self.token:
            await self.authenticate()
            
        endpoint = f"/api/v1/orderbook?symbol={symbol}"
        data = await self._request("GET", endpoint, "MARKET_DATA", headers=self._get_headers())
        
        return data.get("result", {})

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
        
        # 봇 매매의 소수점 팻핑거 거절 원천 방어망 (내림 정수형 1주 락온 강제)
        payload["quantity"] = str(int(math.floor(quantity)))
        
        if order_type == "LIMIT" and price is not None:
            # 안전한 String 형변환 락온
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
            
        # 3분봉 압축 및 섀도 결측 방어 (Case 35)
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

# 메인 키보드 동적 렌더링 엔진
def get_main_keyboard(state: dict) -> InlineKeyboardMarkup:
    keyboard = []
    keyboard.append([InlineKeyboardButton(text="💰 통합 자산 및 시세 스캔", callback_data="scan_asset")])
    
    for symbol in TARGET_SYMBOLS:
        sym_state = state.get(symbol, {"active": False, "qty": 1, "last_buy_price": 0.0})
        is_active = sym_state.get("active", False)
        # 기본 UI 수량 fallback 1주 락온
        qty = sym_state.get("qty", 1)
        
        status_text = f"🟢 {symbol} (가동 중)" if is_active else f"🔴 {symbol} (대기 중)"
        keyboard.append([
            InlineKeyboardButton(text=status_text, callback_data=f"toggle_{symbol}"),
            InlineKeyboardButton(text=f"⚙️ 수량: {qty}주", callback_data=f"menu_qty_{symbol}")
        ])
        
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# MODIFIED: 시작 시 FSM 초기화 결속
@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
        
    await state.clear() # 컨텍스트 스위칭 락다운 방어
    app_state = await HAStateManager.get_state()
    keyboard = get_main_keyboard(app_state)
    
    welcome_text = (
        "🤖 <b>승승장군 퀀트 관제탑 가동</b>\n\n"
        "▫️ 시스템: Toss Securities V17 / V-REV\n"
        "▫️ 상태: Online 및 다이내믹 패널 대기 중\n\n"
        "아래 패널에서 각 종목별 매매 엔진을 독립 제어하십시오."
    )
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")

# 다중 종목 토글 스위치 코어
@router.callback_query(F.data.startswith("toggle_"))
async def process_toggle(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_CHAT_ID: return
    await state.clear()
    
    symbol = callback_query.data.split("_")[1]
    app_state = await HAStateManager.get_state()
    sym_state = app_state.get(symbol, {"active": False, "qty": 1, "last_buy_price": 0.0})
    
    new_active = not sym_state.get("active", False)
    sym_state["active"] = new_active
    
    # 비활성화 시 잔재 타점 영구 소각 (방어망 결속)
    if not new_active:
        sym_state["last_buy_price"] = 0.0
        
    app_state[symbol] = sym_state
    await HAStateManager.save_state(app_state)
    await callback_query.answer(f"✅ {symbol} 엔진 {'가동' if new_active else '중지'} 완료", show_alert=False)
    
    keyboard = get_main_keyboard(app_state)
    await callback_query.message.edit_reply_markup(reply_markup=keyboard)

# MODIFIED: FSM 상태 진입 및 텍스트 입력 유도
@router.callback_query(F.data.startswith("menu_qty_"))
async def process_menu_qty(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_CHAT_ID: return
    
    symbol = callback_query.data.split("_")[2]
    
    # FSM 상태에 심볼 저장 및 대기 모드 진입
    await state.update_data(target_symbol=symbol)
    await state.set_state(QuantityInputState.waiting_for_qty)
    
    text = (
        f"⚙️ <b>{symbol} 타격 수량 설정</b>\n\n"
        f"🔹 변경하실 수량을 <b>채팅창에 숫자로만</b> 입력하십시오.\n"
        f"🔹 (예시: 10)\n\n"
        f"⚠️ 설정을 취소하시려면 /start 를 다시 입력하십시오."
    )
    await callback_query.message.edit_text(text, parse_mode="HTML")
    await callback_query.answer()

# NEW: FSM 기반 정수형 동적 수량 입력 처리 코어
@router.message(QuantityInputState.waiting_for_qty)
async def process_qty_input(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID: return
    
    input_text = message.text.strip()
    
    # 팻핑거 1차 방어: 순수 숫자 검증
    if not input_text.isdigit():
        await message.answer("🚨 <b>입력 오류</b>: 순수 정수(숫자)만 입력하십시오. (예: 10)", parse_mode="HTML")
        return
        
    new_qty = int(input_text)
    
    # 팻핑거 2차 방어: 0주 이하 락온
    if new_qty < 1:
        await message.answer("🚨 <b>입력 오류</b>: 최소 1주 이상 입력하십시오.", parse_mode="HTML")
        return
        
    data = await state.get_data()
    symbol = data.get("target_symbol")
    
    if not symbol:
        await state.clear()
        await message.answer("🚨 시스템 오류: 대상 종목이 소실되었습니다. /start 를 다시 입력하십시오.")
        return
        
    # 상태 장부에 원자적 쓰기 동기화
    app_state = await HAStateManager.get_state()
    sym_state = app_state.get(symbol, {"active": False, "qty": 1, "last_buy_price": 0.0})
    sym_state["qty"] = new_qty
    app_state[symbol] = sym_state
    await HAStateManager.save_state(app_state)
    
    # FSM 초기화
    await state.clear()
    
    keyboard = get_main_keyboard(app_state)
    success_text = (
        f"✅ <b>{symbol} 수량 변경 완료</b>\n\n"
        f"🔹 현재 설정된 타격 수량: <b>{new_qty}주</b>\n\n"
        f"아래 패널에서 각 종목별 매매 엔진을 독립 제어하십시오."
    )
    await message.answer(success_text, reply_markup=keyboard, parse_mode="HTML")

# 통합 자산 스캔 코어 (다건 실시간 시세 병렬 추출 및 렌더링 필터링 결속)
@router.callback_query(F.data == "scan_asset")
async def process_scan_asset(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_CHAT_ID:
        return

    await state.clear()
    await callback_query.answer("⏳ 전 종목 시세 및 원장 동기화 중...", show_alert=False)
    
    try:
        holdings_task = api_client.get_all_holdings_detail()
        rate_task = api_client.get_usd_to_krw_rate()
        usd_bp_task = api_client.get_usd_buying_power()
        prices_task = api_client.get_current_prices(TARGET_SYMBOLS) # 블라인드 0주 시세 요격망
        
        items, ex_rate, usd_bp, current_prices = await asyncio.gather(
            holdings_task, rate_task, usd_bp_task, prices_task
        )
        
        est_now = datetime.now(ZoneInfo('America/New_York')).strftime("%Y-%m-%d %H:%M:%S")
        safe_est = html.escape(est_now)
        
        # 타겟 종목 최상단 시세 UI 렌더링
        price_texts = []
        for sym in TARGET_SYMBOLS:
            cp = current_prices.get(sym, 0.0)
            price_texts.append(f"{sym} <b>${cp:,.2f}</b>")
        price_str = " / ".join(price_texts)
        
        krw_profit_total = 0.0
        usd_profit_total = 0.0
        item_texts = []
        
        for item in items:
            sym = item.get("symbol", "N/A")
            qty = float(item.get("quantity", 0.0))
            avg_price = float(item.get("averagePurchasePrice", 0.0))
            last_price = float(item.get("lastPrice", 0.0))
            p_usd = float(item.get("profitLoss", {}).get("amount", 0.0))
            p_rate = float(item.get("profitLoss", {}).get("rate", 0.0)) * 100
            
            # 총 수익금 연산은 필터링 없이 전체 계좌 자산 기준으로 100% 팩트 보존
            p_krw = p_usd * ex_rate
            krw_profit_total += p_krw
            usd_profit_total += p_usd
            
            # MODIFIED: 렌더링 과부하 방지를 위해 TARGET_SYMBOLS 만 추출하여 리스트 결속
            if sym in TARGET_SYMBOLS:
                item_texts.append(f"🔸 <b>{sym}</b>: {qty:,.2f}주 (평단 ${avg_price:,.2f} 👉 종가 ${last_price:,.2f}) [{p_rate:+,.2f}%]")
            
        result_text = (
            f"📊 <b>통합 자산 및 시세 스캔 완료</b>\n\n"
            f"🔹 <b>기준 시각</b>: {safe_est} EST\n"
            f"🔹 <b>실시간 종가</b>: {price_str}\n"
            f"🔹 <b>매수 가능 달러</b>: ${usd_bp:,.2f}\n"
            f"🔹 <b>총 수익금</b>: ${usd_profit_total:+,.2f} (₩{krw_profit_total:+,.0f})\n\n"
            f"📈 <b>타겟 종목 상세</b>\n"
            + ("\n".join(item_texts) if item_texts else "🔸 보유 중인 타겟 종목이 없습니다.")
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 자산 및 시세 다시 스캔", callback_data="scan_asset")],
            [InlineKeyboardButton(text="🔙 메인으로 복귀", callback_data="back_to_main")]
        ])
        
        # 단 1회 제자리 갱신(In-place Edit) 타격
        await callback_query.message.edit_text(result_text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        error_msg = html.escape(str(e))
        await callback_query.message.edit_text(f"🚨 <b>시스템 붕괴 감지</b>\n\n▫️ {error_msg}", parse_mode="HTML")

# 뒤로가기 버튼
@router.callback_query(F.data == "back_to_main")
async def process_back_to_main(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_CHAT_ID:
        return
        
    await state.clear()
    app_state = await HAStateManager.get_state()
    keyboard = get_main_keyboard(app_state)
    
    welcome_text = (
        "🤖 <b>승승장군 퀀트 관제탑 가동</b>\n\n"
        "▫️ 시스템: Toss Securities V17 / V-REV\n"
        "▫️ 상태: Online 및 다이내믹 패널 대기 중\n\n"
        "아래 패널에서 각 종목별 매매 엔진을 독립 제어하십시오."
    )
    await callback_query.message.edit_text(welcome_text, reply_markup=keyboard, parse_mode="HTML")


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


# HA 암살자 무한 폴링 루프 (다중 종목 병렬 타격망)
async def ha_assassin_loop(client: TossApiClient):
    last_action_candle_time = {sym: None for sym in TARGET_SYMBOLS}
    
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
                
            state = await HAStateManager.get_state()
            
            # 활성화된 타겟 종목만 순회하며 개별 타격망 가동
            for symbol in TARGET_SYMBOLS:
                sym_state = state.get(symbol, {"active": False, "qty": 1, "last_buy_price": 0.0})
                
                # 종목 비활성 시 타점 연산 및 강제 청산 완전 바이패스
                if not sym_state.get("active", False):
                    continue
                    
                # 타격 엔진 수량 파싱 시 기본 1주 락온
                target_qty = sym_state.get("qty", 1)
                early_state_price = sym_state.get("last_buy_price", 0.0)
                
                # 타겟 종목 실시간 보유 수량 교차 스캔
                sym_qty = await client.get_symbol_holdings(symbol)
                
                # 수동 전량 매도 개입에 따른 0주 상태 파편화 방어 (Case 46)
                if sym_qty == 0 and early_state_price > 0.0:
                    sym_state["last_buy_price"] = 0.0
                    state[symbol] = sym_state
                    await HAStateManager.save_state(state)
                    print(f"♻️ [HA 암살자] 수동 청산 팩트 교정: 실잔고 0주 감지. 오염된 {symbol} 장부 매수가(${early_state_price:.2f})를 0.0으로 강제 동기화 완료.")

                # 세션 마감 2분 전(Zero-Overnight) 활성 종목 전량 덤핑 방어막 격발 (Case 09 & 23)
                if session_end_time and (session_end_time - now_kst).total_seconds() <= 120:
                    if sym_qty >= 1:
                        orderbook = await client.get_orderbook(symbol)
                        bids = orderbook.get("bids", [])
                        if bids:
                            bid_1_price = float(bids[0]["price"])
                            now_est_str = datetime.now(ZoneInfo('America/New_York')).strftime("%Y%m%d%H%M%S")
                            await client.create_order(
                                symbol=symbol, 
                                side="SELL", 
                                order_type="LIMIT", 
                                quantity=sym_qty,
                                price=bid_1_price,
                                client_order_id=f"HAZERO_{symbol}_{now_est_str}"
                            )
                            sym_state["last_buy_price"] = 0.0
                            state[symbol] = sym_state
                            await HAStateManager.save_state(state)
                            print(f"⚠️ [HA 암살자] {symbol} 세션 마감 2분 전 컷오프. Zero-Overnight 방어막 가동 -> {sym_qty}주 지정가(${bid_1_price:.2f}) 덤핑 완료.")
                        else:
                            print(f"⚠️ [HA 암살자] {symbol} Zero-Overnight 덤핑 시도 중 호가창 붕괴 요격. 지정가 덤핑 불가.")
                    continue # 덤핑 진행 시 정규 타점 로직 진입 원천 차단 (Bypass)

                # HA 예열 및 캔들 추출
                candles_json = await client.get_1m_candles(symbol, count=200)
                ha_df = HeikinAshiEngine.calculate_3m_ha(candles_json)
                
                if len(ha_df) < 3:
                    continue
                    
                # Repainting 방어를 위해 닫힌(Closed) 직전 2개의 캔들만 팩트 검증
                c1 = ha_df.iloc[-3]
                c2 = ha_df.iloc[-2]
                current_closed_time = c2.name
                
                # 동일 3분 캔들 구간 내 이중 타격 원천 차단
                if last_action_candle_time[symbol] == current_closed_time:
                    continue
                    
                is_c1_yang = c1['HA_Close'] >= c1['HA_Open']
                is_c2_yang = c2['HA_Close'] >= c2['HA_Open']
                
                is_c1_eum = c1['HA_Close'] < c1['HA_Open']
                is_c2_eum = c2['HA_Close'] < c2['HA_Open']
                
                # 2연속 양봉 또는 2연속 음봉이 아닌 경우 캔들 추적만 하고 관망
                if not ((is_c1_yang and is_c2_yang) or (is_c1_eum and is_c2_eum)):
                    continue

                # Limit-Trap 방어망 (미체결 스캔)
                open_orders = await client.get_orders(status="OPEN", symbol=symbol)
                if open_orders:
                    print(f"⚠️ [HA 암살자] {symbol} 미체결 대기 주문 감지. 이중 결제 방지를 위해 루프 바이패스합니다.")
                    continue
                    
                last_buy_price = sym_state.get("last_buy_price", 0.0)
                
                # 실시간 종가 폴링
                current_price = await client.get_current_price(symbol)
                if current_price <= 0.0:
                    continue
                
                # 유령 잔고 자가 치유(Self-Healing)
                if sym_qty >= 1 and last_buy_price <= 0.0:
                    last_buy_price = current_price
                    sym_state["last_buy_price"] = last_buy_price
                    state[symbol] = sym_state
                    await HAStateManager.save_state(state)
                    print(f"♻️ [HA 암살자] {symbol} 유령 잔고 팩트 교정 완료. 앵커링가: ${last_buy_price:.2f}")
                    
                now_est_str = datetime.now(ZoneInfo('America/New_York')).strftime("%Y%m%d%H%M%S")
                
                # [매수 타점] 0주 상태 & 2연속 양봉 -> 합성 시장가 목표 수량 매수 격발
                if is_c1_yang and is_c2_yang and sym_qty == 0:
                    orderbook = await client.get_orderbook(symbol)
                    asks = orderbook.get("asks", [])
                    
                    if not asks:
                        print(f"⚠️ [HA 암살자] {symbol} 매도 호가창 붕괴. 타점 소각.")
                        continue
                        
                    ask_1_price = float(asks[0]["price"])
                    usd_bp = await client.get_usd_buying_power()
                    
                    # 동적 수량 스케일링 자본 잠김 검증
                    required_bp = ask_1_price * target_qty * 1.03
                    if usd_bp < required_bp:
                        print(f"⚠️ [HA 암살자] 자본 잠김 컷오프: 가용 달러(${usd_bp:.2f})가 {symbol} 지정가 증거금 버퍼(${required_bp:.2f})보다 부족합니다. 타점 소각.")
                        continue
                        
                    client_order_id = f"HABUY_{symbol}_{now_est_str}"
                    
                    await client.create_order(
                        symbol=symbol, 
                        side="BUY", 
                        order_type="LIMIT", 
                        quantity=target_qty, 
                        price=ask_1_price,
                        client_order_id=client_order_id
                    )
                    
                    sym_state["last_buy_price"] = ask_1_price
                    state[symbol] = sym_state
                    await HAStateManager.save_state(state)
                    last_action_candle_time[symbol] = current_closed_time
                    print(f"🎯 [HA 암살자] {symbol} 2연속 양봉 포착. 합성 시장가 {target_qty}주 매수 완료 (기록가: ${ask_1_price:.2f}).")
                    
                # [매도 타점] 1주 이상 보유 & 2연속 음봉 -> 절대 이격도 0.2% 검증 후 지정가 덤핑
                elif is_c1_eum and is_c2_eum and sym_qty >= 1:
                    deviation = abs(current_price - last_buy_price) / last_buy_price
                    
                    if deviation >= 0.002:
                        orderbook = await client.get_orderbook(symbol)
                        bids = orderbook.get("bids", [])
                        
                        if not bids:
                            print(f"⚠️ [HA 암살자] {symbol} 매수 호가창 붕괴. 타점 소각.")
                            continue
                            
                        bid_1_price = float(bids[0]["price"])
                        client_order_id = f"HASELL_{symbol}_{now_est_str}"
                        
                        # 파편화 방어 동적 매도 물량 할당
                        sell_qty = target_qty if sym_qty >= target_qty else sym_qty
                        
                        await client.create_order(
                            symbol=symbol, 
                            side="SELL", 
                            order_type="LIMIT", 
                            quantity=sell_qty, 
                            price=bid_1_price,
                            client_order_id=client_order_id
                        )
                        
                        sym_state["last_buy_price"] = 0.0
                        state[symbol] = sym_state
                        await HAStateManager.save_state(state)
                        last_action_candle_time[symbol] = current_closed_time
                        print(f"🎯 [HA 암살자] {symbol} 2연속 음봉 & 절대 이격도({deviation*100:.2f}%) 돌파. {sell_qty}주 매도 완료.")
                    else:
                        print(f"🛡️ [HA 암살자] {symbol} 절대 이격도({deviation*100:.2f}%) 0.2% 미달. 휩쏘 방어막 가동 -> 타점 소각.")
                
        except Exception as e:
            print(f"🚨 [HA 암살자 글로벌 루프] 치명적 붕괴 감지: {e}")


# 시스템 심장부 및 비동기 데몬 격발
async def main():
    # 텔레그램 네트워크 단절(Errno 104) 완화용 세션 타임아웃 주입
    session = AiohttpSession(timeout=60.0)
    bot = Bot(token=TELEGRAM_BOT_TOKEN, session=session)
    dp = Dispatcher()
    dp.include_router(router)
    
    # 12시간 선제 타격 토큰 갱신 스케줄러 백그라운드 데몬 격발
    asyncio.create_task(api_client.token_renewal_loop())
    
    # HA 암살자 다중 종목 무한 매매 폴링 루프 백그라운드 데몬 격발
    asyncio.create_task(ha_assassin_loop(api_client))
    
    print("시스템 코어 로드 완료. 텔레그램 롱 폴링(Long-Polling) 개시...")
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("관제탑 셧다운 완료.")
