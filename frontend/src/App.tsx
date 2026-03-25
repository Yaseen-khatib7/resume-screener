import { Suspense, lazy, useMemo, useState } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import "./App.css";
import { useAuth } from "./auth/useAuth";
import { ProtectedRoute } from "./auth/RouteGuards";
import { firebaseConfigError, firebaseReady } from "./firebase";
import type { ScreenResponse } from "./types/screening";

const ScreeningPage = lazy(() => import("./pages/ScreeningPage"));
const SignInPage = lazy(() => import("./pages/SignInPage"));
const SignUpPage = lazy(() => import("./pages/SignUpPage"));
const SuspendedPage = lazy(() => import("./pages/SuspendedPage"));
const TrainingPage = lazy(() => import("./pages/TrainingPage"));
const UserManagementPage = lazy(() => import("./pages/UserManagementPage"));

type AppTab = "screening" | "training" | "users";
const trainingEnabled = import.meta.env.DEV || import.meta.env.VITE_ENABLE_TRAINING === "true";

function AppShell() {
  const { firebaseUser, profile, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  if (!trainingEnabled && location.pathname.startsWith("/app/training")) {
    return <Navigate to="/app/screening/setup" replace />;
  }

  const [jd, setJd] = useState<File | null>(null);
  const [resumes, setResumes] = useState<File[]>([]);
  const [matchStyle, setMatchStyle] = useState<number>(0.5);
  const [cutoff, setCutoff] = useState<number>(48);
  const [modelChoice, setModelChoice] = useState<string>("baseline");
  const [data, setData] = useState<ScreenResponse | null>(null);

  const tab = useMemo<AppTab>(() => {
    if (trainingEnabled && location.pathname.startsWith("/app/training")) return "training";
    if (location.pathname.startsWith("/app/users")) return "users";
    return "screening";
  }, [location.pathname]);

  const displayName = profile?.name || firebaseUser?.displayName || profile?.email || firebaseUser?.email || "Signed in";
  const displayEmail = profile?.email || firebaseUser?.email || "";
  const displayRole = profile?.role || "account";

  async function handleLogout() {
    await logout();
    navigate("/signin", { replace: true });
  }

  return (
    <div className="page">
      <div className="topbar appTopbar">
        <div className="brand">
          <div className="brandTitle">Resume Screening System</div>
          <div className="brandSub">Secure screening, ATS review, explainable ranking, and admin access control.</div>
        </div>

        <div className="topbarRight">
          <div className="tabs">
            <button
              className={tab === "screening" ? "secondaryBtn" : "linkBtn"}
              onClick={() => navigate("/app/screening/setup")}
            >
              Screening
            </button>

            {trainingEnabled ? (
              <button
                className={tab === "training" ? "secondaryBtn" : "linkBtn"}
                onClick={() => navigate("/app/training")}
              >
                Training + NDCG
              </button>
            ) : null}

            {profile?.role === "admin" ? (
              <button
                className={tab === "users" ? "secondaryBtn" : "linkBtn"}
                onClick={() => navigate("/app/users")}
              >
                User Management
              </button>
            ) : null}
          </div>

          <div className="userBadge">
            <div>
              <div className="userBadgeName">{displayName}</div>
              <div className="hint">{displayEmail ? `${displayEmail} | ${displayRole}` : displayRole}</div>
            </div>
            <button className="secondaryBtn" onClick={handleLogout}>Logout</button>
          </div>
        </div>
      </div>

      {tab === "screening" ? (
        <ScreeningPage
          jd={jd}
          setJd={setJd}
          resumes={resumes}
          setResumes={setResumes}
          matchStyle={matchStyle}
          setMatchStyle={setMatchStyle}
          cutoff={cutoff}
          setCutoff={setCutoff}
          modelChoice={modelChoice}
          setModelChoice={setModelChoice}
          data={data}
          setData={setData}
        />
      ) : null}

      {trainingEnabled && tab === "training" ? (
        <TrainingPage
          jd={jd}
          resumes={resumes}
          matchStyle={matchStyle}
          modelChoice={modelChoice}
          data={data}
        />
      ) : null}

      {tab === "users" ? (
        profile?.role === "admin" ? <UserManagementPage /> : <Navigate to="/app/screening" replace />
      ) : null}
    </div>
  );
}

export default function App() {
  if (!firebaseReady) {
    return (
      <div className="authShell">
        <div className="authCard">
          <div className="authHeader">
            <div className="brandTitle">Firebase Configuration Required</div>
            <div className="brandSub">
              The frontend cannot start until the required Firebase environment variables are set.
            </div>
          </div>
          <div className="statusBanner error">{firebaseConfigError}</div>
        </div>
      </div>
    );
  }

  return (
    <Suspense
      fallback={
        <div className="authShell">
          <div className="authCard">
            <div className="hint">Loading application...</div>
          </div>
        </div>
      }
    >
      <Routes>
        <Route path="/" element={<Navigate to="/app/screening" replace />} />
        <Route path="/signin" element={<SignInPage />} />
        <Route path="/signup" element={<SignUpPage />} />
        <Route path="/suspended" element={<SuspendedPage />} />

        <Route path="/app/screening" element={<Navigate to="/app/screening/setup" replace />} />

        <Route element={<ProtectedRoute />}>
          <Route path="/app/*" element={<AppShell />} />
        </Route>

        <Route path="*" element={<Navigate to="/app/screening" replace />} />
      </Routes>
    </Suspense>
  );
}
