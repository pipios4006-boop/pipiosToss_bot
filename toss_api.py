# =====================================================================
# FILE: toss_api.py
# 목적: 토스증권 Open API 통신 엣지 케이스 방어 및 중앙 통제소 가동
# =====================================================================

import asyncio
import aiohttp
import time
import html
import json
from datetime import datetime
from zoneinfo import ZoneInfo

class GlobalThrottle:
    _api_lock = asyncio.Lock()
    _file_locks = {}
    _last_api_time = 0.0

    @classmethod
    async def wait_api_sync(cls):
        async with cls._api_lock:
            now = time.time()
            elapsed = now - cls._last_api_time
            if elapsed < 0.15:  
                await asyncio.sleep(0.15 - elapsed)
            cls._last_api_time = time.time()

    @classmethod
    def get_file_lock(cls, filepath: str):
        if filepath not in cls._file_locks:
            cls._file_locks[filepath] = asyncio.Lock()
        return cls._file_locks[filepath]

class TossApiClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://openapi.tossinvest.com"
        self.token = None
        self.account_seq = None
        self._calendar_cache = None
        self._calendar_cache_time = 0.0
        # NEW: 401 레이스 컨디션 붕괴 방어용 인증 전용 뮤텍스 락온
        self._auth_lock = asyncio.Lock()

    async def _request(self, method: str, endpoint: str, rate_limit_group: str, headers: dict = None, json_data: dict = None, timeout: float = 10.0):
        url = f"{self.base_url}{endpoint}"
        
        # MODIFIED: 헤더 객체 오염 방지 및 401 치유 시 동적 재주입을 위한 얕은 복사
        req_headers = dict(headers) if headers else {}
        
        for attempt in range(3):
            await GlobalThrottle.wait_api_sync()
            
            # NEW: 매 시도마다 시스템 최신 토큰을 동적으로 주입 (401 재발사 요격망)
            if self.token:
                req_headers["Authorization"] = f"Bearer {self.token}"

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.request(method, url, headers=req_headers, json=json_data, timeout=timeout) as resp:
                        
                        # NEW: 401 Unauthorized 레이스 컨디션 방어 및 3단 자동 치유
                        if resp.status == 401:
                            if attempt == 2:
                                raise Exception("API HTTP 401: Unauthorized (Max retries exceeded)")
                            
                            async with self._auth_lock:
                                # 다른 비동기 태스크가 이미 토큰을 갱신했는지 검증하여 중복 발급 차단
                                failed_auth = req_headers.get("Authorization")
                                current_system_auth = f"Bearer {self.token}" if self.token else None
                                if failed_auth == current_system_auth or not failed_auth:
                                    await self._do_authenticate()
                            continue
                            
                        # MODIFIED: 429 한도 초과 시 남은 시도 횟수 소진 예외 처리 명시
                        if resp.status == 429:
                            if attempt == 2:
                                raise Exception("API HTTP 429: Rate Limit Exceeded (Max retries)")
                            retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
                            await asyncio.sleep(retry_after)
                            continue
                            
                        if resp.status >= 400:
                            err_text = await resp.text()
                            try:
                                err_json = json.loads(err_text)
                                err_msg = err_json.get("error", {}).get("message", err_text)
                                safe_err = html.escape(str(err_msg))
                            except Exception:
                                safe_err = html.escape(err_text)
                            raise Exception(f"API HTTP {resp.status}: {safe_err}")
                        
                        return await resp.json()
            except asyncio.TimeoutError:
                if attempt == 2: raise Exception("API Timeout")
                await asyncio.sleep(2 ** attempt)
            except Exception as e:
                # 401, 429 방어 로직은 위에서 continue 하므로 여기 도달하는 것은 통신 단절 등 치명적 에러임
                if attempt == 2: raise e
                await asyncio.sleep(2 ** attempt)

    def _get_headers(self, requires_account: bool = False) -> dict:
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if requires_account and self.account_seq:
            headers["X-Tossinvest-Account"] = str(self.account_seq)
        return headers

    # MODIFIED: 인증 뮤텍스 락온 적용 및 실제 발급 로직 분리
    async def authenticate(self):
        async with self._auth_lock:
            await self._do_authenticate()

    async def _do_authenticate(self):
        url = f"{self.base_url}/oauth2/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        await GlobalThrottle.wait_api_sync()
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=payload, timeout=10.0) as resp:
                data = await resp.json()
                self.token = data.get("access_token")

    async def token_renewal_loop(self):
        while True:
            try:
                # MODIFIED: 기동 직후 2중 발급으로 인한 토큰 증발(Amnesia) 원천 방어 (전진 배치)
                await asyncio.sleep(40000)
                await self.authenticate()
            except Exception:
                await asyncio.sleep(60)

    async def fetch_account_seq(self):
        if not self.token: await self.authenticate()
        data = await self._request("GET", "/api/v1/accounts", "ACCOUNT", headers=self._get_headers())
        accounts = data.get("result", [])
        for acc in accounts:
            if acc.get("accountType") == "BROKERAGE":
                self.account_seq = acc.get("accountSeq")
                break

    async def get_1m_candles_pagination(self, symbol: str, count: int = 200, before: str = None) -> dict:
        if not self.token: await self.authenticate()
        endpoint = f"/api/v1/candles?symbol={symbol}&interval=1m&count={count}"
        if before:
            endpoint += f"&before={before.replace('+', '%2B')}"
        data = await self._request("GET", endpoint, "MARKET_DATA_CHART", headers=self._get_headers())
        return data.get("result", {})

    async def get_symbol_holdings_detail(self, symbol: str) -> dict:
        if not self.account_seq: await self.fetch_account_seq()
        data = await self._request("GET", f"/api/v1/holdings?symbol={symbol}", "ASSET", headers=self._get_headers(requires_account=True))
        items = data.get("result", {}).get("items", [])
        if not items:
            return {"qty": 0.0, "avg_price": 0.0, "profit_rate": 0.0, "profit_usd": 0.0}
        item = items[0]
        
        qty_raw = item.get("quantity")
        avg_price_raw = item.get("averagePurchasePrice")
        return {
            "qty": float(qty_raw) if qty_raw is not None else 0.0,
            "avg_price": float(avg_price_raw) if avg_price_raw is not None else 0.0,
            "profit_rate": float(item.get("profitLoss", {}).get("rate") or 0.0),
            "profit_usd": float(item.get("profitLoss", {}).get("amount") or 0.0)
        }

    async def get_usd_buying_power(self) -> float:
        if not self.account_seq: await self.fetch_account_seq()
        data = await self._request("GET", "/api/v1/buying-power?currency=USD", "ORDER_INFO", headers=self._get_headers(requires_account=True))
        bp_raw = data.get("result", {}).get("cashBuyingPower")
        return float(bp_raw) if bp_raw is not None else 0.0

    async def is_market_open(self) -> tuple[bool, datetime, str, datetime]:
        now_ts = time.time()
        if now_ts - self._calendar_cache_time < 60.0 and self._calendar_cache:
            return self._calendar_cache

        if not self.token: await self.authenticate()
        now_est = datetime.now(ZoneInfo('America/New_York'))
        est_today_str = now_est.strftime("%Y-%m-%d")
        endpoint = f"/api/v1/market-calendar/US?date={est_today_str}"
        data = await self._request("GET", endpoint, "MARKET_INFO", headers=self._get_headers())
        today_data = data.get("result", {}).get("today", {})
        
        for session_name in ["dayMarket", "preMarket", "regularMarket", "afterMarket"]:
            session = today_data.get(session_name)
            if session:
                start = datetime.fromisoformat(session["startTime"]).astimezone(ZoneInfo('America/New_York'))
                end = datetime.fromisoformat(session["endTime"]).astimezone(ZoneInfo('America/New_York'))
                if start <= now_est <= end:
                    self._calendar_cache = (True, end, session_name, start)
                    self._calendar_cache_time = now_ts
                    return self._calendar_cache
                    
        self._calendar_cache = (False, None, "CLOSED", None)
        self._calendar_cache_time = now_ts
        return self._calendar_cache

    async def get_current_price(self, symbol: str) -> float:
        if not self.token: await self.authenticate()
        data = await self._request("GET", f"/api/v1/prices?symbols={symbol}", "MARKET_DATA", headers=self._get_headers())
        result = data.get("result", [])
        if not result: return 0.0
        price_raw = result[0].get("lastPrice")
        return float(price_raw) if price_raw is not None else 0.0

    async def get_orderbook(self, symbol: str) -> dict:
        if not self.token: await self.authenticate()
        data = await self._request("GET", f"/api/v1/orderbook?symbol={symbol}", "MARKET_DATA", headers=self._get_headers())
        return data.get("result", {})

    async def get_orders(self, status: str, symbol: str) -> list:
        if not self.account_seq: await self.fetch_account_seq()
        data = await self._request("GET", f"/api/v1/orders?status={status}&symbol={symbol}", "ORDER_HISTORY", headers=self._get_headers(requires_account=True))
        return data.get("result", {}).get("orders", [])

    async def cancel_order(self, order_id: str):
        if not self.account_seq: await self.fetch_account_seq()
        await self._request("POST", f"/api/v1/orders/{order_id}/cancel", "ORDER", headers=self._get_headers(requires_account=True))

    async def get_order_detail(self, order_id: str) -> dict:
        if not self.account_seq: await self.fetch_account_seq()
        data = await self._request("GET", f"/api/v1/orders/{order_id}", "ORDER_HISTORY", headers=self._get_headers(requires_account=True))
        return data.get("result", {})

    async def create_order(self, symbol: str, side: str, order_type: str, quantity: float, price: str, client_order_id: str) -> dict:
        if not self.account_seq: await self.fetch_account_seq()
        payload = {
            "clientOrderId": client_order_id,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "quantity": str(quantity),
            "price": price,
            "timeInForce": "DAY"
        }
        return await self._request("POST", "/api/v1/orders", "ORDER", headers=self._get_headers(requires_account=True), json_data=payload)

    async def create_conditional_order(self, symbol: str, quantity: int, price: str, client_order_id: str, expire_date: str) -> dict:
        if not self.account_seq: await self.fetch_account_seq()
        payload = {
            "clientOrderId": client_order_id,
            "symbol": symbol,
            "type": "SINGLE",
            "quantity": str(quantity),
            "orderType": "LIMIT",
            "expireDate": expire_date,
            "first": {
                "orderSide": "SELL",
                "triggerPrice": price,
                "orderPrice": price
            }
        }
        return await self._request("POST", "/api/v1/conditional-orders", "CONDITIONAL_ORDER", headers=self._get_headers(requires_account=True), json_data=payload)

    async def cancel_conditional_order(self, cond_order_id: str):
        if not self.account_seq: await self.fetch_account_seq()
        await self._request("DELETE", f"/api/v1/conditional-orders/{cond_order_id}", "CONDITIONAL_ORDER", headers=self._get_headers(requires_account=True))

