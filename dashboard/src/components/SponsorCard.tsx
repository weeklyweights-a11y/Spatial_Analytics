import type { SponsorListItem } from "../types";

interface SponsorCardProps {
  sponsor: SponsorListItem;
  selected: boolean;
  onSelect: () => void;
}

const TIER_COLORS: Record<string, string> = {
  gold: "bg-amber-600",
  silver: "bg-slate-400",
  bronze: "bg-orange-700",
};

export function SponsorCard({ sponsor, selected, onSelect }: SponsorCardProps) {
  const tierClass = TIER_COLORS[sponsor.tier ?? ""] ?? "bg-slate-600";
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full text-left p-4 rounded-lg border transition ${
        selected ? "border-emerald-500 bg-slate-900" : "border-slate-800 bg-slate-950 hover:border-slate-600"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold text-slate-100">{sponsor.name}</span>
        {sponsor.tier && (
          <span className={`text-xs px-2 py-0.5 rounded text-white capitalize ${tierClass}`}>{sponsor.tier}</span>
        )}
      </div>
      <p className="text-sm text-slate-400 mt-1">{sponsor.booth_zone ?? "No booth"}</p>
      <p className="text-sm text-emerald-400 mt-2">{sponsor.unique_visitors} unique visitors</p>
    </button>
  );
}
