import { useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Brand, PineRule } from "./Brand";

const MIN_PASSWORD = 12;

export default function AuthScreen() {
  const { signIn } = useAuth();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  const tooShort = mode === "register" && password.length > 0 && password.length < MIN_PASSWORD;

  async function submit(e) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      if (mode === "register") {
        const res = await api.register(email, name, password);
        setNotice(
          res.note
            ? `${res.note} You can sign in now.`
            : "Account created. You can sign in now."
        );
        setMode("login");
        setPassword("");
      } else {
        await signIn(email, password);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-uc-mist">
      <PineRule />
      <div className="flex flex-1 items-center justify-center px-4 py-10">
        <div className="w-full max-w-md">
          <div className="mb-6 flex justify-center">
            <Brand />
          </div>

          <div className="rounded-xl border border-uc-green/15 bg-white p-6 shadow-sm">
            <h1 className="text-lg font-semibold text-uc-green-dark">
              Project TERRA-AI
            </h1>
            <p className="mt-1 text-sm text-slate-600">
              Benguet farmgate price baseline. Sign in to view the panel.
            </p>

            <div className="mt-5 flex gap-1 rounded-lg bg-uc-mist p-1 text-sm">
              {["login", "register"].map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => {
                    setMode(m);
                    setError(null);
                  }}
                  className={`flex-1 rounded-md px-3 py-1.5 font-medium transition ${
                    mode === m
                      ? "bg-white text-uc-green-dark shadow-sm"
                      : "text-slate-600 hover:text-uc-green-dark"
                  }`}
                >
                  {m === "login" ? "Sign in" : "Register"}
                </button>
              ))}
            </div>

            <form onSubmit={submit} className="mt-5 space-y-3">
              {mode === "register" && (
                <Field
                  label="Full name"
                  value={name}
                  onChange={setName}
                  autoComplete="name"
                  required
                />
              )}
              <Field
                label="Institutional email"
                type="email"
                value={email}
                onChange={setEmail}
                autoComplete="username"
                required
              />
              <Field
                label="Password"
                type="password"
                value={password}
                onChange={setPassword}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                required
              />
              {mode === "register" && (
                <p className={`text-xs ${tooShort ? "text-amber-700" : "text-slate-500"}`}>
                  At least {MIN_PASSWORD} characters. A long passphrase beats a short
                  complicated one.
                </p>
              )}

              {error && (
                <div
                  role="alert"
                  className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800"
                >
                  {error}
                </div>
              )}
              {notice && (
                <div
                  role="status"
                  className="rounded-md border border-uc-green/30 bg-uc-green/5 px-3 py-2 text-sm text-uc-green-dark"
                >
                  {notice}
                </div>
              )}

              <button
                type="submit"
                disabled={busy || (mode === "register" && password.length < MIN_PASSWORD)}
                className="w-full rounded-md bg-uc-green px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-uc-green-dark disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy ? "Working…" : mode === "login" ? "Sign in" : "Create account"}
              </button>
            </form>
          </div>

          <p className="mt-4 text-center text-[11px] leading-snug text-slate-500">
            Research prototype. PSA OpenSTAT data under CC BY 4.0; PSA does not endorse
            this use.
          </p>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, type = "text", ...rest }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-700">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-uc-green focus:ring-2 focus:ring-uc-green/20"
        {...rest}
      />
    </label>
  );
}
