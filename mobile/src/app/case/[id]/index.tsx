import { useAudioPlayer, useAudioPlayerStatus } from 'expo-audio';
import { router, useLocalSearchParams } from 'expo-router';
import { Image, ScrollView, StyleSheet, View } from 'react-native';

import type { Case, CaseDiagnosis } from '../../../api/types';
import { chipFor, ErrorState, EvidenceBlock, InfoCard, ProgressTracker, StatusChip, trackerStep } from '../../../components/blocks';
import Icon from '../../../components/Icon';
import { Button, Card, Loading, Row, Screen, Text } from '../../../components/ui';
import { formatDate, useI18n } from '../../../i18n';
import { useCase, useDiagnosis, useFollowUp } from '../../../lib/queries';
import { colors, radius, space } from '../../../theme/tokens';

const AFTER_DIAGNOSIS = ['DIAGNOSED', 'PRESCRIBED', 'EXPIRED', 'PURCHASED', 'VERIFIED', 'FLAGGED'];

/** M2 (with C5/C6): one case — progress, diagnosis and evidence, photos, and the next step. */
export default function CaseDetail() {
  const { t, language } = useI18n();
  const { id } = useLocalSearchParams<{ id: string }>();
  const item = useCase(id);
  const diagnosis = useDiagnosis(id);
  const followUp = useFollowUp(id, item.data?.status === 'VERIFIED');

  if (item.isPending) return <Loading label={t('common.loading')} />;
  if (!item.data) return <ErrorState onRetry={() => item.refetch()} />;
  const data = item.data;
  const confirmed = AFTER_DIAGNOSIS.includes(data.status);

  let primary: { label: string; icon: 'leaf' | 'spray' | 'camera' | 'calendar'; go: () => void } | null = null;
  if (data.detection.needs_retake) {
    primary = { label: t('diagnosis.retakeAction'), icon: 'camera', go: () => router.push({ pathname: '/check/photos', params: { caseId: id } }) };
  } else if (data.status === 'VERIFIED' && followUp.data && !followUp.data.complete) {
    const due = followUp.data.schedule.find((s) => s.status === 'due');
    if (followUp.data.can_record_spray) primary = { label: t('followup.recordSpray'), icon: 'spray', go: () => router.push(`/case/${id}/followup`) };
    else if (due) primary = { label: `${t('followup.due')} · ${t('followup.day', { day: due.day })}`, icon: 'calendar', go: () => router.push(`/case/${id}/followup`) };
  } else if (confirmed) {
    primary = { label: t('diagnosis.seeTreatment'), icon: 'leaf', go: () => router.push(`/case/${id}/prescription`) };
  }

  return (
    <Screen
      onBack={() => router.back()}
      backLabel={t('common.back')}
      footer={
        <>
          {primary ? <Button label={primary.label} icon={primary.icon} onPress={primary.go} /> : null}
          <Button label={t('ask.button')} icon="question" variant={primary ? 'text' : 'secondary'} onPress={() => router.push(`/case/${id}/ask`)} />
        </>
      }
    >
      <View style={{ gap: space.sm }}>
        <Text variant="display" accessibilityRole="header">
          {confirmed ? (diagnosis.data?.disease_name ?? data.disease ?? '') : t('status.waitingAgrovet')}
        </Text>
        <StatusChip kind={chipFor(data.status)} />
        <Text color={colors.inkMuted}>{t('cases.reported', { date: formatDate(data.submitted_at ?? data.created_at, language) })}</Text>
      </View>
      <Card>
        <ProgressTracker done={trackerStep(data.status)} />
      </Card>

      {data.detection.needs_retake ? (
        <InfoCard icon="camera" tone="soil" title={t('diagnosis.retakeTitle')} body={data.detection.retake_message ?? undefined} />
      ) : null}
      {diagnosis.data ? <DiagnosisSection item={data} diagnosis={diagnosis.data} /> : null}
      {followUp.data?.complete ? <InfoCard icon="checkCircle" tone="soft" title={t('followup.complete')} /> : null}

      {data.photos.length ? (
        <View style={{ gap: space.sm }}>
          <Text variant="h2">{t('cases.photos')}</Text>
          <ScrollView horizontal contentContainerStyle={{ gap: space.sm }}>
            {data.photos.map((photo) => (
              <Image key={photo.id} source={{ uri: photo.image }} style={styles.photo} accessibilityLabel={photo.type} />
            ))}
          </ScrollView>
        </View>
      ) : null}
      {data.voice_note ? <VoiceNote uri={data.voice_note} /> : null}
    </Screen>
  );
}

