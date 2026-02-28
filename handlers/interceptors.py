"""LLM请求拦截器 - 拦截AI请求并验证权限"""

import asyncio

from astrbot.api.event import AstrMessageEvent

from ..managers.permission import PermissionManager
from ..managers.usage_manager import UsageManager


class LLMInterceptor:
    """LLM请求拦截器"""

    def __init__(
        self,
        permission_manager: PermissionManager,
        usage_manager: UsageManager,
    ):
        """
        初始化LLM拦截器

        Args:
            permission_manager: 权限管理器
            usage_manager: 使用次数管理器
        """
        self.permission_manager = permission_manager
        self.usage_manager = usage_manager
        self.background_tasks = set()  # 保存后台任务引用

    async def on_llm_request(self, event: AstrMessageEvent):
        """拦截 LLM 请求"""
        user_id = event.get_sender_id()
        platform = str(event.platform)
        group_id = event.message_obj.group_id or ""

        # 获取权限配置
        allowed, limit, mode, source = await self.permission_manager.check_permission(
            user_id, platform, group_id
        )

        # 黑名单直接拦截
        if not allowed:
            event.stop_event()
            await event.send(event.plain_result("❌ 您已被限制使用 AI 功能"))
            return

        # 白名单直接放行
        if limit == -1:
            return

        # 判断使用哪种模式
        if group_id and mode == "shared":
            # 共享模式：群组共用计数
            identity_id = group_id
            identity_type = "group"
            msg_type = "群组"
        else:
            # 独立模式或私聊：用户独立计数
            identity_id = user_id
            identity_type = "user"
            msg_type = "个人" if not group_id else "个人（群内）"

        # 检查使用次数
        current_count = await self.usage_manager.get_usage_count(
            identity_id, identity_type, platform, group_id
        )

        if current_count >= limit:
            event.stop_event()
            await event.send(
                event.plain_result(
                    f"❌ 今日{msg_type} AI 使用次数已达上限！\n"
                    f"已使用: {current_count}/{limit} 次\n"
                    f"配置来源: {source}"
                )
            )
            return

        # 异步更新计数（不阻塞请求，保存任务引用）
        task = asyncio.create_task(
            self.usage_manager.increment_usage(
                identity_id, identity_type, platform, group_id, user_id
            )
        )
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)
