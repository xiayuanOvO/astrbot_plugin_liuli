import aiosqlite

from ..schema import (
    CREATE_CURRENCY_ACCOUNTS_TABLE,
    CREATE_CURRENCY_TRANSACTIONS_TABLE,
    CREATE_CURRENCY_TRANSACTION_PLAYER_INDEX,
    CREATE_PROFILES_TABLE,
)


VERSION = 1


async def apply(connection: aiosqlite.Connection) -> None:
    """Create the initial profile and currency tables."""
    await connection.execute(CREATE_PROFILES_TABLE)
    await connection.execute(CREATE_CURRENCY_ACCOUNTS_TABLE)
    await connection.execute(CREATE_CURRENCY_TRANSACTIONS_TABLE)
    await connection.execute(CREATE_CURRENCY_TRANSACTION_PLAYER_INDEX)
