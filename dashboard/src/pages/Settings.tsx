import { useEffect, useState } from "react";
import { api } from "../utils/api";
import { ZoneEditorCanvas } from "../components/ZoneEditorCanvas";
import type { ZoneDefinition } from "../types";

interface CameraOption {
  id: string;
  name?: string;
}

interface ScoringRow {
  activity: string;
  weight: number;
  min_dwell_seconds: number;
}

export default function SettingsPage() {
  const [tab, setTab] = useState<"zones" | "scoring">("zones");
  const [cameras, setCameras] = useState<CameraOption[]>([]);
  const [cameraId, setCameraId] = useState("");
  const [zones, setZones] = useState<ZoneDefinition[]>([]);
  const [cameraPoly, setCameraPoly] = useState<number[][]>([]);
  const [floorPoly, setFloorPoly] = useState<number[][]>([]);
  const [form, setForm] = useState({ name: "", zone_type: "coding", floor: 0, capacity: 50 });
  const [weights, setWeights] = useState<ScoringRow[]>([]);

  useEffect(() => {
    api.get("/api/v1/cameras").then((res) => {
      const cams = res.data.data.cameras as CameraOption[];
      setCameras(cams);
      if (cams[0]) setCameraId(cams[0].id);
    });
    api.get("/api/v1/config/scoring").then((res) => setWeights(res.data.data ?? []));
  }, []);

  useEffect(() => {
    if (!cameraId) return;
    api.get("/api/v1/zones", { params: { camera_id: cameraId } }).then((res) => setZones(res.data.data ?? []));
  }, [cameraId]);

  const saveZone = async () => {
    await api.post("/api/v1/zones", {
      ...form,
      camera_id: cameraId,
      polygon_coords: cameraPoly,
      floor_polygon: floorPoly.length ? floorPoly : cameraPoly,
    });
    setCameraPoly([]);
    setFloorPoly([]);
    const res = await api.get("/api/v1/zones", { params: { camera_id: cameraId } });
    setZones(res.data.data ?? []);
  };

  const saveWeights = async () => {
    await api.put("/api/v1/config/scoring", { weights });
    alert("Scoring weights saved. New weights apply on the next scoring cycle.");
  };

  const snapshotUrl = cameraId ? `/api/v1/cameras/${cameraId}/snapshot?t=${Date.now()}` : "";

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-slate-100">Settings</h1>
      <div className="flex gap-2">
        <button type="button" onClick={() => setTab("zones")} className={`px-3 py-1 rounded ${tab === "zones" ? "bg-emerald-600" : "bg-slate-800"}`}>
          Zone Editor
        </button>
        <button type="button" onClick={() => setTab("scoring")} className={`px-3 py-1 rounded ${tab === "scoring" ? "bg-emerald-600" : "bg-slate-800"}`}>
          Scoring Weights
        </button>
      </div>
      {tab === "zones" && (
        <div className="space-y-4">
          <select value={cameraId} onChange={(e) => setCameraId(e.target.value)} className="bg-slate-900 border border-slate-700 rounded px-2 py-1">
            {cameras.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name ?? c.id}
              </option>
            ))}
          </select>
          {snapshotUrl && (
            <div>
              <h3 className="text-sm text-slate-400 mb-2">Camera polygon</h3>
              <ZoneEditorCanvas imageUrl={snapshotUrl} points={cameraPoly} onChange={setCameraPoly} />
            </div>
          )}
          <div>
            <h3 className="text-sm text-slate-400 mb-2">Floor plan polygon (optional mapping)</h3>
            <ZoneEditorCanvas imageUrl="/static/venue/floor_0_ground.png" points={floorPoly} onChange={setFloorPoly} />
          </div>
          <div className="grid grid-cols-2 gap-2 max-w-lg">
            <input placeholder="Zone name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="bg-slate-900 border border-slate-700 rounded px-2 py-1" />
            <input placeholder="Zone type" value={form.zone_type} onChange={(e) => setForm({ ...form, zone_type: e.target.value })} className="bg-slate-900 border border-slate-700 rounded px-2 py-1" />
            <input type="number" placeholder="Floor" value={form.floor} onChange={(e) => setForm({ ...form, floor: Number(e.target.value) })} className="bg-slate-900 border border-slate-700 rounded px-2 py-1" />
            <input type="number" placeholder="Capacity" value={form.capacity} onChange={(e) => setForm({ ...form, capacity: Number(e.target.value) })} className="bg-slate-900 border border-slate-700 rounded px-2 py-1" />
          </div>
          <button type="button" onClick={saveZone} className="px-4 py-2 bg-emerald-600 rounded">
            Save Zone
          </button>
          <ul className="text-sm text-slate-400">
            {zones.map((z) => (
              <li key={z.id}>
                {z.name} ({z.zone_type}) — floor {z.floor}
              </li>
            ))}
          </ul>
        </div>
      )}
      {tab === "scoring" && (
        <div className="space-y-3 max-w-xl">
          <p className="text-sm text-amber-400">Changing weights applies on the next scoring cycle.</p>
          {weights.map((w, i) => (
            <div key={w.activity} className="flex gap-2 items-center">
              <span className="w-32 text-sm text-slate-300">{w.activity}</span>
              <input
                type="number"
                step="0.1"
                value={w.weight}
                onChange={(e) => {
                  const next = [...weights];
                  next[i] = { ...w, weight: Number(e.target.value) };
                  setWeights(next);
                }}
                className="bg-slate-900 border border-slate-700 rounded px-2 py-1 w-24"
              />
            </div>
          ))}
          <button type="button" onClick={saveWeights} className="px-4 py-2 bg-emerald-600 rounded">
            Save Weights
          </button>
        </div>
      )}
    </div>
  );
}
