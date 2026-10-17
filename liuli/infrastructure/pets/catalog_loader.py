import json
import logging
from pathlib import Path
from typing import Any

from ...domain.pet import PetCatalog, PetSkillDefinition, PetSpecies, SkillUnlock


logger = logging.getLogger(__name__)
CATALOG_DIR = Path(__file__).resolve().parents[2] / "resources" / "pets"
ALLOWED_TARGET_TYPES = {"self", "single_enemy", "all_enemies", "single_ally", "all_allies"}
ALLOWED_EFFECT_TYPES = {"damage", "heal", "buff", "debuff"}
PVP_SKILL_COMBINATIONS = {("single_enemy", "damage"), ("single_ally", "heal")}


def load_pet_catalog() -> PetCatalog:
    skill_data = _load_json(CATALOG_DIR / "skills.json")
    pet_data = _load_json(CATALOG_DIR / "pets.json")

    skills: dict[str, PetSkillDefinition] = {}
    for item in _as_list(skill_data, "skills.json"):
        try:
            skill = PetSkillDefinition(
                skill_id=_required_string(item, "skill_id"),
                name=_required_string(item, "name"),
                description=_required_string(item, "description"),
                mp_cost=_nonnegative_int(item, "mp_cost"),
                target_type=_required_string(item, "target_type"),
                effect_type=_required_string(item, "effect_type"),
                effect_value=_nonnegative_int(item, "effect_value"),
            )
            if skill.target_type not in ALLOWED_TARGET_TYPES:
                raise ValueError(f"未知目标类型：{skill.target_type}")
            if skill.effect_type not in ALLOWED_EFFECT_TYPES:
                raise ValueError(f"未知技能效果：{skill.effect_type}")
            if skill.skill_id in skills:
                raise ValueError(f"技能 ID 重复：{skill.skill_id}")
            skills[skill.skill_id] = skill
        except (TypeError, ValueError) as error:
            logger.warning("跳过无效宠物技能定义 %r：%s", item, error)

    species: dict[str, PetSpecies] = {}
    for item in _as_list(pet_data, "pets.json"):
        try:
            level_skills_data = item.get("level_skills", [])
            if not isinstance(level_skills_data, list):
                raise ValueError("level_skills 必须是列表")
            level_skills = tuple(
                SkillUnlock(
                    level=_positive_int(entry, "level"),
                    skill_id=_required_string(entry, "skill_id"),
                )
                for entry in level_skills_data
            )
            pet = PetSpecies(
                species_id=_required_string(item, "pet_id"),
                name=_required_string(item, "name"),
                description=_required_string(item, "description"),
                base_hp=_positive_int(item, "base_hp"),
                hp_per_level=_nonnegative_int(item, "hp_per_level"),
                base_mp=_positive_int(item, "base_mp"),
                mp_per_level=_nonnegative_int(item, "mp_per_level"),
                base_attack=_nonnegative_int(item, "base_attack"),
                attack_per_level=_nonnegative_int(item, "attack_per_level"),
                base_defense=_nonnegative_int(item, "base_defense"),
                defense_per_level=_nonnegative_int(item, "defense_per_level"),
                speed=_nonnegative_int(item, "speed"),
                starting_skills=_string_tuple(item, "starting_skills"),
                level_skills=level_skills,
            )
            if pet.species_id in species:
                raise ValueError(f"宠物 ID 重复：{pet.species_id}")
            referenced_skills = set(pet.starting_skills)
            referenced_skills.update(unlock.skill_id for unlock in pet.level_skills)
            if len(set(pet.starting_skills)) != len(pet.starting_skills):
                raise ValueError("starting_skills 不能重复")
            if len({(unlock.level, unlock.skill_id) for unlock in pet.level_skills}) != len(
                pet.level_skills
            ):
                raise ValueError("level_skills 不能包含重复的等级与技能")
            missing = referenced_skills - skills.keys()
            if missing:
                raise ValueError(f"引用了不存在的技能：{', '.join(sorted(missing))}")
            for skill_id in referenced_skills:
                skill = skills[skill_id]
                if (skill.target_type, skill.effect_type) not in PVP_SKILL_COMBINATIONS:
                    logger.info("技能 %s 暂不支持精灵对战，将不会加入战斗技能快照", skill_id)
            if any(unlock.level < 2 or unlock.level > 100 for unlock in pet.level_skills):
                raise ValueError("等级技能的解锁等级必须介于 2 和 100 之间")
            species[pet.species_id] = pet
        except (TypeError, ValueError) as error:
            logger.warning("跳过无效宠物定义 %r：%s", item, error)

    if not species:
        raise RuntimeError("宠物目录中没有可用的宠物定义")
    return PetCatalog(species=species, skills=skills)


def _load_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"无法加载宠物资源 {path.name}: {error}") from error


def _as_list(data: Any, source: str) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        raise RuntimeError(f"宠物资源 {source} 根节点必须是列表")
    return [item for item in data if isinstance(item, dict)]


def _required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} 必须是非空字符串")
    return value.strip()


def _nonnegative_int(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} 必须是非负整数")
    return value


def _positive_int(data: dict[str, Any], key: str) -> int:
    value = _nonnegative_int(data, key)
    if value == 0:
        raise ValueError(f"{key} 必须大于 0")
    return value


def _string_tuple(data: dict[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{key} 必须是非空字符串列表")
    return tuple(item.strip() for item in value)
