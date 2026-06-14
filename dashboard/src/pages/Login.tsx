import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, parseApiError } from "../utils/api";
import { useAuth } from "../hooks/useAuth";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const { setAuth } = useAuth();
  const navigate = useNavigate();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const res = await api.post("/api/v1/auth/login", { username, password });
      const { token, role } = res.data.data;
      setAuth(token, role);
      navigate(role === "viewer" ? "/leaderboard" : "/cctv-wall");
    } catch (err) {
      setError(parseApiError(err));
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 bg-slate-900 p-8 rounded-xl border border-slate-800">
        <h1 className="text-2xl font-bold text-center text-emerald-400">SpatialScore</h1>
        <p className="text-slate-400 text-center text-sm">Organizer login</p>
        {error && <p className="text-red-400 text-sm text-center">{error}</p>}
        <input
          type="text"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg"
          required
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg"
          required
        />
        <button type="submit" className="w-full py-2 bg-emerald-600 hover:bg-emerald-500 rounded-lg font-medium">
          Login
        </button>
      </form>
    </div>
  );
}
