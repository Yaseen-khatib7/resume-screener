import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import Pagination from "../components/Pagination";
import type { ScreenResponse } from "../types/screening";

type Props = {
  jd: File | null;
  resumes: File[];
  matchStyle: number;
  modelChoice: string;
  data: ScreenResponse | null;
};

type Row = {
  name: string;
  label: number;
};

type EvaluationResult = {
  ok?: boolean;
  error?: string;
  k: number;
  ndcg_baseline: number;
  ndcg_finetuned: number;
  evaluation_model?: string;
};

const LABELS_PAGE_SIZE = 10;

function labelText(v: number) {
  if (v === 3) return "3 (Excellent match)";
  if (v === 2) return "2 (Strong match)";
  if (v === 1) return "1 (Partial match)";
  return "0 (Irrelevant)";
}

export default function TrainingPage({ jd, resumes }: Props) {
  const [loading, setLoading] = useState(false);
  const [k, setK] = useState<number>(10);
  const [rows, setRows] = useState<Row[]>([]);
  const [mode, setMode] = useState<"local" | "none">("none");
  const [autoLabelVersion, setAutoLabelVersion] = useState(0);
  const [result, setResult] = useState<EvaluationResult | null>(null);
  const [status, setStatus] = useState<string>("");
  const [epochs, setEpochs] = useState<number>(1);
  const [batchSize, setBatchSize] = useState<number>(8);
  const [posThreshold, setPosThreshold] = useState<number>(2);
  const [setAsDefault, setSetAsDefault] = useState(false);
  const [trainedModelId, setTrainedModelId] = useState<string>("");
  const [trainExamples, setTrainExamples] = useState<number | null>(null);
  const [labelsPage, setLabelsPage] = useState(1);

  const hasLocal = !!jd && resumes.length > 0;

  useEffect(() => {
    setResult(null);
    setStatus("");
    setTrainedModelId("");
    setTrainExamples(null);

    if (hasLocal) {
      setMode("local");
      setRows(resumes.map((r) => ({ name: r.name, label: 0 })));
      setLabelsPage(1);
      setAutoLabelVersion((prev) => prev + 1);
      return;
    }

    setMode("none");
    setRows([]);
  }, [hasLocal, resumes]);

  useEffect(() => {
    async function autoLabelDefault() {
      if (rows.length === 0 || mode !== "local") return;

      try {
        setLoading(true);
        setStatus("Auto-labeling resumes...");

        if (!jd || resumes.length === 0) return;

        const form = new FormData();
        form.append("jd", jd);
        resumes.forEach((r) => form.append("resumes", r));

        const res = await api.post("/auto-label", form);
        if (res.data?.ok) {
          const labels: number[] = res.data.labels || [];
          setRows((prev) => prev.map((p, idx) => ({ ...p, label: Number(labels[idx] ?? 0) })));
          setStatus("Auto-label completed.");
        } else {
          setStatus("Auto-label failed.");
        }
      } catch (e) {
        console.error(e);
        setStatus("Auto-label failed. Check backend console.");
      } finally {
        setLoading(false);
      }
    }

    autoLabelDefault().catch(() => {});
  }, [autoLabelVersion, jd, mode, resumes, rows.length]);

  const labelsArray = useMemo(() => rows.map((r) => r.label), [rows]);
  const positiveCount = useMemo(() => rows.filter((r) => r.label >= posThreshold).length, [posThreshold, rows]);
  const evaluationModelChoice = trainedModelId || "default";
  const labelTotalPages = Math.max(1, Math.ceil(rows.length / LABELS_PAGE_SIZE));
  const pagedRows = useMemo(() => {
    const start = (labelsPage - 1) * LABELS_PAGE_SIZE;
    return rows.slice(start, start + LABELS_PAGE_SIZE);
  }, [labelsPage, rows]);

  function updateLabel(name: string, newLabel: number) {
    setRows((prev) => prev.map((r) => (r.name === name ? { ...r, label: newLabel } : r)));
  }

  async function evaluate() {
    if (rows.length === 0) {
      alert("No resumes found. Upload JD and resumes in Screening first.");
      return;
    }

    setLoading(true);
    setResult(null);

    try {
      setStatus("Evaluating NDCG...");
      const form = new FormData();
      form.append("labels_json", JSON.stringify(labelsArray));
      form.append("k", String(k));
      form.append("model_choice", evaluationModelChoice);

      if (!jd || resumes.length === 0) {
        alert("Upload JD and resumes in Screening first.");
        setLoading(false);
        return;
      }

      if (mode !== "local") {
        alert("Upload JD and resumes in Screening first.");
      } else {
        form.append("jd", jd);
        resumes.forEach((r) => form.append("resumes", r));
        const res = await api.post("/evaluate", form);
        setResult(res.data);
      }

      setStatus("Evaluation completed.");
    } catch (e) {
      console.error(e);
      alert("Evaluation failed. Check backend console.");
      setStatus("Evaluation failed.");
    } finally {
      setLoading(false);
    }
  }

  async function trainModel() {
    if (rows.length === 0) {
      alert("No resumes found. Upload JD and resumes in Screening first.");
      return;
    }

    if (positiveCount < 3) {
      alert("Training needs at least 3 resumes at or above the positive threshold.");
      return;
    }

    setLoading(true);
    setResult(null);

    try {
      setStatus("Training fine-tuned model...");
      const form = new FormData();
      form.append("labels_json", JSON.stringify(labelsArray));
      form.append("epochs", String(epochs));
      form.append("batch_size", String(batchSize));
      form.append("pos_threshold", String(posThreshold));
      form.append("set_as_default", String(setAsDefault));

      let res;
      if (!jd || resumes.length === 0) {
        alert("Upload JD and resumes in Screening first.");
        setLoading(false);
        return;
      }

      if (mode === "local") {
        form.append("jd", jd);
        resumes.forEach((r) => form.append("resumes", r));
        res = await api.post("/train", form);
      } else {
        alert("Upload JD and resumes in Screening first.");
        setLoading(false);
        return;
      }

      if (res.data?.ok === false) {
        alert(res.data?.error || "Training failed.");
        setStatus("Training failed.");
        return;
      }

      setTrainedModelId(String(res.data?.model_id || ""));
      setTrainExamples(Number(res.data?.train_examples || 0));
      setStatus(`Training completed. New model: ${res.data?.model_id}`);
    } catch (e) {
      console.error(e);
      alert("Training failed. Check backend console.");
      setStatus("Training failed.");
    } finally {
      setLoading(false);
    }
  }

  function reAutoLabel() {
    setResult(null);
    setTrainedModelId("");
    setTrainExamples(null);
    setRows((prev) => prev.map((r) => ({ ...r, label: 0 })));
    setAutoLabelVersion((prev) => prev + 1);
  }

  return (
    <div className="card">
      <div className="cardTitle">Training + NDCG</div>
      <div className="hint">
        Auto-label resumes, correct labels manually, train a fine-tuned model, then compare baseline vs trained NDCG.
      </div>

      <div className="divider" />

      <div className="field">
        <label>NDCG@K</label>
        <input type="text" value={String(k)} onChange={(e) => setK(Number(e.target.value || "10"))} />
        <div className="hint">Common values: 5 or 10</div>
      </div>

      <div className="field">
        <label>Positive threshold</label>
        <select value={posThreshold} onChange={(e) => setPosThreshold(Number(e.target.value))}>
          <option value={3}>Only label 3 counts as positive</option>
          <option value={2}>Labels 2 and 3 count as positive</option>
          <option value={1}>Labels 1, 2 and 3 count as positive</option>
        </select>
        <div className="hint">Current positives: {positiveCount} / {rows.length}</div>
      </div>

      <div className="rowBetween" style={{ gap: 12 }}>
        <div className="field" style={{ flex: 1, marginBottom: 0 }}>
          <label>Epochs</label>
          <input type="text" value={String(epochs)} onChange={(e) => setEpochs(Number(e.target.value || "1"))} />
        </div>
        <div className="field" style={{ flex: 1, marginBottom: 0 }}>
          <label>Batch size</label>
          <input
            type="text"
            value={String(batchSize)}
            onChange={(e) => setBatchSize(Number(e.target.value || "8"))}
          />
        </div>
      </div>

      <label style={{ display: "flex", gap: 8, alignItems: "center", margin: "12px 0" }}>
        <input
          type="checkbox"
          checked={setAsDefault}
          onChange={(e) => setSetAsDefault(e.target.checked)}
          style={{ width: "auto" }}
        />
        Set newly trained model as default for screening
      </label>

      {status && (
        <div
          className="hint"
          style={{
            padding: "10px 12px",
            borderRadius: 12,
            border: "1px solid #e5e7eb",
            background: "#f8fafc",
            marginBottom: 12,
            color: "#0f172a",
          }}
        >
          {status}
        </div>
      )}

      {trainedModelId && (
        <div
          style={{
            padding: "10px 12px",
            borderRadius: 12,
            border: "1px solid #bbf7d0",
            background: "#ecfdf5",
            marginBottom: 12,
            fontSize: 13,
          }}
        >
          Evaluating with trained model <b>{trainedModelId}</b>
          {trainExamples !== null ? <> ({trainExamples} positive training pairs)</> : null}
        </div>
      )}

      <div className="rowBetween" style={{ marginBottom: 10 }}>
        <div className="cardTitle" style={{ margin: 0 }}>Labels per Resume</div>
        <button className="secondaryBtn" onClick={reAutoLabel} disabled={loading || rows.length === 0}>
          Re-run Auto Label
        </button>
      </div>

      <div className="tableWrap">
        <table className="table">
          <thead>
            <tr>
              <th>Resume</th>
              <th style={{ width: 220 }}>Label</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={2} className="hint">
                  Upload JD and resumes in Screening first.
                </td>
              </tr>
            ) : (
              pagedRows.map((r) => (
                <tr key={r.name}>
                  <td>{r.name}</td>
                  <td>
                    <select value={r.label} onChange={(e) => updateLabel(r.name, Number(e.target.value))}>
                      <option value={3}>{labelText(3)}</option>
                      <option value={2}>{labelText(2)}</option>
                      <option value={1}>{labelText(1)}</option>
                      <option value={0}>{labelText(0)}</option>
                    </select>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <Pagination
        page={labelsPage}
        totalPages={labelTotalPages}
        onPageChange={setLabelsPage}
        label={`${rows.length} labeled resumes`}
      />

      <div style={{ marginTop: 12, display: "flex", gap: 10, flexWrap: "wrap" }}>
        <button className="primaryBtn" onClick={trainModel} disabled={loading || rows.length === 0}>
          {loading ? "Working..." : "Train Fine-Tuned Model"}
        </button>
        <button className="secondaryBtn" onClick={evaluate} disabled={loading || rows.length === 0}>
          {loading ? "Working..." : "Evaluate NDCG"}
        </button>
      </div>

      {result && (
        <>
          <div className="divider" />
          <div className="cardTitle">Result</div>
          <div className="hint">
            NDCG@{result.k} - SBERT baseline: <b>{Number(result.ndcg_baseline).toFixed(3)}</b>
            <br />
            NDCG@{result.k} - evaluation model ({result.evaluation_model || "default"}):{" "}
            <b>{Number(result.ndcg_finetuned).toFixed(3)}</b>
          </div>
        </>
      )}
    </div>
  );
}
