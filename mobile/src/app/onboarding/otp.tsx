import { router } from 'expo-router';
import { useState } from 'react';

import { ApiError } from '../../api/client';
import { requestCode, verifyCode } from '../../api/endpoints';
import Field from '../../components/Field';
import { Button, Screen } from '../../components/ui';
import { useI18n } from '../../i18n';
import { useSignUp } from './_layout';

/** O2b: the 6-digit SMS code proves the farmer holds the phone. */
export default function OtpScreen() {
  const { t, language } = useI18n();
  const [{ phone }, update] = useSignUp();
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const verify = async () => {
    setBusy(true);
    setError(null);
    try {
      const { phone_token } = await verifyCode(phone, code);
      update({ phoneToken: phone_token });
      router.push('/onboarding/details');
    } catch (e) {
      setError(e instanceof ApiError && !e.offline ? e.message : t('common.errorBody'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen
      title={t('onboarding.otpTitle')}
      onBack={() => router.back()}
      backLabel={t('common.back')}
      footer={
        <>
          <Button label={t('onboarding.verify')} icon="check" onPress={verify} loading={busy} disabled={code.length !== 6} />
          <Button label={t('onboarding.resend')} variant="text" onPress={() => requestCode(phone, language).catch(() => undefined)} />
        </>
      }
    >
      <Field
        label={t('onboarding.otpLabel')}
        hint={t('onboarding.otpHint', { phone })}
        keyboardType="number-pad"
        autoComplete="sms-otp"
        textContentType="oneTimeCode"
        maxLength={6}
        value={code}
        onChangeText={(value) => setCode(value.replace(/\D/g, ''))}
        error={error}
        style={{ letterSpacing: 8, fontSize: 28 }}
        autoFocus
      />
    </Screen>
  );
}
