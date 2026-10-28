import { useId, useState } from 'react';
import { Info } from 'lucide-react';
import './catalog-feature-presentation.css';

// Shared website rendering only. Inclusion comes from validated entitlements;
// presentation copy never grants access or manufactures preview destinations.
export default function CatalogFeaturePresentation({
  label,
  information,
  included,
  informationLabel = label
}) {
  const id = useId();
  const [pinned, setPinned] = useState(false);
  const [open, setOpen] = useState(false);
  return <div className="catalog-feature-row">
    <span>{included ? label : <s>{label}</s>}</span>
    <span className="catalog-feature-icons">
      {information && <span className="catalog-feature-info" onMouseEnter={() => setOpen(true)} onMouseLeave={event => {
        if (!pinned && !event.currentTarget.contains(document.activeElement)) setOpen(false);
      }} onFocus={() => setOpen(true)} onBlur={() => {
        if (!pinned) setOpen(false);
      }} onKeyDown={event => {
        if (event.key === 'Escape') {
          event.stopPropagation();
          setPinned(false);
          setOpen(false);
        }
      }}>
        <button type="button" aria-label={`About ${informationLabel}`} aria-describedby={id} aria-expanded={open} onClick={event => {
          event.stopPropagation();
          setPinned(!pinned);
          setOpen(!pinned);
        }}><Info size={16} aria-hidden="true" /></button>
        <span id={id} role="tooltip" className={open ? 'is-pinned' : ''}>{information}</span>
      </span>}
    </span>
  </div>;
}
