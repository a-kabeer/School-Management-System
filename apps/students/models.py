"""Students, guardians, enrollment and history."""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.academics.models import AcademicYear, SchoolClass, Section
from apps.core.constants import Gender
from apps.core.models import BranchOwnedModel, BranchOwnedSoftDeleteModel
from apps.core.validators import validate_phone


class Guardian(BranchOwnedModel):
    """A parent or guardian; optionally linked to a portal login."""

    class Relation(models.TextChoices):
        FATHER = "father", _("Father")
        MOTHER = "mother", _("Mother")
        BROTHER = "brother", _("Brother")
        SISTER = "sister", _("Sister")
        UNCLE = "uncle", _("Uncle")
        GRANDPARENT = "grandparent", _("Grandparent")
        OTHER = "other", _("Other")

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guardian_profile",
        verbose_name=_("portal account"),
    )
    full_name = models.CharField(_("full name"), max_length=200)
    relation = models.CharField(
        _("relation"),
        max_length=30,
        choices=Relation.choices,
        default=Relation.FATHER,
    )
    national_id = models.CharField(_("national ID"), max_length=50, blank=True)
    phone = models.CharField(
        _("phone"), max_length=40, blank=True, validators=[validate_phone]
    )
    alternate_phone = models.CharField(
        _("alternate phone"), max_length=40, blank=True, validators=[validate_phone]
    )
    email = models.EmailField(_("email"), blank=True)
    occupation = models.CharField(_("occupation"), max_length=150, blank=True)
    address = models.TextField(_("address"), blank=True)

    class Meta:
        verbose_name = _("guardian")
        verbose_name_plural = _("guardians")
        ordering = ["full_name"]
        indexes = [
            models.Index(fields=["branch", "full_name"]),
            models.Index(fields=["branch", "phone"]),
        ]

    def __str__(self):
        return self.full_name


class Student(BranchOwnedSoftDeleteModel):
    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        INACTIVE = "inactive", _("Inactive")
        WITHDRAWN = "withdrawn", _("Withdrawn")
        GRADUATED = "graduated", _("Graduated")
        TRANSFERRED = "transferred", _("Transferred")
        EXPELLED = "expelled", _("Expelled")

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_profile",
        verbose_name=_("login account"),
    )
    admission_no = models.CharField(_("admission number"), max_length=100)
    full_name = models.CharField(_("full name"), max_length=200)
    father_name = models.CharField(_("father name"), max_length=200, blank=True)
    gender = models.CharField(
        _("gender"), max_length=20, choices=Gender.choices, blank=True
    )
    date_of_birth = models.DateField(_("date of birth"), null=True, blank=True)
    place_of_birth = models.CharField(_("place of birth"), max_length=150, blank=True)
    nationality = models.CharField(_("nationality"), max_length=100, blank=True)
    national_id = models.CharField(_("national ID"), max_length=50, blank=True)
    photo = models.ImageField(
        _("photo"), upload_to="students/photos/", blank=True, null=True
    )
    phone = models.CharField(
        _("phone"), max_length=40, blank=True, validators=[validate_phone]
    )
    email = models.EmailField(_("email"), blank=True)
    address = models.TextField(_("address"), blank=True)
    city = models.CharField(_("city"), max_length=120, blank=True)
    previous_institution = models.CharField(
        _("previous institution"), max_length=255, blank=True
    )
    admission_date = models.DateField(_("admission date"), null=True, blank=True)
    is_boarder = models.BooleanField(_("boarder"), default=False)
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        verbose_name = _("student")
        verbose_name_plural = _("students")
        ordering = ["full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "admission_no"], name="uq_student_admission_no"
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "branch", "status"]),
            models.Index(fields=["branch", "full_name"]),
            models.Index(fields=["branch", "admission_no"]),
            models.Index(fields=["branch", "created_at"]),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.admission_no})"

    @property
    def current_enrollment(self):
        """The live enrollment, reusing a prefetch when the caller set one up.

        Filtering a prefetched related manager issues a fresh query, so a list
        of students would cost one query per row. Scanning the cached rows
        instead keeps a table of students to a single enrollment query.
        """
        cache = getattr(self, "_prefetched_objects_cache", None)
        if cache and "enrollments" in cache:
            for enrollment in cache["enrollments"]:
                if enrollment.is_current:
                    return enrollment
            return None
        return (
            self.enrollments.filter(is_current=True)
            .select_related("school_class", "section", "academic_year")
            .first()
        )

    @property
    def current_class_display(self):
        enrollment = self.current_enrollment
        if enrollment is None:
            return "—"
        if enrollment.section_id:
            return f"{enrollment.school_class.name} / {enrollment.section.name}"
        return enrollment.school_class.name


class StudentProfile(BranchOwnedModel):
    """Extended student detail kept out of the hot list queries."""

    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name=_("student"),
    )
    blood_group = models.CharField(_("blood group"), max_length=10, blank=True)
    medical_conditions = models.TextField(_("medical conditions"), blank=True)
    allergies = models.TextField(_("allergies"), blank=True)
    emergency_contact_name = models.CharField(
        _("emergency contact"), max_length=150, blank=True
    )
    emergency_contact_phone = models.CharField(
        _("emergency phone"), max_length=40, blank=True, validators=[validate_phone]
    )
    transport_required = models.BooleanField(_("transport required"), default=False)
    hostel_room = models.CharField(_("hostel room"), max_length=50, blank=True)
    remarks = models.TextField(_("remarks"), blank=True)

    class Meta:
        verbose_name = _("student profile")
        verbose_name_plural = _("student profiles")

    def __str__(self):
        return f"{self.student} — {_('profile')}"


