import type { MasterSettings, Practice } from '@beauty/api';
import {
  Badge,
  Button,
  ErrorState,
  Icon,
  SelectField,
  Sheet,
  Skeleton,
  TextArea,
  Toggle,
  buttonClass,
  useOnline,
} from '@beauty/ui';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { MAX_PRACTICE, practiceGroups } from '../../entities/playbook/model';
import { usePlaybook, usePlaybookChange } from '../../entities/playbook/queries';
import { SettingsScreen } from './SettingsScreen';
import styles from './Settings.module.css';

type Editing = { readonly kind: 'new' } | { readonly kind: 'edit'; readonly practice: Practice };

/**
 * «Ассистент»: самостоятельность записи и опыт мастера — что знает ассистент. Опыт —
 * словами мастера; ассистент учитывает его и решает сам. Пополняется и в «Поручениях».
 */
export function AssistantSettings() {
  return (
    <SettingsScreen title="Ассистент">
      {(settings) => (
        <div className={styles.body}>
          <AssistantBody settings={settings} />
        </div>
      )}
    </SettingsScreen>
  );
}

function AssistantBody({ settings }: { readonly settings: MasterSettings }) {
  const playbook = usePlaybook();
  const online = useOnline();
  const [editing, setEditing] = useState<Editing | null>(null);
  const autonomy = usePlaybookChange((gateway, on: boolean) => gateway.setAutonomy(on));
  const remove = usePlaybookChange(
    (gateway, id: string) => gateway.removePractice(id),
    'Запись удалена',
  );

  if (!playbook.data) {
    return playbook.isError ? (
      <ErrorState offline={!online} onRetry={() => void playbook.refetch()} />
    ) : (
      <div aria-busy="true" style={{ display: 'grid', gap: 16 }}>
        <Skeleton height={110} radius={18} />
        <Skeleton height={220} radius={18} />
      </div>
    );
  }
  const groups = practiceGroups(playbook.data);
  return (
    <>
      <section className={styles.card} aria-labelledby="autonomy">
        <h2 id="autonomy" className={styles.cardTitle}>
          Запись клиентов
        </h2>
        <Toggle
          label="Записывать клиентов сразу"
          checked={playbook.data.auto_confirm}
          disabled={autonomy.isPending || !online}
          onChange={(on) => autonomy.mutate(on)}
        />
        <p className={styles.muted}>
          {playbook.data.auto_confirm
            ? 'Ассистент сам подтверждает запись по вашему опыту — вы видите её в графике.'
            : 'Ассистент оставляет заявку — вы подтверждаете сами.'}
        </p>
      </section>

      <section className={styles.card} aria-labelledby="knows">
        <h2 id="knows" className={styles.cardTitle}>
          Что знает ассистент
        </h2>
        <p className={styles.muted}>
          Ваш опыт словами: как вы строите день, особенности услуг, что можно решать без вас.
          Ассистент учитывает это в разговорах с клиентами и решает сам.
        </p>
        {groups.length === 0 ? (
          <p className={styles.muted}>Пока пусто — расскажите о себе.</p>
        ) : (
          groups.map((group) => (
            <div key={group.key} className={styles.practiceGroup}>
              <h3 className={styles.sectionTitle}>{group.title}</h3>
              <ul className={styles.practices} aria-label={group.title}>
                {group.items.map((practice) => (
                  <li key={practice.id} className={styles.practice}>
                    <span className={styles.grow}>
                      {practice.text}
                      {practice.author === 'agent' && (
                        <>
                          {' '}
                          <Badge tone="muted">ИИ</Badge>
                        </>
                      )}
                    </span>
                    <button
                      type="button"
                      className={styles.practiceAction}
                      aria-label={`Изменить: ${practice.text}`}
                      disabled={!online}
                      onClick={() => setEditing({ kind: 'edit', practice })}
                    >
                      <Icon name="settings" size={18} />
                    </button>
                    <button
                      type="button"
                      className={styles.practiceAction}
                      aria-label={`Удалить: ${practice.text}`}
                      disabled={remove.isPending || !online}
                      onClick={() => remove.mutate(practice.id)}
                    >
                      <Icon name="trash" size={18} />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}
        <div className={styles.actions}>
          <Button variant="outline" disabled={!online} onClick={() => setEditing({ kind: 'new' })}>
            Добавить
          </Button>
          <Link to="/assistant" className={buttonClass({ variant: 'ghost' })}>
            Рассказать в «Поручениях»
          </Link>
        </div>
      </section>

      <Sheet
        open={editing !== null}
        title={editing?.kind === 'edit' ? 'Запись опыта' : 'Новая запись'}
        onClose={() => setEditing(null)}
      >
        {editing && (
          <PracticeForm
            key={editing.kind === 'edit' ? editing.practice.id : 'new'}
            editing={editing}
            settings={settings}
            onDone={() => setEditing(null)}
          />
        )}
      </Sheet>
    </>
  );
}

function PracticeForm({
  editing,
  settings,
  onDone,
}: {
  readonly editing: Editing;
  readonly settings: MasterSettings;
  readonly onDone: () => void;
}) {
  const current = editing.kind === 'edit' ? editing.practice : null;
  const [text, setText] = useState(current?.text ?? '');
  const [serviceId, setServiceId] = useState(current?.service_id ?? '');
  const save = usePlaybookChange(
    (gateway, input: { text: string; service_id: string | null }) =>
      current ? gateway.editPractice(current.id, input) : gateway.addPractice(input),
    current ? 'Запись изменена' : 'Ассистент запомнил',
  );
  const options = [
    { value: '', label: 'Ко всему дню' },
    ...settings.page.services.map((s) => ({ value: s.id, label: s.title })),
    ...(current?.service_id && !settings.page.services.some((s) => s.id === current.service_id)
      ? [{ value: current.service_id, label: 'Услуга убрана' }]
      : []),
  ];
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate({ text: text.trim(), service_id: serviceId || null }, { onSuccess: onDone });
  };
  return (
    <form className={styles.sheetForm} onSubmit={submit} aria-label="Запись опыта">
      <TextArea
        label="Что важно знать"
        value={text}
        maxLength={MAX_PRACTICE}
        rows={4}
        placeholder="Например: окрашивания — только с утра, не больше двух в день"
        hint={`${text.length} / ${MAX_PRACTICE}`}
        onChange={(e) => setText(e.target.value)}
      />
      <SelectField
        label="О чём это"
        value={serviceId}
        options={options}
        onChange={(e) => setServiceId(e.target.value)}
      />
      <Button type="submit" size="lg" block disabled={!text.trim() || save.isPending}>
        {save.isPending ? 'Сохраняем…' : 'Сохранить'}
      </Button>
    </form>
  );
}
