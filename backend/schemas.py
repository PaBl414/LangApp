"""
Schematy Pydantic — walidacja żądań i odpowiedzi.
"""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator
import re

PASSWORD_RE = re.compile(
    r"^(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{6,}$"
)


class APIRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(APIRequest):
    login: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    password_confirm: str = Field(min_length=6, max_length=128)
    fingerprint: str = Field(min_length=8, max_length=128)
    cookie_id: str = Field(min_length=8, max_length=128)

    @field_validator("login")
    @classmethod
    def login_safe(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}", v):
            raise ValueError("Login może zawierać tylko litery, cyfry, _ . -")
        return v

    @field_validator("password")
    @classmethod
    def password_strong(cls, v: str) -> str:
        if not PASSWORD_RE.match(v):
            raise ValueError(
                "Hasło musi mieć min. 6 znaków, w tym wielką literę, cyfrę i znak specjalny."
            )
        return v


class LoginRequest(APIRequest):
    login: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    fingerprint: str = Field(min_length=8, max_length=128)
    cookie_id: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    id: int
    login: str
    created_at: str


PositiveId = Annotated[int, Field(strict=True, gt=0)]
WordText = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=128)]


class AddLanguageRequest(APIRequest):
    language_id: PositiveId


class AddWordRequest(APIRequest):
    word: WordText
    translation_pl: WordText
    translation_alternatives: list[WordText] = Field(default_factory=list, max_length=10)
    word_alternatives: list[WordText] = Field(default_factory=list, max_length=10)
    # This remains a client-reported flag until dictionary verification moves server-side.
    is_valid: bool = Field(default=False, strict=True)


class StudyStartRequest(APIRequest):
    language_id: PositiveId
    mode: Literal["lang_to_pl", "pl_to_lang", "mix"]
    count: int = Field(default=10, strict=True, ge=1, le=50)
    request_id: UUID | None = None
    source: Literal["all", "due"] = "all"

    @model_validator(mode="after")
    def review_direction(self):
        if self.source == "due" and self.mode == "mix":
            raise ValueError("Wybierz jeden kierunek zaplanowanej powtórki.")
        return self


class StudyAnswerRequest(APIRequest):
    word_id: PositiveId
    given: str = Field(default="", max_length=128, strict=True)


class StudyAnswersRequest(APIRequest):
    answers: list[StudyAnswerRequest] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def unique_answers(self):
        ids = [answer.word_id for answer in self.answers]
        if len(ids) != len(set(ids)):
            raise ValueError("Każde słowo może mieć tylko jedną odpowiedź.")
        return self


class StudySubmitRequest(StudyAnswersRequest):
    session_id: PositiveId
    revision: int | None = Field(default=None, strict=True, ge=0)


class StudyDraftRequest(StudyAnswersRequest):
    revision: int = Field(strict=True, ge=0)
    current_index: int = Field(strict=True, ge=0, le=49)
