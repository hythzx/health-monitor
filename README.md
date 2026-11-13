# 服务健康监控系统

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Docker Pulls](https://img.shields.io/docker/pulls/hythzx/health-monitor)](https://hub.docker.com/r/hythzx/health-monitor)
[![Build Status](https://img.shields.io/github/actions/workflow/status/hythzx/health-monitor/docker-build.yml?branch=master)](https://github.com/hythzx/health-monitor/actions)

一个基于Python的服务健康监控和报警系统，支持监控多种类型的服务（Redis、MongoDB、MySQL、EMQX、RESTful接口等）的健康状态，并在服务异常时通过可配置的方式发送告警通知。

## ✨ 特性

- 🔍 **多服务支持**: 支持Redis、MongoDB、MySQL、EMQX、RESTful API等多种服务类型
- 📊 **实时监控**: 可配置的检查间隔，实时监控服务健康状态
- 🚨 **灵活告警**: 支持钉钉、企业微信、Slack、邮件等多种告警方式
- 🔧 **热更新配置**: 支持配置文件热更新，无需重启服务
- 📝 **详细日志**: 完整的日志记录和轮转功能
- 🎯 **高可用**: 异步架构，支持并发检查和容错处理
- 🛠️ **易于扩展**: 模块化设计，易于添加新的服务类型和告警方式
- 🐳 **容器化部署**: 完整的Docker支持，一键部署

## 📋 系统要求

- Python 3.11+
- Docker (可选，用于容器化部署)
- 支持的操作系统：Linux、macOS、Windows

## 🚀 快速开始

使用下方「Web 管理面板」的源码或 Docker Compose 部署步骤。旧版部署升级时，需要增加管理令牌、可写配置挂载及预警历史目录。

只运行监控、不启用 Web 的方式仍然可用：

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py config/config.yaml
```

## 📖 配置说明

### 基础配置示例

```yaml
# 全局配置
global:
  check_interval: 30
  log_level: INFO
  log_file: health-monitor.log
  max_concurrent_checks: 10

# 服务监控配置
services:
  redis-cache:
    type: redis
    host: localhost
    port: 6379
    timeout: 5
    check_interval: 10

  mysql-db:
    type: mysql
    host: localhost
    port: 3306
    username: root
    password: "your_password"
    database: test
    timeout: 10

  api-service:
    type: restful
    url: https://api.example.com/health
    method: GET
    timeout: 10
    expected_status: 200

# 告警配置
alerts:
  - name: dingtalk
    type: http
    url: "https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN"
    method: POST
    headers:
      Content-Type: "application/json"
    template: |
      {
        "msgtype": "text",
        "text": {
          "content": "🚨 服务告警\n服务: {{service_name}}\n状态: {{status}}\n时间: {{timestamp}}"
        }
      }
```

### 支持的服务类型

| 服务类型 | 配置示例 | 说明 |
|---------|---------|------|
| Redis | `type: redis` | 支持密码认证、数据库选择 |
| MySQL | `type: mysql` | 支持连接池、查询测试 |
| MongoDB | `type: mongodb` | 支持认证、副本集 |
| EMQX | `type: emqx` | 支持MQTT和HTTP检查 |
| RESTful | `type: restful` | 支持各种HTTP方法和验证 |

### 告警渠道

- 🔔 **钉钉机器人**: 企业内部通知
- 💬 **企业微信**: 团队协作平台
- 📱 **Slack**: 国际化团队沟通
- 📧 **邮件**: 传统邮件通知
- 🌐 **自定义Webhook**: 集成其他系统

## 🔧 命令行选项

```bash
# 基本用法
python main.py config.yaml

# 可用选项
python main.py [选项] 配置文件

选项:
  -h, --help           显示帮助信息
  -v, --version        显示版本信息
  --validate           验证配置文件格式
  --test-alerts        测试告警系统
  --check-once         执行一次健康检查后退出
  --log-level LEVEL    设置日志级别
  --log-file FILE      日志文件路径
  -d, --daemon         守护进程模式
  --pid-file FILE      PID文件路径
```

## 📊 Web 管理面板（v1.1）

提供中文管理界面：服务状态概览、预警与恢复历史（按服务和状态筛选、分页），以及完整 YAML 配置的查看、校验和在线编辑。界面每 10 秒刷新，编辑中的内容不会被自动覆盖。

### 源码启动

Python 3.11+，建议使用 Python 3.13。依赖已按 2026-11-13 可获取的稳定版本固定。

```bash
pip install -r requirements.txt
export HEALTH_MONITOR_WEB_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
# 请自行安全保存该环境变量的值，登录面板时使用。
python main.py config/config.yaml --web
```

打开 http://127.0.0.1:8080，输入管理令牌。令牌只保留在当前页面内存，刷新页面需要重新登录。默认只监听本机；远程访问可加 `--web-host 0.0.0.0`，并在反向代理上配置 HTTPS。API 使用 `Authorization: Bearer <token>`；令牌至少 16 位，不写入 YAML。未加 `--web` 时保留原有纯监控启动方式。

### Docker Compose

```bash
mkdir -p config logs data
# 使用你自己的监控配置，或从 config/basic_example.yaml 复制后调整地址。
# 容器使用 UID/GID 10001，需要配置目录可写以便原子替换配置和生成备份。
sudo chown -R 10001:10001 config logs data
python -c 'import secrets; print("HEALTH_MONITOR_WEB_TOKEN="+secrets.token_urlsafe(32))' > .env
chmod 600 .env
docker compose up -d --build
```

打开 http://localhost:8080，使用 `.env` 中的令牌登录。Compose 挂载可写配置目录和持久化 `data` 目录；不再自动启动示例数据库。已有部署请同步调整端口、令牌、目录权限与挂载，不能沿用 `:ro` 配置挂载。

`docker run` 需要传入 `-e HEALTH_MONITOR_WEB_TOKEN`、`-p 8080:8080`，并挂载可写的 `/app/config` 和 `/app/data`。

### 配置生效与预警历史

- 保存前校验 YAML、服务参数和通知渠道；校验通过后备份为同目录 `config.yaml.bak`，原子替换文件并立即应用。备份与新配置仅文件所有者可读写。
- 使用内容版本号防止多人编辑相互覆盖。发生冲突会保留编辑内容，需重新加载并整合修改后再保存。
- 全局检查间隔、最大并发检查数、日志和通知渠道支持热更新。`state_file` 与 `enable_performance_monitoring` 变更需要修改文件并重启，在线编辑会阻止这两项变化。
- 预警记录保存在 SQLite（默认 `data/events.sqlite3`，用 `--events-db` 修改），包含首次检查异常及后续异常/恢复，每次状态改变只记录一条，最多保留 10,000 条。记录代表检测事件，不等同于通知投递成功。
- 历史从升级启用面板后开始积累，不回填旧日志。当前异常可在概览查看。通知仍沿用原有状态变化机制（首次检查不发送通知）。
- 配置包含数据库密码与渠道密钥，所有配置 API 均需要管理令牌；`/health` 仅公开存活状态。
- 依赖升级已将 Motor 替换为 PyMongo 官方异步 API，并适配 aiomqtt 的 `identifier` 参数。参考 [MongoDB 官方迁移说明](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/reference/migration/)。

API：`GET /api/status`、`GET /api/alerts?service=&status=DOWN&limit=50&offset=0`、`GET /api/config`、`POST /api/config/validate`、`PUT /api/config`。配置校验请求体为 `{"content":"YAML文本"}`，保存时另附读取时的 `revision`。存活检查使用 `GET /health`。

开发测试：`pip install -r requirements-dev.txt && pytest`。

## 🛠️ 开发指南

### 本地开发环境

```bash
# 设置开发环境
git clone https://github.com/hythzx/health-monitor.git
cd health-monitor
python -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt

# 运行测试
pytest tests/

# 代码格式化
black health_monitor/
flake8 health_monitor/

# 启动开发服务器
python main.py config/development_template.yaml
```

### 添加新服务类型

1. 在`health_monitor/checkers/`目录创建新的检查器
2. 继承`BaseHealthChecker`类
3. 实现必要的方法
4. 在工厂类中注册

```python
from .base import BaseHealthChecker
from .factory import register_checker

@register_checker('new_service')
class NewServiceChecker(BaseHealthChecker):
    async def check_health(self):
        # 实现健康检查逻辑
        pass
```

### 贡献代码

1. Fork项目
2. 创建特性分支: `git checkout -b feature/new-feature`
3. 提交更改: `git commit -am 'Add new feature'`
4. 推送分支: `git push origin feature/new-feature`
5. 创建Pull Request

## 🔍 故障排除

### 常见问题

1. **配置文件错误**
   ```bash
   # 验证配置
   python main.py --validate config.yaml
   ```

2. **Docker容器启动失败**
   ```bash
   # 查看容器日志
   docker logs health-monitor
   
   # 检查配置挂载
   docker exec health-monitor ls -la config/
   ```

3. **服务连接失败**
   - 检查网络连通性
   - 验证认证信息
   - 确认防火墙设置

### 日志分析

```bash
# 实时查看日志
tail -f logs/health-monitor.log

# 过滤错误日志
grep ERROR logs/health-monitor.log

# Docker容器日志
docker-compose logs -f health-monitor
```

## 📈 CI/CD流程

项目包含完整的GitHub Actions工作流：

- ✅ **自动构建**: 每次提交自动构建Docker镜像
- 🧪 **自动测试**: 运行完整测试套件
- 🔒 **安全扫描**: Docker镜像安全扫描
- 📦 **自动发布**: 自动推送到Docker Hub
- 🏷️ **版本管理**: 基于Git标签的版本控制

### 发布新版本

```bash
# 创建新版本标签
git tag -a v1.1.0 -m "Release version 1.1.0"
git push origin v1.1.0

# GitHub Actions会自动:
# 1. 构建Docker镜像
# 2. 运行测试
# 3. 推送到Docker Hub
# 4. 创建GitHub Release
```

## 📄 许可证

本项目采用MIT许可证 - 查看[LICENSE](LICENSE)文件了解详情。

## 🤝 社区

- 📧 **问题反馈**: [GitHub Issues](https://github.com/hythzx/health-monitor/issues)
- 💬 **讨论交流**: [GitHub Discussions](https://github.com/hythzx/health-monitor/discussions)
- 📖 **文档**: [项目Wiki](https://github.com/hythzx/health-monitor/wiki)
- 🐳 **镜像**: [Docker Hub](https://hub.docker.com/r/hythzx/health-monitor)

## 🗺️ 路线图

- [x] Web管理界面
- [ ] Prometheus指标导出
- [ ] Grafana仪表板
- [ ] 更多数据库支持
- [ ] 微服务监控
- [ ] 自动故障恢复
- [ ] 监控模板市场

## 📊 项目统计

- ⭐ **GitHub Stars**: 持续增长中
- 🐳 **Docker Pulls**: 活跃使用中
- 🔧 **活跃贡献者**: 欢迎加入
- 📈 **版本发布**: 定期更新

---

**🚀 让服务监控变得简单可靠！**

开始使用：
```bash
git clone https://github.com/hythzx/health-monitor.git
cd health-monitor
docker compose up -d --build
```
