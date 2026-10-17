from dataclasses import dataclass


@dataclass(frozen=True)
class Quest:
    quest_id: str
    title: str
    rank: str
    reward: str


QUESTS: dict[str, Quest] = {
    "1": Quest(quest_id="1", title="清理魔物", rank="A", reward="10 银币"),
}
