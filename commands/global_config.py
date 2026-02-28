"""全局配置命令 - /limit_global"""

from astrbot.api.event import AstrMessageEvent, filter

from ..managers.config_manager import ConfigManager


class GlobalConfigCommand:
    """全局配置命令处理器"""

    def __init__(self, config_manager: ConfigManager):
        """
        初始化全局配置命令处理器

        Args:
            config_manager: 配置管理器
        """
        self.config_manager = config_manager

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_global")
    async def limit_global(self, event: AstrMessageEvent, key: str, value: str):
        """设置全局配置 /limit_global <key> <value>"""
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
