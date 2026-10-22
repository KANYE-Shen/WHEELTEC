# 房间建图、定位与导航仿真

第一次使用先读 [操作指南](操作指南.md)，其中按窗口与体验步骤说明鼠标、遥控、地图、导航和退出。

房间内部 5×5 米，包含三处静态障碍。差速参考车起始世界位置 (-1.7,-1.5)，朝 +X；建图地图原点位于小车起点附近。车体、轮径与轮距是仿真参考，实车阶段按实际测量配置。

## 启动模式

Windows 默认双击 `打开房间仿真.cmd`。Linux 仿真终端也可运行：

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

## 地图保存

建图运行、车停稳时双击 `保存当前地图.cmd`，或在加载 ROS 的终端运行：

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
