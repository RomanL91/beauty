import { useEffect, useId, useRef, type ReactNode } from 'react';
import styles from './Sheet.module.css';
import { IconButton } from './Button';
import { Icon } from './Icon';

/**
 * Нижний лист на нативном `<dialog>`: фокус-ловушка, Escape и фон — от браузера.
 */
export function Sheet({
  open,
  title,
  onClose,
  children,
}: {
  readonly open: boolean;
  readonly title: string;
  readonly onClose: () => void;
  readonly children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      if (typeof dialog.showModal === 'function') dialog.showModal();
      else dialog.setAttribute('open', '');
    } else if (!open && dialog.open) {
      if (typeof dialog.close === 'function') dialog.close();
      else dialog.removeAttribute('open');
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      className={styles.sheet}
      aria-labelledby={titleId}
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      {open && (
        <div className={styles.inner}>
          <span className={styles.grabber} aria-hidden="true" />
          <div className={styles.head}>
            <h2 id={titleId} className={styles.title}>
              {title}
            </h2>
            <IconButton label="Закрыть" onClick={onClose}>
              <Icon name="close" strokeWidth={2} />
            </IconButton>
          </div>
          {children}
        </div>
      )}
    </dialog>
  );
}
