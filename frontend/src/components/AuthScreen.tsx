
import { useState, type FormEvent } from "react";
import { useAuth } from "../context/AuthContext";
import "./AuthScreen.css";

export default function AuthScreen() {
  const { login, register } = useAuth();

  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");

    if (mode === "register" && password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setSubmitting(true);

    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password);
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Authentication failed.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const switchMode = () => {
    setMode((current) => current === "login" ? "register" : "login");
    setError("");
    setPassword("");
    setConfirmPassword("");
  };

  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="auth-brand">
          <div className="auth-brand-icon">D</div>
          <div>
            <h1>DocuFlow AI</h1>
            <p>Document Intelligence Platform</p>
          </div>
        </div>

        <div className="auth-heading">
          <h2>
            {mode === "login" ? "Welcome back" : "Create your account"}
          </h2>
          <p>
            {mode === "login"
              ? "Sign in to manage your business documents."
              : "Get started with intelligent document processing."}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          <div className="auth-field">
            <label htmlFor="auth-email">Email address</label>
            <input
              id="auth-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
              required
              disabled={submitting}
            />
          </div>

          <div className="auth-field">
            <label htmlFor="auth-password">Password</label>
            <input
              id="auth-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Enter your password"
              autoComplete={
                mode === "login" ? "current-password" : "new-password"
              }
              minLength={8}
              required
              disabled={submitting}
            />
          </div>

          {mode === "register" && (
            <div className="auth-field">
              <label htmlFor="auth-confirm-password">Confirm password</label>
              <input
                id="auth-confirm-password"
                type="password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                placeholder="Confirm your password"
                autoComplete="new-password"
                minLength={8}
                required
                disabled={submitting}
              />
            </div>
          )}

          {error && <div className="auth-error">{error}</div>}

          <button
            type="submit"
            className="auth-submit"
            disabled={submitting}
          >
            {submitting
              ? "Please wait..."
              : mode === "login" ? "Sign In" : "Create Account"}
          </button>
        </form>

        <div className="auth-switch">
          {mode === "login"
            ? "Don't have an account?"
            : "Already have an account?"}
          {" "}
          <button type="button" onClick={switchMode} disabled={submitting}>
            {mode === "login" ? "Create account" : "Sign in"}
          </button>
        </div>

        <p className="auth-footer">
          AI-powered business document processing
        </p>
      </section>
    </main>
  );
}
