from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult


@filter.command("sign")
async def signin(event: AstrMessageEvent):
    print(event)
    yield event.plain_result("签到成功")
