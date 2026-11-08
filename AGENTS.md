# WHEELTEC 开发约定

本文件规定当前项目的开发和安全边界；用户操作从 [README.md](README.md) 开始。历史部署、验证和授权以 `setup/verification/` 的原始记录为准，不自动成为当前实车操作许可。已实现、已部署和已验收应分别表述。

## 现有产品和职责

“控制终端”是 `http://127.0.0.1:8766` 的现有网页：`console/start.py` 启动；`console/frontend/` 为 React/TypeScript 界面，`console/backend/` 为 FastAPI/Paramiko 本机网关，`console/target/adapter.py` 为车端适配器。连接经固定主机指纹 SSH 隧道到车端回环接口，电脑无需 ROS。SLAM、Nav2、探索、任务和安全链运行于车端 RDK X5；相机只监看。

保留网页地图、雷达、相机、日志、空间拖动、按钮缩放、自主探索、远程接管、WASD、Space 和三挡；网页无任意点选导航。低/中/高默认 0.03/0.06/0.10 m/s，自主开始为中挡。自主/启动模式下普通键、输入框焦点及可见窗口失焦不取消；非输入区 WASD 先安全停止并接管，只有仍按住才行驶。手动失焦、页面隐藏/关闭、断连和心跳失效停车，不能自动续行或伪造后台心跳。Space 抢占停车；重连不恢复旧按键。

## 优先复用现成能力

车端厂家目录 `/home/wheeltec/wheeltec_ros2/src` 已集成驱动、URDF、EKF、SLAM Toolbox、Nav2 及 `wheeltec_robot_rrt2` 探索链。厂家的完整 RRT 演示包含找箱行为，完成、取消和返航并不构成可直接替换的完整任务。

