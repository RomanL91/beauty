const TZ = 'Asia/Almaty';

const dateTime = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  timeZone: TZ,
});
const dateOnly = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'short',
  timeZone: 'UTC',
});
const number = new Intl.NumberFormat('ru-RU');

/** «12 окт., 14:05» (время Астаны). */
export function formatDateTime(iso: string | null | undefined): string {
  return iso ? dateTime.format(new Date(iso)).replace('.', '') : '—';
}

/** «12 окт» для дня `YYYY-MM-DD`. */
export function formatDay(date: string): string {
  return dateOnly.format(new Date(`${date}T12:00:00Z`)).replace('.', '');
}

/** «1 234». */
export function formatNumber(value: number): string {
  return number.format(value);
}

/** «2,4 с». */
export function formatSeconds(value: number | null): string {
  return value === null ? '—' : `${value.toFixed(1).replace('.', ',')} с`;
}

/** «+7 701 123 45 67». */
export function formatPhone(phone: string | null | undefined): string {
  if (!phone) return '—';
  const m = /^\+7(\d{3})(\d{3})(\d{2})(\d{2})$/.exec(phone);
  return m ? `+7 ${m[1]} ${m[2]} ${m[3]} ${m[4]}` : phone;
}

/** Формы слова: одна, две–четыре, пять. */
export type Forms = readonly [string, string, string];

/** «1 заявка», «3 заявки», «11 заявок». */
export function count(value: number, forms: Forms): string {
  const n = Math.abs(value) % 100;
  const last = n % 10;
  const form =
    n > 10 && n < 20
      ? forms[2]
      : last === 1
        ? forms[0]
        : last >= 2 && last <= 4
          ? forms[1]
          : forms[2];
  return `${formatNumber(value)} ${form}`;
}
