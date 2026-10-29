# 2026-10-29 三阶段实车流程调整

用户指令：合并原G0–G2为连接后校准及订阅确认；之后人工控制建图，验证SLAM Toolbox和Nav2；再自主探索，覆盖旧G0–G5；删除agent提出的G6–G9。

完成：robot/准入关卡.md只有阶段一/二/三，阶段一内部顺序为订阅→停车安全→低速校准，不增设旧三个独立关卡；阶段二先人工参考图并独立量测，再验证导航；阶段三自主选点、另存图和返航。所有原验收门限保留。人工图不自动作为真值。原G1–G9草案已按用户要求删除，删除文件SHA见removed-proposal.json，未删除历史失败数据。

同步AGENTS.md、README.md、PLAN.md、部署说明.md、robot/README.md、console/README.md、现场测量表当前部分、calibration/README.md、setup/STATUS.md及轮次索引。历史有日期记录里的旧编号只用于追溯。

同步静态预检：内部gate 1/2/3对应三阶段，manual仅1/2，完整Nav2为2、explore为3。采用three-stage-20261029，人工批准记录独立整行匹配当前协议与阶段；旧记录不自动转换，错误阶段/旧协议/否定句不通过。阶段一可采集尚未完成的校准；阶段二/三要求完整实测校准和制动数据。hardware_verified仍false、approval_record仍null，没有创建批准记录。代码是未部署模板，本轮没有连接实车、改钟、发运动、启动ROS节点或通过任何阶段，也没有提交/推送。

先失败回归safety-red.log保留；robot35/35、console29/29、静态launch --show-args和watchdog/adapter --help通过（launch-help-strict.log，set -e确保各步失败不会被最后返回码掩盖）。业务diff --check通过。validation.json为9/9，受保护947份历史/失败数据/仿真算法文件哈希不变。未执行新仿真/实车测试，不把静态验证写成现场通过。

审阅：检查旧协议不误配、阶段1不会豁免硬件/安全值、阶段2/3不能跳校准、manual与explore入口阶段一致、默认只读不变；未改MotionGate、SLAM、Nav2参数、探索算法或原始试验结果。新审批协议在部署前需由操作者提供对应新记录，不自动迁移旧授权。

下一步：只安排阶段一连接订阅与校准的具体清单/场地和现场操作范围；必须先核对当前连接/硬件，不能从历史PID/IP推断在线或有运动授权。odom/TF一次有界核查后缺失即反馈，不反复猜测硬件。
