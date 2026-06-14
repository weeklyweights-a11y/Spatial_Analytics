export interface ApiError {
  error: string;
  code?: string;
}

export interface LeaderboardEntry {
  participant_id: string;
  name: string;
  team_name: string;
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
