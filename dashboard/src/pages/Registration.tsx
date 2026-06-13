import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, parseApiError } from "../utils/api";
import { CameraCapture } from "../components/CameraCapture";
import { SkillsInput } from "../components/SkillsInput";

const TRACKS = [
  { value: "ai_ml", label: "AI/ML" },
  { value: "web3", label: "Web3" },
  { value: "devtools", label: "DevTools" },
  { value: "fintech", label: "FinTech" },
  { value: "health", label: "Health" },
  { value: "open", label: "Open" },
];

export default function RegistrationPage() {
  const [photoBlob, setPhotoBlob] = useState<Blob | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [teamName, setTeamName] = useState("");
  const [track, setTrack] = useState("ai_ml");
  const [skills, setSkills] = useState<string[]>([]);
  const [consent, setConsent] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: countData, refetch: refetchCount } = useQuery({
    queryKey: ["participant-count"],
    queryFn: async () => {
      const res = await api.get("/api/v1/participants?count_only=true");
      return res.data.data.count as number;
    },
    refetchInterval: 10000,
  });

  const resetForm = () => {
    setPhotoBlob(null);
    setName("");
    setEmail("");
    setTeamName("");
    setTrack("ai_ml");
    setSkills([]);
    setConsent(false);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    if (!name || !teamName) {
      setError("Missing fields");
      return;
    }
    if (!photoBlob) {
      setError("Please capture a photo first");
      return;
    }
    if (!consent) {
      setError("Consent must be confirmed");
      return;
    }
    const form = new FormData();
    form.append("photo", photoBlob, "photo.jpg");
    form.append("name", name);
    form.append("email", email);
    form.append("team_name", teamName);
    form.append("track", track);
    form.append("skills", skills.join(","));
    form.append("consent_confirmed", "true");
    try {
      const res = await api.post("/api/v1/register", form);
      const registered = res.data.data;
      await refetchCount();
      setSuccess(`Registered: ${registered.name}. Total registered: ${countData ?? "?"}.`);
      resetForm();
    } catch (err) {
      const msg = parseApiError(err);
      if (msg.toLowerCase().includes("face")) setError("No face detected");
      else if (msg.toLowerCase().includes("already")) setError("Already registered");
      else setError(msg);
    }
  };

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Registration</h1>
        <span className="text-sm text-slate-400 bg-slate-800 px-3 py-1 rounded-full">
          Total: {countData ?? "…"}
        </span>
      </div>
      <p className="text-slate-500 text-sm mb-4">
        Verify participant physical ID before capturing face.
      </p>
      {success && <p className="mb-4 p-3 bg-emerald-900/50 text-emerald-300 rounded-lg">{success}</p>}
      {error && <p className="mb-4 p-3 bg-red-900/50 text-red-300 rounded-lg">{error}</p>}
      <form onSubmit={submit} className="space-y-4">
        <CameraCapture onCapture={setPhotoBlob} />
        <input
          required
          placeholder="Name *"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg"
        />
        <input
          placeholder="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg"
        />
        <input
          required
          placeholder="Team name *"
          value={teamName}
          onChange={(e) => setTeamName(e.target.value)}
          className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg"
        />
        <select
          value={track}
          onChange={(e) => setTrack(e.target.value)}
          className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg"
        >
          {TRACKS.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
        <SkillsInput skills={skills} onChange={setSkills} />
        <label className="flex items-start gap-2 text-sm text-slate-300">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-1" />
          Participant informed about camera tracking. Consent confirmed.
        </label>
        <button type="submit" className="w-full py-3 bg-emerald-600 hover:bg-emerald-500 rounded-lg font-medium">
          Register
        </button>
      </form>
    </div>
  );
}
