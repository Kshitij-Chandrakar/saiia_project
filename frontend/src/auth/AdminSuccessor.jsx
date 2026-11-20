import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { supabase } from './supabaseClient';
import './admin-console.css';

export default function AdminSuccessor({ backendUrl, client = supabase }) {
  const [session, setSession] = useState(null), [reference, setReference] = useState(''), [code, setCode] = useState(''), [status, setStatus] = useState(''), [busy, setBusy] = useState(false), [accepted, setAccepted] = useState(false);
  const locked = useRef(false), generation = useRef(0), active = useRef(null);
  useEffect(() => {
    let mounted = true, subject; const generationRef = generation;
    if (!client) return;
    client.auth.getSession().then(({ data }) => { if (mounted && subject === undefined) { subject = data.session?.user?.id; setSession(data.session); } });
    const subscription = client.auth.onAuthStateChange((_event, next) => { if (!mounted) return; if (subject !== next?.user?.id) { ++generation.current; active.current?.abort(); setCode(''); setStatus(''); setAccepted(false); } subject = next?.user?.id; setSession(next); }).data.subscription;
    return () => { mounted = false; ++generationRef.current; active.current?.abort(); subscription.unsubscribe(); };
  }, [client]);
  async function run(kind) {
    if (locked.current || !session?.access_token) return;
    locked.current = true; setBusy(true); const current = generation.current;
    const controller = new AbortController(); active.current = controller;
    try {
      if (kind === 'proof') {
        const factors = await client.auth.mfa.listFactors(), factor = factors.data?.totp?.find(x => x.status === 'verified');
        if (!factor || factors.error) throw Error();
        const response = await client.auth.mfa.challengeAndVerify({ factorId: factor.id, code });
        if (response.error) throw Error();
        setCode(''); return;
      }
      const response = await fetch(backendUrl.replace(/\/$/, '') + '/api/admin/' + (kind === 'verify' ? 'me' : 'successor/accept'), { method: kind === 'verify' ? 'GET' : 'POST', signal: controller.signal, credentials: 'omit', redirect: 'error', cache: 'no-store', headers: { Authorization: 'Bearer ' + session.access_token, 'Content-Type': 'application/json' }, ...(kind === 'verify' ? {} : { body: JSON.stringify({ transfer_id: reference, confirm: true }) }) });
      if (!response.ok) throw Error();
      const result = await response.json();
      if (kind === 'verify' && result.role !== 'super_admin') throw Error();
      if (current === generation.current) { setAccepted(kind === 'accept'); setStatus(kind === 'verify' ? 'Successor administration access verified.' : 'Transfer accepted. Verify administration access to finish.'); }
    } catch { if (current === generation.current) setStatus('Not confirmed. Check your identity, current authenticator proof and transfer expiry.'); }
    finally { locked.current = false; setBusy(false); }
  }
  return <main className="admin-console"><section style={{ padding: 32, maxWidth: 760, margin: 'auto' }}><h1>Accept successor responsibility</h1><p>A current Super admin must offer this transfer to your verified existing account. Acceptance grants Super admin responsibility; it does not remove the current Super admin or block either person’s own account deletion.</p>{session ? <><form onSubmit={event => { event.preventDefault(); void run('proof'); }}><label>Authenticator code<input required pattern="[0-9]{6}" inputMode="numeric" autoComplete="one-time-code" value={code} onChange={e => setCode(e.target.value)} /></label><button disabled={busy}>Verify authenticator</button></form><form onSubmit={event => { event.preventDefault(); void run('accept'); }}><label>Transfer reference<input required disabled={busy} pattern="[0-9a-fA-F-]{36}" value={reference} onChange={e => { setReference(e.target.value); setAccepted(false); }} /></label><button disabled={busy}>Accept Super admin responsibility</button></form><button disabled={busy || !accepted} onClick={() => run('verify')}>Verify administration access</button><Link to="/auth/admin">Open administration</Link></> : <Link to="/auth/login?next=/auth/admin/successor">Sign in with the designated existing account</Link>}{status && <p role="status">{status}</p>}<p>Emergency recovery remains unavailable.</p></section></main>;
}
