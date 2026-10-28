# 传感器启动后的G0记录

用户授权只启动独立相机与雷达，未启动底盘。正式结果见summary.json：激光通过15秒接口检查，但odom/TF缺失、相机源时间戳异常、系统时钟2000年，G0未通过。interfaces.json及stdout/stderr保留原始returncode=1。

首包record进程60秒但启动耗时导致实际扫描跨度53.09秒，保留未删。追加v2在Recording就绪后计时：610条scan，实际跨度60.774949041秒，bag审计/元数据/日志分别保存，原包位于车端/home/wheeltec/.wheeltec-console/g0-sensors-20000101T082312/，哈希见bag-audit*.json。没有odom/TF消息，不以空话题冒充通过。该静止扫描尚未做几何基准测量，不能称为完成全部校准。

相机网页专项修复及7/7结果见../../2026-10-28-camera-flicker/README.md。未提交或推送本轮改动。
