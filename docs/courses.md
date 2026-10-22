# Course format

A course is a folder. Adding one needs no code change: drop the folder into `content/courses/`, run `make courses-check`, then `python scripts/courses.py publish "reason"` (or the normal seed) to make it a new, audit-logged config version.

```
content/courses/<CODE>/
  course.json
  quiz.json
  lessons/<id>.<lang>.md          # standard text, e.g. budget.en.md, budget.es.md
  lessons/<id>.<lang>.simple.md   # optional plain-language variant (resident reading level "simple")
```

The folder name must equal `code`.

## course.json

| Key | Meaning |
|---|---|
| `code` | Unique, upper case (`NUM101`). |
| `level` | `basic`, `advanced` or `program`. Decides which entitlement gates it and the default points event (`points_by_level` in `config/courses.yaml`). |
| `languages` | `["en"]` or `["en","es"]`. English is required; a missing Spanish lesson falls back to English on screen. |
| `reading_levels` | `["standard"]` or `["standard","simple"]`. |
| `title`, `summary` | `{en, es}`. |
| `pass_mark` | 0 to 1, share of drawn questions that must be right. |
| `prerequisites` | Course codes to finish first. Basic courses may only require basic courses, and at least one basic course must have none, so baseline education always has an open door (invariant 1). |
| `points_kind` | Optional override of the points event kind. |
| `quiz` | `{draw, max_attempts, cooldown_minutes}`; each optional, defaults in `config/courses.yaml` `quiz_defaults`. |
| `lessons` | Ordered list of lesson ids. |
| `license` | Required. Source and licence of the text. |

## quiz.json

`{"questions": [{"id", "prompt": {en, es}, "choices": [{en, es}, ...], "answer": <index>}]}`. `draw` questions are picked at random from the bank, and the choices are shuffled, for every attempt. The answer key never leaves the server.

## Lessons

First line is `# Title`. Only paragraphs, `-` bullets, `1.` numbered lists, `**bold**` and `*italic*` are allowed. No HTML, links or images. Text is screened for personal data (emails, phone numbers, SSNs and similar).

## Validation

`make courses-check` (or `python scripts/courses.py validate [folder ...]`) lists every problem at once and exits 1: missing files, bad JSON, unknown keys, prerequisite cycles or unknown codes, a basic course with a non-basic prerequisite, an answer index out of range, a draw larger than the bank, disallowed Markdown, personal data. `list` shows what is loaded.

## Behaviour

- Lessons can be read and finished offline. The device saves the course, completions are queued and sent on reconnect; progress only moves forward.
- The quiz needs a connection. Starting a paper counts as an attempt (resuming the open paper does not). After a failed paper there is a cooldown; after `max_attempts` in 24 hours the next try waits for the oldest to age out. These limits pace the **quiz only**; lessons never lock.
- A pass awards the points once, issues one certificate (serial `CODE-XXXXXXXX`, append-only), and may raise the tier. Residents see their certificates on the device; staff can print them from the resident page.
