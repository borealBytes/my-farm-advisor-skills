import { describe, expect, it } from 'vitest';

import { parseConfig } from '../../src/config.js';

describe('config parsing', () => {
  it('uses JD_DATA_ROOT and JD_GROWER overrides', () => {
    const config = parseConfig({
      cwd: '/workspace/project',
      env: {
        JD_DATA_ROOT: '/tmp/jd-data',
        JD_GROWER: 'iowa-demo-grower'
      }
    });

    expect(config).toEqual({
      dataRoot: '/tmp/jd-data',
      grower: 'iowa-demo-grower',
      profile: 'default'
    });
  });
});
