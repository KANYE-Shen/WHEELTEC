# 网页调试与控制终端

电脑本地打开 `http://127.0.0.1:8766`，后台通过 SSH 连接 WSL 或小车。连接小车热点后，在未连接页面的“小车 SSH 密码”栏输入密码，点击“连接小车”；无需打开 Codex 或 SSH 窗口。页面保留目标对象、在线状态和断开按钮。电脑无需安装 ROS。地图、激光、视频和日志来自目标端真实 ROS 话题；未连接时显示无数据，不生成演示结果。

目前可用：SSH 指纹校验、密码/私钥/SSH agent 认证、真实 PTY 终端、地图与雷达图层、局部雷达、JPEG 视频、ROS 日志筛选/暂停/导出、WASD 控制接口、控制权互斥及停车保持。实车只读连接及雷达/视频监看已验证；本轮相机源时间最小补丁已在独立overlay完成约65秒实测，后续Hz统计实现仍未部署；实车运动、安全服务及板上满负载未验证。完整结果和当前仿真端点回波问题见[验证报告](../setup/verification/2026-10-27-console-results.md)。

## 电脑安装与启动

在仓库根目录执行。已验证 Windows Python 3.12、Node 24；建议 Python 3.11+、Node 22.12+。后端依赖固定在 requirements.txt，前端由 package-lock.json 固定。Mac/Linux 的启动方式相同，跨平台实机未验证。

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r console/requirements.txt
npm ci --prefix console/frontend
npm run build --prefix console/frontend
.venv\Scripts\python.exe console/start.py --check
.venv\Scripts\python.exe console/start.py
```

macOS/Linux 对应命令为 `.venv/bin/python`。浏览器打开上面的本机地址；Ctrl+C 关闭网关。服务仅监听 localhost，不要通过改监听地址将完整 SSH 终端暴露到局域网。

## WSL 仿真连接

先完成项目已有 ROS/仿真安装。以下命令仅用于电脑 WSL，不能复制到真实小车启动运动。

仿真终端一：

```bash
cd /mnt/d/虚拟c盘/WHEELTEC
source /opt/ros/humble/setup.bash
source ~/wheeltec_sim_ws/install/setup.bash
export ROS_DOMAIN_ID=77 ROS_LOCALHOST_ONLY=1
python3 simulation/run_room.py navigation:=false realism:=on
```

关闭 Nav2 的速度发布器，确保手动控制独占；不同时运行原键盘遥控。正式准入仍只认 realism=on。当前 on/off 的末端激光束均出现近距离回波，会触发停车；没有删除回波或降低保护，不能声称行驶验收通过。

仿真终端二：

```bash
cd /mnt/d/虚拟c盘/WHEELTEC
source /opt/ros/humble/setup.bash
source ~/wheeltec_sim_ws/install/setup.bash
export ROS_DOMAIN_ID=77 ROS_LOCALHOST_ONLY=1
python3 -m console.target.adapter --kind simulation   --enable-simulation-control --token-file ~/.wheeltec-console/adapter.token   --ros-args -p use_sim_time:=true
```

首次启动生成权限 0600 的随机令牌。仿真由维护者通过原 `/api/v1/connect` 接口传入内存中的 adapter_token，接口仍支持显式 simulation 配置；网页“小车 SSH 密码”入口仅用于实车。不提交、不截图、不把令牌放入 URL。去掉 `--enable-simulation-control` 即为只读；仿真运动仅允许命名 WSL 发行版的 x86 主机、localhost-only ROS。

目标端默认话题 `/scan`、`/odom`、`/map`、`/image_raw` 与 `/image_raw/compressed`。可用 `--scan-topic`、`--odom-topic`、`--map-topic`、`--camera-topic`、`--base-frame` 指定真实名称。图像支持 rgb8/bgr8/mono8/rgba8/bgra8 和 JPEG 压缩图像。仿真原场景无相机，未运行相机时“无实时画面”是正常结果。

### WSL SSH 初次配置

可复用已有 SSH 服务。尚无 SSH 时，在 Windows 创建本机专用密钥：

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\wheeltec_wsl"
```

