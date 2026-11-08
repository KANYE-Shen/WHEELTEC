# 2026-11-08 厂家网页探索：停车部署记录

用户授权停车部署；本次没有启动探索、解锁或移动车辆。

部署前固定指纹 SSH 检查：任务处于 remote、无控制者、watchdog 未解锁、selector 为 hold、最终速度与原始 odom 为零，五个导航节点 active。厂家 global/local RRT、filter、参数及 PointArray 消息包存在。

同批部署 `console/target/adapter.py` 和探索包中的 `node.py`、`defaults.py`、`frontiers.py`、`vendor_frontiers.py`、`vendor_runtime.py`、`vendor_supervisor.py`。只重启已核实身份的车端适配器；不重启其他组件或覆盖地图。部署保留车端原有 known_ratio 局部观察，未把本地加权区域实验上线。

部署后独立 SSH 检查 task=remote、owner=null、watchdog 未解锁；本机网页网关经原连接读取相机返回 HTTP 200 和 JPEG。适配器当时 PID 为 94643，仅作当次记录，不可用于后续操作判断。静止和画面检查不代表已验证完整探索、存图或返航。

## 恢复边界

原文件及当次进程索引保存在车端 `/home/wheeltec/.wheeltec-console/trial-20261031/vendor-deploy-1794145072179132400/backup`。需要回滚时先取得相应授权，重新核对实时停车、无控制者、任务和 boot/PID 身份，再针对本次文件恢复；保留现有地图、其他服务和新任务证据。不要凭本记录中的历史 PID 或停车状态执行操作。

厂家 RRT 源码的 `char` 有符号性影响候选生成；车端现有二进制的实际行为尚未验证。首次探索由用户根据当前授权在网页发起，若失败先保存任务日志并按实际原因处理。
