/**
 * Core building blocks: text, buttons, cards, screens. One primary action per screen;
 * every touch target at least 48 dp, primary buttons full width and 56 dp tall.
 */
import { ReactNode } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text as RNText,
  TextProps,
  TextStyle,
  View,
  ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { colors, radius, space, touch, type } from '../theme/tokens';
import Icon, { IconName } from './Icon';
import OfflineBanner from './OfflineBanner';

type Variant = keyof typeof type;

export function Text({ variant = 'body', color = colors.ink, style, ...props }: TextProps & { variant?: Variant; color?: string }) {
  return <RNText {...props} maxFontSizeMultiplier={1.6} style={[type[variant] as TextStyle, { color }, style]} />;
}

type ButtonProps = {
  label: string;
  onPress?: () => void;
  icon?: IconName;
  variant?: 'primary' | 'secondary' | 'text';
  disabled?: boolean;
  loading?: boolean;
  style?: ViewStyle;
  big?: boolean; // the giant "Check my tomatoes" button
};

export function Button({ label, onPress, icon, variant = 'primary', disabled, loading, style, big }: ButtonProps) {
  const inactive = disabled || loading;
  const palette = {
    primary: { bg: colors.leaf, pressed: colors.leafDark, fg: colors.inkOnDark, border: colors.leaf },
    secondary: { bg: colors.surface, pressed: colors.soilSoft, fg: colors.soil, border: colors.soil },
    text: { bg: 'transparent', pressed: colors.leafSoft, fg: colors.leaf, border: 'transparent' },
  }[variant];
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: !!inactive, busy: !!loading }}
      disabled={inactive}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        variant !== 'text' && styles.buttonBlock,
        big && styles.buttonBig,
        {
          backgroundColor: inactive && variant === 'primary' ? colors.disabled : pressed ? palette.pressed : palette.bg,
          borderColor: inactive && variant !== 'text' ? colors.disabled : palette.border,
        },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={variant === 'primary' ? colors.inkOnDark : palette.fg} />
      ) : (
        <View style={[styles.buttonContent, big && styles.buttonContentBig]}>
          {icon ? <Icon name={icon} size={big ? 44 : 24} color={inactive && variant !== 'primary' ? colors.disabled : palette.fg} /> : null}
          <Text
            variant={big ? 'h1' : 'bodyStrong'}
            color={inactive && variant !== 'primary' ? colors.disabled : palette.fg}
            style={{ textAlign: 'center' }}
          >
            {label}
          </Text>
        </View>
      )}
    </Pressable>
  );
}

export function Card({ children, style, tone }: { children: ReactNode; style?: ViewStyle; tone?: 'plain' | 'soft' | 'soil' }) {
  const background = tone === 'soft' ? colors.leafSoft : tone === 'soil' ? colors.soilSoft : colors.surface;
  return <View style={[styles.card, { backgroundColor: background }, style]}>{children}</View>;
}

/** A screen: safe area, optional title and back button, scrolling content, and a footer for the one primary action. */
export function Screen({
  title,
  onBack,
  backLabel,
  children,
  footer,
  scroll = true,
  step,
}: {
  title?: string;
  onBack?: () => void;
  backLabel?: string;
  children: ReactNode;
  footer?: ReactNode;
  scroll?: boolean;
  step?: string; // "Step 2 of 3"
}) {
  const Body = scroll ? ScrollView : View;
  return (
    <SafeAreaView style={styles.screen} edges={['top', 'left', 'right']}>
      <OfflineBanner />
      {title || onBack ? (
        <View style={styles.header}>
          {onBack ? (
            <Pressable accessibilityRole="button" accessibilityLabel={backLabel} onPress={onBack} style={styles.back}>
              <Icon name="arrowLeft" size={24} color={colors.leaf} />
              <Text variant="label" color={colors.leaf}>
                {backLabel}
              </Text>
            </Pressable>
          ) : null}
          {step ? (
            <Text variant="bodyStrong" color={colors.soil} style={styles.step}>
              {step}
            </Text>
          ) : null}
          {title ? (
            <Text variant="h1" accessibilityRole="header">
              {title}
            </Text>
          ) : null}
        </View>
      ) : null}
      <Body style={styles.body} contentContainerStyle={scroll ? styles.bodyContent : undefined} keyboardShouldPersistTaps="handled">
        {scroll ? children : <View style={[styles.bodyContent, { flex: 1 }]}>{children}</View>}
      </Body>
      {footer ? <View style={styles.footer}>{footer}</View> : null}
    </SafeAreaView>
  );
}

export function Gap({ size = space.lg }: { size?: number }) {
  return <View style={{ height: size }} />;
}

export function Row({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  return <View style={[{ flexDirection: 'row', alignItems: 'center', gap: space.sm }, style]}>{children}</View>;
}

/** A tappable list row with an icon and label (Profile and Settings). */
export function ListItem({ icon, label, detail, onPress }: { icon: IconName; label: string; detail?: string; onPress?: () => void }) {
  return (
    <Pressable
      accessibilityRole={onPress ? 'button' : undefined}
      onPress={onPress}
      style={({ pressed }) => [styles.listItem, pressed && onPress ? { backgroundColor: colors.leafSoft } : null]}
    >
      <Icon name={icon} color={colors.leaf} />
      <View style={{ flex: 1 }}>
        <Text variant="bodyStrong">{label}</Text>
        {detail ? <Text color={colors.inkMuted}>{detail}</Text> : null}
      </View>
      {onPress ? <Icon name="arrowRight" color={colors.inkMuted} size={20} /> : null}
    </Pressable>
  );
}

export function Loading({ label }: { label: string }) {
  return (
    <View style={styles.center} accessibilityLiveRegion="polite">
      <ActivityIndicator size="large" color={colors.leaf} />
      <Gap size={space.md} />
      <Text color={colors.inkMuted}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.cream },
  header: { paddingHorizontal: space.lg, paddingTop: space.sm, paddingBottom: space.md, gap: space.xs },
  back: { flexDirection: 'row', alignItems: 'center', gap: space.xs, minHeight: touch.min, alignSelf: 'flex-start', paddingRight: space.md },
  step: { textTransform: 'none' },
  body: { flex: 1 },
  bodyContent: { padding: space.lg, gap: space.lg },
  footer: { padding: space.lg, gap: space.sm, borderTopWidth: 1, borderTopColor: colors.border, backgroundColor: colors.cream },
  button: {
    minHeight: touch.min,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.lg,
    borderWidth: 2,
  },
  buttonBlock: { minHeight: touch.primary, alignSelf: 'stretch' },
  buttonBig: { minHeight: 140, borderRadius: radius.lg },
  buttonContent: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  buttonContentBig: { flexDirection: 'column', gap: space.md },
  card: { borderRadius: radius.lg, padding: space.lg, gap: space.md, borderWidth: 1, borderColor: colors.border },
  listItem: { flexDirection: 'row', alignItems: 'center', gap: space.md, minHeight: 64, paddingVertical: space.md, paddingHorizontal: space.lg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.xl },
});
