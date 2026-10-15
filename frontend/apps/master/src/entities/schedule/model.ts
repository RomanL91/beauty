import type { Appointment, DaySchedule, ScheduleItem } from '@beauty/api';

/** Ключи кэша графика. */
export const scheduleKeys = {
  all: ['schedule'] as const,
  day: (date: string) => ['schedule', date] as const,
};

/**
 * Подменить запись в дне графика. Отменённая запись превращается в окно
 * (точные окна и сводку пересчитает следующий запрос к серверу).
 */
export function patchAppointment(day: DaySchedule, appointment: Appointment): DaySchedule {
  let found = false;
  const items = day.items.map((item): ScheduleItem => {
    if (item.kind !== 'appointment' || item.appointment.id !== appointment.id) return item;
    found = true;
    return appointment.status === 'cancelled'
      ? { kind: 'free', start: appointment.start, end: appointment.end }
      : { ...item, appointment };
  });
  if (!found) return day;
  const pending = items.filter(
    (i) => i.kind === 'appointment' && i.appointment.status === 'requested',
  ).length;
  const count = items.filter((i) => i.kind === 'appointment').length;
  return {
    ...day,
    items,
    summary: { ...day.summary, pending_requests: pending, appointments: count },
  };
}

/** Есть ли запись в дне. */
export function hasAppointment(day: DaySchedule | undefined, id: string): boolean {
  return day?.items.some((i) => i.kind === 'appointment' && i.appointment.id === id) ?? false;
}
