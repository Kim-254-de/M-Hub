import { useQueryClient } from '@tanstack/react-query';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { Linking, Pressable, StyleSheet } from 'react-native';

import { ApiError } from '../../api/client';
import { createOrder, payOrder } from '../../api/endpoints';
import { ErrorState } from '../../components/blocks';
import Icon from '../../components/Icon';
import { Button, Card, Loading, Row, Screen, Text } from '../../components/ui';
import { useI18n } from '../../i18n';
import { keys, useMe, usePrescription, useStores } from '../../lib/queries';
import { colors, radius, space, touch } from '../../theme/tokens';

/** S2: one verified store's offer — quantity pre-filled from the prescription, then pay or reserve. */
export default function Store() {
  const { t } = useI18n();
  const { caseId, storeItemId } = useLocalSearchParams<{ caseId: string; storeItemId: string }>();
  const queryClient = useQueryClient();
  const me = useMe();
  const card = usePrescription(caseId);
  const farm = me.data?.farms[0];
  const stores = useStores(card.data?.code ?? null, farm ? { latitude: farm.latitude, longitude: farm.longitude } : undefined);
  const offer = stores.data?.find((o) => o.store_item_id === storeItemId);
  const [quantity, setQuantity] = useState(1);
  const [busy, setBusy] = useState<'mpesa' | 'pay_at_shop' | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (card.data?.dose_packs) setQuantity(card.data.dose_packs);
  }, [card.data?.dose_packs]);

  if (card.isPending || stores.isPending) return <Loading label={t('common.loading')} />;
  if (!card.data || !offer) return <ErrorState onRetry={() => stores.refetch()} />;

  const order = async (method: 'mpesa' | 'pay_at_shop') => {
    setBusy(method);
    setError(null);
    try {
      const created = await createOrder({ prescription_code: card.data!.code, store_item_id: offer.store_item_id, quantity, payment_method: method });
      if (method === 'mpesa') await payOrder(created.id);
      queryClient.invalidateQueries({ queryKey: keys.orders });
      router.replace({ pathname: '/shop/pay', params: { orderId: created.id } });
    } catch (e) {
      setError(e instanceof ApiError && !e.offline ? e.message : t('common.errorBody'));
    } finally {
      setBusy(null);
    }
  };

  const directions = () =>
    Linking.openURL(`https://www.google.com/maps/dir/?api=1&destination=${offer.latitude},${offer.longitude}`);

  return (
    <Screen
      title={offer.agrovet_name}
      onBack={() => router.back()}
      backLabel={t('common.back')}
      footer={
        <>
          <Button label={t('shop.payMpesa')} icon="phone" onPress={() => order('mpesa')} loading={busy === 'mpesa'} disabled={!!busy} />
          <Button label={t('shop.reserve')} icon="shop" variant="secondary" onPress={() => order('pay_at_shop')} loading={busy === 'pay_at_shop'} disabled={!!busy} />
        </>
      }
    >
      <Card>
        <Text variant="h2">{offer.product.name}</Text>
        <Row>
          <Icon name="shield" color={colors.verified} size={20} />
          <Text variant="label" color={colors.verified}>
            {t('prescription.registered')} ✓ · {offer.product.pcpb_reg_no}
          </Text>
        </Row>
        <Text variant="h1" color={colors.soil}>
          {t('common.kes', { amount: offer.price_kes.toLocaleString() })}
        </Text>
      </Card>

      <Card>
        <Text variant="bodyStrong">{t('shop.quantity')}</Text>
        <Row style={{ justifyContent: 'space-between' }}>
          <Stepper label="−" onPress={() => setQuantity(Math.max(1, quantity - 1))} disabled={quantity <= 1} />
          <Text variant="display" accessibilityLiveRegion="polite">
            {quantity}
          </Text>
          <Stepper label="+" onPress={() => setQuantity(Math.min(20, quantity + 1))} />
        </Row>
        <Text color={colors.inkMuted}>{card.data.instructions.dose}</Text>
        <Row style={{ justifyContent: 'space-between' }}>
          <Text variant="bodyStrong">{t('shop.total')}</Text>
          <Text variant="h2">{t('common.kes', { amount: (offer.price_kes * quantity).toLocaleString() })}</Text>
        </Row>
      </Card>

      <Button label={t('shop.directions')} icon="directions" variant="text" onPress={directions} />
      {error ? (
        <Text variant="bodyStrong" color={colors.danger}>
          ⚠ {error}
        </Text>
      ) : null}
    </Screen>
  );
}

function Stepper({ label, onPress, disabled }: { label: string; onPress: () => void; disabled?: boolean }) {
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress} disabled={disabled} style={[styles.stepper, disabled && { borderColor: colors.disabled }]}>
      <Text variant="h1" color={disabled ? colors.disabled : colors.leaf}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  stepper: { width: touch.primary, height: touch.primary, borderRadius: radius.md, borderWidth: 2, borderColor: colors.leaf, alignItems: 'center', justifyContent: 'center' },
});

