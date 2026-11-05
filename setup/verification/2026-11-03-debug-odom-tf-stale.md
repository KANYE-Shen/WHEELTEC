# 2026-11-03：11月1日自主退出的 odom TF 本地排查

2026-11-01 17:26:23.090（香港时间），用户报告 console.task：`自主探索已停止：tf_stale`，target=`odom_combined`，source=`base_footprint`，reason=`source_age`，age=`1.0099921226501465`，at=`1793525183.0900872`。这是本轮唯一取得的该次失败原始事件；任务ID、启动时刻、探索终态及对应时间窗的车端文件尚未取得。原文存 user-error.json，未知字段保留为 null。

直接触发点已确认：Adapter.blockers 先通过 scan/odom 新鲜度检查，再调用 transform(odom_combined, base_footprint)；该调用通过 TF 接收链检查，随后因查询到的变换源年龄超过现有1秒门限返回 None。tick 据此执行既有 tasks.remote(message)，回到远程模式。单条日志只证明消费端看到旧源时间，不能区分 EKF/发布端延迟、TF 订阅积压或时钟问题，也不能据此要求调大超时。这次指向 odom→base，不能套用上一轮 map→odom 平移参考点缺陷的结论。

当前用户确认小车未连接，只做本地排查和程序修改；底盘任何指令（包括零速）、停车/解锁/切模式、任务启动与车端控制组件重启均不在本轮操作范围。2026-11-03只读 SSH 尝试超时后，用户确认连接状态，后续仅本地工作。没有部署本轮修改。

取证限制及恢复路线：

- 11月1日 collect_failure.py 在 /proc/pressure/cpu 不存在时退出，未落下预期任务证据。该旧脚本还请求 /state；适配器 snapshot 可能在发现探索子进程退出时调用 halt，因此它不适合当前“不给底盘发指令”的边界。
- 新 collect_failure_readonly.py 只读任务文件、owned-processes 对应日志、/proc 和历史内核日志；不请求适配器接口、不创建ROS节点。缺失的 /proc/pressure 会标记 unavailable；每次尝试另存目录，保留错误记录。对固定失败时间选取此前最近的任务，不把两天后的最新任务误认成这次失败。
- 当前脚本的 SSH 超时已保留在 collection-* 目录。连接恢复后的第一步应是使用新脚本取回11月1日这次失败的已有文件；无需先让用户再次启动探索。

本地代码检查发现两个影响后续定位的证据缺口：tf_edges 只有接收时刻，没有源时间历史；console.task 停止详情主要位于400条内存环形日志，之后会被挤掉。已做如下诊断补丁，保持运行判据：

1. 每条已跟踪TF边保留最近4次“单调接收时刻、原始源时间戳”。原有最多1024条边的上限保持，tf_edges 的二元组结构及 tf_chain_fresh 行为保持。
2. TF失败仍保留 target/source/reason/age/at，额外记录查询使用的 source_stamp、ros_now、TF链各边的最近源时间、源年龄、接收年龄、源时间增量及接收间隔。这里的每边样本表示最近收到的消息；顶层 source_stamp 是实际 Buffer 查询结果，两者分开命名，便于发现旧消息/乱序交付。
3. 安全中止沿用原 tasks.remote 处理，再将失败原因、TF上下文、watchdog（含 timeout_detail）、速度源及传感器时间记录写入该任务的 console-stop.json。即使环形日志被覆盖，这份记录仍在。文件写入失败仅记录警告，既有停止顺序不受影响。

生产修改是 console/target/adapter.py 和新增 console/target/diagnostics.py，新增回归在 console/tests/test_stop_diagnostics.py。未修改 blockers、TF/scan/odom门限、watchdog或驱动超时、SLAM队列/关键帧设置、前沿算法或网页。之前的探索线程调度和地图校正参考点修复保留。TF源时间没有被重写，也没有用接收时间代替源时间。

本地验证：原版新增的6项关键诊断断言先失败；补丁后8项专项测试通过，终端完整单元回归73/73通过。测试执行实际 Adapter.transform、tf_received 和 tick 方法，以内存对象替代ROS，覆盖旧源时间仍拒绝、接收停更仍拒绝、新鲜/静态TF原契约、有限历史、原停车处理先于写盘、磁盘失败仍停车及内存日志挤出后的文件可读性。首次沙箱专项运行因临时目录清理受限额外报错，该输出保留；用真实本机临时目录重跑得到纯断言失败，再完成修复。完整回归存在已有 Starlette/httpx 弃用警告，与本轮诊断功能无关。

当前结论：已确认这次回退的直接安全触发项；上游根因等待这次失败的车端文件。已完成并验证本地诊断补丁，未部署，实车自主退出问题仍开放。连接恢复后先比对 EKF/Nav2 日志和任务终态；若历史文件不足，再使用独立只读TF订阅与适配器的源/接收上下文区分发布端和消费端。在证据明确前不更改运行门限或以其他补丁覆盖现象。

本机证据目录：C:/Users/30120/OneDrive/文档/ChatGPT/WHEELTEC/outputs/20261101-autonomy-odom-tf-stale/。包含用户事件、旧取证脚本及更正版本、SSH失败记录、adapter修改前副本、diff、专项红/绿测试和完整回归。已有地图和原始失败记录保持原位。本轮没有新增开机项。
