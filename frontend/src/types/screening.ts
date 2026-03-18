export type Evidence = { jd: string; resume: string; sim: number };

export type CandidateExplanation = {
  fitLabel?: string;
  summary?: string;
  whyGood?: string[];
  whyBad?: string[];
  recommendation?: string;
  recommendationReason?: string;
};

export type AtsBreakdown = {
  textExtractionQuality: number;
  sectionPresence: number;
  keywordSkillMatch: number;
  structureQuality: number;
  resumeLengthQuality: number;
};

export type InterviewQuestions = {
  skillQuestions?: string[];
  projectQuestions?: string[];
  weaknessQuestions?: string[];
  experienceQuestions?: string[];
};

export type Candidate = {
  candidate: string;
  candidateName?: string;
  score: number;
  screeningSkipped?: boolean;
  projects?: string[];
  experienceYears?: string;
  contactEmail?: string | null;
  skills?: string[];
  recommendation?: string;
  recommendationReason?: string;
  normalizedSkills?: string[];
  graphMatchedSkills?: string[];
  graphMissingSkills?: string[];
  graphSkillScore?: number;
  graphSkillNotes?: string[];
  fraudRiskScore?: number;
  fraudStatus?: "Low Risk" | "Medium Risk" | "High Risk";
  fraudReasons?: string[];
  fraudRecommendation?: "Proceed" | "Review Carefully" | "Flag for Verification";
  resumeQualityScore?: number;
  resumeQualityStatus?: "Strong" | "Moderate" | "Weak";
  resumeQualityReasons?: string[];
  improvementSuggestions?: string[];
  interviewQuestions?: InterviewQuestions;
  matchedSkills: string[];
  missingRequired: string[];
  missingPreferred: string[];
  evidence?: Evidence[];
  explanation?: CandidateExplanation;
  atsScore: number;
  atsStatus: "PASS" | "REVIEW" | "FAIL";
  atsDecision: "Screen" | "Review" | "Reject";
  atsReasons: string[];
  atsWarnings?: string[];
  atsBreakdown?: AtsBreakdown;
};

export type AtsTrackerCandidate = {
  candidate: string;
  score?: number;
  recommendation?: string;
  contactEmail?: string | null;
  atsScore?: number;
  atsStatus?: "PASS" | "REVIEW" | "FAIL";
  atsDecision?: "Screen" | "Review" | "Reject";
  atsReasons?: string[];
  stage: string;
  notes?: string;
  updated_at?: string;
};

export type ScreenResponse = {
  ok?: boolean;
  session_id?: string;
  modelUsed: string;
  autoImproveTriggered: boolean;
  warnings?: { file: string; severity: string; message: string }[];
  extractionStats?: {
    jdChars: number;
    resumeChars: Record<string, number>;
  };
  ats?: {
    candidates: AtsTrackerCandidate[];
  };
  atsSummary?: {
    pass: number;
    review: number;
    fail: number;
    screened: number;
    rejected: number;
  };
  ranked: Candidate[];
  shortlist: Candidate[];
};
