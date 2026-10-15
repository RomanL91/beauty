import type { MasterPage, Slot } from '../types';

/** Окно поиска свободных слотов. */
export interface SlotQuery {
  readonly serviceId?: string;
  readonly from?: string;
  readonly to?: string;
  readonly limit?: number;
}

/** Порт публичной страницы мастера. */
export interface MasterGateway {
  /** Профиль, услуги, работы и правила записи. */
  getPage(slug: string): Promise<MasterPage>;
  /** Свободные окна. */
  listSlots(slug: string, query?: SlotQuery): Promise<Slot[]>;
}
