# How Claude writes the weekly bond briefing

Every Saturday the GitHub job `briefing.yml` saves `data/briefings/facts/<date>.json` (every number
the briefing may use) and a plain factual draft `data/briefings/<date>.md`. Claude then rewrites the
draft into the finished briefing, following these rules.

## Who it's for

A careful individual investor in the UK who is not a finance professional, but who wants to follow
government bond markets properly. Write so they understand every sentence without a glossary, while
keeping the numbers precise enough for someone who does know the jargon.

## Rules

1. **Only use numbers from the facts file.** Never invent, estimate, round differently or bring in
   outside figures, news or events. If the facts don't explain *why* something moved, don't guess a
   cause; describe what happened and, at most, what usually drives such a move (for example "rising
   yields across most countries at once usually reflect expectations for interest rates or inflation").
2. **Explain the direction.** Every time, say what a move means for a bond holder: when yields rise,
   bond prices fall, and longer bonds fall most.
3. **Basis points.** Write "basis points" in full the first time (one basis point is 0.01 percentage
   points), then "bp" is fine. Yields themselves are in percent.
4. **Name every comparison.** "Italy pays 0.9 percentage points more than Germany", not "spreads widened".
   Scores rank markets against each other, so say "ranks among the highest of the 33 markets".
5. **Pounds first.** The practice portfolios are in pounds; say so. Yields hedged into pounds are the fair
   way to compare countries for a UK investor; mention them where useful.
6. **Not advice.** Describe what the data shows. Never tell the reader to buy or sell. The score was tested
   on the past (facts: `scoreTestOnThePast`) and the result was encouraging, but frame high scores as "worth
   a closer look", never as a recommendation.
7. **No jargon without an explanation.** "Overweight" = "the numbers favour holding more"; "real yield" =
   "yield after expected inflation"; "spread" = "the extra yield over ..."; "curve inversion" = "short-term
   yields above long-term ones".
8. **Plain, calm, British English.** Short sentences. No hype, no exclamation marks.
9. **Metric units** if a quantity ever needs a unit (the site never uses pounds as a weight).

## Structure (about 600 to 900 words)

1. Title: `# Bond briefing: week to <weekEnding written out, e.g. Friday 9 October 2026>`
2. **In brief**: 3 to 5 bullet points a busy reader could stop at.
3. **Yields this week**: the headline 10-year yields (US, UK, Germany, France, Italy, Japan), the US curve,
   and the euro-area gaps (France and Italy over Germany).
4. **Biggest moves**: the largest rises and falls in benchmark yields; group related moves (for example
   several euro-area countries together) rather than listing everything.
5. **Credit, inflation and volatility**: corporate spreads, inflation expectations, the MOVE index; one
   sentence each on what the level means.
6. **Central banks**: any rate changes in the week, and next week's scheduled decisions and data (facts:
   `nextWeek`). Leave the section out if both are empty.
7. **Scores and signals**: highest and lowest scores, biggest score changes, any signal changes.
8. **Practice portfolios**: values against £10,000, with a reminder that weeks of results mean very little.
9. **Worth watching next week**: two to four things taken from the facts.
10. A one-line reminder that this is not investment advice.

The file must start with the line `<!-- author: Claude -->` so the site labels it correctly.
