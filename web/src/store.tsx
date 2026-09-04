import { PlatformClient, type Me } from '@platform/core';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

interface AppState {
  client: PlatformClient;
  me: Me | null;
  refreshMe: () => Promise<void>;
  setToken: (token: string | null) => void;
  hasToken: boolean;
}

const Ctx = createContext<AppState | null>(null);

export function AppProvider({ children, client: injected }: { children: ReactNode; client?: PlatformClient }) {
  const [token, setTokenState] = useState<string | null>(() => localStorage.getItem('token'));
  const [me, setMe] = useState<Me | null>(null);

  const client = useMemo(
    () =>
      injected ??
      new PlatformClient({
        baseUrl: '', // 同源，经 vite 代理 / 生产反代
        getToken: () => localStorage.getItem('token'),
      }),
    [injected],
  );

  const setToken = useCallback((t: string | null) => {
    if (t) localStorage.setItem('token', t);
    else localStorage.removeItem('token');
    setTokenState(t);
  }, []);

  const refreshMe = useCallback(async () => {
    if (!localStorage.getItem('token')) {
      setMe(null);
      return;
    }
    try {
      setMe(await client.me());
    } catch {
      setToken(null);
      setMe(null);
    }
  }, [client, setToken]);

  useEffect(() => {
    void refreshMe();
  }, [token, refreshMe]);

  return (
    <Ctx.Provider value={{ client, me, refreshMe, setToken, hasToken: !!token }}>{children}</Ctx.Provider>
  );
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error('useApp 必须在 AppProvider 内使用');
  return v;
}
