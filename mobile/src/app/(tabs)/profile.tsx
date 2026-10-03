import { router } from 'expo-router';
import { View } from 'react-native';

import { ErrorState } from '../../components/blocks';
import { Card, ListItem, Loading, Row, Screen, Text } from '../../components/ui';
import Icon from '../../components/Icon';
import { useI18n } from '../../i18n';
import { useMe } from '../../lib/queries';
import { colors, space } from '../../theme/tokens';

/** P1: who the farmer is and their farm, with links to points and settings. */
export default function Profile() {
  const { t } = useI18n();
  const me = useMe();
  if (me.isPending) return <Loading label={t('common.loading')} />;
  if (!me.data) return <ErrorState onRetry={() => me.refetch()} />;
  const farm = me.data.farms[0];
  const acres = farm ? Number(farm.size_acres) : null;

  return (
    <Screen title={t('profile.title')}>
      <Card>
        <Row style={{ gap: space.md }}>
          <View style={{ width: 56, height: 56, borderRadius: 28, backgroundColor: colors.leafSoft, alignItems: 'center', justifyContent: 'center' }}>
            <Icon name="person" color={colors.leaf} size={32} />
          </View>
          <View style={{ flex: 1 }}>
            <Text variant="h2">{me.data.name}</Text>
            <Text color={colors.inkMuted}>{me.data.phone}</Text>
          </View>
        </Row>
      </Card>
      {farm ? (
        <Card>
          <Row style={{ justifyContent: 'space-between' }}>
            <Text variant="h2">{t('profile.farm')}</Text>
          </Row>
          <ListItem icon="pin" label={t('profile.location')} detail={me.data.ward || `${farm.latitude}, ${farm.longitude}`} />
          <ListItem icon="leaf" label={t('profile.size')} detail={acres != null ? (acres >= 5 ? t('onboarding.sizeFivePlus') : t('profile.acres', { acres })) : ''} />
          <ListItem icon="leaf" label={t('profile.crops')} detail={t('onboarding.tomato')} />
        </Card>
      ) : null}
      <Card style={{ padding: 0 }}>
        <ListItem icon="edit" label={t('profile.editProfile')} onPress={() => router.push('/profile/edit')} />
        <ListItem icon="star" label={t('profile.points')} detail={t('profile.balance', { points: me.data.points })} onPress={() => router.push('/profile/points')} />
        <ListItem icon="globe" label={t('profile.settings')} onPress={() => router.push('/profile/settings')} />
      </Card>
    </Screen>
  );
}
