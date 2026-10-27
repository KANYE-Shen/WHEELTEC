# 现实化启动及首组 A/B

seed=0，baseline/spawn0，同一配置，0× 与 1×。原始运行均保留在 Linux data/runs/20261027-t4-{A,B}-scale{0,1}-baseline0；result.json 保存源文件逐项 SHA256。

传感器：两组 scan 945/946、odom 2778/2783 条；TF 有 odom→base_link；SLAM 无 map。可证伪假设：生成 YAML 中量程整数类型使 SLAM 崩溃，日志应出现 InvalidParameterTypeException。两组 launch.log 均见 max_laser_range double/integer 冲突及退出 -6。定位/规划无地图，探索未启动，评估失败；未调整门限。下游精度不具备可评条件。

回归先断言生成 SLAM/Nav2 量程是 float，5项中1项失败；生成器显式转换 float 后5/5通过。对应修复次数1。

同种子重跑 A2/B2，SLAM 和 TF 正常，真值有效，两组均 incomplete、0个目标；覆盖84.10%/84.40%，墙面双向95分位2.291/0.921 m，轮廓覆盖49.06%/67.67%。均未达到原门限。未产生计划，bag 缺 /plan 也记录失败，不删除失败。启动故障已修复，不等于探索已通过。

当前假设：有限视场使机器人起始足迹附近仍未知，严格安全膨胀及0.15 m起点吸附找不到安全连通起点。需用记录的栅格计算起点与安全集合距离后验证；不得扩大吸附距离或允许未知导航。若成立，应通过原地安全观测补图，再在同批种子上 A/B。

本机静态原生 lidar 噪声实验：80帧/组，σ=0测得0，σ=0.05 m测得0.0493972 m。原始数据 data/runs/20261027-native-lidar-noise/result.json。没有实车数据，传感器真实性未验证。

参数来源、模型限制和复现入口见 simulation/realism.md。CPU 数值为 WSL 参考，不能推断板上性能。
