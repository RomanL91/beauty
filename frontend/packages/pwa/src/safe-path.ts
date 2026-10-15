/** Только внутренний путь (уведомление не должно уводить на чужой сайт). */
export function safePath(url: string | undefined): string {
  return url && url.startsWith('/') && !url.startsWith('//') ? url : '/';
}
