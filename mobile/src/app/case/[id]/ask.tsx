import { useMutation } from '@tanstack/react-query';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { askAdviser } from '../../../api/endpoints';
import { InfoCard } from '../../../components/blocks';
import Field from '../../../components/Field';
import Icon from '../../../components/Icon';
import { Button, Card, Row, Screen, Text } from '../../../components/ui';
import { useI18n } from '../../../i18n';
import { colors, space } from '../../../theme/tokens';

type Exchange = { question: string; answer: string; blocked: boolean };

/** Ask the adviser about this case. Answers are in the farmer's language; products and doses come from the card. */
export default function Ask() {
  const { t } = useI18n();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [question, setQuestion] = useState('');
  const [history, setHistory] = useState<Exchange[]>([]);
  const ask = useMutation({
    mutationFn: (text: string) => askAdviser(id, text),
    onSuccess: (answer, text) => {
      setHistory((current) => [...current, { question: text, answer: answer.answer, blocked: answer.blocked }]);
      setQuestion('');
    },
  });

  return (
    <Screen
      title={t('ask.title')}
      onBack={() => router.back()}
      backLabel={t('common.back')}
      footer={<Button label={t('ask.send')} icon="question" onPress={() => ask.mutate(question.trim())} loading={ask.isPending} disabled={question.trim().length < 3} />}
    >
      <Text color={colors.inkMuted}>{t('ask.hint')}</Text>
      {history.map((exchange, index) => (
        <View key={index} style={{ gap: space.sm }}>
          <Card tone="soil">
            <Row style={{ alignItems: 'flex-start' }}>
              <Icon name="person" color={colors.soil} />
              <Text style={{ flex: 1 }}>{exchange.question}</Text>
            </Row>
          </Card>
          <Card>
            <Row style={{ alignItems: 'flex-start' }}>
              <Icon name="leaf" color={colors.leaf} />
              <Text variant="bodyStrong" style={{ flex: 1 }}>
                {exchange.answer}
              </Text>
            </Row>
          </Card>
        </View>
      ))}
      {ask.isError ? <InfoCard icon="offline" tone="soil" title={t('ask.unavailable')} /> : null}
      <Field label={t('ask.yourQuestion')} placeholder={t('ask.placeholder')} value={question} onChangeText={setQuestion} multiline maxLength={1000} style={{ minHeight: 96, textAlignVertical: 'top', paddingTop: space.md }} />
      <InfoCard icon="shield" title={t('ask.safetyNote')} />
    </Screen>
  );
}
