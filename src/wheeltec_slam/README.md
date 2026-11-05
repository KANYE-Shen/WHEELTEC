# 实车 SLAM 的静止关键帧门限

复用已安装的 SLAM Toolbox 2.6.10 异步节点。只重载虚函数 addScan，在成功加入一帧后记录对应里程计位姿；移动至少 3 cm 或转动至少 0.1 rad 才加入下一帧。静止重复观测不再持续扩大图，纯转动仍可加入观测。不是新的探索算法，也没有改变雷达测量。

Humble 的外层 shouldProcessScan 只检查平移，因此 minimum_travel_distance 仍须为 0；stationary_keyframe_distance 控制这里的平移门限，minimum_travel_heading 控制角度门限。继承的回调仍接收每帧真实扫描并保留源 header，过滤、暂停、匹配、优化、TF 发布和序列化服务仍由原 SDK 实现。没有重打 TF 时间或放宽网页定位健康门限。反序列化地图成功后重置门限记忆。

在 ROS2 Humble 工作区构建并 source 对应 install/setup.bash：

```bash
colcon build --packages-select wheeltec_slam --cmake-args -DCMAKE_BUILD_TYPE=Release
colcon test --packages-select wheeltec_slam
```

实车 robot.launch.py 使用 motion_gated_slam；仿真入口不改。当前车端部署是本次手动诊断目录中的独立 CMake install，不覆盖 /opt/ros/humble，运行身份记在 owned-processes.json 的 slam 项。未安装开机服务。

实车配置 scan_queue_size=3。队列 1 在 10 Hz 雷达与 TF 存在相位偏移时会提前淘汰仍待变换的扫描，产生间歇性饥饿；队列 3 有界保留短暂等待。隔离真实 SDK 对照见 outputs/20261031-autonomous-trial/slam-filter-phase/result.json。不能通过无限队列、旧缓存或更新源时间隐藏处理积压。

回归：C++ 门限测试；隔离 Domain 197 SDK 对照证明静止 19 帧对 1 帧、原地转向和平移仍接收；相位对照证明队列 1 为零交付、队列 3 正常且 TF 源时间新鲜。真实运动和长期建图质量未验收。
