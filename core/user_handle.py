from astrbot.core.platform import AstrMessageEvent

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
        yield event.plain_result(f"大地之母正在聚集魔力为你铸造身躯...\n欢迎你，{username}")
