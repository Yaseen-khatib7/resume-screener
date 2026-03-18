import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./useAuth";

export function ProtectedRoute() {
  const { firebaseUser, loading, blockedMessage } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div className="authShell"><div className="authCard"><div className="hint">Loading account...</div></div></div>;
  }

  if (blockedMessage) {
    return <Navigate to="/suspended" replace />;
  }

  if (!firebaseUser) {
    return <Navigate to="/signin" state={{ from: location }} replace />;
  }

  return <Outlet />;
}

export function AdminRoute() {
  const { profile, loading, blockedMessage } = useAuth();

  if (loading) {
    return <div className="authShell"><div className="authCard"><div className="hint">Loading account...</div></div></div>;
  }

  if (blockedMessage) {
    return <Navigate to="/suspended" replace />;
  }

  if (profile?.role !== "admin") {
    return <Navigate to="/app/screening" replace />;
  }

  return <Outlet />;
}
