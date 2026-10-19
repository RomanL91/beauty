import { describe, expect, it } from 'vitest';
import { niceTicks } from './scale';

describe('шкала графика', () => {
  it('круглые деления от нуля', () => {
    expect(niceTicks(0)).toEqual([0, 1]);
    expect(niceTicks(7)).toEqual([0, 5, 10]);
    expect(niceTicks(38)).toEqual([0, 20, 40]);
    expect(niceTicks(130)).toEqual([0, 50, 100, 150]);
  });
});
