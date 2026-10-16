import { ApiError, type MasterSettings, type ProfileInput } from '@beauty/api';
import { Avatar, Button, useOnline } from '@beauty/ui';
import { useRef, useState, type FormEvent } from 'react';
import { TIMEZONES } from '../../entities/settings/model';
import { useSettingsChange } from '../../entities/settings/queries';
import { SelectField, TextArea, TextField } from '../../shared/ui/Field';
import { imageProblem } from './images';
import { FormError, SaveBar, SettingsScreen } from './SettingsScreen';
import styles from './Settings.module.css';

/** «Профиль»: фото, имя и его падежи, специализация, адрес, о себе, часовой пояс. */
export function ProfileSettings() {
  return (
    <SettingsScreen title="Профиль">
      {(settings) => (
        <div className={styles.body}>
          <AvatarCard settings={settings} />
          <ProfileForm settings={settings} />
        </div>
      )}
    </SettingsScreen>
  );
}

function initial({ page }: MasterSettings): ProfileInput {
  return {
    display_name: page.display_name,
    name_forms: { ...page.name_forms },
    specialty: page.specialty,
    address: page.address,
    about: page.about,
    timezone: page.timezone,
  };
}

type Errors = Partial<
  Record<'display_name' | 'nominative' | 'genitive' | 'dative' | 'timezone', string>
>;

function validate(form: ProfileInput): Errors {
  const errors: Errors = {};
  if (!form.display_name.trim()) errors.display_name = 'Как вас покажем клиентам';
  if (!form.name_forms.nominative.trim()) errors.nominative = 'Нужно для сообщений агента';
  if (!form.name_forms.genitive.trim()) errors.genitive = 'Нужно для сообщений агента';
  if (!form.name_forms.dative.trim()) errors.dative = 'Нужно для сообщений агента';
  return errors;
}

function ProfileForm({ settings }: { readonly settings: MasterSettings }) {
  const [form, setForm] = useState(() => initial(settings));
  const [touched, setTouched] = useState(false);
  const save = useSettingsChange(
    (gateway, input: ProfileInput) => gateway.updateProfile(input),
    'Профиль сохранён',
  );
  const errors = touched ? validate(form) : {};
  const serverError = save.error instanceof ApiError ? save.error : null;
  const dirty = JSON.stringify(form) !== JSON.stringify(initial(settings));
  const set = <K extends keyof ProfileInput>(key: K, value: ProfileInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));
  const setName = (key: keyof ProfileInput['name_forms'], value: string) =>
    setForm((f) => ({ ...f, name_forms: { ...f.name_forms, [key]: value } }));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (Object.keys(validate(form)).length > 0) return;
    save.mutate(form, { onSuccess: (next) => setForm(initial(next)) });
  };

  const timezones = TIMEZONES.some((t) => t.id === form.timezone)
    ? TIMEZONES
    : [...TIMEZONES, { id: form.timezone, label: form.timezone }];

  return (
    <form className={styles.form} onSubmit={submit} noValidate aria-label="Профиль">
      <section className={styles.card}>
        <TextField
          label="Имя на странице"
          value={form.display_name}
          maxLength={80}
          autoComplete="name"
          error={errors.display_name}
          onChange={(e) => set('display_name', e.target.value)}
        />
        <TextField
          label="Специализация"
          value={form.specialty}
          maxLength={120}
          placeholder="Косметолог · массаж"
          onChange={(e) => set('specialty', e.target.value)}
        />
        <TextField
          label="Адрес"
          value={form.address}
          maxLength={200}
          autoComplete="street-address"
          hint="Агент называет его клиентам после записи"
          onChange={(e) => set('address', e.target.value)}
        />
        <TextArea
          label="О себе"
          value={form.about}
          maxLength={2000}
          rows={6}
          hint={`${form.about.length} из 2000`}
          onChange={(e) => set('about', e.target.value)}
        />
      </section>

      <section className={styles.card} aria-labelledby="name-forms">
        <div>
          <h2 id="name-forms" className={styles.cardTitle}>
            Как агент называет вас
          </h2>
          <p className={styles.muted}>
            «{form.name_forms.nominative || 'Алиса'} подтвердит запись», «запись к{' '}
            {form.name_forms.dative || 'Алисе'}»
          </p>
        </div>
        <TextField
          label="Кто?"
          value={form.name_forms.nominative}
          maxLength={40}
          error={errors.nominative}
          onChange={(e) => setName('nominative', e.target.value)}
        />
        <div className={styles.pair}>
          <TextField
            label="Кого? (нет …)"
            value={form.name_forms.genitive}
            maxLength={40}
            error={errors.genitive}
            onChange={(e) => setName('genitive', e.target.value)}
          />
          <TextField
            label="Кому? (к …)"
            value={form.name_forms.dative}
            maxLength={40}
            error={errors.dative}
            onChange={(e) => setName('dative', e.target.value)}
          />
        </div>
        <SelectField
          label="Часовой пояс"
          value={form.timezone}
          options={timezones.map((t) => ({ value: t.id, label: t.label }))}
          hint="По нему считаются окна записи и напоминания"
          error={serverError?.code === 'invalid_timezone' ? serverError.message : null}
          onChange={(e) => set('timezone', e.target.value)}
        />
      </section>

      <FormError
        text={serverError && serverError.code !== 'invalid_timezone' ? serverError.message : null}
      />
      <SaveBar dirty={dirty} saving={save.isPending} />
    </form>
  );
}

function AvatarCard({ settings }: { readonly settings: MasterSettings }) {
  const input = useRef<HTMLInputElement>(null);
  const online = useOnline();
  const [problem, setProblem] = useState<string | null>(null);
  const upload = useSettingsChange(
    (gateway, file: File) => gateway.setAvatar(file),
    'Фото обновлено',
  );
  const remove = useSettingsChange((gateway) => gateway.removeAvatar(), 'Фото убрано');
  const { page } = settings;
  const busy = upload.isPending || remove.isPending;

  return (
    <section className={styles.card} aria-labelledby="avatar">
      <h2 id="avatar" className={styles.cardTitle}>
        Фото профиля
      </h2>
      <div className={styles.avatarRow}>
        <Avatar name={page.display_name} src={page.avatar_url} size={72} display />
        <div className={styles.actions}>
          <Button
            variant="outline"
            disabled={busy || !online}
            onClick={() => input.current?.click()}
          >
            {upload.isPending ? 'Загружаем…' : page.avatar_url ? 'Заменить' : 'Загрузить'}
          </Button>
          {page.avatar_url && (
            <Button
              variant="ghost"
              disabled={busy || !online}
              onClick={() => remove.mutate(undefined)}
            >
              Убрать
            </Button>
          )}
        </div>
      </div>
      <input
        ref={input}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className={styles.fileInput}
        aria-label="Файл фото профиля"
        tabIndex={-1}
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = '';
          if (!file) return;
          const issue = imageProblem(file);
          setProblem(issue);
          if (!issue) upload.mutate(file);
        }}
      />
      <FormError text={problem} />
    </section>
  );
}
