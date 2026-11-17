"""Vocabulário e modelos centrais do GLOBAL OSINT."""

from dataclasses import dataclass
from enum import StrEnum


class Axis(StrEnum):
    ENERGY = "energy"
    CONFLICT = "conflict"
    ECONOMY = "economy"
    CLIMATE = "climate"
    CYBER = "cyber"
    HEALTH = "health"


class Language(StrEnum):
    EN = "en"
    PT = "pt"
    ES = "es"
    AR = "ar"
    RU = "ru"
    FR = "fr"
    ZH = "zh"


class SourceKind(StrEnum):
    INSTITUTIONAL = "institutional"
    MEDIA = "media"
    SOCIAL = "social"
    RESEARCH = "research"
    OTHER = "other"


class SourceStatus(StrEnum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class Source:
    id: int
    name: str
    url: str
    kind: SourceKind
    languages: tuple[str, ...]
    axes: tuple[str, ...]
    status: SourceStatus
    reliability_score: int | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class SourceInput:
    name: str
    url: str
    kind: SourceKind
    languages: tuple[str, ...]
    axes: tuple[str, ...]
    notes: str | None = None
