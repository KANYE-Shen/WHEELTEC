# 仿真环境安装状态

更新：2026-10-22。基础环境、建图、导航、地图保存、重定位、自主探索及返航已通过实际仿真。

## 已安装

| 组件 | 已核实版本或状态 |
| --- | --- |
| WSL2 | WSL 3.0.3.0，内核 6.18.54.1-1，WSLg 1.0.79 |
| Ubuntu | 22.04.5 LTS；默认普通用户 wheeltec |
| ROS2 | Humble desktop 0.10.0 |
| Gazebo Fortress | Gazebo Sim 6.18.0；ros_gz 0.244.26 |
| Nav2 | navigation2 / nav2_bringup 1.1.20 |
| SLAM Toolbox | 2.6.10 |
| 开发工具 | ros-dev-tools、编译工具、colcon 等依赖 |

Linux 虚拟磁盘实际位置为 `D:\WSL\WHEELTEC-Ubuntu-22.04\ext4.vhdx`。开发工作区为 `/home/wheeltec/wheeltec_sim_ws`，位于该 D 盘虚拟磁盘内。

项目源码和手写配置统一维护在 Windows 项目根目录 `D:\虚拟c盘\WHEELTEC`，WSL 通过 `/mnt/d/虚拟c盘/WHEELTEC` 读取。已建立 `src/`、`simulation/`、`robot/`、`data/` 入口。Linux 工作区归 `wheeltec` 用户管理，已建立 `build`、`install`、`log` 和 `data/maps`、`data/bags`、`data/runs` 目录，用于后续构建与实验数据；现有 Linux `src/` 为空，不另维护一套源码。

`C:\Users\30120\.wslconfig` 仅设置 `swapFile=D:\\WSL\\wheeltec-swap.vhdx`，将 WSL 交换文件放到 D 盘；这是 WSL 的全局设置。已重启 WSL 并核实该文件生成、Linux 可使用 2 GiB 交换空间。

环境安装完成时记录：Linux 虚拟磁盘文件约 7.7 GiB，Linux 文件系统已用约 6.3 GiB；交换文件按实际使用增长。C 盘剩余约 34.3 GiB，D 盘剩余约 72.6 GiB。数字会随系统使用变化。Windows 的 WSL 系统组件仍在系统位置。

## 已通过的实际检查

- `dpkg --audit` 无异常输出，`apt-get check` 成功，软件依赖完整。
- 默认用户是 `wheeltec`；终端自动加载 `ROS_DISTRO=humble`、`ROS_DOMAIN_ID=77`、`ROS_LOCALHOST_ONLY=1`，进入开发工作区。
- C++ talker 向 Python listener 成功传递至少 3 条 ROS 消息。
- Gazebo 物理服务器启动，ROS 通过 ros_gz_bridge 收到连续递增的仿真时钟。
- OpenGL 使用 D3D12 / NVIDIA GeForce RTX 4070 Laptop GPU，硬件加速已启用。
- Gazebo 和 RViz 窗口均可启动，已通过 Windows 侧截图人工检查；当前房间入口可见三维场景、雷达、二维地图和 TF，RViz Global Status 为 OK。
- Gazebo 自带激光场景通过兼容渲染模式运行，ROS 收到至少 2 条 LaserScan，每条 640 个距离值，检查样本中有 315 个有限距离值。
- 调整交换文件位置后，WSL 冷启动成功，默认用户及 Linux 文件系统正常。

## 已处理的兼容性问题

本机 WSLg 下，Gazebo 默认 Ogre2 渲染触发 `GL3PlusTextureGpu::copyTo` 异常。图形入口已加 `--render-engine-gui ogre`；激光场景已使用 `--render-engine-server ogre` 验证通过。

以后在终端启动同时包含界面和传感器的场景时，可明确指定：

```bash
ign gazebo --render-engine ogre -r <场景文件.sdf>
```

后续自定义仿真启动文件也应保留兼容渲染配置。没有更换 Windows 显卡驱动，也没有改成 Gazebo Classic。

检查脚本中的通信域遗漏和配置包版本格式校验错误已修正。曾失败的原始日志保留在 Linux 的 `simulation-checks` 和 D 盘安装日志中，不把这些失败记录当作最终通过结果。

## 验证证据

基础环境安装阶段的检查结果：

- `setup/verification/runtime-result.json`：ROS 收发、仿真时钟、软件版本和 OpenGL 检查。
- `setup/verification/gui-result.json`：两个图形窗口及 Windows 截图记录。
- `setup/verification/lidar-result.json`：激光传感器桥接检查。
- `setup/verification/gazebo-windows.png`、`rviz-windows.png`：实际窗口截图，已查看。

Linux 原始日志目录：

- `/home/wheeltec/simulation-checks/20261022-113311`
- `/home/wheeltec/simulation-checks/gui-20261022-114019`
- `/home/wheeltec/simulation-checks/lidar-20261022-114113`

