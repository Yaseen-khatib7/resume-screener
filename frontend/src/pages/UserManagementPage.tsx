import { useEffect, useMemo, useState } from "react";
import Pagination from "../components/Pagination";
import { api } from "../api";
import type {
  AdminUserCreatePayload,
  AdminUserUpdatePayload,
  EmailTemplates,
  UserProfile,
  UserRole,
} from "../types/auth";

const PAGE_SIZE = 8;

type CreateFormState = {
  name: string;
  email: string;
  password: string;
  role: UserRole;
};

export default function UserManagementPage() {
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [savingUid, setSavingUid] = useState("");
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [createForm, setCreateForm] = useState<CreateFormState>({
    name: "",
    email: "",
    password: "",
    role: "hr",
  });
  const [templates, setTemplates] = useState<EmailTemplates>({
    acceptanceSubject: "",
    acceptanceBody: "",
    processingSubject: "",
    processingBody: "",
    rejectionSubject: "",
    rejectionBody: "",
  });
  const [activeTemplate, setActiveTemplate] = useState<"acceptance" | "processing" | "rejection">("acceptance");

  async function loadUsers() {
    setLoading(true);
    try {
      const res = await api.get("/admin/users");
      setUsers(res.data?.users || []);
    } catch (error) {
      console.error(error);
      setStatus("Could not load users.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadUsers().catch(() => {});
  }, []);

  useEffect(() => {
    async function loadTemplates() {
      try {
        const res = await api.get("/admin/email-templates");
        if (res.data?.templates) {
          setTemplates(res.data.templates as EmailTemplates);
        }
      } catch (error) {
        console.error(error);
      }
    }

    loadTemplates().catch(() => {});
  }, []);

  const filteredUsers = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return users;
    return users.filter((user) =>
      [user.name, user.email, user.role, user.status].some((value) => String(value).toLowerCase().includes(needle))
    );
  }, [query, users]);

  const totalPages = Math.max(1, Math.ceil(filteredUsers.length / PAGE_SIZE));
  const pageRows = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return filteredUsers.slice(start, start + PAGE_SIZE);
  }, [filteredUsers, page]);

  useEffect(() => {
    setPage(1);
  }, [query, users]);

  async function createUser() {
    setStatus("");
    setSavingUid("create");
    try {
      const payload: AdminUserCreatePayload = {
        name: createForm.name,
        email: createForm.email,
        password: createForm.password,
        role: createForm.role,
      };
      await api.post("/admin/users", payload);
      setCreateForm({ name: "", email: "", password: "", role: "hr" });
      setStatus("User created successfully.");
      await loadUsers();
    } catch (error) {
      console.error(error);
      setStatus("Could not create user.");
    } finally {
      setSavingUid("");
    }
  }

  async function updateUser(uid: string, payload: AdminUserUpdatePayload) {
    setStatus("");
    setSavingUid(uid);
    try {
      await api.patch(`/admin/users/${uid}`, payload);
      setStatus("User updated successfully.");
      await loadUsers();
    } catch (error) {
      console.error(error);
      setStatus("Could not update user.");
    } finally {
      setSavingUid("");
    }
  }

  async function saveTemplates() {
    setStatus("");
    setSavingUid("templates");
    try {
      await api.patch("/admin/email-templates", templates);
      setStatus("Email templates updated successfully.");
    } catch (error) {
      console.error(error);
      setStatus("Could not update email templates.");
    } finally {
      setSavingUid("");
    }
  }

  return (
    <div className="card">
      <div className="panelIntro">
        <div>
          <div className="cardTitle" style={{ marginBottom: 4 }}>User Management</div>
          <div className="hint">Admin-only controls for account creation, role assignment, and suspension.</div>
        </div>
        <div className="panelMeta">{users.length} total users</div>
      </div>

      {status ? <div className="statusBanner info" style={{ marginBottom: 12 }}>{status}</div> : null}

      <div className="sectionCard">
        <div className="cardTitle">Email Templates</div>
        <div className="hint" style={{ marginBottom: 12 }}>
          Edit the shared candidate email templates. Available placeholders:
          <span className="mono"> {"{{candidateName}}"}</span>
          <span className="mono"> {"{{candidateEmail}}"}</span>
        </div>

        <div className="field">
          <label>Select Template</label>
          <select value={activeTemplate} onChange={(e) => setActiveTemplate(e.target.value as "acceptance" | "processing" | "rejection")}>
            <option value="acceptance">Acceptance Email</option>
            <option value="processing">Processing Email</option>
            <option value="rejection">Rejection Email</option>
          </select>
        </div>

        {activeTemplate === "acceptance" ? (
          <>
            <div className="field">
              <label>Acceptance Subject</label>
              <input
                type="text"
                value={templates.acceptanceSubject}
                onChange={(e) => setTemplates((prev) => ({ ...prev, acceptanceSubject: e.target.value }))}
              />
            </div>
            <div className="field">
              <label>Acceptance Body</label>
              <textarea
                rows={8}
                value={templates.acceptanceBody}
                onChange={(e) => setTemplates((prev) => ({ ...prev, acceptanceBody: e.target.value }))}
              />
            </div>
          </>
        ) : null}

        {activeTemplate === "processing" ? (
          <>
            <div className="field">
              <label>Processing Subject</label>
              <input
                type="text"
                value={templates.processingSubject}
                onChange={(e) => setTemplates((prev) => ({ ...prev, processingSubject: e.target.value }))}
              />
            </div>
            <div className="field">
              <label>Processing Body</label>
              <textarea
                rows={8}
                value={templates.processingBody}
                onChange={(e) => setTemplates((prev) => ({ ...prev, processingBody: e.target.value }))}
              />
            </div>
          </>
        ) : null}

        {activeTemplate === "rejection" ? (
          <>
            <div className="field">
              <label>Rejection Subject</label>
              <input
                type="text"
                value={templates.rejectionSubject}
                onChange={(e) => setTemplates((prev) => ({ ...prev, rejectionSubject: e.target.value }))}
              />
            </div>
            <div className="field">
              <label>Rejection Body</label>
              <textarea
                rows={10}
                value={templates.rejectionBody}
                onChange={(e) => setTemplates((prev) => ({ ...prev, rejectionBody: e.target.value }))}
              />
            </div>
          </>
        ) : null}

        <button className="primaryBtn" onClick={saveTemplates} disabled={savingUid === "templates"}>
          {savingUid === "templates" ? "Saving..." : "Save Email Templates"}
        </button>
      </div>

      <div className="sectionCard">
        <div className="cardTitle">Create User</div>
        <div className="adminGrid">
          <div className="field">
            <label>Name</label>
            <input
              type="text"
              value={createForm.name}
              onChange={(e) => setCreateForm((prev) => ({ ...prev, name: e.target.value }))}
            />
          </div>
          <div className="field">
            <label>Email</label>
            <input
              type="email"
              value={createForm.email}
              onChange={(e) => setCreateForm((prev) => ({ ...prev, email: e.target.value }))}
            />
          </div>
          <div className="field">
            <label>Password</label>
            <input
              type="password"
              value={createForm.password}
              onChange={(e) => setCreateForm((prev) => ({ ...prev, password: e.target.value }))}
            />
          </div>
          <div className="field">
            <label>Role</label>
            <select
              value={createForm.role}
              onChange={(e) => setCreateForm((prev) => ({ ...prev, role: e.target.value as UserRole }))}
            >
              <option value="hr">HR</option>
              <option value="admin">Admin</option>
            </select>
          </div>
        </div>
        <button className="primaryBtn" onClick={createUser} disabled={savingUid === "create"}>
          {savingUid === "create" ? "Creating..." : "Create User"}
        </button>
      </div>

      <div className="sectionCard">
        <div className="rowBetween">
          <div>
            <div className="cardTitle">All Users</div>
            <div className="hint">Search by name, email, role, or status.</div>
          </div>
          <div className="adminSearch">
            <input type="text" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search users" />
          </div>
        </div>

        {loading ? (
          <div className="emptyState" style={{ marginTop: 12 }}>Loading users...</div>
        ) : (
          <>
            <div className="tableWrap" style={{ marginTop: 12 }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((user) => (
                    <tr key={user.uid}>
                      <td>{user.name || "-"}</td>
                      <td>{user.email}</td>
                      <td>
                        <select
                          value={user.role}
                          onChange={(e) => updateUser(user.uid, { role: e.target.value as UserRole })}
                        >
                          <option value="hr">HR</option>
                          <option value="admin">Admin</option>
                        </select>
                      </td>
                      <td>{user.status}</td>
                      <td>{user.createdAt ? user.createdAt.slice(0, 10) : "-"}</td>
                      <td>
                        <button
                          className="secondaryBtn"
                          onClick={() =>
                            updateUser(user.uid, { status: user.status === "active" ? "suspended" : "active" })
                          }
                          disabled={savingUid === user.uid}
                        >
                          {savingUid === user.uid
                            ? "Saving..."
                            : user.status === "active"
                            ? "Suspend"
                            : "Reactivate"}
                        </button>
                      </td>
                    </tr>
                  ))}
                  {pageRows.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="hint">No users found.</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>

            <Pagination page={page} totalPages={totalPages} onPageChange={setPage} label={`${filteredUsers.length} users`} />
          </>
        )}
      </div>
    </div>
  );
}
