import React, { useEffect, useState, useCallback } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from "recharts";

const API = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";

interface ModelInfo {
  version: string;
  n_profiles: number;
  model_name: string;
  far: number;
  frr: number;
  eer: number;
  tar: number;
}

interface DriftInfo {
  drift_score: number;
  baseline_score: number;
  recent_mean: number;
  alert: boolean;
}

interface TrainingStatus {
  running: boolean;
  task_ids: string[];
}

interface TrainingConfig {
  FINE_TUNE_THRESHOLD: string;
  CONFIDENCE_MIN: string;
  CONFIDENCE_MAX: string;
  AUTO_DEPLOY: string;
  MIN_IMPROVEMENT_PCT: string;
}

interface TrainingRun {
  run_id: string;
  run_name: string;
  start_time: string;
  status: string;
  far_before: number | null;
  far_after: number | null;
  eer_before: number | null;
  eer_after: number | null;
  improvement_pct: number | null;
  outcome: string | null;
  n_samples: number | null;
}

function pct(v: number | null | undefined): string {
  if (v == null) return "—";
  return (v * 100).toFixed(3) + "%";
}

function MetricCard({
  label, value, target, colorClass,
}: {
  label: string; value: number | null; target: string; colorClass: string;
}) {
  const display = value == null ? "—" : (value * 100).toFixed(3) + "%";
  return (
    <div className={`rounded-xl border-2 p-4 flex flex-col gap-1 ${colorClass}`}>
      <span className="text-xs font-semibold uppercase tracking-wider opacity-70">{label}</span>
      <span className="text-3xl font-bold">{display}</span>
      <span className="text-xs opacity-60">Cible : {target}</span>
    </div>
  );
}

