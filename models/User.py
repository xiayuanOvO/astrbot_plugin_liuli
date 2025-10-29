from tortoise import fields, models

class User(models.Model):
    id = fields.IntField(pk=True)
    user_id = fields.BigIntField(unique=True)
    name = fields.TextField(null=True)
    coins = fields.IntField(default=0)

    class Meta:
        table = "astrbot_user"
