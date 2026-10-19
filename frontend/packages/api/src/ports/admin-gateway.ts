import type {
  AdminAccount,
  AdminAccountInput,
  AdminAgentReport,
  AdminAuditEntry,
  AdminClientRow,
  AdminDashboard,
  AdminMasterDetail,
  AdminMasterInput,
  AdminMasterRow,
  AdminSession,
  AdminSystem,
  MasterStatus,
} from '../types';

/** Фильтр клиентов. */
export interface ClientQuery {
  readonly q?: string;
  readonly blocked?: boolean;
  readonly limit?: number;
  readonly offset?: number;
}

/**
 * Порт админ-панели. Сессия — httpOnly-cookie; CSRF-токен адаптер запоминает из входа
 * и `me()` и сам кладёт в изменяющие запросы.
 */
export interface AdminGateway {
  login(login: string, password: string): Promise<AdminSession>;
  /** Текущая сессия или `null` (не вошли или истекла). */
  me(): Promise<AdminSession | null>;
  logout(): Promise<void>;
  changePassword(currentPassword: string, newPassword: string): Promise<void>;

  dashboard(): Promise<AdminDashboard>;
  masters(query?: {
    readonly q?: string;
    readonly status?: MasterStatus;
  }): Promise<AdminMasterRow[]>;
  master(masterId: string): Promise<AdminMasterDetail>;
  createMaster(input: AdminMasterInput): Promise<AdminMasterDetail>;
  setOwner(masterId: string, phone: string): Promise<AdminMasterDetail>;
  setPublication(masterId: string, published: boolean): Promise<AdminMasterDetail>;
  setAgent(masterId: string, enabled: boolean): Promise<AdminMasterDetail>;

  clients(query?: ClientQuery): Promise<{ items: AdminClientRow[]; total: number }>;
  setClientBlock(clientId: string, blocked: boolean, reason?: string): Promise<AdminClientRow>;

  agent(): Promise<AdminAgentReport>;
  system(): Promise<AdminSystem>;

  admins(): Promise<AdminAccount[]>;
  createAdmin(input: AdminAccountInput): Promise<AdminAccount>;
  updateAdmin(
    adminId: string,
    patch: { readonly active?: boolean; readonly password?: string },
  ): Promise<AdminAccount>;
  audit(before?: string): Promise<{ items: AdminAuditEntry[]; has_more: boolean }>;
}