function OutcomeBadge({ outcome }: { outcome: string | null }) {
  if (!outcome) return <span className="text-gray-400">—</span>;
  const map: Record<string, { cls: string; label: string }> = {
    deployed:    { cls: "bg-green-100 text-green-800",  label: "Déployé" },
    rolled_back: { cls: "bg-red-100 text-red-800",    label: "Annulé" },
    unchanged:   { cls: "bg-gray-100 text-gray-700",  label: "Inchangé" },
  };
  const { cls, label } = map[outcome] ?? { cls: "bg-gray-100 text-gray-600", label: outcome };
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${cls}`}>
      {label}
    </span>
  );
}

export default function MonitoringML() {
  const [modelInfo, setModelInfo]     = useState<ModelInfo | null>(null);
  const [drift, setDrift]             = useState<DriftInfo | null>(null);
  const [trainStatus, setTrainStatus] = useState<TrainingStatus>({ running: false, task_ids: [] });
  const [history, setHistory]         = useState<TrainingRun[]>([]);
  const [queueCount, setQueueCount]   = useState<number>(0);
  const [config, setConfig]           = useState<TrainingConfig | null>(null);
  const [configDraft, setConfigDraft] = useState<Partial<TrainingConfig>>({});
  const [configOpen, setConfigOpen]   = useState(false);
  const [configSaving, setConfigSaving] = useState(false);
  const [triggerLoading, setTriggerLoading] = useState(false);
  const [rollbackTarget, setRollbackTarget] = useState<string | null>(null);
  const [toast, setToast]             = useState<{ msg: string; type: "ok" | "err" } | null>(null);

  const token   = () => localStorage.getItem("access_token") ?? "";
  const authHdr = () => ({ Authorization: `Bearer ${token()}` });

  const showToast = (msg: string, type: "ok" | "err" = "ok") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  const fetchAll = useCallback(async () => {
    try {
      const [infoR, driftR, statusR, histR, statsR, cfgR] = await Promise.all([
        fetch(`${API}/ml/model/info`,          { headers: authHdr() }),
        fetch(`${API}/ml/drift`,               { headers: authHdr() }),
        fetch(`${API}/review/training/status`, { headers: authHdr() }),
        fetch(`${API}/review/training/history`,{ headers: authHdr() }),
        fetch(`${API}/review/stats`,           { headers: authHdr() }),
        fetch(`${API}/review/training/config`, { headers: authHdr() }),
      ]);
      if (infoR.ok)   setModelInfo(await infoR.json());
      if (driftR.ok)  setDrift(await driftR.json());
      if (statusR.ok) setTrainStatus(await statusR.json());
      if (histR.ok)   setHistory(await histR.json());
      if (statsR.ok)  { const s = await statsR.json(); setQueueCount(s.pending ?? 0); }
      if (cfgR.ok)    { const c = await cfgR.json(); setConfig(c); setConfigDraft(c); }
    } catch (e) {
      console.error("MonitoringML fetchAll:", e);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, 15_000);
    return () => clearInterval(id);
  }, [fetchAll]);

  const triggerTraining = async () => {
    setTriggerLoading(true);
    try {
      const r = await fetch(`${API}/review/training/trigger`, {
        method: "POST", headers: authHdr(),
      });
      if (r.ok) { showToast("Fine-tuning déclenché \u2713"); fetchAll(); }
      else showToast("Erreur déclenchement", "err");
    } finally { setTriggerLoading(false); }
  };

  const saveConfig = async () => {
    setConfigSaving(true);
    try {
      const r = await fetch(`${API}/review/training/config`, {
        method: "PUT",
        headers: { ...authHdr(), "Content-Type": "application/json" },
        body: JSON.stringify(configDraft),
      });
      if (r.ok) { showToast("Configuration sauvegardée \u2713"); fetchAll(); }
      else showToast("Erreur sauvegarde config", "err");
    } finally { setConfigSaving(false); }
  };

  const doRollback = async (runId: string) => {
    try {
      const r = await fetch(`${API}/review/training/rollback/${runId}`, {
        method: "POST", headers: authHdr(),
      });
      if (r.ok) { showToast("Rollback effectué \u2713"); setRollbackTarget(null); fetchAll(); }
      else showToast("Erreur rollback", "err");
    } catch { showToast("Erreur rollback", "err"); }
  };

  const chartData = [...history]
    .filter(r => r.far_after != null)
    .sort((a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime())
    .map(r => ({
      date: new Date(r.start_time).toLocaleDateString("fr-FR"),
      FAR:  r.far_after  != null ? +(r.far_after  * 100).toFixed(4) : null,
      EER:  r.eer_after  != null ? +(r.eer_after  * 100).toFixed(4) : null,
    }));

  return (
    <div className="p-6 space-y-6 bg-gray-50 min-h-screen">

      {/* Toast */}
      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-2 rounded-lg text-white shadow-lg text-sm font-medium
          ${toast.type === "ok" ? "bg-green-600" : "bg-red-600"}`}>
          {toast.msg}
        </div>
      )}

      {/* Rollback modal */}
      {rollbackTarget && (
        <div className="fixed inset-0 bg-black/50 z-40 flex items-center justify-center">
          <div className="bg-white rounded-xl p-6 shadow-2xl max-w-sm w-full space-y-4">
            <h3 className="font-bold text-lg">Confirmer le rollback</h3>
            <p className="text-sm text-gray-600">
              Restaurer le modèle au run{" "}
              <code className="bg-gray-100 px-1 rounded font-mono">
                {rollbackTarget.slice(0, 8)}…
              </code>
              {" "}? Le modèle actif sera remplacé.
            </p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setRollbackTarget(null)}
                className="px-4 py-2 rounded-lg border text-sm">Annuler</button>
              <button onClick={() => doRollback(rollbackTarget)}
                className="px-4 py-2 rounded-lg bg-red-600 text-white text-sm font-semibold">
                Confirmer
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Monitoring ML</h1>
          <p className="text-sm text-gray-500">
            Modèle : <span className="font-mono">{modelInfo?.model_name ?? "—"}</span>
            {" · "}Version : <span className="font-mono">{modelInfo?.version ?? "—"}</span>
            {" · "}{modelInfo?.n_profiles ?? 0} profils
          </p>
        </div>
        <div className="flex items-center gap-3">
          {trainStatus.running ? (
            <span className="flex items-center gap-2 px-3 py-1.5 bg-purple-100 text-purple-800 rounded-full text-sm font-semibold">
              <span className="inline-block w-2 h-2 bg-purple-500 rounded-full animate-pulse" />
              Fine-tuning en cours
            </span>
          ) : (
            <span className="px-3 py-1.5 bg-gray-100 text-gray-600 rounded-full text-sm">Idle</span>
          )}
          <button
            onClick={triggerTraining}
            disabled={triggerLoading || trainStatus.running}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-semibold
              disabled:opacity-50 hover:bg-purple-700 transition-colors"
          >
            {triggerLoading ? "Lancement…" : "Déclencher fine-tuning"}
          </button>
        </div>
      </div>

      {/* 6 metric cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <MetricCard
          label="FAR" value={modelInfo?.far ?? null} target="< 0.1%"
          colorClass="border-red-300 bg-red-50 text-red-900"
        />
        <MetricCard
          label="FRR" value={modelInfo?.frr ?? null} target="< 1%"
          colorClass="border-orange-300 bg-orange-50 text-orange-900"
        />
        <MetricCard
          label="EER" value={modelInfo?.eer ?? null} target="< 0.5%"
          colorClass="border-purple-300 bg-purple-50 text-purple-900"
        />
        <MetricCard
          label="TAR" value={modelInfo?.tar ?? null} target="> 99%"
          colorClass="border-green-300 bg-green-50 text-green-900"
        />
        {/* Drift card */}
        <div className={`rounded-xl border-2 p-4 flex flex-col gap-1
          ${drift?.alert
            ? "border-yellow-500 bg-yellow-50 text-yellow-900"
            : "border-yellow-200 bg-yellow-50 text-yellow-800"}`}>
          <span className="text-xs font-semibold uppercase tracking-wider opacity-70">Drift Score</span>
          <span className="text-3xl font-bold">
            {drift ? drift.drift_score.toFixed(4) : "—"}
          </span>
          <span className="text-xs opacity-60">
            {drift?.alert ? "⚠ Dérive détectée" : "Stable"} · Cible &lt; 0.05
          </span>
        </div>
        {/* AL Queue card */}
        <div className="rounded-xl border-2 border-blue-300 bg-blue-50 text-blue-900 p-4 flex flex-col gap-1">
          <span className="text-xs font-semibold uppercase tracking-wider opacity-70">File AL</span>
          <span className="text-3xl font-bold">{queueCount}</span>
          <span className="text-xs opacity-60">Frames en attente</span>
        </div>
      </div>

      {/* Evolution chart */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
        <h2 className="font-semibold text-gray-800 mb-4">
          Évolution FAR / EER (après chaque run)
        </h2>
        {chartData.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-10">Aucun historique disponible</p>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={v => v + "%"} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v: number) => v.toFixed(4) + "%"} />
              <Legend />
              <Line type="monotone" dataKey="FAR" stroke="#ef4444" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="EER" stroke="#9333ea" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Config panel */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <button
          onClick={() => setConfigOpen(o => !o)}
          className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-gray-50 transition-colors"
        >
          <span className="font-semibold text-gray-800">⚙️ Configuration fine-tuning</span>
          <span className="text-gray-400 text-sm">{configOpen ? "▲ Replier" : "▼ Déplier"}</span>
        </button>
        {configOpen && config && (
          <div className="px-5 pb-5 border-t border-gray-100">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5 pt-4">
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">
                  Seuil de déclenchement (nb labels)
                </label>
                <input
                  type="number" min={1}
                  value={configDraft.FINE_TUNE_THRESHOLD ?? config.FINE_TUNE_THRESHOLD}
                  onChange={e => setConfigDraft(d => ({ ...d, FINE_TUNE_THRESHOLD: e.target.value }))}
                  className="w-full border rounded-lg px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">
                  Amélioration minimum (%)
                </label>
                <input
                  type="number" min={0} max={100} step={0.1}
                  value={configDraft.MIN_IMPROVEMENT_PCT ?? config.MIN_IMPROVEMENT_PCT}
                  onChange={e => setConfigDraft(d => ({ ...d, MIN_IMPROVEMENT_PCT: e.target.value }))}
                  className="w-full border rounded-lg px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">
                  Confiance min AL : {configDraft.CONFIDENCE_MIN ?? config.CONFIDENCE_MIN}
                </label>
                <input
                  type="range" min={0} max={1} step={0.01}
                  value={configDraft.CONFIDENCE_MIN ?? config.CONFIDENCE_MIN}
                  onChange={e => setConfigDraft(d => ({ ...d, CONFIDENCE_MIN: e.target.value }))}
                  className="w-full accent-purple-600"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">
                  Confiance max AL : {configDraft.CONFIDENCE_MAX ?? config.CONFIDENCE_MAX}
                </label>
                <input
                  type="range" min={0} max={1} step={0.01}
                  value={configDraft.CONFIDENCE_MAX ?? config.CONFIDENCE_MAX}
                  onChange={e => setConfigDraft(d => ({ ...d, CONFIDENCE_MAX: e.target.value }))}
                  className="w-full accent-purple-600"
                />
              </div>
              <div className="flex items-center gap-3 col-span-full">
                <input
                  type="checkbox" id="auto-deploy"
                  checked={(configDraft.AUTO_DEPLOY ?? config.AUTO_DEPLOY) === "true"}
                  onChange={e => setConfigDraft(d => ({ ...d, AUTO_DEPLOY: e.target.checked ? "true" : "false" }))}
                  className="w-4 h-4 accent-purple-600"
                />
                <label htmlFor="auto-deploy" className="text-sm text-gray-700">
                  Déploiement automatique si l’amélioration est atteinte
                </label>
              </div>
            </div>
            <button
              onClick={saveConfig}
              disabled={configSaving}
              className="mt-4 px-5 py-2 bg-purple-600 text-white rounded-lg text-sm font-semibold
                disabled:opacity-50 hover:bg-purple-700 transition-colors"
            >
              {configSaving ? "Sauvegarde…" : "Appliquer"}
            </button>
          </div>
        )}
      </div>

      {/* History table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100">
          <h2 className="font-semibold text-gray-800">Historique des runs MLflow</h2>
        </div>
        {history.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-10">Aucun run enregistré</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500 uppercase tracking-wide">
                <tr>
                  <th className="px-4 py-3 text-left">Run ID</th>
                  <th className="px-4 py-3 text-left">Date</th>
                  <th className="px-4 py-3 text-left">Statut</th>
                  <th className="px-4 py-3 text-right">FAR avant→après</th>
                  <th className="px-4 py-3 text-right">EER avant→après</th>
                  <th className="px-4 py-3 text-right">Amélioration</th>
                  <th className="px-4 py-3 text-center">Résultat</th>
                  <th className="px-4 py-3 text-right">Samples</th>
                  <th className="px-4 py-3 text-center">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {history.map(run => (
                  <tr key={run.run_id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3 font-mono text-xs text-gray-500">
                      {run.run_id.slice(0, 8)}…
                    </td>
                    <td className="px-4 py-3 text-gray-700 whitespace-nowrap">
                      {run.start_time
                        ? new Date(run.start_time).toLocaleString("fr-FR")
                        : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-semibold
                        ${
                          run.status === "FINISHED" ? "bg-green-100 text-green-800" :
                          run.status === "FAILED"   ? "bg-red-100 text-red-800"   :
                          run.status === "RUNNING"  ? "bg-blue-100 text-blue-800"  :
                          "bg-gray-100 text-gray-600"
                        }`}>
                        {run.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs">
                      {pct(run.far_before)} → {pct(run.far_after)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs">
                      {pct(run.eer_before)} → {pct(run.eer_after)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs">
                      {run.improvement_pct != null ? (
                        <span className={run.improvement_pct > 0 ? "text-green-700" : "text-red-600"}>
                          {run.improvement_pct > 0 ? "+" : ""}
                          {run.improvement_pct.toFixed(2)}%
                        </span>
                      ) : "—"}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <OutcomeBadge outcome={run.outcome} />
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600">
                      {run.n_samples ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {run.outcome === "deployed" && (
                        <button
                          onClick={() => setRollbackTarget(run.run_id)}
                          className="px-3 py-1 rounded-lg bg-red-50 text-red-700 border border-red-200
                            text-xs font-semibold hover:bg-red-100 transition-colors"
                        >
                          Rollback
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
