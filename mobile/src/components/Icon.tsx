/**
 * Simple line icons (24 x 24, 2 px stroke). Always shown with a text label next to or under them.
 */
import type { ReactElement } from 'react';
import type { ColorValue } from 'react-native';
import Svg, { Circle, Path, Rect } from 'react-native-svg';

import { colors } from '../theme/tokens';

export type IconName =
  | 'camera'
  | 'cases'
  | 'shop'
  | 'person'
  | 'check'
  | 'checkCircle'
  | 'warning'
  | 'clock'
  | 'leaf'
  | 'pin'
  | 'phone'
  | 'copy'
  | 'mic'
  | 'stop'
  | 'play'
  | 'arrowRight'
  | 'arrowLeft'
  | 'close'
  | 'refresh'
  | 'offline'
  | 'star'
  | 'globe'
  | 'bell'
  | 'chat'
  | 'help'
  | 'logout'
  | 'gloves'
  | 'mask'
  | 'boots'
  | 'calendar'
  | 'question'
  | 'shield'
  | 'tag'
  | 'directions'
  | 'spray'
  | 'edit'
  | 'image';

type Props = { name: IconName; size?: number; color?: ColorValue; strokeWidth?: number };

export default function Icon({ name, size = 24, color = colors.ink, strokeWidth = 2 }: Props) {
  const stroke = { stroke: color, strokeWidth, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, fill: 'none' };
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" accessibilityElementsHidden importantForAccessibility="no">
      {PATHS[name](stroke)}
    </Svg>
  );
}

type Stroke = { stroke: ColorValue; strokeWidth: number; strokeLinecap: 'round'; strokeLinejoin: 'round'; fill: string };

