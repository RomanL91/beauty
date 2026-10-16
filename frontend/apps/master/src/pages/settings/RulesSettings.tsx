import { ApiError, type BookingRulesSettings, type MasterSettings } from '@beauty/api';
import { formatMinutes } from '@beauty/ui';
import { useState, type FormEvent } from 'react';
import { SLOT_STEPS } from '../../entities/settings/model';
import { useSettingsChange } from '../../entities/settings/queries';
import { plural } from '../../shared/lib/plural';
import { SelectField } from '../../shared/ui/Field';
import { FormError, SaveBar, SettingsScreen } from './SettingsScreen';
import styles from './Settings.module.css';

const hours = (n: number) => `${n} ${plural(n, ['час', 'часа', 'часов'])}`;
const days = (n: number) => `${n} ${plural(n, ['день', 'дня', 'дней'])}`;

/** Варианты правила (текущее значение, даже нестандартное, всегда есть в списке). */
function options(values: readonly number[], current: number, label: (n: number) => string) {
  return [...new Set([...values, current])]
    .sort((a, b) => a - b)
    .map((value) => ({ value, label: label(value) }));
}

/** «Правила записи»: подтверждение, перенос, минимум до визита, горизонт, шаг сетки. */
export function RulesSettings() {
  return (
    <SettingsScreen title="Правила записи">
      {(settings) => (
        <div className={styles.body}>
          <RulesForm settings={settings} />
        </div>
      )}
    </SettingsScreen>
  );
}

function RulesForm({ settings }: { readonly settings: MasterSettings }) {
  const [rules, setRules] = useState<BookingRulesSettings>(settings.booking_rules);
  const save = useSettingsChange(
    (gateway, input: BookingRulesSettings) => gateway.setBookingRules(input),
    'Правила сохранены',
  );
  const dirty = JSON.stringify(rules) !== JSON.stringify(settings.booking_rules);
  const set = (key: keyof BookingRulesSettings) => (e: { target: { value: string } }) =>
    setRules((r) => ({ ...r, [key]: Number(e.target.value) }));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate(rules, { onSuccess: (next) => setRules(next.booking_rules) });
  };

  return (
    <form className={styles.form} onSubmit={submit} aria-label="Правила записи">
      <section className={styles.card}>
        <SelectField
          label="Подтвердить заявку в течение"
          value={rules.confirm_within_hours}
          options={options([1, 2, 3, 4, 6, 8, 12, 24, 48, 72], rules.confirm_within_hours, hours)}
          hint="Не успели — заявка отклоняется, клиент получает другие окна"
          onChange={set('confirm_within_hours')}
        />
        <SelectField
          label="Клиент может перенести или отменить не позже чем за"
          value={rules.change_deadline_hours}
          options={options([0, 2, 4, 6, 12, 24, 48, 72], rules.change_deadline_hours, (n) =>
            n === 0 ? 'в любой момент' : hours(n),
          )}
          onChange={set('change_deadline_hours')}
        />
        <SelectField
          label="Ближайшая запись — не раньше чем через"
          value={rules.min_notice_minutes}
          options={options(
            [0, 30, 60, 120, 180, 240, 360, 720, 1440, 2880],
            rules.min_notice_minutes,
            (n) => (n === 0 ? 'можно сразу' : formatMinutes(n)),
          )}
          hint="Чтобы не получить заявку на «через 10 минут»"
          onChange={set('min_notice_minutes')}
        />
        <SelectField
          label="Запись открыта вперёд на"
          value={rules.horizon_days}
          options={options([7, 14, 21, 30, 45, 60, 90], rules.horizon_days, days)}
          onChange={set('horizon_days')}
        />
        <SelectField
          label="Шаг окон"
          value={rules.slot_step_minutes}
          options={SLOT_STEPS.map((n) => ({ value: n, label: `каждые ${n} мин` }))}
          hint="10:00, 10:30, 11:00… — с каким шагом агент предлагает время"
          onChange={set('slot_step_minutes')}
        />
      </section>
      <FormError text={save.error instanceof ApiError ? save.error.message : null} />
      <SaveBar dirty={dirty} saving={save.isPending} />
    </form>
  );
}
