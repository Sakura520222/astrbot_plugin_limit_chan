"""白名单管理命令 - /limit_whitelist_add/remove/list"""

from datetime import datetime

from astrbot.api.event import AstrMessageEvent, filter

from ..database.connection import DatabaseConnection


class WhitelistCommands:
    """白名单管理命令处理器"""

    def __init__(self, db_connection: DatabaseConnection):
        """
        初始化白名单管理命令处理器

        Args:
            db_connection: 数据库连接管理器
        """
        self.db_connection = db_connection

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_whitelist_add")
    async def whitelist_add(self, event: AstrMessageEvent, user_id: str):
        """添加白名单 /limit_whitelist_add <用户ID>"""
        platform = str(event.platform)
        now = int(datetime.now().timestamp())

        db = await self.db_connection.get_connection()
        async with await db.execute(
            "INSERT OR IGNORE INTO whitelist (user_id, platform, add_time) VALUES (?, ?, ?)",
            (user_id, platform, now),
        ):
            pass
        await db.commit()

        yield event.plain_result(f"✅ 用户 {user_id} 已添加到白名单")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_whitelist_remove")
    async def whitelist_remove(self, event: AstrMessageEvent, user_id: str):
        """移除白名单 /limit_whitelist_remove <用户ID>"""
        platform = str(event.platform)

        db = await self.db_connection.get_connection()
        async with await db.execute(
            "DELETE FROM whitelist WHERE user_id = ? AND platform = ?",
            (user_id, platform),
        ):
            pass
        await db.commit()

        yield event.plain_result(f"✅ 用户 {user_id} 已从白名单移除")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_whitelist_list")
    async def whitelist_list(self, event: AstrMessageEvent):
        """查看白名单 /limit_whitelist_list"""
        platform = str(event.platform)

        db = await self.db_connection.get_connection()
        async with db.execute(
            "SELECT user_id FROM whitelist WHERE platform = ?", (platform,)
        ) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            yield event.plain_result("📋 白名单为空")
            return

        result = "📋 白名单列表\n━━━━━━━━━━━━━\n"
        # 限制显示条数,避免消息过长
        max_display = 20
        for i, (user_id,) in enumerate(rows[:max_display], 1):
            result += f"{i}. {user_id}\n"

        if len(rows) > max_display:
            result += f"\n... 还有 {len(rows) - max_display} 条记录未显示"

        yield event.plain_result(result)
