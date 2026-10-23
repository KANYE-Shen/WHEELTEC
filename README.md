# WHEELTEC：二维建图与自主导航

用现有 WHEELTEC 小车完成房间探索、二维建图、重定位和网页点选导航。先在电脑仿真，再将导航系统部署到小车的地瓜派 RDK X5。

**实车的建图、定位、自主探索、Nav2 和底盘控制在车端运行。电脑负责显示地图、姿态和视频，以及下发目标。车端持续使用本地传感器数据计算运动指令，已接收任务的执行不依赖 SSH 连接。**

GitHub 仓库：[KANYE-Shen/WHEELTEC](https://github.com/KANYE-Shen/WHEELTEC)。

## 当前进度

更新：2026-10-23。

- 基础环境已安装：WSL2、Ubuntu 22.04、ROS2 Humble、Gazebo Fortress、RViz、Nav2、SLAM Toolbox。
- 已检查 ROS 消息收发、仿真时钟、模拟激光数据以及 Gazebo/RViz 图形窗口。
- 项目已迁移到 D 盘，85 个原文件迁移时逐一通过 SHA256 校验。
- 已建立 5×5 米房间、三处静态障碍和差速参考小车，接通 360° 激光、里程计、TF、仿真时钟与速度控制。
- 已验证虚拟小车前进、停止和转向，Gazebo/RViz 场景可显示。
- 已接入 SLAM Toolbox、Nav2、地图保存与 AMCL 重定位。建图模式四个目标和重定位后一个目标均已到达，Gazebo 真值到位误差约 12.6–17.3 cm。
- 自主探索闭环已通过：自动到达4个探索目标，已知空地约22.7平方米，保存地图和位姿图后返回起点，返航误差15.3 cm。
- 临时箱子绕行、封路等待、移除障碍后原任务继续、取消后停车及保存地图不变已通过；已补充图文操作指南、遥控和各模式双击入口。
- 已加入本机 Gazebo 画面同步补丁，约62秒的900帧完整场景与小车运动检查通过；GPU 加速保留。根目录启动入口由9个精简为6个，按用途重新命名。

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
| `启动_自主探索建图.cmd` | 小车自己选择探索目标，保存地图并返回起点 |

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

## 仿真怎么推进

仿真阶段，Gazebo、建图、定位、探索和 Nav2 全部在电脑的 WSL Ubuntu 中运行。Gazebo 提供虚拟传感器数据，并根据速度指令更新虚拟小车的位置。

1. **准备小车和房间。** 建立车体、激光和里程计模型，以及约 20–30 平方米的封闭房间。先检查尺寸、坐标关系、数据频率与速度指令是否一致。
2. **跑通建图与移动。** 用 SLAM Toolbox 根据激光和里程计生成二维占据栅格地图，检查小车移动时地图与位置是否稳定。
3. **加入自主探索。** 探索模块选择尚未观察区域附近的目标，Nav2 负责规划和行驶。逐步验证绕障、无路可走时停车、探索结束判定和返回起点。
4. **保存并重新定位。** 保存地图和人为标定的参考方向；重启定位模块，允许给定粗略初始位置与朝向，检查能否在原地图中恢复位置。
5. **验证点选导航。** 指定地图目标，检查路线、到位误差和任务状态，并测试新增障碍、绕行、无路等待及监看连接断开。
6. **整理结果，再接实车。** 保存每次实验的参数与结果；核查真实底盘、里程计、传感器和坐标变换，再将功能部署到地瓜派进行低速测试，最后整合进已有网页。

当前仿真已通过上述建图、探索、保存、重定位、目标导航和临时障碍检查。下一步是实车只读核查和网页整合，监看连接断开后车端持续执行需在部署阶段验证。

首版用激光建图，相机用于监看。仿真中的真实位置只用于计算误差，定位和导航使用传感器估计的位置。详细目标见 [PLAN.md](PLAN.md)。

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

## 更新记录

| 日期 | 事项 |
| --- | --- |
| 2026-10-22 | 安装 D 盘 WSL 仿真环境并完成基础检查；整理项目目录；明确主要算法在地瓜派运行；添加 AGENTS.md 和仿真流程。 |
| 2026-10-22 | 全部项目内容迁至 `D:\虚拟c盘\WHEELTEC`；准备 25 平方米参考场景，完成传感器、运动与图形检查。 |
| 2026-10-22 | 接入 SLAM、Nav2、AMCL、地图保存与自主探索；通过目标导航、返航及临时障碍检查，补充图文操作指南。 |
| 2026-10-23 | 修复 WSLg 下 Gazebo 绘制交接造成的场景消失；精简并重新命名六个常用入口。 |
