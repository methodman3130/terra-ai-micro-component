import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";

/** Administrator user management. Role changes are audited server-side. */
export default function AdminPanel({ open, onClose }) {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);

  const load = () => api.users().then((r) => setUsers(r.users)).catch((e) => setError(e.message));

  useEffect(() => {
    if (open) load();
  }, [open]);

  if (!open) return null;

  async function change(id, fn) {
    setBusy(id);
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/30" onClick={onClose}>
      <aside
        className="h-full w-full max-w-2xl overflow-y-auto bg-white p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-uc-green-dark">User administration</h2>
            <p className="text-xs text-slate-500">
              Role changes are recorded with who made them and when.
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded px-2 py-1 text-sm text-slate-500 hover:bg-slate-100"
          >
            close
          </button>
        </div>

        {error && (
          <div className="mb-3 rounded border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
            {error}
          </div>
        )}

        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="py-1.5 pr-3">name</th>
              <th className="py-1.5 pr-3">email</th>
              <th className="py-1.5 pr-3">role</th>
              <th className="py-1.5 pr-3">status</th>
              <th className="py-1.5">last sign-in</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => {
              const self = u.user_id === user?.user_id;
              return (
                <tr key={u.user_id} className="border-b border-slate-100">
                  <td className="py-2 pr-3 font-medium text-slate-800">
                    {u.display_name}
                    {self && <span className="ml-1 text-[10px] text-slate-400">(you)</span>}
                  </td>
                  <td className="py-2 pr-3 text-slate-600">{u.email}</td>
                  <td className="py-2 pr-3">
                    <select
                      value={u.role}
                      disabled={busy === u.user_id || self}
                      title={self ? "You cannot change your own role" : undefined}
                      onChange={(e) =>
                        change(u.user_id, () => api.setRole(u.user_id, e.target.value))
                      }
                      className="rounded border border-slate-300 px-1.5 py-0.5 disabled:opacity-50"
                    >
                      <option value="user">user</option>
                      <option value="admin">admin</option>
                    </select>
                  </td>
                  <td className="py-2 pr-3">
                    <button
                      disabled={busy === u.user_id || self}
                      onClick={() =>
                        change(u.user_id, () => api.setActive(u.user_id, !u.is_active))
                      }
                      className={`rounded px-2 py-0.5 text-[11px] font-medium disabled:opacity-50 ${
                        u.is_active
                          ? "bg-uc-green/10 text-uc-green-dark"
                          : "bg-slate-200 text-slate-600"
                      }`}
                    >
                      {u.is_active ? "active" : "disabled"}
                    </button>
                  </td>
                  <td className="py-2 text-slate-500">
                    {u.last_login_at ? String(u.last_login_at).slice(0, 16).replace("T", " ") : "never"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        <p className="mt-4 text-[11px] leading-snug text-slate-500">
          You cannot remove your own administrator access or disable your own account, so a
          deployment can never be left with no administrator. Disabling an account ends its
          sessions on the next request rather than waiting for the token to expire.
        </p>
      </aside>
    </div>
  );
}
