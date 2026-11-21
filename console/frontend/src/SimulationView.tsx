import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { api } from "./api";
import { MapView } from "./MapView";
import { gridCellAt } from "./mapGeometry";
import type { MapPoint } from "./mapGeometry";
import type { Grid, Pose, Scan, State, Stream } from "./protocol";

type Mode = "mapping" | "localization";
type Phase = "stopped" | "starting" | "running" | "failed";
const goalLabels = {
  pending: "等待 Nav2 接受",
  active: "目标执行中",
  canceling: "正在取消目标",
  succeeded: "已到达目标",
  canceled: "目标已取消",
  rejected: "Nav2 拒绝目标",
  aborted: "导航失败",
};
type Goal = MapPoint & { yaw: number; status: keyof typeof goalLabels; message: string };
type SavedMap = { id: string; name: string };
type SimulationState = {
  phase: Phase;
  message: string;
  run_id: string | null;
  mode: Mode | null;
  navigation_ready: boolean;
  map: Grid | null;
  pose: Pose | null;
  laser_pose: Pose | null;
  scan: Scan | null;
  goal: Goal | null;
};
type Action = "start" | "goal" | "cancel" | "save" | "stop";

const scenarios = {
  baseline: "基准房间",
  l_shape: "L 形房间",
  clutter: "密集障碍",
  bent_passage: "折线通道",
  recess: "带凹室的房间",
  irregular_arc: "不规则弧形区域",
  irregular_frame: "不规则框形区域",
};
const phaseLabels: Record<Phase, string> = {
  stopped: "已停止",
  starting: "启动中",
  running: "运行中",
  failed: "运行故障",
};
const scanFresh: Stream = { stamp: null, age: null, hz: 0, fresh: true };

