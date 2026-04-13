import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { format } from "date-fns";

const LEVEL_STYLE: Record<string, string> = {
  INFO:     "text-blue-400 border-blue-700",
  WARNING:  "text-orange-400 border-orange-700",
  ALERT:    "text-red-400 border-red-700",
  CRITICAL: "text-red-300 border-red-500 animate-pulse",
};

export default function Alerts() {
  const [statusFilter, setStatusFilter] = useState("open");
  const [levelFilter, setLevelFilter] = useState("");
  const [page, setPage] = useState(1);
  const [ackNote, setAckNote] = useState<{ id: string; note: string } | null>(null);
  const qc = useQueryClient();

  const { data: alerts = [], isLoading } = useQuery({
    queryKey: ["alerts", statusFilter, levelFilter, page],
    queryFn: () =>
      axios.get("/api/v1/alerts/", {
        params: { status: statusFilter || undefined, level: levelFilter || undefined, page },
      }).then((r) => r.data),
    refetchInterval: 10000,
  });

  const ack = useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) =>
      axios.post(`/api/v1/alerts/${id}/ack`, { note }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["alerts"] }); setAckNote(null); },
  });

  const exportCSV = () => { window.open("/api/v1/alerts/export/csv", "_blank"); };

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-white">Alertes & Incidents</h2>
        <button onClick={exportCSV} className="text-xs bg-gray-700 hover:bg-gray-600 text-white px-3 py-1.5 rounded">
          Export CSV
        </button>
      </div>

      {/* Filtres */}
      <div className="flex gap-3">
        {[["", "Tous statuts"], ["open", "Ouverts"], ["acknowledged", "Acquittés"]].map(([v, l]) => (
          <button key={v} onClick={() => setStatusFilter(v)}
            className={`text-xs px-3 py-1.5 rounded ${statusFilter === v ? "bg-blue-600 text-white" : "bg-gray-700 text-gray-300"}`}>
            {l}
          </button>
        ))}
        <select value={levelFilter} onChange={(e) => setLevelFilter(e.target.value)}
          className="text-xs bg-gray-700 text-gray-300 px-3 py-1.5 rounded border border-gray-600">
          <option value="">Tous niveaux</option>
          {["INFO","WARNING","ALERT","CRITICAL"].map(l => <option key={l} value={l}>{l}</option>)}
        </select>
      </div>

      {/* Liste */}
      {isLoading ? <p className="text-gray-500 text-sm">Chargement...</p> : (
        <div className="space-y-2">
          {alerts.map((a: any) => (
            <div key={a.id} className={`bg-gray-800 border-l-4 rounded p-4 ${LEVEL_STYLE[a.level] || "border-gray-600"}`}>
              <div className="flex justify-between items-start">
                <div>
                  <span className={`text-xs font-bold ${LEVEL_STYLE[a.level]?.split(" ")[0]}`}>{a.level}</span>
                  <span className="text-xs text-gray-400 ml-3">{a.camera_id}</span>
                  <span className="text-xs text-gray-500 ml-3">
                    {format(new Date(a.created_at), "dd/MM/yyyy HH:mm:ss")}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-400">{(a.confidence * 100).toFixed(1)}%</span>
                  {a.status === "open" && (
                    <button onClick={() => setAckNote({ id: a.id, note: "" })}
                      className="text-xs bg-gray-700 hover:bg-gray-600 px-2 py-1 rounded text-white">
                      Acquitter
                    </button>
                  )}
                  {a.status === "acknowledged" && (
                    <span className="text-xs text-green-500">✓ Acquitté</span>
                  )}
                </div>
              </div>
              {a.profile_id && <p className="text-xs text-gray-400 mt-1">Profil : {a.profile_id}</p>}
              {a.operator_note && <p className="text-xs text-gray-500 mt-1 italic">Note : {a.operator_note}</p>}
            </div>
          ))}
          {alerts.length === 0 && <p className="text-gray-500 text-sm">Aucune alerte.</p>}
        </div>
      )}

      {/* Modal acquittement */}
      {ackNote && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 w-96">
            <h3 className="text-sm font-bold text-white mb-3">Acquitter l'alerte</h3>
            <textarea value={ackNote.note} onChange={(e) => setAckNote({ ...ackNote, note: e.target.value })}
              placeholder="Note obligatoire..."
              className="w-full bg-gray-700 text-white text-sm rounded p-2 h-20 resize-none border border-gray-600 focus:outline-none focus:border-blue-500" />
            <div className="flex gap-2 mt-3">
              <button onClick={() => ack.mutate({ id: ackNote.id, note: ackNote.note })}
                disabled={!ackNote.note.trim()}
                className="flex-1 bg-blue-600 hover:bg-blue-700 text-white text-sm py-1.5 rounded disabled:opacity-40">
                Confirmer
              </button>
              <button onClick={() => setAckNote(null)} className="flex-1 bg-gray-700 text-white text-sm py-1.5 rounded">
                Annuler
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
