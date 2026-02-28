"""查询命令 - /limit"""

from astrbot.api.event import AstrMessageEvent, filter

from ..managers.permission import PermissionManager
from ..managers.usage_manager import UsageManager


class QueryCommand:
    """查询命令处理器"""

    def __init__(
        self,
        permission_manager: PermissionManager,
        usage_manager: UsageManager,
    ):
        """
        初始化查询命令处理器

        Args:
            permission_manager: 权限管理器
            usage_manager: 使用次数管理器
        """
        self.permission_manager = permission_manager
        self.usage_manager = usage_manager

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
            yield event.plain_result("✅ 您在白名单中，无限制使用 AI 功能")
            return

        # 判断使用哪种模式
        if group_id and mode == "shared":
            identity_id = group_id
            identity_type = "group"
            msg_type = "群组"
        else:
            identity_id = user_id
            identity_type = "user"
            msg_type = "个人" if not group_id else "个人（群内）"

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
