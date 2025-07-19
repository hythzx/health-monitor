# API 文档

本文档描述了健康监控系统的内部API接口和扩展开发指南。

## 目录

- [核心接口](#核心接口)
- [健康检查器API](#健康检查器api)
- [告警器API](#告警器api)
- [配置管理API](#配置管理api)
- [状态管理API](#状态管理api)
- [扩展开发](#扩展开发)

## 核心接口

### BaseHealthChecker

所有健康检查器的基类，定义了统一的接口。

```python
from abc import ABC, abstractmethod
from typing import Dict, Any
from ..models.health_check import HealthCheckResult

class BaseHealthChecker(ABC):
    """健康检查器基类"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        初始化健康检查器
        
        Args:
            name: 服务名称
            config: 服务配置
        """
        self.name = name
        self.config = config
        self.logger = get_logger(f'checker.{self.__class__.__name__.lower()}.{name}')
    
    @abstractmethod
    def validate_config(self) -> bool:
        """
        验证配置参数是否有效
        
        Returns:
            bool: 配置是否有效
        """
        pass
    
    @abstractmethod
    async def check_health(self) -> HealthCheckResult:
        """
        执行健康检查
        
        Returns:
            HealthCheckResult: 健康检查结果
        """
        pass
    
    def get_timeout(self) -> int:
        """
        获取超时时间
        
        Returns:
            int: 超时时间（秒）
        """
        return self.config.get('timeout', 10)
    
    def get_check_interval(self) -> int:
        """
        获取检查间隔
        
        Returns:
            int: 检查间隔（秒）
        """
        return self.config.get('check_interval', 30)
    
    async def close(self):
        """关闭连接和清理资源"""
        pass
```

### HealthCheckResult

健康检查结果数据模型。

```python
from dataclasses import dataclass
from typing import Dict, Any, Optional
from datetime import datetime

@dataclass
class HealthCheckResult:
    """健康检查结果"""
    service_name: str                    # 服务名称
    service_type: str                    # 服务类型
    is_healthy: bool                     # 是否健康
    response_time: float                 # 响应时间（秒）
    error_message: Optional[str] = None  # 错误信息
    timestamp: datetime = None           # 检查时间戳
    metadata: Dict[str, Any] = None      # 额外元数据
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.metadata is None:
            self.metadata = {}
```

## 健康检查器API

### 注册检查器

使用装饰器注册新的健康检查器：

```python
from .factory import register_checker

@register_checker('my_service')
class MyServiceChecker(BaseHealthChecker):
    """自定义服务检查器"""
    
    def validate_config(self) -> bool:
        """验证配置"""
        required_fields = ['host', 'port']
        for field in required_fields:
            if field not in self.config:
                self.logger.error(f"缺少必需配置: {field}")
                return False
        return True
    
    async def check_health(self) -> HealthCheckResult:
        """执行健康检查"""
        start_time = time.time()
        
        try:
            # 执行具体的健康检查逻辑
            # ...
            
            return HealthCheckResult(
                service_name=self.name,
                service_type='my_service',
                is_healthy=True,
                response_time=time.time() - start_time
            )
        except Exception as e:
            return HealthCheckResult(
                service_name=self.name,
                service_type='my_service',
                is_healthy=False,
                response_time=time.time() - start_time,
                error_message=str(e)
            )
```

### 现有检查器

#### RedisHealthChecker

Redis健康检查器配置选项：

```python
config = {
    'host': 'localhost',           # Redis主机地址
    'port': 6379,                  # Redis端口
    'password': 'password',        # 密码（可选）
    'database': 0,                 # 数据库编号
    'timeout': 5,                  # 连接超时时间
    'test_operations': False,      # 是否执行SET/GET测试
    'collect_info': True           # 是否收集服务器信息
}
```

#### MySQLHealthChecker

MySQL健康检查器配置选项：

```python
config = {
    'host': 'localhost',           # MySQL主机地址
    'port': 3306,                  # MySQL端口
    'username': 'user',            # 用户名
    'password': 'password',        # 密码
    'database': 'test',            # 数据库名
    'timeout': 10,                 # 连接超时时间
    'test_queries': False,         # 是否执行测试查询
    'collect_status': True,        # 是否收集状态信息
    'test_database_access': True   # 是否测试数据库访问
}
```

#### MongoHealthChecker

MongoDB健康检查器配置选项：

```python
config = {
    'host': 'localhost',           # MongoDB主机地址
    'port': 27017,                 # MongoDB端口
    'username': 'user',            # 用户名（可选）
    'password': 'password',        # 密码（可选）
    'database': 'test',            # 数据库名
    'timeout': 10,                 # 连接超时时间
    'test_queries': False,         # 是否执行查询测试
    'test_operations': False,      # 是否执行文档操作测试
    'collect_status': True,        # 是否收集状态信息
    'test_database_access': True   # 是否测试数据库访问
}
```

#### EMQXHealthChecker

EMQX健康检查器配置选项：

```python
config = {
    'host': 'localhost',           # EMQX主机地址
    'port': 1883,                  # MQTT端口
    'username': 'user',            # MQTT用户名
    'password': 'password',        # MQTT密码
    'client_id': 'health_monitor', # MQTT客户端ID
    'timeout': 15,                 # 连接超时时间
    'check_method': 'mqtt',        # 检查方法: mqtt 或 http
    'test_pubsub': False,          # 是否测试发布/订阅
    'also_check_api': False,       # 是否同时检查HTTP API
    'api_port': 18083,             # HTTP API端口
    'api_username': 'admin',       # API用户名
    'api_password': 'public',      # API密码
    'collect_stats': False         # 是否收集统计信息
}
```

#### RestfulHealthChecker

RESTful API健康检查器配置选项：

```python
config = {
    'url': 'http://api.example.com/health',  # API URL
    'method': 'GET',                         # HTTP方法
    'timeout': 10,                           # 请求超时时间
    'headers': {                             # 请求头
        'Authorization': 'Bearer token',
        'Accept': 'application/json'
    },
    'data': None,                            # POST数据
    'json': None,                            # JSON数据
    'params': {},                            # 查询参数
    'expected_status': 200,                  # 期望状态码
    'expected_content': 'healthy',           # 期望内容
    'validate_json': True,                   # 是否验证JSON
    'required_json_fields': ['status'],      # 必需JSON字段
    'collect_response_stats': True,          # 是否收集响应统计
    'auth_username': None,                   # HTTP基本认证用户名
    'auth_password': None                    # HTTP基本认证密码
}
```

## 告警器API

### BaseAlerter

所有告警器的基类：

```python
from abc import ABC, abstractmethod
from ..models.health_check import AlertMessage

class BaseAlerter(ABC):
    """告警器基类"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        初始化告警器
        
        Args:
            name: 告警器名称
            config: 告警器配置
        """
        self.name = name
        self.config = config
        self.logger = get_logger(f'alerter.{self.__class__.__name__.lower()}.{name}')
    
    @abstractmethod
    def validate_config(self) -> bool:
        """
        验证配置参数是否有效
        
        Returns:
            bool: 配置是否有效
        """
        pass
    
    @abstractmethod
    async def send_alert(self, message: AlertMessage) -> bool:
        """
        发送告警消息
        
        Args:
            message: 告警消息对象
            
        Returns:
            bool: 发送是否成功
        """
        pass
    
    def get_timeout(self) -> int:
        """
        获取超时时间
        
        Returns:
            int: 超时时间（秒）
        """
        return self.config.get('timeout', 10)
```

### AlertMessage

告警消息数据模型：

```python
@dataclass
class AlertMessage:
    """告警消息"""
    service_name: str                    # 服务名称
    service_type: str                    # 服务类型
    status: str                          # 状态: UP, DOWN, DEGRADED
    timestamp: datetime                  # 时间戳
    error_message: Optional[str] = None  # 错误信息
    response_time: Optional[float] = None # 响应时间
    metadata: Dict[str, Any] = None      # 元数据
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
```

### HTTPAlerter

HTTP告警器配置选项：

```python
config = {
    'url': 'https://webhook.example.com',  # Webhook URL
    'method': 'POST',                      # HTTP方法
    'timeout': 10,                         # 请求超时时间
    'max_retries': 3,                      # 最大重试次数
    'retry_delay': 1.0,                    # 重试延迟（秒）
    'retry_backoff': 2.0,                  # 指数退避倍数
    'headers': {                           # 请求头
        'Content-Type': 'application/json'
    },
    'template': '{"message": "{{service_name}} is {{status}}"}' # 消息模板
}
```

## 配置管理API

### ConfigManager

配置管理器提供配置文件的加载、验证和监控功能：

```python
class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_path: str):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self.config = {}
        self.last_modified = None
        self.logger = get_logger('config_manager')
    
    def load_config(self) -> Dict[str, Any]:
        """
        加载配置文件
        
        Returns:
            Dict[str, Any]: 配置内容
            
        Raises:
            ConfigError: 配置文件错误
        """
        pass
    
    def get_global_config(self) -> Dict[str, Any]:
        """获取全局配置"""
        return self.config.get('global', {})
    
    def get_services_config(self) -> Dict[str, Any]:
        """获取服务配置"""
        return self.config.get('services', {})
    
    def get_alerts_config(self) -> List[Dict[str, Any]]:
        """获取告警配置"""
        return self.config.get('alerts', [])
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        验证配置内容
        
        Args:
            config: 配置内容
            
        Returns:
            bool: 验证是否通过
        """
        pass
```

### ConfigWatcher

配置文件监控器，支持热更新：

```python
class ConfigWatcher:
    """配置文件监控器"""
    
    def __init__(self, config_manager: ConfigManager):
        """
        初始化配置监控器
        
        Args:
            config_manager: 配置管理器实例
        """
        self.config_manager = config_manager
        self.observer = None
        self.change_callbacks = []
        self.logger = get_logger('config_watcher')
    
    def add_change_callback(self, callback):
        """
        添加配置变更回调函数
        
        Args:
            callback: 回调函数，签名为 callback(old_config, new_config)
        """
        self.change_callbacks.append(callback)
    
    def start_watching(self):
        """开始监控配置文件"""
        pass
    
    def stop_watching(self):
        """停止监控配置文件"""
        pass
```

## 状态管理API

### StateManager

状态管理器负责跟踪服务状态变化：

```python
class StateManager:
    """状态管理器"""
    
    def __init__(self, state_file: Optional[str] = None):
        """
        初始化状态管理器
        
        Args:
            state_file: 状态持久化文件路径
        """
        self.state_file = state_file
        self.current_states = {}
        self.state_history = []
        self.logger = get_logger('state_manager')
    
    def update_state(self, result: HealthCheckResult) -> Optional[StateChange]:
        """
        更新服务状态
        
        Args:
            result: 健康检查结果
            
        Returns:
            StateChange: 状态变化事件，如果状态未变化返回None
        """
        pass
    
    def get_current_state(self, service_name: str) -> Optional[bool]:
        """
        获取服务当前状态
        
        Args:
            service_name: 服务名称
            
        Returns:
            bool: 服务状态，True为健康，False为不健康，None为未知
        """
        return self.current_states.get(service_name)
    
    def get_all_states(self) -> Dict[str, bool]:
        """获取所有服务的当前状态"""
        return self.current_states.copy()
    
    def get_state_history(self, service_name: Optional[str] = None, 
                         limit: int = 100) -> List[StateChange]:
        """
        获取状态变化历史
        
        Args:
            service_name: 服务名称，None表示所有服务
            limit: 返回记录数限制
            
        Returns:
            List[StateChange]: 状态变化历史
        """
        pass
```

### StateChange

状态变化事件数据模型：

```python
@dataclass
class StateChange:
    """状态变化事件"""
    service_name: str                    # 服务名称
    service_type: str                    # 服务类型
    old_state: Optional[bool]            # 旧状态
    new_state: bool                      # 新状态
    timestamp: datetime                  # 变化时间
    error_message: Optional[str] = None  # 错误信息
    response_time: Optional[float] = None # 响应时间
    metadata: Dict[str, Any] = None      # 元数据
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
```

## 扩展开发

### 添加新的服务类型

1. **创建检查器类**

```python
# health_monitor/checkers/my_service_checker.py
from .base import BaseHealthChecker
from .factory import register_checker
from ..models.health_check import HealthCheckResult

@register_checker('my_service')
class MyServiceChecker(BaseHealthChecker):
    """自定义服务检查器"""
    
    def validate_config(self) -> bool:
        """验证配置"""
        # 检查必需的配置项
        required_fields = ['host', 'port']
        for field in required_fields:
            if field not in self.config:
                self.logger.error(f"缺少必需配置: {field}")
                return False
        
        # 验证配置值
        port = self.config.get('port')
        if not isinstance(port, int) or port <= 0 or port > 65535:
            self.logger.error(f"无效的端口号: {port}")
            return False
        
        return True
    
    async def check_health(self) -> HealthCheckResult:
        """执行健康检查"""
        start_time = time.time()
        error_message = None
        is_healthy = False
        metadata = {}
        
        try:
            # 实现具体的健康检查逻辑
            host = self.config.get('host')
            port = self.config.get('port')
            timeout = self.get_timeout()
            
            # 例如：TCP连接测试
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout
            )
            
            # 发送测试数据
            writer.write(b'PING\r\n')
            await writer.drain()
            
            # 读取响应
            response = await asyncio.wait_for(
                reader.readline(),
                timeout=timeout
            )
            
            if response.strip() == b'PONG':
                is_healthy = True
                metadata['response'] = response.decode()
            else:
                error_message = f"意外的响应: {response}"
            
            writer.close()
            await writer.wait_closed()
            
        except asyncio.TimeoutError:
            error_message = "连接超时"
        except Exception as e:
            error_message = f"连接失败: {e}"
        
        response_time = time.time() - start_time
        
        return HealthCheckResult(
            service_name=self.name,
            service_type='my_service',
            is_healthy=is_healthy,
            response_time=response_time,
            error_message=error_message,
            metadata=metadata
        )
    
    async def close(self):
        """清理资源"""
        # 如果有需要清理的资源，在这里处理
        pass
```

2. **注册检查器**

检查器会通过 `@register_checker` 装饰器自动注册，无需额外步骤。

3. **配置示例**

```yaml
services:
  my-custom-service:
    type: my_service
    host: localhost
    port: 8080
    timeout: 10
    check_interval: 30
    # 自定义配置项
    custom_option: value
```

### 添加新的告警方式

1. **创建告警器类**

```python
# health_monitor/alerts/my_alerter.py
from .base import BaseAlerter
from ..models.health_check import AlertMessage

class MyAlerter(BaseAlerter):
    """自定义告警器"""
    
    def validate_config(self) -> bool:
        """验证配置"""
        required_fields = ['api_key', 'channel']
        for field in required_fields:
            if field not in self.config:
                self.logger.error(f"缺少必需配置: {field}")
                return False
        return True
    
    async def send_alert(self, message: AlertMessage) -> bool:
        """发送告警"""
        try:
            api_key = self.config.get('api_key')
            channel = self.config.get('channel')
            
            # 实现具体的告警发送逻辑
            alert_data = {
                'channel': channel,
                'message': f"服务 {message.service_name} 状态: {message.status}",
                'timestamp': message.timestamp.isoformat(),
                'error': message.error_message
            }
            
            # 发送告警（示例）
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://api.example.com/alerts',
                    headers={'Authorization': f'Bearer {api_key}'},
                    json=alert_data,
                    timeout=self.get_timeout()
                ) as response:
                    return response.status == 200
                    
        except Exception as e:
            self.logger.error(f"发送告警失败: {e}")
            return False
```

2. **在告警管理器中注册**

```python
# 在 AlertManager 中添加对新告警器的支持
from .my_alerter import MyAlerter

class AlertManager:
    def _create_alerter(self, alert_config: Dict[str, Any]) -> BaseAlerter:
        """创建告警器实例"""
        alert_type = alert_config.get('type')
        alert_name = alert_config.get('name', 'unnamed')
        
        if alert_type == 'http':
            return HTTPAlerter(alert_name, alert_config)
        elif alert_type == 'my_alert':
            return MyAlerter(alert_name, alert_config)
        else:
            raise ValueError(f"不支持的告警类型: {alert_type}")
```

### 自定义模板变量

可以在告警模板中添加自定义变量：

```python
class AlertManager:
    def render_template(self, template: str, message: AlertMessage) -> str:
        """渲染告警模板"""
        variables = {
            'service_name': message.service_name,
            'service_type': message.service_type,
            'status': message.status,
            'timestamp': message.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'error_message': message.error_message or '',
            'response_time': int(message.response_time * 1000) if message.response_time else 0,
            'metadata_json': json.dumps(message.metadata, ensure_ascii=False),
            
            # 自定义变量
            'hostname': socket.gethostname(),
            'environment': os.getenv('ENVIRONMENT', 'unknown'),
            'alert_level': self._get_alert_level(message),
        }
        
        # 使用简单的字符串替换
        rendered = template
        for key, value in variables.items():
            rendered = rendered.replace(f'{{{{{key}}}}}', str(value))
        
        return rendered
```

### 插件系统

可以通过插件系统动态加载扩展：

```python
# health_monitor/plugins/__init__.py
import importlib
import pkgutil

def load_plugins():
    """动态加载插件"""
    plugin_modules = []
    
    # 扫描插件目录
    for finder, name, ispkg in pkgutil.iter_modules(__path__):
        try:
            module = importlib.import_module(f'health_monitor.plugins.{name}')
            plugin_modules.append(module)
        except ImportError as e:
            logger.warning(f"加载插件失败: {name}, 错误: {e}")
    
    return plugin_modules
```

这样就可以通过插件的方式扩展系统功能，而不需要修改核心代码。