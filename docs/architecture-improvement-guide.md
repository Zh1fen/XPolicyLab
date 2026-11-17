# RoboLab 架构改进指南

**用途**　交给实施 agent 的完整变更说明。依据 2026-11-16 的工作树审查，涵盖共享 infra、控制台、公共转换器和八个活动 adapter。本文描述拟实施的改动；当前实现与验证状态以 [STATUS](STATUS.md) 为准。

**交付目标**　一次评测从提交到执行使用同一份可追溯配置；同一种原始数据和同一份机器人配置有明确的解释入口；服务与 adapter 的公开命令可以继续使用；新增 benchmark 时，其预算、启动与成绩规则能在所属模块内维护。下文各项均属于本次交接范围。实施顺序体现依赖关系，各项都有独立的验收条件。

## 1. 目标目录与依赖方向

| 所有者 | 负责的决定 | 调用边界 |
| --- | --- | --- |
| 根入口、`scripts/` | 解析命令、组装具体实现、返回退出码 | 保留公开路径和参数。可复用的业务逻辑放进可导入模块，命令行与网页经同一接口调用。 |
| `policy/<POLICY>/` | 模型构造、输入映射、权重 step 选择、模型特有服务及依赖环境 | adapter 使用共享数据和 checkpoint helper。仅模型进程加载 Torch、JAX 或上游模型包。 |
| `client_server/` | 编解码、消息与请求生命周期、重连、推理调用 | 服务实例接收已构造的模型。由启动入口选择具体模型与传输协议。 |
| `environment/` | 单环境 reset/step、动作校验、执行反馈、单 episode 收尾 | 通过策略接口调用本地模型或客户端。suite、队列、成绩汇总属于评测层。 |
| 评测后端，建议 `evaluation/` | benchmark 的就绪条件、任务展开、预算、运行配置、命令与结果解析 | 供网页和 CLI 导入。外部模拟器、硬件 SDK 和模型通过明确的进程或 factory 边界调用。 |
| `web/` | HTTP、表单、历史、日志和产物展示；串行任务调度 | 请求交给评测后端解析。队列只负责领取任务、运行阶段、取消和进程回收。已有 HTTP 路径及响应字段兼容。 |
| 共享数据与配置模块 | 原始 episode 字段提取、机器人配置、图像字节语义、checkpoint 根目录解析 | 现有 `XPolicyLab.utils.*` 公共路径继续可用。版本专有的数据集 writer 依赖留在各自转换环境。 |
| `configs/`、`experiments/`、`artifacts/`、`docs/` | 分别保存可复用配置、实验记录、运行产物、规范和证据 | 单次执行快照与日志属于运行产物；实验记录引用它们的标识。仓库架构文档只描述已实施的边界。 |

建议的主调用关系如下。共享队列和后端可在同一进程内运行，现有串行工作方式已足够。

```text
网页 / CLI → 评测后端解析请求 → 固化本次运行 → 队列领取
          → 后端使用快照生成命令 → 进程执行 → 后端解释结果 → 历史与产物

环境 client → 标准 ws → 策略服务 → policy/<POLICY>/Model
LIBERO 原生 client → OpenPI 原生服务 → Pi_05

原始 episode → 共享输入读取与字段提取 → 各格式 writer → 回读验证
```

执行前记录 `git status --short` 和活动策略名单。当前工作树含已有修改及未跟踪的控制台代码，评审基线应包含它们。遵循父工作区路径、稀疏视图、RGB、双份机器人注册和 upstream 归属约定。入口见 [架构地图](architecture.md)、[仓库规范](../AGENTS.md) 和 [兼容层参考](reference/adapter-contracts.md)。

## 2. 运行记录、队列和恢复

**现状。** `Store.list()` 按时间倒序取最近 500 条，worker 反转该结果并寻找待执行项。内存 SQLite 验证过，501 个排队项中的最早一条会落在调度视野之外，即使后 500 条都完成也不会被领取。`Store.create()` 又先提交数据库行，再创建目录及参数文件。`Manager.create()` 最后才计算客户端摘要、写入后端快照。写文件失败可能留下一个提交方认为失败、worker 却可以执行的任务。见 [Store](../web/store.py) 和 [Manager](../web/jobs.py)。

