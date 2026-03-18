import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";

export default function SignInPage() {
  const { signInWithEmail, signInWithGoogle, sendPasswordResetLink } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(((location.state as { notice?: string } | null)?.notice || ""));
  const [resetMode, setResetMode] = useState(false);
  const [loading, setLoading] = useState(false);
  const redirectTo = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname || "/app/screening";

  useEffect(() => {
    function restoreInteractiveState() {
      setLoading(false);
    }

    window.addEventListener("pageshow", restoreInteractiveState);
    window.addEventListener("focus", restoreInteractiveState);
    return () => {
      window.removeEventListener("pageshow", restoreInteractiveState);
      window.removeEventListener("focus", restoreInteractiveState);
    };
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setNotice("");
    setLoading(true);
    try {
      if (resetMode) {
        await sendPasswordResetLink(email);
        setNotice("Password reset email sent. Use the link in your inbox to set a new password.");
        setResetMode(false);
      } else {
        await signInWithEmail(email, password);
        navigate(redirectTo, { replace: true });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleGoogle() {
    setError("");
    setNotice("");
    setLoading(true);
    try {
      await signInWithGoogle();
      navigate("/app/screening", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Google sign in failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="authShell">
      <div className="authCard">
        <div className="authHeader">
          <div className="brandTitle">AI Resume Screening</div>
          <div className="brandSub">
            {resetMode
              ? "Enter your email and we will send a password reset link."
              : "Sign in to access screening, ATS, reports, and training."}
          </div>
        </div>

        <form className="authForm" onSubmit={handleSubmit}>
          <div className="field">
            <label>Email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>

          {!resetMode ? (
            <div className="field">
              <label>Password</label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </div>
          ) : null}

          {notice ? <div className="statusBanner success">{notice}</div> : null}
          {error ? <div className="statusBanner error">{error}</div> : null}

          <button className="primaryBtn" type="submit" disabled={loading}>
            {loading ? "Working..." : resetMode ? "Send Reset Link" : "Sign In"}
          </button>
        </form>

        {!resetMode ? (
          <button className="secondaryBtn" type="button" onClick={handleGoogle} disabled={loading}>
            Continue with Google
          </button>
        ) : null}

        <button className="linkBtn" type="button" onClick={() => { setResetMode((prev) => !prev); setError(""); setNotice(""); }}>
          {resetMode ? "Back to Sign In" : "Forgot password?"}
        </button>

        <div className="authFooter">
          No account yet? <Link to="/signup">Create one</Link>
        </div>
      </div>
    </div>
  );
}
