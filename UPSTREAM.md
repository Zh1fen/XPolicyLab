# 来源与致谢

RoboLab 基于 [XPolicyLab](https://github.com/XPolicyLab/XPolicyLab) 继续开发，
复用其策略 adapter、通信协议、数据处理、checkpoint 解析与 benchmark 接入代码。
本地当前同步的上游基线为 `f4a351dc`，对应仓库的 Git 历史可追溯原始作者与改动。

本分支新增了研究工作区管理、中文文档与实验记录规范、统一环境反馈接口和本地控制台。
“RoboLab”是本分支的产品展示名，不代表上游团队的官方发行版。

## 许可证与原始作者

根 [LICENSE](LICENSE) 保留上游 Apache-2.0 文本。各 policy 中 vendored 模型的许可证、
版权头、原始贡献者和论文来源保持原样，以对应目录的文件为准。
不将上游获奖、项目负责人、合作机构、排行榜成绩作为 RoboLab 自身的资历展示。

## 兼容命名

现有 `XPolicyLab` Python 导入名、checkout 路径、环境变量及协议标记仍按原接口保留，
包括 `XPL-RGB1` 图像标记与现有服务的标识。它们是兼容契约，品牌整理不会改写编码格式或批量重命名模型源码。
Git 远程仍指向实际存在的 fork 与 upstream，仓库托管名称不在本轮自动修改。

## 上游引用信息

以下条目来自上游原 README，保留供使用其工作的研究引用参考；不作为本分支的新论文信息：

```bibtex
@article{community2026xpolicylab,
  title={{XPolicyLab}: A Unified Standard and Open Ecosystem for Robot Policy Evaluation and Deployment},
  author={Community, XPolicyLab and Chen, Tianxing and Chen, Yue and Nian, Tian and Cai, Zijian and Chen, Guangyu and Lin, Wenwei and Liang, Qiwei and Xiang, Peicheng and Su, Kailun and others},
  journal={arXiv preprint arXiv:2608.09892},
  year={2026}
}
```
