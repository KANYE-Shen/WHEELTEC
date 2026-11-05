# 自主重试：地图校正参考点

真实任务 1793520313357531076 在约65.19秒以 map_unstable / map_to_odom_translation_jump 结束，仍是失败记录。最新原因、时间线、缺失证据与修复边界见[详细诊断](../../setup/verification/2026-11-01-debug-map-correction-reference.md)。

已停车复现原度量依赖 odom 原点的缺陷，并完成两个探索器方法的最小修复、61项本地回归、115秒候选静止验证及部署后30秒真实路径复核。未启动探索或导航，完整自主待用户网页发起。原任务的前后原始TF缺失，不能把.611m全部认定为误报；watchdog故障时间窗的timeout_detail也没有历史样本，不补造。

先读case.json，再核对failed-task原件与manifest.json。stationary-corrections.json为真实停车采样，recorded-correction-ab.json含对同一组实测TF的等价坐标变换，不是移动小车或重放动作。脚本和旧PID只作证据，回退/采样须重新核对当前停车条件；本目录不自动执行动作。
