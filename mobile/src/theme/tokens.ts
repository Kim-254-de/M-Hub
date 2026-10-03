/**
 * AgriSense design tokens (style guide in the design brief, section 5).
 * Contrast pairs used for text are WCAG AA or better on their background, for reading in sunlight.
 */
export const colors = {
  // Brand
  leaf: '#1F5F2E', // deep leaf green: primary actions, active tab (white text 7.7:1)
  leafDark: '#164622', // pressed
  leafSoft: '#E3EFE5', // selected options, light panels
  soil: '#6B4A2E', // warm earth brown: secondary actions (white text 7.9:1)
  soilSoft: '#F1E8DD',
  tomato: '#D2462E', // accent only (never for errors)
  cream: '#FBF7EF', // app background
  surface: '#FFFFFF', // cards

  // Text
  ink: '#1D2420', // body text on cream 14.8:1
  inkMuted: '#4A544E', // secondary text on cream 7.4:1
  inkOnDark: '#FFFFFF',

  // Meaning (always paired with an icon and a word)
  verified: '#17652A', // clear green (on verifiedSoft 6.2:1)
  verifiedSoft: '#E2F3E5',
  warning: '#8A5A00', // amber text on warningSoft 5.3:1
  warningIcon: '#C98A00',
  warningSoft: '#FFF2D1',
  danger: '#8A2C00', // strong amber-brown for "do not use", 7.0:1 (not tomato red)
  dangerSoft: '#FCE3D3',
  info: '#1D4E7A',
  infoSoft: '#E1ECF6',

  border: '#D9D2C3',
  borderStrong: '#8C8576',
  disabled: '#B8B2A6',
  overlay: 'rgba(0,0,0,0.55)',
} as const;

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;

export const radius = { sm: 8, md: 12, lg: 16, pill: 999 } as const;

/** Type scale in sp: body never below 16. */
export const type = {
  display: { fontSize: 28, lineHeight: 34, fontFamily: 'NotoSans_700Bold' },
  h1: { fontSize: 24, lineHeight: 30, fontFamily: 'NotoSans_700Bold' },
  h2: { fontSize: 20, lineHeight: 26, fontFamily: 'NotoSans_700Bold' },
  bodyStrong: { fontSize: 17, lineHeight: 24, fontFamily: 'NotoSans_600SemiBold' },
  body: { fontSize: 16, lineHeight: 24, fontFamily: 'NotoSans_500Medium' },
  label: { fontSize: 14, lineHeight: 18, fontFamily: 'NotoSans_600SemiBold' }, // tab and chip labels only
  code: { fontSize: 30, lineHeight: 36, fontFamily: 'NotoSans_700Bold', letterSpacing: 2 },
} as const;

export const touch = { min: 48, primary: 56 } as const;
