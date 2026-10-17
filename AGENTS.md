# Codex 项目指令

本文件适用于整个 `astrbot_plugin_liuli` 仓库。处理代码、配置、文档或数据时，遵守以下要求；如有冲突，遵循更高优先级的系统、开发者和用户指令。

## 开始工作前

- 先检查相关源码、调用链和当前 Git 状态，再决定修改范围。不要把下方结构示例当作当前文件清单，也不要凭空假设模块已经存在。
- 保留用户已有的未提交改动。只修改完成当前请求所需的文件，不清理或覆盖无关改动。
- 以插件当前代码和实际 AstrBot API 为准。需要确认 AstrBot 行为或接口时，查阅官方开发文档及项目实际依赖，不凭记忆猜测。
- 按用户要求执行验证；如用户没有要求测试或验证，不要自行添加或运行测试。

## 项目结构与职责

保持 AstrBot 插件发现所需的根目录 `main.py`。将插件自身的业务代码放入 `liuli/`，并按真实职责扩展现有分层：

```text
main.py                         AstrBot 插件入口、事件适配和依赖组装
liuli/application/              用例编排和应用服务
liuli/application/ports/        应用服务实际需要的接口（按需）
liuli/domain/                   框架无关的业务模型和规则
liuli/infrastructure/           数据库及其他外部技术实现
liuli/resources/                随代码发布的静态游戏内容
tests/                          按需要维护的自动化测试
docs/                           按需要维护的设计文档
```

- 以实际需求决定是否新增模块或目录；不要预建空目录、空接口或装饰性抽象。
- 优先扩展职责相符的现有模块。只有当模块职责混杂或持续膨胀时才拆分。
- 角色、公会、委托、货币、宠物、副本、灵宠战斗及后续领域功能应通过明确的服务和数据接口协作，不直接读写彼此的内部状态。
- 静态游戏定义放在 `liuli/resources/`；用户运行状态放在插件数据目录；不要把存档、数据库、密钥或运行日志写进源码目录。

## 分层边界

### `main.py`：AstrBot 适配层

- 负责定义 Star 插件、注册元数据、处理 `initialize()` / `terminate()` 生命周期、命令和事件适配，以及组装服务依赖。
- 从事件中提取平台、发送者、群组等身份和命令参数，调用应用服务，并把结果转换成 AstrBot 消息。
- 不在命令处理器中写 SQL、维护游戏状态或实现领域规则。
- 避免继续把业务逻辑堆进 `main.py`；新增用例应进入 `liuli/application/`，规则应进入 `liuli/domain/`，技术实现应进入 `liuli/infrastructure/`。

### `liuli/application/`：应用用例层

- 编排完整用户操作，检查用例前置条件，调用领域规则，并通过所需接口读取或保存状态。
- 可以依赖 `liuli/domain/` 和本层定义的 ports；不得依赖 `astrbot.*`、`aiosqlite` 或具体 SQLite 仓储实现。
- 只为实际用例定义所需的 ports；不得为了抽象而重复封装简单调用。
- 不发送 AstrBot 消息，不读取全局会话变量；身份及业务参数应由调用方明确传入。

### `liuli/domain/`：领域层

- 定义业务概念、状态、校验和纯业务规则；规则应通过明确输入和结果表达。
- 不依赖其他项目层、AstrBot、SQLite、平台 SDK、聊天文案或配置文件。
- 不保存依赖运行环境的可变全局状态。

### `liuli/infrastructure/`：基础设施层

- 实现应用层实际需要的接口，负责 SQLite 等外部技术访问和持久化。
- 仓储负责数据读写，不决定玩家资格、奖励或状态转换等业务规则。
- 异步 I/O 保持异步；不要在命令事件循环中执行长时间同步文件或网络操作。

## 身份、数据与数据库

- 玩家档案以 `platform_id + sender_id` 共同定位，避免不同平台的 ID 冲突。
- 首次调用任意琉璃命令时，以平台昵称创建默认档案；之后只通过 `/改名 <昵称>` 更新玩家主动设置的名字，不因平台昵称变化覆盖它。
- 群组数据按 `platform_id + group_id` 定位。只有实际实现群组功能时才增加相应表和模块。
- 通过仓储访问持久化数据。服务接收明确的身份和业务参数，不读取全局用户或命令上下文。
- SQLite 数据目录使用 `StarTools.get_data_dir("astrbot_plugin_liuli")`，不要自行改为源码目录或其他临时路径。
- SQLite 实现放在 `liuli/infrastructure/persistence/sqlite/`。结构升级放在该目录的 `migrations/`，并使用版本判断和向前迁移；不要在普通命令调用期间临时改表。
- 管理员可调选项才进入 AstrBot 插件配置 schema；固定规则和静态游戏内容不要伪装成配置项。
- 插件仍处于开发阶段；不要为不存在的旧版用户存档添加 JSON 兼容逻辑。

## 新功能实现顺序

按功能需要从内向外实现，保持依赖方向：

1. 在 `liuli/domain/` 明确规则、状态及结果。
2. 在 `liuli/application/` 编排用例；只在需要时定义 ports。
3. 在 `liuli/infrastructure/` 实现持久化或其他外部能力；涉及数据库变化时同时维护 schema 和迁移。
4. 在根目录 `main.py` 添加最薄的 AstrBot 入口，负责取参、调用服务和返回消息。
5. 根据用户要求更新 README、配置 schema、静态资源或开发文档。

依赖方向必须保持为：

```text
AstrBot 事件 -> main.py -> application -> domain
                         application ports <- infrastructure
```

`main.py` 可以依赖 application 和 infrastructure 以组装实现；application 依赖 domain 和 ports；infrastructure 可依赖 ports 和 domain；domain 不依赖其他项目层。

## 命名、错误和依赖

- Python 包、模块、函数和变量使用 `snake_case`；类使用 `PascalCase`；常量使用 `UPPER_SNAKE_CASE`。
- 模块名应体现领域职责，例如 `player_service.py`、`quest.py`、`profile_repository.py`。避免使用职责不清的 `utils.py`、`manager.py`、`common.py`。
- 在业务边界把可预期错误转换为清楚的用户提示；日志用于诊断，不得泄露密钥或敏感凭据。
- 新增运行依赖前先确认 AstrBot 或现有依赖没有提供相同能力；确需新增时更新 `requirements.txt`。

## AstrBot 官方资料

涉及插件结构、命令、生命周期或消息事件时，优先核对对应的官方文档：

- 插件结构与开发入口：<https://docs.astrbot.app/dev/star/plugin-new.html>
- 简单插件、命令和生命周期：<https://docs.astrbot.app/dev/star/guides/simple.html>
- 事件消息监听：<https://docs.astrbot.app/dev/star/guides/listen-message-event.html>
- 事件消息发送：<https://docs.astrbot.app/dev/star/guides/send-message.html>
