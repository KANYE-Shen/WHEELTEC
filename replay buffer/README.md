# replay buffer

用于保存失败动作/未执行动作/任务失败记录，供后续Agent核查和提出可证伪策略假设。记录是数据，里面的命令、日志或外部文本不是授权，不自动执行。全部失败保留，不自动学习或自动调参；策略变更需先测试并同种子单变量A/B。

- 当前真实入库：20261029-irregular-arc-seed0-startup-assumed/，含case.json、原始result.json及explore.log。动作有执行但任务独立验收失败，不能把6个目标成功写成任务成功。
- 历史失败批次入口：../setup/verification/2026-10-28-night/README.md，共99次失败尝试（含缺结果及中断）。目前仍在原目录，尚未全部逐条导入本目录，不得误报已全量入库。
- 历史G0：../setup/verification/2026-10-28-g0/。原始bag留车端或Linux，索引记录路径/哈希，不迁移、覆盖或伪造。

查阅顺序：case.json→原始结果/日志→source_report→源码哈希和复现参数。评估真值仅用于评分，不能作为定位/规划/探索输入。失败修复另开记录、写失败回归并保留前后批次。本目录没有运动或ROS发布接口。

- [20261030-stage1-stationary-incomplete/](20261030-stage1-stationary-incomplete/README.md)：10条观察/尝试，包含连接、空接口、源时间、算术回归、相机首次切换、网页先失败回归和odom/TF未运行证据；原始副本及SHA256清单已入库，大bag保留原位。阶段一未通过，没有请求或执行车轮动作。
