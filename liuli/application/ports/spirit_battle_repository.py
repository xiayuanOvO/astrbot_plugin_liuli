from typing import Any, Protocol

from ...domain.pet import PetCatalog


class SpiritBattleRepository(Protocol):
    async def create_challenge(
        self, platform_id: str, group_id: str, challenger_id: str, opponent_id: str,
        battle_id: str, now: str, expires_at: str,
    ) -> tuple[str, dict[str, Any] | None]: ...

    async def accept_challenge(
        self, platform_id: str, group_id: str, player_id: str, now: str,
        expires_at: str, roll: float, catalog: PetCatalog,
    ) -> tuple[str, dict[str, Any] | None]: ...

    async def decline_challenge(
        self, platform_id: str, group_id: str, player_id: str, now: str
    ) -> tuple[str, dict[str, Any] | None]: ...

    async def get_for_player(
        self, platform_id: str, group_id: str, player_id: str, now: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]: ...

    async def act(
        self, platform_id: str, group_id: str, player_id: str, action_type: str,
        skill_id: str | None, now: str, next_expires_at: str,
    ) -> tuple[str, dict[str, Any] | None]: ...

    async def forfeit(
        self, platform_id: str, group_id: str, player_id: str, now: str
    ) -> tuple[str, dict[str, Any] | None]: ...
