# Indie Hackers Post — Ready to Paste

**Title:** I run 3 rank-and-rent sites making $400/week. I got tired of listening to every call, so I built an AI tool to classify them.

---

I run rank-and-rent lead gen sites — basically SEO websites that rank for "[trade] near me" in a city, capture calls, and sell those leads to local businesses at $50/lead. Right now I've got 3 sites in Toowoomba (Queensland, Australia) across hot tub repair, locksmiths, and tow trucks. They bring in about $400/week combined.

The business model works. The problem I ran into wasn't getting leads — it was figuring out which calls actually booked a job.

**The problem:** At 50+ calls a week across multiple sites and partners, I was spending hours every week listening to call recordings one by one. Did this one book? Was that one a voicemail? What did the customer actually say? I was updating spreadsheets from memory and guessing half the time. When a partner asked "what am I paying for?" I'd just point at a call log with no context.

This doesn't scale. At 10 calls a week it's fine. At 50-100 it's a second job. And I had 15+ more niches planned.

**What I built:** [CallOutcome](https://calloutcome.com?utm_source=indiehackers&utm_medium=organic&utm_campaign=launch_2026_03) — it connects to your existing call tracking (CallRail or Twilio — takes about 2 minutes to connect), pulls every recording, transcribes it with OpenAI Whisper, and classifies the outcome using GPT: job booked, not booked, or voicemail. The whole pipeline runs automatically. I just check the dashboard.

It also extracts the customer name, service type, urgency, and booking date from each call. And there are shareable "proof dashboards" I can send to partners — they can see exactly which calls booked jobs without needing a login.

**The numbers:** I've scored 500+ calls through it so far. AI accuracy is ~95% on classification (I've manually verified). Cost is about $0.03-0.04 per call for the AI processing (Whisper + GPT). I was spending maybe 3-4 hours a week on call review before — now it's zero.

**Stack:** Flask, PostgreSQL (Supabase), OpenAI Whisper + GPT-4o-mini, Stripe for billing. Deployed on Railway. Total infra cost is maybe $20/month at my current volume.

**The business side:** I'm now opening this up to other lead gen operators, rank-and-rent people, and agencies who have the same problem. Pricing is:

- **Free:** 50 calls/month (enough to see if it works for you)
- **Starter:** $29/month (100 calls)
- **Pro:** $79/month (500 calls)
- **Agency:** $149/month (1,500 calls)

I'm also running a **Founding 50** deal — $149 one-time for lifetime Pro access (500 calls/month forever). Figured the first 50 users should get rewarded for taking a chance on something new. Details at [calloutcome.com/founding](https://calloutcome.com/founding).

Right now I have zero external users. I'm the only one using it. I built it to solve my own problem and it works well for me — now I'm trying to figure out distribution. Reddit ads burned A$91 on 51 clicks with zero signups (turns out most of those "clicks" were bots). YouTube outreach to creators got zero replies. So here I am, posting on IH.

If you run lead gen, rank-and-rent, pay-per-call, or anything where you need to know whether calls booked jobs — I'd genuinely appreciate you trying it. Free plan is 50 calls/month, no credit card. I want real feedback more than revenue right now.

Happy to answer any questions about the build, the rank-and-rent model, or the AI pipeline.

---

**Screenshot to attach:** Use `marketing/dashboard-screenshot-2026-03-09.png` (redacted version showing the dashboard with real call data)
