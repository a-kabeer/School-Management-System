"""ID cards for students and staff.

A card is assembled from records that already exist — the organization's
branding, the person's own row, their current class or designation — so
nothing here duplicates the database.

The QR code resolves to a verification page that shows only what is printed on
the card face. Scanning therefore proves a card is genuine without revealing
anything the card does not already display.
"""

import io
from dataclasses import dataclass, field

import qrcode
import qrcode.image.svg
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

#: Cards print at CR80, the bank-card size every badge holder fits.
CARD_WIDTH_MM = 85.6
CARD_HEIGHT_MM = 54.0

LANGUAGES = (("en", _("English")), ("ur", _("Urdu")), ("ar", _("Arabic")))
RTL_LANGUAGES = {"ur", "ar"}


@dataclass
class Branding:
    """What the madrasa puts on the card, taken from the organization."""

    name: str = ""
    subtitle: str = ""
    logo_url: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""


@dataclass
class Card:
    kind: str                      # "student" or "staff"
    person: object = None
    photo_url: str = ""
    identifier: str = ""
    id_label: str = ""
    title: str = ""
    full_name: str = ""
    rows: list = field(default_factory=list)   # [(label, value), ...]
    qr_svg: str = ""
    verify_url: str = ""
    valid: bool = True
    validity_label: str = ""
    scan_label: str = ""


def branding_for(organization, branch=None):
    """Branding from the organization, with the branch as the subtitle."""
    if organization is None:
        return Branding()

    parts = [organization.address, organization.city, organization.country]
    return Branding(
        name=organization.name,
        subtitle=(branch.name if branch is not None else organization.legal_name) or "",
        logo_url=organization.logo.url if organization.logo else "",
        address=", ".join(p for p in parts if p),
        phone=organization.phone or "",
        email=organization.email or "",
    )


def qr_svg(data, size_mm=22):
    """An inline SVG QR code.

    SVG rather than PNG: it stays sharp at any print resolution, needs no
    image pipeline, and survives the browser's print-to-PDF unchanged.
    """
    code = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=1,
    )
    code.add_data(data)
    code.make(fit=True)
    image = code.make_image(image_factory=qrcode.image.svg.SvgPathImage)

    buffer = io.BytesIO()
    image.save(buffer)
    svg = buffer.getvalue().decode("utf-8")

    # Strip the XML declaration so the markup can be inlined in a page, and
    # let CSS size it instead of the fixed millimetres qrcode writes.
    svg = svg.split("?>", 1)[-1].strip()
    svg = svg.replace('width="', 'data-width="', 1).replace('height="', 'data-height="', 1)
    return svg


def verify_url(request, kind, pk):
    path = reverse("core:verify", args=[kind, pk])
    return request.build_absolute_uri(path) if request else path


def student_card(student, request=None, language="en"):
    """Build a student's card from their own record."""
    enrollment = student.current_enrollment
    guardian_link = (
        student.guardian_links.filter(is_primary=True)
        .select_related("guardian")
        .first()
    )

    rows = [
        ("father_name", student.father_name or (
            guardian_link.guardian.full_name if guardian_link else ""
        )),
        ("class", enrollment.school_class.name if enrollment else ""),
        ("section", enrollment.section.name if enrollment and enrollment.section else ""),
        ("session", enrollment.academic_year.name if enrollment else ""),
        ("date_of_birth", student.date_of_birth.isoformat() if student.date_of_birth else ""),
    ]

    url = verify_url(request, "student", student.pk)
    return _card(
        "student", student, student.photo, student.admission_no, student.full_name,
        rows, url, student.status == student.Status.ACTIVE, language,
    )


def staff_card(staff, request=None, language="en"):
    """Build a staff member's card from their own record."""
    rows = [
        ("designation", staff.designation.name if staff.designation else
            staff.get_staff_type_display()),
        ("department", staff.department.name if staff.department else ""),
        ("joined", staff.joining_date.isoformat() if staff.joining_date else ""),
        ("phone", staff.phone or ""),
    ]
    url = verify_url(request, "staff", staff.pk)
    return _card(
        "staff", staff, staff.photo, staff.employee_no, staff.full_name,
        rows, url, staff.status == staff.Status.ACTIVE, language,
    )


def _card(kind, person, photo, identifier, full_name, rows, url, valid, language):
    """Resolve each row's label in the card's own language.

    Labels are translated here rather than in the template: a card's language
    is chosen per print run and is independent of the interface language.
    """
    labels = labels_for(language)
    return Card(
        kind=kind,
        person=person,
        photo_url=photo.url if photo else "",
        identifier=identifier,
        id_label=labels["student_id"] if kind == "student" else labels["staff_id"],
        title=labels["student_card"] if kind == "student" else labels["staff_card"],
        full_name=full_name,
        rows=[(labels.get(key, key), value) for key, value in rows if value],
        qr_svg=qr_svg(url),
        verify_url=url,
        valid=valid,
        validity_label=labels["valid"] if valid else labels["not_valid"],
        scan_label=labels["scan"],
    )


#: Field labels per language. Proper names are never translated — only the
#: labels beside them are.
LABELS = {
    "en": {
        "student_id": "Student ID",
        "staff_id": "Staff ID",
        "father_name": "Father's Name",
        "class": "Class",
        "section": "Section",
        "session": "Academic Session",
        "date_of_birth": "Date of Birth",
        "designation": "Designation",
        "department": "Department",
        "joined": "Joining Date",
        "phone": "Phone",
        "student_card": "Student Identity Card",
        "staff_card": "Staff Identity Card",
        "valid": "Valid",
        "not_valid": "Not valid",
        "scan": "Scan to verify",
    },
    "ur": {
        "student_id": "طالب علم نمبر",
        "staff_id": "ملازم نمبر",
        "father_name": "والد کا نام",
        "class": "جماعت",
        "section": "شعبہ",
        "session": "تعلیمی سال",
        "date_of_birth": "تاریخ پیدائش",
        "designation": "عہدہ",
        "department": "شعبہ جات",
        "joined": "تاریخ تقرری",
        "phone": "فون",
        "student_card": "طالب علم شناختی کارڈ",
        "staff_card": "ملازم شناختی کارڈ",
        "valid": "کارآمد",
        "not_valid": "غیر کارآمد",
        "scan": "تصدیق کے لیے اسکین کریں",
    },
    "ar": {
        "student_id": "رقم الطالب",
        "staff_id": "رقم الموظف",
        "father_name": "اسم الأب",
        "class": "الصف",
        "section": "الشعبة",
        "session": "العام الدراسي",
        "date_of_birth": "تاريخ الميلاد",
        "designation": "الوظيفة",
        "department": "القسم",
        "joined": "تاريخ التعيين",
        "phone": "الهاتف",
        "student_card": "بطاقة هوية الطالب",
        "staff_card": "بطاقة هوية الموظف",
        "valid": "سارية",
        "not_valid": "غير سارية",
        "scan": "امسح للتحقق",
    },
}


def labels_for(language):
    return LABELS.get(language, LABELS["en"])
