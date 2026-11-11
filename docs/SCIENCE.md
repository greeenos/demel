# Biological age and daily scores

## Everyday data: fitness, sleep and lifestyle

The main overview needs no blood tests. It keeps a fitness-equivalent age separate from sleep, movement, nutrition and recovery. Demel never pretends to compute a numeric biological age from arbitrarily weighted habits.

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

## Daily wellness heuristics

These are the app's own heuristics. They are not a validated biological age and not the algorithms of any commercial wearable:

- **Sleep:** how close you came to your own duration goal, at most 100 %. It does not diagnose sleep disorders.
- **Recovery:** HRV (RMSSD, log-transformed) and resting heart rate relative to the previous 30 days, plus last night's sleep. At least 14 paired days; today's value is not part of the baseline. A missing input means no score. Formula: `clamp(50 + 15×z(ln HRV) − 12×z(RHR) + 0.25×(sleep − 80), 0, 100)`. The minimum SD is 0.10 for ln HRV and 2 bpm for RHR, so a flat baseline cannot produce extreme results.
- **Strain:** the sum of minutes × the RPE you entered, mapped with `100 × (1 − exp(−load / 400))`. The 400 is the app's chosen scale, not a published clinical threshold. Activities without RPE show up in the history but are not part of this score.
- **Journal patterns:** the average length of the following night after a logged habit versus nights without it. At least 10 nights and 3 in each group. Descriptive only, without control for confounders and without proof of causation.

Calculations, conversions, rejection of invalid inputs and the handling of missing measurements are covered by the automated tests in `tests/`.
