import type { Candidate } from "../types/screening";
import { useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { api } from "../api";

function AtsBadge({ status }: { status: Candidate["atsStatus"] }) {
  const cls =
    status === "PASS" ? "atsBadge pass" : status === "REVIEW" ? "atsBadge review" : "atsBadge fail";
  return <span className={cls}>ATS {status}</span>;
}

function RiskBadge({ status }: { status?: Candidate["fraudStatus"] }) {
  if (!status) return null;
  const cls =
    status === "High Risk" ? "pill low" : status === "Medium Risk" ? "pill mid" : "pill good";
  return <span className={cls}>{status}</span>;
}

function QualityBadge({ status }: { status?: Candidate["resumeQualityStatus"] }) {
  if (!status) return null;
  const cls = status === "Strong" ? "pill good" : status === "Moderate" ? "pill mid" : "pill low";
  return <span className={cls}>{status}</span>;
}

export default function CandidateDrawer({
  open,
  candidate,
  onClose,
}: {
  open: boolean;
  candidate: Candidate | null;
  onClose: () => void;
}) {
  const [mailingAction, setMailingAction] = useState<"" | "accept" | "reject" | "process">("");
  const [mailStatus, setMailStatus] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [pendingAction, setPendingAction] = useState<null | "accept" | "reject" | "process">(null);
  const [interviewOpen, setInterviewOpen] = useState(false);
  const [interviewQuestions, setInterviewQuestions] = useState<Candidate["interviewQuestions"]>({});
  const [questionGroupsOpen, setQuestionGroupsOpen] = useState({
    skill: true,
    project: false,
    weakness: false,
    experience: false,
  });
  const currentCandidate = candidate;

  const explanation = currentCandidate?.explanation || {};
  const projects = currentCandidate?.projects || [];
  const skills = currentCandidate?.skills || currentCandidate?.matchedSkills || [];
  const recommendation = explanation.recommendation || currentCandidate?.recommendation;
  const recommendationReason = explanation.recommendationReason || currentCandidate?.recommendationReason;
  const missingSkills = [...(currentCandidate?.missingRequired || []), ...(currentCandidate?.missingPreferred || [])];
  const uniqueMissing = Array.from(new Set(missingSkills));
  const atsReasons = currentCandidate?.atsReasons || [];
  const atsWarnings = currentCandidate?.atsWarnings || [];
  const breakdown = currentCandidate?.atsBreakdown;
  const contactEmail = currentCandidate?.contactEmail || "";
  const fraudReasons = currentCandidate?.fraudReasons || [];
  const qualityReasons = currentCandidate?.resumeQualityReasons || [];
  const improvementSuggestions = currentCandidate?.improvementSuggestions || [];
  const loadedQuestions = interviewQuestions || {};
  const skillQuestions = loadedQuestions.skillQuestions || [];
  const projectQuestions = loadedQuestions.projectQuestions || [];
  const weaknessQuestions = loadedQuestions.weaknessQuestions || [];
  const experienceQuestions = loadedQuestions.experienceQuestions || [];

  useEffect(() => {
    setInterviewQuestions(candidate?.interviewQuestions || {});
    setInterviewOpen(false);
  }, [candidate]);

  if (!open || !currentCandidate) {
    return null;
  }

  const drawerCandidate = currentCandidate;

  function toggleQuestionGroup(group: "skill" | "project" | "weakness" | "experience") {
    setQuestionGroupsOpen((current) => ({
      ...current,
      [group]: !current[group],
    }));
  }

  async function sendCandidateEmail(action: "accept" | "reject" | "process") {
    if (!contactEmail) {
      setMailStatus({ kind: "error", text: "No candidate email was detected in the resume." });
      return;
    }

    setMailingAction(action);
    setMailStatus(null);
    try {
      const res = await api.post("/candidate-email", {
        action,
        candidate: drawerCandidate.candidate,
        candidateName: drawerCandidate.candidateName || drawerCandidate.candidate,
        contactEmail,
        atsStatus: drawerCandidate.atsStatus,
        atsDecision: drawerCandidate.atsDecision,
        screeningSkipped: Boolean(drawerCandidate.screeningSkipped),
        score: drawerCandidate.score,
        atsScore: drawerCandidate.atsScore,
        recommendation,
        recommendationReason,
        matchedSkills: drawerCandidate.matchedSkills || [],
        missingRequired: drawerCandidate.missingRequired || [],
        missingPreferred: drawerCandidate.missingPreferred || [],
        atsReasons,
        explanationSummary: explanation.summary || "",
        whyBad: explanation.whyBad || [],
      });

      if (res.data?.ok) {
        setMailStatus({
          kind: "success",
          text:
            action === "accept"
              ? `Interview selection email sent to ${contactEmail}.`
              : action === "process"
              ? `Processing update email sent to ${contactEmail}.`
              : `Rejection email sent to ${contactEmail}.`,
        });
      } else {
        setMailStatus({ kind: "error", text: "Email sending failed." });
      }
    } catch (error: unknown) {
      const detail = isAxiosError(error) ? error.response?.data?.detail : null;
      setMailStatus({ kind: "error", text: detail ? String(detail) : "Email sending failed." });
    } finally {
      setMailingAction("");
    }
  }

  const pendingConfig =
    pendingAction === "accept"
      ? {
          title: "Confirm Interview Selection",
          text: `Send an interview selection email to ${contactEmail || "this candidate"}?`,
          actionLabel: mailingAction === "accept" ? "Sending..." : "Send Selection Email",
        }
      : pendingAction === "process"
      ? {
          title: "Confirm Processing Update",
          text: `Send an application-in-process update to ${contactEmail || "this candidate"}?`,
          actionLabel: mailingAction === "process" ? "Sending..." : "Send Processing Update",
        }
      : pendingAction === "reject"
      ? {
          title: "Confirm Rejection Email",
          text: `Send a rejection email with role-fit gaps to ${contactEmail || "this candidate"}?`,
          actionLabel: mailingAction === "reject" ? "Sending..." : "Send Rejection Email",
        }
      : null;

  return (
    <div className="drawerBackdrop" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="rowBetween">
          <div>
            <div className="drawerTitle">{currentCandidate.candidate}</div>
            <div className="hint drawerMeta">
              <AtsBadge status={currentCandidate.atsStatus} />
              <span>ATS score: <b>{currentCandidate.atsScore}/100</b></span>
              <span>{currentCandidate.screeningSkipped ? "Rejected before screening" : `Screening score: ${currentCandidate.score}/100`}</span>
              {explanation.fitLabel ? <span><b>{explanation.fitLabel}</b></span> : null}
            </div>
          </div>

          <button className="secondaryBtn" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="drawerSection">
          <div className="sectionTitle">Candidate Actions</div>
          <div className="rowBetween">
            <div>
              <div style={{ fontSize: 13, fontWeight: 700 }}>
                {contactEmail ? contactEmail : "No email detected in resume"}
              </div>
              <div className="hint" style={{ marginTop: 4 }}>
                Use these actions to notify the candidate directly from the screening report.
              </div>
            </div>
            <div className="drawerActions">
              <button
                className="primaryBtn"
                disabled={!contactEmail || mailingAction !== ""}
                onClick={() => setPendingAction("accept")}
              >
                {mailingAction === "accept" ? "Sending..." : "Select for Interview"}
              </button>
              <button
                className="secondaryBtn"
                disabled={!contactEmail || mailingAction !== ""}
                onClick={() => setPendingAction("process")}
              >
                {mailingAction === "process" ? "Sending..." : "In Process"}
              </button>
              <button
                className="secondaryBtn"
                disabled={!contactEmail || mailingAction !== ""}
                onClick={() => setPendingAction("reject")}
              >
                {mailingAction === "reject" ? "Sending..." : "Reject Candidate"}
              </button>
            </div>
          </div>
          {mailStatus ? (
            <div className={`statusBanner ${mailStatus.kind === "success" ? "success" : "error"}`} style={{ marginTop: 10 }}>
              {mailStatus.text}
            </div>
          ) : null}
        </div>

        <div className="drawerSection">
          <div className="sectionTitle">ATS Validation</div>
          <div style={{ fontSize: 13, fontWeight: 700 }}>
            {currentCandidate.atsDecision === "Reject" ? "Rejected by ATS validation" : `ATS decision: ${currentCandidate.atsDecision}`}
          </div>
          {atsReasons.length ? (
            <ul style={{ marginTop: 8 }}>
              {atsReasons.map((reason) => (
                <li key={reason} style={{ fontSize: 13, marginBottom: 6 }}>
                  {reason}
                </li>
              ))}
            </ul>
          ) : (
            <div className="hint" style={{ marginTop: 8 }}>No ATS rejection reasons recorded.</div>
          )}
          {atsWarnings.length ? (
            <div className="hint" style={{ marginTop: 8 }}>
              Warnings: {atsWarnings.join(" | ")}
            </div>
          ) : null}
        </div>

        {breakdown && (
          <div className="drawerSection">
            <div className="sectionTitle">ATS Breakdown</div>
            <div className="atsBreakdownList">
              <div className="atsBreakdownItem">
                <span>Text extraction</span>
                <b>{breakdown.textExtractionQuality}</b>
              </div>
              <div className="atsBreakdownItem">
                <span>Sections</span>
                <b>{breakdown.sectionPresence}</b>
              </div>
              <div className="atsBreakdownItem">
                <span>Skill match</span>
                <b>{breakdown.keywordSkillMatch}</b>
              </div>
              <div className="atsBreakdownItem">
                <span>Structure</span>
                <b>{breakdown.structureQuality}</b>
              </div>
              <div className="atsBreakdownItem">
                <span>Length</span>
                <b>{breakdown.resumeLengthQuality}</b>
              </div>
            </div>
          </div>
        )}

        {explanation.summary && (
          <div className="drawerSection">
            <div className="sectionTitle">Summary</div>
            <div style={{ fontSize: 13 }}>{explanation.summary}</div>
          </div>
        )}

        {recommendation && (
          <div className="drawerSection">
            <div className="sectionTitle">Hiring Recommendation</div>
            <div style={{ fontSize: 13, fontWeight: 700 }}>{recommendation}</div>
            {recommendationReason ? (
              <div className="hint" style={{ marginTop: 6 }}>
                {recommendationReason}
              </div>
            ) : null}
          </div>
        )}

        <div className="drawerSection">
          <div className="sectionTitle">Fraud Risk</div>
          <div className="rowBetween">
            <div style={{ fontSize: 13, fontWeight: 700 }}>
              Fraud risk score: {currentCandidate.fraudRiskScore ?? 0}/100
            </div>
            <div className="chips">
              <RiskBadge status={currentCandidate.fraudStatus} />
            </div>
          </div>
          {currentCandidate.fraudRecommendation ? (
            <div className="hint" style={{ marginTop: 8 }}>
              Recommended recruiter action: <b>{currentCandidate.fraudRecommendation}</b>
            </div>
          ) : null}
          {fraudReasons.length ? (
            <ul style={{ marginTop: 8 }}>
              {fraudReasons.map((reason) => (
                <li key={reason} style={{ fontSize: 13, marginBottom: 6 }}>
                  {reason}
                </li>
              ))}
            </ul>
          ) : (
            <div className="hint" style={{ marginTop: 8 }}>No fraud-risk notes were generated.</div>
          )}
        </div>

        <div className="drawerSection">
          <div className="sectionTitle">Resume Quality</div>
          <div className="rowBetween">
            <div style={{ fontSize: 13, fontWeight: 700 }}>
              Resume quality score: {currentCandidate.resumeQualityScore ?? 0}/100
            </div>
            <div className="chips">
              <QualityBadge status={currentCandidate.resumeQualityStatus} />
            </div>
          </div>

          {qualityReasons.length ? (
            <>
              <div style={{ marginTop: 10, fontSize: 13, fontWeight: 700 }}>Quality review</div>
              <ul style={{ marginTop: 8 }}>
                {qualityReasons.map((reason) => (
                  <li key={reason} style={{ fontSize: 13, marginBottom: 6 }}>
                    {reason}
                  </li>
                ))}
              </ul>
            </>
          ) : null}

          <div style={{ marginTop: 10, fontSize: 13, fontWeight: 700 }}>Improvement suggestions</div>
          {improvementSuggestions.length ? (
            <ul style={{ marginTop: 8 }}>
              {improvementSuggestions.map((item) => (
                <li key={item} style={{ fontSize: 13, marginBottom: 6 }}>
                  {item}
                </li>
              ))}
            </ul>
          ) : (
            <div className="hint" style={{ marginTop: 8 }}>No resume improvement suggestions were generated.</div>
          )}
        </div>

        <div className="drawerSection">
          <button className="drawerDropdown" onClick={() => setInterviewOpen((current) => !current)}>
            <span className="sectionTitle" style={{ margin: 0 }}>Interview Questions</span>
            <span className="drawerDropdownIcon">{interviewOpen ? "−" : "+"}</span>
          </button>

          {interviewOpen ? (
            <div className="drawerDropdownBody">
              <QuestionGroup
                title="Skill Questions"
                open={questionGroupsOpen.skill}
                onToggle={() => toggleQuestionGroup("skill")}
                items={skillQuestions}
                emptyText="No skill-focused questions were generated."
              />
              <QuestionGroup
                title="Project Questions"
                open={questionGroupsOpen.project}
                onToggle={() => toggleQuestionGroup("project")}
                items={projectQuestions}
                emptyText="No project-specific questions were generated."
              />
              <QuestionGroup
                title="Weakness Questions"
                open={questionGroupsOpen.weakness}
                onToggle={() => toggleQuestionGroup("weakness")}
                items={weaknessQuestions}
                emptyText="No weakness-focused questions were generated."
              />
              <QuestionGroup
                title="Experience Questions"
                open={questionGroupsOpen.experience}
                onToggle={() => toggleQuestionGroup("experience")}
                items={experienceQuestions}
                emptyText="No experience-focused questions were generated."
              />
            </div>
          ) : null}
        </div>

        <div className="drawerSection">
          <div className="sectionTitle">Projects Done</div>
          {projects.length ? (
            <ul style={{ marginTop: 8 }}>
              {projects.map((p, i) => (
                <li key={i} style={{ fontSize: 13, marginBottom: 6 }}>
                  {p}
                </li>
              ))}
            </ul>
          ) : (
            <div className="hint">No clear project section detected.</div>
          )}
        </div>

        <div className="drawerSection">
          <div className="sectionTitle">Experience Years</div>
          <div style={{ fontSize: 13 }}>{currentCandidate.experienceYears || "Not clearly mentioned"}</div>
        </div>

        <div className="drawerSection">
          <div className="sectionTitle">Skills Candidate Has</div>
          <div className="chips">
            {skills.length ? (
              skills.map((s) => (
                <span key={s} className="chip">
                  {s}
                </span>
              ))
            ) : (
              <span className="hint">No clear matching skills detected.</span>
            )}
          </div>
        </div>

        <div className="drawerSection">
          <div className="sectionTitle">Missing Skills</div>
          <div className="chips">
            {uniqueMissing.length ? (
              uniqueMissing.map((s) => (
                <span key={s} className="chip warn">
                  {s}
                </span>
              ))
            ) : (
              <span className="hint">No major missing skills detected.</span>
            )}
          </div>
        </div>

        <div className="drawerSection">
          <div className="sectionTitle">Why this candidate is a good match</div>
          {explanation.whyGood?.length ? (
            <ul style={{ marginTop: 8 }}>
              {explanation.whyGood.map((t, i) => (
                <li key={i} style={{ fontSize: 13, marginBottom: 6 }}>
                  {t}
                </li>
              ))}
            </ul>
          ) : (
            <div className="hint">No strong positive reasons extracted.</div>
          )}
        </div>

        <div className="drawerSection">
          <div className="sectionTitle">Why this candidate may not be a good match</div>
          {explanation.whyBad?.length ? (
            <ul style={{ marginTop: 8 }}>
              {explanation.whyBad.map((t, i) => (
                <li key={i} style={{ fontSize: 13, marginBottom: 6 }}>
                  {t}
                </li>
              ))}
            </ul>
          ) : (
            <div className="hint">No major concerns detected.</div>
          )}
        </div>
      </div>

      {pendingConfig ? (
        <div className="confirmOverlay" onClick={() => setPendingAction(null)}>
          <div className="confirmCard" onClick={(e) => e.stopPropagation()}>
            <div className="cardTitle" style={{ marginBottom: 6 }}>{pendingConfig.title}</div>
            <div className="hint">{pendingConfig.text}</div>
            <div className="confirmActions">
              <button className="secondaryBtn" onClick={() => setPendingAction(null)} disabled={mailingAction !== ""}>
                Cancel
              </button>
              <button
                className="primaryBtn"
                onClick={() => {
                  if (pendingAction) {
                    sendCandidateEmail(pendingAction);
                  }
                  setPendingAction(null);
                }}
                disabled={mailingAction !== ""}
              >
                {pendingConfig.actionLabel}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function QuestionGroup({
  title,
  open,
  onToggle,
  items,
  emptyText,
}: {
  title: string;
  open: boolean;
  onToggle: () => void;
  items: string[];
  emptyText: string;
}) {
  return (
    <div className="nestedDropdown">
      <button className="nestedDropdownBtn" onClick={onToggle}>
        <span>{title}</span>
        <span className="drawerDropdownIcon">{open ? "−" : "+"}</span>
      </button>
      {open ? (
        items.length ? (
          <ul style={{ marginTop: 8 }}>
            {items.map((item) => (
              <li key={item} style={{ fontSize: 13, marginBottom: 6 }}>
                {item}
              </li>
            ))}
          </ul>
        ) : (
          <div className="hint" style={{ marginTop: 8 }}>{emptyText}</div>
        )
      ) : null}
    </div>
  );
}
