# 0006：运行发布、执行快照与模块所有权

- 日期：2026-11-16
- 状态：采用
- 依据：[架构改进指南](../architecture-improvement-guide.md)

使用 evaluation/ 承担公共评测规则及持久化执行，web/ 专注 HTTP 与展示。保留旧导入 facade 和所有已有启动命令。
后端通过 describe/normalize/freeze/execute 声明行为，运行队列通过小范围 ExecutionContext 调用它们。

每次提交冻结配置，完成参数和快照文件后才发布数据库行。领取采用 SQL 事务内的 FIFO 查询及状态转换；
历史分页不影响队列。终态由存储层决定，解决取消与完成竞争；异常重启保留结果，不自动恢复实际动作。
依赖文件变化时明确失败。无可靠快照的旧排队记录需用户显式重提，终态记录继续可读。

公共输入处理抽到 utils/episode_input.py，版本专有 writer 与指令优先级留在转换器。
机器人元数据由 utils/environment_config.py 统一读取父工作区；训练 shell 的独立本地表路径保持。

服务入口共用 client_server/service.py，根入口仍要求有效端口，ws 模块保留 null→19000 的默认行为。
公开类型使用统一的模块身份；兼容别名不抢占 vendor 自己的 utils 包。
八个活动 adapter 共享已创建进程的生命周期，专有服务与依赖仍由 adapter 管理。

验证、兼容矩阵和未验证的模型边界见[工作记录](../worklog/2026-11-16-architecture-improvement.md)。
