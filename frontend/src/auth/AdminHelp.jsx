import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { Info } from 'lucide-react';

export default function AdminHelp({ label, children }) {
  const id = useId();
  const button = useRef(null), surface = useRef(null), timer = useRef(null);
  const [open, setOpen] = useState(false);
  const pinned = useRef(false);
  const close = useCallback(() => { clearTimeout(timer.current); pinned.current = false; setOpen(false); }, []);
  function show() { clearTimeout(timer.current); setOpen(true); }
  function leave() { if (!pinned.current) timer.current = setTimeout(() => setOpen(false), 120); }
  const position = useCallback(() => {
    const node = surface.current;
    if (!node || !button.current) return;
    const anchor = button.current.getBoundingClientRect(), bounds = node.getBoundingClientRect();
    const scrollport = button.current.closest('main')?.getBoundingClientRect();
    if (anchor.bottom < (scrollport?.top || 0) || anchor.top > innerHeight) { close(); return; }
    node.style.left = `${Math.max(12, Math.min(anchor.left, innerWidth - bounds.width - 12))}px`;
    node.style.top = `${Math.max(12, anchor.bottom + bounds.height + 8 < innerHeight - 12 ? anchor.bottom + 8 : anchor.top - bounds.height - 8)}px`;
  }, [close]);
  useLayoutEffect(() => {
    if (!open) return;
    const node = surface.current;
    node.showPopover();
    position();
  }, [open, position]);
  useEffect(() => {
    if (!open) return;
    function outside(event) { if (!button.current?.contains(event.target) && !surface.current?.contains(event.target)) close(); }
    function escape(event) { if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); } }
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape, true);
    window.addEventListener('scroll', position, true);
    window.addEventListener('resize', position);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', escape, true);
      window.removeEventListener('scroll', position, true);
      window.removeEventListener('resize', position);
      clearTimeout(timer.current);
    };
  }, [open, close, position]);
  useEffect(() => () => clearTimeout(timer.current), []);
  return <span className="ac-help">
    <button ref={button} type="button" className="ac-help-button" aria-label={`About ${label}`} aria-expanded={open} aria-describedby={open ? id : undefined}
      onMouseEnter={show} onMouseLeave={leave} onFocus={show} onBlur={() => { if (!pinned.current) close(); }}
      onClick={() => { if (pinned.current) close(); else { pinned.current = true; show(); } }}><Info size={15} aria-hidden="true" /></button>
    {open && <span ref={surface} id={id} role="tooltip" popover="manual" className="ac-help-surface" onMouseEnter={() => clearTimeout(timer.current)} onMouseLeave={leave}>{children}</span>}
  </span>;
}
