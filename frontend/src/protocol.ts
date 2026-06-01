// Memory Rhythm — WebSocket + REST protocol types.
//
// This file mirrors backend/app/schemas.py EXACTLY: every field name is
// byte-for-byte identical. All user-facing string content is Korean.

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

export type DementiaType = "alzheimer" | "vascular" | "lewy";
export type RecallStatus = "unrecalled" | "recalled";
export type IntervalStage = 1 | 3 | 7 | 21;

// Stage labels (1 -> 정서 안정화, 2 -> 대화형 인출, 3 -> 행동 수행)
export const STAGE_LABELS: Record<number, string> = {
  1: "정서 안정화",
  2: "대화형 인출",
  3: "행동 수행",
};

export function stageLabel(stage: number): string {
  return STAGE_LABELS[stage] ?? "";
}

// Model-name constants (centralized; mock ignores them).
export const REASONING_MODEL = "gpt-4o";
export const DIALOGUE_MODEL = "gpt-4o-mini";

// ---------------------------------------------------------------------------
// Core data shapes (REST + embedded in WS payloads)
// ---------------------------------------------------------------------------

export interface Patient {
  id: string;
  name: string;
  dementia_type: DementiaType;
  persona_profile: string;
  created_at: string;
}

export interface Memory {
  id: string;
  patient_id: string;
  text: string;
  keywords: string[];
  recall_status: RecallStatus;
  created_at: string;
}

export interface AutobiographyPage {
  id: string;
  patient_id: string;
  session_id: string;
  image_url: string;
  narrative: string;
  order_idx: number;
}

export interface RecallItem {
  id: string;
  memory_id: string;
  text: string;
  due_at: string;
  interval_stage: IntervalStage;
}

export interface CaregiverIntake {
  patient_id: string;
  structured: Record<string, unknown>;
}

// The 두뇌 (reasoner) decision attached to a `reasoning` WS message.
export interface ReasoningDecision {
  stage: number;
  next_stage: number;
  hint_level: number;
  recall_detected: boolean;
  keywords: string[];
  reason: string;
}

export interface CommunityTurn {
  persona: string;
  text: string;
}

// ---------------------------------------------------------------------------
// WebSocket: Client -> Server
// ---------------------------------------------------------------------------

export interface StartSession {
  type: "start_session";
  patient_id: string;
}

export interface UserMessage {
  type: "user_message";
  text: string;
}

export interface AdvanceTime {
  type: "advance_time";
  days: number;
}

export interface ToggleTone {
  type: "toggle_tone";
  on: boolean;
}

export type ClientMessage =
  | StartSession
  | UserMessage
  | AdvanceTime
  | ToggleTone;

// ---------------------------------------------------------------------------
// WebSocket: Server -> Client
// ---------------------------------------------------------------------------

export interface ReasoningMsg {
  type: "reasoning";
  decision: ReasoningDecision;
  latency_ms: number;
  model: string;
}

export interface StageChange {
  type: "stage_change";
  stage: number;
  label: string;
}

export interface AssistantMessage {
  type: "assistant_message";
  text: string;
  stage: number;
  hint_level: number;
}

export interface AutobiographyPageMsg {
  type: "autobiography_page";
  page: AutobiographyPage;
}

export interface RecallPrompt {
  type: "recall_prompt";
  text: string;
  memory_id: string;
}

export interface AudioMsg {
  type: "audio";
  format: "mp3";
  b64: string;
}

export interface ErrorMsg {
  type: "error";
  message: string;
}

export type ServerMessage =
  | ReasoningMsg
  | StageChange
  | AssistantMessage
  | AutobiographyPageMsg
  | RecallPrompt
  | AudioMsg
  | ErrorMsg;

// ---------------------------------------------------------------------------
// STEP 1 — Survey (초기 설문) data shapes
// ---------------------------------------------------------------------------
// The survey is a patient-facing conversational onboarding that SETS THE USER'S
// CONTEXT for the therapy flow. It uses its OWN WS endpoint
// (`/ws/survey/{session_id}`) and its OWN message unions — entirely separate
// from the therapy ClientMessage/ServerMessage above.

// `preface` = optional warm persona reaction to the previous answer ("" on the
// very first question).
export interface SurveyQuestionData {
  index: number;
  total: number;
  domain: string;
  text: string;
  preface: string;
}

export interface SurveyResult {
  patient_id: string;
  name: string;
  dementia_type: DementiaType;
  // profile = {name, era, dementia_type, domains:{domainKey: answerText},
  //            recallable_keywords:[...], unrecallable_topics:[...], summary}
  profile: Record<string, unknown>;
  // ranked by frequency desc then first-seen, deduped
  recallable_keywords: string[];
  // human labels of domains the patient could not recall
  unrecallable_topics: string[];
  // 2-3 sentence Korean narrative profile
  summary: string;
  seeded_memory_count: number;
  completed_at: string;
}

// ---------------------------------------------------------------------------
// Survey WebSocket: Client -> Server
// ---------------------------------------------------------------------------

export interface StartSurvey {
  type: "start_survey";
  patient_id: string | null;
  name: string;
  dementia_type: DementiaType;
}

export interface SurveyAnswer {
  type: "survey_answer";
  text: string;
}

export interface SkipQuestion {
  type: "skip_question";
}

export type SurveyClientMessage =
  | StartSurvey
  | SurveyAnswer
  | SkipQuestion;

// ---------------------------------------------------------------------------
// Survey WebSocket: Server -> Client
// ---------------------------------------------------------------------------

// Tier-1 extraction result for the PREVIOUS answer (not on the first turn).
export interface SurveyCaptureMsg {
  type: "survey_capture";
  domain: string;
  answer: string;
  keywords: string[];
  recallable: boolean;
}

export interface SurveyQuestionMsg {
  type: "survey_question";
  index: number;
  total: number;
  domain: string;
  text: string;
  preface: string;
}

export interface SurveyCompleteMsg {
  type: "survey_complete";
  result: SurveyResult;
}

// NOTE: `ErrorMsg` (type="error") is reused from the therapy union above.
export type SurveyServerMessage =
  | SurveyCaptureMsg
  | SurveyQuestionMsg
  | SurveyCompleteMsg
  | ErrorMsg;

// ---------------------------------------------------------------------------
// REST request / response bodies
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: "ok";
  provider: string;
  store: string;
}

export interface CreatePatientRequest {
  name: string;
  dementia_type: DementiaType;
}

export interface CaregiverIntakeRequest {
  patient_id: string;
  structured: Record<string, unknown>;
}

export interface OkResponse {
  ok: true;
}

export interface CommunitySimulateRequest {
  patient_id: string;
  topic: string;
}

export interface CommunitySimulateResponse {
  turns: CommunityTurn[];
}

export interface SttResponse {
  text: string;
}
