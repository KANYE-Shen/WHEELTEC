# 2026-10-31 空间视图交互导致整页黑屏

用户说明：点击/操作空间视图后整页内容消失，刷新后再次操作复现。随后要求仅本地测试，并准备给小车断电。本轮确认后未调用 SSH、未进行车端部署或运动测试；浏览器测试截获全部 API 请求和 WebSocket 写入，使用本地构造状态。

## 原因与复现

MapView 的 onPointerMove 在 setPan 的延迟 updater 里读取 drag.current![0/1]。松手会把 drag.current 清为 null；React 批处理尚未执行的 updater 因此抛出 Cannot read properties of null (reading '0')，导致组件树卸载，页面只剩背景。即使未抛异常，后续移动修改同一 ref 也可能丢失位移。

本地真实浏览器先验证简单点击正常，再在同一批处理中发出 25 次移动并松手：修前应用标题消失，捕获上述 TypeError，截图为全空背景。该失败和调用栈保留在 outputs/20261031-web-black-screen/before/result.json。

## 最小修复

仅修改 console/frontend/src/MapView.tsx：
- 在处理事件时读取原坐标、计算 dx/dy 并保存当前坐标。
- setPan updater 只使用已捕获的数值，不再读取可变 ref 或事件。
- pointercancel 和 lostpointercapture 清理拖动状态。

没有添加隐藏异常的兜底，没有修改 ROS、安全链、控制协议或地图重置逻辑。现有本地网关直接读取新构建的静态文件，不需要重启网关、重连小车或给小车通电。用户浏览器需 Ctrl+F5 获取新资源。

## 验证

- 修前：简单点击通过，批量拖动松手使整页黑屏，1/2。
- 修后：6/6，包括页面保持挂载、完整 100/-50 像素位移、取消/失去捕获在物理松手前停止拖动，以及反复缩放、居中、图层切换；浏览器错误 0。
- 现有 Reset/箭头居中/WASD/Space 隔离浏览器回归 11/11。
- 现有前端单元测试 13/13，TypeScript 与 Vite build 通过。
- 新构建脚本资源 index-BSbMUdOY.js。没有车端实测结论。

本机证据根目录：C:/Users/30120/OneDrive/文档/ChatGPT/WHEELTEC/outputs/20261031-web-black-screen，before 为失败，after 为修复后，reset-regression 为原有行为回归。可复用浏览器回归在 console/frontend/e2e/map-interactions.mjs。
