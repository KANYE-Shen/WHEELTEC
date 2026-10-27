# 校准输入

当前 2026-10-27.json 只有 assumed 区间，没有本车测量、关卡批准或实车 bag。雷达型号、IMU 和底盘运动学待 G0。540 束、270°、8 m 是用于暴露算法假设的临时配置，不是 N10P 或本车规格。

每个参数保存 value、unit、source、basis；assumed 数值必须落在 interval 内，measured 必须引用 evidence。完成 G0–G2 后另建日期文件，保留本文件和原 bag；禁止把资料标称值标为实测。

生成命令（新输出文件优先）：

```bash
python3 simulation/calibrate_realism.py --input robot/calibration/2026-10-27.json --output /tmp/realism.yaml
```

噪声 σ 需用静止同一有效光束的时间序列估计；丢点统计须区分无回波与驱动无效值。直行需卷尺位移和五次 bag，旋转需独立角度基准，速度阶跃需命令、轮速/里程计及制动实测。无这些数据时校准完成标志必须为 false。
