import { buttonClass, cx } from '@beauty/ui';
import { useId } from 'react';
import styles from './Broadcast.module.css';

/** Кнопка выбора фото (JPEG, PNG, WebP) — для объявления рассылки. */
export function PhotoPicker({
  label,
  disabled,
  onPick,
}: {
  readonly label: string;
  readonly disabled?: boolean;
  readonly onPick: (file: File) => void;
}) {
  const id = useId();
  return (
    <>
      <input
        id={id}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className={styles.fileInput}
        aria-label={`Файл фото для объявления`}
        disabled={disabled}
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = '';
          if (file) onPick(file);
        }}
      />
      <label
        htmlFor={id}
        className={cx(buttonClass({ variant: 'outline' }), disabled && styles.disabled)}
        aria-disabled={disabled || undefined}
      >
        {label}
      </label>
    </>
  );
}
