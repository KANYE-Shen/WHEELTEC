# 2026-10-31 自主启动立即退出：本地修复记录

## 当前操作边界

用户最新要求：只做本地核查和修复，不移动小车，离开期间不做现场试验。本记录之后的启动修复仅在本地，未上传车端、未启动自主、未发送运动指令；不能自动恢复此前运动授权。初期只读SSH诊断及诊断版适配器部署发生在此限制之前。

## 已证实的故障链

本地保存的observe-auto-transition.remote-result.json记录：1793426363.587为starting；1793426363.934为autonomous、自主速度源和watchdog已解锁；1793426364.111因tf_stale退回remote；1793426364.325最终hold、disarmed。探索子进程此时尚在Python/ROS初始化，收到SIGINT，日志出现KeyboardInterrupt。不是探索完成，也不是没有前沿的结论。

原tick用tasks.remote()处理安全故障，该方法清空error；随后software_stop/operator_hold覆盖故障显示，用户只看到远程模式。连接接口的“SSH or adapter connection rejected”是通用连接尝试失败日志，不能单凭它断言此次自主退出由SSH导致；采样时SSH、适配器可访问。

TF独立采样中odom_combined→base_footprint源年龄约0.015–0.116秒，map→odom_combined约−0.095–1.389秒。网页激光按scan源时间查询map变换时多次需要向未来外推，某次差约2.69秒；这与瞬时TF/处理延迟一致，但尚不能确定引发那次安全blocker的具体边和上游根因。适配器约99%单核CPU、SLAM约81.5%单核CPU为当时观测，不能据此单独判定CPU饱和是根因。保留原始源时间，不通过放宽门限、重打时间戳或跳过TF保护掩盖问题。

## 已完成的代码修复

1. TaskController保留预检失败和安全停止原因。显式Space/远程动作仍可回远程等待；安全停止会带原因，适配器另写console.task日志，避免后续状态覆盖原始故障。
2. TF失败记录target/source、源年龄或lookup异常。诊断版已在用户限制前部署；不会因此放行失效TF。
3. 本地版把动态地图/TF/Nav2检查移到异步启动线程：先确认最终watchdog已停车、速度源为hold，再等待连续0.5秒健康，最长5秒。等待失败显示最后原因；只有通过后才切自主源及解锁。Space/任务代次取消始终有效，不在后台无限等候或自动恢复。启动等待不输出运动。
4. 探索选点算法、碰撞阈值、非零TTL、最高速度、运行时TF失效停车规则均未更改。未调整SLAM参数、未重启SLAM或覆盖用户地图。

第3项及持久日志目前只有本地源码，尚未在车端生效；第1项和基础TF诊断在限制前已有诊断部署。不能把本地检查通过写成实车自主已修复。

## 本地验证

后端56/56通过。先红后绿的新增场景：安全停止原因保留；TF只有一次新鲜不能启动；恢复需连续健康窗口；等待中Space取消；预检失败留在状态。既有控制、所有权、断连、Space抢占和三挡测试继续通过。修改入口语法编译、diff格式检查通过。没有进行新的实车测试。

## 尚需恢复现场条件后核验

连续采样具体失败TF边、接收年龄、源年龄及lookup异常，判断是上游发布/处理延迟还是适配器积压；本地启动逻辑不能代替修复这个上游问题。后续部署须在用户更新“仅本地、不移动”限制后进行。部署前保留当前地图和原始失败；先零运动核查，再由用户明确发起现场探索验证。完整自主任务仍未通过，不自动启动来验证。

原始证据目录：C:\Users\30120\OneDrive\文档\ChatGPT\WHEELTEC\outputs\20261031-autonomous-trial。关键文件observe-auto-transition.remote-result.json、diagnose-autonomous.remote-result.json、diagnose-tf-edges.remote-result.json、read-tf-diagnostic.remote-result.json。后续同名诊断结果可能是再次只读采样，原任务目录和进程日志保留。


## 继续本地修复：合并TF缓存与接收时效更新（待部署）

旧适配器同时使用TransformListener和自己的/tf、/tf_static订阅。Buffer更新与tf_edges更新来自两套独立回调；即使Buffer已收到新鲜变换，时效记录回调尚未执行也会被tf_chain_fresh拒绝。这是本地可构造复现的回调次序缺陷，车端单核高占用使该缺陷值得修复，但不能据此断言它是实车所有tf_stale的唯一原因。

