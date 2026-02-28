"""缓存管理器 - 提供内存缓存功能以减少数据库查询"""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


class CacheEntry:
    """缓存条目"""

    def __init__(self, value: T, ttl: float = 300):
        """
        初始化缓存条目

        Args:
            value: 缓存值
            ttl: 生存时间（秒），默认5分钟
        """
        self.value = value
        self.expires_at = datetime.now() + timedelta(seconds=ttl)

    def is_expired(self) -> bool:
        """检查是否过期"""
        return datetime.now() > self.expires_at


class CacheManager:
    """缓存管理器 - 使用 LRU 策略和 TTL"""

    def __init__(self, max_size: int = 1000, default_ttl: float = 300):
        """
        初始化缓存管理器

        Args:
            max_size: 最大缓存条目数
            default_ttl: 默认生存时间（秒），默认5分钟
        """
        self._cache: dict[str, CacheEntry] = {}
        self._access_order: list[str] = []  # 用于 LRU
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()

    def _make_key(self, *args) -> str:
        """生成缓存键"""
        return ":".join(str(arg) for arg in args)

    async def get(self, *args) -> T | None:
        """
        获取缓存值

        Args:
            *args: 缓存键的组成部分

        Returns:
            缓存值，如果不存在或已过期则返回 None
        """
        key = self._make_key(*args)

        async with self._lock:
            if key not in self._cache:
                return None

            entry = self._cache[key]

            # 检查是否过期
            if entry.is_expired():
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
                return None

            # 更新访问顺序（LRU）
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)

            return entry.value

    async def set(self, value: T, *args, ttl: float | None = None):
        """
        设置缓存值

        Args:
            value: 要缓存的值
            *args: 缓存键的组成部分
            ttl: 生存时间（秒），None 表示使用默认值
        """
        key = self._make_key(*args)
        ttl = ttl if ttl is not None else self._default_ttl

        async with self._lock:
            # 如果缓存已满，移除最旧的条目
            if key not in self._cache and len(self._cache) >= self._max_size:
                oldest_key = self._access_order.pop(0)
                if oldest_key in self._cache:
                    del self._cache[oldest_key]

            # 添加或更新缓存
            self._cache[key] = CacheEntry(value, ttl)

            # 更新访问顺序
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)

    async def delete(self, *args):
        """
        删除缓存值

        Args:
            *args: 缓存键的组成部分
        """
        key = self._make_key(*args)

        async with self._lock:
            if key in self._cache:
                del self._cache[key]
            if key in self._access_order:
                self._access_order.remove(key)

    async def clear_pattern(self, pattern: str):
        """
        清除匹配模式的缓存

        Args:
            pattern: 要匹配的模式（简单的字符串包含匹配）
        """
        async with self._lock:
            keys_to_delete = [key for key in self._cache if pattern in key]
            for key in keys_to_delete:
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)

            if keys_to_delete:
                logger.debug(f"清除了 {len(keys_to_delete)} 个匹配 '{pattern}' 的缓存")

    async def clear_all(self):
        """清除所有缓存"""
        async with self._lock:
            self._cache.clear()
            self._access_order.clear()
            logger.debug("已清除所有缓存")

    async def get_stats(self) -> dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            包含缓存统计的字典
        """
        async with self._lock:
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "expired_count": sum(
                    1 for entry in self._cache.values() if entry.is_expired()
                ),
            }


def cached(
    cache_manager: CacheManager,
    ttl: float | None = None,
    key_factory: Callable[..., tuple] | None = None,
):
    """
    缓存装饰器

    Args:
        cache_manager: 缓存管理器实例
        ttl: 生存时间（秒），None 表示使用默认值
        key_factory: 生成缓存键的函数，接收函数参数，返回键元组

    Returns:
        装饰器函数
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # 生成缓存键
            if key_factory:
                cache_key = key_factory(*args, **kwargs)
            else:
                # 默认使用函数名和参数作为键
                cache_key = (func.__name__,) + args + tuple(sorted(kwargs.items()))

            # 尝试从缓存获取
            cached_value = await cache_manager.get(*cache_key)
            if cached_value is not None:
                return cached_value

            # 缓存未命中，调用原函数
            result = await func(*args, **kwargs)

            # 存入缓存
            await cache_manager.set(result, *cache_key, ttl=ttl)

            return result

        return wrapper

    return decorator
