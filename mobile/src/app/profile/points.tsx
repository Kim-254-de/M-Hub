import { router } from 'expo-router';
import { View } from 'react-native';

import { EmptyState, ErrorState } from '../../components/blocks';
import { PointsBadge } from '../../components/Illustrations';
import { Card, Loading, Row, Screen, Text } from '../../components/ui';
import { formatDate, useI18n } from '../../i18n';
import { useRewards } from '../../lib/queries';
import { colors, space } from '../../theme/tokens';

/** P2: points balance, discount vouchers and the points history. */
export default function Points() {
  const { t, language } = useI18n();
  const rewards = useRewards();
  if (rewards.isPending) return <Loading label={t('common.loading')} />;
  if (!rewards.data) return <ErrorState onRetry={() => rewards.refetch()} />;

  return (
    <Screen title={t('profile.points')} onBack={() => router.back()} backLabel={t('common.back')}>
      <Card tone="soft" style={{ alignItems: 'center' }}>
        <PointsBadge size={96} />
        <Text variant="display" color={colors.leaf}>
          {t('profile.balance', { points: rewards.data.balance })}
        </Text>
      </Card>
      <Text variant="h2">{t('profile.vouchers')}</Text>
      {/* Vouchers come with the discount scheme agreed with agrovets; none are issued yet. */}
      <EmptyState title={t('profile.vouchers')} body={t('profile.noVouchers')} />
      {rewards.data.entries.length ? (
        <View style={{ gap: space.sm }}>
          <Text variant="h2">{t('profile.history')}</Text>
          <Card>
            {rewards.data.entries.map((entry) => (
              <Row key={entry.id} style={{ justifyContent: 'space-between', minHeight: 48 }}>
                <View style={{ flex: 1 }}>
                  <Text variant="bodyStrong">{t(`profile.reasons.${entry.reason}`)}</Text>
                  <Text color={colors.inkMuted}>{formatDate(entry.created_at, language)}</Text>
                </View>
                <Text variant="h2" color={entry.points >= 0 ? colors.leaf : colors.soil}>
                  {entry.points >= 0 ? '+' : ''}
                  {entry.points}
                </Text>
              </Row>
            ))}
          </Card>
        </View>
      ) : null}
    </Screen>
  );
}
