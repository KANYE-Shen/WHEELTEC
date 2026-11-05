# 2026-10-31 网页探索、接管与三挡

用户明确授权轮胎控制、使用现有探索算法，确认差速和无台阶平地；要求尽量跳过完整阶段一、最小修改UI。此前静止禁令不再适用。

## 交互与数据流

- “自主探索”：固定HTTP动作经SSH到车端，预检通过后切换自主速度源、恢复中挡、解锁最终watchdog，再启动已有wheeltec_explore。没有修改探索选点算法。依赖已运行的Nav2和安全链，不由UI启动底盘驱动。
- “远程接管”：取消本次探索，停车后按WASD自动申请手动控制；松键零速。自主期间WASD不送速度。
- Space：窗口捕获阶段处理，包含输入框、SSH终端和启动等待；先停车再取消任务/导航，只回远程等待，不自动重启。只读状态只能清理任务/租约，不能宣称底盘已停车。
- +/−：三挡限制为实际配置上限的30%/60%/100%。当前模板线速度0.03/0.06/0.10m/s，角速度0.09/0.18/0.30rad/s；每次探索启动恢复中挡。
- 速度路径：手动/自主分别进入/safety/manual_cmd_vel和/safety/autonomy_cmd_vel，经command_selector单一选择及挡位限速，再沿原有smoother、collision_monitor、最终watchdog进入驱动。

/scan和/odom都由网页通过ROS话题订阅。/scan为雷达驱动将硬件扫描转换成LaserScan；/odom为厂商底盘驱动读取下位机反馈速度后积分形成Odometry，不是网页直接读硬件，也不是用所发速度冒充反馈。/odom_combined为EKF融合结果。硬件负责原始测量，ROS驱动负责封装、计算和发布。

## 初次只读部署记录（由下文启用记录更新）

车端192.168.0.100，本轮手动目录/home/wheeltec/.wheeltec-console/trial-20261031；本机http://127.0.0.1:8766。仅管理owned-processes.json中PID、启动时刻和命令身份一致的本轮进程，未注册开机服务。

相机约30Hz，激光约10Hz/540束，原始里程计约20Hz；SLAM地图可显示，地图更新和TF有间歇过期及时间过滤丢帧，不能称为稳定导航验证。底盘反馈采集入口的速度订阅重映射为/trial_20261031/disabled_cmd_vel，无速度源；没有启动实车导航或探索。

用户报告车长0.30m、宽0.25m、最高0.25m、雷达离地约0.21m、差速。仅更新本轮TF雷达高度；其他厂家横向外参仍未独立测量，未标为完整校准。12秒零轮速反馈区间内EKF融合航向变化约-1.80度，原始里程计航向不变，IMU角速度有偏置迹象；保留原始证据，不以此宣布静态/运动标定完成。

实车adapter仍未提供robot-config，control.enabled=false。最终watchdog、安全链和驱动失效超时未部署/核实，制动距离与完整运动校准缺失；当前探索点击返回明确错误，不创建探索子进程。用户授权已取得，剩余问题是技术配置和实际验证。没有伪造hardware_verified、calibration_complete、制动距离或批准文件。

## 验证

- 后端单元：45/45；前端：13/13；既有安全测试：14/14；TypeScript及生产构建通过；新增入口py_compile通过。安全测试首次从根目录按模块名运行时导入路径错误，改用unittest discover -s robot -p test_safety.py后通过，没有改测试来消除错误。
- 浏览器隔离交互：7/7，任务/控制/终端写请求全部拦截，覆盖挡位、探索默认中挡、Space抢占启动、输入框/终端Space、WASD自动claim。不是实车运动证据。
- 隔离ROS域217：8/8，无驱动订阅者，验证启动hold、三挡实际输出、停车、速度源互斥、手动超时及禁止自动恢复。初版启动等待过短的失败记录保留。
- 真实SSH网页：5/5，实时相机/scan/odom/map、挡位元数据往返、未配置探索明确拒绝、远程/Space清理任务、无浏览器错误。只允许gear/stop/release请求；不代表实际车轮控制或制动通过。

原始结果及截图：C:\Users\30120\OneDrive\文档\ChatGPT\WHEELTEC\outputs\20261031-autonomous-trial，保留fixture-v1、ROS-v1等失败记录。关键证据为task-ui-fixture-final/results.json、selector-ros-result-v3.json、live-task-ui-final/results.json、live-task-ui-final/live.png、feedback-observation.json。

