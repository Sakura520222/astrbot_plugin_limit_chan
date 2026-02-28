"""配置管理器 - 处理全局、用户、群组配置及黑白名单"""

from typing import Any

from astrbot.api import AstrBotConfig

from ..database.connection import DatabaseConnection


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

    async def get_global_config(self, key: str, default: Any = None) -> Any:
        """
        获取全局配置（优先从配置文件读取，其次从数据库）

        Args:
            key: 配置键
            default: 默认值

        Returns:
            配置值
        """
        # 先从配置文件读取
        if self.config and key in self.config:
            return self.config[key]

        # 从数据库读取
        db = await self.db_connection.get_connection()
        async with db.execute(
            "SELECT value FROM global_config WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
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

        db = await self.db_connection.get_connection()
        async with db.execute(
            "SELECT 1 FROM blacklist WHERE user_id = ? AND platform = ?",
            (user_id, platform),
        ) as cursor:
            return await cursor.fetchone() is not None

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

        db = await self.db_connection.get_connection()
        async with db.execute(
            "SELECT 1 FROM whitelist WHERE user_id = ? AND platform = ?",
            (user_id, platform),
        ) as cursor:
            return await cursor.fetchone() is not None

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
        db = await self.db_connection.get_connection()
        async with db.execute(
            """SELECT daily_limit, enabled FROM user_config
               WHERE user_id = ? AND platform = ?""",
            (user_id, platform),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"daily_limit": row[0], "enabled": row[1]}
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
        db = await self.db_connection.get_connection()
        async with db.execute(
            """SELECT daily_limit, mode, enabled FROM group_config
               WHERE group_id = ? AND platform = ?""",
            (group_id, platform),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"daily_limit": row[0], "mode": row[1], "enabled": row[2]}
            return None
