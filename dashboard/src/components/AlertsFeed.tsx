import { useWebSocket } from "../hooks/useWebSocket";

export function AlertsFeed() {
  useWebSocket("/ws/alerts", true);
  return (
    <div className="bg-slate-900 rounded-lg border border-slate-800 p-3">
      <h3 className="text-sm font-semibold text-slate-300 mb-2">Alerts</h3>
      <p className="text-sm text-slate-500">No alerts</p>
    </div>
  );
}
