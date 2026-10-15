import { useEffect, useState } from 'react';

/**
 * Текущее время, обновляемое с шагом `intervalMs` (для таймеров и обратных
 * отсчётов). Тикает локально; источник истины по срокам — сервер.
 */
export function useNow(intervalMs = 1000, enabled = true): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!enabled) return undefined;
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs, enabled]);
  return now;
}
