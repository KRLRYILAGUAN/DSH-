#!/usr/bin/env node
/**
 * Optional reranker support: install fastembed into the plugin's vendored
 * directory using the bundled Python. Base install stays lean; rerank becomes
 * available only after this runs.
 */
import { execFileSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const home = join(dirname(fileURLToPath(import.meta.url)), '..', 'python')
const python = process.platform === 'win32'
  ? join(home, 'runtime', 'python.exe')
  : join(home, 'runtime', 'bin', 'python3')
const vendor = join(home, 'vendor')

if (!existsSync(python)) {
  console.error('bundled python not found:', python)
  process.exit(1)
}

console.log('installing fastembed into', vendor)
execFileSync(
  python,
  ['-m', 'pip', 'install', '--disable-pip-version-check', '--target', vendor, 'fastembed'],
  { stdio: 'inherit', env: { ...process.env, PIP_DISABLE_PIP_VERSION_CHECK: '1' } },
)

try {
  execFileSync(python, ['-c', 'import fastembed; print("fastembed", fastembed.__version__)'], {
    stdio: 'inherit',
    env: { ...process.env },
    cwd: home,
  })
} catch {
  console.error('installed but import failed; check the output above')
  process.exit(1)
}
