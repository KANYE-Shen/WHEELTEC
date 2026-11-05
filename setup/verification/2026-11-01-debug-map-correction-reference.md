# 2026-11-01 自主重试退出：地图校正参考点诊断与停车部署

最新失败任务为 `/home/wheeltec/.wheeltec-console/tasks/1793520313357531076`。它发生在上一轮线程调度修复部署之后，终态仍为失败，不能沿用停车候选计算通过宣称完整自主已修复。本轮仅进行了只读采样、局部修复、回归及停车部署；没有启动探索、请求解锁、发布操作者心跳或非零速度，没有发送导航目标。

时间均为香港时间（UTC+8），依据车端实际任务日志和 Nav2 日志：

| 时间 | 证据与行为 |
| --- | --- |
| 16:05:13.357 | 任务目录时间标识；由适配器创建并启动探索子进程 |
| 16:05:17.654 | 探索器记录 starting |
| 16:05:19.332 | 开始候选计算 |
| 16:05:26.813 | 提交前沿导航；Nav2 在 .816 开始处理目标 (-1.27, 3.08) |
| 16:05:26–16:05:42 | 多次 GridBased 无有效路径，行为树等待后重试 |
| 16:05:42.030 | controller_server 开始跟随路径 |
| 16:05:47.153 | 再次规划失败；随后取消 FollowPath，继续等待重规划 |
| 16:06:22.442 | 探索器健康检查锁存 map_to_odom_translation_jump |
| 16:06:22.474 | Nav2 收到取消导航请求 |
| 16:06:22.485 | 终态 map_unstable，运行约 65.19 秒；map_saved=false、returned=false |

准确的直接退出原因是探索器锁存了 0.611058163 m 的 map→odom 平移分量变化，超过 0.5 m 门限。终态 scan 源年龄 .00965 s，TF 源年龄 -.0912 s、接收更新年龄 .0342 s，SLAM 存活；不是上一轮的 scan_stale/tf_stale。报告 goals 数组为空表示尚未完成并登记该目标，不表示没有向 Nav2 提交目标。Nav2 的多次无路是独立观测，没有通过改规划参数或恢复动作来掩盖。

适配器持久日志仅有启动信息，内存 /rosout 环形缓冲中的当时 console.task 事件已经被后续消息淘汰；没有取得 16:06:22 时刻的 watchdog timeout_detail 历史样本。因此不能用本轮当前的 operator_hold / timeout_detail=null 反推当时没有短暂超时，也不能断言用户按了 Space。任务的明确 MapUnstableError 及随后取消导航的顺序，支持以上直接退出原因。SLAM 同一时间窗无新增持久警告，不能从无日志推断匹配或图质量正常。

停车采样确认了一个可复现的坐标参考点缺陷。原 MapHealth.transform 直接计算相邻 map→odom 的 translation 距离。这度量的是 odom 原点的变化；当车远离原点时，围绕车体的正常方向校正也会带出较大的 translation 分量。

100 秒只读实车采样中的原始一对 TF：原点平移变化 .452856075 m，角度变化 .10121 rad；将前后变换作用到同一个当前 odom 车体位置 (-2.342363564, -3.777556533)，车体位置校正只有 .003199919 m。对同一对实测 TF 做等价坐标变换，仅把 odom 原点平移 (0, 3) m 后，原版得到 .728631827 m 并触发 map_to_odom_translation_jump；修正版仍为 .003199919 m 并通过。这里平移坐标原点的是离线数值对照，没有移动小车或修改真实 TF。

最新失败未保存故障前后两组完整原始 TF，报告只有 .611058163 m 和截至退出的最大角度变化 .13262 rad。因此已确认直接触发项和参考点缺陷，但不能把原始失败的 .611 m 全部认定为误报。该根因类别有实测支持，是否足以消除这次真实自主任务退出仍须用户完整运行验证。

最小生产修改只有两处方法：health.py 的 MapHealth.transform，以及 node.py 的 Explorer.health_tick。对同一个新鲜 odom 车体位置 p，同时计算 T_old(p) 和 T_new(p)，用两者距离度量定位校正，避免混入车的正常里程计运动。旋转差仍按原方式检查。node.py 明确查询 odom_combined→base_footprint，参考变换缺失、过期或无效时拒绝继续。真实大位移/大角度仍锁存，并记录前后完整 map→odom、接收时间、odom 参考位置及源时间、原点平移分量，供下一次失败判别。历史故障 key 保持不变，修复后 max_translation_jump_m 表示车体参考点的校正量。

0.5 m / 0.35 rad 跳变门限、scan/TF 1 秒门限、各层命令和操作者超时均未修改。此前 ThreadPoolExecutor 修复完整保留。frontiers.py、评分、安全链、网页和已修复的黑屏逻辑均未改。motion_gated_slam、scan_queue_size=3、stationary_keyframe_distance=.03 未变。没有清图、Reset、重启 SLAM/Nav2/适配器、修改系统安装或增加开机项。

验证边界分别如下：

- 本地：原有 52 项通过。新增实际 health_tick 调用路径的三项回归在原版均以断言失败；修复后完整 61/61 通过。新增测试还覆盖原点变化不变性、真实 .6 m 位移仍停车、原点位移很小但车体位置大跳仍停车、大角度、缺失/过期/非有限参考。
- 车端候选静止：115 秒，526 次健康检查通过；5648 条最终指令全零、2300 条原始 odom 零速、1015 条 watchdog 未解锁。抓到三次原点变化约 .450–.451 m、车体校正约 .0032 m，无健康锁存。未执行 Explorer.run 或导航。
- 部署前：重新确认 remote、无 owner、新鲜且未解锁的 watchdog、hold、250 条最终全零指令、93 条零速 odom，且没有运行中的探索。按 boot_id/start_ticks/cmdline 重核当前服务身份，没有使用历史 PID 操作进程。
- 部署后真实路径：30 秒，108 次健康检查通过；1481 条最终指令全零、565 条原始 odom 零速、269 条 watchdog 未解锁。源文件 SHA256 与本地一致；无探索、无服务重启。
- 用户完整自主：本轮尚未运行，仍待用户在网页点击。静止结果不能代替导航、任务完成、存图、返航或实车制动验证。

另一个保留的事实是停车只读采样中 odom TF 朝向在约 98.47 秒内变化 -.30222 rad，而最终指令和原始 odom 速度为零。它说明估计朝向存在漂移；来源没有在本轮定位，也未通过伪造 TF、关闭匹配、放宽健康门限或强行修改 IMU/EKF 配置处理。受监督免完整校准的许可继续适用，但不把校准状态改成已通过。

部署备份目录：`/home/wheeltec/.wheeltec-console/trial-20261031/correction-reference-fix-1793521150751857000`。其中 health.before.py、node.before.py 是实际部署前的原字节备份；candidate-stationary.json、deployment-precheck.json、deployment.json、deployed-stationary.json 保存原始验证。本地 `C:/Users/30120/OneDrive/文档/ChatGPT/WHEELTEC/outputs/20261101-autonomy-exit-retry/` 保留失败原件、完整采样、红/绿回归、diff、哈希和脚本。raw-manifest.json 保存下载原件哈希，replay buffer 中另留可核查副本。

回退必须先重新确认停车、无控制者、watchdog 新鲜未解锁、hold、原始最终输出/odom 零速且探索已退出，再将本次两份 before 文件作为一组原子恢复到原路径；下一次新探索进程加载恢复版本。不要在自主中回退，不清图，不执行历史 PID 的停止命令。此前 planning-callback-fix 备份继续保留，本轮回退到的 node.before.py 已包含上一轮线程调度修复。
