/**
 * One severity per recorded state (DESIGN.md, severity mapping; console-unification spec). Pages
 * name the state; `Badge` turns it into one icon and one colour, so a state looks the same everywhere.
 */
export type Severity = "clock" | "overdue" | "missing" | "pending" | "done";

export const STATE_SEVERITY = {
  policyUnapproved: "missing", policyReviewOverdue: "overdue", policyCurrent: "done",
  reviewOpen: "pending", reviewLate: "overdue", reviewClosed: "done",
  trainingOpen: "pending", trainingEnded: "overdue", trainingClosed: "done",
  incidentOverdue: "overdue", incidentClosed: "done",
  clockRunning: "clock", clockOverdue: "overdue", clockMet: "done", clockMetLate: "overdue",
  tokenActive: "done", tokenExpired: "overdue", tokenRevoked: "pending",
  measureOverdue: "overdue",
  recordsAct: "overdue", recordsClear: "done", recordsEmpty: "pending",
  // Evidence file malware scan (evidence-malware-scanning spec).
  fileScanPending: "pending", fileClean: "done", fileBlocked: "overdue", fileNotScanned: "missing",
  fileDevUnscanned: "pending",
  connectionActive: "done", connectionWaiting: "pending", connectionIncomplete: "missing",
  connectionOverPrivileged: "overdue", connectionRevoked: "overdue",
  // Operator portal (operator-portal spec): an organization's state, its connections' health and
  // whether its billing details are complete.
  orgActive: "done", orgSuspended: "overdue", orgClosing: "missing",
  healthOk: "done", healthAttention: "missing", healthPending: "pending", healthNone: "pending",
  billingComplete: "done", billingMissing: "missing",
  staffEnabled: "done", staffDisabled: "pending",
  erasurePending: "pending", erasureApproved: "missing", erasureCancelled: "pending", erasureExecuted: "done",
} as const satisfies Record<string, Severity>;

export type State = keyof typeof STATE_SEVERITY;
