"""LLM请求拦截器 - 拦截AI请求并验证权限"""

import logging

from astrbot.api.event import AstrMessageEvent
from astrbot.api.provider import ProviderRequest

from ..managers.permission import PermissionManager
from ..managers.usage_manager import UsageManager

logger = logging.getLogger(__name__)


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

    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        """拦截 LLM 请求

        Args:
            event: 消息事件对象
            req: LLM 请求对象（当前未使用，但框架要求必须接受此参数）
        """
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

        # 原子性检查并增加使用次数
        try:
            allowed, current_count = await self.usage_manager.check_and_increment(
                identity_id, identity_type, platform, group_id, user_id, limit
            )

            if not allowed:
                event.stop_event()
                await event.send(
                    event.plain_result(
                        f"❌ 今日{msg_type} AI 使用次数已达上限！\n"
                        f"已使用: {current_count}/{limit} 次\n"
                        f"配置来源: {source}"
                    )
                )
                return
            # 允许继续使用，计数已自动增加，无需额外操作

        except Exception as e:
            logger.error(f"处理使用次数时发生错误: {e}", exc_info=True)
            # 出错时为了安全起见，拒绝请求
            event.stop_event()
            await event.send(event.plain_result("❌ 系统错误，请稍后重试"))
            return