const PATHS: Record<IconName, (s: Stroke) => ReactElement> = {
  camera: (s) => (
    <>
      <Path {...s} d="M4 8h3l2-3h6l2 3h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z" />
      <Circle {...s} cx="12" cy="13" r="3.5" />
    </>
  ),
  cases: (s) => (
    <>
      <Rect {...s} x="5" y="4" width="14" height="17" rx="2" />
      <Path {...s} d="M9 4V3h6v1M8.5 10h7M8.5 14h7M8.5 18h4" />
    </>
  ),
  shop: (s) => (
    <>
      <Path {...s} d="M3 9l2-5h14l2 5M3 9h18M3 9a3 3 0 0 0 6 0a3 3 0 0 0 6 0a3 3 0 0 0 6 0" />
      <Path {...s} d="M5 11v9h14v-9M10 20v-5h4v5" />
    </>
  ),
  person: (s) => (
    <>
      <Circle {...s} cx="12" cy="8" r="4" />
      <Path {...s} d="M4 21c1-4 4-6 8-6s7 2 8 6" />
    </>
  ),
  check: (s) => <Path {...s} d="M5 12.5l4.5 4.5L19 7.5" />,
  checkCircle: (s) => (
    <>
      <Circle {...s} cx="12" cy="12" r="9" />
      <Path {...s} d="M8 12.5l3 3 5-6" />
    </>
  ),
  warning: (s) => (
    <>
      <Path {...s} d="M12 3l10 18H2L12 3z" />
      <Path {...s} d="M12 10v4.5M12 17.5v.5" />
    </>
  ),
  clock: (s) => (
    <>
      <Circle {...s} cx="12" cy="12" r="9" />
      <Path {...s} d="M12 7v5l3 2" />
    </>
  ),
  leaf: (s) => (
    <>
      <Path {...s} d="M5 19C5 10 10 5 20 4c0 10-5 15-14 15" />
      <Path {...s} d="M5 19l8-8" />
    </>
  ),
  pin: (s) => (
    <>
      <Path {...s} d="M12 21s-7-6.5-7-12a7 7 0 0 1 14 0c0 5.5-7 12-7 12z" />
      <Circle {...s} cx="12" cy="9" r="2.5" />
    </>
  ),
  phone: (s) => (
    <>
      <Rect {...s} x="7" y="2.5" width="10" height="19" rx="2" />
      <Path {...s} d="M11 18.5h2" />
    </>
  ),
  copy: (s) => (
    <>
      <Rect {...s} x="8" y="8" width="12" height="12" rx="2" />
      <Path {...s} d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3" />
    </>
  ),
  mic: (s) => (
    <>
      <Rect {...s} x="9" y="3" width="6" height="11" rx="3" />
      <Path {...s} d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M9 21h6" />
    </>
  ),
  stop: (s) => <Rect {...s} x="6" y="6" width="12" height="12" rx="1.5" />,
  play: (s) => <Path {...s} d="M8 5l11 7-11 7V5z" />,
  arrowRight: (s) => <Path {...s} d="M5 12h14M13 6l6 6-6 6" />,
  arrowLeft: (s) => <Path {...s} d="M19 12H5M11 6l-6 6 6 6" />,
  close: (s) => <Path {...s} d="M6 6l12 12M18 6L6 18" />,
  refresh: (s) => <Path {...s} d="M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6" />,
  offline: (s) => (
    <>
      <Path {...s} d="M2 8.5a15 15 0 0 1 5-3M9.5 4.6A15 15 0 0 1 22 8.5M5 12a10 10 0 0 1 4-2.3M14 9.8a10 10 0 0 1 5 2.2M8.5 15.5a5 5 0 0 1 7 0" />
      <Path {...s} d="M12 19.5v.5M3 3l18 18" />
    </>
  ),
  star: (s) => <Path {...s} d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9L12 3z" />,
  globe: (s) => (
    <>
      <Circle {...s} cx="12" cy="12" r="9" />
      <Path {...s} d="M3 12h18M12 3c2.5 2.5 3.5 5.5 3.5 9s-1 6.5-3.5 9c-2.5-2.5-3.5-5.5-3.5-9s1-6.5 3.5-9z" />
    </>
  ),
  bell: (s) => (
    <>
      <Path {...s} d="M6 17V11a6 6 0 0 1 12 0v6l2 2H4l2-2z" />
      <Path {...s} d="M10 21h4" />
    </>
  ),
  chat: (s) => <Path {...s} d="M4 5h16v11H9l-5 4V5z" />,
  help: (s) => (
    <>
      <Circle {...s} cx="12" cy="12" r="9" />
      <Path {...s} d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.5v.7M12 17v.5" />
    </>
  ),
  logout: (s) => <Path {...s} d="M10 4H5v16h5M15 8l4 4-4 4M19 12H9" />,
  gloves: (s) => (
    <Path {...s} d="M8 21v-5l-3-4.5a1.5 1.5 0 0 1 2.5-1.6L9 12V5a1.5 1.5 0 0 1 3 0v5V4a1.5 1.5 0 0 1 3 0v6V6a1.5 1.5 0 0 1 3 0v8c0 3-1.5 5-3 7H8z" />
  ),
  mask: (s) => (
    <>
      <Path {...s} d="M5 9c3-2 11-2 14 0v4c0 4-3.5 6-7 6s-7-2-7-6V9z" />
      <Path {...s} d="M5 10H3v2a3 3 0 0 0 2.5 3M19 10h2v2a3 3 0 0 1-2.5 3M9 12h6M9 15h6" />
    </>
  ),
  boots: (s) => <Path {...s} d="M7 3h6v10l6 3a2 2 0 0 1 1 1.7V20H5V13l2-1V3zM5 17h15" />,
  calendar: (s) => (
    <>
      <Rect {...s} x="3.5" y="5" width="17" height="15" rx="2" />
      <Path {...s} d="M3.5 10h17M8 3v4M16 3v4" />
    </>
  ),
  question: (s) => (
    <>
      <Path {...s} d="M4 5h16v11h-7l-5 4v-4H4V5z" />
      <Path {...s} d="M10 9a2 2 0 1 1 2.8 1.8c-.5.3-.8.7-.8 1.2M12 13.5v.3" />
    </>
  ),
  shield: (s) => (
    <>
      <Path {...s} d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z" />
      <Path {...s} d="M8.5 12l2.5 2.5 4.5-5" />
    </>
  ),
  tag: (s) => (
    <>
      <Path {...s} d="M3 12V4h8l10 10-8 8L3 12z" />
      <Circle {...s} cx="7.5" cy="8" r="1.5" />
    </>
  ),
  directions: (s) => (
    <>
      <Path {...s} d="M12 2.5l9.5 9.5-9.5 9.5L2.5 12 12 2.5z" />
      <Path {...s} d="M9 14v-3h5M12 8.5L14.5 11 12 13.5" />
    </>
  ),
  spray: (s) => (
    <>
      <Path {...s} d="M9 9h6v12H9zM10 9V6h4v3M14 6l3-2M17 4h3M17 7h3M17 10h3" />
    </>
  ),
  edit: (s) => <Path {...s} d="M4 20h4L19 9l-4-4L4 16v4zM13.5 6.5l4 4" />,
  image: (s) => (
    <>
      <Rect {...s} x="3" y="4" width="18" height="16" rx="2" />
      <Circle {...s} cx="9" cy="9.5" r="1.5" />
      <Path {...s} d="M21 16l-5-5-9 9" />
    </>
  ),
};
