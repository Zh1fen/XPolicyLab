# RoboLab 控制台

仓库内的本地网页入口，当前实现评测模块。代码目录统一为 `web/`，后续可在这里扩展数据采集等功能。
后端使用 Python 标准库，前端为无构建的 HTML/CSS/JavaScript；不需要 Node、npm 或额外 Web 框架即可运行。

## 启动

从仓库根目录执行：

```bash
./start.sh
```

本机打开 `http://127.0.0.1:8765`；SSH 远程启动后，直接打开终端打印的“远程访问”地址，
形如 `http://<服务器IP>:8765/`，无需手动输入密钥或登录。
默认监听 `0.0.0.0:8765`，客户端须能连通服务器该端口。
脚本自动选择 `configs/web.local.json`，没有则使用示例配置，
无需激活模型环境或手动传配置。默认配置按当前工作区布局连接现有 LIBERO。
需要改路径时可复制示例为已忽略的 `configs/web.local.json`；相对资产路径相对仓库根目录解释。

```bash
cp configs/web.example.json configs/web.local.json
./start.sh --port 8765
```

所有高级参数可以追加在启动脚本后，例如 `./start.sh --port 9000 --data-dir /path/to/history`。
`ROBOLAB_PYTHON` 可显式指定 Python；默认使用 python3。运行 `./start.sh --help` 查看参数。
底层 `scripts/run_web.py` 保留，便于工具调用；其他入口按实际条件显示待配置。
启动输出包含 Python、工作目录、实际配置与历史目录、监听地址、活动策略数和评测入口配置状态。
“入口已配置”只表示配置与文件检查通过。启动不加载 GPU 模型或仿真，它们会在提交任务后启动，
详细运行日志在控制台的任务详情查看。配置错误、端口占用和历史目录冲突会打印明确错误。

若只需要 SSH 转发，可限制为回环监听：

```bash
./start.sh --host 127.0.0.1
# 在自己的电脑上执行：
ssh -L 8765:127.0.0.1:8765 <user>@<server>
```

随后在浏览器打开本机同端口地址。当前是可信内网使用的单用户控制台，
可连通端口的人均可操作任务；不提供登录或多用户权限，跨不可信网络时使用 SSH 转发。

## 当前功能

- 从八个活动策略中选择模型、benchmark、任务、checkpoint、seed 和 GPU。
- 检查入口与文件是否配置，明确显示缺少的环境、权重或父工作区；文件存在检查不是模型运行验证。
- 单 worker 排队执行，任务自动部署所需服务；查看状态、实时增量日志、参数快照与产物。
- 停止排队/运行任务，或从历史配置创建一次新运行；每次写入独立目录。
- SQLite 保留运行历史，页面显示最近 500 条；实际评测指标与 CPU mock 结果分开显示。
- 关闭页面不影响后台运行；正常关闭控制台会停止其管理的任务并清理进程组。

## 各入口的实际边界

| 入口 | 实现 | 当前验证 |
| --- | --- | --- |
| 协议检查 / demo_policy | 无 GPU 的 mock 环境闭环，产出逐步 JSONL；不是实际模型推理 | 已通过 API、进程和浏览器验证 |
| LIBERO / Pi_05 | 自动启动已有 OpenPI 原生服务和外部 LIBERO client，使用选择的 checkpoint、seed、GPU 与每任务 episodes | 文件与命令接线已核对；本轮未跑真实模型/仿真 |
| RoboDojo / RoboTwin | 调用现有 adapter eval.sh，使用配置中的两端环境 | 当前缺完整父工作区与 conda，入口显示待配置 |
| 真机 | 通过已登记 profile 调用统一环境 factory 与已部署策略服务 | 无硬件，默认不可启动；只提供接口 |

LIBERO 默认“常用完整评测”，一次顺序运行 Spatial、Object、Goal、10 四组，
每任务默认 50 次，共 2,000 episodes，模型只加载一次。
可选择单个 suite 或“扩展全量（含 90）”；LIBERO-90 是原始基准中的预训练集，扩展成绩与四组成绩分开。
episodes 是**每任务**预算；少于 50 次自动标为快速检查。
每组独立保存日志和逐任务结果，缺失/不足/异常不作为完整成绩；中断保留已完成的组。
主成绩为 suite 等权平均，同时保存 episodes 加权结果。首页显示最近完整四组成绩，不混合不同运行。

