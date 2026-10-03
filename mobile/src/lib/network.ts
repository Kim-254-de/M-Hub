import NetInfo from '@react-native-community/netinfo';
import { useEffect, useState } from 'react';

/** True when the phone has no usable connection. Unknown counts as online so nothing is blocked by mistake. */
export function useOffline(): boolean {
  const [offline, setOffline] = useState(false);
  useEffect(
    () =>
      NetInfo.addEventListener((state) => {
        setOffline(state.isConnected === false || state.isInternetReachable === false);
      }),
    [],
  );
  return offline;
}
