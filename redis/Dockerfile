FROM redis:7-alpine

# 复制 Redis 服务器配置
COPY redis.conf /usr/local/etc/redis/redis.conf

# 复制 ACL 模板到非卷路径（密码占位符，运行时由 start_redis.sh 替换）
COPY redis-acl.txt /usr/local/etc/redis/users.acl.template

# 复制启动脚本和初始化脚本
COPY start_redis.sh /usr/local/bin/start_redis.sh
COPY init_streams.sh /usr/local/bin/init_streams.sh
RUN chmod +x /usr/local/bin/start_redis.sh /usr/local/bin/init_streams.sh

# 创建 ACL 和数据目录
RUN mkdir -p /usr/local/etc/redis/acl /data

# Redis 服务器默认端口
EXPOSE 6379

# 数据目录为 volume（持久化），ACL 目录不需要卷（每次启动重新生成）
VOLUME ["/data"]

# 使用启动脚本作为 entrypoint（生成 ACL + 启动 Redis）
ENTRYPOINT ["/usr/local/bin/start_redis.sh"]
