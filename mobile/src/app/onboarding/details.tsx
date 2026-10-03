import { router } from 'expo-router';
import { useState } from 'react';

import Field from '../../components/Field';
import { Button, Screen } from '../../components/ui';
import { useI18n } from '../../i18n';
import { useSignUp } from './_layout';

/** O2c: name (for the greeting) and a 4-digit PIN for later logins. */
export default function DetailsScreen() {
  const { t } = useI18n();
  const [signUp, update] = useSignUp();
  const [name, setName] = useState(signUp.name);
  const [pin, setPin] = useState('');
  const [error, setError] = useState<string | null>(null);

  const next = () => {
    if (!/^\d{4}$/.test(pin)) return setError(t('onboarding.pinInvalid'));
    update({ name: name.trim(), pin });
    router.push('/onboarding/consent');
  };

  return (
    <Screen
      title={t('onboarding.detailsTitle')}
      onBack={() => router.back()}
      backLabel={t('common.back')}
      footer={<Button label={t('common.next')} icon="arrowRight" onPress={next} disabled={!name.trim() || pin.length !== 4} />}
    >
      <Field label={t('onboarding.nameLabel')} value={name} onChangeText={setName} autoComplete="name" autoCapitalize="words" autoFocus />
      <Field
        label={t('onboarding.pinLabel')}
        hint={t('onboarding.pinHint')}
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
