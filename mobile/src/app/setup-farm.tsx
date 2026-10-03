import { useQueryClient } from '@tanstack/react-query';
import * as Location from 'expo-location';
import { router } from 'expo-router';
import { useState } from 'react';

import { ApiError } from '../api/client';
import { createFarm } from '../api/endpoints';
import { InfoCard, OptionSelector } from '../components/blocks';
import { Button, Screen, Text } from '../components/ui';
import { useI18n } from '../i18n';
import { keys } from '../lib/queries';
import { colors } from '../theme/tokens';

type Size = '0.25' | '0.50' | '1.00' | '2.00' | '5.00';

/** O4: farm setup in 3 short steps — location, size, crop. */
export default function SetupFarm() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [step, setStep] = useState(1);
  const [location, setLocation] = useState<{ latitude: string; longitude: string } | null>(null);
  const [size, setSize] = useState<Size | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const locate = async () => {
    setBusy(true);
    setError(null);
    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (!permission.granted) throw new Error('denied');
      const position = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      setLocation({ latitude: position.coords.latitude.toFixed(6), longitude: position.coords.longitude.toFixed(6) });
    } catch {
      setError(t('onboarding.locationDenied'));
    } finally {
      setBusy(false);
    }
  };

  const finish = async () => {
    if (!location || !size) return;
    setBusy(true);
    setError(null);
    try {
      await createFarm({ ...location, size_acres: size, crops: ['tomato'] });
      await queryClient.invalidateQueries({ queryKey: keys.me });
      router.replace('/');
    } catch (e) {
      setError(e instanceof ApiError && !e.offline ? e.message : t('common.errorBody'));
    } finally {
      setBusy(false);
    }
  };

  const footer =
    step === 1 ? (
      location ? (
        <Button label={t('common.next')} icon="arrowRight" onPress={() => setStep(2)} />
      ) : (
        <Button label={t('onboarding.useMyLocation')} icon="pin" onPress={locate} loading={busy} />
      )
    ) : step === 2 ? (
      <Button label={t('common.next')} icon="arrowRight" onPress={() => setStep(3)} disabled={!size} />
    ) : (
      <Button label={t('onboarding.finish')} icon="check" onPress={finish} loading={busy} />
    );

  return (
    <Screen
      title={t('onboarding.farmTitle')}
      step={t('common.stepOf', { step, total: 3 })}
      onBack={step > 1 ? () => setStep(step - 1) : undefined}
      backLabel={t('common.back')}
      footer={footer}
    >
      {step === 1 ? (
        <>
          <Text variant="h2">{t('onboarding.farmLocation')}</Text>
          {location ? (
            <InfoCard icon="pin" tone="soft" title={`✓ ${t('onboarding.locationFound')}`} body={`${location.latitude}, ${location.longitude}`} />
          ) : null}
        </>
      ) : null}
      {step === 2 ? (
        <OptionSelector<Size>
          question={t('onboarding.farmSize')}
          value={size}
          onChange={setSize}
          options={[
            { value: '0.25', label: t('onboarding.sizeQuarter') },
            { value: '0.50', label: t('onboarding.sizeHalf') },
            { value: '1.00', label: t('onboarding.sizeOne') },
            { value: '2.00', label: t('onboarding.sizeTwo') },
            { value: '5.00', label: t('onboarding.sizeFivePlus') },
          ]}
        />
      ) : null}
      {step === 3 ? (
        <OptionSelector question={t('onboarding.crop')} value="tomato" onChange={() => undefined} options={[{ value: 'tomato', label: t('onboarding.tomato') }]} />
      ) : null}
      {error ? (
        <Text variant="bodyStrong" color={colors.danger} accessibilityLiveRegion="polite">
          ⚠ {error}
        </Text>
      ) : null}
    </Screen>
  );
}
