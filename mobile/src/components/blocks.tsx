/**
 * Components from the design brief (section 7). Meaning is never carried by colour alone:
 * each state has an icon and a word as well.
 */
import { ReactNode } from 'react';
import { Image, Pressable, StyleSheet, View } from 'react-native';

import type { Case, CaseStatus, StoreOffer, VerificationResult } from '../api/types';
import { formatDate, TextKey, useI18n } from '../i18n';
import { colors, radius, space, touch } from '../theme/tokens';
import Icon, { IconName } from './Icon';
import { Button, Card, Gap, Row, Text } from './ui';

// --- Status chip ------------------------------------------------------------------------------

type ChipKind = 'waiting' | 'confirmed' | 'treatment' | 'bought' | 'verified' | 'flagged' | 'second' | 'unsure' | 'draft' | 'expired';

const CHIPS: Record<ChipKind, { label: TextKey; icon: IconName; fg: string; bg: string }> = {
  waiting: { label: 'status.waiting', icon: 'clock', fg: colors.warning, bg: colors.warningSoft },
  second: { label: 'status.secondOpinion', icon: 'clock', fg: colors.warning, bg: colors.warningSoft },
  draft: { label: 'status.draft', icon: 'offline', fg: colors.warning, bg: colors.warningSoft },
  confirmed: { label: 'status.confirmed', icon: 'checkCircle', fg: colors.leaf, bg: colors.leafSoft },
  treatment: { label: 'status.treatmentReady', icon: 'leaf', fg: colors.leaf, bg: colors.leafSoft },
  bought: { label: 'status.bought', icon: 'shop', fg: colors.soil, bg: colors.soilSoft },
  verified: { label: 'status.verified', icon: 'shield', fg: colors.verified, bg: colors.verifiedSoft },
  flagged: { label: 'status.flagged', icon: 'warning', fg: colors.danger, bg: colors.dangerSoft },
  unsure: { label: 'status.notSure', icon: 'help', fg: colors.info, bg: colors.infoSoft },
  expired: { label: 'status.expired', icon: 'clock', fg: colors.inkMuted, bg: colors.soilSoft },
};

export function chipFor(status: CaseStatus): ChipKind {
  switch (status) {
    case 'DRAFT':
      return 'draft';
    case 'REPORTED':
    case 'DIAGNOSING':
      return 'waiting';
    case 'SECOND_OPINION':
      return 'second';
    case 'DIAGNOSED':
      return 'confirmed';
    case 'PRESCRIBED':
      return 'treatment';
    case 'PURCHASED':
      return 'bought';
    case 'VERIFIED':
      return 'verified';
    case 'FLAGGED':
      return 'flagged';
    case 'UNKNOWN':
      return 'unsure';
    case 'EXPIRED':
      return 'expired';
  }
}

export function StatusChip({ kind }: { kind: ChipKind }) {
  const { t } = useI18n();
  const chip = CHIPS[kind];
  return (
    <View style={[styles.chip, { backgroundColor: chip.bg, borderColor: chip.fg }]}>
      <Icon name={chip.icon} size={18} color={chip.fg} />
      <Text variant="label" color={chip.fg}>
        {t(chip.label)}
      </Text>
    </View>
  );
}

// --- Progress tracker: Sent → Checking → Confirmed → Treatment ------------------------------------

export function trackerStep(status: CaseStatus): number {
  // Number of completed steps (0-4).
  if (status === 'DRAFT') return 0;
  if (['REPORTED', 'DIAGNOSING', 'SECOND_OPINION', 'UNKNOWN'].includes(status)) return 1;
  if (status === 'DIAGNOSED') return 3;
  return 4; // prescribed and beyond
}

