# 2026-10-28 夜间离线工作记录

状态：离线验证已完成，最终归档/推送核验中；实车已断开，未连接、未部署、未发送运动命令。新版AGENTS与附件字节一致；旧版AGENTS-before.md、副本AGENTS-attached.md。机器进度task.json；凌晨3点续作登记证明scheduler-proof.json，说明见setup/automation/g0-night-continuation.md。


最终结果：相机Hz离线7/7，ROS/仿真回归97/97，完整探索0/40、首目标0/40，G0未通过。新增算法保持默认关闭，不部署实车。完整对照见[P0-results.md](P0-results.md)，Git提交和远端核验见push-receipt.json。

| 检查 | 通过/总数 | 结论边界 |
| --- | --- | --- |
| 网页后端 | 29/29 | 本地回归 |
| 网页前端 | 11/11 | Hz与告警状态 |
| 浏览器相机Hz | 7/7 | 真实时间异常记录+合成视频离线回放 |
| ROS/仿真测试 | 97/97 | 包含动作future夹具，不是实际Spin制动 |
| 探索纯Python | 45/45 | 净空/前沿/健康等 |
| Robot工具/安全 | 26/26 | 未部署实车 |
| 续作守卫 | 5/5 | 实际未来定时触发未验证 |
| 上游C++候选 | 8/8 | 未构建完整驱动，车上版本未知 |
| 最终完整任务 | 0/40 | 未达到独立验收，失败全部保留 |

## 今晚实测证据

前期在线G0采样保留在../2026-10-28-g0/；初次无传感器失败、首包53.09秒、补录60.775秒/610条各自保留。雷达约10.02Hz、540束、消息角跨度360度；驱动声明0.15–50m，不是有效FOV/量程实测。相机源时间倒退/未来时间、系统年份2000、odom/TF缺失，G0未通过。原始bag仍在车端，仅元数据与SHA已归档，未声称已上传大包。

## 相机Hz离线修复

接收频率receive_hz采用单调接收时间，按源stamp去重raw/compressed；保留原采集hz/fresh及异常告警。scan/odom/map安全健康判定未放宽。断流、暂停更新、断线均隐藏过期指标。

最终验证：后端29/29、前端11/11、TypeScript/Vite构建通过；离线浏览器专项7/7。原6/6和新增检查6/7失败批次也保留。浏览器使用今晚记录的时间异常序列及明确标注的合成视频/7.5Hz接收数据，不是新实车验证。实际画面修复此前已在只读连接完成7/7，见../2026-10-28-camera-flicker/；本轮Hz与receive_hz尚未部署。

复现：
~~~powershell
D:/Python/python.exe -m unittest discover -s console/tests -v
npm test --prefix console/frontend
npm run build --prefix console/frontend
node console/frontend/e2e/camera-hz-offline.mjs
~~~
浏览器专项要求已有本机网关提供前端文件；脚本拦截全部API/WS，不连接实车。不要运行含运动的旧浏览器全量脚本。

## G0离线补齐

inspect_interfaces.py增加相机、逐条未来/陈旧时间检查和异常年代诊断。车端工具及安全回归26/26。未伪造odom/TF，未启动底盘。源码审计与候选patch见[g0-timestamp/REPORT.md](g0-timestamp/REPORT.md)：Python12/12，真实上游头C++候选8/8；旧版及不完整PR失败保留。候选不是完整驱动，更不是本车已修复。

下次先核对本车驱动SHA/V4L2时基、系统clock来源、既有odom/TF接口；提交G0只读补采、停止和回滚步骤后等待授权。版本未知时拒绝应用候选。物理尺寸/运动学由操作者测量，G1–G5仍未批准。

## P0安全主动观测实验

默认active_scan_angle_deg=0，仅use_sim_time、ROS_LOCALHOST_ONLY=1且非板卡环境允许显式打开；经Nav2 Spin，不直接发布速度。完整圆形包络覆盖车体扫掠范围，未知/占据/越界拒绝；TF/地图健康检查、次数与ROS超时有界。不会提高激光单帧角分辨率。

探索策略及既有回归45/45，colcon build通过。真实Gazebo smoke因unknown_swept_space拒绝，完整任务失败，原始目录Linux工作区data/runs/20261028-active-scan-smoke-v1。正式冻结批次已全部归档，最终v3严格0/40：irregular_arc和recess各5种子，每种子0/90/180/360四角度，realism=on且其余输入相同。

~~~bash
source /opt/ros/humble/setup.bash
source /home/wheeltec/wheeltec_sim_ws/install/setup.bash
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/paired_active_scan_batch.py --output /home/wheeltec/wheeltec_sim_ws/data/runs/NEW-active-scan-ab --scenarios irregular_arc recess --seeds 5 --domain 90
~~~

未验证：安全已知区域内真实Spin成功/取消与后续目标生成、实车驱动修复、物理准入、sim-to-real gap。完整成功率与Wilson区间见最终结果；不以原型存在冒充P0全部完成。

