# 首轮房间仿真

已准备一个内部尺寸 5×5 米的封闭房间，包含三处静态障碍和一辆差速参考小车。小车初始位于房间坐标 (-1.7, -1.5)，车头朝 +X。

## 运行

在 Windows 双击项目根目录的 `打开房间仿真.cmd`，会同时启动 Gazebo、ROS 桥接和 RViz。

也可在仿真终端运行：

```bash
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/run_room.py
```

在启动终端按 Ctrl+C 结束本次仿真。只运行后台物理和传感器时：

```bash
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/run_room.py gui:=false rviz:=false
```

当前入口提供房间、传感器与底盘接口。下一阶段接入 SLAM Toolbox 后，再显示建图结果。

## 文件

| 文件或目录 | 内容 |
| --- | --- |
| `models/wheeltec_reference/` | 参考车体、车轮、激光与差速驱动 |
| `worlds/room_25m2.sdf` | 房间、障碍物与初始位置 |
| `config/bridge.yaml` | Gazebo 与 ROS 话题桥接 |
| `config/room.rviz` | 雷达、里程计与 TF 的视图 |
| `launch/room.launch.py` | 统一启动与退出 |
| `run_room.py`、`Start-Room.ps1` | Linux / Windows 入口 |
| `check_room.py` | 数据、坐标与短距离虚拟运动检查 |
| `PREPARE.md` | 本阶段准备步骤和验收条件 |

## 参考参数与接口

车体盒尺寸 0.36×0.28×0.12 m，轮半径 0.075 m，轮距 0.35 m。雷达平面距地面约 0.25 m，360°、720 束、10 Hz，里程计发布频率 30 Hz。这些数值用于首轮仿真，实车参数在核查后更新。

| ROS 话题 | 类型 | 方向 |
| --- | --- | --- |
| `/clock` | rosgraph_msgs/Clock | Gazebo → ROS |
| `/scan` | sensor_msgs/LaserScan | Gazebo → ROS |
| `/odom` | nav_msgs/Odometry | Gazebo → ROS |
| `/tf` | tf2_msgs/TFMessage | Gazebo → ROS |
| `/cmd_vel` | geometry_msgs/Twist | ROS → Gazebo |

坐标链为 `odom → base_link → wheeltec_reference/base_link/laser`。里程计原点是启动位置；房间坐标中的初始偏移不直接作为定位结果提供给后续 SLAM。

仿真使用本机通信和 ROS 域 77。Gazebo 采用 Ogre 渲染；本机单条垂直扫描线会输出异常最小量程，因此模型设置三条相邻垂直渲染线，ROS 桥接取正中间的水平线，仍输出二维 LaserScan。不要将其改回单垂直像素而不检查实际墙距。

## 重跑检查

在已加载 ROS 的仿真终端中：

```bash
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/check_room.py
python3 /mnt/d/虚拟c盘/WHEELTEC/setup/check-gui.py --room
```

第一项会让虚拟车低速前进、停止和转向，将里程计位移与雷达墙距变化核对后退出。第二项打开并截图两个图形窗口，再关闭本次进程。原始结果保存在 Linux 的实验目录与 simulation-checks；摘要见 [验证结果](../setup/verification/room/room-result.json)，截图位于同一目录。

下一阶段：接入 SLAM Toolbox，检查移动时地图是否稳定，保存第一张房间地图；之后加入自主探索。

接口依据：[Gazebo 差速驱动](https://gazebosim.org/docs/fortress/moving_robot/)、[传感器](https://gazebosim.org/docs/fortress/sensors/)、[ROS-Gazebo LaserScan 转换](https://github.com/gazebosim/ros_gz/blob/humble/ros_gz_bridge/src/convert/sensor_msgs.cpp)。
