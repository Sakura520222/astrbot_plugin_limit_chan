"""数据库模型和表结构定义"""

from astrbot.api import AstrBotConfig

from .connection import DatabaseConnection


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

    async def init_db(self):
        """初始化数据库表结构"""
        db = await self.db_connection.get_connection()

        # 确保 data 目录存在
        self.db_connection.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 启用 WAL 模式以提高并发性能
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")

        # 批量创建表和索引
        await db.executescript("""
            -- 全局配置表
            CREATE TABLE IF NOT EXISTS global_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            -- 群组配置表
            CREATE TABLE IF NOT EXISTS group_config (
                group_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                daily_limit INTEGER NOT NULL,
                mode TEXT NOT NULL DEFAULT 'individual',
                enabled INTEGER DEFAULT 1,
                PRIMARY KEY (group_id, platform)
            );

            -- 用户配置表
            CREATE TABLE IF NOT EXISTS user_config (
                user_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                daily_limit INTEGER NOT NULL,
                enabled INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, platform)
            );

            -- 黑名单表
            CREATE TABLE IF NOT EXISTS blacklist (
                user_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                add_time INTEGER NOT NULL,
                reason TEXT DEFAULT '',
                PRIMARY KEY (user_id, platform)
            );

            -- 白名单表
            CREATE TABLE IF NOT EXISTS whitelist (
                user_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                add_time INTEGER NOT NULL,
                PRIMARY KEY (user_id, platform)
            );

            -- 使用记录表
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

            -- 创建索引
            CREATE INDEX IF NOT EXISTS idx_identity_usage
            ON ai_usage(identity_id, identity_type, use_date);

            CREATE INDEX IF NOT EXISTS idx_user_usage
            ON ai_usage(user_id, platform, use_date);
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
