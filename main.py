from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

from .core.sign_handle import SignHandle
from .config import config_load
from .utils.user_manager import udm

@register(
    "琉璃",
    "夏源",
    "来自异世界的娱乐插件",
    "0.0.1",
    "https://github.com/xiayuanOvO/astrbot_plugin_liuli"
)
class MyPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.cfg = config

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        config_load()
        self.sign = SignHandle()

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        pass

    @filter.command("hi")
    async def reg(self, event: AstrMessageEvent):
        if not event.is_admin():
            return

        user_name = event.get_sender_name()
        platform_name = event.get_platform_name()
        message_str = event.message_str  # 用户发的纯文本消息字符串
        message_chain = event.get_messages()  # 用户所发的消息的消息链 # from astrbot.api.message_components import *
        logger.info(message_chain)
        yield event.plain_result(f"Hello, {user_name}, {platform_name} 你发了 {message_str}!")

    @filter.command("注册")
    async def sign(self, event: AstrMessageEvent):
        username = event.get_sender_name()
        with udm.user_session(event.get_sender_id()) as user_data:
            user_data["name"] = username
            user_data["level"] = 1
            user_data["stats"]['HP'] = 140
            user_data["stats"]['MP'] = 80
        yield event.plain_result(f"大地之母正在聚集魔力为你铸造身躯...\n欢迎你，{username}")
