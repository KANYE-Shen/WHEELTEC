> 2026-10-30：网页已移除 SSH 连接表单；以下连接/配置接口继续供本机后台或 agent 使用。主机指纹校验、适配器令牌及会话/Origin 保护未删除，不允许由不可信页面代为连接。

# 控制台接口 v1

浏览器只访问本机 127.0.0.1:8766。GET /bootstrap 建立 HttpOnly、SameSite=Strict 会话 cookie；API 必须携带 cookie，POST/WS 额外核对完整同源 Origin 和 localhost Host。SSH 凭据不放进 URL。OpenAPI 路由索引在 /openapi.json；事件数据类型以 frontend/src/protocol.ts 为准。

| 接口 | 请求/响应 |
| --- | --- |
| GET /api/v1/logs | 最近100条工具网关事件；仅固定事件文字，不记录命令、密码或令牌 |
| GET /api/v1/profiles | 名称到非敏感连接配置的映射 |
| POST /api/v1/profiles | 保存白名单字段；忽略 password、adapter_token 等非白名单字段 |
| POST /api/v1/probe | host、port → fingerprint；仅探测，不代表身份已核实 |
| POST /api/v1/connect | profile、临时 password、adapter_token；验证指纹和目标 kind 后建立会话 |
| POST /api/v1/task | 固定action：explore / remote / stop，经SSH转发目标端/task；explore执行预检后异步启动已有算法，remote/stop抢占启动并停车 |
| POST /api/v1/disconnect | 请求停车、关闭 SSH，不停止目标算法服务 |
| GET /api/v1/camera | 单调接收年龄≤1秒的 JPEG；接收中断/不可用返回503；不保证源采集时间戳合格 |
| WS /api/v1/events | state、offline、ack、error 事件；接收 control 命令 |
| WS /api/v1/terminal | JSON input/resize 请求、二进制 PTY 输出；与手动控制互斥 |
| GET /api/v1/desktop/{path} | 仿真 noVNC 静态资源，经 SSH 转发到指定 localhost 端口 |
| WS /api/v1/desktop/websockify | binary 子协议的只读桌面转发；仅仿真 |

配置字段：name、kind（robot/simulation）、host、port、username、fingerprint（完整 SHA256:...）、key_file（电脑本机路径）、adapter_port（默认8767）、desktop_port（默认6080）。密码/令牌不包含在可保存结构中。目标端适配器只监听 localhost:8767，要求随机 Bearer token；不暴露原始 ROS 网络。

事件包：`{ "type": "state", "data": State }`。State 包含 kind、clock、connection、streams、scan、map、pose、laser_pose、odom、logs、control、task。task.mode为remote/starting/autonomous，task.error为启动/退出错误。control.epoch为任务代次，control.gear为0/1/2，selection_mode为车端速度源确认。streams 含原始 stamp、age、hz、fresh；缺失数据为 null/缺少字段，不生成假数据。地图原点包含 x、y、yaw；栅格 -1 为未知，0–100 为占据概率。雷达无效束保留数组位置并编码为 null。laser_pose 按该次 scan 源时间查询 TF，无法查询则 null；这时切局部雷达查看。

控制请求：

```json
{"type":"control","data":{"action":"claim","epoch":0}}
{"type":"control","data":{"action":"command","epoch":0,"linear":0.0,"angular":0.0}}
{"type":"control","data":{"action":"release"}}
{"type":"control","data":{"action":"stop"}}
{"type":"control","data":{"action":"gear","delta":1}}
{"type":"control","data":{"action":"heartbeat"}}
```

owner 由网关为每条事件连接生成，不接受客户端指定身份；claim 初始速度为零。command 有效期仅由真实请求更新，读取状态不续租。release 只能释放自己的控制权，stop 为软件停车保持。正速度须 control.mine 与 control.ready 均真；实车须最终 watchdog 已确认解锁。命令不直接进入驱动话题。重连、超时或安全故障后必须重新 claim，不重放旧命令。UI在远程模式首次按WASD自动claim，仅转交仍按住的当前按键；启动/自主模式不发送手动速度。gear.delta仅允许整数+1/-1，挡位限制0–2；最终速度源选择器同时限制手动和自主速度。heartbeat仅来自可见、聚焦、数据在线的实车页面，不解锁或恢复停车状态。

