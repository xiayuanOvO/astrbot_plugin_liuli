import json
import logging
from pathlib import Path
from typing import Any

from ...domain.pet import PetCatalog
from ...domain.world import WorldCatalog


logger = logging.getLogger(__name__)
WORLD_DIR = Path(__file__).resolve().parents[2] / "resources" / "world"
ALLOWED_EVENTS = {"story", "spirit_battle", "rest", "choice", "hazard", "treasure"}
ALLOWED_EFFECTS = {"rest", "currency", "damage", "battle"}


def load_world_catalog(pet_catalog: PetCatalog) -> WorldCatalog:
    world = _read(WORLD_DIR / "world.json")
    countries = _mapped(_read(WORLD_DIR / "countries.json"), "country_id", "countries.json")
    cities = _mapped(_read(WORLD_DIR / "cities.json"), "city_id", "cities.json")
    dungeons = _mapped(_read(WORLD_DIR / "dungeons.json"), "dungeon_id", "dungeons.json")
    events = _mapped(
        _read(WORLD_DIR / "events.json"), "event_id", "events.json",
        label_fields=("title", "text"),
    )
    enemies = _mapped(_read(WORLD_DIR / "enemies.json"), "enemy_id", "enemies.json")

    country_refs: set[str] = set()
    for country in countries.values():
        aliases = country.get("aliases", [])
        if not isinstance(aliases, list):
            raise RuntimeError(f"国家 {country['country_id']} 的 aliases 必须是列表")
        refs = [country["country_id"], *aliases]
        for ref in refs:
            if not isinstance(ref, str) or not ref.strip():
                raise RuntimeError(f"国家 {country['country_id']} 的编号或简称必须是非空字符串")
            normalized = ref.strip().casefold()
            if normalized in country_refs:
                raise RuntimeError(f"国家编号或简称重复：{ref}")
            country_refs.add(normalized)

    _required_string(world, "world_id")
    _required_string(world, "name")
    if world.get("starting_country_id") not in countries:
        raise RuntimeError("world.json 的 starting_country_id 未引用有效国家")
    if world.get("starting_city_id") not in cities:
        raise RuntimeError("world.json 的 starting_city_id 未引用有效城市")

    for country in countries.values():
        _validate_requirements(country.get("unlock_requires", []), dungeons)
        city_ids = [city["city_id"] for city in cities.values() if city["country_id"] == country["country_id"]]
        if not city_ids:
            raise RuntimeError(f"国家 {country['country_id']} 没有关联城市")
    for city in cities.values():
        if city.get("country_id") not in countries:
            raise RuntimeError(f"城市 {city['city_id']} 引用了未知国家")
        if not isinstance(city.get("dungeon_ids"), list) or not city["dungeon_ids"]:
            raise RuntimeError(f"城市 {city['city_id']} 必须至少列出一个副本")
        if any(dungeon_id not in dungeons for dungeon_id in city["dungeon_ids"]):
            raise RuntimeError(f"城市 {city['city_id']} 引用了未知副本")
        if _integer(city, "rest_cost", 0) < 0:
            raise RuntimeError(f"城市 {city['city_id']} 的 rest_cost 不能为负数")
        _validate_requirements(city.get("unlock_requires", []), dungeons)
    if cities[world["starting_city_id"]]["country_id"] != world["starting_country_id"]:
        raise RuntimeError("起始城市不属于起始国家")

    for event in events.values():
        _required_string(event, "title")
        _required_string(event, "text")
        if event.get("type") not in ALLOWED_EVENTS:
            raise RuntimeError(f"事件 {event['event_id']} 使用未知类型")
        if event["type"] in {"spirit_battle", "boss"}:
            _validate_enemy_pool(event.get("enemy_pool", []), enemies, event["event_id"])
        if event["type"] == "choice":
            options = event.get("options")
            if not isinstance(options, list) or not options:
                raise RuntimeError(f"选择事件 {event['event_id']} 没有选项")
            option_ids = set()
            for option in options:
                option_id = _required_string(option, "option_id")
                _required_string(option, "text")
                if option_id in option_ids:
                    raise RuntimeError(f"选择事件 {event['event_id']} 包含重复选项")
                option_ids.add(option_id)
                effect = option.get("effect")
                if not isinstance(effect, dict) or effect.get("type") not in ALLOWED_EFFECTS:
                    raise RuntimeError(f"选择事件 {event['event_id']} 包含未知效果")
                _validate_effect(effect, enemies, event["event_id"])
        if event["type"] == "rest":
            _validate_percent(event, "hp_percent")
            _validate_percent(event, "mp_percent")
        if event["type"] == "hazard" and _integer(event, "damage", 0) < 0:
            raise RuntimeError(f"事件 {event['event_id']} 伤害不能为负数")
        if event["type"] == "treasure" and _integer(event, "currency_amount", 0) < 0:
            raise RuntimeError(f"事件 {event['event_id']} 货币奖励不能为负数")

    for enemy in enemies.values():
        for key in ("base_hp", "base_mp", "base_attack", "base_defense"):
            if _integer(enemy, key, 0) < 0:
                raise RuntimeError(f"敌人 {enemy['enemy_id']} 的 {key} 不能为负数")
        for key in ("hp_per_level", "mp_per_level", "attack_per_level", "defense_per_level", "speed"):
            if _integer(enemy, key, 0) < 0:
                raise RuntimeError(f"敌人 {enemy['enemy_id']} 的 {key} 不能为负数")
        if _integer(enemy, "exp_reward", 0) < 0:
            raise RuntimeError(f"敌人 {enemy['enemy_id']} 的经验奖励不能为负数")
        skills = enemy.get("skills")
        if not isinstance(skills, list) or any(skill_id not in pet_catalog.skills for skill_id in skills):
            raise RuntimeError(f"敌人 {enemy['enemy_id']} 引用了未知技能")

    for dungeon in dungeons.values():
        if dungeon.get("city_id") not in cities:
            raise RuntimeError(f"副本 {dungeon['dungeon_id']} 引用了未知城市")
        if cities[dungeon["city_id"]]["dungeon_ids"].count(dungeon["dungeon_id"]) != 1:
            raise RuntimeError(f"副本 {dungeon['dungeon_id']} 必须且只能归属一个城市")
        _validate_requirements(dungeon.get("unlock_requires", []), dungeons)
        difficulty_ids = set()
        difficulties = dungeon.get("difficulties")
        if not isinstance(difficulties, list) or not difficulties:
            raise RuntimeError(f"副本 {dungeon['dungeon_id']} 没有难度配置")
        for difficulty in difficulties:
            difficulty_id = _required_string(difficulty, "difficulty_id")
            if difficulty_id in difficulty_ids:
                raise RuntimeError(f"副本 {dungeon['dungeon_id']} 难度 ID 重复")
            difficulty_ids.add(difficulty_id)
            _validate_requirements(difficulty.get("unlock_requires", []), dungeons)
            for key in ("recommended_level", "enemy_level"):
                if _integer(difficulty, key, 1) <= 0:
                    raise RuntimeError(f"副本 {dungeon['dungeon_id']} 难度 {difficulty_id} 的 {key} 必须大于零")
            multiplier = difficulty.get("xp_multiplier")
            if not isinstance(multiplier, (int, float)) or isinstance(multiplier, bool) or multiplier <= 0:
                raise RuntimeError(f"副本 {dungeon['dungeon_id']} 难度 {difficulty_id} 的经验倍率无效")
            stages = difficulty.get("stages")
            if not isinstance(stages, list) or not stages or len(stages) > 10:
                raise RuntimeError(f"副本 {dungeon['dungeon_id']} 难度 {difficulty_id} 路线长度必须为 1 到 10")
            for stage in stages:
                _validate_event_pool(stage, events, dungeon["dungeon_id"])
            if difficulty.get("boss_enemy_id") not in enemies:
                raise RuntimeError(f"副本 {dungeon['dungeon_id']} 难度 {difficulty_id} 缺少有效首领")
    _validate_unlock_cycles(dungeons)
    return WorldCatalog(world, countries, cities, dungeons, events, enemies)


