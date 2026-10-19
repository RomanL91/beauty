import type { AdminAccount, AdminAccountInput } from '@beauty/api';
import {
  Badge,
  Button,
  ErrorState,
  Notice,
  Sheet,
  Skeleton,
  TextField,
  useOnline,
  useToast,
} from '@beauty/ui';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useAdminApi } from '../shared/lib/container';
import { formatDateTime } from '../shared/lib/format';
import { keys, useAdmins } from '../shared/lib/queries';
import { errorText, useSession } from '../shared/lib/session';
import ui from '../shared/ui.module.css';

const MIN_PASSWORD = 10;

type Editing =
  { readonly kind: 'new' } | { readonly kind: 'password'; readonly admin: AdminAccount };

/** Администраторы панели и смена своего пароля. */
export function AdminsPage() {
  const admins = useAdmins();
  const me = useSession().data?.admin;
  const online = useOnline();
  const [editing, setEditing] = useState<Editing | null>(null);
  const update = useAdminUpdate();

  return (
    <div className={ui.page}>
      <header className={ui.header}>
        <div>
          <h1 className={ui.h1}>Администраторы</h1>
          <p className={ui.muted}>
            Кто может входить в панель. Отключённый теряет все сессии сразу.
          </p>
        </div>
        <Button onClick={() => setEditing({ kind: 'new' })} disabled={!online}>
          Добавить
        </Button>
      </header>
      {admins.data ? (
        <div className={ui.tableWrap}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>Администратор</th>
                <th>Статус</th>
                <th>Последний вход</th>
                <th>Добавлен</th>
                <th aria-label="Действия" />
              </tr>
            </thead>
            <tbody>
              {admins.data.map((a) => (
                <tr key={a.id}>
                  <td>
                    <strong>{a.display_name}</strong>
                    {a.id === me?.id && ' (вы)'}
                    <div className={ui.muted}>{a.login}</div>
                  </td>
                  <td>
                    {a.active ? (
                      <Badge tone="ok">Активен</Badge>
                    ) : (
                      <Badge tone="muted">Отключён</Badge>
                    )}
                  </td>
                  <td>{formatDateTime(a.last_login_at)}</td>
                  <td>{formatDateTime(a.created_at)}</td>
                  <td>
                    <div className={ui.row}>
                      <Button
                        variant="ghost"
                        disabled={!online}
                        onClick={() => setEditing({ kind: 'password', admin: a })}
                      >
                        Пароль
                      </Button>
                      {a.id !== me?.id && (
                        <Button
                          variant="ghost"
                          disabled={update.isPending || !online}
                          onClick={() => update.mutate({ admin: a, patch: { active: !a.active } })}
                        >
                          {a.active ? 'Отключить' : 'Включить'}
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : admins.isError ? (
        <ErrorState offline={!online} onRetry={() => void admins.refetch()} />
      ) : (
        <Skeleton height={160} radius={18} />
      )}
      <OwnPassword />
      <Sheet
        open={editing !== null}
        title={
          editing?.kind === 'password' ? `Пароль: ${editing.admin.login}` : 'Новый администратор'
        }
        onClose={() => setEditing(null)}
      >
        {editing?.kind === 'new' && <NewAdminForm onDone={() => setEditing(null)} />}
        {editing?.kind === 'password' && (
          <SetPasswordForm admin={editing.admin} onDone={() => setEditing(null)} />
        )}
      </Sheet>
    </div>
  );
}

function useAdminUpdate() {
  const api = useAdminApi();
  const queryClient = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: ({
      admin,
      patch,
    }: {
      admin: AdminAccount;
      patch: { active?: boolean; password?: string };
    }) => api.updateAdmin(admin.id, patch),
    onSuccess: (_admin, { patch }) => {
      void queryClient.invalidateQueries({ queryKey: keys.admins });
      void queryClient.invalidateQueries({ queryKey: keys.audit });
      toast({
        text:
          patch.password !== undefined
            ? 'Пароль задан — его сессии закрыты'
            : patch.active
              ? 'Администратор включён'
              : 'Администратор отключён — его сессии закрыты',
      });
    },
    onError: (error) => toast({ text: errorText(error) }),
  });
}

function NewAdminForm({ onDone }: { readonly onDone: () => void }) {
  const api = useAdminApi();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [form, setForm] = useState<AdminAccountInput>({
    login: '',
    display_name: '',
    password: '',
  });
  const [touched, setTouched] = useState(false);
  const create = useMutation({
    mutationFn: (input: AdminAccountInput) => api.createAdmin(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.admins });
      void queryClient.invalidateQueries({ queryKey: keys.audit });
      toast({ text: 'Администратор добавлен — передайте ему логин и пароль' });
      onDone();
    },
  });
  const loginOk = /^[a-z0-9._-]{3,64}$/.test(form.login.trim().toLowerCase());
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (!loginOk || !form.display_name.trim() || form.password.length < MIN_PASSWORD) return;
    create.mutate({ ...form, login: form.login.trim().toLowerCase() });
  };
  return (
    <form className={ui.form} onSubmit={submit} noValidate aria-label="Новый администратор">
      <TextField
        label="Логин"
        autoCapitalize="none"
        value={form.login}
        hint="латиница, цифры, точка, дефис"
        error={touched && !loginOk ? 'Логин — 3–64 символа: латиница, цифры, . _ -' : null}
        onChange={(e) => setForm((f) => ({ ...f, login: e.target.value }))}
      />
      <TextField
        label="Имя"
        value={form.display_name}
        error={touched && !form.display_name.trim() ? 'Как его подписывать в журнале' : null}
        onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
      />
      <TextField
        label="Пароль"
        type="password"
        autoComplete="new-password"
        value={form.password}
        error={
          touched && form.password.length < MIN_PASSWORD ? `От ${MIN_PASSWORD} символов` : null
        }
        onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
      />
      {create.error && (
        <Notice tone="warn" role="alert">
          {errorText(create.error)}
        </Notice>
      )}
      <Button type="submit" size="lg" block disabled={create.isPending}>
        Добавить
      </Button>
    </form>
  );
}

function SetPasswordForm({
  admin,
  onDone,
}: {
  readonly admin: AdminAccount;
  readonly onDone: () => void;
}) {
  const update = useAdminUpdate();
  const [password, setPassword] = useState('');
  const [touched, setTouched] = useState(false);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (password.length >= MIN_PASSWORD)
      update.mutate({ admin, patch: { password } }, { onSuccess: onDone });
  };
  return (
    <form className={ui.form} onSubmit={submit} noValidate aria-label="Новый пароль">
      <p className={ui.muted}>
        Сессии {admin.login} закроются — войти можно будет только с новым паролем.
      </p>
      <TextField
        label="Новый пароль"
        type="password"
        autoComplete="new-password"
        value={password}
        error={touched && password.length < MIN_PASSWORD ? `От ${MIN_PASSWORD} символов` : null}
        onChange={(e) => setPassword(e.target.value)}
      />
      <Button type="submit" size="lg" block disabled={update.isPending}>
        Задать пароль
      </Button>
    </form>
  );
}

