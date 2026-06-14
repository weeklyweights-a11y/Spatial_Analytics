interface EnergyLevelBarProps {
  energyLevel: number;
  totalActive?: number;
  totalRegistered?: number;
}

export function EnergyLevelBar({ energyLevel, totalActive, totalRegistered }: EnergyLevelBarProps) {
  const pct = Math.round(Math.min(1, Math.max(0, energyLevel)) * 100);
  return (
    <div className="bg-slate-900 rounded-lg border border-slate-800 p-3">
      <h3 className="text-sm font-semibold text-slate-300 mb-2">Venue Energy</h3>
      <div className="h-3 bg-slate-800 rounded-full overflow-hidden">
        <div className="h-full bg-emerald-500 transition-all duration-500" style={{ width: `${pct}%` }} />
      </div>
      <p className="text-xs text-slate-500 mt-1">
        {pct}% active
        {totalActive !== undefined && totalRegistered !== undefined
          ? ` (${totalActive}/${totalRegistered} participants)`
          : ""}
      </p>
    </div>
  );
}
