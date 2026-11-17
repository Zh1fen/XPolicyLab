# 2026-11-16：按架构改进指南实施

## 基线与范围

依据[用户提供的改进指南](../architecture-improvement-guide.md)实施全部六个单元。
开始时工作树已有控制台、RoboLab 命名、评测范围和界面精简等未提交改动，均纳入本轮基线。
基线来源复制到 artifacts/architecture-qa/baseline/，含原脚本、转换器、服务入口、git-status 和八个活动模型名单；未改动既有训练配置、数据、checkpoint 或视频。

使用仓库 xpolicylab-model-integration 和 xpolicylab-adapter-check 两个 skill 约束 adapter 修改与核验。
未新建模型集成，不运行训练、真实模型推理、模拟器或硬件，不加入 Harness。

## 对应指南的实现

| 指南单元 | 实施与证据 |
| --- | --- |
| 运行发布、队列与恢复 | Store 分开分页与 SQL FIFO 领取；created_at+sequence 稳定排序；先写临时文件并同步、移动目录，最后提交 queued 行；孤立产物只识别不删除；CAS 状态转换和取消/完成仲裁；旧排队无快照则 interrupted |
| 执行快照 | 版本 1 包含展开任务、预算、seed、policy、checkpoint 原选择及解析路径、revision、实际后端配置与外部文件摘要；worker 从快照执行；LIBERO 固定实际配置选择，真机固定选中 profile；凭据引用与运行时解析分开 |
| 评测后端 | evaluation/backends 中各后端拥有 describe/normalize/freeze/execute；web 旧路径为兼容 facade；CLI 和控制台共用 Catalog、Runner 和 Store；小范围 ExecutionContext 提供进程/阶段/结果接口 |
| 数据与配置 | 两版 LeRobot 的 24 个相同函数迁入共享 ConversionInput，显式传入根目录、相机和版本指令查找；ALOHA 只复用相同原语；机器人元数据统一到父工作区读取；shell 训练本地表路径不变 |
| Pi_05 转换 | 修正输入/配置父目录、移除失效的 lerobot.common 导入，保留 next-state+末帧保持动作规则；相机映射和采样频率明确；保留原位置参数并增加临时路径/seed 选项；空输入/异常/已有输出失败 |
| 服务与包身份 | client_server/service.py 共用配置/模型/服务构造；根端口必填与 ws null→19000 分别保留；公开别名共享类型，保留 vendor utils 的优先级；安装范围验证包含 evaluation |
| 八个 adapter | 共享 eval_lifecycle.sh，登记独立进程组，回收 server/client 及 LingBot 自建 VA；原 argv、host、timeout、专有顺序保留；deploy 检查由 demo 全键集驱动并补齐七份配置；各 README 链接迁移说明 |

接口与恢复文档见[evaluation](../../evaluation/README.md)、[架构地图](../architecture.md)、
[生命周期矩阵](../reference/adapter-lifecycle.md)和[架构决策](../decisions/0006-execution-snapshots-and-ownership.md)。

## 实际验证命令与结果

测试均使用临时目录、临时数据库或隔离 QA 历史，不改正式历史与资产。

