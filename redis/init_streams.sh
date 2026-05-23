#!/bin/sh
set -e

REDIS_HOST="redis-streams"
REDIS_PORT="6379"

echo "[init] 等待 Redis 就绪..."
until redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
    --user redis_init --pass "${REDIS_PASS_INIT}" ping > /dev/null 2>&1; do
    sleep 0.5
done
echo "[init] Redis 已就绪"

CLI="redis-cli -h $REDIS_HOST -p $REDIS_PORT --user redis_init --pass ${REDIS_PASS_INIT}"

# 清理旧 stream 数据，避免残留数据格式不兼容
echo "[init] 清理旧 stream 数据..."
$CLI DEL asr_events 2>/dev/null || true
$CLI DEL processed_events 2>/dev/null || true

echo "[init] 创建 Consumer Group: asr_events / nlu_processors ..."
$CLI XGROUP CREATE asr_events nlu_processors 0 MKSTREAM 2>/dev/null || \
    echo "[init] nlu_processors 已存在，跳过"

echo "[init] 创建 Consumer Group: processed_events / ros2_consumers ..."
$CLI XGROUP CREATE processed_events ros2_consumers 0 MKSTREAM 2>/dev/null || \
    echo "[init] ros2_consumers 已存在，跳过"

echo "[init] 初始化完成"
