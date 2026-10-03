import NetInfo from '@react-native-community/netinfo';
import { useEffect } from 'react';

import { flushOutbox } from '../offline/reports';
import { keys, queryClient } from './queries';

/** Sends queued crop reports when the app opens and whenever the phone reconnects. */
export function useOutboxSync(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
    const flush = () =>
      flushOutbox()
        .then((sent) => {
          if (sent > 0) queryClient.invalidateQueries({ queryKey: keys.cases });
        })
        .catch(() => undefined);
    flush();
    let wasOffline = false;
    return NetInfo.addEventListener((state) => {
      const offline = state.isConnected === false;
      if (wasOffline && !offline) flush();
      wasOffline = offline;
    });
  }, [enabled]);
}