export function ProgressTracker({ done }: { done: number }) {
  const { t } = useI18n();
  const steps: TextKey[] = ['tracker.sent', 'tracker.checking', 'tracker.confirmed', 'tracker.treatment'];
  // Vertical, so long Kiswahili words and large phone font sizes always fit.
  return (
    <View accessibilityRole="progressbar" accessibilityValue={{ min: 0, max: 4, now: done }}>
      {steps.map((key, index) => {
        const state = index < done ? 'done' : index === done ? 'current' : 'todo';
        return (
          <View key={key} style={styles.trackerRow}>
            <View style={styles.trackerRail}>
              <View
                style={[
                  styles.trackerDot,
                  state === 'done' && { backgroundColor: colors.leaf, borderColor: colors.leaf },
                  state === 'current' && { borderColor: colors.leaf, backgroundColor: colors.leafSoft },
                ]}
              >
                {state === 'done' ? <Icon name="check" size={18} color={colors.inkOnDark} strokeWidth={3} /> : null}
                {state === 'current' ? <Icon name="clock" size={18} color={colors.leaf} /> : null}
              </View>
              {index < steps.length - 1 ? (
                <View style={[styles.trackerLine, { backgroundColor: index < done ? colors.leaf : colors.border }]} />
              ) : null}
            </View>
            <Text
              variant={state === 'current' ? 'bodyStrong' : 'body'}
              color={state === 'todo' ? colors.inkMuted : colors.ink}
              style={{ paddingTop: 4, flex: 1 }}
            >
              {t(key)}
            </Text>
          </View>
        );
      })}
    </View>
  );
}

// --- Case card --------------------------------------------------------------------------------------

export function CaseCard({ item, onPress }: { item: Case; onPress: () => void }) {
  const { t, language } = useI18n();
  const thumb = item.photos.find((p) => p.type === 'leaf') ?? item.photos[0];
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => [styles.caseCard, pressed && { backgroundColor: colors.leafSoft }]}>
      {thumb ? (
        <Image source={{ uri: thumb.image }} style={styles.thumb} accessibilityIgnoresInvertColors />
      ) : (
        <View style={[styles.thumb, styles.thumbEmpty]}>
          <Icon name="leaf" color={colors.leaf} />
        </View>
      )}
      <View style={{ flex: 1, gap: space.xs }}>
        <Text variant="bodyStrong">{item.disease ?? t('status.waitingAgrovet')}</Text>
        <Text color={colors.inkMuted}>{t('cases.reported', { date: formatDate(item.submitted_at ?? item.created_at, language) })}</Text>
        <StatusChip kind={chipFor(item.status)} />
      </View>
      <Icon name="arrowRight" color={colors.inkMuted} />
    </Pressable>
  );
}

// --- Store card -------------------------------------------------------------------------------------

export function StoreCard({ offer, onPress }: { offer: StoreOffer; onPress: () => void }) {
  const { t } = useI18n();
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => [styles.storeCard, pressed && { backgroundColor: colors.leafSoft }]}>
      <View style={{ flex: 1, gap: space.xs }}>
        <Text variant="bodyStrong">{offer.agrovet_name}</Text>
        <Text color={colors.inkMuted}>{offer.product.name}</Text>
        <Row>
          <View style={[styles.chip, { backgroundColor: colors.verifiedSoft, borderColor: colors.verified }]}>
            <Icon name="shield" size={18} color={colors.verified} />
            <Text variant="label" color={colors.verified}>
              {t('shop.verified')}
            </Text>
          </View>
          {offer.distance_km != null ? (
            <Row style={{ gap: space.xs }}>
              <Icon name="pin" size={18} color={colors.inkMuted} />
              <Text color={colors.inkMuted}>{t('common.km', { km: offer.distance_km.toFixed(1) })}</Text>
            </Row>
          ) : null}
        </Row>
      </View>
      <Text variant="h2" color={colors.soil}>
        {t('common.kes', { amount: offer.price_kes.toLocaleString() })}
      </Text>
    </Pressable>
  );
}

// --- Alert card (nearby outbreak) --------------------------------------------------------------------

export function AlertCard({ message }: { message: string }) {
  return (
    <View style={styles.alert} accessibilityRole="alert">
      <Icon name="warning" color={colors.warningIcon} size={28} />
      <Text variant="bodyStrong" color={colors.warning} style={{ flex: 1 }}>
        {message}
      </Text>
    </View>
  );
}

