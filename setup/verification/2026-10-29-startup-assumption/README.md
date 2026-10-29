# 2026-10-29 起点例外与真实仿真展示

用户指出旧irregular_arc仅12帧。复核确认：原记录t=0.5至5.515秒，采样周期0.5秒；探索器初始化后elapsed_ros=0.83秒即因unknown_swept_space拒绝旋转。0导航目标、motion_requested=false、真值路程0。该段是启动失败，不是完整探索。昨夜99次为失败尝试，不能宣称完成99次探索。

用户此前已明确确认“仅仿真起点例外”。本轮接入initial_rotation_assumed_safe显式参数（默认false作原基线），在首次目标前一次完整360度，记录assumed_start/clearance_proven=false，不改地图；重复尝试和途中仍检查扫掠净空，TF/健康/取消/超时及Nav2碰撞检查保持；参数在物理板卡/非localhost/非仿真条件拒绝。active_scan_angle_deg=0仍总关闭。

先失败测试保存scan-red-assertions.log/lifecycle-red.log；新增夹具漏设rclpy.ok的失败另存lifecycle-fixture-failure.log，未修改生产门限来通过。探索纯Python48/48、ROS生命周期15/15及colcon build通过。未完成全量多种子新A/B，不能宣称成功率提升。

新运行：realism=on、irregular_arc/spawn0/seed0，位姿与昨夜同seed/角度完全一致；隔离domain90、update_latest=false。真实数据在Linux data/runs/20261029-startup-assumption-view-v1/candidate-seed0。启动命令及PID见live-start.json，实际源码哈希与压缩包source.json/frozen-source.zip。页面http://127.0.0.1:8780/实时读取本次process.json，非合成/截图；live-browser-checks.json核对帧数真实增加。

中途核对95帧、t=47.5秒，起点Spin返回成功，之后4个导航目标返回成功。这仅为动作与实时数据证据，不是独立地图/返航验收；最新快照见live-progress-snapshot.json。运行完成以后以result.json为准。未连接实车、未改钟、未检查硬件、未部署或发送运动命令。

暂停待续：replay buffer归档实现、G0时间/odom工作以及≥5种子单变量A/B尚未完成。此前设计/先失败用例不等于功能交付；不得据此声称完整任务已完成。本轮未提交/推送。

## 新单种子运行最终结果

本次实际完成采集221帧，最后仿真时刻110.432s，任务计时106.12 ROS秒。起点Spin成功，随后6个导航目标均返回成功；真值行驶14.1067m，地图已保存、已返航，返航误差0.1341m。最终仍incomplete(active_scan_no_information_gain)，严格0/1，不是多种子结论。

可达覆盖100%；可观测轮廓双向p95=0.1683m（原门限0.10m，失败）；轮廓覆盖81.72%（原门限95%，失败）。任务完成态未通过。真值有效、静态几何投影无重叠、realism=on，全部自有进程组正常清理、latest选择器哈希未变。几何投影无重叠不是物理接触传感器保证。

原始完整结果副本demo-result.json、日志demo-explore.log保留；过程与bag仍在Linux运行目录。网页http://127.0.0.1:8780/现在显示本次已结束记录，可回到开始播放，不应再描述为仍在运行。浏览器真实更新验证3/3，运行时帧数209→221，不是预设动画。源stamp保持原样，未连接实车。

本轮展示比旧12帧提供了真正行驶的证据；它不证明最终建图验收或多种子成功率提高。后续正式对照仍需同代码、同种子、仅起点假设开关变化；旧基线只作历史参照。
