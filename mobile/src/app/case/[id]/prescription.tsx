import * as Clipboard from 'expo-clipboard';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import QRCode from 'react-native-qrcode-svg';

import { EmptyState, ErrorState, InfoCard } from '../../../components/blocks';
import Icon, { IconName } from '../../../components/Icon';
import { Button, Card, Loading, Row, Screen, Text } from '../../../components/ui';
import { formatDate, useI18n } from '../../../i18n';
import { useCase, useFollowUp, usePrescription } from '../../../lib/queries';
import { colors, radius, space, touch } from '../../../theme/tokens';

/** M2 prescription card: approved product, amount for this farm, safety, code + QR, approving agrovet. */
export default function Prescription() {
  const { t, language } = useI18n();
  const { id } = useLocalSearchParams<{ id: string }>();
  const item = useCase(id);
  const card = usePrescription(id);
  const followUp = useFollowUp(id);
  const [copied, setCopied] = useState(false);

  if (card.isPending) return <Loading label={t('common.loading')} />;
  if (card.isError) return <ErrorState onRetry={() => card.refetch()} />;
  if (!card.data) {
    return (
      <Screen onBack={() => router.back()} backLabel={t('common.back')} title={t('prescription.title')}>
        <EmptyState title={t('prescription.noPrescription')} body={t('diagnosis.waitingTitle')} />
      </Screen>
    );
  }
  const data = card.data;
  const product = data.approved_product;
  const canBuy = item.data?.status === 'PRESCRIBED' && !data.is_expired;
  const expected = followUp.data?.expected;

  const copy = async () => {
    await Clipboard.setStringAsync(data.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Screen
      title={t('prescription.title')}
      onBack={() => router.back()}
      backLabel={t('common.back')}
      footer={canBuy ? <Button label={t('prescription.buy')} icon="shop" onPress={() => router.push('/shop')} /> : undefined}
    >
      {data.is_expired ? <InfoCard icon="clock" tone="soil" title={t('prescription.expired')} /> : null}

      {product ? (
        <Card>
          <Text variant="h1">{product.name}</Text>
          <Row>
            <View style={[styles.badge, { backgroundColor: colors.verifiedSoft, borderColor: colors.verified }]}>
              <Icon name="shield" size={20} color={colors.verified} />
              <Text variant="label" color={colors.verified}>
                {t('prescription.registered')} ✓
              </Text>
            </View>
          </Row>
          <Text color={colors.inkMuted}>{t('prescription.regNo', { number: product.pcpb_reg_no })}</Text>
        </Card>
      ) : null}

      <Card tone="soft">
        <Text variant="label" color={colors.leaf}>
          {t('prescription.amount')}
        </Text>
        <Text variant="h2">{data.instructions.dose}</Text>
      </Card>

      <Card>
        <Text variant="h2">{t('prescription.safety')}</Text>
        <Row style={{ justifyContent: 'space-around' }}>
          {([['gloves', 'prescription.gloves'], ['mask', 'prescription.mask'], ['boots', 'prescription.boots']] as Array<[IconName, 'prescription.gloves' | 'prescription.mask' | 'prescription.boots']>).map(([icon, label]) => (
            <View key={icon} style={styles.ppe}>
              <Icon name={icon} size={40} color={colors.soil} />
              <Text variant="label">{t(label)}</Text>
            </View>
          ))}
        </Row>
        <View style={styles.harvest}>
          <Icon name="calendar" color={colors.warning} size={28} />
          <Text variant="bodyStrong" color={colors.warning} style={{ flex: 1 }}>
            {data.instructions.harvest}
          </Text>
        </View>
        {data.instructions.safety.map((line) => (
          <Row key={line} style={{ alignItems: 'flex-start' }}>
            <Icon name="check" size={20} color={colors.leaf} />
            <Text style={{ flex: 1 }}>{line}</Text>
          </Row>
        ))}
        {data.instructions.label_notes ? (
          <Text color={colors.inkMuted}>
            {t('prescription.fromLabel')}: {data.instructions.label_notes}
          </Text>
        ) : null}
      </Card>

      <Card>
        <Text variant="label" color={colors.inkMuted}>
          {t('prescription.code')}
        </Text>
        <Pressable accessibilityRole="button" accessibilityLabel={`${t('common.copy')} ${data.code}`} onPress={copy} style={styles.code}>
          <Text variant="code">{data.code}</Text>
          <Row style={{ gap: space.xs }}>
            <Icon name={copied ? 'check' : 'copy'} color={colors.leaf} />
            <Text variant="label" color={colors.leaf}>
              {copied ? t('common.copied') : t('common.copy')}
            </Text>
          </Row>
        </Pressable>
        <View style={styles.qr}>
          <QRCode value={data.qr_payload} size={168} color={colors.ink} backgroundColor={colors.surface} />
        </View>
        <Text color={colors.inkMuted} style={{ textAlign: 'center' }}>
          {t('prescription.codeHint')}
        </Text>
        <Text variant="bodyStrong" style={{ textAlign: 'center' }}>
          ✓ {t('prescription.approvedBy', { agrovet: data.approved_by })}
        </Text>
        <Text color={colors.inkMuted} style={{ textAlign: 'center' }}>
          {t('prescription.validUntil', { date: formatDate(data.expires_at, language) })}
        </Text>
      </Card>

      {data.options.filter((o) => o.id !== product?.id).length ? (
        <Card>
          <Text variant="h2">{t('prescription.alternatives')}</Text>
          {data.options
            .filter((o) => o.id !== product?.id)
            .slice(0, 2)
            .map((option) => (
              <View key={option.id}>
                <Text variant="bodyStrong">{option.name} ✓</Text>
                <Text color={colors.inkMuted}>{t('prescription.regNo', { number: option.pcpb_reg_no })}</Text>
              </View>
            ))}
        </Card>
      ) : null}

      {expected ? (
        <InfoCard
          icon="person"
          tone="soil"
          title={
            expected.enough_data && expected.improved != null && expected.reported != null
              ? t('prescription.localResults', { improved: expected.improved, reported: expected.reported })
              : t('prescription.noLocalData')
          }
          body={expected.enough_data ? `✓ ${t('prescription.verifiedFarmers')}` : undefined}
        />
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  badge: { flexDirection: 'row', alignItems: 'center', gap: space.xs, paddingHorizontal: space.sm, paddingVertical: 4, borderRadius: radius.pill, borderWidth: 1 },
  ppe: { alignItems: 'center', gap: space.xs, minWidth: touch.min },
  harvest: { flexDirection: 'row', gap: space.sm, alignItems: 'center', padding: space.md, borderRadius: radius.md, backgroundColor: colors.warningSoft },
  code: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', minHeight: touch.primary, paddingVertical: space.sm },
  qr: { alignItems: 'center', padding: space.md, backgroundColor: colors.surface },
});
