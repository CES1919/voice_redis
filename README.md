# voice_redis — Redis Streams 消息接口层

本项目为 **A 服务（ASR）、B 服务（NLU）、ROS2 节点** 三端提供基于 Redis Streams 的异步消息通信，并使用 ACL 实现最小权限隔离。

## 前置条件

- Docker + Docker Compose v2
- Python 3.9+（运行示例脚本时需要）

## 架构总览

```
A 服务 (ASR)
  │  XADD asr_events
  ▼
Redis Stream: asr_events
  │  XREADGROUP (b_processors)
  ▼
B 服务 (NLU)
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

### 1. 配置密码

复制并编辑环境变量文件：

```bash
cp .env.example .env    # 首次使用时（如无 .env.example 则直接编辑 .env）
vim .env
```

`.env` 内容：

```dotenv
# Redis 密码配置
# 避免使用: ' (单引号) \ (反斜杠) $ (美元符号)
# 生产环境请使用强密码，生成方法: openssl rand -base64 32
REDIS_PASS_HEALTH=<健康检查密码>
REDIS_PASS_INIT=<管理员密码>
REDIS_PASS_A=<A 服务密码>
REDIS_PASS_B=<B 服务密码>
REDIS_PASS_ROS2=<ROS2 密码>

# Redis 内存与 Stream 限制
REDIS_MAXMEMORY=512mb
REDIS_MAXLEN=50000
```

> **注意**：`.env` 已在 `.gitignore` 中，不会被提交到版本控制。所有 5 个密码必须设置，否则容器无法正常启动。

### 2. 构建镜像

```bash
docker compose -f compose/docker-compose.redis.yml build
```

这会构建自定义镜像 `voice-redis:latest`，将 redis.conf、ACL 模板、初始化脚本打包进镜像。

### 3. 启动 Redis

```bash
docker compose -f compose/docker-compose.redis.yml up -d
```

这会启动两个容器：

| 容器 | 作用 |
|------|------|
| `redis-streams` | Redis 7 服务器 |
| `redis-init` | 初始化 ACL 用户、Consumer Group，运行后自动退出 |

### 4. 验证启动

```bash
# 检查容器状态（redis-init 应为 Exited(0)，redis-streams 应为 Up）
docker compose -f compose/docker-compose.redis.yml ps

# 检查初始化日志，确认 ACL 加载和 Consumer Group 创建成功
docker logs redis-init

# 检查 Redis 健康状态
docker inspect redis-streams --format='{{.State.Health.Status}}'
# 输出应为 "healthy"
```

如果 `redis-init` 日志显示 `[init] 初始化完成`，说明一切正常。

### 5. 停止 Redis

```bash
docker compose -f compose/docker-compose.redis.yml down
# 如需清除所有数据（包括 ACL 和 Stream 数据）：
docker compose -f compose/docker-compose.redis.yml down -v
```

## 镜像导出与迁移

### 导出镜像

```bash
# 导出为 tar 文件
docker save voice-redis:latest -o voice-redis.tar
```

### 传输到目标环境

```bash
scp voice-redis.tar user@target:/path/
```

### 在目标环境加载并启动

```bash
# 加载镜像
docker load -i voice-redis.tar

# 确认镜像已加载
docker images voice-redis:latest

# 配置 .env（密码必须与源环境一致，否则客户端无法认证）
vim .env

# 启动
docker compose -f compose/docker-compose.redis.yml up -d
```

> **注意**：目标环境只需要 `voice-redis.tar` 镜像文件、`.env` 密码配置和 `compose/docker-compose.redis.yml` 即可运行，不需要源码目录中的 redis.conf、redis-acl.txt 等文件（它们已打包在镜像中）。

## Docker 网络

Redis 容器创建了一个名为 `shared-redis-net` 的 bridge 网络。其他模块的容器需要加入此网络才能访问 Redis。

### 其他模块加入方式

在模块的 `docker-compose.yml` 中添加：

```yaml
networks:
  shared-redis-net:
    external: true

