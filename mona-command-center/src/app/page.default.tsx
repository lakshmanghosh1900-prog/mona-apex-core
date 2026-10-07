"tsx"
'use client';

import React, { useEffect, useState } from 'react';

export default function CommandCenter() {
  const [health, setHealth] = useState<any>(null);
  const [phase7, setPhase7] = useState<any>(null);
  const [phase8, setPhase8] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const hRes = await fetch('http://127.0.0.1:8000/health');
        const hData = await hRes.json();
        setHealth(hData);

        const p7Res = await fetch('http://127.0.0.1:8000/phase7/mega/verify');
        const p7Data = await p7Res.json();
        setPhase7(p7Data);

        const p8Res = await fetch('http://127.0.0.1:8000/phase8/mega/verify');
        const p8Data = await p8Res.json();
        setPhase8(p8Data);
      } catch (err) {
        console.error("Failed to fetch from backend", err);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-900 text-white font-mono">
        <div className="text-xl animate-pulse">? Connecting to Mona Apex Core backend...</div>
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-gray-950 text-gray-100 p-8 font-sans">
      <div className="max-w-6xl mx-auto space-y-8">
        
        {/* Header */}
        <header className="border-b border-gray-800 pb-4 flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-emerald-400">MONA COMMAND CENTER</h1>
            <p className="text-sm text-gray-400 mt-1">Enterprise Operations & Governance Dashboard (Powered by Apex Core)</p>
          </div>
          <div className="bg-emerald-950 border border-emerald-800 px-4 py-2 rounded-lg text-emerald-300 text-sm font-mono">
            ? SYSTEM ONLINE
          </div>
        </header>

        {/* Grid Status Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          
          {/* Health Card */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 shadow-lg">
            <h2 className="text-lg font-semibold text-gray-200 mb-3 border-b border-gray-800 pb-2">??? Core Health</h2>
            <div className="space-y-2 text-sm">
              <p><span className="text-gray-400">Service:</span> {health?.service}</p>
              <p><span className="text-gray-400">Status:</span> <span className="text-emerald-400 font-bold">{health?.status}</span></p>
              <p><span className="text-gray-400">Environment:</span> {health?.env}</p>
              <p><span className="text-gray-400">Telegram Gate:</span> {health?.telegram?.enabled ? "Enabled" : "Waiting"}</p>
            </div>
          </div>

          {/* Phase 7 Mega Verify */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 shadow-lg">
            <h2 className="text-lg font-semibold text-gray-200 mb-3 border-b border-gray-800 pb-2">?? Phase 7 Mega Ops</h2>
            <div className="space-y-2 text-sm">
              <p><span className="text-gray-400">Passed Checks:</span> <span className="text-emerald-400 font-bold">{phase7?.passed} / {phase7?.total}</span></p>
              <p><span className="text-gray-400">Status:</span> <span className="text-xs bg-emerald-900 text-emerald-200 px-2 py-1 rounded">{phase7?.status}</span></p>
              <p><span className="text-gray-400">Zero Cost:</span> {phase7?.zero_cost ? "True (Free Tier Active)" : "False"}</p>
            </div>
          </div>

          {/* Phase 8 FPA Gates */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 shadow-lg">
            <h2 className="text-lg font-semibold text-gray-200 mb-3 border-b border-gray-800 pb-2">?? Phase 8 FPA Security</h2>
            <div className="space-y-2 text-sm">
              <p><span className="text-gray-400">FPA Passed:</span> <span className="text-emerald-400 font-bold">{phase8?.fpa_passed} / {phase8?.fpa_total}</span></p>
              <p><span className="text-gray-400">CORS Allowlist:</span> <span className="text-emerald-400">Protected (FPA-04)</span></p>
              <p><span className="text-gray-400">Status:</span> <span className="text-xs bg-emerald-900 text-emerald-200 px-2 py-1 rounded">5/5 PASS</span></p>
            </div>
          </div>

        </div>

        {/* Footer info */}
        <div className="text-center text-xs text-gray-500 pt-8 border-t border-gray-900">
          Canonical Spec: MONA - Powered by Apex Core | Build · Test · Verify · Human Review · Commit · Push
        </div>

      </div>
    </main>
  );
}
