import { router } from 'expo-router';
import { View } from 'react-native';

import { PointsBadge } from '../../components/Illustrations';
import { Button, Screen, Text } from '../../components/ui';
import { useI18n } from '../../i18n';
import { useRewards } from '../../lib/queries';
import { colors, space } from '../../theme/tokens';

/** S5: small celebration for the points earned by a verified purchase. */
export default function Reward() {
  const { t } = useI18n();
  const rewards = useRewards();
  const latest = rewards.data?.entries.find((e) => e.reason === 'verified_purchase');
  return (
    <Screen footer={<Button label={t('reward.continue')} icon="arrowRight" onPress={() => router.replace('/cases')} />}>
      <View style={{ alignItems: 'center', gap: space.md, paddingTop: space.xxl }}>
        <PointsBadge />
        {latest ? (
          <>
            <Text variant="h1" style={{ textAlign: 'center' }} accessibilityLiveRegion="polite">
              {t('reward.earned', { points: latest.points })}
            </Text>
            <Text variant="bodyStrong" color={colors.inkMuted}>
              {t('reward.earnedFor')}
            </Text>
          </>
        ) : null}
        {rewards.data ? (
          <Text color={colors.leaf} variant="bodyStrong">
            {t('profile.balance', { points: rewards.data.balance })}
          </Text>
        ) : null}
      </View>
    </Screen>
  );
}
