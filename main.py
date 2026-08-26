import asyncio
import aiohttp
import os
import html
from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# NEW: 자격증명 및 시스템 상수 락온
TOSS_CLIENT_ID = os.getenv("TOSS_CLIENT_ID", "tsck_live_QogVVVdZPhhg3sbTo5T7hB")
TOSS_CLIENT_SECRET = os.getenv("TOSS_CLIENT_SECRET", "tssk_live_vvWo029zWfkoNLKscu8QbEoM7enrcOeNpCg98sHTeVYD")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7850532415:AAGiZg_gbUDXjBA7QOnvTbSPXii5WwFQ7wQ")
ADMIN_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "796232854"))

# NEW: 제1헌법 - 동기 I/O 비동기 격리 및 Rate Limit 중앙 통제소
class GlobalThrottle:
    _locks = {}
    
    @classmethod
    async def wait_api_sync(cls, group_name: str):
        # NEW: Rate Limits Group별 독립 통제 (Case 31)
        if group_name not in cls._locks:
            cls._locks[group_name] = asyncio.Lock()
        async with cls._locks[group_name]:
            # NEW: 429 밴 방어를 위한 루프 내 강제 지연 (Case 43)
            await asyncio.sleep(1.5)

# NEW: 비동기 토스증권 API 클라이언트
class TossApiClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://openapi.tossinvest.com"
        self.token = None
        self.account_seq = None

    # NEW: 429 백오프 및 중앙 통제소가 결속된 공통 Request 엔진 (Case 31, Case 32)
    async def _request(self, method: str, endpoint: str, group_name: str, **kwargs) -> dict:
        url = f"{self.base_url}{endpoint}"
        max_retries = 3
        
        async with aiohttp.ClientSession() as session:
            for attempt in range(max_retries):
                await GlobalThrottle.wait_api_sync(group_name)
                
                async with session.request(method, url, **kwargs) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 429:
                        # NEW: 429 에러 시 Retry-After 헤더 파싱 및 무중단 Fallback 강제
                        retry_after = int(response.headers.get("Retry-After", 3))
                        print(f"⚠️ 429 Rate Limit 타격. {retry_after}초 지수 백오프 대기...")
                        await asyncio.sleep(retry_after)
                        continue
                    else:
                        error_text = await response.text()
                        raise ConnectionError(f"API 통신 붕괴 ({response.status}): {error_text}")
            raise TimeoutError("최대 재시도 횟수 초과로 통신이 즉사했습니다.")

    # NEW: OAuth2 액세스 토큰 발급
    async def authenticate(self) -> None:
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        data = await self._request("POST", "/oauth2/token", "AUTH", data=payload)
        self.token = data.get("access_token")

    def _get_headers(self, requires_account: bool = False) -> dict:
        headers = {"Authorization": f"Bearer {self.token}"}
        if requires_account:
            if not self.account_seq:
                raise ValueError("accountSeq가 누락되었습니다.")
            headers["X-Tossinvest-Account"] = str(self.account_seq)
        return headers

    # NEW: 종합매매(BROKERAGE) 계좌 식별자 확보
    async def fetch_account_seq(self) -> None:
        if not self.token:
            await self.authenticate()
            
        data = await self._request("GET", "/api/v1/accounts", "ACCOUNT", headers=self._get_headers())
        accounts = data.get("result", [])
        
        # NEW: 결측치 방어 및 단락 평가 (Case 24)
        if not accounts:
            raise IndexError("조회 가능한 계좌가 없습니다.")
        
        brokerage_account = next((acc for acc in accounts if acc.get("accountType") == "BROKERAGE"), None)
        if brokerage_account:
            self.account_seq = brokerage_account.get("accountSeq")
        else:
            raise ValueError("종합매매 계좌를 찾을 수 없습니다.")

    # NEW: USD 매수가능금액 조회
    async def get_usd_buying_power(self) -> float:
        if not self.account_seq:
            await self.fetch_account_seq()
            
        data = await self._request("GET", "/api/v1/buying-power?currency=USD", "ORDER_INFO", headers=self._get_headers(requires_account=True))
        result = data.get("result", {})
        
        # NEW: 결측치 0.0 강제 형변환 (Case 05)
        raw_bp = result.get("cashBuyingPower")
        return float(raw_bp) if raw_bp is not None else 0.0

    # NEW: SOXL 보유 수량 조회
    async def get_soxl_holdings(self) -> int:
        if not self.account_seq:
            await self.fetch_account_seq()
            
        data = await self._request("GET", "/api/v1/holdings?symbol=SOXL", "ASSET", headers=self._get_headers(requires_account=True))
        result = data.get("result", {})
        
        # NEW: 빈 배열 응답(0주) 시 IndexError 100% 방어 (Case 03)
        items = result.get("items", [])
        if not items:
            return 0
            
        soxl_item = next((item for item in items if item.get("symbol") == "SOXL"), None)
        if not soxl_item:
            return 0
            
        # NEW: 정수형 락온 (Case 60)
        raw_qty = soxl_item.get("quantity")
        return int(float(raw_qty)) if raw_qty is not None else 0

