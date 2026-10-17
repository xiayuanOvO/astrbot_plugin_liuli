from ....application.ports.pet_repository import PetRepository
from ....domain.pet import Pet, PetSkillState, PetSpecies
from .database import SQLiteDatabase


class SQLitePetRepository(PetRepository):
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    async def list_pets(self, platform_id: str, player_id: str) -> list[Pet]:
        async with self.database.lock:
            async with self.database.connection.execute(
                """SELECT * FROM pets WHERE platform_id=? AND player_id=?
                   ORDER BY is_active DESC, created_at, pet_id""",
                (platform_id, player_id),
            ) as cursor:
                rows = await cursor.fetchall()
            return [await self._hydrate(row) for row in rows]

    async def get_pet(self, platform_id: str, player_id: str, pet_id: str) -> Pet | None:
        async with self.database.lock:
            async with self.database.connection.execute(
                """SELECT * FROM pets
                   WHERE platform_id=? AND player_id=? AND pet_id=?""",
                (platform_id, player_id, pet_id),
            ) as cursor:
                row = await cursor.fetchone()
            return await self._hydrate(row) if row else None

    async def adopt_initial_pet(self, pet: Pet) -> bool:
        async with self.database.lock:
            connection = self.database.connection
            await connection.execute("BEGIN IMMEDIATE")
            try:
                async with connection.execute(
                    """SELECT 1 FROM pets WHERE platform_id=? AND player_id=? LIMIT 1""",
                    (pet.platform_id, pet.player_id),
                ) as cursor:
                    already_has_pet = await cursor.fetchone() is not None
                if already_has_pet:
                    await connection.rollback()
                    return False
                await connection.execute(
                    """INSERT INTO pets
                       (pet_id, platform_id, player_id, species_id, name, level,
                        experience, current_hp, current_mp, is_active)
                       VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                    (
                        pet.pet_id,
                        pet.platform_id,
                        pet.player_id,
                        pet.species_id,
                        pet.name,
                        pet.level,
                        pet.experience,
                        pet.current_hp,
                        pet.current_mp,
                    ),
                )
                await connection.executemany(
                    """INSERT INTO pet_skills(pet_id, skill_id, slot)
                       VALUES(?, ?, ?)""",
                    [(pet.pet_id, skill.skill_id, skill.slot) for skill in pet.skills],
                )
                await connection.commit()
                return True
            except Exception:
                await connection.rollback()
                raise

    async def rename_pet(
        self,
        platform_id: str,
        player_id: str,
        pet_id: str,
        name: str,
    ) -> bool:
        async with self.database.lock:
            async with self.database.connection.execute(
                """UPDATE pets SET name=? WHERE platform_id=? AND player_id=? AND pet_id=?""",
                (name, platform_id, player_id, pet_id),
            ) as cursor:
                updated = cursor.rowcount > 0
            await self.database.connection.commit()
            return updated

    async def set_active_pet(
        self, platform_id: str, player_id: str, pet_id: str
    ) -> bool:
        async with self.database.lock:
            connection = self.database.connection
            await connection.execute("BEGIN IMMEDIATE")
            try:
                async with connection.execute(
                    """SELECT 1 FROM pets WHERE platform_id=? AND player_id=? AND pet_id=?""",
                    (platform_id, player_id, pet_id),
                ) as cursor:
                    exists = await cursor.fetchone() is not None
                if not exists:
                    await connection.rollback()
                    return False
                await connection.execute(
                    """UPDATE pets SET is_active=0 WHERE platform_id=? AND player_id=?""",
                    (platform_id, player_id),
                )
                await connection.execute(
                    """UPDATE pets SET is_active=1
                       WHERE platform_id=? AND player_id=? AND pet_id=?""",
                    (platform_id, player_id, pet_id),
                )
                await connection.commit()
                return True
            except Exception:
                await connection.rollback()
                raise

    async def equip_skill(
        self, platform_id: str, player_id: str, pet_id: str, skill_id: str
    ) -> tuple[str, int | None]:
        async with self.database.lock:
            connection = self.database.connection
            await connection.execute("BEGIN IMMEDIATE")
            try:
                async with connection.execute(
                    """SELECT s.slot FROM pet_skills s JOIN pets p ON p.pet_id=s.pet_id
                       WHERE p.platform_id=? AND p.player_id=? AND p.pet_id=? AND s.skill_id=?""",
                    (platform_id, player_id, pet_id, skill_id),
                ) as cursor:
                    learned = await cursor.fetchone()
                if learned is None:
                    await connection.rollback()
                    return "not_learned", None
                if learned["slot"] is not None:
                    await connection.rollback()
                    return "already_equipped", int(learned["slot"])

                async with connection.execute(
                    """SELECT slot FROM pet_skills WHERE pet_id=? AND slot IS NOT NULL""",
                    (pet_id,),
                ) as cursor:
                    occupied = {int(row["slot"]) for row in await cursor.fetchall()}
                slot = next((value for value in range(1, 5) if value not in occupied), None)
                if slot is None:
                    await connection.rollback()
                    return "slots_full", None
                await connection.execute(
                    "UPDATE pet_skills SET slot=? WHERE pet_id=? AND skill_id=?",
                    (slot, pet_id, skill_id),
                )
                await connection.commit()
                return "equipped", slot
            except Exception:
                await connection.rollback()
                raise

    async def unequip_skill(
        self, platform_id: str, player_id: str, pet_id: str, skill_id: str
    ) -> str:
        async with self.database.lock:
            connection = self.database.connection
            async with connection.execute(
                """UPDATE pet_skills SET slot=NULL WHERE pet_id=? AND skill_id=?
                   AND slot IS NOT NULL AND EXISTS (
                     SELECT 1 FROM pets WHERE pets.pet_id=pet_skills.pet_id
                       AND platform_id=? AND player_id=?
                   )""",
                (pet_id, skill_id, platform_id, player_id),
            ) as cursor:
                updated = cursor.rowcount > 0
            await connection.commit()
            if updated:
                return "unequipped"
            async with connection.execute(
                """SELECT 1 FROM pet_skills s JOIN pets p ON p.pet_id=s.pet_id
                   WHERE p.platform_id=? AND p.player_id=? AND p.pet_id=? AND s.skill_id=?""",
                (platform_id, player_id, pet_id, skill_id),
            ) as check_cursor:
                learned = await check_cursor.fetchone()
            return "not_equipped" if learned else "not_learned"

    async def grant_experience(
        self,
        platform_id: str,
        player_id: str,
        pet_id: str,
        amount: int,
        species: PetSpecies,
    ) -> tuple[Pet | None, list[str]]:
        async with self.database.lock:
            connection = self.database.connection
            await connection.execute("BEGIN IMMEDIATE")
            try:
                async with connection.execute(
                    """SELECT * FROM pets WHERE platform_id=? AND player_id=? AND pet_id=?""",
                    (platform_id, player_id, pet_id),
                ) as cursor:
                    row = await cursor.fetchone()
                if row is None:
                    await connection.rollback()
                    return None, []
                pet = await self._hydrate(row)
                unlocked = pet.gain_experience(amount, species)
                await connection.execute(
                    """UPDATE pets SET level=?, experience=?, current_hp=?, current_mp=?
                       WHERE pet_id=? AND platform_id=? AND player_id=?""",
                    (
                        pet.level,
                        pet.experience,
                        pet.current_hp,
                        pet.current_mp,
                        pet_id,
                        platform_id,
                        player_id,
                    ),
                )
                if unlocked:
                    await connection.executemany(
                        "INSERT OR IGNORE INTO pet_skills(pet_id, skill_id) VALUES(?, ?)",
                        [(pet_id, skill_id) for skill_id in unlocked],
                    )
                updated = await self._get_pet_unlocked(platform_id, player_id, pet_id)
                await connection.commit()
                return updated, unlocked
            except Exception:
                await connection.rollback()
                raise

    async def _get_pet_unlocked(
        self, platform_id: str, player_id: str, pet_id: str
    ) -> Pet | None:
        async with self.database.connection.execute(
            """SELECT * FROM pets WHERE platform_id=? AND player_id=? AND pet_id=?""",
            (platform_id, player_id, pet_id),
        ) as cursor:
            row = await cursor.fetchone()
        return await self._hydrate(row) if row else None

    async def _hydrate(self, row) -> Pet:
        async with self.database.connection.execute(
            "SELECT skill_id, slot FROM pet_skills WHERE pet_id=? ORDER BY slot, learned_at",
            (row["pet_id"],),
        ) as cursor:
            skill_rows = await cursor.fetchall()
        return Pet(
            pet_id=row["pet_id"],
            platform_id=row["platform_id"],
            player_id=row["player_id"],
            species_id=row["species_id"],
            name=row["name"],
            level=int(row["level"]),
            experience=int(row["experience"]),
            current_hp=int(row["current_hp"]),
            current_mp=int(row["current_mp"]),
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            skills=[
                PetSkillState(
                    skill_id=skill_row["skill_id"],
                    slot=int(skill_row["slot"]) if skill_row["slot"] is not None else None,
                )
                for skill_row in skill_rows
            ],
        )