将生成的 `.pub` 公钥追加到 WSL 用户 `~/.ssh/authorized_keys`；不要复制私钥。目录权限 0700、authorized_keys 权限 0600。WSL 中安装和手动启动仅本机 SSH：

```bash
sudo apt install openssh-server
sudo systemctl disable --now ssh.service
sudo ssh-keygen -A
sudo install -d -m 755 /run/sshd
sudo /usr/sbin/sshd -D -e -f /dev/null -p 2222   -o ListenAddress=127.0.0.1 -o HostKey=/etc/ssh/ssh_host_ed25519_key   -o AuthorizedKeysFile=.ssh/authorized_keys -o PasswordAuthentication=no   -o PermitRootLogin=no -o AllowTcpForwarding=local
```

此终端保留运行，Ctrl+C 关闭；不需要启用系统 SSH 服务。后台连接使用 host=`127.0.0.1`、port=`2222`、username=`wheeltec` 及对应私钥，适配器端口默认 8767。维护者通过受本机会话和 Origin 保护的 `/api/v1/connect` 接口建立连接，详见 [API.md](API.md)。普通使用者无需在网页选择指纹或令牌。

SSH 主机指纹是目标主机公钥的 SHA256 摘要，用于确认是同一台主机；不是密码。首次需通过可信途径核对，不能只相信网络探测结果，已知密钥意外变化仍拒绝连接。适配器令牌是后台访问车端只读/控制服务的随机凭据，与热点密码、SSH 密码分别独立。实车密码入口复用已保存且已核实指纹的唯一 robot 配置，不提供临时信任新主机或覆盖指纹的选项；仿真配置继续走后台接口。

`~/.wheeltec-console/profiles.json` 仅保存名称、主机、端口、用户名、指纹及私钥路径。SSH 密码只用于本次认证，输入框提交即清空，不写入浏览器缓存、配置、日志或仓库；适配器令牌经已认证 SSH 的 SFTP 读取后仅供网关内存使用。网关重启或热点断开后需要重新连接，不自动恢复运动。维护 SSH PTY 是另一个功能，仍受既有停车检查约束。

### 日常连接小车

1. 连接小车热点，打开 `http://127.0.0.1:8766`；若本机网关未运行，先按上面的现有入口启动。更新网页后按一次Ctrl+F5。
2. 输入“小车 SSH 密码”，点击一次“连接小车”。网页显示SSH认证、配置核对、必要校时和原服务停车准备进度，通常需数十秒；无需Codex或SSH窗口。
3. 顶部显示数据通道在线、传感数据恢复后，确认周围安全，再由你点击“自主探索”。连接过程不解锁、不自动探索。

准备只补启动缺失的原有雷达、相机、模型TF、EKF、安全链、底盘反馈、SLAM和适配器，不重启已有进程、不覆盖已保存地图、不增加开机项。驱动启动前先确认新鲜停车保持和零输出，导航与零里程计就绪后才连接适配器。若适配器原已在线，直接连接，不执行这套准备。冷启动新建的是当前内存SLAM会话，不会把完整参考地图交给探索算法。

若显示“自动准备未完成，SSH已保留”，按页面具体原因处理，可“读取适配器日志”或明确点击“重试停车准备”；不会自动反复启动。校时需重新认证时，先断开，再输入一次密码连接。首次仍需维护者配置唯一实车目标及固定指纹；指纹不符、陌生ROS进程或配置变化须先排查，不能自动信任或覆盖。

已有会话不会被密码请求替换。热点断开后若留下旧会话，先“断开连接”再输入密码；显式断开取消候选连接，不能恢复旧按键或运动。密码提交即清空，不保存到浏览器或配置。详细证据见[本轮记录](../setup/verification/2026-11-06-web-auto-prepare.md)。

## 页面操作