终端请求：`{"type":"input","data":"..."}`；调整尺寸：`{"type":"resize","cols":100,"rows":30}`。输出为原始终端字节。该终端是完整 SSH shell，拥有登录账户权限；它不能阻止操作者手动执行 shell 命令。网页安全接口与 shell 权限边界分别看待。

扩展面板：在 main.tsx 导入自己的模块，再调用 `registerPanel({id,title,component})`。组件收到当前 State|null；参见 frontend/src/examples/ClockPanel.tsx。新增 ROS 数据在 target/data.py 做纯数据转换、adapter.py 中订阅，经 state 的新增字段传递。附回归测试，保持旧字段含义，不把仿真真值接入 State、终端自动补全或控制器。

通信失败由 offline/error 明确报告。传输层限定通道读超时及响应大小；日志固定最近400条、视频降采样/压缩，避免无界队列。没有隐式任务恢复、自动重连运动或后台操作者心跳。接口尚无任意导航目标提交。探索按钮调用现有wheeltec_explore，要求已有Nav2、地图、TF和安全链；不启动底盘驱动或代填硬件校准。


日志来源为 ROS `/rosout`、适配器启动事件和网关管理的连接/PTY生命周期事件，最多合并500条；`console.gateway` 使用墙钟时间，ROS日志保留其源时间。SSH命令内容和PTY原始输出不进入聚合日志；第三方Gazebo/RViz详细进程日志仍通过终端/原始日志文件查看。桌面管理器的启动命令不会由网页隐式执行；探索子进程仅由明确的explore请求启动，停止时仅管理本次拥有的子进程。

实现所用接口：[FastAPI WebSocket](https://fastapi.tiangolo.com/advanced/websockets/)、[Paramiko](https://www.paramiko.org/)、[xterm.js Terminal](https://xtermjs.org/docs/api/terminal/classes/terminal/)。


实车PTY前置检查：readonly（control.enabled=false）拒绝；配置安全链后，先请求stop，再要求新的watchdog_revision、watchdog_fresh=true、armed=false，且不存在最终驱动输出不独占或watchdog不可用状态。1.5秒未获确认则拒绝。stop响应scope为manual_pipeline或local_lease_only，accepted只表示该作用域内的请求被接收，不是物理制动距离证明。原始ROS状态中的watchdog_revision由适配器接收计数，不由浏览器填写。


相机streams额外提供receiving（单调接收年龄≤1秒）和receive_age（秒）。fresh、stamp、age保留原始采集时间校验含义；receiving=true且fresh=false仅可显示并告警，不作为有效测量或运动安全依据。其他传感器不改用接收时间替代源时间。旧适配器缺少receiving时前端回退到fresh。

相机另提供receive_hz：按采集stamp去重raw/compressed后，以单调接收间隔统计的近期接收频率；不是源时钟频率或硬件标称帧率。原hz保留兼容。新前端优先显示receive_hz，旧适配器缺字段时回退hz；旧源时间戳异常仍需修复。


实车claim/command必须携带最新State.control.epoch（示例0不能硬编码）。Space/远程切换增加代次，旧请求返回stale_control_epoch；缺字段提示Ctrl+F5。epoch不替代owner/lease鉴权。等待解锁允许持有者command(0,0)续租，非零仍须manual源与最终watchdog确认。网页每200ms发送当前指令；手动租约期间由指令更新心跳。Space并行WS stop与独立HTTP task stop，旧claim/command不能恢复运动。


本地待部署版：explore先执行静态配置预检，再由异步线程在hold/disarmed状态等待动态健康连续0.5秒（最多5秒），通过后切源/解锁。失败原因保留在task.error。安全中断也写入console.task日志，不以空error掩盖；显式stop/remote仍取消启动和任务。此版本尚未实车验证。



POST /api/v1/task 新增 {"action":"reset_map"}，沿用 cookie/Origin、SSH 指纹及适配器令牌校验。仅配置 --mapping-runtime 的实车目标可用；维护终端打开时拒绝。立即停车并返回异步状态，State.map_reset={busy,error,sequence} 表示进度与失败；busy 时拒绝手动 claim/command 和探索启动。仅归档并重启明确记录的自有 mapper；备份失败不清图，完成不自动恢复运动。备份在车端 owned-processes.json 同目录的 map-resets/<时间>/。新图去除全部旧图恢复参数并清理导航代价图。重置视图仅改变画布中心，不调用 ROS。
