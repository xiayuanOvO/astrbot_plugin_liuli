import json
from typing import Any

from ....application.ports.profile_repository import ProfileRepository, ProfileUpdate
from .database import SQLiteDatabase


class SQLiteProfileRepository(ProfileRepository):
    """SQLite adapter implementing the application profile repository port."""

    def __init__(self, database: SQLiteDatabase):
        self.database = database

    async def get_or_create_profile(
        self,
        scope: str,
        platform_id: str,
        entity_id: str,
        initial_data: dict[str, Any],
    ) -> dict[str, Any]:
        async with self.database.lock:
            encoded = json.dumps(initial_data, ensure_ascii=False, separators=(",", ":"))
            await self.database.connection.execute(
                """INSERT OR IGNORE INTO profiles(scope, platform_id, entity_id, data_json)
                   VALUES(?, ?, ?, ?)""",
                (scope, platform_id, entity_id, encoded),
            )
            await self.database.connection.commit()
            return await self._get_unlocked(scope, platform_id, entity_id)

    async def get_profile(self, scope: str, platform_id: str, entity_id: str) -> dict[str, Any]:
        async with self.database.lock:
            async with self.database.connection.execute(
                "SELECT data_json FROM profiles WHERE scope=? AND platform_id=? AND entity_id=?",
                (scope, platform_id, entity_id),
            ) as cursor:
                row = await cursor.fetchone()
            return self._decode(row["data_json"]) if row else {}

    async def update_profile(
        self,
        scope: str,
        platform_id: str,
        entity_id: str,
        update: ProfileUpdate,
    ) -> dict[str, Any]:
        async with self.database.lock:
            data = await self._get_unlocked(scope, platform_id, entity_id)
            update(data)
            encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            await self.database.connection.execute(
                """INSERT INTO profiles(scope, platform_id, entity_id, data_json, updated_at)
                   VALUES(?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(scope, platform_id, entity_id)
                   DO UPDATE SET data_json=excluded.data_json, updated_at=CURRENT_TIMESTAMP""",
                (scope, platform_id, entity_id, encoded),
            )
            await self.database.connection.commit()
            return data

    async def _get_unlocked(self, scope: str, platform_id: str, entity_id: str) -> dict[str, Any]:
        async with self.database.connection.execute(
            "SELECT data_json FROM profiles WHERE scope=? AND platform_id=? AND entity_id=?",
            (scope, platform_id, entity_id),
        ) as cursor:
            row = await cursor.fetchone()
        return self._decode(row["data_json"]) if row else {}

    @staticmethod
    def _decode(value: str) -> dict[str, Any]:
        try:
            data = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}
