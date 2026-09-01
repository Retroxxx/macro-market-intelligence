# Local Macro Extension Deployment

## Architecture

`macro` 是 NiuOne Compose 的 sidecar，默认监听容器 8790、宿主机 `127.0.0.1:8790`，只通过 Docker 内网访问 `dashboard:8787` 的公开读 API。数据写入独立 `local-macro-data` volume，不触碰 `niuone-data` 或 `newsnow-data`。

## Development

```bash
cp local.env.example .local-data/local.env
# 按需修改 LOCAL_MACRO_NIUONE_BASE_URL
python3 -m uvicorn local_ext.api.app:app --host 127.0.0.1 --port 8790
```

本地 sidecar 需要一个已运行的官方 Dashboard，或用测试中的 mock adapter。不要在正式运行目录做实验。

## Staging / Docker smoke

```bash
docker compose -f compose.yaml -f deploy/compose.prod.yaml \
  -p niuone-smoke --env-file local.env \
  up -d --build macro dashboard scheduler
curl -fsS http://127.0.0.1:8790/api/local/v1/health
curl -fsS http://127.0.0.1:8790/api/local/v1/context

docker compose -f compose.yaml -f deploy/compose.prod.yaml \
  -p niuone-smoke down -v
```

实际 smoke 前确认 8790 未被占用，并保留 NewsNow 由基础 Compose 自动编排。

## Production release

1. 固定 `LOCAL_MACRO_IMAGE`，不要使用 `latest`。
2. 在隔离环境执行单元、兼容性和 Compose smoke 测试。
3. 记录 `LOCAL_MACRO_VERSION` 与 `LOCAL_MACRO_UPSTREAM_COMMIT`。
4. 构建并标记镜像，例如 `niuone-macro:2026.09.01-r1`。
5. 备份 `local-macro-data` volume。
6. 使用相同固定 tag 启动 overlay。
7. 检查 `docker compose ps`、macro health、官方 `/healthz` 和 `/readyz`。

```bash
docker compose -f compose.yaml -f deploy/compose.prod.yaml \
  -p niuone-prod --env-file .local-data/local.env \
  up -d macro
curl -fsS http://127.0.0.1:8790/api/local/v1/health
```

禁止把服务器上的 `git pull && docker compose up` 当作生产升级流程。

## Backup

```bash
docker run --rm --volumes-from niuone-prod-macro-1 \
  -v "$PWD/.local-data/backups:/backup" alpine \
  tar czf /backup/local-macro-data.tgz -C /data local-ext
```

实际容器名以 `docker compose ps` 为准；备份官方 `niuone-data`、NewsNow volume 与本地 volume 时分别处理。

## Rollback

保留上一版固定镜像 tag 和对应环境文件。发现 health、兼容性或数据质量异常时：

```bash
LOCAL_MACRO_IMAGE=niuone-macro:<previous-tag> \
docker compose -f compose.yaml -f deploy/compose.prod.yaml \
  -p niuone-prod --env-file .local-data/local.env up -d macro
```

回滚只替换 macro，不回滚官方账户、成交或交易数据库；先验证 API 再恢复流量。

## Limits

宏观服务当前按请求缓存 60 秒，官方源请求并行且每个请求超时 5 秒。无数据时 fail-safe 输出 `UNKNOWN`。此版本没有反向代理、认证或自动交易能力，生产公网暴露 8790 前必须配置受控访问层。
