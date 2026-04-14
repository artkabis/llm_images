import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { format } from "date-fns";

// ── Types ─────────────────────────────────────────────────────────
interface Candidate { profile_id: string; score: number; name?: string; }
interface ReviewItem {
  id: string; camera_id: string; confidence: number;
  suggested_profile_id?: string; candidates?: Candidate[];
  created_at?: string; status: string;
}
interface QueueResponse {
  items: ReviewItem[]; total_pending: number; labeled_count: number;
  trigger_threshold: number; next_trigger_in: number; progress_pct: number;
}
interface StatsResponse {
  counts: Record<string, number>;
  labeled_since_last_training: number;
  trigger_threshold: number; next_trigger_in: number; progress_pct: number;
}
interface TrainingStatus { is_running: boolean; }

// ── Constantes ─────────────────────────────────────────────────────
const ACTIONS = [
  { value: "confirmed",   label: "Confirmer",      icon: "✓", color: "bg-green-700 hover:bg-green-600",  ring: "ring-green-400" },
  { value: "corrected",   label: "Corriger",        icon: "✎", color: "bg-yellow-700 hover:bg-yellow-600", ring: "ring-yellow-400" },
  { value: "new_profile", label: "Nouveau profil",  icon: "+", color: "bg-blue-700 hover:bg-blue-600",    ring: "ring-blue-400" },
  { value: "intruder",    label: "Intrus",          icon: "⚠", color: "bg-red-700 hover:bg-red-600",      ring: "ring-red-400" },
  { value: "rejected",    label: "Rejeter (flou)",  icon: "×", color: "bg-gray-700 hover:bg-gray-600",    ring: "ring-gray-400" },
] as const;

// ── Helpers ─────────────────────────────────────────────────────────
function confidenceColor(score: number) {
  if (score < 75) return "text-red-400";
  if (score < 82) return "text-orange-400";
  return "text-yellow-400";
}

