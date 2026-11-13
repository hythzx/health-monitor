# Health Monitor

一个轻量的服务健康监控工具，支持定时检查、异常通知和 Web 管理。

## 功能

- 监控 Redis、MySQL、MongoDB、EMQX 和 RESTful API。
- 通过 Webhook、邮件或阿里云短信发送告警。
- 在中文管理界面查看服务状态、预警和恢复记录。
- 在线查看、编辑和校验 YAML 配置，保存后热更新，并自动备份。
- 使用 SQLite 保存预警历史，支持 Docker 部署。

## Docker 部署

```bash
git clone https://github.com/hythzx/health-monitor.git
cd health-monitor
mkdir -p logs data
```

编辑 `config/config.yaml`，填入实际服务地址和告警配置。仓库中的配置用于演示，需要按自己的环境调整。

生成管理令牌并启动（Linux）：

```bash
printf 'HEALTH_MONITOR_WEB_TOKEN=%s\n' "$(openssl rand -hex 24)" > .env
chmod 600 .env
sudo chown -R 10001:10001 config logs data
docker compose up -d --build
```

打开 [http://localhost:8080](http://localhost:8080)，使用 `.env` 中的令牌登录。

配置目录需要可写；`data` 目录用于保存预警历史。远程访问建议通过 HTTPS 反向代理。

## 源码运行

需要 Python 3.11+。在项目目录中执行：

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export HEALTH_MONITOR_WEB_TOKEN="$(openssl rand -hex 24)"
python main.py config/config.yaml --web
```

打开 [http://127.0.0.1:8080](http://127.0.0.1:8080)，使用环境变量中的令牌登录。令牌至少 16 位，请自行保存。

不需要界面时去掉 `--web`；需要远程访问时添加 `--web-host 0.0.0.0`。

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

完整示例见 [config](config/)，告警配置见 [告警说明](docs/ALERTS.md)。服务和告警配置支持热更新；`state_file`、`enable_performance_monitoring` 修改后需要重启。

## 开发与文档

```bash
pip install -r requirements-dev.txt
pytest
```

- [API 文档](docs/API.md)
- [问题反馈](https://github.com/hythzx/health-monitor/issues)
