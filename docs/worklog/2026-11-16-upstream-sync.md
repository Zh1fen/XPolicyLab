# 2026-11-16：同步原始仓库 main 到开发分支

## 目标与来源

用户要求跟进 fork 原始仓库的更新并合并到 dev。
开始时 main、dev、origin/main 都在 `6baccd57`，前几轮开发内容均未提交。
origin 最初为 `https://github.com/Zh1fen/XPolicyLab.git`；后按用户指令改为 `git@github.com:Zh1fen/XPolicyLab.git`。
新增 upstream 为 `https://github.com/XPolicyLab/XPolicyLab.git`。

## 操作与结果

- fetch origin 后确认 fork main 仍是旧版本；fetch upstream/main 得到 `f4a351dc`。
- 上游增加 4 个提交，仅涉及 CloudRobo_WM 与 GPT_6_Astra_Direct_EEF，均不在当前八个活动策略中。
- 本地开发文件先保存至 `artifacts/git-sync/20261116T073526Z/`，含 62 个文件的归档、binary diff 和元数据。
- 建立 `backup/dev-before-upstream-sync-20261116`，保存原分支提交位置。
- 使用 stash 暂存跟踪与未跟踪文件，再将本地 main 快进到 upstream/main，dev 快进合并 main。
- stash apply 成功，无冲突；逐文件与归档比较完全一致，保留全部未提交开发状态。
- 保留恢复用 stash：`8ce195131032d89685372835899b50dfb6d9c204`，未删除。
- 尝试 `git push origin main`，因当前环境没有 GitHub HTTPS 凭据而失败；origin/main 尚未更新。
- 用户确认 SSH 密钥已配置后，改用 SSH origin，验证读取成功，并成功推送 main：`6baccd57..f4a351dc`。

## 验证与交接

本地 main、dev、upstream/main、origin/main 均为 `f4a351dc`；远程 fork main 已同步。
当前在 dev，八策略稀疏视图保持。
45 项测试、工作区检查及 `git diff --check` 通过。未创建开发提交，未推送 dev。
SSH 后续拉取与推送使用 origin 的 SSH 地址，无需 HTTPS 登录。
再次恢复备份前先检查当前工作区，避免重复应用已有开发修改。

## 后续开发提交

用户随后明确要求提交并推送本地开发改动，提供 Git 提交身份后，在本仓库局部配置署名。
本批提交覆盖先前的 Pi_05 本地配方、八策略工作区、中文文档规范、公共环境与反馈接口及其测试，
不包含数据、权重、虚拟环境或运行产物。提交基线为 `f4a351dc`，提交与远程分支状态以 `git log` / `origin/dev` 为准。
