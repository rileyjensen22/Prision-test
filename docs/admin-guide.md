# Admin guide (for facility staff)

This guide is for the people who run the unit day to day: officers, supervisors, administrators and
auditors. It uses the words you see on screen and assumes no technical background. Everything in the
guide uses synthetic data in the demo.

## What this system does, in three sentences

Each resident has a wall-mounted screen in their cell. The screen unlocks more features (longer calls,
texting, video, more commissary) as the resident earns points, mostly by finishing courses, and it
shows plain reasons whenever something is locked. Every decision a staff member makes is recorded in a
log that nobody, including administrators, can change.

## Who can do what

| Role | Can | Cannot |
|---|---|---|
| **Officer** | See the roster and residents, record an infraction, act on welfare flags, tap residents out and in, answer staff requests, handle family and friend contact requests, change a resident's screen settings (with a reason) | Confirm a significant sanction, review appeals, see peer comparisons, edit configuration |
| **Supervisor** | Everything an officer can, plus confirm or reject pending sanctions, review appeals, approve attorney contacts, read monitored messages and review monitored calls (with a reason), start a live mirror (with a reason), run intake | Confirm a sanction they recorded themselves, review an appeal about their own sanction |
| **Admin** | Everything a supervisor can, plus edit configuration (every change is a new version), manage devices and staff accounts, enter outcomes | Change or delete the audit log. An admin can only add a correcting entry. |
| **Auditor** | Read everything, including the audit log, transparency data and the config history | Change anything |

## Your screen

The left side lists the pages. A number next to **Welfare**, **Devices**, **Confirmations** or
**Appeals** means something is waiting for you. The top right switches between English and Spanish and
signs you out. Tables can be sorted by clicking a column heading and filtered with the box above them.

## Daily routine

1. **Dashboard.** Check the tiles with a warning symbol: awaiting confirmation, open appeals, devices
   offline, welfare flags, staff outlier flags. A red banner about reconciliation means a money balance
   did not match its ledger; tell an administrator (see "When something looks wrong").
2. **Welfare.** Open every flag. Each one says "please check in", not that something is wrong. Check
   on the resident, then press **I checked in…** and record what you did. A flag nobody has handled
   for 12 hours goes to a supervisor.
3. **Out of cell.** Tap residents **out** when they leave their cell and **in** when they come back.
   Time is counted from these taps. Any resident under the daily minimum is listed so you can fix it today.
4. **Confirmations** (supervisors). Review each pending sanction: read the reason code, the evidence
   and who recorded it, then **Confirm** or **Reject** (rejecting needs a reason). Nothing locks for the
   resident until you confirm.
5. **Appeals** (supervisors). Open appeals are due within the review window (default 72 hours). Choose
   **Uphold** or **Overturn**, write the reason, and press **Submit decision**. An overturned appeal
   lifts the lock at once.
6. **Contacts.** Approve or refuse residents' requests to add people to their call and text lists. Refusing
   needs a note. Attorney contacts need a supervisor.

## Recording an infraction

Open the resident (Roster, then click the code), find **Record an infraction**, choose the code and
submit. What happens next depends on the code:

- **Minor, officer-immediate** (for example disruptive behavior, cell cleanliness): the lock starts
  now, for the listed time. Each officer can do only a few a week (default 3).
- **Everything larger, and disrespect to staff**: the infraction waits for a supervisor. You must
  attach evidence: a system event, or a second staff member's report.
- The resident sees the reason, the end time and an **Appeal** button. They cannot be locked out of
  the protected services below, whatever you record.

**Always available to every resident, under every lock:** law library and legal materials, grievances
and appeals, medical and mental-health requests, the Request staff button, emergency contact,
religious texts, basic education, attorney calls and the minimum out-of-cell time.

## Residents and devices

- **Intake** (supervisors and admins): enter the resident, their cell and device, language and
  screen settings, prior returns (with the source of that number), offense categories, approved
  contacts and anyone to keep separate. Everything is recorded in the audit log.
- **Screen settings** (language, text size, reading level, captions) are changed by staff only, from the
  resident's page, with a reason. Residents cannot change them.
- **Devices:** the page lists every screen, when it last checked in, and its health. **Pause** locks a
  screen's optional features (baseline stays open), **Restart** reloads it, **Enroll** registers a new
  one and gives a one-time setup code to type on the device. Setup codes work once and expire.
- A device that stops checking in for the offline period (default 30 minutes) shows as offline. Its
  locks keep applying from what it last knew, and optional features pause when that knowledge expires.
- **Replacing a broken screen:** enroll a new device, assign it to the cell and resident, then retire the old one.

## Releases and transfers

Set the release date on the resident's page (supervisors and admins). The resident sees a countdown
and a reentry checklist you update as items are done.

On the resident's page, **Move or release** (supervisors and admins) records a release, court,
hospital or other departure (**vacate**) or a move to another cell (**transfer**). The cell and the
device become free, nothing about the resident is deleted, and each step needs a reason and is
logged. A transfer is refused if a resident the person must be kept separate from is on the new
unit. Released residents leave the roster, welfare checks and the daily job.

