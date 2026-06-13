import { useAppStore } from "../stores/appStore";

export function useAuth() {
  const token = useAppStore((s) => s.token);
  const role = useAppStore((s) => s.role);
  const setAuth = useAppStore((s) => s.setAuth);
  const logout = useAppStore((s) => s.logout);
  return { token, role, setAuth, logout, isAuthenticated: !!token };
}
