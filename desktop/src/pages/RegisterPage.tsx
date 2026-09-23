import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../api/client";
import { Button, Card, ErrorNotice } from "../components/ui";
import "./AuthPages.css";

const MIN_PASSWORD_LENGTH = 10;

export function RegisterPage() {
  const auth = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await auth.register(email, password, name, organizationName);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create your account. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <Card title="Create your Vero.ai account">
        <form className="auth-form" onSubmit={handleSubmit}>
          <div className="settings-row">
            <label htmlFor="register-name">Your name</label>
            <input id="register-name" type="text" required autoFocus value={name} onChange={(e) => setName(e.currentTarget.value)} />
          </div>
          <div className="settings-row">
            <label htmlFor="register-email">Email</label>
            <input id="register-email" type="email" required value={email} onChange={(e) => setEmail(e.currentTarget.value)} />
          </div>
          <div className="settings-row">
            <label htmlFor="register-password">Password</label>
            <input
              id="register-password"
              type="password"
              required
              minLength={MIN_PASSWORD_LENGTH}
              value={password}
              onChange={(e) => setPassword(e.currentTarget.value)}
            />
            <span className="auth-hint">At least {MIN_PASSWORD_LENGTH} characters.</span>
          </div>
          <div className="settings-row">
            <label htmlFor="register-org">Organization name</label>
            <input
              id="register-org"
              type="text"
              required
              placeholder="e.g. Acme Retail"
              value={organizationName}
              onChange={(e) => setOrganizationName(e.currentTarget.value)}
            />
            <span className="auth-hint">You&apos;ll be its owner; you can add other people to it later.</span>
          </div>
          {error && <ErrorNotice message={error} />}
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? "Creating account..." : "Create account"}
          </Button>
        </form>
        <p className="auth-switch">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </Card>
    </div>
  );
}
