import { createElement, useEffect, useRef, useState } from 'react';
import { Activity, BriefcaseBusiness, Ellipsis, FileClock, Home, LayoutDashboard, LogOut, Megaphone, Shield, Ticket, Users, X } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import logo from '../assets/dashboard/logo.svg';
import { supabase } from './supabaseClient';
import { signOutWebsite } from './websiteSessionLoss';

const entries = [
  ['overview', 'Overview', LayoutDashboard], ['users', 'Customers', Users], ['campaigns', 'Campaigns', Megaphone],
  ['memberships', 'Administrators', Shield], ['coupons', 'Coupon drafts', Ticket], ['audit', 'Audit history', FileClock],
];

export default function AdminSidebar({ identity, user, section, navigate, close }) {
  const navigateTo = useNavigate(), accountOptions = useRef(null), optionsTrigger = useRef(null);
  const [optionsOpen, setOptionsOpen] = useState(false), [logoutPending, setLogoutPending] = useState(false), [logoutError, setLogoutError] = useState('');
  const name = [user?.user_metadata?.full_name, user?.user_metadata?.display_name, user?.user_metadata?.name, user?.email?.split('@')[0]].find(value => typeof value === 'string' && value.trim()) || 'Checking account';
  const initials = name.split(/[\s@._-]+/).filter(Boolean).slice(0, 2).map(part => part[0]).join('').toUpperCase();
  useEffect(() => {
    if (!optionsOpen) return undefined;
    function dismiss(event) {
      if (event.type === 'keydown' && event.key !== 'Escape') return;
      if (event.type === 'pointerdown' && accountOptions.current?.contains(event.target)) return;
      setOptionsOpen(false);
      if (event.type === 'keydown' || event.type === 'pointerdown') optionsTrigger.current?.focus();
    }
    document.addEventListener('pointerdown', dismiss);
    document.addEventListener('keydown', dismiss);
    return () => { document.removeEventListener('pointerdown', dismiss); document.removeEventListener('keydown', dismiss); };
  }, [optionsOpen]);
  async function logout() {
    if (logoutPending) return;
    setLogoutPending(true); setLogoutError('');
    try {
      const result = await signOutWebsite(supabase);
      if (result?.error) throw new Error('Sign out failed. Please try again.');
      navigateTo('/auth/login', { replace: true, state: { authMessage: 'Signed out.' } });
    } catch {
      setLogoutError('Sign out failed. Please try again.'); setLogoutPending(false); setOptionsOpen(true);
    }
  }
  return <aside className="ac-sidebar" aria-label="Administration sidebar">
    <div className="ac-sidebar-brand"><Link to="/auth/dashboard" className="ac-brand"><img src={logo} alt="" /><span>Intervucopilot</span></Link>{close && <button className="ac-icon-button" aria-label="Close navigation" onClick={close}><X size={20} aria-hidden="true" /></button>}</div>
    {identity ? <nav aria-label="Administration">{entries.filter(([key]) => ['overview', 'users', 'campaigns'].includes(key) || identity.role === 'super_admin').map(([key, label, Icon]) => <button className={key === 'memberships' ? 'ac-management-start' : undefined} key={key} aria-current={section === key ? 'page' : undefined} onClick={() => { navigate(key); close?.(); }}>{createElement(Icon, { size: 20, strokeWidth: 1.6, 'aria-hidden': true })}<span>{label}</span></button>)}{identity.role === 'super_admin' && <Link to="/auth/admin/subscriptions" aria-current={section === 'commercial' ? 'page' : undefined} onClick={close}><BriefcaseBusiness size={20} strokeWidth={1.6} aria-hidden="true" /><span>Commercial configuration</span></Link>}</nav> : <div className="ac-navigation-loading" aria-label="Checking administration access"><Activity size={20} aria-hidden="true" /><span>Checking access</span></div>}
    <div className="ac-account" ref={accountOptions} onKeyDown={event => { if (event.key === 'Escape' && optionsOpen) { event.preventDefault(); event.stopPropagation(); setOptionsOpen(false); optionsTrigger.current?.focus(); } }}><span className="ac-initials" aria-hidden="true">{initials}</span><div className="ac-account-details"><strong title={user?.email}>{name}</strong><span>{identity ? identity.role === 'super_admin' ? 'Super admin' : 'Admin' : 'Access not confirmed'}</span></div><button ref={optionsTrigger} type="button" className="ac-account-options-trigger" aria-label="Account options" aria-expanded={optionsOpen} aria-haspopup="true" onClick={() => { setLogoutError(''); setOptionsOpen(value => !value); }}><Ellipsis size={20} aria-hidden="true" /></button>{optionsOpen && <div className="ac-account-options" aria-label="Account options"><Link to="/auth/dashboard" onClick={() => { setOptionsOpen(false); close?.(); }}>{createElement(Home, { size: 16, 'aria-hidden': true })}<span>Home</span></Link><button type="button" disabled={logoutPending} onClick={logout}>{createElement(LogOut, { size: 16, 'aria-hidden': true })}<span>{logoutPending ? 'Logging out…' : 'Log out'}</span></button>{logoutError && <span className="ac-account-options-error" role="alert">{logoutError}</span>}</div>}</div>
  </aside>;
}
