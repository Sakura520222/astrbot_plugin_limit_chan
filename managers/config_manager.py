"""配置管理器 - 从配置文件读取黑名单、白名单、用户/群组配置"""

import json
import logging
from typing import Any

from astrbot.api import AstrBotConfig

from ..database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


def _parse_json_config(value: Any, default: Any = None) -> Any:
    """
    解析配置中的 JSON 字符串
    
    Args:
        value: 配置值（可能是字符串或字典）
        default: 默认值
        
    Returns:
        解析后的值
    """
    if value is None:
        return default
    
    # 如果已经是字典/列表，直接返回
    if isinstance(value, (dict, list)):
        return value
    
    # 如果是字符串，尝试解析 JSON
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"无法解析 JSON 配置: {value}")
            return default
    
    return default


class ConfigManager:
    """配置管理器 - 从配置文件读取所有配置"""

    def __init__(self, db_connection: DatabaseConnection, config: AstrBotConfig = None):
        """
        初始化配置管理器

        Args:
            db_connection: 数据库连接管理器
            config: 插件配置
        """
        self.db_connection = db_connection
        self.config = config or {}

    async def get_global_config(self, key: str, default: Any = None) -> Any:
        """
        获取全局配置（优先级：配置文件 > 数据库 > 默认值）

        Args:
            key: 配置键
            default: 默认值

        Returns:
            配置值
        """
        # 优先从配置文件读取
        if self.config and key in self.config:
            return self.config[key]

        # 其次从数据库读取（兼容旧数据）
        db = await self.db_connection.get_connection()
        async with db.execute(
            "SELECT value FROM global_config WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]

        # 最后使用默认值
        return default

    async def set_global_config(self, key: str, value: str):
        """
        设置全局配置到数据库

        Args:
            key: 配置键
            value: 配置值
        """
        db = await self.db_connection.get_connection()
        await db.execute(
            "INSERT OR REPLACE INTO global_config (key, value) VALUES (?, ?)",
            (key, str(value)),
        )
        await db.commit()

    def is_blacklisted(self, user_id: str, platform: str) -> bool:
        """
        检查是否在黑名单（从配置文件读取）

        Args:
            user_id: 用户ID
            platform: 平台（暂未使用，保留用于未来扩展）

        Returns:
            是否在黑名单中
        """
        if not self.config:
            return False

        blacklist = self.config.get("blacklist", [])
        return user_id in blacklist

    def is_whitelisted(self, user_id: str, platform: str) -> bool:
        """
        检查是否在白名单（从配置文件读取）

        Args:
            user_id: 用户ID
            platform: 平台（暂未使用，保留用于未来扩展）

        Returns:
            是否在白名单中
        """
        if not self.config:
            return False

        whitelist = self.config.get("whitelist", [])
        return user_id in whitelist

    def get_user_config(self, user_id: str, platform: str) -> dict[str, Any] | None:
        """
        获取用户配置（从配置文件读取）

        Args:
            user_id: 用户ID
            platform: 平台

        Returns:
            用户配置字典或None
        """
        if not self.config:
            return None

        user_configs = _parse_json_config(self.config.get("user_configs", {}), {})
        if not user_configs or platform not in user_configs:
            return None

        return user_configs[platform].get(user_id)

    def get_group_config(self, group_id: str, platform: str) -> dict[str, Any] | None:
        """
        获取群组配置（从配置文件读取）

        Args:
            group_id: 群组ID
            platform: 平台

        Returns:
            群组配置字典或None
        """
        if not self.config:
            return None

        group_configs = _parse_json_config(self.config.get("group_configs", {}), {})
        if not group_configs or platform not in group_configs:
            return None

        return group_configs[platform].get(group_id)

    async def invalidate_user_cache(self, user_id: str, platform: str):
        """
        清除用户相关缓存（已废弃，配置文件无需缓存）

        Args:
            user_id: 用户ID
            platform: 平台
        """
        # 配置文件模式无需缓存，此方法保留以兼容
        pass

    async def invalidate_group_cache(self, group_id: str, platform: str):
        """
        清除群组相关缓存（已废弃，配置文件无需缓存）

        Args:
            group_id: 群组ID
            platform: 平台
        """
        # 配置文件模式无需缓存，此方法保留以兼容
        pass