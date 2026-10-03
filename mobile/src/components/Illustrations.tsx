/**
 * Friendly line illustrations (no photos, so the app stays light on data). Drawn in the brand
 * colours; decorative, so hidden from screen readers.
 */
import Svg, { Circle, Ellipse, G, Path, Rect } from 'react-native-svg';

import { colors } from '../theme/tokens';

const line = { stroke: colors.ink, strokeWidth: 2.5, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, fill: 'none' };
const hidden = { accessibilityElementsHidden: true, importantForAccessibility: 'no-hide-descendants' as const };

/** A farmer in a headscarf beside a staked tomato plant. */
export function FarmerWithPlant({ size = 180 }: { size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 200 200" {...hidden}>
      <Ellipse cx="100" cy="186" rx="86" ry="8" fill={colors.soilSoft} />
      {/* farmer */}
      <G>
        <Path d="M52 70c0-14 10-24 22-24s22 10 22 24" fill={colors.soil} stroke={colors.ink} strokeWidth={2.5} />
        <Circle cx="74" cy="78" r="16" fill="#8D5A3B" stroke={colors.ink} strokeWidth={2.5} />
        <Path {...line} d="M68 80c2 3 10 3 12 0" />
        <Path d="M50 186l4-62c1-14 9-22 20-22s19 8 20 22l4 62z" fill={colors.leaf} stroke={colors.ink} strokeWidth={2.5} />
        <Path {...line} d="M60 120l-14 34M88 120l18 26" />
        <Circle cx="108" cy="148" r="6" fill={colors.tomato} stroke={colors.ink} strokeWidth={2} />
      </G>
      {/* tomato plant */}
      <G>
        <Path {...line} d="M150 186V62" stroke={colors.soil} />
        <Path {...line} d="M138 186V96c0-10 6-18 12-22" />
        <Path d="M138 110c-14-2-22 6-24 14 12 2 20-4 24-14zM150 92c14-4 22 2 26 10-12 4-22 0-26-10zM142 140c-14 0-20 8-22 16 12 0 20-6 22-16zM150 124c12-6 22-2 26 6-12 6-22 2-26-6z" fill={colors.leafSoft} stroke={colors.leaf} strokeWidth={2.5} />
        <Circle cx="132" cy="122" r="7" fill={colors.tomato} stroke={colors.ink} strokeWidth={2} />
        <Circle cx="158" cy="108" r="6" fill={colors.tomato} stroke={colors.ink} strokeWidth={2} />
        <Circle cx="148" cy="152" r="7" fill={colors.tomato} stroke={colors.ink} strokeWidth={2} />
      </G>
    </Svg>
  );
}

/** Example for step 1: one leaf with dark blight patches, filling the frame. */
export function ExampleLeaf({ size = 88 }: { size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 88 88" {...hidden}>
      <Rect x="1" y="1" width="86" height="86" rx="12" fill={colors.cream} stroke={colors.border} strokeWidth={2} />
      <Path d="M14 74C14 40 34 18 74 14c0 38-22 60-60 60z" fill={colors.leafSoft} stroke={colors.leaf} strokeWidth={2.5} />
      <Path d="M14 74L58 30" stroke={colors.leaf} strokeWidth={2} />
      <Ellipse cx="42" cy="50" rx="8" ry="6" fill="#5B4636" />
      <Ellipse cx="56" cy="34" rx="5" ry="4" fill="#5B4636" />
      <Ellipse cx="30" cy="62" rx="4" ry="3" fill="#5B4636" />
    </Svg>
  );
}

