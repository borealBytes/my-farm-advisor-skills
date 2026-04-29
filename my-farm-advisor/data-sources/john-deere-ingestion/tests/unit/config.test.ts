import { describe, expect, it } from 'vitest';

import { DEFAULT_JD_ENVIRONMENT, DEFAULT_JD_REDIRECT_URI, parseConfig } from '../../src/config.js';

describe('config parsing', () => {
  it('loads John Deere config from environment variables', () => {
    const config = parseConfig({
      cwd: '/workspace/project',
      env: {
        JD_DATA_ROOT: '/tmp/jd-data',
        JD_GROWER: 'iowa-demo-grower',
        JD_PROFILE: 'sandbox-profile',
        JD_CLIENT_ID: 'client-id',
        JD_CLIENT_SECRET: 'client-secret',
        JD_REDIRECT_URI: 'http://localhost:9090/custom-callback',
        JD_ENVIRONMENT: 'production'
      }
    });

    expect(config).toMatchObject({
      dataRoot: '/tmp/jd-data',
      grower: 'iowa-demo-grower',
      profile: 'sandbox-profile',
      clientId: 'client-id',
      clientSecret: 'client-secret',
      redirectUri: 'http://localhost:9090/custom-callback',
      environment: 'production'
    });
    expect(config.configDir).toBe('/tmp/jd-data/.john-deere');
    expect(config.configFile).toBe('/tmp/jd-data/.john-deere/config.json');
    expect(config.tokenStorePath).toBe('/tmp/jd-data/tokens/iowa-demo-grower.sandbox-profile.json');
  });

  it('uses fallback defaults when JD env vars are unset', () => {
    const config = parseConfig({
      cwd: '/repo/my-farm-advisor/data-sources/john-deere-ingestion',
      env: {},
      pathExists: () => false
    });

    expect(config.dataRoot).toBe('/repo/.runtime/my-farm-advisor/data');
    expect(config.redirectUri).toBe(DEFAULT_JD_REDIRECT_URI);
    expect(config.environment).toBe(DEFAULT_JD_ENVIRONMENT);
    expect(config.tokenStorePath).toBe('/repo/.runtime/my-farm-advisor/data/tokens/todo-grower.json');
  });

  it('lets CLI-style overrides win over environment values', () => {
    const config = parseConfig({
      cwd: '/repo/my-farm-advisor/data-sources/john-deere-ingestion',
      env: {
        JD_DATA_ROOT: '/tmp/env-root',
        JD_GROWER: 'env-grower',
        JD_PROFILE: 'env-profile',
        JD_CLIENT_ID: 'env-client-id',
        JD_CLIENT_SECRET: 'env-client-secret',
        JD_REDIRECT_URI: 'http://localhost:9090/env-callback',
        JD_ENVIRONMENT: 'production'
      },
      overrides: {
        dataRoot: '/tmp/cli-root',
        grower: 'cli-grower',
        profile: 'cli-profile',
        clientId: 'cli-client-id',
        clientSecret: 'cli-client-secret',
        redirectUri: 'http://localhost:9090/cli-callback',
        environment: 'sandboxapi'
      },
      pathExists: () => false
    });

    expect(config).toMatchObject({
      dataRoot: '/tmp/cli-root',
      grower: 'cli-grower',
      profile: 'cli-profile',
      clientId: 'cli-client-id',
      clientSecret: 'cli-client-secret',
      redirectUri: 'http://localhost:9090/cli-callback',
      environment: 'sandboxapi'
    });
    expect(config.tokenStorePath).toBe('/tmp/cli-root/tokens/cli-grower.cli-profile.json');
  });
});