标准 RoboDojo/RoboTwin 的 episode 数由 benchmark 本身配置决定，页面不提供一个实际上不会生效的覆盖参数。
支持单任务或全部已登记任务，这个集合不代表官方全集。
标准入口目前只收集进程状态与日志，不猜测各 benchmark 的结果格式或把进程完成当任务成功。
完整范围、官方来源与尚未接入的内容见[评测口径](../docs/reference/evaluation-protocols.md)。

## 配置说明

参考 [web.example.json](../configs/web.example.json)：

- `libero.client_root`：含现有 `main.py` 的 client 项目；`client_python` 为该环境的 Python。
- `libero.uv_bin`：OpenPI 使用的 uv；`startup_timeout_s` 与 `timeout_s` 分别限制模型启动和评测等待。
- `policy_environments`：标准 adapter 第九参数，例如 Pi_05 的 uv、其他策略的 conda 名或项目路径。
- `standard.<benchmark>.eval_env / tasks / robots / policies`：标准客户端环境和允许选择的任务、机器人、已登记兼容模型。
  policies 默认空，避免把活动策略直接当成每个 benchmark 都已接入；任务示例只表示一个本地任务。
  当前标准脚本要求 benchmark 的 env_cfg 和 scripts 位于 checkout 的父工作区，不会自动创建或下载这些内容。
- `real_profiles`：由本机管理员登记的硬件 profile；前端不能提交任意 shell 命令或任意 factory。

硬件 profile 格式（只是接口格式，不是已连接硬件）：

```json
{
  "id": "my_robot",
  "policy": "Pi_05",
  "python": "/path/to/hardware-env/bin/python",
  "env_factory": "my_robot:create_env",
  "env_config": "/path/to/robot.json",
  "policy_url": "ws://127.0.0.1:6000",
  "timeout_s": 3600
}
```

factory 遵循 [environment/README.md](../environment/README.md)。硬件 profile 不负责自动部署模型，使用其中已运行的标准策略服务。
软件停止会给进程组发送中断/终止信号，不能代替硬件急停；驱动需自己实现 stop 回调和超时。

## 记录与指标

默认 `artifacts/web/` 下保存 `history.sqlite3` 与 `runs/<id>/`，后者包含参数、日志及结果。
运行记录包含代码 revision 和 dirty 标记；未提交代码的完整再现仍需按实验规范保存代码快照。
LIBERO 按 suite 独立核对逐次 Success、每任务次数和最终汇总；客户端报告 `Caught exception` 时标为运行失败。
参数中的 tasks 固定本次展开后的任务列表；backend_config.json 保存后端配置及 LIBERO client 脚本哈希，
metrics.json 保存分组、逐任务和总体结果，suites/ 或 tasks/ 保存独立日志。
没有明确指标时显示“未提供指标”，进程退出码 0 不代表机器人完成了任务。
现存的旧视频不自动导入为完整评测记录，避免从文件名推断并不存在的完整基线。

异常退出重启后，原 running/cancelling 记录标为 interrupted；控制台不根据旧 PID 盲目终止其他进程。
如服务器曾被强制结束，需先检查原评测进程再重跑。每个数据目录只允许一个控制台实例。
数据、日志、视频和数据库均不进 Git，迁移时连同记录目录一起保存。

## API 与验证

- `GET /api/catalog`：模型、benchmark 和可配置状态。
- `GET/POST /api/runs`：历史记录、创建运行。
- `GET /api/runs/<id>`、`POST /api/runs/<id>/cancel`：状态与停止。
- `GET /api/runs/<id>/logs?offset=...`：增量日志。
- `GET /api/runs/<id>/artifacts`、`.../files/<relative-path>`：运行产物，限制在对应运行目录内。

浏览器首次打开首页建立本地会话。API 需要会话令牌，修改请求需额外 header；不开放跨域控制。
服务通过明确参数数组启动子进程，不执行前端传入的 shell 字符串。

```bash
python3 -m unittest discover -s tests -p test_web.py -v
node --check web/static/app.js
python3 scripts/check_workspace.py
```

完整仓库测试应使用已安装根 infra 依赖的 Python。浏览器验证使用独立的 QA 数据目录，不污染正式历史。

## 执行与恢复

评测规则和队列实现已移动到[evaluation](../evaluation/README.md)，web 中旧 Python 导入继续可用。
任务从提交时的 snapshot.json 执行；后端配置、client 摘要、选定真机 profile 和两端环境均随运行保存。
无快照的旧排队记录会标为 interrupted，可在页面使用原参数重新提交；旧终态历史不受影响。