最终ROS图只读核查确认：/scan发布者lslidar_driver_node，/odom发布者wheeltec_robot，/odom_combined发布者ekf_filter_node；实际底盘订阅/trial_20261031/disabled_cmd_vel且无发布者，/cmd_vel及/safety/nav_cmd_vel也无发布者。最终部署后实际网页再次5/5。最后一次重启首次连接遇到端口尚未就绪，等待适配器返回真实/state后恢复连接，未修改SSH指纹或凭据检查。


## 后续实际启用与operator_timeout修复

用户明确批准跳过完整校准、实测制动两项启动限制，以最高0.10m/s直接启用；随后批准停车零速持续发布、等待解锁只续零速和Space独立请求，并在清空右侧近障碍后允许测试。使用supervised-live-session-v1；原严格validate及未配置只读行为保持，hardware_verified、calibration_complete、measured_braking_distance_m未伪造成已通过。

实际链路：manual/autonomy → selector → smoother → collision_monitor → watchdog → /console/driver_cmd_vel → 独立overlay厂商驱动。最终话题只有watchdog发布、wheeltec_robot订阅。驱动补丁增加steady-clock 0.3秒无新命令归零，串口读取等待50ms并检查读取长度；隔离域217假串口实测约0.352678秒归零。这是驱动进程软件保护，不是MCU独立超时，也不是实测制动距离。

原collision_monitor停车零速只发1秒，久停后watchdog无法取得新鲜零速以解锁。获批准后改为86400秒，仅延续零速。等待源/arm确认时允许持有租约的零命令续期；非零仍须manual+arm确认。200ms指令节拍减少SSH排队，仍按住的待处理按键最多等待3秒，松键/Space立即清除。Space并行独立HTTP请求，任务epoch拒绝停车前排队的claim/command。非零0.5秒TTL、碰撞保护、失焦/断连停车及0.10m/s上限保留。

SLAM独立运行，控制launch以start_slam=false避免重复；实时配置throttle_scans=2、minimum_time_interval=1.0、minimum_travel_distance=0，降低积压并保留原地观测。重启前旧栅格另存map-before-rate-adjustment.json，未覆盖latest.json。相机640×480约10Hz，长时间内存增长尚未完成验证。scan/odom/map/TF仍按源时间校验；曾出现tf_stale及message-filter丢帧，不能称为全时稳定。

最终验证：

- 后端51/51、前端13/13、既有安全测试14/14；TypeScript与生产构建通过。隔离浏览器9/9，新增1.5秒延迟解锁只续零速，以及等待中Space取消后不恢复。所有写请求拦截，不控制实车。
- 真实网页v4（0.03m/s、650ms）、v5/v6（0.06m/s、1秒）均5/6：解锁、指令和Space通过，短时浏览器里程计响应检查失败。保留失败，不改门限。v4原始odom为零，v5峰值仅0.001m/s。
- v6的25秒独立ROS订阅包含用户后续操作，原始/odom峰值0.061m/s；用户先报告短测没有转动/声音，随后确认“网页端远程接管没问题”。支持遥控可用，不能将后续用户运动写成自动化一秒测试通过。
- Nav2 controller/planner/bt_navigator/smoother/collision_monitor/map_saver均active，NavigateToPose、Spin就绪，探索模块可导入。最后8秒地图TF采样387条，源年龄约−0.117至0.535秒，位姿年龄约0.122秒；前一快照tf_stale也保留。自主入口已接通，但未代用户启动完整自主任务，不宣称探索成功或地图精度达标。
- 最后快照为用户网页手动操作（高挡、manual、armed），未为交付抢占或改变其状态。未注册自启，仅管理本轮拥有的进程。

证据根目录仍为上文outputs/20261031-autonomous-trial。关键文件：delayed-arm-ui-fixture-final/results.json、live-control-enabled-v4/v5/v6/results.json、enable-live/audit-live-control-v4/v5/v6.remote-result.json、enable-live/check-live-readiness.remote-result.json、enable-live/observe-runtime-final.remote-result.json。先前只读5/5与隔离ROS8/8不和实车结果合并。
