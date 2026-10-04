import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { CaseCard, EmptyState, ErrorState, StatusChip } from '../../components/blocks';
import { EmptyCases } from '../../components/Illustrations';
import OfflineBanner from '../../components/OfflineBanner';
import { Button, Loading, Text } from '../../components/ui';
import { formatDate, useI18n } from '../../i18n';
import { useCases } from '../../lib/queries';
import { flushOutbox, PendingReport, pendingReports } from '../../offline/reports';
import { colors, radius, space } from '../../theme/tokens';

/** M1: the farmer's cases, newest first; reports waiting to be sent are shown on top. */
export default function MyCases() {
  const { t, language } = useI18n();
  const cases = useCases();
  const [queued, setQueued] = useState<PendingReport[]>([]);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  const sendNow = async () => {
    setSending(true);
    setSendError(null);
    const result = await flushOutbox();
    setSendError(result.error);
    setQueued(await pendingReports());
    cases.refetch();
    setSending(false);
  };

  useEffect(() => {
    pendingReports().then(setQueued);
  }, [cases.dataUpdatedAt]);

  const items = cases.data ?? [];
  return (
    <SafeAreaView style={styles.screen} edges={['top', 'left', 'right']}>
      <OfflineBanner />
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={cases.isRefetching} onRefresh={() => cases.refetch()} colors={[colors.leaf]} />}
      >
        <Text variant="h1" accessibilityRole="header">
          {t('cases.title')}
        </Text>
        {queued.map((report) => (
          <View key={report.localId} style={styles.queued}>
            <Text variant="bodyStrong">{t('check.queuedTitle')}</Text>
            <Text color={colors.inkMuted}>{t('cases.reported', { date: formatDate(report.createdAt, language) })}</Text>
            <StatusChip kind="draft" />
            {report.retake ? (
              <Button label={t('diagnosis.retakeAction')} icon="camera" variant="secondary" onPress={() => router.push(`/check/photos?localId=${report.localId}`)} />
            ) : report.answers ? (
              <Button label={t('cases.sendNow')} icon="refresh" variant="secondary" onPress={sendNow} loading={sending} />
            ) : null}
            {sendError ? (
              <Text variant="bodyStrong" color={colors.danger}>
                ⚠ {sendError}
              </Text>
            ) : null}
          </View>
        ))}
        {cases.isPending ? <Loading label={t('common.loading')} /> : null}
        {cases.isError && !cases.data ? <ErrorState onRetry={() => cases.refetch()} /> : null}
        {cases.data && items.length === 0 && queued.length === 0 ? (
          <EmptyState
            art={<EmptyCases />}
            title={t('cases.emptyTitle')}
            body={t('cases.emptyBody')}
            action={<Button label={t('check.checkMyTomatoes')} icon="camera" onPress={() => router.push('/check/photos')} />}
          />
        ) : null}
        {items
          .filter((item) => item.status !== 'DRAFT')
          .map((item) => (
            <CaseCard key={item.id} item={item} onPress={() => router.push(`/case/${item.id}`)} />
          ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.cream },
  content: { padding: space.lg, gap: space.md },
  queued: {
    padding: space.lg,
    gap: space.xs,
    borderRadius: radius.lg,
    borderWidth: 2,
    borderStyle: 'dashed',
    borderColor: colors.warningIcon,
    backgroundColor: colors.warningSoft,
  },
});
