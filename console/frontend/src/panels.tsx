import type { ComponentType } from "react";
import type { State } from "./protocol";
export type PanelProps = { state: State | null };
export type Panel = {
  id: string;
  title: string;
  component: ComponentType<PanelProps>;
};
const registry: Panel[] = [];
export function registerPanel(panel: Panel) {
  if (registry.some((p) => p.id === panel.id))
    throw new Error("Duplicate panel id");
  registry.push(panel);
}
export function getPanels() {
  return [...registry];
}
// Extension example: registerPanel({id:'clock',title:'ROS 时钟',component:({state})=><output>{state?.clock??'未连接'}</output>});
