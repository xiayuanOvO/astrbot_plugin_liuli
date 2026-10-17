from typing import Any

from ..domain.adventurer import AdventurerProfile
from ..domain.quest import QUESTS, Quest
from .ports.profile_repository import ProfileRepository


class QuestService:
    def __init__(self, repository: ProfileRepository):
        self.repository = repository

    @staticmethod
    def view_quest(quest_id: str | None) -> str:
        if quest_id is None:
            rows = ["══════ 委托 ══════"]
            rows.extend(QuestService._format_quest(quest) for quest in QUESTS.values())
            rows.append("使用 /查看委托 <编号> 查看详情")
            return "\n".join(rows)
        quest = QUESTS.get(quest_id)
        if quest is None:
            return f"没有编号为 {quest_id} 的委托。"
        return (
            f"══════ 委托 {quest.quest_id} ══════\n"
            f"名称：{quest.title}\n等级：{quest.rank}级\n报酬：{quest.reward}\n"
            f"使用 /接取委托 {quest.quest_id} 接取"
        )

    async def accept_quest(self, platform_id: str, player_id: str, quest_id: str) -> str:
        quest = QUESTS.get(quest_id)
        if quest is None:
            return f"没有编号为 {quest_id} 的委托。"

        outcome = "not_registered"

        def accept(data: dict[str, Any]) -> None:
            nonlocal outcome
            profile = AdventurerProfile.from_dict(data)
            outcome = profile.accept_quest(quest_id)
            data.clear()
            data.update(profile.to_dict())

        await self.repository.update_profile("guild", platform_id, player_id, accept)
        if outcome == "not_registered":
            return "请先发送 /注册冒险者，再接取委托。"
        if outcome == "already_accepted":
            return "你已经接取过这项委托。"
        return f"已接取委托：{quest.title}。"

    @staticmethod
    def _format_quest(quest: Quest) -> str:
        return f"{quest.quest_id} {quest.title} —— {quest.rank}级 —— {quest.reward}"
