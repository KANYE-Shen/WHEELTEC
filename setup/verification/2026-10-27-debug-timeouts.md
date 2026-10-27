# ROS时间与任务预算误标修复

T3在修改前有3条预期失败：墙钟前进但ROS暂停仍消耗预算；任务预算到期没有保留task_timeout；position接受陈旧TF。修复后3项通过，26项探索纯算法和实际ROS健康跳变回归通过。原始红绿日志保存在Linux data/runs/20261027-regressions/t3-*。

复现：加载ROS后运行simulation/test_explorer_time_ros.py、simulation/test_health_ros.py及src/wheeltec_explore/test中的unittest。输入时钟由测试显式控制，暂停不消耗任务预算；开始时间在首次非零ROS时间建立。外层评估器仍有独立墙钟进程上限，防止仿真时钟停止后试验无限挂起；墙钟仅用于进程监督和耗时记录，不再参与探索策略超时。

参数集中在src/wheeltec_explore/wheeltec_explore/defaults.py，均可由同名ROS参数覆盖。原0.30/0.35/0.6/0.15值保持不变，分别按访问半径、安全半径、接近搜索半径与起点吸附/返航容差命名。MapHealth和纯算法共用该源，不修改独立评分门限。

position检查TF源时间戳，过旧、过度未来、非有限位置返回None；check_sensors同时核查map、scan、TF与SLAM存活。总预算结束被明确保留为task_timeout，不再在地图等待分支误标map_update_timeout。实际地图停更由MapHealth阻断并产生map_unstable。完整多种子A/B仍待T5，当前只证明回归用例与ROS适配行为，不宣称任务成功率改善。

## 首次在线回归的启动竞争

20261027-t3-D-recess1未通过：90秒初始化超时、0个探索目标。传感器/TF过程记录189帧、37版地图且issues为空；地图、scan、TF最终年龄均新鲜，SLAM节点图存活，odom未运动、AMCL不适用。健康报告保留map_stamp_invalid={stamp:2.7,received:0.0}，证明持久化map先于首条clock到达，而非SLAM停更。假设：未初始化ROS时间参与未来时间比较导致永久误锁；新增回归在原实现失败。修复只在received<=0时不接纳该样本，等待有效ROS时钟后正常检查，不放宽有效时钟的年龄门限。首次失败及缺少地图成果、plan消息的评估失败全部保留；同配置第二次回归使用20261027-t3-D2-recess1。本症状修复计数1。

同配置D2已完整结束：正常探索后按300个ROS秒预算保存与返回，state=incomplete、reason=task_timeout、failures=[]。该次只证明初始化竞争与原因归属修复，不是独立验收通过。D首次失败继续计入本轮新增实跑总数，不以D2替换。
