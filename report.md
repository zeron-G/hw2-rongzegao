# Report: Build and Evaluate a Simple GenAI Workflow

## Business Use Case

The workflow I chose is drafting first-pass customer support email replies for a fictional B2B SaaS company called Northstar Analytics. The user is a support specialist who receives a customer message plus limited account and policy context. The system's job is to produce a concise draft reply, internal notes, and a `review_required` flag for risky cases.

This is a good candidate for partial automation because support writing is repetitive, high-volume, and time-sensitive. At the same time, it is risky enough that a fully autonomous system would be unsafe. Refunds, credits, privacy requests, and account ownership changes all require policy discipline and sometimes human approval. That made the task a good fit for this assignment: the model can save writing time, but honest evaluation should still surface clear human-review boundaries.

## Model Choice

I used `gpt-4.1-mini` for the live evaluation runs. I chose it for three practical reasons: it was the only provider with a working API key in my local environment on March 31, 2026, it produced consistently structured JSON output, and it was inexpensive enough to run the full evaluation set multiple times during prompt iteration.

I also designed the CLI to support Anthropic / Claude and Gemini models, because I wanted the prototype to be reusable across providers. However, the local `.env` available to me only contained a working OpenAI key. Anthropic and Gemini code paths were validated through configuration checks and error handling, but I did not complete a live apples-to-apples model comparison for those providers. I am noting that limitation explicitly because it affects how strongly I can generalize the findings.

## Baseline vs. Final Design

My baseline prompt was intentionally simple: it asked the model to act as a helpful support writer and return structured JSON. That baseline already produced readable drafts, but it was too generic. In the live six-case evaluation set, the baseline scored `26/30` on my heuristic checks. The biggest problem was not grammar or tone. The bigger problem was operational judgment. The model was less reliable about when a case should be treated as routine versus when it clearly needed review.

Revision 1 improved the prompt substantially by adding three kinds of constraints: grounding to the provided facts only, a rule against inventing completed actions, and a clearer requirement for when `review_required` should be true. That immediately fixed a meaningful failure mode. In the SSO case, the baseline over-escalated a relatively straightforward plan-limitation question; Revision 1 correctly answered that SSO is an Enterprise-only feature and treated it as a normal commercial limitation rather than a special-review event. Revision 1 raised the score to `30/30`.

Revision 2 kept the same overall structure but added more explicit decision rules for risky categories such as service credits, refund exceptions, privacy requests, and ownership transfers. I also added a specific writing rule: if a case needs human review, the customer-facing reply should explicitly say the request is "under review" or "needs review." I added that rule because I saw a softer phrasing in the outage-credit case that sounded polite but did not communicate the review state as clearly as I wanted. After that change, the final prompt still scored `30/30`, but the wording was safer and more operationally clear. In other words, Revision 2 did not dramatically improve the numeric score over Revision 1, but it improved the quality of the escalation language in the exact cases where ambiguity is most costly.

## Where the Prototype Still Fails or Needs Human Review

Even the final version should not be treated as an autonomous support agent. First, the evaluation rubric is still a heuristic rubric, not a full semantic judge. It can check for signals like whether the model mentioned "Enterprise" or set the review flag correctly, but it cannot fully measure whether the response sounded too confident, missed a subtle policy nuance, or used the wrong tone for an angry customer.

Second, the model still depends entirely on the context provided in the prompt. If the policy snippet is incomplete, stale, or contradictory, the draft may still be wrong even if it is well written. Third, several categories in my own evaluation set should always trigger human review before anything is sent: service credits, refund exceptions, privacy / deletion requests, and account ownership transfer. Those are precisely the categories where a polished but incorrect answer would be dangerous.

## Deployment Recommendation

I would recommend deploying this workflow only as a draft-assist tool inside a support queue, not as an auto-send system. The safest use would be: a support specialist opens a ticket, the tool generates a first draft plus internal notes, and a human edits or approves the draft before sending. I would make human review mandatory for any ticket involving refunds, credits, privacy, security, or account changes.

Under those conditions, I think the workflow is deployable and useful. It clearly reduces writing effort on routine cases while also surfacing a review boundary for riskier ones. I would not recommend fully autonomous deployment without tighter policy retrieval, stronger evaluation, and audit logging of which prompt version generated each draft.
