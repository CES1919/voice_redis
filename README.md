# voice_redis — Redis Streams 通信层

用于 **A(ASR)**、**B(NLU)**、**ROS2 节点** 之间的 Redis Streams 通信，包含最小 ACL 权限控制与 Consumer Group 初始化。

## 1) 环境要求（Ubuntu 22.04）

- Docker Engine
- Docker Compose v2

## 2) 配置

在项目根目录创建 `.env`：

```dotenv
REDIS_PASS_HEALTH=xxx
REDIS_PASS_INIT=xxx
REDIS_PASS_A=xxx
REDIS_PASS_B=xxx
REDIS_PASS_ROS2=xxx
```

> 5 个密码都必须配置。

## 3) 构建与启动

```bash
docker compose -f compose/docker-compose.redis.yml build
docker compose -f compose/docker-compose.redis.yml up -d
```

查看状态：

```bash
docker compose -f compose/docker-compose.redis.yml ps
docker logs redis-streams
docker logs redis-init
```

## 4) 已保留的最小能力

- A 仅写 `asr_events`
- B 读 `asr_events`，写 `processed_events`
- ROS2 仅读 `processed_events`
- `redis-init` 启动时自动创建：
  - `asr_events / b_processors`
  - `processed_events / ros2_consumers`

## 5) 与其他模块容器通信

其他模块容器与本项目在同一 docker compose 内时，可直接使用：

- `REDIS_HOST=redis-streams`
- `REDIS_PORT=6379`

若外部进程/host 网络访问，使用：

- `REDIS_HOST=127.0.0.1`
- `REDIS_PORT=6379`

## 6) 常见问题

### ACL 语法错误导致 Redis 重启

如果日志出现：

- `Aborting Redis startup because of ACL errors`

说明 ACL 文件格式不符合 Redis 语法。当前仓库已改为 Redis 7 可识别的标准 ACL 规则（`user ... ~pattern -@all +command`）。

### overcommit_memory 警告

Ubuntu 22.04 建议设置：

```bash
sudo sysctl -w vm.overcommit_memory=1
```

持久化配置：

```bash
echo 'vm.overcommit_memory=1' | sudo tee /etc/sysctl.d/99-redis.conf
sudo sysctl --system
```
