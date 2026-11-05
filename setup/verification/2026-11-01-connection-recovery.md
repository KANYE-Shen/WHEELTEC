# 2026-11-01 热点重连与停车恢复核查

用户重新连接小车热点，要求确认连接，准备由用户点击自主探路。本次更新此前“仅本地、准备断电”范围：允许 SSH 核查和必要停车恢复；agent 未启动自主、未解锁或发送非零指令。

## 发现与恢复

- WLAN 192.168.0.248，小车 192.168.0.100，固定主机指纹 SSH 成功；本地 127.0.0.1:8766 服务继续运行。
- 小车已重启约 6 分钟，系统时间退回 2000 年；旧 owned-processes 中所有组件均不存在。检查实际进程与串口设备后，先以电脑时间校时。
- 保留旧进程记录到车端本次 reconnect-* 运行目录（路径见 reconnect-current.json）；先恢复雷达/相机/模型/EKF，以及 start_slam=false、explore=false 的控制栈。
- 底盘启动前订阅核查：看门狗 boot_hold / armed=false，选择器 hold，336 条最终驱动指令全零。第一版核查脚本误把选择器纯文本 hold 作为 JSON 解析失败，已保留失败记录并更正，仅影响核查脚本。
- 随后恢复原带 .3 秒独立超时的 driver-overlay、motion_gated_slam（scan_queue_size=3、stationary_keyframe_distance=.03）与具 mapping-runtime 的适配器。没有启用原版未修复 SLAM，没有调整安全阈值。
- 本地网页认证连接 HTTP 200；源码未修改，前端继续提供已修复空间拖动黑屏的 index-BSbMUdOY.js。
- 断电后的 SLAM 内存图已丢失，本次启动新的内存建图会话；未触发地图 Reset，已保存地图与旧归档保持原样。

## 本次实测结果

- 首次实时状态：/scan 540 束约 10.02 Hz，/odom 约 20.00 Hz，相机实际接收约 9.99 Hz，map 存在且约 1 Hz，里程计速度为零。
- 车端 40 秒共同负载：132/132 位姿有效，最大年龄 .1853 秒，原始 map TF 年龄 .0282–.1280 秒；tf_stale=0。最终驱动 1998 条全零，碰撞输出 400 条；无解锁或非零违规，始终 remote / disarmed。
- 网页只读 WebSocket + JPEG 持续 48 秒：170/170 位姿有效，最大年龄 .6573 秒，最大状态间隔 .4061 秒；相机 131/131 JPEG 成功；未发送控制或操作者心跳，保持停车。
- velocity_smoother、collision_monitor、controller_server、planner_server、bt_navigator 全部 active；/navigate_to_pose 动作服务 ready，gate=3 运行配置校验通过，现有探索算法文件存在且探索节点未启动。
- 指令发布者独占：/safety/nav_cmd_vel 只有 wheeltec_command_selector，/console/driver_cmd_vel 只有 wheeltec_watchdog。静止未申请网页控制权，control.ready=false 是未持有租约/未解锁的预期状态。

证据：电脑 C:/Users/30120/OneDrive/文档/ChatGPT/WHEELTEC/outputs/20261101-connection-check/；车端队列验证 /home/wheeltec/.wheeltec-console/trial-20261031/queue3-final-verification-1793519432010885268.json。新进程身份、日志目录记录于车端 owned-processes.json 与 reconnect-current.json；上次启动记录已备份。

这是本次连接及静止启动条件核查通过，不代表完整自主实车任务或完整校准通过。既有相机长期内存增长问题未在本轮修复，短测不证明长期稳定。不新增任何开机项；本次为手动恢复。用户应 Ctrl+F5 刷新并保持页面前台，由用户点击自主探索；Space 停车并回远程，断连/超时保护继续保留。agent 未执行运动试验。
