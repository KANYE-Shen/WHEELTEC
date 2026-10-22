# 算法源码

后续 ROS 功能包和仿真、实车共用逻辑统一放在这里。目前尚无功能包。

Windows 项目内的源码是维护源，WSL 通过 `/mnt/d/虚拟c盘/WHEELTEC/src` 读取。编译产物写入 `/home/wheeltec/wheeltec_sim_ws` 的 `build/`、`install/`、`log/`，不在这里生成。

使用 Nav2、SLAM Toolbox 等已有项目时优先通过依赖和配置接入；需引入源码时记录仓库、版本、许可证与改动。
