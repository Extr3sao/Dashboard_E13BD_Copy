import { describe, expect, it } from 'vitest';

import { getAutomationRunReportUrl } from './automation.js';

describe('automation api helpers', () => {
  it('returns a plain report URL string for automation runs', () => {
    expect(getAutomationRunReportUrl(7)).toBe('/api/automation/runs/7/report');
  });
});