Windows直接运行Linux/ROS测试套件产生缺rclpy/POSIX接口等失败，保存在simulation-all-tests.log，不能视为通过；改在已有WSL ROS环境复验，不修改测试放宽要求。

## 历史排障与分项推送过程（阶段快照）

已推送工作分支work/irregular-frontiers-20261027，远端823a522；分项提交e3e7f7a（实测/附件规则）、ee756f9（相机）、cdd572a（G0工具/候选）、823a522（普通权限续作）。

v1正式40次已完成，严格成功0/40，首目标0/40；每场景/角度均0/5，Wilson95%区间[0,43.45%]。不是提高成功率的证据。诊断保存终态：10次baseline无目标，28次主动观测净空未知拒绝，2次Nav2未激活；无运动请求。12次wire终态缺失中含上述2次未启动。估计地图诊断图estimated-sweep-refusal.png，红叉为扫掠范围内未知格，灰色为未知、白为空闲、黑为障碍；未将诊断反馈算法。

取消遗漏经先失败测试修复；8项生命周期检查及3项状态订阅检查通过。实际Spin旋转/取消仍未验证，纯future夹具不构成该证明。实际proto默认关闭，只在有完整已知净空时允许仿真动作。

v2复验单纯1秒回调排空仍漏收，16个完整结果及第17个中断尝试全部保留（0/17），其他计划行未执行，不加入已执行成功率。中断时父/评估器退出未完成子进程清理；已按确切命令行与独立进程组发送SIGINT，两组remaining=[]、未强杀，见v2-owned-orphan-cleanup.json。这是测试工具中断路径的已知限制；不得把其现场复用为可靠实车进程管理。

进一步假设为短寿命status发布器未等DDS匹配，评估harness显式要求record模式2个状态订阅，默认任务不要求评估器。单次复验拿到5条状态和5条录包状态，最终map_unstable/tf_stale仍失败。v3重新冻结相同40个种子/角度，全量复验中。最终统计以后续追加为准。

初步实车差异见sim-to-real-gap-preliminary.md，校准观测索引robot/calibration/2026-10-28-g0-observations.json；未知数据保持未知。真实bag本机尚无，不能离线估计量程噪声并宣称已校准。

## 最终验收数据（2026-10-29 凌晨）

相机Hz与整卡片告警稳定性新增1项失败回归并修复，最终离线浏览器7/7，前端11/11，后端29/29、构建通过。原6/6和新增检查的6/7失败批次均保留，未选择性丢弃。新Hz/告警代码没有部署到已断开的实车，真实视频旧专项7/7是此前另一项验证。

最终v3严格0/40，首目标0/40；37个incomplete、3个map_unstable/tf_stale。真值有效40/40，最近地图选择40/40保持不变，终态消息40/40收到，无运动请求。每场景每角度均0/5，Wilson95%[0,43.45%]。完整逐格质量、耗时和失败见[P0-results.md](P0-results.md)与final-statistics.json。原v1 0/40、v2 0/17及两个smoke失败保留，本夜99次仿真尝试全部失败，算法没有通过独立验收。

状态采集改进：v1有12/40缺wire终态，其中2个Explorer未启动；最终v3 0/40缺失。比较仅证明该批次采集完整，不证明统计可靠性或探索成功改善。TF源与消费者时序的真实bag分析见../2026-10-29-debug-save-tf-stale.md；源TF持续更新而探索器持有旧TF，剩余回调/计算积压假设未修复，不调门限或盲调SLAM。

最终回归：ROS/仿真97/97、探索纯Python45/45、robot26/26、后端29/29、前端11/11、续作守卫5/5、C++候选8/8、离线浏览器7/7；这些不等于完整任务通过。原始红/绿日志、错误运行平台日志和中断清理记录都保留。冻结源码zip保留试验实际字节；批次结束后仅清理两处文件尾空行，不改变算法逻辑。

未解决：P0正向Spin及真实取消/制动尚未运行验证；未知扫掠空间阻止启动；3个消费者TF过期；批次中断曾遗留自有子进程（已核对清理）；本车驱动版本、源stamp修复、系统clock、odom/TF、有效FOV与物理测量待G0补采。G0未通过，不进入G1。准入补充见robot/2026-10-28-实车准入补充.md。初步gap不是完整sim-to-real报告。

新旧续作守卫均已使用同会话queue，不覆盖审批权限；旧守卫遗留选项有先失败回归后修复。03:00任务已登记，实际未来定时触发未验证；离线交付完成后状态标completed以保持静默。不要为验证定时器而启动新的代理或绕过审批。

状态订阅配对复验使用v2全部16个完整尝试及v3对应相同种子/pose/角度，未按结果筛选；旧漏收2/16，新0/16。第17个中断尝试另记失败，未丢弃。记录paired-status-observer-comparison.json。