// --- Evidence block ---------------------------------------------------------------------------------

export function EvidenceBlock({ icon, title, value, tone = 'plain' }: { icon: IconName; title: string; value: string; tone?: 'plain' | 'verified' }) {
  const verified = tone === 'verified';
  return (
    <View style={[styles.evidence, verified && { backgroundColor: colors.verifiedSoft, borderColor: colors.verified }]}>
      <Icon name={icon} color={verified ? colors.verified : colors.soil} />
      <View style={{ flex: 1 }}>
        <Text variant="label" color={verified ? colors.verified : colors.inkMuted}>
          {title}
        </Text>
        <Text variant="bodyStrong" color={verified ? colors.verified : colors.ink}>
          {value}
        </Text>
      </View>
    </View>
  );
}

// --- Verification result banner ----------------------------------------------------------------------

const BANNERS: Record<'verified' | 'warning' | 'danger', { icon: IconName; fg: string; bg: string }> = {
  verified: { icon: 'checkCircle', fg: colors.verified, bg: colors.verifiedSoft },
  warning: { icon: 'warning', fg: colors.warning, bg: colors.warningSoft },
  danger: { icon: 'warning', fg: colors.danger, bg: colors.dangerSoft },
};

export function bannerFor(result: VerificationResult): 'verified' | 'warning' | 'danger' {
  if (result === 'verified') return 'verified';
  if (result === 'not_registered' || result === 'mismatch') return 'danger';
  return 'warning';
}

export function VerificationBanner({ tone, title, body }: { tone: 'verified' | 'warning' | 'danger'; title: string; body?: string }) {
  const banner = BANNERS[tone];
  return (
    <View
      style={[styles.banner, { backgroundColor: banner.bg, borderColor: banner.fg, borderWidth: tone === 'danger' ? 3 : 2 }]}
      accessibilityRole="alert"
    >
      <Icon name={banner.icon} size={40} color={banner.fg} strokeWidth={2.5} />
      <Text variant="h2" color={banner.fg} style={{ textAlign: 'center' }}>
        {tone === 'verified' ? '✓ ' : '⚠ '}
        {title}
      </Text>
      {body ? (
        <Text variant="bodyStrong" color={banner.fg} style={{ textAlign: 'center' }}>
          {body}
        </Text>
      ) : null}
    </View>
  );
}

// --- Photo capture step header ---------------------------------------------------------------------

export function PhotoStepHeader({ step, total, title, hint, example }: { step: number; total: number; title: string; hint: string; example: ReactNode }) {
  const { t } = useI18n();
  return (
    <View style={{ gap: space.sm }}>
      <Text variant="bodyStrong" color={colors.soil}>
        {t('common.stepOf', { step, total })}
      </Text>
      <Row style={{ alignItems: 'flex-start', gap: space.md }}>
        <View style={styles.example}>
          {example}
          <Text variant="label" color={colors.inkMuted}>
            {t('check.example')}
          </Text>
        </View>
        <View style={{ flex: 1, gap: space.xs }}>
          <Text variant="h2">{title}</Text>
          <Text color={colors.inkMuted}>{hint}</Text>
        </View>
      </Row>
    </View>
  );
}

// --- Large option selector (single choice) ---------------------------------------------------------------