def _read(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"无法加载世界资源 {path.name}: {error}") from error


def _mapped(
    data: Any, key: str, filename: str,
    label_fields: tuple[str, str] = ("name", "description"),
) -> dict[str, dict[str, Any]]:
    if not isinstance(data, list):
        raise RuntimeError(f"{filename} 根节点必须是列表")
    result = {}
    for entry in data:
        if not isinstance(entry, dict):
            raise RuntimeError(f"{filename} 每项都必须是对象")
        value = _required_string(entry, key)
        if value in result:
            raise RuntimeError(f"{filename} 中 ID {value} 重复")
        for field in label_fields:
            _required_string(entry, field)
        result[value] = entry
    return result


def _required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"字段 {key} 必须是非空字符串")
    return value.strip()


def _integer(data: dict[str, Any], key: str, default: int) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f"字段 {key} 必须是整数")
    return value


def _validate_percent(data: dict[str, Any], key: str) -> None:
    value = data.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 1:
        raise RuntimeError(f"字段 {key} 必须介于 0 和 1")


def _validate_requirements(requirements: Any, dungeons: dict[str, dict[str, Any]]) -> None:
    if not isinstance(requirements, list):
        raise RuntimeError("unlock_requires 必须是列表")
    for requirement in requirements:
        if not isinstance(requirement, dict) or requirement.get("dungeon_id") not in dungeons:
            raise RuntimeError("解锁条件引用了未知副本")
        difficulty_id = _required_string(requirement, "difficulty_id")
        if not any(item.get("difficulty_id") == difficulty_id for item in dungeons[requirement["dungeon_id"]].get("difficulties", [])):
            raise RuntimeError(
                f"解锁条件引用了未知难度：{requirement['dungeon_id']}/{difficulty_id}"
            )


