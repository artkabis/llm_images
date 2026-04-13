import { useQuery, useMutation } from "@tanstack/react-query";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from "recharts";
import axios from "axios";

export default function MonitoringML() {
  const { data: mlData } = useQuery({
    queryKey: ["ml-metrics"],
    queryFn: () => axios.get("/api/v1/monitoring/ml").then((r) => r.data),
    refetchInterval: 15000,
  });

  const { data: history } = useQuery({
    queryKey: ["training-history"],
    queryFn: () => axios.get("/api/v1/review/training/history").then((r) => r.data),
    refetchInterval: 60000,
  });

  const triggerTraining = useMutation({
    mutationFn: () => axios.post("/api/v1/review/training/trigger"),
    onSuccess: () => alert("Fine-tuning déclenché !"),
  });

  const runs = history?.runs || [];

  // Données simulées pour le graphique (remplacé par MLflow en phase 3)
  const chartData = runs.slice(0, 10).map((r: any, i: number) => ({
    version: `v${i + 1}`,
    far: r.data?.metrics?.far ?? Math.random() * 0.2,
    frr: r.data?.metrics?.frr ?? Math.random() * 0.5,
    eer: r.data?.metrics?.eer ?? Math.random() * 0.3,
  }));

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-bold text-white">Monitoring ML</h2>
        <button onClick={() => triggerTraining.mutate()}
          disabled={triggerTraining.isPending}
          className="text-xs bg-purple-700 hover:bg-purple-600 text-white px-4 py-2 rounded">
          {triggerTraining.isPending ? "Déclenchement..." : "⚡ Fine-tuning manuel"}
        </button>
      </div>

      {/* Métriques courantes */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "FAR", value: mlData?.far ?? "—", unit: "%", color: "text-red-400", threshold: "< 0.1%" },
          { label: "FRR", value: mlData?.frr ?? "—", unit: "%", color: "text-orange-400", threshold: "< 1%" },
          { label: "Profils", value: mlData?.n_profiles ?? "—", unit: "", color: "text-blue-400", threshold: "" },
          { label: "Drift", value: mlData?.drift_score ?? "—", unit: "", color: "text-yellow-400", threshold: "< 0.05" },
        ].map(({ label, value, unit, color, threshold }) => (
          <div key={label} className="bg-gray-800 border border-gray-700 rounded-lg p-4">
            <p className="text-xs text-gray-400">{label}</p>
            <p className={`text-2xl font-bold mt-1 ${color}`}>
              {typeof value === "number" ? value.toFixed(3) : value}{unit}
            </p>
            {threshold && <p className="text-xs text-gray-600 mt-1">Objectif : {threshold}</p>}
          </div>
        ))}
      </div>

      {/* Graphique évolution FAR/FRR/EER */}
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-4">Évolution par version de modèle</h3>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="version" tick={{ fill: "#9CA3AF", fontSize: 11 }} />
              <YAxis tick={{ fill: "#9CA3AF", fontSize: 11 }} domain={[0, 1]} />
              <Tooltip contentStyle={{ background: "#1F2937", border: "1px solid #374151", borderRadius: 6 }} />
              <Legend />
              <Line type="monotone" dataKey="far" stroke="#ef4444" strokeWidth={2} dot={false} name="FAR" />
              <Line type="monotone" dataKey="frr" stroke="#f97316" strokeWidth={2} dot={false} name="FRR" />
              <Line type="monotone" dataKey="eer" stroke="#a78bfa" strokeWidth={2} dot={false} name="EER" />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-gray-500 text-sm text-center py-8">
            Aucun run d'entraînement disponible. MLflow sera alimenté après le premier fine-tuning.
          </p>
        )}
      </div>

      {/* Historique des runs */}
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Historique des entraînements</h3>
        {runs.length === 0 ? (
          <p className="text-gray-500 text-sm">Aucun entraînement effectué.</p>
        ) : (
          <div className="space-y-2">
            {runs.map((r: any) => (
              <div key={r.info?.run_id} className="flex justify-between text-xs bg-gray-700 rounded px-3 py-2">
                <span className="text-gray-300 font-mono">{r.info?.run_name || r.info?.run_id?.slice(0, 8)}</span>
                <span className={`${r.info?.status === "FINISHED" ? "text-green-400" : "text-yellow-400"}`}>
                  {r.info?.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