**实施。**

1. 分开历史分页和调度查询。领取操作直接查询 `status='queued'`，按创建时间及稳定的次序键选最早一条，在同一 SQLite 事务内将其转为运行中。取消和关停也直接按状态查询，覆盖全部待处理记录。
2. 明确发布点。先解析参数并准备本次运行所需文件；所有准备成功后才提交可领取记录。区分写入中的临时目录和已发布运行。针对进程在文件准备与数据库提交之间退出的情况，定义孤立目录的识别与恢复方式，避免误删历史产物。
3. 由运行存储负责状态转换，采用带预期旧状态的更新。排队取消、运行中取消、正常退出、执行失败各有明确终态；处理完成与取消同时发生的情况。启动恢复应保留历史结果，能识别上次异常终止的运行。
4. 为新任务保存带版本的执行快照。至少保存 benchmark、任务清单、预算、seed、policy、checkpoint 选择与解析结果、工作区 revision、后端配置以及实际使用的外部客户端身份。标准后端还需要 policy/eval 环境，真机需要实际选中的 profile、factory、policy URL 和环境配置。若运行依赖配置文件内容，保存副本或摘要并在执行前核验。敏感凭据仅保存引用。
5. worker 从快照恢复运行。当前 LIBERO 提交时记录客户端摘要，运行时却再读 catalog；真机的提交路径从 `standard` 写快照，执行路径从 `real_profiles` 选配置。改成按后端构造一次快照。对于旧库，可读的终态历史继续展示；旧排队记录仅在所需信息可可靠还原时恢复，对缺失项记录原因并支持按现配置显式重提。

**验收。** 用临时 SQLite 和产物目录覆盖 501 条排队记录、同时间戳入队、快照写入失败、取消与完成相遇、异常重启、旧记录读取。在任务提交后修改 catalog 并重启，核对 fixture 子进程收到的实际参数与原快照一致。模拟客户端文件变化并检查诊断及终态。现有 HTTP 历史、日志、按配置重跑、单实例数据目录锁都应通过。扩展 [控制台测试](../tests/test_web.py) 与 [评测测试](../tests/test_evaluation.py)。

## 3. 评测后端与控制台解耦

**现状。** 一个 benchmark 的可选项和就绪条件在 `Catalog.snapshot()`，请求归一化在 `Catalog.validate()`，启动及指标保存又在 `Manager._execute()`。LIBERO 成绩解析已独立，适合作为迁移起点。见 [目录与校验](../web/catalog.py)、[执行分支](../web/jobs.py) 和 [成绩计算](../web/evaluation.py)。

**实施。** 先把 LIBERO 的任务展开、就绪检查、运行配置、启动和结果汇总放到一个可独立导入的后端。协议检查、标准评测、真机分别实现相应行为，RoboDojo 与 RoboTwin 共享标准启动实现并使用各自声明的配置。可以用显式映射按 benchmark ID 选择实现。就绪探测、请求解析与执行可以是普通函数。后端只通过小范围的执行接口启动、等待、记录阶段与保存中间结果；SQLite、HTTP handler 和进程组清理各有单独所有者。checkpoint 根目录沿用共享 resolver，数字 step 和 `params/` 等布局规则留给对应模型或后端。

**验收。** 从普通 Python 入口和控制台提交同一请求，两者得到相同任务顺序、命令参数、配置和指标。LIBERO 多 suite 运行只加载一次模型，取消或失败保留已完成 suite；维持 suite 宏平均、episode 加权平均和完整预算判定。标准 benchmark 的进程退出只能证明运行完成。协议 mock 的结果、真实任务成功率及真机未知成功值在记录和页面上均可区分。详见 [评测口径](reference/evaluation-protocols.md)。

## 4. 数据转换、机器人配置与 Pi_05

