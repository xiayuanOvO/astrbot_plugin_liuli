from tortoise import Tortoise

async def init_db():
    await Tortoise.init(
        db_url="sqlite://liuli.db",
        modules={"models": ["models"]},
    )
    await Tortoise.generate_schemas()
