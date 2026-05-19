# voice_redis — Redis Streams 消息接口层

为 **ASR 服务、NLU 服务、ROS2 节点** 提供基于 Redis Streams 的异步消息通信，使用 ACL 实现最小权限隔离。

## 架构

```
ASR 服务
  │  XADD asr_events
  ▼
Redis Stream: asr_events
  │  XREADGROUP (nlu_processors)
  ▼
NLU 服务
  │  XADD processed_events
  │  XACK asr_events
  ▼
Redis Stream: processed_events
  │  XREADGROUP (ros2_consumers)
  ▼
ROS2 节点
  │  publish ROS2 topic
  │  XACK processed_events
  ▼
ROS2 Topic: /voice_command
```

## 快速启动

### 1. 构建镜像

```bash
docker compose -f compose/docker-compose.redis.yml build
```

构建 `voice-redis:latest` 镜像，包含 redis.conf、ACL 模板、启动脚本和初始化脚本。

### 2. 启动

```bash
docker compose -f compose/docker-compose.redis.yml up -d
```

启动两个容器：

| 容器 | 作用 |
|------|------|
| `redis-streams` | Redis 7 服务器（启动时从模板生成 ACL 文件并加载） |
| `redis-init` | 创建 Consumer Group，运行后自动退出 |

> ACL 密码已配置在 `docker-compose.redis.yml` 的 `environment` 中，无需额外配置文件。

### 3. 验证

```bash
# 检查容器状态
docker compose -f compose/docker-compose.redis.yml ps

# 检查健康状态
docker inspect redis-streams --format='{{.State.Health.Status}}'
# 输出应为 "healthy"

# 检查初始化日志
docker logs redis-init
# 应显示 [init] 初始化完成
```

### 4. 停止

```bash
docker compose -f compose/docker-compose.redis.yml down
# 清除所有数据（包括 Stream 数据）：
docker compose -f compose/docker-compose.redis.yml down -v
```

## 镜像导出与迁移

目标环境只需 Ubuntu 22.04 + Docker。迁移只需两个文件：

```bash
# 导出镜像
docker save voice-redis:latest -o voice-redis.tar

# 传输到目标环境
scp voice-redis.tar compose/docker-compose.redis.yml user@target:/path/

# 在目标环境加载并启动
docker load -i voice-redis.tar
docker compose -f docker-compose.redis.yml up -d
```

> 目标环境只需 `voice-redis.tar` + `docker-compose.redis.yml` 即可运行，无需其他配置文件。如需修改密码，直接编辑 `docker-compose.redis.yml` 中的 `environment` 部分。

## Docker 网络

Redis 容器使用 `shared-redis-net` bridge 网络。其他模块需加入此网络才能访问 Redis。

### Docker 网络模式容器加入方式

```yaml
networks:
  shared-redis-net:
    external: true

services:
  my-service:
    networks:
      - shared-redis-net
    environment:
      - REDIS_HOST=redis-streams   # 容器名，Docker DNS 解析
      - REDIS_PORT=6379
```

### host 网络模式容器

使用 `network_mode: host` 的容器（如 ROS2 节点）无法通过 Docker DNS 访问，应使用：

```yaml
environment:
  - REDIS_HOST=127.0.0.1    # Redis 端口映射到宿主机 127.0.0.1:6379
  - REDIS_PORT=6379
```

## ACL 权限体系

默认用户已禁用，所有访问必须通过 ACL 用户认证。

### 用户一览

| 用户 | 用途 | Key 权限 | 允许的命令 |
|------|------|----------|-----------|
| `healthcheck` | Docker 健康检查 | 无 | `auth`, `ping` |
| `redis_init` | 初始化 / 维护 | `~*`（所有 key） | `+@all`（所有命令） |
| `asr` | ASR 服务 | `%W~asr_events`（只写） | `auth`, `ping`, `xadd` |
| `nlu` | NLU 服务 | `%R~asr_events`（只读）<br>`%W~processed_events`（只写） | `auth`, `ping`, `xgroup`, `xreadgroup`, `xack`, `xadd`, `xpending`, `xautoclaim`, `xinfo` |
| `ros2_reader` | ROS2 节点 | `%R~processed_events`（只读） | `auth`, `ping`, `xgroup`, `xreadgroup`, `xack`, `xpending`, `xautoclaim`, `xinfo` |

### 模块读写权限

| 模块 | 读 | 写 | Stream | Consumer Group |
|------|----|----|--------|---------------|
| ASR 服务 | 否 | 是 | 写 `asr_events` | 无 |
| NLU 服务 | 是 | 是 | 读 `asr_events`，写 `processed_events` | `nlu_processors` |
| ROS2 节点 | 是 | 否 | 读 `processed_events` | `ros2_consumers` |

## Stream 与 Consumer Group

| Stream | 方向 | 生产者 | 消费者 | Consumer Group |
|--------|------|--------|--------|---------------|
| `asr_events` | ASR → NLU | ASR 服务 | NLU 服务 | `nlu_processors` |
| `processed_events` | NLU → ROS | NLU 服务 | ROS2 节点 | `ros2_consumers` |

Consumer Group 由 `redis-init` 容器启动时自动创建，服务代码无需自行创建。

## 环境变量

各模块连接 Redis 时需要配置的环境变量：

| 变量 | ASR 服务 | NLU 服务 | ROS2 |
|------|----------|----------|------|
| `REDIS_HOST` | `redis-streams` | `redis-streams` | `127.0.0.1` |
| `REDIS_PORT` | `6379` | `6379` | `6379` |
| `REDIS_USERNAME` | `asr` | `nlu` | `ros2_reader` |
| `REDIS_PASSWORD` | `docker-compose.redis.yml` 中 `REDIS_PASS_ASR` | `docker-compose.redis.yml` 中 `REDIS_PASS_NLU` | `docker-compose.redis.yml` 中 `REDIS_PASS_ROS2` |
| `REDIS_STREAM_OUT` | `asr_events` | `processed_events` | 无 |
| `REDIS_STREAM_IN` | 无 | `asr_events` | `processed_events` |
| `REDIS_GROUP_IN` | 无 | `nlu_processors` | `ros2_consumers` |
| `REDIS_CONSUMER_NAME` | 无 | `nlu-1` | `ros2-1` |

## 常见问题

### 连接被拒绝 (NOAUTH)

Redis 禁用了默认用户，所有连接必须认证。检查 `REDIS_USERNAME` 和 `REDIS_PASSWORD` 是否与 `docker-compose.redis.yml` 中配置一致。

### 服务无法连接 Redis

- Docker 网络内服务：确认 `REDIS_HOST=redis-streams`，确认已加入 `shared-redis-net`
- host 网络模式服务：确认 `REDIS_HOST=127.0.0.1`
- 检查网络：`docker network inspect shared-redis-net`

### 多个 ROS2 节点使用同一个 consumer name

同一 Consumer Group 下不同实例必须使用不同的 `REDIS_CONSUMER_NAME`（如 `ros2-1`、`ros2-2`），否则消息分配不均或丢失。

## 目录结构

```
voice_redis/
├── .gitignore
├── README.md
├── redis/
│   ├── Dockerfile                # 自定义 Redis 镜像
│   ├── start_redis.sh            # 启动脚本（生成 ACL + 启动服务器）
│   ├── redis.conf                # Redis 服务器配置
│   ├── redis-acl.txt             # ACL 模板（密码占位符，启动时替换）
│   └── init_streams.sh           # 初始化脚本（创建 Consumer Group）
└── compose/
    └── docker-compose.redis.yml  # Docker Compose 配置（含 ACL 密码）
```