- **空间视图**：地图、雷达和位姿叠加；点击 `+ / −` 缩放（显示当前比例），拖动平移、重置恢复视图；滚轮只滚动页面，不改变雷达或地图缩放。雷达按扫描时间查询 TF，无法对齐时不叠加；可切“局部雷达”查看传感器坐标中的原始点。
- **数据状态**：区分 SSH/适配器通路与话题状态；显示源时间、频率、数据年龄。相机或 TF 过期时隐藏对应实时画面/位置；地图保留最后收到的内容并标记更新状态。
- **模式与速度**：点击“自主探索”启动现有算法；点击“远程接管”停止自主任务，按住 W/S 前后、A/D 转向，可组合，首次按键自动申请控制权，松键发零。Space 在任意页面位置停车并回到远程等待，不自动恢复任务。+/− 选择低、中、高三挡，按当前上限的30%、60%、100%限速；默认上限下为0.03、0.06、0.10 m/s，转向上限0.09、0.18、0.30 rad/s。自主探索每次启动恢复中挡。当前新版（2026-11-05已部署，本轮实际输入效果待验证）：自主/启动模式普通键、输入框聚焦和可见窗口失焦不停车；在非输入区按WASD先取消自主并停车，确认远程模式和控制权就绪后，只有仍按住的键才行驶。手动模式窗口失焦或输入框获焦仍停车；页面隐藏/关闭、维护终端启用或断开连接均停车保持。重新连接、重新取得控制权不会恢复旧按键，必须重新按键。
- **维护终端**：真实 SSH PTY，可运行交互命令、调整窗口尺寸、Ctrl+C 和退出 shell。启用前要求目标端确认停车，期间禁止网页遥控。终端内 W/A/S/D 用于输入命令；Space 按用户要求全局保留给软件停车，不再输入空格。Shell 是完整账户权限，不能当作受限控制接口。
- **日志**：汇集 `/rosout` 最近400条、适配器事件和网关最近100条连接/PTY生命周期事件；可筛选节点/文字、暂停滚动及导出当前列表为 JSONL。终端命令输出留在终端；适配器/systemd 进程日志可通过 `journalctl -u wheeltec-console` 查看。 2026-11-05已部署的诊断版本会在安全中止后，把TF源/接收时间、watchdog分项和停止原因保存到任务目录 `console-stop.json`，不依赖环形日志留存；当前状态见[诊断记录](../setup/verification/2026-11-03-debug-odom-tf-stale.md)。

速度显示分别为目标、适配器输出和原始里程计反馈。带噪仿真停车后里程计也可有非零读数，不能据此伪造零反馈。初始接口上限 0.1 m/s、0.3 rad/s，命令/操作者有效期 0.5 s；这些是保守模板，不是本车测得的制动性能。适配器的 0.55 m 全周近点停车保护为 assumed 模板，不能作为已测安全距离。实车最终限制取已核查的安全配置及看门狗。

## 可选 Gazebo / RViz 嵌入

Gazebo/RViz 通过只读 noVNC 桌面显示，原生程序和项目 Ogre 配置不变。只在仿真主机安装：

```bash
sudo apt install xvfb x11vnc novnc websockify
python3 -m console.target.desktop --private-display --display :88
```

之后在**新仿真终端**给原启动命令增加 `DISPLAY=:88 QT_QPA_PLATFORM=xcb`，并取消该终端的 WAYLAND_DISPLAY，启动 Gazebo/RViz。后台连接配置中的 noVNC 端口设为 6080，点击“仿真桌面”。可以并排移动原生窗口；私有 X 显示与现有 WSLg 桌面独立。已有 X 显示可省略 `--private-display` 并指定实际显示号。桌面入口仅仿真可用，VNC 服务必须保留 `-localhost -viewonly`。安装 openssh-server 可能自动启动系统服务；只使用本机专用SSH时应先停止并禁用默认服务，避免意外开放22端口。

相机链路验证使用独立 Gazebo 观察相机，配置见 tests/observer-camera.sdf，不代表实车相机位置或规格。复现夹具见下节。

## 实车连接边界

按[准入关卡](../robot/准入关卡.md)先取得阶段一连接/订阅范围的书面确认，再由人部署并启动默认只读适配器。沿用实车 ROS 域；不设置仿真时钟，不启动 Gazebo，不修改驱动。使用 `--kind robot` 且不传 robot-config 时不创建速度发布器、心跳发布器或解锁客户端。

`robot/systemd/wheeltec-console.service` 和 `robot/start_console.sh` 是未安装的服务模板：确认部署目录、账户、话题、ROS 域及 0600 环境文件后由人按对应阶段的具体实测范围配置。默认仅需 `WHEELTEC_CONSOLE_TOKEN_FILE`；配置 `WHEELTEC_CONSOLE_ROBOT_CONFIG` 与明确 `WHEELTEC_CONSOLE_GATE` 才进入运动预检。不要直接 enable/start 未配置模板。

