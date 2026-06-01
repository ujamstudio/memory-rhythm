// Typed fetch wrappers for the REST API (prefix /api). All paths are relative
// so the Vite dev proxy forwards them to the backend on :8000.

import type {
  AutobiographyPage,
  CaregiverIntakeRequest,
  CommunitySimulateResponse,
  CreatePatientRequest,
  HealthResponse,
  Memory,
  OkResponse,
  Patient,
  RecallItem,
  SttResponse,
  SurveyResult,
} from "../protocol";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    let detail = "";
    try {
      detail = await res.text();
    } catch {
      /* ignore */
    }
    throw new Error(`API ${path} 실패 (${res.status}): ${detail}`);
  }
  // 204 / empty body guard.
  const text = await res.text();
  return (text ? JSON.parse(text) : null) as T;
}

export const api = {
  // --- health ------------------------------------------------------------
  health(): Promise<HealthResponse> {
    return request<HealthResponse>("/health");
  },

  // --- patients ----------------------------------------------------------
  createPatient(body: CreatePatientRequest): Promise<Patient> {
    return request<Patient>("/patients", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  getPatient(id: string): Promise<Patient> {
    return request<Patient>(`/patients/${encodeURIComponent(id)}`);
  },

  getMemories(id: string): Promise<Memory[]> {
    return request<Memory[]>(`/patients/${encodeURIComponent(id)}/memories`);
  },

  getAutobiography(id: string): Promise<AutobiographyPage[]> {
    return request<AutobiographyPage[]>(
      `/patients/${encodeURIComponent(id)}/autobiography`
    );
  },

  getRecallQueue(id: string): Promise<RecallItem[]> {
    return request<RecallItem[]>(
      `/patients/${encodeURIComponent(id)}/recall-queue`
    );
  },

  // --- survey (STEP 1 초기 설문) ------------------------------------------
  // 404 if the patient has not completed a survey yet.
  getSurvey(patientId: string): Promise<SurveyResult> {
    return request<SurveyResult>(
      `/patients/${encodeURIComponent(patientId)}/survey`
    );
  },

  // --- caregiver ---------------------------------------------------------
  caregiverIntake(body: CaregiverIntakeRequest): Promise<OkResponse> {
    return request<OkResponse>("/caregiver/intake", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  // --- community ---------------------------------------------------------
  communitySimulate(
    patientId: string,
    topic: string
  ): Promise<CommunitySimulateResponse> {
    return request<CommunitySimulateResponse>("/community/simulate", {
      method: "POST",
      body: JSON.stringify({ patient_id: patientId, topic }),
    });
  },

  // --- speech-to-text (optional) -----------------------------------------
  // multipart upload; do NOT set Content-Type (browser sets boundary).
  async stt(audio: Blob, filename = "speech.webm"): Promise<SttResponse> {
    const form = new FormData();
    form.append("audio", audio, filename);
    const res = await fetch(`${BASE}/stt`, { method: "POST", body: form });
    if (!res.ok) {
      throw new Error(`STT 실패 (${res.status})`);
    }
    return (await res.json()) as SttResponse;
  },
};

export type Api = typeof api;
