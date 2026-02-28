"""用户配置命令 - /limit_user"""

from astrbot.api.event import AstrMessageEvent, filter

from ..database.connection import DatabaseConnection


class UserCommand:
    """用户配置命令处理器"""

    def __init__(self, db_connection: DatabaseConnection):
        """
        初始化用户配置命令处理器

        Args:
            db_connection: 数据库连接管理器
        """
        self.db_connection = db_connection

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_user")
    async def limit_user(self, event: AstrMessageEvent, user_id: str, limit: int):
        """设置用户配置 /limit_user <用户ID> <limit>"""
        platform = str(event.platform)

        db = await self.db_connection.get_connection()
        async with await db.execute(
            """
            INSERT OR REPLACE INTO user_config
            (user_id, platform, daily_limit, enabled)
            VALUES (?, ?, ?, 1)
        """,
            (user_id, platform, limit),
        ):
            pass
        await db.commit()

        yield event.plain_result(
            f"✅ 用户 {user_id} 配置已更新\n限制: {limit} 次/天（独立模式）"
        )
