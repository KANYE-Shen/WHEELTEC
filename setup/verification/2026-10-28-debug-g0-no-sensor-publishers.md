# 2026-10-28 G0 只读核查：未通过

用户已回复“通过关卡0”，本次解释为允许执行G0，不代表实际接口数据已通过。没有G1或运动授权；未启动驱动、Nav2、探索、底盘或安全控制链，未设置系统时钟。

## 本次数据

- RDK X5 V1.0，aarch64，Ubuntu 22.04.5，ROS Humble。
- `robot/inspect_interfaces.py --seconds 15`：15.049秒，返回1；scan/odom各0条消息、0个发布者，两项失败。接口检查JSON中的null频率为无样本，不写成测得0Hz。
- ROS图仅检查节点及网页适配器；列出的scan/image/map/odom话题由订阅端也能建立，不代表驱动运行。未得到odom→base→laser，不声称TF正常。
- 内存总7080 MiB，可用6267 MiB；检查期间主机CPU忙碌9.9%。这是本次空闲/监看负载，不是SLAM+Nav2+探索负载。
- 小车时钟独立复核为2000-01-01T00:18:35Z，电脑记录日期2026-10-28；未改时钟。机器人内部同钟消息的相对新鲜度与跨设备绝对时间必须区分。
- 相机别名/dev/RgbCam指向/dev/video0；雷达/dev/wheeltec_lidar指向/dev/ttyACM0，控制板/dev/wheeltec_controller指向/dev/ttyACM1。存在设备节点不代表驱动健康。
- 厂商配置写mini_4wd、ls_N10Plus_uart、usb；这些是配置事实，不是实物运动学、雷达铭牌或有效FOV测量。没有消息，不能填实测束数、视场、量程、IMU有无。

## 复现与定位

最小复现：在既有ROS Humble环境运行本仓库robot/inspect_interfaces.py，15秒、新输出JSON。源码SHA256及车端精确命令/目录见run.json；原始stdout/stderr及interfaces.json全部保留，失败不覆盖。网页连接证据显示kind=robot、control.enabled=false，所有流无消息，与0发布者交叉印证。

分层：传感器发布者0 → TF未取得 → 里程计0 → SLAM未运行、map未收到 → AMCL未运行 → Nav2未运行 → 探索未运行 → 评估仅订阅/资源读数，不读取仿真真值。可证伪假设是“驱动未启动导致无数据”；若成立，应无驱动发布者，而经核验启动独立传感器后应出现真实消息。本次前半证据满足，后半未执行，不能判定硬件损坏。

另独立读取time.time/gmtime确认2000年时钟，非报告日期格式问题。是否缺RTC电池/NTP/网络路由尚未验证，不猜改配置。

## 安全审阅与下一步

已静态读取相机入口及USB下游launch，只含相机及图像转发；雷达入口按现有配置构造lslidar_driver。未运行这些入口。`turn_on_wheeltec_robot.launch.py`会包含base_serial，并实例化wheeltec_robot_node，具有控制板接入；不能用“看看odom”为由启动。完整命令类型和可安全只读获取odom的方法尚待进一步核实。

现有robot/准入关卡.md的G0写“不开启本轮新服务”“不重启驱动、不改车端配置”；因此暂停在保留报告，下一步需用户明确是否扩展到启动已审阅的独立相机/雷达驱动。系统校时另需明确允许，不能自动跳时后仍把旧采样与新采样拼成一批。实物尺寸、雷达铭牌和急停情况需操作者填写；本轮不进入G1。

没有有效sensor流，未录空bag冒充静止校准；后续有真实流后才单独录60秒。保留网页只读适配器，不启用PTY/WASD。

## 审计脚本元数据修正

config-audit.json原输出的config_path字段因循环变量复用错误指向最后一个cpp；原输出保留。config-audit-corrected.json明确真正读取的配置路径。configured_not_measured内容未更改，不把错误路径当配置来源。本次没有算法修改，无需为只读采样写与实现同构的测试；结论由实机15秒样本和独立读数支持。
