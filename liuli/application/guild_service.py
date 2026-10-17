from typing import Any

from ..domain.adventurer import AdventurerProfile
from .ports.profile_repository import ProfileRepository


class GuildService:
    def __init__(self, repository: ProfileRepository):
        self.repository = repository

    async def home(self, platform_id: str, player_id: str, name: str) -> str:
        data = await self.repository.get_profile("guild", platform_id, player_id)
        profile = AdventurerProfile.from_dict(data)
        text = f"欢迎来到冒险者公会，{name}~\n要做点什么呢？\n════════════════\n"
        if not profile.is_registered:
            return text + "请先发送 /注册冒险者"
        return text + f"当前等级：{profile.rank}\n/查看委托\n/接取委托 <编号>"

    async def register_adventurer(self, platform_id: str, player_id: str) -> str:
        def register(data: dict[str, Any]) -> None:
            profile = AdventurerProfile.from_dict(data)
            profile.register()
            data.clear()
            data.update(profile.to_dict())

        data = await self.repository.update_profile("guild", platform_id, player_id, register)
        profile = AdventurerProfile.from_dict(data)
        return (
            "正在评估您的实力...\n\n冒险者注册成功！\n"
            f"根据您的实力，您的冒险者等级为：{profile.rank}"
        )

