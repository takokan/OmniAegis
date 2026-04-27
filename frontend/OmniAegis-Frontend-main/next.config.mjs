import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

function loadEnvFile(filePath) {
  if (!existsSync(filePath)) {
    return;
  }

  const content = readFileSync(filePath, 'utf8');
  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) {
      continue;
    }

    const separatorIndex = trimmed.indexOf('=');
    const key = trimmed.slice(0, separatorIndex).trim();
    if (!key || process.env[key] !== undefined) {
      continue;
    }

    let value = trimmed.slice(separatorIndex + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }

    process.env[key] = value;
  }
}

const projectRoot = process.cwd();
const workspaceRoot = join(projectRoot, '..', '..');

loadEnvFile(join(projectRoot, '.env.local'));
loadEnvFile(join(projectRoot, '.env.development.local'));
loadEnvFile(join(projectRoot, '.env'));
loadEnvFile(join(workspaceRoot, '.env.local'));
loadEnvFile(join(workspaceRoot, '.env.development.local'));
loadEnvFile(join(workspaceRoot, '.env'));

const nextConfig = {
  reactStrictMode: true,
};

export default nextConfig;