export function velocity(keys: Set<string>): [number, number] {
  return [
    ((keys.has("w") ? 1 : 0) - (keys.has("s") ? 1 : 0)) * 0.1,
    ((keys.has("a") ? 1 : 0) - (keys.has("d") ? 1 : 0)) * 0.3,
  ];
}
export function editable(tag: string, contentEditable: boolean) {
  return ["INPUT", "TEXTAREA", "SELECT"].includes(tag) || contentEditable;
}

export function controlStatus(
  online: boolean,
  enabled: boolean,
  mine: boolean,
) {
  if (!online) return "控制状态离线";
  if (!enabled) return "只读模式";
  return mine ? "持有控制权" : "停车保持";
}
