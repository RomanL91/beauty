import { useId, useLayoutEffect, useRef, useState } from 'react';
import { count, formatDay, formatNumber, type Forms } from '../shared/lib/format';
import styles from './BarChart.module.css';
import { niceTicks } from './scale';

export interface BarPoint {
  /** День `YYYY-MM-DD`. */
  readonly date: string;
  readonly value: number;
}

const HEIGHT = 168;
const PAD = { top: 12, right: 8, bottom: 24, left: 36 };
const MAX_BAR = 24;

function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return undefined;
    setWidth(Math.max(240, node.clientWidth || 600));
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.max(240, Math.round(entry.contentRect.width)));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

/**
 * Столбцы по дням — один ряд (легенда не нужна: что на графике, говорит заголовок).
 * Наведение — подсказка со значением; «Таблица» — те же данные текстом.
 */
export function BarChart({
  title,
  points,
  unit,
}: {
  readonly title: string;
  readonly points: readonly BarPoint[];
  /** Единица в трёх формах: «заявка», «заявки», «заявок». */
  readonly unit: Forms;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const titleId = useId();
  const ticks = niceTicks(Math.max(0, ...points.map((p) => p.value)));
  const top = ticks.at(-1) ?? 1;
  const plotW = width - PAD.left - PAD.right;
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const band = plotW / Math.max(1, points.length);
  const bar = Math.max(2, Math.min(MAX_BAR, band - 2));
  const y = (v: number) => PAD.top + plotH - (v / top) * plotH;
  const labelEvery = Math.max(1, Math.ceil(points.length / 6));
  const total = points.reduce((sum, p) => sum + p.value, 0);
  const active = hover === null ? null : points[hover];

  return (
    <figure className={styles.figure} aria-labelledby={titleId}>
      <figcaption className={styles.caption}>
        <span id={titleId} className={styles.title}>
          {title}
        </span>
        <span className={styles.total}>
          {count(total, unit)} за {points.length} дн.
        </span>
        <button type="button" className={styles.toggle} onClick={() => setTable((t) => !t)}>
          {table ? 'График' : 'Таблица'}
        </button>
      </figcaption>
      {table ? (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>День</th>
                <th>Сколько</th>
              </tr>
            </thead>
            <tbody>
              {points.map((p) => (
                <tr key={p.date}>
                  <td>{formatDay(p.date)}</td>
                  <td>{formatNumber(p.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div ref={ref} className={styles.plot} onMouseLeave={() => setHover(null)}>
          {width > 0 && (
            <svg
              width={width}
              height={HEIGHT}
              role="img"
              aria-label={`${title}: ${formatNumber(total)}`}
            >
              {ticks.map((t) => (
                <g key={t}>
                  <line
                    x1={PAD.left}
                    x2={width - PAD.right}
                    y1={y(t)}
                    y2={y(t)}
                    className={styles.grid}
                  />
                  <text
                    x={PAD.left - 8}
                    y={y(t)}
                    className={styles.tick}
                    textAnchor="end"
                    dominantBaseline="middle"
                  >
                    {formatNumber(t)}
                  </text>
                </g>
              ))}
              {points.map((p, i) => {
                const x = PAD.left + i * band + (band - bar) / 2;
                const top = y(p.value);
                const base = y(0);
                const r = Math.min(4, bar / 2, base - top);
                const path =
                  p.value <= 0
                    ? ''
                    : `M${x},${base}V${top + r}Q${x},${top} ${x + r},${top}H${x + bar - r}Q${x + bar},${top} ${x + bar},${top + r}V${base}Z`;
                return (
                  <g key={p.date}>
                    {path && (
                      <path d={path} className={hover === i ? styles.barActive : styles.bar} />
                    )}
                    <rect
                      x={PAD.left + i * band}
                      y={PAD.top}
                      width={band}
                      height={plotH}
                      className={styles.hit}
                      onMouseEnter={() => setHover(i)}
                    />
                    {i % labelEvery === 0 && (
                      <text
                        x={x + bar / 2}
                        y={HEIGHT - 6}
                        className={styles.tick}
                        textAnchor="middle"
                      >
                        {formatDay(p.date)}
                      </text>
                    )}
                  </g>
                );
              })}
            </svg>
          )}
          {active && hover !== null && (
            <div
              className={styles.tooltip}
              style={{
                left: Math.min(width - 120, Math.max(0, PAD.left + hover * band + band / 2 - 60)),
                top: Math.max(0, y(active.value) - 52),
              }}
              role="status"
            >
              <span className={styles.tooltipDay}>{formatDay(active.date)}</span>
              <strong>{count(active.value, unit)}</strong>
            </div>
          )}
        </div>
      )}
    </figure>
  );
}
