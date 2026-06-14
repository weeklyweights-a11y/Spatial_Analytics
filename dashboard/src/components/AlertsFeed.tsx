import { useEffect, useState } from "react";
import { api } from "../utils/api";
import { useWebSocket } from "../hooks/useWebSocket";
import type { AlertMessage } from "../types";

interface ApiAlertRow {
  id: string;
  rule_name: string;
  severity: AlertMessage["severity"];
  message: string;
  zone?: string;
  floor?: number;
  fired_at: string;
  acknowledged?: boolean;
}

interface AlertRow extends AlertMessage {
  acknowledged?: boolean;
}

export function AlertsFeed() {
  const [alerts, setAlerts] = useState<AlertRow[]>([]);

  useWebSocket<AlertMessage>("/ws/alerts", true, (msg) => {
    setAlerts((prev) => [msg, ...prev].slice(0, 10));
  });

  useEffect(() => {
    api.get("/api/v1/alerts", { params: { limit: 10 } }).then((res) => {
      setAlerts(
        (res.data.data ?? []).map((a: ApiAlertRow) => ({
          type: "alert",
          id: a.id,
          rule_name: a.rule_name,
          severity: a.severity,
          message: a.message,
          zone: a.zone,
          floor: a.floor,
          timestamp: a.fired_at,
          acknowledged: a.acknowledged,
        }))
      );
    });
  }, []);

  const acknowledge = async (id: string) => {
    await api.put(`/api/v1/alerts/${id}/acknowledge`);
    setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, acknowledged: true } : a)));
  };

  return (
    <div className="bg-slate-900 rounded-lg border border-slate-800 p-3">
      <h3 className="text-sm font-semibold text-slate-300 mb-2">Alerts</h3>
      <ul className="space-y-2 max-h-48 overflow-y-auto">
        {alerts.map((a) => (
          <li key={a.id} className={`text-xs p-2 rounded border border-slate-800 ${a.acknowledged ? "opacity-50" : ""}`}>
            <div className="text-slate-300">{a.message}</div>
            {!a.acknowledged && (
              <button type="button" onClick={() => acknowledge(a.id)} className="text-emerald-400 mt-1">
                Acknowledge
              </button>
            )}
          </li>
        ))}
        {alerts.length === 0 && <li className="text-sm text-slate-500">No alerts</li>}
      </ul>
    </div>
  );
}
