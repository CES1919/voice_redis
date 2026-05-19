#!/usr/bin/env python3
"""
B 镜像示例：从 asr_events 读取 → NLU 处理 → 写入 processed_events → ACK

关键：ACK 顺序必须是「处理 → 写输出 → ACK」，
     如果先 ACK 再写输出，中间崩溃会丢链路数据。

用法:
    pip install redis
    python consume_asr_write_processed.py

环境变量:
    REDIS_HOST         (默认 127.0.0.1)
    REDIS_PORT         (默认 6379)
    REDIS_USERNAME     (默认 service_b)
    REDIS_PASSWORD     (默认 change_me_b)
    REDIS_STREAM_IN    (默认 asr_events)
    REDIS_GROUP_IN     (默认 b_processors)
    REDIS_CONSUMER_NAME(默认 b-1)
    REDIS_STREAM_OUT   (默认 processed_events)
    REDIS_MAXLEN       (默认 50000)
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
        username=os.getenv("REDIS_USERNAME", "service_b"),
        password=os.getenv("REDIS_PASSWORD", "change_me_b"),
        decode_responses=True,
    )


def nlu_process(event: dict) -> dict:
    """模拟 NLU 处理：从 text 中提取标签"""
    now = datetime.now(timezone(timedelta(hours=8)))
    date_str = now.strftime("%Y%m%d")
    ts = now.isoformat()

    text = event.get("text", "")
    label = {}
    if "高速" in text:
        label["道路"] = "高速"
    if "晴" in text:
        label["天气"] = "晴"
    if "雨" in text:
        label["天气"] = "雨"

    return {
        "id": event["id"].replace("asr_", "nlu_", 1),
        "timestamp": ts,
        "label": label,
        "wav_path": event.get("wav_path", ""),
        "sample_rate": event.get("sample_rate", 16000),
        "offset_sec": event.get("offset_sec", 0.0),
        "duration_sec": event.get("duration_sec", 0.0),
        "segment_index": event.get("segment_index", 0),
        "nlu_model": "/models/bert",
    }


def main():
    client = get_redis_client()
    stream_in = os.getenv("REDIS_STREAM_IN", "asr_events")
    group_in = os.getenv("REDIS_GROUP_IN", "b_processors")
    consumer = os.getenv("REDIS_CONSUMER_NAME", "b-1")
    stream_out = os.getenv("REDIS_STREAM_OUT", "processed_events")
    maxlen = int(os.getenv("REDIS_MAXLEN", "50000"))

    # Consumer Group 由 init 容器统一创建，无需手动创建

    print(f"消费者: {group_in}/{consumer}")
    print(f"读取: {stream_in} → 写入: {stream_out}")
    print("等待消息...\n")

    while True:
        # 阻塞读取，超时 5 秒
        messages = client.xreadgroup(
            group_in, consumer, {stream_in: ">"}, count=10, block=5000
        )

        if not messages:
            continue

        for stream_name, entries in messages:
            for msg_id, fields in entries:
                print(f"  收到: {msg_id} -> {json.dumps(fields, ensure_ascii=False)}")

                # 1. 处理
                result = nlu_process(fields)

                # 2. 写输出（先于 ACK）
                out_id = client.xadd(
                    stream_out, result, maxlen=maxlen, approximate=True
                )
                print(f"  写出: {out_id} -> {json.dumps(result, ensure_ascii=False)}")

                # 3. ACK（最后一步）
                client.xack(stream_in, group_in, msg_id)
                print(f"  已确认: {msg_id}\n")


if __name__ == "__main__":
    main()