services:
  my-service:
    # ...其他配置...
    networks:
      - shared-redis-net
    environment:
      - REDIS_HOST=redis-streams   # Redis 容器名
      - REDIS_PORT=6379
```

> **关键**：`REDIS_HOST` 必须使用 Redis 容器名 `redis-streams`（Docker 网络内 DNS 解析），而非 IP 地址。

### host 网络模式的容器

使用 `network_mode: host` 的容器（如 ROS2 节点）无法通过 Docker 网络 DNS 访问，应使用：

```yaml
environment:
  - REDIS_HOST=127.0.0.1    # Redis 端口映射到宿主机 127.0.0.1:6379
  - REDIS_PORT=6379
```

## ACL 权限体系

Redis 默认用户已被禁用，所有访问必须通过 ACL 用户认证。每个用户遵循最小权限原则。

### 用户一览

| 用户 | 用途 | Key 权限 | 允许的命令 |
|------|------|----------|-----------|
| `healthcheck` | Docker 健康检查 | 无 | `auth`, `ping` |
| `redis_init` | 初始化 / 维护 | `~*`（所有 key） | `+@all`（所有命令） |
| `service_a` | A 服务（ASR） | `%W~asr_events`（只写） | `auth`, `ping`, `xadd` |
| `service_b` | B 服务（NLU） | `%R~asr_events`（只读）<br>`%W~processed_events`（只写） | `auth`, `ping`, `xgroup`, `xreadgroup`, `xack`, `xadd`, `xpending`, `xautoclaim`, `xinfo` |
| `ros2_reader` | ROS2 节点 | `%R~processed_events`（只读） | `auth`, `ping`, `xgroup`, `xreadgroup`, `xack`, `xpending`, `xautoclaim`, `xinfo` |

### 权限说明

- `%W~key` — 只能写入该 key
- `%R~key` — 只能读取该 key
- `-@all +cmd` — 白名单模式，默认禁用所有命令，仅显式允许的命令可用
- `default` 用户已禁用，任何未认证的连接都会被拒绝

### 模块读写权限

| 模块 | 读 | 写 | Stream | Consumer Group |
|------|----|----|--------|---------------|
| A 服务（ASR） | 否 | 是 | 写 `asr_events` | 无 |
| B 服务（NLU） | 是 | 是 | 读 `asr_events`，写 `processed_events` | `b_processors` |
| ROS2 节点 | 是 | 否 | 读 `processed_events` | `ros2_consumers` |

## Stream 与 Consumer Group

| Stream | 方向 | 生产者 | 消费者 | Consumer Group |
|--------|------|--------|--------|---------------|
| `asr_events` | A → B | A 服务 | B 服务 | `b_processors` |
| `processed_events` | B → ROS | B 服务 | ROS2 节点 | `ros2_consumers` |

Consumer Group 由 `redis-init` 容器在启动时自动创建，服务代码无需自行创建。

## 环境变量

各模块连接 Redis 时需要配置的环境变量：

| 变量 | A 服务 | B 服务 | ROS2 |
|------|--------|--------|------|
| `REDIS_HOST` | `redis-streams` | `redis-streams` | `127.0.0.1` |
| `REDIS_PORT` | `6379` | `6379` | `6379` |
| `REDIS_USERNAME` | `service_a` | `service_b` | `ros2_reader` |
| `REDIS_PASSWORD` | 对应 `.env` 中 `REDIS_PASS_A` | 对应 `.env` 中 `REDIS_PASS_B` | 对应 `.env` 中 `REDIS_PASS_ROS2` |
| `REDIS_STREAM_OUT` | `asr_events` | `processed_events` | 无 |
| `REDIS_STREAM_IN` | 无 | `asr_events` | `processed_events` |
| `REDIS_GROUP_IN` | 无 | `b_processors` | `ros2_consumers` |
| `REDIS_CONSUMER_NAME` | 无 | `b-1` | `ros2-1` |
| `REDIS_MAXLEN` | `50000` | `50000` | 无 |
| `ROS_TOPIC` | 无 | 无 | `/voice_command` |

## JSON Schema

### asr_events（A 服务输出）

```json
{
  "id": "asr_YYYYMMDD_sessionId_NNNNNN",
  "timestamp": "2026-05-09T14:00:05.200000+08:00",
  "text": "当前道路为高速，天气晴",
  "wav_path": "/output/audio/20260509_140000_ab12cd34/part_000001.wav",
  "sample_rate": 16000,
  "offset_sec": 0.0,
  "duration_sec": 2.3,
  "segment_index": 1,
  "asr_model": "/models/FunAudioLLM/Fun-ASR-Nano-2512"
}
```

详细 Schema 见 `schemas/asr_event.schema.json`。

### processed_events（B 服务输出）

```json
{
  "id": "nlu_YYYYMMDD_sessionId_NNNNNN",
  "timestamp": "2026-05-09T14:00:05.200000+08:00",
  "label": {"天气": "晴", "道路": "高速"},
  "wav_path": "/output/audio/20260509_140000_ab12cd34/part_000001.wav",
  "sample_rate": 16000,
  "offset_sec": 0.0,
  "duration_sec": 2.3,
  "segment_index": 1,
  "nlu_model": "/models/bert"
}
```

详细 Schema 见 `schemas/processed_event.schema.json`。

## 联调测试

### 第一阶段：只测 Redis

```bash
# 1. 构建并启动 Redis
docker compose -f compose/docker-compose.redis.yml up -d --build

