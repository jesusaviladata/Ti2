export type FMProtocol = "sftp" | "ftp" | "ftps";

export interface FMConnection {
  id:        string;
  label:     string;
  host:      string;
  port:      number;
  protocol:  FMProtocol;
  username:  string;
  password:  string;
  /** Contenido PEM de la llave privada (AWS EC2, solo SFTP). Nunca se persiste. */
  privateKey?: string;
  passphrase?: string;
  createdAt: string;
}

export interface FileEntry {
  name:        string;
  size:        number;
  modified:    number | null;
  isDir:       boolean;
  permissions: string | null;
}

export interface FMListResponse {
  entries: FileEntry[];
  path:    string;
}

export type OpStatus = "pending" | "running" | "done" | "error";

export interface FMOperation {
  id:     string;
  label:  string;
  status: OpStatus;
  count?: number;
  error?: string;
  ts:     Date;
}

export interface StatusMessage {
  id:   string;
  text: string;
  kind: "info" | "success" | "error";
  ts:   Date;
}

export interface QuickRule {
  id:           string;
  label:        string;
  path:         string;
  type:         "contents" | "pattern";
  pattern?:     string;
}
