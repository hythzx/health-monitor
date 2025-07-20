# 告警系统使用指南

服务健康监控系统支持多种告警方式，包括HTTP、邮件和阿里云短信。本文档详细介绍如何配置和使用这些告警器。

## 支持的告警器类型

### 1. HTTP告警器
通过HTTP请求发送告警，支持钉钉机器人、企业微信、Slack等Webhook服务。

### 2. 邮件告警器
通过SMTP协议发送邮件告警，支持Gmail、企业邮箱等邮件服务。

### 3. 阿里云短信告警器
通过阿里云短信服务发送短信告警，支持批量发送和模板参数。

## 配置示例

### HTTP告警器配置

```yaml
alerts:
  - name: dingtalk-robot
    type: http
    url: "https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN"
    method: POST
    headers:
      Content-Type: "application/json"
    template: |
      {
        "msgtype": "text",
        "text": {
          "content": "🚨 服务告警\n服务名称: {{service_name}}\n状态: {{status}}\n时间: {{timestamp}}\n错误信息: {{error_message}}"
        }
      }
    max_retries: 3
    retry_delay: 1.0
    timeout: 30
```

**配置参数说明：**
- `url`: Webhook URL地址
- `method`: HTTP方法（GET、POST、PUT、PATCH）
- `headers`: 请求头（可选）
- `template`: 消息模板，支持变量替换
- `max_retries`: 最大重试次数（默认3）
- `retry_delay`: 重试延迟秒数（默认1.0）
- `timeout`: 请求超时时间（默认30秒）

### 邮件告警器配置

```yaml
alerts:
  - name: email-alert
    type: email
    smtp_server: smtp.gmail.com
    smtp_port: 587
    username: "your-email@gmail.com"
    password: "your-app-password"
    use_tls: true
    from_email: "your-email@gmail.com"
    from_name: "服务健康监控系统"
    to_emails:
      - "admin@company.com"
      - "ops@company.com"
    cc_emails:
      - "manager@company.com"
    subject_template: "🚨 服务告警: {{service_name}} - {{status}}"
    body_template: |
      服务健康监控告警通知
      
      服务名称: {{service_name}}
      服务类型: {{service_type}}
      当前状态: {{status}}
      发生时间: {{timestamp}}
      响应时间: {{response_time}}ms
      错误信息: {{error_message}}
      
      请及时处理相关问题！
    max_retries: 3
    retry_delay: 2.0
    timeout: 30
```

**配置参数说明：**
- `smtp_server`: SMTP服务器地址
- `smtp_port`: SMTP端口（通常587用于TLS，465用于SSL）
- `username`: 邮箱用户名
- `password`: 邮箱密码或应用专用密码
- `use_tls`: 是否使用TLS加密（默认true）
- `use_ssl`: 是否使用SSL加密（默认false）
- `from_email`: 发件人邮箱
- `from_name`: 发件人名称（可选）
- `to_emails`: 收件人邮箱列表
- `cc_emails`: 抄送邮箱列表（可选）
- `bcc_emails`: 密送邮箱列表（可选）
- `subject_template`: 邮件主题模板
- `body_template`: 邮件正文模板

### 阿里云短信告警器配置

```yaml
alerts:
  - name: aliyun-sms-alert
    type: aliyun_sms
    access_key_id: "YOUR_ACCESS_KEY_ID"
    access_key_secret: "YOUR_ACCESS_KEY_SECRET"
    region: "cn-hangzhou"
    sign_name: "您的签名"
    template_code: "SMS_123456789"
    phone_numbers:
      - "13800138000"
      - "13900139000"
    template_params:
      service: "{{service_name}}"
      status: "{{status}}"
      time: "{{timestamp}}"
    max_retries: 3
    retry_delay: 1.0
    batch_size: 100
    timeout: 30
```

**配置参数说明：**
- `access_key_id`: 阿里云AccessKey ID
- `access_key_secret`: 阿里云AccessKey Secret
- `region`: 阿里云区域（默认cn-hangzhou）
- `sign_name`: 短信签名
- `template_code`: 短信模板代码
- `phone_numbers`: 手机号码列表
- `template_params`: 模板参数映射
- `batch_size`: 批量发送大小（默认100，最大1000）

## 模板变量

