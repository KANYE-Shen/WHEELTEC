# 首轮仿真准备

目标：在 25 平方米房间里验证虚拟小车的雷达、里程计、坐标变换与速度控制，作为后续 SLAM 和 Nav2 的输入。

采用 ROS2 Humble、Gazebo Fortress、ros_gz_bridge。首轮使用差速参考车：轮半径 0.075 m、轮距 0.35 m、车体约 0.36×0.28 m；这些是仿真参数，后续按实车测量更新。房间内设三处静态障碍，场景不依赖在线模型下载。

数据链路：Gazebo → /clock、/scan、/odom、/tf → ROS；ROS /cmd_vel → Gazebo。激光在车体上方，雷达坐标通过固定 TF 与 base_link 连接。此阶段只打通仿真底座，建图与导航分别在下一阶段接入。

- [x] 将项目迁至 D 盘并校验全部文件。
- [x] 更新路径与图形检查脚本。
- [x] 添加 simulation/check_room.py：启动场景，检查雷达/时钟/TF，并对虚拟车执行短距离前进、停止与转向；核对里程计和雷达墙距变化。
- [x] 添加 simulation/models/wheeltec_reference/model.sdf 与 model.config。
- [x] 添加 simulation/worlds/room_25m2.sdf、config/bridge.yaml 和 config/room.rviz。
- [x] 添加 simulation/launch/room.launch.py、run_room.py、Start-Room.ps1 和根目录打开房间仿真.cmd。
- [x] 在 WSL 中运行检查：python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/check_room.py（先加载 /opt/ros/humble/setup.bash）。
- [x] 启动图形场景，查看并保存截图；关闭本次检查进程。
- [x] 更新 README、AGENTS.md 和安装状态，记录实验路径及下一步。

验收：雷达 720 束且能测到房间墙面；仿真时钟递增；/odom 与 /tf 坐标一致；前进时里程计位移和墙面距离变化相符；停止后速度收敛；转向时朝向改变。

依据：[Gazebo 移动车辆](https://gazebosim.org/docs/fortress/moving_robot/)、[传感器](https://gazebosim.org/docs/fortress/sensors/)、[Fortress DiffDrive 参数](https://gazebosim.org/api/gazebo/6/classignition_1_1gazebo_1_1systems_1_1DiffDrive.html)。

最终检查摘要与截图见 `../setup/verification/room/`；原始实验目录通过 `../data/README.md` 查阅。下一阶段：接入 SLAM Toolbox，验证地图生成及保存。
