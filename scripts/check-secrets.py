"""Fail if tracked files contain anything that looks like a real secret.

    python scripts/check-secrets.py          # scans files tracked by git
    python scripts/check-secrets.py --all    # also scans untracked, not-ignored files

Known synthetic development values (see scripts/secrets-allowlist.txt) are allowed because the
repository holds synthetic data only. Everything else that looks like a credential is reported.
"""

import fnmatch
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / "scripts" / "secrets-allowlist.txt"

FORBIDDEN_PATHS = [
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "id_rsa*",
    "var/*",
    "web/e2e/.fixtures.json",
    ".venv/*",
    "*/node_modules/*",
]
ALLOWED_PATHS = [".env.example"]
SKIP_FILES = ["package-lock.json", "*.png", "*.ico", "*.svg", "*.woff2"]

TOKEN_PATTERNS = {
    "private key": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP |ENCRYPTED )?PRIVATE KEY-----"
    ),
    "AWS access key id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b"
    ),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "Stripe-style key": re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    "API key (sk-...)": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "JSON web token": re.compile(
        r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
    ),
}
ASSIGNED = re.compile(
    r"""(?ix)\b(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|private[_-]?key)\w*
        \s*[:=]\s*["']([^"'\s$\{\}]{8,})["']"""
)
URL_PASSWORD = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@]+:([^@\s/]{4,})@")
PLACEHOLDER = re.compile(
    r"(?i)(change-?me|example|placeholder|your[-_]|xxxx|<[^>]+>|\.\.\.|dummy)"
)


def allowed_values() -> set[str]:
    vals = set()
    for line in ALLOWLIST.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            vals.add(line)
    return vals


def files(include_untracked: bool) -> list[str]:
    cmd = ["git", "ls-files"] + (
        ["--others", "--exclude-standard", "--cached"] if include_untracked else []
    )
    out = subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    return sorted(set(out.splitlines()))


def mask(v: str) -> str:
    return v[:3] + "…" + f"({len(v)} chars)"


def scan(paths: list[str], root: Path = ROOT) -> list[str]:
    ok = allowed_values()
    findings = []
    for rel in paths:
        if any(fnmatch.fnmatch(rel, p) for p in ALLOWED_PATHS):
            pass
        elif any(
            fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(Path(rel).name, p)
            for p in FORBIDDEN_PATHS
        ):
            findings.append(f"{rel}: file that must never be committed")
            continue
        if any(fnmatch.fnmatch(Path(rel).name, p) for p in SKIP_FILES):
            continue
        path = root / rel
        try:
            text = path.read_text()
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for name, rx in TOKEN_PATTERNS.items():
                for m in rx.finditer(line):
                    if m.group(0) not in ok:
                        findings.append(
                            f"{rel}:{n}: looks like a {name} ({mask(m.group(0))})"
                        )
            for rx, what in (
                (ASSIGNED, "hard-coded secret"),
                (URL_PASSWORD, "password in a URL"),
            ):
                for m in rx.finditer(line):
                    value = m.group(1)
                    if (
                        value in ok
                        or PLACEHOLDER.search(value)
                        or any(a in value for a in ok if len(a) > 8)
                    ):
                        continue
                    findings.append(f"{rel}:{n}: {what} ({mask(value)})")
    return findings


def main() -> int:
    findings = scan(files("--all" in sys.argv))
    if findings:
        print("Possible secrets found:\n  " + "\n  ".join(findings))
        print(
            "\nIf a value is a synthetic development value, add it to scripts/secrets-allowlist.txt."
        )
        return 1
    print("No secrets found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
