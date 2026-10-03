import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { FarmerWithPlant } from '../../components/Illustrations';
import { Button, Screen, Text } from '../../components/ui';
import { Language, useI18n } from '../../i18n';
import { colors, space } from '../../theme/tokens';

/** O1: choose a language. Shown in both languages at once so anyone can pick. */
export default function ChooseLanguage() {
  const { setLanguage, t } = useI18n();
  const choose = (language: Language) => {
    setLanguage(language);
    router.push('/onboarding/phone');
  };
  return (
    <Screen>
      <View style={styles.hero}>
        <FarmerWithPlant size={180} />
        <Text variant="display" color={colors.leaf}>
          AgriSense
        </Text>
        <Text variant="h2" style={styles.center}>
          Choose your language{'\n'}Chagua lugha yako
        </Text>
      </View>
      <View style={{ gap: space.md }}>
        <Button label={t('languages.en')} variant="secondary" onPress={() => choose('en')} />
        <Button label={t('languages.sw')} variant="secondary" onPress={() => choose('sw')} />
        <Button label={t('languages.ki')} variant="secondary" onPress={() => choose('ki')} />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  hero: { alignItems: 'center', gap: space.md, paddingVertical: space.lg },
  center: { textAlign: 'center' },
});
