from __future__ import annotations

import random
from typing import Any

from .pet import PetCatalog
from .spirit_battle import first_turn_probability
from .world import WorldCatalog


def requirements_met(
    requirements: list[dict[str, str]], cleared: set[tuple[str, str]]
) -> bool:
    return all((item["dungeon_id"], item["difficulty_id"]) in cleared for item in requirements)


def make_route(difficulty: dict[str, Any], catalog: WorldCatalog) -> list[dict[str, Any]]:
    route = []
    for stage in difficulty["stages"]:
        chosen = _weighted_choice(stage)
        route.append({"event_id": chosen["event_id"]})
    route.append({"event_id": "__boss__", "enemy_id": difficulty["boss_enemy_id"]})
    return route


def make_encounter(
    player_id: str,
    pet: dict[str, Any],
    enemy_id: str,
    enemy_level: int,
    enemy_template: dict[str, Any],
    pet_catalog: PetCatalog,
    rng: random.Random | random.SystemRandom,
) -> dict[str, Any]:
    enemy = _enemy_snapshot(enemy_template, enemy_level, pet_catalog)
    enemy["pet_id"] = enemy_id
    enemy["pet_name"] = enemy_template["name"]
    enemy["species_name"] = enemy_template["name"]
    enemy["is_enemy"] = True
    pet["is_enemy"] = False
    enemy_actor_id = "__enemy__"
    probability = first_turn_probability(pet["speed"], enemy["speed"])
    first_turn = player_id if rng.random() < probability else enemy_actor_id
    return {
        "status": "active",
        "players": {player_id: pet, enemy_actor_id: enemy},
        "current_turn_player_id": first_turn,
        "round_number": 1,
        "acted_this_round": [],
        "winner_id": None,
        "first_turn": {
            "player_speed": pet["speed"],
            "enemy_speed": enemy["speed"],
            "player_probability": probability,
            "player_id": first_turn,
        },
        "enemy_id": enemy_id,
    }


def choose_enemy_action(combat: dict[str, Any]) -> tuple[str, str]:
    enemy = combat["players"]["__enemy__"]
    hp_ratio = enemy["hp"] / max(enemy["max_hp"], 1)
    skills = list(enemy.get("skills", {}).values())
    heals = [skill for skill in skills if skill["effect_type"] == "heal"]
    if heals and hp_ratio <= 0.45:
        skill = min(heals, key=lambda entry: entry["mp_cost"])
        if enemy["mp"] >= skill["mp_cost"]:
            return "skill", skill["skill_id"]
    attacks = [skill for skill in skills if skill["effect_type"] == "damage"]
    affordable = [skill for skill in attacks if enemy["mp"] >= skill["mp_cost"]]
    if affordable:
        skill = max(affordable, key=lambda entry: (entry["effect_value"], -entry["mp_cost"]))
        return "skill", skill["skill_id"]
    return "skill", "basic_attack"


def experience_reward(enemy_template: dict[str, Any], xp_multiplier: float) -> int:
    return max(1, round(enemy_template["exp_reward"] * xp_multiplier))


def _enemy_snapshot(
    template: dict[str, Any], level: int, pet_catalog: PetCatalog
) -> dict[str, Any]:
    skills = {}
    for skill_id in template["skills"]:
        skill = pet_catalog.skills[skill_id]
        if (skill.target_type, skill.effect_type) not in {
            ("single_enemy", "damage"), ("single_ally", "heal")
        }:
            continue
        skills[skill_id] = {
            "skill_id": skill.skill_id,
            "name": skill.name,
            "mp_cost": skill.mp_cost,
            "target_type": skill.target_type,
            "effect_type": skill.effect_type,
            "effect_value": skill.effect_value,
        }
    max_hp = template["base_hp"] + (level - 1) * template["hp_per_level"]
    max_mp = template["base_mp"] + (level - 1) * template["mp_per_level"]
    return {
        "level": level,
        "hp": max_hp,
        "max_hp": max_hp,
        "mp": max_mp,
        "max_mp": max_mp,
        "attack": template["base_attack"] + (level - 1) * template["attack_per_level"],
        "defense": template["base_defense"] + (level - 1) * template["defense_per_level"],
        "speed": template["speed"],
        "guarding": False,
        "skills": skills,
    }


def _weighted_choice(entries: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(entry["weight"] for entry in entries)
    roll = random.randrange(total)
    for entry in entries:
        roll -= entry["weight"]
        if roll < 0:
            return entry
    return entries[-1]
