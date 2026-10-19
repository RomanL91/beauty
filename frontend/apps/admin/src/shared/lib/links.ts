/** Адрес страницы мастера: рядом с панелью (`admin.<домен>` → `<slug>.<домен>`). */
export function pageUrl(slug: string, location: { protocol: string; host: string }): string {
  const { protocol, host } = location;
  if (host.startsWith('admin.')) return `${protocol}//${slug}.${host.slice('admin.'.length)}/`;
  return `https://${slug}.beautiful.kz/`;
}
