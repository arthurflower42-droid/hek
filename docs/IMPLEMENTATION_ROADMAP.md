# HEK implementation roadmap

Status: planning only. Existing application code has not been reviewed or changed for this roadmap. No bot token, payment connection, live station or deployment is created by these documents.

## 1. Establish the actual application baseline

Before modifying runtime code, inspect repository instructions, entry points, deployment configuration and current tests. Identify existing balance, payment and referral behavior. Preserve user data and document migrations and rollback steps. Do not overwrite an unknown application blindly.

## 2. Telegram companion

Provide Start, Listen, Schedule, Tools, Plans, Account, Support and Disclosures actions. Account shows service entitlements and billing status; it does not imply an investment account. Only show working features and configured links. Validate external URLs, keep bot tokens in deployment secrets and redact them from logs.

Acceptance: navigation works for new and returning users; missing configuration produces an honest unavailable message; unauthorized users cannot access paid features or another user's account.

## 3. Radio service

Configure a broadcaster, licensed content, a schedule, fallback audio and health monitoring. Provide an accessible play/pause player and a visible offline state. Mark replays and sponsored segments. Define an operator runbook for outages and content complaints.

Acceptance: a real stream plays after user interaction; an outage is detectable; scheduled content and fallback behavior are verified; no claim of 24/7 availability is made before sustained operation has been tested.

## 4. Paid services

Select a payment provider compatible with the platform, product and customer jurisdictions. Check Telegram's current requirements for digital goods before selecting its checkout mechanism. Set actual prices and complete cancellation, refund, support and privacy information.

Implement server-side payment verification, idempotent fulfillment and refund/revocation handling. Never accept a browser redirect or user-supplied receipt alone as proof of payment. Keep receipts separate from service credits and hypothetical analytics.

Acceptance: sandbox purchase grants access once; duplicate notifications do not duplicate entitlements; invalid notifications fail; cancellation and refunds update access according to the published policy; secrets are absent from source and logs.

## 5. Sponsorship and business sales

Add clearly disclosed sponsor inventory, an inquiry route and white-label service descriptions. Do not publish sponsor logos without permission or sell unmeasured audience figures as verified reach. Launch affiliates only with appropriate disclosures.

Acceptance: listeners can identify advertising; sales materials distinguish actual metrics from estimates; white-label contracts specify deliverables and support.

## 6. Release

Run repository checks and end-to-end tests for account isolation, payment events, paid access, radio playback and failure states. Verify links, privacy handling, accessibility and operational recovery. Summarize what is implemented, what was tested and what remains unconfigured before deploying.

## Later options

Add original reports, usage-based analytics, licensed data APIs, courses, events, production services, syndication, marketplace offerings and merchandise only when the corresponding product is deliverable. Avoid adding checkout buttons for unfinished products.
