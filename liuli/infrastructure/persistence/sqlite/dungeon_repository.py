import json
import random
import sqlite3
import uuid
from copy import deepcopy
from typing import Any

from ....application.ports.dungeon_repository import DungeonRepository
from ....domain.dungeon import choose_enemy_action, experience_reward, make_encounter
from ....domain.pet import Pet, PetCatalog, PetSkillState
from ....domain.spirit_battle import resolve_action
from ....domain.world import WorldCatalog
from .database import SQLiteDatabase


class SQLiteDungeonRepository(DungeonRepository):
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    async def start_run(
        self, platform_id: str, player_id: str, run_id: str, dungeon_id: str,
        difficulty: dict[str, Any], route: list[dict[str, Any]], city_id: str,
        now: str, pet_catalog: PetCatalog, world_catalog: WorldCatalog,
    ) -> tuple[str, dict[str, Any] | None]:
        async with self.database.lock:
            connection = self.database.connection
            await connection.execute("BEGIN IMMEDIATE")
            try:
                async with connection.execute(
                    "SELECT 1 FROM dungeon_runs WHERE platform_id=? AND player_id=? AND state='active'",
                    (platform_id, player_id),
                ) as cursor:
                    if await cursor.fetchone():
                        await connection.rollback()
                        return "run_active", None
                async with connection.execute(
                    """SELECT 1 FROM spirit_battles WHERE platform_id=?
                       AND state IN ('pending', 'active') AND (challenger_id=? OR opponent_id=?) LIMIT 1""",
                    (platform_id, player_id, player_id),
                ) as cursor:
                    if await cursor.fetchone():
                        await connection.rollback()
                        return "battle_active", None

                dungeon = world_catalog.dungeons[dungeon_id]
                city = world_catalog.cities[city_id]
                country = world_catalog.countries[city["country_id"]]
                requirements = (
                    country.get("unlock_requires", [])
                    + city.get("unlock_requires", [])
                    + dungeon.get("unlock_requires", [])
                    + difficulty.get("unlock_requires", [])
                )
                if not await self._requirements_met_unlocked(platform_id, player_id, requirements):
                    await connection.rollback()
                    return "locked", None

                pet_row = await self._get_active_pet_unlocked(platform_id, player_id)
                if pet_row is None:
                    await connection.rollback()
                    return "no_pet", None
                species = pet_catalog.species.get(pet_row["species_id"])
                if species is None:
                    await connection.rollback()
                    return "species_missing", None
                pet = await self._hydrate_pet_unlocked(pet_row)
                if pet.current_hp <= 0:
                    await connection.rollback()
                    return "pet_fainted", None
                pet_snapshot = self._player_snapshot(pet, species, pet_catalog)
                state = {
                    "status": "exploring",
                    "dungeon_id": dungeon_id,
                    "dungeon_name": dungeon["name"],
                    "difficulty_id": difficulty["difficulty_id"],
                    "difficulty_name": difficulty["name"],
                    "recommended_level": difficulty["recommended_level"],
                    "enemy_level": difficulty["enemy_level"],
                    "xp_multiplier": difficulty["xp_multiplier"],
                    "city_id": city_id,
                    "pet_id": pet.pet_id,
                    "pet_snapshot": pet_snapshot,
                    "route": route,
                    "stage_index": 0,
                    "current_event": None,
                    "combat": None,
                    "selected_option": None,
                    "started_at": now,
                }
                await connection.execute(
                    """INSERT INTO dungeon_runs
                       (run_id, platform_id, player_id, dungeon_id, difficulty_id,
                        state, state_json, started_at, updated_at)
                       VALUES(?, ?, ?, ?, ?, 'active', ?, ?, ?)""",
                    (run_id, platform_id, player_id, dungeon_id, difficulty["difficulty_id"], _dump(state), now, now),
                )
                await connection.execute(
                    """INSERT INTO dungeon_player_state(platform_id, player_id, current_city_id, updated_at)
                       VALUES(?, ?, ?, ?) ON CONFLICT(platform_id, player_id) DO UPDATE SET
                       current_city_id=excluded.current_city_id, updated_at=excluded.updated_at""",
                    (platform_id, player_id, city_id, now),
                )
                await connection.commit()
                return "started", _record(run_id, "active", state)
            except sqlite3.IntegrityError:
                await connection.rollback()
                return "run_active", None
            except Exception:
                await connection.rollback()
                raise

    async def get_active_run(self, platform_id: str, player_id: str) -> dict[str, Any] | None:
        async with self.database.lock:
            async with self.database.connection.execute(
                """SELECT run_id, state, state_json FROM dungeon_runs
                   WHERE platform_id=? AND player_id=? AND state='active' LIMIT 1""",
                (platform_id, player_id),
            ) as cursor:
                row = await cursor.fetchone()
            if row is None:
                return None
            state = _load(row["state_json"])
            if state.get("status") == "battling" and state.get("combat") and not state.get("button_token"):
                state["button_token"] = uuid.uuid4().hex
                await self.database.connection.execute(
                    "UPDATE dungeon_runs SET state_json=? WHERE run_id=?",
                    (_dump(state), row["run_id"]),
                )
                await self.database.connection.commit()
            return _record(row["run_id"], row["state"], state)

    async def get_progress(
        self, platform_id: str, player_id: str, starting_city_id: str
    ) -> tuple[set[tuple[str, str]], str]:
        async with self.database.lock:
            async with self.database.connection.execute(
                """SELECT dungeon_id, difficulty_id FROM dungeon_progress
                   WHERE platform_id=? AND player_id=? AND clear_count>0""",
                (platform_id, player_id),
            ) as cursor:
                cleared = {(row["dungeon_id"], row["difficulty_id"]) for row in await cursor.fetchall()}
            async with self.database.connection.execute(
                """SELECT current_city_id FROM dungeon_player_state
                   WHERE platform_id=? AND player_id=?""",
                (platform_id, player_id),
            ) as cursor:
                row = await cursor.fetchone()
            return cleared, row["current_city_id"] if row else starting_city_id

    async def advance(
        self, platform_id: str, player_id: str, now: str,
        world_catalog: WorldCatalog, pet_catalog: PetCatalog,
    ) -> tuple[str, dict[str, Any] | None]:
        async with self.database.lock:
            connection = self.database.connection
            await connection.execute("BEGIN IMMEDIATE")
            try:
                row = await self._active_run_unlocked(platform_id, player_id)
                if row is None:
                    await connection.rollback()
                    return "no_run", None
                state = _load(row["state_json"])
                if state["status"] == "battling":
                    await connection.rollback()
                    return "battling", _record(row["run_id"], row["state"], state)
                if state.get("pending_choice"):
                    await connection.rollback()
                    return "choice_pending", _record(row["run_id"], row["state"], state)
                if state["stage_index"] >= len(state["route"]):
                    await connection.rollback()
                    return "route_complete", _record(row["run_id"], row["state"], state)

                stage_index = state["stage_index"]
                route_node = state["route"][stage_index]
                is_boss = route_node["event_id"] == "__boss__"
                if is_boss:
                    event = {
                        "event_id": "__boss__", "type": "boss", "title": "最终首领",
                        "text": f"{state['dungeon_name']} 的首领现身了！",
                    }
                    enemy_id = route_node["enemy_id"]
                else:
                    event = deepcopy(world_catalog.events[route_node["event_id"]])
                    enemy_id = None

                state["current_event"] = event
                state["last_event"] = deepcopy(event)
                state["selected_option"] = None
                if event["type"] == "choice":
                    state["pending_choice"] = True
                    await self._save_run_unlocked(row["run_id"], "active", state, now)
                    await connection.commit()
                    return "choice_pending", _record(row["run_id"], "active", state)
                if event["type"] in {"spirit_battle", "boss"}:
                    if enemy_id is None:
                        enemy_entry = _weighted_choice(event["enemy_pool"])
                        enemy_id = enemy_entry["enemy_id"]
                    status, battle = await self._begin_encounter_unlocked(
                        row, state, event, enemy_id, is_boss, now,
                        world_catalog, pet_catalog, random.SystemRandom(),
                    )
                    if status == "defeated":
                        await self._save_run_unlocked(row["run_id"], "defeated", state, now)
                        await connection.commit()
                        return "defeated", _record(row["run_id"], "defeated", state)
                    if status != "battling":
                        await connection.rollback()
                        return status, None
                    await connection.commit()
                    return "battling", _record(row["run_id"], "active", state)

                outcome = await self._apply_immediate_event_unlocked(
                    row, state, event, stage_index, now, world_catalog, pet_catalog
                )
                if outcome == "defeated":
                    await self._save_run_unlocked(row["run_id"], "defeated", state, now)
                    await self._log_event_unlocked(row["run_id"], stage_index, event["event_id"], state.get("last_event_result", {}), now)
                    await connection.commit()
                    return "defeated", _record(row["run_id"], "defeated", state)
                state["stage_index"] += 1
                state["current_event"] = None
                await self._log_event_unlocked(row["run_id"], stage_index, event["event_id"], state.get("last_event_result", {}), now)
                await self._save_run_unlocked(row["run_id"], "active", state, now)
                await connection.commit()
                return "advanced", _record(row["run_id"], "active", state)
            except Exception:
                await connection.rollback()
                raise

    async def choose(
        self, platform_id: str, player_id: str, option_id: str, now: str,
        world_catalog: WorldCatalog, pet_catalog: PetCatalog,
    ) -> tuple[str, dict[str, Any] | None]:
        async with self.database.lock:
            connection = self.database.connection
            await connection.execute("BEGIN IMMEDIATE")
            try:
                row = await self._active_run_unlocked(platform_id, player_id)
                if row is None:
                    await connection.rollback()
                    return "no_run", None
                state = _load(row["state_json"])
                event = state.get("current_event")
                if not state.get("pending_choice") or not event:
                    await connection.rollback()
                    return "no_choice", None
                option = next((item for item in event["options"] if item["option_id"] == option_id), None)
                if option is None:
                    await connection.rollback()
                    return "invalid_option", None
                stage_index = state["stage_index"]
                effect = option["effect"]
                state["selected_option"] = option_id
                state["pending_choice"] = False
                if effect["type"] == "battle":
                    status, _ = await self._begin_encounter_unlocked(
                        row, state, event, effect["enemy_id"], False, now,
                        world_catalog, pet_catalog, random.SystemRandom(),
                    )
                    if status != "battling":
                        await connection.rollback()
                        return status, None
                    await self._log_event_unlocked(row["run_id"], stage_index, event["event_id"], {"selected_option": option_id}, now)
                    await connection.commit()
                    return "battling", _record(row["run_id"], "active", state)
                await self._apply_effect_unlocked(row, state, effect, now, world_catalog, pet_catalog)
                outcome = state.get("last_event_result", {})
                outcome["selected_option"] = option_id
                await self._log_event_unlocked(row["run_id"], stage_index, event["event_id"], outcome, now)
                state["stage_index"] += 1
                state["current_event"] = None
                state["pending_choice"] = False
                status = "defeated" if state["pet_snapshot"]["hp"] <= 0 else "active"
                await self._save_run_unlocked(row["run_id"], status, state, now)
                await connection.commit()
                return ("defeated" if status == "defeated" else "chosen"), _record(row["run_id"], status, state)
            except Exception:
                await connection.rollback()
                raise

    async def act(
        self, platform_id: str, player_id: str, action_type: str, skill_id: str | None,
        request_key: str | None, now: str, world_catalog: WorldCatalog,
        pet_catalog: PetCatalog, expected_button_token: str | None = None,
    ) -> tuple[str, dict[str, Any] | None]:
        async with self.database.lock:
            connection = self.database.connection
            await connection.execute("BEGIN IMMEDIATE")
            try:
                if request_key:
                    async with connection.execute(
                        "SELECT result_json FROM dungeon_actions WHERE request_key=?",
                        (request_key,),
                    ) as cursor:
                        duplicate = await cursor.fetchone()
                    if duplicate:
                        await connection.rollback()
                        return "duplicate", _load(duplicate["result_json"])
                row = await self._active_run_unlocked(platform_id, player_id)
                if row is None:
                    await connection.rollback()
                    return "no_run", None
                state = _load(row["state_json"])
                if expected_button_token and state.get("button_token") != expected_button_token:
                    await connection.rollback()
                    return "stale_button", None
                if state.get("status") != "battling" or not state.get("combat"):
                    await connection.rollback()
                    return "not_battling", None
                combat = state["combat"]
                if combat.get("current_turn_player_id") != player_id:
                    await connection.rollback()
                    return "not_your_turn", None
                player_before = _dump(combat)
                try:
                    player_result = resolve_action(combat, player_id, action_type, skill_id)
                except ValueError as error:
                    await connection.rollback()
                    return "invalid_action", {"message": str(error)}
                action_records = [(player_result, player_before, _dump(combat))]
                if combat["status"] == "active" and combat["current_turn_player_id"] == "__enemy__":
                    enemy_action, enemy_skill = choose_enemy_action(combat)
                    enemy_before = _dump(combat)
                    enemy_result = resolve_action(combat, "__enemy__", enemy_action, enemy_skill)
                    action_records.append((enemy_result, enemy_before, _dump(combat)))

                state["combat"] = combat
                player_snapshot = combat["players"][player_id]
                state["pet_snapshot"]["hp"] = player_snapshot["hp"]
                state["pet_snapshot"]["mp"] = player_snapshot["mp"]
                await connection.execute(
                    "UPDATE pets SET current_hp=?, current_mp=? WHERE pet_id=? AND platform_id=? AND player_id=?",
                    (player_snapshot["hp"], player_snapshot["mp"], state["pet_id"], platform_id, player_id),
                )
                current_event = state["current_event"]
                event_index = state["stage_index"]
                if combat["status"] in {"finished", "draw"}:
                    if combat.get("winner_id") == player_id:
                        enemy_id = combat["enemy_id"]
                        enemy = world_catalog.enemies[enemy_id]
                        xp = experience_reward(enemy, state["xp_multiplier"])
                        state["last_xp_reward"] = xp
                        pet = await self._load_owned_pet_unlocked(platform_id, player_id, state["pet_id"])
                        species = pet_catalog.species[pet.species_id]
                        learned = pet.gain_experience(xp, species)
                        await self._save_pet_unlocked(pet, learned)
                        state["pet_snapshot"] = self._player_snapshot(pet, species, pet_catalog)
                        state["last_event_result"] = {
                            "enemy_id": enemy_id, "won": True, "xp": xp,
                            "pet_hp": pet.current_hp, "pet_mp": pet.current_mp,
                        }
                        await self._log_event_unlocked(
                            row["run_id"], event_index, current_event["event_id"],
                            state["last_event_result"], now,
                        )
                        state["combat"] = None
                        state["current_event"] = None
                        state["stage_index"] += 1
                        state["status"] = "exploring"
                        if current_event.get("type") == "boss":
                            state["status"] = "completed"
                            await self._record_clear_unlocked(
                                platform_id, player_id, state["dungeon_id"],
                                state["difficulty_id"], now,
                            )
                    else:
                        state["last_event_result"] = {
                            "enemy_id": combat.get("enemy_id"), "won": False,
                            "pet_hp": player_snapshot["hp"], "pet_mp": player_snapshot["mp"],
                        }
                        await self._log_event_unlocked(
                            row["run_id"], event_index, current_event["event_id"],
                            state["last_event_result"], now,
                        )
                        state["combat"] = None
                        state["status"] = "defeated"
                if state.get("status") == "battling":
                    state["button_token"] = uuid.uuid4().hex
                else:
                    state.pop("button_token", None)
                result_payload = {"results": [result for result, _, _ in action_records], "run": state}
                for result, before, after in action_records:
                    await self._log_action_unlocked(
                        row["run_id"], event_index, result, before,
                        after, request_key if result is player_result else None, now,
                    )
                run_state = state["status"] if state["status"] in {"completed", "defeated"} else "active"
                await self._save_run_unlocked(row["run_id"], run_state, state, now)
                await connection.commit()
                return "acted", result_payload
            except sqlite3.IntegrityError:
                await connection.rollback()
                return "duplicate", None
            except Exception:
                await connection.rollback()
                raise

    async def retreat(
        self, platform_id: str, player_id: str, now: str
    ) -> tuple[str, dict[str, Any] | None]:
        async with self.database.lock:
            connection = self.database.connection
            await connection.execute("BEGIN IMMEDIATE")
            try:
                row = await self._active_run_unlocked(platform_id, player_id)
                if row is None:
                    await connection.rollback()
                    return "no_run", None
                state = _load(row["state_json"])
                state["status"] = "retreated"
                state["combat"] = None
                state["current_event"] = None
                await self._save_run_unlocked(row["run_id"], "retreated", state, now)
                await connection.commit()
                return "retreated", _record(row["run_id"], "retreated", state)
            except Exception:
                await connection.rollback()
                raise

    async def rest_pet(
        self, platform_id: str, player_id: str, now: str,
        starting_city_id: str, world_catalog: WorldCatalog, pet_catalog: PetCatalog,
    ) -> tuple[str, dict[str, Any] | None]:
        async with self.database.lock:
            connection = self.database.connection
            await connection.execute("BEGIN IMMEDIATE")
            try:
                async with connection.execute(
                    "SELECT 1 FROM dungeon_runs WHERE platform_id=? AND player_id=? AND state='active'",
                    (platform_id, player_id),
                ) as cursor:
                    if await cursor.fetchone():
                        await connection.rollback()
                        return "run_active", None
                async with connection.execute(
                    """SELECT current_city_id FROM dungeon_player_state
                       WHERE platform_id=? AND player_id=?""",
                    (platform_id, player_id),
                ) as cursor:
                    row = await cursor.fetchone()
                city_id = row["current_city_id"] if row else starting_city_id
                city = world_catalog.cities[city_id]
                cost = city["rest_cost"]
                pet_row = await self._get_active_pet_unlocked(platform_id, player_id)
                if pet_row is None:
                    await connection.rollback()
                    return "no_pet", None
                pet = await self._hydrate_pet_unlocked(pet_row)
                species = pet_catalog.species.get(pet.species_id)
                if species is None:
                    await connection.rollback()
                    return "species_missing", None
                max_hp, max_mp = species.max_hp(pet.level), species.max_mp(pet.level)
                if pet.current_hp >= max_hp and pet.current_mp >= max_mp:
                    await connection.rollback()
                    return "already_restored", None
                balance = await self._get_balance_unlocked(platform_id, player_id)
                if balance < cost:
                    await connection.rollback()
                    return "insufficient_currency", {"cost": cost, "balance": balance, "city": city["name"]}
                if cost:
                    await connection.execute(
                        "UPDATE currency_accounts SET balance=balance-?, updated_at=CURRENT_TIMESTAMP WHERE platform_id=? AND player_id=?",
                        (cost, platform_id, player_id),
                    )
                    await connection.execute(
                        """INSERT INTO currency_transactions(platform_id, player_id, amount, reason)
                           VALUES(?, ?, ?, ?)""",
                        (platform_id, player_id, -cost, f"{city['name']}宠物休息"),
                    )
                pet.current_hp, pet.current_mp = max_hp, max_mp
                await connection.execute(
                    "UPDATE pets SET current_hp=?, current_mp=? WHERE pet_id=? AND platform_id=? AND player_id=?",
                    (max_hp, max_mp, pet.pet_id, platform_id, player_id),
                )
                await connection.commit()
                return "rested", {"city": city["name"], "cost": cost, "hp": max_hp, "mp": max_mp}
            except Exception:
                await connection.rollback()
                raise

    async def _begin_encounter_unlocked(
        self, row, state: dict[str, Any], event: dict[str, Any], enemy_id: str,
        is_boss: bool, now: str, world_catalog: WorldCatalog,
        pet_catalog: PetCatalog, rng: random.Random | random.SystemRandom,
    ) -> tuple[str, dict[str, Any] | None]:
        enemy = world_catalog.enemies.get(enemy_id)
        if enemy is None:
            return "enemy_missing", None
        player_snapshot = deepcopy(state["pet_snapshot"])
        combat = make_encounter(
            row["player_id"], player_snapshot, enemy_id, state["enemy_level"],
            enemy, pet_catalog, rng,
        )
        event["type"] = "boss" if is_boss else "spirit_battle"
        event["enemy_id"] = enemy_id
        state["current_event"] = event
        state["combat"] = combat
        state["button_token"] = uuid.uuid4().hex
        state["status"] = "battling"
        if combat["current_turn_player_id"] == "__enemy__":
            action_type, skill_id = choose_enemy_action(combat)
            before = _dump(combat)
            result = resolve_action(combat, "__enemy__", action_type, skill_id)
            await self._log_action_unlocked(
                row["run_id"], state["stage_index"], result, before, _dump(combat), None, now,
            )
            player_combat = combat["players"][row["player_id"]]
            state["pet_snapshot"]["hp"] = player_combat["hp"]
            state["pet_snapshot"]["mp"] = player_combat["mp"]
            await self.database.connection.execute(
                "UPDATE pets SET current_hp=?, current_mp=? WHERE pet_id=? AND platform_id=? AND player_id=?",
                (player_combat["hp"], player_combat["mp"], state["pet_id"], row["platform_id"], row["player_id"]),
            )
            if combat["status"] != "active":
                state["status"] = "defeated"
                state["combat"] = None
                state["last_event_result"] = {"enemy_id": enemy_id, "won": False}
                await self._log_event_unlocked(
                    row["run_id"], state["stage_index"], event["event_id"],
                    state["last_event_result"], now,
                )
        await self._save_run_unlocked(
            row["run_id"], "defeated" if state["status"] == "defeated" else "active", state, now
        )
        return state["status"], combat

    async def _apply_immediate_event_unlocked(
        self, row, state: dict[str, Any], event: dict[str, Any], event_index: int,
        now: str, world_catalog: WorldCatalog, pet_catalog: PetCatalog,
    ) -> str:
        if event["type"] == "story":
            state["last_event_result"] = {"text": event["text"]}
        elif event["type"] == "rest":
            await self._apply_effect_unlocked(
                row, state,
                {"type": "rest", "hp_percent": event["hp_percent"], "mp_percent": event["mp_percent"]},
                now, world_catalog, pet_catalog,
            )
        elif event["type"] == "treasure":
            amount = event["currency_amount"]
            await self._credit_unlocked(
                row["platform_id"], row["player_id"], amount,
                f"副本事件奖励：{event['title']}",
                f"dungeon:{row['run_id']}:event:{event_index}",
            )
            state["last_event_result"] = {"currency": amount}
        elif event["type"] == "hazard":
            hp = state["pet_snapshot"]["hp"]
            damage = min(hp, event["damage"])
            state["pet_snapshot"]["hp"] -= damage
            state["last_event_result"] = {"damage": damage}
            await self._persist_pet_hpmp_unlocked(row, state)
            if state["pet_snapshot"]["hp"] <= 0:
                state["status"] = "defeated"
                return "defeated"
        return "ok"

    async def _apply_effect_unlocked(
        self, row, state: dict[str, Any], effect: dict[str, Any], now: str,
        world_catalog: WorldCatalog, pet_catalog: PetCatalog,
    ) -> None:
        pet = state["pet_snapshot"]
        if effect["type"] == "rest":
            hp_restore = max(0, round(pet["max_hp"] * effect["hp_percent"]))
            mp_restore = max(0, round(pet["max_mp"] * effect["mp_percent"]))
            hp_actual = min(pet["max_hp"] - pet["hp"], hp_restore)
            mp_actual = min(pet["max_mp"] - pet["mp"], mp_restore)
            pet["hp"] += hp_actual
            pet["mp"] += mp_actual
            state["last_event_result"] = {"hp_restored": hp_actual, "mp_restored": mp_actual}
            await self._persist_pet_hpmp_unlocked(row, state)
        elif effect["type"] == "currency":
            amount = effect["amount"]
            event_index = state["stage_index"]
            await self._credit_unlocked(
                row["platform_id"], row["player_id"], amount, "副本选择奖励",
                f"dungeon:{row['run_id']}:event:{event_index}",
            )
            state["last_event_result"] = {"currency": amount}
        elif effect["type"] == "damage":
            damage = min(pet["hp"], effect["amount"])
            pet["hp"] -= damage
            state["last_event_result"] = {"damage": damage}
            await self._persist_pet_hpmp_unlocked(row, state)

    async def _persist_pet_hpmp_unlocked(self, row, state: dict[str, Any]) -> None:
        pet = state["pet_snapshot"]
        await self.database.connection.execute(
            "UPDATE pets SET current_hp=?, current_mp=? WHERE pet_id=? AND platform_id=? AND player_id=?",
            (pet["hp"], pet["mp"], state["pet_id"], row["platform_id"], row["player_id"]),
        )

    async def _log_action_unlocked(
        self, run_id: str, event_index: int, result: dict[str, Any], before: str,
        after: str, request_key: str | None, now: str,
    ) -> None:
        await self.database.connection.execute(
            """INSERT INTO dungeon_actions
               (run_id, event_index, round_number, actor_id, action_type, skill_id,
                request_key, result_json, state_before_json, state_after_json, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id, event_index, result["round_number"], result["player_id"],
                result["action_type"], result.get("skill_id"), request_key,
                _dump(result), before, after, now,
            ),
        )

    async def _log_event_unlocked(
        self, run_id: str, event_index: int, event_id: str,
        outcome: dict[str, Any], now: str,
    ) -> None:
        await self.database.connection.execute(
            """INSERT INTO dungeon_run_events(run_id, event_index, event_id, outcome_json, created_at)
               VALUES(?, ?, ?, ?, ?) ON CONFLICT(run_id, event_index) DO UPDATE SET
               outcome_json=excluded.outcome_json""",
            (run_id, event_index, event_id, _dump(outcome), now),
        )

    async def _save_run_unlocked(self, run_id: str, status: str, state: dict[str, Any], now: str) -> None:
        if status in {"battling", "exploring", "completed", "defeated", "retreated"}:
            state["status"] = status
        await self.database.connection.execute(
            "UPDATE dungeon_runs SET state=?, state_json=?, updated_at=? WHERE run_id=?",
            ("active" if status in {"active", "battling", "exploring"} else status, _dump(state), now, run_id),
        )

    async def _active_run_unlocked(self, platform_id: str, player_id: str):
        async with self.database.connection.execute(
            """SELECT * FROM dungeon_runs WHERE platform_id=? AND player_id=? AND state='active' LIMIT 1""",
            (platform_id, player_id),
        ) as cursor:
            return await cursor.fetchone()

    async def _get_active_pet_unlocked(self, platform_id: str, player_id: str):
        async with self.database.connection.execute(
            "SELECT * FROM pets WHERE platform_id=? AND player_id=? AND is_active=1 LIMIT 1",
            (platform_id, player_id),
        ) as cursor:
            return await cursor.fetchone()

    async def _hydrate_pet_unlocked(self, row) -> Pet:
        async with self.database.connection.execute(
            "SELECT skill_id, slot FROM pet_skills WHERE pet_id=? ORDER BY slot, learned_at",
            (row["pet_id"],),
        ) as cursor:
            skills = await cursor.fetchall()
        return Pet(
            pet_id=row["pet_id"], platform_id=row["platform_id"], player_id=row["player_id"],
            species_id=row["species_id"], name=row["name"], level=int(row["level"]),
            experience=int(row["experience"]), current_hp=int(row["current_hp"]),
            current_mp=int(row["current_mp"]), is_active=bool(row["is_active"]),
            created_at=row["created_at"], skills=[
                PetSkillState(skill_id=skill["skill_id"], slot=int(skill["slot"]) if skill["slot"] is not None else None)
                for skill in skills
            ],
        )

    async def _load_owned_pet_unlocked(self, platform_id: str, player_id: str, pet_id: str) -> Pet:
        async with self.database.connection.execute(
            "SELECT * FROM pets WHERE platform_id=? AND player_id=? AND pet_id=?",
            (platform_id, player_id, pet_id),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("探索中的宠物档案不存在")
        return await self._hydrate_pet_unlocked(row)

    async def _save_pet_unlocked(self, pet: Pet, learned: list[str]) -> None:
        await self.database.connection.execute(
            """UPDATE pets SET level=?, experience=?, current_hp=?, current_mp=?
               WHERE pet_id=? AND platform_id=? AND player_id=?""",
            (pet.level, pet.experience, pet.current_hp, pet.current_mp, pet.pet_id, pet.platform_id, pet.player_id),
        )
        if learned:
            await self.database.connection.executemany(
                "INSERT OR IGNORE INTO pet_skills(pet_id, skill_id) VALUES(?, ?)",
                [(pet.pet_id, skill_id) for skill_id in learned],
            )

    def _player_snapshot(self, pet: Pet, species, pet_catalog: PetCatalog) -> dict[str, Any]:
        skills = {}
        for entry in pet.equipped_skills:
            skill = pet_catalog.skills.get(entry.skill_id)
            if skill is None or (skill.target_type, skill.effect_type) not in {
                ("single_enemy", "damage"), ("single_ally", "heal")
            }:
                continue
            skills[skill.skill_id] = {
                "skill_id": skill.skill_id, "name": skill.name, "mp_cost": skill.mp_cost,
                "target_type": skill.target_type, "effect_type": skill.effect_type,
                "effect_value": skill.effect_value,
            }
        max_hp, max_mp = species.max_hp(pet.level), species.max_mp(pet.level)
        return {
            "pet_id": pet.pet_id, "pet_name": pet.name, "species_id": species.species_id,
            "species_name": species.name, "level": pet.level, "experience": pet.experience,
            "hp": min(pet.current_hp, max_hp), "max_hp": max_hp,
            "mp": min(pet.current_mp, max_mp), "max_mp": max_mp,
            "attack": species.attack(pet.level), "defense": species.defense(pet.level),
            "speed": species.speed, "guarding": False, "skills": skills,
        }

    async def _requirements_met_unlocked(
        self, platform_id: str, player_id: str, requirements: list[dict[str, str]]
    ) -> bool:
        for requirement in requirements:
            async with self.database.connection.execute(
                """SELECT 1 FROM dungeon_progress WHERE platform_id=? AND player_id=?
                   AND dungeon_id=? AND difficulty_id=? AND clear_count>0""",
                (platform_id, player_id, requirement["dungeon_id"], requirement["difficulty_id"]),
            ) as cursor:
                if await cursor.fetchone() is None:
                    return False
        return True

    async def _record_clear_unlocked(
        self, platform_id: str, player_id: str, dungeon_id: str,
        difficulty_id: str, now: str,
    ) -> None:
        await self.database.connection.execute(
            """INSERT INTO dungeon_progress
               (platform_id, player_id, dungeon_id, difficulty_id, clear_count, first_cleared_at)
               VALUES(?, ?, ?, ?, 1, ?) ON CONFLICT(platform_id, player_id, dungeon_id, difficulty_id)
               DO UPDATE SET clear_count=clear_count+1""",
            (platform_id, player_id, dungeon_id, difficulty_id, now),
        )

    async def _credit_unlocked(
        self, platform_id: str, player_id: str, amount: int, reason: str, key: str
    ) -> None:
        if amount <= 0:
            return
        async with self.database.connection.execute(
            "SELECT 1 FROM currency_transactions WHERE idempotency_key=?", (key,)
        ) as cursor:
            if await cursor.fetchone():
                return
        await self.database.connection.execute(
            "INSERT OR IGNORE INTO currency_accounts(platform_id, player_id) VALUES(?, ?)",
            (platform_id, player_id),
        )
        await self.database.connection.execute(
            "UPDATE currency_accounts SET balance=balance+?, updated_at=CURRENT_TIMESTAMP WHERE platform_id=? AND player_id=?",
            (amount, platform_id, player_id),
        )
        await self.database.connection.execute(
            """INSERT OR IGNORE INTO currency_transactions
               (platform_id, player_id, amount, reason, idempotency_key) VALUES(?, ?, ?, ?, ?)""",
            (platform_id, player_id, amount, reason, key),
        )

    async def _get_balance_unlocked(self, platform_id: str, player_id: str) -> int:
        async with self.database.connection.execute(
            "SELECT balance FROM currency_accounts WHERE platform_id=? AND player_id=?",
            (platform_id, player_id),
        ) as cursor:
            row = await cursor.fetchone()
        return int(row["balance"]) if row else 0


def _weighted_choice(entries: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(entry["weight"] for entry in entries)
    roll = random.SystemRandom().randrange(total)
    for entry in entries:
        roll -= entry["weight"]
        if roll < 0:
            return entry
    return entries[-1]


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load(value: str) -> dict[str, Any]:
    return json.loads(value)


def _record(run_id: str, state: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"run_id": run_id, "state": state, "data": data}
