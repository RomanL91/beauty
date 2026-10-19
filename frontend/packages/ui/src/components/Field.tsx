import { cx } from '../cx';
import {
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react';
import styles from './Field.module.css';

interface FieldProps {
  readonly label: string;
  readonly hint?: ReactNode;
  readonly error?: string | null;
}

/** Поле формы: подпись, подсказка и ошибка связаны с вводом (`aria-describedby`). */
function Field({
  label,
  hint,
  error,
  children,
}: FieldProps & { readonly children: (ids: Ids) => ReactNode }) {
  const id = useId();
  const ids: Ids = {
    id,
    describedBy:
      [hint ? `${id}-hint` : '', error ? `${id}-error` : ''].join(' ').trim() || undefined,
    invalid: Boolean(error),
  };
  return (
    <div className={styles.field}>
      <label htmlFor={id} className={styles.label}>
        {label}
      </label>
      {children(ids)}
      {hint && !error && (
        <p id={`${id}-hint`} className={styles.hint}>
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className={styles.error} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

interface Ids {
  readonly id: string;
  readonly describedBy: string | undefined;
  readonly invalid: boolean;
}

/** Однострочное поле. */
export function TextField({
  label,
  hint,
  error,
  className,
  ...input
}: FieldProps & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <Field label={label} hint={hint} error={error}>
      {(ids) => (
        <input
          id={ids.id}
          aria-describedby={ids.describedBy}
          aria-invalid={ids.invalid || undefined}
          className={cx(styles.input, className)}
          {...input}
        />
      )}
    </Field>
  );
}

/** Многострочное поле. */
export function TextArea({
  label,
  hint,
  error,
  className,
  ...input
}: FieldProps & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <Field label={label} hint={hint} error={error}>
      {(ids) => (
        <textarea
          id={ids.id}
          aria-describedby={ids.describedBy}
          aria-invalid={ids.invalid || undefined}
          className={cx(styles.input, styles.textarea, className)}
          {...input}
        />
      )}
    </Field>
  );
}

/** Выбор из списка. */
export function SelectField({
  label,
  hint,
  error,
  className,
  options,
  ...select
}: FieldProps &
  SelectHTMLAttributes<HTMLSelectElement> & {
    readonly options: ReadonlyArray<{ readonly value: string | number; readonly label: string }>;
  }) {
  return (
    <Field label={label} hint={hint} error={error}>
      {(ids) => (
        <select
          id={ids.id}
          aria-describedby={ids.describedBy}
          aria-invalid={ids.invalid || undefined}
          className={cx(styles.input, styles.select, className)}
          {...select}
        >
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
}

/** Переключатель (чекбокс в виде тумблера). */
export function Toggle({
  label,
  checked,
  onChange,
  disabled,
}: {
  readonly label: string;
  readonly checked: boolean;
  readonly onChange: (checked: boolean) => void;
  readonly disabled?: boolean;
}) {
  return (
    <label className={styles.toggle}>
      <span>{label}</span>
      <input
        type="checkbox"
        role="switch"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
    </label>
  );
}
