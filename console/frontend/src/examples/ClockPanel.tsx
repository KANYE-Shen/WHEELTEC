import { registerPanel } from "../panels";
// Import this module once from main.tsx to add a read-only panel.
registerPanel({
  id: "example-ros-clock",
  title: "ROS 时钟",
  component: ({ state }) => (
    <output>{state ? state.clock.toFixed(3) + " s" : "未连接"}</output>
  ),
});
