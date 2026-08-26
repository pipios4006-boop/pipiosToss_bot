import asyncio
import aiohttp
import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

# NEW: 제1헌법 - 동기 I/O 비동기 격리 및 Rate Limit 중앙 통제소 스켈레톤
class GlobalThrottle:
    _locks = {}
    
    @classmethod
    async def wait_api_sync(cls, group_name: str):
        # NEW: 토스증권 API Rate Limit 그룹별(AUTH, ACCOUNT, ORDER_INFO, ASSET 등) 독립 락온
        if group_name not in cls._locks:
            cls._locks[group_name] = asyncio.Lock()
        async with cls._locks[group_name]:
            # NEW: 429 방어를 위한 폴링 감시 간격 안전 보장 (Case 43)
            await asyncio.sleep(1.5)

# NEW: 비동기 토스증권 API 클라이언트 아키텍처
class TossApiClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://openapi.tossinvest.com"
        self.token = None
        self.account_seq = None

    # NEW: OAuth2 액세스 토큰 발급 및 메모리 캐싱 (Rate Limit: AUTH)
    async def authenticate(self) -> None:
        await GlobalThrottle.wait_api_sync("AUTH")
        url = f"{self.base_url}/oauth2/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        
        # NEW: 비동기 I/O 직접 호출 강제 (Case 06)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    self.token = data.get("access_token")
                else:
                    raise ConnectionError(f"토큰 발급 실패: {await response.text()}")

    # NEW: API 공통 요청 헤더 주입 및 accountSeq 무결성 검증
    def _get_headers(self, requires_account: bool = False) -> dict:
        headers = {"Authorization": f"Bearer {self.token}"}
        if requires_account:
            if not self.account_seq:
                raise ValueError("accountSeq가 없습니다. 시스템 논리 붕괴.")
            headers["X-Tossinvest-Account"] = str(self.account_seq)
        return headers

    # NEW: 종합매매(BROKERAGE) 계좌 식별자 획득 (Rate Limit: ACCOUNT)
    async def fetch_account_seq(self) -> None:
        if not self.token:
            await self.authenticate()
            
        await GlobalThrottle.wait_api_sync("ACCOUNT")
        url = f"{self.base_url}/api/v1/accounts"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self._get_headers()) as response:
                data = await response.json()
                accounts = data.get("result", [])
                
                # NEW: 결측치 방어 및 단락 평가 (Case 24)
                if not accounts:
                    raise IndexError("조회 가능한 계좌가 없습니다.")
                
                brokerage_account = next((acc for acc in accounts if acc.get("accountType") == "BROKERAGE"), None)
                if brokerage_account:
                    self.account_seq = brokerage_account.get("accountSeq")
                else:
                    raise ValueError("종합매매(BROKERAGE) 계좌를 찾을 수 없습니다.")

    # NEW: 매수가능금액(USD) 조회 (Rate Limit: ORDER_INFO)
    async def get_usd_buying_power(self) -> float:
        if not self.account_seq:
            await self.fetch_account_seq()
            
        await GlobalThrottle.wait_api_sync("ORDER_INFO")
        url = f"{self.base_url}/api/v1/buying-power?currency=USD"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self._get_headers(requires_account=True)) as response:
                data = await response.json()
                result = data.get("result", {})
                
                # NEW: 결측치 null 방어를 위한 0.0 강제 형변환 (Case 05)
                raw_bp = result.get("cashBuyingPower")
                if raw_bp is None:
                    return 0.0
                return float(raw_bp)

    # NEW: SOXL 보유 수량 조회 (Rate Limit: ASSET)
    async def get_soxl_holdings(self) -> int:
        if not self.account_seq:
            await self.fetch_account_seq()
            
        await GlobalThrottle.wait_api_sync("ASSET")
        url = f"{self.base_url}/api/v1/holdings?symbol=SOXL"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self._get_headers(requires_account=True)) as response:
                data = await response.json()
                result = data.get("result", {})
                
                # NEW: 빈 배열(items: []) 응답 시 IndexError 100% 사수 및 결측 방어 (Case 03)
                items = result.get("items", [])
                if not items:
                    return 0
                    
                # NEW: 단락 평가를 통한 타겟 심볼 정밀 스캔
                soxl_item = next((item for item in items if item.get("symbol") == "SOXL"), None)
                if not soxl_item:
                    return 0
                    
                # NEW: 토스 API 규격상 LIMIT 주문 수량 정수형(Integer) 락온 (Case 60)
                raw_qty = soxl_item.get("quantity")
                if raw_qty is None:
                    return 0
                return int(float(raw_qty))

# NEW: 단일 파일 격리 테스트 및 실행 관제탑
async def main():
    # 자격증명 시스템 코어 주입
    CLIENT_ID = os.getenv("TOSS_CLIENT_ID", "tsck_live_QogVVVdZPhhg3sbTo5T7hB")
    CLIENT_SECRET = os.getenv("TOSS_CLIENT_SECRET", "tssk_live_vvWo029zWfkoNLKscu8QbEoM7enrcOeNpCg98sHTeVYD")
    
    client = TossApiClient(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
    
    try:
        # 비동기 병렬 I/O 실행 금지 (Rate Limit 붕괴 방어를 위해 순차적 await 강제)
        usd_bp = await client.get_usd_buying_power()
        soxl_qty = await client.get_soxl_holdings()
        
        # NEW: 논리 시계열 오직 미국 동부 시간(EST) 100% 락온 (제3헌법)
        est_now = datetime.now(ZoneInfo('America/New_York')).strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{est_now} EST] 팩트 스캔 완료")
        print(f"USD 매수가능금액: ${usd_bp}")
        print(f"SOXL 보유주식: {soxl_qty}주")
        
    except Exception as e:
        print(f"시스템 붕괴 감지: {e}")

if __name__ == "__main__":
    asyncio.run(main())
