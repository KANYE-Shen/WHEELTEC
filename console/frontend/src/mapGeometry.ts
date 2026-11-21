import type { Grid } from "./protocol";

export type MapPoint = { x: number; y: number };

export function canvasToWorld(
  x: number, y: number, width: number, height: number,
  pan: readonly [number, number], zoom: number,
): MapPoint {
  return {
    x: (x - width / 2 - pan[0]) / zoom,
    y: (height / 2 + pan[1] - y) / zoom,
  };
}

export function gridCellAt(map: Grid, point: MapPoint): number | undefined {
  const [originX, originY, yaw] = map.origin;
  const dx = point.x - originX;
  const dy = point.y - originY;
  const cos = Math.cos(yaw);
  const sin = Math.sin(yaw);
  const col = Math.floor((dx * cos + dy * sin) / map.resolution);
  const row = Math.floor((-dx * sin + dy * cos) / map.resolution);
  if (col >= 0 && col < map.width && row >= 0 && row < map.height) {
    return map.data[row * map.width + col];
  }
}

export function movedPastClickTolerance(dx: number, dy: number) {
  return Math.hypot(dx, dy) > 5;
}
