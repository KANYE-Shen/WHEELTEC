# 陌生房间验证

本轮沿用前沿探索、SLAM Toolbox、Nav2 运动参数、720 束 Ogre 激光和 GUI 同步插件。场景几何只供 Gazebo 与独立评估器使用。`process.json` 保存算法估计量，仿真真值单独写入 `truth.json`。

## 运行入口

WSL 加载 ROS 与工作区后：

```bash
source /opt/ros/humble/setup.bash
source ~/wheeltec_sim_ws/install/setup.bash
cd /mnt/d/虚拟c盘/WHEELTEC
python3 -m unittest discover -s simulation -p test_validation.py -v
python3 simulation/check_exploration.py --scenario l_shape --spawn 0 --record
```

`--scenario` 支持 `l_shape`、`clutter`、`bent_passage`、`recess`，另有原布局 `baseline`。每个场景定义三个具名安全起点，`--spawn` 从 0 编号；JSON 单位为米，房间多边形为逆时针内墙面，家具为轴对齐矩形。起点距实体至少 0.35 m，且处于同一个四连通可达分量。房间面积为 25–26 平方米。

`--output` 指定新的结果目录，已有目录拒绝覆盖；默认写入 `~/wheeltec_sim_ws/data/runs/<时间>_<场景>_spawnN`。`--task-timeout` 默认 300 秒，`--timeout` 默认 460 秒，后者须大于前者；拒绝非有限超时。`--record` 开启 rosbag，`--no-record` 只保留 JSON。新场景默认域 83，未指定场景的旧检查为域 80，可用 `--domain` 指定 0–232；普通入口仍为域 77。

手工启动新房间：

```bash
python3 simulation/run_room.py scenario:=recess spawn:=1 explore:=true
python3 simulation/run_room.py scenario:=l_shape spawn:=0 explore:=true map_output:=/home/wheeltec/wheeltec_sim_ws/data/maps/my_run/room
```

场景生成到 Linux 数据目录 `~/wheeltec_sim_ws/data/worlds/room-<PID>.sdf`，通过 launch 的 `world` 参数传入；`scenario`/`spawn` 由启动器消化，不是算法参数。默认仍使用原 `worlds/room_25m2.sdf`。`map_output` 不带扩展名。普通探索继续更新 `data/maps/latest.json`；检查明确使用 `update_latest:=false`，并比较运行前后的选择文件 SHA-256。

## 独立评分

`map_metrics.py` 不依赖 ROS。初次可用的 `map→base_link` 位姿与仿真起点确定唯一的世界到地图刚体变换，不按最终地图重新拟合、不缩放。栅格原点平移和 yaw 均参与采样。

正确空地覆盖率的分母：在真实实体几何中，以 0.05 m 栅格筛选距实体至少 0.35 m 的机器人中心，再从起点四连通洪泛。分子为其中在估计图中正确标为空地的数量。未知和地图范围外均不算空地。另报全部物理空地面积及未知部分、其他物理空地、断开的安全区域，以及家具/实体内错误空地。

轮廓分母由真实几何确定：真实表面每 0.05 m 采样，从可达安全中心中每第三格取视点，在 10 m 范围内做无遮挡视线检查。未扫到的墙面不会从分母消失。估计轮廓只取占据格与已知空地相邻处，排除障碍内部；真实不可观测面的近邻估计点不参与评分。分别报告真实到估计、估计到真实的距离 95 分位；对称值定义为两者最大值，避免较大的准确轮廓点集稀释另一方向的错误。同时报告 10 cm 容差内真实可观测墙面覆盖率及缺失比例。早期 first/fixed 记录使用合并点集的历史公式，不与新公式直接比较；重算摘要单独保留，不修改原始证据。没有估计轮廓时误差为 `null`、缺失比例为 1；没有可观测真值轮廓时相关值为 `null`。

轨迹安全使用独立真值，读取参考 SDF 中实际机身和双轮二维碰撞投影，按 yaw 旋转；脚轮投影包含在机身内。轨迹插值限制最大平移/车体外缘转动约 0.02 m，检查与静态实体相交及最小净距。名称为 `geometric_projection_only`，没有物理接触传感器，不能称作物理接触次数。0.35 m 半径只用于安全中心分母，不代替真实车体。

`result.json` 分别保留最终 OccupancyGrid 与实际保存后按 YAML 重载的评分。`acceptance` 逐项记录内部完成、保存、返回、实际返航误差、几何重叠、覆盖率和墙面指标。新场景目标为正确空地覆盖率 ≥95%、墙面距离 95 分位 ≤10 cm、可观测墙面覆盖率 ≥95%、无几何重叠及返航误差 <20 cm；未达标保留全部证据，不修改算法的最小面积 8 平方米或降低门槛。

## 过程文件

结果包括 `result.json`、`process.json`、`truth.json`、地图与任务状态、`launch.log`、`explore.log`；录包时还包括 `bag/`、`bag.log`、QoS 配置。结果记录场景、起点、源码/配置 SHA-256、Git 版本、失败列表、返回误差、各自有进程退出码与强杀标志。

`process.json` v1：

```text
version: 1
coordinate_frame: "map"
scenario: {id,name,spawn_index,spawn_name}
frames: [{t,wall_t,pose:[x,y,yaw]|null,scan:[[x,y],...]|null,
          scan_age_s,plan:[[x,y],...]|null,plan_age_wall_s,status,map,issues}]
maps: [{width,height,resolution,origin:[x,y,yaw],data:[-1..100]}]
statuses: [{t,wall_t,...status}]
path: [[x,y],...]
terminal: {...status}|null
capture: {initial_pose,initial_pose_t,issue_counts,sample_period_sim_s}
```

