import uuid

from ..domain.pet import Pet, PetCatalog, PetSpecies
from .ports.pet_repository import PetRepository


class PetService:
    def __init__(self, repository: PetRepository, catalog: PetCatalog):
        self.repository = repository
        self.catalog = catalog

    async def adopt(self, platform_id: str, player_id: str, species_id: str | None) -> str:
        if not species_id:
            return self._format_species_list()
        species = self.catalog.species.get(species_id) or next(
            (entry for entry in self.catalog.species.values() if entry.name == species_id),
            None,
        )
        if species is None:
            return f"没有找到名为「{species_id}」的宠物。\n{self._format_species_list()}"

        pet = Pet.adopt(
            pet_id=uuid.uuid4().hex,
            platform_id=platform_id,
            player_id=player_id,
            species=species,
        )
        if not await self.repository.adopt_initial_pet(pet):
            return "你已经领养过初始宠物了。使用 /我的宠物 查看。"
        return f"领养成功！{pet.name} 成为你的伙伴。\n{self._format_pet(pet, species)}"

    async def list_or_view(
        self, platform_id: str, player_id: str, pet_ref: str | None
    ) -> str:
        if pet_ref:
            pet, error = await self._find_pet(platform_id, player_id, pet_ref)
            if error:
                return error
            assert pet is not None
            species = self.catalog.species.get(pet.species_id)
            if species is None:
                return "这只宠物的种类数据已不可用，请联系管理员检查宠物资源。"
            return self._format_pet(pet, species)

        pets = await self.repository.list_pets(platform_id, player_id)
        if not pets:
            return f"你还没有宠物。发送 /领养宠物 查看可领养的伙伴。\n{self._format_species_list()}"
        rows = ["══════ 我的宠物 ══════"]
        for index, pet in enumerate(pets, 1):
            species = self.catalog.species.get(pet.species_id)
            species_name = species.name if species else pet.species_id
            active_label = "（当前宠物）" if pet.is_active else ""
            rows.append(
                f"宠物{index}：{pet.name} · {species_name} · 等级 {pet.level}{active_label}"
            )
        rows.append("发送 /我的宠物 宠物序号 查看属性和技能")
        return "\n".join(rows)

    async def rename(
        self, platform_id: str, player_id: str, pet_ref: str | None, name: str | None
    ) -> str:
        if not pet_ref or name is None:
            return "用法：/宠物改名 宠物序号 新昵称"
        pet, error = await self._find_pet(platform_id, player_id, pet_ref)
        if error:
            return error
        assert pet is not None
        try:
            pet.rename(name)
        except ValueError as exception:
            return f"{exception}。"
        await self.repository.rename_pet(platform_id, player_id, pet.pet_id, pet.name)
        return f"宠物昵称已修改为：{pet.name}"

    async def set_active(
        self, platform_id: str, player_id: str, pet_ref: str | None
    ) -> str:
        if not pet_ref:
            return "用法：/出战宠物 宠物序号"
        pet, error = await self._find_pet(platform_id, player_id, pet_ref)
        if error:
            return error
        assert pet is not None
        if pet.is_active:
            return f"{pet.name} 已经是你的当前宠物。"
        if not await self.repository.set_active_pet(platform_id, player_id, pet.pet_id):
            return f"没有找到序号为 {pet_ref} 的自己的宠物。"
        return f"已将 {pet.name} 设为当前宠物。"

    async def list_skills(
        self, platform_id: str, player_id: str, pet_ref: str | None
    ) -> str:
        pet, error = await self._find_pet(platform_id, player_id, pet_ref)
        if error:
            return error
        assert pet is not None
        if not pet.skills:
            return f"{pet.name} 还没有学会技能。"
        rows = [f"══════ {pet.name} 的技能 ══════"]
        for index, skill_state in enumerate(pet.skills, 1):
            skill = self.catalog.skills.get(skill_state.skill_id)
            if skill is None:
                continue
            combat_supported = (skill.target_type, skill.effect_type) in {
                ("single_enemy", "damage"), ("single_ally", "heal")
            }
            status = f"已装备·技能槽 {skill_state.slot}" if skill_state.slot else "已学会·未装备"
            if skill_state.slot and not combat_supported:
                status += "·暂不支持对战"
            rows.append(
                f"技能{index}：{skill.name}（{status}，消耗魔力 {skill.mp_cost}）\n"
                f"  {skill.description}"
            )
        rows.append("精灵对战可使用已装备的攻击或治疗技能；普通攻击使用 /精灵技能 普通攻击")
        rows.append("使用 /宠物技能装备 宠物序号 技能名称 进行装备")
        return "\n".join(rows)

    async def equip_skill(
        self,
        platform_id: str,
        player_id: str,
        pet_ref: str | None,
        skill_id: str | None,
    ) -> str:
        if not pet_ref or not skill_id:
            return "用法：/宠物技能装备 宠物序号 技能名称"
        skill_id = self._resolve_skill_id(skill_id)
        skill = self.catalog.skills.get(skill_id)
        if skill is None:
            return "没有找到该技能，请通过 /宠物技能 查看已学技能名称。"
        pet, error = await self._find_pet(platform_id, player_id, pet_ref)
        if error:
            return error
        assert pet is not None
        status, slot = await self.repository.equip_skill(
            platform_id, player_id, pet.pet_id, skill_id
        )
        if status == "not_learned":
            return f"{pet.name} 还没有学会 {skill.name}。"
        if status == "already_equipped":
            return f"{skill.name} 已装备在槽位 {slot}。"
        if status == "slots_full":
            return "技能槽已满，请先卸下一项技能。"
        return f"已将 {skill.name} 装备到 {pet.name} 的技能槽 {slot}。"

    async def unequip_skill(
        self,
        platform_id: str,
        player_id: str,
        pet_ref: str | None,
        skill_id: str | None,
    ) -> str:
        if not pet_ref or not skill_id:
            return "用法：/宠物技能卸下 宠物序号 技能名称"
        skill_id = self._resolve_skill_id(skill_id)
        pet, error = await self._find_pet(platform_id, player_id, pet_ref)
        if error:
            return error
        assert pet is not None
        status = await self.repository.unequip_skill(
            platform_id, player_id, pet.pet_id, skill_id
        )
        skill = self.catalog.skills.get(skill_id)
        skill_name = skill.name if skill else skill_id
        if status == "not_learned":
            return f"{pet.name} 还没有学会 {skill_name}。"
        if status == "not_equipped":
            return f"{skill_name} 当前没有装备。"
        return f"已从 {pet.name} 身上卸下 {skill_name}。"

    async def grant_experience(
        self, platform_id: str, player_id: str, pet_id: str, amount: int
    ) -> str:
        if amount <= 0:
            return "宠物经验必须为正整数。"
        pet, error = await self._find_pet(platform_id, player_id, pet_id)
        if error:
            return error
        assert pet is not None
        species = self.catalog.species.get(pet.species_id)
        if species is None:
            return "这只宠物的种类数据已不可用。"
        updated, unlocked = await self.repository.grant_experience(
            platform_id, player_id, pet.pet_id, amount, species
        )
        if updated is None:
            return "找不到这只宠物。"
        message = f"{updated.name} 获得 {amount} 点经验。"
        if updated.level > pet.level:
            message += f"\n等级提升至 {updated.level} 级！"
        unlocked_names = [
            self.catalog.skills[skill_id].name
            for skill_id in unlocked
            if skill_id in self.catalog.skills
        ]
        if unlocked_names:
            message += f"\n学会新技能：{'、'.join(unlocked_names)}"
        return message

    async def _find_pet(
        self, platform_id: str, player_id: str, pet_ref: str | None
    ) -> tuple[Pet | None, str | None]:
        if pet_ref is None or str(pet_ref).strip() == "":
            pets = await self.repository.list_pets(platform_id, player_id)
            pet = next((candidate for candidate in pets if candidate.is_active), None)
            if pet is None:
                return None, "你还没有当前宠物。使用 /我的宠物 查看，或先发送 /领养宠物。"
            return pet, None

        pet_ref = str(pet_ref).strip()
        pets = await self.repository.list_pets(platform_id, player_id)
        if pet_ref.isdecimal():
            index = int(pet_ref)
            if 1 <= index <= len(pets):
                return pets[index - 1], None
        matches = [pet for pet in pets if pet.pet_id.startswith(pet_ref)]
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, "宠物序号不唯一，请使用我的宠物列表中的序号。"
        return None, f"没有找到序号为 {pet_ref} 的自己的宠物。"

    def _resolve_skill_id(self, skill_ref: str) -> str:
        value = skill_ref.strip()
        if value in self.catalog.skills:
            return value
        return next(
            (skill_id for skill_id, skill in self.catalog.skills.items() if skill.name == value),
            value,
        )

    def _format_species_list(self) -> str:
        rows = ["可领养的初始宠物（免费）："]
        for species in self.catalog.species.values():
            rows.append(
                f"{species.name} —— "
                f"生命 {species.base_hp} / 魔力 {species.base_mp} / 攻击 {species.base_attack} / "
                f"防御 {species.base_defense} / 速度 {species.speed} —— {species.description}"
            )
        rows.append("使用 /领养宠物 宠物名称 选择一只")
        return "\n".join(rows)

    def _format_pet(self, pet: Pet, species: PetSpecies) -> str:
        max_hp = species.max_hp(pet.level)
        max_mp = species.max_mp(pet.level)
        current_hp = min(max(pet.current_hp, 0), max_hp)
        current_mp = min(max(pet.current_mp, 0), max_mp)
        next_exp = pet.level * 100 if pet.level < 100 else None
        exp_display = f"{pet.experience}/{next_exp}" if next_exp else "已达最高等级"
        status = "当前宠物" if pet.is_active else "休息中"
        rows = [
            f"══════ {pet.name} ══════",
            f"种类：{species.name}（{species.description}）",
            f"等级：{pet.level}（经验 {exp_display}）",
            f"生命：{current_hp}/{max_hp}",
            f"魔力：{current_mp}/{max_mp}",
            f"攻击：{species.attack(pet.level)} · 防御：{species.defense(pet.level)} · 速度：{species.speed}",
            f"状态：{status}",
        ]
        if pet.skills:
            skill_names = []
            for skill_state in pet.skills:
                skill = self.catalog.skills.get(skill_state.skill_id)
                if skill:
                    equip_label = f"槽位 {skill_state.slot}" if skill_state.slot else "未装备"
                    skill_names.append(f"{skill.name}（{equip_label}）")
            rows.append(f"技能：{'、'.join(skill_names) if skill_names else '暂无'}")
        else:
            rows.append("技能：暂无")
        return "\n".join(rows)
