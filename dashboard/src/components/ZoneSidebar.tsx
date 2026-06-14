import type { HeatmapSnapshot, ZoneDefinition } from "../types";

interface ZoneSidebarProps {
  zones: ZoneDefinition[];
  snapshot: HeatmapSnapshot | null;
  selectedZone: string | null;
  onZoneClick: (name: string) => void;
}

export function ZoneSidebar({ zones, snapshot, selectedZone, onZoneClick }: ZoneSidebarProps) {
  return (
    <div className="bg-slate-900 rounded-lg border border-slate-800 p-3 space-y-2 max-h-[520px] overflow-y-auto">
      <h3 className="text-sm font-semibold text-slate-300 mb-2">Zones</h3>
      {zones.map((zone) => {
        const occ = snapshot?.zones[zone.name];
        const count = occ?.count ?? 0;
        const capacity = occ?.capacity ?? zone.capacity;
        const pct = occ?.pct ?? 0;
        const selected = selectedZone === zone.name;
        return (
          <button
            key={zone.id}
            id={`zone-row-${zone.name.replace(/\s+/g, "-")}`}
            type="button"
            onClick={() => onZoneClick(zone.name)}
            className={`w-full text-left p-2 rounded-lg border ${
              selected ? "border-emerald-500 bg-emerald-500/10" : "border-slate-800 hover:bg-slate-800"
            }`}
          >
            <div className="flex justify-between text-sm text-slate-200">
              <span>{zone.name}</span>
              <span>
                {count}/{capacity}
              </span>
            </div>
            <div className="h-2 bg-slate-800 rounded-full mt-1 overflow-hidden">
              <div className="h-full bg-emerald-500 transition-all" style={{ width: `${Math.min(100, pct)}%` }} />
            </div>
          </button>
        );
      })}
    </div>
  );
}
