// WebSocket client for the live session loop.
//
// The URL is built from window.location so the Vite dev proxy ("/ws" -> :8000,
// ws:true) handles routing transparently. In production behind a single host
// it Just Works too. Endpoint: ws://<host>/ws/session/{session_id}.

import type {
  ClientMessage,
  ServerMessage,
  DementiaType,
  SurveyClientMessage,
  SurveyServerMessage,
} from "../protocol";

export type ConnectionState = "idle" | "connecting" | "open" | "closed";

type MessageHandler = (msg: ServerMessage) => void;
type StateHandler = (state: ConnectionState) => void;

function buildWsUrl(sessionId: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  // Use the current host so the Vite proxy (and any reverse proxy) forwards it.
  return `${proto}//${window.location.host}/ws/session/${encodeURIComponent(
    sessionId
  )}`;
}

function buildSurveyWsUrl(sessionId: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/survey/${encodeURIComponent(
    sessionId
  )}`;
}

export class WSClient {
  private ws: WebSocket | null = null;
  private messageHandlers = new Set<MessageHandler>();
  private stateHandlers = new Set<StateHandler>();
  private _state: ConnectionState = "idle";

  get state(): ConnectionState {
    return this._state;
  }

  private setState(s: ConnectionState) {
    this._state = s;
    this.stateHandlers.forEach((h) => h(s));
  }

  /** Open a connection for the given session id. Closes any existing socket. */
  connect(sessionId: string): void {
    this.close();
    this.setState("connecting");
    const ws = new WebSocket(buildWsUrl(sessionId));
    this.ws = ws;

    ws.onopen = () => this.setState("open");
    ws.onclose = () => this.setState("closed");
    ws.onerror = () => {
      // onerror is followed by onclose; surface as closed for the UI.
      if (this._state !== "open") this.setState("closed");
    };
    ws.onmessage = (ev) => {
      let parsed: ServerMessage;
      try {
        parsed = JSON.parse(ev.data) as ServerMessage;
      } catch {
        return; // ignore non-JSON frames
      }
      this.messageHandlers.forEach((h) => h(parsed));
    };
  }

  /** Subscribe to inbound server messages. Returns an unsubscribe fn. */
  onMessage(cb: MessageHandler): () => void {
    this.messageHandlers.add(cb);
    return () => this.messageHandlers.delete(cb);
  }

  /** Subscribe to connection-state transitions. Returns an unsubscribe fn. */
  onState(cb: StateHandler): () => void {
    this.stateHandlers.add(cb);
    return () => this.stateHandlers.delete(cb);
  }

  /** Send a typed client message. No-op (with warning) if socket not open. */
  send(msg: ClientMessage): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    } else {
      console.warn("[WSClient] send dropped — socket not open", msg);
    }
  }

  close(): void {
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onclose = null;
      this.ws.onerror = null;
      this.ws.onmessage = null;
      try {
        this.ws.close();
      } catch {
        /* ignore */
      }
      this.ws = null;
    }
  }

  // --- typed convenience helpers (mirror the ClientMessage union) ---------

  startSession(patientId: string): void {
    this.send({ type: "start_session", patient_id: patientId });
  }

  sendUserMessage(text: string): void {
    this.send({ type: "user_message", text });
  }

  advanceTime(days: number): void {
    this.send({ type: "advance_time", days });
  }

  toggleTone(on: boolean): void {
    this.send({ type: "toggle_tone", on });
  }
}

// ---------------------------------------------------------------------------
// SurveySocket — separate client for the STEP 1 초기 설문 WS endpoint.
//
// Mirrors WSClient's lifecycle but is typed over the survey unions
// (SurveyClientMessage / SurveyServerMessage) and targets
// ws://<host>/ws/survey/{session_id}. It is intentionally a distinct class so
// the therapy WSClient is never broken or coupled to the survey protocol.
// ---------------------------------------------------------------------------

type SurveyMessageHandler = (msg: SurveyServerMessage) => void;

export class SurveySocket {
  private ws: WebSocket | null = null;
  private messageHandlers = new Set<SurveyMessageHandler>();
  private stateHandlers = new Set<StateHandler>();
  private _state: ConnectionState = "idle";

  get state(): ConnectionState {
    return this._state;
  }

  private setState(s: ConnectionState) {
    this._state = s;
    this.stateHandlers.forEach((h) => h(s));
  }

  /** Open a survey connection for the given session id. Closes any existing socket. */
  connect(sessionId: string): void {
    this.close();
    this.setState("connecting");
    const ws = new WebSocket(buildSurveyWsUrl(sessionId));
    this.ws = ws;

    ws.onopen = () => this.setState("open");
    ws.onclose = () => this.setState("closed");
    ws.onerror = () => {
      if (this._state !== "open") this.setState("closed");
    };
    ws.onmessage = (ev) => {
      let parsed: SurveyServerMessage;
      try {
        parsed = JSON.parse(ev.data) as SurveyServerMessage;
      } catch {
        return; // ignore non-JSON frames
      }
      this.messageHandlers.forEach((h) => h(parsed));
    };
  }

  /** Subscribe to inbound survey server messages. Returns an unsubscribe fn. */
  onMessage(cb: SurveyMessageHandler): () => void {
    this.messageHandlers.add(cb);
    return () => this.messageHandlers.delete(cb);
  }

  /** Subscribe to connection-state transitions. Returns an unsubscribe fn. */
  onState(cb: StateHandler): () => void {
    this.stateHandlers.add(cb);
    return () => this.stateHandlers.delete(cb);
  }

  /** Send a typed survey client message. No-op (with warning) if socket not open. */
  send(msg: SurveyClientMessage): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    } else {
      console.warn("[SurveySocket] send dropped — socket not open", msg);
    }
  }

  close(): void {
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onclose = null;
      this.ws.onerror = null;
      this.ws.onmessage = null;
      try {
        this.ws.close();
      } catch {
        /* ignore */
      }
      this.ws = null;
    }
  }

  // --- typed convenience helpers (mirror the SurveyClientMessage union) ----

  startSurvey(
    patientId: string | null,
    name: string,
    dementiaType: DementiaType
  ): void {
    this.send({
      type: "start_survey",
      patient_id: patientId,
      name,
      dementia_type: dementiaType,
    });
  }

  sendSurveyAnswer(text: string): void {
    this.send({ type: "survey_answer", text });
  }

  skipQuestion(): void {
    this.send({ type: "skip_question" });
  }
}
