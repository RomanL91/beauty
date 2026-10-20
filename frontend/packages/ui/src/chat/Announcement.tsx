import { Icon } from '../components/Icon';
import styles from './Announcement.module.css';

/**
 * Объявление мастера из рассылки: метка, фото (если есть) и текст. Внутри пузыря
 * `layout="flush"` — фото во всю ширину карточки.
 */
export function Announcement({
  label,
  text,
  photoUrl,
}: {
  /** «Объявление от Алисы». */
  readonly label: string;
  readonly text: string;
  readonly photoUrl: string | null;
}) {
  return (
    <div className={styles.card}>
      {photoUrl && <img className={styles.photo} src={photoUrl} alt="" loading="lazy" />}
      <div className={styles.body}>
        <span className={styles.label}>
          <Icon name="bell" size={14} strokeWidth={2} />
          {label}
        </span>
        <span className={styles.text}>{text}</span>
      </div>
    </div>
  );
}
