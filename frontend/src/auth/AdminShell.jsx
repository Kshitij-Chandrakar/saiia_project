import { useEffect, useRef, useState } from 'react';
import { Menu } from 'lucide-react';
import AdminSidebar from './AdminSidebar';
import { containDialogFocus } from './adminFocus';
import './admin-console.css';

export default function AdminShell({ identity, user, section, navigate, title, subtitle, controls, children }) {
  useEffect(() => { document.title = `${title} | Intervucopilot`; }, [title]);
  const dialog = useRef(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  function close() { dialog.current?.close(); }
  return <div className="admin-console">
    <a className="ac-skip" href="#admin-content">Skip to administration</a>
    <div className="ac-desktop-sidebar"><AdminSidebar identity={identity} user={user} section={section} navigate={navigate} /></div>
    <dialog className="ac-navigation-drawer" ref={dialog} aria-label="Administration navigation" onKeyDown={containDialogFocus} onClose={() => setDrawerOpen(false)} onCancel={() => setDrawerOpen(false)}><AdminSidebar identity={identity} user={user} section={section} navigate={navigate} close={close} /></dialog>
    <div className="ac-workspace">
      <header className="ac-page-header"><div className="ac-heading-group"><button className="ac-icon-button ac-menu-toggle" aria-label="Open navigation" aria-expanded={drawerOpen} onClick={() => { setDrawerOpen(true); dialog.current?.showModal(); dialog.current?.querySelector('[aria-current=page]')?.focus(); }}><Menu size={22} aria-hidden="true" /></button><div><h1>{title}</h1><p>{subtitle}</p></div></div>{controls && <div className="ac-header-controls">{controls}</div>}</header>
      {children}
    </div>
  </div>;
}
