# wheeltec_explore

从 SLAM Toolbox 的 `/map` 和 TF `map → base_link` 选探索目标，交给 Nav2 `/navigate_to_pose` 行驶。模块不读取 Gazebo 场景或真实位置。源码是本项目独立实现，没有复制 explore_lite 的代码。

默认安全半径 0.35 米，覆盖参考小车足迹外接圆和一格地图误差。算法对障碍、未知区和地图外边界按足迹收缩空地，再在整车可落入的已知可通行区域内做四连通可达搜索；将已知区域与未知区域之间的边界聚类，从前沿向已知区域内退让，选择 0.6 米搜索范围内可达、整车落在已知空地内的接近点。目标按前沿长度和行驶距离评分。到达后的目标及实际观察位置进入访问记录，后续接近点与已访问位置至少相隔0.30米，避免在相邻点之间来回循环；接近点都已访问仍不足以认定完成：只有至少两个相距0.30米、地图版本不同且对整簇有已知空地视线的实际观察位置，才计为 multiview_observed；只被未知格阻挡的前沿不能据此算足迹不可进入。失败目标暂停 20 秒后再试，同一区域最多尝试 3 次；单目标 120 秒、整任务 900 秒，最多 60 个目标。

## 使用

先启动建图与 Nav2，再执行：

```bash
source /opt/ros/humble/setup.bash
cd /home/wheeltec/wheeltec_sim_ws
colcon build --symlink-install --base-paths /mnt/d/虚拟c盘/WHEELTEC/src --packages-select wheeltec_explore
source install/setup.bash
ros2 run wheeltec_explore explore --ros-args -p use_sim_time:=true
```

需要 `/map_saver/save_map`（已激活的 Nav2 map_saver）、`/slam_toolbox/serialize_map`、`/navigate_to_pose`。参数 `map_output` 指定不带扩展名的地图路径；默认保存在 `~/wheeltec_sim_ws/data/maps/<时间>_explore/room`。

## 任务结果

`/exploration/status` 发布 JSON，当前状态包括 `starting`、`exploring`、`saving`、`returning`、`completed`、`completed_with_residual_frontiers`、`incomplete`、`map_unstable`、`failed`。同一内容同步写入 `<map_output>.exploration.json`。

连续三次新地图都没有可选目标后，保存 `.yaml`、`.pgm`、`.posegraph`、`.data`，返回起点，再判断结果。只有已观察空地至少 8 平方米、没有剩余不可达前沿、没有因超时或重试耗尽而中断、保存和返回都成功，才报告 `completed`。完成表示按当前分辨率与前沿阈值完成了可达区域探索；小于 `min_frontier_size`（默认 0.25 米）的碎片另外计数。

地图旁的 `.metadata.json` 保存参考方向 `reference_yaw_rad`、起点和保存时间，同时原子更新 `~/wheeltec_sim_ws/data/maps/latest.json`，方便重定位入口找到最新地图。参考方向是 map 坐标系下人为定义的方向，默认 0 弧度。

当前地图改变后仍存在的孤立自由区会记录为不可达前沿。临时无路会先交给 Nav2 恢复，再按探索重试规则处理，不删除障碍或改写保存地图。停止探索程序会取消其当前导航任务。

## 检查

```bash
python3 -m unittest discover -s /mnt/d/虚拟c盘/WHEELTEC/src/wheeltec_explore/test -v
```

纯算法测试覆盖已知空地目标、障碍间隙、不可达前沿、完整封闭房间、地图旋转原点、失败冷却及完成判据。仿真整体结果由根目录的阶段记录提供。

接口来源：[Nav2 Humble Map Server](https://api.nav2.org/nav2-humble/html/md_nav2_map_server_README.html)、[SLAM Toolbox](https://github.com/SteveMacenski/slam_toolbox)。候选 [m-explore-ros2](https://github.com/robo-friends/m-explore-ros2) 可作为后续对比。
验证运行可设置 `update_latest:=false`，只在指定 `map_output` 保存地图及元数据，不更新用户 `latest.json`；默认仍为 `true`。Humble trinary PGM 保存统一采用空地阈值 0.19、占据阈值 0.65，使灰度 205 的未知格在重新加载后保持未知。

前沿格采用八邻域聚类，使倾斜墙边的前沿不会碎成短簇；车体安全膨胀与可达路径仍按四邻域搜索，禁止从障碍角斜穿。该区别由45度边界和障碍角回归测试覆盖。

2026-10-27：状态 JSON 增加 residual_counts 与 residual_frontiers。分类为 reachable_unexplored、footprint_excluded、multiview_observed；footprint_excluded 要求已测障碍阻挡附近全部可能中心，未知格本身不构成证明。后两类可产生 completed_with_residual_frontiers，保存、返回、最小面积和独立几何评分仍需分别通过。rc=2 且有终态、无强杀和残留进程时属于任务未通过，不再附加异常退出。新增0.6/0.8米凹袋与静态阴影回归；本轮 baseline0 的单次名义 A/B 两边均未通过，不是多种子准入数据。


## 不规则边界视点试验（默认关闭的候选策略）

保留原 centroid 默认。参数 `frontier_viewpoint_strategy:=visibility` 开启遮挡感知视点：从原安全可达候选中选取48个确定性候选，最多96个前沿格样本，用包含角点接触的保守射线检测已知自由空间，再按可见前沿与路径距离选点，朝向一个实际可见格。`viewpoint_candidate_budget` 和 `viewpoint_frontier_budget` 可配置，属于工程预算。八连通前沿簇保持不变，不把不规则物体拟合成填满的矩形，不改变0.35m安全半径、未知格膨胀或完成门限。

在已启动的隔离仿真中使用 `ros2 run wheeltec_explore explore --ros-args -p use_sim_time:=true -p frontier_viewpoint_strategy:=visibility`；不要与已有探索器并行运行。自动验证入口为 `python3 simulation/check_exploration.py --scenario irregular_frame --viewpoint-strategy visibility --realism on --record --output ~/wheeltec_sim_ws/data/runs/NEW-visibility`（从仓库目录执行，必须新目录）。这不是实车运动授权。

状态 JSON 的 `viewpoint_diagnostics` 记录候选总数/评估数、前沿样本数、预算是否用尽及可见样本数；采样没有可见目标时保持 reachable_unexplored，不作为 footprint_excluded 或 completed 的证明。LOS仅表示当前地图几何无遮挡，不保证真实雷达FOV、量程或新信息量。完整数据及限制见[不规则前沿报告](../../setup/verification/2026-10-27-irregular-frontier-results.md)。


## 主动观测与实车阶段

`active_scan_angle_deg` 默认0，`initial_rotation_assumed_safe` 默认false。主动观测仅用于已隔离的仿真：须同时启用非零 `active_scan_angle_deg`（本次360）和起点例外参数；启用起点例外时，首次导航前一次完整旋转记录为 `assumed_start`、`clearance_proven=false`，不修改未知格；途中旋转仍检查完整扫掠净空，保留健康、取消和超时约束。新单种子演示有6个成功目标但严格0/1，见[证据](../../setup/verification/2026-10-29-startup-assumption/README.md)。没有新的多种子A/B结论。

实车只按[三阶段清单](../../robot/准入关卡.md)执行；阶段三才使用自主探索，仿真起点例外不能用于实车。上面的 `use_sim_time:=true` 命令是仿真命令，不能复制为实车启动方式。实车map→odom只能由当前SLAM或AMCL之一发布。
