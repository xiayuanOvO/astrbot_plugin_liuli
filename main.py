from datetime import datetime
import json
import random
import re
from zoneinfo import ZoneInfo

from astrbot import logger
from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
import astrbot.api.message_components as Comp
from astrbot.api.star import Context, Star, StarTools, register

from .liuli.application.currency_service import CurrencyService
from .liuli.application.dungeon_service import DungeonService
from .liuli.application.guild_service import GuildService
from .liuli.application.player_service import PlayerService
from .liuli.application.pet_service import PetService
from .liuli.application.spirit_battle_service import SpiritBattleService
from .liuli.application.quest_service import QuestService
from .liuli.domain.currency import CurrencySettings, DEFAULT_WEEKLY_REWARDS, WEEKDAY_KEYS
from .liuli.domain.player import PlayerProfile
from .liuli.infrastructure.persistence.sqlite.currency_repository import SQLiteCurrencyRepository
from .liuli.infrastructure.persistence.sqlite.dungeon_repository import SQLiteDungeonRepository
from .liuli.infrastructure.persistence.sqlite.database import SQLiteDatabase
from .liuli.infrastructure.persistence.sqlite.profile_repository import SQLiteProfileRepository
from .liuli.infrastructure.persistence.sqlite.pet_repository import SQLitePetRepository
from .liuli.infrastructure.persistence.sqlite.spirit_battle_repository import SQLiteSpiritBattleRepository
from .liuli.infrastructure.pets.catalog_loader import load_pet_catalog
from .liuli.infrastructure.world.catalog_loader import load_world_catalog


_ACTIVE_LIULI_PLUGIN = None


