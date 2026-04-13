import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";

export default function Profiles() {
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", role: "" });
  const [photos, setPhotos] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["profiles"],
    queryFn: () => axios.get("/api/v1/profiles/").then((r) => r.data),
    refetchInterval: 30000,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => axios.delete(`/api/v1/profiles/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) setPhotos(Array.from(e.target.files));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (photos.length < 1) { setError("Minimum 1 photo requise"); return; }
    setUploading(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("name", form.name);
      if (form.role) fd.append("role", form.role);
      photos.forEach((p) => fd.append("photos", p));
      await axios.post("/api/v1/profiles/", fd);
      qc.invalidateQueries({ queryKey: ["profiles"] });
      setShowForm(false);
      setForm({ name: "", role: "" });
      setPhotos([]);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Erreur lors de l'enrôlement");
    } finally {
      setUploading(false);
    }
  };

  const profiles = data?.items || [];

  return (
    <div className="p-6 space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-bold text-white">Profils autorisés</h2>
        <button onClick={() => setShowForm(true)}
          className="text-xs bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded font-semibold">
          + Nouveau profil
        </button>
      </div>

      {/* Grille profils */}
      {isLoading ? <p className="text-gray-500 text-sm">Chargement...</p> : (
        <div className="grid grid-cols-3 gap-4">
          {profiles.map((p: any) => (
            <div key={p.id} className="bg-gray-800 border border-gray-700 rounded-lg p-4">
              <div className="flex justify-between items-start">
                <div>
                  <p className="text-sm font-semibold text-white">{p.name}</p>
                  {p.role && <p className="text-xs text-gray-400 mt-0.5">{p.role}</p>}
                </div>
                <span className={`text-xs px-2 py-0.5 rounded ${p.active ? "bg-green-900 text-green-400" : "bg-gray-700 text-gray-500"}`}>
                  {p.active ? "Actif" : "Inactif"}
                </span>
              </div>
              <p className="text-xs text-gray-500 mt-2">{p.n_images} photo{p.n_images > 1 ? "s" : ""}</p>
              <p className="text-xs text-gray-600 mt-1 font-mono">{p.id.slice(0, 8)}…</p>
              <button
                onClick={() => { if (confirm(`Supprimer ${p.name} ?`)) deleteMutation.mutate(p.id); }}
                className="mt-3 text-xs text-red-400 hover:text-red-300">
                Supprimer
              </button>
            </div>
          ))}
          {profiles.length === 0 && (
            <p className="col-span-3 text-gray-500 text-sm">Aucun profil enrôlé.</p>
          )}
        </div>
      )}

      {/* Modal création */}
      {showForm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 w-[480px]">
            <h3 className="text-sm font-bold text-white mb-4">Enrôler un nouveau profil</h3>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="text-xs text-gray-400 block mb-1">Nom *</label>
                <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                  required className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500" />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Rôle</label>
                <input value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}
                  placeholder="ex: Employé, Manager, Visiteur..."
                  className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500" />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">
                  Photos * ({photos.length} sélectionnée{photos.length > 1 ? "s" : ""}) — minimum 5 recommandées, angles variés
                </label>
                <div onClick={() => fileRef.current?.click()}
                  className="border-2 border-dashed border-gray-600 rounded p-4 text-center cursor-pointer hover:border-blue-500 transition-colors">
                  <p className="text-xs text-gray-400">Cliquer pour sélectionner des photos</p>
                  {photos.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2 justify-center">
                      {photos.map((f, i) => (
                        <span key={i} className="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded">{f.name}</span>
                      ))}
                    </div>
                  )}
                </div>
                <input ref={fileRef} type="file" multiple accept="image/*" onChange={handleFileChange} className="hidden" />
              </div>
              {error && <p className="text-red-400 text-xs">{error}</p>}
              <div className="flex gap-2">
                <button type="submit" disabled={uploading}
                  className="flex-1 bg-blue-600 hover:bg-blue-700 text-white text-sm py-2 rounded disabled:opacity-40">
                  {uploading ? "Enrôlement en cours..." : "Enrôler"}
                </button>
                <button type="button" onClick={() => setShowForm(false)}
                  className="flex-1 bg-gray-700 text-white text-sm py-2 rounded">
                  Annuler
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
