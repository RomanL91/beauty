import { Button, Notice, TextField } from '@beauty/ui';
import { useState, type FormEvent } from 'react';
import { Navigate, useSearchParams } from 'react-router';
import { errorText, useLogin, useSession } from '../shared/lib/session';
import styles from './LoginPage.module.css';

/** Вход в панель: логин и пароль. */
export function LoginPage() {
  const session = useSession();
  const login = useLogin();
  const [params] = useSearchParams();
  const [form, setForm] = useState({ login: '', password: '' });
  const back = params.get('return');
  const target = back && back.startsWith('/') && !back.startsWith('//') ? back : '/';

  if (session.data) return <Navigate to={target} replace />;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (form.login.trim() && form.password) login.mutate(form);
  };

  return (
    <main className={styles.page}>
      <form className={styles.card} onSubmit={submit} aria-label="Вход в панель">
        <div>
          <span className={styles.logo}>b</span>
          <h1 className={styles.h1}>Панель beautiful.kz</h1>
          <p className={styles.muted}>Вход для хозяина сервиса и его помощников.</p>
        </div>
        <TextField
          label="Логин"
          autoComplete="username"
          autoCapitalize="none"
          value={form.login}
          onChange={(e) => setForm((f) => ({ ...f, login: e.target.value }))}
        />
        <TextField
          label="Пароль"
          type="password"
          autoComplete="current-password"
          value={form.password}
          onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
        />
        {login.error && (
          <Notice tone="warn" role="alert">
            {errorText(login.error)}
          </Notice>
        )}
        <Button
          type="submit"
          size="lg"
          block
          disabled={login.isPending || !form.login.trim() || !form.password}
        >
          {login.isPending ? 'Входим…' : 'Войти'}
        </Button>
      </form>
    </main>
  );
}
