"""配置管理器 - 处理全局、用户、群组配置及黑白名单"""

from typing import Any

from astrbot.api import AstrBotConfig

from ..database.connection import DatabaseConnection
from .cache_manager import CacheManager


class ConfigManager:
    """配置管理器"""

    def __init__(self, db_connection: DatabaseConnection, config: AstrBotConfig = None):
        """
        初始化配置管理器

        Args:
            db_connection: 数据库连接管理器
            config: 插件配置
        """
        self.db_connection = db_connection
        self.config = config or {}

        # 初始化缓存管理器
        # 黑白名单和配置数据缓存5分钟
        self.cache = CacheManager(max_size=2000, default_ttl=300)

    async def get_global_config(self, key: str, default: Any = None) -> Any:
        """
        获取全局配置（优先级：缓存 > 数据库 > 配置文件 > 默认值）

        Args:
            key: 配置键
            default: 默认值

        Returns:
            配置值
        """
        # 先从缓存读取
        cached_value = await self.cache.get("global", key)
        if cached_value is not None:
            return cached_value

        # 缓存未命中，从数据库读取
        db = await self.db_connection.get_connection()
        async with db.execute(
            "SELECT value FROM global_config WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                value = row[0]
                await self.cache.set(value, "global", key)
                return value

        # 其次从配置文件读取
        if self.config and key in self.config:
            value = self.config[key]
            await self.cache.set(value, "global", key)
            return value

        # 最后使用默认值
        return default

    async def set_global_config(self, key: str, value: str):
        """
        设置全局配置

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

        # 清除相关缓存
        await self.cache.delete("global", key)

    async def is_blacklisted(self, user_id: str, platform: str) -> bool:
        """
        检查是否在黑名单

        Args:
            user_id: 用户ID
            platform: 平台

        Returns:
            是否在黑名单中
        """
        # 检查配置文件中是否启用了黑名单功能
        if self.config and not self.config.get("enable_blacklist", True):
            return False

        # 先从缓存读取
        cached_value = await self.cache.get("blacklist", user_id, platform)
        if cached_value is not None:
            return cached_value

        # 缓存未命中，从数据库读取
        db = await self.db_connection.get_connection()
        async with db.execute(
            "SELECT 1 FROM blacklist WHERE user_id = ? AND platform = ?",
            (user_id, platform),
        ) as cursor:
            result = await cursor.fetchone() is not None
            # 缓存结果
            await self.cache.set(result, "blacklist", user_id, platform)
            return result

    async def is_whitelisted(self, user_id: str, platform: str) -> bool:
        """
        检查是否在白名单

        Args:
            user_id: 用户ID
            platform: 平台

        Returns:
            是否在白名单中
        """
        # 检查配置文件中是否启用了白名单功能
        if self.config and not self.config.get("enable_whitelist", True):
            return False

        # 先从缓存读取
        cached_value = await self.cache.get("whitelist", user_id, platform)
        if cached_value is not None:
            return cached_value

        # 缓存未命中，从数据库读取
        db = await self.db_connection.get_connection()
        async with db.execute(
            "SELECT 1 FROM whitelist WHERE user_id = ? AND platform = ?",
            (user_id, platform),
        ) as cursor:
            result = await cursor.fetchone() is not None
            # 缓存结果
            await self.cache.set(result, "whitelist", user_id, platform)
            return result

    async def get_user_config(
        self, user_id: str, platform: str
    ) -> dict[str, Any] | None:
        """
        获取用户配置

        Args:
            user_id: 用户ID
            platform: 平台

        Returns:
            用户配置字典或None
        """
        # 先从缓存读取
        cached_value = await self.cache.get("user_config", user_id, platform)
        if cached_value is not None:
            return cached_value if cached_value else None

        # 缓存未命中，从数据库读取
        db = await self.db_connection.get_connection()
        async with db.execute(
            """SELECT daily_limit, enabled FROM user_config
               WHERE user_id = ? AND platform = ?""",
            (user_id, platform),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                result = {"daily_limit": row[0], "enabled": row[1]}
                await self.cache.set(result, "user_config", user_id, platform)
                return result
            # 缓存空结果以避免重复查询
            await self.cache.set(False, "user_config", user_id, platform)
            return None

    async def get_group_config(
        self, group_id: str, platform: str
    ) -> dict[str, Any] | None:
        """
        获取群组配置

        Args:
            group_id: 群组ID
            platform: 平台

        Returns:
            群组配置字典或None
        """
        # 先从缓存读取
        cached_value = await self.cache.get("group_config", group_id, platform)
        if cached_value is not None:
            return cached_value if cached_value else None

        # 缓存未命中，从数据库读取
        db = await self.db_connection.get_connection()
        async with db.execute(
            """SELECT daily_limit, mode, enabled FROM group_config
               WHERE group_id = ? AND platform = ?""",
            (group_id, platform),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                result = {"daily_limit": row[0], "mode": row[1], "enabled": row[2]}
                await self.cache.set(result, "group_config", group_id, platform)
                return result
            # 缓存空结果以避免重复查询
            await self.cache.set(False, "group_config", group_id, platform)
            return None

    async def invalidate_user_cache(self, user_id: str, platform: str):
        """
        清除用户相关缓存

        Args:
            user_id: 用户ID
            platform: 平台
        """
        await self.cache.delete("blacklist", user_id, platform)
        await self.cache.delete("whitelist", user_id, platform)
        await self.cache.delete("user_config", user_id, platform)

    async def invalidate_group_cache(self, group_id: str, platform: str):
        """
        清除群组相关缓存

        Args:
            group_id: 群组ID
            platform: 平台
        """
        await self.cache.delete("group_config", group_id, platform)
