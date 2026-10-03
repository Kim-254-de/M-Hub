import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

import type { TokenPair } from './types';

const KEY = 'agrisense.tokens';

// SecureStore is native only; the web preview keeps tokens in local storage.
const store = Platform.OS === 'web'
  ? { get: (k: string) => AsyncStorage.getItem(k), set: (k: string, v: string) => AsyncStorage.setItem(k, v), del: (k: string) => AsyncStorage.removeItem(k) }
  : { get: (k: string) => SecureStore.getItemAsync(k), set: (k: string, v: string) => SecureStore.setItemAsync(k, v), del: (k: string) => SecureStore.deleteItemAsync(k) };

let cached: TokenPair | null | undefined;

export async function getTokens(): Promise<TokenPair | null> {
  if (cached !== undefined) return cached;
  const raw = await store.get(KEY);
  cached = raw ? (JSON.parse(raw) as TokenPair) : null;
  return cached;
}

export async function setTokens(tokens: TokenPair | null): Promise<void> {
  cached = tokens;
  if (tokens) await store.set(KEY, JSON.stringify(tokens));
  else await store.del(KEY);
}
