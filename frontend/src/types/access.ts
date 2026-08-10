export type AccessTool   = "RDP" | "SSH" | "VNC" | "TeamViewer" | "Other";
export type SessionStatus = "active" | "closed";

export interface AccessSession {
  id:            string;
  user_id:       string;
  user:          string;
  role:          string;
  server:        string;
  ip:            string;
  tool:          AccessTool;
  reason:        string;
  client:        string;
  start:         string;
  end:           string | null;
  duration_min:  number | null;
  status:        SessionStatus;
  notes:         string;
  is_suspicious: boolean;
}

export interface CreateSessionPayload {
  server:   string;
  ip:       string;
  tool:     AccessTool;
  reason:   string;
  client:   string;
  engineer: string;
}
