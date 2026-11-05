# 2026-11-01 自主探索计算阻塞导致退出

## 真实症状与根因

用户已自行启动自主，进入后数秒退出。最后一轮车端任务 `/home/wheeltec/.wheeltec-console/tasks/1793519625938414301`：2.42 秒开始选择边界，6.59 秒请求导航，6.63 秒 `map_unstable: scan_stale,tf_stale` 结束。Nav2 日志确认目标随后立即被取消；报告 goals 为空、map_saved=false、returned=false，不能记为任务成功。前一轮 `/tasks/1793519616277693108` 以 operator_interrupted 结束，不能据此推断一定是用户按键，原始记录一并保留。

原因：Explorer.run 同步调用 CPU 密集的 select_frontiers，其数秒执行期间没有 rclpy.spin_once；/scan、/map、TF 在 DDS 队列里等待，探索节点自己的缓存老化。恢复 spin 时健康回调先看到旧缓存，把 scan_stale/tf_stale 锁存，取消导航退出。上游没有随之断流。

停车只读复现命令为电脑 outputs/20261101-autonomy-exit 下的 probe-planning-starvation.py，经 run-remote-script.py 在车端执行。核查节点重命名 console_frontier_readonly_probe，仅调用候选计算与健康检查，不调用 Explorer.run，不发送任何导航目标、心跳、解锁或运动指令。

修复前 225×235 真实地图，候选 29 个，计算 4.639 秒后同样抛 MapUnstableError(scan_stale,tf_stale)。同一时间独立适配器观察 18 次，上游位姿最大年龄 .1792 秒、雷达 .1193 秒，全部停车；证明是消费端阻塞。样本原目录 frontier-probe-1793519825880975071，包含 fixture.json/result.json。

## 最小修复与验证

只改 src/wheeltec_explore/wheeltec_explore/node.py 的调度：把原 select_frontiers 调用放到单个工作线程；地图栅格、visited、observations 均传入不可变快照，工作线程不操作 ROS。主线程用原 wait 持续处理订阅、TF 和健康检查，同时检查任务总超时。得到候选后再次 require_health；真实断流、突跳、超时仍拒绝继续。frontiers.py、评分、候选顺序、地图、1秒新鲜度门限和底盘安全链均未改。

新增 test_planning_callbacks.py 在实际 run/wait/require_health 方法调用路径覆盖：慢计算但新消息持续到达应可进入导航步骤；真实断流、任务超时必须阻止导航；工作线程异常必须传出。旧版先运行，其中慢计算报 MapUnstableError、任务超时期望失败；修复后完整探索纯算法回归 52/52 通过。首次完整测试因未设置包 PYTHONPATH 导入 test_active_scan 失败，设置正确路径后完整通过；没有通过修改算法规避。

部署前两次未满足停车检查，均主动中止且没有替换文件。用户明确回复已按 Space 暂停操作后再次验证 remote、无 owner、watchdog 新鲜未解锁、hold、零输出和零 odom，再原子替换单文件；未重启控制栈、适配器或 SLAM，未清空地图。原文件备份：`/home/wheeltec/.wheeltec-console/trial-20261031/planning-callback-fix-1793520086975717900/node.before.py`；修复文件 SHA256 d15071df31b7361d4b9d650f960194fc27f477ad431254eee9369d702a26d688。下一次用户点击探索自动加载新文件。

- 首次修复后实时地图更大（249×247），计算及检查8.938秒，22个候选，健康通过、无锁存问题；上游位姿最大.1973秒、雷达.1428秒。
- 为控制地图变化，再用修复前保存的同一225×235栅格、同一姿态及参数复核：计算及检查8.329秒，仍29个候选，健康通过、无锁存问题；最终scan源年龄.0711秒，TF源年龄-.0292秒（SLAM允许的.2秒真实前置变换，未修改时间戳），TF更新年龄.0217秒；独立上游位姿最大.3218秒、雷达.1558秒，全部停车。
- 计算速度不是本轮改进结论。线程共享Python执行时间，实际耗时更长，但消息消费和安全监测持续运行。健康失败时会等待本轮工作线程清理，不会因此发导航；最终停车由独立安全链维持。
- 最终只读检查仍remote/hold/disarmed、无owner、输出及原始odom速度全零。两次真实验证均未发送导航目标，完整自主行驶效果待用户重新点击验证。

## 证据与回退

电脑证据目录 `C:/Users/30120/OneDrive/文档/ChatGPT/WHEELTEC/outputs/20261101-autonomy-exit/` 保留 user-failed-task.json、user-explore.log、timeline.json、red-live-result.json、recorded-grid.json、green-live-result.json、green-recorded-result.json、部署diff/哈希和最终停车状态。失败经验副本及SHA清单见 replay buffer/20261101-autonomy-planning-starvation/。

若需要回退，必须重新核查停车、无控制权/无运行中的探索，再将上述node.before.py原子恢复到原路径；下一次探索使用旧版。不要在探索中替换，也不要重置地图来回退。没有新建系统服务或开机项。既有完整校准、实测制动和相机长期内存增长问题未在此轮解决。
