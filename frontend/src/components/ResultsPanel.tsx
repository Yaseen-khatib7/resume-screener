import { useMemo, useState } from "react";
import Pagination from "./Pagination";
import type { Candidate, ScreenResponse } from "../types/screening";

type Warning = {
  file: string;
  severity: string;
  message: string;
};

type CsvRow = Record<string, string | number>;

const SHORTLIST_PAGE_SIZE = 6;
const RANKED_PAGE_SIZE = 8;

function ScorePill({ score }: { score: number }) {
  const cls = score >= 80 ? "pill good" : score >= 60 ? "pill mid" : "pill low";
  return <span className={cls}>{score}</span>;
}

function AtsBadge({ status }: { status: Candidate["atsStatus"] }) {
  const cls =
    status === "PASS" ? "atsBadge pass" : status === "REVIEW" ? "atsBadge review" : "atsBadge fail";
  return <span className={cls}>ATS {status}</span>;
}

function candidateRowClass(r: Candidate, selectedCandidate: string | null) {
  const classes = [];
  if (selectedCandidate === r.candidate) classes.push("activeRow");
  if (r.atsStatus === "FAIL") classes.push("rejectedRow");
  return classes.join(" ");
}

function paginate<T>(items: T[], page: number, pageSize: number) {
  const start = (page - 1) * pageSize;
  return items.slice(start, start + pageSize);
}

