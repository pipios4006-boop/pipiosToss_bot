# =====================================================================
# 파일명: ha_engine.py
# 목적: 1분봉 데이터 수신 및 3분봉 하이킨 아시(Heikin-Ashi) 100% 벡터화 연산
# =====================================================================

import asyncio
import aiohttp
import os
import pandas as pd
import numpy as np
from zoneinfo import ZoneInfo

# 자격증명 및 시스템 상수 락온
TOSS_CLIENT_ID = os.getenv("TOSS_CLIENT_ID", "tsck_live_QogVVVdZPhhg3sbTo5T7hB")
TOSS_CLIENT_SECRET = os.getenv("TOSS_CLIENT_SECRET", "tssk_live_vvWo029zWfkoNLKscu8QbEoM7enrcOeNpCg98sHTeVYD")

# 제1헌법 - 비동기 격리 및 Rate Limit 중앙 통제소
class GlobalThrottle:
    _locks = {}
    
    @classmethod
    async def wait_api_sync(cls, group_name: str):
        if group_name not in cls._locks:
            cls._locks[group_name] = asyncio.Lock()
        async with cls._locks[group_name]:
            await asyncio.sleep(1.5)

# 토스증권 API 클라이언트 (캔들 조회 확장)
class TossApiClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://openapi.tossinvest.com"
        self.token = None

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
                        print(f"⚠️ 429 Rate Limit 타격. {retry_after}초 백오프 대기...")
                        await asyncio.sleep(retry_after)
                        continue
                    else:
                        error_text = await response.text()
                        raise ConnectionError(f"API 통신 붕괴 ({response.status}): {error_text}")
            raise TimeoutError("최대 재시도 횟수 초과 즉사.")

    async def authenticate(self) -> None:
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        data = await self._request("POST", "/oauth2/token", "AUTH", data=payload)
        self.token = data.get("access_token")

    def _get_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    # NEW: 1분봉 캔들 조회 API 타격
    async def get_1m_candles(self, symbol: str, count: int = 200) -> list:
        if not self.token:
            await self.authenticate()
            
        endpoint = f"/api/v1/candles?symbol={symbol}&interval=1m&count={count}"
        data = await self._request("GET", endpoint, "MARKET_DATA_CHART", headers=self._get_headers())
        
        # 빈 배열 결측 방어 (Case 03)
        return data.get("result", {}).get("candles", [])

# NEW: 3분봉 하이킨 아시 벡터화 엔진
class HeikinAshiEngine:
    @staticmethod
    def calculate_3m_ha(candles_json: list) -> pd.DataFrame:
        if not candles_json:
            return pd.DataFrame()
            
        # 1. 원시 데이터프레임 생성 및 타입 락온
        df = pd.DataFrame(candles_json)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # 2. 타임존 락온 (제3헌법: KST 파싱 후 EST 강제 변환)
        df['timestamp'] = df['timestamp'].dt.tz_convert(ZoneInfo('America/New_York'))
        df.set_index('timestamp', inplace=True)
        
        # float 연산 정밀도 확보를 위한 강제 형변환 (Case 05)
        for col in ['openPrice', 'highPrice', 'lowPrice', 'closePrice', 'volume']:
            df[col] = df[col].astype(float)
            
        # 3. 3분봉 리샘플링 및 결측치 섀도우 쉴드 (Case 35)
        # label='left', closed='left' 지정으로 09:30 EST부터 3분 단위 정확한 정렬 강제
        df_3m = df.resample('3min', label='left', closed='left').agg({
            'openPrice': 'first',
            'highPrice': 'max',
            'lowPrice': 'min',
            'closePrice': 'last',
            'volume': 'sum'
        }).ffill() # 거래량 없는 구간은 이전 종가로 메움
        
        # 4. 하이킨 아시 100% 벡터화 연산 (루프 영구 소각)
        ha_df = pd.DataFrame(index=df_3m.index)
        
        # HA Close = (O + H + L + C) / 4
        ha_df['HA_Close'] = (df_3m['openPrice'] + df_3m['highPrice'] + df_3m['lowPrice'] + df_3m['closePrice']) / 4.0
        
        # HA Open 수학적 벡터화 (EMA 트릭)
        shifted_ha_close = ha_df['HA_Close'].shift(1)
        # 첫 캔들의 HA_Open 앵커링 = (Open[0] + Close[0]) / 2
        shifted_ha_close.iloc[0] = (df_3m['openPrice'].iloc[0] + df_3m['closePrice'].iloc[0]) / 2.0
        # alpha=0.5 EMA를 통한 재귀 연산 치환
        ha_df['HA_Open'] = shifted_ha_close.ewm(alpha=0.5, adjust=False).mean()
        
        # HA High / Low (결측 방어를 위해 concat 후 연산)
        ha_df['HA_High'] = pd.concat([df_3m['highPrice'], ha_df['HA_Open'], ha_df['HA_Close']], axis=1).max(axis=1)
        ha_df['HA_Low'] = pd.concat([df_3m['lowPrice'], ha_df['HA_Open'], ha_df['HA_Close']], axis=1).min(axis=1)
        ha_df['Volume'] = df_3m['volume']
        
        # 오름차순 정렬 팩트 보장
        return ha_df.sort_index(ascending=True)

# 테스트용 로컬 심장부 격발
async def main():
    api_client = TossApiClient(client_id=TOSS_CLIENT_ID, client_secret=TOSS_CLIENT_SECRET)
    
    print("⏳ 토스증권 1분봉 원장 수신 중...")
    candles_json = await api_client.get_1m_candles("SOXL", count=200)
    
    print("⏳ 하이킨 아시 벡터화 엔진 가동 중...")
    ha_df = HeikinAshiEngine.calculate_3m_ha(candles_json)
    
    if not ha_df.empty:
        print("✅ 3분봉 하이킨 아시 렌더링 완료 (최근 5개 캔들):")
        print(ha_df.tail(5))
    else:
        print("🚨 캔들 데이터 붕괴 감지 (빈 배열).")

if __name__ == "__main__":
    asyncio.run(main())