class StudentGuardian(BranchOwnedModel):
    """Links a student to a guardian, marking who to contact first."""

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="guardian_links",
        verbose_name=_("student"),
    )
    guardian = models.ForeignKey(
        Guardian,
        on_delete=models.CASCADE,
        related_name="student_links",
        verbose_name=_("guardian"),
    )
    relation = models.CharField(_("relation"), max_length=50, blank=True)
    is_primary = models.BooleanField(_("primary contact"), default=False)
    can_view_portal = models.BooleanField(_("portal access"), default=True)
    can_collect_student = models.BooleanField(_("authorised for pickup"), default=True)

    class Meta:
        verbose_name = _("student guardian")
        verbose_name_plural = _("student guardians")
        constraints = [
            models.UniqueConstraint(
                fields=["student", "guardian"], name="uq_student_guardian"
            ),
            models.UniqueConstraint(
                fields=["student"],
                condition=models.Q(is_primary=True),
                name="uq_student_primary_guardian",
            ),
        ]
        indexes = [
            models.Index(fields=["guardian", "can_view_portal"]),
            models.Index(fields=["student", "is_primary"]),
        ]

    def __str__(self):
        return f"{self.guardian} → {self.student}"


class StudentDocument(BranchOwnedModel):
    class DocumentType(models.TextChoices):
        BIRTH_CERTIFICATE = "birth_certificate", _("Birth Certificate")
        ID_CARD = "id_card", _("ID Card")
        TRANSFER_CERTIFICATE = "transfer_certificate", _("Transfer Certificate")
        RESULT_CARD = "result_card", _("Result Card")
        PHOTO = "photo", _("Photograph")
        OTHER = "other", _("Other")

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name=_("student"),
    )
    document_type = models.CharField(
        _("document type"),
        max_length=40,
        choices=DocumentType.choices,
        default=DocumentType.OTHER,
    )
    title = models.CharField(_("title"), max_length=200)
    file = models.FileField(_("file"), upload_to="students/documents/")
    issued_on = models.DateField(_("issued on"), null=True, blank=True)
    notes = models.CharField(_("notes"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("student document")
        verbose_name_plural = _("student documents")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["student", "document_type"])]

    def __str__(self):
        return self.title


class StudentEnrollment(BranchOwnedModel):
    """A student's place in a class/section for one academic year."""

    student = models.ForeignKey(
        Student,
        on_delete=models.PROTECT,
        related_name="enrollments",
        verbose_name=_("student"),
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="enrollments",
        verbose_name=_("academic year"),
    )
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.PROTECT,
        related_name="enrollments",
        verbose_name=_("class"),
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="enrollments",
        verbose_name=_("section"),
    )
    roll_number = models.CharField(_("roll number"), max_length=50, blank=True)
    start_date = models.DateField(_("start date"))
    end_date = models.DateField(_("end date"), null=True, blank=True)
    is_current = models.BooleanField(_("current"), default=True)

    class Meta:
        verbose_name = _("enrollment")
        verbose_name_plural = _("enrollments")
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "academic_year"], name="uq_student_year_enrollment"
            ),
            models.UniqueConstraint(
                fields=["student"],
                condition=models.Q(is_current=True),
                name="uq_student_single_current_enrollment",
            ),
        ]
        indexes = [
            models.Index(fields=["branch", "academic_year", "school_class", "section"]),
            models.Index(fields=["student", "is_current"]),
            models.Index(fields=["branch", "is_current"]),
        ]

    def __str__(self):
        return f"{self.student} — {self.school_class}"

    def clean(self):
        super().clean()
        if (
            self.section_id
            and self.school_class_id
            and self.section.school_class_id != self.school_class_id
        ):
            raise ValidationError(
                {"section": _("That section belongs to a different class.")}
            )


class StudentClassHistory(BranchOwnedModel):
    """Append-only record of class/section movements."""

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="class_history",
        verbose_name=_("student"),
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, verbose_name=_("academic year")
    )
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.PROTECT, verbose_name=_("class")
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("section"),
    )
    moved_on = models.DateField(_("moved on"))
    reason = models.CharField(_("reason"), max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_class_moves",
        verbose_name=_("recorded by"),
    )

    class Meta:
        verbose_name = _("class history entry")
        verbose_name_plural = _("class history")
        ordering = ["-moved_on", "-created_at"]
        indexes = [models.Index(fields=["student", "moved_on"])]

    def __str__(self):
        return f"{self.student} → {self.school_class}"


class StudentStatusHistory(BranchOwnedModel):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="status_history",
        verbose_name=_("student"),
    )
    previous_status = models.CharField(_("previous status"), max_length=20, blank=True)
    new_status = models.CharField(_("new status"), max_length=20)
    effective_date = models.DateField(_("effective date"))
    reason = models.CharField(_("reason"), max_length=255, blank=True)
    changed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_status_changes",
        verbose_name=_("changed by"),
    )

    class Meta:
        verbose_name = _("status change")
        verbose_name_plural = _("status history")
        ordering = ["-effective_date", "-created_at"]
        indexes = [models.Index(fields=["student", "effective_date"])]

    def __str__(self):
        return f"{self.student} → {self.new_status}"
