/**
 * @beauty/ui — токены, шрифты и базовые компоненты по макетам.
 *
 * Стили подключаются один раз в точке входа приложения:
 * `import '@beauty/ui/styles.css'`.
 */
export { cx } from './cx';
export { Icon, type IconName, type IconProps } from './components/Icon';
export {
  Button,
  IconButton,
  buttonClass,
  iconButtonClass,
  type ButtonLook,
  type ButtonVariant,
} from './components/Button';
export { Avatar, initialsOf } from './components/Avatar';
export { Skeleton } from './components/Skeleton';
export { Notice } from './components/Notice';
export { StateView, ErrorState } from './components/StateView';
export { OfflineBanner } from './components/OfflineBanner';
export { ToastProvider, useToast, type ToastInput } from './components/Toast';
export { AppShell } from './components/AppShell';
export { VisuallyHidden, visuallyHiddenStyle } from './components/VisuallyHidden';
export { Waveform } from './components/Waveform';
export { Badge } from './components/Badge';
export { useOnline } from './hooks/useOnline';
export { useNow } from './hooks/useNow';
