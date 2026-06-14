import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart as RechartsRadar,
  ResponsiveContainer,
} from "recharts";
import type { RadarPoint } from "../types";

interface RadarChartProps {
  data: RadarPoint[];
  size?: "sm" | "md";
}

export function RadarChart({ data, size = "md" }: RadarChartProps) {
  const h = size === "sm" ? 160 : 280;
  const chartData = data.map((d) => ({ axis: d.axis, value: Math.round(d.value * 100) }));
  return (
    <ResponsiveContainer width="100%" height={h}>
      <RechartsRadar data={chartData} cx="50%" cy="50%" outerRadius="70%">
        <PolarGrid stroke="#334155" />
        <PolarAngleAxis dataKey="axis" tick={{ fill: "#94a3b8", fontSize: 11 }} />
        <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
        <Radar dataKey="value" stroke="#34d399" fill="#34d399" fillOpacity={0.35} />
      </RechartsRadar>
    </ResponsiveContainer>
  );
}
