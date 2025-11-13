from astrbot.core.platform import AstrMessageEvent
from faiss.contrib.datasets import username

from ..utils.user_manager import udm


class UserHandle:
    def __init__(self):
        pass

    async def register(self, event: AstrMessageEvent):
        username = event.get_sender_name()
        with udm.user_session(event.get_sender_id()) as user_data:
            user_data["name"] = username
            user_data["level"] = 1
            user_data["stats"] = {
                "HP": 140,
                "MP": 80,
            }
        await event.send(event.plain_result(f"大地之母正在聚集魔力为你铸造身躯...\n欢迎你，{username}"))

    async def status(self, event: AstrMessageEvent):
        username = event.get_sender_name()
        with udm.user_session(event.get_sender_id()) as user_data:
            stats = user_data.get("stats", {})
            await event.send(event.plain_result(f"{username}の状态面板：\n"
                                                f"👑Level：{stats.get('level', 1)}"
                                                f"🩸HP: {stats.get('HP', 0)}\n"
                                                f"💧MP: {stats.get('MP', 0)}"))
