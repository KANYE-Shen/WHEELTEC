# wheeltec_explore

SLAM Toolbox 发布地图，厂家 RRT 提供探索候选，Nav2 执行导航。本包负责检查候选、管理目标及取消、判断探索结果、存图和返航。实车网页、普通 CLI 和自主仿真使用同一条候选链。

## 启动探索

常用入口由探索器托管厂家 `global_rrt`、`local_rrt` 和 `filter`。它根据 SLAM 地图确定采样矩形，地图原点或范围变动时重新初始化三者。启动前需要已有建图、Nav2、地图保存服务、有效的 `map → odom → base_footprint` TF 和新鲜雷达。实车从网页启动，按实车准入清单验收。[实车准入清单](../../robot/准入关卡.md)

隔离仿真中，先启动建图和 Nav2，再在同一 ROS domain 中运行探索器。

```bash
source /opt/ros/humble/setup.bash
source "$HOME/.local/share/wheeltec-vendor-rrt/install/setup.bash"
source "$HOME/.local/share/wheeltec-refactor-sim/install/local_setup.bash"
ros2 run wheeltec_explore explore --ros-args -p use_sim_time:=true
```

默认按启动时间在 `~/wheeltec_sim_ws/data/maps/<时间>_explore/room` 创建地图。如果同名输出已存在，探索器会在启动前拒绝覆盖。可用 `-p map_output:=/tmp/新任务/room` 另选路径。

厂家 ROS 包名为 `wheeltec_robot_rrt` 和 `wheeltec_rrt_msg`。本机以已审计的厂家包副本构建独立 overlay。若需从合法取得的包重建，厂家 RRT 包清单需声明已有的 `wheeltec_rrt_msg` 构建依赖。厂家 CMake 的 `find_package(filters REQUIRED)` 未用于任何目标，若环境缺该包，可在本地构建副本省略该行。x86 构建用 `-DCMAKE_CXX_FLAGS=-funsigned-char` 保持厂家代码将未知格字节与 `255` 比较的语义。厂家源码由相应安装环境提供。

独立诊断时可用 `vendor_rrt.launch.py` 显式指定轴对齐采样矩形。起点应在矩形内，规划半径应与实际 Nav2 和碰撞保护区一致。此入口关闭 `update_latest`，需要未被占用的地图输出前缀。

```bash
ros2 launch wheeltec_explore vendor_rrt.launch.py \
  bounds:='-5,-5,5,5' use_sim_time:=true base_frame:=base_footprint odom_frame:=odom \
  robot_radius:=0.35 footprint_exclusion_radius:=0.0 map_output:=/tmp/wheeltec-vendor-test/room
```

每个探索任务拥有唯一的候选节点组，导航和底盘仍由现有运行栈管理。单独的厂家完整演示包含 assigner 和找箱流程，和上述入口同时启动会产生控制和话题冲突。

## 从候选到导航

厂家 `filter` 输出 `wheeltec_rrt_msg/msg/PointArray`，本包按接收时间限制候选有效期。按厂家批次顺序处理，通过当前地图检查已知空地、整车净空和四连通可达性，把候选吸附到安全接近点并按栅格去重。未知区和地图之外均计入净空约束。实车规划半径取共享校准及碰撞保护区，参考仿真的默认半径为 0.35 m。足迹排除可使用单独的校准半径，避免把额外规划余量当成物理不可进入的证据。

失败点冷却 20 s，同一区域最多尝试 3 次，单目标最多 120 s。连续 25 s 有效位姿移动不足 0.1 m 时确认取消后换点，正常绕障的实际位移也计入进展。机器人在目标 0.6 m 内，且目标周围 1 m 圆域已知格比例连续两次不同地图更新达到 85%，可以确认取消后换点，记录 `locally_observed` 和实际观察位置。这个局部规则只控制换点，区域残余由全图另判。候选和全图计算各自使用地图快照在工作线程运行，ROS 主线程继续处理雷达、TF 和任务时限。

## 完成和保存

候选为空、过期或暂时不能导航时，独立普查全图残余。如果仍有可接近前沿，等待新厂家候选。已用尽的目标或只靠局部观察跳过的目标会使任务不完整。持续 三次不同地图更新均无剩余可接近前沿，才按完成条件进行保存和返航。报告完成需要原始已知空地面积至少 8 m²、零未解决的不可达前沿、保存成功、返航成功以及任务未因超限中止。

独立普查用八连通保留倾斜的前沿边界，并以四连通检查行驶。小于 `min_frontier_size` 的碎片单独计数，默认 0.25 m。已测障碍证明足迹无法进入，或至少两次不同地图更新且相距 0.30 m 的观察位置都能看到整簇，可分别归类为 `footprint_excluded` 或 `multiview_observed`。这些残余单列，其他条件满足时报告 `completed_with_residual_frontiers`。

`/exploration/status` 和 `<map_output>.exploration.json` 记录过程、导航结果与终态。当前地图未经全图普查时，前沿和不可达计数为 `null`。任务地图包含占据图 `.yaml`、`.pgm` 与 SLAM Toolbox 位姿图 `.posegraph`、`.data`。元数据记载起点和 `reference_yaw_rad`。独立验证用新 `map_output` 和 `update_latest:=false` 保留用户的最近地图。占据图使用 Humble trinary 的 0.19 / 0.65 阈值，保存并重载未知栅格。

`active_scan_angle_deg` 默认 0，`initial_rotation_assumed_safe` 默认关闭。起点旋转例外只用于隔离仿真，途中旋转仍要求扫掠净空通过。

## 回归检查

在仓库根目录运行以下命令。端到端房间覆盖仍需在仿真或经批准的实车试验中独立验收。

```bash
PYTHONPATH=src/wheeltec_explore:src/wheeltec_explore/test \
  python3 -m unittest discover -s src/wheeltec_explore/test -v
```

历史实车记录保留原条件。2026-11-08 记录验证的是网页停车准备和相机访问。此处的统一探索入口需单独部署和验收。[厂家网页停车部署记录](../../setup/verification/2026-11-08-vendor-web-deploy.md)
