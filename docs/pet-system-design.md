# 宠物系统设计

## 目标与边界

宠物是玩家拥有的独立成长角色，具备生命值、魔力、等级和技能。第一阶段建立可持久化的宠物档案、领养/查看/切换/技能管理和经验升级基础；战斗、捕捉、孵化、宠物交易、自动战斗和宠物装备留待玩法确定后再接入。

玩家身份沿用插件现有的 `platform_id + sender_id`。同一平台的玩家可拥有多只宠物，但任一时刻至多指定一只当前宠物。新玩家首次领养时，从静态宠物目录中免费选择一只初始宠物；后续新增宠物由委托、活动或其他已定义的奖励用例调用领养服务，不在宠物模块里自行发奖。

## 核心规则

### 属性与等级

- 宠物从等级 1 开始，建议上限 100；当前经验记录在宠物实例中。
- 每个宠物模板定义基础生命、基础魔力及每级成长值。最大属性由模板和等级计算：

  ```text
  最大生命 = 基础生命 + (等级 - 1) × 每级生命成长
  最大魔力 = 基础魔力 + (等级 - 1) × 每级魔力成长
  ```

- 当前生命和当前魔力持久化保存，并限制在 `0..最大值`。升级增加最大值时，同时给当前值增加相同的成长量，保留原有已损失数值，不把升级当作免费治疗。
- `experience` 表示当前等级内已累积经验，不是账号总经验。建议升到下一级需要 `当前等级 × 100` 经验；升级时扣除本级门槛并循环结算，避免一次奖励跨级时漏升。
- 宠物被修改为更低的模板成长值时，读取时将当前生命/魔力限制到新上限；模板 ID 一经发布不删除，退役模板仍保留给已有宠物读取。

### 技能

- 技能定义是静态内容，宠物实例只记录已学技能和当前装备技能；名称、说明、魔力消耗和效果留在技能目录。
- 初始技能和按等级解锁的技能由宠物模板指定。达到解锁等级时自动学会；所有已学技能都保留在技能列表中。
- 初始技能会自动装备到前几个技能槽；升级解锁的技能先加入技能列表，由玩家决定是否装备。
- 每只宠物最多装备 4 个技能。技能装备只改变当前战斗配置，不删除已学技能。
- 技能数据至少包含稳定 ID、名称、说明、魔力消耗、目标类型、效果类型、效果参数和解锁等级。效果类型采用有限枚举，由未来战斗服务解释；资源文件不得存放可执行代码。
- 第一阶段只支持查看、装备和卸下技能，不实际施放。施放时由战斗用例检查宠物为当前宠物、技能已学且已装备、魔力足够，再原子扣除魔力并结算效果。

## 宠物模板与实例

模板存放于 `liuli/resources/pets/`，随插件版本管理。例如：

```json
{
  "pet_id": "slime",
  "name": "史莱姆",
  "description": "温顺而有韧性的伙伴。",
  "base_hp": 50,
  "hp_per_level": 8,
  "base_mp": 20,
  "mp_per_level": 3,
  "starting_skills": ["tackle"],
  "level_skills": [
    {"level": 5, "skill_id": "acid_splash"}
  ]
}
```

运行时宠物实例和模板分开存储。建议实例字段：

| 字段 | 用途 |
| --- | --- |
| `pet_id` | UUID，实例唯一标识 |
| `platform_id`, `player_id` | 宠物所有者 |
| `species_id` | 静态宠物模板 ID |
| `name` | 玩家可改的宠物昵称 |
| `level`, `experience` | 等级与当前等级经验 |
| `current_hp`, `current_mp` | 当前生命和魔力 |
| `is_active` | 是否为当前宠物 |
| `created_at` | 领养时间 |

技能单独使用宠物技能关系记录：`pet_id`、`skill_id`、学习时间、装备槽位。装备槽位为空表示已学但未装备；非空槽位为 1 到 4。数据库以唯一约束保证同一宠物不能重复学习同一技能、不能重复占用同一技能槽。

对应运行数据表建议如下：

