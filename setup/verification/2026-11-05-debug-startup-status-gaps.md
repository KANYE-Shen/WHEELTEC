# 2026-11-05：选择器 / watchdog 退出与停车初始化修复

## 当前结果

新版局部换点与规划净空部署后，用户实际点击仍在数秒内退出，记录到 command_selector_unavailable 和 watchdog_unavailable。启动顺序修复已停车部署，随后用户两轮已分别实际运行约103秒、200秒，另有新一轮在继续；一次TF失效仍未解决，完整持续自主尚未通过。

## 已保存的失败证据

- 被动网页时间线：starting 1793884467.944、autonomous 1793884469.866、remote 1793884470.437，退出为 command_selector_unavailable。
- 任务1793885265317682284：选择器接收年龄0.503150824秒，服务ready=true，本次blockers检查耗时0.002470465秒；看门狗最后状态armed，未报告命令/操作者超时。因此本次不是切换服务掉线，也不是这一次检查阻塞0.5秒。
- 任务1793885271892682716同样为选择器年龄0.503515616秒。
- 任务1793885284277333086、1793885291171269395为watchdog_unavailable。后一任务选择器年龄0.463120125秒、服务ready=true；原停止记录未保存watchdog接收年龄与arm服务可用性，不能仅凭最后一份armed状态判定看门狗进程掉线。
- 这些任务的SIGINT栈分别位于sensor_msgs、rclpy、lark等模块初始化；探索进程还未完成初始化，未把这轮算作正常导航或85%换点效果验证。

## 有限只读对照

独立12秒接收者记录到选择器最大接收间隔1.101849756秒，watchdog最大0.294536598秒。另一次15秒接收中，两路及选择器输出均无超过0.3秒的间隔，确认是间歇现象。

停车状态下只导入探索模块、不创建探索节点：耗时3.13477秒、最多8线程，两路最大间隔约0.136秒，未复现。因此不把线程数或纯模块导入写成已证实根因。只读ROS发现/订阅初始化对照在接收者warmup/idle阶段记录0.62–0.81秒选择器间隔、0.737秒watchdog间隔；子进程发现阶段未复现0.5秒断流。发送调度、DDS传递与接收调度尚未分离。

## 修正启动顺序，不放宽保护

原顺序为：停车/健康握手 → 解锁 → spawn探索进程 → Python导入和ROS初始化。进程尚未具备执行能力时，控制链已暴露在解锁后的状态时效检查中。

现顺序为：

1. 用户点击后保持starting，先停车并取消旧导航。
2. 启动受阻挡的探索子进程；它接收地图/扫描/TF并等待Nav2就绪，写任务私有start-gate/ready.json，然后只spin、不进入探索run。
3. 原连续健康检查、选择器切换和最终watchdog解锁完成后，仅当前任务生成代次能原子写入go，才允许探索run。
4. Space、准备失败、子进程退出和30秒准备/放行超时均关闭任务；准备中的子进程已由TaskController持有，可被立即SIGINT。旧worker不得晚到放行或覆盖新任务。

普通CLI/仿真没有WHEELTEC_CONSOLE_START_GATE时保持原入口，不新增外部启动条件。0.5秒控制状态门限、TF原始时间、碰撞区、驱动超时与用户发起运行的要求不变。此修复消除初始化顺序缺陷；间歇状态延迟的底层原因仍未确认，须保留后续运行证据。

## 修改、检查与部署

- console/target/tasks.py：可选prepare/release阶段，保留原四参数调用。
- console/target/adapter.py：停车预初始化与当前任务放行；停止记录分别保存selector_check、watchdog_check的接收年龄和服务可用性。
- src/wheeltec_explore/wheeltec_explore/node.py、startup.py：可选网页启动屏障，放行前不进入算法run。
- 37项定向回归通过，0.418秒：包含真实Explorer.main的屏障/Space/旧入口、TaskController取消竞争、准备失败及原TF/QoS/停止诊断。没有重做全套smoke test。
- 车端仅重启适配器，PID43125；控制栈、驱动、SLAM、地图和相机未重启。新鲜停车反馈及适配器remote/hold/未解锁确认通过。agent未启动探索或解锁。
- 恢复备份：/home/wheeltec/.wheeltec-console/trial-20261031/staged-start-1793886683924700907；包含before/、after/和旧receipt。部署脚本保留同一维护通道内自动恢复源码并重启旧适配器的路径。
- 先前独立SSH worker按30分钟寿命退出，不代表网页断线。用户随后明确允许后台复用原网页维护通道取日志和修复；未弹出命令行窗口，未重新取密。

## 证据与后续验收

本机：C:/Users/30120/OneDrive/文档/ChatGPT/WHEELTEC/outputs/20261105-deploy-local-policy/

12/18/19保存原任务文件；14/15/20/21保存只读对照；17保存诊断更新，22保存本次4文件部署及停车确认；staged-trial-*保存用户下一轮被动状态。16为早期停车订阅尚未匹配的拒绝记录，无车端修改，保留不覆盖。

本轮真实启动已记录，下表给出正负结果。下一次若退出，先保留任务console-stop.json、explore.log和gate文件，再依据selector_check/watchdog_check区分状态断流与服务不可用；不靠重复点击或提高超时掩盖问题。本轮源码尚未提交或推送，远端main仍为此前f3ad1cf。

## 用户真实运行更新

| 任务 | 实际结果 | 验收意义 |
| --- | --- | --- |
| 1793887002951874035 | 探索报告103.02秒，网页autonomous约100.74秒；原始odom峰值0.079m/s；终态map_unstable/tf_stale | 已跨过启动，仍有持续TF失效 |
| 1793887119251137415 | 探索报告199.92秒；3条已结束目标分别为导航状态6、goal_no_progress、locally_observed；终态operator_interrupted | 真实执行换点与无进展冷却，非完整任务通过 |

第二任务局部换点事件known_ratio=0.927710843373494（地图revision135），success仍false；无进展事件known_ratio=0.7718174539631706（revision84）。不把局部阈值当全图覆盖率，也不凭operator_interrupted推断操作者具体按键。

第一任务TF健康年龄stamp_age=1.039647102秒、update_age=0.881631851秒，scan年龄0.042809010秒。同期网页独立适配器的map→odom_combined也显示source_age约0.96–0.97秒，而receipt_age约0.017–0.022秒，并重复收到同一源时间戳；不能把此次仅归因于探索器默认TF队列。证据指向map→odom源时间落后，尚需SLAM进程同一时间窗的原日志分离上游原因；不伪造时间、不放宽1秒门限。

用户随后又发起新一轮，观察到autonomous与原始odom约0.061m/s；维护取证守卫因正在运行而拒绝，未向该轮发送停车/维护指令。已改为连续被动记录，等待用户任务结束后取SLAM日志。本轮启动顺序修复已有真实运行支持，完整持续稳定与建图/存图/返航仍未验收。
