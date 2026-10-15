import type { SVGProps } from 'react';

/**
 * Иконки из макетов (инлайн SVG, обводка `currentColor`).
 * Декоративные по умолчанию (`aria-hidden`); подпись даёт кнопка-обёртка.
 */
const PATHS = {
  back: <path d="m15 5-7 7 7 7" />,
  forward: <path d="m9 5 7 7-7 7" />,
  chat: <path d="M4 5h16v11H9l-5 4z" />,
  telegram: (
    <>
      <path d="M21 4 3 11l6 2 2 6 3-4 5 4z" />
      <path d="m9 13 8-6" />
    </>
  ),
  sparkle: <path d="M12 3v3M12 18v3M3 12h3M18 12h3M6 6l2 2M16 16l2 2M6 18l2-2M16 8l2-2" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  reschedule: <path d="M4 12a8 8 0 0 1 14-5l2-2v6h-6l2-2a5 5 0 1 0 1 6" />,
  bell: (
    <>
      <path d="M6 8a6 6 0 0 1 12 0c0 7 3 8 3 8H3s3-1 3-8" />
      <path d="M10 20a2 2 0 0 0 4 0" />
    </>
  ),
  calendar: (
    <>
      <rect x="4" y="5" width="16" height="15" rx="2" />
      <path d="M8 3v4M16 3v4M4 10h16" />
    </>
  ),
  mic: (
    <>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </>
  ),
  send: <path d="M5 12h14M13 6l6 6-6 6" />,
  check: <path d="m5 12 5 5 9-10" />,
  lock: (
    <>
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </>
  ),
  eye: (
    <>
      <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  card: (
    <>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <circle cx="9" cy="11" r="2.5" />
      <path d="M5.5 17a3.5 3.5 0 0 1 7 0M15 10h3M15 14h3" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21a8 8 0 0 1 16 0" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M3 20a6 6 0 0 1 12 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6 6 0 0 1 3 6" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M19 12a7 7 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14 3h-4l-.5 2.6a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7 7 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 2 1.2L10 21h4l.5-2.6a7 7 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2z" />
    </>
  ),
  pending: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 8v4l2 2" />
    </>
  ),
  close: <path d="M6 6l12 12M18 6 6 18" />,
  trash: <path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" />,
  retry: <path d="M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6" />,
  offline: (
    <>
      <path d="M2 8.5a15 15 0 0 1 20 0M5 12a10 10 0 0 1 14 0M8.5 15.5a5 5 0 0 1 7 0" />
      <path d="M3 3l18 18" />
    </>
  ),
  home: <path d="M4 11 12 4l8 7v9h-5v-6H9v6H4z" />,
} as const;

/** Имя иконки. */
export type IconName = keyof typeof PATHS | 'play' | 'pause' | 'stop';

/** Свойства иконки. */
export interface IconProps extends Omit<SVGProps<SVGSVGElement>, 'name'> {
  readonly name: IconName;
  readonly size?: number;
  readonly strokeWidth?: number;
}

/** Иконка из набора макетов. */
export function Icon({ name, size = 22, strokeWidth = 1.9, ...rest }: IconProps) {
  const filled = name === 'play' || name === 'pause' || name === 'stop';
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? 'currentColor' : 'none'}
      stroke={filled ? 'none' : 'currentColor'}
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {name === 'play' && <path d="M7 4v16l13-8z" />}
      {name === 'pause' && <path d="M7 4h4v16H7zM13 4h4v16h-4z" />}
      {name === 'stop' && <rect x="6" y="6" width="12" height="12" rx="2" />}
      {!filled && PATHS[name]}
    </svg>
  );
}
