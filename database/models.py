"""数据库模型和表结构定义"""

import logging

from astrbot.api import AstrBotConfig

from .connection import DatabaseConnection

logger = logging.getLogger(__name__)


class DatabaseModels:
    """数据库模型管理器"""

    def __init__(self, db_connection: DatabaseConnection, config: AstrBotConfig = None):
        """
        初始化数据库模型管理器

        Args:
            db_connection: 数据库连接管理器
            config: 插件配置
        """
        self.db_connection = db_connection
        self.config = config or {}

    async def init_db(self) -> dict:
        """
        初始化数据库表结构并自动迁移旧配置
        
        Returns:
            迁移的旧配置数据（如果有）
        """
        # 确保 data 目录存在（在获取连接之前）
        self.db_connection.db_path.parent.mkdir(parents=True, exist_ok=True)

        db = await self.db_connection.get_connection()

        # 启用 WAL 模式以提高并发性能
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")

        # 首先检查是否有旧表需要迁移
        migrated_config = await self._auto_migrate_old_config(db)

        # 创建新表结构
        await db.executescript("""
            -- 全局配置表（保留用于兼容）
            CREATE TABLE IF NOT EXISTS global_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            -- 使用记录表（仅保留此表用于记录使用情况）
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
            );

            -- 创建索引优化查询性能
            CREATE INDEX IF NOT EXISTS idx_identity_usage
            ON ai_usage(identity_id, identity_type, use_date);

            CREATE INDEX IF NOT EXISTS idx_user_usage
            ON ai_usage(user_id, platform, use_date);

            CREATE INDEX IF NOT EXISTS idx_date_usage
            ON ai_usage(use_date);
        """)

        # 从配置文件初始化全局默认配置
        daily_limit = self.config.get("daily_limit", 20) if self.config else 20
        mode = self.config.get("mode", "individual") if self.config else "individual"

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

        return migrated_config

    async def _auto_migrate_old_config(self, db) -> dict:
        """
        自动检测并迁移旧数据库配置到字典格式
        
        Args:
            db: 数据库连接
            
        Returns:
            迁移的配置字典
        """
        result = {
            "blacklist": {},
            "whitelist": {},
            "user_configs": {},
            "group_configs": {},
        }

        # 检查是否存在旧表
        try:
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('blacklist', 'whitelist', 'user_config', 'group_config')"
            ) as cursor:
                old_tables = await cursor.fetchall()

            if not old_tables:
                # 没有旧表，无需迁移
                return result

            logger.info("检测到旧配置表，开始自动迁移...")

            # 迁移黑名单
            try:
                async with db.execute("SELECT user_id, platform FROM blacklist") as cursor:
                    rows = await cursor.fetchall()
                    for user_id, platform in rows:
                        if platform not in result["blacklist"]:
                            result["blacklist"][platform] = []
                        result["blacklist"][platform].append(user_id)
                logger.info(f"迁移黑名单: {sum(len(v) for v in result['blacklist'].values())} 条")
            except Exception as e:
                logger.warning(f"迁移黑名单失败: {e}")

            # 迁移白名单
            try:
                async with db.execute("SELECT user_id, platform FROM whitelist") as cursor:
                    rows = await cursor.fetchall()
                    for user_id, platform in rows:
                        if platform not in result["whitelist"]:
                            result["whitelist"][platform] = []
                        result["whitelist"][platform].append(user_id)
                logger.info(f"迁移白名单: {sum(len(v) for v in result['whitelist'].values())} 条")
            except Exception as e:
                logger.warning(f"迁移白名单失败: {e}")

            # 迁移用户配置
            try:
                async with db.execute(
                    "SELECT user_id, platform, daily_limit FROM user_config WHERE enabled = 1"
                ) as cursor:
                    rows = await cursor.fetchall()
                    for user_id, platform, daily_limit in rows:
                        if platform not in result["user_configs"]:
                            result["user_configs"][platform] = {}
                        result["user_configs"][platform][user_id] = {"daily_limit": daily_limit}
                logger.info(f"迁移用户配置: {sum(len(v) for v in result['user_configs'].values())} 条")
            except Exception as e:
                logger.warning(f"迁移用户配置失败: {e}")

            # 迁移群组配置
            try:
                async with db.execute(
                    "SELECT group_id, platform, daily_limit, mode FROM group_config WHERE enabled = 1"
                ) as cursor:
                    rows = await cursor.fetchall()
                    for group_id, platform, daily_limit, mode in rows:
                        if platform not in result["group_configs"]:
                            result["group_configs"][platform] = {}
                        result["group_configs"][platform][group_id] = {
                            "daily_limit": daily_limit,
                            "mode": mode,
                        }
                logger.info(f"迁移群组配置: {sum(len(v) for v in result['group_configs'].values())} 条")
            except Exception as e:
                logger.warning(f"迁移群组配置失败: {e}")

            # 删除旧表
            try:
                await db.execute("DROP TABLE IF EXISTS blacklist")
                await db.execute("DROP TABLE IF EXISTS whitelist")
                await db.execute("DROP TABLE IF EXISTS user_config")
                await db.execute("DROP TABLE IF EXISTS group_config")
                await db.commit()
                logger.info("已删除旧配置表，迁移完成")
            except Exception as e:
                logger.error(f"删除旧表失败: {e}")

        except Exception as e:
            logger.error(f"自动迁移过程出错: {e}", exc_info=True)

        return result