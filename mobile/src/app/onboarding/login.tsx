import { router } from 'expo-router';
import { useState } from 'react';

import { ApiError } from '../../api/client';
import { login, updateMe } from '../../api/endpoints';
import Field from '../../components/Field';
import { Button, Screen } from '../../components/ui';
import { useI18n } from '../../i18n';
import { useAuth } from '../../lib/auth';
import { normalizeKenyanPhone } from '../../lib/phone';
import { queryClient } from '../../lib/queries';

/** Returning farmer on a new phone: phone number and PIN. */
export default function LoginScreen() {
  const { t, language } = useI18n();
  const { signIn } = useAuth();
  const [raw, setRaw] = useState('');
  const [pin, setPin] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const phone = normalizeKenyanPhone(raw);
    if (!phone) return setError(t('onboarding.phoneInvalid'));
    setBusy(true);
    setError(null);
    try {
      await signIn(await login(phone, pin));
      // SMS, advice and disease names follow the language chosen on this phone.
      updateMe({ language })
        .then(() => queryClient.invalidateQueries())
        .catch(() => undefined);
    } catch (e) {
      setError(e instanceof ApiError && e.status === 401 ? t('onboarding.loginFailed') : t('common.errorBody'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen
      title={t('onboarding.loginTitle')}
      onBack={() => router.back()}
      backLabel={t('common.back')}
      footer={
        <>
          <Button label={t('onboarding.login')} icon="arrowRight" onPress={submit} loading={busy} disabled={!raw || pin.length !== 4} />
          <Button label={t('onboarding.newAccount')} variant="text" onPress={() => router.replace('/onboarding/phone')} />
        </>
      }
    >
      <Field label={t('onboarding.phoneLabel')} placeholder={t('onboarding.phonePlaceholder')} keyboardType="phone-pad" value={raw} onChangeText={setRaw} autoFocus />
      <Field
        label={t('onboarding.pin')}
        value={pin}
        onChangeText={(value) => setPin(value.replace(/\D/g, ''))}
        keyboardType="number-pad"
        secureTextEntry
        maxLength={4}
        error={error}
        style={{ letterSpacing: 12, fontSize: 28 }}
      />
    </Screen>
  );
}
