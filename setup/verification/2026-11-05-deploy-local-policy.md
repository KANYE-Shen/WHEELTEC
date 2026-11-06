# 2026-11-05：局部换点与输入修复实车部署

## 当前结果

用户重新连接热点，并要求配置和进行实车部署实验。已将main的f3ad1cf算法版本应用到车端，恢复现有8766网页的认证连接；两层Nav2运行参数已核对，新版页面的地图、位姿和640×480相机实际渲染已检查。当前为remote/hold，watchdog未解锁，原始odom和最终驱动输出为零；agent没有发起探索或导航。用户随后实际点击在初始化阶段因command_selector_unavailable/watchdog_unavailable退出；后续已停车部署启动顺序修复，持续运行待新的用户任务。见[后续失败与修复](2026-11-05-debug-startup-status-gaps.md)。

## 实际部署

- SSH使用项目固定指纹。没有可复用密钥或网关会话时，操作者通过一次隐藏输入框认证；密码和adapter_token仅在进程内存，不落文件或命令行。
- 新boot下原有8项进程都已退出，车端时间回到2000年；已校时。旧PID均未复用。
- 在没有现存ROS控制进程时，备份并应用7个实际变化文件：robot/preflight.py、robot/launch/robot.launch.py、console/target/adapter.py，以及探索defaults.py、frontiers.py、node.py、policy.py。TF短队列、停止诊断、异步候选和校正参考点修复保留。
- 按原命令恢复lidar、camera、model、ekf和control_stack；先取得选择器hold、watchdog未解锁及101条最终驱动指令全零的确认，再恢复原超时驱动overlay、motion_gated_slam和adapter。没有增加开机项，没有启动探索器。
- 采用原SLAM参数，scan_queue_size=3、stationary_keyframe_distance=0.03。没有Reset、删除地图或覆写已保存成果；断电前未保存的内存图不可能恢复，本次是新的内存建图会话。

## 生效参数与必要检查

| 项目 | 实际运行值 |
| --- | --- |
| local/global costmap robot_radius | 0.47762432936357m，两层一致 |
| local/global inflation_radius | 0.57762432936357m |
| costmap footprint | []，使用圆半径，不残留旧多边形 |
| StopZone半长/半宽 | 0.300/0.275m，原保护区未缩小 |
| 探索物理足迹排除半径 | 0.24525624189766637m，规划余量不算排除证据 |
| 生命周期 | controller、planner、bt_navigator、velocity_smoother、collision_monitor均active |
| 停车状态 | hold、watchdog armed=false、最终输出和原始odom均零 |
| 网页 | 地图/位姿/相机在线，实际截图检查；没有点击控制按钮 |

首次参数读取恰好发生在生命周期顺序激活尚未结束时，smoother和collision_monitor仍inactive，检查失败记录保留。日志随后明确记录Managed nodes are active，再读取全部通过；没有为此重启或改参数。

复用既有本地算法/交互回归，没有重做整套smoke test。只做部署前零指令确认、部署后实际参数/生命周期/停车核对及网页实际呈现检查。

## 恢复与证据

车端备份：/home/wheeltec/.wheeltec-console/trial-20261031/deploy-local-policy-1793883673672126527。其中before/保存旧源码，owned-processes.before.json保存历史启动命令；新进程记录已写回owned-processes.json，包含本轮boot_id和start_ticks。恢复前必须先核查新鲜停车状态和实际进程身份；不要照抄旧PID，不在用户探索时做维护。

本机证据根目录：C:/Users/30120/OneDrive/文档/ChatGPT/WHEELTEC/outputs/20261105-deploy-local-policy/。

- 01-inspect、02-verify-clean-boot：本次新boot、配置与原进程退出证据。
- 03-clock、04-install：校时及备份/文件应用记录。
- 05/06：先恢复传感/安全栈，再确认最终零指令。
- 07/08/09/10：恢复驱动/SLAM/适配器、初次早读失败、激活完成日志及有效参数最终通过。
- 11-connect-gateway：现有网关连接成功。
- live-console.png、live-page-result.json：真实网页呈现；只读观察浏览器拦截控制/心跳和所有非GET请求。
- trial-task-events.jsonl、trial-latest-state.json：用户试验的被动观察，不发送控制或心跳。尚无新任务时不能写成实车自主通过。

[算法条件和离线反例](2026-11-05-debug-local-observation-and-input.md)：85%仅允许当前观察点换点，不是全局完成率；25秒内有效位姿无0.1m进展才冷却目标。普通键/可见窗口失焦不取消自主，WASD接管、Space停车；隐藏页面、断连、心跳、碰撞和驱动超时保护保持。