安装日志：`D:\WSL\wheeltec-setup-20261022\ubuntu-provision-verified.log`，最终退出码 0。

安装镜像仍保留在 `D:\WSL\wheeltec-setup-20261022`：

| 文件 | 已核实 SHA256 |
| --- | --- |
| `wsl.3.0.3.0.x64.msi` | `ae977286974255bd26bf925f00f40f5692c6b2084155cbc0563c09aea091f211`；微软数字签名 Valid |
| `ubuntu-22.04.5-wsl-amd64.wsl` | `4499c4fe257f2fc83145b429ce211a0a43fd590e70d6261ede616210947d9f8f` |

## 当前范围与下一阶段

当前25平方米参考场景已接入 SLAM Toolbox、Nav2、AMCL、保存服务和 wheeltec_explore。接口检查验证前进0.45米、转向0.70弧度与墙距变化；导航检查验证建图四目标及重启 AMCL 后一目标；探索检查验证自动选点、保存和返回；障碍检查验证绕行、封路与取消停车。下一步核查实车接口及车端运行条件，再整合网页。

原有双系统 Ubuntu、实车及监看网页均未改动。后续按 PLAN.md 的阶段推进。

## 官方来源

- [WSL 安装与配置](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)
- [ROS2 Humble 安装说明](https://github.com/ros2/ros2_documentation/blob/humble/source/Installation/Ubuntu-Install-Debs.rst)
- [ROS 软件源配置包](https://github.com/ros-infrastructure/ros-apt-source/releases/tag/1.3.0)
- [Gazebo 与 ROS 版本配对](https://gazebosim.org/docs/fortress/ros_installation/)
- [Gazebo 官方故障排查](https://gazebosim.org/docs/fortress/troubleshooting/)
- [Gazebo 渲染项目中的 WSLg / Ogre2 问题](https://github.com/gazebosim/gz-rendering/issues/662)

## 2026-10-22 项目迁移与房间场景

项目根目录为 `D:\虚拟c盘\WHEELTEC`，WSL 路径为 `/mnt/d/虚拟c盘/WHEELTEC`。迁移时全部 85 个文件（包括 .git）通过逐文件 SHA256 核对，校验后清空 C 盘原目录内容。历史记录见 `migration-result.json`，其中哈希对应路径更新前的文件。旧图形检查 JSON 保留当时的截图路径；当前房间截图和结果位于 `verification/room/`。

本机 Ogre 单垂直扫描线输出全部最小量程，改为三条相邻垂直渲染线，由 ROS 桥接取中间线；保留 360°、720 束的二维输出。验证脚本同时检查实际墙距，防止把有消息等同有效测距。加载 room.rviz 后的窗口标题已适配 Windows 截图工具。


## 当前算法验证（2026-10-22）

| 检查 | 实际结果 | 项目证据 |
| --- | --- | --- |
| 房间接口 | 720束有效激光、时钟/里程计/TF连续；前进0.45米、转向0.70弧度 | [room-result.json](verification/room/room-result.json) |
| SLAM → 保存 → 重启 AMCL → Nav2 | 5个目标全部成功，真值误差12.6–17.3厘米 | [导航结果](verification/navigation/result.json) |
| 自主探索 → 保存 → 返回 | 4个探索目标，已知空地22.713平方米，返航误差15.3厘米，completed | [探索结果](verification/exploration/result.json) |
| 临时障碍 | 箱子绕行成功，封路等待时3秒内位置/朝向不变，移除障碍后原任务到达，取消后静止，地图文件哈希不变 | [障碍结果](verification/obstacles/result.json) |
| 遥控/探索规则 | 12个探索规则测试、5个遥控规则测试、1个真实ROS终端退出停车测试通过 | simulation/test_teleop*.py、src/wheeltec_explore/test |
| 图形界面 | Gazebo播放/暂停可见、RViz地图/姿态/导航工具可见；截图已查看 | [房间GUI](verification/room/gui-result.json) |
| 操作指南 | 本地HTML用Chrome离线渲染并查看，中文与图片正常 | [指南截图](verification/operator-guide.png) |

控制器使用 Regulated Pure Pursuit，规划器为 NavFn A*。Humble 的 SLAM Toolbox 2.6.10 需要将 minimum_travel_distance 设为0，使原地旋转扫描进入匹配；否则转角里程计误差会在障碍层留下错误墙线。设置原因和源码链接见 simulation/README.md。

任务终端已确认完成后的结果、地图和完整日志保存在各 JSON 的 run_dir。地图小样例见 data/samples/room-25m2；大位姿图不进入 Git。仿真真值只用于误差评估，算法未订阅它。

实车的驱动、里程计、IMU、TF、车体尺寸与并行运行负载仍需现场核查；主要算法在 RDK X5 运行的架构要求已写入 AGENTS.md。网页地图/姿态/目标与车端常驻服务属于下一阶段。
