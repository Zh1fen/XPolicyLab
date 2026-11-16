# 策略工作区

按用户确认，日常保留八个入口：`GR00T_N17`、`TinyVLA`、`FastWAM`、`LingBot_VA`、
`LingBot_VLA`、`StarVLA`、`Pi_05`、`demo_policy`。保留不代表已经在本机验证通过。
其中 `demo_policy` 用于公共协议与形状检查，`Pi_05` 已有本地运行资产；模型复现顺序另行确定。

其余 70 个 adapter（含 ACT、DP）保存在 Git 中，用 sparse checkout 收起，默认搜索不会遍历它们。
这是工作区视图，不是代码删除；新 clone 需要手动应用一次。

从仓库根目录运行：

```bash
python3 scripts/policy_workspace.py status
python3 scripts/policy_workspace.py list
python3 scripts/policy_workspace.py focus             # 八个默认入口
python3 scripts/policy_workspace.py focus Mem_0        # 默认入口 + 指定参考策略
python3 scripts/policy_workspace.py full              # 恢复全部，不回滚本地修改
```

默认集合在 [configs/policy_workspace.json](../configs/policy_workspace.json)。
收起前，脚本检查待收起策略下的已修改、未跟踪、被忽略文件；有本地内容就拒绝收起。
权重、虚拟环境、结果不搬动。临时展开某个策略后，再执行 `focus` 可恢复默认视图。

阅读 [项目入口](../docs/README.md)、[当前状态](../docs/STATUS.md)；模型命令以各 adapter README 为准。
