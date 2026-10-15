/**
 * Ошибка обращения к API в едином виде.
 *
 * Понимает оба формата ответа сервера: RFC 9457 `problem+json` (новые эндпоинты)
 * и `{"error": {"code", "message"}}` (identity сейчас), а также сетевой сбой
 * (офлайн, обрыв соединения) — у него `status = 0`.
 */
export class ApiError extends Error {
  override readonly name = 'ApiError';

  constructor(
    /** HTTP-статус; 0 — запрос не дошёл до сервера. */
    readonly status: number,
    /** Машиночитаемый код (`invalid_session`, `slot_taken`, …) или `network`/`http_<status>`. */
    readonly code: string,
    message: string,
    /** Ошибки полей для 422 (JSON Pointer → текст). */
    readonly fieldErrors: ReadonlyArray<{ pointer: string; detail: string }> = [],
  ) {
    super(message);
  }

  /** Запрос не дошёл до сервера. */
  get isNetwork(): boolean {
    return this.status === 0;
  }

  /** Сессия недействительна (после неудачного refresh). */
  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  /** Сетевой сбой. */
  static network(cause?: unknown): ApiError {
    const error = new ApiError(0, 'network', 'Нет соединения с сервером');
    if (cause !== undefined) Object.defineProperty(error, 'cause', { value: cause });
    return error;
  }

  /** Ошибка из тела ответа (любой из поддерживаемых форматов). */
  static fromBody(status: number, body: unknown): ApiError {
    if (isRecord(body)) {
      const envelope = body['error'];
      if (isRecord(envelope) && typeof envelope['code'] === 'string') {
        return new ApiError(status, envelope['code'], String(envelope['message'] ?? ''));
      }
      if (typeof body['title'] === 'string') {
        const code = typeof body['code'] === 'string' ? body['code'] : `http_${status}`;
        const detail = typeof body['detail'] === 'string' ? body['detail'] : body['title'];
        const fields = Array.isArray(body['errors']) ? body['errors'].filter(isFieldError) : [];
        return new ApiError(status, code, detail, fields);
      }
    }
    return new ApiError(status, `http_${status}`, `Ошибка сервера (${status})`);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function isFieldError(value: unknown): value is { pointer: string; detail: string } {
  return (
    isRecord(value) && typeof value['pointer'] === 'string' && typeof value['detail'] === 'string'
  );
}
