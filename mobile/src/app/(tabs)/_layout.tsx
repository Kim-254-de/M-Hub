import { Tabs } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import Icon, { IconName } from '../../components/Icon';
import { TextKey, useI18n } from '../../i18n';
import { Text } from '../../components/ui';
import { colors } from '../../theme/tokens';

/** Bottom navigation: exactly 4 tabs, each with an icon and a word. */
const TABS: Array<{ name: string; label: TextKey; icon: IconName }> = [
  { name: 'index', label: 'tabs.check', icon: 'camera' },
  { name: 'cases', label: 'tabs.cases', icon: 'cases' },
  { name: 'shop', label: 'tabs.shop', icon: 'shop' },
  { name: 'profile', label: 'tabs.profile', icon: 'person' },
];

export default function TabLayout() {
  const { t } = useI18n();
  const insets = useSafeAreaInsets();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        sceneStyle: { backgroundColor: colors.cream },
        tabBarActiveTintColor: colors.leaf,
        tabBarInactiveTintColor: colors.inkMuted,
        tabBarActiveBackgroundColor: colors.leafSoft,
        tabBarStyle: {
          height: 84 + insets.bottom,
          paddingBottom: insets.bottom,
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          borderTopWidth: 1,
        },
        tabBarItemStyle: { paddingTop: 8, paddingBottom: 10 },
        tabBarAllowFontScaling: true,
      }}
    >
      {TABS.map((tab) => (
        <Tabs.Screen
          key={tab.name}
          name={tab.name}
          options={{
            title: t(tab.label),
            tabBarAccessibilityLabel: t(tab.label),
            // Two lines allowed: "Angalia Shamba" does not fit on one at 360 dp.
            tabBarLabel: ({ color }) => (
              <Text variant="label" color={String(color)} numberOfLines={2} style={{ textAlign: 'center' }}>
                {t(tab.label)}
              </Text>
            ),
            tabBarIcon: ({ color, focused }) => <Icon name={tab.icon} color={color} size={26} strokeWidth={focused ? 2.5 : 2} />,
          }}
        />
      ))}
    </Tabs>
  );
}
