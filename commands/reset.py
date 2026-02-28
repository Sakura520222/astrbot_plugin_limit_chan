"""重置计数命令 - /limit_reset"""

from astrbot.api.event import AstrMessageEvent, filter

from ..database.connection import DatabaseConnection


class ResetCommand:
    """重置计数命令处理器"""

    def __init__(self, db_connection: DatabaseConnection):
        """
        初始化重置计数命令处理器

        Args:
            db_connection: 数据库连接管理器
        """
        self.db_connection = db_connection

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_reset")
    async def limit_reset(self, event: AstrMessageEvent, identity_id: str):
        """重置计数 /limit_reset <用户ID|群ID>"""
        platform = str(event.platform)

        db = await self.db_connection.get_connection()
        cursor = await db.execute(
            "DELETE FROM ai_usage WHERE (user_id = ? OR group_id = ?) AND platform = ?",
            (identity_id, identity_id, platform),
        )
        deleted = cursor.rowcount
        await db.commit()

        if deleted > 0:
            yield event.plain_result(f"✅ 已重置 {identity_id} 的使用计数")
        else:
            yield event.plain_result(f"⚠️ 未找到 {identity_id} 的使用记录")
