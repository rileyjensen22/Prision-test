# Assumptions (UNVERIFIED; confirm with counsel before any deployment)

Stub created in Phase 0; filled in Phase 7. See `config/compliance.yaml` and CLAUDE.md sections 11-12.

- Resident identity = staff-made device-to-cell-to-resident assignment (revisit).
- Regime is ~23h in cell; may be classed as restrictive housing (Mandela Rules). Safeguards in section 11.
- Job/work programs: compliance review required (wages, deductions, voluntariness).

## Added in Phase 4 (UNVERIFIED; confirm with counsel)

- **Call monitoring disclosure.** Non-attorney calls are flagged monitored and the resident is told so. The required wording, recording consent rules, and retention (`recording_retention_days`) vary by state and contract.
- **Who is an "attorney" contact.** v1 trusts the contact type set by staff when the contact is approved. A real deployment needs a verification process (bar number check, privilege log) and rules for investigators, paralegals, and consular officials.
- **Rate caps and call fees.** `call_rate_cap_per_minute` is null; calls are free in the mock. Federal and state rate-cap and fee rules must be checked before any real telephony.
- **Trust account rules.** Deposit limits, holds, fees, refunds on release, escheat, and who may spend from the account differ by state. The mock ledger is only a model of balances.
- **Commissary restrictions by offense** use placeholder categories. Real categories and item rules come from the customer.
- **Education credit.** Points for courses are a behavior incentive. Whether course completion can also count toward earned-time or certificates is a separate legal question.

## Added in Phase 6 (UNVERIFIED; confirm with counsel)

- **Resident notice for screen mirroring.** The device does not currently tell the resident when staff are mirroring it. Whether notice is required (or prohibited for security reasons), and what the disclosure should say, varies by jurisdiction and policy. Every session is logged with a reason so it can be reviewed either way.
- **What counts as a private screen.** v1 redacts attorney calls and the legal, grievance, medical and mental-health services. Counsel should confirm the list (for example religious services, and PREA reporting channels) and whether any of it should be viewable under supervision.
- **Who may mirror, and why.** v1 allows supervisors and admins with a written reason. A real policy may need a stated purpose list, second approval, or limits per resident.
- **Retention of mirror logs.** Session records follow the audit log (kept indefinitely in v1). No screen images or content are captured or stored.

## Added in Phase 7 (UNVERIFIED; confirm with counsel before any deployment)

- **Restrictive housing and out-of-cell time.** The standard regime is about 23 hours in cell, which the UN Mandela Rules and many jurisdictions treat as restrictive housing. The system records out-of-cell minutes per day (append-only), flags days under `min_out_of_cell_minutes_per_day` (default 60, a placeholder, not a legal standard), and flags days with no record. Real minimums, review intervals, and reporting duties for the target state must be set by counsel. The log relies on facility staff entering or ingesting the numbers; the software cannot measure it.
- **Welfare monitoring.** Flags are prompts for a person to check in, not a medical or suicide-risk screen, and must not replace the facility's own mental-health procedures. Thresholds are placeholders. Whether device-usage patterns may be analysed this way, and how long flags and acknowledgements are kept, needs review (privacy, ADA, PREA).
- **Public log.** Publication duties and limits vary (public-records laws, privacy of people in custody, victim and staff safety). The v1 export publishes only pseudonymous, week-level, role-level information and is **off by default**; a real deployment needs counsel to decide whether to publish at all, how often, what delay to apply, and what minimum group size is safe. Pseudonym salts must be generated and stored by the operator, outside the repository.
- **Activity timeline and monitored metadata.** Who may see call and message metadata, for what purposes, and how long it is kept is a legal question. v1 limits it to supervisors, admins and auditors with a written reason, and logs each view. Message *content* retention (`recording_retention_days`) is unset.
- **Texting and video.** Monitoring notices, retention, per-message or per-minute fees, accessibility requirements (captions, TTY), and rules for video visits all need review. Attorney messages are never stored, but the real provider's behaviour must be verified before relying on the guard.
- **Work programs (required compliance review).** Wages, deductions, the facility's share, voluntariness safeguards, workers' compensation, and any prison-labour statutes must be reviewed **before** any real use of jobs. v1 stores no hours, tasks or pay, only voluntary enrolment, and limits task types to ones that never handle anyone's personal data (public-domain transcription, captioning, labeling non-personal data). The pay split in config is a placeholder.
- **Reading and education content.** Bundled texts were chosen as public domain or original; a real library needs content review, approval workflow and licensing. The allow-list (`approved_content_sources`) is the control for anything external.
- **Facility camera events.** The software only receives events from the facility's own systems and never runs cameras. How a camera "obstruction" is detected, how often it is wrong, and whether it may count as evidence on its own is for the facility and counsel; in v1 it can only create a pending sanction that a supervisor must confirm.
- **Legal and religious reading material (unverified, counsel to review).** v1 ships a few public-domain placeholders (selected US Bill of Rights amendments; Psalm 23, KJV; the opening of the Dhammapada) and keeps them available at every tier and under every sanction. A real law library (statutes, case law, court rules, the facility's own policies) and an appropriate range of faith texts in the languages residents use must come from the customer, with counsel confirming what a facility must provide (access-to-courts and religious-exercise obligations). Reading history for these texts is not shown to staff by name, which counsel should also confirm against any monitoring or records duty.
