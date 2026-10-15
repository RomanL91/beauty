import type { SessionState } from '@beauty/api';
import { useSyncExternalStore } from 'react';
import { useContainer } from '../../shared/lib/container-context';

/** Текущее состояние сессии. */
export function useSession(): SessionState {
  const { session } = useContainer();
  return useSyncExternalStore(session.subscribe, session.getSnapshot, session.getSnapshot);
}
