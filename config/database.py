from tortoise import Tortoise


async def init_db():
    """
    初始化数据库连接
    """
    await Tortoise.init(
        db_url="sqlite://liuli.db",
        modules={"models": ["models"]},
    )
    await Tortoise.generate_schemas()
