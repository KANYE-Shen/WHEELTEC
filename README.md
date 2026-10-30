# WHEELTEC：二维建图与自主导航

WHEELTEC / RDK X5 的 ROS 2 Humble 项目：二维激光建图、自主探索、存图返航及 Nav2 导航；电脑使用 WSL2 + Gazebo Fortress 验证，并通过本地网页终端监看和调试。

实车算法与安全服务在车端运行，电脑负责监看、开发及任务下发。服务独立于 SSH；操作者心跳失效后停车保持，恢复连接不自动续行。相机目前只用于监看，未融合定位。

## 现行实车流程

更新：2026-10-29。当前只采用以下三个阶段，详细检查、预期读数、停止条件和回滚见 [实车准入清单](robot/准入关卡.md)。

| 阶段 | 任务 | 交付 |
| --- | --- | --- |
| 一：连接、订阅确认与校准 | 静止检查时间/雷达/相机/odom/TF；验证停车链路后进行低速校准 | 订阅报告、bag、现场测量与日期校准 JSON、realism 参数 |
| 二：人工参考建图及导航验证 | 人工建图，以独立测量检查 SLAM Toolbox；保存参考图，再验证 Nav2 规划、绕障、等待和停车 | 人工参考图、SLAM 误差和各导航目标结果 |
| 三：自主探索建图 | 算法自行选择目标，探索、另存地图并返航，与人工参考及独立测量对比 | 自主图、独立质量评分、全部失败与 sim-to-real gap |

阶段一内部按静止订阅→停车验证→低速校准执行，不再拆成原 G0–G2；阶段二合并原人工建图/导航，阶段三为监督自主探索。原 G0–G5 编号仅用于历史证据，G6–G9 建议已取消。人工地图是参考，不能代替卷尺等独立测量；自主地图单独保存。

**阶段一尚未完成，三个阶段均未验收通过。** 每阶段的具体实测范围仍须用户书面确认；流程调整不授权实车运动，旧批准不自动迁移。运动模板使用 `three-stage-20261029` 协议及内部 `gate=1/2/3`，默认只读、硬件未确认、批准记录为空。

## 当前结果与未解决问题

| 验证范围 | 实际结果 | 结论与证据 |
| --- | --- | --- |
| 原房间建图/存图/重定位/导航 | 目标误差约 12.6–17.3 cm，探索返航 15.3 cm | 特定参考场景通过；不代表陌生房间或实车达标，[原记录](simulation/validation.md) |
| 陌生房间 13 组 | 独立验收 1/13，内部 completed 2/13 | [逐组结果](setup/verification/unknown_rooms/README.md) |
| realism=on 基线与噪声扫描 | 0/75、0/20；全部尝试保留 | 参数仍为 assumed，[回归报告](setup/verification/2026-10-27-regression-results.md) |
| 遮挡感知视点 A/B | realism=on 两策略均 0/10 | 默认 centroid 不变，visibility 仅显式试验，[报告](setup/verification/2026-10-27-irregular-frontier-results.md) |
| 主动观测旧批次 | 严格 0/40，首目标 0/40 | 起点安全空间不足及 TF 消费滞后；[夜间记录](setup/verification/2026-10-28-night/README.md) |
| 起点旋转例外单种子仿真 | 221 帧，6 个目标成功，行驶 14.11 m，返航 13.41 cm；严格验收 0/1 | 墙面 p95 16.83 cm、轮廓覆盖 81.72%，仍 incomplete；[原始结果](setup/verification/2026-10-29-startup-assumption/README.md) |
| 网页终端真实仿真 E2E | 最近完整批次 9/12 | 运动近点保护及多客户端超时未解决，[报告](setup/verification/2026-10-27-console-results.md) |
| 实车只读采样（2026-10-28） | 雷达约 10.02 Hz，60.775 s/610 条；视频可见，源时间异常；odom/TF 缺失 | 已连接过实车；底盘、安全停车、完整负载未验证，[采样记录](setup/verification/2026-10-28-g0/sensors-on-v1/README.md) |

以上批次条件不同，不能合并成一个成功率。尚无实测参数完成的 sim-to-real gap，不能建议跳到自主实车探索。每布局/起点的正式仿真至少 5 个固定种子并报告 Wilson 区间；单变量同种子 A/B，原验收门限不变。

主动观测原型默认关闭。仅隔离仿真起点可显式使用 `initial_rotation_assumed_safe=true`，记录为 `assumed_start`，跳过一次起点扫掠评估；途中旋转仍需安全评估，实车不适用。这不修改地图未知格或 Nav2 碰撞检查。[算法接口](src/wheeltec_explore/README.md) · [当前计划](PLAN.md)。

## 网页调试与控制终端

`console/` 使用 React/TypeScript、FastAPI/Paramiko 和 xterm.js，电脑无需 ROS。通过 SSH 展示实时雷达、相机、地图、估计位姿、消息健康与日志，提供交互式 PTY、WASD 遥控和可选 noVNC Gazebo/RViz 桌面；未连接时显示无数据。首版没有网页点选导航或探索启动按钮，阶段二的目标验证须使用经批准的 Nav2 客户端。

