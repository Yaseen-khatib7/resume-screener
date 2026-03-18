import {
  createUserWithEmailAndPassword,
  getRedirectResult,
  onAuthStateChanged,
  sendEmailVerification,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
  signInWithPopup,
  signInWithRedirect,
  signOut,
  updateProfile,
  type User,
} from "firebase/auth";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { AuthContext } from "./auth-context";
import { auth, firebaseConfigError, firebaseReady, googleProvider } from "../firebase";
import type { AuthContextValue, UserProfile } from "../types/auth";

const AUTH_BOOT_TIMEOUT_MS = 8000;

function actionCodeSettings() {
  return {
    url: `${window.location.origin}/signin`,
    handleCodeInApp: false,
  };
}

function mapFirebaseError(error: unknown): string {
  const code = typeof error === "object" && error && "code" in error ? String(error.code) : "";

  switch (code) {
    case "auth/email-already-in-use":
      return "This email is already in use.";
    case "auth/invalid-credential":
    case "auth/wrong-password":
    case "auth/user-not-found":
      return "Invalid email or password.";
    case "auth/popup-closed-by-user":
      return "Google sign-in was cancelled.";
    case "auth/popup-blocked":
      return "Popup sign-in was blocked by the browser.";
    case "auth/cancelled-popup-request":
      return "Another Google sign-in request is already in progress.";
    case "auth/unauthorized-domain":
      return "This domain is not authorized for Google sign-in in Firebase.";
    case "auth/operation-not-supported-in-this-environment":
      return "Google popup sign-in is not supported in this environment.";
    case "auth/too-many-requests":
      return "Too many attempts. Try again later.";
    case "auth/user-disabled":
      return "Your account has been suspended. Contact admin.";
    default:
      return error instanceof Error ? error.message : "Authentication failed.";
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [firebaseUser, setFirebaseUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [blockedMessage, setBlockedMessage] = useState<string | null>(null);

  const refreshProfile = useCallback(async () => {
    if (!auth?.currentUser) {
      setProfile(null);
      return null;
    }

    const res = await api.get("/auth/me", { timeout: AUTH_BOOT_TIMEOUT_MS });
    const nextProfile = (res.data?.profile || null) as UserProfile | null;

    if (nextProfile?.status === "suspended" || nextProfile?.suspended) {
      await signOut(auth);
      setBlockedMessage("Your account has been suspended. Contact admin.");
      setFirebaseUser(null);
      setProfile(null);
      return null;
    }

    setProfile(nextProfile);
    return nextProfile;
  }, []);

  useEffect(() => {
    if (!firebaseReady || !auth) {
      setLoading(false);
      setBlockedMessage(firebaseConfigError || "Firebase is not configured.");
      return;
    }

    getRedirectResult(auth).catch((error) => {
      console.error(error);
    });

    const unsub = onAuthStateChanged(auth, async (user) => {
      setLoading(true);
      setFirebaseUser(user);

      if (!user) {
        setProfile(null);
        setLoading(false);
        return;
      }

      try {
        await refreshProfile();
      } catch (error) {
        console.error(error);
        setBlockedMessage(null);
      } finally {
        setLoading(false);
      }
    });

    return () => unsub();
  }, [refreshProfile]);

  const signInWithEmail = useCallback(async (email: string, password: string) => {
    try {
      if (!auth) throw new Error(firebaseConfigError || "Firebase is not configured.");
      setBlockedMessage(null);
      const cred = await signInWithEmailAndPassword(auth, email, password);
      await cred.user.reload();
      if (!cred.user.emailVerified) {
        await sendEmailVerification(cred.user, actionCodeSettings());
        await signOut(auth);
        throw new Error("Email not verified. A new verification link has been sent to your inbox.");
      }
    } catch (error) {
      throw new Error(mapFirebaseError(error));
    }
  }, []);

  const signUpWithEmail = useCallback(async (name: string, email: string, password: string) => {
    try {
      if (!auth) throw new Error(firebaseConfigError || "Firebase is not configured.");
      setBlockedMessage(null);
      const cred = await createUserWithEmailAndPassword(auth, email, password);
      await updateProfile(cred.user, { displayName: name });
      await sendEmailVerification(cred.user, actionCodeSettings());
      await signOut(auth);
    } catch (error) {
      throw new Error(mapFirebaseError(error));
    }
  }, []);

  const signInWithGoogle = useCallback(async () => {
    try {
      if (!auth) throw new Error(firebaseConfigError || "Firebase is not configured.");
      setBlockedMessage(null);
      await signInWithPopup(auth, googleProvider);
      try {
        await refreshProfile();
      } catch (error) {
        console.error(error);
      }
    } catch (error) {
      const code = typeof error === "object" && error && "code" in error ? String(error.code) : "";
      if (auth && code in {
        "auth/popup-blocked": true,
        "auth/operation-not-supported-in-this-environment": true,
      }) {
        await signInWithRedirect(auth, googleProvider);
        return;
      }
      throw new Error(mapFirebaseError(error));
    }
  }, [refreshProfile]);

  const logout = useCallback(async () => {
    if (!auth) return;
    await signOut(auth);
    setProfile(null);
    setFirebaseUser(null);
  }, []);

  const sendPasswordResetLink = useCallback(async (email: string) => {
    try {
      if (!auth) throw new Error(firebaseConfigError || "Firebase is not configured.");
      await sendPasswordResetEmail(auth, email, actionCodeSettings());
    } catch (error) {
      throw new Error(mapFirebaseError(error));
    }
  }, []);

  const clearBlockedMessage = useCallback(() => {
    setBlockedMessage(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      firebaseUser,
      profile,
      loading,
      blockedMessage,
      signInWithEmail,
      signUpWithEmail,
      signInWithGoogle,
      sendPasswordResetLink,
      logout,
      clearBlockedMessage,
      refreshProfile,
    }),
    [
      blockedMessage,
      clearBlockedMessage,
      firebaseUser,
      loading,
      logout,
      profile,
      refreshProfile,
      sendPasswordResetLink,
      signInWithEmail,
      signInWithGoogle,
      signUpWithEmail,
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
