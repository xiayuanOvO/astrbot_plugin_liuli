from typing import Protocol


class CurrencyRepository(Protocol):
    async def get_balance(self, platform_id: str, player_id: str) -> int: ...

    async def claim_daily_reward(
        self,
        platform_id: str,
        player_id: str,
        day: str,
        amount: int,
    ) -> tuple[bool, int]: ...

    async def spend(
        self,
        platform_id: str,
        player_id: str,
        amount: int,
        reason: str,
    ) -> int | None: ...
