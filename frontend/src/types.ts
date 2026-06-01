// App-level type surface. Everything authoritative lives in the shared
// contract (protocol.ts); re-export it here so components can import from a
// single, stable module path ("../types") if they prefer.
export * from "./protocol";

// Convenience aliases used by the patient page / reasoning panel.
import type { ReasoningMsg } from "./protocol";

// A reasoning-chain log entry = the server `reasoning` message plus a local
// receive timestamp (ms epoch) so the panel can show ordering.
export interface ReasoningLogEntry extends ReasoningMsg {
  received_at: number;
}

// Connection lifecycle state for the WS client (surfaced in the UI).
export type ConnectionState = "idle" | "connecting" | "open" | "closed";