# 2. 安装 Python 依赖
pip install redis

# 3. 运行 A 服务示例（写入 asr_events）
#    按回车发送示例数据，输入 q 退出
REDIS_PASSWORD=<你的 REDIS_PASS_A> python examples/publish_asr_event.py

# 4. 在另一个终端运行 B 服务示例（读 asr_events → 写 processed_events）
REDIS_PASSWORD=<你的 REDIS_PASS_B> python examples/consume_asr_write_processed.py

# 5. 在第三个终端运行 ROS2 示例（读 processed_events，无 ROS2 环境时输出到 stdout）
REDIS_PASSWORD=<你的 REDIS_PASS_ROS2> python examples/redis_to_ros2_string.py
```

示例脚本的环境变量均有默认值，只需覆盖 `REDIS_PASSWORD` 即可。其他变量如 `REDIS_HOST`、`REDIS_USERNAME` 在默认值匹配时无需修改。

### 第二阶段：接入 A 服务

1. 启动 A 服务（加入 `shared-redis-net` 网络）
2. 确认 `asr_events` 增长
3. 确认 B 能消费处理
4. 确认 `processed_events` 增长

### 第三阶段：接入 ROS2

1. 启动 ROS2 节点
2. `ros2 topic list` 确认 `/voice_command` 存在
3. `ros2 topic echo /voice_command` 确认收到消息
4. 确认 `processed_events` 的 pending 不持续增长

## 调试命令

以下命令需要在 Redis 容器内使用 `redis_init` 管理员账户执行：

```bash
# 进入 Redis 容器
docker exec -it redis-streams sh

# 在容器内执行（替换 <密码> 为 REDIS_PASS_INIT 的值）
CLI="redis-cli --user redis_init --pass <密码>"

# 查看 asr_events 消息数量
$CLI XLEN asr_events

# 查看 asr_events 最近 3 条消息
$CLI XREVRANGE asr_events + - COUNT 3

# 查看 processed_events 消息数量
$CLI XLEN processed_events

# 查看 processed_events 最近 3 条输出
$CLI XREVRANGE processed_events + - COUNT 3

# 查看 B 消费组状态
$CLI XINFO GROUPS asr_events

