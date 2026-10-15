import { useRef, useState, type ReactNode } from 'react';

/** Сдвиг влево (px), после которого отпускание отменяет запись. */
const CANCEL_SHIFT = 80;

/**
 * Кнопка «удерживайте и говорите»: нажатие начинает запись, отпускание —
 * заканчивает, свайп влево перед отпусканием — отменяет. С клавиатуры:
 * удерживать Пробел/Enter, Escape — отмена.
 */
export function HoldToRecord({
  label,
  className,
  recording,
  onStart,
  onStop,
  onCancel,
  onCancelArmedChange,
  children,
}: {
  readonly label: string;
  readonly className?: string;
  readonly recording: boolean;
  readonly onStart: () => void;
  readonly onStop: () => void;
  readonly onCancel: () => void;
  readonly onCancelArmedChange?: (armed: boolean) => void;
  readonly children: ReactNode;
}) {
  const origin = useRef<number | null>(null);
  const [armed, setArmed] = useState(false);

  const arm = (value: boolean) => {
    setArmed(value);
    onCancelArmedChange?.(value);
  };
  const end = (cancel: boolean) => {
    if (origin.current === null) return;
    origin.current = null;
    arm(false);
    if (cancel) onCancel();
    else onStop();
  };

  return (
    <button
      type="button"
      className={className}
      aria-label={label}
      aria-pressed={recording}
      data-cancel-armed={armed || undefined}
      style={{ touchAction: 'none', userSelect: 'none', WebkitUserSelect: 'none' }}
      onContextMenu={(e) => e.preventDefault()}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        e.currentTarget.setPointerCapture(e.pointerId);
        origin.current = e.clientX;
        onStart();
      }}
      onPointerMove={(e) => {
        if (origin.current === null) return;
        const shouldArm = e.clientX - origin.current < -CANCEL_SHIFT;
        if (shouldArm !== armed) arm(shouldArm);
      }}
      onPointerUp={() => end(armed)}
      onPointerCancel={() => end(true)}
      onKeyDown={(e) => {
        if ((e.key === ' ' || e.key === 'Enter') && !e.repeat && origin.current === null) {
          e.preventDefault();
          origin.current = 0;
          onStart();
        } else if (e.key === 'Escape') {
          end(true);
        }
      }}
      onKeyUp={(e) => {
        if (e.key === ' ' || e.key === 'Enter') {
          e.preventDefault();
          end(false);
        }
      }}
      onBlur={() => end(true)}
    >
      {children}
    </button>
  );
}
