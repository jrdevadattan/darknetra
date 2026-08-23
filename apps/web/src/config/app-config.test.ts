import { describe, expect, it } from 'vitest';
import { APP_CONFIG } from './app-config';

describe('DARKNETRA brand contract', () => {
  it('uses the DARKNETRA investigator product identity', () => {
    expect(APP_CONFIG.name).toBe('DARKNETRA');
    expect(APP_CONFIG.meta.title).toContain('DARKNETRA');
    expect(APP_CONFIG.meta.description).toContain('investigator');
  });
});
