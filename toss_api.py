# =====================================================================
# 파일명: toss_api.py
# 목적: 토스증권 Open API 통신 전담 및 제1헌법(GlobalThrottle) 격리망
# =====================================================================

import asyncio
import aiohttp
import math
import contextlib
from datetime import datetime
from zoneinfo import ZoneInfo

# NEW: 제1헌법 - 동기 I/O 비동기 격리 및 Rate Limit 중앙 통제소 (독립 모듈화)
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

# NEW: API 클라이언트 엔진 단독 분리
class TossApiClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://openapi.tossinvest.com"
        self.token = None
        self.account_seq = None
        
        self._auth_lock = None
        self._last_auth_time = 0.0
        
        self._calendar_cache = {}
        self._calendar_lock = None

    async def _request(self, method: str, endpoint: str, group_name: str, **kwargs) -> dict:
        url = f"{self.base_url}{endpoint}"
        max_retries = 3
        timeout = aiohttp.ClientTimeout(total=10.0)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for attempt in range(max_retries):
                await GlobalThrottle.wait_api_sync(group_name)
                
                if "headers" in kwargs and "Authorization" in kwargs["headers"]:
                    kwargs["headers"]["Authorization"] = f"Bearer {self.token}"
                
                try:
                    async with session.request(method, url, **kwargs) as response:
                        if response.status == 200:
                            return await response.json()
                        elif response.status == 401 and group_name != "AUTH":
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
                    if attempt < max_retries - 1:
                        backoff_time = 2 ** attempt
                        print(f"⚠️ API 통신 예외 요격 ({e}). {backoff_time}초 지수 백오프 후 재시도...")
                        await asyncio.sleep(backoff_time)
                        continue
                    raise TimeoutError(f"최대 재시도 횟수 초과 즉사: {e}")

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

    async def token_renewal_loop(self):
        while True:
            await asyncio.sleep(43200)
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

    async def is_market_open(self) -> tuple[bool, datetime]:
        if not self.token:
            await self.authenticate()
            
        if self._calendar_lock is None:
            self._calendar_lock = asyncio.Lock()
            
        async with self._calendar_lock:
            now_kst = datetime.now(ZoneInfo('Asia/Seoul'))
            est_today_str = datetime.now(ZoneInfo('America/New_York')).strftime("%Y-%m-%d")
            
            if self._calendar_cache.get("date") != est_today_str:
                try:
                    endpoint = f"/api/v1/market-calendar/US?date={est_today_str}"
                    data = await self._request("GET", endpoint, "MARKET_INFO", headers=self._get_headers())
                    result_data = data.get("result", {})
                    
                    sessions = []
                    for day_key in ["previousBusinessDay", "today", "nextBusinessDay"]:
                        day_cal = result_data.get(day_key, {})
                        if not day_cal:
                            continue
                        for session_name in ["dayMarket", "preMarket", "regularMarket", "afterMarket"]:
                            session_data = day_cal.get(session_name)
                            if session_data:
                                start_dt = datetime.fromisoformat(session_data["startTime"])
                                end_dt = datetime.fromisoformat(session_data["endTime"])
                                sessions.append((start_dt, end_dt))
                    
                    self._calendar_cache = {"date": est_today_str, "sessions": sessions}
                    print(f"📅 토스증권 US 시장 3영업일 달력 병합 완료: {est_today_str} (총 {len(sessions)}개 세션 확보)")
                except Exception as e:
                    cached_sessions = self._calendar_cache.get("sessions", [])
                    if cached_sessions:
                        print(f"⚠️ [달력 API] 통신 지연. 인메모리 캐시 기반 Dual Fallback 가동: {e}")
                    else:
                        print(f"🚨 [달력 API] 통신 붕괴 및 캐시 부재. Fail-Open(조건부 허용) 섀도 모드 가동: {e}")
                        return True, None
                    
            cached_sessions = self._calendar_cache.get("sessions", [])
            
            if not cached_sessions:
                return False, None
                
            for start_dt, end_dt in cached_sessions:
                if start_dt <= now_kst <= end_dt:
                    return True, end_dt
                    
            return False, None

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

    async def get_soxl_holdings_detail(self) -> dict:
        if not self.account_seq:
            await self.fetch_account_seq()
            
        data = await self._request("GET", "/api/v1/holdings?symbol=SOXL", "ASSET", headers=self._get_headers(requires_account=True))
        items = data.get("result", {}).get("items", [])
        
        if not items:
            return {"qty": 0.0, "avg_price": 0.0, "profit_rate": 0.0, "profit_usd": 0.0}
            
        item = items[0]
        return {
            "qty": float(item.get("quantity", 0.0)),
            "avg_price": float(item.get("averagePurchasePrice", 0.0)),
            "profit_rate": float(item.get("profitLoss", {}).get("rate", 0.0)),
            "profit_usd": float(item.get("profitLoss", {}).get("amount", 0.0))
        }

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

    async def get_orders(self, status: str, symbol: str = None) -> list:
        if not self.account_seq:
            await self.fetch_account_seq()
            
        endpoint = f"/api/v1/orders?status={status}"
        if symbol:
            endpoint += f"&symbol={symbol}"
            
        data = await self._request("GET", endpoint, "ORDER_HISTORY", headers=self._get_headers(requires_account=True))
        return data.get("result", {}).get("orders", [])

    async def create_order(self, symbol: str, side: str, order_type: str, quantity: float, price: float = None, time_in_force: str = "DAY", client_order_id: str = None) -> dict:
        if not self.account_seq:
            await self.fetch_account_seq()
            
        payload = {
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "timeInForce": time_in_force
        }
        
        payload["quantity"] = str(int(math.floor(quantity)))
        
        if order_type == "LIMIT" and price is not None:
            payload["price"] = str(price)
            
        if client_order_id:
            payload["clientOrderId"] = client_order_id
            
        data = await self._request("POST", "/api/v1/orders", "ORDER", headers=self._get_headers(requires_account=True), json=payload)
        return data.get("result", {})

    async def cancel_order(self, order_id: str) -> dict:
        if not self.account_seq:
            await self.fetch_account_seq()
            
        endpoint = f"/api/v1/orders/{order_id}/cancel"
        data = await self._request("POST", endpoint, "ORDER", headers=self._get_headers(requires_account=True))
        return data.get("result", {})
