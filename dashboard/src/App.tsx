import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { AuthProvider } from "./providers/AuthProvider";
import { useAuth } from "./hooks/useAuth";
import LoginPage from "./pages/Login";
import CCTVWallPage from "./pages/CCTVWall";
import LeaderboardPage from "./pages/Leaderboard";
import HeatmapPage from "./pages/Heatmap";
import AnalyticsPage from "./pages/Analytics";
import SponsorReportsPage from "./pages/SponsorReports";
import RegistrationPage from "./pages/Registration";
import SettingsPage from "./pages/Settings";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="/cctv-wall" replace />} />
          <Route path="cctv-wall" element={<CCTVWallPage />} />
          <Route path="leaderboard" element={<LeaderboardPage />} />
          <Route path="heatmap" element={<HeatmapPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="sponsors" element={<SponsorReportsPage />} />
          <Route path="registration" element={<RegistrationPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </AuthProvider>
  );
}
