
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import {
  clearAccessToken,
  getAccessToken,
  setAccessToken,
  SESSION_EXPIRED_EVENT,
} from "../services/apiClient";

import {
  getCurrentUser,
  loginUser,
  registerUser,
} from "../services/api";

import type { UserResponse } from "../types/auth";

interface AuthContextValue {
  user: UserResponse | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    const restoreSession = async () => {
      const token = getAccessToken();

      if (!token) {
        if (active) setLoading(false);
        return;
      }

      try {
        const currentUser = await getCurrentUser();
        if (active) setUser(currentUser);
      } catch {
        clearAccessToken();
        if (active) setUser(null);
      } finally {
        if (active) setLoading(false);
      }
    };

    void restoreSession();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const handleSessionExpired = () => {
      clearAccessToken();
      setUser(null);
    };

    window.addEventListener(
      SESSION_EXPIRED_EVENT,
      handleSessionExpired,
    );

    return () => {
      window.removeEventListener(
        SESSION_EXPIRED_EVENT,
        handleSessionExpired,
      );
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const result = await loginUser({ email, password });

    setAccessToken(result.access_token);

    try {
      const currentUser = await getCurrentUser();
      setUser(currentUser);
    } catch (error) {
      clearAccessToken();
      setUser(null);
      throw error;
    }
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    await registerUser({ email, password });
    await login(email, password);
  }, [login]);

  const logout = useCallback(() => {
    clearAccessToken();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider.");
  }

  return context;
}
