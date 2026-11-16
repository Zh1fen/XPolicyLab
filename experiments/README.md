# 实验记录

这里提交可复现的运行说明、配置快照和小型结果，不提交视频、权重、数据集或完整日志。
新实验创建 `experiments/<run-id>/record.md`，从 [实验模板](../docs/templates/experiment.md) 复制。
run-id 建议为 `YYYY-MM-DD-model-benchmark-variant`；后续重跑使用新 run-id。

结果产物放外部存储或 Git 忽略的 `artifacts/`、`logs/`、各 adapter 的 `eval_result/`；
记录明确位置与标识。旧文件只有在配置、预算和 provenance 补齐后，才能作为正式复现证据。

当前还没有可声明为正式基线的实验记录。Pi_05 已有资产的清点见
[复现手册](../docs/reproduction/pi05-libero.md)。
