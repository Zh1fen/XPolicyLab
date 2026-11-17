# 活动 adapter 启动生命周期

八个活动 eval.sh 继续接收原有十个位置参数，模型的环境激活逻辑仍在 setup_eval_policy_server.sh / setup_eval_env_client.sh。
共享的 utils/eval_lifecycle.sh 负责退出/中断处理、已登记进程组回收、client 等待与公共端口/就绪 helper 调用。
服务启动为独立进程组，创建后显式登记；client 也由共享 helper 创建并登记。模型依赖不进入共享 shell。

| Adapter | 原有差异及保留方式 |
| --- | --- |
| demo_policy | 保留原 server/client 参数及 1200 秒启动等待；原 PID 清理改为整个已创建进程组 |
| GR00T_N17 | server 不新增 host 参数，保留 helper 默认 host 和 600 秒启动等待 |
| TinyVLA | 保留 conda 环境参数、server 默认 host 与 1200 秒等待 |
| FastWAM | 保留第九参数和原 server 参数数组、1200 秒等待 |
| LingBot_VLA | 保留模型环境与原 server 参数数组、1200 秒等待 |
| StarVLA | 保留十参数检查、显式 server host 和 1200 秒等待 |
| Pi_05 | 保留第九参数默认 uv、显式 server host、1200 秒等待；原独立进程组清理转入共享实现 |
| LingBot_VA | 先启动/等待自有 wan_va，再启动 forward server；保留额外 CONFIG_NAME 参数、1800 秒 VA 默认等待和 600 秒 forward 等待。使用外部 VA 时不登记或停止外部进程 |

所有启动参数在含空格工作区和 CPU stub 下与变更前逐项对照。
已验证公共失败/超时/client 非零退出、直接中断，以及控制台取消时 adapter 创建的子进程回收。
LingBot_VA 另验证了自建 VA + forward + client 的顺序与退出回收。

这里的证据是 shell 和 CPU stub；未加载八个模型的真实权重，未运行真实模拟器或硬件。
SIGKILL 或主机掉电无法触发 shell trap，重启后仍需按运行记录检查残留进程。
详见[架构改进记录](../worklog/2026-11-16-architecture-improvement.md)。
