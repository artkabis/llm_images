import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/auth";

const NAV = [
  { to: "/",               label: "Dashboard",      roles: ["viewer","operator","admin"] },
  { to: "/alerts",         label: "Alertes",         roles: ["operator","admin"] },
  { to: "/profiles",       label: "Profils",         roles: ["admin"] },
  { to: "/review",         label: "Review IA",       roles: ["operator","admin"] },
  { to: "/monitoring/ml",  label: "Monitoring ML",   roles: ["admin"] },
  { to: "/monitoring/system", label: "Système",      roles: ["admin"] },
];

export default function Layout() {
  const { role, email, logout } = useAuthStore();
  const navigate = useNavigate();

  const handleLogout = () => { logout(); navigate("/login"); };

  return (
    <div className="flex h-screen bg-gray-900 text-gray-100 font-mono">
      {/* Sidebar */}
      <aside className="w-56 bg-gray-950 border-r border-gray-800 flex flex-col">
        <div className="p-4 border-b border-gray-800">
          <h1 className="text-sm font-bold text-blue-400 uppercase tracking-widest">FaceRec</h1>
          <p className="text-xs text-gray-500 mt-1">Surveillance IA</p>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {NAV.filter(item => role && item.roles.includes(role)).map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `block px-3 py-2 rounded text-sm transition-colors ${
                  isActive
                    ? "bg-blue-600 text-white"
                    : "text-gray-400 hover:bg-gray-800 hover:text-white"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="p-3 border-t border-gray-800">
          <p className="text-xs text-gray-500 truncate">{email}</p>
          <span className="inline-block text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded mt-1">{role}</span>
          <button
            onClick={handleLogout}
            className="mt-2 w-full text-xs text-red-400 hover:text-red-300 text-left"
          >
            Déconnexion
          </button>
        </div>
      </aside>

      {/* Contenu principal */}
      <main className="flex-1 overflow-auto bg-gray-900">
        <Outlet />
      </main>
    </div>
  );
}
