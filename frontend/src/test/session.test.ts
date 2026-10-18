import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { extractAndRemoveLaunchCode } from '../auth/session-bootstrap';

describe('Session Bootstrap & One-Time Code Handling', () => {
  beforeEach(() => {
    // Reset window hash
    window.location.hash = '';
  });

  afterEach(() => {
    window.location.hash = '';
  });

  it('extracts code from #k= fragment and clears the fragment immediately', () => {
    window.location.hash = '#k=test-launch-code-12345';
    const code = extractAndRemoveLaunchCode();
    expect(code).toBe('test-launch-code-12345');
    // Fragment should be stripped from URL
    expect(window.location.hash).toBe('');
  });

  it('returns null when no #k= fragment is present', () => {
    window.location.hash = '';
    const code = extractAndRemoveLaunchCode();
    expect(code).toBeNull();

    window.location.hash = '#other-hash';
    const code2 = extractAndRemoveLaunchCode();
    expect(code2).toBeNull();
  });
});