**可复用范围。** 比较两份公共 LeRobot 脚本的顶层函数，30 个同名函数中有 24 个 AST 完全一致。它们覆盖目标发现、维度规划、状态/动作及相机字段提取、图像尺寸探测等。相同函数体也可能调用不同的全局配置，例如两版 `_choose_instruction` 调用的字段查找顺序不同。见 [v2.1 转换器](../scripts/transform_lerobot_v21_format.py)、[v3.0 转换器](../scripts/transform_lerobot_v30_format.py)。

| 改动 | 保留的行为与验收 |
| --- | --- |
| 提取与 LeRobot 版本无关的输入读取、任务发现和有效数据变换。写出层各自拥有 dataset 创建、视频设置、flush/finalize 和相应库依赖。 | 同一小样本比较变更前后的帧数、相机、像素、指令、动作与状态顺序、dtype 和逐臂 padding。两版各用对应 reader 回读。固定随机种子，用同时含 `instruction` 和 `instructions` 的样本检查原有优先级，记录异常输入处理的版本差异。 |
| 核对 ALOHA 和 Pi_05 的动作构造后复用确实相同的输入处理。 | ALOHA 的动作提取接收 `qpos`；Pi_05 的特有路径由下一帧 state 构造 action 并处理末帧。分别测试缺失动作、单帧和多帧。见 [ALOHA](../scripts/transform_aloha_hdf5_format.py)、[Pi_05 转换器](../policy/Pi_05/openpi/scripts/process_data.py)。 |
| 收拢 Python 环境配置读取，让维度总和、机器人名、数据采样频率等从同一份父工作区配置取得。保留原有 helper 导入路径。 | 用父目录有 `env_cfg/`、checkout 内无该目录的 fixture 测试。运行时按 YAML 的机器人名查表；训练 shell 按 `env_cfg_type` 查本地表并可独立运行。用两个键名不同的 fixture 验证两入口的关节维度一致。见 [公共 helper](../utils/process_data.py)、[训练维度入口](../utils/get_action_dim.sh)。 |
| 修复 Pi_05 正式转换入口的环境路径及与已安装 LeRobot 的 API 兼容性。核对原始数据与输出位置各自的契约，单独解释已有数据位置。 | 从 [process_data.sh](../policy/Pi_05/process_data.sh) 启动小数据转换，在临时输出下逐帧回读。核对相机键、动作、指令和 episode 数；出现跳过所有 episode 或未完成写出时，命令应报告失败。既有数据和 checkpoint 不作为测试输出。 |
| 图像编解码继续由 `utils/process_data.py` 负责。HDF5 依赖在实际读取 HDF5 的位置加载。 | 仅导入服务解码路径时无需加载 HDF5；两种历史 JPEG 字节格式和已解码 RGB 数组各走一遍共享路径。保留旧容器布局和 marker 的处理。见 [文件读取 helper](../utils/load_file.py)。 |

## 5. 服务入口、配置与包身份

**配置所有者。** 根服务入口与 ws 模块入口都读 YAML、导入 `XPolicyLab.policy.<POLICY>.model`、构造模型与服务。根入口要求有效 port，ws 入口对 `port: null` 使用 19000。提取公共配置解析、模型构造和 ws 服务构造；两个 CLI 通过显式参数表达各自已公开的默认行为。保留根入口支持的 overrides 写法、显式 CLI 参数优先级、协议选择和错误诊断。见 [根服务入口](../setup_policy_server.py)、[ws 服务入口](../client_server/ws/model_server.py)。

**包身份。** `XPolicyLab.py`、父工作区包与顶层安装包共同提供历史兼容。按当前入口的路径设置，`environment.contracts` 与 `XPolicyLab.environment.contracts` 指向同一文件，加载出的 `ExecutionFeedback` 却是两个类。项目内部统一公共类型的导入身份，将顶层兼容集中在已公开的包入口。核查 `pyproject.toml` 的实际分发范围、vendor 路径和直接运行脚本的调用方。保留外部使用的 `client_server.*`、`XPolicyLab.policy.*` 命名。见 [打包配置](../pyproject.toml)、[兼容模块](../XPolicyLab.py)、[环境 CLI](../scripts/run_environment.py)。

