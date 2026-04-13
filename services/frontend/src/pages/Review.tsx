import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { format } from "date-fns";

const ACTIONS = [
  { value: "confirmed",   label: "Confirmer",      color: "bg-green-700 hover:bg-green-600" },
  { value: "corrected",   label: "Corriger",        color: "bg-yellow-700 hover:bg-yellow-600" },
  { value: "intruder",    label: "Intrus",          color: "bg-red-700 hover:bg-red-600" },
  { value: "rejected",    label: "Rejeter (flou)",  color: "bg-gray-700 hover:bg-gray-600" },
];

export default function Review() {
  const [current, setCurrent] = useState(0);
  const [action, setAction] = useState<string | null>(null);
  const [correctedId, setCorrectedId] = useState("");
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["review-queue"],
    queryFn: () => axios.get("/api/v1/review/queue").then((r) => r.data),
  });

  const label = useMutation({
    mutationFn: ({ id, body }: { id: string; body: object }) =>
      axios.post(`/api/v1/review/${id}/label`, body),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["review-queue"] });
      setCurrent(0);
      setAction(null);
      setCorrectedId("");
      if (res.data.fine_tuning_triggered) {
        alert("Seuil atteint — fine-tuning déclenché automatiquement !");
      }
    },
  });

  const items = data?.items || [];
  const totalPending = data?.total_pending || 0;
  const threshold = data?.trigger_threshold || 50;
  const item = items[current];

  const handleSubmit = () => {
    if (!item || !action) return;
    if (action === "corrected" && !correctedId.trim()) return;
    label.mutate({
      id: item.id,
      body: { action, profile_id: action === "corrected" ? correctedId : undefined },
    });
  };

  if (isLoading) return <div className="p-6 text-gray-500 text-sm">Chargement...</div>;

  return (
    <div className="p-6 space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-bold text-white">Review — Active Learning</h2>
        <div className="text-xs text-gray-400">
          <span className="text-white font-semibold">{totalPending}</span> frames en attente
          {" · "}Fine-tuning dans <span className="text-blue-400 font-semibold">{Math.max(0, threshold - (items.length || 0))} labels</span>
        </div>
      </div>

      {/* Barre de progression */}
      <div className="bg-gray-800 rounded-lg p-3">
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span>Progression vers fine-tuning</span>
          <span>{Math.min(items.length, threshold)}/{threshold}</span>
        </div>
        <div className="h-2 bg-gray-700 rounded">
          <div className="h-2 bg-blue-500 rounded transition-all"
            style={{ width: `${Math.min((items.length / threshold) * 100, 100)}%` }} />
        </div>
      </div>

      {items.length === 0 ? (
        <div className="bg-gray-800 rounded-lg p-8 text-center text-gray-500 text-sm">
          Aucune frame en attente de review.
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-6">
          {/* Image + metadata */}
          <div className="bg-gray-800 rounded-lg p-4 space-y-3">
            <div className="aspect-video bg-gray-700 rounded flex items-center justify-center overflow-hidden">
              {item?.frame_path ? (
                <img src={`/api/v1/review/${item.id}/frame`} alt="frame"
                  className="object-contain w-full h-full" />
              ) : (
                <span className="text-gray-500 text-xs">Aperçu non disponible</span>
              )}
            </div>
            <div className="space-y-1 text-xs text-gray-400">
              <p>Caméra : <span className="text-white">{item?.camera_id}</span></p>
              <p>Score : <span className="text-orange-400 font-semibold">{item?.confidence?.toFixed(1)}%</span></p>
              {item?.created_at && (
                <p>Date : <span className="text-white">{format(new Date(item.created_at), "dd/MM HH:mm:ss")}</span></p>
              )}
            </div>
            {/* Candidats proposés */}
            {item?.suggested_profile_id && (
              <div className="border-t border-gray-700 pt-2">
                <p className="text-xs text-gray-400 mb-1">Candidat suggéré :</p>
                <span className="text-xs bg-gray-700 text-white px-2 py-1 rounded">
                  {item.suggested_profile_id}
                </span>
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="bg-gray-800 rounded-lg p-4 space-y-4">
            <p className="text-sm font-semibold text-white">Que faire de cette frame ?</p>
            <div className="grid grid-cols-2 gap-2">
              {ACTIONS.map((a) => (
                <button key={a.value} onClick={() => setAction(a.value)}
                  className={`text-xs text-white py-2 rounded transition-colors ${a.color} ${action === a.value ? "ring-2 ring-white" : ""}`}>
                  {a.label}
                </button>
              ))}
            </div>

            {action === "corrected" && (
              <div>
                <label className="text-xs text-gray-400 block mb-1">ID du bon profil</label>
                <input value={correctedId} onChange={(e) => setCorrectedId(e.target.value)}
                  placeholder="profile-uuid..."
                  className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500" />
              </div>
            )}

            <button onClick={handleSubmit}
              disabled={!action || (action === "corrected" && !correctedId.trim()) || label.isPending}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white text-sm py-2 rounded font-semibold disabled:opacity-40">
              {label.isPending ? "Envoi..." : "Valider ce label"}
            </button>

            <div className="flex justify-between text-xs text-gray-500">
              <button onClick={() => setCurrent(Math.max(0, current - 1))} disabled={current === 0}>← Précédent</button>
              <span>{current + 1} / {items.length}</span>
              <button onClick={() => setCurrent(Math.min(items.length - 1, current + 1))} disabled={current === items.length - 1}>Suivant →</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
