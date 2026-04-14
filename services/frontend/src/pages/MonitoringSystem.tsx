import React, { useEffect, useState, useRef, useCallback } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from "recharts";

const API = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";
const WS_URL = API.replace(/^http/, "ws");
const PREFIX = "/api/v1";

interface SystemResources {
  cpu_percent: number;
  ram_percent: number;
  ram_used_gb: number;
  ram_total_gb: number;
  disk_percent: number;
  disk_used_gb: number;
  disk_total_gb: number;
  net_sent_mb: number;
  net_recv_mb: number;
  gpu_percent: number | null;
  gpu_vram_used_mb: number | null;
  gpu_vram_total_mb: number | null;
}

interface ServiceHealth {
  overall: string;
  services: Record<string, string>;
}

interface HistoryPoint {
  time: string;
  cpu: number;
  ram: number;
  disk: number;
}

function GaugeBar({ value, warn, crit, label, unit = "%", max = 100 }: {
  value: number | null; warn: number; crit: number;
  label: string; unit?: string; max?: number;
}) {
  const v = value ?? 0;
  const pct = Math.min((v / max) * 100, 100);
  const color = v >= crit ? "bg-red-500" : v >= warn ? "bg-yellow-400" : "bg-green-500";
  const textColor = v >= crit ? "text-red-700" : v >= warn ? "text-yellow-700" : "text-green-700";
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
      <div className="flex justify-between items-baseline mb-2">
        <span className="text-sm font-semibold text-gray-600">{label}</span>
        <span className={`text-2xl font-bold ${textColor}`}>
          {value != null ? v.toFixed(1) + unit : "N/A"}
        </span>
      </div>
      <div className="w-full bg-gray-100 rounded-full h-3">
        <div className={`${color} h-3 rounded-full transition-all duration-500`}
          style={{ width: `${pct}%` }} />
      </div>
      <div className="flex justify-between text-xs text-gray-400 mt-1">
        <span>0</span>
        <span className="text-yellow-500">{warn}{unit}</span>
        <span className="text-red-500">{crit}{unit}</span>
        <span>{max}{unit}</span>
      </div>
    </div>
  );
}

