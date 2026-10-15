import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import styles from './Toast.module.css';

/** Уведомление внизу экрана. */
export interface ToastInput {
  readonly text: string;
  readonly action?: { readonly label: string; readonly onClick: () => void };
  /** Мс до скрытия. */
  readonly duration?: number;
}

type Show = (toast: ToastInput) => void;

const ToastContext = createContext<Show | null>(null);

/** Провайдер уведомлений (область `aria-live`). */
export function ToastProvider({ children }: { readonly children: ReactNode }) {
  const [toasts, setToasts] = useState<Array<ToastInput & { id: number }>>([]);
  const seq = useRef(0);
  const show = useCallback<Show>((toast) => {
    seq.current += 1;
    const id = seq.current;
    setToasts((list) => [...list.slice(-2), { ...toast, id }]);
    setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), toast.duration ?? 4000);
  }, []);
  const value = useMemo(() => show, [show]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className={styles.region} role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={styles.toast}>
            <span className={styles.text}>{t.text}</span>
            {t.action && (
              <button type="button" className={styles.action} onClick={t.action.onClick}>
                {t.action.label}
              </button>
            )}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/** Показать уведомление. */
export function useToast(): Show {
  const show = useContext(ToastContext);
  if (!show) throw new Error('useToast вне ToastProvider');
  return show;
}
