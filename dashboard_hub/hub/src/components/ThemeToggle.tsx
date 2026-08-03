import { useThemeMode } from '../ThemeContext';
import './ThemeToggle.css';

export default function ThemeToggle() {
  const { mode, toggle } = useThemeMode();
  const next = mode === 'light' ? 'dark' : 'light';

  return (
    <button
      type="button"
      className="stock-toggle"
      onClick={toggle}
      aria-label={`Switch to ${next} stock`}
      title={`Switch to ${next} stock`}
    >
      <span className={`stock-toggle__chip${mode === 'light' ? ' is-on' : ''}`} aria-hidden="true" />
      <span className={`stock-toggle__chip${mode === 'dark' ? ' is-on' : ''}`} aria-hidden="true" />
    </button>
  );
}
