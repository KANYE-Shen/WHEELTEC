# 算法源码

`wheeltec_explore/` 是前沿探索 ROS 功能包：读取占据地图和估计位姿，向 Nav2 下目标，处理有限重试、保存地图与返回起点。运行与测试见 [包说明](wheeltec_explore/README.md)。

SLAM Toolbox、Nav2 和 AMCL 复用已安装的 Humble 软件包；本项目配置在 `../simulation/config/`。仿真与实车共用的算法源码统一维护在这里，仿真世界与图形工具留在 simulation。

WSL 构建读取 `/mnt/d/虚拟c盘/WHEELTEC/src`，产物写入 `/home/wheeltec/wheeltec_sim_ws` 的 build、install 和 log；不要另存一套源码。
