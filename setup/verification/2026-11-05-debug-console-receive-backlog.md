# 2026-11-05：网页探索启动后退出，适配器接收积压修复

> 后续状态：用户已断开小车，仅做本地修复；下方连接与PID是本次部署时记录。后续换点/净空/键盘修复见[本地修复记录](2026-11-05-debug-local-observation-and-input.md)，尚未部署。

## 本次部署状态：真实点击已进入导航，持续探索仍待验收

原有 `http://127.0.0.1:8766` 网页已认证连接车端，动态 TF 与安全状态队列修复已部署。仅重启了网页适配器；底盘驱动、SLAM、Nav2、雷达与相机没有因此重启，部署时的当前地图保持。修复后用户已在网页实际发起任务并进入前沿导航；持续探索仍待验收。

修复后的真实操作观测：

- 18:22:08开始的一轮进入前沿选择，约17.47秒后保存地图、确认已在起点，报告 `incomplete: remaining_unreachable_frontiers_or_insufficient_observed_area`，退出代码2。该轮没有再因 TF/watchdog 启动中断；未将缺少可达前沿或面积不足改写成成功，也没有降低足迹/已知空间约束。
- 18:23:23开始的下一轮于18:23:35左右报告 `Navigating to a frontier approach`，现场观测到 autonomous 模式、原始 odom 线速度约0.06m/s；约18:24:05回到 remote、错误字段为空，随后用户手动接管。该轮停止来源仍待车端原始任务文件，不把空错误当作算法已完成。
- 用户正在遥控时不打开维护 PTY、不发停车或模式请求；先通过现有事件流保留证据，待实际停车再取本轮任务文件。

## 本次真实点击不是按钮无响应

2026-11-05 17:59（香港时间），用户点击后，网关观测到 `starting → autonomous → remote`：

| 车端任务 | 本次证据 |
| --- | --- |
| `1793872740549469760` | 约17:59:01进入自主，17:59:05观测到 `watchdog_unavailable`；探索子进程在创建 ROS 参数服务时收到中断，尚无导航目标 |
| `1793872747017663885` | 约17:59:07进入自主，随后回到 remote，错误字段为空；子进程在导入 ROS 消息模块时收到中断，未将中断来源推断为用户或算法 |
| `1793872765779042450` | 17:59:30.072由适配器以 `tf_stale` 停止，`odom_combined → base_footprint` 源年龄 `1.1477363109588623` 秒；探索报告仅运行0.39秒、无目标、终态 `operator_interrupted` |

适配器中止子进程也会产生 `operator_interrupted`，不能凭这个探索终态把故障归因于用户。最新故障中，适配器先报告 TF 过期并停车，探索算法尚未开始前沿目标执行。

## 区分上游断流与消费积压

只读订阅首先确认停车时 `/odom` 约20Hz、底盘 TF 约10Hz，TF发布者为 EKF；普通稳态窗口内 TF 源最大年龄0.049秒、看门狗接收最大间隔0.123秒。进程 CPU 样本显示适配器曾占用约一个 CPU 核。

随后在停车状态创建一组不发送请求/消息的 ROS 订阅、服务客户端与 action 客户端，复现探索初始化的实体创建负载；没有实例化探索算法、发送导航目标、解锁或发布速度。独立订阅者与原网页适配器同时观察：

| 同一只读初始化负载 | 修复前 | 修复后 |
| --- | ---: | ---: |
| 独立订阅者的底盘 TF 最大源年龄 | 0.094秒 | 0.142秒 |
| 网页适配器位姿 TF 最大年龄 | 0.929秒 | 0.406秒 |
| 网页采样中的 watchdog_fresh=false | 0 | 0 |

原适配器的 TF 年龄明显落后于独立订阅者，表明此负载下存在消费端积压。上述只读负载没有完整重现真实自主时的1.148秒过期，且修复后独立订阅者的选择器状态最大间隔仍有0.571秒；实际探索能否持续，需要保留并查看下一次真实任务，不能由这张表替代。

## 最小修复及必要回归

- `console/target/adapter.py`：动态 `/tf` 明确采用可靠、volatile、depth=10 的短队列，替代 TransformListener 默认100条动态历史。保留一定深度以容纳交错的 map/odom 更新，没有将共享 TF 话题粗暴设成仅一条；静态 TF 的 transient-local 历史沿用原默认。
- `/safety/status` 与 `/safety/selected_source` 各使用 depth=1，消费最新状态，不排队回放旧状态。
- 同时部署此前已完成的 `console/target/diagnostics.py` 与适配器停止证据增强：每条 TF 边保留4个源/接收样本，在原停止处理之后写任务 `console-stop.json`。写盘失败不撤销停车。
- 没有改变 TF、scan、odom、watchdog、驱动的超时门限，没有改写源时间或以接收时间代替源时间；未修改探索算法、异步前沿计算、地图校正参考点或 SLAM 设置。

新增2项回归先确认原接线失败，再修复。仅执行直接相关的 `test_live_state_qos`、`test_tf_tracking`、`test_stop_diagnostics`，14项通过，覆盖实际订阅接线、静态 TF 保留、过期数据仍拒绝、先停车后持久记录、诊断磁盘失败仍保持停车。未执行整套 smoke test。

TransformListener 的动态默认100和静态独立 QoS 接口见 [ROS 2 Humble 源码](https://github.com/ros2/geometry2/blob/humble/tf2_ros_py/tf2_ros/transform_listener.py)。

## 部署、恢复入口与证据

用户明确批准在停车状态仅重启适配器。通过现有已认证网关的维护 PTY 操作，没有再次索取密码或弹出命令行窗口。部署前核对当前 PID、start_ticks、boot_id、实际源码，以及 remote、无控制者、选择器hold、watchdog新鲜且未解锁、最终输出和原始 odom 速度全零。

18:19:58左右，适配器 PID `46379` 重新提供新鲜传感器、有效位姿和停车状态。`owned-processes.json` 只更新适配器项并保留其旧记录；六项其他服务记录逐项保持。网关原 SSH 会话继续使用，维护结束后网页恢复可操作。

车端备份与结果：

`/home/wheeltec/.wheeltec-console/trial-20261031/deploy-live-state-qos-1793873986164466050/`

其中包含原源码、部署前进程索引、`restore-input.json`、新适配器日志与 `result.json`。部署脚本在新适配器无法恢复时会在原维护通道内恢复原文件及适配器，避免适配器离线后无法重新进入维护通道。

本机完整证据根目录：

`C:/Users/30120/OneDrive/文档/ChatGPT/WHEELTEC/outputs/20261105-recovery/`

- `task-events.jsonl`：第一次真实点击的任务时间线。
- `failure-1793872907/evidence.json`：该次任务、EKF、Nav2、底盘及适配器原日志。
- `failure-1793873525/evidence.json` 与 `discovery-adapter-observations.json`：修复前同一只读初始化负载。
- `failure-1793873986/evidence.json`：成功部署与当前服务/停车证据。
- `failure-1793874064/evidence.json` 与 `discovery-adapter-after-1793874089.json`：修复后对比。
- `gateway-observed-state.json`、`gateway-task-events.jsonl`：随后通过既有网页事件流被动保留任务变化及对应日志；有界观察，不自动启动或重试任务。

11月1日的历史失败与原始地图、任务记录均保留。本轮新证据不能自动证明11月1日全部事件具有同一上游原因。
