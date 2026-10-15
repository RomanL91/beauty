import { AppShell, Button, StateView } from '@beauty/ui';

/** Непредвиденная ошибка рендеринга. */
export function RouteError() {
  return (
    <AppShell>
      <StateView
        role="alert"
        icon="retry"
        title="Что-то пошло не так"
        text="Обновите страницу — если не поможет, напишите нам."
        action={
          <Button variant="secondary" onClick={() => window.location.reload()}>
            Обновить
          </Button>
        }
      />
    </AppShell>
  );
}
