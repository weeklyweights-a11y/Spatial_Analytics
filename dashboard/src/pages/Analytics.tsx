import { useEffect, useState } from "react";
import { api } from "../utils/api";
import { EnergyGraph } from "../components/EnergyGraph";

export default function AnalyticsPage() {
  const [energyPoints, setEnergyPoints] = useState<{ timestamp: string; energy: number }[]>([]);
  const [zoneSeries, setZoneSeries] = useState<Record<string, { timestamp: string; count: number; pct: number }[]>>({});

  useEffect(() => {
    const to = new Date();
    const from = new Date(to.getTime() - 24 * 60 * 60 * 1000);
    api
      .get("/api/v1/analytics/energy", {
        params: { from: from.toISOString(), to: to.toISOString(), interval: 30 },
      })
      .then((res) => setEnergyPoints(res.data.data.points ?? []));
    api
      .get("/api/v1/analytics/zones", {
        params: { from: from.toISOString(), to: to.toISOString(), interval: 30 },
      })
      .then((res) => setZoneSeries(res.data.data.zones ?? {}));
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-slate-100">Analytics</h1>
      <EnergyGraph points={energyPoints} height={280} />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Object.entries(zoneSeries).slice(0, 6).map(([name, points]) => (
          <div key={name} className="bg-slate-900 border border-slate-800 rounded-lg p-3">
            <h3 className="text-sm font-semibold text-slate-300 mb-2">{name}</h3>
            <div className="text-xs text-slate-500 space-y-1 max-h-32 overflow-y-auto">
              {points.slice(-8).map((p) => (
                <div key={`${name}-${p.timestamp}`} className="flex justify-between">
                  <span>{p.timestamp}</span>
                  <span>
                    {p.count} ({p.pct}%)
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
