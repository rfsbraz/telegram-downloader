# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest release | Yes |
| `edge` (main branch) | Best effort |
| older releases | No |

Security fixes target the latest release and `main`. Older releases may receive patches for critical vulnerabilities on a best-effort basis.

## Reporting a Vulnerability

Please report security vulnerabilities through [GitHub Security Advisories](https://github.com/rfsbraz/telegram-downloader/security/advisories/new).

- Include steps to reproduce, affected version, and impact assessment
- Allow up to 72 hours for an initial response
- Keep details private until a fix is released

## Scope

- Unauthorized access to user data or downloads
- Remote code execution or privilege escalation
- Bypass of download filters or configuration restrictions
- Insecure handling of credentials, tokens, or session files
- Container misconfigurations that weaken security

## Out of Scope

- Social engineering attacks on maintainers
- Issues requiring physical access to the host
- Denial-of-service requiring unrealistic resources
- Known dependency vulnerabilities without practical exploitation in this project

## Disclosure Process

1. You report the vulnerability privately
2. We investigate and develop a fix
3. You receive a pre-release advisory to confirm the fix
4. Fix is released with a security advisory
5. You're welcome to discuss the vulnerability publicly after release

We're happy to credit reporters in release notes unless you prefer to remain anonymous.
