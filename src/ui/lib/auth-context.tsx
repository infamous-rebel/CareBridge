"use client";

import React, {
  createContext,
  useContext,
  useCallback,
  useState,
  useEffect,
  useRef,
  type ReactNode,
} from "react";
import { api, type TokenResponse, type UserOut } from "@/lib/api";
import {
  signInWithGoogle as fbSignInWithGoogle,
  signInWithEmail as fbSignInWithEmail,
  signUpWithEmail as fbSignUpWithEmail,
  getIdToken,
  onAuthStateChanged,
  signOutFirebase,
} from "@/lib/firebase";

interface AuthContextType {
  user: UserOut | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  loginWithGoogle: () => Promise<void>;
  loginWithFirebaseEmail: (email: string, password: string) => Promise<void>;
  signupWithFirebase: (
    email: string,
    password: string,
    fullName: string
  ) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const TOKEN_KEY = "cb_access_token";
const REFRESH_KEY = "cb_refresh_token";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [loading, setLoading] = useState(true);
  const exchangedRef = useRef(false);

  const loadUser = useCallback(async () => {
    const token = sessionStorage.getItem(TOKEN_KEY);
    if (!token) {
      setLoading(false);
      return;
    }
    api.setAccessToken(token);
    try {
      const u = await api.getMe();
      setUser(u);
    } catch {
      sessionStorage.removeItem(TOKEN_KEY);
      sessionStorage.removeItem(REFRESH_KEY);
      api.clearTokens();
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  // On page refresh, if Firebase has a user, silently re-exchange tokens.
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(async (fbUser) => {
      if (fbUser && !exchangedRef.current && !sessionStorage.getItem(TOKEN_KEY)) {
        exchangedRef.current = true;
        try {
          const idToken = await getIdToken();
          if (idToken) {
            const result = await api.exchangeFirebaseToken(idToken);
            api.setAccessToken(result.access_token);
            sessionStorage.setItem(TOKEN_KEY, result.access_token);
            sessionStorage.setItem(REFRESH_KEY, result.refresh_token);
            setUser(result.user);
          }
        } catch {
          // Silent failure — user will need to log in manually.
        }
      }
    });
    return unsubscribe;
  }, []);

  /** Helper: exchange a Firebase ID token for CareBridge JWTs. */
  const exchangeAndSetUser = useCallback(async () => {
    const idToken = await getIdToken();
    if (!idToken) throw new Error("No Firebase user signed in");
    const result = await api.exchangeFirebaseToken(idToken);
    api.setAccessToken(result.access_token);
    sessionStorage.setItem(TOKEN_KEY, result.access_token);
    sessionStorage.setItem(REFRESH_KEY, result.refresh_token);
    setUser(result.user);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const result: TokenResponse = await api.login(email, password);
    api.setAccessToken(result.access_token);
    sessionStorage.setItem(TOKEN_KEY, result.access_token);
    const u = await api.getMe();
    setUser(u);
  }, []);

  const loginWithGoogle = useCallback(async () => {
    await fbSignInWithGoogle();
    await exchangeAndSetUser();
  }, [exchangeAndSetUser]);

  const loginWithFirebaseEmail = useCallback(
    async (email: string, password: string) => {
      await fbSignInWithEmail(email, password);
      await exchangeAndSetUser();
    },
    [exchangeAndSetUser]
  );

  const signupWithFirebase = useCallback(
    async (email: string, password: string, fullName: string) => {
      await fbSignUpWithEmail(email, password, fullName);
      await exchangeAndSetUser();
    },
    [exchangeAndSetUser]
  );

  const logout = useCallback(async () => {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(REFRESH_KEY);
    api.clearTokens();
    setUser(null);
    try {
      await signOutFirebase();
    } catch {
      // Firebase sign-out failure is non-fatal.
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        logout,
        loginWithGoogle,
        loginWithFirebaseEmail,
        signupWithFirebase,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
