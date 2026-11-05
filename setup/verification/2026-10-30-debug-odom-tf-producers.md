# 2026-10-30 调试：/odom 与 TF 不可用

状态：在用户规定10分钟内定位当前直接原因后停止；没有启动底盘或验证硬件是否正常。

源证据：2026-10-30-stage1-stationary-v2/odom-tf-conclusion.json。开始09:33:23 UTC，完成结论09:37:13 UTC，共约230秒；实际图/进程查询18.391秒，其余用于启动源码与证据核对。先前15秒无数据的失败记录保留。

复现：SSH只读进入现有ROS环境后 ros2 topic info /odom -v 与 ros2 topic info /tf -v，均Publisher count:0。话题之所以出现在列表中是适配器订阅，不能据此称为有数据。本机Windows网页通过SSH读车端ROS，不运行本机另一套ROS定位。配置/源码哈希见当轮artifact manifest；实车seed不适用。

分层证据：独立scan约10Hz、相机约30Hz可用，说明不能将整个ROS通信链认定为失效；/odom、/tf发布者0；运行进程只有传感器/适配器，无wheeltec_robot_node、EKF、模型TF。厂商wheeltec_robot.cpp:761创建odom发布器，base_serial.launch.py启动该底盘串口节点；turn_on_wheeltec_robot.launch.py组合底盘、EKF、模型，后两者负责动态/静态变换链。源码显示底盘节点会写串口和订阅cmd_vel，因此在当前禁动条件下没有为取odom而启动它。

假设：如果缺失直接来自生产者未启动，应观察发布者为0且对应进程不存在；两者及源码均符合。该证据不能排除未来启动后另有串口、IMU、帧名或硬件故障。/dev/wheeltec_controller→ttyACM1仅路径存在，没有读取控制串口或测编码器，硬件状态未验证。

SLAM/AMCL/Nav2/探索均未运行，后续层的map→odom、定位协方差、目标/重试和地图评估未验证；没有为消除告警而补假TF或用cmd_vel积分替代测得里程计。仅根据指令速度积分无法观察打滑或执行器误差。本轮不进行修复尝试，保留软件生产者缺失结论并暂停，等待安全位置及具体范围的新授权，不重复无限核查。
