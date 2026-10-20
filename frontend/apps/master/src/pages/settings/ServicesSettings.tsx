import { ApiError, type MasterSettings, type Service, type ServiceInput } from '@beauty/api';
import {
  Button,
  Icon,
  SelectField,
  Sheet,
  StateView,
  TextArea,
  TextField,
  formatMinutes,
  formatMoney,
  useOnline,
} from '@beauty/ui';
import { useState, type FormEvent } from 'react';
import { parseTenge, tengeText } from '../../entities/settings/model';
import { useSettingsChange } from '../../entities/settings/queries';
import { FormError, SettingsScreen } from './SettingsScreen';
import styles from './Settings.module.css';

const DURATIONS = Array.from({ length: 96 }, (_, i) => (i + 1) * 5);

type Editing = { readonly kind: 'new' } | { readonly kind: 'edit'; readonly service: Service };

/** «Услуги»: список, добавление и правка в нижнем листе, удаление в архив. */
export function ServicesSettings() {
  const [editing, setEditing] = useState<Editing | null>(null);
  const online = useOnline();
  return (
    <SettingsScreen title="Услуги">
      {(settings) => (
        <div className={styles.body}>
          {settings.page.services.length === 0 ? (
            <StateView
              icon="card"
              title="Пока нет услуг"
              text="Без услуг страницу не опубликовать: клиенту не на что записаться."
            />
          ) : (
            <ul className={styles.services} aria-label="Услуги">
              {settings.page.services.map((service) => (
                <li key={service.id}>
                  <button
                    type="button"
                    className={styles.service}
                    onClick={() => setEditing({ kind: 'edit', service })}
                  >
                    <span className={styles.grow}>
                      <span className={styles.strong} style={{ display: 'block' }}>
                        {service.title}
                      </span>
                      <span className={styles.muted}>
                        {formatMinutes(service.duration_min)} · {formatMoney(service.price)}
                      </span>
                    </span>
                    <Icon name="forward" size={18} strokeWidth={2} className={styles.chevron} />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <Button
            variant="outline"
            size="lg"
            block
            disabled={!online}
            onClick={() => setEditing({ kind: 'new' })}
          >
            Добавить услугу
          </Button>
          <Sheet
            open={editing !== null}
            title={editing?.kind === 'edit' ? 'Услуга' : 'Новая услуга'}
            onClose={() => setEditing(null)}
          >
            {editing && (
              <ServiceForm
                key={editing.kind === 'edit' ? editing.service.id : 'new'}
                editing={editing}
                settings={settings}
                onDone={() => setEditing(null)}
              />
            )}
          </Sheet>
        </div>
      )}
    </SettingsScreen>
  );
}

function ServiceForm({
  editing,
  settings,
  onDone,
}: {
  readonly editing: Editing;
  readonly settings: MasterSettings;
  readonly onDone: () => void;
}) {
  const current = editing.kind === 'edit' ? editing.service : null;
  const [title, setTitle] = useState(current?.title ?? '');
  const [description, setDescription] = useState(current?.description ?? '');
  const [duration, setDuration] = useState(current?.duration_min ?? 60);
  const [price, setPrice] = useState(tengeText(current?.price ?? null));
  const [touched, setTouched] = useState(false);
  const online = useOnline();

  const save = useSettingsChange(
    (gateway, input: ServiceInput) =>
      current ? gateway.updateService(current.id, input) : gateway.addService(input),
    current ? 'Услуга сохранена' : 'Услуга добавлена',
  );
  const archive = useSettingsChange(
    (gateway, id: string) => gateway.archiveService(id),
    'Услуга убрана',
  );

  const parsedPrice = parseTenge(price);
  const titleError = touched && !title.trim() ? 'Как услуга называется у вас в прайсе' : null;
  const priceError = touched && parsedPrice === undefined ? 'Сумма в тенге, например 12000' : null;
  const error = save.error instanceof ApiError ? save.error : null;
  const lastOne = settings.status === 'published' && settings.page.services.length === 1;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (!title.trim() || parsedPrice === undefined) return;
    save.mutate(
      {
        title: title.trim(),
        description: description.trim(),
        duration_min: duration,
        price: parsedPrice,
      },
      { onSuccess: onDone },
    );
  };

  return (
    <form className={styles.sheetForm} onSubmit={submit} noValidate>
      <TextField
        label="Название"
        value={title}
        maxLength={120}
        error={titleError}
        onChange={(e) => setTitle(e.target.value)}
      />
      <div className={styles.pair}>
        <SelectField
          label="Длительность"
          value={duration}
          options={DURATIONS.map((m) => ({ value: m, label: formatMinutes(m) }))}
          error={error?.code === 'invalid_service_duration' ? error.message : null}
          onChange={(e) => setDuration(Number(e.target.value))}
        />
        <TextField
          label="Цена, ₸"
          value={price}
          inputMode="decimal"
          placeholder="по запросу"
          error={priceError ?? (error?.code === 'invalid_money' ? error.message : null)}
          onChange={(e) => setPrice(e.target.value)}
        />
      </div>
      <p className={styles.muted}>Без цены клиент увидит «цена по запросу».</p>
      <TextArea
        label="Описание"
        value={description}
        maxLength={1000}
        rows={4}
        placeholder="Для кого, как проходит, сколько процедур в курсе, противопоказания"
        hint="Клиент увидит его на странице, ИИ-администратор отвечает по нему на вопросы."
        onChange={(e) => setDescription(e.target.value)}
      />
      <FormError
        text={
          error && !['invalid_service_duration', 'invalid_money'].includes(error.code)
            ? error.message
            : null
        }
      />
      <Button type="submit" size="lg" block disabled={save.isPending || !online}>
        {save.isPending ? 'Сохраняем…' : current ? 'Сохранить' : 'Добавить'}
      </Button>
      {current && (
        <>
          <Button
            variant="ghost"
            block
            disabled={archive.isPending || !online || lastOne}
            onClick={() => archive.mutate(current.id, { onSuccess: onDone })}
          >
            <Icon name="trash" size={18} /> Убрать услугу
          </Button>
          <p className={styles.muted}>
            {lastOne
              ? 'Это последняя услуга опубликованной страницы — сначала добавьте другую.'
              : 'Записи на эту услугу сохранятся, новых не будет.'}
          </p>
        </>
      )}
    </form>
  );
}
