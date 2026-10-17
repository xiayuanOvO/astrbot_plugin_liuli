from collections.abc import Callable
from typing import Any, Protocol


ProfileUpdate = Callable[[dict[str, Any]], None]


class ProfileRepository(Protocol):
    """应用层读写玩家和公会档案所需的接口。"""

    async def get_or_create_profile(
        self,
        scope: str,
        platform_id: str,
        entity_id: str,
        initial_data: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def get_profile(
        self, scope: str, platform_id: str, entity_id: str
    ) -> dict[str, Any]: ...

    async def update_profile(
        self,
        scope: str,
        platform_id: str,
        entity_id: str,
        update: ProfileUpdate,
    ) -> dict[str, Any]: ...
