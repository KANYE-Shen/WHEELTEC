export function velocity(keys: Set<string>, gear = 2, limits: [number, number] = [0.1, 0.3]): [number, number] {
  const ratio = [0.3, 0.6, 1][Math.max(0, Math.min(2, gear))];
  return [
    ((keys.has("w") ? 1 : 0) - (keys.has("s") ? 1 : 0)) * limits[0] * ratio,
    ((keys.has("a") ? 1 : 0) - (keys.has("d") ? 1 : 0)) * limits[1] * ratio,
  ];
}
export function editable(tag: string, contentEditable: boolean) {
  return ["INPUT", "TEXTAREA", "SELECT"].includes(tag) || contentEditable;
}

export function controlStatus(
  online: boolean,
  enabled: boolean,
  mine: boolean,
  mode?: string,
  armed?: boolean,
) {
  if (!online) return "控制状态离线";
  if (!enabled) return "只读模式";
  if (mode === "starting") return "正在启动探索";
  if (mode === "autonomous") return armed === false ? "自主探索 · 保护停车" : "自主探索中";
  return mine ? "持有控制权" : "停车保持";
}
