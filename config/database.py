from tortoise import Tortoise

async def init_db():
    """
    初始化数据库连接
    1
    """
    await Tortoise.init_db(
        "sqlite://liuli.db",
        modules={"models": ["models"]},
    )
    await Tortoise.generate_schemas()
