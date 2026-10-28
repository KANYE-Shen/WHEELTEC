# 2026-10-28 debug：探索器终态漏收

环境：WSL ROS2 Humble、Gazebo Fortress，localhost域90（单次复验89），实车已断开。原始目录data/runs/20261028-active-scan-ab-v1、v2，各source SHA在plan.json；源代码快照保留night/active-scan-frozen-source-v1/v2.zip。没有删除失败或修改独立验收门限。

## 最小复现与证据

v2/002_irregular_arc_seed0_angle180：场景irregular_arc、seed0、realism=on、angle180、300秒任务预算、460秒监督预算；配对扰动pose见plan.json，不用未扰动pose替代。

运行paired_active_scan_batch.py相同参数能保留同批种子的有/无漏收结果。症状是explore.log已有starting→exploring→initial_observation→saving→returning→incomplete，约1.07秒结束、rc=2；评估器explorer={}、status_history=[]，bag根本没有/exploration/status消息。不能称为探索器崩溃。

分层：
- 传感器：该包/scan56条、/clock5571条，未见所有传感器停流证据。
- TF：/tf424条、/tf_static1条；ProcessCapture有新鲜估计pose，起始/终态年龄见原result/process。
- 里程计：/odom163条；本案无动作请求。不能把零行驶距离当作里程计运动精度测试。
- SLAM：/map5条，探索日志已完成地图保存；未证明SLAM故障。
- 定位：mapping阶段未启动AMCL，不以AMCL协方差解释。
- Nav2：本案在生命周期检查通过后才启动Explorer；另v1两个Nav2未激活试验单列，不能混同。
- 探索：日志及独立原子map.exploration.json确认incomplete/active_scan_clearance_unproven，motion_requested=false。
- 评估：无任何status回调，recorder也未记录该话题；状态发布器存活约1秒，订阅发现/匹配尚未证实。保存文件仅诊断，不回填为ROS收到消息。

## 可证伪假设与修复

H1：退出后只排空20次回调不足，因为高频/clock会使20次远小于1秒。若仅此原因，改为1秒单调时钟截止后，同种子应不再漏收。先写失败测试，再实现drain_terminal_status；单元通过，但v2仍出现完全零状态消息，H1不能充分解释。v1原40次保留；v2部分批次经精确匹配PID发送SIGINT停止，当前子评估器自行清理其仿真。中断记录v2-interruption.json，不能把未执行种子算成功或用剩余缺失值计算有利比例。

H2：短寿命发布器未等状态消费者完成DDS匹配。若成立，记录模式要求发布器匹配capture+recorder共2个订阅后才开始任务，应消除“已启动Explorer但两路均零状态”症状。新增expected_status_observers，默认0不要求评估器；harness显式传record时2、否则1。初始化超时就失败并不启动探索，不调DDS/SLAM/Nav2参数，不放宽任务或几何门限。3项先失败回归后实现；实际同种子复验结果在observer-smoke-v3.log及下一冻结批次。若依然失败，不宣称已经解决，继续按证据定位；第三次无效后停止并写剩余假设。

取消旁路问题另有独立回归：等待Spin响应期间健康异常时，原代码未注册晚到响应的取消回调。用离线future夹具复现1/6失败；修复后6/6及新增两项pending清理测试通过。这不是实际Nav2旋转/制动验证；active_scan仍仅仿真、默认关闭。

## 结果边界

v1严格0/40、0首目标；保存终态38个incomplete，2个Nav2启动失败。10个baseline无目标，28个主动扫描因未知扫掠空间拒绝，0运动请求。wire终态缺12个中包括上述2个未启动。不能将采集协议修复后仍失败的探索任务包装成算法成功；也不能以未知格改为空闲来启动。

