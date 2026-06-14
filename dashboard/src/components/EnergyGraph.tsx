import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface EnergyPoint {
  timestamp: string;
  energy: number;
  active?: number;
}

interface EnergyGraphProps {
  points: EnergyPoint[];
  height?: number;
}

export function EnergyGraph({ points, height = 160 }: EnergyGraphProps) {
  const chartData = points.map((p) => ({
    label: new Date(p.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    energy: Math.round(p.energy * 100),
  }));
  return (
    <div className="bg-slate-900 rounded-lg border border-slate-800 p-3">
      <h3 className="text-sm font-semibold text-slate-300 mb-2">Energy Level</h3>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={chartData}>
          <XAxis dataKey="label" tick={{ fill: "#64748b", fontSize: 10 }} />
          <YAxis domain={[0, 100]} tick={{ fill: "#64748b", fontSize: 10 }} />
          <Tooltip />
          <Line type="monotone" dataKey="energy" stroke="#34d399" dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
