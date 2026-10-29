# 多种子配对回归

当前默认全部7布局、每布局3命名起点、每格5种子，共105次；旧5布局基线为75次；默认realism=on和1×强度。起点扰动x/y各±0.03m、yaw±0.06rad由scenario/spawn/seed的稳定哈希产生，跨强度完全相同。几何检查发现不安全起点时拒绝整项计划，不筛掉不利种子。

```bash
python3 simulation/regression_batch.py --output ~/wheeltec_sim_ws/data/runs/NEW --scales 1
python3 simulation/regression_batch.py --output ~/wheeltec_sim_ws/data/runs/NEW-noise --scenarios baseline --spawns 0 --scales 0 0.5 1 2
```

输出plan.json冻结试验与源码哈希，summary.json仅为衍生视图，每次原始目录/日志/bag保留。源码改变则停止批次；resume要求原计划和源码哈希一致，不能原地替换失败。缺失/损坏结果按失败纳入已执行分母；汇总同时报告planned/executed/complete，不能把未完成批次写成完整成功率。

每格输出通过率与Wilson95%区间；至少五种子，0/5区间仍为0–43.45%，不能解释成泛化概率已确定。当前7布局四档全矩阵为420次，未完整执行；历史5布局实际执行75次1×基线及代表起点20次四档扫描，两批均未通过。详情见setup/verification/2026-10-27-regression-results.md。

代码回归：python3 -m unittest simulation/test_regression_batch.py simulation/test_validation.py，共30项通过；实际仿真全部失败继续保留，纯测试不替代任务验收。