function ServiceBadge({ name, status }: { name: string; status: string }) {
  const map: Record<string, string> = {
    ok: "bg-green-100 text-green-800 border-green-200",
    degraded: "bg-yellow-100 text-yellow-800 border-yellow-200",
    down: "bg-red-100 text-red-800 border-red-200",
    unknown: "bg-gray-100 text-gray-600 border-gray-200",
  };
  return (
    <div className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm font-medium ${map[status] ?? map.unknown}`}>
      <span className={`w-2 h-2 rounded-full ${
        status === "ok" ? "bg-green-500" :
        status === "degraded" ? "bg-yellow-400" :
        status === "down" ? "bg-red-500" : "bg-gray-400"
      }`} />
      <span className="capitalize">{name}</span>
      <span className="uppercase text-xs opacity-70">{status}</span>
    </div>
  );
}

export default function MonitoringSystem() {
  const [resources, setResources] = useState<SystemResources | null>(null);
  const [health, setHealth] = useState<ServiceHealth | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const token = () => localStorage.getItem("access_token") ?? "";
  const authHdr = () => ({ Authorization: `Bearer ${token()}` });

  const fetchResources = useCallback(async () => {
    try {
      const [resR, hlthR] = await Promise.all([
        fetch(`${API}${PREFIX}/monitoring/system/resources`, { headers: authHdr() }),
        fetch(`${API}${PREFIX}/monitoring/health`, { headers: authHdr() }),
      ]);
      if (resR.ok) {
        const data: SystemResources = await resR.json();
        setResources(data);
        setHistory(prev => {
          const point: HistoryPoint = {
            time: new Date().toLocaleTimeString("fr-FR"),
            cpu: data.cpu_percent,
            ram: data.ram_percent,
            disk: data.disk_percent,
          };
          return [...prev.slice(-29), point];
        });
      }
      if (hlthR.ok) setHealth(await hlthR.json());
    } catch (e) {
      console.error("MonitoringSystem fetch error:", e);
    }
  }, []);

  // WebSocket pour mises a jour temps reel
  useEffect(() => {
    const connect = () => {
      const ws = new WebSocket(`${WS_URL}/ws/metrics`);
      wsRef.current = ws;
      ws.onopen = () => setWsConnected(true);
      ws.onclose = () => { setWsConnected(false); setTimeout(connect, 3000); };
      ws.onerror = () => ws.close();
      ws.onmessage = (e) => {
        try {
          const d = JSON.parse(e.data);
          setResources(prev => prev ? { ...prev, ...d } : d);
        } catch {}
      };
    };
    connect();
    return () => wsRef.current?.close();
  }, []);

  // Polling fallback + sante des services
  useEffect(() => {
    fetchResources();
    const id = setInterval(fetchResources, 15_000);
    return () => clearInterval(id);
  }, [fetchResources]);

  const overall = health?.overall ?? "unknown";

  return (
    <div className="p-6 space-y-6 bg-gray-50 min-h-screen">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Monitoring Systeme</h1>
          <p className="text-sm text-gray-500">Ressources materiel et etat des services</p>
        </div>
        <div className="flex items-center gap-3">
          <span className={`px-3 py-1.5 rounded-full text-sm font-semibold border ${
            overall === "ok" ? "bg-green-100 text-green-800 border-green-200" :
            overall === "degraded" ? "bg-yellow-100 text-yellow-800 border-yellow-200" :
            "bg-red-100 text-red-800 border-red-200"
          }`}>
            Systeme : {overall.toUpperCase()}
          </span>
          <span className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs border ${
            wsConnected
              ? "bg-green-50 text-green-700 border-green-200"
              : "bg-gray-100 text-gray-500 border-gray-200"
          }`}>
            <span className={`w-2 h-2 rounded-full ${
              wsConnected ? "bg-green-500 animate-pulse" : "bg-gray-400"
            }`} />
            {wsConnected ? "Temps reel" : "Polling 15s"}
          </span>
        </div>
      </div>

      {/* Jauges CPU / RAM / Disque / GPU */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <GaugeBar label="CPU" value={resources?.cpu_percent ?? null} warn={75} crit={85} />
        <GaugeBar label="RAM" value={resources?.ram_percent ?? null} warn={70} crit={80}
          unit={`% (${resources?.ram_used_gb?.toFixed(1) ?? "?"}/${resources?.ram_total_gb?.toFixed(0) ?? "?"}Go)`} />
        <GaugeBar label="Disque"
          value={resources?.disk_percent ?? null} warn={70} crit={85}
          unit={`% (${resources?.disk_used_gb?.toFixed(0) ?? "?"}/${resources?.disk_total_gb?.toFixed(0) ?? "?"}Go)`} />
        <GaugeBar
          label={resources?.gpu_percent != null ? "GPU VRAM" : "GPU"}
          value={resources?.gpu_percent ?? null}
          warn={80} crit={90}
          unit={resources?.gpu_vram_used_mb != null
            ? `% (${(resources.gpu_vram_used_mb / 1024).toFixed(1)}/${(resources.gpu_vram_total_mb! / 1024).toFixed(0)}Go)`
            : " (N/A)"}
        />
      </div>

      {/* Reseau */}
      {resources && (
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Reseau envoye</p>
            <p className="text-2xl font-bold text-blue-700">{resources.net_sent_mb.toFixed(0)} Mo</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Reseau recu</p>
            <p className="text-2xl font-bold text-indigo-700">{resources.net_recv_mb.toFixed(0)} Mo</p>
          </div>
        </div>
      )}

      {/* Graphe historique */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
        <h2 className="font-semibold text-gray-800 mb-4">Historique CPU / RAM / Disque (30 derniers points)</h2>
        {history.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-8">En attente de donnees...</p>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={history} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="time" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
              <YAxis domain={[0, 100]} tickFormatter={v => v + "%"} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v: number) => v.toFixed(1) + "%"} />
              <Legend />
              <Line type="monotone" dataKey="cpu"  stroke="#3b82f6" strokeWidth={2} dot={false} name="CPU" />
              <Line type="monotone" dataKey="ram"  stroke="#f97316" strokeWidth={2} dot={false} name="RAM" />
              <Line type="monotone" dataKey="disk" stroke="#8b5cf6" strokeWidth={2} dot={false} name="Disque" />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Etat des services */}
      {health && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <h2 className="font-semibold text-gray-800 mb-4">Etat des services</h2>
          <div className="flex flex-wrap gap-3">
            {Object.entries(health.services).map(([name, status]) => (
              <ServiceBadge key={name} name={name} status={status} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
