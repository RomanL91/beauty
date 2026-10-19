import { ApiError, type AdminSession } from '@beauty/api';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAdminApi } from './container';

export const sessionKey = ['admin', 'session'] as const;

/** Сессия администратора (`null` — не вошли). */
export function useSession() {
  const api = useAdminApi();
  return useQuery({
    queryKey: sessionKey,
    queryFn: () => api.me(),
    staleTime: 5 * 60_000,
    retry: 0,
  });
}

/** Вход по логину и паролю. */
export function useLogin() {
  const api = useAdminApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ login, password }: { login: string; password: string }) =>
      api.login(login, password),
    onSuccess: (session: AdminSession) => queryClient.setQueryData(sessionKey, session),
  });
}

/** Выход: сессия закрыта, кэш панели очищен. */
export function useLogout() {
  const api = useAdminApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.logout(),
    onSettled: () => {
      queryClient.clear();
      queryClient.setQueryData(sessionKey, null);
    },
  });
}

/** Ошибка «сессия кончилась» — панель возвращает на вход. */
export function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

/** Текст ошибки для тоста или формы. */
export function errorText(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Не получилось — попробуйте ещё раз';
  if (error.isNetwork) return 'Нет соединения с сервером';
  if (error.code === 'validation_error') return 'Проверьте поля формы';
  if (error.status >= 500) return 'Сервер не ответил — попробуйте ещё раз';
  return error.message || 'Не получилось';
}
