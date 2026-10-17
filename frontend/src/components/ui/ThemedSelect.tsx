import { useEffect, useId, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown } from 'lucide-react';

export type ThemedSelectOption = { value: string; label: string };

type Props = {
  id: string;
  value: string;
  options: ThemedSelectOption[];
  onChange: (value: string) => void;
  className?: string;
  disabled?: boolean;
  'aria-label'?: string;
};

export function ThemedSelect({ id, value, options, onChange, className = '', disabled = false, 'aria-label': ariaLabel }: Props) {
  const generatedId = useId();
  const listboxId = `${id || generatedId}-options`;
  const rootRef = useRef<HTMLDivElement>(null);
  const optionsRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const selectedIndex = Math.max(0, options.findIndex((option) => option.value === value));
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(selectedIndex);
  const [popupStyle, setPopupStyle] = useState<CSSProperties>({});
  const selectedOption = options.find((option) => option.value === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    setActiveIndex(selectedIndex);
    const positionPopup = () => {
      const rect = triggerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const availableBelow = window.innerHeight - rect.bottom - 8;
      const availableAbove = rect.top - 8;
      const opensBelow = availableBelow >= Math.min(240, options.length * 38) || availableBelow >= availableAbove;
      const maxHeight = Math.max(80, Math.min(280, opensBelow ? availableBelow : availableAbove));
      setPopupStyle({
        position: 'fixed',
        left: `${Math.max(8, Math.min(rect.left, window.innerWidth - rect.width - 8))}px`,
        top: opensBelow ? `${rect.bottom + 4}px` : undefined,
        bottom: opensBelow ? undefined : `${window.innerHeight - rect.top + 4}px`,
        width: `${rect.width}px`,
        maxHeight: `${maxHeight}px`,
      });
    };
    positionPopup();
    const closeOnOutsidePointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!rootRef.current?.contains(target) && !optionsRef.current?.contains(target)) setOpen(false);
    };
    document.addEventListener('pointerdown', closeOnOutsidePointer);
    window.addEventListener('resize', positionPopup);
    window.addEventListener('scroll', positionPopup, true);
    return () => {
      document.removeEventListener('pointerdown', closeOnOutsidePointer);
      window.removeEventListener('resize', positionPopup);
      window.removeEventListener('scroll', positionPopup, true);
    };
  }, [open, selectedIndex, options.length]);

  const choose = (index: number) => {
    const option = options[index];
    if (!option) return;
    onChange(option.value);
    setOpen(false);
    triggerRef.current?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const direction = event.key === 'ArrowDown' ? 1 : -1;
      if (!open) {
        setActiveIndex(selectedIndex);
        setOpen(true);
      } else {
        setActiveIndex((index) => (index + direction + options.length) % options.length);
      }
      return;
    }
    if (event.key === 'Home' || event.key === 'End') {
      if (!open) return;
      event.preventDefault();
      setActiveIndex(event.key === 'Home' ? 0 : Math.max(0, options.length - 1));
      return;
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      if (open) choose(activeIndex);
      else setOpen(true);
      return;
    }
    if (event.key === 'Escape' && open) {
      event.preventDefault();
      setOpen(false);
    }
  };

  return <div ref={rootRef} className={`themed-select ${className}`}>
    <button
      ref={triggerRef}
      id={id}
      type="button"
      className="themed-select-trigger"
      role="combobox"
      aria-label={ariaLabel}
      aria-haspopup="listbox"
      aria-expanded={open}
      aria-controls={listboxId}
      aria-activedescendant={open ? `${listboxId}-option-${activeIndex}` : undefined}
      disabled={disabled || options.length === 0}
      onClick={() => setOpen((current) => !current)}
      onKeyDown={onKeyDown}
    >
      <span className="themed-select-value">{selectedOption?.label ?? ''}</span>
      <ChevronDown size={15} aria-hidden="true" className={`themed-select-chevron ${open ? 'is-open' : ''}`} />
    </button>
    {open && createPortal(<div ref={optionsRef} id={listboxId} className="themed-select-options" style={popupStyle} role="listbox" aria-labelledby={id}>
      {options.map((option, index) => <button
        key={option.value}
        id={`${listboxId}-option-${index}`}
        type="button"
        role="option"
        aria-selected={option.value === value}
        className={`themed-select-option ${index === activeIndex ? 'is-active' : ''} ${option.value === value ? 'is-selected' : ''}`}
        onMouseEnter={() => setActiveIndex(index)}
        onClick={() => choose(index)}
      >
        <span>{option.label}</span>
        {option.value === value && <Check size={14} aria-hidden="true" />}
      </button>)}
    </div>, document.body)}
  </div>;
}
