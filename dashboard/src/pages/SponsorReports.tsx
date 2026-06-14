import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { SponsorCard } from "../components/SponsorCard";
import { SponsorReport } from "../components/SponsorReport";
import { useAuth } from "../hooks/useAuth";
import { useSponsorReport, useSponsors } from "../hooks/useSponsors";
import { api } from "../utils/api";

export default function SponsorReportsPage() {
  const { role } = useAuth();
  const { data: sponsors, isLoading } = useSponsors();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const activeId = selectedId ?? sponsors?.[0]?.id ?? null;
  const { data: report } = useSponsorReport(activeId);

  const comparisonData = useMemo(
    () => (sponsors ?? []).map((s) => ({ name: s.name, visitors: s.unique_visitors })),
    [sponsors]
  );

  const downloadPdf = async () => {
    if (!activeId) return;
    const res = await api.get(`/api/v1/sponsors/${activeId}/report/pdf`, { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = `spatialscore_report.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (role === "viewer") {
    return <p className="text-slate-400">Sponsor reports require operator or admin access.</p>;
  }

  if (isLoading) return <p className="text-slate-400">Loading sponsors...</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Sponsor Reports</h1>
        {role === "admin" && activeId && (
          <button
            type="button"
            onClick={downloadPdf}
            className="px-4 py-2 rounded bg-emerald-600 hover:bg-emerald-500 text-sm font-medium"
          >
            Download PDF
          </button>
        )}
      </div>

      <div className="grid lg:grid-cols-4 gap-6">
        <div className="space-y-2">
          {(sponsors ?? []).map((s) => (
            <SponsorCard
              key={s.id}
              sponsor={s}
              selected={s.id === activeId}
              onSelect={() => setSelectedId(s.id)}
            />
          ))}
        </div>
        <div className="lg:col-span-3">
          {report ? <SponsorReport report={report} /> : <p className="text-slate-500">Select a sponsor</p>}
        </div>
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-3">vs Other Sponsors</h2>
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={comparisonData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="name" tick={{ fill: "#94a3b8", fontSize: 11 }} />
              <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
              <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155" }} />
              <Bar dataKey="visitors" fill="#6366f1" name="Unique visitors" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
