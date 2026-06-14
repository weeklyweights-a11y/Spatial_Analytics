import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface TrafficChartProps {
  data: Array<{ hour: string; visitors: number; entries: number }>;
}

export function TrafficChart({ data }: TrafficChartProps) {
  if (!data.length) {
    return <p className="text-slate-500 text-sm">No hourly traffic data yet.</p>;
  }
  return (
    <div className="h-64">
      <h3 className="text-sm font-semibold text-slate-300 mb-2">Hourly traffic</h3>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="hour" tick={{ fill: "#94a3b8", fontSize: 11 }} />
          <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
          <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155" }} />
          <Bar dataKey="visitors" fill="#10b981" name="Visitors" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
