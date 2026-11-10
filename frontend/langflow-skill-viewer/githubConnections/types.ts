export type Principal = { id: number; login: string };
export type Repository = { id: number; full_name: string; private: boolean };
export type PendingConnection = {
  request_id: string;
  connection_id: string;
  expires_at: number;
  phase: "authorize" | "consent";
  authorization_url: string | null;
  inventory: { principal: Principal; repositories: Repository[] } | null;
};
export type Connection = {
  id: string;
  generation: number;
  mode: "browser" | "token";
  principal: Principal;
  repositories: Repository[];
  state: "ready" | "reauthorization_required" | "revoked";
};
export type ConnectionIndex = {
  revision: number;
  callback_uri: string;
  app: { slug: string; client_id: string } | null;
  connections: {
    connection: Connection;
    availability: string;
    credential_cleanup_pending: boolean;
  }[];
  pending: PendingConnection[];
  credential_cleanup_pending: boolean;
};
export type ConnectionResult = { index: ConnectionIndex; outcome: unknown };
export type ConnectionAction =
  | "setup"
  | "begin"
  | "token"
  | "confirm"
  | "cancel"
  | "refresh"
  | "disconnect"
  | "cleanup";
