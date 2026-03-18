import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";

export default function SignUpPage() {
  const { signUpWithEmail, signInWithGoogle } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setError("");
    setSuccess("");
    setLoading(true);
    try {
      await signUpWithEmail(name, email, password);
      navigate("/signin", {
        replace: true,
        state: { notice: "Verification email sent. Please verify your email before signing in." },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign up failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleGoogle() {
    setError("");
    setSuccess("");
    setLoading(true);
    try {
      await signInWithGoogle();
      navigate("/app/screening", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Google sign up failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="authShell">
      <div className="authCard">
        <div className="authHeader">
          <div className="brandTitle">Create Account</div>
          <div className="brandSub">New signups are created as HR users by default.</div>
        </div>

        <form className="authForm" onSubmit={handleSubmit}>
          <div className="field">
            <label>Full name</label>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>

          <div className="field">
            <label>Email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>

          <div className="field">
            <label>Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={6} />
          </div>

          <div className="field">
            <label>Confirm password</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              minLength={6}
            />
          </div>

          {success ? <div className="statusBanner success">{success}</div> : null}
          {error ? <div className="statusBanner error">{error}</div> : null}

          <button className="primaryBtn" type="submit" disabled={loading}>
            {loading ? "Creating account..." : "Sign Up"}
          </button>
        </form>

        <button className="secondaryBtn" type="button" onClick={handleGoogle} disabled={loading}>
          Continue with Google
        </button>

        <div className="authFooter">
          Already have an account? <Link to="/signin">Sign in</Link>
        </div>
      </div>
    </div>
  );
}
