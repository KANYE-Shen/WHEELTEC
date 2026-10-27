import { useEffect, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { socket } from "./api";
export function TerminalView({ close }: { close: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const terminal = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: "Consolas, monospace",
      theme: { background: "#0b141d", foreground: "#c8d9e1" },
      scrollback: 5000,
    });
    const fit = new FitAddon();
    terminal.loadAddon(fit);
    terminal.open(ref.current!);
    fit.fit();
    terminal.writeln(
      "维护终端 · 网页遥控已释放。Shell 使用 SSH 账户的完整权限。",
    );
    const ws = socket("terminal");
    ws.binaryType = "arraybuffer";
    ws.onopen = () => {
      terminal.focus();
      ws.send(
        JSON.stringify({
          type: "resize",
          cols: terminal.cols,
          rows: terminal.rows,
        }),
      );
    };
    ws.onmessage = (e) =>
      terminal.write(
        typeof e.data === "string" ? e.data : new Uint8Array(e.data),
      );
    ws.onclose = () => terminal.writeln("\r\n[SSH 终端已关闭；运动保持停止]");
    const input = terminal.onData((data) => {
      if (ws.readyState === 1) ws.send(JSON.stringify({ type: "input", data }));
    });
    const observer = new ResizeObserver(() => {
      fit.fit();
      if (ws.readyState === 1)
        ws.send(
          JSON.stringify({
            type: "resize",
            cols: terminal.cols,
            rows: terminal.rows,
          }),
        );
    });
    observer.observe(ref.current!);
    return () => {
      input.dispose();
      observer.disconnect();
      ws.close();
      terminal.dispose();
    };
  }, []);
  return (
    <section className="panel terminal-panel">
      <div className="panel-head">
        <h2>SSH 维护终端</h2>
        <span className="amber">完整账户权限 · 遥控互斥</span>
        <button onClick={close}>关闭终端</button>
      </div>
      <div className="terminal" ref={ref} />
    </section>
  );
}
