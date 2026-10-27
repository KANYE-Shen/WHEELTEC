# 控制台接口 v1

浏览器只访问本机 127.0.0.1:8766。GET /bootstrap 建立 HttpOnly、SameSite=Strict 会话 cookie；API 必须携带 cookie，POST/WS 额外核对完整同源 Origin 和 localhost Host。SSH 凭据不放进 URL。OpenAPI 路由索引在 /openapi.json；事件数据类型以 frontend/src/protocol.ts 为准。

| 接口 | 请求/响应 |
| --- | --- |
| GET /api/v1/logs | 最近100条工具网关事件；仅固定事件文字，不记录命令、密码或令牌 |
| GET /api/v1/profiles | 名称到非敏感连接配置的映射 |
| POST /api/v1/profiles | 保存白名单字段；忽略 password、adapter_token 等非白名单字段 |
| POST /api/v1/probe | host、port → fingerprint；仅探测，不代表身份已核实 |
| POST /api/v1/connect | profile、临时 password、adapter_token；验证指纹和目标 kind 后建立会话 |
| POST /api/v1/disconnect | 请求停车、关闭 SSH，不停止目标算法服务 |
| GET /api/v1/camera | 新鲜 JPEG；过期/不可用返回 503 |
| WS /api/v1/events | state、offline、ack、error 事件；接收 control 命令 |
| WS /api/v1/terminal | JSON input/resize 请求、二进制 PTY 输出；与手动控制互斥 |
| GET /api/v1/desktop/{path} | 仿真 noVNC 静态资源，经 SSH 转发到指定 localhost 端口 |
| WS /api/v1/desktop/websockify | binary 子协议的只读桌面转发；仅仿真 |

配置字段：name、kind（robot/simulation）、host、port、username、fingerprint（完整 SHA256:...）、key_file（电脑本机路径）、adapter_port（默认8767）、desktop_port（默认6080）。密码/令牌不包含在可保存结构中。目标端适配器只监听 localhost:8767，要求随机 Bearer token；不暴露原始 ROS 网络。

事件包：`{ "type": "state", "data": State }`。State 包含 kind、clock、connection、streams、scan、map、pose、laser_pose、odom、logs、control。streams 含原始 stamp、age、hz、fresh；缺失数据为 null/缺少字段，不生成假数据。地图原点包含 x、y、yaw；栅格 -1 为未知，0–100 为占据概率。雷达无效束保留数组位置并编码为 null。laser_pose 按该次 scan 源时间查询 TF，无法查询则 null；这时切局部雷达查看。

控制请求：

```json
{"type":"control","data":{"action":"claim"}}
{"type":"control","data":{"action":"command","linear":0.0,"angular":0.0}}
{"type":"control","data":{"action":"release"}}
{"type":"control","data":{"action":"stop"}}
```

owner 由网关为每条事件连接生成，不接受客户端指定身份；claim 初始速度为零。command 有效期仅由真实请求更新，读取状态不续租。release 只能释放自己的控制权，stop 为软件停车保持。正速度须 control.mine 与 control.ready 均真；实车须最终 watchdog 已确认解锁。命令不直接进入驱动话题。重连、超时或安全故障后必须重新 claim，不重放旧命令。

终端请求：`{"type":"input","data":"..."}`；调整尺寸：`{"type":"resize","cols":100,"rows":30}`。输出为原始终端字节。该终端是完整 SSH shell，拥有登录账户权限；它不能阻止操作者手动执行 shell 命令。网页安全接口与 shell 权限边界分别看待。

扩展面板：在 main.tsx 导入自己的模块，再调用 `registerPanel({id,title,component})`。组件收到当前 State|null；参见 frontend/src/examples/ClockPanel.tsx。新增 ROS 数据在 target/data.py 做纯数据转换、adapter.py 中订阅，经 state 的新增字段传递。附回归测试，保持旧字段含义，不把仿真真值接入 State、终端自动补全或控制器。

通信失败由 offline/error 明确报告。传输层限定通道读超时及响应大小；日志固定最近400条、视频降采样/压缩，避免无界队列。没有隐式任务恢复、自动重连运动或后台操作者心跳。接口尚无导航目标提交；后续功能需单独定义控制权切换和关卡要求。


日志来源为 ROS `/rosout`、适配器启动事件和网关管理的连接/PTY生命周期事件，最多合并500条；`console.gateway` 使用墙钟时间，ROS日志保留其源时间。SSH命令内容和PTY原始输出不进入聚合日志；第三方Gazebo/RViz详细进程日志仍通过终端/原始日志文件查看。适配器和桌面管理器的启动命令不会由网页隐式执行。

实现所用接口：[FastAPI WebSocket](https://fastapi.tiangolo.com/advanced/websockets/)、[Paramiko](https://www.paramiko.org/)、[xterm.js Terminal](https://xtermjs.org/docs/api/terminal/classes/terminal/)。


实车PTY前置检查：readonly（control.enabled=false）拒绝；配置安全链后，先请求stop，再要求新的watchdog_revision、watchdog_fresh=true、armed=false，且不存在最终驱动输出不独占或watchdog不可用状态。1.5秒未获确认则拒绝。stop响应scope为manual_pipeline或local_lease_only，accepted只表示该作用域内的请求被接收，不是物理制动距离证明。原始ROS状态中的watchdog_revision由适配器接收计数，不由浏览器填写。
