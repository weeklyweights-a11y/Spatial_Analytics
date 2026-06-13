import { useEffect, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useAppStore } from "../stores/appStore";
import { setAuthToken } from "../utils/api";

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const token = useAppStore((s) => s.token);
  const logout = useAppStore((s) => s.logout);
  const navigate = useNavigate();

  useEffect(() => {
    if (token) {
      setAuthToken(token);
    }
  }, [token]);

  useEffect(() => {
    const handler = () => {
      logout();
      navigate("/login");
    };
    window.addEventListener("spatialscore:unauthorized", handler);
    return () => window.removeEventListener("spatialscore:unauthorized", handler);
  }, [logout, navigate]);

  return <>{children}</>;
}
