"""Staff: teachers and administrative employees."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.constants import Gender
from apps.core.models import BranchOwnedModel, BranchOwnedSoftDeleteModel, money_field
from apps.core.validators import validate_phone


class StaffDepartment(BranchOwnedModel):
    name = models.CharField(_("name"), max_length=150)
    description = models.CharField(_("description"), max_length=255, blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("department")
        verbose_name_plural = _("departments")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "name"], name="uq_staff_department_name"
            )
        ]

    def __str__(self):
        return self.name


class StaffDesignation(BranchOwnedModel):
    name = models.CharField(_("name"), max_length=150)
    department = models.ForeignKey(
        StaffDepartment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="designations",
        verbose_name=_("department"),
    )
    is_teaching = models.BooleanField(_("teaching role"), default=False)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("designation")
        verbose_name_plural = _("designations")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "name"], name="uq_staff_designation_name"
            )
        ]

    def __str__(self):
        return self.name


class Staff(BranchOwnedSoftDeleteModel):
    class StaffType(models.TextChoices):
        TEACHER = "teacher", _("Teacher")
        ADMINISTRATIVE = "administrative", _("Administrative")
        SUPPORT = "support", _("Support")

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        ON_LEAVE = "on_leave", _("On Leave")
        SUSPENDED = "suspended", _("Suspended")
        RESIGNED = "resigned", _("Resigned")
        TERMINATED = "terminated", _("Terminated")

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_profile",
        verbose_name=_("login account"),
    )
    employee_no = models.CharField(_("employee number"), max_length=100)
    full_name = models.CharField(_("full name"), max_length=200)
    father_name = models.CharField(_("father name"), max_length=200, blank=True)
    staff_type = models.CharField(
        _("staff type"),
        max_length=20,
        choices=StaffType.choices,
        default=StaffType.TEACHER,
    )
    department = models.ForeignKey(
        StaffDepartment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff",
        verbose_name=_("department"),
    )
    designation = models.ForeignKey(
        StaffDesignation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff",
        verbose_name=_("designation"),
    )
    gender = models.CharField(
        _("gender"), max_length=20, choices=Gender.choices, blank=True
    )
    date_of_birth = models.DateField(_("date of birth"), null=True, blank=True)
    national_id = models.CharField(_("national ID"), max_length=50, blank=True)
    phone = models.CharField(
        _("phone"), max_length=40, blank=True, validators=[validate_phone]
    )
    email = models.EmailField(_("email"), blank=True)
    address = models.TextField(_("address"), blank=True)
    qualification = models.CharField(_("qualification"), max_length=255, blank=True)
    photo = models.ImageField(
        _("photo"), upload_to="staff/photos/", blank=True, null=True
    )
    joining_date = models.DateField(_("joining date"), null=True, blank=True)
    leaving_date = models.DateField(_("leaving date"), null=True, blank=True)
    basic_salary = money_field(_("basic salary"), default=0)
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.ACTIVE
    )

    class Meta:
        verbose_name = _("staff member")
        verbose_name_plural = _("staff")
        ordering = ["full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "employee_no"], name="uq_staff_employee_no"
            ),
            models.CheckConstraint(
                condition=models.Q(basic_salary__gte=0), name="ck_staff_salary_positive"
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "branch", "status"]),
            models.Index(fields=["branch", "staff_type"]),
            models.Index(fields=["branch", "full_name"]),
        ]

    def __str__(self):
        return self.full_name

    @property
    def is_teacher(self):
        return self.staff_type == self.StaffType.TEACHER


class StaffProfile(BranchOwnedModel):
    """Extended, less frequently read staff details."""

    staff = models.OneToOneField(
        Staff, on_delete=models.CASCADE, related_name="profile", verbose_name=_("staff")
    )
    blood_group = models.CharField(_("blood group"), max_length=10, blank=True)
    marital_status = models.CharField(_("marital status"), max_length=30, blank=True)
    emergency_contact_name = models.CharField(
        _("emergency contact"), max_length=150, blank=True
    )
    emergency_contact_phone = models.CharField(
        _("emergency phone"), max_length=40, blank=True, validators=[validate_phone]
    )
    bank_name = models.CharField(_("bank name"), max_length=150, blank=True)
    bank_account_number = models.CharField(
        _("bank account number"), max_length=60, blank=True
    )
    experience_years = models.PositiveSmallIntegerField(
        _("years of experience"), default=0
    )
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        verbose_name = _("staff profile")
        verbose_name_plural = _("staff profiles")

    def __str__(self):
        return f"{self.staff} — {_('profile')}"


class StaffDocument(BranchOwnedModel):
    class DocumentType(models.TextChoices):
        CONTRACT = "contract", _("Contract")
        DEGREE = "degree", _("Degree")
        ID_CARD = "id_card", _("ID Card")
        CERTIFICATE = "certificate", _("Certificate")
        OTHER = "other", _("Other")

    staff = models.ForeignKey(
        Staff, on_delete=models.CASCADE, related_name="documents", verbose_name=_("staff")
    )
    document_type = models.CharField(
        _("document type"),
        max_length=30,
        choices=DocumentType.choices,
        default=DocumentType.OTHER,
    )
    title = models.CharField(_("title"), max_length=200)
    file = models.FileField(_("file"), upload_to="staff/documents/")
    issued_on = models.DateField(_("issued on"), null=True, blank=True)
    expires_on = models.DateField(_("expires on"), null=True, blank=True)
    notes = models.CharField(_("notes"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("staff document")
        verbose_name_plural = _("staff documents")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["staff", "document_type"])]

    def __str__(self):
        return self.title


class StaffAssignment(BranchOwnedModel):
    """A non-teaching duty or posting, e.g. hostel warden or exam controller."""

    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name=_("staff"),
    )
    title = models.CharField(_("title"), max_length=200)
    department = models.ForeignKey(
        StaffDepartment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignments",
        verbose_name=_("department"),
    )
    start_date = models.DateField(_("start date"))
    end_date = models.DateField(_("end date"), null=True, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    notes = models.CharField(_("notes"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("staff assignment")
        verbose_name_plural = _("staff assignments")
        ordering = ["-start_date"]
        indexes = [models.Index(fields=["staff", "is_active"])]

    def __str__(self):
        return f"{self.staff} — {self.title}"


class StaffStatusHistory(BranchOwnedModel):
    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name="status_history",
        verbose_name=_("staff"),
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
        related_name="staff_status_changes",
        verbose_name=_("changed by"),
    )

    class Meta:
        verbose_name = _("staff status change")
        verbose_name_plural = _("staff status history")
        ordering = ["-effective_date", "-created_at"]
        indexes = [models.Index(fields=["staff", "effective_date"])]

    def __str__(self):
        return f"{self.staff} → {self.new_status}"
