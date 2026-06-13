export interface AuthUser {
  token: string;
  role: string;
}

export interface Participant {
  id: string;
  name: string;
  email?: string;
  team_name: string;
  track: string;
  skills?: string[];
  embedding_id?: number;
  registered_at: string;
}

export interface ApiError {
  error: string;
  code: string;
}

export interface PaginationMeta {
  page: number;
  per_page: number;
  total: number;
}
