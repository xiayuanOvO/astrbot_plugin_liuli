"""Deterministic rules for a two-player spirit battle."""

from __future__ import annotations

import math
from typing import Any


MAX_ROUNDS = 30
BASIC_ATTACK_ID = "basic_attack"


def first_turn_probability(first_speed: int, second_speed: int) -> float:
    return 0.5 + 0.25 * (first_speed - second_speed) / max(first_speed + second_speed, 1)


def resolve_action(
    state: dict[str, Any], player_id: str, action_type: str, skill_id: str | None = None
) -> dict[str, Any]:
    """Apply one validated action to a decoded battle state and return its result."""
    if state.get("status") != "active":
        raise ValueError("这场对战已经结束。")
    if state.get("current_turn_player_id") != player_id:
        raise ValueError("现在还不是你的行动回合。")

    players = state["players"]
    if player_id not in players:
        raise ValueError("你不在这场对战中。")
    opponent_id = next(candidate for candidate in players if candidate != player_id)
    actor = players[player_id]
    target = players[opponent_id]
    result: dict[str, Any] = {
        "player_id": player_id,
        "action_type": action_type,
        "skill_id": None,
        "skill_name": None,
        "damage": 0,
        "healing": 0,
    }

    if action_type == "defend":
        target["guarding"] = False
        actor["guarding"] = True
        result["skill_name"] = "防御姿态"
    elif action_type == "skill":
        skill = _get_skill(actor, skill_id)
        if actor["mp"] < skill["mp_cost"]:
            raise ValueError(f"魔力不足，需要 {skill['mp_cost']} 点魔力，目前有 {actor['mp']} 点魔力。")
        actor["mp"] -= skill["mp_cost"]
        result["skill_id"] = skill["skill_id"]
        result["skill_name"] = skill["name"]
        if skill["effect_type"] == "damage":
            damage = max(1, skill["effect_value"] + actor["attack"] // 2 - target["defense"])
            if target["guarding"]:
                damage = max(1, math.floor(damage / 2))
            target["hp"] = max(0, target["hp"] - damage)
            target["guarding"] = False
            result["damage"] = damage
        elif skill["effect_type"] == "heal":
            healing = min(skill["effect_value"], actor["max_hp"] - actor["hp"])
            actor["hp"] += healing
            target["guarding"] = False
            result["healing"] = healing
        else:
            raise ValueError("该技能效果暂不支持精灵对战。")
    else:
        raise ValueError("未知的对战行动。")

    acted = state.setdefault("acted_this_round", [])
    acted.append(player_id)
    state["current_turn_player_id"] = opponent_id
    if target["hp"] <= 0:
        _finish(state, player_id, "finished")
    elif len(acted) == 2:
        state["acted_this_round"] = []
        if state["round_number"] >= MAX_ROUNDS:
            _finish_by_remaining_hp(state)
        else:
            state["round_number"] += 1

    result["status"] = state["status"]
    result["winner_id"] = state.get("winner_id")
    result["round_number"] = state["round_number"]
    result["next_player_id"] = state.get("current_turn_player_id")
    result["players"] = {
        key: {"hp": value["hp"], "max_hp": value["max_hp"], "mp": value["mp"], "max_mp": value["max_mp"]}
        for key, value in players.items()
    }
    return result


def _get_skill(player: dict[str, Any], skill_id: str | None) -> dict[str, Any]:
    if skill_id == BASIC_ATTACK_ID:
        return {
            "skill_id": BASIC_ATTACK_ID,
            "name": "普通攻击",
            "mp_cost": 0,
            "effect_type": "damage",
            "effect_value": 8,
        }
    skill = player.get("skills", {}).get(skill_id or "")
    if skill is None:
        raise ValueError("该技能未装备或暂不支持精灵对战。")
    return skill


def _finish(state: dict[str, Any], winner_id: str | None, status: str) -> None:
    state["status"] = status
    state["winner_id"] = winner_id
    state["current_turn_player_id"] = None


def _finish_by_remaining_hp(state: dict[str, Any]) -> None:
    player_ids = list(state["players"])
    first, second = (state["players"][player_id] for player_id in player_ids)
    first_ratio = first["hp"] * max(second["max_hp"], 1)
    second_ratio = second["hp"] * max(first["max_hp"], 1)
    winner = player_ids[0] if first_ratio > second_ratio else player_ids[1] if second_ratio > first_ratio else None
    _finish(state, winner, "finished" if winner else "draw")
