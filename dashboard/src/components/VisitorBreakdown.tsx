import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

interface VisitorBreakdownProps {
  breakdown: {
    by_track: Record<string, number>;
    by_floor: Record<string, number>;
  };
}

const COLORS = ["#10b981", "#3b82f6", "#f97316", "#a855f7", "#64748b"];

function toChartData(record: Record<string, number>) {
  return Object.entries(record).map(([name, value]) => ({ name, value }));
}

export function VisitorBreakdown({ breakdown }: VisitorBreakdownProps) {
  const trackData = toChartData(breakdown.by_track ?? {});
  const floorData = toChartData(breakdown.by_floor ?? {});

  return (
    <div className="grid md:grid-cols-2 gap-6">
      <PieBlock title="By track" data={trackData} />
      <PieBlock title="By floor" data={floorData} />
    </div>
  );
}

function PieBlock({ title, data }: { title: string; data: Array<{ name: string; value: number }> }) {
  if (!data.length) {
    return (
      <div>
        <h3 className="text-sm font-semibold text-slate-300 mb-2">{title}</h3>
        <p className="text-slate-500 text-sm">No data</p>
      </div>
    );
  }
  return (
    <div className="h-56">
      <h3 className="text-sm font-semibold text-slate-300 mb-2">{title}</h3>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} label>
            {data.map((_, i) => (
              <Cell key={data[i].name} fill={COLORS[i % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155" }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
