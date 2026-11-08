# wheeltec_explore

从 SLAM Toolbox 的 `/map` 和 TF 选探索目标，交给 Nav2 `/navigate_to_pose` 行驶。原 CLI/仿真默认使用本项目的栅格前沿，网页任务配置使用厂家 RRT 候选并由本项目检查净空。模块不读取 Gazebo 场景或真实位置。

默认安全半径 0.35 米，覆盖参考小车足迹外接圆和一格地图误差。算法对障碍、未知区和地图外边界按足迹收缩空地，再在整车可落入的已知可通行区域内做四连通可达搜索；将已知区域与未知区域之间的边界聚类，从前沿向已知区域内退让，选择 0.6 米搜索范围内可达、整车落在已知空地内的接近点。目标按前沿长度和行驶距离评分。到达后的目标及实际观察位置进入访问记录，后续接近点与已访问位置至少相隔0.30米，避免在相邻点之间来回循环；接近点都已访问仍不足以认定完成：只有至少两个相距0.30米、地图版本不同且对整簇有已知空地视线的实际观察位置，才计为 multiview_observed；只被未知格阻挡的前沿不能据此算足迹不可进入。失败目标暂停 20 秒后再试，同一区域最多尝试 3 次；单目标 120 秒、整任务 900 秒，最多 60 个目标。

## 当前观察点允许85%局部观测后换点（2026-11-05已部署，完整任务未验收）

单目标120秒仍是导航硬上限；新增 `goal_no_progress_timeout=25.0`、`goal_progress_distance=0.1`：连续25秒有效位姿相对进展参考点未移动0.1m，就确认取消并按原规则冷却重选；正常绕障即使暂时远离目标也算移动进展，返航不使用局部提前换点。

`local_observation_threshold=0.85`、`local_observation_radius=1.0`、`local_observation_distance=0.6`、`local_observation_maps=2` 定义当前点的近似观测：机器人在目标0.6m以内，目标周围1m完整圆域已知格比例连续两次不同地图更新≥85%。占据格也是已观察到的结构，不代表可通行；地图外仍为未知。此比例只决定换点，不改SLAM栅格或全局完成标准。

`local_observation_events` 保存比例、半径、地图版本和结果。`locally_observed` 的导航成功字段为false，不把未达到的位置记成成功导航，也不据此生成多视角证明；仅当前实际位置在扫描新鲜时可留作观察记录。同一任务暂不重选该目标邻域，残余前沿保留；若只剩这些目标，保存/返航后以 `local_observation_residuals` 报告 `incomplete`。

默认0.35m仍供参考仿真调用。实车启动入口从共享校准和原碰撞区计算全朝向规划半径，不再用裸车体外接圆代替StopZone净空；本次保存配置为0.477624m。前沿探索与Nav2 costmap必须一致更新。实车另以 `footprint_exclusion_radius` 保留旧校准参考半径作残余分类依据，不把新增规划余量误当物理不可进入的证明；旧调用默认0仍采用原robot_radius。见[本地修复与证据](../../setup/verification/2026-11-05-debug-local-observation-and-input.md)。

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


2026-11-01 自主退出根因已停车复现：同步候选计算阻塞ROS消息处理4.64秒，触发scan_stale/tf_stale。已把原候选计算移到工作线程，主线程继续收消息和健康检查，1秒门限不变；52项探索回归通过。用户Space停车后单文件修复已部署，同一真实地图对照仍29个候选且健康通过，未发导航、未清图，完整自主待用户重试。见[故障复现与修复](../../setup/verification/2026-11-01-debug-planning-starvation.md)。


2026-11-01跳变度量修复：health_tick使用新鲜odom→base位置p，对相邻map→odom分别计算T_old(p)、T_new(p)，其距离作为车体定位校正量；不比较两个不同的车体位置，正常运动不计作跳变。0.5m位移与0.35rad角度门限保持，参考TF缺失/过期时拒绝继续。max_translation_jump_m现在表示车体参考点校正量，故障记录增加原始变换、参考位置/时间与原点平移分量。61项本地回归和车端静止验证通过且已部署；完整自主待用户验证，原失败TF对缺失的限制见[诊断](../../setup/verification/2026-11-01-debug-map-correction-reference.md)。


## 厂家 RRT 候选后端（实验性）

2026-11-08 停车部署后，网页自主任务配置选择厂家候选后端，任务自行管理厂家 `global_rrt`、`local_rrt`、`filter`，根据当前地图自动确定采样范围、根据现有小车配置取得安全几何；地图范围改变时重新初始化厂家候选节点。网页操作不增加输入项；原 CLI 和仿真默认仍使用栅格前沿。该网页改动已部署到车端；停驻检查和网页相机访问通过，但尚未启动实车探索或完成自主任务验证。见[停车部署记录](../../setup/verification/2026-11-08-vendor-web-deploy.md)。

以下独立实验入口同样只启动厂家 `global_rrt`、`local_rrt`、`filter` 和本项目任务，不启动厂家的 `assigner`、找箱行为树、SLAM、Nav2 或底盘；这些底座和最终安全链必须已经由现有环境唯一启动。

需要在同一 ROS 环境安装厂家 `wheeltec_robot_rrt`、`wheeltec_rrt_msg` 和本包。调用方必须提供 map 坐标系下轴对齐采样矩形 `xmin,ymin,xmax,ymax`，起点须在其中；厂家 local RRT 固定使用 `map` 和 `base_footprint`，因此新入口要求车体坐标系必须为 `base_footprint`，并显式给出里程计坐标系、规划半径、足迹排除半径、时间源和新任务地图输出前缀 `map_output`。输出前缀及地图、图优化文件、元数据、任务状态文件必须尚不存在，避免覆盖旧任务。规划半径须与实际 Nav2 costmap 和碰撞保护区配置一致，不能将仿真尺寸当实车校准。每次任务新启动整组候选节点；不要并行启动第二组或向其边界话题发点。

例如，**仅在已经运行的隔离仿真**中，按仿真地图实际边界调整数值，并为每次运行选择一个不存在的新输出路径后：

```bash
ros2 launch wheeltec_explore vendor_rrt.launch.py \
  bounds:='-5,-5,5,5' use_sim_time:=true base_frame:=base_footprint odom_frame:=odom \
  robot_radius:=0.35 footprint_exclusion_radius:=0.0 map_output:=/tmp/wheeltec-vendor-test/room
```

厂家候选消息不带时间戳；本项目以本机接收时间限制候选有效期，并根据当前地图重新判断前沿、未知区膨胀和可达净空。采样空窗并不表示完成：仅当独立全图分析连续确认无可选前沿，才进入原有存图、返航及完成条件判断。厂家点只参与选点，不接管 Nav2 动作或底盘速度输出。候选数据尚未做全图分析时，状态中的前沿簇与不可达簇计数为 `null`，不是零。

厂家源码把未知返回值 `-1` 存入 `char`，随后与 `255` 比较。隔离 x86 测试中默认 signed-char 没有发现前沿，使用 `-funsigned-char` 则能产生候选；车端现有二进制的构建方式和实际任务表现未核验。独立实验 launch 未随本次停车部署安装；已部署的网页任务路径也尚未完成实车探索验收。
