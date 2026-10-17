from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ..domain.dungeon import make_route, requirements_met
from ..domain.pet import PetCatalog
from ..domain.world import WorldCatalog
from .ports.dungeon_repository import DungeonRepository


class DungeonService:
    def __init__(
        self, repository: DungeonRepository, world: WorldCatalog,
        pets: PetCatalog, currency_name: str = "银币",
    ):
        self.repository = repository
        self.world = world
        self.pets = pets
        self.currency_name = currency_name

    async def world_map(self, platform_id: str, player_id: str) -> str:
        cleared, current_city = await self.repository.get_progress(
            platform_id, player_id, self.world.world["starting_city_id"]
        )
        lines = [f"# {self.world.world['name']}", f"> {self.world.world['description']}", "", "## 世界地图"]
        for country in self.world.countries.values():
            country_open = requirements_met(country.get("unlock_requires", []), cleared)
            lines.append(f"\n### {'🗺' if country_open else '🔒'} {country['name']}")
            for city in self.world.cities.values():
                if city["country_id"] != country["country_id"]:
                    continue
                city_open = country_open and requirements_met(city.get("unlock_requires", []), cleared)
                marker = "📍" if city["city_id"] == current_city else "🏙" if city_open else "🔒"
                lines.append(f"- {marker} **{city['name']}**")
                for dungeon_id in city["dungeon_ids"]:
                    dungeon = self.world.dungeons[dungeon_id]
                    dungeon_open = city_open and requirements_met(dungeon.get("unlock_requires", []), cleared)
                    difficulties = []
                    for difficulty in dungeon["difficulties"]:
                        open_difficulty = dungeon_open and requirements_met(
                            difficulty.get("unlock_requires", []), cleared
                        )
                        is_cleared = (dungeon_id, difficulty["difficulty_id"]) in cleared
                        label = difficulty["name"] + ("✓" if is_cleared else "")
                        difficulties.append(label if open_difficulty else f"🔒{label}")
                    lines.append(f"  - {'⚔' if dungeon_open else '🔒'} **{dungeon['name']}**：{' / '.join(difficulties)}")
        lines.append("\n浏览：`/国家 云岚王国` · `/城市 青溪城` · `/副本 回声林地`")
        return "\n".join(lines)

    async def country_info(self, platform_id: str, player_id: str, ref: str | None) -> str:
        country = self._find(self.world.countries, ref)
        if country is None:
            return "请提供国家名称，例如：/国家 云岚王国。也可以输入拼音首字母简称。"
        cleared, _ = await self.repository.get_progress(platform_id, player_id, self.world.world["starting_city_id"])
        opened = requirements_met(country.get("unlock_requires", []), cleared)
        lines = [f"# {'🗺 已开放' if opened else '🔒 尚未开放'} · {country['name']}", f"> {country['description']}"]
        for city in self.world.cities.values():
            if city['country_id'] != country['country_id']:
                continue
            open_city = opened and requirements_met(city.get("unlock_requires", []), cleared)
            lines.append(f"\n## {'🏙' if open_city else '🔒'} {city['name']}")
            lines.extend(f"- {self.world.dungeons[dungeon_id]['name']}" for dungeon_id in city['dungeon_ids'])
        return "\n".join(lines)

    async def city_info(self, platform_id: str, player_id: str, ref: str | None) -> str:
        city = self._find(self.world.cities, ref)
        if city is None:
            return "请提供城市名称，例如：/城市 青溪城。"
        cleared, current_city = await self.repository.get_progress(platform_id, player_id, self.world.world["starting_city_id"])
        country = self.world.countries[city['country_id']]
        opened = requirements_met(country.get("unlock_requires", []), cleared) and requirements_met(city.get("unlock_requires", []), cleared)
        lines = [f"# {'🏙 已开放' if opened else '🔒 尚未开放'} · {country['name']} / {city['name']}", f"> {city['description']}", f"休息费用：**{city['rest_cost']} {self.currency_name}**" + (" · 当前所在城市" if current_city == city['city_id'] else "")]
        for dungeon_id in city['dungeon_ids']:
            dungeon = self.world.dungeons[dungeon_id]
            dungeon_open = opened and requirements_met(dungeon.get("unlock_requires", []), cleared)
            diffs = []
            for difficulty in dungeon['difficulties']:
                difficulty_open = dungeon_open and requirements_met(difficulty.get("unlock_requires", []), cleared)
                diffs.append(f"{difficulty['name']}（推荐等级 {difficulty['recommended_level']}）" if difficulty_open else f"🔒{difficulty['name']}")
            lines.append(f"\n## {'⚔' if dungeon_open else '🔒'} {dungeon['name']}\n{' / '.join(diffs)}")
        return "\n".join(lines)

    async def dungeon_info(self, platform_id: str, player_id: str, ref: str | None) -> str:
        dungeon = self._find(self.world.dungeons, ref)
        if dungeon is None:
            return "请提供副本名称，例如：/副本 回声林地。"
        cleared, _ = await self.repository.get_progress(platform_id, player_id, self.world.world["starting_city_id"])
        city = self.world.cities[dungeon['city_id']]
        country = self.world.countries[city['country_id']]
        opened = all((requirements_met(item.get("unlock_requires", []), cleared) for item in (country, city, dungeon)))
        lines = [f"# {'⚔ 已开放' if opened else '🔒 尚未开放'} · {dungeon['name']}", f"{country['name']} / {city['name']}", f"> {dungeon['description']}", "## 难度"]
        for difficulty in dungeon['difficulties']:
            requirements = difficulty.get("unlock_requires", [])
            available = opened and requirements_met(requirements, cleared)
            state = "开放" if available else "锁定"
            lines.append(f"- **{difficulty['name']}**（{state}，推荐等级 {difficulty['recommended_level']}）")
        lines.append("进入：`/进入副本 回声林地 简单`")
        return "\n".join(lines)

    async def start(self, platform_id: str, player_id: str, dungeon_ref: str | None, difficulty_ref: str | None) -> str:
        dungeon = self._find(self.world.dungeons, dungeon_ref)
        if dungeon is None:
            return "用法：/进入副本 副本名称 难度名称，例如：/进入副本 回声林地 简单"
        difficulty = next((entry for entry in dungeon['difficulties'] if difficulty_ref in {entry['difficulty_id'], entry['name']}), None)
        if difficulty is None:
            return f"难度名称无效，可选：{'、'.join(entry['name'] for entry in dungeon['difficulties'])}。"
        cleared, _ = await self.repository.get_progress(platform_id, player_id, self.world.world['starting_city_id'])
        city = self.world.cities[dungeon['city_id']]
        country = self.world.countries[city['country_id']]
        requirements = country.get('unlock_requires', []) + city.get('unlock_requires', []) + dungeon.get('unlock_requires', []) + difficulty.get('unlock_requires', [])
        if not requirements_met(requirements, cleared):
            return "该副本或难度尚未解锁，请先查看 /世界地图 的解锁进度。"
        now = _now()
        status, record = await self.repository.start_run(
            platform_id, player_id, uuid.uuid4().hex, dungeon['dungeon_id'],
            {**difficulty, "difficulty_id": difficulty['difficulty_id']},
            make_route(difficulty, self.world), dungeon['city_id'], now,
            self.pets, self.world,
        )
        if status == "started":
            return f"✅ 已进入 **{dungeon['name']} · {difficulty['name']}**（推荐等级 {difficulty['recommended_level']}）。\n使用 `/探索副本` 前进，`/副本状态` 查看进度。"
        return {
            "run_active": "你已有进行中的副本，使用 /副本状态 继续或 /退出副本 撤退。",
            "battle_active": "你正在参与精灵对战，结束对战后才能进入副本。",
            "locked": "该副本尚未解锁。",
            "no_pet": "请先领养并设置出战宠物。",
            "pet_fainted": "当前宠物生命值为零，请先使用 /宠物休息。",
            "species_missing": "当前宠物数据异常，暂时无法进入副本。",
        }.get(status, "进入副本失败，请稍后重试。")

    async def explore(self, platform_id: str, player_id: str) -> str:
        status, record = await self.repository.advance(platform_id, player_id, _now(), self.world, self.pets)
        if record is None:
            return {"no_run": "你当前没有进行中的副本。", "battling": "正在与野生精灵战斗，请先行动。", "choice_pending": "请先使用 /副本选择 序号。", "route_complete": "副本路线已完成。"}.get(status, "暂时无法继续探索。")
        data = record['data']
        if status == "choice_pending":
            event = data['current_event']
            options = "\n".join(f"- **{index}**：{item['text']}" for index, item in enumerate(event['options'], 1))
            return f"### {event['title']}\n> {event['text']}\n\n{options}\n\n使用 `/副本选择 序号`。"
        if status == "battling":
            return self._combat_intro(data)
        if status == "defeated":
            return self._event_message(data) + "\n宠物已无法继续，本次探索结束。已获得的经验保留。"
        if status == "advanced":
            message = self._event_message(data)
            if data['status'] == 'completed':
                return message + "\n副本首领已击败，探索完成！"
            return message + "\n使用 /探索副本 前往下一处。"
        return status

    async def choose(self, platform_id: str, player_id: str, option_ref: str | None) -> str:
        if not option_ref:
            return "用法：/副本选择 序号"
        active = await self.repository.get_active_run(platform_id, player_id)
        event = active['data'].get('current_event') if active else None
        selected_index = None
        selected_id = option_ref
        if event and event.get('options'):
            value = option_ref.strip()
            if value.isdecimal():
                selected_index = int(value)
                if 1 <= selected_index <= len(event['options']):
                    selected_id = event['options'][selected_index - 1]['option_id']
            else:
                option = next((item for item in event['options'] if item['text'] == value), None)
                if option:
                    selected_id = option['option_id']
                    selected_index = event['options'].index(option) + 1
        status, record = await self.repository.choose(platform_id, player_id, selected_id, _now(), self.world, self.pets)
        if record is None:
            return {"no_run": "你当前没有进行中的副本。", "no_choice": "当前没有等待处理的事件选择。", "invalid_option": "选项序号无效，请使用 /副本状态 查看选项。"}.get(status, "选择失败。")
        if status == "battling":
            return f"你选择了第 {selected_index or 1} 项。\n" + self._combat_intro(record['data'])
        if status == "defeated":
            return "这个选择造成的伤害令宠物无法继续，本次探索结束。"
        return f"已选择第 {selected_index or 1} 项。\n{self._event_message(record['data'])}\n使用 `/探索副本` 前往下一处。"

    async def status(self, platform_id: str, player_id: str) -> str:
        record = await self.repository.get_active_run(platform_id, player_id)
        if not record:
            return "你当前没有进行中的副本。使用 /世界地图 浏览可进入的副本。"
        data = record['data']
        lines = [f"# {data['dungeon_name']} · {data['difficulty_name']}", f"进度：**{min(data['stage_index'] + 1, len(data['route']))}/{len(data['route'])}**", f"宠物：**{data['pet_snapshot']['pet_name']} · 等级 {data['pet_snapshot']['level']}** · 生命 {data['pet_snapshot']['hp']}/{data['pet_snapshot']['max_hp']} · 魔力 {data['pet_snapshot']['mp']}/{data['pet_snapshot']['max_mp']}"]
        if data.get('status') == 'battling' and data.get('combat'):
            combat = data['combat']
            enemy = combat['players']['__enemy__']
            lines.append(f"遭遇：**{data['current_event']['title']}** · {enemy['pet_name']} 等级 {enemy['level']}，生命 {enemy['hp']}/{enemy['max_hp']}，魔力 {enemy['mp']}/{enemy['max_mp']}")
            lines.append("行动方：你" if combat['current_turn_player_id'] == player_id else "行动方：野生精灵（会自动行动）")
            pet_combat = combat['players'].get(player_id, {})
            lines.extend(self._skill_menu(pet_combat.get('skills', {})))
        elif data.get('pending_choice'):
            event = data['current_event']
            lines.append(f"等待选择：{event['title']}")
            lines.extend(f"- **{index}**：{item['text']}" for index, item in enumerate(event['options'], 1))
        else:
            lines.append("使用 `/探索副本` 触发下一处事件。")
        lines.append("`/退出副本` 可随时撤退。")
        return "\n".join(lines)

    async def retreat(self, platform_id: str, player_id: str) -> str:
        status, _ = await self.repository.retreat(platform_id, player_id, _now())
        return "已撤退出副本，已获得经验保留；宠物当前生命和魔力保留。" if status == "retreated" else "你当前没有进行中的副本。"

    async def rest(self, platform_id: str, player_id: str) -> str:
        status, value = await self.repository.rest_pet(platform_id, player_id, _now(), self.world.world['starting_city_id'], self.world, self.pets)
        if status == "rested":
            return f"在「{value['city']}」休息完成：生命 {value['hp']}、魔力 {value['mp']}，花费 {value['cost']} {self.currency_name}。"
        if status == "insufficient_currency":
            return f"休息需要 {value['cost']} {self.currency_name}，当前余额 {value['balance']}。"
        return {"run_active": "副本进行中无法休息，请先完成或退出副本。", "no_pet": "你还没有出战宠物。", "species_missing": "宠物数据异常，无法恢复。", "already_restored": "当前宠物生命和魔力已满。"}.get(status, "休息失败。")

    async def is_in_battle(self, platform_id: str, player_id: str) -> bool:
        record = await self.repository.get_active_run(platform_id, player_id)
        return bool(record and record['data'].get('status') == 'battling')

    async def has_active_run(self, platform_id: str, player_id: str) -> bool:
        return await self.repository.get_active_run(platform_id, player_id) is not None

    async def battle_actions(self, platform_id: str, player_id: str) -> list[dict[str, Any]]:
        active = await self.repository.get_active_run(platform_id, player_id)
        if not active:
            return []
        state = active['data']
        combat = state.get('combat') or {}
        if state.get('status') != 'battling' or combat.get('current_turn_player_id') != player_id:
            return []
        player = combat.get('players', {}).get(player_id, {})
        token = state.get('button_token')
        if not token:
            return []
        actions = [{"action": "skill", "skill_id": "basic_attack", "name": "普通攻击", "button_token": token}]
        actions.extend(
            {"action": "skill", "skill_id": skill_id, "name": skill.get('name', skill_id), "button_token": token}
            for skill_id, skill in player.get('skills', {}).items()
        )
        actions.append({"action": "defend", "skill_id": None, "name": "防御", "button_token": token})
        return actions

    async def act(
        self, platform_id: str, player_id: str, action: str, skill_id: str | None,
        request_key: str | None = None, expected_button_token: str | None = None,
    ) -> str:
        if action == "skill":
            active = await self.repository.get_active_run(platform_id, player_id)
            combat_player = ((active['data'].get('combat') or {}).get('players', {}).get(player_id, {}) if active else {})
            if skill_id is None or not str(skill_id).strip():
                return "## 可用技能\n" + "\n".join(self._skill_menu(combat_player.get('skills', {})))
            skill_name = str(skill_id).strip()
            if skill_name in {"普通攻击", "普攻"}:
                skill_id = "basic_attack"
            else:
                skills = combat_player.get('skills', {})
                if skill_name.isdecimal():
                    index = int(skill_name)
                    skill_ids = list(skills)
                    if 1 <= index <= len(skill_ids):
                        skill_id = skill_ids[index - 1]
                    else:
                        return "技能序号无效，请按上方技能列表选择。"
                else:
                    skill_id = next(
                        (key for key, value in skills.items() if value.get('name') == skill_name),
                        next(
                            (entry.skill_id for entry in self.pets.skills.values() if entry.name == skill_name),
                            skill_name,
                        ),
                    )
        status, value = await self.repository.act(
            platform_id, player_id, action, skill_id, request_key, _now(),
            self.world, self.pets, expected_button_token,
        )
        if status == "not_battling":
            return "你当前没有正在进行的副本精灵战斗。"
        if status == "not_your_turn":
            return "现在还不是你的行动回合。"
        if status == "invalid_action":
            return value.get('message', '行动无效。')
        if status == "duplicate":
            return "这条行动已处理。"
        if status == "stale_button":
            return "这个按钮已过期，请使用最新的战斗消息操作。"
        if value is None:
            return "副本战斗状态已结束或不存在。"
        run = value['run']
        lines = []
        for result in value['results']:
            name = result.get('skill_name') or "行动"
            if result.get('damage'):
                name += f"，造成 {result['damage']} 点伤害"
            if result.get('healing'):
                name += f"，恢复 {result['healing']} 点生命"
            actor = "野生精灵" if result['player_id'] == '__enemy__' else run['pet_snapshot']['pet_name']
            lines.append(f"**{actor}** 使用 **{name}**。")
        pet = run['pet_snapshot']
        enemy = (run.get('combat') or {}).get('players', {}).get('__enemy__')
        if enemy:
            lines.append(f"**{pet['pet_name']}** 生命 {pet['hp']}/{pet['max_hp']} · 魔力 {pet['mp']}/{pet['max_mp']}；**{enemy['pet_name']}** 生命 {enemy['hp']}/{enemy['max_hp']} · 魔力 {enemy['mp']}/{enemy['max_mp']}。")
        elif run['status'] == 'defeated':
            lines.append(f"**{pet['pet_name']}** 生命 {pet['hp']}/{pet['max_hp']} · 魔力 {pet['mp']}/{pet['max_mp']}。")
        else:
            reward = run.get('last_xp_reward', 0)
            lines.append(f"**{pet['pet_name']}** 获得 **{reward} 点经验**，当前等级 {pet['level']}，生命 {pet['hp']}/{pet['max_hp']} · 魔力 {pet['mp']}/{pet['max_mp']}。")
        if run['status'] == 'defeated':
            lines.append("宠物战败，本次探索结束。")
        elif run['status'] == 'completed':
            lines.append("首领战胜利，副本已通关！")
        elif run['status'] == 'exploring':
            lines.append("使用 `/探索副本` 前往下一处。")
        else:
            lines.append("野生精灵已行动。")
        return "\n".join(lines)

    def _find(self, entries: dict[str, dict[str, Any]], ref: str | None) -> dict[str, Any] | None:
        if not ref:
            return None
        value = ref.strip()
        folded = value.casefold()
        return entries.get(value) or next(
            (
                entry for entry in entries.values()
                if entry['name'] == value
                or entry.get('country_id', '').casefold() == folded
                or any(alias.casefold() == folded for alias in entry.get('aliases', []))
            ),
            None,
        )

    def _event_message(self, state: dict[str, Any]) -> str:
        event = state.get('last_event') or state.get('current_event') or {}
        result = state.get('last_event_result') or {}
        lines = [f"### {event.get('title', '探索事件')}", f"> {event.get('text', '')}"]
        if result.get('damage'):
            lines.append(f"宠物受到 {result['damage']} 点伤害。")
        if result.get('hp_restored') or result.get('mp_restored'):
            lines.append(f"恢复生命 {result.get('hp_restored', 0)}、魔力 {result.get('mp_restored', 0)}。")
        if result.get('currency'):
            lines.append(f"获得 {result['currency']} {self.currency_name}。")
        if result.get('xp'):
            lines.append(f"宠物获得 {result['xp']} 点经验。")
        return "\n".join(line for line in lines if line)

    def _combat_intro(self, state: dict[str, Any]) -> str:
        combat = state['combat']
        enemy = combat['players']['__enemy__']
        player_id = next(player_id for player_id in combat['players'] if player_id != '__enemy__')
        pet = combat['players'][player_id]
        lines = [
            f"### ⚔️ {state['current_event']['title']}",
            f"> {state['current_event'].get('text', '')}",
            f"**遭遇：{enemy['pet_name']}** · 等级 {enemy['level']}",
            "",
            f"**{pet['pet_name']}**　生命 {pet['hp']}/{pet['max_hp']}　魔力 {pet['mp']}/{pet['max_mp']}",
            f"**{enemy['pet_name']}**　生命 {enemy['hp']}/{enemy['max_hp']}　魔力 {enemy['mp']}/{enemy['max_mp']}",
        ]
        if combat['current_turn_player_id'] == '__enemy__':
            lines.extend(["", "野生精灵先手并已自动行动。"])
        else:
            lines.extend(["", "轮到你行动。"])
        lines.extend(["", "## 可用技能", *self._skill_menu(pet.get('skills', {}))])
        return "\n".join(lines)

    @staticmethod
    def _skill_menu(skills: dict[str, dict[str, Any]]) -> list[str]:
        lines = [
            f"{index}. **{skill['name']}**（消耗魔力 {skill['mp_cost']}）"
            for index, skill in enumerate(skills.values(), 1)
        ]
        if not lines:
            lines.append("当前没有可用的已装备技能。")
        lines.extend([
            "普通攻击：`/精灵技能 普通攻击`（不消耗魔力）",
            "也可以点击下方按钮直接行动。",
            "手动操作：发送 `/精灵技能 序号` 释放技能，或使用 `/精灵防御`。",
        ])
        return lines


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")
