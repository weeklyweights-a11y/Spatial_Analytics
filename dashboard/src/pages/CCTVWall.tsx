import { useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { AlertsFeed } from "../components/AlertsFeed";
import { CameraFeed } from "../components/CameraFeed";
import { ConnectionStatusBar } from "../components/ConnectionStatusBar";
import { EnergyLevelBar } from "../components/EnergyLevelBar";
import { LiveLeaderboard } from "../components/LiveLeaderboard";
import { ScoreCard } from "../components/ScoreCard";
import { useWebSocket } from "../hooks/useWebSocket";
import { useCameras } from "../hooks/useScores";
import { useAuth } from "../hooks/useAuth";

export default function CCTVWallPage() {
  const { role } = useAuth();
  const { data: camerasData } = useCameras();
  const { connectionState } = useWebSocket("/ws/leaderboard", role === "admin" || role === "operator");
  const [selected, setSelected] = useState<{ id: string; x: number; y: number } | null>(null);

  const cameras = camerasData?.cameras ?? [];
  const byFloor = useMemo(() => {
    const map: Record<number, typeof cameras> = {};
    for (const cam of cameras) {
      const floor = cam.floor ?? 0;
      map[floor] ??= [];
      map[floor].push(cam);
    }
    return map;
  }, [cameras]);

  if (role === "viewer") {
    return <Navigate to="/leaderboard" replace />;
  }

  const totalCapacity = cameras.length * 50;
  const occupancy = Math.min(totalCapacity, cameras.length * 8);

  return (
    <div className="flex flex-col h-full min-h-[calc(100vh-4rem)]">
      <ConnectionStatusBar state={connectionState} />
      <div className="flex flex-1 gap-4 p-2">
        <div className="flex-[7] overflow-y-auto">
          {Object.entries(byFloor).map(([floor, cams]) => (
            <div key={floor} className="mb-4">
              <h2 className="text-sm text-slate-400 mb-2">Floor {floor}</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                {cams.map((cam) => (
                  <CameraFeed
                    key={cam.id}
                    cameraId={cam.id}
                    cameraName={cam.name ?? cam.id}
                    onPersonClick={(id, x, y) => setSelected({ id, x, y })}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
        <aside className="flex-[3] space-y-3 min-w-[240px]">
          <LiveLeaderboard />
          <EnergyLevelBar occupancy={occupancy} capacity={totalCapacity || 1} />
          <AlertsFeed />
        </aside>
      </div>
      {selected && (
        <ScoreCard
          participantId={selected.id}
          position={{ x: selected.x, y: selected.y }}
          onClose={() => setSelected(null)}
          onSwitch={(id) => setSelected((s) => (s ? { ...s, id } : null))}
        />
      )}
    </div>
  );
}
