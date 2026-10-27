# T6：暂不启动SLAM参数A/B

T2历史bag确认两次大幅map→odom跳变，不能仅凭跳变推断假回环。T5完整75次均没有导航目标，四档噪声20次也没有建立正常行驶基线，尚不具备对回环参数做因果比较的前提。因此不改loop参数，不把没有实施写成调参成功。

已核实本机Humble默认配置与项目在loop_search_space_dimension=8.0、loop_search_maximum_distance=3.0、loop_match_minimum_response_fine=0.45三项相同。这只证明这些值沿用默认，不能证明不适合场景。后续须在真实雷达参数校准、启动观测受阻解决后，用相同布局/起点/seed复现跳变，结合图优化/回环日志与bag，再选择一个参数作可证伪A/B；不同时修改其他参数或门限。

Fortress ign-gazebo6 DiffDrive实现未发现插件级里程计随机噪声配置，本轮采用独立估计节点注入而非借用真值。已核对官方实现：https://raw.githubusercontent.com/gazebosim/gz-sim/ign-gazebo6/src/systems/diff_drive/DiffDrive.cc 。SLAM默认值以本机/opt/ros/humble/share/slam_toolbox/config/mapper_params_online_async.yaml为依据。

完整统计和保留故障见2026-10-27-regression-results.md。T6状态为前提未满足、未执行，不是通过。
