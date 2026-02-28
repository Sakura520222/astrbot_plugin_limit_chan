"""群组配置命令 - /limit_group"""

from astrbot.api.event import AstrMessageEvent, filter

from ..database.connection import DatabaseConnection


class GroupCommand:
    """群组配置命令处理器"""

    def __init__(self, db_connection: DatabaseConnection):
        """
        初始化群组配置命令处理器

        Args:
            db_connection: 数据库连接管理器
        """
        self.db_connection = db_connection

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_group")
    async def limit_group(
        self,
        event: AstrMessageEvent,
        group_id: str,
        limit: int,
        mode: str = "individual",
    ):
        """设置群组配置 /limit_group <群ID> <limit> [mode]"""
        platform = str(event.platform)

        if mode not in ["individual", "shared"]:
            yield event.plain_result("❌ 模式必须是 individual 或 shared")
            return

        db = await self.db_connection.get_connection()
        await db.execute(
            """
            INSERT OR REPLACE INTO group_config
            (group_id, platform, daily_limit, mode, enabled)
            VALUES (?, ?, ?, ?, 1)
        """,
            (group_id, platform, limit, mode),
        )
        await db.commit()

        yield event.plain_result(
            f"✅ 群组 {group_id} 配置已更新\n限制: {limit} 次/天\n模式: {mode}"
        )
