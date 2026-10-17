import aiosqlite

from ..schema import (
    CREATE_ONE_ACTIVE_PET_INDEX,
    CREATE_PET_OWNER_INDEX,
    CREATE_PET_SKILLS_TABLE,
    CREATE_PETS_TABLE,
)


VERSION = 2


async def apply(connection: aiosqlite.Connection) -> None:
    """Create pet instance and learned/equipped skill tables."""
    await connection.execute(CREATE_PETS_TABLE)
    await connection.execute(CREATE_PET_OWNER_INDEX)
    await connection.execute(CREATE_PET_SKILLS_TABLE)
    await connection.execute(CREATE_ONE_ACTIVE_PET_INDEX)
