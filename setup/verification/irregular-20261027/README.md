# 不规则边界试验的小型证据

阅读顺序：上级目录2026-10-27-irregular-frontier-results.md → raw-outcome-index.json → 各summary和失败诊断。完整bag、process.json、launch/explore日志及冻结plan/source位于WSL `~/wheeltec_sim_ws/data/runs/20261027-irregular-*`，没有复制大体积原始数据进源码仓库。

- raw-outcome-index.json：45次真实仿真，原始result哈希、raw与strict结果、保存/实时指标分别记录；strict统一追加launch子进程强杀拒绝，raw保持不变。
- mechanism-summary.json / replay-summary.json：60对合成单步输入、65个预定历史ROS时点（49有效）；均不等于整屋探索成功率。
- checks-summary.json：10组84项回归全部通过，指向Linux各组原始日志及哈希。
- startup-audit.json：on批次40份首末快照的独立EDT起步阻塞证据。
- replay-regression-analysis.json / saved-quality-replay.json / recorded-selector-profile.json：保留全部局部退化与保存工件反例，隔离函数计时不等于板上并发负载。
- runtime-reproductions-summary.json：4个原运行时症状各复现一次，均未重现原症状，停止猜测修复；不替换原批次。
- nominal-runtime-context.json / environment-audit.json：父进程CPU限制与隔离测试域末次存活检查；日志中的3次嵌套强杀仍算异常。
- scheduler-proof.json：04:00任务登记证据，实际到点触发未验证。credential-scan.json只保存模式扫描计数，不保存凭据。

同目录Python文件为审计、作图与复现脚本。collect_results.py只读取原始result，派生索引可重建；run_checks.py要求新输出目录。reproduce_runtime_failures.py冻结了一次性路径，重跑会拒绝已存在目录，应先明确制定新实验而非覆盖。analyze_replay_regressions.py默认只生成分析，只有显式--export-fixture才写小型测试fixture。所有新运行必须隔离仿真域，不是实车运动授权。
