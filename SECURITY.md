# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.9.x   | :white_check_mark: |
| < 0.9   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in No-Slop Harness, please report it
privately. **Do not open a public issue.**

### How to Report

1. **GitHub Security Advisory**: Use the [GitHub private vulnerability reporting](https://github.com/iknowkungfubar/no-slop-harness/security/advisories/new) feature (preferred).
2. **Email**: Send details to the maintainer at the email listed on the GitHub profile.

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Affected versions
- Potential impact
- Any suggested fixes (optional)

### What to Expect

- **Acknowledgment**: Within 48 hours
- **Assessment**: Within 5 business days
- **Fix**: We aim to release a patch within 30 days, depending on severity
- **Disclosure**: We practice coordinated disclosure — you will be credited unless you prefer anonymity

## Security Design

No-Slop Harness is a local-first framework. Key security principles:

- **No network by default**: The harness does not make outbound connections unless explicitly configured
- **Sandboxed execution**: Tool commands run in isolated environments via the sandbox layer
  - Commands are parsed with `shlex.split()` into list form (no `shell=True`), preventing allowlist bypass via subshells (`$(...)`, `` `...` ``), pipes, and chained commands
  - Implicit blocklist always prohibits destructive operations (`rm -rf /`, `mkfs`, `shutdown`, etc.)
  - Configurable allowlist restricts execution to approved commands
  - Output is truncated at the configured byte limit to prevent memory exhaustion
- **API keys**: All credentials are read from environment variables or config files excluded from version control (see `.gitignore`)
- **Input validation**: Task schemas enforce type and constraint validation before execution
- **Path traversal protection**: File operations in the Implementor agent validate that target paths resolve within the working directory, preventing unauthorized file access
- **Pipeline state isolation**: State files are persisted with `0o600` (owner-only) permissions and stored in `.no-slop/` (excluded from version control)
- **Git worktree isolation**: Each task executes in an isolated git worktree; changes are merged only after passing verification, ensuring atomic task boundaries
- **Secrets redaction**: Accidental secret exposure is minimized via `.gitignore` patterns (`.env`, `.env.*`), CI gitleaks scanning, and redaction of API keys from the LICENSE file

## Hall of Fame

We appreciate and will credit security researchers who responsibly disclose vulnerabilities.
