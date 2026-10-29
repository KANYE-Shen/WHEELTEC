# 本次irregular_arc自主性说明（2026-10-29）

用户询问是否为现有算法自主运行，是否有agent干涉。

本轮核对live-start.json、demo-result.json、source.json，并重算active_scan.py/node.py/defaults.py/check_exploration.py四个关键文件SHA256，全部与运行前冻结清单一致。

运行前改动：按用户确认加入仅隔离仿真的起点完整旋转假设。显式--active-scan-angle 360 --initial-rotation-assumed-safe，首目标前由Explorer调用Nav2 Spin一次；后续旋转仍按完整已知净空与增益检查。默认例外false，原默认centroid视点策略保留。不是昨夜原封不动的启动流程，也不是普通默认入口自动启用。

自主行为：SLAM Toolbox根据模拟scan/估计odom建图；frontier centroid策略自动选择6个目标；Nav2规划与控制并返回6次成功；Explorer决定保存和返航。途中另一次扫描候选通过净空评估但因无预期信息增益而不发动作，最终incomplete。

本agent运行中操作：只读查看日志/过程/结果、启动只读查看器及浏览器、写证据报告。没有发额外遥控或手工导航目标，没有运行中修改算法/地图/机器人位置。场景/起点/seed为预先给定，spawn-pose用于仿真初始化和评估，不作为定位输入；真值仅评估。该说明描述本轮agent自己的操作，不以它冒充独立审计所有外部发布者。

结论：这是现有核心算法加已授权起点策略后的自主运行，不能把它说成完全未修改旧版。动作层面有真实旋转、行驶、自动目标和返航；独立地图精度/完成判据仍未通过，单种子不能代替正式多种子成功率。

原始结果见demo-result.json；失败归档见replay buffer/20261029-irregular-arc-seed0-startup-assumed/。本轮未再次运行仿真、连接实车、提交或推送。
