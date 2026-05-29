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
- **API keys**: All credentials are read from environment variables or config files excluded from version control (see `.gitignore`)
- **Input validation**: Task schemas enforce type and constraint validation before execution

## Hall of Fame

We appreciate and will credit security researchers who responsibly disclose vulnerabilities.
