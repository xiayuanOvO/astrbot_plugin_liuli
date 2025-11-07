from tortoise import Tortoise

async def init_db():
    """初始化数据库连接
    
    使用Tortoise ORM连接SQLite数据库并生成表结构
    
    Returns:
        None
    """
    # 在tortoise-orm 0.25.1版本中，正确的初始化方式
    await Tortoise.init(
        db_url="sqlite://liuli.db",
        modules={"models": ["models"]}
    )
    # 单独调用生成表结构的方法
    await Tortoise.generate_schemas()
