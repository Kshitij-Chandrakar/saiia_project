import React, { useEffect, useLayoutEffect, useRef, useState, useId } from 'react'
import { createPortal } from 'react-dom'
import { Cpu, ChevronDown, Check } from 'lucide-react'
import openai from '../assets/provider-logos/openai.svg'
import groq from '../assets/provider-logos/groq.svg'
import gemini from '../assets/provider-logos/googlegemini.svg'

const logos = { openai, groq, gemini }
function Logo({ name }) {
  const asset = Object.hasOwn(logos, name) ? logos[name] : null
  return asset ? <img src={asset} alt="" aria-hidden="true" /> : <Cpu aria-hidden="true" size={18} />
}

export default function AnswerModelSelect({ items, value, onChange, disabled, placeholder = 'Choose a model' }) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [position, setPosition] = useState({})
  const trigger = useRef(null), popup = useRef(null), options = useRef([])
  const id = useId()
  const selected = items.find(m => m.key === value)
  const close = (restore = false) => { setOpen(false); if (restore) trigger.current?.focus() }
  useEffect(() => { if (disabled) setOpen(false) }, [disabled])
  useLayoutEffect(() => {
    if (!open) return
    const place = () => {
      const r = trigger.current.getBoundingClientRect()
      if (r.bottom < 0 || r.top > window.innerHeight) { close(); return }
      const width = Math.min(360, window.innerWidth - 16)
      const below = window.innerHeight - r.bottom - 12
      const above = r.top - 12
      const down = below >= 200 || below >= above
      setPosition({ position: 'fixed', width, left: Math.max(8, Math.min(r.left, window.innerWidth - width - 8)),
        maxHeight: Math.max(40, Math.min(320, down ? below : above)),
        ...(down ? { top: r.bottom + 6 } : { bottom: window.innerHeight - r.top + 6 }) })
    }
    place()
    window.addEventListener('resize', place)
    document.addEventListener('scroll', place, true)
    const outside = e => { if (!popup.current?.contains(e.target) && !trigger.current?.contains(e.target)) close() }
    document.addEventListener('pointerdown', outside)
    return () => { window.removeEventListener('resize', place); document.removeEventListener('scroll', place, true); document.removeEventListener('pointerdown', outside) }
  }, [open])
  useEffect(() => { if (open) { options.current[active]?.focus({ preventScroll: true }); options.current[active]?.scrollIntoView({ block: 'nearest' }) } }, [open, active])
  const show = () => {
    setActive(Math.max(0, items.findIndex(m => m.key === value)))
    setOpen(true)
  }
  const select = model => { if (model.selectable) { onChange(model.key); close(true) } }
  const keyDown = event => {
    if (event.key === 'Escape') { event.preventDefault(); close(true); return }
    if (event.key === 'Tab') { close(true); return }
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(items[active]); return }
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const available = items.map((m,i) => m.selectable ? i : -1).filter(i => i >= 0)
    if (!available.length) return
    const index = available.indexOf(active)
    setActive(event.key === 'Home' ? available[0] : event.key === 'End' ? available.at(-1) : available[(index + (event.key === 'ArrowUp' ? -1 : 1) + available.length) % available.length])
  }
  return <div className="setup-model-field">
    <span id={`${id}-label`}>AI Model</span>
    <button ref={trigger} type="button" className="setup-model-trigger" aria-labelledby={`${id}-label ${id}-value`}
      aria-describedby="setup-model-description" aria-haspopup="listbox" aria-expanded={open} aria-controls={open ? `${id}-list` : undefined}
      disabled={disabled} onClick={() => open ? close(true) : show()} onKeyDown={e => { if (['ArrowDown','ArrowUp'].includes(e.key)) { e.preventDefault(); show() } }}>
      {selected && <Logo name={selected.logo_key} />}<span id={`${id}-value`}>{selected?.display_name || placeholder}</span><ChevronDown size={14} aria-hidden="true" />
    </button>
    {open && createPortal(<div ref={popup} id={`${id}-list`} role="listbox" aria-labelledby={`${id}-label`} className="setup-model-popup" style={position} onKeyDown={keyDown}>
      {items.map((model,i) => <button ref={el => { options.current[i] = el }} key={model.key} type="button" role="option" tabIndex={i === active ? 0 : -1}
        aria-selected={model.key === value} aria-disabled={!model.selectable} aria-describedby={`${id}-description-${i}`} onFocus={() => setActive(i)} onClick={() => select(model)}>
        <Logo name={model.logo_key} /><span><strong>{model.display_name}</strong>{model.default && <small className="setup-model-badge">Default</small>}
          <span id={`${id}-description-${i}`}>{model.description}{!model.selectable ? ' · Unavailable' : ''}</span></span>{model.key === value && <Check size={15} aria-hidden="true" />}
      </button>)}
    </div>, document.body)}
  </div>
}
