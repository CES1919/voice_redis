#!/bin/sh
set -e

ACL_TEMPLATE="/usr/local/etc/redis/users.acl.template"
ACL_FILE="/usr/local/etc/redis/acl/users.acl"

# ---- 每次启动时从模板生成 ACL 文件 ----
# 密码通过 .env → env_file → 容器环境变量注入
# 这确保 ACL 文件始终与当前密码配置一致，无需外部 init 容器
echo "[entrypoint] 生成 ACL 文件..."
mkdir -p /usr/local/etc/redis/acl

sed \
    -e "s/__REDIS_PASS_HEALTH__/${REDIS_PASS_HEALTH}/g" \
    -e "s/__REDIS_PASS_INIT__/${REDIS_PASS_INIT}/g" \
    -e "s/__REDIS_PASS_A__/${REDIS_PASS_A}/g" \
    -e "s/__REDIS_PASS_B__/${REDIS_PASS_B}/g" \
    -e "s/__REDIS_PASS_ROS2__/${REDIS_PASS_ROS2}/g" \
    "$ACL_TEMPLATE" > "$ACL_FILE"

echo "[entrypoint] 启动 Redis 服务器..."
exec redis-server /usr/local/etc/redis/redis.conf
