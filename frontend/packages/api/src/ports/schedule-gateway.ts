import type { Appointment, DaySchedule, MasterPage } from '../types';

/** Порт графика мастера. */
export interface ScheduleGateway {
  /** Свой профиль (имя в падежах, часовой пояс). */
  getProfile(): Promise<MasterPage>;
  /** День (и обзор его недели). `date` — `YYYY-MM-DD`. */
  getDay(date: string): Promise<DaySchedule>;
  confirm(appointmentId: string): Promise<Appointment>;
  /** Отклонить; `offerAlternatives` — агент предложит клиенту другие окна. */
  decline(appointmentId: string, options?: { offerAlternatives?: boolean }): Promise<Appointment>;
}
