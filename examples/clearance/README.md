# Clearance demo

这个内置演示不是 BlindAssist 研究结论，只用于验证 DiscoveryOS 的机制闭环。

候选修改四个受限参数：风险阈值、尺度、偏置和因果平滑系数。硬约束是 `false_clear <= 0.08` 和 `latency_ms <= 2.5`；可行候选再按冻结的 `false_block → clearance_mae → temporal_jitter → latency_ms` 字典序规则选 winner。

Development 和 final-blind 数据由不同种子生成。Discovery 命令不会产生任何 G7 收据；Certification 命令也不能改写已经冻结的 winner。
