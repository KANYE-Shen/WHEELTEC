# 2026-10-31 双端地图 Reset 与定位 TF 间歇过期

沿用用户“允许 SSH 部署，保持停车，不启动探索”。新增明确需求是空间视图 Reset 同时清空车端 SLAM 和网页，供人工搬动高度后重新建图；原“重置视图”只把车体箭头居中。agent 没有请求解锁或启动自主，所有实际 Reset 都先确认 remote/hold、最终 watchdog 新鲜且未解锁、无控制者、输出和里程计速度为零。

## 原始失败与定位

用户先确认手动恢复，随后实际点击自主再次因 TF 或 command_or_operator_timeout 停止。新增 timeout_detail 记录命令/操作者年龄与 expired 分项，不改 0.5 秒非零 TTL。1793436977.844 的 TF 故障时最终 watchdog 仍 armed，命令年龄约 0.04 秒、操作者约 0.108 秒，所以不能把该次故障归为网页心跳超时。用户最新 source_age=2.7214 是后一次启动稳定检查失败。

状态重复消息改为约 10 Hz、状态变化立即发布；驱动输出仍 50 Hz，已有实际 Watchdog 类回归验证。这个限频没有单独修好 TF。只读新 ROS 节点发现压力试验未复现 >0.5 秒指令空隙，也不能据此归因于探索器初始化。

最早两个 profile 尝试分别遇到 profile.py 遮蔽标准库和模块路径缺失，所得退出过程 profile 无效，均保留；后用标准 python -m cProfile -m console.target.adapter 得到有效采样，并恢复正常启动命令。主线程主要消耗在 rclpy 分发，未证实 JPEG 是主要瓶颈。

地图更新 1→3 秒的对照仍只有 34/50 位姿、原始 map 链最大年龄 5.48 秒；不是有效修复，现已恢复 1 秒。

## 两个得到对照支持的问题

1. minimum_travel_distance=0 为保留原地转动，却让静止重复扫描持续入图。新增 wheeltec_slam，动态链接原 2.6.10 SDK，只在 addScan 入口按 3 cm 平移或 0.1 rad 转向去重；原回调、暂停、时间戳和算法服务仍由 SDK 实现。隔离同输入静止阶段原版 19 帧、修正版 1 帧，转向和平移后分别 2、3 帧，源 TF 保持新鲜。保存同一张旧图后车端短测 50/50 位姿，最大年龄约 0.347 秒；旧完整图 72,147,768 + 64,871,580 字节在 slam-motion-gate-deploy-1793439691343548887 保留。
2. 延长观察仍失败：99 次仅 71 次位姿可用，原始 map 链最大年龄 9.407 秒；这组失败保留，不能沿用短测宣称稳定。只读关联采样发现雷达/odom 年龄约 0.03–0.05 秒，SLAM 主线程在 futex 等待，恢复时输出位姿年龄约 0.065 秒，反驳“这段时间一定是在做耗时匹配”。单槽队列会在下个扫描到达时扔掉尚待 TF 的上一帧。隔离真实 SDK 单变量相位对照：TF 在扫描后 60 ms 到达，源时间比该扫描早 10 ms；队列 1 为 0 帧交付、0 条地图 TF，队列 3 为 1 帧交付、200 条 TF，最大年龄 0.075 秒。实车 scan_queue_size 改为 3，仍有界，未改任何时效门限。

## Reset 的最终行为

点击 Reset 先执行已有停车/取消任务链，再异步等待新鲜停车、探索退出和导航空闲。通过 SLAM serialize_map 完整备份旧图和数据、SHA256 清单、网页旧栅格、旧参数与命令；备份失败保留原图。只核对并停止本次 owned-processes.json 指向的 mapper PID/start_ticks/cmdline/进程组。等待整个旧组结束并回收自己的子进程后，用当前实车规范配置启动新的空图，不带 map_file_name/map_start_pose/map_start_at_dock；不启动探索，不解锁。

