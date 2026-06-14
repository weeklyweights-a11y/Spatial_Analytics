import { Link } from "react-router-dom";
import { useWebSocket } from "../hooks/useWebSocket";
import type { LeaderboardMessage } from "../types";

export function LiveLeaderboard() {
  const { lastMessage } = useWebSocket<LeaderboardMessage>("/ws/leaderboard", true);
  const entries = (lastMessage?.data ?? []).slice(0, 10);

  return (
    <div className="bg-slate-900 rounded-lg border border-slate-800 p-3">
      <div className="flex justify-between items-center mb-2">
        <h3 className="text-sm font-semibold text-slate-300">Top 10</h3>
        <Link to="/leaderboard" className="text-xs text-emerald-400 hover:underline">
          View All
        </Link>
      </div>
      <ul className="space-y-1 text-sm">
        {entries.map((e) => (
          <li key={e.participant_id} className="flex justify-between text-slate-300">
            <span>
              #{e.rank ?? "-"} {e.name}
            </span>
            <span className="text-emerald-400">{e.total_score.toFixed(0)}</span>
          </li>
        ))}
        {entries.length === 0 && <li className="text-slate-500">Waiting for scores...</li>}
      </ul>
    </div>
  );
}
