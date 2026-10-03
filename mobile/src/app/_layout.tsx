// Only the three weights the app uses (the package index would bundle all 18, ~11 MB).
import { NotoSans_500Medium } from '@expo-google-fonts/noto-sans/500Medium';
import { NotoSans_600SemiBold } from '@expo-google-fonts/noto-sans/600SemiBold';
import { NotoSans_700Bold } from '@expo-google-fonts/noto-sans/700Bold';
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { I18nProvider, useI18n } from '../i18n';
import { AuthProvider, useAuth } from '../lib/auth';
import { useOutboxSync } from '../lib/outbox';
import { persister, queryClient } from '../lib/queries';
import { colors } from '../theme/tokens';

SplashScreen.preventAutoHideAsync().catch(() => undefined);

function Navigator() {
  const { status } = useAuth();
  const { ready } = useI18n();
  useOutboxSync(status === 'signedIn');

  useEffect(() => {
    if (status !== 'loading' && ready) SplashScreen.hideAsync().catch(() => undefined);
  }, [status, ready]);

  if (status === 'loading' || !ready) return null;
  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.cream }, animation: 'slide_from_right' }}>
      <Stack.Protected guard={status === 'signedIn'}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="check" />
        <Stack.Screen name="case" />
        <Stack.Screen name="shop" />
        <Stack.Screen name="profile" />
        <Stack.Screen name="setup-farm" />
      </Stack.Protected>
      <Stack.Protected guard={status === 'signedOut'}>
        <Stack.Screen name="onboarding" />
      </Stack.Protected>
    </Stack>
  );
}

export default function RootLayout() {
  const [fontsLoaded] = useFonts({ NotoSans_500Medium, NotoSans_600SemiBold, NotoSans_700Bold });
  if (!fontsLoaded) return null;
  return (
    <SafeAreaProvider>
      <PersistQueryClientProvider client={queryClient} persistOptions={{ persister, maxAge: 7 * 24 * 60 * 60 * 1000 }}>
        <I18nProvider>
          <AuthProvider>
            <StatusBar style="dark" />
            <Navigator />
          </AuthProvider>
        </I18nProvider>
      </PersistQueryClientProvider>
    </SafeAreaProvider>
  );
}
