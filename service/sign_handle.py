from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult


class SignHandle:
    def __init__(self):
        pass

    async def signin(self, event):
        pass


@filter.command("ii")
async def signin(event: AstrMessageEvent):
    print(event)
    yield event.plain_result("签到成功")
