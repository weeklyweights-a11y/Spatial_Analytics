import { useScoreTimeline } from "../hooks/useScores";

interface ActivityTimelineProps {
  participantId: string;
}

export function ActivityTimeline({ participantId }: ActivityTimelineProps) {
  const { data, isLoading } = useScoreTimeline(participantId);
  if (isLoading) return <p className="text-slate-500">Loading timeline...</p>;
  if (!data?.length) return <p className="text-slate-500">No activity logged yet.</p>;
  return (
    <div className="space-y-2 max-h-96 overflow-y-auto">
      {data.map((block) => (
        <div
          key={`${block.hour}-${block.primary_activity}`}
          className="p-3 rounded-lg bg-slate-900 border border-slate-800"
        >
          <div className="flex justify-between text-sm">
            <span className="font-medium text-slate-200">{block.hour}</span>
            <span className="text-slate-400">{block.minutes.toFixed(0)} min</span>
          </div>
          <p className="text-sm text-slate-400">
            {block.zone} — {block.primary_activity}
          </p>
        </div>
      ))}
    </div>
  );
}
