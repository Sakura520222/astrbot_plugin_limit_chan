"""权限管理器 - 处理权限检查核心逻辑"""

import logging

from .config_manager import ConfigManager

logger = logging.getLogger(__name__)


def safe_int(value, default=20):
    """
    安全地将值转换为整数

    Args:
        value: 要转换的值
        default: 转换失败时的默认值

    Returns:
        转换后的整数或默认值
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        logger.warning(f"无法将值 {value} 转换为整数，使用默认值 {default}")
        return default


class PermissionManager:
    """权限管理器"""

    def __init__(self, config_manager: ConfigManager):
        """
        初始化权限管理器

        Args:
            config_manager: 配置管理器实例
        """
        self.config_manager = config_manager

    async def check_permission(
        self, user_id: str, platform: str, group_id: str
    ) -> tuple[bool, int, str, str]:
        """
        检查权限和限制配置

        优化后的优先级: 白名单 > 黑名单 > 用户配置 > 群组配置 > 全局配置
        将白名单提前检查，因为白名单用户可以直接放行，无需后续检查

        Args:
            user_id: 用户ID
            platform: 平台
            group_id: 群组ID

        Returns:
            (是否允许, 限制次数(-1为无限制), 模式, 配置来源)
        """
        # 1. 最高优先级：白名单检查（优先放行）
        if self.config_manager.is_whitelisted(user_id, platform):
            return True, -1, "individual", "whitelist"

        # 2. 次高优先级：黑名单检查（拦截）
        if self.config_manager.is_blacklisted(user_id, platform):
            return False, 0, "individual", "blacklist"

        # 3. 用户特定配置
        user_config = self.config_manager.get_user_config(user_id, platform)
        if user_config and user_config.get("enabled"):
            limit = user_config["daily_limit"]
            return True, limit, "individual", f"user_config:{limit}"

        # 4. 群组特定配置
        if group_id:
            group_config = self.config_manager.get_group_config(
                group_id, platform
            )
            if group_config and group_config.get("enabled"):
                limit = group_config["daily_limit"]
                mode = group_config["mode"]
                return True, limit, mode, f"group_config:{limit}:{mode}"

        # 5. 全局默认配置
        global_limit = safe_int(
            await self.config_manager.get_global_config("daily_limit", 20), default=20
        )
        global_mode = await self.config_manager.get_global_config("mode", "individual")

        # 验证 mode 值的合法性
        if global_mode not in ["individual", "shared"]:
            logger.warning(f"非法的 mode 值: {global_mode}，使用默认值 'individual'")
            global_mode = "individual"

        return True, global_limit, global_mode, f"global:{global_limit}:{global_mode}"
