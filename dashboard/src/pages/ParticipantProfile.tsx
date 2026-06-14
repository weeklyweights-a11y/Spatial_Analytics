import { Link, Navigate, useParams } from "react-router-dom";
import { ActivityTimeline } from "../components/ActivityTimeline";
import { RadarChart } from "../components/RadarChart";
import { useScoreDetail } from "../hooks/useScores";
import { useAuth } from "../hooks/useAuth";
import { useWebSocket } from "../hooks/useWebSocket";
import { useParticipantSponsorVisits, useParticipantZoneHistory } from "../hooks/useSponsors";
import type { ParticipantUpdateMessage } from "../types";

export default function ParticipantProfilePage() {
  const { id } = useParams<{ id: string }>();
  const { role } = useAuth();
  const { data, isLoading } = useScoreDetail(id ?? null);
  const { lastMessage } = useWebSocket<ParticipantUpdateMessage>(
    id ? `/ws/participant/${id}` : "",
    !!id && (role === "admin" || role === "operator")
  );
  const { data: sponsorVisits } = useParticipantSponsorVisits(id ?? null);
  const { data: zoneHistory } = useParticipantZoneHistory(id ?? null);

  if (role === "viewer") {
    return <Navigate to="/leaderboard" replace />;
  }

  if (isLoading || !data) {
    return <p className="text-slate-400">Loading profile...</p>;
  }

  const live = lastMessage;
  const score = live?.score ?? data.total_score;
  const rank = live?.rank ?? data.rank;

  return (
    <div className="max-w-4xl space-y-6">
      <Link to="/cctv-wall" className="text-sm text-emerald-400 hover:underline">
        Back to CCTV Wall
      </Link>
      <div className="flex gap-6 items-start">
        {data.photo_base64 && (
          <img src={data.photo_base64} alt="" className="w-24 h-24 rounded-full object-cover" />
        )}
        <div>
          <h1 className="text-2xl font-bold">{data.name}</h1>
          <p className="text-slate-400">
            {data.team_name} — {data.track}
          </p>
          <p className="mt-2 text-emerald-400 text-xl font-semibold">
            Score {score.toFixed(1)} · Rank #{rank ?? "-"}
          </p>
          <p className="text-sm text-slate-400">
            {live?.zone ?? data.current_zone} — {live?.activity ?? data.current_activity}
          </p>
        </div>
      </div>
      <RadarChart data={data.radar_data} />
      <div className="flex flex-wrap gap-2">
        {(live?.tags ?? data.tags).map((t) => (
          <span key={t} className="text-xs px-2 py-1 rounded bg-slate-800 text-emerald-300">
            {t}
          </span>
        ))}
      </div>
      <div>
        <h2 className="text-lg font-semibold mb-2">Activity breakdown</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-400 text-left">
              <th>Activity</th>
              <th>Minutes</th>
              <th>Points</th>
              <th>%</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(data.breakdown).map(([act, row]) => (
              <tr key={act} className="border-t border-slate-800">
                <td className="py-1 capitalize">{act}</td>
                <td>{row.minutes.toFixed(1)}</td>
                <td>{row.points.toFixed(1)}</td>
                <td>{row.percentage.toFixed(0)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {id && (
        <div>
          <h2 className="text-lg font-semibold mb-2">Activity timeline</h2>
          <ActivityTimeline participantId={id} />
        </div>
      )}
      {sponsorVisits && sponsorVisits.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-2">Sponsor visits</h2>
          <SponsorVisitsNarrative visits={sponsorVisits} />
        </div>
      )}
      {zoneHistory && (
        <div>
          <h2 className="text-lg font-semibold mb-2">Zones and floors</h2>
          <p className="text-sm text-slate-400 mb-2">
            Visited {zoneHistory.distinct_coding_zones_visited} distinct coding areas
          </p>
          <p className="text-sm text-slate-400 mb-3">
            Ground {zoneHistory.floor_totals_hours.ground ?? 0}h · First{" "}
            {zoneHistory.floor_totals_hours.first ?? 0}h · Second {zoneHistory.floor_totals_hours.second ?? 0}h
          </p>
          <ul className="text-sm space-y-1">
            {zoneHistory.zones.map((z) => (
              <li key={z.zone} className="text-slate-300">
                {z.zone} — {z.minutes} min
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function SponsorVisitsNarrative({
  visits,
}: {
  visits: Array<{
    sponsor_name: string;
    visit_number: number;
    entered_at: string;
    exited_at: string | null;
    dwell_seconds: number | null;
  }>;
}) {
  const bySponsor: Record<string, typeof visits> = {};
  for (const v of visits) {
    bySponsor[v.sponsor_name] = bySponsor[v.sponsor_name] ?? [];
    bySponsor[v.sponsor_name].push(v);
  }
  return (
    <div className="space-y-3 text-sm text-slate-300">
      {Object.entries(bySponsor).map(([name, rows]) => {
        const totalMin = rows.reduce((s, r) => s + (r.dwell_seconds ?? 0), 0) / 60;
        const parts = rows.map(
          (r, i) =>
            `${i === 0 ? "First" : i === 1 ? "Second" : "Third"} visit: ${new Date(r.entered_at).toLocaleTimeString()} (${Math.round((r.dwell_seconds ?? 0) / 60)} min)`
        );
        return (
          <p key={name}>
            Visited {name} {rows.length} time{rows.length === 1 ? "" : "s"} for a total of{" "}
            {Math.round(totalMin)} minutes. {parts.join(". ")}.
          </p>
        );
      })}
    </div>
  );
}
