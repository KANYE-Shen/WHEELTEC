# 现实化仿真

通过 run_room.py 使用 realism:=on（默认），对照为 realism:=off。直接 ros2 launch 保留 off 默认，因为运行资产须由 run_room.py 生成；正式评估使用 check_exploration.py，默认 on。

```bash
python3 simulation/run_room.py gui:=false rviz:=false scenario:=baseline spawn:=0 realism:=on seed:=0 noise_scale:=1
python3 simulation/check_exploration.py --scenario baseline --spawn 0 --realism on --seed 0 --noise-scale 1 --record --output ~/wheeltec_sim_ws/data/runs/NEW-NAME
```

参数唯一来源是 robot/calibration/日期.json 生成的 config/realism.yaml；每次运行保存完整来源、哈希、seed、强度及生成的模型/bridge/Nav2/SLAM。原始参考文件不覆盖。现有全部值为 assumed，实际雷达规格、车体、IMU 未验证；未校准配置不能作为实车准入证明。

激光经 raw_scan 后处理，独立随机流控制高斯误差、丢点及时间戳抖动。FOV、束数、频率、量程在生成模型中配置。270° 以外为假设盲区，其他盲区须测量后加入。保留 Ogre 三条相邻垂直线兼容方案。本机原生 Gaussian 有效，但本实现关闭原生噪声，统一在可设种子的节点注入，避免重复计噪。

DiffDrive 输出 raw_odom/raw_tf；raw_tf 不桥接。独立节点从轮式里程计增加轮径/轮距比例、左右不对称、白噪声、随机游走和转弯横向滑移，独自发布 /odom 与 odom→base_link。ground_truth 桥接不变，只供评估。命令经延迟、死区、速度及加减速度限幅后进入仿真插件；失去命令时清空队列并制动。该节点没有实车驱动功能。

尺寸、轮参数、Nav2 footprint 与探索半径从同一 profile 生成；探索半径是矩形外接圆加显式安全余量，保持 0.35 m。动力学质量/惯量仍为参考模型，尚未校准。IMU 存在性未知，当前不生成 IMU 或启用 EKF，不能据此得出有无 EKF 的效果结论。

任务与仿真栈使用相同四核 taskset，实际 affinity 写入 manifest；包括 Gazebo 在内的主机负载不能等同 RDK X5。resources.jsonl 记录 SLAM、Nav2、探索的主机 CPU/RSS。最终须板上五分钟实测。

scale=0 保留视场、尺寸、速度/加速度限制，关闭随机误差、比例误差、延迟和死区；其与 scale=1 配对用于噪声诊断。off 是完整旧模型对照，两者不能混称。种子控制注入随机流，不能保证 Gazebo/DDS 调度逐位相同。
