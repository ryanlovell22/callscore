---
title: "Case Study: How I Use AI Call Scoring Across 2 Rank-and-Rent Operations"
slug: case-study-rank-and-rent-call-scoring
description: "Real numbers from a hot tub repair site in Spokane and appliance repair sites in Toowoomba. How CallOutcome replaced manual call listening with AI-powered call scoring."
date: 2026-03-08
author: CallOutcome Team
---

I run rank-and-rent lead gen sites across two markets: a hot tub repair site in Spokane, Washington, and a cluster of appliance repair sites in Toowoomba, Australia. Both operations send inbound calls to local trade partners who pay per lead.

The problem was always the same: **how do you prove which calls actually booked a job?**

This is how I solved it with AI call scoring — and the real numbers behind both operations.

## The Spokane Operation: Hot Tub Repair

### Background

I acquired a rank-and-rent hot tub repair site targeting the Spokane metro area about 6 months ago. The site had been running for 2 years and was already generating steady call volume when I bought it.

**The setup:**

- 4 tracking lines covering Spokane, Spokane Valley, Coeur d'Alene, and Sandpoint
- 1 trade partner (a local hot tub repair company)
- ~100 inbound calls per month
- Partner pays a flat $350/week for exclusive leads

### The problem

My partner specifically requested regular updates on call statistics. He wanted to know:

- How many calls came in each week
- How many of those calls actually booked a job
- Which locations were generating the most leads
- Whether missed calls were costing him opportunities

Before CallOutcome, producing these reports meant **manually listening to call recordings**. At 100 calls per month, that is roughly 8-10 hours of listening time every month — time I did not have as someone running this as a side business.

I tried using [call duration as a proxy](/blog/how-to-track-call-conversions-for-lead-gen) ("calls over 2 minutes are probably booked"), but that was wildly inaccurate. A 4-minute call where the customer asks questions and then says "I'll think about it" is not a booked job. A 40-second call where someone says "Can you come Saturday?" and the tech says "Yep, 9am works" is a booking.

### The solution

I connected my Spokane tracking numbers to CallOutcome. The AI analyses every call recording and classifies it as:

- **Job Booked** — the customer and tech agreed on a date/time
- **Not Booked** — inquiry only, price shopping, or declined
- **Missed** — no answer, voicemail, or hangup

Each call gets a full transcript, so I can verify any classification with a quick scan instead of listening to the whole recording.

### Results

| Metric | Before CallOutcome | After CallOutcome |
|--------|-------------------|-------------------|
| Time spent on call review | ~8-10 hrs/month | ~20 min/month |
| Reporting to partner | Manual spreadsheet, delayed | Shared dashboard, real-time |
| Accuracy of "booked" tracking | ~60% (duration guessing) | ~95% (AI + transcript) |
| Billing disputes | Occasional | None since launch |

The [shared proof dashboard](/blog/how-to-prove-lead-quality-to-clients) was the game-changer for the partner relationship. Instead of me sending a spreadsheet every week, my partner can log in anytime and see exactly which calls came in, which ones booked, and read the transcript if he wants to verify. That transparency eliminated billing disputes entirely.

**Cost of call scoring:** At ~100 calls per month, my CallOutcome cost is roughly $3-4/month in AI processing. Compare that to 8-10 hours of my time.

## The Toowoomba Operation: Appliance Repair

### Background

I run 3 appliance repair lead gen sites in Toowoomba, Queensland, covering oven repair, dishwasher repair, and general appliance repair. These are newer sites with a different billing model.

**The setup:**

- 4 tracking lines across the 3 sites
- 2 trade partners splitting the coverage
- ~100+ calls in the first week
- Partners pay **$50 per booked job** and **$12.50 per missed call**

### Why per-lead billing needs accurate scoring

With the Spokane site, my partner pays a flat weekly rate, so call classification is about transparency and reporting. With the Toowoomba sites, classification directly affects how much I bill. Every misclassified call is money left on the table or an overcharge that damages trust.

If I classify a "not booked" call as "booked", I am overcharging my partner $50 for that call. If I miss a legitimate booking, I am losing $50. At 100+ calls per week, manual review is simply not scalable — and errors compound fast.

### How the AI scoring works

CallOutcome pulls recordings from my call tracking platform, runs them through speech-to-text transcription, then uses AI to read the transcript and answer one question: **did the customer and the tradesperson agree on a job?**

It is not looking for keywords or call duration. It is [reading the actual conversation and understanding context](/blog/how-ai-call-scoring-works). A call where the customer says "I need my oven fixed" and the tech says "I can come Thursday at 2pm" and the customer says "Perfect" — that is a booked job. A call where they discuss pricing and the customer says "Let me talk to my wife" — that is not booked.

### Results after week one

| Metric | Value |
|--------|-------|
| Total calls processed | 100+ |
| Time to set up | ~15 minutes |
| Manual call reviews needed | 3 (edge cases I wanted to verify) |
| AI accuracy | ~95%+ on clear calls |

The 3 calls I manually reviewed were genuine edge cases — situations where the customer said something ambiguous like "yeah, sounds good, I'll call back to confirm the time." The AI correctly flagged these as "not booked" because no firm appointment was made.

## What I Have Learned Running Both Operations

### 1. Flat-rate and per-lead billing both benefit from scoring

With Spokane (flat rate), call scoring builds trust and retains the partner. With Toowoomba (per lead), it directly protects revenue. Either way, you need to know which calls booked.

### 2. Manual call review does not scale past ~30 calls per week

If you are running one site with 10 calls a week, you can listen to everything. Once you are running multiple sites across multiple markets, manual review becomes a full-time job. Across Spokane and Toowoomba, I am processing 200+ calls per month. There is no way I am listening to all of those.

### 3. Shared dashboards reduce partner churn

Before CallOutcome, my Spokane partner occasionally questioned the call volume numbers. Now he logs into his own dashboard and sees every call with a transcript. No more "I don't think I got that many calls this week." The data is right there.

### 4. Missed call tracking is surprisingly valuable

I did not expect this, but tracking missed calls turned out to be one of the most useful features. When I can show a partner that they missed 8 calls last Tuesday, that is a conversation about them hiring a receptionist — not about whether my leads are any good. It shifts the blame from my lead quality to their call handling.

### 5. The cost is negligible

Across both operations, my AI call scoring costs less than $10 per month. I was spending that much time on manual review in a single afternoon. The ROI is absurd.

## My Tech Setup

For anyone wanting to replicate this:

1. **Call tracking:** I use Twilio for my tracking numbers. CallOutcome also integrates with [CallRail](/blog/callrail-vs-calloutcome), which is what most rank-and-rent operators use.
2. **Call scoring:** CallOutcome handles transcription and AI classification automatically. I connected my Twilio account in about 5 minutes.
3. **Billing:** I pull the monthly stats from CallOutcome and invoice my partners based on the booked/missed call counts.
4. **Partner access:** Each partner has their own login where they can see only their calls. Full transparency.

The whole setup takes about 15 minutes. Connect your call tracking, select your numbers, and the AI starts scoring calls automatically.

## The Bottom Line

If you are running rank-and-rent sites and still manually listening to calls or guessing based on call duration, you are wasting hours every month and leaving money on the table.

AI call scoring is not a "nice to have" — it is the difference between running a professional lead gen operation and running a hobby. Your partners expect data. Your billing depends on accuracy. And your time is worth more than listening to phone calls.

I have been running both operations through CallOutcome and the time savings alone justify the switch. The accuracy, the shared dashboards, and the elimination of billing disputes are just bonuses.
