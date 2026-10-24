# 房间建图、定位与导航仿真

第一次使用先读 [操作指南](操作指南.md)，其中按窗口与体验步骤说明鼠标、遥控、地图、导航和退出。

房间内部 5×5 米，包含三处静态障碍。差速参考车起始世界位置 (-1.7,-1.5)，朝 +X；建图地图原点位于小车起点附近。车体、轮径与轮距是仿真参考，实车阶段按实际测量配置。

## 启动模式

Windows 默认双击 `启动_手动建图.cmd`。Linux 仿真终端也可运行：

```bash
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/run_room.py
# 自动探索
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/run_room.py explore:=true
# 最近保存地图 + AMCL；启动后在 RViz 用 2D Pose Estimate 给粗略位置
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/run_room.py mode:=localization
# 指定另一张地图
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/run_room.py mode:=localization map:=/home/wheeltec/wheeltec_sim_ws/data/maps/某次实验/room.yaml
# 无图形运行；接口模式可另加 mode:=interfaces
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/run_room.py gui:=false rviz:=false
```

普通会话使用域77，启动器会阻止在同一域打开第二套房间。启动终端 Ctrl+C 结束整个会话。

`mapping` 使用 SLAM Toolbox 在线更新地图；`localization` 用 AMCL 在已存地图中定位。两个模式共用 Nav2，规划 A*、控制 Regulated Pure Pursuit（RPP）、实时激光障碍层及速度平滑。Nav2 只穿越已知空地，位置容差0.15米，终点朝向不限。封路时保留激光障碍观测，停车等待并每5秒重试，最多60次（约5分钟）；移除障碍后原目标继续，随时可以取消。此行为由 `config/navigate_wait.xml` 定义，不调用旋转、后退或清空全局障碍的恢复；跟踪失败时仅刷新局部图，并等待0.5秒接收新激光后才重试。键盘遥控不经过 Nav2，使用时由操作者避障，并在导航前退出遥控。

## 场景选择与过程记录

双击自主入口后选择5种布局（原房间、L形、家具、弯通道、凹角）和起点0/1/2。Windows非交互重复：

```powershell
.\simulation\Start-Room.ps1 -Explore -Scenario l_shape -Spawn 2
```

Linux直接启动：

```bash
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/run_room.py explore:=true scenario:=l_shape spawn:=2
```

普通自主会话自动启动只读浏览器过程页，约5秒刷新。页面可播放、暂停、拖动时间、调整倍速及切换地图/激光/估计车头/已走轨迹/规划路线。仅绘制所选时刻已记录的算法估计，不使用仿真真值，缺失或过期数据单独标明。关闭网页不会停止算法；完整退出用启动终端 Ctrl+C。

记录在 Linux `data/runs/时间_场景_spawn起点/`：`process.json`、自包含 `replay.html`、`session.json`。任务终态时自动导出回放；中途退出也保存已记录过程。普通会话没有独立评分，页面显示未评分；验证目录若有 `result.json`，页面单独显示本次最终覆盖率、轮廓p95与返航误差验收。任务 completed 与独立验收通过分别显示。

已有验证记录可直接导出或只读浏览：

```bash
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/view_process.py export ~/wheeltec_sim_ws/data/runs/某次实验/process.json
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/view_process.py serve ~/wheeltec_sim_ws/data/runs/某次实验
```

serve仅绑定127.0.0.1，打印自动选择的端口；只开放固定过程、评分与回放文件，没有控制或写入接口。`replay.html`内含数据与代码，可直接双击离线查看。

普通自主保存地图前预留 `.simulation.json`，记录场景ID、起点和场景SHA-256。加载最近地图或显式map时自动恢复同场景；历史地图没有sidecar继续使用原房间。场景文件校验不一致会停止启动；用户主动传入 `scenario:=ID spawn:=N` 才覆盖恢复信息。此记录不会传给SLAM、Nav2或探索策略。 手动建图或自主探索运行时点击原有“保存当前成果”，也会保存当前活跃房间的布局与起点。身份来自同域启动会话，并核对进程及其互斥锁；退出后遗留记录不会被当作当前房间。

## 地图保存

建图运行、车停稳时双击 `地图_保存当前成果.cmd`，或在加载 ROS 的终端运行：

```bash
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/save_map.py
# 自定义参考方向：相对 map +X 逆时针 30°
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/save_map.py --reference-yaw 0.5235987756
```

