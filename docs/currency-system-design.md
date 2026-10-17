# 货币系统设计

## 目标

- 后台可修改玩家看到的货币名称。
- 玩家可查看余额、完成每日签到领取货币，并消耗自己的货币。
- 后续商店、委托收费等玩法可以复用同一套加减余额规则。
- 签到和消费并发或重复触发时，不重复发放、不透支，也不丢账。

## 规则

1. 当前只提供一种货币，默认名称为“银币”。货币名称和余额分开保存；改名只影响展示，不换算、不重置玩家余额。
2. 余额使用非负整数，所有发放、消费均以最小整数单位计数，不使用浮点数。
3. 每个玩家每天可签到一次。签到日按 `Asia/Shanghai` 的自然日计算，跨日后可再次签到。
4. 周一至周日的签到奖励分别在插件配置中调整，默认依次为 10、12、14、16、18、20、30。货币名称配置默认“银币”。
5. 货币账户沿用现有身份范围，以 `platform_id + sender_id` 隔离；不同平台的同一 sender ID 是不同账户。
6. 消费必须给出正整数金额，余额不足时整笔失败，余额不能变成负数。
7. 余额变更必须同时写入流水。任何业务都只能通过货币服务变更余额，不直接改账户表。

## 玩家命令

| 命令 | 行为 |
| --- | --- |
| `/余额` | 显示当前余额和后台配置的货币名称 |
| `/签到` | 领取当日配置的签到奖励；重复签到返回已签到提示 |
| `/消费 <数量>` | 消耗本人指定数量；成功后显示消耗额和剩余余额 |

消费命令只会扣除调用者自己的余额。后续商店、升级或委托费用不调用此命令，而是通过同一个 `spend_currency(...)` 用例结算，并传入业务来源作为流水说明。

## 后台配置

恢复并维护插件根目录的 `_conf_schema.json`，定义货币名称和七个星期奖励配置项：

```json
{
  "currency_name": {
    "description": "货币名称",
    "type": "string",
    "default": "银币",
    "hint": "玩家余额和奖励消息中显示的名称。修改名称不会改变现有余额。"
  },
  "signin_reward_monday": {
    "description": "周一签到奖励",
    "type": "int",
    "default": 10,
    "hint": "每位玩家周一签到获得的货币数量。"
  }
}
```

另外六项使用 `signin_reward_tuesday` 至 `signin_reward_sunday` 命名，默认值依次为 12、14、16、18、20、30。奖励限制为 1 到 10000 的整数。

加载配置时对名称做 `strip()`，空名称回退到默认值；签到奖励必须为正整数，非法值回退到默认值。配置仅控制展示名称和之后签到领取的奖励，不回写旧流水，也不改现有账户。

## 数据设计

账户和流水单独建表，不把余额只塞入 `profiles.data_json`。余额属于高频、需要原子增减的经济数据，流水可用于排错、幂等和未来查询。

```sql
CREATE TABLE currency_accounts (
    platform_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    balance INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (platform_id, player_id)
);

CREATE TABLE currency_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK (amount != 0),
    reason TEXT NOT NULL,
    idempotency_key TEXT UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

`amount > 0` 表示发放，`amount < 0` 表示消费。签到流水的 `idempotency_key` 使用稳定的玩家与日期键，例如 `signin:{platform_id}:{player_id}:2026-10-16`；唯一约束保证同日只成功记账一次。人工发放等未来功能也应使用幂等键或明确允许重复的业务凭据。

## 业务分层

- `main.py`：读取 AstrBot 配置、取平台和发送者身份、注册 `/余额`、`/签到`、`/消费` 命令，并返回服务层消息。
- `liuli/domain/currency.py`：货币数量校验和消费前置规则，不依赖 AstrBot 或 SQLite。
- `liuli/application/currency_service.py`：编排查余额、签到奖励、消费；生成包含配置名称的用户消息。
- `liuli/application/ports/currency_repository.py`：定义余额、流水和签到幂等所需的仓储接口。
- `liuli/infrastructure/persistence/sqlite/currency_repository.py`：实现账户和流水的 SQLite 原子操作。
- `liuli/infrastructure/persistence/sqlite/schema.py` 与 `migrations/v1.py`：定义建表和初始版本迁移。初始化时按 `PRAGMA user_version` 执行迁移，不在命令期间建表。

货币配置由插件入口作为参数传给 `CurrencyService`。领域层、仓储层都不读取 AstrBot 配置，也不依赖 `main.py`。

## 原子性和错误处理

签到在一个 SQLite 写事务内完成：确保账户存在、插入签到流水、增加余额、提交。重复键冲突时回滚本次操作并报告已经签到，不能再次增加余额。

消费也在一个 SQLite 写事务内完成：校验金额、确认余额足够、扣减余额并插入负数流水。任何一步失败都回滚。可使用 `BEGIN IMMEDIATE` 串行化写入；账户更新和流水插入必须处于同一事务中。多个仓储共用同一数据库连接时，事务同步锁放在 `SQLiteDatabase`，避免各仓储的独立锁互相绕过。

应用服务按结果生成明确中文回复：签到成功、重复签到、余额不足或金额错误。数据库异常继续向插件错误处理边界抛出，不会被伪装成成功回复。

## 实施顺序

1. 新增配置 schema，并在插件入口恢复配置注入。
2. 增加账户、流水表和版本化 SQLite migration。
3. 实现货币领域规则、仓储接口、SQLite 仓储和应用服务。
4. 接入余额、签到、消费命令，并使用配置名称和奖励数。
5. 更新 README 命令表及项目架构文档。
6. 验证首次签到发奖、重复签到不发奖、跨日可签到、配置名称变更不影响余额、余额不足不扣款、并发消费不透支、失败事务无孤立流水。

## 设计边界

- 目前不支持多种货币、玩家转账、管理员增删余额、群组共享账户和签到连签加成。
- 当前数据按平台隔离；若以后需要同一玩家跨平台共用余额，再增加显式账号绑定流程，不直接合并已有账户。
- AstrBot 插件配置由 `_conf_schema.json` 定义，并注入插件构造函数；货币名这类简单可编辑设置适合使用此配置入口。
