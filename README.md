# RoboLab

机器人科研基础设施：模型部署、仿真评测、真机接口与实验记录。

当前先把策略复现和评测流程做好，控制台作为统一操作入口；数据采集等能力后续在同一项目内扩展。

<a id="-quick-start"></a>
<a id="-快速开始"></a>

## 快速开始

在仓库根目录执行：

```bash
./start.sh
```

本机打开 **http://127.0.0.1:8765**；通过 SSH 在远程服务器启动时，直接打开终端打印的
**远程访问**地址（服务器 IP + 端口，无需密钥）。

只需 Python 3.10 及以上版本即可启动控制台。脚本会自动选择本地配置，没有则使用默认配置；
模型运行环境仍按各策略独立安装。启动会输出配置、历史目录与评测入口状态；
模型和仿真在提交任务后才加载。更多参数见[控制台说明](web/README.md)。

<a id="-what-xpolicylab-enables"></a>
<a id="-xpolicylab-能做什么"></a>

## 能做什么

- **控制台**：选择模型、checkpoint 和任务，启动、排队、停止运行，查看日志和历史记录。
- **策略接入**：模型依赖与环境依赖分开，沿用统一观测、动作和服务接口。
- **环境适配**：连接仿真接口、已有 TASK_ENV 和未来真机回调，区分成功、终止、截断与程序错误。
- **实验追溯**：每次运行保存参数、代码版本、日志与结果；支持按历史配置重跑。
- **开发协作**：为 agent 提供当前状态、操作手册、检查入口和工作记录规范。

<a id="-supported-benchmarks-and-infrastructure"></a>
<a id="-已支持的-benchmark-与基础设施"></a>

## 环境与验证范围

| 入口 | 当前状态 |
| --- | --- |
| CPU 协议检查 | 可运行，不需要 GPU 或模型权重；不计入实际任务成功率 |
| LIBERO / Pi_05 | 默认四组完整预算，也可单组/含 90 扩展全量；编排与结果处理已验证，真实模型效果仍需实跑 |
| RoboDojo / RoboTwin | 已有 adapter 入口，需配置完整 benchmark 工作区与运行环境 |
| 真机 | 已定义环境与反馈接口，具体硬件驱动和停止能力尚未联调 |

具体已验证能力与待办以[当前状态](docs/STATUS.md)为准。控制台不会把尚未配置的环境显示成可直接运行。

<a id="-integrated-policies"></a>
<a id="-已接入策略"></a>

## 默认策略

| 策略 | 策略 | 策略 | 策略 |
| --- | --- | --- | --- |
| [GR00T_N17](policy/GR00T_N17/README.md) | [TinyVLA](policy/TinyVLA/README.md) | [FastWAM](policy/FastWAM/README.md) | [LingBot_VA](policy/LingBot_VA/README.md) |
| [LingBot_VLA](policy/LingBot_VLA/README.md) | [StarVLA](policy/StarVLA/README.md) | [Pi_05](policy/Pi_05/README.md) | [demo_policy](policy/demo_policy/README.md) |

其余 adapter 保存在 Git 中，可[按需展开](policy/README.md)。保留某个策略不代表已经验证其模型效果。
`demo_policy` 是接口检查模板；各模型的安装、数据和训练命令以对应 README 为准。

<a id="-framework-overview"></a>
<a id="-框架概览"></a>

## 项目结构

```text
start.sh          一键启动控制台
web/              控制台、运行队列、历史记录
policy/           模型 adapter 与上游实现
client_server/    策略通信
model_template.py 模型接口
environment/     仿真与真机环境契约
utils/            图像、状态、维度和 checkpoint 等共享工具
configs/          工作区与控制台配置
scripts/          命令行运行与开发工具
docs/             架构、手册、状态、决策和工作记录
experiments/      可复现的实验说明与小型结果
artifacts/        本地运行产物，不提交 Git
```

<a id="research-workspace"></a>
<a id="-contents"></a>
<a id="-目录"></a>
<a id="-common-workflow"></a>
<a id="-通用工作流"></a>
<a id="-coding-agents"></a>
<a id="-编程-agent"></a>
<a id="-add-your-own-policy"></a>
<a id="-接入你自己的策略"></a>

## 开发与记录

从[文档入口](docs/README.md)、[当前状态](docs/STATUS.md)和 [AGENTS.md](AGENTS.md) 开始。
开发规则见[开发规范](docs/development.md)，模型接入见[适配规范](CONTRIBUTING.md)。

```bash
python3 scripts/check_workspace.py
python3 -m unittest discover -s tests -v
```

完整测试需要根 infra 依赖；真实模型和仿真验证在各自运行环境中进行。
控制台的配置、日志和数据库默认放在 `artifacts/web/`，工作记录与实验结论另行维护。

<a id="-standard-data-formats"></a>
<a id="-标准数据格式"></a>
<a id="decode-only-through-decode_image_bit"></a>
<a id="图像解码只能走-decode_image_bit"></a>
<a id="official-lerobot-conversion"></a>
<a id="官方-lerobot-转换"></a>
<a id="-data-and-checkpoints"></a>
<a id="-数据与-checkpoint"></a>
<a id="-deployment-flow"></a>
<a id="-部署流程"></a>
<a id="what-the-arguments-mean"></a>
<a id="参数含义"></a>

## 数据与接口

- 图像保持 RGB，存储编解码使用共享 `decode_image_bit` / `encode_image_bit`。
- checkpoint 和机器人维度由共享 helper 解析，观测与动作遵循已有 adapter 契约。
- 环境侧统一接口与反馈见 [environment](environment/README.md)。
- 详细[数据格式](docs/reference/adapter-contracts.md#-standard-data-formats)、[LeRobot 转换](docs/reference/adapter-contracts.md#official-lerobot-conversion)、[部署流程](docs/reference/adapter-contracts.md#-deployment-flow)与[参数表](docs/reference/adapter-contracts.md#what-the-arguments-mean)放在技术参考中，保留旧锚点兼容现有文档链接。

<a id="-citation"></a>
<a id="-引用"></a>
<a id="-contact"></a>
<a id="-联系方式"></a>

## 项目来源

RoboLab 基于 XPolicyLab 继续开发。原始代码来源、作者与引用信息见 [UPSTREAM.md](UPSTREAM.md)，
许可证见 [LICENSE](LICENSE)。当前 Python 兼容导入名与已有 checkout 路径保留，项目展示名称统一为 RoboLab。

命令行评测、执行快照和恢复规则见 [evaluation](evaluation/README.md)。
