import { useContainer } from '../../shared/lib/container-context';
import { PlaceholderPage } from '../placeholder/PlaceholderPage';
import { AssistantPage } from './AssistantPage';

/** Поручения — пока агента нет на бэкенде, в реальной сборке показываем заглушку. */
export function AssistantRoute() {
  const { env } = useContainer();
  if (env.assistantPending) {
    return (
      <PlaceholderPage
        title="Поручения"
        text="Поручения администратору появятся вместе с ИИ-агентом. График, заявки и чаты уже работают."
      />
    );
  }
  return <AssistantPage />;
}
