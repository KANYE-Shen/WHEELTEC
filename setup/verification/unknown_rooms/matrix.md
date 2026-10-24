# 13组陌生房间结果

独立验收通过 1/13；真值质量有效 13/13；探索内部completed 2/13。

覆盖率为可达安全中心的正确空地覆盖率；墙面值为双向轮廓95分位的较大值。目标：覆盖≥95%、墙面≤10cm、轮廓覆盖≥95%、返航<20cm（原房间旧检查<22cm）、无几何重叠并完成保存和返回。

| 布局/起点 | 任务状态 | 空地覆盖 | 墙面95分位 | 返航误差 | 独立验收 |
| --- | --- | --- | --- | --- | --- |
| 原房间/0 | incomplete | 100.0% | 6.5cm | 14.0cm | 未通过 |
| L形/0 | incomplete | 100.0% | 9.7cm | 11.0cm | 未通过 |
| L形/1 | completed | 100.0% | 7.7cm | 16.3cm | 通过 |
| L形/2 | incomplete | 100.0% | 7.4cm | 14.1cm | 未通过 |
| 家具/0 | incomplete | 100.0% | 7.5cm | 17.2cm | 未通过 |
| 家具/1 | incomplete | 100.0% | 11.9cm | 16.0cm | 未通过 |
| 家具/2 | incomplete | 100.0% | 5.9cm | 15.0cm | 未通过 |
| 弯通道/0 | incomplete | 65.8% | 223.1cm | 280.7cm | 未通过 |
| 弯通道/1 | completed | 100.0% | 79.4cm | 14.1cm | 未通过 |
| 弯通道/2 | incomplete | 100.0% | 15.7cm | 5.7cm | 未通过 |
| 凹角/0 | incomplete | 100.0% | 20.1cm | 10.0cm | 未通过 |
| 凹角/1 | incomplete | 100.0% | 18.3cm | 14.1cm | 未通过 |
| 凹角/2 | incomplete | 59.4% | 219.4cm | 288.4cm | 未通过 |

所有尝试、逐项验收、源码SHA256、进程退出和数据目录见 [matrix.json](matrix.json)。原始13组保留在 [original-batch.json](original-batch.json)，采集器修复后两组重跑见 [truth-reruns.json](truth-reruns.json)。重跑由原真值失效触发，不按地图表现挑选最好结果。

未通过的主要原因见各组 exploration_reason 和 acceptance。incomplete 时探索程序使用返回码2主动报告未完成；原记录中的 abnormal shutdown explorer 字样应结合该状态阅读。地图已保存不等于探索或地图质量已通过。
