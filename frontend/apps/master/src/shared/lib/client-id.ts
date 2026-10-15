/** Идентификатор сообщения на стороне клиента (идемпотентность отправки). */
export function newClientId(): string {
  return crypto.randomUUID();
}