| 环境 / 命令 | 结果 |
| --- | --- |
| Pi_05 Python 3.11.18，`ROBOLAB_CONVERSION_VERSION=30 policy/Pi_05/openpi/.venv/bin/python -m unittest discover -s tests -v` | 最终 107 项通过，无跳过，61.589 秒；包含真机未知成功值、凭据引用和两项真实 v3 数据回读 |
| 同环境 `-m unittest discover -s tests -p test_architecture.py -q` | 队列 501 条、同时间戳、发布失败注入、取消竞争、重启/旧记录、catalog 修改、client 变化诊断、CLI 一致性、类型身份、配置默认值/优先级和服务子进程矩阵覆盖 |
| 同环境 `-m unittest discover -s tests -p test_adapter_lifecycle.py -q` | 四项通过：八个 adapter 实际 argv 前后对照、公共失败/超时/client 非零/中断回收、LingBot 自建后端顺序、经控制台取消的子进程回收 |
| `ROBOLAB_CONVERSION_VERSION=30 policy/Pi_05/openpi/.venv/bin/python -m unittest discover -s tests -p test_conversion_architecture.py -v` | 六项通过：前后字段/像素/padding/优先级、双注册维度、延迟 HDF5、动作末帧差异、v3 reader 与 Pi_05 shell 逐帧回读、空输入失败 |
| `ROBOLAB_CONVERSION_VERSION=21 PYTHONPATH="$PWD/artifacts/architecture-qa/lerobot033:$PWD:$PWD/.." policy/Pi_05/openpi/.venv/bin/python -m unittest discover -s tests -p test_conversion_architecture.py -v` | 五项通过，一项明确不适用：Pi_05 正式入口使用 v3。v2.1 使用隔离安装的 LeRobot 0.3.3 + datasets 3.6.0，回读 state/action/像素/指令 |
| `policy/Pi_05/openpi/.venv/bin/python scripts/smoke_infra.py` | 真实 CPU demo ws：reset、单条/批量、RGB 数组/两种编码布局、环境反馈/trial_end 通过 |
| `python3 scripts/check_workspace.py` / `node --check web/static/app.js` / `git diff --check` | 通过；deploy 缺 ckpt_name/gpu_id 的反例输出键名，有效 null 和模型专有键通过 |
| `uv build --wheel --offline --out-dir artifacts/architecture-qa/dist`、分别安装到隔离 wheel/editable target | 从 /tmp 导入公开类型与 evaluation 通过，轮包从 target 加载，editable 从源码加载；不安装或分发 vendor 权重 |

依赖隔离安装仅在 artifacts/architecture-qa/：通过 `uv pip install --target ... --no-deps lerobot==0.3.3 datasets==3.6.0` 准备旧 reader，未替换 Pi_05 原环境的软件包。
旧 reader 最初与环境已有 datasets 4.x 不兼容，按其发布依赖限定为 3.6.0 后回读通过。

回读暴露并修正了 v3 原 finalizer 未关闭数据 writer 的问题：以前生成的 Parquet 没有可读 footer。
测试 fixture 的 Python 3.11 字符串与静态检查 fixture 文件列表问题均已修正，不属于模型运行结果。

## 验证边界与交接

- Pi_05、其他七个模型的真实权重推理与真实仿真未执行。标准工作区仍缺父 env_cfg 和 conda；fixture 不替代这些依赖。
- LeRobot 回读使用 image 模式的小样本；AV1/NVENC 视频编码和大规模转换吞吐未重跑。
- Pi_05 原训练修改与外部 LIBERO 数据保持，HDF5 next-state 转换与既有 LIBERO 配方是两条独立路径。
- 包别名检查覆盖两种导入顺序、父目录/其他 cwd、editable/wheel 和 vendor 同名 utils；模型 vendor 本身未逐个导入测试。
- 整体服务仍需用户自行重启 `./start.sh`，本轮不重启用户进程。旧终态历史保持；旧 queued 无可靠快照会要求显式重提。
- .staging 或未发布 runs 目录仅列入恢复报告，不自动执行、不自动删除；SIGKILL 等异常后仍须检查残留外部进程。

最终浏览器回归通过：实际 CPU 提交至共享 Runner、snapshot.json 产物、历史分页、LIBERO 默认预算、导航及 390px 无页面溢出；无脚本错误。
截图在 artifacts/architecture-qa/browser/console.png，独立 QA 服务已关闭。
最终 wheel 核对包含 evaluation 与当前静态资源，包内 LICENSE 和仓库原文件逐字一致；git diff -- LICENSE 无变更。

完整环境版本记录在 artifacts/architecture-qa/versions.json：Python 3.11.18、LeRobot 0.4.4、datasets 4.8.5、
PyArrow 24.0.0、NumPy 1.26.4、h5py 3.16.0、websockets 15.0.1。
公共检查最终为 46 份 Markdown、八个 adapter、88 个 Python 文件和 63 个 shell 文件通过。


收尾把 Pi_05 数字 step/params 的候选规则移到 LIBERO 后端，可选 checkpoint_choices 供所属后端维护；
每任务次数上限也由后端声明。此次归属调整后重跑 `python3 -m unittest discover -s tests -p test_web.py -q`
（16 项）和 `policy/Pi_05/openpi/.venv/bin/python -m unittest discover -s tests -p test_evaluation.py -q`
（12 项）均通过，公共语法/文档/diff 检查通过。
