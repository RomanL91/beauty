import styles from './Avatar.module.css';
import { cx } from '../cx';
import { Icon } from './Icon';

/** Инициалы: «Алиса Мельникова» → «А», «Дарья К.» → «ДК». */
export function initialsOf(name: string, max = 2): string {
  return name
    .split(/[\s.]+/)
    .filter((w) => /^\p{L}/u.test(w))
    .slice(0, max)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('');
}

/** Аватар: фото, инициалы или «неизвестный клиент». */
export function Avatar({
  name,
  size = 40,
  src,
  initials,
  display = false,
  anonymous = false,
}: {
  readonly name: string;
  readonly size?: number;
  readonly src?: string | null;
  /** Свои инициалы (иначе — из имени). */
  readonly initials?: string;
  /** Буквы шрифтом Unbounded (как у мастера). */
  readonly display?: boolean;
  /** Без имени — силуэт. */
  readonly anonymous?: boolean;
}) {
  const fontSize = Math.round(size * (display ? 0.36 : 0.33));
  return (
    <span
      className={cx(styles.avatar, display && styles.display, anonymous && styles.muted)}
      style={{ width: size, height: size, fontSize }}
      aria-hidden="true"
    >
      {src ? (
        <img src={src} alt="" />
      ) : anonymous ? (
        <Icon name="user" size={Math.round(size * 0.48)} strokeWidth={1.8} />
      ) : (
        (initials ?? initialsOf(name))
      )}
    </span>
  );
}
