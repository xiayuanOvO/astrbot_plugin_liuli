from dataclasses import dataclass, field
from typing import Any


@dataclass
class AdventurerProfile:
    rank: str | None = None
    accepted_quests: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AdventurerProfile":
        accepted = data.get("accepted_quests", [])
        if not isinstance(accepted, list):
            accepted = []
        return cls(
            rank=str(data["rank"]) if data.get("rank") else None,
            accepted_quests=[str(item) for item in accepted],
        )

    @property
    def is_registered(self) -> bool:
        return self.rank is not None

    def register(self) -> None:
        if self.rank is None:
            self.rank = "F"

    def accept_quest(self, quest_id: str) -> str:
        if not self.is_registered:
            return "not_registered"
        if quest_id in self.accepted_quests:
            return "already_accepted"
        self.accepted_quests.append(quest_id)
        return "accepted"

    def to_dict(self) -> dict[str, Any]:
        return {"rank": self.rank, "accepted_quests": self.accepted_quests}
