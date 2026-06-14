import { useEffect, useState } from "react";
import { api } from "../utils/api";
import { useWebSocket } from "../hooks/useWebSocket";
import { HeatmapOverlay } from "../components/HeatmapOverlay";
import { ZoneSidebar } from "../components/ZoneSidebar";
import { EnergyGraph } from "../components/EnergyGraph";
import type { FloorPlan, HeatmapMessage, HeatmapSnapshot, ZoneDefinition } from "../types";

export default function HeatmapPage() {
  const [floors, setFloors] = useState<FloorPlan[]>([]);
  const [activeFloor, setActiveFloor] = useState(0);
  const [zones, setZones] = useState<ZoneDefinition[]>([]);
  const [snapshot, setSnapshot] = useState<HeatmapSnapshot | null>(null);
  const [energyPoints, setEnergyPoints] = useState<{ timestamp: string; energy: number }[]>([]);
  const [selectedZone, setSelectedZone] = useState<string | null>(null);

  const { lastMessage } = useWebSocket<HeatmapMessage>("/ws/heatmap", true, (msg) => {
    setSnapshot(msg.data);
  });

  useEffect(() => {
    if (lastMessage?.data) setSnapshot(lastMessage.data);
  }, [lastMessage]);

  useEffect(() => {
    api.get("/api/v1/venues/floors").then((res) => {
      const list = res.data.data.floors as FloorPlan[];
      setFloors(list);
      if (list.length) setActiveFloor(list[0].floor);
    });
    api.get("/api/v1/analytics/heatmap").then((res) => setSnapshot(res.data.data));
    const to = new Date();
    const from = new Date(to.getTime() - 2 * 60 * 60 * 1000);
    api
      .get("/api/v1/analytics/energy", {
        params: { from: from.toISOString(), to: to.toISOString(), interval: 5 },
      })
      .then((res) => setEnergyPoints(res.data.data.points ?? []));
  }, []);

  useEffect(() => {
    api.get("/api/v1/zones", { params: { floor: activeFloor } }).then((res) => {
      setZones(res.data.data ?? []);
    });
  }, [activeFloor]);

  const floorPlan = floors.find((f) => f.floor === activeFloor);

  const handleZoneClick = (name: string) => {
    setSelectedZone(name);
    const el = document.getElementById(`zone-row-${name.replace(/\s+/g, "-")}`);
    el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-slate-100">Heatmap</h1>
      <div className="flex gap-2">
        {floors.map((f) => (
          <button
            key={f.floor}
            type="button"
            onClick={() => setActiveFloor(f.floor)}
            className={`px-3 py-1 rounded-lg text-sm ${
              activeFloor === f.floor ? "bg-emerald-600 text-white" : "bg-slate-800 text-slate-400"
            }`}
          >
            {f.name}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
        <div className="xl:col-span-3">
          {floorPlan && (
            <HeatmapOverlay
              floorPlanUrl={floorPlan.image_url}
              zones={zones}
              snapshot={snapshot}
              selectedZone={selectedZone}
              onZoneClick={handleZoneClick}
            />
          )}
        </div>
        <ZoneSidebar
          zones={zones}
          snapshot={snapshot}
          selectedZone={selectedZone}
          onZoneClick={handleZoneClick}
        />
      </div>
      <EnergyGraph points={energyPoints} />
    </div>
  );
}
