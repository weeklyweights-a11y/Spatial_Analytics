import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../utils/api";
import { useAuth } from "../hooks/useAuth";

const NAV_ITEMS = [
  { to: "/cctv-wall", label: "CCTV Wall", roles: ["admin", "operator"] },
  { to: "/leaderboard", label: "Leaderboard", roles: ["admin", "operator", "viewer"] },
  { to: "/heatmap", label: "Heatmap", roles: ["admin", "operator", "viewer"] },
  { to: "/analytics", label: "Analytics", roles: ["admin", "operator"] },
  { to: "/sponsors", label: "Sponsors", roles: ["admin", "operator"] },
  { to: "/registration", label: "Registration", roles: ["admin", "operator"] },
  { to: "/settings", label: "Settings", roles: ["admin"] },
];

export function Layout() {
  const { role, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const isRegistrationTablet =
    location.pathname === "/registration" && typeof window !== "undefined" && window.innerWidth >= 768 && window.innerWidth < 1024;

  const handleLogout = async () => {
    try {
      await api.post("/api/v1/auth/logout");
    } catch {
      /* ignore */
    }
    logout();
    navigate("/login");
  };

  if (isRegistrationTablet) {
    return (
      <div className="min-h-screen p-4">
        <Outlet />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <aside className="hidden lg:flex w-56 flex-col bg-slate-900 border-r border-slate-800 p-4">
        <h1 className="text-xl font-bold text-emerald-400 mb-8">SpatialScore</h1>
        <nav className="flex flex-col gap-1 flex-1">
          {NAV_ITEMS.filter((item) => role && item.roles.includes(role)).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `px-3 py-2 rounded-lg text-sm ${isActive ? "bg-emerald-600/20 text-emerald-400" : "text-slate-400 hover:bg-slate-800"}`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <button onClick={handleLogout} className="text-sm text-slate-500 hover:text-slate-300 mt-4">
          Logout
        </button>
      </aside>
      <main className="flex-1 p-6 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
