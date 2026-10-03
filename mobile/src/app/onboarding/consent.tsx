import { router } from 'expo-router';
import { useState } from 'react';

import { ApiError } from '../../api/client';
import { register } from '../../api/endpoints';
import { InfoCard } from '../../components/blocks';
import { Button, Screen, Text } from '../../components/ui';
import { useI18n } from '../../i18n';
import { useAuth } from '../../lib/auth';
import { colors } from '../../theme/tokens';
import { useSignUp } from './_layout';

/** O3: plain-language consent (Kenya Data Protection Act). Agreeing creates the account. */
export default function ConsentScreen() {
  const { t, language } = useI18n();
  const [signUp] = useSignUp();
  const { signIn } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const agree = async () => {
    setBusy(true);
    setError(null);
    try {
      const tokens = await register({
        phone: signUp.phone,
        phone_token: signUp.phoneToken,
        pin: signUp.pin,
        name: signUp.name,
        language,
        consent: true,
      });
      await signIn(tokens); // the farm setup follows automatically
    } catch (e) {
      setError(e instanceof ApiError && !e.offline ? e.message : t('common.errorBody'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen
      title={t('onboarding.consentTitle')}
      onBack={() => router.back()}
      backLabel={t('common.back')}
      footer={<Button label={t('onboarding.agree')} icon="check" onPress={agree} loading={busy} />}
    >
      <InfoCard icon="camera" title={t('onboarding.consentPhotos')} />
      <InfoCard icon="pin" title={t('onboarding.consentLocation')} />
      <InfoCard icon="phone" title={t('onboarding.consentPhone')} />
      <InfoCard icon="shield" title={t('onboarding.consentRights')} />
      {error ? (
        <Text variant="bodyStrong" color={colors.danger} accessibilityLiveRegion="polite">
          ⚠ {error}
        </Text>
      ) : null}
    </Screen>
  );
}