# 查看 ROS2 消费组状态
$CLI XINFO GROUPS processed_events

# 查看 pending 消息（未确认的消息）
$CLI XPENDING asr_events b_processors
$CLI XPENDING processed_events ros2_consumers

# 查看所有 ACL 用户
$CLI ACL LIST

# 查看 ACL 操作日志（认证失败、权限拒绝等）
$CLI ACL LOG
```

## ACK 顺序（重要）

**必须遵循「处理 → 写输出 → ACK」的顺序。**

正确流程：

```
1. 读取消息 (XREADGROUP)
2. 处理消息
3. 写输出 (XADD)
4. 确认消息 (XACK)
```

错误流程：

```
1. 读取消息 (XREADGROUP)
2. 确认消息 (XACK)  ← 先 ACK
3. 处理消息
4. 写输出 (XADD)     ← 如果步骤 3/4 崩溃，消息已 ACK，链路数据丢失
```

## 启动时序

```
1. start_redis.sh 启动 → 从模板生成 ACL 文件（替换密码占位符）
2. Redis 服务器启动 → 加载 ACL 文件，所有用户生效
3. Healthcheck → healthcheck 用户认证成功
4. redis-init 启动 → 使用 redis_init 认证
5. redis-init 创建 Consumer Group（已存在则跳过）
6. redis-init 退出
```

## 常见问题

### 连接被拒绝 (NOAUTH)

Redis 禁用了默认用户，所有连接必须认证。检查：
- `REDIS_USERNAME` 和 `REDIS_PASSWORD` 是否与 `.env` 中配置一致
- 服务是否已加入 `shared-redis-net` 网络

### 服务无法连接 Redis

- Docker 网络内的服务：确认 `REDIS_HOST=redis-streams`，确认已加入 `shared-redis-net`
- host 网络模式的服务：确认 `REDIS_HOST=127.0.0.1`
- 检查网络：`docker network inspect shared-redis-net`，确认双方容器都在列表中

### 多个 ROS2 节点使用同一个 consumer name

同一个 Consumer Group 下，不同实例**必须**使用不同的 `REDIS_CONSUMER_NAME`：
- `ros2-1`、`ros2-2`、`ros2-3` ...

否则消息会被分配不均或丢失。

### MAXLEN 太小导致离线期间消息被裁剪

如果 A 服务每分钟 100 条，B 服务离线 1 小时，`MAXLEN=1000` 会导致早期消息被裁剪。建议 `MAXLEN=50000`。

### 先 ACK 再写输出

B 服务在 ACK 后崩溃，导致链路数据丢失。**必须先写输出再 ACK。** 详见 [ACK 顺序](#ack-顺序重要)。

## 目录结构

```
voice_redis/
├── .env                          # 密码与环境变量（不提交到版本控制）
├── .gitignore
├── README.md                     # 本文件
├── redis/
│   ├── Dockerfile                # 自定义 Redis 镜像（打包配置文件）
│   ├── start_redis.sh            # Redis 启动脚本（bootstrap ACL + 启动服务器）
│   ├── redis.conf                # Redis 服务器配置
│   ├── redis-acl.txt             # ACL 模板（密码为占位符，启动时替换）
│   └── init_streams.sh           # 初始化脚本（替换密码、加载 ACL、创建 Consumer Group）
├── compose/
│   └── docker-compose.redis.yml  # Docker Compose 配置
├── schemas/
│   ├── asr_event.schema.json     # A 服务输出 JSON Schema
│   └── processed_event.schema.json # B 服务输出 JSON Schema
└── examples/
    ├── publish_asr_event.py              # A 服务示例：写入 asr_events
    ├── consume_asr_write_processed.py    # B 服务示例：读 asr_events → 写 processed_events
    └── redis_to_ros2_string.py           # ROS2 节点示例：读 processed_events → ROS2 topic
```