export default function ResultsPanel({
  data,
  loading,
  onSelectCandidate,
  selectedCandidate,
  mode = "overview",
}: {
  data: ScreenResponse | null;
  loading: boolean;
  onSelectCandidate: (name: string) => void;
  selectedCandidate: string | null;
  mode?: "overview" | "ranked";
}) {
  if (loading) {
    return (
      <div className="card">
        <div className="cardTitle">Results</div>
        <div className="hint">Running screening...</div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="card">
        <div className="cardTitle">Results</div>
        <div className="hint">
          Upload files and click <b>Shortlist</b> to see results.
        </div>
      </div>
    );
  }

  const shortlist = data.shortlist || [];
  const ranked = data.ranked || [];
  const warnings: Warning[] = data.warnings || [];
  const atsSummary = data.atsSummary;
  const showShortlist = mode === "overview";
  const showRanked = mode === "ranked";
  const shortlistKey = data.session_id || `shortlist-${shortlist.length}-${ranked.length}`;
  const rankedKey = data.session_id || `ranked-${ranked.length}-${shortlist.length}`;

  return (
    <div className="card resultsCard">
      <div className="panelIntro">
        <div>
          <div className="cardTitle" style={{ marginBottom: 4 }}>Screening Results</div>
          <div className="hint">
            {mode === "overview"
              ? "Use the shortlist to review the strongest ATS-approved matches first."
              : "Audit the full ranking, including ATS-rejected resumes and borderline candidates."}
          </div>
        </div>
        <div className="panelMeta">Model in use: <b>{data.modelUsed}</b></div>
      </div>

      {warnings.length > 0 && (
        <div className="warningPanel">
          <b>Upload warnings</b>
          <div className="hint">Some files may be scanned or low-text. Results may be less accurate.</div>
          <ul style={{ marginTop: 8 }}>
            {warnings.map((w, idx) => (
              <li key={idx} style={{ fontSize: 13 }}>
                <b>{w.file}</b>: {w.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {atsSummary && (
        <div className="atsSummaryGrid">
          <div className="atsSummaryCard">
            <span className="hint">ATS Pass</span>
            <strong>{atsSummary.pass}</strong>
          </div>
          <div className="atsSummaryCard">
            <span className="hint">ATS Review</span>
            <strong>{atsSummary.review}</strong>
          </div>
          <div className="atsSummaryCard">
            <span className="hint">ATS Fail</span>
            <strong>{atsSummary.fail}</strong>
          </div>
          <div className="atsSummaryCard">
            <span className="hint">Sent to model</span>
            <strong>{atsSummary.screened}</strong>
          </div>
        </div>
      )}

      {showShortlist ? (
        <ShortlistSection
          key={shortlistKey}
          shortlist={shortlist}
          rankedCount={ranked.length}
          selectedCandidate={selectedCandidate}
          onSelectCandidate={onSelectCandidate}
        />
      ) : null}

      {showRanked ? (
        <RankedSection
          key={rankedKey}
          ranked={ranked}
          selectedCandidate={selectedCandidate}
          onSelectCandidate={onSelectCandidate}
        />
      ) : null}
    </div>
  );
}

function ShortlistSection({
  shortlist,
  rankedCount,
  selectedCandidate,
  onSelectCandidate,
}: {
  shortlist: Candidate[];
  rankedCount: number;
  selectedCandidate: string | null;
  onSelectCandidate: (name: string) => void;
}) {
  const [page, setPage] = useState(1);
  const totalPages = Math.max(1, Math.ceil(shortlist.length / SHORTLIST_PAGE_SIZE));
  const pageRows = useMemo(() => paginate(shortlist, page, SHORTLIST_PAGE_SIZE), [page, shortlist]);

  return (
    <div className="sectionCard">
      <div className="rowBetween">
        <div>
          <div className="cardTitle">Shortlist</div>
          <div className="hint">
            ATS-approved candidates above cutoff: <b>{shortlist.length}</b> / {rankedCount}
          </div>
        </div>
        <DownloadButton data={shortlist} />
      </div>

      <div className="tableWrap">
        <table className="table">
          <thead>
            <tr>
              <th>Candidate</th>
              <th>ATS</th>
              <th>Score</th>
              <th>Recommendation</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {pageRows.map((r) => (
              <tr key={r.candidate} className={candidateRowClass(r, selectedCandidate)}>
                <td>{r.candidate}</td>
                <td>
                  <div className="atsCell">
                    <AtsBadge status={r.atsStatus} />
                    <span className="hint">{r.atsScore}/100</span>
                  </div>
                </td>
                <td>{r.screeningSkipped ? <span className="hint">Rejected</span> : <ScorePill score={r.score} />}</td>
                <td>{r.recommendation || "-"}</td>
                <td>
                  <button className="linkBtn" onClick={() => onSelectCandidate(r.candidate)}>
                    View
                  </button>
                </td>
              </tr>
            ))}
            {shortlist.length === 0 && (
              <tr>
                <td colSpan={5} className="hint">
                  No ATS-approved candidates meet the cutoff. Lower the cutoff or review ATS-rejected resumes individually.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <Pagination
        page={page}
        totalPages={totalPages}
        onPageChange={setPage}
        label={`${shortlist.length} shortlisted candidates`}
      />
    </div>
  );
}

function RankedSection({
  ranked,
  selectedCandidate,
  onSelectCandidate,
}: {
  ranked: Candidate[];
  selectedCandidate: string | null;
  onSelectCandidate: (name: string) => void;
}) {
  const [page, setPage] = useState(1);
  const totalPages = Math.max(1, Math.ceil(ranked.length / RANKED_PAGE_SIZE));
  const pageRows = useMemo(() => paginate(ranked, page, RANKED_PAGE_SIZE), [page, ranked]);

  return (
    <div className="sectionCard">
      <div className="rowBetween">
        <div>
          <div className="cardTitle">All Candidates</div>
          <div className="hint">Full ranking after ATS gating, including rejected resumes for audit visibility.</div>
        </div>
        <div className="panelMeta">{ranked.length} total candidates</div>
      </div>

      <div className="tableWrap">
        <table className="table">
          <thead>
            <tr>
              <th>Candidate</th>
              <th>ATS</th>
              <th>Score</th>
              <th>Decision</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {pageRows.map((r) => (
              <tr key={r.candidate} className={candidateRowClass(r, selectedCandidate)}>
                <td>{r.candidate}</td>
                <td>
                  <div className="atsCell">
                    <AtsBadge status={r.atsStatus} />
                    <span className="hint">{r.atsScore}/100</span>
                  </div>
                </td>
                <td>{r.screeningSkipped ? <span className="hint">Rejected by ATS</span> : <ScorePill score={r.score} />}</td>
                <td>{r.atsDecision === "Reject" ? "Rejected by ATS validation" : r.recommendation || "-"}</td>
                <td>
                  <button className="linkBtn" onClick={() => onSelectCandidate(r.candidate)}>
                    View
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
        label={`${ranked.length} ranked candidates`}
      />
    </div>
  );
}

function DownloadButton({ data }: { data: Candidate[] }) {
  function download() {
    const rows = data.map((r) => ({
      candidate: r.candidate,
      atsScore: r.atsScore,
      atsStatus: r.atsStatus,
      atsDecision: r.atsDecision,
      score: r.score,
      recommendation: r.recommendation || "",
      recommendationReason: r.recommendationReason || "",
      matchedSkills: (r.matchedSkills || []).join(", "),
      missingRequired: (r.missingRequired || []).join(", "),
      atsReasons: (r.atsReasons || []).join(" | "),
    }));

    const csv = toCSV(rows);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "shortlist.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <button className="secondaryBtn" onClick={download} disabled={!data.length}>
      Download CSV
    </button>
  );
}

function toCSV(rows: CsvRow[]) {
  if (!rows.length) return "";

  const headers = Object.keys(rows[0]);
  const escape = (v: string | number | undefined) => `"${String(v ?? "").replaceAll('"', '""')}"`;

  const lines = [headers.join(","), ...rows.map((r) => headers.map((h) => escape(r[h])).join(","))];
  return lines.join("\n");
}
