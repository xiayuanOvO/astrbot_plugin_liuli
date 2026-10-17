from typing import Any, Protocol

from ...domain.pet import PetCatalog
from ...domain.world import WorldCatalog


class DungeonRepository(Protocol):
    async def start_run(
        self, platform_id: str, player_id: str, run_id: str, dungeon_id: str,
        difficulty: dict[str, Any], route: list[dict[str, Any]], city_id: str,
        now: str, pet_catalog: PetCatalog, world_catalog: WorldCatalog,
    ) -> tuple[str, dict[str, Any] | None]: ...

    async def get_active_run(
        self, platform_id: str, player_id: str
    ) -> dict[str, Any] | None: ...

    async def get_progress(
        self, platform_id: str, player_id: str, starting_city_id: str
    ) -> tuple[set[tuple[str, str]], str]: ...

    async def advance(
        self, platform_id: str, player_id: str, now: str,
        world_catalog: WorldCatalog, pet_catalog: PetCatalog,
    ) -> tuple[str, dict[str, Any] | None]: ...

    async def choose(
        self, platform_id: str, player_id: str, option_id: str, now: str,
        world_catalog: WorldCatalog, pet_catalog: PetCatalog,
    ) -> tuple[str, dict[str, Any] | None]: ...

    async def act(
        self, platform_id: str, player_id: str, action_type: str, skill_id: str | None,
        request_key: str | None, now: str, world_catalog: WorldCatalog,
        pet_catalog: PetCatalog, expected_button_token: str | None = None,
    ) -> tuple[str, dict[str, Any] | None]: ...

    async def retreat(self, platform_id: str, player_id: str, now: str) -> tuple[str, dict[str, Any] | None]: ...

    async def rest_pet(
        self, platform_id: str, player_id: str, now: str,
        starting_city_id: str, world_catalog: WorldCatalog, pet_catalog: PetCatalog,
    ) -> tuple[str, dict[str, Any] | None]: ...
