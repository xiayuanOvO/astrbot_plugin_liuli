import asyncio
from pathlib import Path

import aiosqlite

from .migrations import v1, v2, v3, v4, v5


MIGRATIONS = (
    (v1.VERSION, v1.apply),
    (v2.VERSION, v2.apply),
    (v3.VERSION, v3.apply),
    (v4.VERSION, v4.apply),
    (v5.VERSION, v5.apply),
)
LATEST_SCHEMA_VERSION = MIGRATIONS[-1][0]


class SQLiteDatabase:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "liuli.sqlite3"
        self._connection: aiosqlite.Connection | None = None
        self.lock = asyncio.Lock()

    async def initialize(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self.path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA foreign_keys = ON")
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._migrate()

    async def _migrate(self) -> None:
        async with self.lock:
            async with self.connection.execute("PRAGMA user_version") as cursor:
                row = await cursor.fetchone()
            version = int(row[0])
            if version > LATEST_SCHEMA_VERSION:
                raise RuntimeError(
                    f"数据库版本 {version} 高于插件支持版本 {LATEST_SCHEMA_VERSION}"
                )
            for migration_version, apply_migration in MIGRATIONS:
                if version >= migration_version:
                    continue
                await self.connection.execute("BEGIN IMMEDIATE")
                try:
                    await apply_migration(self.connection)
                    await self.connection.execute(
                        f"PRAGMA user_version = {migration_version}"
                    )
                    await self.connection.commit()
                    version = migration_version
                except Exception:
                    await self.connection.rollback()
                    raise

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("SQLiteDatabase 尚未初始化")
        return self._connection

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
