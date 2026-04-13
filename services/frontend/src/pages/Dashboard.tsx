import { useEffect, useRef, useState } from "react";

interface FaceDetection {
  camera_id: string;
  faces: Array<{
    bbox: number[];
    status: "authorized" | "suspect" | "unknown";
    confidence: number;
    profile_id: string | null;
  }>;
  timestamp: number;
}

interface SystemMetrics {
  cpu_percent: number;
  ram_percent: number;
  disk_percent: number;
}

const STATUS_COLOR = {
  authorized: "#22c55e",
  suspect:    "#f97316",
  unknown:    "#ef4444",
};

function MetricBar({ label, value, warn = 75, critical = 85 }: {
  label: string; value: number; warn?: number; critical?: number;
}) {
  const color = value >= critical ? "bg-red-500" : value >= warn ? "bg-orange-400" : "bg-green-500";
  return (
    <div>
      <div className="flex justify-between text-xs text-gray-400 mb-1">
        <span>{label}</span>
        <span>{value.toFixed(1)}%</span>
      </div>
      <div className="h-2 bg-gray-700 rounded">
        <div className={`h-2 rounded transition-all ${color}`} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [metrics, setMetrics] = useState<SystemMetrics>({ cpu_percent: 0, ram_percent: 0, disk_percent: 0 });
  const [detections, setDetections] = useState<Record<string, FaceDetection>>({});
  const [alertCount, setAlertCount] = useState({ authorized: 0, suspect: 0, unknown: 0 });
  const wsMetrics = useRef<WebSocket | null>(null);
  const wsAlerts = useRef<WebSocket | null>(null);

  useEffect(() => {
    // WebSocket métriques système
    const connectMetrics = () => {
      wsMetrics.current = new WebSocket(`ws://${location.host}/ws/metrics`);
      wsMetrics.current.onmessage = (e) => setMetrics(JSON.parse(e.data));
      wsMetrics.current.onclose = () => setTimeout(connectMetrics, 3000);
    };
    connectMetrics();

    // WebSocket alertes/détections
    const connectAlerts = () => {
      wsAlerts.current = new WebSocket(`ws://${location.host}/ws/alerts`);
      wsAlerts.current.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.faces) {
          setDetections(prev => ({ ...prev, [data.camera_id]: data }));
          data.faces.forEach((f: any) => {
            setAlertCount(prev => ({ ...prev, [f.status]: prev[f.status as keyof typeof prev] + 1 }));
          });
        }
      };
      wsAlerts.current.onclose = () => setTimeout(connectAlerts, 3000);
    };
    connectAlerts();

    return () => {
      wsMetrics.current?.close();
      wsAlerts.current?.close();
    };
  }, []);

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-lg font-bold text-white">Dashboard — Surveillance temps réel</h2>

      {/* Compteurs */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Autorisés", count: alertCount.authorized, color: "text-green-400 border-green-800" },
          { label: "Suspects",  count: alertCount.suspect,    color: "text-orange-400 border-orange-800" },
          { label: "Intrus",    count: alertCount.unknown,    color: "text-red-400 border-red-800" },
        ].map(({ label, count, color }) => (
          <div key={label} className={`bg-gray-800 border rounded-lg p-4 ${color}`}>
            <div className="text-3xl font-bold">{count}</div>
            <div className="text-sm mt-1">{label} (session)</div>
          </div>
        ))}
      </div>

      {/* Flux caméras annotés */}
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Flux caméras</h3>
        {Object.keys(detections).length === 0 ? (
          <p className="text-gray-500 text-sm">En attente de détections...</p>
        ) : (
          <div className="grid grid-cols-2 gap-4">
            {Object.values(detections).map((det) => (
              <div key={det.camera_id} className="bg-gray-900 rounded p-3">
                <div className="flex justify-between text-xs text-gray-400 mb-2">
                  <span>{det.camera_id}</span>
                  <span className="text-green-400">● LIVE</span>
                </div>
                {det.faces.map((face, i) => (
                  <div
                    key={i}
                    className="text-xs p-2 rounded mb-1"
                    style={{ borderLeft: `3px solid ${STATUS_COLOR[face.status]}` }}
                  >
                    <span style={{ color: STATUS_COLOR[face.status] }}>
                      {face.status === "authorized" ? face.profile_id : face.status.toUpperCase()}
                    </span>
                    <span className="text-gray-400 ml-2">{face.confidence}%</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Santé système */}
      <div className="bg-gray-800 rounded-lg p-4 space-y-3">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Santé système</h3>
        <MetricBar label="CPU"   value={metrics.cpu_percent} />
        <MetricBar label="RAM"   value={metrics.ram_percent} />
        <MetricBar label="Disque" value={metrics.disk_percent} warn={70} critical={85} />
      </div>
    </div>
  );
}