/** Example for step 2: the whole plant, top to bottom. */
export function ExamplePlant({ size = 88 }: { size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 88 88" {...hidden}>
      <Rect x="1" y="1" width="86" height="86" rx="12" fill={colors.cream} stroke={colors.border} strokeWidth={2} />
      <Path d="M44 80V14" stroke={colors.leaf} strokeWidth={3} strokeLinecap="round" />
      <Path d="M44 30c-12-4-20 2-22 8 10 2 18-1 22-8zM44 44c12-6 20-2 24 4-10 4-18 2-24-4zM44 58c-12-2-20 4-22 10 10 0 18-4 22-10z" fill={colors.leafSoft} stroke={colors.leaf} strokeWidth={2} />
      <Circle cx="30" cy="48" r="4" fill={colors.tomato} />
      <Circle cx="58" cy="62" r="4" fill={colors.tomato} />
      <Path d="M20 80h48" stroke={colors.soil} strokeWidth={3} strokeLinecap="round" />
    </Svg>
  );
}

/** Example for step 3: a stem with a brown lesion and a spotted tomato. */
export function ExampleStemFruit({ size = 88 }: { size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 88 88" {...hidden}>
      <Rect x="1" y="1" width="86" height="86" rx="12" fill={colors.cream} stroke={colors.border} strokeWidth={2} />
      <Path d="M28 84V6" stroke={colors.leaf} strokeWidth={6} strokeLinecap="round" />
      <Rect x="24" y="30" width="8" height="16" rx="3" fill="#5B4636" />
      <Path d="M28 50c10 0 16 4 18 10" stroke={colors.leaf} strokeWidth={3} fill="none" />
      <Circle cx="56" cy="64" r="16" fill={colors.tomato} stroke={colors.ink} strokeWidth={2} />
      <Ellipse cx="52" cy="60" rx="6" ry="5" fill="#5B4636" />
    </Svg>
  );
}

/** Example for the label check: a product pack with the PCPB number highlighted. */
export function ExampleLabel({ size = 88 }: { size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 88 88" {...hidden}>
      <Rect x="1" y="1" width="86" height="86" rx="12" fill={colors.cream} stroke={colors.border} strokeWidth={2} />
      <Path d="M22 14h44l4 10v54H18V24z" fill={colors.surface} stroke={colors.ink} strokeWidth={2.5} strokeLinejoin="round" />
      <Rect x="26" y="30" width="36" height="8" rx="2" fill={colors.leafSoft} />
      <Rect x="26" y="56" width="36" height="12" rx="3" fill={colors.warningSoft} stroke={colors.warningIcon} strokeWidth={2} />
      <Path d="M30 62h28" stroke={colors.ink} strokeWidth={2} />
    </Svg>
  );
}

/** Empty "My Cases": a clipboard and a seedling. */
export function EmptyCases({ size = 140 }: { size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 140 140" {...hidden}>
      <Ellipse cx="70" cy="128" rx="52" ry="6" fill={colors.soilSoft} />
      <Rect x="34" y="20" width="56" height="76" rx="8" fill={colors.surface} stroke={colors.ink} strokeWidth={2.5} />
      <Rect x="50" y="14" width="24" height="12" rx="4" fill={colors.soil} />
      <Path {...line} d="M44 44h36M44 58h36M44 72h22" />
      <Path d="M102 124v-26" stroke={colors.leaf} strokeWidth={3} strokeLinecap="round" />
      <Path d="M102 106c-10-2-16 2-18 8 8 2 14-1 18-8zM102 100c8-6 16-4 20 0-8 6-16 4-20 0z" fill={colors.leafSoft} stroke={colors.leaf} strokeWidth={2} />
    </Svg>
  );
}

/** Points earned: a small star badge with sparkles. */
export function PointsBadge({ size = 120 }: { size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 120 120" {...hidden}>
      <Circle cx="60" cy="60" r="40" fill={colors.leafSoft} stroke={colors.leaf} strokeWidth={3} />
      <Path d="M60 36l7 15 16 2-12 11 3 16-14-8-14 8 3-16-12-11 16-2z" fill="#F2B632" stroke={colors.ink} strokeWidth={2} strokeLinejoin="round" />
      <Path d="M18 30l4 4M102 30l-4 4M14 70h6M100 70h6" stroke={colors.tomato} strokeWidth={3} strokeLinecap="round" />
    </Svg>
  );
}
