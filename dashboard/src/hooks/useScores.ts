import { useQuery } from "@tanstack/react-query";
import { api } from "../utils/api";
import type { ScoreDetail } from "../types";

export function useScoreDetail(participantId: string | null) {
  return useQuery({
    queryKey: ["score", participantId],
    queryFn: async () => {
      const res = await api.get<{ data: ScoreDetail }>(`/api/v1/scores/${participantId}`);
      return res.data.data;
    },
    enabled: !!participantId,
    staleTime: 30000,
  });
}

export function useScoreTimeline(participantId: string | null) {
  return useQuery({
    queryKey: ["score-timeline", participantId],
    queryFn: async () => {
      const res = await api.get(`/api/v1/scores/${participantId}/timeline`);
      return res.data.data.timeline as Array<{
        hour: string;
        zone: string;
        primary_activity: string;
        minutes: number;
      }>;
    },
    enabled: !!participantId,
    staleTime: 30000,
  });
}

export function useCameras() {
  return useQuery({
    queryKey: ["cameras"],
    queryFn: async () => {
      const res = await api.get("/api/v1/cameras");
      return res.data.data as {
        cameras: Array<{ id: string; name: string; floor: number }>;
        by_floor: Record<string, unknown[]>;
      };
    },
    staleTime: 30000,
  });
}
