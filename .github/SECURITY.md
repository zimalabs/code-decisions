# Security Policy

## Scope

code-decisions is a local-only Claude Code plugin. It:
- Reads and writes markdown files in `.claude/decisions/` (in the repo)
- Has no authentication, no server, no network calls
- Runs entirely in your local shell via Claude Code hooks

## Reporting a Vulnerability

If you discover a security issue, email **security@zimalabs.ai** with:
- Description of the vulnerability
- Steps to reproduce
- Impact assessment

**Do not open a public issue for security vulnerabilities.**

## Response Timeline

- Acknowledgment within 48 hours
- Fix or mitigation within 7 days for confirmed issues
- Public disclosure after fix is released

## Out of Scope

- Issues requiring physical access to the machine
- Social engineering attacks