def _validate_event_pool(pool: Any, events: dict[str, dict[str, Any]], dungeon_id: str) -> None:
    if not isinstance(pool, list) or not pool:
        raise RuntimeError(f"副本 {dungeon_id} 的事件池不能为空")
    for entry in pool:
        if not isinstance(entry, dict) or entry.get("event_id") not in events:
            raise RuntimeError(f"副本 {dungeon_id} 事件池引用未知事件")
        weight = entry.get("weight")
        if isinstance(weight, bool) or not isinstance(weight, int) or weight <= 0:
            raise RuntimeError(f"副本 {dungeon_id} 事件权重必须是正整数")


def _validate_enemy_pool(pool: Any, enemies: dict[str, dict[str, Any]], event_id: str) -> None:
    if not isinstance(pool, list) or not pool:
        raise RuntimeError(f"事件 {event_id} 的敌人池不能为空")
    for entry in pool:
        if not isinstance(entry, dict) or entry.get("enemy_id") not in enemies:
            raise RuntimeError(f"事件 {event_id} 引用了未知敌人")
        weight = entry.get("weight")
        if isinstance(weight, bool) or not isinstance(weight, int) or weight <= 0:
            raise RuntimeError(f"事件 {event_id} 敌人权重必须是正整数")


def _validate_effect(effect: dict[str, Any], enemies: dict[str, dict[str, Any]], event_id: str) -> None:
    if effect["type"] == "rest":
        _validate_percent(effect, "hp_percent")
        _validate_percent(effect, "mp_percent")
    elif effect["type"] == "currency" and _integer(effect, "amount", 0) < 0:
        raise RuntimeError(f"事件 {event_id} 的货币效果不能为负数")
    elif effect["type"] == "damage" and _integer(effect, "amount", 0) < 0:
        raise RuntimeError(f"事件 {event_id} 的伤害效果不能为负数")
    elif effect["type"] == "battle" and effect.get("enemy_id") not in enemies:
        raise RuntimeError(f"事件 {event_id} 的战斗效果引用了未知敌人")


def _validate_unlock_cycles(dungeons: dict[str, dict[str, Any]]) -> None:
    graph = {
        dungeon_id: {requirement["dungeon_id"] for requirement in dungeon.get("unlock_requires", [])}
        for dungeon_id, dungeon in dungeons.items()
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(dungeon_id: str) -> None:
        if dungeon_id in visiting:
            raise RuntimeError(f"副本解锁条件存在循环：{dungeon_id}")
        if dungeon_id in visited:
            return
        visiting.add(dungeon_id)
        for prerequisite in graph[dungeon_id]:
            visit(prerequisite)
        visiting.remove(dungeon_id)
        visited.add(dungeon_id)

    for dungeon_id in graph:
        visit(dungeon_id)
