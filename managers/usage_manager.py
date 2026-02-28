"""使用次数管理器 - 处理使用次数查询和更新"""

import logging
from datetime import date, datetime

from ..database.connection import DatabaseConnection
from .cache_manager import CacheManager

logger = logging.getLogger(__name__)


class UsageManager:
    """使用次数管理器"""

    def __init__(self, db_connection: DatabaseConnection):
        """
        初始化使用次数管理器

        Args:
            db_connection: 数据库连接管理器
        """
        self.db_connection = db_connection
        # 使用计数缓存：缓存30秒以平衡性能和实时性
        self.count_cache = CacheManager(max_size=5000, default_ttl=30)
        # 批量更新队列
        self._pending_updates: dict[str, int] = {}
        self._update_lock = None  # 将在初始化时设置为 asyncio.Lock()

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

    async def check_and_increment(
        self,
        identity_id: str,
        identity_type: str,
        platform: str,
        group_id: str,
        user_id: str,
        limit: int,
    ) -> tuple[bool, int]:
        """
        原子性检查并增加使用次数（带缓存优化）

        优化版本：
        1. 先从缓存读取当前计数
        2. 如果缓存显示已超限，直接返回
        3. 如果缓存未命中或可能未超限，从数据库读取并更新
        4. 更新后刷新缓存

        Args:
            identity_id: 身份ID(用户ID或群组ID)
            identity_type: 身份类型(user或group)
            platform: 平台
            group_id: 群组ID
            user_id: 用户ID
            limit: 限制次数(-1表示无限制)

        Returns:
            (是否允许继续使用, 当前计数)

        Raises:
            Exception: 数据库操作失败时抛出异常
        """
        today = date.today()
        today_str = str(today)
        now = int(datetime.now().timestamp())

        # 生成缓存键
        cache_key = (identity_type, platform, group_id, identity_id, today_str)

        try:
            # 先从缓存尝试获取
            cached_count = await self.count_cache.get(*cache_key)

            # 如果缓存显示已经超限，直接返回（快速拒绝）
            if cached_count is not None and cached_count >= limit:
                return False, cached_count

            # 缓存未命中或可能未超限，从数据库读取
            db = await self.db_connection.get_connection()

            async with db.execute(
                """SELECT use_count FROM ai_usage
                   WHERE identity_id = ? AND identity_type = ?
                   AND platform = ? AND group_id = ? AND use_date = ?""",
                (identity_id, identity_type, platform, group_id, today_str),
            ) as cursor:
                row = await cursor.fetchone()
                current_count = row[0] if row else 0

            # 检查是否超限
            if current_count >= limit:
                # 缓存超限状态
                await self.count_cache.set(current_count, *cache_key)
                return False, current_count

            # 未超限，原子性增加计数
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
                    today_str,
                    now,
                    now,
                ),
            )
            await db.commit()

            # 更新后的计数
            new_count = current_count + 1

            # 更新缓存
            await self.count_cache.set(new_count, *cache_key)

            return True, new_count

        except Exception as e:
            logger.error(
                f"检查并增加使用次数失败: identity_id={identity_id}, "
                f"identity_type={identity_type}, platform={platform}, error={e}"
            )
            # 清除可能错误的缓存
            try:
                await self.count_cache.delete(*cache_key)
            except Exception:
                pass
            # 重新抛出异常，让调用方处理
            raise

    async def invalidate_cache(self, identity_id: str, platform: str, group_id: str):
        """
        清除使用计数缓存（用于重置等操作）

        Args:
            identity_id: 身份ID
            platform: 平台
            group_id: 群组ID
        """
        today = date.today()
        today_str = str(today)

        # 清除可能的缓存
        for identity_type in ["user", "group"]:
            try:
                await self.count_cache.delete(
                    identity_type, platform, group_id, identity_id, today_str
                )
            except Exception:
                pass
