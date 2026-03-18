import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import UploadPanel from "../components/UploadPanel";
import ResultsPanel from "../components/ResultsPanel";
import CandidateDrawer from "../components/CandidateDrawer";
import AtsBoard from "../components/AtsBoard";
import { api } from "../api";
import type { ScreenResponse } from "../types/screening";

type ModelsResponse = {
  ok?: boolean;
  default_model?: string;
  models?: ModelOption[];
};

type ErrorResponse = {
  ok?: boolean;
  error?: string;
};

type ModelOption = {
  id: string;
  label: string;
  is_default?: boolean;
};

type Props = {
  jd: File | null;
  setJd: (f: File | null) => void;
  resumes: File[];
  setResumes: React.Dispatch<React.SetStateAction<File[]>>;
  matchStyle: number;
  setMatchStyle: (v: number) => void;
  cutoff: number;
  setCutoff: (v: number) => void;
  modelChoice: string;
  setModelChoice: (v: string) => void;
  data: ScreenResponse | null;
  setData: (d: ScreenResponse | null) => void;
};

export default function ScreeningPage({
  jd,
  setJd,
  resumes,
  setResumes,
  matchStyle,
  setMatchStyle,
  cutoff,
  setCutoff,
  modelChoice,
  setModelChoice,
  data,
  setData,
}: Props) {
  const navigate = useNavigate();
  const location = useLocation();
  const view = location.pathname.endsWith("/results") ? "results" : "setup";

  const [loading, setLoading] = useState(false);
  const [selectedCandidate, setSelectedCandidate] = useState<string | null>(null);
  const [modelOptions, setModelOptions] = useState<ModelOption[]>([
    { id: "baseline", label: "SBERT baseline", is_default: true },
  ]);
  const [status, setStatus] = useState<{ kind: "info" | "success" | "error"; text: string } | null>(null);
  const [resultsView, setResultsView] = useState<"overview" | "ranked" | "ats">("overview");
  const [progressPercent, setProgressPercent] = useState(0);
  const [progressLabel, setProgressLabel] = useState("Preparing batch");

  const selectedObj = useMemo(() => {
    if (!selectedCandidate) return null;
    const ranked = data?.ranked ?? [];
    return ranked.find((x) => x.candidate === selectedCandidate) || null;
  }, [data?.ranked, selectedCandidate]);

  const hasLocalFiles = !!jd && resumes.length > 0;
  useEffect(() => {
    if (!loading) {
      return;
    }

    const timer = window.setInterval(() => {
      setProgressPercent((current) => {
        if (current >= 90) {
          return current;
        }
        const next = current < 20 ? current + 6 : current < 45 ? current + 5 : current < 70 ? current + 4 : current + 3;
        return Math.min(90, next);
      });
    }, 800);

    return () => window.clearInterval(timer);
  }, [loading]);

  useEffect(() => {
    if (!loading) {
      return;
    }

    if (progressPercent < 20) {
      setProgressLabel("Uploading files");
    } else if (progressPercent < 45) {
      setProgressLabel("Running ATS checks");
    } else if (progressPercent < 72) {
      setProgressLabel("Scoring candidates");
    } else {
      setProgressLabel("Finalizing shortlist");
    }
  }, [loading, progressPercent]);

  async function runScreening() {
    setLoading(true);
    setSelectedCandidate(null);
    setProgressPercent(8);
    setProgressLabel("Uploading files");

    try {
      if (!hasLocalFiles || !jd) {
        setStatus({
          kind: "error",
          text: "Upload a job description and at least one resume before screening.",
        });
        setProgressPercent(0);
        setLoading(false);
        return;
      }

      setStatus({ kind: "info", text: "Running screening..." });

      const form = new FormData();
      form.append("jd", jd);
      resumes.forEach((resume) => form.append("resumes", resume));
      form.append("match_style", String(matchStyle));
      form.append("cutoff", String(cutoff));
      form.append("model_choice", modelChoice);
      form.append("auto_improve", "false");

      const res = await api.post<ScreenResponse & ErrorResponse>("/screen", form);

      if (res.data?.ok === false) {
        setStatus({ kind: "error", text: res.data.error || "Screening failed." });
        setProgressPercent(0);
      } else {
        setProgressLabel("Done");
        setProgressPercent(100);
        setData(res.data);
        setResultsView("overview");
        setStatus(null);
        navigate("/app/screening/results");
      }
    } catch (e) {
      console.error(e);
      setStatus({ kind: "error", text: "Screening failed. Check backend console." });
      setProgressPercent(0);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    async function loadModels() {
      try {
        const res = await api.get<ModelsResponse>("/models");
        if (!res.data?.ok || !Array.isArray(res.data?.models)) return;

        const nextOptions: ModelOption[] = res.data.models.map((item) => ({
          id: String(item.id),
          label: String(item.label || item.id),
          is_default: Boolean(item.is_default),
        }));

        setModelOptions(nextOptions.length ? nextOptions : [{ id: "baseline", label: "SBERT baseline", is_default: true }]);

        const defaultModel = String(res.data.default_model || "baseline");
        const currentIsInitialFallback = modelChoice === "baseline" && !nextOptions.some((item) => item.id === "baseline" && item.is_default);
        const hasCurrent = nextOptions.some((item) => item.id === modelChoice);
        if (!hasCurrent || currentIsInitialFallback) {
          setModelChoice(defaultModel);
        }
      } catch (e) {
        console.error(e);
      }
    }

    loadModels().catch(() => {});
  }, [modelChoice, setModelChoice]);

  function clearScreening() {
    setJd(null);
    setResumes([]);
    setData(null);
    setSelectedCandidate(null);
    setStatus(null);
    setResultsView("overview");
    setProgressPercent(0);
    setProgressLabel("Preparing batch");
    navigate("/app/screening/setup");
  }

  if (view === "results") {
    return (
      <>
        {!data ? (
          <div className="card">
            <div className="emptyState">
              No screening results yet. Complete the setup step and run screening first.
            </div>
            <div style={{ marginTop: 12 }}>
              <button className="primaryBtn" onClick={() => navigate("/app/screening/setup")}>
                Go to Screening Setup
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="resultsWorkspace">
              <div className="card resultsSidebar">
                <div className="cardTitle" style={{ marginBottom: 12 }}>Review Workspace</div>
                <div className="resultsNav">
                  <button
                    className={resultsView === "overview" ? "secondaryBtn" : "linkBtn"}
                    onClick={() => setResultsView("overview")}
                  >
                    Shortlist Overview
                  </button>
                  <button
                    className={resultsView === "ranked" ? "secondaryBtn" : "linkBtn"}
                    onClick={() => setResultsView("ranked")}
                  >
                    Full Ranking
                  </button>
                  <button
                    className={resultsView === "ats" ? "secondaryBtn" : "linkBtn"}
                    onClick={() => setResultsView("ats")}
                  >
                    ATS Tracker
                  </button>
                </div>

                <div className="sectionCard compactSection" style={{ marginTop: 14 }}>
                  <div className="hint" style={{ marginBottom: 10 }}>
                    Use shortlist first for fast review. Switch to full ranking for audit, or ATS tracker for stage updates.
                  </div>
                  {data?.session_id ? (
                    <div className="compactList">
                      <div className="cardTitle" style={{ marginBottom: 8 }}>Current run</div>
                      <div className="hint" style={{ marginBottom: 8 }}>
                        ATS tracker is linked to this screening session.
                      </div>
                      <span className="chip">{data.session_id}</span>
                      <div style={{ marginTop: 12 }}>
                        <button className="secondaryBtn" onClick={clearScreening}>
                          Clear Screening
                        </button>
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>

              <div className="resultsMain">
                {resultsView === "ats" ? (
                  <AtsBoard
                    sessionId={data?.session_id || ""}
                    visible={Boolean(data?.session_id)}
                  />
                ) : (
                  <ResultsPanel
                    data={data}
                    loading={loading}
                    onSelectCandidate={setSelectedCandidate}
                    selectedCandidate={selectedCandidate}
                    mode={resultsView}
                  />
                )}
              </div>
            </div>

            <CandidateDrawer
              open={!!selectedObj}
              candidate={selectedObj}
              onClose={() => setSelectedCandidate(null)}
            />
          </>
        )}
      </>
    );
  }

  return (
    <>
      {status ? (
        <div className={`statusBanner ${status.kind}`} style={{ marginBottom: 16 }}>
          {status.text}
        </div>
      ) : null}

      <div className="screeningSetupLayout singleColumn compactSetupLayout">
        <UploadPanel
          jd={jd}
          resumes={resumes}
          setJd={setJd}
          setResumes={setResumes}
          matchStyle={matchStyle}
          setMatchStyle={setMatchStyle}
          cutoff={cutoff}
          setCutoff={setCutoff}
          modelChoice={modelChoice}
          setModelChoice={setModelChoice}
          modelOptions={modelOptions}
          onRun={runScreening}
          onClearScreening={clearScreening}
          loading={loading}
          progressPercent={progressPercent}
          progressLabel={progressLabel}
          hasResults={Boolean(data)}
          onOpenResults={() => {
            setResultsView("overview");
            navigate("/app/screening/results");
          }}
        />
      </div>
    </>
  );
}
