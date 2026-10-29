# 2026-10-29 起点假设与失败记录设计

用户确认：仅仿真起点例外。实车仍遵守G0–G5。

1. replay buffer/保存不可覆盖的逐尝试case.json与原始结果/状态副本；索引保留缺结果、中断及未执行动作。大bag留原位置并记录路径/哈希。历史证据不移动、不重评分；评估真值永不自动注入算法。
2. initial_rotation_assumed_safe显式布尔参数，默认false作原基线；active_scan_angle_deg=0仍禁用主动扫描。启用且为隔离仿真时，在首个目标前一次完整360度观测；在状态中明确assumed、clearance_proven=false。不修改地图。途中仍由完整扫掠检查和现有观测预算决定，健康/TF/超时/取消及Nav2碰撞检查不变。重复initial调用不得再次享受例外。
3. 时钟统一以本机即时UTC为参考；实车use_sim_time=false，不重写已有bag/stamp。改钟后可能需重新初始化驱动时间基和TF缓存，先备份/核实具体进程后再维护。当前SSH读取失败，未改钟。
4. odom/TF最多一轮15秒采样及发布者/节点清单；未取得SSH不算硬件故障。编码器/实测轮速可积分，cmd_vel只能作标记的开环预测，不发布冒充可靠odom。

验证：先失败单测；纯策略、真实ROS生命周期、仿真回归；相同固定种子比较仅startup-assumption false/true。所有运行新目录，latest不变；不为赶结果取消底层安全。
