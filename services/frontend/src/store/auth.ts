/**
 * Store auth — JWT stocké en mémoire uniquement (jamais localStorage).
 * Conforme AGENT_FRONTEND.md §6 Sécurité Frontend.
 */
import { create } from "zustand";
import axios from "axios";

interface AuthState {
  token: string | null;
  role: string | null;
  email: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: null,
  role: null,
  email: null,

  login: async (email, password) => {
    const form = new URLSearchParams();
    form.append("username", email);
    form.append("password", password);

    const { data } = await axios.post("/api/v1/auth/login", form, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });

    // Stocker le token dans le store (mémoire uniquement)
    axios.defaults.headers.common["Authorization"] = `Bearer ${data.access_token}`;
    set({ token: data.access_token, email });

    // Récupérer le rôle
    const me = await axios.get("/api/v1/auth/me");
    set({ role: me.data.role });
  },

  logout: () => {
    delete axios.defaults.headers.common["Authorization"];
    set({ token: null, role: null, email: null });
  },
}));
