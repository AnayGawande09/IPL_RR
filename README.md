# Reliable Under Pressure: SupeRR Selector Season 2

**Who should Rajasthan Royals back at the IPL 2027 auction?** This project finds the 10 batters and 10 bowlers who perform most reliably when a match is on the line. It then matches them to the gaps in RR's own squad.

Everything is built from the competition data pack (IPL 2022–2026 and T20Is 2022–2026, 200,999 balls) in plain Python, with no third-party packages. A separate machine-learning model, trained on public IPL data, is included **only as a cross-check**. Nothing from it feeds into the lists.

| | |
|---|---|
| **Dashboard** | `report/site/index.html` (deployed on Vercel, see [Hosting](#hosting-the-dashboard-on-vercel)) |
| **Summary for judges** | [`report/SupeRR_Judges_Summary.pdf`](report/SupeRR_Judges_Summary.pdf) (7 pages, plain language) |
| **Full methodology** | [`report/SupeRR_Pressure_Report.pdf`](report/SupeRR_Pressure_Report.pdf) (every rule, table and check) |

---

## The answer

**Back Heinrich Klaasen, Tim David, Mohsin Khan and Bhuvneshwar Kumar first.** Each is reliable under pressure *and* fills one of RR's two measured gaps: finishing chases in the death overs, and pace bowling. **Keep Yashasvi Jaiswal**, RR's only player in the top 10.

### Top 10 batters under pressure

| # | Player | 2026 team | SR under pressure (usual) | Stays top 10* | Call for RR |
|---|---|---|---|---|---|
| 1 | Heinrich Klaasen | Sunrisers Hyderabad | 190.4 (158.4) | 91% | Back: priority 1 |
| 2 | Tim David | Royal Challengers Bengaluru | 185.4 (172.6) | 46% | Back: priority 1 |
| 3 | Suryakumar Yadav | Mumbai Indians | 169.1 (162.8) | 29% | Depth option |
| 4 | Rinku Singh | Kolkata Knight Riders | 162.5 (147.9) | 71% | Back: priority 2 |
| 5 | Josh Inglis | Lucknow Super Giants | 176.2 (169.3) | 40% | Depth option |
| 6 | Yashasvi Jaiswal | Rajasthan Royals | 181.8 (155.2) | 66% | Retain |
| 7 | Abhishek Sharma | Sunrisers Hyderabad | 200.0 (182.9) | 26% | Watch |
| 8 | Rajat Patidar | Royal Challengers Bengaluru | 155.6 (168.9) | 7% | Watch |
| 9 | Shreyas Iyer | Punjab Kings | 174.7 (147.1) | 58% | Watch |
| 10 | Prabhsimran Singh | Punjab Kings | 166.2 (160.6) | 35% | Watch |

### Top 10 bowlers under pressure

| # | Player | 2026 team | Economy under pressure (usual) | Stays top 10* | Call for RR |
|---|---|---|---|---|---|
| 1 | Sunil Narine | Kolkata Knight Riders | 6.13 (7.01) | 74% | Depth option |
| 2 | Rashid Khan | Gujarat Titans | 7.04 (7.47) | 48% | Depth option |
| 3 | Kuldeep Yadav | Delhi Capitals | 7.88 (7.83) | 44% | Depth option |
| 4 | Sufiyan Muqeem | not in IPL 2026 data | 3.88 (6.79) | 85% | Watch |
| 5 | Varun Chakravarthy | Kolkata Knight Riders | 8.07 (8.02) | 37% | Depth option |
| 6 | Mohsin Khan | Lucknow Super Giants | 8.06 (8.30) | 39% | Back: priority 1 |
| 7 | Bhuvneshwar Kumar | Royal Challengers Bengaluru | 10.45 (7.97) | 33% | Back: priority 1 |
| 8 | Mohammad Nawaz | not in IPL 2026 data | 7.11 (7.46) | 43% | Watch |
| 9 | Krunal Pandya | Royal Challengers Bengaluru | 6.52 (7.98) | 31% | Watch |
| 10 | Mitchell Santner | Mumbai Indians | 6.26 (7.80) | 35% | Watch |

\*Share of 300 re-runs on re-sampled matches in which the player stays in the top 10: how firm the place is.

The rankings use run value adjusted for the opponent and the stage of the innings, not raw strike rate or economy. That is why a death bowler like Bhuvneshwar Kumar ranks well despite an economy above 10.

**What the calls mean.**
- *Retain:* already RR; keep if possible.
- *Back, priority 1:* fills an RR gap, and the rating is firm.
- *Back, priority 2:* fills an RR gap, but the rating is less firm.
- *Depth option:* reliable, but in an area where RR are not short.
- *Watch:* less certain, because of a small sample, no IPL record, or a rank that leans on the less repeatable "clutch" part of the score.

---

## How it works

```
 1 Clean data  →  2 Win chances  →  3 Find pressure  →  4 Score players  →  5 Check and fit RR
```

1. **Clean the data.** Rebuild the match state before every ball: score, wickets, balls left and target. Every cleaning rule is checked against the data. The rebuilt totals reproduce 372/372 "won by N wickets" results and 99.7% of "won by N runs" margins exactly.
2. **Win chances.** Fit a win-probability model. It combines a Duckworth–Lewis-style resource curve (made monotone with isotonic regression, PAVA) with logistic regression, and was checked by match-grouped cross-validation.
3. **Find pressure.** The **Leverage Index**, from baseball analytics, measures how much one ball can swing the win probability. A ball with LI ≥ 1.5 counts as high pressure; that is 12% of balls. On these balls batters are dismissed 20% more often. Balls in games already decided are removed using a Gaussian mixture fitted by EM.
4. **Score players.** Each ball gets a win-probability-added and a run value. Ridge regression (backfitting) adjusts for the opponent and the phase. **Empirical-Bayes (James–Stein) shrinkage** pulls small samples toward each player's own usual level. Four measures are combined on a true-score scale. To qualify, a player needs at least 60 pressure balls, at least 6 pressure innings, and a match in 2025 or 2026.
5. **Rank, check and fit RR.**
   - **Final order:** three specifications are averaged (all data, IPL only, recency-weighted).
   - **Robustness:** Borda count, SMAA with 4,000 random weightings, and a Poisson bootstrap over matches (300 re-runs).
   - **Accuracy:** an audit plus a time-split test (rate on 2022–24, check against 2025–26).
   - **RR fit:** RR's own 2025–26 pressure record is compared with the rest of the IPL, and each player is matched to the gaps.

### What the checks found
- **Data:** no duplicate or missing balls; every listed player's numbers recount exactly from the raw data.
- **Robust picks:** these are top 10 at both pressure thresholds (LI 1.5 and 2.0).
  - Batting: Klaasen, Tim David, Rinku Singh, Shreyas Iyer.
  - Bowling: Narine, Rashid Khan, Kuldeep Yadav, Varun Chakravarthy, Krunal Pandya.
- **Honest limit:** pressure performance is only partly a stable skill.
  - In the time-split test, a player's underlying quality carried forward better than the "clutch" part of the score.
  - So players whose rank leans on clutch are flagged rather than re-ranked.

### Separate check: a machine-learning model on public data
- **Training data:** every IPL match from 2008 to 2026 (Cricsheet, 1,243 matches) plus public auction prices from 2013 to 2025.
- **Models:** ridge regression and gradient-boosted trees, written in pure Python, chosen by season-by-season validation.
- **Test:** both methods were frozen at the end of 2024 and scored against 2025–26.
  - Batters: the model was closer (0.29–0.39 vs 0.18).
  - Bowlers: our method was closer (0.12–0.26 vs the model's −0.16 to 0.01).
  - Every 90% interval overlaps, so neither result is conclusive.
- **How its lists differ:** its batting list favours expensive top-order batters, and its bowling model found almost no repeatable signal.
- **Where they agree:** both methods put Suryakumar Yadav, Abhishek Sharma, Shreyas Iyer, Sunil Narine and Bhuvneshwar Kumar in their top 10.

---

## Repository layout

```
analysis/                     main method (Python standard library only)
  run_all.sh                  runs every step below, about 6 minutes
  step1_preprocess.py         cleaning, extras, match-state rebuild, era par
  step2_winprob.py            resource curve + PAVA, win-probability model, Leverage Index, WPA, run value
  step3_pressure.py           dead-ball detection (EM), pressure tiers, validation tests
  step4_ratings.py            opponent adjustment, empirical-Bayes ratings, Borda, SMAA, bootstrap
  step5_final.py              model-averaged final ranking
  step6_rr_fit.py             RR's pressure record, 2026 squad, player profiles
  step7_audit.py              data integrity, recount, robustness, time-split test
  step8_rr_backlist.py        the auction call for each player
  compare.py / evidence.py    sensitivity summaries, raw evidence
  make_report.py              full methodology report (HTML)
  make_summary.py             summary for judges (HTML)
  build_dashboard.py          dashboard (+ dashboard_template.html)
  serve_dashboard.py          serve the dashboard on http://localhost:8000
  out/                        results (FINAL_*.csv, rank_*.csv, *.json)
public_model/                 separate public-data model (cross-check only)
  run_public_model.sh, pm1_parse.py, pm2_link.py, pm3_model.py, out/pm_results.json
report/
  SupeRR_Judges_Summary.pdf   SupeRR_Pressure_Report.pdf   dashboard.html
  site/                       static site deployed to Vercel (index.html + both PDFs)
vercel.json                   tells Vercel to serve report/site
```

