# 服务健康监控系统

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://python.org)
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

- Python 3.8+
- Docker (可选，用于容器化部署)
- 支持的操作系统：Linux、macOS、Windows

## 🚀 快速开始

### 方式一：Docker部署（推荐）

1. **使用预构建镜像**

```bash
# 拉取最新镜像
docker pull hythzx/health-monitor:latest

# 创建配置文件
mkdir -p ./config ./logs
cp config/basic_example.yaml ./config/config.yaml

# 启动容器
docker run -d \
  --name health-monitor \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/logs:/app/logs \
  hythzx/health-monitor:latest
```

2. **使用Docker Compose（推荐）**

```bash
# 克隆项目
git clone https://github.com/hythzx/health-monitor.git
cd health-monitor

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f health-monitor
```

### 方式二：从源码部署

1. **克隆项目**

```bash
git clone https://github.com/hythzx/health-monitor.git
cd health-monitor
```

2. **设置Python环境**

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
source venv/bin/activate  # Linux/macOS
# 或
venv\Scripts\activate     # Windows

# 安装依赖
pip install -r requirements.txt
```

3. **配置和启动**

```bash
# 复制配置模板
cp config/basic_example.yaml config.yaml

# 编辑配置文件（根据需要修改）
vim config.yaml

# 启动监控系统
python main.py config.yaml
```

### 方式三：开发模式

```bash
# 克隆项目
git clone https://github.com/hythzx/health-monitor.git
cd health-monitor

# 安装开发环境
pip install -e .

# 运行测试
pytest

# 启动开发服务器
python main.py config/development_template.yaml
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

## 🐳 Docker部署详解

### 构建自定义镜像

```bash
# 克隆项目
git clone https://github.com/hythzx/health-monitor.git
cd health-monitor

# 构建镜像
docker build -t my-health-monitor .

# 运行自定义镜像
docker run -d \
  --name health-monitor \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/logs:/app/logs \
  my-health-monitor
```

### Docker Compose配置

项目包含完整的`docker-compose.yml`配置：

```yaml
version: '3.8'

services:
  health-monitor:
    image: hythzx/health-monitor:latest
    container_name: health-monitor
    volumes:
      - ./config:/app/config
      - ./logs:/app/logs
    environment:
      - PYTHONUNBUFFERED=1
    restart: unless-stopped
    command: ["python", "main.py", "config/config.yaml"]

  # 示例服务 - Redis
  redis:
    image: redis:7-alpine
    container_name: redis-demo
    ports:
      - "6379:6379"
    restart: unless-stopped

  # 示例服务 - MySQL
  mysql:
    image: mysql:8.0
    container_name: mysql-demo
    environment:
      MYSQL_ROOT_PASSWORD: password
      MYSQL_DATABASE: testdb
    ports:
      - "3306:3306"
    restart: unless-stopped
```

### 环境变量配置

```bash
# .env 文件示例
HEALTH_MONITOR_LOG_LEVEL=INFO
HEALTH_MONITOR_CONFIG_PATH=/app/config/config.yaml
MYSQL_PASSWORD=your_password
REDIS_PASSWORD=your_redis_password
DINGTALK_TOKEN=your_dingtalk_token
```

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

## 📊 监控面板

系统提供简单的状态查询接口：

```bash
# 查看所有服务状态
curl http://localhost:8080/status

# 获取特定服务状态
curl http://localhost:8080/service/{service_name}

# 查看告警统计
curl http://localhost:8080/alerts/stats
```

## 🛠️ 开发指南

### 本地开发环境

```bash
# 设置开发环境
git clone https://github.com/hythzx/health-monitor.git
cd health-monitor
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

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

- [ ] Web管理界面
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
docker-compose up -d
```