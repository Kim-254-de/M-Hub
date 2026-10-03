/** Kenyan mobile numbers, the same rule as the backend (accounts/phone.py). */
const KENYAN_MOBILE = /^(?:\+?254|0)?([17]\d{8})$/;

export function normalizeKenyanPhone(raw: string): string | null {
  const match = raw.replace(/[\s\-().]/g, '').match(KENYAN_MOBILE);
  return match ? `+254${match[1]}` : null;
}
