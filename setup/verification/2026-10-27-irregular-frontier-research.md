# 不规则障碍边界下的前沿选点研究（2026-10-27）

本报告只做原始源码与论文核查，没有修改探索算法、运行仿真或连接实车。结论用于设计下一轮单变量 A/B；不代表复杂场景成功率已提高。资料核查日期为 2026-10-27，引用在线分支会变化，正式实现和实验应另记录本项目提交及配置哈希。

## 当前问题与建议

本地 `src/wheeltec_explore/wheeltec_explore/frontiers.py` 已保留真实栅格形状：前沿八连通聚类，候选目标来自已知自由、膨胀后安全且 BFS 可达的格子。当前每簇只选择一个接近全簇质心的目标；选点过程没有根据障碍遮挡计算该目标实际可见的前沿数量。现有 `visible()` 用于残余前沿多视角判断，没有用于这一选点过程。这是代码观察，不能据此认定已有失败均由它造成。

建议本轮先只改变“安全候选目标的选择方法”：在原地图、原前沿簇、原安全区、原完成判据下加入遮挡感知的候选可见性。PCA 拆簇留作独立第二轮；不同时改变地图分辨率、机器人半径、SLAM 参数或验收门限。

## 已核实的原始资料

### FUEL：空间分簇与可见性是两个不同步骤

