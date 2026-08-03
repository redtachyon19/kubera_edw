import { useCallback, useEffect, useId, useRef, useState } from 'react';

import './Select.css';

export interface SelectProps {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}

/**
 * A dropdown in the house style.
 *
 * A native `<select>` cannot be made to match: `appearance: none` reaches the
 * closed control but the open list is drawn by the operating system, so the
 * menu arrives in the platform's font on the platform's stock in the middle of
 * a page set in Copperplate on bone. This is the same listbox the search
 * results already use, with the keyboard behaviour a select is expected to have
 * — arrows to move, Enter to take, Escape to leave it alone.
 */
export default function Select({ label, value, options, onChange }: SelectProps) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(() => Math.max(0, options.indexOf(value)));
  const boxRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const id = useId();

  // Opening always lands on the current choice, so arrowing starts from where
  // the reader is rather than from the top of the list.
  const show = useCallback(() => {
    setActive(Math.max(0, options.indexOf(value)));
    setOpen(true);
  }, [options, value]);

  const close = useCallback(() => {
    setOpen(false);
    setActive(Math.max(0, options.indexOf(value)));
  }, [options, value]);

  useEffect(() => {
    if (!open) return;
    function onClick(event: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) close();
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open, close]);

  // Keep the highlighted option in view when arrowing through a long list.
  useEffect(() => {
    if (!open) return;
    listRef.current?.children[active]?.scrollIntoView({ block: 'nearest' });
  }, [open, active]);

  function take(option: string) {
    onChange(option);
    setOpen(false);
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === 'Escape') {
      close();
      return;
    }
    if (!open && (event.key === 'Enter' || event.key === ' ' || event.key === 'ArrowDown')) {
      event.preventDefault();
      show();
      return;
    }
    if (!open) return;

    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const step = event.key === 'ArrowDown' ? 1 : -1;
      setActive((current) => (current + step + options.length) % options.length);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      take(options[active]);
    } else if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault();
      setActive(event.key === 'Home' ? 0 : options.length - 1);
    }
  }

  return (
    <div className="pick" ref={boxRef}>
      <span className="eyebrow" id={`${id}-label`}>
        {label}
      </span>
      <button
        type="button"
        className={`pick__field${open ? ' is-open' : ''}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-labelledby={`${id}-label`}
        onClick={() => (open ? close() : show())}
        onKeyDown={onKeyDown}
      >
        <span className="pick__value">{value}</span>
        <svg className="pick__caret" viewBox="0 0 10 6" aria-hidden="true">
          <path d="M0 0 L5 6 L10 0" />
        </svg>
      </button>

      {open && (
        <ul
          className="pick__list"
          role="listbox"
          aria-labelledby={`${id}-label`}
          tabIndex={-1}
          ref={listRef}
        >
          {options.map((option, index) => (
            <li key={option}>
              <button
                type="button"
                role="option"
                aria-selected={option === value}
                className={`pick__option${index === active ? ' is-active' : ''}${
                  option === value ? ' is-on' : ''
                }`}
                onMouseEnter={() => setActive(index)}
                onClick={() => take(option)}
              >
                {option}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
