# 2026-10-31 watchdog_arm_failed 与自主回退：安全链进程恢复

用户再次报告自主启动回远程，随后报告手动也提示 watchdog_arm_failed。沿用用户已批准的 SSH 修复范围：保持停车，agent 不解锁、不启动探索、不发运动指令。

## 故障证据

首次只读 12 秒观察：选择器约 50Hz 输出零速，但 /safety/smoothed_cmd_vel 和 /safety/collision_cmd_vel 收到 0 条消息；最终 watchdog 在线、disarmed/operator_hold。碰撞监控生命周期和参数请求超时，controller_server 生命周期不可用，相关进程仍存在。故障属于安全指令流未到达最终 gate，不能据此认定底盘电源或轮胎硬件坏了。部分 1 秒服务发现超时可能由发现延迟造成，不能仅凭一次 unavailable 判定进程死亡；这里同时有整段指令流缺失证据。

内核记录 15:43:27 相机进程 28821 因 OOM 被杀，anon-rss 约 5.55GB。该记录能证明先前相机内存耗尽，但尚未证明它是所有 Nav2 不应答或 TF 故障的唯一根因。

## 恢复与范围

两次确认 remote、hold、无控制者、watchdog 新鲜且未解锁、输出全零后，核对 control_stack PID45515、start_ticks、cmdline、进程组，停止该自有 launch 并等待所有原组成员退出，再按原命令启动新组 PID107433。原启动器对未及时退出的旧子进程执行了 SIGTERM/SIGKILL；没有遗留旧组副本。新命令明确 explore:=false、start_slam:=false，watchdog 启动保持锁定。保留 driver PID34738、SLAM PID101025 和当前地图，未修改算法或速度、TF、心跳时效门限，没有自动恢复运动。

车端证据目录 trial-20261031/stack-recovery-1793436160924227247 保存 before-state、原进程身份、组成员和新日志。

## 当前验证

恢复后的只读采样先等待发现，再连续观察10秒：smoother 201条、collision 100条、最终驱动命令501条，所有观测速度均为零；97次采样三段指令流全部在0.5秒时效内，最大接收年龄分别0.059、0.114、0.023秒。速度平滑器、碰撞监控、控制器、规划器、BT导航器五个生命周期均 active。最后 remote/hold/disarmed，原始odom速度为零。用户随后明确确认“已能远程控制”。这证明运行时安全链和用户手动控制恢复，不是完整自主任务验收。

自主回退仍需用户本人保持网页前台点击复核；agent 只被动采样。现有网页 window.blur/hidden 会请求停车，返回聊天本身会触发该保护。新 Nav2 日志仍有全局代价图的激光TF消息过滤记录，不能凭生命周期 active 宣布导航或探索成功。长期运行稳定性尚未验证。

本机原始记录位于 outputs/20261031-autonomous-trial：diagnose-stack-faults.remote-result.json、recover-stack-stopped.remote-result.json、verify-stack-recovery.remote-result.json、observe-operator-retry.remote-result.json。前期同名短时采样结果后来由复核覆盖，恢复前的0条观测数在本记录及本次工具日志中保留；原车端日志仍保留。


后续已部署分项超时证据与约10Hz状态限频；进一步完成 SLAM 静止去重、单槽扫描队列饥饿修复及双端地图 Reset。最终共同负载位姿132/132（车端）和194/194（网页）有效、2000条驱动命令全零。不是实车自主任务验收；完整故障对照和最新状态见2026-10-31-debug-map-reset-and-slam.md。