function DiagnosisSection({ item, diagnosis }: { item: Case; diagnosis: CaseDiagnosis }) {
  const { t } = useI18n();
  const provisional = diagnosis.provisional;
  const percent = provisional?.probability != null ? Math.round(provisional.probability * 100) : null;
  const aiValue =
    provisional?.kind === 'likely' && provisional.name && percent != null
      ? t('diagnosis.aiSuggestionValue', { name: provisional.name, percent })
      : provisional?.message ?? null;

  if (item.status === 'SECOND_OPINION') {
    return <InfoCard icon="clock" tone="soft" title={t('diagnosis.secondOpinionTitle')} body={t('diagnosis.secondOpinionBody')} />;
  }
  if (item.status === 'UNKNOWN') {
    return <InfoCard icon="help" tone="soft" title={t('diagnosis.unsureTitle')} body={t('diagnosis.unsureBody')} />;
  }
  if (!diagnosis.confirmed_by) {
    // Waiting: the AI suggestion is clearly provisional; never the final answer.
    return (
      <View style={{ gap: space.md }}>
        <InfoCard
          icon="clock"
          tone="soft"
          title={t('diagnosis.waitingTitle')}
          body={diagnosis.reviewer ? t('diagnosis.reviewer', { agrovet: diagnosis.reviewer.name }) : undefined}
        />
        {aiValue ? <EvidenceBlock icon="leaf" title={`${t('diagnosis.aiSuggestion')} · ${t('diagnosis.notConfirmedYet')}`} value={aiValue} /> : null}
        {diagnosis.safe_actions.length ? (
          <View style={{ gap: space.sm }}>
            <Text variant="h2">{t('check.whatToDoNow')}</Text>
            {diagnosis.safe_actions.map((step) => (
              <InfoCard key={step} icon="leaf" title={step} />
            ))}
          </View>
        ) : null}
      </View>
    );
  }
  // Confirmed (C5): the agrovet's confirmation is the authority; AI and nearby cases are supporting evidence.
  return (
    <View style={{ gap: space.md }}>
      {diagnosis.explanation ? <Text variant="bodyStrong">{diagnosis.explanation}</Text> : diagnosis.message ? <Text variant="bodyStrong">{diagnosis.message}</Text> : null}
      {diagnosis.ai_corrected ? <InfoCard icon="warning" tone="soil" title={t('diagnosis.aiCorrected')} /> : null}
      <View style={{ gap: space.sm }}>
        {diagnosis.ai_evidence ? (
          <EvidenceBlock icon="leaf" title={t('diagnosis.aiSuggestion')} value={t('diagnosis.aiSuggestionValue', diagnosis.ai_evidence)} />
        ) : null}
        {diagnosis.similar_nearby != null ? (
          <EvidenceBlock icon="pin" title={t('diagnosis.similarNearby')} value={t('diagnosis.similarNearbyValue', { count: diagnosis.similar_nearby })} />
        ) : null}
        <EvidenceBlock icon="shield" tone="verified" title={`✓ ${t('status.confirmed')}`} value={t('diagnosis.confirmedBy', { agrovet: diagnosis.confirmed_by })} />
      </View>
    </View>
  );
}

function VoiceNote({ uri }: { uri: string }) {
  const { t } = useI18n();
  const player = useAudioPlayer(uri);
  const status = useAudioPlayerStatus(player);
  return (
    <Card tone="soil">
      <Row style={{ justifyContent: 'space-between' }}>
        <Row>
          <Icon name="mic" color={colors.soil} />
          <Text variant="bodyStrong">{t('cases.voiceNote')}</Text>
        </Row>
        <Button
          label={status.playing ? t('cases.stop') : t('cases.play')}
          icon={status.playing ? 'stop' : 'play'}
          variant="text"
          onPress={() => {
            if (status.playing) player.pause();
            else {
              player.seekTo(0);
              player.play();
            }
          }}
        />
      </Row>
    </Card>
  );
}

const styles = StyleSheet.create({
  photo: { width: 96, height: 96, borderRadius: radius.md, backgroundColor: colors.leafSoft },
});
