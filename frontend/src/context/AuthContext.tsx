import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';
import { login as apiLogin, getMe, type UserInfo } from '@/lib/api';
import { getToken, setToken, clearToken } from '@/lib/auth';

interface AuthContextValue {
  token: string | null;
  user: UserInfo | null;
  isAuthenticated: boolean;
  isAdmin: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(getToken);
  const [user, setUser] = useState<UserInfo | null>(null);

  // Restaurer le profil utilisateur depuis le token stocké au démarrage
  useEffect(() => {
    if (!token) { setUser(null); return; }
    getMe(token)
      .then(setUser)
      .catch(() => {
        // Token expiré ou invalide → déconnecter silencieusement
        clearToken();
        setTokenState(null);
        setUser(null);
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const login = useCallback(async (email: string, password: string) => {
    const res = await apiLogin(email, password);
    setToken(res.access_token);
    setTokenState(res.access_token);
    const me = await getMe(res.access_token);
    setUser(me);
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setTokenState(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{
      token,
      user,
      isAuthenticated: !!token && !!user,
      isAdmin: user?.role === 'admin',
      login,
      logout,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