手动安全链独立入口为 `robot/launch/manual.launch.py`，仅阶段一/二（内部gate 1/2），在对应具体实测范围书面确认后由操作者启动。它包含 velocity_smoother、collision_monitor、最终 watchdog，不启动自主速度发布器；阶段二的 SLAM 另外按批准范围启动。真实运动学、尺寸、驱动话题/失联超时及审批记录必须通过既有 preflight。当前仅支持实测确认的差速底盘；其他运动学保持只读。

手动速度链：网页 → SSH → 适配器控制权/时限保护 → `/safety/manual_cmd_vel` → command_selector → `/safety/nav_cmd_vel` → smoother → collision_monitor → watchdog → 核实后的驱动话题。最终 watchdog 解锁有异步确认，丢失后必须重新人工取得控制权；发现其他速度发布器或驱动输出不独占时拒绝手动控制。关闭网页/SSH 不结束车端安全服务，心跳过期后停车保持。硬件急停、看门狗及实际停止距离仍须现场验证。

## 扩展与验证

接口与扩展示例见 [API.md](API.md)。新增面板通过 src/panels.tsx 注册，`src/examples/ClockPanel.tsx` 是不默认启用的最小例子。新增后端能力使用 `/api/v1`，继续保留认证和控制权检查。

```powershell
python -m unittest discover -s console/tests -v
npm test --prefix console/frontend
npm run build --prefix console/frontend
npm audit --prefix console/frontend
```

真实仿真端到端使用 Playwright Chromium，先运行独立 WSL 夹具，不能用其结果冒充实车或陌生房间算法验收。`tests/simulation_fixture.py` 提供 start/camera/evaluate/tile/stop，默认域 87；每次指定全新 run-id，先等待仿真启动，再添加相机。创建仅测试用的 SSH 密钥/连接 JSON 放在仓库外，连接文件路径通过 WHEELTEC_TEST_CONNECTION 指定；格式为 `{ "profile": {网页同名字段}, "adapter_token": "临时令牌" }`。随后运行 `npm run e2e --prefix console/frontend`。所有失败先归档再重跑；原始结果目录和复现步骤见验证报告。


当前最终浏览器验收9/12。运动近点停车与多客户端原持有者超时仍未解决；前一轮10/12也保留，不能作为当前发布全部达标证明。完整记录见验证报告。


安全审查补充：实车只读模式不创建底盘停止能力，不能把“释放网页租约”当作底盘停车确认。只读时按钮和Space仍可清理本次网页任务/租约，但不创建底盘停车能力；维护PTY拒绝开启。配置并通过对应关卡的安全链后，PTY必须等待最终watchdog在停止请求之后新的、未解锁的状态确认且输出仍独占；缺失确认则保持关闭。完整Shell仍是账户权限。此限制来自已批准计划的“维护终端启用前先停车”，不能用未验证的停止能力绕过；实车已有只读采样，真实watchdog确认仍未验证。补强增加了先失败后通过的HTTP/WS回归，后端共25/25。最近完整真实仿真为补强前9/12；补强后完成单元回归与构建，真实watchdog确认分支未经实车验证，不把旧仿真结果称为该分支的实测证明。


## 2026-10-28 实车视频显示

现有实车只读连接按Ctrl+F5刷新。画面单调接收年龄超过1秒停止显示；源时间戳独立校验，异常明确告警，不能用于定位或安全判断。先解码新帧再替换，慢请求不重叠；断流、断网与重连需真实新数据才恢复。相机专项7/7，不替代完整仿真验收，见[报告](../setup/verification/2026-10-28-camera-flicker/README.md)。

现行实车流程仅三阶段：连接校准→人工参考建图及Nav2验证→自主探索建图。适配器 `--gate` 仅1/2/3，采用 `three-stage-20261029` 审批协议；默认只读，安全配置缺失时拒绝运动。2026-10-31新增显式网页探索启动接口；这不代表本车已部署运动模板。


