# 2026-10-30 阶段一静止核查 v2

第一阶段仍未完成。用户“位置危险、不要启动轮胎”的限制持续有效：未启动底盘、电机、Nav2、探索；未发布速度或做物理停车验证。仅运行本轮独立相机/雷达、只读适配器和短时记录器。没有提交或推送本轮修改。

## 当前结果

| 项目 | 本轮结果 | 证据 |
| --- | --- | --- |
| SSH/网页 | 已认证，实车只读；8766 在线，control.enabled=false | adapter-final-state.json、browser-final/results.json |
| 系统时钟 | 从2000年对齐电脑；首次偏差约-0.209 s | clock-before.json、clock-set-result.json、clock-after.json、clock-final.json |
| 雷达 | 修复后对照651条/64.873 s，10.01956 Hz；超前/倒退/陈旧均0 | sensor-statistics-after.json |
| 相机源时间 | 下表；独立驱动补丁实测改善，原安装保留 | vendor-timestamp.patch、camera-loaded-library-after.json |
| odom/TF | 发布者均0；底盘驱动、EKF、模型TF进程未运行，原因已定位后停止排查 | odom-tf-conclusion.json、vendor-base*.py、vendor-base-wheeltec_robot.cpp |
| 网页简化 | SSH连接表单已删除；后台认证保留；+ / − 缩放，滚轮不缩放，拖动/重置保留 | browser-final/results.json：7/7 |
| 视频浏览器 | 连续显示、源时间健康、503/断流/断网恢复专项7/7 | camera-source-final/results.json |
| 代码检查 | 前端11/11，网关/传输8/8，TypeScript/Vite构建通过 | summary.json；复现见下方 |

## 相机时间戳单变量比较

同一相机、640×480、mmap、30 FPS、同一参数文件；两份配置SHA256一致，见camera-runtime-file-hashes.json。仅改变时间戳换算，未修改网页时效门限、接收时间或原始历史bag。两次顺序采样均未指令运动；操作者未独立确认场景完全静止，所以不能据此标定物理噪声、宣称受控运动A/B或多种子成功率。

| 指标 | 原驱动 | 补丁驱动 |
| --- | ---: | ---: |
| 图像消息数 | 1876 | 1948 |
| 首尾有效时长/s | 62.6278 | 64.9599 |
| 接收频率/Hz | 29.9388 | 29.9723 |
| 源时间超前>150 ms/帧 | 940 | 0 |
| 时间倒退/次 | 62 | 0 |
| 陈旧>1 s/帧 | 0 | 0 |
| 源时间年龄范围/s | -0.85246～0.15447 | 0.05506～0.06204 |

实际厂商源码不匹配先前上游三文件夹具，自动审计正确返回unknown，不能套用旧补丁。重新保存本车源码/完整压缩备份并逐文件审阅；原算法将半秒进位后仍保留小数，并丢失开机时钟的小数偏移，userptr分支还存在微秒/纳秒单位错误。最小补丁统一采用整数微秒累加与规范化纳秒。旧公共秒级getter保留；未改变相机配置、IO方式或其他图像处理。

从实际源码表达式抽取的算术回归：原2/11、候选11/11；整包独立构建成功。此算术测试不覆盖完整V4L2协议或所有设备；本车mmap路径另有上述实测，userptr只有算术验证，长期运行未验证。源时钟换算在相机启动时建立偏移，因此以后若系统时钟跳变，须在安全只读范围内重新启动相机，不能将旧偏移视为持续同步。

## 原始数据与失败保留

车端目录：`/home/wheeltec/.wheeltec-console/stationary-20261030-v2`。

