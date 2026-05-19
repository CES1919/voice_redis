#!/usr/bin/env python3
"""
A 镜像示例：向 asr_events Stream 写入 ASR 结果

用法:
    pip install redis
    python publish_asr_event.py

环境变量:
    REDIS_HOST     (默认 127.0.0.1)
    REDIS_PORT     (默认 6379)
    REDIS_USERNAME (默认 service_a)
    REDIS_PASSWORD (默认 change_me_a)
    REDIS_STREAM_OUT (默认 asr_events)
    REDIS_MAXLEN   (默认 50000)
"""

import json
import os
import time
from datetime import datetime, timezone, timedelta

import redis


def get_redis_client() -> redis.Redis:
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "127.0.0.1"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        username=os.getenv("REDIS_USERNAME", "service_a"),
        password=os.getenv("REDIS_PASSWORD", "change_me_a"),
        decode_responses=True,
    )


def build_sample_event(index: int = 1) -> dict:
    now = datetime.now(timezone(timedelta(hours=8)))
    date_str = now.strftime("%Y%m%d")
    ts = now.isoformat()
    session_id = "ab12cd34"
    return {
        "id": f"asr_{date_str}_{session_id}_{index:06d}",
        "timestamp": ts,
        "text": "当前道路为高速，天气晴",
        "wav_path": f"/output/audio/{date_str}_{now.strftime('%H%M%S')}_{session_id}/part_{index:06d}.wav",
        "sample_rate": 16000,
        "offset_sec": 0.0,
        "duration_sec": 2.3,
        "segment_index": index,
        "asr_model": "/models/FunAudioLLM/Fun-ASR-Nano-2512",
    }


def main():
    client = get_redis_client()
    stream = os.getenv("REDIS_STREAM_OUT", "asr_events")
    maxlen = int(os.getenv("REDIS_MAXLEN", "50000"))

    print(f"连接 Redis: {client.connection_pool.connection_kwargs.get('host')}:{client.connection_pool.connection_kwargs.get('port')}")
    print(f"Stream: {stream}, MAXLEN: ~{maxlen}")
    print("输入 JSON 或按回车发送示例数据，输入 q 退出\n")

    index = 1
    while True:
        line = input(f"[{index}] > ").strip()
        if line.lower() == "q":
            break

        if line:
            try:
                event = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"JSON 解析失败: {e}")
                continue
        else:
            event = build_sample_event(index)

        # 将 dict 的每个字段作为 Stream field 写入
        msg_id = client.xadd(stream, event, maxlen=maxlen, approximate=True)
        print(f"  已写入: {msg_id} -> {json.dumps(event, ensure_ascii=False)}")
        index += 1


if __name__ == "__main__":
    main()
