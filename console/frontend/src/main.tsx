import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import { api, socket } from "./api";
import type { State, Log } from "./protocol";
import { MapView } from "./MapView";
import { TerminalView } from "./TerminalView";
import { velocity, editable, controlStatus } from "./control";
import { getPanels } from "./panels";
import { streamReadout } from "./streamReadout";
import "./style.css";
function App() {
  const [state, setState] = useState<State | null>(null),
    [connected, setConnected] = useState(false),
    [adapterRecovery, setAdapterRecovery] = useState(false),
    [preparation, setPreparation] = useState(""),
    [adapterEvidence, setAdapterEvidence] = useState<{log_tail?:string;missing_services?:string[];reason?:string}|null>(null),
    [error, setError] = useState(""),
    [terminal, setTerminal] = useState(false),
    [desktop, setDesktop] = useState(false),
    [filter, setFilter] = useState(""),
    [paused, setPaused] = useState(false),
    [logs, setLogs] = useState<Log[]>([]),
    [now, setNow] = useState(0),
    [lastReceive, setLastReceive] = useState(0),
    [busy, setBusy] = useState(false),
    [cameraUrl, setCameraUrl] = useState(""),
    [cameraFailed, setCameraFailed] = useState(false),
    [cameraStampWarning, setCameraStampWarning] = useState(false);
  const pendingManual = useRef<{ keys: Set<string>; until: number; sent: boolean; waitingRemote?: boolean } | null>(null);
  const passwordInput = useRef<HTMLInputElement>(null);
  const logBox = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!paused && logBox.current)
      logBox.current.scrollTop = logBox.current.scrollHeight;
  }, [logs, paused]);
  const ws = useRef<WebSocket | null>(null),
    keys = useRef(new Set<string>()),
    current = useRef<State | null>(null),
    lastGood = useRef(0),
    pause = useRef(false),
    frozenLogs = useRef<Log[]>([]);
  current.current = state;
  pause.current = paused;
  const send = (action: string, extra: object = {}) => {
    if (ws.current?.readyState === 1)
      ws.current.send(
        JSON.stringify({ type: "control", data: { action, ...extra, ...(["claim", "command"].includes(action) ? { epoch: current.current?.control.epoch ?? 0 } : {}) } }),
      );
  };
  const claimPending = () => {
    const pending = pendingManual.current, s = current.current;
    if (!pending || pending.sent || pending.waitingRemote || !pending.keys.size ||
        Date.now() > pending.until || Date.now()-lastGood.current >= 800 ||
        !s?.control.enabled || (s.task?.mode && s.task.mode !== "remote")) return;
    if (s.kind === "robot" &&
        (s.control.selection_mode !== "hold" || s.control.watchdog?.armed !== false)) return;
    pending.sent = true;
    send("claim");
  };
  const stop = () => {
    keys.current.clear();
    pendingManual.current = null;
    send("stop");
    api("task", { action: "stop" }).catch((e) => setError(e.message));
  };
  useEffect(() => {
    let active = true,
      retry: ReturnType<typeof setTimeout>;
    const open = () => {
      if (!active) return;
      const s = socket("events");
      ws.current = s;
      s.onmessage = (e) => {
        const m = JSON.parse(e.data);
        if (m.type === "state") {
          current.current = m.data;
          if (pendingManual.current) {
            if (Date.now() > pendingManual.current.until) {
              keys.current.clear(); pendingManual.current = null;
            } else if (!pendingManual.current.waitingRemote &&
                       (!m.data.task?.mode || m.data.task.mode === "remote") &&
                       m.data.control.mine && m.data.control.ready) {
              keys.current = new Set(pendingManual.current.keys);
              pendingManual.current = null;
              const [linear, angular] = velocity(keys.current, m.data.control.gear ?? 1, m.data.control.limits);
              send("command", { linear, angular });
            } else claimPending();
          } else if (m.data.task?.mode === "autonomous" || m.data.task?.mode === "starting" || !m.data.control.mine || !m.data.control.ready) keys.current.clear();
          if (m.data.streams.camera?.receiving && !m.data.streams.camera.fresh)
            setCameraStampWarning(true);
          setState(m.data);
          setConnected(true);
          setAdapterRecovery(false);
          setPreparation("");
          setLastReceive(Date.now());
          lastGood.current = Date.now();
          if (!pause.current) {
            setLogs(m.data.logs);
            frozenLogs.current = m.data.logs;
          }
        } else if (m.type === "offline") {
          if (!pause.current && m.data.logs) setLogs(m.data.logs);
          setConnected(false);
          setAdapterRecovery(Boolean(m.data.adapter_recovery));
          setPreparation(m.data.preparation || "");
          if (!m.data.adapter_recovery) setAdapterEvidence(null);
          keys.current.clear(); pendingManual.current = null;
        } else if (m.type === "error") {
          if (m.data.reason !== "stale_control_epoch") setError(m.data.reason);
          keys.current.clear();
          if (m.data.reason === "stale_control_epoch" && pendingManual.current && Date.now() <= pendingManual.current.until)
            pendingManual.current.sent = false;
          else pendingManual.current = null;
        }
      };
      s.onclose = () => {
        setConnected(false);
        setAdapterRecovery(false);
        setPreparation("");
        keys.current.clear(); pendingManual.current = null;
        retry = setTimeout(open, 1500);
      };
    };
    fetch("/bootstrap").then(open).catch((e) => setError(e.message));
    const timer = setInterval(() => setNow(Date.now()), 200);
    return () => {
      active = false;
      clearInterval(timer);
      clearTimeout(retry);
      ws.current?.close();
    };
  }, []);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    const poll = async () => {
      let url = "";
      try {
        const camera = current.current?.streams.camera;
        if ((camera?.receiving ?? camera?.fresh) &&
            Date.now() - lastGood.current <= 1000) {
          const r = await fetch("/api/v1/camera", { signal: controller.signal });
          if (!r.ok) throw Error();
          url = URL.createObjectURL(await r.blob());
          const image = new Image();
          image.src = url;
          await image.decode();
          if (active) {
            setCameraUrl(url);
            setCameraFailed(false);
            url = ""; // The rendered frame owns this URL until React replaces it.
          }
        }
      } catch {
        if (active) setCameraFailed(true);
      } finally {
        if (url) URL.revokeObjectURL(url);
        if (active) timer = setTimeout(poll, 220);
      }
    };
    timer = setTimeout(poll, 220);
    return () => {
      active = false;
      clearTimeout(timer);
      controller.abort();
    };
  }, []);
  useEffect(() => {
    // Cleanup runs after the replacement has committed, never during its fetch/decode.
    return () => { if (cameraUrl) URL.revokeObjectURL(cameraUrl); };
  }, [cameraUrl]);
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      // Space is global, including input fields and the maintenance terminal.
      if (k === " " || e.code === "Space") {
        e.preventDefault(); e.stopImmediatePropagation(); stop(); return;
      }
      const target = e.target as HTMLElement;
      if (editable(target.tagName, target.isContentEditable) || terminal || e.repeat) return;
      if (!"wasd".includes(k) || k.length !== 1 || !current.current?.control.enabled) return;
      if (current.current.map_reset?.busy || Date.now()-lastGood.current >= 800) return;
      e.preventDefault();
      const autonomous = current.current.task?.mode === "autonomous" || current.current.task?.mode === "starting";
      if (autonomous) {
        if (!pendingManual.current) {
          const pending = { keys: new Set<string>(), until: Date.now()+3000, sent: false, waitingRemote: true };
          pendingManual.current = pending;
          // The existing task endpoint cancels navigation and parks first. Never
          // claim or publish motion until its response AND fresh hold/disarm state.
          api("task", { action: "remote" }).then(() => {
            if (pendingManual.current === pending) {
              pending.waitingRemote = false; claimPending();
            }
          }).catch((e) => {
            if (pendingManual.current === pending) pendingManual.current = null;
            setError(e.message);
          });
        }
        pendingManual.current.keys.add(k); return;
      }
      if (!current.current.control.mine || !current.current.control.ready) {
        if (!pendingManual.current)
          pendingManual.current = { keys: new Set(), until: Date.now()+3000, sent: false };
        pendingManual.current.keys.add(k); claimPending(); return;
      }
      keys.current.add(k);
      const [linear, angular] = velocity(keys.current, current.current.control.gear ?? 1, current.current.control.limits);
      send("command", { linear, angular });
    };
    const up = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      pendingManual.current?.keys.delete(k);
      if (pendingManual.current && !pendingManual.current.keys.size) pendingManual.current = null;
      if (keys.current.delete(k) && current.current?.control.mine && current.current.control.ready) {
        const [linear, angular] = velocity(keys.current, current.current.control.gear ?? 1, current.current.control.limits);
        send("command", { linear, angular });
      }
    };
    const autonomous = () => current.current?.task?.mode === "autonomous" || current.current?.task?.mode === "starting";
    const blur = () => {
      if (!autonomous() || pendingManual.current || current.current?.control.mine) stop();
    };
    const pagehide = () => stop();
    const hidden = () => {
      if (document.hidden) stop();
    };
    const focus = (e: FocusEvent) => {
      const el = e.target as HTMLElement;
      if ((el === passwordInput.current || el.closest('.adapter-recovery')) && !current.current?.control.mine && !pendingManual.current) return;
      if (editable(el.tagName, el.isContentEditable) && (!autonomous() || pendingManual.current)) stop();
    };
    window.addEventListener("keydown", down, true);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", blur);
    document.addEventListener("visibilitychange", hidden);
    document.addEventListener("focusin", focus);
    window.addEventListener("pagehide", pagehide);
    const timer = setInterval(() => {
      // Only a live, visible operator page supplies the robot watchdog heartbeat.
      // This does not renew a manual lease or arm/resume a held watchdog.
      if (!current.current?.control.mine && current.current?.kind === 'robot' &&
          current.current.control.enabled &&
          !current.current.maintenance && (document.hasFocus() || autonomous()) &&
          !document.hidden && !terminal && Date.now() - lastGood.current < 800)
        send('heartbeat');
      if (
        current.current?.control.mine &&
        document.hasFocus() &&
        !document.hidden &&
        !terminal &&
        Date.now() - lastGood.current < 800
      ) {
        const [linear, angular] = current.current.control.ready
          ? velocity(keys.current, current.current.control.gear ?? 1, current.current.control.limits)
          : [0, 0];
        send("command", { linear, angular });
      }
    }, 200);
    return () => {
      clearInterval(timer);
      window.removeEventListener("keydown", down, true);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", blur);
      document.removeEventListener("visibilitychange", hidden);
      document.removeEventListener("focusin", focus);
      window.removeEventListener("pagehide", pagehide);
    };
  }, [terminal]);
  const run = async (fn: () => Promise<unknown>) => {
    setError("");
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const healthy = connected && now - lastReceive < 1000;
  const preparationLabel = ({ssh:"正在认证 SSH",checking:"正在核对原有配置与进程",clock:"正在校准小车时间",services:"正在按停车顺序准备原有服务"} as Record<string,string>)[preparation] || "正在准备连接";
  const list = logs.filter((l) =>
    `${l.name} ${l.message}`.toLowerCase().includes(filter.toLowerCase()),
  );
  function exportLogs() {
    const url = URL.createObjectURL(
      new Blob([list.map((l) => JSON.stringify(l)).join("\n")], {
        type: "application/x-ndjson",
      }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download =
      "wheeltec-logs-" +
      new Date().toISOString().replaceAll(":", "-") +
      ".jsonl";
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <>
      <header>
        <div className="brand">
          <span className="brand-icon">W</span>
          <div>
            <strong>WHEELTEC</strong>
            <small>ROBOT OPERATIONS CONSOLE</small>
          </div>
        </div>
        <div className="connection">
          <span className={`dot ${healthy ? "live" : ""}`} />
          <span>{healthy ? "数据通道在线" : "未连接 / 数据通道离线"}</span>
          <span className={`badge ${state?.kind === "robot" ? "real" : ""}`}>
            {!healthy ? "未连接" : state?.kind === "robot" ? "实车" : "仿真"}
          </span>
        </div>
        <button
          disabled={busy}
          onClick={() =>
            run(async () => {
              if (connected) stop();
              setTerminal(false);
              await api("disconnect", {});
            })
          }
        >
          断开连接
        </button>
      </header>
      <div className="workspace">
        <aside>
          <div className="section-label">工作空间</div>
          <button className="nav active">◫　实时监看</button>
          <button
            className="nav"
            disabled={!connected}
            onClick={() => {
              stop();
              setTerminal(true);
            }}
          >
            ⌘　SSH 终端
          </button>
          <button
            className="nav"
            disabled={!connected || state?.kind !== "simulation"}
            onClick={() => {
              stop();
              setDesktop(!desktop);
            }}
          >
            ▣　仿真桌面
          </button>
          <div className="sidebar-bottom">
            <span className="dot" /> API v1{" "}
            <p>
              算法运行在目标端
              <br />
              SSH 仅用于数据与维护
            </p>
          </div>
        </aside>
        <main>
          <div className="page-title">
            <div>
              <div className="eyebrow">LIVE WORKSPACE</div>
              <h1>运行监看与调试</h1>
              <p>
                {healthy
                  ? (state?.connection?.name || "当前目标") +
                    " · " +
                    (state?.connection?.host || "")
                  : adapterRecovery ? "SSH 已认证 · 车端适配器未就绪" : "连接小车热点后，输入 SSH 密码连接"}
              </p>
            </div>
            <button
              className="stop"
              title="停止自主任务并切回远程接管等待"
              onClick={stop}
              aria-label="软件停车"
            >
              ■ 软件停车 <kbd>SPACE</kbd>
            </button>
          </div>
          {error && (
            <div role="alert" className="alert">
              {error}
              <button onClick={() => setError("")}>关闭</button>
            </div>
          )}
          {!connected && !adapterRecovery && <form className="connection-form" onSubmit={(e) => {
            e.preventDefault();
            const password = passwordInput.current?.value ?? "";
            if (passwordInput.current) passwordInput.current.value = "";
            void run(() => api("connect-robot", { password }));
          }}>
            <label htmlFor="robot-password">小车 SSH 密码</label>
            <input id="robot-password" ref={passwordInput} type="password" autoComplete="off" required disabled={busy} />
            <button className="primary" type="submit" disabled={busy}>{busy ? "正在准备…" : "连接小车"}</button>
            <span>连接后自动完成停车准备，不会启动探索。</span>
          </form>}
          {!connected && adapterRecovery && <section className="adapter-recovery" aria-label="适配器恢复">
            <div className="recovery-actions">
              <span role="status">{preparation ? preparationLabel + "…" : "自动准备未完成，SSH 已保留。"}</span>
              <button disabled={busy || Boolean(preparation)} onClick={() => void run(async () => {
                setAdapterEvidence(await api("adapter/diagnostics"));
              })}>读取适配器日志</button>
            </div>
            <button className="primary" disabled={busy || Boolean(preparation)} onClick={() => void run(async () => {
              await api("robot/prepare", {confirm_parked:true});
            })}>{busy || preparation ? "正在准备…" : "重试停车准备"}</button>
            <p>只补启动缺失的原有服务；不重启已运行进程、不覆盖已保存地图、不解锁、不启动探索。</p>
            {adapterEvidence && <details open><summary>适配器退出记录</summary>
              {adapterEvidence.missing_services?.length ? <p>缺失服务：{adapterEvidence.missing_services.join("、")}</p> : null}
              <pre>{adapterEvidence.log_tail || adapterEvidence.reason || "未找到原适配器日志"}</pre>
            </details>}
          </section>}
          <div className="metrics">
            {["scan", "odom", "map", "camera"].map((key, i) => {
              const s = state?.streams[key];
              const readout = streamReadout(key, s, healthy, (now - lastReceive) / 1000, cameraStampWarning);
              const fresh = readout.available;
              return (
                <div className="metric" key={key}>
                  <div>
                    <span>
                      {["激光雷达", "轮式里程计", "占据栅格地图", "相机"][i]}
                    </span>
                    <span className={`dot ${fresh ? (readout.timestampWarning ? "warning" : "live") : ""}`} />
                  </div>
                  <strong>
                    {fresh ? readout.hz.toFixed(1) : "—"}
                    <small> Hz</small>
                  </strong>
                  <p>
                    {readout.age != null
                      ? `数据年龄 ${Math.max(0, readout.age).toFixed(2)} s`
                      : "尚未收到数据"}{" "}
                    · {readout.status}
                    {readout.timestampWarning && " · 已检测到时间异常"}
                  </p>
                </div>
              );
            })}
          </div>
          <div className="primary-grid">
            <section className="panel map-panel">
              <div className="panel-head">
                <h2>空间视图</h2>
                <span>占据栅格 · 雷达 · 估计位姿</span>
              </div>
              <MapView state={healthy ? state : null} resetDisabled={!healthy || busy || terminal || !!state?.maintenance}
                onReset={() => run(async () => {
                  keys.current.clear(); pendingManual.current = null;
                  await api("task", { action: "reset_map" });
                })} />
            </section>
            <div className="right-column">
              <section className="panel camera-panel">
                <div className="panel-head">
                  <h2>相机</h2>
                  <span>只用于监看</span>
                </div>
                {cameraStampWarning && (
                    <p role="status" className="camera-warning">
                      已检测到相机采集时间戳异常；画面按接收时间显示，不用于定位或安全判定。
                    </p>
                  )}
                <div className="camera">
                  {healthy &&
                  (state?.streams.camera?.receiving ?? state?.streams.camera?.fresh) &&
                  cameraUrl &&
                  !cameraFailed ? (
                    <img src={cameraUrl} alt="实时相机画面" />
                  ) : (
                    <div className="empty">
                      <span>▧</span>
                      <strong>暂无实时画面</strong>
                      <p>
                        {state?.camera_error ||
                          "等待相机话题 / 检查编码与时间戳"}
                      </p>
                    </div>
                  )}
                </div>
              </section>
              <section className="panel control-panel">
                <div className="panel-head">
                  <h2>手动控制</h2>
                  <span
                    className={
                      healthy && state?.control.mine ? "green" : "amber"
                    }
                  >
                    {controlStatus(
                      healthy,
                      Boolean(state?.control.enabled),
                      Boolean(state?.control.mine),
                      state?.task?.mode,
                      state?.control.watchdog?.armed,
                    )}
                  </span>
                </div>
                <div className="control-content">
                  <div className="keys">
                    <kbd>W</kbd>
                    <div>
                      <kbd>A</kbd>
                      <kbd>S</kbd>
                      <kbd>D</kbd>
                    </div>
                  </div>
                  <div>
                    <strong>按住行驶，松键停车</strong>
                    <p>
                      W/S 前后 · A/D 转向
                      <br />
                      WASD 接管并按住行驶，松键停车；Space 停止探索
                    </p>
                  </div>
                </div>
                <div className="control-readings">
                  <span>
                    手动目标{" "}
                    {(healthy ? state?.control.target : undefined)
                      ?.map((v) => v.toFixed(2))
                      .join(" / ") || "—"}
                  </span>
                  <span>
                    手动输出{" "}
                    {(healthy ? state?.control.output : undefined)
                      ?.map((v) => v.toFixed(2))
                      .join(" / ") || "—"}
                  </span>
                  <span>
                    反馈{" "}
                    {healthy && state?.streams.odom?.fresh && state?.odom
                      ? `${state.odom.linear.toFixed(2)} / ${state.odom.angular.toFixed(2)}`
                      : "—（过期或缺失）"}
                  </span>
                </div>
                <p className="hint">
                  m/s · rad/s ｜接口上限{" "}
                  {state?.control.limits
                    ?.map((v) => v.toFixed(2))
                    .join(" / ") ?? "—"}
                  <br />
                  命令 / 心跳超时 {state?.control.command_timeout ?? 0.5}s /{" "}
                  {state?.control.heartbeat_timeout ?? 0.5}s<br />
                  状态：{state?.control.reason || (healthy ? "数据在线" : "未连接")}
                  <br />
                  最终看门狗：
                  {state?.control.watchdog
                    ? JSON.stringify(state.control.watchdog)
                    : "仿真本地保护 / 实车未在线"}
                  <br />
                  {state?.control.enabled
                    ? "软件停车不能替代硬件急停"
                    : "只读不发送底盘停车指令；现场使用硬件急停"}
                </p>
                <p className="hint" aria-label="当前控制模式">
                  当前：{state?.task?.mode === "autonomous" ? "自主探索" : state?.task?.mode === "starting" ? "正在启动探索" : "远程接管 · 等待 WASD"}
                </p>
                {state?.task?.error && <p role="alert" className="hint">{state.task.error}</p>}
                <div className="task-actions">
                  <button className="primary" disabled={!healthy || busy || terminal || state?.maintenance || state?.map_reset?.busy || state?.task?.mode === "autonomous" || state?.task?.mode === "starting"}
                    onClick={() => run(async () => {
                      keys.current.clear(); pendingManual.current = null;
                      await api("task", { action: "explore" });
                    })}>自主探索</button>
                  <button disabled={!healthy} onClick={() => {
                    stop(); setTerminal(false);
                    api("task", { action: "remote" }).catch((e) => setError(e.message));
                  }}>远程接管</button>
                </div>
                <div className="task-actions" aria-label="速度挡位">
                  <button aria-label="降低速度挡位" disabled={!healthy || (state?.control.gear ?? 1) === 0}
                    onClick={() => send("gear", { delta: -1 })}>−</button>
                  <span>{["低挡", "中挡", "高挡"][state?.control.gear ?? 1]} ·
                    {((state?.control.limits[0] ?? .1) * [.3, .6, 1][state?.control.gear ?? 1]).toFixed(2)} m/s</span>
                  <button aria-label="提高速度挡位" disabled={!healthy || (state?.control.gear ?? 1) === 2}
                    onClick={() => send("gear", { delta: 1 })}>＋</button>
                </div>
              </section>
            </div>
          </div>
          {terminal && <TerminalView close={() => setTerminal(false)} />}
          {desktop && (
            <section className="panel desktop-panel">
              <div className="panel-head">
                <h2>Gazebo / RViz 仿真桌面</h2>
                <span>查看模式 · 控制使用网页 WASD</span>
                <button onClick={() => setDesktop(false)}>关闭</button>
              </div>
              <iframe
                title="Gazebo 和 RViz 桌面"
                src="/api/v1/desktop/vnc.html?autoconnect=true&resize=scale&view_only=true&path=api/v1/desktop/websockify"
              />
            </section>
          )}
          <section className="panel logs-panel">
            <div className="panel-head">
              <h2>
                运行日志 <span className="count">{list.length}</span>
              </h2>
              <input
                aria-label="筛选日志"
                placeholder="筛选节点 / 日志内容…"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
              <button onClick={() => setPaused(!paused)}>
                {paused ? "继续滚动" : "暂停滚动"}
              </button>
              <button onClick={exportLogs}>导出 JSONL</button>
            </div>
            <div className="logs" ref={logBox}>
              {list.length ? (
                list.map((l) => (
                  <div className="log" key={l.id}>
                    <time>{l.stamp.toFixed(3)}</time>
                    <span
                      className={
                        l.level >= 40
                          ? "red"
                          : l.level >= 30
                            ? "amber"
                            : "green"
                      }
                    >
                      {l.level >= 40
                        ? "ERROR"
                        : l.level >= 30
                          ? "WARN"
                          : "INFO"}
                    </span>
                    <strong>{l.name}</strong>
                    <code>{l.message}</code>
                  </div>
                ))
              ) : (
                <div className="empty-log">
                  尚未收到 /rosout 日志。SSH 命令输出显示在维护终端中。
                </div>
              )}
            </div>
          </section>
          {getPanels().map((p) => (
            <section className="panel extension" key={p.id}>
              <h2>{p.title}</h2>
              <p.component state={healthy ? state : null} />
            </section>
          ))}
          <footer>
            <span>
              估计 TF：
              {healthy && state?.pose
                ? `${state.pose.frame} → base · ${state.pose.age.toFixed(2)} s`
                : "不可用 / 过期"}
            </span>
            <span>真实车运动须先通过对应关卡 · 当前控制台不批准关卡</span>
          </footer>
        </main>
      </div>
    </>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