**验收。** 用最小模型 fixture 对照两个服务入口的显式 host/port、空端口、非法配置及根入口的 overrides 和 legacy TCP。比较实际加载的模型配置和退出码。在父工作区、其他当前目录和仓库支持的 editable 安装环境中分别运行公开入口。对支持的别名按两种先后顺序导入，校验公共类型的 `is` 身份。执行真实 CPU ws smoke，覆盖数组和编码图像。

## 6. adapter 启动生命周期与提交契约

**启动脚本。** 八个活动 adapter 都有端口选择、启动、等待服务、运行 client 和清理逻辑。先比较每个 adapter 的原始参数数组、timeout、环境激活、host 传递和需要回收的进程，再提取公共生命周期。demo 按 PID 清理，Pi_05 使用独立进程组，LingBot_VA 还会单独启动 VA 服务。公共实现管理其创建的进程；有额外进程的模型显式登记或由模型专有入口负责。直接运行 adapter 与经控制台取消都要验证。见 [demo](../policy/demo_policy/eval.sh)、[Pi_05](../policy/Pi_05/eval.sh)、[LingBot_VA](../policy/LingBot_VA/eval.sh)。

**迁移范围。** 先用 demo 和一个普通单服务模型检验公共接口，再逐一迁移其余活动 adapter 的共用部分。保留原 `eval.sh` 的十个位置参数、模型专有默认值、conda/uv 选择、GPU 分配、退出码以及专有服务就绪顺序。把每个 adapter 的例外及原因写入对应 README 或迁移记录。以含空格路径和 CPU stub 进程验证 argv、超时、服务启动失败、client 失败、正常退出和中断后的子进程回收。

**deploy 契约。** 以 demo 的完整顶层公共键集驱动检查；区分缺键和允许为 null 的运行时覆盖项。当前八个活动配置中，七个非 demo 配置至少缺 `ckpt_name`、`gpu_id` 中的一项。补齐时核对调用处对“缺键”和“显式 null”的解释。静态检查继续允许模型专有字段，并在无模型依赖环境运行。验收时主动删去 fixture 的一个公共键，确认 CI 输出缺少的键名，再验证专有字段和有效空值通过。见 [参考模板](../policy/demo_policy/deploy.yml)、[工作区检查器](../scripts/check_workspace.py)。

## 7. 交付顺序与证据

| 顺序 | 实施单元 | 提交给审阅者的证据 |
| --- | --- | --- |
| 1 | 固定现有行为 | 当前入口、活动 adapter 参数差异、历史库 fixture、两版转换样本和基线输出。记录工作区已有改动。 |
| 2 | 运行发布、领取、恢复及快照 | 第 2 节的失败注入、501 条排队和重启用例，数据库状态、实际 argv、快照三者对照结果。 |
| 3 | 厘清评测后端 | 第 3 节各后端的 CLI/网页一致性、LIBERO 中断恢复证据和原有成绩口径。这里的恢复指保留已完成结果，重启程序不隐式续跑真机动作。 |
| 4 | 机器人配置与数据转换 | 第 4 节的维度一致性、两版 reader 回读及 Pi_05 入口小数据结果。 |
| 5 | 服务构造、包身份、deploy 模板 | 第 5、6 节的导入矩阵、入口默认值矩阵、缺键反例和 demo ws smoke。 |
| 6 | 启动器与文档收尾 | 八个活动 adapter 各自的迁移结果，进程回收测试；更新架构地图、相关 README、STATUS 和一份实际工作记录。 |

仓库公共检查从根目录执行：

```bash
python3 scripts/check_workspace.py
python3 -m unittest discover -s tests -v
node --check web/static/app.js
python scripts/smoke_infra.py
git diff --check
```

工作记录逐项写明使用的 Python/依赖环境、命令、通过和跳过的用例。使用临时工作区验证队列和转换器，保存测试数据库或样本的构造方法。CPU stub、真实 ws、真实数据回读、模型推理、模拟器、硬件各自记录证据；缺少的外部依赖具体到路径或版本。实际训练或评测另按 [实验记录规范](../experiments/README.md) 留档。本文中的验收用例是给实施者的交付要求，未执行项不计为已通过。
