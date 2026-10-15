import { unwrap, type HttpCore } from '../http/client';
import type { MasterGateway, SlotQuery } from '../ports/master-gateway';
import type { MasterPage, Slot } from '../types';

/** Адаптер публичной страницы мастера. */
export class HttpMasterGateway implements MasterGateway {
  constructor(private readonly core: HttpCore) {}

  getPage(slug: string): Promise<MasterPage> {
    return unwrap(() => this.core.api.GET('/masters/{slug}', { params: { path: { slug } } }));
  }

  async listSlots(slug: string, query: SlotQuery = {}): Promise<Slot[]> {
    const page = await unwrap(() =>
      this.core.api.GET('/masters/{slug}/slots', {
        params: {
          path: { slug },
          query: {
            ...(query.serviceId !== undefined && { service: query.serviceId }),
            ...(query.from !== undefined && { from: query.from }),
            ...(query.to !== undefined && { to: query.to }),
            ...(query.limit !== undefined && { limit: query.limit }),
          },
        },
      }),
    );
    return page.items;
  }
}
