import { unwrap, type HttpCore } from '../http/client';
import type { ScheduleGateway } from '../ports/schedule-gateway';
import type { Appointment, DaySchedule, MasterPage } from '../types';

/** Адаптер графика мастера. */
export class HttpScheduleGateway implements ScheduleGateway {
  constructor(private readonly core: HttpCore) {}

  getProfile(): Promise<MasterPage> {
    return unwrap(() => this.core.api.GET('/me'));
  }

  getDay(date: string): Promise<DaySchedule> {
    return unwrap(() => this.core.api.GET('/me/schedule', { params: { query: { date } } }));
  }

  confirm(appointmentId: string): Promise<Appointment> {
    return unwrap(() =>
      this.core.api.POST('/me/appointments/{appointment_id}/confirm', {
        params: { path: { appointment_id: appointmentId } },
      }),
    );
  }

  decline(
    appointmentId: string,
    options: { offerAlternatives?: boolean } = {},
  ): Promise<Appointment> {
    return unwrap(() =>
      this.core.api.POST('/me/appointments/{appointment_id}/decline', {
        params: { path: { appointment_id: appointmentId } },
        body: { offer_alternatives: options.offerAlternatives ?? false },
      }),
    );
  }
}
