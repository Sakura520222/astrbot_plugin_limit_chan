"""使用次数管理器 - 处理使用次数查询和更新"""

from datetime import date, datetime

from ..database.connection import DatabaseConnection


class UsageManager:
    """使用次数管理器"""

    def __init__(self, db_connection: DatabaseConnection):
        """
        初始化使用次数管理器

        Args:
            db_connection: 数据库连接管理器
        """
        self.db_connection = db_connection

    async def get_usage_count(
        self, identity_id: str, identity_type: str, platform: str, group_id: str
    ) -> int:
        """
        获取使用次数

        Args:
            identity_id: 身份ID(用户ID或群组ID)
            identity_type: 身份类型(user或group)
            platform: 平台
            group_id: 群组ID

        Returns:
            使用次数
        """
        today = date.today()
        db = await self.db_connection.get_connection()
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
        """
        原子性增加使用次数

        Args:
            identity_id: 身份ID(用户ID或群组ID)
            identity_type: 身份类型(user或group)
            platform: 平台
            group_id: 群组ID
            user_id: 用户ID
        """
        today = date.today()
        now = int(datetime.now().timestamp())

        db = await self.db_connection.get_connection()
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
