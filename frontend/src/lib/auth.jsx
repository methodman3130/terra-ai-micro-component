import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, setToken, getToken } from "./api";

/**
 * Session handling.
 *
 * The token is kept in localStorage so a refresh does not sign the user out.
 * That is a deliberate trade-off: it survives reload but is readable by any
 * script on the origin. It is acceptable here because the app is read-only,
 * institutionally hosted and runs no third-party scripts. If this ever serves
 * wider traffic, move to an httpOnly cookie with CSRF protection.
 *
 * Sign-out calls the server so the token is revoked, not merely forgotten.
 */

const AuthContext = createContext(null);
const STORAGE_KEY = "terra.session";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let saved = null;
    try {
      saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
    } catch {
      saved = null;
    }
    if (!saved?.token) {
      setReady(true);
      return;
    }
    setToken(saved.token);
    // Never trust the stored copy of the user: ask the server who this token is
    // now. A role changed or an account disabled must take effect immediately.
    api
      .me()
      .then(setUser)
      .catch(() => {
        setToken(null);
        try {
          localStorage.removeItem(STORAGE_KEY);
        } catch {
          /* private mode */
        }
      })
      .finally(() => setReady(true));
  }, []);

  const signIn = useCallback(async (email, password) => {
    const res = await api.login(email, password);
    setToken(res.access_token);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ token: res.access_token }));
    } catch {
      /* private mode: session lasts this tab only */
    }
    const me = await api.me();
    setUser(me);
    return me;
  }, []);

  const signOut = useCallback(async () => {
    try {
      if (getToken()) await api.logout();
    } catch {
      /* already expired or revoked; clear locally regardless */
    }
    setToken(null);
    setUser(null);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* private mode */
    }
  }, []);

  const value = useMemo(
    () => ({ user, ready, signIn, signOut, isAdmin: user?.role === "admin" }),
    [user, ready, signIn, signOut]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
