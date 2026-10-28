import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import { api, socket } from "./api";
import type { State, Profile, Log } from "./protocol";
import { MapView } from "./MapView";
import { TerminalView } from "./TerminalView";
import { velocity, editable, controlStatus } from "./control";
import { getPanels } from "./panels";
import { streamReadout } from "./streamReadout";
import "./style.css";
const blank: Profile = {
  name: "WSL 仿真",
  kind: "simulation",
  host: "127.0.0.1",
  port: 2222,
  username: "wheeltec",
  fingerprint: "",
  key_file: "",
  adapter_port: 8767,
  desktop_port: 6080,
};
function App() {
  const [state, setState] = useState<State | null>(null),
    [connected, setConnected] = useState(false),
    [profiles, setProfiles] = useState<Record<string, Profile>>({}),
    [profile, setProfile] = useState<Profile>(blank),
    [settings, setSettings] = useState(true),
    [password, setPassword] = useState(""),
    [token, setToken] = useState(""),
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
        JSON.stringify({ type: "control", data: { action, ...extra } }),
      );
  };
  const stop = () => {
    keys.current.clear();
    if (current.current?.control.enabled) send("stop");
  };
  useEffect(() => {
    let active = true,
      retry: ReturnType<typeof setTimeout>;
    fetch("/bootstrap")
      .then(() => api<Record<string, Profile>>("profiles"))
      .then((p) => {
        if (active) setProfiles(p);
      })
      .catch((e) => setError(e.message));
    const open = () => {
      if (!active) return;
      const s = socket("events");
      ws.current = s;
      s.onmessage = (e) => {
        const m = JSON.parse(e.data);
        if (m.type === "state") {
          if (!m.data.control.mine || !m.data.control.ready)
            keys.current.clear();
          if (m.data.streams.camera?.receiving && !m.data.streams.camera.fresh)
            setCameraStampWarning(true);
          setState(m.data);
          setConnected(true);
          setLastReceive(Date.now());
          lastGood.current = Date.now();
          if (!pause.current) {
            setLogs(m.data.logs);
            frozenLogs.current = m.data.logs;
          }
        } else if (m.type === "offline") {
          if (!pause.current && m.data.logs) setLogs(m.data.logs);
          setConnected(false);
          keys.current.clear();
        } else if (m.type === "error") {
          setError(m.data.reason);
          keys.current.clear();
        }
      };
      s.onclose = () => {
        setConnected(false);
        keys.current.clear();
        retry = setTimeout(open, 1500);
      };
    };
    fetch("/bootstrap").then(open);
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
      const target = e.target as HTMLElement;
      if (editable(target.tagName, target.isContentEditable) || terminal)
        return;
      const k = e.key.toLowerCase();
      if (e.repeat && k !== " ") return;
      if (k === " ") {
        e.preventDefault();
        stop();
        return;
      }
      if (!"wasd".includes(k) || k.length !== 1) return;
      if (!current.current?.control.mine || !current.current.control.ready)
        return;
      e.preventDefault();
      keys.current.add(k);
      const [linear, angular] = velocity(keys.current);
      send("command", { linear, angular });
    };
    const up = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      if (keys.current.delete(k)) {
        const [linear, angular] = velocity(keys.current);
        send("command", { linear, angular });
      }
    };
    const blur = () => stop();
    const hidden = () => {
      if (document.hidden) stop();
    };
    const focus = (e: FocusEvent) => {
      const el = e.target as HTMLElement;
      if (editable(el.tagName, el.isContentEditable)) stop();
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", blur);
    document.addEventListener("visibilitychange", hidden);
    document.addEventListener("focusin", focus);
    window.addEventListener("pagehide", blur);
    const timer = setInterval(() => {
      if (
        current.current?.control.mine &&
        document.hasFocus() &&
        !document.hidden &&
        !terminal &&
        Date.now() - lastGood.current < 800
      ) {
        const [linear, angular] = velocity(keys.current);
        send("command", { linear, angular });
      }
    }, 100);
    return () => {
      clearInterval(timer);
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", blur);
      document.removeEventListener("visibilitychange", hidden);
      document.removeEventListener("focusin", focus);
      window.removeEventListener("pagehide", blur);
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
  const connect = () =>
    run(async () => {
      await api("connect", { profile, password, adapter_token: token });
      setPassword("");
      setToken("");
      setSettings(false);
    });
  const healthy = connected && now - lastReceive < 1000;
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
            {state?.kind === "robot" ? "实车" : "仿真"}
          </span>
        </div>
        <button onClick={() => setSettings(!settings)}>连接设置</button>
        <button
          disabled={!connected}
          onClick={() =>
            run(async () => {
              stop();
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
                  ? (state?.connection?.name || profile.name) +
                    " · " +
                    (state?.connection?.host || profile.host)
                  : "连接目标主机后查看实时 ROS 数据"}
              </p>
            </div>
            <button
              className="stop"
              disabled={!healthy || !state?.control.enabled}
              title="只读状态不能发送底盘停车指令；现场使用硬件急停"
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
          {settings && (
            <section className="panel settings">
              <div className="panel-head">
                <h2>SSH 连接</h2>
                <span>凭据仅保留在当前会话内存</span>
              </div>
              <div className="form-grid">
                <label>
                  已存配置
                  <select
                    onChange={(e) => {
                      const p = profiles[e.target.value];
                      if (p) setProfile(p);
                    }}
                  >
                    <option value="">选择配置</option>
                    {Object.keys(profiles).map((n) => (
                      <option key={n}>{n}</option>
                    ))}
                  </select>
                </label>
                {(
                  [
                    "name",
                    "host",
                    "username",
                    "port",
                    "adapter_port",
                    "desktop_port",
                    "key_file",
                  ] as const
                ).map((k) => (
                  <label key={k}>
                    {
                      {
                        name: "配置名称",
                        host: "SSH 地址",
                        username: "SSH 用户",
                        port: "SSH 端口",
                        adapter_port: "目标适配器端口",
                        desktop_port: "noVNC 端口",
                        key_file: "本机私钥路径（可选）",
                      }[k]
                    }
                    <input
                      aria-label={k}
                      value={profile[k]}
                      onChange={(e) =>
                        setProfile({
                          ...profile,
                          [k]: [
                            "port",
                            "adapter_port",
                            "desktop_port",
                          ].includes(k)
                            ? Number(e.target.value)
                            : e.target.value,
                        })
                      }
                    />
                  </label>
                ))}
                <label>
                  目标类型
                  <select
                    value={profile.kind}
                    onChange={(e) =>
                      setProfile({
                        ...profile,
                        kind: e.target.value as Profile["kind"],
                      })
                    }
                  >
                    <option value="simulation">WSL / 仿真</option>
                    <option value="robot">真实小车 · 默认只读</option>
                  </select>
                </label>
                <label className="wide">
                  SSH SHA256 指纹
                  <input
                    aria-label="fingerprint"
                    value={profile.fingerprint}
                    onChange={(e) =>
                      setProfile({ ...profile, fingerprint: e.target.value })
                    }
                  />
                </label>
                <label>
                  SSH 密码（或使用密钥）
                  <input
                    aria-label="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="off"
                  />
                </label>
                <label>
                  适配器访问令牌
                  <input
                    aria-label="adapter_token"
                    type="password"
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    autoComplete="off"
                  />
                </label>
              </div>
              <p className="hint">
                先在目标主机核对 SSH
                指纹，再填入。探测结果本身不能证明主机身份。
              </p>
              <div className="actions">
                <button
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      const p = await api<{ fingerprint: string }>("probe", {
                        host: profile.host,
                        port: profile.port,
                      });
                      setProfile({ ...profile, fingerprint: p.fingerprint });
                    })
                  }
                >
                  探测主机指纹
                </button>
                <button
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      await api("profiles", profile);
                      setProfiles(await api("profiles"));
                    })
                  }
                >
                  保存非敏感配置
                </button>
                <button
                  className="primary"
                  disabled={busy || !profile.fingerprint || !token}
                  onClick={connect}
                >
                  {busy ? "处理中…" : "连接目标"}
                </button>
              </div>
            </section>
          )}
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
              <MapView state={healthy ? state : null} />
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
                      空格停车 · 失焦释放
                    </p>
                  </div>
                </div>
                <div className="control-readings">
                  <span>
                    目标{" "}
                    {(healthy ? state?.control.target : undefined)
                      ?.map((v) => v.toFixed(2))
                      .join(" / ") || "—"}
                  </span>
                  <span>
                    输出{" "}
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
                  状态：{state?.control.reason || "未连接"}
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
                <button
                  className="primary full"
                  disabled={
                    !healthy ||
                    !state?.control.enabled ||
                    terminal ||
                    state?.maintenance ||
                    state?.control.mine
                  }
                  onClick={() => {
                    keys.current.clear();
                    send("claim");
                  }}
                >
                  取得手动控制权
                </button>
                <button
                  className="full"
                  disabled={!state?.control.mine}
                  onClick={() => {
                    keys.current.clear();
                    send("release");
                  }}
                >
                  释放控制权
                </button>
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
