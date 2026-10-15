import type { ButtonHTMLAttributes, ReactNode } from 'react';
import styles from './Button.module.css';
import { cx } from '../cx';

/** Вариант кнопки из макетов. */
export type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'soft' | 'telegram' | 'ghost';

/** Параметры внешнего вида кнопки — общие для `<button>` и ссылок. */
export interface ButtonLook {
  readonly variant?: ButtonVariant;
  /** `md` — 44 px, `lg` — 52 px (CTA), `xl` — 54 px. */
  readonly size?: 'md' | 'lg' | 'xl';
  readonly block?: boolean;
}

/** Классы кнопки — чтобы оформить `<Link>` роутера как кнопку. */
export function buttonClass({
  variant = 'primary',
  size = 'md',
  block = false,
}: ButtonLook = {}): string {
  return cx(styles.button, styles[variant], size !== 'md' && styles[size], block && styles.block);
}

/** Кнопка. */
export function Button({
  variant,
  size,
  block,
  className,
  type = 'button',
  ...rest
}: ButtonLook & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type={type}
      className={cx(buttonClass({ variant, size, block }), className)}
      {...rest}
    />
  );
}

/** Круглая кнопка-иконка 44×44; подпись обязательна. */
export function IconButton({
  label,
  look = 'plain',
  className,
  children,
  type = 'button',
  ...rest
}: {
  readonly label: string;
  readonly look?: 'plain' | 'outlined' | 'accent';
  readonly children: ReactNode;
} & Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'aria-label'>) {
  return (
    <button
      type={type}
      aria-label={label}
      className={cx(
        styles.iconButton,
        look === 'outlined' && styles.iconButtonOutlined,
        look === 'accent' && styles.iconButtonAccent,
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

/** Классы круглой кнопки-иконки — для ссылок «Назад». */
export function iconButtonClass(look: 'plain' | 'outlined' | 'accent' = 'plain'): string {
  return cx(
    styles.iconButton,
    look === 'outlined' && styles.iconButtonOutlined,
    look === 'accent' && styles.iconButtonAccent,
  );
}
