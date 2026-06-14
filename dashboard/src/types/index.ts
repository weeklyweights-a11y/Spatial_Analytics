export interface ApiError {
  error: string;
  code?: string;
}

export interface LeaderboardEntry {
  participant_id: string;
  name: string;
  team_name: string;
  track?: string;
  total_score: number;
  rank: number | null;
  current_activity?: string;
  current_zone?: string;
  tags: string[];
}

export interface LeaderboardMessage {
  type: "leaderboard";
  data: LeaderboardEntry[];
  total_participants: number;
  timestamp: string;
}

export interface TrackingPerson {
  track_id: number;
  participant_id: string | null;
  name: string;
  bbox: [number, number, number, number];
  activity: string;
  confidence: number;
  frame_width: number;
  frame_height: number;
}

export interface TrackingMessage {
  type: "tracking";
  camera_id: string;
  persons: TrackingPerson[];
  timestamp: string;
}

export interface ParticipantUpdateMessage {
  type: "participant_update";
  participant_id: string;
  name: string;
  zone?: string;
  activity?: string;
  score: number;
  rank: number | null;
  tags: string[];
  timestamp: string;
}

export interface RadarPoint {
  axis: string;
  value: number;
}

export interface ScoreDetail {
  participant_id: string;
  name: string;
  team_name: string;
  track: string;
  total_score: number;
  rank: number | null;
  tags: string[];
  current_zone?: string;
  current_activity?: string;
  photo_base64?: string;
  radar_data: RadarPoint[];
  breakdown: Record<string, { minutes: number; points: number; percentage: number }>;
  registered_at?: string;
  last_seen_at?: string;
}

export interface HeatmapZoneData {
  count: number;
  capacity: number;
  pct: number;
  floor: number;
}

export interface HeatmapSnapshot {
  zones: Record<string, HeatmapZoneData>;
  total_active: number;
  total_registered: number;
  energy_level: number;
  timestamp: string;
}

export interface HeatmapMessage {
  type: "heatmap";
  data: HeatmapSnapshot;
}

export interface AlertMessage {
  type: "alert";
  id: string;
  rule_name: string;
  severity: "info" | "warning" | "critical";
  message: string;
  zone?: string;
  floor?: number;
  timestamp: string;
}

export interface ZoneDefinition {
  id: string;
  name: string;
  zone_type: string;
  camera_id: string;
  polygon_coords: number[][];
  floor_polygon: number[][];
  floor: number;
  capacity: number;
}

export interface FloorPlan {
  floor: number;
  name: string;
  image_url: string;
}

export interface CompareParticipant {
  id: string;
  name: string;
  team_name: string;
  track: string;
  total_score: number;
  rank: number | null;
  tags: string[];
  radar_data: RadarPoint[];
  breakdown: Record<string, { minutes: number; points: number; percentage: number }>;
}

export interface SponsorListItem {
  id: string;
  name: string;
  tier: string | null;
  booth_zone: string | null;
  unique_visitors: number;
  logo_url: string | null;
}

export interface SponsorReportData {
  sponsor: {
    id: string;
    name: string;
    tier: string | null;
    booth_zone: string | null;
    logo_url: string | null;
  };
  metrics: {
    unique_visitors: number;
    total_visits: number;
    avg_dwell_seconds: number;
    median_dwell_seconds: number;
    return_visitors: number;
    return_rate_pct: number;
    peak_hour: string;
    total_dwell_minutes: number;
  };
  hourly_traffic: Array<{ hour: string; visitors: number; entries: number }>;
  visitor_breakdown: {
    by_track: Record<string, number>;
    by_floor: Record<string, number>;
  };
  top_visitors: Array<{
    participant_id: string;
    name: string;
    visits: number;
    total_dwell_minutes: number;
  }>;
}

export interface TimelineBlock {
  hour: string;
  zone: string;
  primary_activity: string;
  minutes: number;
  sub_activities?: Record<string, number>;
}
