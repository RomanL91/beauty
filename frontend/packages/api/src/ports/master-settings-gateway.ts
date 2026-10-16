import type {
  BookingRulesSettings,
  MasterSettings,
  ProfileInput,
  ServiceInput,
  WorkingDay,
} from '../types';

/** Порт настроек страницы мастера: каждое изменение возвращает настройки целиком. */
export interface MasterSettingsGateway {
  get(): Promise<MasterSettings>;
  updateProfile(input: ProfileInput): Promise<MasterSettings>;
  addService(input: ServiceInput): Promise<MasterSettings>;
  updateService(serviceId: string, input: ServiceInput): Promise<MasterSettings>;
  /** Убрать услугу (в архив: записи на неё сохраняются). */
  archiveService(serviceId: string): Promise<MasterSettings>;
  /** Рабочие дни; дня нет в списке — выходной. */
  setWorkingHours(days: WorkingDay[]): Promise<MasterSettings>;
  /** Выходные даты `YYYY-MM-DD` (список целиком). */
  setDaysOff(days: string[]): Promise<MasterSettings>;
  setBookingRules(rules: BookingRulesSettings): Promise<MasterSettings>;
  addPhoto(file: Blob, alt?: string): Promise<MasterSettings>;
  removePhoto(photoId: string): Promise<MasterSettings>;
  setAvatar(file: Blob): Promise<MasterSettings>;
  removeAvatar(): Promise<MasterSettings>;
  publish(): Promise<MasterSettings>;
  unpublish(): Promise<MasterSettings>;
}
