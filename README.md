# Health Monitor

一个轻量的服务健康监控工具，支持定时检查、异常通知和 Web 管理。

## 功能

- 监控 Redis、MySQL、MongoDB、EMQX 和 RESTful API。
- 通过 Webhook、邮件或阿里云短信发送告警。
- 在中文管理界面查看服务状态、预警和恢复记录。
- 通过表单添加、编辑、删除监控项和通知渠道，保存后立即生效。
- SQLite 保存配置、检查结果、预警恢复、运行日志、错误及通知投递记录。
- 历史支持分页、服务、关键字和时间筛选，支持自动保留策略与手动清理。
- 保留 YAML 导入 / 导出，支持 Docker 部署。

## Docker 部署

```bash
git clone https://github.com/hythzx/health-monitor.git
cd health-monitor
mkdir -p logs data
```

首次启动会将 `config/config.yaml` 导入数据库。已有配置可以直接沿用；如需从空配置开始，将该文件内容改为 `services: {}`。启动后在管理界面添加监控项和通知渠道。

生成管理令牌并启动（Linux）：

```bash
printf 'HEALTH_MONITOR_WEB_TOKEN=%s\n' "$(openssl rand -hex 24)" > .env
chmod 600 .env
sudo chown -R 10001:10001 logs data
docker compose up -d --build
```

打开 [http://localhost:8080](http://localhost:8080)，使用 `.env` 中的令牌登录。

`data` 目录需要可写，保存配置及全部历史；配置目录只读挂载即可。远程访问建议通过 HTTPS 反向代理。

## 源码运行

需要 Python 3.11+。在项目目录中执行：

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export HEALTH_MONITOR_WEB_TOKEN="$(openssl rand -hex 24)"
python main.py --web
```

打开 [http://127.0.0.1:8080](http://127.0.0.1:8080)，使用环境变量中的令牌登录。令牌至少 16 位，请自行保存。

导入现有 YAML：`python main.py config/config.yaml --web`。数据库已有配置后，后续修改 YAML 不会覆盖在线配置；可在「高级：YAML 导入 / 导出」主动导入。

不需要界面时执行 `python main.py config/config.yaml`，仍然记录历史。需要远程访问时添加 `--web-host 0.0.0.0`。

## 配置示例

```yaml
global:
  check_interval: 30
  log_level: INFO

services:
  api:
    type: restful
    url: https://example.com/health
    timeout: 5
    expected_status: 200

alerts: []
```

完整示例见 [config](config/)，告警配置见 [告警说明](docs/ALERTS.md)。监控项、通知渠道和全局检查参数支持热更新；`state_file`、`enable_performance_monitoring` 修改后需要重启。

## 数据与清理

- 默认数据库为 `data/events.sqlite3`，可用 `--database /path/monitor.sqlite3` 指定；旧参数 `--events-db` 仍可使用。旧版预警表会自动保留并升级。
- 已有数据库可独立启动，不再依赖原 YAML。新数据库不传 YAML 时会创建空配置。
- 「历史与日志」可查看每次检查、运行错误和渠道投递结果；「预警记录」仅记录异常与恢复，不能作为通知送达证明。
- 默认保留 30 天，每类最多 10,000 条。可在线调整，启动时及每小时清理过期数据，写入时限制条数。
- 手动清理需选择类型、截止时间并确认；只删除历史，保留配置和服务最后状态。错误历史属于运行日志，清理运行日志也会清理其中的错误。
- 清理后空间会复用，数据库文件不会立即缩小。完整备份：停服后复制 `data` 目录，恢复时停服替换即可。
- 配置含连接密码和通知密钥，请妥善保管数据库及备份。日志会遮盖已配置的密码、请求头和常见 URL 密钥参数；不要把额外敏感数据写入日志。

管理接口均需 Bearer 管理令牌：`GET/PUT /api/settings` 读取或保存结构化配置（保存必须携带读取时的 `revision`，冲突返回 409）；`GET /api/history/{checks|events|logs|errors|deliveries}` 查询历史；`GET/PUT /api/retention` 管理策略；`POST /api/history/cleanup` 清理历史。完整参数见 [API 文档](docs/API.md#数据库管理接口)。

## 开发与文档

```bash
pip install -r requirements-dev.txt
pytest
```

- [API 文档](docs/API.md)
- [问题反馈](https://github.com/hythzx/health-monitor/issues)
