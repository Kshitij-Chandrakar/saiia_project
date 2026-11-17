import AdminSuccessor from '../../src/auth/AdminSuccessor';
import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom';
import AdminConsole from '../../src/auth/AdminConsole';
import { supabase } from '../../src/auth/supabaseClient';
import '../../src/index.css';

export default function Login() {
  const [email, setEmail] = useState(''), [password, setPassword] = useState(''), [error, setError] = useState(false);
  const navigate = useNavigate();
  return <form onSubmit={async event => { event.preventDefault(); const result = await supabase.auth.signInWithPassword({ email, password }); if (result.error) setError(true); else navigate('/auth/admin'); }}>
    <h1>Isolated synthetic identity login</h1><label>Synthetic email<input type="email" value={email} onChange={event => setEmail(event.target.value)} /></label><label>Synthetic password<input type="password" value={password} onChange={event => setPassword(event.target.value)} /></label><button>Sign in</button>{error && <p role="alert">Synthetic login failed</p>}
  </form>;
}
createRoot(document.getElementById('root')).render(<BrowserRouter><p style={{ padding: 12, background: '#fff3d6', color: '#473912', margin: 0 }}>LOCAL ACCEPTANCE - synthetic accounts; actual Auth and application APIs. No production data.</p><Routes><Route path="/auth/login" element={<Login />} /><Route path="/auth/admin/successor" element={<AdminSuccessor backendUrl="" />} /><Route path="*" element={<AdminConsole backendUrl="" />} /></Routes></BrowserRouter>);