[作者仓库](https://github.com/HKUST-Aerial-Robotics/FUEL)、[原始论文](https://arxiv.org/abs/2010.11561)、[论文全文 IV-B/IV-C](https://arxiv.org/html/2010.11561v2)。论文为面向三维无人机探索的 FUEL；arXiv 页面注明接受于 IEEE Robotics and Automation Letters。没有查询或采用期刊影响因子数值。

[frontier_finder.cpp](https://github.com/HKUST-Aerial-Robotics/FUEL/blob/main/fuel_planner/active_perception/src/frontier_finder.cpp) 中：

- `splitHorizontally()`：下采样簇中任一点到均值的 XY 距离超过 `cluster_size_xy_` 时触发拆分；用 XY 协方差最大特征值对应的主轴，把原始簇点按投影正负分为两组并递归。
- `sampleViewpoints()`：在簇周围采样，排除膨胀障碍和靠近未知的候选；`countVisibleCells()` 检查 FOV 与射线遮挡，射线遇膨胀障碍或未知即不计可见。
- `computeFrontierInfo()` 的 AABB 保存更新索引；不是用填满的矩形替代真实障碍轮廓。

论文文字将拆分触发描述为最大特征值阈值，当前源码实际使用上述距离阈值；二者不能混写。可借鉴“分簇和视点分离”的设计，不照搬飞行轨迹、三维通行、无人机安全间距及完成定义。论文的速度提升也不能作为本车性能证据。

### m-explore-ros2：适合作为二维 BFS 基线，未提供本轮所需的遮挡评分

[作者维护仓库](https://github.com/robo-friends/m-explore-ros2)、[frontier_search.cpp](https://github.com/robo-friends/m-explore-ros2/blob/main/explore/src/frontier_search.cpp)。`searchFrom()` 使用 Nav2 costmap 搜索；`buildNewFrontier()` 八邻域聚类、保存质心及距机器人最近的前沿点；`frontierCost()` 组合距离与簇大小。此文件中未发现按候选视点射线遮挡统计可见前沿的步骤。

`isNewFrontierCell()` 把邻接自由格的未知格定义为前沿；本项目则使用邻接未知的已知自由格。不能直接复制其前沿坐标作为本项目安全导航目标，也不能仅换成这一基线便宣称解决不规则边界。

### TARE：局部精细视点与全局粗粒度规划

[作者项目页](https://www.cmu-exploration.com/tare-planner)、[RSS 2021 原始论文](https://www.roboticsproceedings.org/rss17/p018.pdf)、[作者源码](https://github.com/caochao39/tare_planner)。其局部稠密、全局稀疏表示适合区分局部覆盖与全局巡回，不要求把障碍拟合成规则矩形。

[viewpoint_manager.cpp](https://github.com/caochao39/tare_planner/blob/melodic-noetic/src/tare_planner/src/viewpoint_manager/viewpoint_manager.cpp) 的 `CheckViewPointLineOfSight()`、`CheckViewPointConnectivity()` 分别处理视线与视点连通；[local_coverage_planner.cpp](https://github.com/caochao39/tare_planner/blob/melodic-noetic/src/tare_planner/src/local_coverage_planner/local_coverage_planner.cpp) 的 `EnqueueViewpointCandidates()` 使用新增覆盖点/前沿点计数，`SolveLocalCoverageProblem()` 维护局部覆盖选择。项目不只面向无人机，也考虑地面机器人，但源码是 ROS 1 Melodic/Noetic，不能直接作为 Humble 插件接入。

作者项目页列出 *Representation Granularity Enables Time-Efficient Autonomous Exploration in Large, Complex Worlds*（Science Robotics 8(80), 2023）。本次核实其作者项目页书目信息，出版方正文链接未成功读取；不把未读取正文的细节写成证据。作者展示的基准速度、平台、任务终点及覆盖定义不同，不能替代本项目独立验收。

### 二维相关原始论文

Deng 等，*Robotic Exploration of Unknown 2D Environment Using a Frontier-based Automatic-Differentiable Information Gain Measure*：[原始论文页面](https://arxiv.org/abs/2011.05323)、[作者论文全文](https://arxiv.org/html/2011.05323v1)。该文针对二维占据地图与范围传感器，把前沿信息收益用于视点/路径选择，并报告仿真及 TurtleBot3 实验。它支持优先研究“观测收益”的方向；本次来源仅核实为预印本，不声称其期刊档次或本项目可复现其结果。其连续可微收益及路径梯度优化比本轮单变量改动更大，暂不引入。

## 四条路线的取舍（本项目推论）

| 路线 | 可能收益 | 风险与本轮决定 |
| --- | --- | --- |
| 全局地图栅格更细 | 表达更多已被传感器分辨的细节 | 边长减半时同面积格数约四倍；不能凭空恢复激光未观测的薄框。影响 SLAM、代价图和探索，暂不改。 |
| 用小矩形拟合边界 | 可作索引、可视化或搜索分块 | 填充矩形可能堵死弧形凹口；不保守拟合可能漏掉细框。保留原始 occupied/unknown，不替换安全地图。 |
| PCA 空间拆簇 | 避免弯曲长簇共用一个质心和一个视点 | 不保证遮挡被消除；近圆对称主轴不稳定，投影结果可能不连通。适合独立后续 A/B，所有子簇和未观测证据都须保留。 |
| 遮挡感知视点 | 在既有安全候选中优先选择真正能看到前沿的位置 | 需要保守射线遍历和性能预算；与当前缺口直接对应，优先单变量验证。 |

这里“更细”优先指局部候选和观测关系，而非无测量依据地缩小占据地图像素或足迹。AABB 只用于筛选，不成为可通行性证据。

## 最小可证伪实验

假设 H：部分弧形、锯齿或薄框场景中，质心偏置选出被遮挡的接近点；若成立，应在相同静态地图上观察到原策略选点可见前沿数偏低，替代候选保持同样安全和可达但能看到更多前沿。

先添加纯 Python 用例，使原策略暴露问题，再引入一个命名选点策略开关做 A/B。LOS 应遍历线段接触的全部栅格，覆盖对角穿角情况，不能用稀疏取样跳过一格薄障碍。射线穿过 occupied 或 unknown 不计可见；候选仍必须使用原安全 BFS 集合。可见性是传感器观测约束，不能把导航膨胀区误当真实障碍轮廓，也不能绕开候选足迹约束。FOV、盲区和量程只使用有来源配置，实车参数未测时仍标 assumed。

| 用例 | 可以证伪或暴露的行为 |
| --- | --- |
| C/U 形弯曲前沿，簇均值落在遮挡后 | 存在安全可达替代视点；不能把均值方向当可见证据。 |
| 锯齿/L 形薄墙，两侧同簇 | 射线不得穿墙计收益；一侧观察不能直接覆盖另一侧。 |
| 斜置一格薄框、对角接触障碍 | LOS 不得跳格或穿角；改变遍历方向结果应一致。 |
| 某候选可见但在不连通自由区 | 必须因原 BFS 不可达而排除。 |
| 全部候选被遮挡 | 无目标仍保留未探索证据，不能据此报告 completed。 |
| 开阔直前沿及单候选 | 不增加无依据的拒绝；相同输入和 seed 选点确定。 |
| 大簇/多簇压力图 | 记录候选数、射线数、用时及内存，避免车端计算失控。 |

第一轮保持原聚类和簇间策略，单独验证候选可见性；不要同时接入 PCA、改残余前沿判据或修改 SLAM。排序、距离惩罚、确定性 tie-break 均需写清。若有限候选预算会漏掉有效视点，必须记录“预算不足/未搜索完”，不能伪称物理不可达。

纯 Python 通过后，在同一批布局、起点和每格至少五个 seed 上运行原策略/新策略，保留全部失败及原始批次。报告独立验收通过数/总数、每格 Wilson 区间，以及可见前沿数、零可见目标比例、目标重试次数和选点 p50/p95 耗时。地图覆盖率、墙面误差、返航与安全门限沿用现有评估器；真值只进入评估器。地图健康、激光断流或安全区无法连通须单独定位，不能归因到本假设或通过选点掩盖。

## 尚未验证

- 不规则场景优化后的多种子成功率、地图精度、返航与实际运行耗时。
- 实车雷达可见性、薄框反射、盲区、真实足迹、打滑及 RDK X5 负载。
- PCA 是否比仅增加可见性更有效；需要单独 A/B 后判断。
- Science Robotics 2023 正文细节；未读取，不作为具体算法实现依据。

本轮研究结论：成熟实现支持保留真实占据地图、把安全可达与传感器可见性分别检查。当前最小可检验改动是安全候选的遮挡感知选点；是否改善完整探索，必须由后续回归数据回答。
