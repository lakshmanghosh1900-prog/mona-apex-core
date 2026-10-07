"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const BACKENDS = ["http://127.0.0.1:8000", "http://127.0.0.1:8025"];
const REFRESH_MS = 20000;

type Tab = "overview" | "memories" | "evidence" | "audit";
type Conn = "checking" | "online" | "offline";
type Msg = { kind: "ok" | "err"; text: string } | null;

async function getJson(url: string, init?: RequestInit, timeoutMs = 6000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...init, signal: ctrl.signal });
    let data: any = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }
    return { ok: res.ok, status: res.status, data };
  } catch {
    return { ok: false, status: 0, data: null };
  } finally {
    clearTimeout(timer);
  }
}

function toEntries(obj: any): [string, any][] {
  return obj && typeof obj === "object" && !Array.isArray(obj) ? Object.entries(obj) : [];
}

function isPass(v: any) {
  if (typeof v === "boolean") return v;
  const s = String(v).toLowerCase();
  return s.includes("pass") || s.includes("ok") || s.includes("true") || s.includes("complete");
}

function fmt(v: any) {
  if (v === undefined || v === null) return "--";
  return String(v);
}

export default function MonaCommandCenter() {
  const [backendUrl, setBackendUrl] = useState(BACKENDS[0]);
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [conn, setConn] = useState<Conn>("checking");
  const [health, setHealth] = useState<any>(null);
  const [p7, setP7] = useState<any>(null);
  const [p8, setP8] = useState<any>(null);
  const [memStats, setMemStats] = useState<any>(null);
  const [memories, setMemories] = useState<any[]>([]);
  const [memApi, setMemApi] = useState<"unknown" | "ok" | "missing">("unknown");
  const [loading, setLoading] = useState(false);
  const [lastUpdate, setLastUpdate] = useState("--");
  const [msg, setMsg] = useState<Msg>(null);

  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState('{"note":"test memory"}');
  const [taskId, setTaskId] = useState("");
  const [evidenceJson, setEvidenceJson] = useState('{"result":"verified"}');

  const urlRef = useRef(backendUrl);
  urlRef.current = backendUrl;

  const fetchAll = useCallback(async () => {
    const url = urlRef.current;
    setLoading(true);
    const [h, ph7, ph8, stats, list] = await Promise.all([
      getJson(`${url}/health`),
      getJson(`${url}/phase7/mega/verify`),
      getJson(`${url}/phase8/mega/verify`),
      getJson(`${url}/memory/stats`),
      getJson(`${url}/memory/list?limit=50`),
    ]);

    if (url !== urlRef.current) return; // backend switched mid-request

    setConn(h.ok ? "online" : "offline");
    setHealth(h.ok ? h.data : null);
    setP7(ph7.ok ? ph7.data : null);
    setP8(ph8.ok ? ph8.data : null);

    if (stats.ok) {
      setMemStats(stats.data);
      setMemApi("ok");
    } else {
      setMemStats(null);
      setMemApi(h.ok ? "missing" : "unknown");
    }

    if (list.ok && list.data) {
      const arr = list.data.memories || list.data.items || list.data.data || [];
      setMemories(Array.isArray(arr) ? arr : []);
    } else {
      setMemories([]);
    }

    setLastUpdate(new Date().toLocaleTimeString());
    setLoading(false);
  }, []);

  useEffect(() => {
    setConn("checking");
    fetchAll();
    const id = setInterval(fetchAll, REFRESH_MS);
    return () => clearInterval(id);
  }, [backendUrl, fetchAll]);

  const parseJson = (raw: string): any => {
    try {
      const v = JSON.parse(raw);
      return v && typeof v === "object" && !Array.isArray(v) ? v : { content: v };
    } catch {
      return { content: raw };
    }
  };

  const saveMemory = async () => {
    const key = newKey.trim();
    if (key.length < 2 || key.length > 128) {
      setMsg({ kind: "err", text: "Key must be 2-128 characters." });
      return;
    }
    const res = await getJson(`${backendUrl}/memory/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, value: parseJson(newValue), actor: "ui-user", tenant_id: "default" }),
    });
    if (res.ok && res.data?.success !== false) {
      setMsg({ kind: "ok", text: `Saved ${res.data?.id || key}` });
      setNewKey("");
      setNewValue('{"note":""}');
      fetchAll();
    } else {
      setMsg({ kind: "err", text: `Save failed (HTTP ${res.status || "network"}): ${JSON.stringify(res.data)}` });
    }
  };

  const saveEvidence = async () => {
    const id = taskId.trim();
    if (!id) {
      setMsg({ kind: "err", text: "task_id is required." });
      return;
    }
    const res = await getJson(`${backendUrl}/evidence/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_id: id, evidence: parseJson(evidenceJson), actor: "ui-user", tenant_id: "default" }),
    });
    if (res.ok && res.data?.success !== false) {
      setMsg({ kind: "ok", text: `Evidence saved for ${id}` });
      setTaskId("");
      fetchAll();
    } else {
      setMsg({ kind: "err", text: `Evidence save failed (HTTP ${res.status || "network"}): ${JSON.stringify(res.data)}` });
    }
  };

  const total7 = p7?.total;
  const pass7 = p7?.passed;
  const fpaTotal = p8?.fpa_total;
  const fpaPass = p8?.fpa_passed;
  const allGreen =
    conn === "online" && p7 && p8 && pass7 === total7 && fpaPass === fpaTotal;

  const statusLabel =
    conn === "checking" ? "CONNECTING" : conn === "offline" ? "BACKEND OFFLINE" : allGreen ? "ALL CHECKS PASS" : "CHECK FAILURES";
  const dotColor =
    conn === "online" ? (allGreen ? "bg-emerald-500 animate-pulse" : "bg-amber-500") : conn === "offline" ? "bg-red-500" : "bg-zinc-500";

  const memRoot = memStats?.memory_root;
  const totalMemories = memStats?.total_memories ?? (memories.length || undefined);

  const tabs: { id: Tab; label: string }[] = [
    { id: "overview", label: `OVERVIEW [${fmt(pass7)}/${fmt(total7)} + ${fmt(fpaPass)}/${fmt(fpaTotal)}]` },
    { id: "memories", label: `MEMORIES [${fmt(totalMemories)}]` },
    { id: "evidence", label: `EVIDENCE [${fmt(memStats?.total_evidence)}]` },
    { id: "audit", label: "AUDIT" },
  ];

  const Card = ({ children, className = "" }: any) => (
    <div className={`bg-zinc-900 border border-zinc-800 p-5 ${className}`}>{children}</div>
  );

  const GateList = ({ obj }: { obj: any }) => {
    const entries = toEntries(obj);
    if (!entries.length) return <div className="text-[10px] text-zinc-600 mt-4">No per-check data returned.</div>;
    return (
      <div className="grid grid-cols-2 gap-2 mt-4">
        {entries.map(([k, v]) => (
          <div key={k} className="flex justify-between bg-black border border-zinc-800 px-2 py-1 text-[10px]">
            <span className="truncate mr-2">{k}</span>
            <span className={isPass(v) ? "text-emerald-400" : "text-red-400"}>{isPass(v) ? "PASS" : "FAIL"}</span>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-zinc-100 font-mono">
      <header className="border-b border-zinc-800 bg-black/60 backdrop-blur sticky top-0 z-20">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-white text-black flex items-center justify-center font-black text-lg">M</div>
            <div>
              <h1 className="text-[13px] font-black tracking-widest">MONA APEX CORE - COMMAND CENTER</h1>
              <p className="text-[9px] text-zinc-500">
                {health?.version ?? "v2.2.0-observability"} | {health?.branch ?? "main 643c104"} |{" "}
                {health?.env ? `env=${health.env}` : "env=--"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-[10px] px-2 py-1 bg-zinc-900 border border-zinc-700">{lastUpdate}</span>
            <div className={`w-2 h-2 rounded-full ${dotColor}`} />
            <span className="text-[10px] text-zinc-400">{statusLabel}</span>
          </div>
        </div>

        <div className="max-w-7xl mx-auto px-6 flex flex-wrap gap-1 border-t border-zinc-900">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={`px-4 py-2 text-[11px] tracking-widest border-b-2 transition ${
                activeTab === t.id ? "border-white bg-zinc-900 text-white" : "border-transparent text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {t.label}
            </button>
          ))}
          <div className="ml-auto flex items-center gap-2 py-1">
            <select
              value={BACKENDS.includes(backendUrl) ? backendUrl : "custom"}
              onChange={(e) => e.target.value !== "custom" && setBackendUrl(e.target.value)}
              className="bg-black border border-zinc-800 px-2 py-1 text-[10px] outline-none"
            >
              {BACKENDS.map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
              <option value="custom">custom...</option>
            </select>
            <input
              value={backendUrl}
              onChange={(e) => setBackendUrl(e.target.value.trim().replace(/\/$/, ""))}
              className="bg-black border border-zinc-800 px-2 py-1 text-[10px] w-48 outline-none"
            />
            <button onClick={fetchAll} className="px-3 py-1 bg-white text-black text-[10px] font-bold">
              {loading ? "SYNC..." : "VERIFY"}
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {conn === "offline" && (
          <div className="border border-red-800 bg-red-950/40 text-red-300 text-[11px] p-3">
            Cannot reach {backendUrl}. Start the backend and check the CORS allowlist (FPA-04) includes http://localhost:3000.
          </div>
        )}
        {conn === "online" && memApi === "missing" && (
          <div className="border border-amber-800 bg-amber-950/40 text-amber-300 text-[11px] p-3">
            Backend is online but /memory/stats is not exposed. Add the memory routes (memory_store is working, only the API layer is missing).
          </div>
        )}
        {msg && (
          <div
            onClick={() => setMsg(null)}
            className={`cursor-pointer border text-[11px] p-3 ${
              msg.kind === "ok" ? "border-emerald-800 bg-emerald-950/40 text-emerald-300" : "border-red-800 bg-red-950/40 text-red-300"
            }`}
          >
            {msg.text} <span className="text-zinc-500">(click to dismiss)</span>
          </div>
        )}

        {activeTab === "overview" && (
          <div className="space-y-6">
            <div className="grid grid-cols-12 gap-4">
              <Card className="col-span-12 lg:col-span-8">
                <h2 className="text-[11px] tracking-widest text-zinc-400 mb-3">BACKEND / RUNTIME</h2>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-[11px]">
                  <div className="bg-black border border-zinc-800 p-3">
                    <div className="text-zinc-500">SERVICE</div>
                    <div className="font-bold mt-1">{fmt(health?.service)}</div>
                  </div>
                  <div className="bg-black border border-zinc-800 p-3">
                    <div className="text-zinc-500">STATUS / ENV</div>
                    <div className="font-bold mt-1">
                      <span className={health?.status === "ok" ? "text-emerald-400" : "text-red-400"}>{fmt(health?.status)}</span>
                      {" / "}
                      <span className="text-amber-400">{fmt(health?.env)}</span>
                    </div>
                  </div>
                  <div className="bg-black border border-zinc-800 p-3">
                    <div className="text-zinc-500">MEMORY</div>
                    <div className="font-bold mt-1">
                      {fmt(health?.memory?.mode)} | {fmt(health?.memory?.embedding)}
                    </div>
                  </div>
                </div>
                <div className="mt-3 text-[10px] text-zinc-500">
                  telegram: {health?.telegram?.enabled ? "enabled" : "disabled"} pending={fmt(health?.telegram?.pending)} | groq=
                  {fmt(health?.providers?.groq)} gemini={fmt(health?.providers?.gemini)}
                </div>
              </Card>

              <Card className="col-span-12 lg:col-span-4">
                <h2 className="text-[11px] tracking-widest text-zinc-400 mb-3">STORAGE BACKEND</h2>
                <div className="text-[11px] space-y-1">
                  <div className="flex justify-between"><span className="text-zinc-500">CURRENT</span><span className="text-emerald-400">LocalJSONLBackend</span></div>
                  <div className="flex justify-between gap-2"><span className="text-zinc-500">ROOT</span><span className="text-[10px] break-all text-right">{fmt(memRoot)}</span></div>
                  <div className="flex justify-between"><span className="text-zinc-500">POSTGRES</span><span className="text-zinc-600">scaffold</span></div>
                  <div className="flex justify-between"><span className="text-zinc-500">REDIS</span><span className="text-zinc-600">scaffold</span></div>
                  <div className="flex justify-between"><span className="text-zinc-500">STACK</span><span>{fmt(memStats?.stack)}</span></div>
                </div>
              </Card>
            </div>

            <div className="grid grid-cols-12 gap-4">
              <Card className="col-span-12 lg:col-span-6">
                <div className="flex justify-between mb-3">
                  <h2 className="text-[11px] text-zinc-400">PHASE 7 - DEPLOYMENT & OPS</h2>
                  <span className="text-[10px] px-2 py-1 bg-zinc-800 border border-zinc-700">{fmt(pass7)}/{fmt(total7)}</span>
                </div>
                <div className="text-[12px] font-black">{fmt(p7?.status)}</div>
                <GateList obj={p7?.stages} />
              </Card>

              <Card className="col-span-12 lg:col-span-6">
                <div className="flex justify-between mb-3">
                  <h2 className="text-[11px] text-zinc-400">PHASE 8 - FPA HARDENING</h2>
                  <span className="text-[10px] px-2 py-1 bg-zinc-800 border border-zinc-700">FPA {fmt(fpaPass)}/{fmt(fpaTotal)}</span>
                </div>
                <div className="text-[12px] font-black">{fmt(p8?.status)}</div>
                <GateList obj={p8?.fpa_gates} />
              </Card>
            </div>

            <Card className="flex flex-wrap justify-between items-center gap-3">
              <div>
                <h3 className="text-[11px] text-zinc-300">Backend API</h3>
                <p className="text-[11px] text-emerald-400 mt-1">{backendUrl}</p>
              </div>
              <a
                href={`${backendUrl}/docs`}
                target="_blank"
                rel="noreferrer"
                className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-[11px]"
              >
                Open Swagger Docs
              </a>
            </Card>
          </div>
        )}

        {activeTab === "memories" && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              {[
                ["TOTAL_MEMORIES", totalMemories],
                ["TOTAL_EVIDENCE", memStats?.total_evidence],
                ["TOTAL_REPORTS", memStats?.total_reports],
                ["RESUME_QUEUE", memStats?.resume_queue_len],
              ].map(([label, val]: any) => (
                <Card key={label} className="!p-4">
                  <div className="text-[10px] text-zinc-500">{label}</div>
                  <div className="text-2xl font-black mt-1">{fmt(val)}</div>
                </Card>
              ))}
            </div>

            <div className="grid grid-cols-12 gap-6">
              <Card className="col-span-12 lg:col-span-5">
                <h3 className="text-[11px] tracking-widest text-zinc-400 mb-4">SAVE NEW MEMORY</h3>
                <div className="space-y-3">
                  <div>
                    <label className="text-[10px] text-zinc-500">KEY (2-128 chars)</label>
                    <input
                      value={newKey}
                      onChange={(e) => setNewKey(e.target.value)}
                      placeholder="e.g. mona_phase7_verify"
                      className="w-full mt-1 bg-black border border-zinc-800 px-3 py-2 text-[11px] outline-none focus:border-white"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-zinc-500">VALUE (JSON object)</label>
                    <textarea
                      value={newValue}
                      onChange={(e) => setNewValue(e.target.value)}
                      rows={6}
                      className="w-full mt-1 bg-black border border-zinc-800 px-3 py-2 text-[11px] outline-none focus:border-white"
                    />
                  </div>
                  <button onClick={saveMemory} className="w-full py-2 bg-white text-black text-[11px] font-bold tracking-widest hover:bg-zinc-200">
                    SAVE MEMORY (POST /memory/save)
                  </button>
                  <div className="text-[9px] text-zinc-600">tenant_id: default | actor: ui-user | audit auto-recorded by backend</div>
                </div>
              </Card>

              <div className="col-span-12 lg:col-span-7 bg-black border border-zinc-800 p-5">
                <div className="flex justify-between mb-4">
                  <h3 className="text-[11px] tracking-widest text-zinc-400">MEMORY LIST</h3>
                  <button onClick={fetchAll} className="text-[10px] px-2 py-1 border border-zinc-700">REFRESH</button>
                </div>
                <div className="space-y-2 max-h-[420px] overflow-y-auto">
                  {memories.length === 0 && (
                    <div className="text-[11px] text-zinc-500 py-8 text-center">
                      {memApi === "missing"
                        ? "Memory endpoints are not exposed by the backend yet."
                        : "No memories returned. Save one from the left panel."}
                    </div>
                  )}
                  {memories.map((m: any, i: number) => (
                    <div key={m.id || i} className="border border-zinc-800 bg-zinc-900 p-3 text-[11px]">
                      <div className="flex justify-between gap-2">
                        <span className="font-bold truncate">{m.key || m.id}</span>
                        <span className="text-[9px] text-zinc-500 shrink-0">
                          {m.tenant_id || "default"} | {String(m.id || "").slice(0, 16)}
                        </span>
                      </div>
                      <div className="text-zinc-400 mt-1 text-[10px] break-all">
                        {JSON.stringify(m.value ?? m).slice(0, 220)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === "evidence" && (
          <div className="grid grid-cols-12 gap-6">
            <Card className="col-span-12 lg:col-span-5">
              <h3 className="text-[11px] tracking-widest text-zinc-400 mb-4">SAVE EVIDENCE</h3>
              <div className="space-y-3">
                <div>
                  <label className="text-[10px] text-zinc-500">TASK ID</label>
                  <input
                    value={taskId}
                    onChange={(e) => setTaskId(e.target.value)}
                    placeholder="e.g. task_phase8_verify"
                    className="w-full mt-1 bg-black border border-zinc-800 px-3 py-2 text-[11px] outline-none focus:border-white"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-zinc-500">EVIDENCE (JSON object)</label>
                  <textarea
                    value={evidenceJson}
                    onChange={(e) => setEvidenceJson(e.target.value)}
                    rows={6}
                    className="w-full mt-1 bg-black border border-zinc-800 px-3 py-2 text-[11px] outline-none focus:border-white"
                  />
                </div>
                <button onClick={saveEvidence} className="w-full py-2 bg-white text-black text-[11px] font-bold tracking-widest hover:bg-zinc-200">
                  SAVE EVIDENCE (POST /evidence/save)
                </button>
              </div>
            </Card>
            <Card className="col-span-12 lg:col-span-7">
              <h3 className="text-[11px] tracking-widest text-zinc-400 mb-4">EVIDENCE CHAIN</h3>
              <div className="text-[11px] space-y-2">
                <div className="flex justify-between"><span className="text-zinc-500">Total evidence</span><span>{fmt(memStats?.total_evidence)}</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">Total reports</span><span>{fmt(memStats?.total_reports)}</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">Resume queue</span><span>{fmt(memStats?.resume_queue_len)}</span></div>
                <div className="pt-3 text-[10px] text-zinc-500 break-all">{fmt(memStats?.dod_ref)}</div>
              </div>
            </Card>
          </div>
        )}

        {activeTab === "audit" && (
          <div className="space-y-6">
            <Card>
              <h3 className="text-[11px] tracking-widest text-zinc-400 mb-4">
                AUDIT TRAIL - PHASE 7 {fmt(pass7)}/{fmt(total7)} | PHASE 8 FPA {fmt(fpaPass)}/{fmt(fpaTotal)}
              </h3>
              <div className="text-[10px] text-zinc-500 mb-3">Wiring: {JSON.stringify(memStats?.wired ?? "--")}</div>
            </Card>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Card>
                <h4 className="text-[11px] text-zinc-400 mb-3">PHASE 7 DETAILS</h4>
                <div className="grid grid-cols-2 gap-2 text-[10px]">
                  {toEntries(p7?.details).map(([k, v]) => (
                    <div key={k} className="bg-black border border-zinc-800 p-2">
                      <div className="text-zinc-500">{k}</div>
                      <div className="mt-1 break-all">{typeof v === "object" ? JSON.stringify(v) : String(v)}</div>
                    </div>
                  ))}
                  {!toEntries(p7?.details).length && <div className="text-zinc-600">No details returned.</div>}
                </div>
              </Card>
              <Card>
                <h4 className="text-[11px] text-zinc-400 mb-3">PHASE 8 DETAILS</h4>
                <div className="grid grid-cols-2 gap-2 text-[10px]">
                  {toEntries(p8?.details).map(([k, v]) => (
                    <div key={k} className="bg-black border border-zinc-800 p-2">
                      <div className="text-zinc-500">{k}</div>
                      <div className="mt-1 break-all">{typeof v === "object" ? JSON.stringify(v) : String(v)}</div>
                    </div>
                  ))}
                  {!toEntries(p8?.details).length && <div className="text-zinc-600">No details returned.</div>}
                </div>
              </Card>
            </div>
          </div>
        )}

        <div className="border-t border-zinc-800 pt-4 mt-8 flex flex-wrap justify-between gap-2 text-[9px] text-zinc-600">
          <span>MONA - Powered by Apex Core | zero-cost | Build, Test, Verify, Human Review, Commit, Push, Next</span>
          <span>localhost:3000 to {backendUrl} | {lastUpdate}</span>
        </div>
      </main>
    </div>
  );
}
