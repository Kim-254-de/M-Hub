"""What the adviser may know about the farmer's case. Never products or doses (Documentation §11)."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.utils import timezone

from apps.cases.models import Case
from apps.diagnosis import review
from apps.diagnosis.messages import safe_actions
from apps.diagnosis.models import FinalDiagnosis
from apps.followups.models import SprayRecord


class Stage:
    WAITING = "waiting"  # reported; a verified agrovet has not confirmed it yet
    CONFIRMED = "confirmed"  # diagnosis confirmed, no prescription yet
    PRESCRIBED = "prescribed"  # prescription card issued
    SPRAYED = "sprayed"  # farmer recorded spraying; follow-up running
    UNKNOWN = "unknown"  # agrovets could not agree


@dataclass(frozen=True)
class CaseContext:
    stage: str
    disease: str | None = None  # confirmed disease, or the AI's unconfirmed suggestion while waiting
    share_affected: str = ""  # few / some / most, from the Detect quick questions
    ward: str = ""
    days_since_spray: int | None = None
    last_check_in: str = ""  # spreading / fewer / stopped
    first_steps: list[str] = field(default_factory=list)  # reviewed, product-free steps (English)
    crop: str = "tomato"

    def describe(self) -> str:
        """Plain facts for the model, in English (the model answers in the farmer's language)."""
        lines = [f"Crop: {self.crop}."]
        if self.stage == Stage.WAITING:
            lines.append(
                "Diagnosis: NOT confirmed yet. A verified agrovet is reviewing the photos."
                + (f" The computer's first suggestion is {self.disease}." if self.disease else "")
            )
        elif self.stage == Stage.UNKNOWN:
            lines.append(
                "Diagnosis: the agrovets could not agree. The farmer was told to take a sample to a plant "
                "clinic or extension officer."
            )
        elif self.disease:
            lines.append(f"Diagnosis confirmed by a verified agrovet: {self.disease}.")
        if self.share_affected:
            lines.append(f"Share of plants affected when reported: {self.share_affected}.")
        if self.stage == Stage.PRESCRIBED:
            lines.append(
                "The agrovet has issued a prescription card with the product, amount and safety steps."
            )
        if self.stage == Stage.SPRAYED:
            lines.append(
                "The farmer sprayed the prescribed product and is reporting progress on days 2, 4 and 7."
            )
            if self.days_since_spray is not None:
                lines.append(f"Days since spraying: {self.days_since_spray}.")
            if self.last_check_in:
                lines.append(f"Latest report on new spots: {self.last_check_in}.")
        if self.ward:
            lines.append(f"Ward: {self.ward}.")
        if self.first_steps:
            lines.append("Reviewed first steps already given to the farmer:")
            lines.extend(f"- {step}" for step in self.first_steps)
        return "\n".join(lines)


def context_for_case(case: Case) -> CaseContext:
    """Build the context from a case in the database."""
    final = FinalDiagnosis.objects.filter(case=case).select_related("disease").first()
    record = SprayRecord.objects.filter(case=case).prefetch_related("check_ins").first()
    disease = final.disease if final else None
    disease_name = disease.name if disease else None
    if record is not None:
        stage = Stage.SPRAYED
    elif case.status == Case.Status.UNKNOWN:
        stage = Stage.UNKNOWN
    elif final is None:
        stage = Stage.WAITING
        provisional = review.provisional_result(case)
        if provisional is not None:
            disease = provisional["disease"]
            disease_name = disease.name if disease else provisional["name"]
    elif case.prescriptions.exists():
        stage = Stage.PRESCRIBED
    else:
        stage = Stage.CONFIRMED

    days_since_spray, last_check_in = None, ""
    if record is not None:
        days_since_spray = (timezone.now() - record.sprayed_at).days
        check_ins = list(record.check_ins.all())
        last_check_in = check_ins[-1].new_spots if check_ins else ""
    return CaseContext(
        stage=stage,
        disease=disease_name,
        share_affected=(case.symptom_answers or {}).get("share_affected", ""),
        ward=case.ward,
        days_since_spray=days_since_spray,
        last_check_in=last_check_in,
        first_steps=safe_actions(disease, "en"),
    )
