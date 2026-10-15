import type { Appointment, DaySchedule } from '@beauty/api';
import {
  ErrorState,
  Icon,
  IconButton,
  Skeleton,
  StateView,
  cx,
  dateKey,
  formatDayHeading,
  formatMinutes,
  useNow,
  useOnline,
} from '@beauty/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useRef } from 'react';
import { Link, useNavigate, useParams } from 'react-router';
import { scheduleKeys } from '../../entities/schedule/model';
import { useAppointmentDecision, useDay, useProfile } from '../../entities/schedule/queries';
import { DEFAULT_TZ, addDays, isDate, mondayOf, weekdayShort } from '../../shared/lib/dates';
import { plural } from '../../shared/lib/plural';
import { BottomNav } from '../../widgets/bottom-nav/BottomNav';
import { DayTimeline } from '../../widgets/day-timeline/DayTimeline';
import styles from './SchedulePage.module.css';

/** Экран «График дня» (макет MasterSchedule). */
export function SchedulePage() {
  const params = useParams();
  const navigate = useNavigate();
  const profile = useProfile();
  const tz = profile.data?.timezone ?? DEFAULT_TZ;
  const now = useNow(60_000);
  const today = dateKey(now, tz);
  const date = isDate(params.date) ? params.date : today;
  const day = useDay(date);
  const online = useOnline();
  const queryClient = useQueryClient();
  const decision = useAppointmentDecision(date);

  const go = useCallback((d: string) => void navigate(`/schedule/${d}`), [navigate]);
  const swipe = useSwipe((dir) => go(addDays(date, dir)));
  const monday = mondayOf(date);
  const week = Array.from({ length: 7 }, (_, i) => addDays(monday, i));
  const offDays = new Set(day.data?.week.filter((d) => d.day_off).map((d) => d.date) ?? []);

  const onExpired = useCallback(
    () => void queryClient.invalidateQueries({ queryKey: scheduleKeys.day(date) }),
    [queryClient, date],
  );

  return (
    <>
      <header className={styles.header}>
        <div className={styles.titleRow}>
          <h1 className={styles.h1} aria-live="polite">
            {formatDayHeading(date)}
          </h1>
          <IconButton label="Предыдущий день" look="outlined" onClick={() => go(addDays(date, -1))}>
            <Icon name="back" size={20} strokeWidth={2} />
          </IconButton>
          <IconButton label="Следующий день" look="outlined" onClick={() => go(addDays(date, 1))}>
            <Icon name="forward" size={20} strokeWidth={2} />
          </IconButton>
        </div>
        <nav className={styles.week} aria-label="Дни недели">
          {week.map((d) => (
            <Link
              key={d}
              to={`/schedule/${d}`}
              className={cx(styles.day, offDays.has(d) && d !== date && styles.off)}
              aria-current={d === date ? 'date' : undefined}
              aria-label={`${formatDayHeading(d)}${d === today ? ', сегодня' : ''}${offDays.has(d) ? ', выходной' : ''}`}
            >
              {weekdayShort(d)}
              <span className={styles.dayNum}>{offDays.has(d) ? 'вых' : Number(d.slice(8))}</span>
            </Link>
          ))}
        </nav>
      </header>

      <main className={styles.main} {...swipe}>
        {day.isPending ? (
          <TimelineSkeleton />
        ) : day.isError ? (
          <ErrorState offline={!online} onRetry={() => void day.refetch()} />
        ) : day.data.day_off ? (
          <StateView icon="calendar" title="Выходной" text="В этот день записи закрыты." />
        ) : (
          <>
            <Summary day={day.data} />
            {day.data.items.length === 0 ? (
              <StateView icon="calendar" title="День свободен" text="Записей пока нет." />
            ) : (
              <DayTimeline
                day={day.data}
                timeZone={tz}
                handlers={{
                  busyId: decision.isPending ? (decision.variables?.appointment.id ?? null) : null,
                  onConfirm: (appointment: Appointment) =>
                    decision.mutate({ appointment, decision: { kind: 'confirm' } }),
                  onDecline: (appointment: Appointment) =>
                    decision.mutate({
                      appointment,
                      decision: { kind: 'decline', offerAlternatives: false },
                    }),
                  onExpired,
                }}
              />
            )}
          </>
        )}
      </main>
      <BottomNav />
    </>
  );
}

function Summary({ day }: { readonly day: DaySchedule }) {
  const { appointments, pending_requests: pending, free_minutes: free } = day.summary;
  return (
    <div className={styles.chips}>
      <span className={styles.chip}>
        {appointments} {plural(appointments, ['запись', 'записи', 'записей'])}
      </span>
      {pending > 0 && (
        <span className={cx(styles.chip, styles.chipWarn)}>
          {pending} {plural(pending, ['заявка ждёт', 'заявки ждут', 'заявок ждут'])} вас
        </span>
      )}
      {free > 0 && <span className={styles.chip}>Окна: {formatMinutes(free)}</span>}
    </div>
  );
}

/** Свайп по дню: влево — следующий, вправо — предыдущий. */
function useSwipe(onSwipe: (direction: 1 | -1) => void) {
  const start = useRef<{ x: number; y: number } | null>(null);
  return {
    onTouchStart: (e: React.TouchEvent) => {
      const t = e.touches[0];
      start.current = t ? { x: t.clientX, y: t.clientY } : null;
    },
    onTouchEnd: (e: React.TouchEvent) => {
      const t = e.changedTouches[0];
      const s = start.current;
      start.current = null;
      if (!t || !s) return;
      const dx = t.clientX - s.x;
      const dy = t.clientY - s.y;
      if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) onSwipe(dx < 0 ? 1 : -1);
    },
  };
}

function TimelineSkeleton() {
  return (
    <div
      style={{ display: 'flex', flexDirection: 'column', gap: 12 }}
      aria-busy="true"
      aria-label="Загрузка графика"
    >
      <div style={{ display: 'flex', gap: 8 }}>
        <Skeleton width={80} height={30} radius={12} />
        <Skeleton width={140} height={30} radius={12} />
      </div>
      {[96, 44, 160, 44, 72].map((h, i) => (
        <div key={i} style={{ display: 'flex', gap: 10 }}>
          <Skeleton width={44} height={14} style={{ marginTop: 12 }} />
          <Skeleton height={h} radius={16} />
        </div>
      ))}
    </div>
  );
}
