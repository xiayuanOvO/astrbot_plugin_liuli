from typing import Protocol

from ...domain.pet import Pet, PetSpecies


class PetRepository(Protocol):
    async def list_pets(self, platform_id: str, player_id: str) -> list[Pet]: ...

    async def get_pet(self, platform_id: str, player_id: str, pet_id: str) -> Pet | None: ...

    async def adopt_initial_pet(self, pet: Pet) -> bool: ...

    async def rename_pet(
        self,
        platform_id: str,
        player_id: str,
        pet_id: str,
        name: str,
    ) -> bool: ...

    async def set_active_pet(
        self, platform_id: str, player_id: str, pet_id: str
    ) -> bool: ...

    async def equip_skill(
        self, platform_id: str, player_id: str, pet_id: str, skill_id: str
    ) -> tuple[str, int | None]: ...

    async def unequip_skill(
        self, platform_id: str, player_id: str, pet_id: str, skill_id: str
    ) -> str: ...

    async def grant_experience(
        self,
        platform_id: str,
        player_id: str,
        pet_id: str,
        amount: int,
        species: PetSpecies,
    ) -> tuple[Pet | None, list[str]]: ...
