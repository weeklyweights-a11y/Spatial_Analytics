import { useQuery } from "@tanstack/react-query";
import { api } from "../utils/api";
import type { SponsorListItem, SponsorReportData } from "../types";

export function useSponsors() {
  return useQuery({
    queryKey: ["sponsors"],
    queryFn: async () => {
      const res = await api.get<{ data: SponsorListItem[] }>("/api/v1/sponsors");
      return res.data.data;
    },
    staleTime: 60000,
  });
}

export function useSponsorReport(sponsorId: string | null) {
  return useQuery({
    queryKey: ["sponsor-report", sponsorId],
    queryFn: async () => {
      const res = await api.get<{ data: SponsorReportData }>(`/api/v1/sponsors/${sponsorId}/report`);
      return res.data.data;
    },
    enabled: !!sponsorId,
    staleTime: 60000,
  });
}

export function useParticipantSponsorVisits(participantId: string | null) {
  return useQuery({
    queryKey: ["sponsor-visits", participantId],
    queryFn: async () => {
      const res = await api.get(`/api/v1/participants/${participantId}/sponsor-visits`);
      return res.data.data as Array<{
        sponsor_name: string;
        visit_number: number;
        entered_at: string;
        exited_at: string | null;
        dwell_seconds: number | null;
      }>;
    },
    enabled: !!participantId,
  });
}

export function useParticipantZoneHistory(participantId: string | null) {
  return useQuery({
    queryKey: ["zone-history", participantId],
    queryFn: async () => {
      const res = await api.get(`/api/v1/participants/${participantId}/zone-history`);
      return res.data.data as {
        zones: Array<{ zone: string; zone_type: string; minutes: number }>;
        floor_totals_hours: Record<string, number>;
        distinct_coding_zones_visited: number;
      };
    },
    enabled: !!participantId,
  });
}
