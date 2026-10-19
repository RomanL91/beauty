import type { AdminMasterInput, MasterStatus } from '@beauty/api';
import {
  Button,
  ErrorState,
  Notice,
  SelectField,
  Sheet,
  Skeleton,
  TextField,
  useOnline,
} from '@beauty/ui';
import { useDeferredValue, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router';
import { formatDateTime, formatNumber, formatPhone } from '../shared/lib/format';
import { useMasterAction, useMasters } from '../shared/lib/queries';
import { errorText } from '../shared/lib/session';
import { isSlug, parsePhone, slugOf } from '../shared/lib/slug';
import ui from '../shared/ui.module.css';
import { AgentBadge, StatusBadge } from '../widgets/badges';

const FILTERS: Array<{ id: MasterStatus | null; label: string }> = [
  { id: null, label: 'Все' },
  { id: 'published', label: 'Опубликованы' },
  { id: 'draft', label: 'Черновики' },
];

/** Мастера: поиск, фильтр, заведение нового. */
export function MastersPage() {
  const [q, setQ] = useState('');
  const [status, setStatus] = useState<MasterStatus | null>(null);
  const [creating, setCreating] = useState(false);
  const query = useDeferredValue(q.trim());
  const masters = useMasters(query, status);
  const online = useOnline();

  return (
    <div className={ui.page}>
      <header className={ui.header}>
        <div>
          <h1 className={ui.h1}>Мастера</h1>
          <p className={ui.muted}>Страницы мастеров, владельцы и ИИ-администратор.</p>
        </div>
        <Button onClick={() => setCreating(true)} disabled={!online}>
          Завести мастера
        </Button>
      </header>
      <div className={ui.toolbar}>
        <input
          type="search"
          className={ui.search}
          placeholder="Адрес, имя или телефон владельца"
          aria-label="Поиск мастеров"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <div className={ui.chips} role="group" aria-label="Статус">
          {FILTERS.map((f) => (
            <button
              key={f.label}
              type="button"
              className={ui.chip}
              aria-pressed={status === f.id}
              onClick={() => setStatus(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>
      {masters.data ? (
        masters.data.length === 0 ? (
          <div className={ui.tableWrap}>
            <p className={ui.empty}>Никого не нашли.</p>
          </div>
        ) : (
          <div className={ui.tableWrap}>
            <table className={ui.table}>
              <thead>
                <tr>
                  <th>Мастер</th>
                  <th>Статус</th>
                  <th>ИИ-администратор</th>
                  <th>Владелец</th>
                  <th className={ui.num}>Услуги</th>
                  <th className={ui.num}>Заявки, 30 дн.</th>
                  <th>Активность</th>
                </tr>
              </thead>
              <tbody>
                {masters.data.map((m) => (
                  <tr key={m.id}>
                    <td>
                      <Link to={`/masters/${m.id}`} className={ui.rowLink}>
                        {m.display_name}
                      </Link>
                      <div className={ui.muted}>
                        {m.slug}
                        {m.specialty ? ` · ${m.specialty}` : ''}
                      </div>
                    </td>
                    <td>
                      <StatusBadge status={m.status} />
                    </td>
                    <td>
                      <AgentBadge state={m.agent} />
                    </td>
                    <td>{formatPhone(m.owner_phone)}</td>
                    <td className={ui.num}>{formatNumber(m.services)}</td>
                    <td className={ui.num}>{formatNumber(m.appointments_30d)}</td>
                    <td>{formatDateTime(m.last_activity_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : masters.isError ? (
        <ErrorState offline={!online} onRetry={() => void masters.refetch()} />
      ) : (
        <Skeleton height={240} radius={18} />
      )}
      <Sheet open={creating} title="Новый мастер" onClose={() => setCreating(false)}>
        {creating && <NewMasterForm onDone={() => setCreating(false)} />}
      </Sheet>
    </div>
  );
}

const TIMEZONES = [
  { value: 'Asia/Almaty', label: 'Астана, Алматы (UTC+5)' },
  { value: 'Asia/Aqtobe', label: 'Актобе (UTC+5)' },
  { value: 'Asia/Oral', label: 'Уральск (UTC+5)' },
];

function NewMasterForm({ onDone }: { readonly onDone: () => void }) {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [slugTouched, setSlugTouched] = useState(false);
  const [forms, setForms] = useState({ nominative: '', genitive: '', dative: '' });
  const [specialty, setSpecialty] = useState('');
  const [timezone, setTimezone] = useState('Asia/Almaty');
  const [phone, setPhone] = useState('');
  const [touched, setTouched] = useState(false);
  const create = useMasterAction(
    (api, input: AdminMasterInput) => api.createMaster(input),
    'Мастер заведён — страница в черновике',
  );
  const address = slugTouched ? slug : slugOf(name);
  const owner = parsePhone(phone);
  const nominative = forms.nominative || name.trim().split(/\s+/)[0] || '';
  const errors = {
    name: touched && !name.trim() ? 'Как мастера увидят клиенты' : null,
    slug: touched && !isSlug(address) ? 'Латиница, цифры и дефис, 2–40 символов' : null,
    genitive: touched && !forms.genitive.trim() ? 'Нужно агенту: «нет Даны»' : null,
    dative: touched && !forms.dative.trim() ? 'Нужно агенту: «запись к Дане»' : null,
    phone: touched && owner === undefined ? 'Телефон в формате +7 701 123 45 67' : null,
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (!name.trim() || !isSlug(address) || !forms.genitive.trim() || !forms.dative.trim()) return;
    if (owner === undefined) return;
    create.mutate(
      {
        slug: address,
        display_name: name.trim(),
        name_forms: { nominative, genitive: forms.genitive.trim(), dative: forms.dative.trim() },
        specialty: specialty.trim(),
        timezone,
        owner_phone: owner,
      },
      {
        onSuccess: (master) => {
          onDone();
          navigate(`/masters/${master.id}`);
        },
      },
    );
  };

  return (
    <form className={ui.form} onSubmit={submit} noValidate aria-label="Новый мастер">
      <TextField
        label="Имя на странице"
        value={name}
        placeholder="Дана Ахметова"
        error={errors.name}
        onChange={(e) => setName(e.target.value)}
      />
      <TextField
        label="Адрес страницы"
        value={address}
        hint={address ? `${address}.beautiful.kz` : 'латиницей'}
        error={errors.slug}
        onChange={(e) => {
          setSlugTouched(true);
          setSlug(e.target.value.toLowerCase());
        }}
      />
      <div className={ui.pair}>
        <TextField
          label="Кто?"
          value={forms.nominative}
          placeholder={nominative || 'Дана'}
          onChange={(e) => setForms((f) => ({ ...f, nominative: e.target.value }))}
        />
        <TextField
          label="Кого? (нет …)"
          value={forms.genitive}
          placeholder="Даны"
          error={errors.genitive}
          onChange={(e) => setForms((f) => ({ ...f, genitive: e.target.value }))}
        />
        <TextField
          label="Кому? (к …)"
          value={forms.dative}
          placeholder="Дане"
          error={errors.dative}
          onChange={(e) => setForms((f) => ({ ...f, dative: e.target.value }))}
        />
      </div>
      <div className={ui.pair}>
        <TextField
          label="Специализация"
          value={specialty}
          placeholder="Маникюр"
          onChange={(e) => setSpecialty(e.target.value)}
        />
        <SelectField
          label="Часовой пояс"
          value={timezone}
          options={TIMEZONES}
          onChange={(e) => setTimezone(e.target.value)}
        />
      </div>
      <TextField
        label="Телефон владельца"
        type="tel"
        inputMode="tel"
        value={phone}
        placeholder="+7 701 123 45 67"
        hint="Номер Telegram мастера — по нему откроется кабинет. Можно задать позже."
        error={errors.phone}
        onChange={(e) => setPhone(e.target.value)}
      />
      {create.error && (
        <Notice tone="warn" role="alert">
          {errorText(create.error)}
        </Notice>
      )}
      <p className={ui.muted}>
        Страница появится черновиком: услуги, график и фото мастер заполнит в кабинете, потом её
        можно опубликовать.
      </p>
      <Button type="submit" size="lg" block disabled={create.isPending}>
        {create.isPending ? 'Заводим…' : 'Завести мастера'}
      </Button>
    </form>
  );
}
