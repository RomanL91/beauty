import type { AdminGateway } from '@beauty/api';
import { createContext, useContext } from 'react';

/** Зависимости панели: только порты. */
export interface AdminContainer {
  readonly admin: AdminGateway;
}

export const ContainerContext = createContext<AdminContainer | null>(null);

/** Гейтвей панели. */
export function useAdminApi(): AdminGateway {
  const container = useContext(ContainerContext);
  if (!container) throw new Error('useAdminApi вне ContainerContext');
  return container.admin;
}
