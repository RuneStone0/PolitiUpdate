# PolitiUpdate — Financials

## Cost model
- **X Premium subscription**: ~$8/mo (~$96/yr) — required for long posts (>280 chars) and monetization eligibility
- **X API posting**: $0.015/post link-free; $0.20/post if the text contains a URL
  - Link-free at ~15 posts/day: ~$7/mo
  - With URLs: ~$90/mo (avoided — strategy is link-free)
- **LLM for weekly summary**: negligible (pennies/mo)
- **Hosting**: local UmbrelOS server — no recurring cloud cost
- **Total running cost**: ~$100–110/yr (dominated by Premium)

## Revenue model — X Ads/Creator Revenue Sharing
Eligibility (all required simultaneously):
- X Premium subscription (~$8/mo)
- 500 *verified* (Premium) followers
- 5M organic impressions in last 90 days
- Stripe account, 18+, account 3+ months old, complete profile, verified email + 2FA, good standing
- Payout: ~$30 minimum, biweekly via Stripe; weighted to verified (Premium) impressions

Market constraints:
- Denmark: ~1.1–1.23M X users; ~6K–20K Premium users nationwide
- 500 verified followers realistically needs ~17K–50K total followers
- 5M impressions/90 days ≈ 55K/day ≈ ~5% of Danish X users daily

Revenue estimate (if eligible):
- Realistic: ~$10–100/mo (verified-impression-weighted)
- Aggregator cut (April 2026): repost accounts earn ~60% of normal, with further cuts planned
- Ceiling: a few hundred $/month in a best case

## Odds
- Base case (plain snippet bot): ~5–15% chance of ever net-positive
- With link-free + full text + weekly AI summaries: ~15–30%
- Expected value is negative for the first 1–3 years in most scenarios
- X auto-translates posts, so posting Danish adds no translation cost; English summaries remain the biggest lever to reach US/UK Premium audiences

## Levers that improve the picture
- English/bilingual summaries → international Premium audiences (highest penetration + multipliers)
- Original content (summaries, context) reduces aggregator classification risk
- Website/newsletter funnel → monetization we control, not dependent on X's program

## Decision
- Build as a portfolio/public-service project; treat monetization as optional upside
- Re-evaluate when/if follower count and impressions approach the eligibility thresholds
