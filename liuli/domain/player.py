from dataclasses import dataclass
from typing import Any


@dataclass
class PlayerProfile:
    name: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlayerProfile":
        return cls(name=str(data.get("name") or ""))

    def rename(self, name: str) -> None:
        self.name = name

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
        }