## 2026-10-31 网页模式与三挡接口

已加入“自主探索 / 远程接管”、全局Space停车及+/−三挡，沿用SSH、现有探索算法和最终安全链。默认速度为低0.03、中0.06、高0.10 m/s；探索每次从中挡启动。远程模式按WASD自动申请控制权，Space取消启动/自主任务并回到远程等待。

本次真实连接中相机约30Hz、/scan约10Hz、/odom约20Hz，SLAM地图已显示，但TF仍有间歇过期/丢帧。实车适配器当前仍只读，最终watchdog、驱动命令失效和制动距离未验证，未执行实车WASD或自主探索。用户运动授权已获得，不再重复询问；不能用授权替代实际硬件读数。详见[本轮验证](../setup/verification/2026-10-31-console-task-controls.md)。


## 2026-10-31 当前实车会话

本机 http://127.0.0.1:8766 ，更新后Ctrl+F5。远程模式直接按住WASD；自主按钮启动已有算法并恢复中挡；Space在任何面板停车、取消本次任务并回远程等待。+/−调节低0.03、中0.06、高0.10m/s，角速度0.09、0.18、0.30rad/s。自主期间WASD不发布手动速度，点击远程接管后再操作。

本次经用户明确批准使用supervised-live-session-v1，只豁免完整校准和实测制动两项启动限制，保留未校准标记、数据健康、碰撞监控、最终watchdog及驱动软件超时。默认未配置连接仍只读，原三阶段严格校验不变。等待解锁期间只续发零速，非零仍在0.5秒后失效；碰撞监控86400秒设置只延续停车零速。Space独立HTTP请求抢占旧排队指令。未安装开机服务。实际通过范围与失败记录见[本轮验证](../setup/verification/2026-10-31-console-task-controls.md)。


2026-10-31后续核查：自主启动被tf_stale中断，启动等待和停止原因保留已完成本地修复，后端56项通过；上游TF间歇失效尚待进一步定位。用户现要求仅本地、不移动，稳定启动修复未部署，实车自主尚未通过。见[故障与本地修复记录](../setup/verification/2026-10-31-debug-autonomy-tf.md)。


后续经用户明确批准，TF同步与稳定启动修复已SSH部署。归档旧图和完整建图状态后恢复新的实时建图会话，并恢复原相机进程。最终共同负载35/35位姿和相机在线，0次控制链tf_stale，全程remote/hold/disarmed、零输出；源码哈希与本地60项通过版本一致。保持不启动探索、不移动限制，完整实车自主尚未验证。详见[部署与静止验证](../setup/verification/2026-10-31-debug-autonomy-tf.md)。


后续 watchdog_arm_failed：发现速度平滑/碰撞安全指令流中断，已在停车锁定状态恢复自有 Nav2/安全链进程，保留驱动和当前SLAM地图。97次静止采样指令流全部新鲜、全零，五个关键节点active；用户确认远程控制恢复。自主回退仍等待用户前台点击复核，未由agent启动自主或运动。见[安全链恢复记录](../setup/verification/2026-10-31-debug-watchdog-arm.md)。


2026-10-31 最新：空间视图新增双端地图 Reset，先停车、完整备份旧图，再清空车端 SLAM 与网页缓存，完成后等待远程接管；原“重置视图”改为小车居中。静止关键帧去重和扫描/TF 相位队列修复已部署，保持时效/停车门限。真实自主任务仍未由 agent 启动。详见 setup/verification/2026-10-31-debug-map-reset-and-slam.md；历史短测不代替最终持续复核。

最终静止共同负载复核：车端132/132、网页194/194位姿有效，网页最大年龄0.31秒；2000条最终驱动指令全零。Reset已实际连续验证；完整自主任务仍待用户发起，不自动启动。见上述最新故障记录。


2026-10-31 空间视图黑屏本地修复：拖动松手后异步回调读取已清空坐标，导致整页崩溃；已改为提前保存位移并处理拖动取消。新版前端已构建，交互回归6/6、原Reset/控制回归11/11、单元测试13/13；Ctrl+F5刷新使用。全部是拦截接口的本地测试，未连接或部署到车端。详见 setup/verification/2026-10-31-debug-map-interaction-black-screen.md。
