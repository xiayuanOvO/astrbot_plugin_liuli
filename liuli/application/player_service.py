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
        return PlayerProfile.from_dict(data)

    @staticmethod
    def status(profile: PlayerProfile, fallback_name: str) -> str:
        return (
            f"{profile.name or fallback_name}の角色状态：\n"
            f"👑等级：{profile.level}\n"
            f"🩸生命：{profile.hp}\n"
            f"💧魔力：{profile.mp}"
        )

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
