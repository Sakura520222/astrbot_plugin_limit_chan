"""数据库连接管理"""

import asyncio
from pathlib import Path

import aiosqlite


class DatabaseConnection:
    """数据库连接管理器"""

    def __init__(self, db_path: Path):
        """
        初始化数据库连接管理器

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._db_connection = None
        self._db_lock = asyncio.Lock()

    async def get_connection(self) -> aiosqlite.Connection:
        """
        获取数据库连接(复用)

        Returns:
            数据库连接对象
        """
        if self._db_connection is None:
            async with self._db_lock:
                if self._db_connection is None:
                    self._db_connection = await aiosqlite.connect(self.db_path)
        return self._db_connection

    async def close(self):
        """关闭数据库连接"""
        async with self._db_lock:
            if self._db_connection:
                await self._db_connection.close()
                self._db_connection = None
