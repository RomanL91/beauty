import type { CSSProperties } from 'react';
import styles from './Skeleton.module.css';

/** Скелетон-заглушка на время загрузки. */
export function Skeleton({
  width = '100%',
  height = 16,
  radius = 8,
  style,
}: {
  readonly width?: CSSProperties['width'];
  readonly height?: CSSProperties['height'];
  readonly radius?: CSSProperties['borderRadius'];
  readonly style?: CSSProperties;
}) {
  return (
    <span
      className={styles.skeleton}
      style={{ width, height, borderRadius: radius, ...style }}
      aria-hidden="true"
    />
  );
}
