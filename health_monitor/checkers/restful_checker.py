"""RESTful接口健康检查器"""

import time
import json
from typing import Dict, Any, Optional, List
import aiohttp
from .base import BaseHealthChecker
from .factory import register_checker
from ..models.health_check import HealthCheckResult
from ..utils.exceptions import CheckerError


@register_checker('restful')
class RestfulHealthChecker(BaseHealthChecker):
    """RESTful接口健康检查器"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        初始化RESTful健康检查器
        
        Args:
            name: 服务名称
            config: RESTful配置
        """
        super().__init__(name, config)
    
    def validate_config(self) -> bool:
        """
        验证RESTful配置
        
        Returns:
            bool: 配置是否有效
        """
        required_fields = ['url']
        for field in required_fields:
            if field not in self.config:
                return False
        
        # 验证URL格式
        url = self.config.get('url')
        if not isinstance(url, str) or not url.startswith(('http://', 'https://')):
            return False
        
        # 验证HTTP方法
        method = self.config.get('method', 'GET')
        if method not in ['GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS', 'PATCH']:
            return False
        
        # 验证期望状态码
        expected_status = self.config.get('expected_status', 200)
        if not isinstance(expected_status, (int, list)):
            return False
        
        if isinstance(expected_status, list):
            for status in expected_status:
                if not isinstance(status, int) or status < 100 or status > 599:
                    return False
        elif not (100 <= expected_status <= 599):
            return False
        
        return True
    
    def _is_status_expected(self, status_code: int) -> bool:
        """
        检查状态码是否符合期望
        
        Args:
            status_code: HTTP状态码
            
        Returns:
            bool: 是否符合期望
        """
        expected_status = self.config.get('expected_status', 200)
        
        if isinstance(expected_status, list):
            return status_code in expected_status
        else:
            return status_code == expected_status
    
    def _validate_response_content(self, content: str, content_type: str) -> tuple[bool, Dict[str, Any]]:
        """
        验证响应内容
        
        Args:
            content: 响应内容
            content_type: 内容类型
            
        Returns:
            tuple: (验证是否通过, 验证元数据)
        """
        metadata = {}
        
        # 检查响应内容长度
        content_length = len(content)
        metadata['response_length'] = content_length
        
        # 可选：验证响应内容包含特定字符串
        expected_content = self.config.get('expected_content')
        if expected_content:
            if isinstance(expected_content, str):
                contains_expected = expected_content in content
                metadata['content_validation'] = 'passed' if contains_expected else 'failed'
                if not contains_expected:
                    return False, metadata
            elif isinstance(expected_content, list):
                for expected in expected_content:
                    if expected not in content:
                        metadata['content_validation'] = 'failed'
                        metadata['missing_content'] = expected
                        return False, metadata
                metadata['content_validation'] = 'passed'
        
        # 可选：验证JSON响应格式
        if self.config.get('validate_json', False) and 'json' in content_type.lower():
            try:
                json_data = json.loads(content)
                metadata['json_validation'] = 'passed'
                metadata['json_keys'] = list(json_data.keys()) if isinstance(json_data, dict) else None
                
                # 可选：验证JSON字段
                required_json_fields = self.config.get('required_json_fields', [])
                if required_json_fields and isinstance(json_data, dict):
                    missing_fields = []
                    for field in required_json_fields:
                        if field not in json_data:
                            missing_fields.append(field)
                    
                    if missing_fields:
                        metadata['json_validation'] = 'failed'
                        metadata['missing_json_fields'] = missing_fields
                        return False, metadata
                    else:
                        metadata['json_fields_validation'] = 'passed'
                        
            except json.JSONDecodeError as e:
                metadata['json_validation'] = 'failed'
                metadata['json_error'] = str(e)
                return False, metadata
        
        return True, metadata
    
    async def check_health(self) -> HealthCheckResult:
        """
        执行RESTful接口健康检查
        
        Returns:
            HealthCheckResult: 健康检查结果
        """
        start_time = time.time()
        error_message = None
        is_healthy = False
        metadata = {}
        
        try:
            url = self.config.get('url')
            method = self.config.get('method', 'GET').upper()
            headers = self.config.get('headers', {})
            data = self.config.get('data')
            json_data = self.config.get('json')
            params = self.config.get('params', {})
            
            # 设置超时
            timeout = aiohttp.ClientTimeout(total=self.get_timeout())
            
            # 可选：设置认证
            auth = None
            if 'auth_username' in self.config and 'auth_password' in self.config:
                auth = aiohttp.BasicAuth(
                    self.config['auth_username'],
                    self.config['auth_password']
                )
            
            async with aiohttp.ClientSession(timeout=timeout, auth=auth) as session:
                # 准备请求参数
                request_kwargs = {
                    'headers': headers,
                    'params': params
                }
                
                if data is not None:
                    request_kwargs['data'] = data
                elif json_data is not None:
                    request_kwargs['json'] = json_data
                
                # 发送HTTP请求
                request_start = time.time()
                async with session.request(method, url, **request_kwargs) as response:
                    request_time = time.time() - request_start
                    metadata['request_time'] = request_time
                    metadata['status_code'] = response.status
                    metadata['response_headers'] = dict(response.headers)
                    
                    # 检查状态码
                    if self._is_status_expected(response.status):
                        # 读取响应内容
                        content_start = time.time()
                        content = await response.text()
                        content_time = time.time() - content_start
                        metadata['content_read_time'] = content_time
                        
                        # 验证响应内容
                        content_type = response.headers.get('content-type', '')
                        content_valid, content_metadata = self._validate_response_content(content, content_type)
                        metadata.update(content_metadata)
                        
                        if content_valid:
                            is_healthy = True
                            
                            # 可选：收集响应统计信息
                            if self.config.get('collect_response_stats', False):
                                metadata['content_type'] = content_type
                                metadata['response_size'] = len(content)
                                
                                # 尝试解析JSON以获取更多信息
                                if 'json' in content_type.lower():
                                    try:
                                        json_data = json.loads(content)
                                        if isinstance(json_data, dict):
                                            metadata['json_object_keys'] = len(json_data.keys())
                                        elif isinstance(json_data, list):
                                            metadata['json_array_length'] = len(json_data)
                                    except json.JSONDecodeError:
                                        pass
                        else:
                            error_message = "响应内容验证失败"
                    else:
                        error_message = f"HTTP状态码不符合期望: {response.status}"
                        
        except aiohttp.ClientError as e:
            error_message = f"HTTP客户端错误: {e}"
        except asyncio.TimeoutError:
            error_message = "HTTP请求超时"
        except Exception as e:
            error_message = f"RESTful健康检查异常: {e}"
        
        response_time = time.time() - start_time
        
        return HealthCheckResult(
            service_name=self.name,
            service_type='restful',
            is_healthy=is_healthy,
            response_time=response_time,
            error_message=error_message,
            metadata=metadata
        )
    
    async def close(self):
        """关闭RESTful连接（无需特殊处理）"""
        pass