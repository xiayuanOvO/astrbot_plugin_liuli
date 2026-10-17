import sqlite3

from ....application.ports.currency_repository import CurrencyRepository
from .database import SQLiteDatabase


class SQLiteCurrencyRepository(CurrencyRepository):
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    async def get_balance(self, platform_id: str, player_id: str) -> int:
        async with self.database.lock:
            async with self.database.connection.execute(
                """SELECT balance FROM currency_accounts
                   WHERE platform_id=? AND player_id=?""",
                (platform_id, player_id),
            ) as cursor:
                row = await cursor.fetchone()
            return int(row["balance"]) if row else 0

    async def claim_daily_reward(
        self,
        platform_id: str,
        player_id: str,
        day: str,
        amount: int,
    ) -> tuple[bool, int]:
        idempotency_key = f"signin:{platform_id}:{player_id}:{day}"
        async with self.database.lock:
            connection = self.database.connection
            await connection.execute("BEGIN IMMEDIATE")
            try:
                async with connection.execute(
                    """SELECT 1 FROM currency_transactions WHERE idempotency_key=?""",
                    (idempotency_key,),
                ) as cursor:
                    already_claimed = await cursor.fetchone() is not None
                await connection.execute(
                    """INSERT OR IGNORE INTO currency_accounts(platform_id, player_id)
                       VALUES(?, ?)""",
                    (platform_id, player_id),
                )
                if already_claimed:
                    balance = await self._get_balance_unlocked(platform_id, player_id)
                    await connection.commit()
                    return False, balance

                await connection.execute(
                    """UPDATE currency_accounts
                       SET balance=balance + ?, updated_at=CURRENT_TIMESTAMP
                       WHERE platform_id=? AND player_id=?""",
                    (amount, platform_id, player_id),
                )
                await connection.execute(
                    """INSERT INTO currency_transactions
                       (platform_id, player_id, amount, reason, idempotency_key)
                       VALUES(?, ?, ?, ?, ?)""",
                    (
                        platform_id,
                        player_id,
                        amount,
                        f"每日签到 {day}",
                        idempotency_key,
                    ),
                )
                balance = await self._get_balance_unlocked(platform_id, player_id)
                await connection.commit()
                return True, balance
            except sqlite3.IntegrityError:
                await connection.rollback()
                async with connection.execute(
                    """SELECT 1 FROM currency_transactions WHERE idempotency_key=?""",
                    (idempotency_key,),
                ) as cursor:
                    duplicate = await cursor.fetchone() is not None
                if not duplicate:
                    raise
                balance = await self._get_balance_unlocked(platform_id, player_id)
                return False, balance
            except Exception:
                await connection.rollback()
                raise

    async def spend(
        self,
        platform_id: str,
        player_id: str,
        amount: int,
        reason: str,
    ) -> int | None:
        async with self.database.lock:
            connection = self.database.connection
            await connection.execute("BEGIN IMMEDIATE")
            try:
                await connection.execute(
                    """INSERT OR IGNORE INTO currency_accounts(platform_id, player_id)
                       VALUES(?, ?)""",
                    (platform_id, player_id),
                )
                balance = await self._get_balance_unlocked(platform_id, player_id)
                if balance < amount:
                    await connection.rollback()
                    return None

                await connection.execute(
                    """UPDATE currency_accounts
                       SET balance=balance - ?, updated_at=CURRENT_TIMESTAMP
                       WHERE platform_id=? AND player_id=?""",
                    (amount, platform_id, player_id),
                )
                await connection.execute(
                    """INSERT INTO currency_transactions
                       (platform_id, player_id, amount, reason)
                       VALUES(?, ?, ?, ?)""",
                    (platform_id, player_id, -amount, reason),
                )
                balance -= amount
                await connection.commit()
                return balance
            except Exception:
                await connection.rollback()
                raise

    async def _get_balance_unlocked(self, platform_id: str, player_id: str) -> int:
        async with self.database.connection.execute(
            """SELECT balance FROM currency_accounts
               WHERE platform_id=? AND player_id=?""",
            (platform_id, player_id),
        ) as cursor:
            row = await cursor.fetchone()
        return int(row["balance"]) if row else 0
