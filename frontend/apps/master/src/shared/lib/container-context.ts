import { createContext, useContext } from 'react';
import type { MasterContainer } from '../../app/container';

/** Контекст контейнера зависимостей. */
export const ContainerContext = createContext<MasterContainer | null>(null);

/** Зависимости кабинета (порты). */
export function useContainer(): MasterContainer {
  const container = useContext(ContainerContext);
  if (!container) throw new Error('useContainer вне AppContainer');
  return container;
}
