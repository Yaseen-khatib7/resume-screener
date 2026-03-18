export type UserRole = "admin" | "hr";
export type UserStatus = "active" | "suspended";

export type UserProfile = {
  uid: string;
  name: string;
  email: string;
  role: UserRole;
  status: UserStatus;
  suspended: boolean;
  createdAt?: string | null;
};

export type AuthContextValue = {
  firebaseUser: import("firebase/auth").User | null;
  profile: UserProfile | null;
  loading: boolean;
  blockedMessage: string | null;
  signInWithEmail: (email: string, password: string) => Promise<void>;
  signUpWithEmail: (name: string, email: string, password: string) => Promise<void>;
  signInWithGoogle: () => Promise<void>;
  sendPasswordResetLink: (email: string) => Promise<void>;
  logout: () => Promise<void>;
  clearBlockedMessage: () => void;
  refreshProfile: () => Promise<UserProfile | null>;
};

export type AdminUserCreatePayload = {
  name: string;
  email: string;
  password: string;
  role: UserRole;
};

export type AdminUserUpdatePayload = {
  role?: UserRole;
  status?: UserStatus;
};

export type EmailTemplates = {
  acceptanceSubject: string;
  acceptanceBody: string;
  processingSubject: string;
  processingBody: string;
  rejectionSubject: string;
  rejectionBody: string;
};
