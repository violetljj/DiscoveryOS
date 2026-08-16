# 架构与路线图

## 不可越权的三条平面

| 平面 | 当前权威 | 能做什么 | 不能做什么 |
|---|---|---|---|
| Evidence | frozen evaluator + split binding + receipts | 产生可重放观察 | 自己修改协议或 claim |
| Search | operator + safe racing + Pareto | 选择下一笔资源 | 读取 final blind 或宣布科学胜利 |
| Claim | GateEngine + contract ceiling | 限制可声明范围 | 把 scheduling utility 当作 verdict |

系统中的 scalar 只允许用于调度。协议违规、mechanics failure、hard-constraint failure、科学结果和 claim ceiling 分开记录。

## 当前代码边界

```text
src/discoveryos/
├── contracts/     # frozen schemas, codecs, protocol admission
├── graph/         # hypothesis/component/strategy/claim nodes
├── evaluation/    # evaluator registry, hard gates, Pareto, replay
├── operators/     # bounded random-search operator; future portfolio hook
├── memory/        # semantic delta and progressive context
├── runtime/       # artifacts, SQLite ledger, split vault, async scheduler
└── domains/       # executable domain packs
```

顶层模块通过 `CandidateSpec`、`ExperimentSpec` 和 `EvidenceRecord` 交互。evaluator digest 与 data digest 都被冻结进证据；同一个 experiment 只能拥有一条 create-once receipt。

## 下一批实现顺序

1. **R0.2 生产隔离**：final-blind 独立服务身份、一次性认证票据、shadow 聚合反馈与查询预算。
2. **R1.1 搜索组合**：Random/ASHA/BOHB、Local Patch、Structural Rewrite、统一 operator result schema、repair queue。
3. **R1.2 图搜索**：Hypothesis/Component effect ledger、分支预算、cross-branch transfer、自动消融、failure signature library。
4. **R2 策略层**：contextual bandit、停滞检测、受限 Meta-Strategy admission。
5. **R3 领域和计算**：BlindAssist domain pack、远端 GPU/device worker、checkpoint/cache、部署 parity。
6. **R4 学习型 Advisor**：只使用通过复验和消融晋升的轨迹训练 promotion/operator policy。

每阶段都必须用独立 benchmark 证明增量价值；mechanics smoke、单 seed 或 development improvement 都不允许升级成算法优越性、安全性或产品结论。