所有告警器都支持以下模板变量：

- `{{service_name}}`: 服务名称
- `{{service_type}}`: 服务类型
- `{{status}}`: 服务状态（UP/DOWN）
- `{{timestamp}}`: 时间戳
- `{{error_message}}`: 错误信息
- `{{response_time}}`: 响应时间（毫秒）
- `{{metadata_*}}`: 元数据变量（如{{metadata_host}}）

## 常用SMTP配置

### Gmail
```yaml
smtp_server: smtp.gmail.com
smtp_port: 587
use_tls: true
# 需要使用应用专用密码，不是普通密码
```

### QQ邮箱
```yaml
smtp_server: smtp.qq.com
smtp_port: 587
use_tls: true
# 需要开启SMTP服务并获取授权码
```

### 企业微信邮箱
```yaml
smtp_server: smtp.exmail.qq.com
smtp_port: 465
use_ssl: true
```

### Outlook/Hotmail
```yaml
smtp_server: smtp-mail.outlook.com
smtp_port: 587
use_tls: true
```

## 阿里云短信服务配置

### 1. 开通短信服务
1. 登录阿里云控制台
2. 开通短信服务
3. 创建短信签名
4. 创建短信模板

### 2. 获取AccessKey
1. 访问阿里云RAM控制台
2. 创建用户并授权短信服务权限
3. 获取AccessKey ID和Secret

### 3. 短信模板示例
```
服务告警：${service}状态变为${status}，时间：${time}，请及时处理。
```

## 安全最佳实践

### 1. 敏感信息保护
- 不要在代码中硬编码密码和密钥
- 使用环境变量存储敏感配置
- 定期更新密码和访问密钥

### 2. 权限控制
- 为告警系统创建专用账号
- 授予最小必要权限
- 启用多因素认证

### 3. 网络安全
- 使用TLS/SSL加密传输
- 配置防火墙规则
- 监控异常访问

## 故障排除

### HTTP告警器问题
1. **连接超时**
   - 检查网络连接
   - 验证URL地址
   - 调整超时设置

2. **认证失败**
   - 检查Token或API密钥
   - 验证请求头配置
   - 查看服务商文档

### 邮件告警器问题
1. **SMTP认证失败**
   - 检查用户名和密码
   - 使用应用专用密码（Gmail）
   - 开启SMTP服务（QQ邮箱）

2. **SSL/TLS错误**
   - 检查端口配置
   - 验证加密设置
   - 更新证书

### 阿里云短信问题
1. **签名或模板审核失败**
   - 检查签名内容合规性
   - 验证模板格式
   - 联系阿里云客服

2. **发送频率限制**
   - 检查发送频率
   - 调整批量大小
   - 增加重试延迟

## 监控和日志

### 日志级别
- `INFO`: 正常发送记录
- `WARNING`: 重试和警告
- `ERROR`: 发送失败和错误

### 监控指标
- 告警发送成功率
- 平均响应时间
- 重试次数统计
- 错误类型分布

## 示例和测试

### 运行演示脚本
```bash
python examples/alert_demo.py
```

### 测试单个告警器
```python
from health_monitor.alerts.email_alerter import EmailAlerter
from health_monitor.models.health_check import AlertMessage
from datetime import datetime

# 创建告警器
config = {...}  # 您的配置
alerter = EmailAlerter('test', config)

# 创建测试消息
message = AlertMessage(
    service_name='test-service',
    service_type='redis',
    status='DOWN',
    timestamp=datetime.now(),
    error_message='测试告警'
)

# 发送告警
success = await alerter.send_alert(message)
print(f"发送结果: {success}")
```

## 扩展开发

### 创建自定义告警器
1. 继承`BaseAlerter`类
2. 实现`send_alert`方法
3. 实现`validate_config`方法
4. 在集成器中注册新类型

```python
from health_monitor.alerts.base import BaseAlerter

class CustomAlerter(BaseAlerter):
    async def send_alert(self, message):
        # 实现发送逻辑
        pass
    
    def validate_config(self):
        # 实现配置验证
        pass
```

## 更多信息

- 查看完整配置示例：`config/alerts_example.yaml`
- 运行测试：`python -m pytest tests/test_*_alerter.py`
- 查看API文档：`docs/API.md`