默认生成新的时间目录，保存 `.yaml`/`.pgm`占据地图、`.posegraph`/`.data`位姿图和`.metadata.json`参考方向。`~/wheeltec_sim_ws/data/maps/latest.json`指向最近保存地图。AMCL加载占据地图，位姿图用于后续继续建图；参考方向不等同地理北。

## 文件与接口

| 内容 | 文件 |
| --- | --- |
| 车体、激光和差速驱动 | models/wheeltec_reference/ |
| 房间与图形工具 | worlds/room_25m2.sdf |
| 话题桥接、SLAM、Nav2、RViz参数 | config/ |
| 仿真与算法启动 | launch/room.launch.py、launch/navigation.launch.py |
| 前沿探索算法与任务状态 | ../src/wheeltec_explore/ |
| 保存地图、键盘遥控 | save_map.py、teleop.py |

仿真输入为 `/clock`、`/scan`、`/odom`、`/tf`，速度输出为 `/cmd_vel`。完整坐标链为 `map → odom → base_link → wheeltec_reference/base_link/laser`；接口模式没有 map。激光360°、720束、10Hz，里程计约30Hz。

保留 Ogre 兼容渲染，以及三条相邻垂直渲染线、桥接取中间水平线的激光配置。`/simulation/ground_truth`仅供检查程序评估实际位置，SLAM、Nav2和探索不读取它。轮式里程计会随转弯打滑产生偏差，不能把 `/odom` 当作实际位置。

## 检查

先加载 ROS 和已构建的探索包：

```bash
source /opt/ros/humble/setup.bash
source /home/wheeltec/wheeltec_sim_ws/install/setup.bash
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/check_room.py
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/check_navigation.py
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/check_exploration.py
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/check_obstacles.py --map /home/wheeltec/wheeltec_sim_ws/data/runs/<导航实验目录>/map.yaml
python3 /mnt/d/虚拟c盘/WHEELTEC/setup/check-gui.py --room
```

检查使用独立仿真域，将原始日志和指标写入 `~/wheeltec_sim_ws/data/runs`。小型结果摘要见 `../setup/verification/`。本轮步骤见 [实施记录](IMPLEMENTATION.md)。

接口来源：[SLAM Toolbox Humble](https://github.com/SteveMacenski/slam_toolbox/tree/humble)、[Nav2 Humble](https://github.com/ros-navigation/navigation2/tree/humble)、[Gazebo Fortress](https://gazebosim.org/docs/fortress/)。

SLAM Toolbox 2.6.10 的扫描预过滤只检查平移，原地旋转时会跳过扫描，造成旋转里程计误差积累并在障碍层留下错误墙线。本项目将 `minimum_travel_distance` 设为0，让原地转弯也进入扫描匹配；`minimum_time_interval: 0.1` 控制处理频率。版本依据：[2.6.10 的 shouldProcessScan](https://github.com/SteveMacenski/slam_toolbox/blob/2.6.10/src/slam_toolbox_common.cpp)。

## 图形兼容与连续帧检查

本机使用 Ogre + GPU 加速。`gui_sync/` 的局部插件在 Ogre 绘制完成及 Qt 读取场景纹理后分别等待 GPU，避免界面拿到未画完的图。`run_room.py` 在插件缺失或源码更新时自动编译到 Linux `~/wheeltec_sim_ws/build/gui_sync/`，无需替换系统 Gazebo 库。物理、雷达和导航参数沿用原配置。改动后需重新启动仿真。

启动房间后，在 WSL 终端可运行以下检查。保持默认房间视角；如果有多个 Gazebo 窗口，先用 `xwininfo -root -tree` 找到对应窗口，再加 `--window-id 0x...`。该检查同时识别场景退化为单色，以及地板、绿色柜体、棕色家具缺失的帧；任一情况会返回非零退出码。结果中的 unique_scene_images 用于配合运动实验确认画面持续变化。

```bash
python3 /mnt/d/虚拟c盘/WHEELTEC/setup/check-rendering.py \
  --frames 600 --output ~/simulation-checks/render-check
```

插件构建需要已安装的 `cmake`、C++ 编译器、`libignition-gui6-dev` 和 Qt5 开发依赖。单独重建可执行 `python3 simulation/build_gui_sync.py`。渲染修复原理和验证记录见 [环境状态](../setup/STATUS.md)。
