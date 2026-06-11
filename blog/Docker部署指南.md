# Docker 部署指南

## 1. 构建镜像

```bash
docker compose build
```

## 2. 启动服务

```bash
docker compose up -d
```

## 3. 查看状态

```bash
docker compose ps
```

## 4. 查看日志

```bash
docker compose logs -f agent-qq
```

## 5. 重启服务

```bash
docker compose restart agent-qq
```

## 6. 停止服务

```bash
docker compose down
```

## 7. Claude Code 配置挂载

`docker-compose.yml` 中默认挂载：

```yaml
${CLAUDE_CONFIG_DIR:-$HOME/.claude}:/root/.claude:ro
```

如果宿主机配置目录是 `/home/ww/.claude`，则 `.env` 中配置：

```env
CLAUDE_CONFIG_DIR=/home/ww/.claude
```

## 8. 连接 NapCat

容器访问宿主机 NapCat 时，通常使用：

```env
ONEBOT_WS_URL=ws://host.docker.internal:3001
```
