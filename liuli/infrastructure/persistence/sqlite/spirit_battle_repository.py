import json
from typing import Any

from ....application.ports.spirit_battle_repository import SpiritBattleRepository
from ....domain.pet import PetCatalog
from ....domain.spirit_battle import first_turn_probability, resolve_action
from .database import SQLiteDatabase


class SQLiteSpiritBattleRepository(SpiritBattleRepository):
    def __init__(self, database: SQLiteDatabase, catalog: PetCatalog):
        self.database = database
        self.catalog = catalog

    async def create_challenge(
        self,
        platform_id: str,
        group_id: str,
        challenger_id: str,
        opponent_id: str,
        battle_id: str,
        now: str,
        expires_at: str,
    ) -> tuple[str, dict[str, Any] | None]:
        async with self.database.lock:
            connection = self.database.connection
            await connection.execute("BEGIN IMMEDIATE")
            try:
                await self._expire_group_unlocked(platform_id, group_id, now)
                await self._expire_players_unlocked(platform_id, (challenger_id, opponent_id), now)
                placeholders = "?, ?"
                async with connection.execute(
                    f"""SELECT 1 FROM dungeon_runs WHERE platform_id=? AND state='active'
                        AND player_id IN ({placeholders}) LIMIT 1""",
                    (platform_id, challenger_id, opponent_id),
                ) as cursor:
                    if await cursor.fetchone():
                        await connection.rollback()
                        return "player_busy", None
                if await self._has_active_pet_unlocked(platform_id, challenger_id) is False:
                    await connection.rollback()
                    return "challenger_no_pet", None
                if await self._has_active_pet_unlocked(platform_id, opponent_id) is False:
                    await connection.rollback()
                    return "opponent_no_pet", None
                async with connection.execute(
                    """SELECT 1 FROM spirit_battles WHERE platform_id=? AND group_id=?
                       AND state IN ('pending', 'active') LIMIT 1""",
                    (platform_id, group_id),
                ) as cursor:
                    if await cursor.fetchone():
                        await connection.rollback()
                        return "group_busy", None
                async with connection.execute(
                    """SELECT 1 FROM spirit_battles WHERE platform_id=?
                       AND state IN ('pending', 'active')
                       AND (challenger_id IN (?, ?) OR opponent_id IN (?, ?)) LIMIT 1""",
                    (platform_id, challenger_id, opponent_id, challenger_id, opponent_id),
                ) as cursor:
                    if await cursor.fetchone():
                        await connection.rollback()
                        return "player_busy", None
                state = {"status": "pending", "winner_id": None}
                await connection.execute(
                    """INSERT INTO spirit_battles
                       (battle_id, platform_id, group_id, challenger_id, opponent_id,
                        state, current_turn_player_id, round_number, state_json, winner_id,
                        created_at, updated_at, expires_at)
                       VALUES(?, ?, ?, ?, ?, 'pending', NULL, 0, ?, NULL, ?, ?, ?)""",
                    (
                        battle_id, platform_id, group_id, challenger_id, opponent_id,
                        _dump(state), now, now, expires_at,
                    ),
                )
                await connection.commit()
                return "created", {"battle_id": battle_id, "state": "pending"}
            except Exception:
                await connection.rollback()
                raise

    async def accept_challenge(
        self,
        platform_id: str,
        group_id: str,
        player_id: str,
        now: str,
        expires_at: str,
        roll: float,
        catalog: PetCatalog,
    ) -> tuple[str, dict[str, Any] | None]:
        async with self.database.lock:
            connection = self.database.connection
            await connection.execute("BEGIN IMMEDIATE")
            try:
                async with connection.execute(
                    """SELECT * FROM spirit_battles WHERE platform_id=? AND group_id=?
                       AND opponent_id=? AND state='pending' ORDER BY created_at DESC LIMIT 1""",
                    (platform_id, group_id, player_id),
                ) as cursor:
                    row = await cursor.fetchone()
                if row is None:
                    await connection.rollback()
                    return "no_challenge", None
                if row["expires_at"] <= now:
                    state = _load(row["state_json"])
                    state["status"] = "expired"
                    await self._update_terminal_unlocked(row, state, "expired", None, now)
                    await connection.commit()
                    return "expired", _record(row, state)
                challenger_id = row["challenger_id"]
                await self._expire_players_unlocked(platform_id, (challenger_id, player_id), now)
                if await self._has_other_battle_unlocked(platform_id, challenger_id, row["battle_id"]):
                    await connection.rollback()
                    return "player_busy", None
                challenger = await self._active_pet_snapshot_unlocked(platform_id, challenger_id, catalog)
                opponent = await self._active_pet_snapshot_unlocked(platform_id, player_id, catalog)
                if challenger is None or opponent is None:
                    await connection.rollback()
                    return "pet_unavailable", None
                challenger_speed = challenger["speed"]
                opponent_speed = opponent["speed"]
                probability = first_turn_probability(challenger_speed, opponent_speed)
                first_turn = challenger_id if roll < probability else player_id
                state = {
                    "status": "active",
                    "players": {challenger_id: challenger, player_id: opponent},
                    "current_turn_player_id": first_turn,
                    "round_number": 1,
                    "acted_this_round": [],
                    "winner_id": None,
                    "first_turn": {
                        "challenger_speed": challenger_speed,
                        "opponent_speed": opponent_speed,
                        "challenger_probability": probability,
                        "roll": roll,
                        "player_id": first_turn,
                    },
                }
                await connection.execute(
                    """UPDATE spirit_battles SET state='active', current_turn_player_id=?,
                       round_number=1, state_json=?, updated_at=?, expires_at=? WHERE battle_id=?""",
                    (first_turn, _dump(state), now, expires_at, row["battle_id"]),
                )
                await connection.commit()
                row = dict(row)
                row.update(state="active", current_turn_player_id=first_turn, round_number=1,
                           state_json=_dump(state), updated_at=now, expires_at=expires_at)
                return "accepted", _record(row, state)
            except Exception:
                await connection.rollback()
                raise

    async def decline_challenge(
        self, platform_id: str, group_id: str, player_id: str, now: str
    ) -> tuple[str, dict[str, Any] | None]:
        async with self.database.lock:
            connection = self.database.connection
            await connection.execute("BEGIN IMMEDIATE")
            try:
                async with connection.execute(
                    """SELECT * FROM spirit_battles WHERE platform_id=? AND group_id=?
                       AND opponent_id=? AND state='pending' ORDER BY created_at DESC LIMIT 1""",
                    (platform_id, group_id, player_id),
                ) as cursor:
                    row = await cursor.fetchone()
                if row is None:
                    await connection.rollback()
                    return "no_challenge", None
                state = _load(row["state_json"])
                status = "expired" if row["expires_at"] <= now else "declined"
                state["status"] = status
                await self._update_terminal_unlocked(row, state, status, None, now)
                await connection.commit()
                return status, _record(row, state)
            except Exception:
                await connection.rollback()
                raise

    async def get_for_player(
        self, platform_id: str, group_id: str, player_id: str, now: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        async with self.database.lock:
            connection = self.database.connection
            await connection.execute("BEGIN IMMEDIATE")
            try:
                async with connection.execute(
                    """SELECT * FROM spirit_battles WHERE platform_id=? AND group_id=?
                       AND state IN ('pending', 'active')
                       AND (challenger_id=? OR opponent_id=?)""",
                    (platform_id, group_id, player_id, player_id),
                ) as cursor:
                    rows = await cursor.fetchall()
                expired = []
                for row in rows:
                    if row["expires_at"] > now:
                        continue
                    state = _load(row["state_json"])
                    if row["state"] == "pending":
                        state["status"] = "expired"
                        await self._update_terminal_unlocked(row, state, "expired", None, now)
                    else:
                        winner = row["opponent_id"] if row["current_turn_player_id"] == row["challenger_id"] else row["challenger_id"]
                        state["status"] = "finished"
                        state["winner_id"] = winner
                        state["current_turn_player_id"] = None
                        state["finish_reason"] = "timeout"
                        await self._update_terminal_unlocked(row, state, "finished", winner, now)
                    expired.append(_record(row, state))
                async with connection.execute(
                    """SELECT * FROM spirit_battles WHERE platform_id=? AND group_id=?
                       AND state IN ('pending', 'active')
                       AND (challenger_id=? OR opponent_id=?) ORDER BY created_at DESC LIMIT 1""",
                    (platform_id, group_id, player_id, player_id),
                ) as cursor:
                    active = await cursor.fetchone()
                await connection.commit()
                return ([_record(active, _load(active["state_json"]))] if active else [], expired[-1] if expired else None)
            except Exception:
                await connection.rollback()
                raise

    async def act(
        self,
        platform_id: str,
        group_id: str,
        player_id: str,
        action_type: str,
        skill_id: str | None,
        now: str,
        next_expires_at: str,
    ) -> tuple[str, dict[str, Any] | None]:
        async with self.database.lock:
            connection = self.database.connection
            await connection.execute("BEGIN IMMEDIATE")
            try:
                async with connection.execute(
                    """SELECT * FROM spirit_battles WHERE platform_id=? AND group_id=?
                       AND state='active' AND (challenger_id=? OR opponent_id=?) LIMIT 1""",
                    (platform_id, group_id, player_id, player_id),
                ) as cursor:
                    row = await cursor.fetchone()
                if row is None:
                    await connection.rollback()
                    return "no_battle", None
                state = _load(row["state_json"])
                if row["expires_at"] <= now:
                    winner = row["opponent_id"] if row["current_turn_player_id"] == row["challenger_id"] else row["challenger_id"]
                    state.update(status="finished", winner_id=winner, current_turn_player_id=None, finish_reason="timeout")
                    await self._update_terminal_unlocked(row, state, "finished", winner, now)
                    await connection.commit()
                    return "timeout", _record(row, state)
                before = _dump(state)
                try:
                    result = resolve_action(state, player_id, action_type, skill_id)
                except ValueError as error:
                    await connection.rollback()
                    return "invalid_action:" + str(error), None
                state_after = _dump(state)
                status = state["status"]
                winner = state.get("winner_id")
                deadline = next_expires_at if status == "active" else now
                await connection.execute(
                    """INSERT INTO spirit_battle_actions
                       (battle_id, round_number, player_id, action_type, skill_id, result_json,
                        state_before_json, state_after_json, created_at)
                       VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        row["battle_id"], row["round_number"], player_id, action_type,
                        skill_id, _dump(result), before, state_after, now,
                    ),
                )
                await connection.execute(
                    """UPDATE spirit_battles SET state=?, current_turn_player_id=?, round_number=?,
                       state_json=?, winner_id=?, updated_at=?, expires_at=? WHERE battle_id=?""",
                    (
                        status, state.get("current_turn_player_id"), state["round_number"],
                        state_after, winner, now, deadline, row["battle_id"],
                    ),
                )
                await connection.commit()
                row = dict(row)
                row.update(state=status, current_turn_player_id=state.get("current_turn_player_id"),
                           round_number=state["round_number"], state_json=state_after,
                           winner_id=winner, updated_at=now, expires_at=deadline)
                return "acted", {"battle": _record(row, state), "result": result}
            except Exception:
                await connection.rollback()
                raise

    async def forfeit(
        self, platform_id: str, group_id: str, player_id: str, now: str
    ) -> tuple[str, dict[str, Any] | None]:
        async with self.database.lock:
            connection = self.database.connection
            await connection.execute("BEGIN IMMEDIATE")
            try:
                async with connection.execute(
                    """SELECT * FROM spirit_battles WHERE platform_id=? AND group_id=?
                       AND state='active' AND (challenger_id=? OR opponent_id=?) LIMIT 1""",
                    (platform_id, group_id, player_id, player_id),
                ) as cursor:
                    row = await cursor.fetchone()
                if row is None:
                    await connection.rollback()
                    return "no_battle", None
                if row["expires_at"] <= now:
                    state = _load(row["state_json"])
                    winner = row["opponent_id"] if row["current_turn_player_id"] == row["challenger_id"] else row["challenger_id"]
                    state.update(status="finished", winner_id=winner, current_turn_player_id=None, finish_reason="timeout")
                    await self._update_terminal_unlocked(row, state, "finished", winner, now)
                    await connection.commit()
                    return "timeout", _record(row, state)
                state = _load(row["state_json"])
                winner = row["opponent_id"] if player_id == row["challenger_id"] else row["challenger_id"]
                state.update(status="forfeit", winner_id=winner, current_turn_player_id=None, finish_reason="forfeit")
                await self._update_terminal_unlocked(row, state, "forfeit", winner, now)
                await connection.commit()
                return "forfeit", _record(row, state)
            except Exception:
                await connection.rollback()
                raise

    async def _has_active_pet_unlocked(self, platform_id: str, player_id: str) -> bool:
        async with self.database.connection.execute(
            "SELECT 1 FROM pets WHERE platform_id=? AND player_id=? AND is_active=1 LIMIT 1",
            (platform_id, player_id),
        ) as cursor:
            return await cursor.fetchone() is not None

    async def _has_other_battle_unlocked(self, platform_id: str, player_id: str, battle_id: str) -> bool:
        async with self.database.connection.execute(
            """SELECT 1 FROM spirit_battles WHERE platform_id=? AND battle_id<>?
               AND state IN ('pending', 'active') AND (challenger_id=? OR opponent_id=?) LIMIT 1""",
            (platform_id, battle_id, player_id, player_id),
        ) as cursor:
            return await cursor.fetchone() is not None

    async def _active_pet_snapshot_unlocked(
        self, platform_id: str, player_id: str, catalog: PetCatalog
    ) -> dict[str, Any] | None:
        async with self.database.connection.execute(
            """SELECT * FROM pets WHERE platform_id=? AND player_id=? AND is_active=1 LIMIT 1""",
            (platform_id, player_id),
        ) as cursor:
            pet = await cursor.fetchone()
        if pet is None:
            return None
        species = catalog.species.get(pet["species_id"])
        if species is None:
            return None
        async with self.database.connection.execute(
            """SELECT skill_id FROM pet_skills WHERE pet_id=? AND slot IS NOT NULL ORDER BY slot""",
            (pet["pet_id"],),
        ) as cursor:
            skill_rows = await cursor.fetchall()
        skills = {}
        for skill_row in skill_rows:
            skill = catalog.skills.get(skill_row["skill_id"])
            if skill is None or (skill.target_type, skill.effect_type) not in {
                ("single_enemy", "damage"), ("single_ally", "heal")
            }:
                continue
            skills[skill.skill_id] = {
                "skill_id": skill.skill_id,
                "name": skill.name,
                "mp_cost": skill.mp_cost,
                "target_type": skill.target_type,
                "effect_type": skill.effect_type,
                "effect_value": skill.effect_value,
            }
        level = int(pet["level"])
        return {
            "pet_id": pet["pet_id"], "pet_name": pet["name"], "species_id": species.species_id,
            "species_name": species.name, "level": level,
            "hp": species.max_hp(level), "max_hp": species.max_hp(level),
            "mp": species.max_mp(level), "max_mp": species.max_mp(level),
            "attack": species.attack(level), "defense": species.defense(level),
            "speed": species.speed, "guarding": False, "skills": skills,
        }

    async def _expire_group_unlocked(self, platform_id: str, group_id: str, now: str) -> None:
        async with self.database.connection.execute(
            """SELECT * FROM spirit_battles WHERE platform_id=? AND group_id=?
               AND state IN ('pending', 'active') AND expires_at<=?""",
            (platform_id, group_id, now),
        ) as cursor:
            rows = await cursor.fetchall()
        for row in rows:
            state = _load(row["state_json"])
            if row["state"] == "pending":
                state["status"] = "expired"
                await self._update_terminal_unlocked(row, state, "expired", None, now)
            else:
                winner = row["opponent_id"] if row["current_turn_player_id"] == row["challenger_id"] else row["challenger_id"]
                state.update(status="finished", winner_id=winner, current_turn_player_id=None, finish_reason="timeout")
                await self._update_terminal_unlocked(row, state, "finished", winner, now)

    async def _expire_players_unlocked(
        self, platform_id: str, player_ids: tuple[str, ...], now: str
    ) -> None:
        if not player_ids:
            return
        placeholders = ",".join("?" for _ in player_ids)
        async with self.database.connection.execute(
            f"""SELECT * FROM spirit_battles WHERE platform_id=?
                AND state IN ('pending', 'active') AND expires_at<=?
                AND (challenger_id IN ({placeholders}) OR opponent_id IN ({placeholders}))""",
            (platform_id, now, *player_ids, *player_ids),
        ) as cursor:
            rows = await cursor.fetchall()
        for row in rows:
            state = _load(row["state_json"])
            if row["state"] == "pending":
                state["status"] = "expired"
                await self._update_terminal_unlocked(row, state, "expired", None, now)
            else:
                winner = row["opponent_id"] if row["current_turn_player_id"] == row["challenger_id"] else row["challenger_id"]
                state.update(status="finished", winner_id=winner, current_turn_player_id=None, finish_reason="timeout")
                await self._update_terminal_unlocked(row, state, "finished", winner, now)

    async def _update_terminal_unlocked(
        self, row, state: dict[str, Any], status: str, winner: str | None, now: str
    ) -> None:
        await self.database.connection.execute(
            """UPDATE spirit_battles SET state=?, current_turn_player_id=NULL,
               state_json=?, winner_id=?, updated_at=?, expires_at=? WHERE battle_id=?""",
            (status, _dump(state), winner, now, now, row["battle_id"]),
        )


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load(value: str) -> dict[str, Any]:
    return json.loads(value)


def _record(row, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "battle_id": row["battle_id"], "platform_id": row["platform_id"],
        "group_id": row["group_id"], "challenger_id": row["challenger_id"],
        "opponent_id": row["opponent_id"], "state": state.get("status", row["state"]),
        "current_turn_player_id": state.get("current_turn_player_id", row["current_turn_player_id"]),
        "round_number": state.get("round_number", row["round_number"]),
        "winner_id": state.get("winner_id", row["winner_id"]),
        "expires_at": row["expires_at"], "data": state,
    }
