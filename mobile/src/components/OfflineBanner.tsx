import { StyleSheet, View } from 'react-native';

import { useI18n } from '../i18n';
import { useOffline } from '../lib/network';
import { colors, space } from '../theme/tokens';
import Icon from './Icon';
import { Text } from './ui';

/** Shown at the top of every screen while there is no connection. */
export default function OfflineBanner() {
  const offline = useOffline();
  const { t } = useI18n();
  if (!offline) return null;
  return (
    <View style={styles.banner} accessibilityRole="alert" accessibilityLiveRegion="polite">
      <Icon name="offline" color={colors.warning} />
      <Text variant="bodyStrong" color={colors.warning} style={{ flex: 1 }}>
        {t('common.offline')}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    backgroundColor: colors.warningSoft,
    borderBottomWidth: 1,
    borderBottomColor: colors.warningIcon,
  },
});
