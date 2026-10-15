import { createContext, useContext } from 'react';
import type { ClientContainer } from '../../app/container';

/** Контекст контейнера зависимостей. */
export const ContainerContext = createContext<ClientContainer | null>(null);

/** Зависимости приложения (порты). */
export function useContainer(): ClientContainer {
  const container = useContext(ContainerContext);
  if (!container) throw new Error('useContainer вне AppContainer');
  return container;
}

/** Slug мастера; экраны внутри роутера вызываются только когда он есть. */
export function useMasterSlug(): string {
  const { masterSlug } = useContainer();
  if (!masterSlug) throw new Error('Мастер не определён');
  return masterSlug;
}
