import { useQueryClient } from '@tanstack/react-query';
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { setSignedOutHandler } from '../api/client';
import { getTokens, setTokens } from '../api/tokens';
import type { TokenPair } from '../api/types';

type Status = 'loading' | 'signedOut' | 'signedIn';
type Auth = { status: Status; signIn: (tokens: TokenPair) => Promise<void>; signOut: () => Promise<void> };

const AuthContext = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>('loading');
  const queryClient = useQueryClient();

  useEffect(() => {
    getTokens().then((tokens) => setStatus(tokens ? 'signedIn' : 'signedOut'));
    setSignedOutHandler(() => setStatus('signedOut'));
  }, []);

  const signIn = useCallback(async (tokens: TokenPair) => {
    await setTokens(tokens);
    setStatus('signedIn');
  }, []);

  const signOut = useCallback(async () => {
    await setTokens(null);
    queryClient.clear();
    setStatus('signedOut');
  }, [queryClient]);

  const value = useMemo(() => ({ status, signIn, signOut }), [status, signIn, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): Auth {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