function OwnPassword() {
  const api = useAdminApi();
  const toast = useToast();
  const [form, setForm] = useState({ current: '', next: '' });
  const [touched, setTouched] = useState(false);
  const change = useMutation({
    mutationFn: () => api.changePassword(form.current, form.next),
    onSuccess: () => {
      setForm({ current: '', next: '' });
      setTouched(false);
      toast({ text: 'Пароль изменён — другие ваши сессии закрыты' });
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (form.current && form.next.length >= MIN_PASSWORD) change.mutate();
  };
  return (
    <section className={ui.card} aria-labelledby="own-password" style={{ maxWidth: 520 }}>
      <h2 id="own-password" className={ui.h2}>
        Мой пароль
      </h2>
      <form className={ui.form} onSubmit={submit} noValidate aria-label="Мой пароль">
        <TextField
          label="Текущий пароль"
          type="password"
          autoComplete="current-password"
          value={form.current}
          onChange={(e) => setForm((f) => ({ ...f, current: e.target.value }))}
        />
        <TextField
          label="Новый пароль"
          type="password"
          autoComplete="new-password"
          value={form.next}
          error={touched && form.next.length < MIN_PASSWORD ? `От ${MIN_PASSWORD} символов` : null}
          onChange={(e) => setForm((f) => ({ ...f, next: e.target.value }))}
        />
        {change.error && (
          <Notice tone="warn" role="alert">
            {errorText(change.error)}
          </Notice>
        )}
        <Button
          type="submit"
          variant="outline"
          disabled={change.isPending || !form.current || !form.next}
        >
          Сменить пароль
        </Button>
      </form>
    </section>
  );
}
