import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, token, type User } from "./api";

interface AuthState {
  user: User | null;
  ready: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, name: string) => Promise<void>;
  signOut: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  const refresh = useCallback(async () => {
    if (!token.get()) { setUser(null); return; }
    try { setUser(await api.me()); } catch { token.set(null); setUser(null); }
  }, []);

  useEffect(() => { refresh().finally(() => setReady(true)); }, [refresh]);

  const value: AuthState = {
    user, ready, refresh,
    signIn: async (email, password) => { const r = await api.login(email, password); token.set(r.token); setUser(r.user); },
    signUp: async (email, password, name) => { const r = await api.register(email, password, name); token.set(r.token); setUser(r.user); },
    signOut: () => { token.set(null); setUser(null); },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
