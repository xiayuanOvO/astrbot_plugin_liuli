from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core import AstrBotConfig
from astrbot.core.star import StarTools

from .config import config_load

from .utils.user_manager import udm
from .core.user_handle import UserHandle
from .core.sign_handle import SignHandle
from .core.guild_handle import GuildHandle


@register(
    "琉璃",
    "夏源",
    "来自异世界的娱乐插件",
    "0.0.1",
    "https://github.com/xiayuanOvO/astrbot_plugin_liuli"
)
class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.cfg = config
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_liuli")

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        udm.set_plugin_dir(self.data_dir)
        config_load(self.data_dir)
        self.sign = SignHandle()
        self.user = UserHandle()
        self.guild = GuildHandle(self.cfg)

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        pass

    @filter.command("注册")
    async def register(self, event: AstrMessageEvent):
        await self.user.register(event)

    @filter.command("状态")
    async def status(self, event: AstrMessageEvent):
        await self.user.status(event)

    @filter.command("公会", alias={"gh"})
    async def _(self, event: AstrMessageEvent):
        await self.guild.guild(event)

    @filter.command("注册冒险者", alias={"zcmxz"})
    async def register_adventurer(self, event: AstrMessageEvent):
        await self.guild.register(event)

    @filter.command("查看委托", alias={"ckwt"})
    async def view_quest(self, event: AstrMessageEvent, quest_id: str = None):
        await self.guild.view_quest(event, quest_id)
