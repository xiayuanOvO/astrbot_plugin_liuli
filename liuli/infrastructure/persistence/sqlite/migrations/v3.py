import aiosqlite

from ..schema import (
    CREATE_SPIRIT_BATTLE_ACTIONS_INDEX,
    CREATE_SPIRIT_BATTLE_ACTIONS_TABLE,
    CREATE_SPIRIT_BATTLE_GROUP_INDEX,
    CREATE_SPIRIT_BATTLE_PLAYER_INDEX,
    CREATE_SPIRIT_BATTLES_TABLE,
)


VERSION = 3


async def apply(connection: aiosqlite.Connection) -> None:
    """Create spirit battle and action history tables."""
    await connection.execute(CREATE_SPIRIT_BATTLES_TABLE)
    await connection.execute(CREATE_SPIRIT_BATTLE_PLAYER_INDEX)
    await connection.execute(CREATE_SPIRIT_BATTLE_GROUP_INDEX)
    await connection.execute(CREATE_SPIRIT_BATTLE_ACTIONS_TABLE)
    await connection.execute(CREATE_SPIRIT_BATTLE_ACTIONS_INDEX)
