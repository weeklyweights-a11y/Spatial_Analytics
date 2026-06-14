import type { ConnectionState } from "../hooks/useWebSocket";

interface ConnectionStatusBarProps {
  state: ConnectionState;
}

export function ConnectionStatusBar({ state }: ConnectionStatusBarProps) {
  const label =
    state === "connected" ? "Connected" : state === "reconnecting" ? "Reconnecting..." : "Offline";
  const color =
    state === "connected" ? "text-emerald-400" : state === "reconnecting" ? "text-amber-400" : "text-red-400";
  return (
    <div className={`text-xs px-3 py-1 border-b border-slate-800 ${color}`}>
      Live status: {label}
    </div>
  );
}