- 原bag `stationary-scan-bag`：/scan 697条，69.4586 s；/rosout 6条。元数据、SHA和各话题时长见bag-metadata.yaml、bag-sha256.json、bag-before-topic-timing.json。
- 修复后 `camera-after-bag`：/scan 694条、69.1562 s；/camera_info 2078条、69.2295 s；/rosout 8条。见bag-metadata-after.yaml、bag-after-manifest.json。未录原始图像像素，图像源header逐条观察留在sensor-statistics-after.json；不冒充完整图像bag。
- 前后完整观察样本分别保存在sensor-statistics*.json；没有删除先前失败。原始bag仍在车端，本轮只将元数据/哈希带回，不存大bag到Git。
- 首次源码下载因目录名usb_cam-ros2被筛选漏掉，旧空目录审计留存；实际源码另存usb-vendor-source、usb-vendor-full.tar.gz并有manifest。
- 本地测试生成命令曾引号语法失败，发生在远程执行前；修正并语法检查后再运行，未产生车辆操作。
- 第一次相机切换未成功：旧nohup父进程忽略SIGINT；20秒后拒绝重复启动。camera-switch-command.json、camera-stop-diagnosis.json保留。核对三个子进程身份后只停止相机子进程，未杀共享进程组；第二次切换成功，见camera-switch-v2-command.json。
- 网页先失败回归browser-before为2/7，修改后browser-after及最终browser-final均7/7。旧视频故障注入结果camera-ui-regression为7/7，修复源时间后另开camera-source-final为7/7；不累加为独立任务成功率。
- 失败索引：`replay buffer/20261030-stage1-stationary-incomplete/case.json`。

## 复现、回滚与后续边界

本机仓库根目录，先确认现有网关已连接**只读实车**：

```powershell
npm test --prefix console/frontend
npm run build --prefix console/frontend
python -m unittest console.tests.test_transport console.tests.test_gateway -v
node console/frontend/e2e/managed-view-readonly.mjs setup/verification/新的只读浏览器目录
node console/frontend/e2e/camera-source-readonly.mjs setup/verification/新的相机专项目录
```

只读ROS确认命令：`ros2 topic info /odom -v`、`ros2 topic info /tf -v`。本轮启动/结束时刻和耗时见odom-tf-conclusion.json，10分钟内已定位原因，不继续串口试错。Windows本机网页不运行另一套ROS；所查看的是经SSH获取的车端图。/dev/wheeltec_controller指向ttyACM1只证明设备路径存在，不能证明底盘反馈正常。cmd_vel积分是开环预测，不能冒充轮式里程计；本轮没有生成假odom/TF。

本轮相机仅手动使用camera-overlay，未覆盖厂商源码或安装，未注册服务/开机项。当前相机launch PID见camera-switch-result.json，库的实际加载路径见camera-loaded-library-after.json。回滚须重新核对当前PID及子进程归属，停止**相机专用**进程后，使用camera-start.json内原相机专用命令重启，不加载overlay；不操作雷达、适配器或底盘。旧硬编码PID脚本只作证据，不能直接重复执行。源码重建前先验证vendor-patch-manifest.json与备份，不自动套用未知源码。

robot/calibration/2026-10-30.json仅把ROS已观察的540束及10.02005 Hz标为measured；有效物理FOV、量程、噪声、底盘、尺寸等继续assumed/未验证。realism.partial.yaml仅供审阅，活动simulation/config/realism.yaml未改。LaserScan头声明360°、0.15～50 m不能写成已测物理规格；scan_time/time_increment均0，不能用于逐束时间校准。已有采样没有操作者静止确认，也没有卷尺/独立角度记录，因此没有sim-to-real gap结论。

下次仍先读AGENTS.md、MOTION_PROHIBITED.json与本报告。硬件串口反馈、物理安全停车、尺寸与外参、低速运动校准以及完整板上负载仍未验证；必须先由操作者消除危险位置并明确新的实测范围，不能将本轮成功自动升级为阶段一通过或运动授权。网页表单删除不删除主机身份校验和令牌认证；密码/令牌不进入仓库。每轮记录和脚本中的操作都不是下一次自动执行授权。
