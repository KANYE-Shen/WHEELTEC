# 地图健康与停更原因审计

T2纯状态机8项红绿回归通过；simulation/test_health_ros.py用真实ROS发布器和TF注入2.2m跳变，探索器require_health拒绝继续且故障保持。生产代码只读估计接口，不读场景或真值。活跃任务出现异常时取消目标并报告map_unstable；仅在所有输入健康时允许完成。

## 复现命令

```bash
source /opt/ros/humble/setup.bash
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/check_health_bags.py --output ~/wheeltec_sim_ws/data/runs/<新的health目录>
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/test_health_ros.py
python3 -m unittest discover -s /mnt/d/虚拟c盘/WHEELTEC/src/wheeltec_explore/test -v
```

所有13项按matrix.json实际引用路径审计，无抽样、无替换。每项bag metadata SHA256、话题数量与健康参数在2026-10-27-health-bags.json中；完整结果在Linux data/runs/20261027-health-bag-suite。命令包装中的shell变量转发曾生成错误bag路径，原始health-.log保留；改为Python遍历矩阵后全部13项成功读取，这不是算法失败重跑。

## 分层证据与可证伪假设

- 传感器：每项回放记录scan消息数及源时间戳时效；不是只检查话题存在。
- TF：弯通道/0最大单步平移2.504m，首次50.630s；凹角/2为2.996m，首次63.328s。均由估计map→odom得出，不使用评估真值。
- 里程计：本项未调整；跳变是否由假回环、匹配错误或其他SLAM内部事件导致，尚未证实。
- SLAM：凹角/0、/1的最大地图更新间隙仅1.118/1.465个ROS秒；历史bag没有记录进程/节点图存活事件，不能证明节点是否曾退出。新在线监测补充节点图存活。
- 定位：全部mapping，AMCL不适用。
- Nav2：本项不改规划器和控制器；新的健康异常先取消自己的目标。
- 探索器：源码wait(check_task=True)可在300秒总预算到期时立即返回False，调用处却写map_update_timeout。两条旧日志都恰在300秒进入saving，支持“任务预算误标为地图超时”假设；T3增加区分回归后修复，不据此改SLAM。
- 评估器：固定初始对齐和几何评分不变；弯通道/1地图误差大但单步跳变只有0.141m，当前跳变监测不能发现缓慢累计漂移。此项仍未解决，不能宣称所有地图不一致都可检出。

## 参数来源与限制

健康诊断阈值0.5m、0.35rad、map15s、scan/TF1s是待实测验证的工程假设，不是改动已有验收门限。TF未来量单独包含slam.yaml的transform_timeout=0.2s：Humble源码publishTransformLoop使用scan_timestamp+transform_timeout；不可套用scan的0.1s未来容差。依据：https://raw.githubusercontent.com/SteveMacenski/slam_toolbox/humble/src/slam_toolbox_common.cpp 。原误报报告health-bent1.json与修正后的全矩阵都保留。

静态核对：本机SLAM安装包的loop_search_space_dimension=8.0、loop_search_maximum_distance=3.0、loop_match_minimum_response_fine=0.45与项目一致，属于默认值；是否假回环仍未验证。Fortress DiffDrive的官方参数与ign-gazebo6实现没有odom随机噪声配置/生成路径，里程计由轮关节位置积分，打滑属于物理模型效应；依据：https://gazebosim.org/api/gazebo/6/classignition_1_1gazebo_1_1systems_1_1DiffDrive.html 与 https://raw.githubusercontent.com/gazebosim/gz-sim/ign-gazebo6/src/systems/diff_drive/DiffDrive.cc 。不把其他Gazebo版本或插件的noise参数照搬到本机。

在线对照：20261027-t2-C-baseline0正常走完探索、保存与返回，终态incomplete；健康监测未阻断。与T1的B一样独立通过0/1，地图、返航、安全几何门限通过。这里只证明正常场景没有被本轮监测误报，不是多种子成功率。
