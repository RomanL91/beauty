import { unwrap, type HttpCore } from '../http/client';
import type { ClientListQuery, ClientsGateway } from '../ports/clients-gateway';
import type { MasterClientCard, MasterClientPage } from '../types';

/** Адаптер картотеки клиентов мастера (`/me/clients`). */
export class HttpClientsGateway implements ClientsGateway {
  constructor(private readonly core: HttpCore) {}

  list(query: ClientListQuery = {}): Promise<MasterClientPage> {
    return unwrap(() =>
      this.core.api.GET('/me/clients', {
        params: { query: { ...query, q: query.q?.trim() || undefined } },
      }),
    );
  }

  card(clientId: string): Promise<MasterClientCard> {
    return unwrap(() =>
      this.core.api.GET('/me/clients/{client_id}', { params: { path: { client_id: clientId } } }),
    );
  }

  rename(clientId: string, name: string | null): Promise<MasterClientCard> {
    return unwrap(() =>
      this.core.api.PUT('/me/clients/{client_id}/name', {
        params: { path: { client_id: clientId } },
        body: { name: name?.trim() || null },
      }),
    );
  }

  addNote(clientId: string, text: string): Promise<MasterClientCard> {
    return unwrap(() =>
      this.core.api.POST('/me/clients/{client_id}/notes', {
        params: { path: { client_id: clientId } },
        body: { text },
      }),
    );
  }

  removeNote(clientId: string, noteId: string): Promise<MasterClientCard> {
    return unwrap(() =>
      this.core.api.DELETE('/me/clients/{client_id}/notes/{note_id}', {
        params: { path: { client_id: clientId, note_id: noteId } },
      }),
    );
  }
}
