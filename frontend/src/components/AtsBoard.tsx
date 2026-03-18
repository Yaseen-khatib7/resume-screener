import { useEffect, useMemo, useState } from "react";
import Pagination from "./Pagination";
import { api } from "../api";
import type { AtsTrackerCandidate, Candidate } from "../types/screening";

type Props = {
  sessionId: string;
  visible: boolean;
};

const STAGES = ["New", "Screening", "Interview", "Offer", "Hired", "Rejected"];
const PAGE_SIZE = 6;

function AtsBadge({ status }: { status?: Candidate["atsStatus"] }) {
  if (!status) return <span className="hint">-</span>;
  const cls =
    status === "PASS" ? "atsBadge pass" : status === "REVIEW" ? "atsBadge review" : "atsBadge fail";
  return <span className={cls}>ATS {status}</span>;
}

export default function AtsBoard({ sessionId, visible }: Props) {
  const [rows, setRows] = useState<AtsTrackerCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [savingName, setSavingName] = useState<string>("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    async function loadAts() {
      if (!visible || !sessionId) return;
      setLoading(true);
      try {
        const res = await api.get(`/ats/${sessionId}`);
        if (res.data?.ok) {
          setRows(res.data.candidates || []);
          setPage(1);
        }
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }

    loadAts().catch(() => {});
  }, [sessionId, visible]);

  async function saveRow(next: AtsTrackerCandidate) {
    setSavingName(next.candidate);
    try {
      const form = new FormData();
      form.append("session_id", sessionId);
      form.append("candidate", next.candidate);
      form.append("stage", next.stage);
      form.append("notes", next.notes || "");

      const res = await api.post("/ats/update", form);
      if (res.data?.ok) {
        setRows((prev) =>
          prev.map((item) => (item.candidate === next.candidate ? { ...item, ...res.data.candidate_state } : item))
        );
      }
    } catch (e) {
      console.error(e);
      alert("Failed to update ATS state.");
    } finally {
      setSavingName("");
    }
  }

  function setStage(candidate: string, stage: string) {
    setRows((prev) => prev.map((item) => (item.candidate === candidate ? { ...item, stage } : item)));
  }

  function setNotes(candidate: string, notes: string) {
    setRows((prev) => prev.map((item) => (item.candidate === candidate ? { ...item, notes } : item)));
  }

  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const pagedRows = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return rows.slice(start, start + PAGE_SIZE);
  }, [page, rows]);

  if (!visible) return null;

  return (
    <div className="card atsBoardCard">
      <div className="panelIntro">
        <div>
          <div className="cardTitle" style={{ marginBottom: 4 }}>ATS Tracker</div>
          <div className="hint">Track ATS outcomes and move screened candidates through the hiring pipeline.</div>
        </div>
        <div className="panelMeta">{rows.length} tracked candidates</div>
      </div>

      {loading ? (
        <div className="hint">Loading ATS board...</div>
      ) : rows.length === 0 ? (
        <div className="emptyState">Run screening to initialize candidate tracking for the current session.</div>
      ) : (
        <>
          <div className="tableWrap" style={{ marginTop: 12 }}>
            <table className="table" style={{ minWidth: 1020 }}>
              <thead>
                <tr>
                  <th>Candidate</th>
                  <th>ATS</th>
                  <th>Decision</th>
                  <th>Score</th>
                  <th>Stage</th>
                  <th>Notes</th>
                  <th>Updated</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {pagedRows.map((row) => (
                  <tr key={row.candidate} className={row.atsStatus === "FAIL" ? "rejectedRow" : ""}>
                    <td>{row.candidate}</td>
                    <td>
                      <div className="atsCell">
                        <AtsBadge status={row.atsStatus} />
                        <span className="hint">{row.atsScore ?? "-"}</span>
                      </div>
                    </td>
                    <td>{row.atsDecision === "Reject" ? "Rejected by ATS validation" : row.atsDecision || "-"}</td>
                    <td>{row.score ?? "-"}</td>
                    <td style={{ minWidth: 150 }}>
                      <select value={row.stage} onChange={(e) => setStage(row.candidate, e.target.value)}>
                        {STAGES.map((stage) => (
                          <option key={stage} value={stage}>
                            {stage}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td style={{ minWidth: 240 }}>
                      <textarea
                        rows={2}
                        value={row.notes || ""}
                        onChange={(e) => setNotes(row.candidate, e.target.value)}
                        placeholder="Add recruiter notes"
                      />
                      {row.atsReasons?.length ? (
                        <div className="hint" style={{ marginTop: 6 }}>
                          {row.atsReasons.slice(0, 2).join(" | ")}
                        </div>
                      ) : null}
                    </td>
                    <td>{row.updated_at ? row.updated_at.slice(0, 10) : "-"}</td>
                    <td>
                      <button className="secondaryBtn" onClick={() => saveRow(row)} disabled={savingName === row.candidate}>
                        {savingName === row.candidate ? "Saving..." : "Save"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <Pagination
            page={page}
            totalPages={totalPages}
            onPageChange={setPage}
            label={`${rows.length} ATS records`}
          />
        </>
      )}
    </div>
  );
}
