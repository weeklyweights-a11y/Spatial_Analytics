import { useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { AlertsFeed } from "../components/AlertsFeed";
import { AlertToastStack } from "../components/AlertToast";
import { CameraFeed } from "../components/CameraFeed";
import { ConnectionStatusBar } from "../components/ConnectionStatusBar";
import { EnergyLevelBar } from "../components/EnergyLevelBar";
import { LiveLeaderboard } from "../components/LiveLeaderboard";
import { ScoreCard } from "../components/ScoreCard";
import { useWebSocket } from "../hooks/useWebSocket";
import { useCameras } from "../hooks/useScores";
import { useAuth } from "../hooks/useAuth";
import type { AlertMessage, HeatmapMessage } from "../types";

export default function CCTVWallPage() {
  const { role } = useAuth();
  const { data: camerasData } = useCameras();
  const { connectionState: lbState } = useWebSocket("/ws/leaderboard", role === "admin" || role === "operator");
  const [toasts, setToasts] = useState<AlertMessage[]>([]);
  const [snapshot, setSnapshot] = useState<HeatmapMessage["data"] | null>(null);
  const [selected, setSelected] = useState<{ id: string; x: number; y: number } | null>(null);

  useWebSocket<HeatmapMessage>("/ws/heatmap", role === "admin" || role === "operator", (msg) => {
    setSnapshot(msg.data);
  });

  useWebSocket<AlertMessage>("/ws/alerts", role === "admin" || role === "operator", (msg) => {
    setToasts((prev) => [msg, ...prev].slice(0, 3));
  });

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

  return (
    <div className="flex flex-col h-full min-h-[calc(100vh-4rem)]">
      <ConnectionStatusBar state={lbState} />
      <AlertToastStack alerts={toasts} onDismiss={(id) => setToasts((t) => t.filter((a) => a.id !== id))} />
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
          <EnergyLevelBar
            energyLevel={snapshot?.energy_level ?? 0}
            totalActive={snapshot?.total_active}
            totalRegistered={snapshot?.total_registered}
          />
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
