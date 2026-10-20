import type { Playbook, Practice } from '@beauty/api';
import { describe, expect, it } from 'vitest';
import { practiceGroups } from './model';

const at = '2026-10-20T10:00:00Z';
const practice = (
  id: string,
  service_id: string | null,
  service_title: string | null,
): Practice => ({
  id,
  text: `запись ${id}`,
  service_id,
  service_title,
  author: 'agent',
  created_at: at,
  updated_at: at,
});

describe('practiceGroups', () => {
  it('общие — «Как вы работаете», к услугам — по названию, убранная услуга подписана', () => {
    const playbook: Playbook = {
      auto_confirm: false,
      practices: [
        practice('1', null, null),
        practice('2', 's1', 'Ботокс'),
        practice('3', 's1', 'Ботокс'),
        practice('4', 's2', null),
      ],
    };
    expect(practiceGroups(playbook).map((g) => [g.title, g.items.length])).toEqual([
      ['Как вы работаете', 1],
      ['Ботокс', 2],
      ['Услуга убрана', 1],
    ]);
  });
});
