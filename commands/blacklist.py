"""黑名单管理命令 - /limit_blacklist_add/remove/list"""

from datetime import datetime

from astrbot.api.event import AstrMessageEvent, filter

from ..database.connection import DatabaseConnection


class BlacklistCommands:
    """黑名单管理命令处理器"""

    def __init__(self, db_connection: DatabaseConnection):
        """
        初始化黑名单管理命令处理器

        Args:
            db_connection: 数据库连接管理器
        """
        self.db_connection = db_connection

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_blacklist_add")
    async def blacklist_add(
        self, event: AstrMessageEvent, user_id: str, reason: str = ""
    ):
        """添加黑名单 /limit_blacklist_add <用户ID> [理由]"""
        platform = str(event.platform)
        now = int(datetime.now().timestamp())

        db = await self.db_connection.get_connection()
        async with await db.execute(
            """
            INSERT OR REPLACE INTO blacklist
            (user_id, platform, add_time, reason)
            VALUES (?, ?, ?, ?)
        """,
            (user_id, platform, now, reason),
        ):
            pass
        await db.commit()

        yield event.plain_result(f"✅ 用户 {user_id} 已添加到黑名单")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_blacklist_remove")
    async def blacklist_remove(self, event: AstrMessageEvent, user_id: str):
        """移除黑名单 /limit_blacklist_remove <用户ID>"""
        platform = str(event.platform)

        db = await self.db_connection.get_connection()
        async with await db.execute(
            "DELETE FROM blacklist WHERE user_id = ? AND platform = ?",
            (user_id, platform),
        ):
            pass
        await db.commit()

        yield event.plain_result(f"✅ 用户 {user_id} 已从黑名单移除")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_blacklist_list")
    async def blacklist_list(self, event: AstrMessageEvent):
        """查看黑名单 /limit_blacklist_list"""
        platform = str(event.platform)

        db = await self.db_connection.get_connection()
        async with db.execute(
            "SELECT user_id, reason FROM blacklist WHERE platform = ?", (platform,)
        ) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            yield event.plain_result("📋 黑名单为空")
            return

        result = "📋 黑名单列表\n━━━━━━━━━━━━━\n"
        # 限制显示条数,避免消息过长
        max_display = 20
        for i, (user_id, reason) in enumerate(rows[:max_display], 1):
            result += f"{i}. {user_id}"
            if reason:
                result += f" ({reason})"
            result += "\n"

        if len(rows) > max_display:
            result += f"\n... 还有 {len(rows) - max_display} 条记录未显示"

        yield event.plain_result(result)