export function OptionSelector<T extends string>({
  question,
  options,
  value,
  onChange,
}: {
  question: string;
  options: Array<{ value: T; label: string }>;
  value: T | null;
  onChange: (value: T) => void;
}) {
  return (
    <View style={{ gap: space.sm }} accessibilityRole="radiogroup" accessibilityLabel={question}>
      <Text variant="h2">{question}</Text>
      <View style={styles.options}>
        {options.map((option) => {
          const selected = option.value === value;
          return (
            <Pressable
              key={option.value}
              accessibilityRole="radio"
              accessibilityState={{ selected }}
              onPress={() => onChange(option.value)}
              style={[styles.option, selected && styles.optionSelected]}
            >
              <View style={[styles.radio, selected && styles.radioSelected]}>
                {selected ? <Icon name="check" size={18} color={colors.inkOnDark} strokeWidth={3} /> : null}
              </View>
              <Text variant="bodyStrong" color={selected ? colors.leaf : colors.ink} style={{ flexShrink: 1 }}>
                {option.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

// --- Empty, error and waiting states ---------------------------------------------------------------------

export function EmptyState({ art, title, body, action }: { art?: ReactNode; title: string; body: string; action?: ReactNode }) {
  return (
    <View style={styles.state}>
      {art}
      <Text variant="h2" style={{ textAlign: 'center' }}>
        {title}
      </Text>
      <Text color={colors.inkMuted} style={{ textAlign: 'center' }}>
        {body}
      </Text>
      {action}
    </View>
  );
}

export function ErrorState({ onRetry, message }: { onRetry?: () => void; message?: string }) {
  const { t } = useI18n();
  return (
    <View style={styles.state} accessibilityRole="alert">
      <Icon name="warning" size={48} color={colors.warningIcon} />
      <Text variant="h2" style={{ textAlign: 'center' }}>
        {t('common.errorTitle')}
      </Text>
      <Text color={colors.inkMuted} style={{ textAlign: 'center' }}>
        {message ?? t('common.errorBody')}
      </Text>
      {onRetry ? (
        <>
          <Gap size={space.sm} />
          <Button label={t('common.retry')} icon="refresh" variant="secondary" onPress={onRetry} />
        </>
      ) : null}
    </View>
  );
}

export function InfoCard({ icon, title, body, tone = 'plain' }: { icon: IconName; title: string; body?: string; tone?: 'plain' | 'soft' | 'soil' }) {
  return (
    <Card tone={tone}>
      <Row style={{ alignItems: 'flex-start' }}>
        <Icon name={icon} color={colors.leaf} size={28} />
        <View style={{ flex: 1, gap: space.xs }}>
          <Text variant="bodyStrong">{title}</Text>
          {body ? <Text color={colors.inkMuted}>{body}</Text> : null}
        </View>
      </Row>
    </Card>
  );
}

const styles = StyleSheet.create({
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    alignSelf: 'flex-start',
    paddingHorizontal: space.sm,
    paddingVertical: 4,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  trackerRow: { flexDirection: 'row', gap: space.md, minHeight: 44 },
  trackerRail: { alignItems: 'center', width: 32 },
  trackerLine: { width: 3, flex: 1, minHeight: 12 },
  trackerDot: {
    width: 32,
    height: 32,
    borderRadius: 16,
    borderWidth: 2,
    borderColor: colors.borderStrong,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  caseCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    padding: space.md,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    minHeight: 96,
  },
  thumb: { width: 72, height: 72, borderRadius: radius.md, backgroundColor: colors.leafSoft },
  thumbEmpty: { alignItems: 'center', justifyContent: 'center' },
  storeCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    padding: space.lg,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    minHeight: touch.primary + 24,
  },
  alert: {
    flexDirection: 'row',
    gap: space.md,
    alignItems: 'flex-start',
    padding: space.lg,
    borderRadius: radius.lg,
    backgroundColor: colors.warningSoft,
    borderWidth: 2,
    borderColor: colors.warningIcon,
  },
  evidence: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  banner: { alignItems: 'center', gap: space.sm, padding: space.xl, borderRadius: radius.lg },
  example: { alignItems: 'center', gap: 4 },
  options: { gap: space.sm },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    minHeight: touch.primary,
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  optionSelected: { borderColor: colors.leaf, backgroundColor: colors.leafSoft },
  radio: {
    width: 28,
    height: 28,
    borderRadius: 14,
    borderWidth: 2,
    borderColor: colors.borderStrong,
    alignItems: 'center',
    justifyContent: 'center',
  },
  radioSelected: { backgroundColor: colors.leaf, borderColor: colors.leaf },
  state: { alignItems: 'center', gap: space.md, padding: space.xl },
});
