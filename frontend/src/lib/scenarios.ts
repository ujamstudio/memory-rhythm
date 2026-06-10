// scenarios.ts — scripted "시뮬레이션 시나리오" for the patient session.
//
// Each scenario is just a list of patient utterances. The simulation runner on
// the Patient page (patient.tsx) replays them one-by-one through the REAL
// WebSocket loop — so the live machinery (두뇌 reasoning chain, stage_change,
// hint escalation, 시장 recall, autobiography page) fires exactly as it would
// for a real conversation. Nothing here is faked; the script only supplies the
// 어르신's side of the dialogue so a reviewer can watch the full arc hands-free
// on the deployed mock demo (no API key required).
//
// Why these turns work in mock mode (see backend mock_provider.py):
//   * Stage 1 -> 2: any reply >= 2 chars advances out of 정서안정화.
//   * Stage 2 hint ladder: a "hesitation" reply (모르/글쎄/기억이 안 나/가물/헷갈/음…)
//     with NO concrete keyword escalates hint_level by 1 (capped at 4).
//   * Stage 2 -> 3 recall: a reply naming a concrete keyword the 두뇌 is fishing
//     for — 시장 / 어머니 / 손 / 고등어 … — counts as a successful recall and
//     produces an autobiography page.
//   * Stage 3: a closing reply wraps the session.
// The 두뇌's hint cues walk toward "시장", so every recall turn lands on the
// market/mother memory to stay coherent with the canned guidance.

export interface ScenarioTurn {
  /** The 어르신's utterance, sent as a user_message. */
  text: string;
  /** Presenter-facing note on what this turn demonstrates (not sent). */
  note?: string;
}

export interface Scenario {
  id: string;
  /** Short menu label. */
  label: string;
  /** One-line description shown under the label in the picker. */
  summary: string;
  /** Seeded persona id used for the session (auto-created if not seeded). */
  patientId: string;
  turns: ScenarioTurn[];
}

export const SCENARIOS: Scenario[] = [
  {
    id: "market-standard",
    label: "시장 회상 · 표준 흐름",
    summary: "정서안정화 → 단서 1단계 → 시장 회상 → 자서전",
    patientId: "demo-soonrye", // 박순례 · 알츠하이머
    turns: [
      {
        text: "안녕하세요. 오늘은 날이 참 포근하네요.",
        note: "1단계(정서안정화) → 2단계(인출)로 전환",
      },
      {
        text: "글쎄요... 옛날 일은 잘 기억이 안 나요.",
        note: "망설임 → 단서 수준 1로 상승",
      },
      {
        text: "아, 어머니 손을 잡고 시장에 가던 게 어렴풋이 떠올라요.",
        note: "‘시장·어머니·손’ 회상 성공 → 3단계 + 자서전 페이지",
      },
      {
        text: "이렇게 떠올리니 마음이 참 좋네요. 고마워요.",
        note: "3단계(행동) 마무리",
      },
    ],
  },
  {
    id: "market-fast",
    label: "빠른 회상 · 단서 없이",
    summary: "단서 없이 한 번에 회상 성공하는 경로",
    patientId: "demo-cheolsu", // 김철수 · 혈관성
    turns: [
      {
        text: "오늘은 기분이 아주 좋습니다.",
        note: "1단계 → 2단계로 전환",
      },
      {
        text: "어머니랑 자갈치 시장에서 고등어 팔던 게 생생하게 생각나요.",
        note: "단서 없이 즉시 회상(‘시장·고등어’) → 3단계 + 자서전",
      },
      {
        text: "참 좋은 시절이었지요. 들어줘서 고마워요.",
        note: "마무리",
      },
    ],
  },
  {
    id: "market-max-hints",
    label: "단서 최대 · 4단계 점증",
    summary: "계속 망설여 단서가 4단계까지 올라간 뒤 회상",
    patientId: "demo-youngja", // 이영자 · 루이소체
    turns: [
      {
        text: "안녕하세요. 오늘은 좀 피곤하네요.",
        note: "1단계 → 2단계로 전환",
      },
      { text: "음... 잘 모르겠어요.", note: "망설임 → 단서 1" },
      { text: "글쎄... 기억이 안 나요.", note: "망설임 → 단서 2" },
      { text: "가물가물하고 자꾸 헷갈려요.", note: "망설임 → 단서 3" },
      { text: "잘 생각이 안 나네요... 흐릿해요.", note: "망설임 → 단서 4(최대)" },
      {
        text: "아, 어머니 손 잡고 시장 가던 게 이제 생각나요!",
        note: "최대 단서 끝에 회상 성공 → 3단계 + 자서전",
      },
      { text: "덕분에 떠올렸어요. 고맙습니다.", note: "마무리" },
    ],
  },
];
