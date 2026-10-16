/** Форматы и размер фото, которые принимает сервер. */
export const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'] as const;
export const MAX_IMAGE_BYTES = 8 * 1024 * 1024;

/** Почему файл не подходит (или `null`) — проверка до загрузки. */
export function imageProblem(file: Blob): string | null {
  if (!(IMAGE_TYPES as readonly string[]).includes(file.type))
    return 'Нужна картинка JPEG, PNG или WebP';
  if (file.size > MAX_IMAGE_BYTES) return 'Фото больше 8 МБ — уменьшите его и попробуйте снова';
  return null;
}
