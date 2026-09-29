import { useEffect, useState } from 'react';
import { configureApiSecurity, getCurrentUser, login, logout } from './client.js';

function LoginForm({ onLoggedIn }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  async function submit(event) {
    event.preventDefault();
    try {
      setError('');
      onLoggedIn(await login(username, password));
    } catch {
      setError('No s’ha pogut iniciar la sessió.');
    }
  }
  return <main className="app-frame grid min-h-screen place-items-center p-6"><form onSubmit={submit} className="glass-card grid w-full max-w-sm gap-4 p-6"><h1 className="text-xl font-bold">Inicia sessió</h1><label>Usuari<input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" className="w-full" /></label><label>Contrasenya<input value={password} onChange={(e) => setPassword(e.target.value)} type="password" autoComplete="current-password" className="w-full" /></label>{error && <p role="alert">{error}</p>}<button type="submit">Entra</button></form></main>;
}

export default function AuthGate({ children }) {
  // Authentication is the canonical default. Local demos may opt out only
  // explicitly, never by accidentally omitting a build variable.
  const required = import.meta.env.VITE_AUTH_REQUIRED !== 'false';
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(required);
  useEffect(() => {
    configureApiSecurity(() => setUser(null));
    if (!required) return;
    getCurrentUser().then(setUser).catch(() => setUser(null)).finally(() => setLoading(false));
  }, [required]);
  if (!required) return children;
  if (loading) return <main className="app-frame p-6">Carregant sessió…</main>;
  if (!user) return <LoginForm onLoggedIn={setUser} />;
  return <>{children}<button type="button" className="fixed right-4 top-4" onClick={() => logout().finally(() => setUser(null))}>Surt</button></>;
}
