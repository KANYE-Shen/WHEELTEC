# 不规则边界视点遮挡调试记录

## 复现与假设

基线 b4a1d37；本地 work/irregular-frontiers-20261027，不推送。原始源码与每个输入哈希由 Linux data/runs/20261027-irregular-mechanism-v1/plan.json、rows.json 保留；不是实车数据。

最小复现：从仓库目录运行 `python -m unittest discover -s src/wheeltec_explore/test -p test_viewpoints.py -v`。固定 100×100、0.05m、25m² 合成输入，seed=0，起点(.85,.85)附近±.03m。原选择器在 straight / curved_c / wavy_edge / thin_frame 中分别看到 98/98、71/202、57/131、39/176 个前沿格；占据图已经保留不规则形状，没有矩形近似障碍。

可证伪假设：若中心选点忽略遮挡是局部低效原因，则在相同安全可达候选中存在更高“可见前沿格数/(0.5m+路径距离)”的候选；若独立 oracle 没有改善或有退化，必须保留并报告，不改门限。

## 自底向上的证据边界

| 层 | 现有证据与本轮边界 |
| --- | --- |
| 传感器/驱动 | 合成输入无传感器；真实Gazebo/bag另记，不能从本测试推断型号、噪声或FOV。 |
| TF | 合成格的地图原点旋转不改变所选格；实ROS仅用估计TF，过期拒绝，禁止接真值。 |
| 里程计 | 合成测试无运动；既有270°假设配置启动阻塞见此前回归报告，本轮不调里程计。 |
| SLAM | 静态地图固定，不调回环；曲形墙SLAM质量需要实际闭环证据，尚未验证。 |
| 定位 | 建图模式无AMCL，不据此判断重定位。 |
| Nav2 | 安全膨胀与四连通可达不变；独立EDT与连通分量核查候选。 |
| 探索器 | frontiers.py 原先仅按整个簇中心及距离选点；已有 visible() 只用于残余多视角证明，未用于选点。 |
| 评估器 | 新评估器按线段与封闭格方形相交的独立slab oracle算遮挡，与整数DDA实现不同；正式map_metrics.py完全不变。 |

## 红绿回归与单变量

新增遮挡用例第一次运行因缺少 viewpoints 模块失败（ModuleNotFoundError），同次保留原算法可见格计数。增加仿真策略接口测试时因 Namespace 无 viewpoint_strategy 失败（AttributeError）；接入后35项探索器、2项退出/策略接口、2项配对计划与27项几何评估回归通过。最终检查以结果报告中的新鲜日志为准。

仅改变选点策略（包括它的可见收益和朝向选择），同一栅格、同一安全膨胀、同一聚类和候选集、同一已有代价尺度。48个候选/96个前沿样本是工程预算，非实车参数。采样未找到可见目标时计 reachable_unexplored；预算不足或LOS不能成为完成证据。无候选时仍走原残余证明，不把未知空间改为可走。

不改变默认 centroid；新 visibility 作为显式试验参数。此次未对同一症状进行三次失败修复；若有后续失败，附完整批次与分析后再决定，不无依据调SLAM。


## 开发批次 v1 汇总失败（保留，不替换）

首轮Gazebo的首个 centroid 原始试验退出后，paired_viewpoint_batch.summarize 对尚未运行的 visibility 分支计算 k/0，抛出 ZeroDivisionError；不是SLAM或底盘故障。原始目录 `~/wheeltec_sim_ws/data/runs/20261027-irregular-gazebo-v1` 保留。本轮只修汇总空样本分支，缺样本成功率显示null，Wilson为(null,null)，不当作0个失败已通过。最小红测试 test_partial_summary_before_other_arm_runs_is_valid 重现同一除零；修复后3项配对测试通过。正式配对另开v2，首轮开发试验仍列入全部试验索引，不能用v2替换v1。


## 图表兼容性记录

给对照图补图例时，WSL自带Matplotlib不接受新版本参数ncols/outside图例位置，报Legend.__init__ TypeError；报错没有改变实验原始数据。改用该版本支持的ncol、lower center和tight边界后重新渲染检查。该问题仅影响图表，不影响源码冻结或仿真结果。


## 独立审查：退出统计（已修复）