@register(
    "琉璃",
    "夏源",
    "来自异世界的娱乐插件",
    "0.1.0",
    "https://github.com/xiayuanOvO/astrbot_plugin_liuli",
)
class LiuliPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_liuli")
        self.database: SQLiteDatabase | None = None
        self.config = config
        self._qq_buttons_enabled = False

    async def initialize(self) -> None:
        self._qq_buttons_enabled = self._install_qq_button_callbacks()
        self.database = SQLiteDatabase(self.data_dir)
        await self.database.initialize()
        repository = SQLiteProfileRepository(self.database)
        currency_repository = SQLiteCurrencyRepository(self.database)
        self.players = PlayerService(repository)
        self.guild = GuildService(repository)
        self.quests = QuestService(repository)
        self.currency = CurrencyService(currency_repository, self._currency_settings())
        catalog = load_pet_catalog()
        self.pets = PetService(SQLitePetRepository(self.database), catalog)
        world = load_world_catalog(catalog)
        self.dungeons = DungeonService(
            SQLiteDungeonRepository(self.database), world, catalog,
            self.currency.settings.name,
        )
        self.spirit_battles = SpiritBattleService(
            SQLiteSpiritBattleRepository(self.database, catalog), catalog
        )

    def _install_qq_button_callbacks(self) -> bool:
        global _ACTIVE_LIULI_PLUGIN
        _ACTIVE_LIULI_PLUGIN = self
        try:
            from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
                QQOfficialPlatformAdapter,
                botClient,
            )
        except ImportError:
            logger.warning("琉璃：无法加载 QQ 官方机器人按钮接口，战斗按钮将不可用。")
            return False

        adapter_init = QQOfficialPlatformAdapter.__init__
        if not getattr(adapter_init, "_liuli_button_patch", False):
            original_init = adapter_init

            def init_with_button_intent(adapter, *args, **kwargs):
                original_init(adapter, *args, **kwargs)
                adapter.intents.interaction = True
                adapter.client.intents = adapter.intents.value
                plugin = _ACTIVE_LIULI_PLUGIN
                if plugin is not None:
                    adapter._liuli_plugin = plugin

            init_with_button_intent._liuli_button_patch = True
            QQOfficialPlatformAdapter.__init__ = init_with_button_intent

        interaction_handler = getattr(botClient, "on_interaction_create", None)
        if not getattr(interaction_handler, "_liuli_button_patch", False):
            original_handler = interaction_handler

            async def on_interaction_create(client, interaction):
                platform = getattr(client, "platform", None)
                plugin = getattr(platform, "_liuli_plugin", None)
                if plugin is not None:
                    handled = await plugin._handle_qq_battle_interaction(client, interaction)
                    if handled:
                        return
                if original_handler is not None:
                    await original_handler(client, interaction)

            on_interaction_create._liuli_button_patch = True
            botClient.on_interaction_create = on_interaction_create

        # AstrBot 在插件热重载时平台可能已经连接；新实例先接管回调，
        # 重新协商互动事件权限仍需重启平台连接。
        for adapter in self.context.platform_manager.get_insts():
            if isinstance(adapter, QQOfficialPlatformAdapter):
                adapter._liuli_plugin = self
                adapter.intents.interaction = True
                adapter.client.intents = adapter.intents.value
        return True

    async def _handle_qq_battle_interaction(self, client, interaction) -> bool:
        resolved = getattr(getattr(interaction, "data", None), "resolved", None)
        button_data = getattr(resolved, "button_data", None)
        if not isinstance(button_data, str) or not button_data.startswith("liuli:"):
            return False

        try:
            payload = json.loads(button_data.removeprefix("liuli:"))
        except (TypeError, ValueError):
            await client.api.on_interaction_result(
                str(getattr(interaction, "id", None) or getattr(interaction, "event_id", "")), 1
            )
            return True

        interaction_id = getattr(interaction, "id", None) or getattr(interaction, "event_id", None)
        if interaction_id:
            # QQ 要求尽快确认点击事件；战斗结算和消息回复随后执行。
            try:
                await client.api.on_interaction_result(str(interaction_id), 0)
            except Exception:
                logger.exception("琉璃：确认 QQ 战斗按钮事件失败，仍将尝试处理操作。")

        player_id = str(
            getattr(interaction, "group_member_openid", None)
            or getattr(interaction, "user_openid", None)
            or getattr(resolved, "user_id", None)
            or ""
        )
        group_id = str(getattr(interaction, "group_openid", None) or "")
        channel_id = str(getattr(interaction, "channel_id", None) or "")
        user_openid = str(getattr(interaction, "user_openid", None) or "")
        context_id = group_id or channel_id or user_openid
        owner_id = str(payload.get("player_id", ""))
        if not player_id or player_id != owner_id or not context_id or context_id != str(payload.get("context_id", "")):
            await self._reply_to_qq_interaction(
                client, interaction, "这个战斗按钮不属于你当前的对战。", [], owner_id, context_id
            )
            return True

        action = payload.get("action")
        button_token = payload.get("button_token")
        if not isinstance(button_token, str) or not button_token:
            await self._reply_to_qq_interaction(
                client, interaction, "这个战斗按钮已失效，请使用最新的战斗消息。", [], player_id, context_id
            )
            return True
        if action == "defend":
            skill_id = None
        elif action == "skill":
            skill_id = payload.get("skill_id")
            if not isinstance(skill_id, str):
                await self._reply_to_qq_interaction(
                    client, interaction, "这个技能按钮无效，请使用最新的战斗消息。", [], player_id, context_id
                )
                return True
        else:
            return True

        platform_id = client.platform.meta().name
        request_key = f"qq_button:{interaction_id}" if interaction_id else None
        try:
            message = await self.dungeons.act(
                platform_id,
                player_id,
                action or "skill",
                skill_id,
                request_key,
                button_token,
            )
            actions = await self.dungeons.battle_actions(platform_id, player_id)
            await self._reply_to_qq_interaction(
                client, interaction, message, actions, player_id, context_id
            )
        except Exception:
            logger.exception("琉璃：处理 QQ 战斗按钮时发生错误。")
            await self._reply_to_qq_interaction(
                client, interaction, "战斗操作暂时失败，请发送 /副本状态 查看最新进度。", [], player_id, context_id
            )
        return True

    async def _reply_to_qq_interaction(
        self, client, interaction, message: str, actions: list[dict],
        player_id: str, context_id: str,
    ) -> None:
        resolved = getattr(getattr(interaction, "data", None), "resolved", None)
        message_id = getattr(resolved, "message_id", None)
        group_id = getattr(interaction, "group_openid", None)
        channel_id = getattr(interaction, "channel_id", None)
        user_openid = getattr(interaction, "user_openid", None)
        keyboard = self._qq_battle_keyboard(actions, player_id, context_id) if actions else None
        if group_id:
            await client.api.post_group_message(
                group_openid=str(group_id),
                msg_type=2,
                markdown={"content": message},
                keyboard=keyboard,
                msg_id=str(message_id) if message_id else None,
                msg_seq=random.randint(1, 10000),
            )
        elif channel_id:
            await client.api.post_message(
                channel_id=str(channel_id),
                markdown={"content": message},
                keyboard=keyboard,
                msg_id=str(message_id) if message_id else None,
                event_id=str(getattr(interaction, "event_id", "") or "") or None,
            )
        elif user_openid:
            interaction_id = getattr(interaction, "id", None) or getattr(interaction, "event_id", None)
            await client.api.post_c2c_message(
                openid=str(user_openid),
                msg_type=2,
                markdown={"content": message},
                keyboard=keyboard,
                event_id=str(interaction_id) if interaction_id else None,
            )

    @staticmethod
    def _qq_battle_keyboard(
        actions: list[dict], player_id: str, context_id: str,
    ) -> dict:
        buttons = []
        for index, item in enumerate(actions, 1):
            name = str(item.get("name", "技能"))
            payload = {
                "player_id": player_id,
                "context_id": context_id,
                "action": item.get("action"),
                "skill_id": item.get("skill_id"),
                "button_token": item.get("button_token"),
            }
            buttons.append({
                "id": f"liuli_{index}_{random.randint(1000, 9999)}",
                "render_data": {"label": name, "visited_label": name, "style": 1},
                "action": {
                    "type": 1,
                    "permission": {"type": 2},
                    "unsupport_tips": "当前 QQ 版本暂不支持此按钮，请发送副本状态查看进度。",
                    "data": "liuli:" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                },
            })
        rows = [
            {"buttons": buttons[start:start + 5]}
            for start in range(0, len(buttons), 5)
        ]
        return {"content": {"rows": rows}}

    async def _send_dungeon_result_with_buttons(
        self, event: AstrMessageEvent, message: str,
    ) -> bool:
        if not self._qq_buttons_enabled or event.get_platform_name() != "qq_official":
            return False
        platform_id, player_id = self._identity(event)
        actions = await self.dungeons.battle_actions(platform_id, player_id)
        if not actions:
            return False
        source = getattr(getattr(event, "message_obj", None), "raw_message", None)
        api = getattr(source, "_api", None)
        group_id = getattr(source, "group_openid", None)
        channel_id = getattr(source, "channel_id", None)
        user_openid = getattr(getattr(source, "author", None), "user_openid", None)
        context_id = str(group_id or channel_id or user_openid or "")
        if api is None or not context_id:
            return False
        try:
            await self._send_qq_battle_message(
                api, source, message, actions, player_id, context_id
            )
            event.stop_event()
            return True
        except Exception:
            logger.exception("琉璃：发送 QQ 战斗按钮失败，将改用普通消息。")
            return False

    async def _send_qq_battle_message(
        self, api, source, message: str, actions: list[dict],
        player_id: str, context_id: str,
    ) -> None:
        keyboard = self._qq_battle_keyboard(actions, player_id, context_id)
        message_id = getattr(source, "id", None)
        if getattr(source, "group_openid", None):
            await api.post_group_message(
                group_openid=str(source.group_openid),
                msg_type=2,
                markdown={"content": message},
                keyboard=keyboard,
                msg_id=str(message_id) if message_id else None,
                msg_seq=random.randint(1, 10000),
            )
        elif getattr(source, "channel_id", None):
            await api.post_message(
                channel_id=str(source.channel_id),
                markdown={"content": message},
                keyboard=keyboard,
                msg_id=str(message_id) if message_id else None,
                event_id=str(getattr(source, "event_id", "") or "") or None,
            )
        else:
            user_openid = getattr(getattr(source, "author", None), "user_openid", None)
            if not user_openid:
                raise ValueError("QQ 单聊消息缺少用户标识，无法发送战斗按钮。")
            await api.post_c2c_message(
                openid=str(user_openid),
                msg_type=2,
                markdown={"content": message},
                keyboard=keyboard,
                msg_id=str(message_id) if message_id else None,
                msg_seq=random.randint(1, 10000),
            )

    def _currency_settings(self) -> CurrencySettings:
        name = str(self.config.get("currency_name", "银币") or "").strip() or "银币"
        rewards = []
        for key, default in zip(WEEKDAY_KEYS, DEFAULT_WEEKLY_REWARDS):
            try:
                reward = int(self.config.get(key, default))
            except (TypeError, ValueError):
                reward = default
            rewards.append(reward if 0 < reward <= 10000 else default)
        return CurrencySettings(name=name, weekly_rewards=tuple(rewards))

    async def terminate(self) -> None:
        global _ACTIVE_LIULI_PLUGIN
        if _ACTIVE_LIULI_PLUGIN is self:
            _ACTIVE_LIULI_PLUGIN = None
        if self.database:
            await self.database.close()
            self.database = None

    @staticmethod
    def _identity(event: AstrMessageEvent) -> tuple[str, str]:
        return event.get_platform_name(), event.get_sender_id()

    @staticmethod
    def _group_id(event: AstrMessageEvent) -> str | None:
        group_id = event.get_group_id()
        return str(group_id) if group_id else None

    @staticmethod
    def _mentioned_user_id(event: AstrMessageEvent) -> str | None:
        mentioned_ids = []
        self_id = str(event.get_self_id())
        for component in event.get_messages():
            if not isinstance(component, Comp.At):
                continue
            target_getter = getattr(component, "target_id", None)
            candidates = [target_getter() if callable(target_getter) else None,
                          getattr(component, "id", None), getattr(component, "qq", None)]
            for target_id in candidates:
                target_id = str(target_id).strip() if target_id is not None else ""
                if target_id and target_id != "0":
                    mentioned_ids.append(target_id)
        return next((target_id for target_id in mentioned_ids if target_id != self_id), None) or (
            mentioned_ids[0] if mentioned_ids else None
        )

    def _battle_group_or_message(self, event: AstrMessageEvent) -> str | None:
        group_id = self._group_id(event)
        return group_id

    async def _ensure_player(self, event: AstrMessageEvent) -> PlayerProfile:
        platform, sender_id = self._identity(event)
        return await self.players.ensure_initialized(platform, sender_id, event.get_sender_name())

    @staticmethod
    def _dungeon_result(event: AstrMessageEvent, message: str):
        if event.get_platform_name() in {"qq_official", "qq_official_webhook"}:
            return event.plain_result(message).use_markdown(True)
        plain = re.sub(r"^#{1,6}\s*|^>\s*|\*\*(.*?)\*\*|`([^`]*)`", lambda match: match.group(1) or match.group(2) or "", message, flags=re.MULTILINE)
        return event.plain_result(plain)

    @filter.command("状态")
    async def player_status(self, event: AstrMessageEvent):
        profile = await self._ensure_player(event)
        yield event.plain_result(self.players.status(profile, event.get_sender_name()))

    @filter.command("改名")
    async def rename_player(self, event: AstrMessageEvent, nickname: str | None = None):
        await self._ensure_player(event)
        if nickname is None:
            yield event.plain_result("用法：/改名 昵称")
            return
        platform, sender_id = self._identity(event)
        yield event.plain_result(await self.players.rename(platform, sender_id, nickname))

    @filter.command("公会", alias={"gh"})
    async def guild_home(self, event: AstrMessageEvent):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        message = await self.guild.home(platform, sender_id, event.get_sender_name())
        yield event.plain_result(message)

    @filter.command("注册冒险者", alias={"zcmxz"})
    async def register_adventurer(self, event: AstrMessageEvent):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        message = await self.guild.register_adventurer(platform, sender_id)
        yield event.plain_result(message)

    @filter.command("查看委托", alias={"ckwt"})
    async def view_quest(self, event: AstrMessageEvent, quest_id: str | None = None):
        await self._ensure_player(event)
        message = self.quests.view_quest(quest_id)
        yield event.plain_result(message)

    @filter.command("接取委托", alias={"jqwt"})
    async def accept_quest(self, event: AstrMessageEvent, quest_id: str | None = None):
        await self._ensure_player(event)
        if not quest_id:
            yield event.plain_result("请提供委托编号，例如：/接取委托 1")
            return
        platform, sender_id = self._identity(event)
        message = await self.quests.accept_quest(platform, sender_id, quest_id)
        yield event.plain_result(message)

    @filter.command("余额")
    async def currency_balance(self, event: AstrMessageEvent):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        yield event.plain_result(await self.currency.balance(platform, sender_id))

    @filter.command("签到")
    async def daily_sign_in(self, event: AstrMessageEvent):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        yield event.plain_result(await self.currency.sign_in(platform, sender_id, today))

    @filter.command("消费")
    async def spend_currency(self, event: AstrMessageEvent, amount: str | None = None):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        yield event.plain_result(await self.currency.spend(platform, sender_id, amount))

    @filter.command("领养宠物")
    async def adopt_pet(self, event: AstrMessageEvent, species_id: str | None = None):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        yield event.plain_result(await self.pets.adopt(platform, sender_id, species_id))

    @filter.command("我的宠物")
    async def my_pets(self, event: AstrMessageEvent, pet_id: str | None = None):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        yield event.plain_result(await self.pets.list_or_view(platform, sender_id, pet_id))

    @filter.command("宠物改名")
    async def rename_pet(
        self,
        event: AstrMessageEvent,
        pet_id: str | None = None,
        nickname: str | None = None,
    ):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        yield event.plain_result(
            await self.pets.rename(platform, sender_id, pet_id, nickname)
        )

    @filter.command("出战宠物")
    async def set_active_pet(self, event: AstrMessageEvent, pet_id: str | None = None):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        if await self.dungeons.has_active_run(platform, sender_id):
            yield event.plain_result("副本探索期间不能更换出战宠物，请先完成或退出副本。")
            return
        yield event.plain_result(await self.pets.set_active(platform, sender_id, pet_id))

    @filter.command("世界地图")
    async def dungeon_world_map(self, event: AstrMessageEvent):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        yield self._dungeon_result(event, await self.dungeons.world_map(platform, sender_id))

    @filter.command("国家")
    async def dungeon_country(self, event: AstrMessageEvent, country_id: str | None = None):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        yield self._dungeon_result(event, await self.dungeons.country_info(platform, sender_id, country_id))

    @filter.command("城市")
    async def dungeon_city(self, event: AstrMessageEvent, city_id: str | None = None):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        yield self._dungeon_result(event, await self.dungeons.city_info(platform, sender_id, city_id))

    @filter.command("副本")
    async def dungeon_info(self, event: AstrMessageEvent, dungeon_id: str | None = None):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        yield self._dungeon_result(event, await self.dungeons.dungeon_info(platform, sender_id, dungeon_id))

    @filter.command("进入副本")
    async def enter_dungeon(
        self, event: AstrMessageEvent, dungeon_id: str | None = None,
        difficulty_id: str | None = None,
    ):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        yield self._dungeon_result(event,
            await self.dungeons.start(platform, sender_id, dungeon_id, difficulty_id)
        )

    @filter.command("探索副本")
    async def explore_dungeon(self, event: AstrMessageEvent):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        message = await self.dungeons.explore(platform, sender_id)
        if await self._send_dungeon_result_with_buttons(event, message):
            return
        yield self._dungeon_result(event, message)

    @filter.command("副本选择")
    async def choose_dungeon_event(self, event: AstrMessageEvent, option_id: str | None = None):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        message = await self.dungeons.choose(platform, sender_id, option_id)
        if await self._send_dungeon_result_with_buttons(event, message):
            return
        yield self._dungeon_result(event, message)

    @filter.command("副本状态")
    async def dungeon_status(self, event: AstrMessageEvent):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        message = await self.dungeons.status(platform, sender_id)
        if await self._send_dungeon_result_with_buttons(event, message):
            return
        yield self._dungeon_result(event, message)

    @filter.command("退出副本")
    async def retreat_dungeon(self, event: AstrMessageEvent):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        yield self._dungeon_result(event, await self.dungeons.retreat(platform, sender_id))

    @filter.command("宠物休息")
    async def rest_pet(self, event: AstrMessageEvent):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        yield self._dungeon_result(event, await self.dungeons.rest(platform, sender_id))

    @filter.command("宠物技能")
    async def view_pet_skills(self, event: AstrMessageEvent, pet_id: str | None = None):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        yield event.plain_result(await self.pets.list_skills(platform, sender_id, pet_id))

    @filter.command("宠物技能装备")
    async def equip_pet_skill(
        self,
        event: AstrMessageEvent,
        pet_id: str | None = None,
        skill_id: str | None = None,
    ):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        yield event.plain_result(
            await self.pets.equip_skill(platform, sender_id, pet_id, skill_id)
        )

    @filter.command("宠物技能卸下")
    async def unequip_pet_skill(
        self,
        event: AstrMessageEvent,
        pet_id: str | None = None,
        skill_id: str | None = None,
    ):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        yield event.plain_result(
            await self.pets.unequip_skill(platform, sender_id, pet_id, skill_id)
        )

    @filter.command("精灵对战")
    async def challenge_spirit(
        self, event: AstrMessageEvent, mention_hint: str | None = None
    ):
        group_id = self._battle_group_or_message(event)
        if group_id is None:
            yield event.plain_result("请在群聊中发起精灵对战。")
            return
        await self._ensure_player(event)
        target_id = self._mentioned_user_id(event)
        if target_id is None:
            yield event.plain_result("用法：/精灵对战 @玩家")
            return
        if target_id == str(event.get_self_id()):
            yield event.plain_result("不能向机器人发起精灵对战。")
            return
        platform, sender_id = self._identity(event)
        yield event.plain_result(
            await self.spirit_battles.challenge(platform, group_id, sender_id, target_id)
        )

    @filter.command("接受对战")
    async def accept_spirit_battle(self, event: AstrMessageEvent):
        group_id = self._battle_group_or_message(event)
        if group_id is None:
            yield event.plain_result("请在群聊中接受精灵对战。")
            return
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        yield event.plain_result(await self.spirit_battles.accept(platform, group_id, sender_id))

    @filter.command("拒绝对战")
    async def decline_spirit_battle(self, event: AstrMessageEvent):
        group_id = self._battle_group_or_message(event)
        if group_id is None:
            yield event.plain_result("请在群聊中拒绝精灵对战。")
            return
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        yield event.plain_result(await self.spirit_battles.decline(platform, group_id, sender_id))

    @filter.command("对战状态")
    async def spirit_battle_status(self, event: AstrMessageEvent):
        if self._battle_group_or_message(event) is None:
            yield event.plain_result("请在群聊中查看精灵对战状态。")
            return
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        group_id = self._group_id(event)
        assert group_id is not None
        yield event.plain_result(
            await self.spirit_battles.battle_status(platform, group_id, sender_id)
        )

    @filter.command("精灵技能")
    async def spirit_battle_skill(self, event: AstrMessageEvent, skill_id: str | None = None):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        if await self.dungeons.is_in_battle(platform, sender_id):
            message_id = getattr(getattr(event, "message_obj", None), "message_id", None)
            request_key = None
            if message_id is not None:
                request_key = ":".join((platform, sender_id, str(self._group_id(event) or "private"), str(message_id)))
            message = await self.dungeons.act(platform, sender_id, "skill", skill_id, request_key)
            if await self._send_dungeon_result_with_buttons(event, message):
                return
            yield self._dungeon_result(event, message)
            return
        group_id = self._battle_group_or_message(event)
        if group_id is None:
            yield event.plain_result("请在群聊中使用精灵对战技能。")
            return
        yield event.plain_result(
            await self.spirit_battles.skill(platform, group_id, sender_id, skill_id)
        )

    @filter.command("精灵防御")
    async def spirit_battle_defend(self, event: AstrMessageEvent):
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        if await self.dungeons.is_in_battle(platform, sender_id):
            message_id = getattr(getattr(event, "message_obj", None), "message_id", None)
            request_key = None
            if message_id is not None:
                request_key = ":".join((platform, sender_id, str(self._group_id(event) or "private"), str(message_id)))
            message = await self.dungeons.act(platform, sender_id, "defend", None, request_key)
            if await self._send_dungeon_result_with_buttons(event, message):
                return
            yield self._dungeon_result(event, message)
            return
        group_id = self._battle_group_or_message(event)
        if group_id is None:
            yield event.plain_result("请在群聊中使用精灵对战防御。")
            return
        yield event.plain_result(await self.spirit_battles.defend(platform, group_id, sender_id))

    @filter.command("精灵认输")
    async def forfeit_spirit_battle(self, event: AstrMessageEvent):
        group_id = self._battle_group_or_message(event)
        if group_id is None:
            yield event.plain_result("请在群聊中认输。")
            return
        await self._ensure_player(event)
        platform, sender_id = self._identity(event)
        yield event.plain_result(await self.spirit_battles.forfeit(platform, group_id, sender_id))
