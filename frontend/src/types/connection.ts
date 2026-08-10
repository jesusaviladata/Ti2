export type AuthMode   = "sql" | "windows";
export type EncryptMode = "Mandatory" | "Optional" | "Strict";

export interface SqlConnection {
  id:                    string;
  label:                 string;
  server:                string;   // "host,port" or "host"
  authMode:              AuthMode;
  username:              string;
  password:              string;
  database:              string;   // "<default>" = master
  encrypt:               EncryptMode;
  trustServerCertificate: boolean;
  createdAt:             string;
}

/** Shape sent to backend API calls */
export interface ConnectionPayload {
  server:     string;
  username:   string;
  password:   string;
  database?:  string;
  encrypt?:   string;
  trust_cert: boolean;
}
