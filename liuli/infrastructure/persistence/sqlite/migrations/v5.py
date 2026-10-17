import aiosqlite


VERSION = 5


async def apply(connection: aiosqlite.Connection) -> None:
    """Add request deduplication to dungeon actions on existing databases."""
    async with connection.execute("PRAGMA table_info(dungeon_actions)") as cursor:
        columns = await cursor.fetchall()
    if not any(column[1] == "request_key" for column in columns):
        await connection.execute(
            "ALTER TABLE dungeon_actions ADD COLUMN request_key TEXT"
        )
    await connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_dungeon_actions_request_key "
        "ON dungeon_actions(request_key)"
    )
