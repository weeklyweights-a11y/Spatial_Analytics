import { TrafficChart } from "./TrafficChart";
import { VisitorBreakdown } from "./VisitorBreakdown";
import type { SponsorReportData } from "../types";

interface SponsorReportProps {
  report: SponsorReportData;
}

export function SponsorReport({ report }: SponsorReportProps) {
  const m = report.metrics;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard label="Unique Visitors" value={String(m.unique_visitors)} />
        <MetricCard label="Avg Dwell" value={`${m.avg_dwell_seconds}s`} />
        <MetricCard label="Return Rate" value={`${m.return_rate_pct}%`} />
        <MetricCard label="Peak Hour" value={m.peak_hour} />
      </div>
      <TrafficChart data={report.hourly_traffic} />
      <VisitorBreakdown breakdown={report.visitor_breakdown} />
      <div>
        <h3 className="text-sm font-semibold text-slate-300 mb-2">Top visitors</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-400 text-left">
              <th>Name</th>
              <th>Visits</th>
              <th>Total time (min)</th>
            </tr>
          </thead>
          <tbody>
            {report.top_visitors.map((v) => (
              <tr key={v.participant_id} className="border-t border-slate-800">
                <td className="py-1">{v.name}</td>
                <td>{v.visits}</td>
                <td>{v.total_dwell_minutes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="p-4 rounded-lg bg-slate-900 border border-slate-800">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="text-xl font-semibold text-slate-100 mt-1">{value}</p>
    </div>
  );
}
