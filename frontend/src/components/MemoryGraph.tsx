// MemoryGraph — Neo4j semantic-graph stub visual.
// Fetches the patient's memories and renders an SVG graph: each Memory is a
// node, linked by edges to the keyword nodes it shares. Recalled memories are
// highlighted. This is a *visual* stub for the production Neo4j graph (plan M3).

import { useEffect, useMemo, useState } from "react";
import type { Memory } from "../protocol";
import { api } from "../lib/api";

interface MemoryGraphProps {
  patientId: string;
  // Bump this number to force a refetch (e.g. after an intake submit).
  refreshKey?: number;
}

// ---- layout primitives ----------------------------------------------------

interface NodePos {
  id: string;
  x: number;
  y: number;
}

interface Edge {
  from: string; // memory node id
  to: string; // keyword node id
}

const WIDTH = 720;
const HEIGHT = 460;
const CX = WIDTH / 2;
const CY = HEIGHT / 2;

// Distribute n points evenly on a circle of the given radius.
function radial(n: number, radius: number, phase = 0): { x: number; y: number }[] {
  if (n === 0) return [];
  return Array.from({ length: n }, (_, i) => {
    const a = phase + (2 * Math.PI * i) / n;
    return { x: CX + radius * Math.cos(a), y: CY + radius * Math.sin(a) };
  });
}

export default function MemoryGraph({ patientId, refreshKey = 0 }: MemoryGraphProps) {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    let alive = true;
    setStatus("loading");
    api
      .getMemories(patientId)
      .then((rows) => {
        if (!alive) return;
        setMemories(rows);
        setStatus("ready");
      })
      .catch((err) => {
        if (!alive) return;
        setErrorMsg(err instanceof Error ? err.message : "기억을 불러오지 못했습니다.");
        setStatus("error");
      });
    return () => {
      alive = false;
    };
  }, [patientId, refreshKey]);

  // Build node positions + edges from memories and their keywords.
  const { memoryNodes, keywordNodes, edges, keywordOf } = useMemo(() => {
    const mNodes: NodePos[] = [];
    const kNodes: NodePos[] = [];
    const eList: Edge[] = [];

    // Memory nodes on an inner ring, keyword nodes on an outer ring.
    const mPos = radial(memories.length, 110, -Math.PI / 2);
    memories.forEach((m, i) => {
      mNodes.push({ id: m.id, x: mPos[i].x, y: mPos[i].y });
    });

    const uniqueKeywords = Array.from(
      new Set(memories.flatMap((m) => m.keywords)),
    );
    const kPos = radial(uniqueKeywords.length, 195, -Math.PI / 2 + 0.25);
    const kIndex = new Map<string, NodePos>();
    uniqueKeywords.forEach((kw, i) => {
      const node: NodePos = { id: `kw:${kw}`, x: kPos[i].x, y: kPos[i].y };
      kNodes.push(node);
      kIndex.set(kw, node);
    });

    memories.forEach((m) => {
      m.keywords.forEach((kw) => {
        if (kIndex.has(kw)) eList.push({ from: m.id, to: `kw:${kw}` });
      });
    });

    const labelOf = new Map<string, string>();
    uniqueKeywords.forEach((kw) => labelOf.set(`kw:${kw}`, kw));

    return {
      memoryNodes: mNodes,
      keywordNodes: kNodes,
      edges: eList,
      keywordOf: labelOf,
    };
  }, [memories]);

  const posById = useMemo(() => {
    const map = new Map<string, NodePos>();
    memoryNodes.forEach((n) => map.set(n.id, n));
    keywordNodes.forEach((n) => map.set(n.id, n));
    return map;
  }, [memoryNodes, keywordNodes]);

  const recalledIds = useMemo(
    () => new Set(memories.filter((m) => m.recall_status === "recalled").map((m) => m.id)),
    [memories],
  );

  return (
    <section className="rounded-3xl border border-amber-100 bg-white/80 p-6 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-stone-800">기억 그래프</h2>
          <p className="text-sm text-stone-500">
            기억 노드와 키워드의 의미 연결 (Neo4j 그래프 시각화 데모)
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs text-stone-500">
          <span className="flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded-full bg-emerald-400" /> 회상됨
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded-full bg-stone-300" /> 미회상
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded-full bg-amber-300" /> 키워드
          </span>
        </div>
      </div>

      {status === "loading" && (
        <div className="flex h-64 items-center justify-center text-stone-400">
          기억을 불러오는 중...
        </div>
      )}

      {status === "error" && (
        <div className="flex h-64 items-center justify-center text-rose-500">
          {errorMsg}
        </div>
      )}

      {status === "ready" && memories.length === 0 && (
        <div className="flex h-64 flex-col items-center justify-center gap-2 text-stone-400">
          <p>아직 기록된 기억이 없습니다.</p>
          <p className="text-sm">문진을 입력하거나 환자와 대화를 시작해 보세요.</p>
        </div>
      )}

      {status === "ready" && memories.length > 0 && (
        <div className="overflow-x-auto">
          <svg
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            className="mx-auto h-auto w-full max-w-3xl"
            role="img"
            aria-label="기억 그래프"
          >
            {/* edges */}
            {edges.map((e, i) => {
              const a = posById.get(e.from);
              const b = posById.get(e.to);
              if (!a || !b) return null;
              return (
                <line
                  key={`e-${i}`}
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  stroke="#e7cfa3"
                  strokeWidth={1.5}
                  strokeLinecap="round"
                />
              );
            })}

            {/* keyword nodes */}
            {keywordNodes.map((n) => (
              <g key={n.id}>
                <circle cx={n.x} cy={n.y} r={20} fill="#fcd34d" opacity={0.9} />
                <text
                  x={n.x}
                  y={n.y}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontSize={11}
                  fill="#78350f"
                  fontWeight={600}
                >
                  {keywordOf.get(n.id) ?? ""}
                </text>
              </g>
            ))}

            {/* memory nodes (drawn last so they sit on top) */}
            {memoryNodes.map((n, i) => {
              const m = memories[i];
              const recalled = recalledIds.has(n.id);
              return (
                <g key={n.id}>
                  <circle
                    cx={n.x}
                    cy={n.y}
                    r={30}
                    fill={recalled ? "#34d399" : "#d6d3d1"}
                    stroke="#ffffff"
                    strokeWidth={3}
                  />
                  <title>{m?.text ?? ""}</title>
                  <text
                    x={n.x}
                    y={n.y}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontSize={10}
                    fill="#1c1917"
                    fontWeight={700}
                  >
                    {(m?.text ?? "").slice(0, 6)}
                  </text>
                </g>
              );
            })}
          </svg>

          {/* legend list of memories beneath the graph */}
          <ul className="mt-4 space-y-2">
            {memories.map((m) => (
              <li
                key={m.id}
                className="flex items-start gap-2 rounded-xl bg-amber-50/60 px-3 py-2 text-sm"
              >
                <span
                  className={`mt-1 inline-block h-2.5 w-2.5 shrink-0 rounded-full ${
                    m.recall_status === "recalled" ? "bg-emerald-400" : "bg-stone-300"
                  }`}
                />
                <span className="text-stone-700">
                  {m.text}
                  {m.keywords.length > 0 && (
                    <span className="ml-2 text-xs text-amber-600">
                      #{m.keywords.join(" #")}
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
