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

当前地图与录包目录已建立。首轮房间接口实验已验证前进、停止、转向及墙距变化；结果摘要位于 `../setup/verification/room/room-result.json`。图形结果位于同目录的 `gui-result.json` 和两张窗口截图；原始日志在 Linux `/home/wheeltec/simulation-checks/`。建图实验将在下一阶段记录。
