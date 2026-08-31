# =====================================================================
# FILE: candle_recorder.py
# 목적: 듀얼 암살자 1분봉 원자적 데이터 영구 누적 파이프라인 (비동기 I/O 격리)
# =====================================================================

import os
import asyncio
import pandas as pd
import numpy as np
from zoneinfo import ZoneInfo

from toss_api import TossApiClient, GlobalThrottle

RAW_DATA_DIR = "/home/pipiosToss/raw_data"

def _sync_upsert_csv(filepath: str, new_df: pd.DataFrame):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    if os.path.exists(filepath):
        try:
            existing_df = pd.read_csv(filepath)
            existing_df['timestamp'] = pd.to_datetime(existing_df['timestamp'], utc=True).dt.tz_convert(ZoneInfo('America/New_York'))
            combined = pd.concat([existing_df, new_df], ignore_index=True)
        except Exception:
            combined = new_df
    else:
        combined = new_df
        
    combined.drop_duplicates(subset=['timestamp'], keep='last', inplace=True)
    combined.sort_values(by='timestamp', inplace=True)
    combined.to_csv(filepath, index=False, date_format='%Y-%m-%dT%H:%M:%S%z')

def _sync_partition_candles(symbol: str, candles_list: list) -> dict:
    if not candles_list:
        return {}
        
    df = pd.DataFrame(candles_list)
    if df.empty:
        return {}
        
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601', utc=True)
    df['timestamp'] = df['timestamp'].dt.tz_convert(ZoneInfo('America/New_York'))
    
    df['logical_time'] = df['timestamp'] - pd.Timedelta(hours=4)
    df['Year'] = df['logical_time'].dt.year.astype(str)
    
    time_int = df['timestamp'].dt.hour * 100 + df['timestamp'].dt.minute
    
    conditions = [
        (time_int >= 400) & (time_int < 930),
        (time_int >= 930) & (time_int < 1600),
        (time_int >= 1600) & (time_int < 1900)
    ]
    choices = ['pre', 'reg', 'aft']
    df['Session'] = np.select(conditions, choices, default='day')
    
    df.drop(columns=['logical_time'], inplace=True)
    
    partitions = {}
    for (year, session), group in df.groupby(['Year', 'Session']):
        filename = f"{symbol}_1m_{year}_{session}.csv"
        partitions[filename] = group
        
    return partitions

async def record_candles_loop(client: TossApiClient, symbol: str):
    while True:
        try:
            data = await client.get_1m_candles_pagination(symbol, count=200)
            candles = data.get("candles", [])
            
            if candles:
                partitions = await asyncio.to_thread(_sync_partition_candles, symbol, candles)
                
                for filename, group_df in partitions.items():
                    filepath = os.path.join(RAW_DATA_DIR, filename)
                    async with GlobalThrottle.get_file_lock(filepath):
                        await asyncio.to_thread(_sync_upsert_csv, filepath, group_df)
                        
        except Exception as e:
            print(f"🚨 [Candle Recorder {symbol}] 수집망 붕괴 방어: {e}", flush=True)
            
        await asyncio.sleep(60.0)