只读审查指出，派生索引collect_results.py把“无强杀/无残留”误当“正常退出”。on-v2/002原始result明确缺终态且explorer rc=2，索引却标clean_shutdown=true。补红测试 test_rc2_without_confirmed_terminal_is_abnormal_even_when_reaped 重现true≠false；修复复用现有shutdown_abnormal判据，新增cleanup_complete单列无强杀/残留。确认终态incomplete+rc2仍正常，缺终态不能正常。原始结果和验收不改；所有派生索引重生成，不能将先前派生all_clean_shutdown=true作为结论。

审查还指出“有console日志无run目录”的续跑边界；等冻结运动批次结束后修复，避免修改运行中的source_manifest。真实65个回放时间点没有同case重复选帧，最大目标时刻偏差0.538s，没有>1s的选帧误差；当前结果未发现跨长间隙取帧。


## 名义Nav2启动失败与嵌套强杀（原始失败保留）

nominal-v1/006_irregular_arc_seed3_visibility：探索器尚未启动即Nav2 did not become active；88份过程帧无capture issue，35版/map，独立真值1323个不同测量时间戳，最大sim间隙0.036s，但到达wall间隙4.596s超过既定0.5s，真值无效。launch.log确认lifecycle_manager_navigation收到SIGINT和SIGTERM后仍未退出，内部发送SIGKILL并报exit code -9。不能以顶层launch rc=0、forced_kill=false宣称无强杀；原试验计失败，不修阈值。

为派生索引补 test_nested_launcher_sigkill_is_not_hidden_by_zero_wrapper_return 红测试，确认此前clean=true错误；新增launch.log嵌套SIGKILL检测，clean_shutdown/cleanup_complete为false，no_live_group_members单独检查。3项统计回归通过。此补丁仅修索引，不修改原始result或验收。Nav2初始化和真值wall gap因果未验证；完整冻结批次结束后按相同seed/pose/4核/120s预算单独复现，若不复现则记录停止，不猜调DDS、CPU、SLAM或策略。


## 独立审查：日志存在、目录未建的续跑（已修复）

20次名义冻结试验退出后，新增 test_resume_preserves_log_only_failure_and_executes_next_trial；原代码在console_log.open(x)重现FileExistsError。修复把run目录或console日志任一存在视为已有尝试：日志原样保留，缺result计失败，后续未执行项继续。绿测试断言只启动后一个试验、不创建或重跑首项目录、原日志内容不变、两项均统计。该修复不改变运动算法或本夜原始结果。

## 最终退出验收漏洞：原始成功中隐藏的子进程SIGKILL

最小复现：`python3 -m unittest discover -s simulation -p test_outcomes.py -v`。先新增 test_launch_child_sigkill_is_not_a_clean_shutdown，红测以AttributeError（缺launch_shutdown_abnormal）失败；补纯函数解析保留日志中的SIGKILL/exit code -9，并在harness关闭日志后、合成功能成功值前加入failure，3项绿测通过。collector复用同一判据，保留raw functional_success，另列strict_functional_success，不改原始result。

全量审计查到nominal/001、006、016三份内部强杀。001_irregular_arc_seed0_visibility原功能通过，但launch日志确认子进程强杀；双方统一重计后centroid仍10/10，visibility由原始6/10变严格5/10。独立审查读取原20份结果再次复算一致。未来harness已拒绝该退出，不放宽任何门限。算法、配置和独立评分保持冻结；harness后改的哈希明确不同。

## 原运行时故障未复现，停止猜测修复

原on/002 tf_stale与off/006、016 Nav2未激活、off/019 tf_stale，按原seed/pose/模式/预算/CPU各复现一次；4/4未重现原症状，结果见runtime-reproductions-summary.json。复现结果原样单列，不覆盖原失败，不并入正式/名义A/B。on复现仍启动阻塞；frame seed3复现有不同保存几何失败，不能以状态completed作成功。当前已排除“确定性同输入必发”假设，尚不能确定调度、DDS、SLAM或策略因果；按规程停止这些诊断，未试调参数。需要后续可重现过程与实测校准；没有达到三次无效修复后继续盲试。

提交前git diff --cached --check发现Matplotlib生成SVG的路径属性行末空格。只去行末空白，并将规范化加入作图脚本；XML全部节点/属性的空白归一化签名改前改后一致，未更改几何或实验数据。复查diff --check通过。该格式问题不计入算法84项测试。
