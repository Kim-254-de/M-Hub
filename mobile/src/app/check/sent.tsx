import { router, useLocalSearchParams } from 'expo-router';
import { View } from 'react-native';

import { InfoCard, ProgressTracker } from '../../components/blocks';
import Icon from '../../components/Icon';
import { Button, Card, Screen, Text } from '../../components/ui';
import { useI18n } from '../../i18n';
import { useDiagnosis } from '../../lib/queries';
import { colors, space } from '../../theme/tokens';

/** C4: the report is sent (or saved to send later); what happens next and what to do meanwhile. */
export default function Sent() {
  const { t } = useI18n();
  const { caseId, localId } = useLocalSearchParams<{ caseId?: string; localId?: string }>();
  const queued = !caseId && !!localId;
  const diagnosis = useDiagnosis(caseId ?? '');
  const steps = diagnosis.data?.safe_actions ?? [];

  return (
    <Screen
      footer={
        <Button
          label={t('check.goToCase')}
          icon="arrowRight"
          onPress={() => (caseId ? router.replace(`/case/${caseId}`) : router.replace('/cases'))}
        />
      }
    >
      <View style={{ alignItems: 'center', gap: space.md, paddingTop: space.lg }}>
        <Icon name={queued ? 'offline' : 'checkCircle'} size={72} color={queued ? colors.warningIcon : colors.verified} strokeWidth={2.5} />
        <Text variant="h1" style={{ textAlign: 'center' }} accessibilityRole="header">
          {queued ? t('check.queuedTitle') : t('check.sentTitle')}
        </Text>
        <Text variant="bodyStrong" color={colors.inkMuted} style={{ textAlign: 'center' }}>
          {queued ? t('check.queuedBody') : t('check.sentBody')}
        </Text>
      </View>
      <Card>
        <ProgressTracker done={queued ? 0 : 1} />
      </Card>
      {steps.length ? (
        <View style={{ gap: space.sm }}>
          <Text variant="h2">{t('check.whatToDoNow')}</Text>
          {steps.map((step) => (
            <InfoCard key={step} icon="leaf" title={step} />
          ))}
        </View>
      ) : null}
    </Screen>
  );
}
