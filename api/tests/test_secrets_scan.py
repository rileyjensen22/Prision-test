import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "check_secrets", ROOT / "scripts" / "check-secrets.py"
)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def scan_text(tmp_path, name, text):
    f = tmp_path / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)
    return check.scan([name], tmp_path)


# Fake secrets are assembled from pieces so this file itself never contains a complete one.
def j(*parts):
    return "".join(parts)


def test_real_secret_shapes_are_found(tmp_path):
    cases = {
        "a.txt": j("-----BEGIN RSA ", "PRIVATE KEY-----\nabc\n"),
        "b.py": j('aws = "AKIA', 'ABCDEFGHIJKLMNOP"'),
        "c.py": j('tok = "ghp_', "a1B2c3D4" * 5, '"'),
        "d.py": j(
            'jwt = "eyJ', "hbGciOiJIUzI1NiJ9.eyJ", "zdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijk123", '"'
        ),
        "e.py": j("pass", 'word = "hunter2', 'hunter2"'),
        "f.yml": j("url: postgresql://appuser:", "S3cretPassw0rd", "@db.internal/prod"),
        "g.js": j("const api", "Key = 'Zx9fA73k", "Lm20Qw81'"),
        "h.py": j('x = "xox', 'b-123456789012-abcdefghij"'),
    }
    for name, text in cases.items():
        assert scan_text(tmp_path, name, text), f"{name} should have been flagged"


def test_forbidden_files_are_flagged_even_when_empty(tmp_path):
    for name in (
        ".env",
        "certs/server.pem",
        "keys/id_rsa",
        "var/seed.json",
        "web/e2e/.fixtures.json",
    ):
        assert scan_text(tmp_path, name, "nothing here"), name
    assert not scan_text(tmp_path, ".env.example", "SECRET_KEY=change-me")


def test_placeholders_and_known_synthetic_values_pass(tmp_path):
    ok = [
        'SECRET_KEY = "change-me-in-production"',
        'password = "dev-password-not-secret"',
        "DATABASE_URL=postgresql+psycopg://isd_app:isd_app_dev_only@localhost:5432/isd",
        'token = "<your-token-here>"',
        "password: str = Field(min_length=1)",
        "const password = useState('')",
        'secret = os.environ.get("SECRET_KEY", "dev-only-secret-change-me")',
    ]
    for i, text in enumerate(ok):
        assert not scan_text(tmp_path, f"ok{i}.py", text), text


def test_findings_never_print_the_secret_itself(tmp_path):
    secret = j("hunter2", "hunter2")
    out = scan_text(tmp_path, "x.py", j("pass", 'word = "', secret, '"'))
    assert out and secret not in " ".join(out)


def test_the_repository_itself_is_clean():
    findings = check.scan(check.files(include_untracked=True))
    assert findings == [], "\n".join(findings)
