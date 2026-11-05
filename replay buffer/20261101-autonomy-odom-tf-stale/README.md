# odom TF过期退出

11月1日17:26:23用户报告odom_combined→base_footprint源年龄1.00999秒而退出。任务ID和车端文件尚缺，直接触发项确认，上游根因待取证。11月3日本地补齐TF时间上下文及console-stop.json，73项回归通过，未部署。

先读case.json与[本地诊断](../../setup/verification/2026-11-03-debug-odom-tf-stale.md)。当前只做本地程序修改与排查，不向底盘发送任何指令（含零速）。连接恢复后先读已有失败文件，不自动启动探索。
