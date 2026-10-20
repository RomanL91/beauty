import { ApiError } from '../http/api-error';
import { call, unwrap, type HttpCore } from '../http/client';
import type { AdminGateway, ClientQuery } from '../ports/admin-gateway';
import type {
  AdminAccount,
  AdminAccountInput,
  AdminAgentReport,
  AdminClientRow,
  AdminDashboard,
  AdminMasterDetail,
  AdminMasterInput,
  AdminMasterRow,
  AdminSession,
  AdminSystem,
  MasterStatus,
} from '../types';

/**
 * Адаптер админ-панели: клиент без access-токена (`bare`) — сессия едет в cookie
 * `bk_admin` того же origin; CSRF-токен — заголовком в изменяющих запросах.
 */
export class HttpAdminGateway implements AdminGateway {
  #csrf = '';

  constructor(private readonly core: HttpCore) {}

  private get csrf() {
    return { header: { 'X-CSRF-Token': this.#csrf } };
  }

  async login(login: string, password: string): Promise<AdminSession> {
    const session = await unwrap(() =>
      this.core.bare.POST('/admin/auth/login', { body: { login, password } }),
    );
    this.#csrf = session.csrf_token;
    return session;
  }

  async me(): Promise<AdminSession | null> {
    const { data, error, response } = await call(() => this.core.bare.GET('/admin/auth/me'));
    if (response.status === 401) return null;
    if (!response.ok || !data) throw ApiError.fromBody(response.status, error);
    this.#csrf = data.csrf_token;
    return data;
  }

  async logout(): Promise<void> {
    await unwrap(() => this.core.bare.POST('/admin/auth/logout', { params: this.csrf }));
    this.#csrf = '';
  }

  changePassword(currentPassword: string, newPassword: string): Promise<void> {
    return unwrap(() =>
      this.core.bare.POST('/admin/auth/password', {
        params: this.csrf,
        body: { current_password: currentPassword, new_password: newPassword },
      }),
    );
  }

  dashboard(): Promise<AdminDashboard> {
    return unwrap(() => this.core.bare.GET('/admin/dashboard'));
  }

  async masters(query: { q?: string; status?: MasterStatus } = {}): Promise<AdminMasterRow[]> {
    const page = await unwrap(() =>
      this.core.bare.GET('/admin/masters', {
        params: { query: { q: query.q || undefined, status: query.status } },
      }),
    );
    return page.items;
  }

  master(masterId: string): Promise<AdminMasterDetail> {
    return unwrap(() =>
      this.core.bare.GET('/admin/masters/{master_id}', {
        params: { path: { master_id: masterId } },
      }),
    );
  }

  createMaster(input: AdminMasterInput): Promise<AdminMasterDetail> {
    return unwrap(() => this.core.bare.POST('/admin/masters', { params: this.csrf, body: input }));
  }

  setOwner(masterId: string, phone: string): Promise<AdminMasterDetail> {
    return unwrap(() =>
      this.core.bare.PUT('/admin/masters/{master_id}/owner', {
        params: { ...this.csrf, path: { master_id: masterId } },
        body: { phone },
      }),
    );
  }

  setPublication(masterId: string, published: boolean): Promise<AdminMasterDetail> {
    return unwrap(() =>
      this.core.bare.PUT('/admin/masters/{master_id}/publication', {
        params: { ...this.csrf, path: { master_id: masterId } },
        body: { published },
      }),
    );
  }

  setAgent(masterId: string, enabled: boolean): Promise<AdminMasterDetail> {
    return unwrap(() =>
      this.core.bare.PUT('/admin/masters/{master_id}/agent', {
        params: { ...this.csrf, path: { master_id: masterId } },
        body: { enabled },
      }),
    );
  }

  setBroadcasts(masterId: string, allowed: boolean): Promise<AdminMasterDetail> {
    return unwrap(() =>
      this.core.bare.PUT('/admin/masters/{master_id}/broadcasts', {
        params: { ...this.csrf, path: { master_id: masterId } },
        body: { allowed },
      }),
    );
  }

  clients(query: ClientQuery = {}): Promise<{ items: AdminClientRow[]; total: number }> {
    return unwrap(() =>
      this.core.bare.GET('/admin/clients', {
        params: {
          query: {
            q: query.q || undefined,
            blocked: query.blocked,
            limit: query.limit,
            offset: query.offset,
          },
        },
      }),
    );
  }

  setClientBlock(clientId: string, blocked: boolean, reason?: string): Promise<AdminClientRow> {
    return unwrap(() =>
      this.core.bare.PUT('/admin/clients/{client_id}/block', {
        params: { ...this.csrf, path: { client_id: clientId } },
        body: { blocked, ...(reason ? { reason } : {}) },
      }),
    );
  }

  agent(): Promise<AdminAgentReport> {
    return unwrap(() => this.core.bare.GET('/admin/agent'));
  }

  system(): Promise<AdminSystem> {
    return unwrap(() => this.core.bare.GET('/admin/system'));
  }

  async admins(): Promise<AdminAccount[]> {
    return (await unwrap(() => this.core.bare.GET('/admin/admins'))).items;
  }

  createAdmin(input: AdminAccountInput): Promise<AdminAccount> {
    return unwrap(() => this.core.bare.POST('/admin/admins', { params: this.csrf, body: input }));
  }

  updateAdmin(
    adminId: string,
    patch: { active?: boolean; password?: string },
  ): Promise<AdminAccount> {
    return unwrap(() =>
      this.core.bare.PATCH('/admin/admins/{admin_id}', {
        params: { ...this.csrf, path: { admin_id: adminId } },
        body: patch,
      }),
    );
  }

  audit(before?: string) {
    return unwrap(() =>
      this.core.bare.GET('/admin/audit', { params: { query: { before, limit: 50 } } }),
    );
  }
}
