import { NavLink, Route, Routes } from "react-router";

import HomePage from "./pages/HomePage";
import ProjectsPage from "./pages/ProjectsPage";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  isActive ? "font-medium text-slate-900" : "text-slate-500 hover:text-slate-900";

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="flex items-center gap-6 border-b border-slate-200 bg-white px-6 py-4">
        <h1 className="text-xl font-semibold">Pulse</h1>
        <nav className="flex gap-4 text-sm">
          <NavLink to="/" end className={linkClass}>
            Home
          </NavLink>
          <NavLink to="/projects" className={linkClass}>
            Projects
          </NavLink>
        </nav>
      </header>
      <main className="mx-auto max-w-3xl px-6 py-8">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/projects" element={<ProjectsPage />} />
        </Routes>
      </main>
    </div>
  );
}
