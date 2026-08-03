/**
 * Locate the Python interpreter that runs the dashboards.
 *
 * The hub reuses the project venv the rest of Kubera_EDW already uses (`make setup`),
 * so there is no second environment to keep in sync. `KUBERA_HUB_PYTHON` overrides it.
 */
export function resolveDashboardsPython({ repoRoot, platform, env, exists, join }) {
  const override = (env.KUBERA_HUB_PYTHON ?? '').trim();
  if (override) {
    if (!exists(override)) {
      throw new Error(`KUBERA_HUB_PYTHON is set to "${override}" but no such file exists.`);
    }
    return override;
  }

  const candidate =
    platform === 'win32'
      ? join(repoRoot, '.venv', 'Scripts', 'python.exe')
      : join(repoRoot, '.venv', 'bin', 'python');

  if (!exists(candidate)) {
    throw new Error(
      `Project virtualenv not found at:\n  ${candidate}\n` +
        'Create it from the repo root with:\n' +
        '  make setup\n' +
        'Or point KUBERA_HUB_PYTHON at an interpreter that already has Streamlit.',
    );
  }
  return candidate;
}

/** Split a chunk into whole lines, tag each with `label`, and carry any partial line over. */
export function prefixLines(label, carry, chunk) {
  const combined = carry + chunk;
  const lines = combined.split(/\r?\n/);
  const nextCarry = lines.pop() ?? '';
  if (lines.length === 0) {
    return { output: '', carry: nextCarry };
  }
  const output = lines.map((line) => `[${label}] ${line}\n`).join('');
  return { output, carry: nextCarry };
}
