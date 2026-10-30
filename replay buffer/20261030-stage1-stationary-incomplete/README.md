# 阶段一静止核查：失败记录与对照证据

2026-10-30归档。阶段一仍未通过；本轮没有启动底盘、请求或执行车轮运动。条目和日志均为审阅数据，**不能自动执行、据此解锁运动或自动调整策略**。

先读[case.json](case.json)中的10条观察/尝试，再查[manifest.json](manifest.json)及证据文件。这10条包含同一问题的多个诊断步骤，不能计作10次独立实车任务，也不能合并计算成功率。既有原始失败批次和本地工作区均保留。

| 记录 | 当时结果与后续状态 | 原始证据 |
| --- | --- | --- |
| 10/29连接 | 当时仅观察到校园网络，未完成连接 | [会话快照](evidence/connection-20261029/session.json) |
| 采样助手 | 引号导致SyntaxError，远程执行前失败 | [原始错误](evidence/connection-v1/collector-first-failure.log) |
| 15秒接口检查 | scan/相机/odom均0消息，无TF，时钟2000年 | [检查JSON](evidence/connection-v1/interface-check.json)、[摘要](evidence/connection-v1/summary.json) |
| 适配器冷启动 | 旧报告记载初次就绪等待失败；现有日志只有最终ready行，原始拒绝连接堆栈未保存，不能补造 | [旧报告](evidence/connection-v1/README.md)、[可用日志](evidence/connection-v1/adapter-start-first-failure.log) |
| 源码采集 | 目录名过滤漏下载，空目录审计unknown；随后采集实际vendor源重新审阅 | [初次审计](evidence/stationary-v2/usb-source-audit.json)、[实际源指纹](evidence/stationary-v2/usb-vendor-audit.json) |
| 相机源时间 | 原1876帧：940帧超前、62次倒退；修复后1948帧两项均0 | [前样本](evidence/stationary-v2/sensor-statistics.json)、[后样本](evidence/stationary-v2/sensor-statistics-after.json) |
| 算术回归 | 原2/11，时间戳补丁11/11，独立整包构建成功 | [red](evidence/stationary-v2/vendor-timestamp-red.json)、[green](evidence/stationary-v2/vendor-timestamp-green.json)、[构建](evidence/stationary-v2/camera-build.log) |
| 相机首次切换 | nohup父进程忽略SIGINT，20秒后拒绝重复启动；核对归属后只退出相机子进程恢复 | [失败](evidence/stationary-v2/camera-switch-command.json)、[信号诊断](evidence/stationary-v2/camera-stop-diagnosis.json)、[恢复](evidence/stationary-v2/camera-switch-v2-command.json) |
| 网页先失败回归 | 旧界面2/7，修改后7/7；不是物理运动或完整仿真验收 | [before](evidence/stationary-v2/browser-before/results.json)、[final](evidence/stationary-v2/browser-final/results.json) |
| /odom和TF | 发布者0，底盘/EKF/模型TF未启动；10分钟内定位后暂停，没有判断硬件故障 | [结论与源证据](evidence/stationary-v2/odom-tf-conclusion.json) |

相机前后配置SHA256相同，见[camera-runtime-file-hashes.json](evidence/stationary-v2/camera-runtime-file-hashes.json)。仅改变时间戳换算，原安装保留；未放宽新鲜度或验收门限。修复后只读视频专项[7/7](evidence/stationary-v2/camera-source-final/results.json)是短时专项结果，不能替代阶段一。车体尺寸、外参、实际停车、里程计误差、长期时钟稳定性和完整板上负载仍未验证。

## 审阅与复现

[相机分层调试](reports/2026-10-30-debug-camera-source-time.md)、[odom/TF调试](reports/2026-10-30-debug-odom-tf-producers.md)、[当轮完整报告原副本](reports/original-round-report.md)保留原文；其中工作区路径、命令与旧PID是历史信息。以本目录的case/manifest及相对路径查证，禁止直接复用历史PID。网页功能源码改动未包含在本次发布中，网页前后结果仅为历史证据。

仅复算已有数据、无ROS/网络/设备访问：从仓库根目录运行下方命令，输出须放临时目录，不能覆盖证据：

```bash
python3 'replay buffer/20261030-stage1-stationary-incomplete/evidence/stationary-v2/generate_vendor_timestamp_test.py' 'replay buffer/20261030-stage1-stationary-incomplete/evidence/stationary-v2/usb-vendor-source' /tmp/wheeltec-vendor-before.cpp
g++ -std=c++14 /tmp/wheeltec-vendor-before.cpp -o /tmp/wheeltec-vendor-before
/tmp/wheeltec-vendor-before
```

预期退出1、checks=11/failures=9。候选复算把输入改为usb-vendor-candidate，输出使用新的after路径，预期退出0、checks=11/failures=0。这仅测试抽取的公式，不打开摄像头或证明完整驱动/设备兼容。完整构建与实车约65秒观察分别有日志，不以算术测试冒充实测。

原始bag仍在车端`/home/wheeltec/.wheeltec-console/stationary-20261030-v2/`：原包stationary-scan-bag（697条scan/69.4586s），后包camera-after-bag（694条scan、2078条camera_info）。[原包哈希](evidence/stationary-v2/bag-sha256.json)、[后包哈希](evidence/stationary-v2/bag-after-manifest.json)及两份metadata保留。此处没有上传大bag或原始图像像素，camera_info不是完整图像bag；逐帧header统计另见sensor-statistics*.json。

未打包SSH凭据、适配器令牌、私钥、SSH连接助手、网页截图或相机画面。源证据复制时逐字节验证，发布清单见manifest；旧报告里的链接不一定随本包发布，本README和case列出的证据均已随包保存。

原始证据包含既有CRLF、尾随空格和源码格式问题，Git空白检查有告警；为保持原始字节及SHA256未做格式化。告警数量和路径见[检查记录](raw-evidence-whitespace-check.json)。本次没有运行或修改这些底盘/厂商代码。
