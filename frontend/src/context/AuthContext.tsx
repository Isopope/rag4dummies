import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';
import { login as apiLogin, getMe, type UserInfo } from '@/lib/api';
import { getToken, setToken, clearToken } from '@/lib/auth';
import { clearPrivateQueryData } from '@/lib/query-client';

interface AuthContextValue {
  token: string | null;
  user: UserInfo | null;
  isAuthenticated: boolean;
  isAdmin: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(getToken);
  const [user, setUser] = useState<UserInfo | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(() => !!getToken());

  // Restaurer le profil utilisateur depuis le token stocké au démarrage
  useEffect(() => {
    if (!token) { setUser(null); setIsLoading(false); return; }
    setIsLoading(true);
    getMe(token)
      .then(setUser)
      .catch(() => {
        // Token expiré ou invalide → déconnecter silencieusement
        clearToken();
        clearPrivateQueryData();
        setTokenState(null);
        setUser(null);
      })
      .finally(() => setIsLoading(false));
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
    clearPrivateQueryData();
    setTokenState(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{
      token,
      user,
      isAuthenticated: !!token && !!user,
      isAdmin: user?.role === 'admin',
      isLoading,
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
