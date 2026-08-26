import asyncio
import aiohttp
import os
import html
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# 자격증명 및 시스템 상수 락온
TOSS_CLIENT_ID = os.getenv("TOSS_CLIENT_ID", "tsck_live_QogVVVdZPhhg3sbTo5T7hB")
TOSS_CLIENT_SECRET = os.getenv("TOSS_CLIENT_SECRET", "tssk_live_vvWo029zWfkoNLKscu8QbEoM7enrcOeNpCg98sHTeVYD")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7850532415:AAGiZg_gbUDXjBA7QOnvTbSPXii5WwFQ7wQ")
ADMIN_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "796232854"))

# 제1헌법 - 동기 I/O 비동기 격리 및 Rate Limit 중앙 통제소
class GlobalThrottle:
    _locks = {}
    
    @classmethod
    async def wait_api_sync(cls, group_name: str):
        if group_name not in cls._locks:
            cls._locks[group_name] = asyncio.Lock()
        async with cls._locks[group_name]:
            await asyncio.sleep(1.5)

# 비동기 토스증권 API 클라이언트
class TossApiClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://openapi.tossinvest.com"
        self.token = None
        self.account_seq = None

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
                        retry_after = int(response.headers.get("Retry-After", 3))
                        print(f"⚠️ 429 Rate Limit 타격. {retry_after}초 지수 백오프 대기...")
                        await asyncio.sleep(retry_after)
                        continue
                    else:
                        error_text = await response.text()
                        raise ConnectionError(f"API 통신 붕괴 ({response.status}): {error_text}")
            raise TimeoutError("최대 재시도 횟수 초과로 통신이 즉사했습니다.")

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

# 텔레그램 관제탑 라우터 및 봇 초기화
router = Router()
api_client = TossApiClient(client_id=TOSS_CLIENT_ID, client_secret=TOSS_CLIENT_SECRET)

# 텔레그램 시작 및 메인 메뉴 렌더링
@router.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 잔고 및 SOXL 스캔", callback_data="scan_asset")]
    ])
    
    welcome_text = (
        "🤖 <b>승승장군 퀀트 관제탑 가동</b>\n\n"
        "▫️ 시스템: Toss Securities V14 / V-REV\n"
        "▫️ 상태: Online 및 API 대기 중\n\n"
        "원하시는 명령을 선택하십시오."
    )
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")

# NEW: 깃허브 원장 강제 동기화 및 봇 자가 부활 모듈 (Case 15)
@router.message(Command("update"))
async def cmd_update(message: types.Message):
    # 관제탑 하드코딩 락온 방어 (Case 11)
    if message.from_user.id != ADMIN_CHAT_ID:
        return

    await message.answer("⏳ <b>깃허브 원장 동기화 및 업데이트 진행 중...</b>", parse_mode="HTML")
    
    try:
        # 비동기 쉘 서브프로세스 격발 (동기 블로킹 원천 차단)
        process = await asyncio.create_subprocess_shell(
            "git pull origin main",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        out_text = stdout.decode('utf-8').strip()
        err_text = stderr.decode('utf-8').strip()
        
        # 특수기호 HTML 파서 붕괴 사수 (Case 26)
        safe_out = html.escape(out_text) if out_text else "출력 없음"
        safe_err = html.escape(err_text) if err_text else "에러 없음"
        
        result_msg = (
            f"🔄 <b>업데이트 타격 결과</b>\n\n"
            f"▫️ <b>STDOUT</b>:\n<pre>{safe_out}</pre>\n\n"
            f"▫️ <b>STDERR</b>:\n<pre>{safe_err}</pre>"
        )
        await message.answer(result_msg, parse_mode="HTML")
        
        # 플러그인 업데이트 시 파이썬 하드 킬 격발로 systemd 부활 유도 (Case 15)
        if "Already up to date." not in out_text:
            await message.answer("⚠️ <b>시스템 코어 변경 팩트 감지. 데몬을 즉시 재가동(Restart)합니다.</b>", parse_mode="HTML")
            await asyncio.sleep(1) # 텔레그램 메시지 타전 보장을 위한 최소 지연
            os._exit(0)
            
    except Exception as e:
        safe_error = html.escape(str(e))
        await message.answer(f"🚨 <b>업데이트 붕괴 감지</b>:\n<pre>{safe_error}</pre>", parse_mode="HTML")

# 인라인 버튼 콜백 수신 및 팩트 렌더링
@router.callback_query(F.data == "scan_asset")
async def process_scan_callback(callback_query: types.CallbackQuery):
    if callback_query.from_user.id != ADMIN_CHAT_ID:
        return

    await callback_query.message.edit_text("⏳ <b>토스증권 API 원장 동기화 중...</b>", parse_mode="HTML")
    
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
            [InlineKeyboardButton(text="🔄 다시 스캔하기", callback_data="scan_asset")]
        ])
        
        await callback_query.message.edit_text(result_text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        error_msg = html.escape(str(e))
        await callback_query.message.edit_text(f"🚨 <b>시스템 붕괴 감지</b>\n\n▫️ {error_msg}", parse_mode="HTML")

# 시스템 심장부 및 비동기 데몬 격발
async def main():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    
    print("시스템 코어 로드 완료. 텔레그램 롱 폴링(Long-Polling) 개시...")
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("관제탑 셧다운 완료.")
