import aiosqlite

from ..schema import (
    CREATE_DUNGEON_ACTIONS_TABLE,
    CREATE_DUNGEON_PLAYER_STATE_TABLE,
    CREATE_DUNGEON_PROGRESS_TABLE,
    CREATE_DUNGEON_RUN_ACTIVE_INDEX,
    CREATE_DUNGEON_RUN_EVENTS_TABLE,
    CREATE_DUNGEON_RUNS_TABLE,
)


VERSION = 4


async def apply(connection: aiosqlite.Connection) -> None:
    """Create dungeon exploration, event history, and player progression tables."""
    await connection.execute(CREATE_DUNGEON_RUNS_TABLE)
    await connection.execute(CREATE_DUNGEON_RUN_ACTIVE_INDEX)
    await connection.execute(CREATE_DUNGEON_PROGRESS_TABLE)
    await connection.execute(CREATE_DUNGEON_PLAYER_STATE_TABLE)
    await connection.execute(CREATE_DUNGEON_RUN_EVENTS_TABLE)
    await connection.execute(CREATE_DUNGEON_ACTIONS_TABLE)
