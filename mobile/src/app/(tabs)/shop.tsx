import { router } from 'expo-router';
import { View } from 'react-native';

import { EmptyState, ErrorState, InfoCard, StoreCard } from '../../components/blocks';
import { Button, Loading, Screen, Text } from '../../components/ui';
import { useI18n } from '../../i18n';
import { useCases, useMe, usePrescription, useStores } from '../../lib/queries';
import { colors, space } from '../../theme/tokens';

/** S1: the active prescription and verified shops near the farm that stock it. */
export default function Shop() {
  const { t } = useI18n();
  const me = useMe();
  const cases = useCases();
  const active = cases.data?.find((c) => c.status === 'PRESCRIBED');
  const prescription = usePrescription(active?.id ?? '', !!active);
  const card = prescription.data && !prescription.data.is_expired ? prescription.data : null;
  const farm = me.data?.farms[0];
  const stores = useStores(card?.code ?? null, farm ? { latitude: farm.latitude, longitude: farm.longitude } : undefined);

  return (
    <Screen
      title={t('shop.title')}
      footer={<Button label={t('shop.checkLabel')} icon="camera" variant="secondary" onPress={() => router.push('/shop/label')} />}
    >
      {cases.isPending ? <Loading label={t('common.loading')} /> : null}
      {!cases.isPending && !card ? (
        <EmptyState title={t('shop.noPrescriptionTitle')} body={t('shop.noPrescriptionBody')} />
      ) : null}
      {card ? (
        <>
          <InfoCard
            icon="leaf"
            tone="soft"
            title={t('shop.yourPrescription', { product: card.approved_product?.name ?? '' })}
            body={card.instructions.dose}
          />
          <Text variant="h2">{t('shop.storesNearby')}</Text>
          {stores.isPending ? <Loading label={t('common.loading')} /> : null}
          {stores.isError ? <ErrorState onRetry={() => stores.refetch()} /> : null}
          {stores.data?.length === 0 ? <Text color={colors.inkMuted}>{t('shop.noStores')}</Text> : null}
          <View style={{ gap: space.md }}>
            {stores.data?.map((offer) => (
              <StoreCard
                key={offer.store_item_id}
                offer={offer}
                onPress={() =>
                  router.push({ pathname: '/shop/store', params: { caseId: active!.id, storeItemId: offer.store_item_id } })
                }
              />
            ))}
          </View>
        </>
      ) : null}
    </Screen>
  );
}
