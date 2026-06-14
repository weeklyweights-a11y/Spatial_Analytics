interface EnergyLevelBarProps {
  occupancy: number;
  capacity: number;
}

export function EnergyLevelBar({ occupancy, capacity }: EnergyLevelBarProps) {
  const pct = capacity > 0 ? Math.min(100, Math.round((occupancy / capacity) * 100)) : 0;
  return (
    <div className="bg-slate-900 rounded-lg border border-slate-800 p-3">
      <h3 className="text-sm font-semibold text-slate-300 mb-2">Venue Energy</h3>
      <div className="h-3 bg-slate-800 rounded-full overflow-hidden">
        <div className="h-full bg-emerald-500 transition-all" style={{ width: `${pct}%` }} />
      </div>
      <p className="text-xs text-slate-500 mt-1">
        {occupancy} / {capacity} zone capacity ({pct}%)
      </p>
    </div>
  );
}