# NEW: 텔레그램 관제탑 라우터 및 봇 초기화
router = Router()
api_client = TossApiClient(client_id=TOSS_CLIENT_ID, client_secret=TOSS_CLIENT_SECRET)

# NEW: 텔레그램 시작 및 메인 메뉴 렌더링
@router.message(Command("start"))
async def cmd_start(message: types.Message):
    # NEW: 관제탑 하드코딩 락온 (외부 접근 전면 차단)
    if message.from_user.id != ADMIN_CHAT_ID:
        return
        
    # NEW: 인라인 키보드 UI 구축
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 잔고 및 SOXL 스캔", callback_data="scan_asset")]
    ])
    
    welcome_text = (
        "🤖 <b>승승장군 퀀트 관제탑 가동</b>\n\n"
        "▫️ 시스템: Toss Securities V14 / V-REV\n"
        "▫️ 상태: Online 및 API 대기 중\n\n"
        "원하시는 명령을 선택하십시오."
    )
    # NEW: 파서 붕괴 사수 및 HTML 전송
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")

# NEW: 인라인 버튼 콜백 수신 및 팩트 렌더링
@router.callback_query(F.data == "scan_asset")
async def process_scan_callback(callback_query: types.CallbackQuery):
    if callback_query.from_user.id != ADMIN_CHAT_ID:
        return

    # NEW: UI 밀림 방지를 위한 처리 중 메시지 제자리 갱신 (Case 38)
    await callback_query.message.edit_text("⏳ <b>토스증권 API 원장 동기화 중...</b>", parse_mode="HTML")
    
    try:
        usd_bp = await api_client.get_usd_buying_power()
        soxl_qty = await api_client.get_soxl_holdings()
        
        # NEW: 논리 시계열 EST 100% 락온 (제3헌법)
        est_now = datetime.now(ZoneInfo('America/New_York')).strftime("%Y-%m-%d %H:%M:%S")
        
        # NEW: 특수기호 파서 붕괴 방어용 html.escape 적용 (Case 26)
        safe_est = html.escape(est_now)
        
        result_text = (
            f"📊 <b>계좌 자산 스캔 완료</b>\n\n"
            f"🔹 <b>기준 시각</b>: {safe_est} EST\n"
            f"🔹 <b>매수 가능 달러</b>: ${usd_bp:,.2f}\n"
            f"🔹 <b>SOXL 보유 수량</b>: {soxl_qty}주\n"
        )
        
        # 스캔 완료 후 원래 메뉴 버튼 복구
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 다시 스캔하기", callback_data="scan_asset")]
        ])
        
        await callback_query.message.edit_text(result_text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        error_msg = html.escape(str(e))
        await callback_query.message.edit_text(f"🚨 <b>시스템 붕괴 감지</b>\n\n▫️ {error_msg}", parse_mode="HTML")

# NEW: 시스템 심장부 및 비동기 데몬 격발
async def main():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    
    print("시스템 코어 로드 완료. 텔레그램 롱 폴링(Long-Polling) 개시...")
    
    # NEW: 텔레그램 서버 구동 (기존 단발성 스캔 로직 소각 및 폴링 루프 주입)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("관제탑 셧다운 완료.")
