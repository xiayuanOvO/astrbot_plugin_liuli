import asyncio
import time

from astrbot.core import AstrBotConfig, logger
from astrbot.core.platform import AstrMessageEvent
from openpyxl.styles.builtins import title

from ..config import config_get
from ..utils.user_manager import udm

_LEVEL = ["S", "A", "B", "C", "D", "E", "F"]
# 任务刷新时间
TASK_SLEEP_TIME = 10


# 委托列表
# {
#     "1": {title: "清理魔物", "level": "A", "coin": 10}
# }

class GuildHandle:
    def __init__(self, cfg: AstrBotConfig):
        self._quest_list: dict = {}
        self._refresh_task = asyncio.create_task(self.refresh_task(cfg))

    def close(self):
        self._refresh_task.cancel()

    async def refresh_task(self, cfg: AstrBotConfig):
        while True:
            try:
                logger.info('执行一次.refresh_task')
                await self.refresh_quest(cfg)
            except Exception as e:
                logger.error(e)
            finally:
                await asyncio.sleep(TASK_SLEEP_TIME)

    async def refresh_quest(self, cfg: AstrBotConfig):
        now_timestamp = int(time.time())
        last_timestamp = config_get("guild.lastReflashTimes", 100000)

        logger.info(f'{cfg.get('guild')}')

        # 获取委托刷新周期
        if now_timestamp - last_timestamp > cfg.get("guild.questReflashTimes"):
            logger.info("刷新委托列表")

    async def guild(self, event: AstrMessageEvent):
        text = (f"欢迎来到冒险者工会，{event.get_sender_name()}~\n"
                f"要做点什么呢？\n"
                f"════════════════")

        with udm.user_session(event.get_sender_id(), "guild") as user_data:
            level = user_data.get("level", 0)
            if level < 1:
                text += "/注册冒险者"
            else:
                text += ("/查看委托\n"
                         "/接取委托")

        await event.send(event.plain_result(text))

    async def register(self, event: AstrMessageEvent):
        """
        注册冒险者工会
        """
        level = "F"
        with udm.user_session(event.get_sender_id(), "guild") as user_data:
            user_data["level"] = level
        await event.send(event.plain_result("正在评估您的实力...\n"
                                            "\n\n"
                                            "冒险者注册成功！\n"
                                            f"根据您的实力，您的冒险者等级为：{level}"))

    async def view_quest(self, event: AstrMessageEvent, delegate_id: str):
        """
        查看委托
        """
        text = "══════ 委托 ══════\n"
        if delegate_id is None:
            text += "1 清理魔物 —— A级 —— 10银币"
        else:
            text += self._quest_list[delegate_id]
        await event.send(event.plain_result(text))

    async def accept_quest(self, event: AstrMessageEvent, delegate_id: str):
        """接取委托"""
        pass
