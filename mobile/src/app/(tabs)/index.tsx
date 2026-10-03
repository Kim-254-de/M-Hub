import { Redirect, router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { AlertCard, ErrorState } from '../../components/blocks';
import { FarmerWithPlant } from '../../components/Illustrations';
import { Button, Loading, Screen, Text } from '../../components/ui';
import { useI18n } from '../../i18n';
import { useMe, useOutbreaks } from '../../lib/queries';
import { colors, space } from '../../theme/tokens';

/** C1: greeting, one giant button, and an alert only when there is an outbreak nearby. */
export default function CheckCropHome() {
  const { t } = useI18n();
  const me = useMe();
  const outbreaks = useOutbreaks();

  if (me.isPending) return <Loading label={t('common.loading')} />;
  if (!me.data) return <ErrorState onRetry={() => me.refetch()} />;
  if (me.data && me.data.farms.length === 0) return <Redirect href="/setup-farm" />;

  const firstName = me.data?.name.split(' ')[0] ?? '';
  const alert = outbreaks.data?.[0];
  return (
    <Screen>
      <View style={{ gap: space.xs }}>
        <Text variant="display" accessibilityRole="header">
          {t('check.greeting', { name: firstName })}
        </Text>
        <Text color={colors.inkMuted}>{t('check.greetingHint')}</Text>
      </View>
      {alert ? <AlertCard message={`⚠ ${alert.message}`} /> : null}
      <View style={styles.art}>
        <FarmerWithPlant size={alert ? 140 : 200} />
      </View>
      <Button big icon="camera" label={t('check.checkMyTomatoes')} onPress={() => router.push('/check/photos')} />
    </Screen>
  );
}

const styles = StyleSheet.create({ art: { alignItems: 'center' } });
