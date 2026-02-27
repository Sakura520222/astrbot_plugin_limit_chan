"""
AstrBot AI 使用次数限制插件
支持黑名单、白名单、用户/群组/全局配置、独立/共享模式
"""

import asyncio
from datetime import date, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register


@register(
    "limit_limiter",
    "AstrBot Community",
    "限制用户每日 AI 使用次数，支持多级配置和黑白名单",
    "1.0.0",
    "https://github.com/astrbot-plugins/limit_limiter",
)
class LimitLimiter(Star):
    """AI 使用次数限制器"""

    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}
        # 使用插件目录下的 data 子目录存储数据
        self.data_dir = Path(__file__).parent / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "limit_limiter.db"
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def on_wakeup(self):
        """插件启动时初始化数据库"""
        async with self._init_lock:
            await self.init_db()

    async def _ensure_initialized(self):
        """确保数据库已初始化"""
        if not self._initialized:
            async with self._init_lock:
                if not self._initialized:
                    await self.init_db()

    async def get_db_connection(self):
        """获取安全的数据库连接，确保数据库已初始化"""
        await self._ensure_initialized()
        return await aiosqlite.connect(self.db_path)

    async def init_db(self):
        """初始化数据库表结构"""
        # 确保 data 目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            # 启用 WAL 模式以提高并发性能
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA synchronous=NORMAL")

            # 全局配置表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS global_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            # 群组配置表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS group_config (
                    group_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    daily_limit INTEGER NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'individual',
                    enabled INTEGER DEFAULT 1,
                    PRIMARY KEY (group_id, platform)
                )
            """)

            # 用户配置表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_config (
                    user_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    daily_limit INTEGER NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    PRIMARY KEY (user_id, platform)
                )
            """)

            # 黑名单表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS blacklist (
                    user_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    add_time INTEGER NOT NULL,
                    reason TEXT DEFAULT '',
                    PRIMARY KEY (user_id, platform)
                )
            """)

            # 白名单表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS whitelist (
                    user_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    add_time INTEGER NOT NULL,
                    PRIMARY KEY (user_id, platform)
                )
            """)

            # 使用记录表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ai_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    identity_id TEXT NOT NULL,
                    identity_type TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    group_id TEXT DEFAULT '',
                    user_id TEXT NOT NULL,
                    use_date DATE NOT NULL,
                    use_count INTEGER DEFAULT 0,
                    last_use_time INTEGER,
                    UNIQUE(identity_id, identity_type, platform, group_id, use_date)
                )
            """)

            # 创建索引
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_identity_usage
                ON ai_usage(identity_id, identity_type, use_date)
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_usage
                ON ai_usage(user_id, platform, use_date)
            """)

            # 从配置文件初始化全局默认配置
            daily_limit = self.config.get("daily_limit", 20) if self.config else 20
            mode = (
                self.config.get("mode", "individual") if self.config else "individual"
            )

            await db.execute(
                """
                INSERT OR IGNORE INTO global_config (key, value)
                VALUES ('daily_limit', ?)
            """,
                (str(daily_limit),),
            )

            await db.execute(
                """
                INSERT OR IGNORE INTO global_config (key, value)
                VALUES ('mode', ?)
            """,
                (mode,),
            )

            await db.commit()
            
        # 标记数据库已初始化
        self._initialized = True

    # ==================== 配置查询方法 ====================

    async def get_global_config(self, key: str, default: Any = None) -> Any:
        """获取全局配置（优先从配置文件读取，其次从数据库）"""
        # 先从配置文件读取
        if self.config and key in self.config:
            return self.config[key]

        # 从数据库读取
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT value FROM global_config WHERE key = ?", (key,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return row[0]
                return default

    async def set_global_config(self, key: str, value: str):
        """设置全局配置"""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO global_config (key, value) VALUES (?, ?)",
                (key, str(value)),
            )
            await db.commit()

    async def is_blacklisted(self, user_id: str, platform: str) -> bool:
        """检查是否在黑名单"""
        # 检查配置文件中是否启用了黑名单功能
        if self.config and not self.config.get("enable_blacklist", True):
            return False

        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT 1 FROM blacklist WHERE user_id = ? AND platform = ?",
                (user_id, platform),
            ) as cursor:
                return await cursor.fetchone() is not None

    async def is_whitelisted(self, user_id: str, platform: str) -> bool:
        """检查是否在白名单"""
        # 检查配置文件中是否启用了白名单功能
        if self.config and not self.config.get("enable_whitelist", True):
            return False

        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT 1 FROM whitelist WHERE user_id = ? AND platform = ?",
                (user_id, platform),
            ) as cursor:
                return await cursor.fetchone() is not None

    async def get_user_config(
        self, user_id: str, platform: str
    ) -> dict[str, Any] | None:
        """获取用户配置"""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """SELECT daily_limit, enabled FROM user_config
                   WHERE user_id = ? AND platform = ?""",
                (user_id, platform),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {"daily_limit": row[0], "enabled": row[1]}
                return None

    async def get_group_config(
        self, group_id: str, platform: str
    ) -> dict[str, Any] | None:
        """获取群组配置"""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """SELECT daily_limit, mode, enabled FROM group_config
                   WHERE group_id = ? AND platform = ?""",
                (group_id, platform),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {"daily_limit": row[0], "mode": row[1], "enabled": row[2]}
                return None

    # ==================== 权限检查核心逻辑 ====================

    async def check_permission(
        self, user_id: str, platform: str, group_id: str
    ) -> tuple[bool, int, str, str]:
        """
        检查权限和限制配置

        返回: (是否允许, 限制次数(-1为无限制), 模式, 配置来源)
        优先级: 黑名单 > 白名单 > 用户配置 > 群组配置 > 全局配置
        """
        # 1. 最高优先级：黑名单检查
        if await self.is_blacklisted(user_id, platform):
            return False, 0, "individual", "blacklist"

        # 2. 次高优先级：白名单检查
        if await self.is_whitelisted(user_id, platform):
            return True, -1, "individual", "whitelist"

        # 3. 用户特定配置
        user_config = await self.get_user_config(user_id, platform)
        if user_config and user_config.get("enabled"):
            limit = user_config["daily_limit"]
            return True, limit, "individual", f"user_config:{limit}"

        # 4. 群组特定配置
        if group_id:
            group_config = await self.get_group_config(group_id, platform)
            if group_config and group_config.get("enabled"):
                limit = group_config["daily_limit"]
                mode = group_config["mode"]
                return True, limit, mode, f"group_config:{limit}:{mode}"

        # 5. 全局默认配置
        global_limit = int(await self.get_global_config("daily_limit", 20))
        global_mode = await self.get_global_config("mode", "individual")
        return True, global_limit, global_mode, f"global:{global_limit}:{global_mode}"

    # ==================== 使用次数管理 ====================

    async def get_usage_count(
        self, identity_id: str, identity_type: str, platform: str, group_id: str
    ) -> int:
        """获取使用次数"""
        today = date.today()
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """SELECT use_count FROM ai_usage
                   WHERE identity_id = ? AND identity_type = ?
                   AND platform = ? AND group_id = ? AND use_date = ?""",
                (identity_id, identity_type, platform, group_id, str(today)),
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def increment_usage(
        self,
        identity_id: str,
        identity_type: str,
        platform: str,
        group_id: str,
        user_id: str,
    ):
        """原子性增加使用次数"""
        today = date.today()
        now = int(datetime.now().timestamp())

        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            # 使用 UPSERT 语法保证原子性
            await db.execute(
                """
                INSERT INTO ai_usage
                (identity_id, identity_type, platform, group_id, user_id, use_date, use_count, last_use_time)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(identity_id, identity_type, platform, group_id, use_date)
                DO UPDATE SET use_count = use_count + 1, last_use_time = ?
            """,
                (
                    identity_id,
                    identity_type,
                    platform,
                    group_id,
                    user_id,
                    str(today),
                    now,
                    now,
                ),
            )
            await db.commit()

    # ==================== 核心拦截逻辑 ====================

    @filter.on_waiting_llm_request(priority=10)
    async def on_llm_request(self, event: AstrMessageEvent):
        """拦截 LLM 请求"""
        user_id = event.get_sender_id()
        platform = str(event.platform)
        group_id = event.message_obj.group_id or ""

        # 获取权限配置
        allowed, limit, mode, source = await self.check_permission(
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
        current_count = await self.get_usage_count(
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

        # 异步更新计数（不阻塞请求）
        asyncio.create_task(
            self.increment_usage(
                identity_id, identity_type, platform, group_id, user_id
            )
        )

    # ==================== 查询指令 ====================

    @filter.command("limit")
    async def query_limit(self, event: AstrMessageEvent):
        """查询当前使用情况"""
        user_id = event.get_sender_id()
        platform = str(event.platform)
        group_id = event.message_obj.group_id or ""

        # 获取权限配置
        allowed, limit, mode, source = await self.check_permission(
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
        current_count = await self.get_usage_count(
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

    # ==================== 管理指令 ====================

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_group")
    async def limit_group(
        self,
        event: AstrMessageEvent,
        group_id: str,
        limit: int,
        mode: str = "individual",
    ):
        """设置群组配置 /limit_group <群ID> <limit> [mode]"""
        platform = str(event.platform)

        if mode not in ["individual", "shared"]:
            yield event.plain_result("❌ 模式必须是 individual 或 shared")
            return

        async with aiosqlite.connect(self.db_path) as db:
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
        """设置用户配置 /limit_user <用户ID> <limit>"""
        platform = str(event.platform)

        async with aiosqlite.connect(self.db_path) as db:
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
            f"✅ 用户 {user_id} 配置已更新\n限制: {limit} 次/天（独立模式）"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_blacklist_add")
    async def blacklist_add(
        self, event: AstrMessageEvent, user_id: str, reason: str = ""
    ):
        """添加黑名单 /limit_blacklist_add <用户ID> [理由]"""
        platform = str(event.platform)
        now = int(datetime.now().timestamp())

        async with aiosqlite.connect(self.db_path) as db:
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
        """移除黑名单 /limit_blacklist_remove <用户ID>"""
        platform = str(event.platform)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM blacklist WHERE user_id = ? AND platform = ?",
                (user_id, platform),
            )
            await db.commit()

        yield event.plain_result(f"✅ 用户 {user_id} 已从黑名单移除")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_blacklist_list")
    async def blacklist_list(self, event: AstrMessageEvent):
        """查看黑名单 /limit_blacklist_list"""
        platform = str(event.platform)

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT user_id, reason FROM blacklist WHERE platform = ?", (platform,)
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            yield event.plain_result("📋 黑名单为空")
            return

        result = "📋 黑名单列表\n━━━━━━━━━━━━━\n"
        for i, (user_id, reason) in enumerate(rows, 1):
            result += f"{i}. {user_id}"
            if reason:
                result += f" ({reason})"
            result += "\n"

        yield event.plain_result(result)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_whitelist_add")
    async def whitelist_add(self, event: AstrMessageEvent, user_id: str):
        """添加白名单 /limit_whitelist_add <用户ID>"""
        platform = str(event.platform)
        now = int(datetime.now().timestamp())

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO whitelist (user_id, platform, add_time) VALUES (?, ?, ?)",
                (user_id, platform, now),
            )
            await db.commit()

        yield event.plain_result(f"✅ 用户 {user_id} 已添加到白名单")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_whitelist_remove")
    async def whitelist_remove(self, event: AstrMessageEvent, user_id: str):
        """移除白名单 /limit_whitelist_remove <用户ID>"""
        platform = str(event.platform)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM whitelist WHERE user_id = ? AND platform = ?",
                (user_id, platform),
            )
            await db.commit()

        yield event.plain_result(f"✅ 用户 {user_id} 已从白名单移除")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_whitelist_list")
    async def whitelist_list(self, event: AstrMessageEvent):
        """查看白名单 /limit_whitelist_list"""
        platform = str(event.platform)

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT user_id FROM whitelist WHERE platform = ?", (platform,)
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            yield event.plain_result("📋 白名单为空")
            return

        result = "📋 白名单列表\n━━━━━━━━━━━━━\n"
        for i, (user_id,) in enumerate(rows, 1):
            result += f"{i}. {user_id}\n"

        yield event.plain_result(result)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_reset")
    async def limit_reset(self, event: AstrMessageEvent, identity_id: str):
        """重置计数 /limit_reset <用户ID|群ID>"""
        platform = str(event.platform)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM ai_usage WHERE (user_id = ? OR group_id = ?) AND platform = ?",
                (identity_id, identity_id, platform),
            )
            deleted = cursor.rowcount
            await db.commit()

        if deleted > 0:
            yield event.plain_result(f"✅ 已重置 {identity_id} 的使用计数")
        else:
            yield event.plain_result(f"⚠️ 未找到 {identity_id} 的使用记录")

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

        await self.set_global_config(key, value)
        yield event.plain_result(f"✅ 全局配置 {key} 已设置为 {value}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("limit_stats")
    async def limit_stats(
        self, event: AstrMessageEvent, identity_id: str | None = None
    ):
        """查看统计 /limit_stats [用户ID|群ID]"""
        platform = str(event.platform)

        if identity_id:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    """SELECT user_id, group_id, use_date, use_count, identity_type
                       FROM ai_usage
                       WHERE (user_id = ? OR group_id = ?) AND platform = ?
                       ORDER BY use_date DESC, use_count DESC""",
                    (identity_id, identity_id, platform),
                ) as cursor:
                    rows = await cursor.fetchall()
        else:
            async with aiosqlite.connect(self.db_path) as db:
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
        for user_id, group_id, use_date, use_count, identity_type in rows:
            if identity_type == "group":
                result += f"群组 {group_id} "
            else:
                result += f"用户 {user_id} "
                if group_id:
                    result += f"(群 {group_id}) "
            result += f"- {use_date}: {use_count} 次\n"

        yield event.plain_result(result)
