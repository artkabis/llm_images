import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import axios from "axios";

interface ResourceSnapshot { time: string; cpu: number; ram: number; disk: number; }

function GaugeBar({ label, value, unit = "%", warn = 70, critical = 85 }: {
  label: string; value: number | null; unit?: string; warn?: number; critical?: number;
}) {
  const v = value ?? 0;
  const color = v >= critical ? "bg-red-500" : v >= warn ? "bg-orange-400" : "bg-green-500";
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-gray-400">{label}</span>
        <span className={v >= critical ? "text-red-400" : v >= warn ? "text-orange-400" : "text-green-400"}>
          {value !== null ? `${v.toFixed(1)}${unit}` : "N/A"}
        </span>
      </div>
      <div className="h-3 bg-gray-700 rounded">
        <div className={`h-3 rounded transition-all ${color}`} style={{ width: `${Math.min(v, 100)}%` }} />
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const s: Record<string, string> = {
    ok:       "bg-green-900 text-green-400",
    degraded: "bg-orange-900 text-orange-400",
    down:     "bg-red-900 text-red-400",
    unknown:  "bg-gray-700 text-gray-400",
  };
  return <span className={`text-xs px-2 py-0.5 rounded ${s[status] || s.unknown}`}>{status}</span>;
}

export default function MonitoringSystem() {
  const [history, setHistory] = useState<ResourceSnapshot[]>([]);

  const { data: resources } = useQuery({
    queryKey: ["system-resources"],
    queryFn: () => axios.get("/api/v1/monitoring/system/resources").then((r) => r.data),
    refetchInterval: 5000,
  });

  const { data: health } = useQuery({
    queryKey: ["system-health"],
    queryFn: () => axios.get("/api/v1/monitoring/health").then((r) => r.data),
    refetchInterval: 10000,
  });

  const { data: cameras } = useQuery({
    queryKey: ["cameras-status"],
    queryFn: () => axios.get("/api/v1/monitoring/cameras/status").then((r) => r.data),
    refetchInterval: 10000,
  });

  // Historique glissant (60 points = 5 min à 5s d'intervalle)
  useEffect(() => {
    if (!resources) return;
    setHistory((h) => [
      ...h.slice(-59),
      {
        time: new Date().toLocaleTimeString(),
        cpu: resources.cpu_percent,
        ram: resources.ram_percent,
        disk: resources.disk_percent,
      },
    ]);
  }, [resources]);

  const services = health?.services || {};

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-lg font-bold text-white">Monitoring Système</h2>

      {/* Statut services */}
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Statut des services</h3>
        <div className="grid grid-cols-4 gap-3">
          {Object.entries(services).map(([svc, status]) => (
            <div key={svc} className="flex justify-between items-center bg-gray-700 rounded px-3 py-2">
              <span className="text-xs text-gray-300 capitalize">{svc}</span>
              <StatusBadge status={status as string} />
            </div>
          ))}
        </div>
      </div>

      {/* Jauges ressources */}
      <div className="bg-gray-800 rounded-lg p-4 space-y-4">
        <h3 className="text-sm font-semibold text-gray-300">Ressources temps réel</h3>
        <GaugeBar label="CPU" value={resources?.cpu_percent ?? null} warn={75} critical={85} />
        <GaugeBar label={`RAM (${resources?.ram_used_gb ?? 0} / ${resources?.ram_total_gb ?? 0} Go)`} value={resources?.ram_percent ?? null} warn={70} critical={80} />
        <GaugeBar label={`Disque (${resources?.disk_used_gb ?? 0} / ${resources?.disk_total_gb ?? 0} Go)`} value={resources?.disk_percent ?? null} warn={70} critical={85} />
        {resources?.gpu_percent !== null && resources?.gpu_percent !== undefined && (
          <GaugeBar label={`GPU VRAM (${resources?.gpu_vram_used_mb ?? 0} / ${resources?.gpu_vram_total_mb ?? 0} Mo)`} value={resources.gpu_percent} warn={80} critical={90} />
        )}
        <div className="grid grid-cols-2 gap-3 pt-2 border-t border-gray-700">
          <div className="text-xs text-gray-400">Réseau envoyé : <span className="text-white">{resources?.net_sent_mb ?? 0} Mo</span></div>
          <div className="text-xs text-gray-400">Réseau reçu : <span className="text-white">{resources?.net_recv_mb ?? 0} Mo</span></div>
        </div>
      </div>

      {/* Graphique historique */}
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Évolution (5 dernières minutes)</h3>
        <ResponsiveContainer width="100%" height={180}>
          <AreaChart data={history}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="time" tick={{ fill: "#6B7280", fontSize: 10 }} interval="preserveStartEnd" />
            <YAxis domain={[0, 100]} tick={{ fill: "#6B7280", fontSize: 10 }} unit="%" />
            <Tooltip contentStyle={{ background: "#1F2937", border: "1px solid #374151", borderRadius: 6 }} />
            <Area type="monotone" dataKey="cpu"  stroke="#3b82f6" fill="#1e3a5f" strokeWidth={2} name="CPU" />
            <Area type="monotone" dataKey="ram"  stroke="#f97316" fill="#431407" strokeWidth={2} name="RAM" />
            <Area type="monotone" dataKey="disk" stroke="#22c55e" fill="#14532d" strokeWidth={2} name="Disque" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Statut caméras */}
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Statut caméras</h3>
        {(cameras?.cameras || []).length === 0 ? (
          <p className="text-gray-500 text-sm">Service vidéo indisponible ou aucune caméra configurée.</p>
        ) : (
          <div className="grid grid-cols-3 gap-3">
            {cameras.cameras.map((c: any) => (
              <div key={c.id} className="bg-gray-700 rounded px-3 py-2">
                <p className="text-xs text-white font-semibold">{c.id}</p>
                <StatusBadge status={c.status === 1 ? "ok" : c.status === 2 ? "degraded" : "down"} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
