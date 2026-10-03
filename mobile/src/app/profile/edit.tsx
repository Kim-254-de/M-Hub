import { useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useState } from 'react';

import { ApiError } from '../../api/client';
import { updateFarm, updateMe } from '../../api/endpoints';
import { OptionSelector } from '../../components/blocks';
import Field from '../../components/Field';
import { Button, Loading, Screen, Text } from '../../components/ui';
import { useI18n } from '../../i18n';
import { keys, useMe } from '../../lib/queries';
import { colors } from '../../theme/tokens';

type Size = '0.25' | '0.50' | '1.00' | '2.00' | '5.00';
const SIZES: Size[] = ['0.25', '0.50', '1.00', '2.00', '5.00'];

/** P1 "Edit": name, ward and farm size. */
export default function EditProfile() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const me = useMe();
  const farm = me.data?.farms[0];
  const [name, setName] = useState(me.data?.name ?? '');
  const [ward, setWard] = useState(me.data?.ward ?? '');
  const [size, setSize] = useState<Size | null>(
    farm ? (SIZES.find((s) => Number(s) >= Number(farm.size_acres)) ?? '5.00') : null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!me.data) return <Loading label={t('common.loading')} />;

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await updateMe({ name: name.trim(), ward: ward.trim() });
      if (farm && size && Number(size) !== Number(farm.size_acres)) await updateFarm(farm.id, { size_acres: size });
      await queryClient.invalidateQueries({ queryKey: keys.me });
      router.back();
    } catch (e) {
      setError(e instanceof ApiError && !e.offline ? e.message : t('common.errorBody'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen
      title={t('profile.editProfile')}
      onBack={() => router.back()}
      backLabel={t('common.back')}
      footer={<Button label={t('common.save')} icon="check" onPress={save} loading={busy} disabled={!name.trim()} />}
    >
      <Field label={t('onboarding.nameLabel')} value={name} onChangeText={setName} autoCapitalize="words" />
      <Field label={t('profile.ward')} value={ward} onChangeText={setWard} autoCapitalize="words" />
      {farm ? (
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
      {error ? <Text variant="bodyStrong" color={colors.danger}>⚠ {error}</Text> : null}
    </Screen>
  );
}
