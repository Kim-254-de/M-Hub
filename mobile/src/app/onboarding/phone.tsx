import { router } from 'expo-router';
import { useState } from 'react';

import { ApiError } from '../../api/client';
import { requestCode } from '../../api/endpoints';
import Field from '../../components/Field';
import { Button, Screen } from '../../components/ui';
import { useI18n } from '../../i18n';
import { normalizeKenyanPhone } from '../../lib/phone';
import { useSignUp } from './_layout';

/** O2a: phone number; an SMS code is sent to it. */
export default function PhoneScreen() {
  const { t, language } = useI18n();
  const [, update] = useSignUp();
  const [raw, setRaw] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const send = async () => {
    const phone = normalizeKenyanPhone(raw);
    if (!phone) return setError(t('onboarding.phoneInvalid'));
    setError(null);
    setBusy(true);
    try {
      await requestCode(phone, language);
      update({ phone });
      router.push('/onboarding/otp');
    } catch (e) {
      setError(e instanceof ApiError && !e.offline ? e.message : t('common.errorBody'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen
      title={t('onboarding.phoneTitle')}
      onBack={() => router.back()}
      backLabel={t('common.back')}
      footer={
        <>
          <Button label={t('onboarding.sendCode')} icon="phone" onPress={send} loading={busy} disabled={!raw.trim()} />
          <Button label={t('onboarding.haveAccount')} variant="text" onPress={() => router.push('/onboarding/login')} />
        </>
      }
    >
      <Field
        label={t('onboarding.phoneLabel')}
        hint={t('onboarding.phoneHint')}
        placeholder={t('onboarding.phonePlaceholder')}
        keyboardType="phone-pad"
        autoComplete="tel"
        textContentType="telephoneNumber"
        value={raw}
        onChangeText={setRaw}
        onSubmitEditing={send}
        error={error}
        autoFocus
      />
    </Screen>
  );
}
