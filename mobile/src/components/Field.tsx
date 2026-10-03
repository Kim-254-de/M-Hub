import { forwardRef } from 'react';
import { StyleSheet, TextInput, TextInputProps, View } from 'react-native';

import { colors, radius, space, touch } from '../theme/tokens';
import Icon from './Icon';
import { Text } from './ui';

type Props = TextInputProps & { label: string; hint?: string; error?: string | null };

/** A labelled text field with large text; the error is shown with an icon, not only in red. */
const Field = forwardRef<TextInput, Props>(function Field({ label, hint, error, style, ...props }, ref) {
  return (
    <View style={{ gap: space.xs }}>
      <Text variant="bodyStrong">{label}</Text>
      {hint ? <Text color={colors.inkMuted}>{hint}</Text> : null}
      <TextInput
        ref={ref}
        accessibilityLabel={label}
        placeholderTextColor={colors.inkMuted}
        maxFontSizeMultiplier={1.6}
        style={[styles.input, error ? { borderColor: colors.danger } : null, style]}
        {...props}
      />
      {error ? (
        <View style={styles.error} accessibilityLiveRegion="polite">
          <Icon name="warning" size={20} color={colors.danger} />
          <Text variant="bodyStrong" color={colors.danger} style={{ flex: 1 }}>
            {error}
          </Text>
        </View>
      ) : null}
    </View>
  );
});

export default Field;

const styles = StyleSheet.create({
  input: {
    minHeight: touch.primary,
    borderWidth: 2,
    borderColor: colors.borderStrong,
    borderRadius: radius.md,
    paddingHorizontal: space.lg,
    fontSize: 20,
    fontFamily: 'NotoSans_600SemiBold',
    color: colors.ink,
    backgroundColor: colors.surface,
  },
  error: { flexDirection: 'row', gap: space.xs, alignItems: 'center' },
});
