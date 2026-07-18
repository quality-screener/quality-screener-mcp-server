# Privacy Policy

**Effective date:** 18 July 2026
**Last updated:** 18 July 2026

This policy explains what personal data the Quality Screener MCP server and the
Quality Screener service behind it collect, why, and what your rights are.

Throughout this document, "the MCP server" means the hosted endpoint at
`https://mcp.qualityscreener.io/mcp`, and "the service" means the Quality
Screener application at `https://qualityscreener.io` that holds your account.

---

## Summary

The only personal data we retain is **your email address**, which identifies your
account. We do not sell it, we do not use it for advertising, and we do not share
it with third parties for their own purposes. Everything else the MCP server
handles is either non-personal market data or a short-lived credential.

---

## What we collect

### Personal data we retain

| Data | Source | Why we hold it |
| --- | --- | --- |
| Email address | You, at sign-up (directly or via Google sign-in) | Identifies your account, enables sign-in, and lets us contact you about the service |
| Username *(optional)* | You, in your profile | Display name inside the application |
| Organization *(optional)* | You, in your profile | Display and grouping inside the application |

Username and organization are optional profile fields. If you leave them blank,
we hold only your email address.

### Credentials

Access tokens are issued when you connect an MCP client and are used to
authenticate your requests. They are credentials rather than profile data, but
they are tied to your account. You can revoke them at any time by signing out.

### Operational logs

Our servers keep standard operational logs (timestamps, request paths, response
status codes, error diagnostics) for security monitoring and debugging. These
logs reference accounts by an internal pseudonymous user identifier, **not** by
email address. They are not used to build a profile of you.

### What we do **not** collect

- Payment or financial account details — the service takes no payments and
  connects to no brokerage.
- The content of your conversations with Claude or any other AI assistant.
- Special-category data (health, biometric, political, religious, or similar).
- Tracking or advertising identifiers. The MCP server sets no cookies and runs
  no analytics or advertising trackers.

---

## How the MCP server handles your data

The MCP server is a **stateless proxy**. It holds no database and writes no
personal data to durable storage of its own. Specifically:

- It forwards each request to the Quality Screener API using **your own** access
  token, so it never acts on a shared or pooled account.
- It keeps OAuth client registrations (which identify *applications*, not people)
  and short-lived authorization codes, which expire within ten minutes.
- When you call the `account_profile` tool, your email address passes **through**
  the server to your AI assistant in the response. It is not stored along the way.

Your account record, including your email address, lives in the Quality Screener
service, not in the MCP server.

---

## How we use your data

We use the data above only to:

1. Authenticate you and keep your session secure.
2. Provide the screening, scoring, and history features you request.
3. Store the scoring systems and shared screens you choose to create.
4. Contact you about service matters such as security or availability issues.

We do **not** use your personal data to train machine-learning models, and we do
not perform automated decision-making that produces legal or similarly
significant effects on you.

---

## Sharing with third parties

We do not sell or rent your personal data. It is disclosed only to the following
categories of recipient, and only as needed to run the service:

| Recipient | What they receive | Purpose |
| --- | --- | --- |
| Your AI assistant provider (e.g. Anthropic, when you use Claude) | The responses to tools you invoke, which include your profile if you call `account_profile` | Delivering results to the client you chose to connect |
| Our hosting provider | Encrypted traffic and operational logs | Running the servers |
| Google | Your email address, if you choose Google sign-in | Authenticating you |

Market and financial data used for screening comes from third-party data
providers. That flow is outbound reference data only — **no personal data is sent
to those providers.**

We may also disclose data where legally required, or to establish, exercise, or
defend legal claims.

---

## Retention

- **Account data (email, username, organization):** retained for as long as your
  account exists, and deleted when you delete it.
- **Access tokens:** retained until you revoke them or they expire.
- **Operational logs:** retained for a limited period for security and debugging,
  then deleted on a rolling basis.

When you delete your account, we delete the associated personal data, except
where we must retain something to meet a legal obligation.

---

## Security

Traffic to the MCP server and the API is encrypted in transit with TLS.
Authentication uses OAuth 2.0 with PKCE, and tokens are scoped to your account
alone. Access to production systems is restricted to maintainers who need it.

No system is perfectly secure, but if a breach affects your personal data we
will notify you and any relevant supervisory authority as the law requires.

---

## Your rights

If you are in the European Economic Area or the United Kingdom, the GDPR gives
you the right to:

- **access** the personal data we hold about you;
- **rectify** it if it is inaccurate;
- **erase** it ("right to be forgotten");
- **restrict** or **object to** our processing of it;
- receive it in a **portable** format;
- **withdraw consent** where processing is based on consent; and
- **lodge a complaint** with your local data protection authority.

Our legal basis for processing your email address is **performance of a contract**
(providing the service you signed up for), and for operational logs it is our
**legitimate interest** in keeping the service secure and reliable.

To exercise any of these rights, email **info@qualityscreener.io**. We aim to
respond within 30 days.

---

## Children

The service is not directed at children under 16, and we do not knowingly
collect their personal data. If you believe a child has provided us with
personal data, contact us and we will delete it.

---

## International transfers

Our infrastructure and service providers may process data outside your home
country, including outside the EEA. Where that happens, we rely on appropriate
safeguards such as the European Commission's Standard Contractual Clauses.

---

## Changes to this policy

We may update this policy as the service evolves. Material changes will be
reflected in the "Last updated" date above and, where the change is significant,
announced through the service. The current version is always published at
<https://github.com/quality-screener/quality-screener-mcp-server/blob/main/PRIVACY.md>.

---

## Contact

Questions, requests, or complaints about this policy or your personal data:

**Email:** info@qualityscreener.io
**Project:** <https://github.com/quality-screener/quality-screener-mcp-server>
**Website:** <https://qualityscreener.io>