在仓库根目录安装并启动：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r console/requirements.txt
npm ci --prefix console/frontend
npm run build --prefix console/frontend
.venv\Scripts\python.exe console/start.py
```

打开 **http://127.0.0.1:8766** → 连接设置 → 核对 SSH 指纹 → 填目标、账户及 SSH 凭据、适配器访问令牌 → 连接。热点密码、SSH 密码和适配器令牌用途不同，不能互相推定；令牌由目标适配器首次启动生成。密码和令牌不进入配置、日志或仓库。WSL/实车接入、面板用途及故障处理见 [终端说明](console/README.md)，扩展见 [API 与面板示例](console/API.md)。

取得手动控制权后按住 **W/S 前后、A/D 转向，松键停车，空格停车保持**。失焦、切后台、终端/输入框获焦、断链或租约过期均释放遥控；重连不恢复旧按键。实车默认只读，未通过安全预检不能遥控；无法取得最终 watchdog 的新鲜停车确认时拒绝维护 PTY。完整 shell 是 SSH 账户权限，不能当作受限运动接口。软件停车不等于硬件急停。

相机闪烁修复有实车只读专项证据；后续 Hz/时间健康修复仅离线回归，未部署。源时间异常继续告警，缓存画面不冒充实时数据。实车运动与板上满负载仍未验证。

## 现在怎么操作

双击 `帮助_操作指南.cmd` 可在浏览器打开图文说明，也可读 [双窗口操作指南](simulation/操作指南.md)。Gazebo 是虚拟现场，RViz 显示雷达、地图、位置和路线。

根目录只保留以下六个入口。三个启动入口代表不同模式，每次选一个。

| 双击入口 | 用途 |
| --- | --- |
| `帮助_操作指南.cmd` | 在浏览器打开图文操作指南 |
| `启动_手动建图.cmd` | 新建地图，同时启动 SLAM 与 Nav2 |
| `控制_键盘遥控.cmd` | 点击遥控终端，用 i 前进、逗号后退、j/l 转向，k 或空格停车，q 退出 |
| `地图_保存当前成果.cmd` | 在建图运行且车已停稳时保存地图、位姿图和参考方向 |
| `启动_已有地图导航.cmd` | 加载最近保存的地图；先用 RViz 的 2D Pose Estimate 指定粗略起点，再用 Nav2 Goal 下目标 |
| `启动_自主探索建图.cmd` | 选择房间和起点，小车自主探索、保存和返回；自动打开过程网页 |

自主探索入口中先选布局（回车为原房间），再选起点（回车为0）。网页显示地图、激光、车头相对初始方向的偏角、已走轨迹和任务状态。拖动时间轴回看，点“回到实时”继续跟随；结束后可双击本次过程目录中的 `replay.html` 离线回放。普通探索不计算真值评分，网页明确显示“未评分”。

切换场景前，在原启动终端按 Ctrl+C 结束。点选导航前退出键盘遥控；遥控没有自动避障。不要同时开两套房间仿真。

画面闪烁修复需要重开仿真：在原启动终端按 Ctrl+C，再双击相应启动入口。旧窗口不会自动加载补丁。

RViz 点选导航：点工具栏 **Nav2 Goal**，在已观察到的浅色空地按住左键，拖出短箭头再松开。首版只要求到达位置，不要求终点朝向。完整按键、鼠标操作与取消步骤见上面的指南。

## 项目文件放在哪里

项目根目录：`D:\虚拟c盘\WHEELTEC`。源码和手写配置统一在这里维护。

```text
WHEELTEC/
├─ README.md              本页：进度、流程、路径、启动方式
├─ AGENTS.md              给后续开发者和 agent 的项目约定
├─ PLAN.md                已确定的目标、阶段与候选开源模块
├─ 部署说明.md             环境准备与实车部署分工
├─ src/                   wheeltec_explore ROS 功能包和共用算法源码
├─ simulation/            仿真模型、房间、参数和测试场景
├─ console/               本地网页终端、SSH 网关、目标端适配器与扩展接口
├─ robot/                 地瓜派上的配置、启动与服务部署文件
├─ data/                  地图、录包和实验结果的位置索引
├─ setup/                 环境安装、检查脚本和验证记录
├─ 启动_手动建图.cmd
├─ 控制_键盘遥控.cmd / 地图_保存当前成果.cmd
├─ 启动_已有地图导航.cmd / 启动_自主探索建图.cmd
└─ 帮助_操作指南.cmd
```

大文件与运行环境放在 D 盘，由 WSL 管理：

| 内容 | 位置 |
| --- | --- |
| Ubuntu、ROS2 及已安装软件 | `D:\WSL\WHEELTEC-Ubuntu-22.04\ext4.vhdx` 内；ROS 位于 Linux `/opt/ros/humble` |
| 编译、安装输出与编译日志 | Linux `/home/wheeltec/wheeltec_sim_ws/build`、`install`、`log` |
| 生成的地图 | Linux `/home/wheeltec/wheeltec_sim_ws/data/maps` |
| ROS 数据录包 | Linux `/home/wheeltec/wheeltec_sim_ws/data/bags` |
| 每次实验的配置、指标、截图和日志 | Linux `/home/wheeltec/wheeltec_sim_ws/data/runs` |
| 已有基础检查原始日志 | Linux `/home/wheeltec/simulation-checks` |
| 安装镜像与安装日志 | `D:\WSL\wheeltec-setup-20261022` |
| WSL 交换文件 | `D:\WSL\wheeltec-swap.vhdx` |

在 Windows 资源管理器地址栏输入下面的路径，可以查看 Linux 工作区：

```text
\\wsl.localhost\WHEELTEC-Ubuntu-22.04\home\wheeltec\wheeltec_sim_ws
```

Linux 访问项目根目录的路径是 `/mnt/d/虚拟c盘/WHEELTEC`。后续构建读取这里的 `src/`，构建输出写到上表中的 Linux 目录；Linux 工作区现有的 `src/` 为空，不另存一套源码。数据命名和实验记录方式见 [data/README.md](data/README.md)。

## 从 Windows 打开环境

- 双击 `启动_手动建图.cmd`：同时打开本项目房间、ROS 桥接、SLAM、Nav2 和 RViz 地图视图。
- 开发终端：在 PowerShell 运行 `wsl.exe -d WHEELTEC-Ubuntu-22.04 -u wheeltec --cd /home/wheeltec/wheeltec_sim_ws`。

房间场景使用仿真参考尺寸：轮半径 0.075 m、轮距 0.35 m；后续按实车测量更新。运行步骤、话题和接口检查命令见 [simulation/README.md](simulation/README.md)。在启动终端按 Ctrl+C 可结束本次仿真。

终端默认加载 ROS2 Humble，使用 `ROS_DOMAIN_ID=77`、`ROS_LOCALHOST_ONLY=1`。本机 Gazebo 使用 Ogre 兼容渲染和项目内的 GUI 同步插件。统一通过上面的双击入口或 `simulation/run_room.py` 启动，会自动准备兼容组件；直接运行 `ign gazebo` 不会自动添加项目插件路径。

开发用户为 `wheeltec`。如需使用 `sudo`，先在 Windows PowerShell 中为该用户设置密码：

```powershell
wsl.exe -d WHEELTEC-Ubuntu-22.04 -u root --exec passwd wheeltec
```

完整安装状态、基础检查命令和证据见 [setup/STATUS.md](setup/STATUS.md) 及 `setup/check-*.py`。

## 记录与后续开发

当前工作顺序及状态见 [PLAN.md](PLAN.md)，agent 规则见 [AGENTS.md](AGENTS.md)，实车执行只以 [三阶段清单](robot/准入关卡.md) 为准。每轮结果写入 [轮次索引](setup/verification/轮次索引.md)；失败动作、未执行动作和任务失败通过 [replay buffer](replay%20buffer/README.md) 索引，原始日志和失败批次保留。

### replay buffer：失败经验与证据库

[`replay buffer/`](replay%20buffer/README.md) 用于长期保存失败动作、未执行或中断的尝试、未通过验收的任务及调试结果。它让后续 agent 从已有证据继续排查和改进策略，减少重复踩坑，也防止只保留成功结果造成判断偏差。

每个案例集中记录：

- **发生了什么**：场景、起点/种子、配置与版本、预期行为、实际结果、失败或未执行原因；实车不适用的种子明确注明。
- **依据是什么**：原始日志、状态JSON、测试结果、前后对照，以及文件SHA256。大bag保留原位，库内记录路径与哈希。
- **如何继续**：复现条件、已排除假设、修复尝试、仍未验证的内容，以及安全限制。

推荐查阅顺序：`case.json` → 案例README → `manifest.json`及原始日志 → 复现与回归。后续 agent 应先据此提出可证伪假设，再做单变量、同种子A/B；保留原失败和完整批次，不放宽验收门限。

当前可查阅[不规则弧形场景失败](replay%20buffer/20261029-irregular-arc-seed0-startup-assumed/case.json)与[阶段一静止核查记录](replay%20buffer/20261030-stage1-stationary-incomplete/README.md)。历史大批次仍按索引存放，并未全部逐条迁入；同一问题的多个诊断步骤不能计作独立任务成功率。

该目录目前只用于证据归档和审阅，不自动训练、调参或重放实车动作。日志中的命令、历史批准和旧PID均不构成新的执行授权；实车仍遵守三阶段流程及当前禁动限制，仿真真值仅用于评估。

旧设计文件均标记为历史；证据目录中的旧编号描述当时试验，不构成现行任务或运动授权。本轮全仓库检查、覆盖清单和发布验证见 [一致性审计](setup/verification/2026-10-29-github-three-stage-audit/README.md)。
