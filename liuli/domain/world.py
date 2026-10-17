from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorldCatalog:
    world: dict[str, Any]
    countries: dict[str, dict[str, Any]]
    cities: dict[str, dict[str, Any]]
    dungeons: dict[str, dict[str, Any]]
    events: dict[str, dict[str, Any]]
    enemies: dict[str, dict[str, Any]]

    def difficulty(self, dungeon_id: str, difficulty_id: str) -> dict[str, Any] | None:
        dungeon = self.dungeons.get(dungeon_id)
        if not dungeon:
            return None
        return next(
            (entry for entry in dungeon["difficulties"] if entry["difficulty_id"] == difficulty_id),
            None,
        )
