from typing import Any

from ..domain.player import PlayerProfile
from .ports.profile_repository import ProfileRepository


class PlayerService:
    def __init__(self, repository: ProfileRepository):
        self.repository = repository

    async def ensure_initialized(self, platform_id: str, player_id: str, platform_name: str) -> PlayerProfile:
        initial_profile = PlayerProfile(name=platform_name).to_dict()
        data = await self.repository.get_or_create_profile(
            "user", platform_id, player_id, initial_profile
        )
        profile = PlayerProfile.from_dict(data)

        # Older profile payloads may contain player combat or race attributes.
        # Keep only the player name; combat stats belong to pets.
        def keep_name_only(stored: dict[str, Any]) -> None:
            stored.clear()
            stored.update(profile.to_dict())

        await self.repository.update_profile("user", platform_id, player_id, keep_name_only)
        return profile

    async def query(self, platform_id: str, player_id: str) -> str:
        data = await self.repository.get_profile("user", platform_id, player_id)
        if not data:
            return "未找到该玩家的档案。"
        profile = PlayerProfile.from_dict(data)
        return f"玩家：{profile.name or player_id}"

    async def rename(self, platform_id: str, player_id: str, new_name: str) -> str:
        new_name = new_name.strip()
        if not new_name:
            return "昵称不能为空。用法：/改名 昵称"
        if len(new_name) > 32:
            return "昵称不能超过 32 个字符。"

        def apply_name(data: dict[str, Any]) -> None:
            profile = PlayerProfile.from_dict(data)
            profile.rename(new_name)
            data.clear()
            data.update(profile.to_dict())

        await self.repository.update_profile("user", platform_id, player_id, apply_name)
        return f"昵称已修改为：{new_name}"
