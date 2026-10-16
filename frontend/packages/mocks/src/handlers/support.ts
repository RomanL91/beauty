import type { paths } from '@beauty/api';
import { HttpResponse } from 'msw';
import { createOpenApiHttp } from 'openapi-msw';
import { MockProblem } from '../db';

/**
 * `http` из openapi-msw, привязанный к контракту: путь, параметры, тело запроса
 * и ответа проверяются компилятором — расхождение с контрактом не соберётся.
 * `*` перед `/api/v1` — любой origin (dev-сервер, тесты).
 */
export const http = createOpenApiHttp<paths>({ baseUrl: '*/api/v1' });

/** Ответ RFC 9457. */
export function problem(status: number, code: string, title: string): HttpResponse<never> {
  return HttpResponse.json(
    { type: 'about:blank', title, status, code },
    { status, headers: { 'Content-Type': 'application/problem+json' } },
  ) as unknown as HttpResponse<never>;
}

/** Без `Authorization: Bearer …` — 401. */
export function requireBearer(request: Request): HttpResponse<never> | null {
  const header = request.headers.get('Authorization') ?? '';
  return header.startsWith('Bearer ') && header.length > 7
    ? null
    : problem(401, 'unauthorized', 'Нужно войти');
}

/** Выполнить сценарий, превратив `MockProblem` в problem+json (как сервер). */
export function run<T>(scenario: () => T): T | HttpResponse<never> {
  try {
    return scenario();
  } catch (error) {
    if (error instanceof MockProblem) return problem(error.status, error.code, error.title);
    throw error;
  }
}

/** Число из query с границами. */
export function intParam(value: string | null, fallback: number, max = 100): number {
  const n = Number(value);
  return Number.isInteger(n) && n > 0 ? Math.min(n, max) : fallback;
}
