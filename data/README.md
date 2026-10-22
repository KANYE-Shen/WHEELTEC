# 地图与实验数据

这里维护数据索引和实验说明。大文件写入 WSL 的 Linux 文件系统，实际占用 D 盘。

| 数据 | Linux 路径 |
| --- | --- |
| 地图、地图参数和参考方向 | `/home/wheeltec/wheeltec_sim_ws/data/maps` |
| ROS 录包 | `/home/wheeltec/wheeltec_sim_ws/data/bags` |
| 各次实验的配置、指标、截图和日志 | `/home/wheeltec/wheeltec_sim_ws/data/runs` |

Windows 资源管理器入口：`\\wsl.localhost\WHEELTEC-Ubuntu-22.04\home\wheeltec\wheeltec_sim_ws\data`。

每次实验使用 `YYYYMMDD-HHMMSS_场景名` 目录名，记录场景、软件版本或提交、使用参数、起点与目标、随机种子（使用时）、数据位置、完成状态及误差/耗时等指标。地图同时记录参考方向定义和坐标约定。

可复现实验的小样例可纳入项目。生成的录包、编译缓存和大体积日志保留在上述 Linux 目录。

## 当前实验索引

| 实验 | 项目中的结果摘要 | 完整数据 |
| --- | --- | --- |
| 房间传感器、前进、停止、转向 | [room-result.json](../setup/verification/room/room-result.json) | 结果中的 run_dir |
| 建图四目标、保存、重启 AMCL 后一目标 | [导航结果](../setup/verification/navigation/result.json) | 结果中的 run_dir |
| 自主探索、保存地图和位姿图、返回起点 | [探索结果](../setup/verification/exploration/result.json) | 结果中的 run_dir |
| 新增箱子绕行、封路停车、取消、固定地图不变 | [障碍结果](../setup/verification/obstacles/result.json) | 结果中的 run_dir |

手动保存按 `maps/年月日-时分秒-微秒/room` 建目录；自主探索用 `maps/年月日-时分秒_explore/room`。每张地图包含 `.yaml` 地图参数、`.pgm` 栅格图像、`.posegraph`/`.data` 位姿图，以及 `.metadata.json` 参考方向和来源。`maps/latest.json` 指向最近保存地图，启动已存地图导航时读取其中的 `map_yaml`。

参考方向 `reference_yaw_rad` 是相对 map +X 的逆时针弧度，默认0；显示车头相对参考方向时应计算两者角度差并归一到 [-π,π]。它随地图保存，不等同地理正北。

功能检查用 `runs/` 下独立目录保存地图和日志。自主探索检查会将测试保存地图设为最近地图，可直接通过已存地图入口体验。图形截图在 `../setup/verification/room/`；早期环境检查日志在 Linux `/home/wheeltec/simulation-checks/`。当前没有录制 rosbag。

[小地图样例](samples/room-25m2/map.yaml) 来自20261022-203127自主探索实验；PGM和元数据一同保留。使用时将 map.yaml 路径传给定位模式，位姿图仍在原始实验目录。

![自主探索实际生成的地图](../setup/verification/exploration/map-preview.png)

橙色数字是依次下发的探索目标，蓝星是起点；图中没有绘制实际行驶轨迹。灰色为尚未观测区域，包括障碍物内部和少量边缘碎片。