// ── Composant principal ───────────────────────────────────────────────
export default function Review() {
  const [current, setCurrent] = useState(0);
  const [action, setAction] = useState<string | null>(null);
  const [correctedId, setCorrectedId] = useState("");
  const [note, setNote] = useState("");
  const [zoom, setZoom] = useState(false);
  const [cameraFilter, setCameraFilter] = useState("");
  const [toast, setToast] = useState<string | null>(null);
  const qc = useQueryClient();

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 4000);
  };

  const { data: queue, isLoading } = useQuery<QueueResponse>({
    queryKey: ["review-queue", cameraFilter],
    queryFn: () =>
      axios.get("/api/v1/review/queue", {
        params: { camera_id: cameraFilter || undefined },
      }).then((r) => r.data),
    refetchInterval: 30000,
  });

  const { data: stats } = useQuery<StatsResponse>({
    queryKey: ["review-stats"],
    queryFn: () => axios.get("/api/v1/review/stats").then((r) => r.data),
    refetchInterval: 15000,
  });

  const { data: trainingStatus } = useQuery<TrainingStatus>({
    queryKey: ["training-status"],
    queryFn: () => axios.get("/api/v1/review/training/status").then((r) => r.data),
    refetchInterval: 10000,
  });

  const label = useMutation({
    mutationFn: ({ id, body }: { id: string; body: object }) =>
      axios.post(`/api/v1/review/${id}/label`, body),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["review-queue"] });
      qc.invalidateQueries({ queryKey: ["review-stats"] });
      setCurrent(0);
      setAction(null);
      setCorrectedId("");
      setNote("");
      if (res.data.fine_tuning_triggered) {
        showToast("⚡ Seuil atteint — fine-tuning déclenché automatiquement !");
      } else {
        showToast("Label enregistré");
      }
    },
  });

  const handleSubmit = () => {
    if (!item || !action) return;
    if (action === "corrected" && !correctedId.trim()) return;
    label.mutate({
      id: item.id,
      body: {
        action,
        profile_id: action === "corrected" ? correctedId : undefined,
        note: note || undefined,
      },
    });
  };

  const items = queue?.items ?? [];
  const item = items[current];
  const threshold = stats?.trigger_threshold ?? 50;
  const labeledMod = stats?.labeled_since_last_training ?? 0;
  const progressPct = stats?.progress_pct ?? 0;

  if (isLoading) return <div className="p-6 text-gray-500 text-sm">Chargement...</div>;

  return (
    <div className="p-6 space-y-4">
      {/* Toast */}
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-blue-600 text-white text-sm px-4 py-2 rounded shadow-lg">
          {toast}
        </div>
      )}

      {/* Zoom modal */}
      {zoom && item && (
        <div
          className="fixed inset-0 z-40 bg-black/80 flex items-center justify-center"
          onClick={() => setZoom(false)}
        >
          <img
            src={`/api/v1/review/${item.id}/frame`}
            alt="frame zoom"
            className="max-h-[90vh] max-w-[90vw] object-contain rounded"
          />
        </div>
      )}

      {/* En-tête */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-white">Review — Active Learning</h2>
        <div className="flex items-center gap-3">
          {trainingStatus?.is_running && (
            <span className="flex items-center gap-1 text-xs text-purple-300 animate-pulse">
              <span className="w-2 h-2 rounded-full bg-purple-400 inline-block" />
              Fine-tuning en cours...
            </span>
          )}
          <span className="text-xs text-gray-400">
            <span className="text-white font-semibold">{queue?.total_pending ?? 0}</span> en attente
          </span>
        </div>
      </div>

      {/* Stats par statut */}
      {stats && (
        <div className="grid grid-cols-5 gap-2">
          {[
            { key: "pending",   label: "En attente", color: "text-gray-400" },
            { key: "confirmed", label: "Confirmés",  color: "text-green-400" },
            { key: "corrected", label: "Corrigés",   color: "text-yellow-400" },
            { key: "intruder",  label: "Intrus",     color: "text-red-400" },
            { key: "rejected",  label: "Rejetés",    color: "text-gray-500" },
          ].map(({ key, label: lbl, color }) => (
            <div key={key} className="bg-gray-800 rounded p-2 text-center">
              <p className={`text-lg font-bold ${color}`}>{stats.counts[key] ?? 0}</p>
              <p className="text-xs text-gray-500">{lbl}</p>
            </div>
          ))}
        </div>
      )}

      {/* Progression fine-tuning */}
      <div className="bg-gray-800 rounded-lg p-3">
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span>Progression vers fine-tuning</span>
          <span className="text-white">
            {labeledMod}/{threshold}
            {stats && stats.next_trigger_in > 0 && (
              <span className="text-gray-500"> — encore {stats.next_trigger_in} labels</span>
            )}
          </span>
        </div>
        <div className="h-2 bg-gray-700 rounded">
          <div
            className="h-2 bg-blue-500 rounded transition-all duration-500"
            style={{ width: `${Math.min(progressPct, 100)}%` }}
          />
        </div>
      </div>

      {/* Filtre caméra */}
      <div className="flex items-center gap-2">
        <label className="text-xs text-gray-400">Caméra :</label>
        <input
          value={cameraFilter}
          onChange={(e) => { setCameraFilter(e.target.value); setCurrent(0); }}
          placeholder="Toutes"
          className="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs text-white w-40 focus:outline-none focus:border-blue-500"
        />
        {cameraFilter && (
          <button
            onClick={() => setCameraFilter("")}
            className="text-xs text-gray-500 hover:text-white"
          >
            × Effacer
          </button>
        )}
      </div>

      {items.length === 0 ? (
        <div className="bg-gray-800 rounded-lg p-8 text-center text-gray-500 text-sm">
          Aucune frame en attente de review.
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-6">
          {/* Colonne gauche : image + metadata + candidats */}
          <div className="space-y-3">
            <div className="bg-gray-800 rounded-lg p-4 space-y-3">
              {/* Image */}
              <div
                className="aspect-video bg-gray-700 rounded flex items-center justify-center overflow-hidden cursor-zoom-in relative"
                onClick={() => setZoom(true)}
              >
                {item?.id ? (
                  <img
                    src={`/api/v1/review/${item.id}/frame`}
                    alt="frame"
                    className="object-contain w-full h-full"
                  />
                ) : (
                  <span className="text-gray-500 text-xs">Aperçu non disponible</span>
                )}
                <span className="absolute bottom-1 right-1 text-xs text-gray-400 bg-black/50 px-1 rounded">
                  ⛶ zoom
                </span>
              </div>

              {/* Métadonnées */}
              <div className="space-y-1 text-xs text-gray-400">
                <p>Caméra : <span className="text-white">{item?.camera_id}</span></p>
                <p>
                  Score :{" "}
                  <span className={`font-bold ${confidenceColor(item?.confidence ?? 0)}`}>
                    {item?.confidence?.toFixed(1)}%
                  </span>
                </p>
                {item?.created_at && (
                  <p>Date : <span className="text-white">{format(new Date(item.created_at), "dd/MM HH:mm:ss")}</span></p>
                )}
              </div>

              {/* Navigation */}
              <div className="flex justify-between text-xs text-gray-500 pt-1">
                <button
                  onClick={() => setCurrent(Math.max(0, current - 1))}
                  disabled={current === 0}
                  className="disabled:opacity-40 hover:text-white"
                >
                  ← Préc
                </button>
                <span className="text-gray-400">{current + 1} / {items.length}</span>
                <button
                  onClick={() => setCurrent(Math.min(items.length - 1, current + 1))}
                  disabled={current === items.length - 1}
                  className="disabled:opacity-40 hover:text-white"
                >
                  Suiv →
                </button>
              </div>
            </div>

            {/* Top-k candidats */}
            {item?.candidates && item.candidates.length > 0 && (
              <div className="bg-gray-800 rounded-lg p-3 space-y-2">
                <p className="text-xs text-gray-400 font-semibold">Candidats suggérés</p>
                {item.candidates.slice(0, 3).map((c, i) => (
                  <button
                    key={i}
                    onClick={() => {
                      setCorrectedId(c.profile_id);
                      setAction("corrected");
                    }}
                    className="w-full flex justify-between items-center bg-gray-700 hover:bg-gray-600 rounded px-3 py-2 text-xs transition-colors"
                  >
                    <span className="text-white font-mono truncate max-w-[60%]">{c.profile_id}</span>
                    <span className="text-blue-400 font-semibold">{(c.score * 100).toFixed(1)}%</span>
                  </button>
                ))}
                <p className="text-xs text-gray-600">Cliquer pour pré-remplir la correction</p>
              </div>
            )}
          </div>

          {/* Colonne droite : actions */}
          <div className="bg-gray-800 rounded-lg p-4 space-y-4">
            <p className="text-sm font-semibold text-white">Que faire de cette frame ?</p>

            {/* 5 boutons d'action */}
            <div className="grid grid-cols-1 gap-2">
              {ACTIONS.map((a) => (
                <button
                  key={a.value}
                  onClick={() => setAction(a.value)}
                  className={`flex items-center gap-2 text-sm text-white py-2 px-3 rounded transition-colors ${
                    a.color
                  } ${action === a.value ? `ring-2 ${a.ring}` : ""}`}
                >
                  <span className="w-5 text-center font-bold">{a.icon}</span>
                  {a.label}
                </button>
              ))}
            </div>

            {/* Champ ID pour correction */}
            {action === "corrected" && (
              <div>
                <label className="text-xs text-gray-400 block mb-1">ID du bon profil</label>
                <input
                  value={correctedId}
                  onChange={(e) => setCorrectedId(e.target.value)}
                  placeholder="profile-uuid..."
                  className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-xs text-white focus:outline-none focus:border-yellow-500"
                />
              </div>
            )}

            {/* Note opérateur */}
            <div>
              <label className="text-xs text-gray-400 block mb-1">Note (optionnel)</label>
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
                placeholder="Contexte, observation..."
                className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500 resize-none"
              />
            </div>

            <button
              onClick={handleSubmit}
              disabled={
                !action ||
                (action === "corrected" && !correctedId.trim()) ||
                label.isPending
              }
              className="w-full bg-blue-600 hover:bg-blue-700 text-white text-sm py-2 rounded font-semibold disabled:opacity-40 transition-colors"
            >
              {label.isPending ? "Envoi..." : "Valider ce label"}
            </button>

            {label.isError && (
              <p className="text-xs text-red-400 text-center">Erreur d'envoi. Reessayer.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
