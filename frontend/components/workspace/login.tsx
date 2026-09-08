"use client";
import { useState, type FormEvent } from "react";
import {
  ArrowUpRight,
  Fingerprint,
  Layers3,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { api } from "@/lib/api";
import type { S } from "@/lib/types";
import { Button, ErrorBanner, Field } from "./shared";
export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <span className="brand">
      <span className="brand-mark">
        <Layers3 size={20} />
      </span>
      {!compact && (
        <span>
          darknetra<span className="brand-period">.</span>
        </span>
      )}
    </span>
  );
}
export function Login({ onLogin }: { onLogin: (user: S<"UserMe">) => void }) {
  const [username, setUsername] = useState(""),
    [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onLogin(
        await api<S<"UserMe">>("/auth/login", "POST", { username, password }),
      );
    } catch (reason) {
      setError(reason);
    } finally {
      setPassword("");
      setBusy(false);
    }
  }
  return (
    <main className="login-page">
      <section className="login-story">
        <Brand />
        <div>
          <span className="eyebrow">
            <span className="live-dot" /> THE INVESTIGATION WORKSPACE
          </span>
          <h1>
            Bring the evidence.
            <br />
            <span>Find the connection.</span>
          </h1>
          <p>
            A focused space for your cases, intelligence, and the agents that
            help you make sense of it.
          </p>
          <div className="login-feature">
            <ShieldCheck />
            <div>
              <strong>Evidence at every step</strong>
              <span>Trace each finding back to its source.</span>
            </div>
          </div>
          <div className="login-feature">
            <Sparkles />
            <div>
              <strong>See your agents at work</strong>
              <span>Follow searches, tool calls, and delegated tasks.</span>
            </div>
          </div>
        </div>
        <footer>CASE INTELLIGENCE, CONNECTED.</footer>
      </section>
      <section className="login-form">
        <div className="login-form-inner">
          <div className="login-glyph">
            <Fingerprint size={28} />
          </div>
          <span className="eyebrow">WELCOME BACK</span>
          <h2>Your workspace awaits.</h2>
          <p>Sign in with your investigator account.</p>
          <form onSubmit={submit}>
            <Field label="Username">
              <input
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="Your username"
                required
              />
            </Field>
            <Field label="Password">
              <input
                autoComplete="current-password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Enter your password"
                required
              />
            </Field>
            <ErrorBanner error={error} />
            <Button className="w-full" size="lg" type="submit" disabled={busy}>
              {busy ? "Signing in…" : "Continue to workspace"}
              <ArrowUpRight size={17} />
            </Button>
          </form>
          <div className="login-note">
            <ShieldCheck size={15} /> Access is restricted to authorised
            investigators.
          </div>
        </div>
      </section>
    </main>
  );
}
export function ChangePassword({ onDone }: { onDone: () => void }) {
  const [current, setCurrent] = useState(""),
    [next, setNext] = useState(""),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false);
  return (
    <div className="centered-page">
      <div className="panel-card max-w-md w-full">
        <h1 className="text-xl font-semibold">Set your personal password</h1>
        <p className="muted mb-5">
          Your account requires a password change before continuing.
        </p>
        <form
          className="content-stack"
          onSubmit={async (event) => {
            event.preventDefault();
            setBusy(true);
            try {
              await api("/auth/change-password", "POST", {
                current_password: current,
                new_password: next,
              });
              onDone();
            } catch (reason) {
              setError(reason);
            } finally {
              setBusy(false);
            }
          }}
        >
          <Field label="Current password">
            <input
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(event) => setCurrent(event.target.value)}
              required
            />
          </Field>
          <Field label="New password" hint="At least 12 characters">
            <input
              type="password"
              autoComplete="new-password"
              minLength={12}
              value={next}
              onChange={(event) => setNext(event.target.value)}
              required
            />
          </Field>
          <ErrorBanner error={error} />
          <Button disabled={busy}>Save password</Button>
        </form>
      </div>
    </div>
  );
}
