# 不规则前沿试验独立代码审查

审查范围：b4a1d37..07cd466，及尚未提交的调度、计划、结果索引。审查者与实现者分开，只读，没有修改源码、启动ROS/仿真、连接实车或推送。15项纯小回归通过。

## 已确认问题

1. P2：paired_viewpoint_batch.py仅以run目录判断已尝试；子进程启动前中断可能只有console日志，--resume再次以x模式打开同日志会FileExistsError。最小mock复现确认。修复要求：日志或目录任一存在即保留为已尝试，缺result计失败，继续未执行项，不在原路径重试。冻结批次结束后已修复；红测试重现FileExistsError，绿测试确认首项不重跑、缺result计失败、后项继续。
2. P2：collect_results.py以无强杀/无残留代替正常退出，on-v2/002缺终态且rc2被误记clean。实现者已用两项红测试独立复现并修复，复用现有shutdown_abnormal；cleanup_complete与clean_shutdown分开。原始失败和门限未改，派生索引已重建。

## 其他核验

未发现保守射线、安全膨胀、四连通可达、八连通聚类、残余分类、默认centroid或ROS参数接入的明确回归。真实回放65行、49 ready，没有同case重复帧，目标时刻最大偏差0.538秒，没有>1秒选帧延迟。保存地图评分与实时地图分列。on-v2全部20份与开发v1一份原始结果保留；未把正在写的off项当成已完成。

本机CLI帮助确认--approve-for-me使用workspace-write与自动审批审查，不是跳过沙箱的参数；未发现明确权限绕过。04:00实际触发依然未验证。


## 最终复核

审查者复核两处修复并独立运行8项相关纯Python测试，全部通过，未发现新增明确问题。on/002缺终态正确标clean=false、cleanup_complete=true；off/006内部SIGKILL正确标nested_sigkill=true、clean=false、cleanup_complete=false、no_live_group_members=true。8项与主回归有重叠，不另加到总测试数。原始结果未改，候选默认不升级。

## 子进程退出验收最终复核

实现者发现raw功能成功的nominal/001也隐藏内部SIGKILL后，审查者只读复核新harness及collector，6项纯测试通过。确认追加failure发生在日志关闭后、成功值计算前。独立读取全部20份off原结果：原策略raw/strict均10/10；候选raw6/10、strict5/10，唯一额外严格失败为001。45份哈希范围复核确认核心算法、配置及评分实现一致；运行harness与续跑工具/测试另列变化合理。未发现新的明确代码问题；文档须保留两种口径，本报告已同步。