`t` 为仿真秒数，`wall_t` 为采集器启动后的实际秒数。每 0.5 仿真秒记录一帧；`map` 为去重后 `maps` 的索引。扫描使用消息时间戳对应的 TF 转到 map；缺失、过期或缺少 TF 时写 `null` 与 `issues`，不将旧扫描冒充当前观测。计划保留最近发布值和实际年龄。`path` 为已走路径。

可复用接口是 `ProcessCapture(node, tf_buffer, output_json, metadata=None)`；构造时创建订阅和定时器，独立 STEADY_TIME 定时器每五个实际秒原子更新 JSON，Gazebo 暂停或 `/clock` 停止时仍落盘；采样仍按仿真时间暂停。查看器应将停止更新的最后帧标作过期。退出调用 `close(terminal)` 并销毁两个定时器。该模块不读取场景几何或真值。

录包话题为 `/scan /odom /tf /tf_static /map /exploration/status /clock /plan`，使用仿真时钟；地图、静态 TF 与状态设 transient-local。检查先停止自有 recorder，再销毁发布进程；随后运行 `ros2 bag info` 并核查必需话题消息数量。

## 未知格保存回归

所有保存入口的 `free_thresh` 统一为 0.19，占据阈值仍为 0.65。Humble trinary PGM 将未知写成灰度 205；旧 0.25 设置在 YAML 重载时因 `1-205/255≈0.196<0.25` 变成空地。0.19 能保留未知，并正确重载 0/254 的占据与空地。评估器严格按 YAML 加载，没有对 205 额外特判；不追改旧用户地图。

```bash
python3 simulation/test_map_roundtrip_ros.py
```

该回归在域 84 发布 `[-1,0,100]` 三格图，经真实 Nav2 saver 保存，再由真实 map_server 加载。0.25 时实测得到 `[0,0,100]`，0.19 修复后实测保持 `[-1,0,100]`；证据保留在 Linux `data/runs/*_map_roundtrip`。源码依据：[Nav2 Humble map_io.cpp](https://github.com/ros-navigation/navigation2/blob/humble/nav2_map_server/src/map_io.cpp)。

## 真值和位置时间有效性

评估真值读取Gazebo原生Pose_V顶层header时间戳；旧ROS真值桥接中每条TransformStamped时间为零，不能用于连续性验收。独立读取器归属本次Ignition partition，采集、错误与退出状态单独记录。读取与源时间解析在单独的Python进程执行，逐行写入 `truth-samples.jsonl`；主进程只读取完整行，避免过程JSON序列化占用Python解释器时阻塞测量采集。`truth-samples.jsonl` 是保留后的测量样本，不是完整原生Pose_V转储。源采样按0.02秒最小间隔保留；实际Gazebo步频下通常约30Hz，不将它写成实测50Hz。任务开始到评分决定之间要求至少三个递增测量，仿真间隔≤0.2秒、实际到达间隔≤0.5秒；终点年龄分别≤0.2和0.5秒，未来容差0.1秒。终态时先暂停大JSON周期写入，若唯一问题是ROS时钟回调落后导致测量看起来在未来，最多用2秒处理回调，要求再收到三个新的源时间戳且时间一致；其他数据质量错误直接保留。随后固定评分时刻，再写文件和退出进程。这个同步不会清除任务期间已经出现的断流或超限间隙。真值不合格时返回误差与轨迹安全置为null，相关验收条件为false；读取器解析错误和丢样同样使整体验收失败。

过程记录使用估计TF，并保存 `pose_stamp_s`、`pose_age_s`、`pose_transform_wall_age_s`。仿真年龄>1秒、未来超过0.1秒，或相同TF时间戳超过2秒实际时间未前进，写入 `pose:null` 与 `stale_pose_transform`，不继续追加轨迹。激光按自身消息时间查询变换，缺失时同样显式留空。

## 斜向前沿回归

L形起点1的首轮地图曾有191个前沿格，按四邻域聚类被拆成113个短簇，全部低于0.25米过滤长度，导致漏扫却提前完成。修复仅把前沿聚类改为八邻域，使斜向可见边界连通；安全膨胀、未知格限制、可达路径四邻域搜索和所有门槛保持原值。新增45度边界测试先复现无目标，再验证恢复目标；穿过障碍角的路径仍不可达。

完整批次与修复前失败均保存在Linux数据目录，索引见 [验证记录](../setup/verification/unknown_rooms/README.md)。

## 普通入口的串行回归

`check_normal_session.py` 从普通 `run_room.py` 入口启动L形起点1，等待探索终态和连续停车，再调用真实保存服务；结束录制并导出回放后，仅凭latest启动定位，不另传布局或起点。它检查场景身份、生成世界哈希、地图文件、AMCL活动状态与估计位姿。完整数据保存到新建的 `data/runs` 子目录，最后按原始字节恢复最近地图选择。它验证入口衔接，不计算独立地图质量。

所有房间仿真退出后运行：

```bash
source /opt/ros/humble/setup.bash
source ~/wheeltec_sim_ws/install/setup.bash
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/check_normal_session.py --run
```

该检查固定使用域82，输出目录拒绝覆盖。可用 `--expected-latest-sha` 指定本次预期的原选择SHA256；未指定时仍备份并恢复启动前的实际选择。实际记录索引见 [验证记录](../setup/verification/unknown_rooms/README.md)。
