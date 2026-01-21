# Security Policy

## Supported Versions
Security fixes target the latest released version and the `main` branch. Older releases may receive fixes on a best-effort basis when the vulnerability is critical and the patch is low risk. If you maintain a fork, we recommend staying current with upstream updates.

## Reporting a Vulnerability
- Email the maintainer team at security@telegram-downloader.example (replace with your preferred contact) with the subject line "Security Report".
- Include details to help reproduce the issue: affected version, configuration, logs, or proof-of-concept if possible.
- If the vulnerability involves sensitive data, encrypt your report with the maintainer's public key if one is published.
- Please allow up to 72 hours for an acknowledgement. If you receive no response, feel free to follow up.

## Preferred Principles
- Avoid opening public GitHub issues to report security vulnerabilities. Public reports will be converted to private discussions when feasible.
- During responsible disclosure, keep details private until a fix is released and documented.
- Provide a timeframe for coordinated disclosure if your policies require it; we generally aim to publish patches within 30 days.

## Coordinated Disclosure Process
1. Maintainers acknowledge receipt of your report and begin investigation.
2. A fix is developed, reviewed, and tested in private.
3. You receive a pre-release advisory to confirm the fix and coordinate disclosure timing.
4. The fix is released with a changelog entry and security advisory (if applicable).
5. After publication, you are welcome to discuss the vulnerability publicly.

## Scope
Security reports should focus on:
- Unauthorized access to user data or downloads
- Remote code execution or privilege escalation within the application
- Bypass of download filters or configuration restrictions
- Insecure handling of credentials, tokens, or secrets
- Container or deployment misconfigurations that materially weaken security

## Out of Scope
- Social engineering attacks on maintainers or contributors
- Issues requiring physical access to the deployment environment
- Dependencies with known vulnerabilities unless they impact practical exploitation of this project
- Denial-of-service attacks that require unrealistic resources or rely on misconfigured infrastructure

## Thank You
We appreciate responsible disclosure and are happy to credit reporters in release notes unless anonymity is requested. Your efforts keep the Telegram Media Downloader community secure.
