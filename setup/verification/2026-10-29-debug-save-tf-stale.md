# 2026-10-29 debug：保存阶段探索器持有的TF过期

症状：最终v3的irregular_arc seed0/1/3、angle180三例终态map_unstable/tf_stale；全部无目标与无Spin请求。原批次不重评分、不删除，不扩大1秒TF门限。

最小复现：按night/active-scan-ab-v3/plan.json的irregular_arc seed0扰动pose，运行check_exploration.py --scenario irregular_arc --spawn 0 --spawn-pose <plan中三个值> --seed 0 --active-scan-angle 180 --realism on --task-timeout 300 --timeout 460 --domain 90 --record --output NEW_DIR。必须指定新目录；一次结果不能保证调度时序确定复现。另单次observer-smoke-v3同seed也出现tf_stale，但未扰动pose不是等价复现。

证据在night/save-tf-stale-evidence.json和Linux原bag，读包命令night/read_save_health_bag.py全程只读，没有ROS发布。

- 传感器：/scan49条，最大源stamp间隔0.1062秒；/clock4857条，最大源stamp间隔0.001秒。
- TF：bag的map→odom241条，最大bag时间间隔0.023秒、最大源stamp间隔0.1062秒。探索器终态却持有age约1.176秒的TF，超过1秒门限。这一例没有证据证明SLAM的TF发布源阻塞。
- 里程计：无运动目标；原bag/odom留存，不能据静止结果推定运动漂移。
- SLAM：终态slam_alive=true，/map5条，最大源stamp间隔约1.002秒。不是进程退出证据。
- 定位：mapping阶段未启动AMCL。
- Nav2：任务启动前生命周期已active，无目标，不能归因于controller轨迹质量。
- 探索器：initial_observation因unknown_swept_space拒绝后进入saving，健康检查在保存/序列化过程中报告tf_stale；源数据新鲜不能代替本节点实际持有数据的新鲜度，停止仍是正确的保守行为。
- 评估：该次真值有效、终态及录包状态收到；没有利用真值补TF或回填completed。

可证伪剩余假设：前沿计算/序列化等待和单线程回调调度使消费者持有旧TF。若成立，应在相同种子/源码下观察到探索器回调/处理耗时尖峰，同时独立订阅的TF源持续更新。需要另立单变量计算/回调剖析试验，不能凭此直接改DDS/TF/SLAM参数或放宽时效。

本症状修复尝试0次。本夜保留为未解决；三例健康失败照常计入0/40。由于安全空间本身仍未知，无运动后的SLAM闭环质量证据，也不满足T6参数调优前提。