新增console/target/tf_buffer.py的TransformReceiptTracking，沿用同一个TransformListener：在同一接收回调、同一锁内先更新Buffer，再记录该变换的单调接收时刻。删去两条独立TF订阅，避免缓存与时效记录错位及重复回调。没有更改1秒TF时效规则、源时间校验、静态变换含义、运行时停车或速度上限。

验证：后端60/60；本机WSL真实ROS2 Humble Buffer和适配器实际transform方法6/6。分别证明分离回调可拒绝已存在的新鲜Buffer、合并更新后接受新鲜odom、静态laser零时间戳可用、刚收到的旧源时间仍拒绝、动态停更仍拒绝、其他动态边失效不影响静态几何。ROS验证仅内存Buffer，无rclpy.init、无节点、无发布者、无实车连接。构造回归不能代替实车复验。

本地验证脚本与输出：outputs/20261031-autonomous-trial/verify-tracked-tf-local.py、tracked-tf-local-result.json。此补丁连同前述启动稳定窗口仍未部署；用户“仅本地、不移动”限制持续有效。后续部署必须同时包含adapter.py、tasks.py和新增tf_buffer.py，避免缺模块；应仅在已停车、无自主任务时更新自有适配器，保留当前源码备份与任务/地图证据，不启动探索来验证。


## 用户随后批准SSH部署，仍禁止启动探索或移动车辆

用户明确答复“允许SSH部署，保持停车，不启动探索”。部署前两次核查remote、disarmed及新鲜watchdog，并核对本轮适配器PID、start_ticks、cmdline、进程组。备份后更新adapter.py、tasks.py、tf_buffer.py。新适配器PID99574；首次10秒就绪等待未通过，后续只读检查确认进程已上线，并保存首次失败，不把它改写为首次通过。原始源码备份位于车端trial-20261031/deploy-tf-fix-1793434952696449300/before。

部署后首次35次静止采样控制链tf_stale为0、始终停车，但地图位姿仅3/35可用。SLAM日志显示扫描落后约6–12秒，不能仅凭控制链通过宣布自主可启动。进一步将旧栅格及完整序列化图保存到车端trial-20261031/slam-recovery-1793435299676505896：previous-map.posegraph 97896556字节，previous-map.data 85951198字节，另有map-before.json、旧配置及进程命令。保存成功后才停止自有SLAM，保留旧图供恢复，没有覆盖latest.json。

新建图会话PID101025，扫描队列20→1，minimum_time_interval 1.0→0.5秒，throttle_scans仍2；minimum_travel_distance仍0以保留纯转动观测。实时地图因此属于新的会话，旧图为上段归档，并非无损延续旧图。Humble源码默认队列1，TF使用扫描源时间加transform_timeout；本轮没有启用restamp_tf，见[官方实现](https://raw.githubusercontent.com/SteveMacenski/slam_toolbox/humble/src/slam_toolbox_common.cpp)。配置同步到robot/config/slam.yaml，仿真配置不改。本次包含会话恢复和参数调整，不是单变量A/B，不能证明唯一根因或长时间性能已根治。

恢复后35/35位姿可用、0次控制链tf_stale、35/35停车。另发现先前相机已被Killed且自有PID不存在；沿用原10Hz命令恢复相机PID101550，不安装新服务。最终共同负载下再采样35次：35/35位姿、35/35相机接收、35/35新鲜watchdog，控制链tf_stale为0，remote/hold/disarmed，目标及输出均零。末帧位姿年龄约0.087秒，scan约10Hz、odom约20Hz、相机接收约10Hz、地图约1Hz。三份车端源码SHA256与本地通过60项测试的源码完全一致。

仍有单帧激光向地图投影因最新odom尚未到达而暂时无法按源时间查询（末帧差约0.026秒），该次laser_pose留空，不用最新姿态冒充该帧源时间姿态；位姿及控制TF正常。长期图规模/相机内存增长仍需后续验证。没有启动自主进程、没有实车运动验证，不能据此宣称完整探索通过。

最终证据：deploy-tf-fix-stopped-result.json（保留首次就绪失败）、inspect-tf-deployment.result.json、verify-tf-deployed-stationary.result.json（位姿3/35）、recover-slam-stationary.remote-result.json、verify-tf-after-slam-recovery.result.json（位姿35/35）、restore-camera-stopped.result.json、verify-tf-final-with-camera.result.json（共同负载35/35）。后端60/60及本机真实Humble Buffer6/6为代码验证，与上述车端静止结果分别列示。
