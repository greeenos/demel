# Biological age and daily scores

## Everyday data: fitness, sleep and lifestyle

The main overview needs no blood tests. Biological age (below) is built only from published hazard ratios; the fitness-equivalent age and the habit index stay separate descriptive views.

**Fitness age:** [Kaminsky et al., FRIEND 2022](https://doi.org/10.1016/j.mayocp.2021.08.020), Table 3, treadmill CPX, RER ≥ 1.0. The app compares the median of the available VO₂ max over the last 30 days with sex-specific reference medians for the decades 20–89. It interpolates linearly between the age-group midpoints; outside them it only returns a boundary label (≤29 or ≥80) and never extrapolates an exact age. The conversion is an interpretation chosen by the app; the paper itself does not validate this combined calculation as a biological-age clock. The norms come from the US and from directly measured CPET, so using a wearable estimate adds uncertainty.

**Habit index:** the plain average of the available areas: meeting your own sleep goal, recorded movement against the guideline of 150 minutes of moderate intensity per week ([AHA Life’s Essential 8](https://www.heart.org/en/healthy-living/healthy-lifestyle/lifes-essential-8)), and protein/fiber against your own goals, only on fully logged food days. It is shown when at least two areas are available, and a missing area is not counted as zero. It is not the official LE8 and not a biological age. The areas used and the number of days are always visible.

**Bedtime regularity** uses the circular standard deviation of minutes on a 24-hour cycle, so 23:55 and 00:05 are close together. **Sleep debt** is the sum of shortfalls against your own goal on observed nights, not a clinical assessment. **Correlations** need at least 14 varied paired days, do not adjust for confounders or multiple testing and do not prove cause. **Intake minus total burn** is only computed for completed past food days with a matching burn measurement.

**BMI** uses the height and weight you actually entered or synced. **Lean mass** combines weight and body-fat percentage measured at most three days apart; it is not a direct muscle measurement. All of these views help you read your data. They are not for diagnosis or treatment changes.

## Clinical PhenoAge: computed in the app

Levine et al. (2018), [paper](https://doi.org/10.18632/aging.101414), [Supplementary Methods and Table S1](https://www.aging-us.com/article/101414/supplementary/SD1/0/aging-v10i4-101414-supplementary-material-SD1.pdf). The implementation is in `backend/age.py`. It needs the age at the blood draw and 9 markers. The source population was adults aged 20 and over; the model expresses a population phenotypic/mortality equivalent, not the exact age of every organ.

Inputs: albumin g/L, creatinine µmol/L, glucose mmol/L, CRP mg/L, lymphocytes %, MCV fL, RDW %, ALP U/L, white blood cells 10⁹/L. The calculation converts CRP to mg/dL and uses the natural log. For γ it uses the more precise 0.0076927 from the Supplementary Methods. The transform is computed algebraically in log space to avoid losing precision when subtracting a very small probability from one. Missing values are not imputed and CRP = 0 is rejected. Age is taken from the date of birth to the date of the draw, not to today.

The difference PhenoAge − calendar age is not statistically residualised age acceleration. Acute illness and lab variability can affect the result. Do not mix inputs from different draws. The app does not interpret the values as a diagnosis or a treatment recommendation.

## Other methods: storing finished lab results

| Method | Primary source | Supported behaviour |
|---|---|---|
| Horvath | [2013, Genome Biology](https://doi.org/10.1186/gb-2013-14-10-r115) | Store the result and provider; computing it needs methylation data. |
| Hannum | [2013, Molecular Cell](https://doi.org/10.1016/j.molcel.2012.10.016) | A separate lab result. |
| DNAm PhenoAge | [Levine 2018](https://doi.org/10.18632/aging.101414) | A separate methylation method; not the clinical PhenoAge above. |
| GrimAge2 | [Lu 2022](https://doi.org/10.18632/aging.204434) | Store the result in years; never estimated from sensors. |
| DunedinPACE | [Belsky 2022, eLife](https://doi.org/10.7554/eLife.73420) | Store the pace of ageing as a ratio, not an age in years. |
| KDM | [Klemera & Doubal 2006](https://doi.org/10.1016/j.mad.2005.10.004) | Store a finished result with its reference model; arbitrary blood values alone are not enough. |

This is not a systematic review of every study. Methods are never averaged and their results are not interchangeable. Wearable metrics are no substitute for a methylation test.

## Daily rings, stress and training load (`backend/engine.py`)

The layout and inputs follow what Bevel publishes about its scores; Bevel does not publish formulas, so each formula below is built from the cited research. App-specific calibration constants are named as such. Minute heart rate and steps come from the Google Health API (`dataPoints:rollUp`, 60 s windows).

- **Heart-rate zones:** % of HRmax, Restorative <50, Z1 50–59, Z2 60–69, Z3 70–79, Z4 80–89, Z5 ≥90 %. HRmax = 220 − age ([Fox 1971](https://pubmed.ncbi.nlm.nih.gov/4929133/), Bevel's default) or the highest observed minute if higher.
- **Strain:** Edwards TRIMP over every waking minute (minutes × zone number), mapped with `100 × (1 − e^(−TRIMP/210))` for diminishing returns. 210 is the app's calibration. Without minute heart rate it falls back to session-RPE ([Foster 2001](https://pubmed.ncbi.nlm.nih.gov/11708692/)).
- **Target strain:** 14-day mean daily TRIMP × (0.2 + 0.4·R) … × (0.9 + 0.6·R), R = Recovery/100; grounded in the acute:chronic workload range ([Gabbett 2016](https://doi.org/10.1136/bjsports-2015-095788)) and HRV-guided training ([Kiviniemi 2007](https://doi.org/10.1007/s00421-007-0552-2)).
- **Recovery:** z-scores of last night's ln HRV ([Plews 2013](https://doi.org/10.1007/s40279-013-0071-8)) and mean sleeping heart rate ([Buchheit 2014](https://doi.org/10.3389/fphys.2014.00073)) against the previous 30 days, plus the Sleep score; elevated breathing rate ([Miller 2020](https://doi.org/10.1371/journal.pone.0243693)), a skin-temperature rise ([Smarr 2020](https://doi.org/10.1038/s41598-020-78355-6)) or SpO₂ < 94 % subtract. `c = 0.5·z(lnHRV) − 0.25·z(sleep HR) + 0.25·(Sleep−75)/15 − penalties`, Recovery = `100·Φ(0.25 + 1.1·c)`. Needs 7 baseline nights (calibrating until 14).
- **Sleep score:** time asleep vs tonight's need 35 % (need = goal + ¼ of the 7-night debt, [Kitamura 2016](https://doi.org/10.1038/srep35812)), deep sleep vs age/sex target 15 %, REM vs 20 % 10 % ([Ohayon 2004](https://doi.org/10.1093/sleep/27.7.1255)), efficiency ≥85 % 15 % and continuity (WASO ≤20 min) 10 % ([Ohayon 2017](https://doi.org/10.1016/j.sleh.2016.11.006)), heart-rate dip ≥10 % 15 % ([Ben-Dov 2007](https://doi.org/10.1001/archinte.167.19.2116)). Bands: <70 poor, 70–85 normal, >85 excellent.
- **Stress (1–100):** waking heart rate above your sleeping baseline relative to heart-rate reserve, `100·(HR − sleep HR)/(0.5·(HRmax − sleep HR))`, 5-minute smoothing; exercise is reported separately ([Myrtek 2004](https://doi.org/10.1027/0269-8803.18.2.102), [Verkuil 2016](https://doi.org/10.1007/s12160-016-9787-2)).
- **Energy:** an app model, not validated: 0.55·Recovery + 0.45·Sleep at waking, drained by time awake and stress.
- **Heart-rate recovery:** 2-minute drop after a zone-4+ effort; ≤22 bpm is associated with higher mortality ([Cole 1999](https://doi.org/10.1056/NEJM199910283411804), [Shetler 2001](https://doi.org/10.1016/S0735-1097(01)01519-4)).
- **Training load:** workout TRIMP, acute = 7-day and chronic = 42-day exponentially weighted averages; optimal acute load 0.8–1.3 × chronic ([Hulin 2016](https://doi.org/10.1136/bjsports-2015-094817)).
- **Detected activity:** ≥10 minutes at ≥60 % HRmax not covered by a logged workout; energy via [Keytel 2005](https://doi.org/10.1080/02640410470001730089).

## Biological age (`backend/bioage.py`)

Five categories as Bevel describes them: Sleep (time asleep, Sleep Regularity Index), Activity (steps, zones 2–3, zones 4–5, strength training), Fitness (device VO₂ max, resting heart rate, lean body mass), Lifestyle (fiber as the nutrition marker, alcohol, smoking) and Blood (Clinical PhenoAge). Factors use four-week averages and update every Monday.

Each factor maps your value onto a published dose–response curve (anchor points interpolated log-linearly) and compares it with a reference: [Wang 2021](https://pubmed.ncbi.nlm.nih.gov/33530979/) / [Cappuccio 2010](https://doi.org/10.1093/sleep/33.5.585) sleep, [Windred 2024](https://pubmed.ncbi.nlm.nih.gov/37995126/) regularity, [Paluch 2022](https://doi.org/10.1016/S2468-2667(21)00302-9) steps, [Arem 2015](https://jamanetwork.com/journals/jamainternalmedicine/fullarticle/2212267) moderate activity, [Stamatakis 2022](https://doi.org/10.1038/s41591-022-02100-x) vigorous activity, [Momma 2022](https://doi.org/10.1136/bjsports-2021-105061) strength, [Kodama 2009](https://doi.org/10.1001/jama.2009.681) with [FRIEND](https://doi.org/10.1016/j.mayocp.2021.08.020) medians for VO₂ max, [Zhang 2016](https://pubmed.ncbi.nlm.nih.gov/26542543/) with [Quer 2020](https://doi.org/10.1371/journal.pone.0227709) for resting heart rate, [Zhao 2023](https://doi.org/10.1001/jamanetworkopen.2023.6185) alcohol, [Jha 2013](https://doi.org/10.1056/NEJMsa1211128) smoking, [Reynolds 2019](https://doi.org/10.1016/S0140-6736(18)31809-9) fiber.

A hazard ratio becomes years through the Gompertz law (adult mortality rises ≈ 8.5 % per year, so years = ln(HR) ÷ 0.085; [Spiegelhalter 2016](https://doi.org/10.1136/bmj.i5395)). Habit effects are halved to allow for overlap between correlated habits, capped at ±4 years per factor and weighted by confidence (20+ days of data = full). Half of the PhenoAge difference counts, fading with the age of the test. The total is the sum of the categories. Confidence is the data coverage across all factors, with a blood test weighted as four. It is a population-level estimate for motivation, not a diagnosis.

Calculations, conversions, rejection of invalid inputs and the handling of missing measurements are covered by the automated tests in `tests/`.
