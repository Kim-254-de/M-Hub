import { Stack } from 'expo-router';
import { createContext, useContext, useState } from 'react';

import { colors } from '../../theme/tokens';

/** What the farmer has entered so far during sign-up (kept in memory only). */
type SignUp = { phone: string; phoneToken: string; name: string; pin: string };
type SignUpState = [SignUp, (changes: Partial<SignUp>) => void];

const SignUpContext = createContext<SignUpState | null>(null);

export function useSignUp(): SignUpState {
  const context = useContext(SignUpContext);
  if (!context) throw new Error('useSignUp must be used inside the onboarding layout');
  return context;
}

export default function OnboardingLayout() {
  const [state, setState] = useState<SignUp>({ phone: '', phoneToken: '', name: '', pin: '' });
  const update = (changes: Partial<SignUp>) => setState((current) => ({ ...current, ...changes }));
  return (
    <SignUpContext.Provider value={[state, update]}>
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.cream } }} />
    </SignUpContext.Provider>
  );
}
