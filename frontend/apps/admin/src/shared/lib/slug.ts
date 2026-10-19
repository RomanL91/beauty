const MAP: Record<string, string> = {
  а: 'a',
  б: 'b',
  в: 'v',
  г: 'g',
  д: 'd',
  е: 'e',
  ё: 'e',
  ж: 'zh',
  з: 'z',
  и: 'i',
  й: 'y',
  к: 'k',
  л: 'l',
  м: 'm',
  н: 'n',
  о: 'o',
  п: 'p',
  р: 'r',
  с: 's',
  т: 't',
  у: 'u',
  ф: 'f',
  х: 'h',
  ц: 'ts',
  ч: 'ch',
  ш: 'sh',
  щ: 'sch',
  ъ: '',
  ы: 'y',
  ь: '',
  э: 'e',
  ю: 'yu',
  я: 'ya',
  ә: 'a',
  ғ: 'g',
  қ: 'k',
  ң: 'n',
  ө: 'o',
  ұ: 'u',
  ү: 'u',
  һ: 'h',
  і: 'i',
};

/** Адрес страницы из имени: «Дана Ахметова» → «dana». Первое слово, латиницей. */
export function slugOf(name: string): string {
  const first = name.trim().toLowerCase().split(/\s+/)[0] ?? '';
  const latin = [...first].map((ch) => MAP[ch] ?? ch).join('');
  return latin
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40);
}

/** Подходит ли адрес: латиница, цифры, дефис; 2–40 символов. */
export function isSlug(value: string): boolean {
  return /^[a-z0-9-]{2,40}$/.test(value);
}

/** Телефон для API: «+7 701 123-45-67» → «+77011234567»; пусто — `null`; неверный — `undefined`. */
export function parsePhone(value: string): string | null | undefined {
  const digits = value.replace(/\D/g, '');
  if (digits === '') return null;
  const normalized =
    digits.length === 11 && digits.startsWith('8') ? `7${digits.slice(1)}` : digits;
  return /^7\d{10}$/.test(normalized) ? `+${normalized}` : undefined;
}
