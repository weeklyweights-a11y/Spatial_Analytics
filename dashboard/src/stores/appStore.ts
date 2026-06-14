import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import { setAuthToken } from "../utils/api";

interface AppState {
  token: string | null;
  role: string | null;
  setAuth: (token: string, role: string) => void;
  logout: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      token: null,
      role: null,
      setAuth: (token, role) => {
        setAuthToken(token);
        set({ token, role });
      },
      logout: () => {
        setAuthToken(null);
        set({ token: null, role: null });
      },
    }),
    {
      name: "spatialscore-auth",
      storage: createJSONStorage(() => sessionStorage),
    }
  )
);
