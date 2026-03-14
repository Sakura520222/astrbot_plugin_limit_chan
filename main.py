"""
AstrBot AI 使用次数限制插件
支持黑名单、白名单、用户/群组/全局配置、独立/共享模式
"""

import asyncio
import logging
from datetime import datetime

from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, StarTools
from astrbot.core.utils.session_waiter import (
    SessionController,
    session_waiter,
)

from .database.connection import DatabaseConnection
from .database.models import DatabaseModels
from .handlers.interceptors import LLMInterceptor
from .managers.config_manager import ConfigManager
from .managers.permission import PermissionManager
from .managers.usage_manager import UsageManager

logger = logging.getLogger(__name__)


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
        """插件启动时初始化数据库并自动迁移配置"""
        migrated_config = await self.db_models.init_db()
        
        # 如果有旧配置被迁移，自动合并到当前配置
        if migrated_config and any(migrated_config.values()):
            logger.info("检测到旧配置，已自动迁移。建议通过 AstrBot 管理界面保存配置以持久化迁移的数据。")
            
            # 确保配置初始化
            if not self.config:
                self.config = {}
            
            # 合并黑名单（从旧的多平台格式合并为简单列表）
            if migrated_config.get("blacklist"):
                current_blacklist = self.config.get("blacklist", [])
                for platform_users in migrated_config["blacklist"].values():
                    if isinstance(platform_users, list):
                        current_blacklist.extend(platform_users)
                self.config["blacklist"] = list(set(current_blacklist))  # 去重
            
            # 合并白名单（从旧的多平台格式合并为简单列表）
            if migrated_config.get("whitelist"):
                current_whitelist = self.config.get("whitelist", [])
                for platform_users in migrated_config["whitelist"].values():
                    if isinstance(platform_users, list):
                        current_whitelist.extend(platform_users)
                self.config["whitelist"] = list(set(current_whitelist))  # 去重

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

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_clear_db")
    async def limit_clear_db(self, event: AstrMessageEvent):
        """一键清空使用记录"""
        user_id = event.get_sender_id()
        platform = str(event.platform)

        # 发送警告信息
        warning_msg = (
            "⚠️ 警告：此操作将清空所有使用记录！\n\n"
            "这将删除：\n"
            "- 所有 AI 使用记录\n\n"
            "注意：黑名单、白名单、用户/群组配置已移至配置文件，不受此操作影响。\n"
            "如需修改配置，请通过 AstrBot 管理界面编辑配置文件。\n\n"
            "请在 30 秒内发送「确认」以继续操作\n"
            "发送其他内容将取消操作"
        )
        yield event.plain_result(warning_msg)

        # 定义会话等待函数
        @session_waiter(timeout=30, record_history_chains=False)
        async def clear_db_waiter(
            controller: SessionController, event: AstrMessageEvent
        ):
            user_input = event.message_str.strip()

            # 检查用户是否确认
            if user_input != "确认":
                await event.send(event.plain_result("❌ 操作已取消"))
                controller.stop()
                return

            # 用户确认，执行清空操作
            try:
                db = await self.db_connection.get_connection()

                # 仅删除使用记录
                await db.execute("DELETE FROM ai_usage")
                await db.commit()

                # 清除使用计数缓存
                await self.usage_manager.count_cache.clear_all()

                # 记录日志
                logger.info(
                    f"使用记录已清空 - 操作者: {user_id} ({platform}), 时间: {datetime.now()}"
                )

                await event.send(event.plain_result("✅ 使用记录已清空完成！"))
                controller.stop()

            except Exception as e:
                logger.error(f"清空失败: {e}", exc_info=True)
                await event.send(event.plain_result(f"❌ 清空失败: {str(e)}"))
                controller.stop()

        # 启动会话等待
        try:
            await clear_db_waiter(event)
        except TimeoutError:
            yield event.plain_result("⏰ 操作已超时，已自动取消")
        except Exception as e:
            logger.error(f"会话控制错误: {e}", exc_info=True)
            yield event.plain_result(f"❌ 发生错误: {str(e)}")
        finally:
            event.stop_event()

    # ==================== 管理命令 ====================

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_group")
    async def limit_group(
        self,
        event: AstrMessageEvent,
        group_id: str = None,
        limit: int = None,
        mode: str = None,
    ):
        """设置群组配置（已迁移至配置文件）"""
        yield event.plain_result(
            "⚠️ 群组配置已迁移至配置文件\n\n"
            "请通过 AstrBot 管理界面编辑插件配置：\n"
            "在 group_configs 中添加配置，格式如下：\n"
            "```\n"
            '"group_configs": {\n'
            '  "qq": {\n'
            '    "群组ID": {\n'
            '      "daily_limit": 30,\n'
            '      "mode": "shared"\n'
            '    }\n'
            "  }\n"
            "}\n"
            "```\n\n"
            "参数说明：\n"
            "- daily_limit: 每日限制次数（-1表示无限制）\n"
            "- mode: individual（独立模式）或 shared（共享模式）"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_user")
    async def limit_user(self, event: AstrMessageEvent, user_id: str = None, limit: int = None):
        """设置用户配置（已迁移至配置文件）"""
        yield event.plain_result(
            "⚠️ 用户配置已迁移至配置文件\n\n"
            "请通过 AstrBot 管理界面编辑插件配置：\n"
            "在 user_configs 中添加配置，格式如下：\n"
            "```\n"
            '"user_configs": {\n'
            '  "qq": {\n'
            '    "用户ID": {\n'
            '      "daily_limit": 10\n'
            '    }\n'
            "  }\n"
            "}\n"
            "```\n\n"
            "参数说明：\n"
            "- daily_limit: 每日限制次数（-1表示无限制）"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_blacklist_add")
    async def blacklist_add(self, event: AstrMessageEvent, user_id: str = None, reason: str = ""):
        """添加黑名单（已迁移至配置文件）"""
        yield event.plain_result(
            "⚠️ 黑名单已迁移至配置文件\n\n"
            "请通过 AstrBot 管理界面编辑插件配置：\n"
            "在 blacklist 中添加用户，格式如下：\n"
            "```\n"
            '"blacklist": {\n'
            '  "qq": ["用户ID1", "用户ID2"]\n'
            "}\n"
            "```\n\n"
            "配置后插件会自动从配置文件读取黑名单"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_blacklist_remove")
    async def blacklist_remove(self, event: AstrMessageEvent, user_id: str = None):
        """移除黑名单（已迁移至配置文件）"""
        yield event.plain_result(
            "⚠️ 黑名单已迁移至配置文件\n\n"
            "请通过 AstrBot 管理界面编辑插件配置：\n"
            "从 blacklist 中删除对应用户ID即可"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_blacklist_list")
    async def blacklist_list(self, event: AstrMessageEvent):
        """查看黑名单"""
        blacklist = self.config.get("blacklist", [])

        if not blacklist:
            yield event.plain_result("📋 黑名单为空")
            return

        result = f"📋 黑名单列表（共 {len(blacklist)} 人）\n━━━━━━━━━━━━━\n"
        # 限制显示条数,避免消息过长
        max_display = 20
        for i, user_id in enumerate(blacklist[:max_display], 1):
            result += f"{i}. {user_id}\n"

        if len(blacklist) > max_display:
            result += f"\n... 还有 {len(blacklist) - max_display} 条记录未显示"

        yield event.plain_result(result)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_whitelist_add")
    async def whitelist_add(self, event: AstrMessageEvent, user_id: str = None):
        """添加白名单（已迁移至配置文件）"""
        yield event.plain_result(
            "⚠️ 白名单已迁移至配置文件\n\n"
            "请通过 AstrBot 管理界面编辑插件配置中的 whitelist 字段。\n\n"
            "白名单用户可无限制使用 AI 功能。"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_whitelist_remove")
    async def whitelist_remove(self, event: AstrMessageEvent, user_id: str = None):
        """移除白名单（已迁移至配置文件）"""
        yield event.plain_result(
            "⚠️ 白名单已迁移至配置文件\n\n"
            "请通过 AstrBot 管理界面编辑插件配置中的 whitelist 字段。"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_whitelist_list")
    async def whitelist_list(self, event: AstrMessageEvent):
        """查看白名单"""
        whitelist = self.config.get("whitelist", [])

        if not whitelist:
            yield event.plain_result("📋 白名单为空")
            return

        result = f"📋 白名单列表（共 {len(whitelist)} 人）\n━━━━━━━━━━━━━\n"
        # 限制显示条数,避免消息过长
        max_display = 20
        for i, user_id in enumerate(whitelist[:max_display], 1):
            result += f"{i}. {user_id}\n"

        if len(whitelist) > max_display:
            result += f"\n... 还有 {len(whitelist) - max_display} 条记录未显示"

        yield event.plain_result(result)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_reset")
    async def limit_reset(self, event: AstrMessageEvent, identity_id: str):
        """重置计数"""
        platform = str(event.platform)
        group_id = ""  # 重置命令可能同时清除用户和群组的计数

        db = await self.db_connection.get_connection()
        async with db.execute(
            "DELETE FROM ai_usage WHERE (user_id = ? OR group_id = ?) AND platform = ?",
            (identity_id, identity_id, platform),
        ) as cursor:
            deleted = cursor.rowcount
        await db.commit()

        # 清除使用计数缓存
        await self.usage_manager.invalidate_cache(identity_id, platform, group_id)

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
