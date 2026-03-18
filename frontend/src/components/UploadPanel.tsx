import React from "react";
type ModelOption = { id: string; label: string; is_default?: boolean };

type Props = {
  jd: File | null;
  resumes: File[];
  setJd: (f: File | null) => void;
  setResumes: React.Dispatch<React.SetStateAction<File[]>>;
  matchStyle: number;
  setMatchStyle: (v: number) => void;
  cutoff: number;
  setCutoff: (v: number) => void;
  modelChoice: string;
  setModelChoice: (v: string) => void;
  modelOptions: ModelOption[];
  onRun: () => void;
  onClearScreening: () => void;
  loading: boolean;
  progressPercent: number;
  progressLabel: string;
  hasResults: boolean;
  onOpenResults: () => void;
};

export default function UploadPanel({
  jd,
  resumes,
  setJd,
  setResumes,
  matchStyle,
  setMatchStyle,
  cutoff,
  setCutoff,
  modelChoice,
  setModelChoice,
  modelOptions,
  onRun,
  onClearScreening,
  loading,
  progressPercent,
  progressLabel,
  hasResults,
  onOpenResults,
}: Props) {
  const pref =
    matchStyle <= 0.2 ? "Flexible" : matchStyle >= 0.8 ? "Strict" : "Balanced";

  function handleResumeUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const newFiles = Array.from(e.target.files ?? []);

    setResumes((prev) => {
      const existingNames = new Set(prev.map((f) => f.name));
      const filtered = newFiles.filter((f) => !existingNames.has(f.name));
      return [...prev, ...filtered];
    });

    e.target.value = "";
  }

  function removeResume(name: string) {
    setResumes((prev) => prev.filter((f) => f.name !== name));
  }

  function clearResumes() {
    setResumes([]);
  }

  return (
    <div className="card">
      <div className="panelIntro">
        <div>
          <div className="cardTitle" style={{ marginBottom: 4 }}>Screening Setup</div>
          <div className="hint">Upload the JD, add resumes, and tune the shortlist rules before running ATS + screening.</div>
        </div>
      </div>

      <div className="setupGrid">
        <div className="sectionCard">
          <div className="cardTitle">Source Files</div>

          <div className="field">
            <label>Job Description</label>
            <input
              type="file"
              accept=".pdf,.docx,.txt,.md"
              onChange={(e) => setJd(e.target.files?.[0] ?? null)}
            />
            <div className="hint">{jd ? jd.name : "No file selected"}</div>
          </div>

          <div className="field" style={{ marginBottom: 0 }}>
            <label>Resumes</label>
            <input
              type="file"
              multiple
              accept=".pdf,.docx,.txt,.md"
              onChange={handleResumeUpload}
            />
            <div className="hint">
              {resumes.length
                ? `${resumes.length} resumes selected locally`
                : "No resumes selected"}
            </div>

            {resumes.length > 0 ? (
              <div className="fileListCompact">
                {resumes.slice(0, 5).map((file) => (
                  <div key={file.name} className="fileRow">
                    <span className="fileName">{file.name}</span>
                    <button className="linkBtn" onClick={() => removeResume(file.name)}>
                      Remove
                    </button>
                  </div>
                ))}
                {resumes.length > 5 ? (
                  <div className="hint">{resumes.length - 5} more files selected.</div>
                ) : null}
                <button className="secondaryBtn" style={{ marginTop: 8 }} onClick={clearResumes}>
                  Clear All
                </button>
              </div>
            ) : null}
          </div>
        </div>

        <div className="sectionCard">
          <div className="cardTitle">Screening Rules</div>

          <div className="field">
            <label>Model</label>
            <select value={modelChoice} onChange={(e) => setModelChoice(e.target.value)}>
              {modelOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                  {option.is_default ? " (default)" : ""}
                </option>
              ))}
            </select>
            <div className="hint">Ranking uses the selected trained model. Training is managed separately.</div>
          </div>

          <div className="field">
            <label>
              Matching preference: <b>{pref}</b>
            </label>

            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={matchStyle}
              onChange={(e) => setMatchStyle(Number(e.target.value))}
            />

            <div className="hint">
              Flexible emphasizes semantic similarity. Strict weights required skill coverage more heavily.
            </div>
          </div>

          <div className="field" style={{ marginBottom: 0 }}>
            <label>
              Shortlist cutoff score: <b>{cutoff}</b>
            </label>

            <input
              type="range"
              min="0"
              max="100"
              step="1"
              value={cutoff}
              onChange={(e) => setCutoff(Number(e.target.value))}
            />

            <div className="hint">Candidates above this threshold stay in the shortlist view.</div>
            <div className="hint">Recommended default is around 48 for a balanced shortlist.</div>
          </div>
        </div>
      </div>

      <div className="setupActionBar">
        <div style={{ flex: 1 }}>
          <div className="hint">
            ATS validation runs first. `PASS` and `REVIEW` resumes continue to semantic screening. `FAIL` resumes are rejected before ranking.
          </div>
          {loading ? (
            <div className="progressPanel">
              <div className="progressMeta">
                <span>{progressLabel}</span>
                <b>{progressPercent}%</b>
              </div>
              <div className="progressTrack" aria-hidden="true">
                <div className="progressFill" style={{ width: `${progressPercent}%` }} />
              </div>
            </div>
          ) : null}
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          {hasResults ? (
            <button className="secondaryBtn" onClick={onOpenResults} disabled={loading}>
              Open Results
            </button>
          ) : null}
          <button className="secondaryBtn" onClick={onClearScreening} disabled={loading}>
            Clear Screening
          </button>
          <button className="primaryBtn" onClick={onRun} disabled={loading}>
            {loading ? "Shortlisting..." : "Run ATS + Screening"}
          </button>
        </div>
      </div>
    </div>
  );
}