网页清理旧地图缓存与变换历史，新地图按新时间边界接收；重置时隐藏旧图投影，新图与定位就绪后清理全局/局部导航代价图。busy 时拒绝手动 claim/command 和探索启动，错误显示在空间视图。Space 仍立即停车、回远程；Reset 完成不会恢复旧按键或自主任务。原“重置视图”改为按当前位姿平移画布，小车位于画布中心。

实际首测和同适配器内连续两次 Reset 均成功，随后用 Reset 应用队列 3 也成功；每次确认新 mapper PID、无旧图恢复参数、地图周期 1 秒、门限 0.03 米，所有状态采样保持 remote/disarmed/零速。进程回归先复现僵尸导致 12 秒误超时，再通过两次真实测试子进程替换确认修复；该回归不初始化 ROS。

## 验证与边界

- 终端 Python 回归 65/65；robot safety 18/18；前端构建通过。
- 隔离浏览器 11/11，包括真实像素验证箭头居中、Reset 隐藏旧栅格、原 WASD、Space 与延迟解锁行为；所有写请求被截获，不是实车运动测试。
- C++ 门限 1 项通过（涵盖静止、平移、双向转动、角度环绕、非法值与重置）；隔离 SDK 静止/移动 5 项、队列相位 3 项通过。
- 自主真实任务仍待用户本人前台点击验证，agent 不启动；校准、制动距离和长期图质量未验收。
- 相机旧进程 OOM 已有内核证据，当前相机也观察到 RSS 增长，最近只读约 3.9 GB；相机长期内存问题未在此修复，不能声称整机长时间稳定性已验收。

原始材料在本机 outputs/20261031-autonomous-trial，车端 trial-20261031。关键：observe-web-timeout.result.json、adapter-profile-*、verify-cadence-stationary.remote-result.json、verify-map-period-stationary.remote-result.json、slam-motion-isolated/result.json、verify-motion-gate-stationary.remote-result.json、verify-final-parked-health.remote-result.json（71/99 失败）、diagnose-slam-source-latency.remote-result.json、slam-filter-phase/result.json、verify-live-map-reset*.result.json、verify-reset-process-lifecycle.py、map-reset-ui-1/results.json。最终持续共同负载复核另追加在下文。


## 最终：队列 3 的持续共同负载复核通过

车端节点发现预热 5 秒后连续观察 40 秒：132/132 位姿可用，最大源年龄 0.175 秒；独立 Buffer 的 map→base 源年龄 0.041–0.141 秒，控制 TF 失效 0。最终驱动命令 2000 条、碰撞输出 400 条，非零/非法值和 armed 违例均 0；所有状态 remote/disarmed/零速。CPU 观测约 adapter 96.9%、SLAM 6.4%，限于这段共同负载，不代表 CPU 问题已全面解决。

同时通过本地网关只读获取网页实际状态流和视频，未发控制或心跳：194/194 位姿有效，最大年龄 0.310 秒，最大状态间隔 0.375 秒，145/145 JPEG 成功。真实用户仍须 Ctrl+F5 刷新旧页面以获取新网关 cookie/前端代码。未发起探索或实车运动，不能把该静止结果写成自主任务通过。

最终适配器 PID129950，本地网关 PID46276；准确 mapper 身份以 owned-processes.json 最新 slam 项为准（Reset 每次更新）。源码 adapter SHA256 d6c079faffe1860fbeeca5ac5152a6d62d3f0b152cefd0ab1fb7955d5340bd6c，mapping SHA256 5dbe1f737f06b038f75f3bb249e1bb3fcc3ac0690ad65cec53b6f350d992b673，规范实车 SLAM 配置 SHA256 9c63e52c7110a683a4ef2d9f0d3929834b02f4530df337f3ad00a6f488659845。地图更新恢复 1 秒、队列 3、SDK 平移关键帧 0.03 米。车端使用独立 SDK install，未改系统安装或开机项。

最终原始证据：verify-final-queue3-health.remote-result.json、verify-web-queue3-readonly.result.json、verify-live-map-reset-queue3.result.json。车端 queue3-final-verification-1793441045618337351.json 留有逐样本。先前 71/99 的失败记录保留；相机长期 RSS 增长与完整运动验收仍是限制。
