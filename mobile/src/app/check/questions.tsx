import { AudioModule, RecordingPresets, setAudioModeAsync, useAudioRecorder, useAudioRecorderState } from 'expo-audio';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import type { SymptomAnswers } from '../../api/types';
import { OptionSelector } from '../../components/blocks';
import Icon from '../../components/Icon';
import { Button, Row, Screen, Text } from '../../components/ui';
import { useI18n } from '../../i18n';
import { keepFile, pendingReports, phoneIsOffline, saveReport, sendReport } from '../../offline/reports';
import { ApiError } from '../../api/client';
import { colors, radius, space } from '../../theme/tokens';

type When = 'today' | 'week' | 'longer';
type Many = 'few' | 'some' | 'most';
type YesNoUnsure = 'yes' | 'no' | 'unsure';

const STARTED: Record<When, SymptomAnswers['started']> = {
  today: 'less_than_3_days',
  week: '3_to_7_days',
  longer: '1_to_2_weeks',
};

const MAX_VOICE_SECONDS = 60;

/** C3: four tap-only questions and an optional voice note, then the report is sent (or queued). */
export default function Questions() {
  const { t } = useI18n();
  const { localId } = useLocalSearchParams<{ localId: string }>();
  const [when, setWhen] = useState<When | null>(null);
  const [many, setMany] = useState<Many | null>(null);
  const [rain, setRain] = useState<YesNoUnsure | null>(null);
  const [sprayed, setSprayed] = useState<'yes' | 'no' | null>(null);
  const [voiceUri, setVoiceUri] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const recorder = useAudioRecorder(RecordingPresets.LOW_QUALITY);
  const recorderState = useAudioRecorderState(recorder);
  const seconds = Math.floor((recorderState.durationMillis ?? 0) / 1000);

  useEffect(() => {
    if (recorderState.isRecording && seconds >= MAX_VOICE_SECONDS) stopRecording();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seconds, recorderState.isRecording]);

  const startRecording = async () => {
    const permission = await AudioModule.requestRecordingPermissionsAsync();
    if (!permission.granted) return;
    await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
    await recorder.prepareToRecordAsync();
    recorder.record();
  };

  const stopRecording = async () => {
    await recorder.stop();
    if (recorder.uri) setVoiceUri(keepFile(recorder.uri, 'voice_note.m4a'));
  };

  const complete = when && many && rain && sprayed;

  const send = async () => {
    if (!complete) return;
    setBusy(true);
    setError(null);
    const report = (await pendingReports()).find((r) => r.localId === localId);
    if (!report) {
      setBusy(false);
      return router.replace('/');
    }
    const answers: SymptomAnswers = {
      started: STARTED[when],
      share_affected: many,
      recent_weather: rain === 'yes' ? ['rainy'] : ['normal'],
      already_sprayed: sprayed === 'yes',
      notes: rain === 'unsure' ? 'Farmer not sure about recent rain.' : '',
    };
    const ready = { ...report, answers, voiceUri: voiceUri ?? undefined };
    await saveReport(ready);
    try {
      const caseId = await sendReport(ready);
      router.replace({ pathname: '/check/sent', params: caseId ? { caseId } : { localId } });
    } catch (e) {
      if (e instanceof ApiError && e.offline && (await phoneIsOffline())) {
        router.replace({ pathname: '/check/sent', params: { localId } }); // queued; sent when back online
      } else {
        // Online but it did not go through: say why and let the farmer press Send again.
        setError(`${t('check.sendFailed')} (${e instanceof Error ? e.message : String(e)})`);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen
      title={t('check.questionsTitle')}
      onBack={() => router.back()}
      backLabel={t('common.back')}
      footer={<Button label={t('check.sendReport')} icon="arrowRight" onPress={send} loading={busy} disabled={!complete || recorderState.isRecording} />}
    >
      <OptionSelector<When>
        question={t('check.qWhen')}
        value={when}
        onChange={setWhen}
        options={[
          { value: 'today', label: t('check.whenToday') },
          { value: 'week', label: t('check.whenWeek') },
          { value: 'longer', label: t('check.whenLonger') },
        ]}
      />
      <OptionSelector<Many>
        question={t('check.qHowMany')}
        value={many}
        onChange={setMany}
        options={[
          { value: 'few', label: t('check.manyFew') },
          { value: 'some', label: t('check.manyHalf') },
          { value: 'most', label: t('check.manyMost') },
        ]}
      />
      <OptionSelector<YesNoUnsure>
        question={t('check.qRain')}
        value={rain}
        onChange={setRain}
        options={[
          { value: 'yes', label: t('common.yes') },
          { value: 'no', label: t('common.no') },
          { value: 'unsure', label: t('common.notSure') },
        ]}
      />
      <OptionSelector<'yes' | 'no'>
        question={t('check.qSprayed')}
        value={sprayed}
        onChange={setSprayed}
        options={[
          { value: 'yes', label: t('common.yes') },
          { value: 'no', label: t('common.no') },
        ]}
      />

      <View style={styles.voice}>
        <Text color={colors.inkMuted}>{t('check.voiceNoteHint')}</Text>
        {voiceUri && !recorderState.isRecording ? (
          <Row style={{ justifyContent: 'space-between' }}>
            <Row>
              <Icon name="checkCircle" color={colors.verified} />
              <Text variant="bodyStrong" color={colors.verified}>
                {t('check.voiceSaved')}
              </Text>
            </Row>
            <Button label={t('check.deleteVoice')} variant="text" onPress={() => setVoiceUri(null)} />
          </Row>
        ) : recorderState.isRecording ? (
          <Button label={`${t('check.stopRecording')} · ${t('check.recording', { seconds })}`} icon="stop" variant="secondary" onPress={stopRecording} />
        ) : (
          <Button label={t('check.voiceNote')} icon="mic" variant="secondary" onPress={startRecording} />
        )}
      </View>
      {error ? (
        <Text variant="bodyStrong" color={colors.danger} accessibilityLiveRegion="polite">
          ⚠ {error}
        </Text>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  voice: { gap: space.sm, padding: space.lg, borderRadius: radius.lg, backgroundColor: colors.soilSoft },
});
