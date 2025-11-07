from tortoise import Tortoise

async def init_db():
    """初始化数据库连接
    
    使用Tortoise ORM连接SQLite数据库并生成表结构
    """
    # 使用Tortoise.init_db()替代Tortoise.init()
    await Tortoise.init_db(
        "sqlite://liuli.db",
        modules={"models": ["models"]},
        generate_schemas=True
    )
