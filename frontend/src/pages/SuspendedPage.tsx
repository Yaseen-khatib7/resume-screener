import { Link } from "react-router-dom";
import { useAuth } from "../auth/useAuth";

export default function SuspendedPage() {
  const { blockedMessage, clearBlockedMessage } = useAuth();
  const message = blockedMessage || "Your account has been suspended. Contact admin.";

  return (
    <div className="authShell">
      <div className="authCard">
        <div className="authHeader">
          <div className="brandTitle">Account Suspended</div>
          <div className="brandSub">{message}</div>
        </div>

        <div className="statusBanner error">{message}</div>

        <Link className="secondaryBtn" to="/signin" onClick={clearBlockedMessage}>
          Back to Sign In
        </Link>
      </div>
    </div>
  );
}
