import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../api/client";
import { Button, Card, ErrorNotice } from "../components/ui";
import "./AuthPages.css";

export function LoginPage() {
  const auth = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await auth.login(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <Card title="Sign in to Vero.ai">
        <form className="auth-form" onSubmit={handleSubmit}>
          <div className="settings-row">
            <label htmlFor="login-email">Email</label>
            <input
              id="login-email"
              type="email"
              required
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.currentTarget.value)}
            />
          </div>
          <div className="settings-row">
            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.currentTarget.value)}
            />
          </div>
          {error && <ErrorNotice message={error} />}
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? "Signing in..." : "Sign in"}
          </Button>
        </form>
        <p className="auth-switch">
          Don&apos;t have an account? <Link to="/register">Create one</Link>
        </p>
      </Card>
    </div>
  );
}
