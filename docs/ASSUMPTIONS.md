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
