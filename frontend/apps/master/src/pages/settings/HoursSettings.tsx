import { ApiError, type MasterSettings } from '@beauty/api';
import { Button, Icon, IconButton, dateKey, formatDayHeading, useNow, useOnline } from '@beauty/ui';
import { useState, type FormEvent } from 'react';
import {
  WEEKDAYS,
  weekDraft,
  weekErrors,
  workingDays,
  type WeekDraft,
} from '../../entities/settings/model';
import { useSettingsChange } from '../../entities/settings/queries';
import { TextField, Toggle } from '../../shared/ui/Field';
import { FormError, SaveBar, SettingsScreen } from './SettingsScreen';
import styles from './Settings.module.css';

const DEFAULT_DAY = [{ start: '10:00', end: '19:00' }];

/** «График и выходные»: рабочие часы по дням недели (с перерывами) и выходные даты. */
export function HoursSettings() {
  return (
    <SettingsScreen title="График и выходные">
      {(settings) => (
        <div className={styles.body}>
          <WeekForm settings={settings} />
          <DaysOff settings={settings} />
        </div>
      )}
    </SettingsScreen>
  );
}

function WeekForm({ settings }: { readonly settings: MasterSettings }) {
  const [draft, setDraft] = useState<WeekDraft>(() => weekDraft(settings.working_hours));
  const [touched, setTouched] = useState(false);
  const save = useSettingsChange(
    (gateway, days: ReturnType<typeof workingDays>) => gateway.setWorkingHours(days),
    'График сохранён',
  );
  const errors = weekErrors(draft);
  const dirty =
    JSON.stringify(workingDays(draft)) !==
    JSON.stringify(workingDays(weekDraft(settings.working_hours)));
  const serverError = save.error instanceof ApiError ? save.error.message : null;

  const update = (day: number, change: (intervals: WeekDraft[number]) => WeekDraft[number]) =>
    setDraft((d) => d.map((intervals, i) => (i === day ? change(intervals) : intervals)));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (errors.some(Boolean)) return;
    save.mutate(workingDays(draft), {
      onSuccess: (next) => setDraft(weekDraft(next.working_hours)),
    });
  };

  return (
    <form className={styles.form} onSubmit={submit} noValidate aria-label="Рабочие часы">
      <p className={styles.muted}>
        Агент предлагает окна только в рабочие часы. Перерыв — второй интервал в дне.
      </p>
      {WEEKDAYS.map(({ day, long }) => {
        const intervals = draft[day] ?? [];
        const working = intervals.length > 0;
        const error = touched || dirty ? errors[day] : null;
        return (
          <fieldset key={day} className={`${styles.day} ${working ? '' : styles.dayOff}`}>
            <legend style={{ display: 'contents' }}>
              <Toggle
                label={working ? long : `${long} — выходной`}
                checked={working}
                onChange={(on) => update(day, () => (on ? DEFAULT_DAY.map((i) => ({ ...i })) : []))}
              />
            </legend>
            {intervals.map((interval, index) => (
              <div key={index} className={styles.interval}>
                <input
                  type="time"
                  step={300}
                  className={styles.time}
                  aria-label={`${long}: начало интервала ${index + 1}`}
                  aria-invalid={Boolean(error) || undefined}
                  value={interval.start}
                  onChange={(e) =>
                    update(day, (all) =>
                      all.map((x, i) => (i === index ? { ...x, start: e.target.value } : x)),
                    )
                  }
                />
                <span className={styles.dash} aria-hidden="true">
                  —
                </span>
                <input
                  type="time"
                  step={300}
                  className={styles.time}
                  aria-label={`${long}: конец интервала ${index + 1}`}
                  aria-invalid={Boolean(error) || undefined}
                  value={interval.end}
                  onChange={(e) =>
                    update(day, (all) =>
                      all.map((x, i) => (i === index ? { ...x, end: e.target.value } : x)),
                    )
                  }
                />
                {intervals.length > 1 && (
                  <IconButton
                    label={`${long}: убрать интервал ${index + 1}`}
                    onClick={() => update(day, (all) => all.filter((_, i) => i !== index))}
                  >
                    <Icon name="close" size={18} strokeWidth={2} />
                  </IconButton>
                )}
              </div>
            ))}
            {error && (
              <p className={styles.dayError} role="alert">
                {error}
              </p>
            )}
            {working && intervals.length < 4 && (
              <button
                type="button"
                className={styles.addLink}
                onClick={() => update(day, (all) => [...all, nextInterval(all)])}
              >
                + Перерыв и ещё интервал
              </button>
            )}
          </fieldset>
        );
      })}
      <FormError text={serverError} />
      <SaveBar dirty={dirty} saving={save.isPending} />
    </form>
  );
}

/** Следующий интервал после последнего: через час, на два часа (в пределах суток). */
function nextInterval(intervals: WeekDraft[number]) {
  const last = intervals.at(-1)?.end ?? '10:00';
  const [h = 10, m = 0] = last.split(':').map(Number);
  const start = Math.min(h + 1, 21);
  const pad = (n: number) => String(n).padStart(2, '0');
  return { start: `${pad(start)}:${pad(m)}`, end: `${pad(Math.min(start + 2, 23))}:${pad(m)}` };
}

function DaysOff({ settings }: { readonly settings: MasterSettings }) {
  const online = useOnline();
  const today = dateKey(useNow(60_000), settings.page.timezone);
  const [date, setDate] = useState('');
  const save = useSettingsChange(
    (gateway, days: string[]) => gateway.setDaysOff(days),
    'Выходные сохранены',
  );
  const days = settings.days_off;
  const add = (e: FormEvent) => {
    e.preventDefault();
    if (!date || days.includes(date)) return;
    save.mutate([...days, date], { onSuccess: () => setDate('') });
  };

  return (
    <section className={styles.card} aria-labelledby="days-off">
      <div>
        <h2 id="days-off" className={styles.cardTitle}>
          Выходные даты
        </h2>
        <p className={styles.muted}>Отпуск, праздник, учёба — в эти дни записи не будет.</p>
      </div>
      {days.length > 0 ? (
        <ul className={styles.chips} aria-label="Выходные даты">
          {days.map((d) => (
            <li key={d} className={styles.chip}>
              {formatDayHeading(d)}
              <IconButton
                label={`Убрать выходной ${formatDayHeading(d)}`}
                disabled={save.isPending || !online}
                onClick={() => save.mutate(days.filter((x) => x !== d))}
              >
                <Icon name="close" size={16} strokeWidth={2} />
              </IconButton>
            </li>
          ))}
        </ul>
      ) : (
        <p className={styles.muted}>Пока нет.</p>
      )}
      <form className={styles.row} onSubmit={add} style={{ alignItems: 'flex-end' }}>
        <div className={styles.grow}>
          <TextField
            label="Дата"
            type="date"
            min={today}
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </div>
        <Button type="submit" variant="outline" disabled={!date || save.isPending || !online}>
          Добавить
        </Button>
      </form>
    </section>
  );
}
