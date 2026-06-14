import { useState } from "react";
import { useScoreTimeline } from "../hooks/useScores";
import type { TimelineBlock } from "../types";

const ACTIVITY_COLORS: Record<string, string> = {
  coding: "bg-emerald-600",
  collaborating: "bg-blue-600",
  mentoring: "bg-orange-600",
  presenting: "bg-purple-600",
  idle: "bg-slate-600",
  networking: "bg-cyan-600",
  sponsor_engagement: "bg-pink-600",
};

interface ActivityTimelineProps {
  participantId: string;
}

export function ActivityTimeline({ participantId }: ActivityTimelineProps) {
  const { data, isLoading } = useScoreTimeline(participantId);
  const [expanded, setExpanded] = useState<string | null>(null);

  if (isLoading) return <p className="text-slate-500">Loading timeline...</p>;
  if (!data?.length) return <p className="text-slate-500">No activity logged yet.</p>;

  return (
    <div className="space-y-2 max-h-96 overflow-y-auto">
      {data.map((block: TimelineBlock) => {
        const isOpen = expanded === block.hour;
        const subs = block.sub_activities ?? {};
        return (
          <div
            key={block.hour}
            className="p-3 rounded-lg bg-slate-900 border border-slate-800"
          >
            <button
              type="button"
              className="w-full text-left"
              onClick={() => setExpanded(isOpen ? null : block.hour)}
            >
              <div className="flex justify-between text-sm">
                <span className="font-medium text-slate-200">{block.hour}</span>
                <span className="text-slate-400">{block.minutes.toFixed(0)} min</span>
              </div>
              <p className="text-sm text-slate-400">
                {block.zone} — {block.primary_activity}
              </p>
            </button>
            {isOpen && Object.keys(subs).length > 0 && (
              <div className="mt-2 space-y-1">
                {Object.entries(subs).map(([act, mins]) => (
                  <div key={act} className="flex items-center gap-2 text-xs text-slate-300">
                    <div className={`h-2 rounded ${ACTIVITY_COLORS[act] ?? "bg-slate-600"}`} style={{ width: `${Math.min(100, mins)}%` }} />
                    <span className="capitalize">{act}</span>
                    <span>{mins.toFixed(0)} min</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