```sql
CREATE TABLE pets (
    pet_id TEXT PRIMARY KEY,
    platform_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    species_id TEXT NOT NULL,
    name TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1 CHECK (level BETWEEN 1 AND 100),
    experience INTEGER NOT NULL DEFAULT 0 CHECK (experience >= 0),
    current_hp INTEGER NOT NULL CHECK (current_hp >= 0),
    current_mp INTEGER NOT NULL CHECK (current_mp >= 0),
    is_active INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX idx_pets_one_active_per_owner
    ON pets(platform_id, player_id) WHERE is_active = 1;

CREATE TABLE pet_skills (
    pet_id TEXT NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
    skill_id TEXT NOT NULL,
    learned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    slot INTEGER CHECK (slot BETWEEN 1 AND 4),
    PRIMARY KEY (pet_id, skill_id),
    UNIQUE (pet_id, slot)
);
```

宠物实例不复制模板的最大生命、成长值或技能描述，避免档案和静态定义重复。宠物 ID 使用 UUID；模板 ID 和技能 ID 属于稳定内容 ID，不使用显示名称作为键。

## 持久化与事务

宠物数据独立于 `profiles.data_json` 和货币账户，增加 `pets` 与 `pet_skills` 两张表。数据库通过现有 `SQLiteDatabase` 共享连接与锁，并新增向前迁移版本。

- 所有权校验必须同时匹配 `platform_id`、`player_id` 和 `pet_id`，不接受用户传入的其他玩家宠物。
- 当前宠物通过 `is_active` 表示；SQLite 增加部分唯一索引，限制每个所有者最多一条 `is_active = 1` 记录。
- 首次领养、宠物及初始技能插入必须在同一个事务内完成。
- 切换当前宠物时，在一个事务中先取消原当前宠物，再激活目标宠物。目标宠物不属于玩家时不修改任何记录。
- 获得经验、跨级、更新属性、解锁等级技能也在一个事务中完成，防止经验已加但升级状态未保存。
- 领养奖励入口应支持业务幂等键，避免委托或活动重复结算发出重复宠物。

## 分层与模块

- `liuli/domain/pet.py`：宠物实例、等级规则、属性上限、经验结算和技能槽规则，不依赖框架或数据库。
- `liuli/application/pet_service.py`：领养、查看、改名、切换当前宠物、技能管理和发放经验等用例。
- `liuli/application/ports/pet_repository.py`：定义宠物所有权查询、原子更新、领养和技能读写接口。
- `liuli/infrastructure/persistence/sqlite/pet_repository.py`：SQLite 查询与事务实现。
- `liuli/infrastructure/persistence/sqlite/schema.py`、`migrations/`：宠物表、技能关系表、唯一索引和版本迁移。
- `liuli/resources/pets/`：宠物与技能静态定义。加载时校验 ID 唯一、属性为非负整数、技能引用存在、装备槽规则有效；坏数据记录错误并跳过，不让单个错误定义阻止插件加载。
- `main.py`：身份和命令参数适配，调用应用服务并回消息，不实现宠物成长或 SQL。

宠物仓储与货币仓储共用数据库锁，避免在同一个 `aiosqlite` 连接上并发交错事务。升级奖励与货币奖励若同属一个委托结算，未来应由应用用例在同一数据库事务边界内协调。

## 玩家命令建议

| 命令 | 行为 |
| --- | --- |
| `/领养宠物 <编号>` | 尚无宠物时免费领养一只目录中的初始宠物 |
| `/我的宠物 [编号]` | 列出自己的宠物，或查看某只宠物的属性与技能 |
| `/宠物改名 <编号> <昵称>` | 修改自己宠物的昵称 |
| `/出战宠物 <编号>` | 设置当前宠物；为未来战斗和跟随玩法提供唯一入口 |
| `/宠物技能 [编号]` | 查看宠物已学技能及装备状态 |
| `/宠物技能装备 <宠物编号> <技能编号>` | 装备一项已学技能；最多 4 项 |
| `/宠物技能卸下 <宠物编号> <技能编号>` | 卸下已装备技能，保留学习记录 |

昵称长度建议限制为 1 到 24 个字符。所有命令都先确保玩家角色存在，再由宠物服务检查所有权和状态。

## 实施阶段

1. 增加宠物/技能模板文件和纯领域规则，确定首批宠物与技能内容。
2. 增加宠物实例、技能关系表及 SQLite 迁移；实现有事务保护的仓储。
3. 接入免费初始领养、查看列表/详情、改名、切换当前宠物和技能管理命令。
4. 定义经验奖励来源，再把委托完成等结算接入 `grant_experience`。
5. 有战斗规则后再实现技能施放、魔力扣除、伤害、治疗和恢复；不要在第一阶段预先把战斗规则塞进宠物仓储。