2026-11-08 停车部署后的网页任务配置已选择厂家 global/local RRT 与 filter 的候选接口，并由任务管理其节点、从当前地图取得采样范围和从安全配置取得几何参数；不要求网页操作者另行输入。原 CLI/仿真默认仍为栅格前沿。独立[厂家候选入口](src/wheeltec_explore/README.md#厂家-rrt-候选后端实验性)仍支持显式设置范围与参数。厂家候选空窗不代表完成，须用独立全图分析确认；地图范围变化需重新初始化厂家候选节点。厂家源码存在 `char` 有符号性差异，车端二进制构建方式未核验。该网页改动已部署车端，尚未启动实车探索或通过自主任务验收；停车状态与恢复依据见[部署记录](setup/verification/2026-11-08-vendor-web-deploy.md)，依赖与使用限制以包 README 为准。

不重新实现已有 SLAM、规划、跟踪、地图格式或硬件协议；优先组合厂家/标准接口。应保留任务语义：目标接受与终态、确认取消、失败冷却、完成/不完整、独立任务存图、起点返航和诊断。自主策略与任务层可以演进，但不得将局部已知率视为房间覆盖率，也不得以内部 completed 代替独立验收。

一套运行中必须明确唯一的 SLAM `map→odom` 发布者、导航 action 服务及底盘最终输出所有者。集成厂家入口前检查其节点、话题、参数和行为树；不能让厂家 launch 绕过现有速度仲裁或形成重复控制链。不要私自启用旋转、倒车或未知区穿行掩盖失败。

`src/wheeltec_slam/` 是上游 SLAM Toolbox 的门控扩展，并非新 SLAM 算法；已有配置保留 `scan_queue_size=3`、`stationary_keyframe_distance=0.03`，除非对照证据支持调整。动态 TF depth=10、安全/选择器状态 depth=1 及真实源时间用于避免积压；不要通过放宽超时掩盖故障。目标选择应与规划/碰撞保护区的几何一致，不缩小保护区或删除潜在真实障碍以制造通路。

## 实车与 SSH 安全

- 当前授权按用户当次范围执行。连接、部署、实际运动分别判断；历史受监督最高 0.10 m/s 或跳过完整校准例外只属于当时会话，不可迁移。实车操作按[三阶段准入清单](robot/准入关卡.md)提供具体允许动作、预期读数、停止条件和回滚，并取得相应书面确认。
- 自主由用户在网页发起；agent 不自行启动、解锁或发送非零速度。用户运行遥控/自主时不打开维护 PTY、停止、重启或干预。若当前限制为不发送底盘指令，也包含零速度、停车、心跳和模式切换。
- 有部署授权后先核实远端状态、唯一进程、无控制者、watchdog 新鲜未解锁、选择器 hold、最终输出及原始 odom 零速；运行中先由用户停车。保护现有地图、任务、日志与恢复路径，不擅自 Reset、重启整栈或设置开机项。旧 PID、命令及批准仅是历史线索。
- 保留速度来源单选、速度平滑、碰撞监控、最终 watchdog 与驱动命令超时；人工接管、失联、控制权丢失、急停与数据异常的停车语义不能丢失。软件发出零速不是物理停车验证，MCU 独立超时和实测制动仍待核实。
- SSH 必须校验已知指纹。密码、令牌、私钥不得写入脚本、参数、日志、仓库或聊天，不从历史对话取密。SSH 密码与适配器令牌不同；独立 SSH shell 不会给网关注入认证。
- 本机维护使用单独的 SSH 密钥，设置和路径只记录在当前用户的本地 `OneDrive/文档/ChatGPT/WHEELTEC/outputs/20261107-reuse-comparison/SSH密钥接续.md`，不将私钥内容放进仓库、聊天或日志。独立登录时使用现有 robot profile 的内存副本并校验其固定主机指纹，不修改网页 profile 或新增 robot profile；该密钥不改变部署或运动授权范围。
- `/api/v1/connect`、适配器 `/state` 及维护 PTY 可能触发 halt，不属于严格只读探活。用户操作期间勿调用；取证优先读取现有文件。维护 PTY 是完整账户权限，开启前必须获得 watchdog 的新鲜停车确认。
- 网页密码连接使用现有固定停车准备：不覆盖地图、不重启已运行组件、不自动解锁或探索；缺失组件按原约束补启，失败后人工判断和显式重试。保留 `/api/v1/connect` 对仿真及已有调用的原契约，不为新功能添加旧调用前提。

## 实验、诊断和验证

- 前沿候选计算不得阻塞 ROS 消息及健康检查回调；曾由同步计算引发 `scan_stale`/`tf_stale`，见[阻塞诊断](setup/verification/2026-11-01-debug-planning-starvation.md)。
- 网页任务的 prepare/ready/go 启动握手只约束网页拥有的任务；停止、失败或超时必须能抢占启动。普通 CLI 和仿真入口保留原有启动契约，不增加网页握手前提。见[启动状态间隙修复](setup/verification/2026-11-05-debug-startup-status-gaps.md)。

- 按问题、可证伪假设和必要的单变量对照推进；本次用户要求只做最简单的必要验证，**各类实验不超过 5 组**。保留失败、中断和未执行案例，不挑选成功结果或降低原验收门限。覆盖、轮廓误差、返航、停车和任务状态独立判断。
- 目标是受监督的 20–30 m² 房间二维激光探索、建图、存图、AMCL/导航及返航；约 20 cm 目标位置精度需独立测量。相机未用于定位，RGB-D、三维融合与强化学习不是当前能力。
- 历史陌生房间独立验收 1/13、现实化基线 0/75，均按原试验条件理解；不能用单测、服务在线或一次启动代替完整任务。真值仅供独立评估；不能用于在线 SLAM、导航、前沿选择或界面。
- 用户要求区域完成度为边界 70%＋内部 30% 各自归一化、达到 85% 自动换区，允许窄口分区；参考图只可离线核验。当前车端 85% 是目标周围 1 m 圆域已知格，距目标不超过 0.6 m 且连续两次不同地图更新满足才换点，地图外计未知；不是该区域策略。加权本地实验曾提前换点，未部署验收。
- 默认主动旋转观测关闭。`initial_rotation_assumed_safe=true` 仅隔离仿真起点可显式使用一次，并记录 `assumed_start`；途中转动仍须净空检查，实车不适用。不得把多帧扫描称为提高雷达单帧固有角分辨率。
- 不同仿真实验隔离 ROS domain、Gazebo partition 和运行目录；测试使用 `update_latest=false`，保护用户最近地图。保留 `simulation/gui_sync`、Gazebo 激光三线渲染/中线采样及已验证的 XML ASCII 临时路径；修改时检查渲染、扫描、运动和导航。
- 按故障时间线保存终态、适配器原因、watchdog `timeout_detail` 及相关 Nav2/SLAM/EKF 日志；TF 源时间和接收时间分开。未复现就记录未知，不沿用上次原因。`replay buffer/` 只做证据库，不自动训练或回放实车动作。
- 与修改相关的本机检查：`python -m unittest discover -s console/tests -v`、`npm test --prefix console/frontend`、`npm run build --prefix console/frontend`；按具体修改选取必要项。仿真、静止测试和完整用户自主任务的证据不可互相替代。

## 仓库和资料

源码仓库 `D:\虚拟c盘\WHEELTEC`；WSL 从 `/mnt/d/虚拟c盘/WHEELTEC` 读取源码，`/home/wheeltec/wheeltec_sim_ws` 放构建及运行数据。`console/` 是现有网页；`robot/` 是车端配置与安全；`src/` 是算法；`simulation/` 是仿真；`setup/`、`data/` 与 `replay buffer/` 存证据和索引。保留六个现有 `.cmd` 仿真入口及原始地图、bag、失败批次，不因厂家功能重合直接删除实验数据或兼容入口。

用户可见功能变化同步 [README.md](README.md)，阶段目标变化同步 [PLAN.md](PLAN.md)，环境变化同步 [setup/STATUS.md](setup/STATUS.md)。历史记录留原貌，当前问题可从[验证索引](setup/verification/轮次索引.md)、[启动与 TF 故障](setup/verification/2026-11-05-debug-startup-status-gaps.md)、[区域研究](setup/verification/2026-11-05-region-reference-and-latency.md)和[网页准备](setup/verification/2026-11-06-web-auto-prepare.md)继续。Git 操作只包含本任务授权的改动，不擅自提交、推送或清理其他工作。
