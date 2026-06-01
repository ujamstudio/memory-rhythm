// Caregiver.tsx — 보호자 포털.
// Composes IntakeForm + MemoryGraph + RecallQueue around a selected patient.
// A patient-id field (defaulting to the demo patient) drives all three panels.
//
// Time-acceleration: the Patient page owns the live WS session. The caregiver
// portal does NOT hold that socket, so its "시간 가속" buttons operate in demo
// mode (REST refetch of the recall queue). If a future integration shares a WS
// session here, pass an `onAdvanceTime` to RecallQueue and flip `wsConnected`.

import { useEffect, useState } from "react";
import type { Patient } from "../protocol";
import { api } from "../lib/api";
import IntakeForm from "../components/IntakeForm";
import MemoryGraph from "../components/MemoryGraph";
import RecallQueue from "../components/RecallQueue";

// The backend auto-creates a demo patient under this id (start_session with an
// unknown/blank id seeds it). Keep in sync with the orchestrator demo seed.
const DEMO_PATIENT_ID = "demo-patient";

export default function Caregiver() {
  const [patientIdInput, setPatientIdInput] = useState(DEMO_PATIENT_ID);
  const [activePatientId, setActivePatientId] = useState(DEMO_PATIENT_ID);
  const [patient, setPatient] = useState<Patient | null>(null);
  const [lookupError, setLookupError] = useState("");
  // Bump to force child panels (graph + queue) to refetch.
  const [refreshKey, setRefreshKey] = useState(0);

  // Resolve patient metadata (best-effort; panels still work with just the id).
  useEffect(() => {
    let alive = true;
    setLookupError("");
    setPatient(null);
    api
      .getPatient(activePatientId)
      .then((p) => {
        if (alive) setPatient(p);
      })
      .catch(() => {
        if (alive) {
          setLookupError(
            "해당 ID의 환자 정보를 찾지 못했습니다. 환자 시뮬레이터에서 세션을 시작하면 데모 환자가 생성됩니다.",
          );
        }
      });
    return () => {
      alive = false;
    };
  }, [activePatientId, refreshKey]);

  function applyPatientId() {
    const id = patientIdInput.trim() || DEMO_PATIENT_ID;
    setPatientIdInput(id);
    setActivePatientId(id);
    setRefreshKey((n) => n + 1);
  }

  function bumpRefresh() {
    setRefreshKey((n) => n + 1);
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <header className="mb-6">
        <h1 className="text-3xl font-extrabold text-stone-800">보호자 포털</h1>
        <p className="mt-1 text-stone-500">
          환자의 기억을 함께 돌보세요. 문진 입력, 기억 그래프, 회상 재질문 일정을 한곳에서 관리합니다.
        </p>
      </header>

      {/* patient selector */}
      <section className="mb-6 rounded-3xl border border-amber-100 bg-white/80 p-5 shadow-sm">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1">
            <label
              htmlFor="patient_id"
              className="mb-1 block text-sm font-semibold text-stone-600"
            >
              환자 ID
            </label>
            <input
              id="patient_id"
              className="w-full rounded-xl border border-amber-200 bg-white px-4 py-3 text-base text-stone-800 focus:border-amber-400 focus:outline-none focus:ring-2 focus:ring-amber-200"
              value={patientIdInput}
              onChange={(e) => setPatientIdInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") applyPatientId();
              }}
              placeholder={DEMO_PATIENT_ID}
            />
          </div>
          <button
            type="button"
            onClick={applyPatientId}
            className="rounded-full bg-stone-800 px-6 py-3 text-base font-bold text-white shadow transition hover:bg-stone-700"
          >
            불러오기
          </button>
          <button
            type="button"
            onClick={() => {
              setPatientIdInput(DEMO_PATIENT_ID);
              setActivePatientId(DEMO_PATIENT_ID);
              setRefreshKey((n) => n + 1);
            }}
            className="rounded-full bg-amber-100 px-6 py-3 text-base font-semibold text-amber-700 transition hover:bg-amber-200"
          >
            데모 환자
          </button>
        </div>

        <div className="mt-3 text-sm">
          {patient ? (
            <span className="text-stone-600">
              현재 환자:{" "}
              <span className="font-semibold text-stone-800">{patient.name}</span>{" "}
              <span className="text-stone-400">({activePatientId})</span>
            </span>
          ) : lookupError ? (
            <span className="text-amber-600">{lookupError}</span>
          ) : (
            <span className="text-stone-400">환자 정보를 불러오는 중...</span>
          )}
        </div>
      </section>

      <div className="space-y-6">
        <IntakeForm patientId={activePatientId} onSubmitted={bumpRefresh} />

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <MemoryGraph patientId={activePatientId} refreshKey={refreshKey} />
          <RecallQueue
            patientId={activePatientId}
            wsConnected={false}
            refreshKey={refreshKey}
          />
        </div>
      </div>
    </div>
  );
}
