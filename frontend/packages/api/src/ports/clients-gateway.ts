import type { MasterClientCard, MasterClientPage } from '../types';

/** Параметры списка клиентов. */
export interface ClientListQuery {
  /** Имя или цифры телефона. */
  readonly q?: string;
  /** `upcoming` — только с заявкой или записью впереди. */
  readonly filter?: 'all' | 'upcoming';
  readonly limit?: number;
  readonly offset?: number;
}

/** Порт картотеки клиентов мастера: каждое изменение возвращает карточку целиком. */
export interface ClientsGateway {
  list(query?: ClientListQuery): Promise<MasterClientPage>;
  card(clientId: string): Promise<MasterClientCard>;
  /** `null` или пустая строка — снова подпись по телефону. */
  rename(clientId: string, name: string | null): Promise<MasterClientCard>;
  addNote(clientId: string, text: string): Promise<MasterClientCard>;
  removeNote(clientId: string, noteId: string): Promise<MasterClientCard>;
}
