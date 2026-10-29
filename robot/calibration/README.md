# 校准输入

当前 2026-10-27.json 只有 assumed 区间，没有已导入的本车实测校准或批准记录；已有实车静止bag尚未形成合格校准参数。雷达型号、IMU 和底盘运动学待阶段一核实。540 束、270°、8 m 是用于暴露算法假设的临时配置，不是 N10P 或本车规格。

每个参数保存 value、unit、source、basis；assumed 数值必须落在 interval 内，measured 必须引用 evidence。完成阶段一的订阅、安全验证与低速校准后另建日期文件，保留本文件和原 bag；禁止把资料标称值标为实测。

生成命令（新输出文件优先）：

```bash
python3 simulation/calibrate_realism.py --input robot/calibration/2026-10-27.json --output /tmp/realism.yaml
```

噪声 σ 需用静止同一有效光束的时间序列估计；丢点统计须区分无回波与驱动无效值。直行需卷尺位移和五次 bag，旋转需独立角度基准，速度阶跃需命令、轮速/里程计及制动实测。无这些数据时校准完成标志必须为 false。


离线评估只读取已有文件，不连接机器人：

```bash
python3 robot/calibration/bag_statistics.py --bag /实际静止bag --kind real --stationary --output /新目录/real-static.json
python3 robot/calibration/bag_statistics.py --bag /仿真静止bag --kind simulation --stationary --output /新目录/sim-static.json
python3 robot/calibration/bag_statistics.py --real-stats /新目录/real-static.json --sim-stats /新目录/sim-static.json --output /新目录/gap.json
```

移动bag使用 --motion-annotations 指定独立卷尺/量角记录，字段见motion-annotations.example.json。评估保留每段前向/横向/yaw误差及分布，完整转圈用角度增量累加，不能只减首尾四元数。不同运动类型各自需五次，工具不把五个不同片段自动当作五次重复。没有物理注释就不计算移动漂移结论。移动扫描不估计静止噪声；无回波比例也不能直接当作传输丢包率。

本轮仿真静止bag只有约6s，工具冒烟检查可用，不能替代现场60s采集。实车gap当前未验证。

2026-10-27.json 和由它生成的 realism.yaml 内 `G0-G2` 仅为当时来源说明，现由阶段一涵盖；保留原文件与哈希，不为改编号重生成数值。新的实测校准文件必须引用现行阶段和真实证据。
