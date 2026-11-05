import { useEffect, useRef, useState } from "react";
import type { State } from "./protocol";
export function MapView({ state, onReset, resetDisabled }: { state: State | null; onReset: () => void; resetDisabled: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null),
    drag = useRef<[number, number] | null>(null);
  const [zoom, setZoom] = useState(58),
    [pan, setPan] = useState<[number, number]>([0, 0]),
    [laser, setLaser] = useState(true),
    [grid, setGrid] = useState(true),
    [local, setLocal] = useState(false);
  useEffect(() => {
    if (!state?.map_reset?.sequence || state.map_reset.busy) return;
    const p = local ? null : state.pose;
    setPan(p ? [-p.x * 58, p.y * 58] : [0, 0]);
    setZoom(58);
  }, [state?.map_reset?.sequence]);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    const draw = () => {
      const w = canvas.clientWidth,
        h = canvas.clientHeight,
        dpr = devicePixelRatio || 1;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.scale(dpr, dpr);
      ctx.fillStyle = "#101b26";
      ctx.fillRect(0, 0, w, h);
      ctx.save();
      ctx.translate(w / 2 + pan[0], h / 2 + pan[1]);
      ctx.scale(zoom, -zoom);
      ctx.strokeStyle = "#22313f";
      ctx.lineWidth = 1 / zoom;
      for (let i = -30; i <= 30; i++) {
        ctx.beginPath();
        ctx.moveTo(i, -30);
        ctx.lineTo(i, 30);
        ctx.moveTo(-30, i);
        ctx.lineTo(30, i);
        ctx.stroke();
      }
      const map = local || state?.map_reset?.busy ? undefined : state?.map;
      if (map && grid) {
        const image = document.createElement("canvas");
        image.width = map.width;
        image.height = map.height;
        const c = image.getContext("2d")!,
          pixels = c.createImageData(map.width, map.height);
        map.data.forEach((v, i) => {
          const color =
            v < 0 ? [43, 57, 70] : v > 50 ? [221, 232, 233] : [100, 135, 145];
          pixels.data.set([...color, 255], i * 4);
        });
        c.putImageData(pixels, 0, 0);
        ctx.save();
        ctx.translate(map.origin[0], map.origin[1]);
        ctx.rotate(map.origin[2]);
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(
          image,
          0,
          0,
          map.width * map.resolution,
          map.height * map.resolution,
        );
        ctx.restore();
      }
      const scan = state?.scan;
      const pose = local || state?.map_reset?.busy ? null : state?.laser_pose;
      if (scan && laser && state?.streams.scan?.fresh && (!map || pose)) {
        ctx.save();
        if (pose) {
          ctx.translate(pose.x, pose.y);
          ctx.rotate(pose.yaw);
        }
        ctx.fillStyle = "#57e2c1";
        scan.ranges.forEach((r, i) => {
          if (r === null) return;
          const a = scan.angle_min + i * scan.angle_increment;
          ctx.fillRect(
            r * Math.cos(a) - 0.013,
            r * Math.sin(a) - 0.013,
            0.026,
            0.026,
          );
        });
        ctx.restore();
      }
      if (state?.pose && !local && !state?.map_reset?.busy) {
        const p = state.pose;
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.yaw);
        ctx.fillStyle = "#ffcc76";
        ctx.beginPath();
        ctx.moveTo(0.23, 0);
        ctx.lineTo(-0.15, 0.13);
        ctx.lineTo(-0.15, -0.13);
        ctx.closePath();
        ctx.fill();
        ctx.restore();
      }
      ctx.restore();
      ctx.fillStyle = "#9bafba";
      ctx.font = "11px monospace";
      ctx.fillText(
        map
          ? `frame: ${map.frame} · ${map.resolution.toFixed(3)} m/cell`
          : `frame: ${scan?.frame || "等待数据"}`,
        16,
        h - 15,
      );
      ctx.fillText("1 m", w - 72, h - 15);
      ctx.fillRect(w - 90, h - 28, zoom, 2);
    };
    draw();
    const o = new ResizeObserver(draw);
    o.observe(canvas);
    return () => o.disconnect();
  }, [state, zoom, pan, laser, grid, local]);
  return (
    <>
      <div className="map-tools">
        <button disabled={resetDisabled || state?.map_reset?.busy} onClick={onReset}
          title="停车并清空车端地图与网页显示，从当前位置重新建图">
          {state?.map_reset?.busy ? "重置地图中…" : "Reset"}
        </button>
        <div className="zoom-tools" role="group" aria-label="视图缩放">
        <button aria-label="放大视图" title="放大视图" disabled={zoom >= 350}
          onClick={() => setZoom((v) => Math.min(350, v * 1.2))}>+</button>
        <output aria-label="视图缩放比例">{Math.round(zoom / 58 * 100)}%</output>
        <button aria-label="缩小视图" title="缩小视图" disabled={zoom <= 12}
          onClick={() => setZoom((v) => Math.max(12, v / 1.2))}>−</button>
        </div>
        <button onClick={() => setLocal(!local)}>
          {local ? "地图叠加" : "局部雷达"}
        </button>
        <label>
          <input
            type="checkbox"
            checked={grid}
            onChange={(e) => setGrid(e.target.checked)}
          />
          占据栅格
        </label>
        <label>
          <input
            type="checkbox"
            checked={laser}
            onChange={(e) => setLaser(e.target.checked)}
          />
          激光点云
        </label>
        <button
          onClick={() => {
            const p = local ? null : state?.pose;
            setPan(p ? [-p.x * 58, p.y * 58] : [0, 0]);
            setZoom(58);
          }}
        >
          重置视图
        </button>
      </div>
      <canvas
        ref={ref}
        aria-label="占据栅格地图与雷达"
        onPointerDown={(e) => {
          drag.current = [e.clientX, e.clientY];
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerUp={() => (drag.current = null)}
        onPointerCancel={() => (drag.current = null)}
        onLostPointerCapture={() => (drag.current = null)}
        onPointerMove={(e) => {
          const previous = drag.current;
          if (!previous) return;
          const x = e.clientX, y = e.clientY;
          const dx = x - previous[0], dy = y - previous[1];
          drag.current = [x, y];
          setPan((p) => [p[0] + dx, p[1] + dy]);
        }}
      />
      {state?.map_reset?.error && <div role="alert" className="map-note">{state.map_reset.error}</div>}
      {!state?.map && (
        <div className="map-note">尚未收到占据栅格地图 · 未自动启动 SLAM</div>
      )}
    </>
  );
}
