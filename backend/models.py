from datetime import date, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Profile(Model):
    name: str = Field(default="", max_length=80)
    birthdate: date | None = None
    sex: Literal["male", "female", "unspecified"] = "unspecified"
    height_cm: float | None = Field(default=None, ge=80, le=250)
    timezone: str = "Europe/Prague"
    sleep_goal: float = Field(default=8, ge=4, le=12)
    calorie_goal: int = Field(default=2200, ge=800, le=8000)
    protein_goal: int = Field(default=120, ge=20, le=400)
    fiber_goal: int = Field(default=30, ge=10, le=80)
    carb_goal: int = Field(default=250, ge=0, le=1000)
    fat_goal: int = Field(default=75, ge=10, le=400)
    water_goal: int = Field(default=2500, ge=250, le=8000)
    steps_goal: int = Field(default=8000, ge=500, le=60000)
    theme: Literal["system", "light", "dark"] = "dark"
    ai_model: str = Field(default="", max_length=150, pattern=r"^[a-zA-Z0-9_/:.~-]*$")
    ai_consent: bool = False
    offline_cache: bool = False
    notify_enabled: bool = False
    morning_time: str = Field(default="08:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    evening_time: str = Field(default="21:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    water_reminders: bool = False
    workout_reminders: bool = False
    smoking: Literal["unknown", "never", "former", "current"] = "unknown"
    cigarettes_per_day: int | None = Field(default=None, ge=1, le=100)
    quit_year: int | None = Field(default=None, ge=1940, le=2100)

    @field_validator("timezone")
    @classmethod
    def timezone_exists(cls, v):
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError:
            raise ValueError("Unknown time zone")
        return v

    @field_validator("birthdate")
    @classmethod
    def birthdate_valid(cls, v):
        if v and not date(1900, 1, 1) <= v <= date.today():
            raise ValueError("Invalid date of birth")
        return v


class Meal(Model):
    name: str = Field(min_length=1, max_length=180)
    meal: Literal["breakfast", "lunch", "dinner", "snack"] = "snack"
    calories: float = Field(ge=0, le=10000)
    protein: float = Field(default=0, ge=0, le=1000)
    carbs: float = Field(default=0, ge=0, le=2000)
    fat: float = Field(default=0, ge=0, le=1000)
    fiber: float = Field(default=0, ge=0, le=300)
    grams: float = Field(default=100, gt=0, le=10000)
    notes: str = Field(default="", max_length=2000)


class ExerciseSet(Model):
    name: str = Field(min_length=1, max_length=100)
    reps: int = Field(default=10, ge=0, le=1000)
    weight: float = Field(default=0, ge=0, le=1000)
    done: bool = False
    exercise_id: str = Field(default="", max_length=100)
    seconds: float | None = Field(default=None, ge=0, le=86400)
    minutes: float | None = Field(default=None, ge=0, le=1440)
    speed_kmh: float | None = Field(default=None, ge=0, le=200)
    rpe: float | None = Field(default=None, ge=0, le=10)
    failure: bool = False
    phase: str = Field(default="", max_length=40)


class Workout(Model):
    name: str = Field(min_length=1, max_length=160)
    activity: str = Field(default="strength", min_length=1, max_length=80)
    minutes: float = Field(gt=0, le=1440)
    calories: float | None = Field(default=None, ge=0, le=15000)
    distance_km: float | None = Field(default=None, ge=0, le=1500)
    avg_hr: float | None = Field(default=None, ge=20, le=250)
    rpe: int | None = Field(default=None, ge=1, le=10)
    sets: list[ExerciseSet] = Field(default_factory=list, max_length=200)
    notes: str = Field(default="", max_length=4000)
    start: str = Field(default="", max_length=40)
    end: str = Field(default="", max_length=40)


class Plan(Model):
    name: str = Field(min_length=1, max_length=160)
    activity: str = Field(default="strength", max_length=80)
    minutes: float = Field(default=45, gt=0, le=1440)
    sets: list[ExerciseSet] = Field(default_factory=list, max_length=200)
    notes: str = Field(default="", max_length=4000)


class Vitals(Model):
    rhr: float | None = Field(default=None, ge=20, le=200)
    hrv: float | None = Field(default=None, gt=0, le=500)
    steps: int | None = Field(default=None, ge=0, le=200000)
    active_kcal: float | None = Field(default=None, ge=0, le=20000)
    weight: float | None = Field(default=None, ge=20, le=400)
    spo2: float | None = Field(default=None, ge=50, le=100)
    respiratory_rate: float | None = Field(default=None, ge=3, le=60)
    temperature: float | None = Field(default=None, ge=20, le=45)
    vo2max: float | None = Field(default=None, ge=5, le=100)
    systolic: int | None = Field(default=None, ge=60, le=260)
    diastolic: int | None = Field(default=None, ge=30, le=160)


class SleepStage(Model):
    stage: Literal["AWAKE", "LIGHT", "DEEP", "REM", "ASLEEP", "RESTLESS"]
    minutes: float = Field(ge=0, le=1440)


class Sleep(Model):
    minutes: float = Field(ge=0, le=1440)
    in_bed_minutes: float | None = Field(default=None, ge=0, le=1440)
    bedtime: str = Field(default="", max_length=40)
    wake_time: str = Field(default="", max_length=40)
    stages: list[SleepStage] = Field(default_factory=list, max_length=1000)
    quality: int | None = Field(default=None, ge=1, le=5)
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def sleep_consistency(self):
        if self.in_bed_minutes is not None and self.minutes > self.in_bed_minutes:
            raise ValueError("Sleep cannot be longer than time in bed")
        return self


class Journal(Model):
    mood: int = Field(default=3, ge=1, le=5)
    energy: int = Field(default=3, ge=1, le=5)
    stress: int = Field(default=3, ge=1, le=5)
    alcohol: bool = False
    caffeine: int = Field(default=0, ge=0, le=1500)
    meditation: int = Field(default=0, ge=0, le=300)
    illness: bool = False
    notes: str = Field(default="", max_length=5000)
    alcohol_drinks: int | None = Field(default=None, ge=0, le=60)
    habits: dict[str, bool | None] = Field(default_factory=dict, max_length=40)

    @field_validator("habits")
    @classmethod
    def habit_keys(cls, v):
        for key in v:
            if not key.replace("_", "").isalnum() or len(key) > 40:
                raise ValueError("Invalid habit name")
        return v


class Water(Model):
    ml: int = Field(gt=0, le=3000)


class NutritionDay(Model):
    complete: bool = False


class Lab(Model):
    albumin: float = Field(gt=0, le=100)
    creatinine: float = Field(gt=0, le=3000)
    glucose: float = Field(gt=0, le=60)
    crp: float = Field(gt=0, le=1000)
    lymphocytes: float = Field(ge=0, le=100)
    mcv: float = Field(gt=0, le=200)
    rdw: float = Field(gt=0, le=60)
    alp: float = Field(gt=0, le=3000)
    wbc: float = Field(gt=0, le=300)
    notes: str = Field(default="", max_length=3000)


class ClockReport(Model):
    method: Literal["Horvath", "Hannum", "DNAm PhenoAge", "GrimAge", "GrimAge2", "DunedinPACE", "KDM", "Other"]
    value: float = Field(gt=0, le=150)
    lab: str = Field(min_length=1, max_length=160)
    notes: str = Field(default="", max_length=3000)

    @model_validator(mode="after")
    def pace_range(self):
        if self.method == "DunedinPACE" and not 0.1 <= self.value <= 3:
            raise ValueError("DunedinPACE is a ratio, e.g. 0.9, not an age in years")
        return self


class Exercise(Model):
    name: str = Field(min_length=1, max_length=180)
    equipment: str = Field(default="", max_length=180)
    muscle: str = Field(default="", max_length=180)
    instructions: str = Field(default="", max_length=8000)


SCHEMAS = {"exercise": Exercise,"meal": Meal, "food": Meal, "workout": Workout, "plan": Plan, "vitals": Vitals,
           "sleep": Sleep, "journal": Journal, "water": Water, "lab": Lab, "clock": ClockReport,
           "nutrition_day": NutritionDay}


class Entry(Model):
    kind: str
    day: date
    data: dict
    id: str | None = Field(default=None, max_length=160, pattern=r"^[a-zA-Z0-9_:-]+$")
    source: Literal["manual", "google", "import"] = "manual"

    @model_validator(mode="after")
    def validate_data(self):
        if self.kind not in SCHEMAS:
            raise ValueError("Unknown entry type")
        self.data = SCHEMAS[self.kind].model_validate(self.data).model_dump(mode="json")
        # "Today" of the user may already be tomorrow on a UTC server (e.g. 00:30 in Prague),
        # so only reject days that are in the future everywhere on Earth (UTC+14).
        if self.day > datetime.now(timezone(timedelta(hours=14))).date():
            raise ValueError("An entry cannot be in the future")
        return self
