"""统计查询命令 - /limit_stats"""

from astrbot.api.event import AstrMessageEvent, filter

from ..database.connection import DatabaseConnection


class StatsCommand:
    """统计查询命令处理器"""

    def __init__(self, db_connection: DatabaseConnection):
        """
        初始化统计查询命令处理器

        Args:
            db_connection: 数据库连接管理器
        """
        self.db_connection = db_connection

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_stats")
    async def limit_stats(
        self, event: AstrMessageEvent, identity_id: str | None = None
    ):
        """查看统计 /limit_stats [用户ID|群ID]"""
        platform = str(event.platform)

        db = await self.db_connection.get_connection()
        if identity_id:
            async with db.execute(
                """SELECT user_id, group_id, use_date, use_count, identity_type
                   FROM ai_usage
                   WHERE (user_id = ? OR group_id = ?) AND platform = ?
                   ORDER BY use_date DESC, use_count DESC""",
                (identity_id, identity_id, platform),
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with db.execute(
                """SELECT user_id, group_id, use_date, use_count, identity_type
                   FROM ai_usage
                   WHERE platform = ?
                   ORDER BY use_date DESC, use_count DESC
                   LIMIT 50""",
                (platform,),
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            yield event.plain_result("📊 暂无使用记录")
            return

        result = "📊 使用统计\n━━━━━━━━━━━━━\n"
        # 限制显示条数,避免消息过长
        max_display = 20
        for user_id, group_id, use_date, use_count, identity_type in rows[:max_display]:
            if identity_type == "group":
                result += f"群组 {group_id} "
            else:
                result += f"用户 {user_id} "
                if group_id:
                    result += f"(群 {group_id}) "
            result += f"- {use_date}: {use_count} 次\n"

        if len(rows) > max_display:
            result += f"\n... 还有 {len(rows) - max_display} 条记录未显示"

        yield event.plain_result(result)
