# HEK business model

Status: proposed product direction. This document does not establish that features, payments, broadcasts, trading services, or revenue are live.

## Product

Build a Telegram companion and dashboard around a 24/7 radio station, useful research, and optional paid software. Customers purchase services with stated deliverables and prices. Customer investment deposits and losses are not revenue streams for this product.

## Revenue streams

| Offering | Revenue basis | Delivery requirement |
| --- | --- | --- |
| Premium bot and dashboard | Subscription | Publish features, billing period, price, cancellation and refund terms before checkout. |
| Reports and backtesting | Usage credits or individual purchase | Show credit cost and data limitations before purchase; distinguish hypothetical results from actual performance. |
| Radio advertising | Sold placements | Label sponsored segments audibly and in associated descriptions. |
| Sponsored shows and newsletters | Fixed sponsorship contracts | Disclose sponsor identity; preserve editorial independence. |
| Premium audio | Subscription | Offer specific exclusive programming or an actually ad-free feed. |
| Listener support | Voluntary tips or memberships | Explain benefits; do not imply charitable status. |
| White-label bots and stations | Setup plus recurring license/support fee | Agree scope, uptime expectations and support terms. |
| Production and syndication | Project or licensing fee | License only content and recordings we own or may distribute. |
| Courses and events | Ticket or access fee | Describe curriculum, dates and refund conditions accurately. |
| Affiliates | Disclosed referral commissions | Disclose commercial relationships near links; do not misrepresent recommendations. |
| Marketplace | Disclosed commission | Publish seller rules, delivery standards and dispute handling. |
| Merchandise | Product margin | State shipping costs and return terms. |
| Original data and APIs | Access or usage fee | Confirm redistribution rights, provenance and privacy obligations. |

Pricing remains undecided. Do not publish invented subscriber counts, returns, sponsor relationships, availability, or earnings.

## Money and account behavior

- Use verified payment-provider events as the basis for paid access. Deduplicate events and handle refunds and cancellations.
- Separate subscription receipts, tips and advertising revenue in accounting. Report net results after refunds, provider fees and operating costs.
- Display credits as service credits, never as invested capital or withdrawable trading profits.
- If a simulation exists, label every relevant balance and result as simulated. It must not accept investment deposits.
- Do not promise returns, fabricate trades or balances, add hidden withdrawal charges, or fund promised returns from new customer deposits.
- Do not collect trading deposits, operate leveraged dealing or copy trading, or charge investment management/performance fees as part of this scope. Those require a separately reviewed business and authorization model.

## 24/7 radio

A player or stream URL alone is not a broadcasting operation. Before claiming continuous service, configure a broadcaster such as a managed station service or an appropriate streaming stack, a scheduled content library, fallback audio, monitoring, and a recovery procedure.

Use original or appropriately licensed content. Verify applicable music, performance, recording and distribution rights for the intended territories and platforms. Label replayed shows and automated presenters accurately. Obtain guest permissions and record sponsor commitments.

Start with original educational programming, interviews and permitted audio. Maintain a schedule and archives with accurate timestamps. Publish live/offline status based on actual stream health. Never autoplay audio without a user action.

## Success measures

Track paying customers, retention, refunds, contribution margin, listening hours, sponsor renewals and support costs. Use aggregate analytics where possible; do not sell personal financial information.

An illustrative model is subscription revenue plus contracted sponsor revenue plus licensing revenue, less payment fees, refunds, content costs, hosting and support. Forecasts are assumptions, not demonstrated earnings.
