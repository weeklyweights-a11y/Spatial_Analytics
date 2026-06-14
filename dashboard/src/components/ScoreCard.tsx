import { useEffect } from "react";
import { Link } from "react-router-dom";
import { useScoreDetail } from "../hooks/useScores";
import { useWebSocket } from "../hooks/useWebSocket";
import type { ParticipantUpdateMessage } from "../types";
import { RadarChart } from "./RadarChart";

interface ScoreCardProps {
  participantId: string;
  position: { x: number; y: number };
  onClose: () => void;
  onSwitch: (participantId: string) => void;
}

export function ScoreCard({ participantId, position, onClose, onSwitch }: ScoreCardProps) {
  const { data, refetch } = useScoreDetail(participantId);
  const { lastMessage } = useWebSocket<ParticipantUpdateMessage>(
    `/ws/participant/${participantId}`,
    !!participantId
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    if (lastMessage?.participant_id && lastMessage.participant_id !== participantId) {
      onSwitch(lastMessage.participant_id);
    }
  }, [lastMessage, participantId, onSwitch]);

  const live = lastMessage;
  const score = live?.score ?? data?.total_score ?? 0;
  const rank = live?.rank ?? data?.rank;
  const zone = live?.zone ?? data?.current_zone;
  const activity = live?.activity ?? data?.current_activity;
  const tags = live?.tags ?? data?.tags ?? [];

  const left = Math.min(position.x, window.innerWidth - 340);
  const top = Math.min(position.y, window.innerHeight - 420);

  return (
    <>
      <button type="button" className="fixed inset-0 z-40 cursor-default" aria-label="Close" onClick={onClose} />
      <div
        className="fixed z-50 w-80 bg-slate-900 border border-slate-700 rounded-xl shadow-xl p-4"
        style={{ left, top }}
        onClick={(e) => e.stopPropagation()}
      >
        {data?.photo_base64 && (
          <img src={data.photo_base64} alt="" className="w-16 h-16 rounded-full object-cover mb-2" />
        )}
        <h3 className="text-lg font-semibold text-white">{data?.name ?? "Loading..."}</h3>
        <p className="text-sm text-slate-400">{data?.team_name}</p>
        <p className="text-sm mt-2">
          {zone} — {activity}
        </p>
        <p className="text-2xl font-bold text-emerald-400 mt-2">
          {score.toFixed(1)} <span className="text-sm text-slate-400">Rank #{rank ?? "-"}</span>
        </p>
        {data?.radar_data && <RadarChart data={data.radar_data} size="sm" />}
        <div className="flex flex-wrap gap-1 mt-2">
          {tags.map((t) => (
            <span key={t} className="text-xs px-2 py-0.5 rounded bg-slate-800 text-emerald-300">
              {t}
            </span>
          ))}
        </div>
        <Link
          to={`/participant/${participantId}`}
          className="block mt-3 text-sm text-emerald-400 hover:underline"
          onClick={() => refetch()}
        >
          View Full Profile
        </Link>
      </div>
    </>
  );
}
