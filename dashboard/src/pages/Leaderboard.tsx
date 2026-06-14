import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../utils/api";
import { RadarChart } from "../components/RadarChart";
import { useAuth } from "../hooks/useAuth";
import type { CompareParticipant, LeaderboardEntry } from "../types";

const TRACKS = ["", "ai_ml", "web3", "devtools", "fintech", "health", "open"];
const SORT_OPTIONS = ["total_score", "coding", "collaborating", "mentoring", "presenting", "networking", "helping"];

export default function LeaderboardPage() {
  const { role } = useAuth();
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("total_score");
  const [sortOrder, setSortOrder] = useState("desc");
  const [track, setTrack] = useState("");
  const [team, setTeam] = useState("");
  const [floor, setFloor] = useState<string>("");
  const [compareMode, setCompareMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [compareData, setCompareData] = useState<CompareParticipant[]>([]);

  const load = useCallback(async () => {
    const res = await api.get("/api/v1/scores/leaderboard", {
      params: {
        page,
        per_page: 50,
        sort_by: sortBy,
        sort_order: sortOrder,
        track: track || undefined,
        team: team || undefined,
        floor: floor === "" ? undefined : Number(floor),
      },
    });
    setEntries(res.data.data);
    setTotal(res.data.pagination?.total ?? res.data.total_participants ?? 0);
  }, [page, sortBy, sortOrder, track, team, floor]);

  useEffect(() => {
    load();
  }, [load]);

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else if (next.size < 3) next.add(id);
      return next;
    });
  };

  const runCompare = async () => {
    if (selected.size < 2) return;
    const ids = Array.from(selected).join(",");
    const res = await api.get("/api/v1/scores/compare", { params: { ids } });
    setCompareData(res.data.data.participants ?? []);
  };

  const activityColor = (activity?: string) => {
    const map: Record<string, string> = {
      coding: "bg-emerald-500",
      collaborating: "bg-blue-500",
      mentoring: "bg-orange-500",
      presenting: "bg-purple-500",
      networking: "bg-yellow-500",
    };
    return map[activity ?? ""] ?? "bg-slate-500";
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3 items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-100">Leaderboard</h1>
        <div className="flex gap-2">
          {role === "admin" && (
            <a
              href={`${import.meta.env.VITE_API_URL || ""}/api/v1/export/scores`}
              className="px-3 py-1 rounded-lg text-sm bg-slate-800 hover:bg-slate-700"
            >
              Export Scores CSV
            </a>
          )}
          <button
            type="button"
            onClick={() => setCompareMode((v) => !v)}
            className={`px-3 py-1 rounded-lg text-sm ${compareMode ? "bg-emerald-600" : "bg-slate-800"}`}
          >
            Compare {compareMode ? "ON" : "OFF"}
          </button>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-sm">
          {SORT_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select value={sortOrder} onChange={(e) => setSortOrder(e.target.value)} className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-sm">
          <option value="desc">Desc</option>
          <option value="asc">Asc</option>
        </select>
        <select value={track} onChange={(e) => setTrack(e.target.value)} className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-sm">
          <option value="">All tracks</option>
          {TRACKS.filter(Boolean).map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <select value={floor} onChange={(e) => setFloor(e.target.value)} className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-sm">
          <option value="">All floors</option>
          <option value="0">Ground</option>
          <option value="1">1st</option>
          <option value="2">2nd</option>
        </select>
        <input
          value={team}
          onChange={(e) => setTeam(e.target.value)}
          placeholder="Team search"
          className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-sm"
        />
      </div>
      <p className="text-sm text-slate-500">
        Showing {(page - 1) * 50 + 1}-{Math.min(page * 50, total)} of {total}
      </p>
      <div className="overflow-x-auto border border-slate-800 rounded-lg">
        <table className="w-full text-sm">
          <thead className="bg-slate-900 text-slate-400">
            <tr>
              {compareMode && <th className="p-2" />}
              <th className="p-2 text-left">Rank</th>
              <th className="p-2 text-left">Name</th>
              <th className="p-2 text-left">Team</th>
              <th className="p-2 text-left">Track</th>
              <th className="p-2 text-left">Score</th>
              <th className="p-2 text-left">Activity</th>
              <th className="p-2 text-left">Zone</th>
              <th className="p-2 text-left">Tags</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.participant_id} className="border-t border-slate-800 hover:bg-slate-900/50">
                {compareMode && (
                  <td className="p-2">
                    <input type="checkbox" checked={selected.has(e.participant_id)} onChange={() => toggleSelect(e.participant_id)} />
                  </td>
                )}
                <td className="p-2">{e.rank ?? "-"}</td>
                <td className="p-2">
                  <Link to={`/participant/${e.participant_id}`} className="text-emerald-400 hover:underline">
                    {e.name}
                  </Link>
                </td>
                <td className="p-2">{e.team_name}</td>
                <td className="p-2">{(e as LeaderboardEntry & { track?: string }).track ?? "-"}</td>
                <td className="p-2">{e.total_score.toFixed(0)}</td>
                <td className="p-2">
                  <span className={`inline-block w-2 h-2 rounded-full ${activityColor(e.current_activity)}`} /> {e.current_activity ?? "-"}
                </td>
                <td className="p-2">{e.current_zone ?? "-"}</td>
                <td className="p-2">{e.tags?.join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex gap-2">
        <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="px-3 py-1 bg-slate-800 rounded disabled:opacity-40">
          Prev
        </button>
        <button type="button" disabled={page * 50 >= total} onClick={() => setPage((p) => p + 1)} className="px-3 py-1 bg-slate-800 rounded disabled:opacity-40">
          Next
        </button>
        {compareMode && selected.size >= 2 && (
          <button type="button" onClick={runCompare} className="px-3 py-1 bg-emerald-600 rounded">
            Compare Selected
          </button>
        )}
      </div>
      {compareData.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 border border-slate-800 rounded-lg p-4">
          {compareData.map((p) => (
            <div key={p.id}>
              <h3 className="font-semibold text-slate-200">{p.name}</h3>
              <p className="text-xs text-slate-500 mb-2">{p.tags.join(", ")}</p>
              <RadarChart data={p.radar_data} size="sm" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
