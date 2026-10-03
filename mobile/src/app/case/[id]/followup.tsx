import { useQueryClient } from '@tanstack/react-query';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { ApiError } from '../../../api/client';
import { addCheckIn, recordSpray } from '../../../api/endpoints';
import { ErrorState, InfoCard, OptionSelector } from '../../../components/blocks';
import Icon from '../../../components/Icon';
import { Button, Card, Loading, Row, Screen, Text } from '../../../components/ui';
import { formatDate, useI18n } from '../../../i18n';
import { keys, useFollowUp } from '../../../lib/queries';
import { colors, space } from '../../../theme/tokens';

type Spots = 'spreading' | 'fewer' | 'stopped';
type Share = 'few' | 'some' | 'most';

/** Apply & Follow-up: record spraying, then report new spots on days 2, 4 and 7. */
export default function FollowUpScreen() {
  const { t, language } = useI18n();
  const { id } = useLocalSearchParams<{ id: string }>();
  const queryClient = useQueryClient();
  const followUp = useFollowUp(id);
  const [daysAgo, setDaysAgo] = useState<'0' | '1' | '2' | null>(null);
  const [spots, setSpots] = useState<Spots | null>(null);
  const [share, setShare] = useState<Share | null>(null);
  const [advice, setAdvice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (followUp.isPending) return <Loading label={t('common.loading')} />;
  if (!followUp.data) return <ErrorState onRetry={() => followUp.refetch()} />;
  const data = followUp.data;
  const due = data.schedule.find((s) => s.status === 'due');

  const run = async (request: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      const result = await request();
      queryClient.setQueryData(keys.followUp(id), result);
      queryClient.invalidateQueries({ queryKey: keys.case(id) });
      return result;
    } catch (e) {
      setError(e instanceof ApiError && !e.offline ? e.message : t('common.errorBody'));
      return null;
    } finally {
      setBusy(false);
    }
  };

  const spray = () => {
    const when = new Date(Date.now() - Number(daysAgo) * 24 * 60 * 60 * 1000);
    run(() => recordSpray(id, when.toISOString()));
  };

  const checkIn = async () => {
    if (!due || !spots || !share) return;
    const result = (await run(() => addCheckIn(id, { day: due.day, new_spots: spots, share_affected: share }))) as typeof data | null;
    const saved = result?.schedule.find((s) => s.day === due.day)?.check_in;
    if (saved) {
      setAdvice(saved.advice);
      setSpots(null);
      setShare(null);
    }
  };

  // 1) Not sprayed yet.
  if (data.can_record_spray) {
    return (
      <Screen
        title={t('followup.title')}
        onBack={() => router.back()}
        backLabel={t('common.back')}
        footer={<Button label={t('followup.recordSpray')} icon="spray" onPress={spray} loading={busy} disabled={!daysAgo} />}
      >
        <Text>{t('followup.sprayHint')}</Text>
        <OptionSelector<'0' | '1' | '2'>
          question={t('followup.whenSprayed')}
          value={daysAgo}
          onChange={setDaysAgo}
          options={[
            { value: '0', label: t('followup.sprayedToday') },
            { value: '1', label: t('followup.sprayedYesterday') },
            { value: '2', label: t('followup.sprayedDaysAgo', { days: 2 }) },
          ]}
        />
        {error ? <Text variant="bodyStrong" color={colors.danger}>⚠ {error}</Text> : null}
      </Screen>
    );
  }
  if (!data.spray) {
    return (
      <Screen title={t('followup.title')} onBack={() => router.back()} backLabel={t('common.back')}>
        <InfoCard icon="shield" title={t('followup.verifiedOnly')} />
      </Screen>
    );
  }

  // 2) Sprayed: schedule, harvest date, and today's check-in when one is due.
  return (
    <Screen
      title={t('followup.title')}
      onBack={() => router.back()}
      backLabel={t('common.back')}
      footer={due && !advice ? <Button label={t('followup.send')} icon="check" onPress={checkIn} loading={busy} disabled={!spots || !share} /> : <Button label={t('common.done')} onPress={() => router.back()} />}
    >
      {data.spray.harvest_safe_from ? (
        <View style={{ flexDirection: 'row', gap: space.sm, alignItems: 'center', padding: space.md, borderRadius: 12, backgroundColor: colors.warningSoft }}>
          <Icon name="calendar" color={colors.warning} size={28} />
          <Text variant="bodyStrong" color={colors.warning} style={{ flex: 1 }}>
            {t('followup.harvestWait', { date: formatDate(data.spray.harvest_safe_from, language) })}
          </Text>
        </View>
      ) : null}

      <Card>
        {data.schedule.map((item) => (
          <Row key={item.day} style={{ justifyContent: 'space-between', minHeight: 48 }}>
            <Text variant="bodyStrong">{t('followup.day', { day: item.day })}</Text>
            <Row style={{ gap: space.xs }}>
              <Icon
                name={item.status === 'done' ? 'checkCircle' : item.status === 'due' ? 'clock' : item.status === 'missed' ? 'close' : 'calendar'}
                size={20}
                color={item.status === 'done' ? colors.verified : item.status === 'due' ? colors.leaf : colors.inkMuted}
              />
              <Text color={item.status === 'due' ? colors.leaf : colors.inkMuted} variant={item.status === 'due' ? 'bodyStrong' : 'body'}>
                {item.status === 'done'
                  ? t('followup.done')
                  : item.status === 'due'
                    ? t('followup.due')
                    : item.status === 'missed'
                      ? t('followup.missed')
                      : t('followup.upcoming', { date: formatDate(item.due_at, language) })}
              </Text>
            </Row>
          </Row>
        ))}
      </Card>

      {advice ? <InfoCard icon="leaf" tone="soft" title={advice} /> : null}

      {due && !advice ? (
        <>
          <Text variant="h2">{t('followup.checkInTitle', { day: due.day })}</Text>
          <OptionSelector<Spots>
            question={t('followup.qNewSpots')}
            value={spots}
            onChange={setSpots}
            options={[
              { value: 'spreading', label: t('followup.spotsSpreading') },
              { value: 'fewer', label: t('followup.spotsFewer') },
              { value: 'stopped', label: t('followup.spotsStopped') },
            ]}
          />
          <OptionSelector<Share>
            question={t('followup.qShare')}
            value={share}
            onChange={setShare}
            options={[
              { value: 'few', label: t('check.manyFew') },
              { value: 'some', label: t('check.manyHalf') },
              { value: 'most', label: t('check.manyMost') },
            ]}
          />
        </>
      ) : null}
      {data.complete ? <InfoCard icon="checkCircle" tone="soft" title={t('followup.complete')} /> : null}
      {error ? <Text variant="bodyStrong" color={colors.danger}>⚠ {error}</Text> : null}
    </Screen>
  );
}
