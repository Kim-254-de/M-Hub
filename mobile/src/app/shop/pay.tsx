import * as Clipboard from 'expo-clipboard';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, View } from 'react-native';

import { ApiError } from '../../api/client';
import { payOrder } from '../../api/endpoints';
import { ErrorState, InfoCard } from '../../components/blocks';
import Icon from '../../components/Icon';
import { Button, Card, Loading, Screen, Text } from '../../components/ui';
import { useI18n } from '../../i18n';
import { useOrder } from '../../lib/queries';
import { colors, space } from '../../theme/tokens';

/** S3: M-Pesa STK push — waiting for the PIN, then the receipt and pickup instructions. */
export default function Pay() {
  const { t } = useI18n();
  const { orderId } = useLocalSearchParams<{ orderId: string }>();
  const [polling, setPolling] = useState(true);
  const order = useOrder(orderId, polling);
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const data = order.data;
  const payment = data?.payments[0];
  const paid = data?.status === 'paid' || data?.status === 'collected';
  const reserved = data?.status === 'reserved';
  const failed = payment?.status === 'failed' && data?.status === 'awaiting_payment';
  const settled = paid || reserved || failed;

  // Stop polling once the payment has an outcome.
  useEffect(() => {
    if (settled) setPolling(false);
  }, [settled]);

  if (order.isPending) return <Loading label={t('common.loading')} />;
  if (!data) return <ErrorState onRetry={() => order.refetch()} />;

  const retry = async () => {
    setRetrying(true);
    setError(null);
    try {
      await payOrder(orderId);
      setPolling(true);
      order.refetch();
    } catch (e) {
      setError(e instanceof ApiError && !e.offline ? e.message : t('common.errorBody'));
    } finally {
      setRetrying(false);
    }
  };

  if (!paid && !reserved) {
    return (
      <Screen
        footer={failed ? <Button label={t('common.retry')} icon="refresh" onPress={retry} loading={retrying} /> : undefined}
      >
        <View style={{ alignItems: 'center', gap: space.lg, paddingTop: space.xl }}>
          <Icon name={failed ? 'warning' : 'phone'} size={72} color={failed ? colors.warningIcon : colors.leaf} />
          <Text variant="h1" style={{ textAlign: 'center' }}>
            {failed ? t('shop.mpesaFailed') : t('shop.mpesaTitle')}
          </Text>
          {!failed ? (
            <>
              <Text variant="bodyStrong" style={{ textAlign: 'center' }}>
                {t('shop.mpesaBody', { amount: t('common.kes', { amount: data.total_kes.toLocaleString() }) })}
              </Text>
              <ActivityIndicator size="large" color={colors.leaf} />
              <Text color={colors.inkMuted}>{t('shop.mpesaWaiting')}</Text>
            </>
          ) : payment?.result_desc ? (
            <Text color={colors.inkMuted} style={{ textAlign: 'center' }}>
              {payment.result_desc}
            </Text>
          ) : null}
          {error ? <Text variant="bodyStrong" color={colors.danger}>⚠ {error}</Text> : null}
        </View>
      </Screen>
    );
  }

  return (
    <Screen footer={<Button label={t('common.done')} icon="check" onPress={() => router.replace('/shop')} />}>
      <View style={{ alignItems: 'center', gap: space.md, paddingTop: space.lg }}>
        <Icon name="checkCircle" size={72} color={colors.verified} strokeWidth={2.5} />
        <Text variant="h1" style={{ textAlign: 'center' }}>
          {paid ? t('shop.paidTitle') : t('shop.reservedTitle')}
        </Text>
        {paid && payment?.mpesa_receipt ? <Text variant="bodyStrong">{t('shop.receipt', { receipt: payment.mpesa_receipt })}</Text> : null}
      </View>
      <Card>
        <Text variant="bodyStrong">{t('shop.pickup', { store: data.agrovet_name })}</Text>
        <Text variant="code" selectable onPress={() => Clipboard.setStringAsync(data.prescription_code)}>
          {data.prescription_code}
        </Text>
        <Text color={colors.inkMuted}>
          {data.product.name} × {data.quantity} · {t('common.kes', { amount: data.total_kes.toLocaleString() })}
        </Text>
      </Card>
      <InfoCard icon="shield" title={t('shop.checkLabel')} body={t('shop.labelHint')} />
    </Screen>
  );
}
