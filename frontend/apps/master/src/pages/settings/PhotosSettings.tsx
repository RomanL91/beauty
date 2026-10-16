import type { MasterSettings } from '@beauty/api';
import { Button, Icon, StateView, useOnline } from '@beauty/ui';
import { useRef, useState } from 'react';
import { useSettingsChange } from '../../entities/settings/queries';
import { imageProblem } from './images';
import { FormError, SettingsScreen } from './SettingsScreen';
import styles from './Settings.module.css';

const MAX_PHOTOS = 30;

/** «Фото работ»: сетка, загрузка (несколько файлов подряд), удаление. */
export function PhotosSettings() {
  return (
    <SettingsScreen title="Фото работ">
      {(settings) => (
        <div className={styles.body}>
          <Photos settings={settings} />
        </div>
      )}
    </SettingsScreen>
  );
}

function Photos({ settings }: { readonly settings: MasterSettings }) {
  const input = useRef<HTMLInputElement>(null);
  const online = useOnline();
  const [problem, setProblem] = useState<string | null>(null);
  const [uploading, setUploading] = useState(0);
  const add = useSettingsChange((gateway, file: File) => gateway.addPhoto(file, ''));
  const remove = useSettingsChange((gateway, id: string) => gateway.removePhoto(id), 'Фото убрано');
  const { photos } = settings.page;
  const left = MAX_PHOTOS - photos.length;

  const upload = async (files: File[]) => {
    const bad = files.map(imageProblem).find(Boolean) ?? null;
    const good = files.filter((f) => !imageProblem(f)).slice(0, left);
    setProblem(
      bad ?? (files.length > left ? `Можно добавить ещё ${left} — лишние пропущены` : null),
    );
    setUploading(good.length);
    for (const file of good) {
      try {
        await add.mutateAsync(file);
      } catch {
        break; // тост уже показан
      } finally {
        setUploading((n) => Math.max(0, n - 1));
      }
    }
  };

  return (
    <>
      <p className={styles.muted}>
        Клиенты видят фото на странице — лучшие работы в начале. JPEG, PNG или WebP до 8 МБ,
        {` ${photos.length} из ${MAX_PHOTOS}`}.
      </p>
      {photos.length === 0 && uploading === 0 ? (
        <StateView
          icon="eye"
          title="Пока нет фото"
          text="Страница с работами вызывает больше доверия."
        />
      ) : (
        <ul className={styles.grid} aria-label="Фото работ">
          {photos.map((photo, index) => (
            <li key={photo.id} className={styles.photo}>
              <img src={photo.url} alt={photo.alt || `Работа ${index + 1}`} loading="lazy" />
              <button
                type="button"
                className={styles.photoRemove}
                aria-label={`Убрать фото ${index + 1}`}
                disabled={remove.isPending || !online}
                onClick={() => remove.mutate(photo.id)}
              >
                <Icon name="trash" size={18} strokeWidth={2} />
              </button>
            </li>
          ))}
          {Array.from({ length: uploading }, (_, i) => (
            <li key={`uploading-${i}`} className={styles.photo} aria-label="Загружается" />
          ))}
        </ul>
      )}
      <FormError text={problem} />
      <Button
        size="lg"
        block
        disabled={!online || left <= 0 || uploading > 0}
        onClick={() => input.current?.click()}
      >
        {uploading > 0 ? 'Загружаем…' : 'Добавить фото'}
      </Button>
      <input
        ref={input}
        type="file"
        multiple
        accept="image/jpeg,image/png,image/webp"
        className={styles.fileInput}
        aria-label="Файлы фото работ"
        tabIndex={-1}
        onChange={(e) => {
          const files = [...(e.target.files ?? [])];
          e.target.value = '';
          if (files.length > 0) void upload(files);
        }}
      />
    </>
  );
}
