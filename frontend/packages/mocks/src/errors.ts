/** Ошибка сценария → problem+json в обработчике. */
export class MockProblem extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly title: string,
  ) {
    super(title);
  }
}
