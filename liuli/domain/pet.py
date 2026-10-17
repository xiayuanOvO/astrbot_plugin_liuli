from dataclasses import dataclass, field


MAX_PET_LEVEL = 100
MAX_EQUIPPED_SKILLS = 4


@dataclass(frozen=True)
class PetSkillDefinition:
    skill_id: str
    name: str
    description: str
    mp_cost: int
    target_type: str
    effect_type: str
    effect_value: int


@dataclass(frozen=True)
class SkillUnlock:
    level: int
    skill_id: str


@dataclass(frozen=True)
class PetSpecies:
    species_id: str
    name: str
    description: str
    base_hp: int
    hp_per_level: int
    base_mp: int
    mp_per_level: int
    base_attack: int
    attack_per_level: int
    base_defense: int
    defense_per_level: int
    speed: int
    starting_skills: tuple[str, ...]
    level_skills: tuple[SkillUnlock, ...]

    def max_hp(self, level: int) -> int:
        return self.base_hp + (level - 1) * self.hp_per_level

    def max_mp(self, level: int) -> int:
        return self.base_mp + (level - 1) * self.mp_per_level

    def attack(self, level: int) -> int:
        return self.base_attack + (level - 1) * self.attack_per_level

    def defense(self, level: int) -> int:
        return self.base_defense + (level - 1) * self.defense_per_level


@dataclass(frozen=True)
class PetSkillState:
    skill_id: str
    slot: int | None = None


@dataclass
class Pet:
    pet_id: str
    platform_id: str
    player_id: str
    species_id: str
    name: str
    level: int
    experience: int
    current_hp: int
    current_mp: int
    is_active: bool = False
    created_at: str = ""
    skills: list[PetSkillState] = field(default_factory=list)

    @classmethod
    def adopt(
        cls,
        pet_id: str,
        platform_id: str,
        player_id: str,
        species: PetSpecies,
    ) -> "Pet":
        return cls(
            pet_id=pet_id,
            platform_id=platform_id,
            player_id=player_id,
            species_id=species.species_id,
            name=species.name,
            level=1,
            experience=0,
            current_hp=species.base_hp,
            current_mp=species.base_mp,
            is_active=True,
            skills=[
                PetSkillState(skill_id=skill_id, slot=slot)
                for slot, skill_id in enumerate(species.starting_skills[:MAX_EQUIPPED_SKILLS], 1)
            ]
            + [
                PetSkillState(skill_id=skill_id)
                for skill_id in species.starting_skills[MAX_EQUIPPED_SKILLS:]
            ],
        )

    @property
    def equipped_skills(self) -> list[PetSkillState]:
        return sorted(
            (skill for skill in self.skills if skill.slot is not None),
            key=lambda skill: skill.slot or 0,
        )

    def gain_experience(self, amount: int, species: PetSpecies) -> list[str]:
        if amount <= 0:
            raise ValueError("经验必须为正整数")
        self.current_hp = min(max(self.current_hp, 0), species.max_hp(self.level))
        self.current_mp = min(max(self.current_mp, 0), species.max_mp(self.level))
        if self.level >= MAX_PET_LEVEL:
            self.experience = 0
            return []

        self.experience += amount
        learned = {skill.skill_id for skill in self.skills}
        unlocked: list[str] = []
        while self.level < MAX_PET_LEVEL and self.experience >= self.level * 100:
            self.experience -= self.level * 100
            self.level += 1
            self.current_hp = min(
                species.max_hp(self.level), self.current_hp + species.hp_per_level
            )
            self.current_mp = min(
                species.max_mp(self.level), self.current_mp + species.mp_per_level
            )
            for unlock in species.level_skills:
                if unlock.level == self.level and unlock.skill_id not in learned:
                    learned.add(unlock.skill_id)
                    unlocked.append(unlock.skill_id)
                    self.skills.append(PetSkillState(skill_id=unlock.skill_id))

        if self.level >= MAX_PET_LEVEL:
            self.experience = 0
        return unlocked

    def rename(self, new_name: str) -> None:
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("宠物昵称不能为空")
        if len(new_name) > 24:
            raise ValueError("宠物昵称不能超过 24 个字符")
        self.name = new_name


@dataclass(frozen=True)
class PetCatalog:
    species: dict[str, PetSpecies]
    skills: dict[str, PetSkillDefinition]
