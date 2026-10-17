from dataclasses import dataclass
from typing import Any


@dataclass
class PlayerProfile:
    name: str = ""
    level: int = 1
    hp: int = 140
    mp: int = 80

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlayerProfile":
        stats = data.get("stats")
        if not isinstance(stats, dict):
            stats = {}
        return cls(
            name=str(data.get("name") or ""),
            level=int(data.get("level", 1)),
            hp=int(stats.get("HP", 140)),
            mp=int(stats.get("MP", 80)),
        )

    def rename(self, name: str) -> None:
        self.name = name

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "level": self.level,
            "stats": {"HP": self.hp, "MP": self.mp},
        }
