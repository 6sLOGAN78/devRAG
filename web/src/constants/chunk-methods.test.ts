import { describe, expect, it } from 'vitest';
import { CHUNK_METHODS, IMPLEMENTED, isImplemented, METHOD_STEMS } from './chunk-methods';
describe('implemented method availability', () => {
  it('offers One document and keeps all fourteen documented methods explicit', () => {
    expect(CHUNK_METHODS).toContain('one');
    expect(CHUNK_METHODS).toHaveLength(14);
    expect(new Set(CHUNK_METHODS).size).toBe(14);
    expect(IMPLEMENTED).toEqual(['naive', 'one', 'manual', 'qa', 'book', 'paper']);
    expect(isImplemented('audio')).toBe(false);
    expect(METHOD_STEMS).toHaveProperty('one', 'one');
  });
});
