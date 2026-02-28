"""
AstrBot AI 使用次数限制插件
支持黑名单、白名单、用户/群组/全局配置、独立/共享模式
"""

import asyncio
from datetime import datetime

from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, StarTools

from .database.connection import DatabaseConnection
from .database.models import DatabaseModels
from .handlers.interceptors import LLMInterceptor
from .managers.config_manager import ConfigManager
from .managers.permission import PermissionManager
from .managers.usage_manager import UsageManager


class LimitLimiter(Star):
    """限定酱 - AI使用次数管理助手✨"""

    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}

        # 初始化数据库路径
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_limit_chan")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "astrbot_plugin_limit_chan.db"

        # 初始化数据库层
        self.db_connection = DatabaseConnection(self.db_path)
        self.db_models = DatabaseModels(self.db_connection, self.config)

        # 初始化业务逻辑层
        self.config_manager = ConfigManager(self.db_connection, self.config)
        self.permission_manager = PermissionManager(self.config_manager)
        self.usage_manager = UsageManager(self.db_connection)

        # 初始化事件处理器
        self.llm_interceptor = LLMInterceptor(
            self.permission_manager,
            self.usage_manager,
        )

    async def on_wakeup(self):
        """插件启动时初始化数据库"""
        await self.db_models.init_db()

    async def cog_unload(self):
        """插件卸载时清理资源"""
        # 关闭数据库连接
        await self.db_connection.close()

        # 等待所有后台任务完成
        if hasattr(self.llm_interceptor, "background_tasks"):
            tasks = self.llm_interceptor.background_tasks
            if tasks:
                for task in list(tasks):
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                tasks.clear()

    # ==================== 事件处理器 ====================

    @filter.on_llm_request(priority=10)
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        """拦截 LLM 请求"""
        await self.llm_interceptor.on_llm_request(event, req)

    # ==================== 查询命令 ====================

    @filter.command("limit")
    async def query_limit(self, event: AstrMessageEvent):
        """查询当前使用情况"""
        user_id = event.get_sender_id()
        platform = str(event.platform)
        group_id = event.message_obj.group_id or ""

        # 获取权限配置
        allowed, limit, mode, source = await self.permission_manager.check_permission(
            user_id, platform, group_id
        )

        # 黑名单
        if not allowed:
            yield event.plain_result("❌ 您已被限制使用 AI 功能")
            return

        # 白名单
        if limit == -1:
            yield event.plain_result("✅ 您在白名单中,无限制使用 AI 功能")
            return

        # 判断使用哪种模式
        if group_id and mode == "shared":
            identity_id = group_id
            identity_type = "group"
            msg_type = "群组"
        else:
            identity_id = user_id
            identity_type = "user"
            msg_type = "个人" if not group_id else "个人(群内)"

        # 获取使用次数
        current_count = await self.usage_manager.get_usage_count(
            identity_id, identity_type, platform, group_id
        )
        remaining = max(0, limit - current_count)

        mode_str = "共享模式" if mode == "shared" else "独立模式"
        result = (
            f"📊 今日{msg_type} AI 使用情况\n"
            f"━━━━━━━━━━━━━\n"
            f"已使用: {current_count}/{limit} 次\n"
            f"剩余: {remaining} 次\n"
            f"模式: {mode_str}\n"
            f"配置来源: {source}"
        )
        yield event.plain_result(result)

    # ==================== 管理命令 ====================

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_group")
    async def limit_group(
        self,
        event: AstrMessageEvent,
        group_id: str,
        limit: int,
        mode: str = "individual",
    ):
        """设置群组配置"""
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

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_user")
    async def limit_user(self, event: AstrMessageEvent, user_id: str, limit: int):
        """设置用户配置"""
        platform = str(event.platform)

        db = await self.db_connection.get_connection()
        await db.execute(
            """
            INSERT OR REPLACE INTO user_config
            (user_id, platform, daily_limit, enabled)
            VALUES (?, ?, ?, 1)
        """,
            (user_id, platform, limit),
        )
        await db.commit()

        yield event.plain_result(
            f"✅ 用户 {user_id} 配置已更新\n限制: {limit} 次/天(独立模式)"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_blacklist_add")
    async def blacklist_add(
        self, event: AstrMessageEvent, user_id: str, reason: str = ""
    ):
        """添加黑名单"""
        platform = str(event.platform)
        now = int(datetime.now().timestamp())

        db = await self.db_connection.get_connection()
        await db.execute(
            """
            INSERT OR REPLACE INTO blacklist
            (user_id, platform, add_time, reason)
            VALUES (?, ?, ?, ?)
        """,
            (user_id, platform, now, reason),
        )
        await db.commit()

        yield event.plain_result(f"✅ 用户 {user_id} 已添加到黑名单")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_blacklist_remove")
    async def blacklist_remove(self, event: AstrMessageEvent, user_id: str):
        """移除黑名单"""
        platform = str(event.platform)

        db = await self.db_connection.get_connection()
        await db.execute(
            "DELETE FROM blacklist WHERE user_id = ? AND platform = ?",
            (user_id, platform),
        )
        await db.commit()

        yield event.plain_result(f"✅ 用户 {user_id} 已从黑名单移除")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_blacklist_list")
    async def blacklist_list(self, event: AstrMessageEvent):
        """查看黑名单"""
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

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_whitelist_add")
    async def whitelist_add(self, event: AstrMessageEvent, user_id: str):
        """添加白名单"""
        platform = str(event.platform)
        now = int(datetime.now().timestamp())

        db = await self.db_connection.get_connection()
        await db.execute(
            "INSERT OR IGNORE INTO whitelist (user_id, platform, add_time) VALUES (?, ?, ?)",
            (user_id, platform, now),
        )
        await db.commit()

        yield event.plain_result(f"✅ 用户 {user_id} 已添加到白名单")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_whitelist_remove")
    async def whitelist_remove(self, event: AstrMessageEvent, user_id: str):
        """移除白名单"""
        platform = str(event.platform)

        db = await self.db_connection.get_connection()
        await db.execute(
            "DELETE FROM whitelist WHERE user_id = ? AND platform = ?",
            (user_id, platform),
        )
        await db.commit()

        yield event.plain_result(f"✅ 用户 {user_id} 已从白名单移除")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_whitelist_list")
    async def whitelist_list(self, event: AstrMessageEvent):
        """查看白名单"""
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

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_reset")
    async def limit_reset(self, event: AstrMessageEvent, identity_id: str):
        """重置计数"""
        platform = str(event.platform)

        db = await self.db_connection.get_connection()
        async with db.execute(
            "DELETE FROM ai_usage WHERE (user_id = ? OR group_id = ?) AND platform = ?",
            (identity_id, identity_id, platform),
        ) as cursor:
            deleted = cursor.rowcount
        await db.commit()

        if deleted > 0:
            yield event.plain_result(f"✅ 已重置 {identity_id} 的使用计数")
        else:
            yield event.plain_result(f"⚠️ 未找到 {identity_id} 的使用记录")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_global")
    async def limit_global(self, event: AstrMessageEvent, key: str, value: str):
        """设置全局配置"""
        valid_keys = ["daily_limit", "mode"]

        if key not in valid_keys:
            yield event.plain_result(
                f"❌ 无效的配置键\n可用键: {', '.join(valid_keys)}"
            )
            return

        if key == "mode" and value not in ["individual", "shared"]:
            yield event.plain_result("❌ 模式必须是 individual 或 shared")
            return

        if key == "daily_limit" and not value.isdigit():
            yield event.plain_result("❌ 限制次数必须是数字")
            return

        await self.config_manager.set_global_config(key, value)
        yield event.plain_result(f"✅ 全局配置 {key} 已设置为 {value}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_stats")
    async def limit_stats(self, event: AstrMessageEvent, identity_id: str = None):
        """查看统计"""
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
