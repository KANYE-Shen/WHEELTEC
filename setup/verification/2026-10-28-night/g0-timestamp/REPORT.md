# G0 相机时间戳：离线源码修复准备（2026-10-28）

当前结论：离线工具、固定上游源码候选和算术验证已完成；本车驱动版本/源码、V4L2 时间基准、真实系统时钟与修复后的实车表现均未核验。**G0 未通过；deployment_ready=false。** 本轮没有 SSH、实车网络、驱动安装/启动/重启、ROS 发布或运动。

## 现有证据与原因边界

依据 `setup/verification/2026-10-28-camera-flicker/source-stamps.json`（未改原数据）：raw 21 条中 3 次倒退、10 条未来时间，年龄范围 -0.807429481～0.202624447 秒；compressed 22 条中 3 次倒退、10 条未来时间，范围 -0.813372164～0.192876335 秒。匹配帧的 raw/compressed stamp 相同。这支持排查共同的采集时间戳来源；不证明实车一定使用此处固定的 usb_cam 版本。

固定上游依据：

- [PR 267](https://github.com/ros-drivers/usb_cam/pull/267)：merge `c743cb16c5080c69a53472b058b7255bef8c5a13`，父版本 `e030e2d4824d2abf9c14fab644b81dd0d6e18447`。旧 mmap 公式将 `usec/1000000` 四舍五入加入秒，又把原微秒放入纳秒，造成半秒处跳至下一秒、真实跨秒处倒退。PR 改成总整数微秒相加后再拆 sec/nsec，并统一 mmap/userptr 路径。
- PR267 本身仍有 `epoch_time.tv_usec / 1000.0` 单位错误；不能整包称为正确修复。这里保留其实际编译失败。
- [后续官方修正 ee0a2f7](https://github.com/ros-drivers/usb_cam/commit/ee0a2f76d8ccf5a4e1e5e88127689d30ba36f243)（2024-06-16）将上述表达式改为 `epoch_time.tv_usec`。本候选仅组合 PR267 的三个生产文件改动及这一处单位修正。没有升级整个驱动。0.7.0 虽含 PR267，源码仍有上述单位错误，因此不能以版本号作充分条件。

`fixture-manifest.json` 记录上述 SHA 与三个文件的精确 SHA256；工具内固定 manifest 本身的 SHA。`fixtures/legacy`、`fixtures/pr267`、`fixtures/candidate` 保留源码及许可证；编译支持头来自同一 PR267 固定版本。三个文件精确匹配不等于整个源码树、安装包或当前运行二进制匹配。

## 实际交付

- `robot/timestamp_source_audit.py`：无网络、ROS 或 subprocess；默认只读计算三个时间戳源码文件哈希。未知、缺失、混合、vendor 改动一律 state=unknown。只支持固定 parent 和 PR267 的离线准备，不承诺支持车上版本或 0.6.0。
- 显式 `--prepare NEW_DIR` 才写入新目录：三个候选源码文件（局部审核材料，不是完整可构建驱动）、`candidate.patch`、`review.json`。拒绝覆盖已有目录、源目录内/外的包含关系、未知源码和已为候选状态的源码；从不原位打补丁。
- `robot/test_timestamp_source_audit.py`：12 项，包括整数微秒、半秒与跨秒边界、规范 nsec、未知/混合源码拒绝、源保持不变、候选篡改拒绝及覆盖保护。
- `robot/test_timestamp_upstream.cpp`、`robot/verify_timestamp_upstream.py`：实际 include 固定的官方头文件，用注入的确定性 clock 值执行算术；旧帧公式因位于依赖完整驱动的 read_frame 中，使用其原表达式复现（标明 LEGACY）。不打开摄像头、不改系统时间、不建立 ROS/Gazebo 域。
- `review-bundle/`：从真实运行工具生成的可审核最小补丁，针对精确 parent；本车源码未知时绝对不可直接套用。

## 已执行命令与结果

在 Windows PowerShell，从仓库根目录执行：

```powershell
& D:\Python\python.exe -m unittest discover -s robot -p test_timestamp_source_audit.py -v
& D:\Python\python.exe robot\verify_timestamp_upstream.py
& D:\Python\python.exe robot\timestamp_source_audit.py setup\verification\2026-10-28-night\g0-timestamp\fixtures\legacy
# 需要一个此前不存在的输出目录：
& D:\Python\python.exe robot\timestamp_source_audit.py setup\verification\2026-10-28-night\g0-timestamp\fixtures\legacy --prepare setup\verification\2026-10-28-night\g0-timestamp\review-bundle-NEW
```

Python：初次缺失实现为 12 errors（保留 tests-red.txt），改用明确缺失实现断言后 12/12 fail（tests-red-assertions.txt），实现后 12/12 pass（tests-green.txt）。

WSL `WHEELTEC-Ubuntu-22.04` g++ 11.4.0，`-std=c++17 -Wall -Wextra -Werror`：三个状态全部编译成功；legacy 5 检查中 4 失败；PR267 8 检查中 1 失败（epoch 微秒）；candidate 8/8 通过。详见 `upstream-cpp-results.json`。编译产物只在结果所列 `/tmp/wheeltec-timestamp-*` 中，未更改仿真目录、域或地图。

独立临时源码副本运行 `git -c core.autocrlf=false apply --check candidate.patch` 及 `git ... apply candidate.patch`，两者返回 0，应用后的三个文件 SHA256 全部等于候选；见 `patch-apply-check.json`。首次 Windows 默认 autocrlf 虽 apply 返回 0，但字节哈希不等，保留 `patch-apply-check-failed-crlf.json`，不算通过。GitHub API 限流、diff 下载 EOF、缓存移动只读权限失败和修复记录见 `download-failures.txt`。下载缓存保存在 `download-cache-location.txt` 指定的 Windows 临时目录，不加入仓库。

## 下次 G0 只读补采（本轮没有执行）

须由用户重新连接实车并明确允许 G0 只读核查；保持现有运动准入限制。先留存新目录/新文件，不覆盖旧采样。

1. 核实主机指纹、硬件、实际运行节点和可执行文件路径；只读记录 `ros2 node info`、进程 `/proc/<PID>/exe` 和 `/proc/<PID>/cmdline`、启动文件、现有日志。不要启动不存在的节点或猜服务名。
2. 在实际 ROS 环境只读记录 `ros2 pkg prefix usb_cam`、对应 package.xml、dpkg-query 包名/版本（若不是系统包则记录 source overlay、git SHA/工作树差异、构建日志）、三个时间戳源码文件和运行二进制 SHA256。仅安装头文件并不足以还原 `src/usb_cam.cpp`；没有完整源码就保持 unknown，不准备车端 patch。
3. 在同一车端时基采集 UTC/system realtime、monotonic、`timedatectl status`、现有时间同步状态、`/clock` 是否有发布者和各传感节点 `use_sim_time`。车端先前 clock≈2000 年须独立定位；不自动设时或启停同步服务。系统时钟在启动后改变会使一次性 epoch shift 失效。
4. 读取相机实际驱动版本、已配置 I/O 方法（read/mmap/userptr）、V4L2 buffer timestamp 的时基标记/既有日志，确认输入确为 monotonic，不能给 realtime buffer 再叠 epoch shift。若现有日志不能提供 flags，先提出最小可审核采样方案，不能未经授权重启/插桩驱动。
5. 同时记录 raw、compressed、camera_info 和 scan/odom/TF 的原始 stamp、车端接收时刻、实际接收/新测量频率、年龄与倒退；采样至少 30 秒、跨越多个整秒。既有只读采样脚本/rosbag 记录只采现存话题，保持 raw 与压缩帧对齐；不得改 stamp、按年龄减一秒或用重发布隐藏故障。
6. 任一倒退、未来 stamp 超出事先约定容差、时钟跳变、TF 在测量时间不可用、源码/二进制不匹配都停止准入；保留证据，继续只读调查。安装候选和重新启动相机是独立维护动作，须先审查与批准，不包含于 G0 只读采样授权。

## 回滚与未验证项

本轮没有修改安装驱动，因此无需实车回滚；可直接不用 review bundle。失败结果、原始采样与三个源码状态保持不变。

未来若批准维护：先备份原 package/deb 或原构建安装树、可执行文件与库、source SHA/dirty diff、参数/launch、环境和 overlay 选择及全部哈希；在隔离 overlay 编译，只替换明确的相机驱动版本与时间戳改动，不能盲升依赖。回滚按已核实的原启动方式恢复原安装树/overlay 和原参数，核对原哈希；驱动停止/重启仅在明确维护授权和停车确认后进行。回滚后同样补采，不把恢复原版本当成时间戳健康通过。

未验证：实际 usb_cam 版本/源码/二进制；本候选与 vendor 驱动的兼容性；完整 ROS 驱动构建、链接与相机 I/O 各路径运行；真实 buffer 时基；车端时间同步/clock≈2000 年根因；真实 frame latency、raw/compressed/CameraInfo 一致性、TF 时效；实车修复后表现。整数算术无法消除成对 clock 读取延迟、系统时钟跳变或设备自身错时。候选8/8不代表实车8/8，G0–G5仍未通过。
