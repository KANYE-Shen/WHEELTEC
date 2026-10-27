# 残余前沿与退出分类调试

起始提交2eace6e，T1首次修复。原始日志在Linux data/runs/20261027-regressions；A/B完整记录分别为20261027-t1-A-baseline0、20261027-t1-B-baseline0。未随机扰动，种子未显式控制，不能称为五种子统计。配置哈希保留在每次result.json的source.sha256。

## 复现

在已加载ROS与workspace的WSL运行：

```bash
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/check_exploration.py --scenario baseline --spawn 0 --record --output ~/wheeltec_sim_ws/data/runs/<新的目录>
python3 -m unittest discover -s /mnt/d/虚拟c盘/WHEELTEC/src/wheeltec_explore/test -v
python3 /mnt/d/虚拟c盘/WHEELTEC/simulation/test_outcomes.py
```

现状复现：原算法几何指标全部通过，state=incomplete、unreachable_clusters=1；harness附加abnormal shutdown explorer rc=2。假设：返回码属于任务结果而非进程失控；若成立，应有终态且无强杀和存活组成员。A记录证实，针对该条件的失败回归修复后通过。

## 分层证据

- 传感器：A/B rosbag验证扫描话题有数据，真值质量均有效；完整时间戳统计继续由bag健康回放核查。
- TF：过程记录实际位置与扫描，仅用已估计TF；T1未修改TF，突跳与年龄监控留T2。
- 里程计：本项未改odom，无新增漂移结论。
- SLAM：均保存地图和位姿图，独立地图几何门限通过；不能据此推定所有布局无假回环。
- 定位：此为mapping模式，AMCL不运行；不混用定位器。
- Nav2：所有选点返回成功，任务返回起点；A返航误差0.159889m、B为0.145606m。
- 探索器：B仍有1簇reachable_unexplored（约18格、21个接近点），缺少足够的实际多视角/完整覆盖证据，保留incomplete。离线检查成功目标端点与连续运动位置的覆盖并不相同，不能把目标坐标当已实际到达的观察位置证明。
- 评估器：几何评分定义与门限未改；仅将有终态、无强杀/残留的rc=2从异常退出分离。B的failures为空，但completed=false，独立验收仍失败。

## 前后结果

| 项目 | A 原算法 | B T1 |
| --- | --- | --- |
| 独立验收通过 | 0/1 | 0/1 |
| 地图/返航/安全门限 | 全部通过 | 全部通过 |
| 内部终态 | incomplete | incomplete |
| 附加异常退出 | rc=2误报 | 无 |

0.6/0.8米构造凹袋与静态阴影红绿测试通过；原有导航安全集和门限未放宽。没有将本轮未通过结果删除，也没有通过修改分类证据要求强行使baseline通过。T1剩余多种子闭环验证随T5进行；不得把纯Python用例通过率当作仿真任务成功率。
