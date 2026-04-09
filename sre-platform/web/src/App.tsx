import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { clearToken, isAuthenticated } from "./auth";
import LoginPage from "./pages/LoginPage";
import ReportPage from "./pages/ReportPage";

// ─── Icons ────────────────────────────────────────────────────────────────────

function IconReport() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="2" y="1" width="12" height="14" rx="1.5" />
      <path d="M5 5h6M5 8h6M5 11h4" strokeLinecap="round" />
    </svg>
  );
}

function IconSettings() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="8" cy="8" r="2.5" />
      <path d="M8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M3.05 3.05l1.06 1.06M11.89 11.89l1.06 1.06M3.05 12.95l1.06-1.06M11.89 4.11l1.06-1.06" strokeLinecap="round" />
    </svg>
  );
}

function IconChevronRight() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ width: 12, height: 12 }}>
      <path d="M6 4l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IconLogout() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M6 2H3a1 1 0 00-1 1v10a1 1 0 001 1h3M10 11l3-3-3-3M13 8H6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// ─── Shell ────────────────────────────────────────────────────────────────────

function AppShell({ children, title }: { children: React.ReactNode; title: string }) {
  const navigate = useNavigate();

  function _logout() {
    clearToken();
    navigate("/login");
  }

  return (
    <div className="app-shell">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-logo-icon">S</div>
          <span className="sidebar-brand">SRE Platform</span>
        </div>

        <nav className="sidebar-nav">
          <a href="/report" className="sidebar-nav-item active">
            <IconReport />
            Incidents
          </a>
          <a href="#" className="sidebar-nav-item">
            <IconSettings />
            Settings
          </a>
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-user">
            <div className="sidebar-avatar">U</div>
            <div className="sidebar-user-info">
              <div className="sidebar-user-name">SRE User</div>
              <div className="sidebar-user-role">Engineer</div>
            </div>
            <button
              onClick={_logout}
              title="Sign out"
              style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", display: "flex", padding: "2px" }}
            >
              <IconLogout />
            </button>
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="main-content">
        <div className="topbar">
          <div className="topbar-breadcrumb">
            <span>SRE Platform</span>
            <IconChevronRight />
            <span className="topbar-breadcrumb-current">{title}</span>
          </div>
        </div>
        <div className="page-content">
          {children}
        </div>
      </div>
    </div>
  );
}

function PrivateRoute({ children, title }: { children: React.ReactNode; title: string }) {
  // useLocation forces a re-render on every navigation so the expiry
  // check runs each time the user moves between routes.
  useLocation();

  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return <AppShell title={title}>{children}</AppShell>;
}

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/report"
        element={
          <PrivateRoute title="Incidents">
            <ReportPage />
          </PrivateRoute>
        }
      />
      <Route path="*" element={<Navigate to={isAuthenticated() ? "/report" : "/login"} replace />} />
    </Routes>
  );
}
