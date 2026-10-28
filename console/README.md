# 网页调试与控制终端

电脑本地打开 `http://127.0.0.1:8766`，通过 SSH 连接 WSL 或小车。电脑无需安装 ROS。地图、激光、视频和日志来自目标端真实 ROS 话题；未连接时显示无数据，不生成演示结果。

目前可用：SSH 指纹校验、密码/私钥/SSH agent 认证、真实 PTY 终端、地图与雷达图层、局部雷达、JPEG 视频、ROS 日志筛选/暂停/导出、WASD 控制接口、控制权互斥及停车保持。实车连接、部署、运动、板上负载均未验证。完整结果和当前仿真端点回波问题见[验证报告](../setup/verification/2026-10-27-console-results.md)。

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

首次启动生成权限 0600 的随机令牌。用本机安全方式读取令牌，填入网页“适配器访问令牌”，不提交、不截图、不放入 URL。去掉 `--enable-simulation-control` 即为只读；仿真运动仅允许命名 WSL 发行版的 x86 主机、localhost-only ROS。

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

此终端保留运行，Ctrl+C 关闭；不需要启用系统 SSH 服务。网页填 host=`127.0.0.1`、port=`2222`、username=`wheeltec`、私钥路径为 Windows 私钥文件路径。适配器端口默认 8767。连接前在目标端执行 `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256`，与网页探测得到的 SHA256 指纹逐字核对。探测按钮不会证明主机身份；已知主机密钥发生变化时拒绝连接。

“保存非敏感配置”只保存名称、主机、端口、用户名、指纹及私钥路径，位于电脑 `~/.wheeltec-console/profiles.json`。密码、私钥内容和适配器令牌不落盘。页面刷新后重新填写必要凭据。

## 页面操作

- **空间视图**：地图、雷达和位姿叠加；滚轮缩放、拖动平移、重置恢复视图。雷达按扫描时间查询 TF，无法对齐时不叠加；可切“局部雷达”查看传感器坐标中的原始点。
- **数据状态**：区分 SSH/适配器通路与话题状态；显示源时间、频率、数据年龄。相机或 TF 过期时隐藏对应实时画面/位置；地图保留最后收到的内容并标记更新状态。
- **手动控制**：先取得控制权，再按住 W/S 前后、A/D 转向，可组合；松键发零。空格停车并释放控制权。切后台、窗口失焦、输入框获焦、维护终端启用或断开连接均停车保持。重新连接、重新取得控制权不会恢复旧按键，必须重新按键。
- **维护终端**：真实 SSH PTY，可运行交互命令、调整窗口尺寸、Ctrl+C 和退出 shell。启用前要求目标端确认停车，期间禁止网页遥控。终端内 W/A/S/D、空格用于输入命令；使用页面软件停车按钮或现场硬件急停停车。Shell 是完整账户权限，不能当作受限控制接口。
- **日志**：汇集 `/rosout` 最近400条、适配器事件和网关最近100条连接/PTY生命周期事件；可筛选节点/文字、暂停滚动及导出当前列表为 JSONL。终端命令输出留在终端；适配器/systemd 进程日志可通过 `journalctl -u wheeltec-console` 查看。

速度显示分别为目标、适配器输出和原始里程计反馈。带噪仿真停车后里程计也可有非零读数，不能据此伪造零反馈。初始接口上限 0.1 m/s、0.3 rad/s，命令/操作者有效期 0.5 s；这些是保守模板，不是本车测得的制动性能。适配器的 0.55 m 全周近点停车保护为 assumed 模板，不能作为已测安全距离。实车最终限制取已核查的安全配置及看门狗。

## 可选 Gazebo / RViz 嵌入

Gazebo/RViz 通过只读 noVNC 桌面显示，原生程序和项目 Ogre 配置不变。只在仿真主机安装：

```bash
sudo apt install xvfb x11vnc novnc websockify
python3 -m console.target.desktop --private-display --display :88
```

之后在**新仿真终端**给原启动命令增加 `DISPLAY=:88 QT_QPA_PLATFORM=xcb`，并取消该终端的 WAYLAND_DISPLAY，启动 Gazebo/RViz。网页的 noVNC 端口填 6080，点击“仿真桌面”。可以并排移动原生窗口；私有 X 显示与现有 WSLg 桌面独立。已有 X 显示可省略 `--private-display` 并指定实际显示号。桌面入口仅仿真可用，VNC 服务必须保留 `-localhost -viewonly`。安装 openssh-server 可能自动启动系统服务；只使用本机专用SSH时应先停止并禁用默认服务，避免意外开放22端口。

相机链路验证使用独立 Gazebo 观察相机，配置见 tests/observer-camera.sdf，不代表实车相机位置或规格。复现夹具见下节。

## 实车连接边界

按[准入关卡](../robot/准入关卡.md)先取得 G0 书面确认，再由人部署并启动默认只读适配器。沿用实车 ROS 域；不设置仿真时钟，不启动 Gazebo，不修改驱动。使用 `--kind robot` 且不传 robot-config 时不创建速度发布器、心跳发布器或解锁客户端。

`robot/systemd/wheeltec-console.service` 和 `robot/start_console.sh` 是未安装的服务模板：确认部署目录、账户、话题、ROS 域及 0600 环境文件后由人按关卡配置。默认仅需 `WHEELTEC_CONSOLE_TOKEN_FILE`；配置 `WHEELTEC_CONSOLE_ROBOT_CONFIG` 与明确 `WHEELTEC_CONSOLE_GATE` 才进入运动预检。不要直接 enable/start 未配置模板。

手动安全链独立入口为 `robot/launch/manual.launch.py`，仅 G1/G2/G3，在对应书面确认后由操作者启动。它包含 velocity_smoother、collision_monitor、最终 watchdog，不启动自主速度发布器；G3 的 SLAM 另外按关卡启动。真实运动学、尺寸、驱动话题/失联超时及审批记录必须通过既有 preflight。当前仅支持实测确认的差速底盘；其他运动学保持只读。

手动速度链：网页 → SSH → 适配器控制权/时限保护 → `/safety/nav_cmd_vel` → smoother → collision_monitor → watchdog → 核实后的驱动话题。最终 watchdog 解锁有异步确认，丢失后必须重新人工取得控制权；发现其他速度发布器或驱动输出不独占时拒绝手动控制。关闭网页/SSH 不结束车端安全服务，心跳过期后停车保持。硬件急停、看门狗及实际停止距离仍须现场验证。

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


安全审查补充：实车只读模式不创建底盘停止能力，不能把“释放网页租约”当作底盘停车确认。只读时软件停车按钮禁用，空格不发送底盘请求；维护PTY拒绝开启。配置并通过对应关卡的安全链后，PTY必须等待最终watchdog在停止请求之后新的、未解锁的状态确认且输出仍独占；缺失确认则保持关闭。完整Shell仍是账户权限。此限制来自已批准计划的“维护终端启用前先停车”，不能用未验证的停止能力绕过；实车仍未连接。补强增加了先失败后通过的HTTP/WS回归，后端共25/25。最近完整真实仿真为补强前9/12；补强后完成单元回归与构建，真实watchdog确认分支未经实车验证，不把旧仿真结果称为该分支的实测证明。


## 2026-10-28 实车视频显示

现有实车只读连接按Ctrl+F5刷新。画面单调接收年龄超过1秒停止显示；源时间戳独立校验，异常明确告警，不能用于定位或安全判断。先解码新帧再替换，慢请求不重叠；断流、断网与重连需真实新数据才恢复。相机专项7/7，不替代完整仿真验收，见[报告](../setup/verification/2026-10-28-camera-flicker/README.md)。