## Keep separate

**Keep separate** (supervisors and admins) lists the pairs of residents who must never be matched in
a game, scheduled together or, where staff can help it, housed on the same unit. Add a pair with a
reason, or end one with a reason; the list shows both and is audited.

## Live mirror and "View as resident"

- **View as resident** is a safe preview. You can change tier, language, restrictions and sanctions
  and see what the resident would see. Nothing is saved and nothing reaches the resident. A red
  SIMULATION banner always shows.
- **Live mirror** shows where a real resident is on their screen. You must write a reason, every
  session is logged with who, which resident, why and for how long, and attorney, legal, grievance and
  health screens are never shown.

## Messages and calls

Monitoring pages list who, when and which keyword rule matched, never the text. To read a message you
must state a reason, and every read is logged. A keyword match only prompts you to look; it never
creates a sanction on its own. **Attorney calls and messages are private: they are never recorded,
shown or listed in any content.** Only that a call happened and how long it lasted is kept.

## Chess

Residents can play the computer (works offline, five levels) and, from tier 5, other residents.
**Chess** (supervisors, admins; auditors read) shows the match log: who played whom, the random name
each had for that match, and the result. Matches never pair two residents on the same line or on a
keep-separate record, so **every cell needs a line** (set it on the same page; a cell with no line
is never matched). To stop one resident from playing others, set their chess setting to Off with a
reason; to stop a whole unit, add it to `disabled_units` in the Chess configuration; a `games`
sanction does the same for a set time. Playing the computer is never affected, and a resident can
always leave a game without penalty.

## Reviewing monitored calls

**Monitoring > Monitored phone calls** (supervisors, admins; auditors can see the list) shows who,
when and how long. To open a recording you must state a reason; the access is logged. Attorney calls
are never listed and can never be opened.

## Accounts and sign-in security

Every staff member signs in with a password and, in production, a code from an authenticator app
(two-step). At first sign-in you set up the app and receive 10 recovery codes: each works once, keep
them somewhere safe. **Security** lets you change your password. Administrators use **Accounts** to
create staff (they get a temporary password and must change it at first sign-in), turn accounts off,
reset a password or reset someone's two-step setup. Each of these needs a reason and is logged.
There is no reset by email.

## Retention and encryption

Retention periods are in `config/compliance.yaml` and are unset until counsel decides, so nothing is
deleted. When set, the daily job removes only the kinds of data they name (messages, call metadata,
recordings) and never audit or money records. Message text, contact numbers, call recording
references and two-step secrets are encrypted in the database. To change the encryption key, see
`docs/security.md` and run `scripts/rotate-encryption-key.py`.

## Outcomes import

**Outcomes > Import outcomes from a file** (admins) takes a CSV with `resident_code`,
`window_months` (6, 12, 24) and `outcome`. It shows a preview first; nothing is saved until you apply,
and a file with any bad line is not applied. A changed answer is added as a correction and the old
entry stays.

## Money

Residents' trust accounts and work earnings are append-only ledgers. A family deposit adds an entry; a
commissary order subtracts one. Nothing is ever edited. If a mistake was made, an administrator adds a
correcting entry that points at the original. Every night the system checks that every balance equals
its ledger; a mismatch is shown on the Dashboard and Finance page and never fixed automatically.

## Configuration (administrators)

The **Config** page changes tiers, limits, point values, sanction codes, offense restrictions and the
repeat-return curve. Each change saves a new version with your reason; old versions stay. You cannot
configure away the protected services above. Make a change small, read the preview, and write a clear
reason, because the auditor reads it.

## When something looks wrong

| You see | Do this |
|---|---|
| A resident says they are locked and cannot see why | Open their page and check Sanctions. Every lock has a reason code and end time. If there is none, record it as a problem to a supervisor immediately: it should not be possible. |
| A resident's screen says "Paused until the connection returns" | The screen has been offline longer than its saved information is valid. Check the Devices page; restore the network or restart the device. Baseline services still work. |
| A device is offline | Check power and network, press **Restart**, and if it stays offline replace it (enroll a new one). |
| Red reconciliation banner | Tell an administrator. Do not try to fix balances. An administrator investigates and adds a correcting entry. |
| An officer's numbers look out of line on the Outliers page | A supervisor reviews that officer's recent sanctions and appeals. It is a prompt to look, not a finding. |
| You made a mistake recording something | Do not look for an edit button: there is none. Ask an administrator to add a correcting entry. |
| A resident asks to see the rules | Everything locked shows its reason and how to appeal. Appeals go to someone other than the person who made the decision. |

## Things this system will not do

It will not record or transcribe attorney communications, lock the protected services, let one person
impose a significant sanction alone, let jobs affect a resident's tier, let a keyword create a sanction,
store camera pictures, give anyone a risk score, or let anyone change the log. If a request would need
one of these, the answer is no, and the Audit log shows who asked.
