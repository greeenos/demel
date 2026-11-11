"""Clinical Phenotypic Age; Levine 2018 supplementary methods and Table S1."""
import math
from datetime import date

METHOD_URL = "https://www.aging-us.com/article/101414/supplementary/SD1/0/aging-v10i4-101414-supplementary-material-SD1.pdf"


def chronological_age(birthdate: str | None, on: str) -> float | None:
    if not birthdate:
        return None
    return (date.fromisoformat(on) - date.fromisoformat(birthdate)).days / 365.2425


def phenoage(lab: dict, age: float) -> dict:
    if not 20 <= age <= 120:
        raise ValueError("PhenoAge is meant for adults aged 20 and over")
    # CRP is entered in mg/L (the usual European lab unit); the paper requires ln(mg/dL).
    terms = {"albumin": -0.0336 * lab["albumin"], "creatinine": 0.0095 * lab["creatinine"],
             "glucose": 0.1953 * lab["glucose"], "crp": 0.0954 * math.log(lab["crp"] / 10),
             "lymphocytes": -0.0120 * lab["lymphocytes"], "mcv": 0.0268 * lab["mcv"],
             "rdw": 0.3306 * lab["rdw"], "alp": 0.0019 * lab["alp"], "wbc": 0.0554 * lab["wbc"]}
    xb = -19.9067 + 0.0804 * age + sum(terms.values())
    gamma = 0.0076927  # Unrounded parameter in Supplementary Methods, not rounded Table S1.
    log_hazard = xb + math.log(math.expm1(120 * gamma) / gamma)
    # Algebraically equivalent to the published mortality transform, avoiding 1-M cancellation.
    result = 141.50225 + (math.log(0.00553) + log_hazard) / 0.090165
    return {"method": "Clinical PhenoAge · Levine 2018", "version": "1.0", "age": round(result, 2),
            "chronological": round(age, 2), "difference": round(result - age, 2), "source": METHOD_URL,
            "terms": terms, "note": "A population estimate from blood; not DNAm PhenoAge and not a diagnosis. The difference is not age-residualised age acceleration."}


STUDIES = [
    {"method": "VO₂ max fitness equivalent", "year": 2022, "authors": "Kaminsky et al. · FRIEND", "status": "computed",
     "input": "VO₂ max, age and sex for the reference table", "url": "https://doi.org/10.1016/j.mayocp.2021.08.020",
     "note": "Interpolation between US fitness medians. The app converts reference norms; this is not a validated biological age. Sleep and food are never converted into years."},
    {"method": "Clinical PhenoAge", "year": 2018, "authors": "Levine et al.", "status": "computed",
     "input": "9 blood markers and age at the draw", "url": "https://doi.org/10.18632/aging.101414",
     "note": "Computed from the published coefficients. The result depends on units and on your health at the time of the draw."},
    {"method": "Horvath", "year": 2013, "authors": "Horvath", "status": "report",
     "input": "DNA methylation, 353 CpGs", "url": "https://doi.org/10.1186/gb-2013-14-10-r115",
     "note": "You can store a finished lab result. It cannot be computed from heart rate or sleep."},
    {"method": "Hannum", "year": 2013, "authors": "Hannum et al.", "status": "report",
     "input": "Blood DNA methylation", "url": "https://doi.org/10.1016/j.molcel.2012.10.016",
     "note": "The lab result is kept separately from other clocks."},
    {"method": "DNAm PhenoAge", "year": 2018, "authors": "Levine et al.", "status": "report",
     "input": "DNA methylation, 513 CpGs", "url": "https://doi.org/10.18632/aging.101414",
     "note": "A different method from clinical PhenoAge based on routine blood tests."},
    {"method": "GrimAge / GrimAge2", "year": 2022, "authors": "Lu et al.", "status": "report",
     "input": "DNA methylation and the lab's own calculation", "url": "https://doi.org/10.18632/aging.204434",
     "note": "Stores the provider's result. Without methylation data no substitute number is estimated."},
    {"method": "DunedinPACE", "year": 2022, "authors": "Belsky et al.", "status": "report",
     "input": "DNA methylation", "url": "https://doi.org/10.7554/eLife.73420",
     "note": "A pace of ageing, not an age: 1.0 means roughly one year of biological change per calendar year."},
    {"method": "Klemera–Doubal (KDM)", "year": 2006, "authors": "Klemera & Doubal", "status": "report",
     "input": "Biomarkers and reference-population parameters", "url": "https://doi.org/10.1016/j.mad.2005.10.004",
     "note": "Stores a finished result including its source. Without the reference model the calculation cannot be reproduced."},
]
