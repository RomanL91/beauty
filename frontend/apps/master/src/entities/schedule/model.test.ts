import type { Appointment, DaySchedule } from '@beauty/api';
import { describe, expect, it } from 'vitest';
import { patchAppointment } from './model';

const service = { id: 's', title: 'Массаж', duration_min: 40, price: null };
const client = { id: 'c', display_name: 'Дарья К.', visit_number: 3 };
const request: Appointment = {
  id: 'a1',
  status: 'requested',
  service,
  client,
  start: '2026-10-15T12:00:00+05:00',
  end: '2026-10-15T12:40:00+05:00',
  hold_until: '2026-10-15T09:00:00Z',
  auto_decline_at: '2026-10-15T09:00:00Z',
};
const day: DaySchedule = {
  date: '2026-10-15',
  week: [],
  day_off: false,
  items: [{ kind: 'appointment', appointment: request, conversation_id: null }],
  summary: { appointments: 1, pending_requests: 1, free_minutes: 0 },
};

describe('patchAppointment', () => {
  it('подтверждение снимает заявку из сводки', () => {
    const next = patchAppointment(day, {
      ...request,
      status: 'confirmed',
      confirmed_at: 'x',
    } as Appointment);
    expect(next.summary.pending_requests).toBe(0);
    expect(next.items[0]).toMatchObject({
      kind: 'appointment',
      appointment: { status: 'confirmed' },
    });
  });

  it('отклонение превращает заявку в окно', () => {
    const next = patchAppointment(day, {
      ...request,
      status: 'cancelled',
      cancelled_by: 'master',
    } as Appointment);
    expect(next.items[0]).toMatchObject({ kind: 'free', start: request.start });
    expect(next.summary.appointments).toBe(0);
  });

  it('чужая запись — без изменений', () => {
    expect(patchAppointment(day, { ...request, id: 'other' })).toBe(day);
  });
});
