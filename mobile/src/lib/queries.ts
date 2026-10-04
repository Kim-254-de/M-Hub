/** Server data used across screens. Cached on the phone so the last known state shows offline. */
import { QueryClient, useQuery } from '@tanstack/react-query';
import { createAsyncStoragePersister } from '@tanstack/query-async-storage-persister';
import AsyncStorage from '@react-native-async-storage/async-storage';

import { ApiError } from '../api/client';
import * as endpoints from '../api/endpoints';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 7 * 24 * 60 * 60 * 1000, // keep a week for offline viewing
      retry: (count, error) => !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2,
      networkMode: 'offlineFirst',
    },
  },
});

export const persister = createAsyncStoragePersister({ storage: AsyncStorage, key: 'agrisense.cache' });

/** 404 means "not there yet" (e.g. no prescription), not an error. */
async function orNull<T>(request: Promise<T>): Promise<T | null> {
  try {
    return await request;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

const POLL_WHILE_WAITING = 20_000;

export const keys = {
  me: ['me'] as const,
  outbreaks: ['outbreaks'] as const,
  cases: ['cases'] as const,
  case: (id: string) => ['case', id] as const,
  diagnosis: (id: string) => ['diagnosis', id] as const,
  prescription: (id: string) => ['prescription', id] as const,
  followUp: (id: string) => ['followUp', id] as const,
  orders: ['orders'] as const,
  order: (id: string) => ['order', id] as const,
  stores: (code: string) => ['stores', code] as const,
  rewards: ['rewards'] as const,
};

export const useMe = () => useQuery({ queryKey: keys.me, queryFn: endpoints.getMe });
export const useOutbreaks = () => useQuery({ queryKey: keys.outbreaks, queryFn: endpoints.getOutbreaks, staleTime: 10 * 60_000 });
export const useCases = () => useQuery({ queryKey: keys.cases, queryFn: endpoints.listCases });
export const useCase = (id: string) =>
  useQuery({
    queryKey: keys.case(id),
    queryFn: () => endpoints.getCase(id),
    refetchInterval: (query) =>
      query.state.data && ['REPORTED', 'DIAGNOSING', 'SECOND_OPINION', 'DIAGNOSED'].includes(query.state.data.status)
        ? POLL_WHILE_WAITING
        : false,
  });
export const useDiagnosis = (id: string) =>
  useQuery({
    queryKey: keys.diagnosis(id),
    queryFn: () => endpoints.getDiagnosis(id),
    enabled: !!id,
    // Poll while waiting so the AI suggestion and the agrovet's confirmation appear without a refresh.
    refetchInterval: (query) => (query.state.data && !query.state.data.confirmed_by ? POLL_WHILE_WAITING : false),
  });
export const usePrescription = (id: string, enabled = true) =>
  useQuery({ queryKey: keys.prescription(id), queryFn: () => orNull(endpoints.getPrescription(id)), enabled });
export const useFollowUp = (id: string, enabled = true) =>
  useQuery({ queryKey: keys.followUp(id), queryFn: () => orNull(endpoints.getFollowUp(id)), enabled });
export const useOrders = () => useQuery({ queryKey: keys.orders, queryFn: endpoints.listOrders });
export const useOrder = (id: string, poll = false) =>
  useQuery({ queryKey: keys.order(id), queryFn: () => endpoints.getOrder(id), refetchInterval: poll ? 3_000 : false });
export const useStores = (code: string | null, location?: { latitude: string; longitude: string }) =>
  useQuery({
    queryKey: [...keys.stores(code ?? ''), location?.latitude, location?.longitude],
    queryFn: () => endpoints.storesFor(code!, location),
    enabled: !!code,
  });
export const useRewards = () => useQuery({ queryKey: keys.rewards, queryFn: endpoints.getRewards });
