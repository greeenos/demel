"""Sip reminder schedule, using the same water log as the rest of Demel."""
from datetime import datetime
from zoneinfo import ZoneInfo
from pydantic import Field, model_validator
from . import db
from .models import Model


class Settings(Model):
    enabled: bool = True
    sip_ml: int = Field(default=50, ge=1, le=1000)
    start: int = Field(default=540, ge=0, le=1439)
    end: int = Field(default=1260, ge=1, le=1440)
    days: list[int] = Field(default_factory=lambda: list(range(7)), max_length=7)

    @model_validator(mode="after")
    def valid(self):
        if self.end <= self.start or any(d not in range(7) for d in self.days) or len(set(self.days)) != len(self.days):
            raise ValueError("Check the time window and reminder days")
        return self


def status(profile, now=None):
    local = now or datetime.now(ZoneInfo(profile.timezone))
    day, timestamp = local.date().isoformat(), local.timestamp()
    settings = Settings.model_validate(db.get("hydration_settings", {}))
    total = sum(e["data"]["ml"] for e in db.entries(day, day) if e["kind"] == "water")
    schedule = db.get("hydration_schedule", {})
    minute = local.hour * 60 + local.minute
    active = settings.enabled and (local.weekday()+1)%7 in settings.days and settings.start <= minute < settings.end and total < profile.water_goal
    if not active:
        return {"settings": settings.model_dump(), "total": total, "remaining": max(0, profile.water_goal-total), "due": False, "next_at": None}
    if schedule.get("day") != day or not schedule.get("next_at"):
        schedule = {"day": day, "next_at": timestamp + delay(settings, profile.water_goal-total, minute)}
        db.put("hydration_schedule", schedule)
    return {"settings": settings.model_dump(), "total": total, "remaining": max(0, profile.water_goal-total), "due": timestamp >= schedule["next_at"], "next_at": schedule["next_at"]}


def delay(settings, remaining, minute):
    import random
    sips = max(1, (remaining+settings.sip_ml-1)//settings.sip_ml)
    return max(300, (settings.end-minute)*60/(sips+1) * random.uniform(.5, 1.5))


def postpone(profile, action, now=None):
    local = now or datetime.now(ZoneInfo(profile.timezone))
    state = status(profile, local)
    seconds = 300 if action == "snooze" else delay(Settings.model_validate(state["settings"]), state["remaining"], local.hour*60+local.minute)
    db.put("hydration_schedule", {"day": local.date().isoformat(), "next_at": local.timestamp()+seconds})
    return status(profile, local)