export default function SimulationView() {
  const [state, setState] = useState<SimulationState | null>(null);
  const [ready, setReady] = useState(false);
  const [connectionError, setConnectionError] = useState("");
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState<Action | null>(null);
  const [mode, setMode] = useState<Mode>("mapping");
  const [scenario, setScenario] = useState("baseline");
  const [spawn, setSpawn] = useState("0");
  const [seed, setSeed] = useState("0");
  const [noise, setNoise] = useState("0.01");
  const [maps, setMaps] = useState<SavedMap[]>([]);
  const [mapId, setMapId] = useState("");
  const [mapListStatus, setMapListStatus] = useState<"idle" | "loading" | "ready" | "failed">("idle");
  const [mapListVersion, setMapListVersion] = useState(0);
  const inFlight = useRef(false);
  const mutation = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let session = false;
    const poll = async () => {
      const version = mutation.current;
      try {
        if (inFlight.current) return;
        if (!session) {
          const response = await fetch("/bootstrap", { signal: controller.signal });
          if (!response.ok) throw new Error("本机仿真网关未就绪");
          session = true;
        }
        const snapshot = await api<SimulationState>("simulation/state", undefined, controller.signal);
        if (controller.signal.aborted || mutation.current !== version) return;
        setState(snapshot);
        setReady(true);
        setConnectionError("");
      } catch (error) {
        if (controller.signal.aborted || mutation.current !== version) return;
        session = false;
        setReady(false);
        setConnectionError(error instanceof Error ? error.message : "读取仿真状态失败");
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(poll, 500);
      }
    };
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, []);

  const canConfigure = state?.phase === "stopped" || state?.phase === "failed";
  useEffect(() => {
    if (mode !== "localization" || !ready || !canConfigure) return;
    const controller = new AbortController();
    setMapListStatus("loading");
    api<{ maps: SavedMap[] }>("simulation/maps", undefined, controller.signal)
      .then(({ maps: options }) => {
        setMaps(options);
        setMapId((current) => options.some((map) => map.id === current) ? current : "");
        setMapListStatus("ready");
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setMapListStatus("failed");
        setActionError(error instanceof Error ? error.message : "读取地图列表失败");
      });
    return () => controller.abort();
  }, [mode, ready, canConfigure, mapListVersion]);

  async function perform(action: Action, args: object = {}) {
    if (inFlight.current) return;
    inFlight.current = true;
    mutation.current += 1;
    setPending(action);
    setActionError("");
    if (action === "start") setNotice("");
    try {
      const result = await api<Partial<SavedMap>>("simulation/" + action, args);
      if (action === "save") {
        setNotice(result.name ? `已保存地图 · ${result.name}` : "已保存地图");
        if (result.id) setMapId(result.id);
      }
      mutation.current += 1;
      try {
        setState(await api<SimulationState>("simulation/state"));
        setReady(true);
        setConnectionError("");
      } catch {
        setReady(false);
        setConnectionError("仿真指令已提交，正在重新获取状态");
      }
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "仿真操作失败");
    } finally {
      inFlight.current = false;
      setPending(null);
    }
  }

  function start(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!configure || (mode === "localization" && !mapId)) return;
    void perform("start", {
      mode,
      ...(mode === "mapping" ? { scenario, spawn: Number(spawn) } : { map_id: mapId }),
      seed: Number(seed),
      lidar_noise_stddev: Number(noise),
    });
  }

  const goal = state?.goal;
  const moving = goal?.status === "pending" || goal?.status === "active" || goal?.status === "canceling";
  const configure = ready && canConfigure && !pending;
  const canSelect = ready && state?.phase === "running" && state.navigation_ready && !moving && !pending;
  const canCancel = ready && (goal?.status === "pending" || goal?.status === "active") && !pending;
  const canSave = ready && state?.phase === "running" && state.mode === "mapping" && !!state.map && !moving && !pending;
  const canStop = ready && (state?.phase === "running" || state?.phase === "starting") && !pending;
  const canStart = configure && (mode === "mapping" || (mapListStatus === "ready" && !!mapId));

  function selectPoint(point: MapPoint, map: Grid) {
    if (!canSelect || !state?.run_id) return;
    const value = gridCellAt(map, point);
    if (value !== 0) {
      setActionError(value === undefined ? "目标超出地图范围" : value < 0 ? "目标在未知区域" : "目标所在栅格被占据");
      return;
    }
    void perform("goal", { ...point, yaw: 0, frame: map.frame, run_id: state.run_id, map_revision: map.revision });
  }

  const telemetry: Pick<State, "map" | "pose" | "scan" | "laser_pose" | "streams"> | null = ready && state ? {
    map: state.map ?? undefined,
    pose: state.pose,
    scan: state.scan ?? undefined,
    laser_pose: state.laser_pose,
    streams: state.scan && state.laser_pose ? { scan: scanFresh } : {},
  } : null;
  const showRuntimeMessage = !!state?.message && (state.phase === "failed" || (state.phase === "running" && !state.navigation_ready));
  const sourceLabel = state?.mode === "localization" ? "已存地图" : state?.mode === "mapping" ? "实时地图" : "";
  const mapStatus = canSelect ? "可点选目标" : moving ? "当前目标尚未结束" :
    canConfigure ? "启动后显示地图" : "等待地图、位姿、雷达及 Nav2";

  return (
    <div className="simulation-page">
      <header className="simulation-header">
        <div className="brand">
          <span className="brand-icon" aria-hidden="true">W</span>
          <div>
            <strong>WHEELTEC</strong>
            <small>GAZEBO · ROS 2 HUMBLE</small>
          </div>
        </div>
        <a className="console-link" href="/">返回控制台</a>
      </header>

      <main className="simulation-main">
        <div className="simulation-title">
          <div>
            <h1>仿真操作台</h1>
            <p>在本机 WSL 中建图、点选导航并重载地图</p>
          </div>
          <div className="simulation-run" role="status">
            <span className={ready && state?.phase === "running" ? "dot live" : "dot"} />
            {connectionError ? "连接异常" : state ? phaseLabels[state.phase] : "正在连接仿真网关"}
            {ready && state?.mode && <span className="simulation-run-mode">{state.mode === "mapping" ? "实时建图" : "已存地图导航"}</span>}
          </div>
        </div>
        {(actionError || connectionError) && <p className="simulation-alert" role="alert">{actionError || connectionError}</p>}
        {showRuntimeMessage && <p className="simulation-alert" role="status">{state.message}</p>}
        <div className="simulation-workspace">
          <section className="panel simulation-map" aria-label="仿真地图">
            <div className="panel-head">
              <h2>地图与雷达</h2>
              {sourceLabel && <span>{sourceLabel}</span>}
            </div>
            <MapView key={state?.run_id ?? ""} state={telemetry} marker={goal ?? null}
              onMapPoint={canSelect ? selectPoint : undefined}
              emptyMessage={state?.phase === "starting" ? "等待 SLAM 或地图服务器发布地图" : "等待仿真地图"} />
            <div className="simulation-map-status">
              <span>{mapStatus}</span>
              <span>{ready && state?.pose ? `车体 (${state.pose.x.toFixed(2)}, ${state.pose.y.toFixed(2)}) m` : "车体位姿未就绪"}</span>
            </div>
          </section>

          <div className="simulation-sidebar">
            <section className="panel" aria-labelledby="sim-goal-title">
              <div className="panel-head">
                <h2 id="sim-goal-title">导航目标</h2>
              </div>
              <div className="simulation-section">
                <div className="simulation-goal" role="status">
                  <strong>{pending === "goal" ? "正在提交目标" : goal ? goalLabels[goal.status] : "尚未选定目标"}</strong>
                  {goal && <span>({goal.x.toFixed(2)}, {goal.y.toFixed(2)}) m</span>}
                  {goal?.message && <p>{goal.message}</p>}
                </div>
                <p>点击已知空地发送目标，拖动可平移地图。</p>
                <div className="simulation-actions">
                  <button onClick={() => void perform("cancel")} disabled={!canCancel}>
                    {pending === "cancel" ? "正在取消…" : "取消目标"}
                  </button>
                  <button className="simulation-stop" onClick={() => void perform("stop")} disabled={!canStop}>
                    {pending === "stop" ? "正在停止…" : "停止仿真"}
                  </button>
                </div>
              </div>
            </section>

            <section className="panel" aria-labelledby="sim-settings-title">
              <div className="panel-head">
                <h2 id="sim-settings-title">运行参数</h2>
              </div>
              <form className="simulation-section" onSubmit={start}>
                <fieldset disabled={!configure}>
                  <label>运行模式
                    <select value={mode} onChange={(event) => { setMode(event.target.value as Mode); setActionError(""); }}>
                      <option value="mapping">实时建图</option>
                      <option value="localization">已存地图导航</option>
                    </select>
                  </label>
                  {mode === "mapping" ? (
                    <div className="simulation-fields">
                      <label>场景
                        <select value={scenario} onChange={(event) => setScenario(event.target.value)}>
                          {Object.entries(scenarios).map(([id, name]) => <option value={id} key={id}>{name}</option>)}
                        </select>
                      </label>
                      <label>起点
                        <select value={spawn} onChange={(event) => setSpawn(event.target.value)}>
                          <option value="0">起点 1</option>
                          <option value="1">起点 2</option>
                          <option value="2">起点 3</option>
                        </select>
                      </label>
                    </div>
                  ) : (
                    <label>已存地图
                      <select value={mapId} onChange={(event) => setMapId(event.target.value)} required>
                        <option value="">{mapListStatus === "loading" ? "正在读取地图…" : "选择地图"}</option>
                        {maps.map((map) => <option value={map.id} key={map.id}>{map.name}</option>)}
                      </select>
                    </label>
                  )}
                  {mode === "localization" && mapListStatus === "ready" && maps.length === 0 &&
                    <p>地图列表为空。先运行实时建图并保存地图。</p>}
                  {mode === "localization" && mapListStatus === "failed" &&
                    <button type="button" onClick={() => {
                      setActionError("");
                      setMapListVersion((value) => value + 1);
                    }}>重试读取地图</button>}
                  <div className="simulation-fields">
                    <label>随机种子
                      <input type="number" min="0" max="2147483647" step="1" required value={seed}
                        onChange={(event) => setSeed(event.target.value)} />
                    </label>
                    <label>激光测距噪声 σ (m)
                      <input type="number" min="0" max="0.03" step="any" required value={noise}
                        onChange={(event) => setNoise(event.target.value)} />
                    </label>
                  </div>
                </fieldset>
                <button className="simulation-start" disabled={!canStart}>
                  {pending === "start" ? "正在启动…" : "启动仿真"}
                </button>
              </form>
            </section>
            <section className="panel simulation-section" aria-label="地图存档">
              <button onClick={() => void perform("save")} disabled={!canSave}>
                {pending === "save" ? "正在保存…" : "保存地图"}
              </button>
              {notice ? <p role="status">{notice}</p> : <p>建图后保存地图。停止仿真，再用已存地图导航。</p>}
            </section>
          </div>
        </div>
      </main>
    </div>
  );
}
