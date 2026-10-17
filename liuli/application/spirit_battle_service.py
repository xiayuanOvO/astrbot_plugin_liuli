import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from ..domain.pet import PetCatalog
from .ports.spirit_battle_repository import SpiritBattleRepository


class SpiritBattleService:
    def __init__(self, repository: SpiritBattleRepository, catalog: PetCatalog):
        self.repository = repository
        self.catalog = catalog

    async def challenge(
        self, platform_id: str, group_id: str, challenger_id: str, opponent_id: str
    ) -> str:
        if challenger_id == opponent_id:
            return "不能向自己发起挑战。"
        now = _now()
        status, record = await self.repository.create_challenge(
            platform_id, group_id, challenger_id, opponent_id, uuid.uuid4().hex,
            now, _after(now, 60),
        )
        battle_id = _battle_tag(record)
        if status == "created":
            return f"已向玩家 {opponent_id} 发起精灵对战挑战（{battle_id}），请对方在 60 秒内发送 /接受对战 或 /拒绝对战。"
        return {
            "challenger_no_pet": "你还没有当前宠物，先使用 /出战宠物 设置参战宠物。",
            "opponent_no_pet": "对方还没有当前宠物，暂时无法挑战。",
            "group_busy": "本群已有未结束的精灵对战，请先完成当前对战。",
            "player_busy": "你或对方已经有一场未结束的精灵对战。",
        }.get(status, "暂时无法创建挑战，请稍后再试。")

    async def accept(self, platform_id: str, group_id: str, player_id: str) -> str:
        now = _now()
        status, record = await self.repository.accept_challenge(
            platform_id, group_id, player_id, now, _after(now, 120), random.random(), self.catalog
        )
        if status != "accepted" or record is None:
            return {
                "no_challenge": "本群没有等待你接受的挑战。",
                "expired": f"挑战（{_battle_tag(record)}）已超时。" if record else "挑战已超时。",
                "player_busy": "挑战者已有另一场未结束的对战。",
                "pet_unavailable": "有一方已没有可用的当前宠物，挑战无法开始。",
            }.get(status, "接受挑战失败，请稍后重试。")
        data = record["data"]
        player_names = _pet_labels(data["players"])
        first = data["current_turn_player_id"]
        return (
            f"精灵对战（{record['battle_id'][:8]}）开始！\n"
            f"{player_names}\n"
            f"先手：{_player_label(data, first)}。每回合限时 120 秒；使用 /精灵技能 技能名称、/精灵防御 或 /精灵认输。"
        )

    async def decline(self, platform_id: str, group_id: str, player_id: str) -> str:
        status, record = await self.repository.decline_challenge(
            platform_id, group_id, player_id, _now()
        )
        if status == "declined" and record:
            return f"挑战（{record['battle_id'][:8]}）已拒绝。"
        if status == "expired" and record:
            return f"挑战（{record['battle_id'][:8]}）已超时。"
        return "本群没有等待你处理的挑战。"

    async def battle_status(self, platform_id: str, group_id: str, player_id: str) -> str:
        active, expired = await self.repository.get_for_player(platform_id, group_id, player_id, _now())
        if not active:
            if expired:
                if expired["state"] == "expired":
                    return f"挑战（{expired['battle_id'][:8]}）已超时。"
                return self._terminal_message(expired)
            return "你当前没有未结束的精灵对战。"
        record = active[0]
        if record["state"] == "pending":
            role = "你发起的挑战正在等待对方接受。" if record["challenger_id"] == player_id else "你有一条待处理挑战，可发送 /接受对战 或 /拒绝对战。"
            return f"挑战（{record['battle_id'][:8]}）：{role}"
        data = record["data"]
        return (
            f"精灵对战（{record['battle_id'][:8]}）·第 {record['round_number']} 回合\n"
            f"{_pet_labels(data['players'])}\n"
            f"当前行动：{_player_label(data, record['current_turn_player_id'])}。"
            + ("轮到你了。" if record["current_turn_player_id"] == player_id else "等待对方行动。")
        )

    async def skill(
        self, platform_id: str, group_id: str, player_id: str, skill_id: str | None
    ) -> str:
        if not skill_id:
            return "用法：/精灵技能 技能名称；使用普通攻击时发送 /精灵技能 普通攻击"
        skill_name = skill_id.strip()
        if skill_name in {"普通攻击", "普攻"}:
            skill_id = "basic_attack"
        else:
            skill_id = next(
                (key for key, skill in self.catalog.skills.items() if skill.name == skill_name),
                skill_id,
            )
        return await self._act(platform_id, group_id, player_id, "skill", skill_id)

    async def defend(self, platform_id: str, group_id: str, player_id: str) -> str:
        return await self._act(platform_id, group_id, player_id, "defend", None)

    async def forfeit(self, platform_id: str, group_id: str, player_id: str) -> str:
        status, record = await self.repository.forfeit(
            platform_id, group_id, player_id, _now()
        )
        if status == "forfeit" and record:
            return self._terminal_message(record, f"{player_id} 主动认输")
        if status == "timeout":
            return "本回合已超时，对战已结算；发送 /对战状态 查看结果。"
        return "本群没有你参与的进行中对战。"

    async def _act(
        self, platform_id: str, group_id: str, player_id: str,
        action_type: str, skill_id: str | None,
    ) -> str:
        now = _now()
        status, value = await self.repository.act(
            platform_id, group_id, player_id, action_type, skill_id, now, _after(now, 120)
        )
        if status.startswith("invalid_action:"):
            return status.removeprefix("invalid_action:")
        if status == "no_battle" or value is None:
            return "本群没有你参与的进行中对战。"
        if status == "timeout":
            return self._terminal_message(value, "行动超时")
        result = value["result"]
        record = value["battle"]
        data = record["data"]
        actor_name = _player_label(data, player_id)
        description = result["skill_name"] or "行动"
        if result["damage"]:
            description += f"，造成 {result['damage']} 点伤害"
        if result["healing"]:
            description += f"，恢复 {result['healing']} 点生命"
        hpmp = "；".join(
            f"{_player_label(data, pid)} 生命 {p['hp']}/{p['max_hp']} · 魔力 {p['mp']}/{p['max_mp']}"
            for pid, p in data["players"].items()
        )
        if record["state"] in {"finished", "draw"}:
            return f"对战（{record['battle_id'][:8]}）{actor_name} 使用{description}。\n{hpmp}\n{self._terminal_message(record)}"
        next_player = record["current_turn_player_id"]
        return (
            f"对战（{record['battle_id'][:8]}）{actor_name} 使用{description}。\n"
            f"{hpmp}\n轮到 {_player_label(data, next_player)} 行动（第 {record['round_number']} 回合，120 秒内）。"
        )

    def _terminal_message(self, record: dict[str, Any], reason: str | None = None) -> str:
        data = record["data"]
        state = record["state"]
        prefix = f"对战（{record['battle_id'][:8]}）"
        if state == "expired":
            return prefix + "挑战已过期。"
        if state == "draw":
            return prefix + "平局。"
        winner = record.get("winner_id") or data.get("winner_id")
        if winner:
            return prefix + f"{_player_label(data, winner)} 获胜" + (f"（{reason}）。" if reason else "！")
        return prefix + "已结束。"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _after(now: str, seconds: int) -> str:
    return (datetime.fromisoformat(now) + timedelta(seconds=seconds)).isoformat(timespec="microseconds")


def _battle_tag(record: dict[str, Any] | None) -> str:
    return record["battle_id"][:8] if record else "未知编号"


def _pet_labels(players: dict[str, Any]) -> str:
    return " 对战 ".join(
        f"{player['pet_name']}（{player['species_name']}，{player['level']}级）"
        for player in players.values()
    )


def _player_label(data: dict[str, Any], player_id: str | None) -> str:
    if player_id is None:
        return "无人"
    player = data.get("players", {}).get(player_id)
    return f"{player['pet_name']}" if player else "玩家"
