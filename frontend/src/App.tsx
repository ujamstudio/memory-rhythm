import { NavLink, Route, Routes } from "react-router-dom";
import Patient from "./pages/Patient";
import Caregiver from "./pages/Caregiver";
import Survey from "./pages/Survey";

// Top-level shell: calm warm top nav + routed pages.
//   "/"          -> Patient (also "/patient")
//   "/survey"    -> Survey (STEP 1 초기 설문, conversational onboarding)
//   "/caregiver" -> Caregiver
// Patient.tsx and Caregiver.tsx are authored by sibling agents.

function NavTab({ to, label, end }: { to: string; label: string; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        [
          "rounded-full px-5 py-2 text-base font-medium transition",
          isActive
            ? "bg-amber-warm text-white shadow-soft"
            : "text-muted hover:bg-sand hover:text-ink",
        ].join(" ")
      }
    >
      {label}
    </NavLink>
  );
}

export default function App() {
  return (
    <div className="flex min-h-screen flex-col bg-cream text-ink">
      <header className="sticky top-0 z-30 border-b border-clay/60 bg-cream/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-6 py-3">
          <NavLink to="/" className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-2xl bg-amber-warm text-xl text-white shadow-soft animate-breathe">
              ♪
            </span>
            <div className="leading-tight">
              <div className="text-lg font-semibold tracking-tight">
                기억의 리듬
              </div>
              <div className="text-xs text-muted">Memory Rhythm · 데모</div>
            </div>
          </NavLink>

          <nav className="ml-auto flex items-center gap-1">
            <NavTab to="/survey" label="초기 설문" />
            <NavTab to="/" label="환자 (D1·D2)" end />
            <NavTab to="/caregiver" label="보호자 포털" />
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-6">
        <Routes>
          <Route path="/" element={<Patient />} />
          <Route path="/patient" element={<Patient />} />
          <Route path="/survey" element={<Survey />} />
          <Route path="/caregiver" element={<Caregiver />} />
          <Route
            path="*"
            element={
              <div className="card mx-auto mt-12 max-w-md text-center">
                <h2 className="text-xl">페이지를 찾을 수 없습니다</h2>
                <p className="mt-2 text-muted">
                  상단 메뉴에서 다시 선택해 주세요.
                </p>
              </div>
            }
          />
        </Routes>
      </main>

      <footer className="border-t border-clay/60 bg-cream/80 px-6 py-3 text-center text-xs text-muted">
        기억의 리듬 — 치매 인지 동반자 AI 데모 · 광과민성 안전 안내 준수
      </footer>
    </div>
  );
}
