import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import en, { type Dictionary } from './en';
import ki from './ki';
import sw from './sw';

export type Language = 'en' | 'sw' | 'ki';
export const LANGUAGES: Language[] = ['en', 'sw', 'ki'];

const DICTIONARIES: Record<Language, unknown> = { en, sw, ki };
// Kikuyu speakers in the pilot area read Kiswahili; English is the last resort.
const FALLBACKS: Record<Language, Language[]> = { en: ['en'], sw: ['sw', 'en'], ki: ['ki', 'sw', 'en'] };
const STORAGE_KEY = 'agrisense.language';

type Leaves<T, P extends string = ''> = {
  [K in keyof T & string]: T[K] extends string ? `${P}${K}` : Leaves<T[K], `${P}${K}.`>;
}[keyof T & string];
export type TextKey = Leaves<Dictionary>;

function lookup(dictionary: unknown, key: string): string | undefined {
  let node: unknown = dictionary;
  for (const part of key.split('.')) {
    if (node == null || typeof node !== 'object') return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === 'string' ? node : undefined;
}

export function translate(language: Language, key: TextKey, values?: Record<string, string | number>): string {
  const template = FALLBACKS[language].map((l) => lookup(DICTIONARIES[l], key)).find((t) => t !== undefined) ?? key;
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (match, name) => (name in values ? String(values[name]) : match));
}

type I18n = {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: TextKey, values?: Record<string, string | number>) => string;
  ready: boolean;
};

const I18nContext = createContext<I18n | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>('sw');
  const [ready, setReady] = useState(false);

  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY)
      .then((saved) => {
        if (saved && (LANGUAGES as string[]).includes(saved)) setLanguageState(saved as Language);
      })
      .finally(() => setReady(true));
  }, []);

  const setLanguage = useCallback((next: Language) => {
    setLanguageState(next);
    AsyncStorage.setItem(STORAGE_KEY, next).catch(() => undefined);
  }, []);

  const value = useMemo<I18n>(
    () => ({ language, setLanguage, ready, t: (key, values) => translate(language, key, values) }),
    [language, ready, setLanguage],
  );
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  const context = useContext(I18nContext);
  if (!context) throw new Error('useI18n must be used inside I18nProvider');
  return context;
}

/** Dates the way farmers read them: 17 Oct 2026 / 17 Okt 2026. */
const MONTHS: Record<'en' | 'sw', string[]> = {
  en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
  sw: ['Jan', 'Feb', 'Mac', 'Apr', 'Mei', 'Jun', 'Jul', 'Ago', 'Sep', 'Okt', 'Nov', 'Des'],
};

export function formatDate(iso: string | null | undefined, language: Language): string {
  if (!iso) return '';
  const date = new Date(iso);
  const months = MONTHS[language === 'en' ? 'en' : 'sw'];
  return `${date.getDate()} ${months[date.getMonth()]} ${date.getFullYear()}`;
}
