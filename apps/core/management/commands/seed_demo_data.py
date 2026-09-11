"""Generate a large, realistic demo dataset across every module.

This is fixture data, not real data: it is created against a demo
organization and every branch it touches is a demo branch. It exists so the
dashboards, reports and ledgers have something to show, and so the system can
be exercised at a realistic size.

High-volume rows are written with ``bulk_create``. Money is the exception -
fee payments, refunds and payroll go through the real services, so the
double-entry ledger ends up balanced rather than merely populated.
"""

import datetime as dt
import random
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.academics.models import (
    AcademicYear,
    ClassSubject,
    SchoolClass,
    Section,
    Subject,
    TeacherAssignment,
    Term,
    Timetable,
)
from apps.attendance.models import AttendanceSession, StaffAttendance, StudentAttendance
from apps.core.constants import AttendanceStatus, Gender
from apps.exams.models import (
    Exam,
    ExamSchedule,
    ExamSubject,
    ExamTerm,
    Grade,
    Mark,
    StudentExam,
)
from apps.fees.models import (
    FeeDiscount,
    FeeInvoice,
    FeeInvoiceItem,
    FeeStructure,
    FeeType,
    StudentFee,
)
from apps.finance.models import Journal, PaymentMethod
from apps.finance.seeds import seed_chart_of_accounts, seed_fiscal_period
from apps.finance.services import (
    CODE_RECEIVABLE,
    CODE_TUITION_INCOME,
    get_account,
    post_journal_entry,
)
from apps.hifz.models import (
    DailyProgress,
    HifzAssessment,
    HifzStudentProfile,
    HifzTeacherAssignment,
    LessonType,
    Quality,
    Revision,
)
from apps.notifications.models import (
    Channel,
    Notification,
    NotificationPreference,
    NotificationRecipient,
    NotificationTemplate,
)
from apps.parents.models import ParentPortalProfile, ParentRequest
from apps.payroll.models import (
    EmployeeSalary,
    PayrollPeriod,
    SalaryComponent,
    SalaryStructure,
    SalaryStructureLine,
)
from apps.reports.models import ReportExport, SavedReport
from apps.staff.models import (
    Staff,
    StaffAssignment,
    StaffDepartment,
    StaffDesignation,
    StaffProfile,
    StaffStatusHistory,
)
from apps.students.models import (
    Guardian,
    Student,
    StudentClassHistory,
    StudentDocument,
    StudentEnrollment,
    StudentGuardian,
    StudentProfile,
    StudentStatusHistory,
)
from apps.tenants.models import Branch, Organization

FIRST_NAMES_M = [
    "Ahmed", "Ali", "Usman", "Bilal", "Hamza", "Yusuf", "Ibrahim", "Zain",
    "Hassan", "Hussain", "Umar", "Talha", "Saad", "Faisal", "Kamran", "Noman",
    "Adnan", "Rizwan", "Shahid", "Tariq", "Imran", "Junaid", "Waqar", "Asad",
    "Danish", "Furqan", "Haris", "Irfan", "Kashif", "Luqman", "Mudassir",
    "Nadeem", "Owais", "Qasim", "Rehan", "Sohail", "Uzair", "Waleed", "Yasir",
]
FIRST_NAMES_F = [
    "Ayesha", "Fatima", "Maryam", "Khadija", "Zainab", "Hafsa", "Amina",
    "Sana", "Hira", "Iqra", "Rabia", "Sadia", "Noor", "Laiba", "Areeba",
    "Mehwish", "Sumaiya", "Zoya", "Anum", "Bushra", "Farah", "Ghazala",
    "Huma", "Javeria", "Kiran", "Mahnoor", "Nimra", "Rimsha", "Saba", "Tooba",
]
LAST_NAMES = [
    "Khan", "Ahmed", "Ali", "Sheikh", "Malik", "Chaudhry", "Butt", "Qureshi",
    "Siddiqui", "Ansari", "Farooqi", "Hashmi", "Abbasi", "Awan", "Baig",
    "Durrani", "Gilani", "Jafri", "Kazmi", "Lodhi", "Mirza", "Naqvi", "Raza",
    "Sethi", "Tariq", "Usmani", "Warraich", "Zaidi",
]
CITIES = ["Lahore", "Karachi", "Islamabad", "Rawalpindi", "Faisalabad", "Multan", "Peshawar"]
SUBJECT_NAMES = [
    ("Quran", Subject.Kind.RELIGIOUS), ("Hadith", Subject.Kind.RELIGIOUS),
    ("Fiqh", Subject.Kind.RELIGIOUS), ("Arabic", Subject.Kind.ACADEMIC),
    ("Urdu", Subject.Kind.ACADEMIC), ("English", Subject.Kind.ACADEMIC),
    ("Mathematics", Subject.Kind.ACADEMIC), ("Science", Subject.Kind.ACADEMIC),
    ("Social Studies", Subject.Kind.ACADEMIC), ("Physical Education", Subject.Kind.ACTIVITY),
]
DEPARTMENTS = ["Religious Studies", "Sciences", "Languages", "Administration", "Support Services"]
TEACHING_DESIGNATIONS = ["Senior Teacher", "Teacher", "Assistant Teacher", "Hifz Instructor"]
SUPPORT_DESIGNATIONS = ["Accountant", "Clerk", "Librarian", "Security Guard", "Caretaker"]
FEE_TYPES = [
    ("Monthly Tuition", FeeType.Frequency.MONTHLY, Decimal("4500.00")),
    ("Admission Fee", FeeType.Frequency.ONE_TIME, Decimal("10000.00")),
    ("Examination Fee", FeeType.Frequency.TERM, Decimal("1500.00")),
    ("Hostel Fee", FeeType.Frequency.MONTHLY, Decimal("6000.00")),
    ("Transport Fee", FeeType.Frequency.MONTHLY, Decimal("2000.00")),
]


class Command(BaseCommand):
    help = "Generate a large demo dataset across every module (development use only)."

    def add_arguments(self, parser):
        parser.add_argument("--students", type=int, default=1000,
                            help="Students per branch (default 1000).")
        parser.add_argument("--staff", type=int, default=45,
                            help="Staff per branch (default 45).")
        parser.add_argument("--classes", type=int, default=10,
                            help="Classes per branch (default 10).")
        parser.add_argument("--attendance-days", type=int, default=10,
                            help="School days of attendance to generate (default 10).")
        parser.add_argument("--pay-ratio", type=float, default=0.6,
                            help="Share of invoices that get a payment (default 0.6).")
        parser.add_argument("--seed", type=int, default=2026,
                            help="Random seed, so runs are reproducible.")
        parser.add_argument("--flush", action="store_true",
                            help="Delete existing demo business data first.")
        parser.add_argument("--adjustments-only", action="store_true",
                            help="Only add waivers, refunds and staff documents.")

    def handle(self, *args, **options):
        from django.conf import settings

        if not settings.DEBUG:
            raise CommandError(
                "Refusing to generate demo data with DEBUG=False. This command "
                "invents thousands of fictional people."
            )

        self.rng = random.Random(options["seed"])
        self.opts = options
        self.today = timezone.localdate()
        self.counts = {}

        organization = Organization.objects.filter(slug="demo-academy").first()
        if organization is None:
            raise CommandError(
                'No "Demo Academy" organization. Run:\n'
                "  python manage.py setup_database --demo"
            )

        if options["flush"]:
            self._flush(organization)

        branches = self._ensure_branches(organization)
        for branch in branches:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n== {branch.name} =="))
            if options["adjustments_only"]:
                self._staff_documents(branch)
                self._fee_adjustments(branch)
                continue
            self._seed_branch(branch)

        if options["adjustments_only"]:
            self._report()
            return

        self._grant_multi_branch_access(organization, branches)
        self._seed_organization_level(organization, branches)
        self._report()

    def _grant_multi_branch_access(self, organization, branches):
        """Let the head-office logins actually see both campuses.

        Without this the admin sees only the branch they were created in -
        correct isolation, but it makes a two-branch demo look empty.
        """
        from apps.accounts.models import User
        from apps.accounts.rbac import grant_branch_access

        for username in ("admin", "finance"):
            user = User.objects.filter(
                organization=organization, username=username
            ).first()
            if user is None:
                continue
            for branch in branches:
                grant_branch_access(
                    user, branch, is_default=(branch.code == "MAIN")
                )
            self._bump("branch access grants", len(branches))

    # ------------------------------------------------------------------
    # structure
    # ------------------------------------------------------------------
    def _ensure_branches(self, organization):
        wanted = [("Main Campus", "MAIN"), ("City Campus", "CITY")]
        branches = []
        for name, code in wanted:
            branch, created = Branch.objects.get_or_create(
                organization=organization,
                code=code,
                defaults={
                    "name": name,
                    "city": self.rng.choice(CITIES),
                    "is_central_administration": code == "MAIN",
                    "opened_on": dt.date(self.today.year - 3, 4, 1),
                },
            )
            if created:
                self._bump("branches")
            seed_chart_of_accounts(branch)
            seed_fiscal_period(
                branch,
                dt.date(self.today.year, 1, 1),
                dt.date(self.today.year, 12, 31),
                name=f"FY {self.today.year} {code}",
            )
            branches.append(branch)
        return branches

    def _seed_branch(self, branch):
        year, terms = self._academics(branch)
        departments, designations = self._departments(branch)
        staff = self._staff(branch, departments, designations)
        classes, sections = self._classes(branch)
        subjects, class_subjects = self._subjects(branch, year, classes)
        self._teaching(branch, year, staff, class_subjects, sections)
        students, enrollments = self._students(branch, year, classes, sections)
        self._guardians(branch, students)
        self._attendance(branch, year, sections, enrollments, staff)
        self._hifz(branch, students, staff)
        self._fees(branch, year, terms, classes, students, enrollments)
        self._staff_documents(branch)
        self._fee_adjustments(branch)
        self._payroll(branch, staff)
        self._exams(branch, year, terms, classes, sections, class_subjects, enrollments, staff)
        self._expenses(branch)

    def _academics(self, branch):
        # Reuse the branch's current year if it has one. Creating a second year
        # here would leave the seeded invoices and exams hanging off a year
        # that nothing else treats as current, and the dashboard would then
        # report zero billed against real collections.
        year = AcademicYear.objects.filter(branch=branch, is_current=True).first()
        if year is None:
            year, _created = AcademicYear.objects.get_or_create(
                branch=branch,
                name=f"{self.today.year}-{self.today.year + 1}",
                defaults={
                    "organization": branch.organization,
                    "start_date": dt.date(self.today.year, 1, 1),
                    "end_date": dt.date(self.today.year, 12, 31),
                    "is_current": True,
                },
            )
        terms = []
        spans = [("First Term", 1, 4), ("Second Term", 5, 8), ("Third Term", 9, 12)]
        for index, (name, start_month, end_month) in enumerate(spans, start=1):
            term, created = Term.objects.get_or_create(
                academic_year=year,
                name=name,
                defaults={
                    "organization": branch.organization,
                    "branch": branch,
                    "sequence": index,
                    "start_date": dt.date(self.today.year, start_month, 1),
                    "end_date": dt.date(self.today.year, end_month, 28),
                    "is_current": start_month <= self.today.month <= end_month,
                },
            )
            terms.append(term)
            if created:
                self._bump("terms")
        return year, terms

    def _departments(self, branch):
        departments = []
        for name in DEPARTMENTS:
            department, created = StaffDepartment.objects.get_or_create(
                branch=branch, name=name,
                defaults={"organization": branch.organization},
            )
            departments.append(department)
            self._bump("departments", int(created))

        designations = []
        for name in TEACHING_DESIGNATIONS + SUPPORT_DESIGNATIONS:
            designation, created = StaffDesignation.objects.get_or_create(
                branch=branch, name=name,
                defaults={
                    "organization": branch.organization,
                    "department": self.rng.choice(departments),
                    "is_teaching": name in TEACHING_DESIGNATIONS,
                },
            )
            designations.append(designation)
            self._bump("designations", int(created))
        return departments, designations

    def _staff(self, branch, departments, designations):
        existing = Staff.objects.filter(branch=branch).count()
        target = self.opts["staff"]
        teaching_designations = [d for d in designations if d.is_teaching]
        support_designations = [d for d in designations if not d.is_teaching]

        new = []
        for index in range(existing, target):
            is_teacher = index < int(target * 0.7)
            gender = self.rng.choice([Gender.MALE, Gender.FEMALE])
            new.append(
                Staff(
                    branch=branch,
                    organization=branch.organization,
                    employee_no=f"{branch.code}-EMP-{index + 1:04d}",
                    full_name=self._name(gender),
                    father_name=self._name(Gender.MALE),
                    staff_type=(
                        Staff.StaffType.TEACHER if is_teacher
                        else self.rng.choice(
                            [Staff.StaffType.ADMINISTRATIVE, Staff.StaffType.SUPPORT]
                        )
                    ),
                    department=self.rng.choice(departments),
                    designation=self.rng.choice(
                        teaching_designations if is_teacher else support_designations
                    ),
                    gender=gender,
                    date_of_birth=self._birthday(24, 58),
                    national_id=self._cnic(),
                    phone=self._phone(),
                    email=f"staff{index + 1}.{branch.code.lower()}@demo.invalid",
                    address=f"{self.rng.randint(1, 400)} Street, {self.rng.choice(CITIES)}",
                    qualification=self.rng.choice(
                        ["Shahadat ul Alamiyyah", "MA Islamic Studies", "BSc", "MSc",
                         "BEd", "MPhil", "Hafiz-e-Quran", "BA"]
                    ),
                    joining_date=self.today - dt.timedelta(days=self.rng.randint(60, 2200)),
                    basic_salary=Decimal(self.rng.randrange(35000, 120000, 500)),
                    status=(
                        Staff.Status.ACTIVE if self.rng.random() < 0.93
                        else self.rng.choice(
                            [Staff.Status.ON_LEAVE, Staff.Status.RESIGNED]
                        )
                    ),
                )
            )
        Staff.objects.bulk_create(new, batch_size=200)
        self._bump("staff", len(new))

        staff = list(Staff.objects.filter(branch=branch))

        profiles = [
            StaffProfile(
                branch=branch, organization=branch.organization, staff=member,
                blood_group=self.rng.choice(["A+", "B+", "O+", "AB+", "A-", "O-"]),
                marital_status=self.rng.choice(["Single", "Married"]),
                emergency_contact_name=self._name(Gender.MALE),
                emergency_contact_phone=self._phone(),
                bank_name=self.rng.choice(["Meezan Bank", "HBL", "UBL", "Bank Alfalah"]),
                bank_account_number=str(self.rng.randint(10**11, 10**12 - 1)),
                experience_years=self.rng.randint(0, 25),
            )
            for member in staff
            if not StaffProfile.objects.filter(staff=member).exists()
        ]
        StaffProfile.objects.bulk_create(profiles, batch_size=200)
        self._bump("staff profiles", len(profiles))

        assignments = [
            StaffAssignment(
                branch=branch, organization=branch.organization, staff=member,
                title=self.rng.choice(
                    ["Exam Controller", "Hostel Warden", "Sports Coordinator",
                     "Discipline In-charge", "Library In-charge", "Transport In-charge"]
                ),
                department=member.department,
                start_date=self.today - dt.timedelta(days=self.rng.randint(30, 700)),
            )
            for member in self.rng.sample(staff, min(12, len(staff)))
        ]
        StaffAssignment.objects.bulk_create(assignments, batch_size=100)
        self._bump("staff assignments", len(assignments))

        history = [
            StaffStatusHistory(
                branch=branch, organization=branch.organization, staff=member,
                previous_status=Staff.Status.ACTIVE, new_status=member.status,
                effective_date=self.today - dt.timedelta(days=self.rng.randint(1, 300)),
                reason="Demo status change",
            )
            for member in staff
            if member.status != Staff.Status.ACTIVE
        ]
        StaffStatusHistory.objects.bulk_create(history, batch_size=100)
        self._bump("staff status history", len(history))
        return staff

    def _classes(self, branch):
        names = [
            "Nursery", "Class 1", "Class 2", "Class 3", "Class 4", "Class 5",
            "Class 6", "Class 7", "Class 8", "Class 9", "Class 10",
            "Hifz Junior", "Hifz Senior",
        ]
        classes = []
        for level, name in enumerate(names[: self.opts["classes"]], start=1):
            school_class, created = SchoolClass.objects.get_or_create(
                branch=branch, code=f"{branch.code}-C{level:02d}",
                defaults={
                    "organization": branch.organization,
                    "name": name,
                    "level": level,
                },
            )
            classes.append(school_class)
            self._bump("classes", int(created))

        sections = []
        for school_class in classes:
            for label in ["A", "B", "C"][: self.rng.randint(2, 3)]:
                section, created = Section.objects.get_or_create(
                    school_class=school_class, name=label,
                    defaults={
                        "organization": branch.organization,
                        "branch": branch,
                        "capacity": 45,
                    },
                )
                sections.append(section)
                self._bump("sections", int(created))
        return classes, sections

    def _subjects(self, branch, year, classes):
        subjects = []
        for name, kind in SUBJECT_NAMES:
            subject, created = Subject.objects.get_or_create(
                branch=branch, name=name,
                defaults={
                    "organization": branch.organization,
                    "code": name[:4].upper(),
                    "kind": kind,
                },
            )
            subjects.append(subject)
            self._bump("subjects", int(created))

        class_subjects = []
        for school_class in classes:
            for subject in self.rng.sample(subjects, 6):
                class_subject, created = ClassSubject.objects.get_or_create(
                    academic_year=year, school_class=school_class, subject=subject,
                    defaults={
                        "organization": branch.organization,
                        "branch": branch,
                        "weekly_periods": self.rng.randint(2, 6),
                    },
                )
                class_subjects.append(class_subject)
                self._bump("class subjects", int(created))
        return subjects, class_subjects

    def _teaching(self, branch, year, staff, class_subjects, sections):
        teachers = [s for s in staff if s.is_teacher and s.status == Staff.Status.ACTIVE]
        if not teachers:
            return

        # One class teacher per section.
        for section in sections:
            if section.class_teacher_id is None:
                section.class_teacher = self.rng.choice(teachers)
        Section.objects.bulk_update(sections, ["class_teacher"], batch_size=200)

        existing = set(
            TeacherAssignment.objects.filter(branch=branch).values_list(
                "class_subject_id", "section_id", "teacher_id"
            )
        )
        assignments = []
        slots = []
        for class_subject in class_subjects:
            class_sections = [
                s for s in sections if s.school_class_id == class_subject.school_class_id
            ]
            for section in class_sections:
                teacher = self.rng.choice(teachers)
                key = (class_subject.pk, section.pk, teacher.pk)
                if key in existing:
                    continue
                existing.add(key)
                assignments.append(
                    TeacherAssignment(
                        branch=branch, organization=branch.organization,
                        academic_year=year, teacher=teacher,
                        class_subject=class_subject, section=section,
                    )
                )
        TeacherAssignment.objects.bulk_create(assignments, batch_size=300)
        self._bump("teacher assignments", len(assignments))

        taken = set(
            Timetable.objects.filter(branch=branch).values_list(
                "section_id", "weekday", "period"
            )
        )
        for section in sections:
            options = [
                cs for cs in class_subjects
                if cs.school_class_id == section.school_class_id
            ]
            if not options:
                continue
            for weekday in range(5):
                for period in range(1, 6):
                    if (section.pk, weekday, period) in taken:
                        continue
                    taken.add((section.pk, weekday, period))
                    class_subject = self.rng.choice(options)
                    start = dt.time(8 + period, 0)
                    slots.append(
                        Timetable(
                            branch=branch, organization=branch.organization,
                            academic_year=year, section=section,
                            class_subject=class_subject,
                            teacher=self.rng.choice(teachers),
                            weekday=weekday, period=period,
                            start_time=start,
                            end_time=dt.time(8 + period, 40),
                            room=f"R{self.rng.randint(101, 320)}",
                        )
                    )
        Timetable.objects.bulk_create(slots, batch_size=500)
        self._bump("timetable slots", len(slots))

    # ------------------------------------------------------------------
    # people
    # ------------------------------------------------------------------
    def _students(self, branch, year, classes, sections):
        existing = Student.all_objects.filter(branch=branch).count()
        target = self.opts["students"]
        if existing >= target:
            self.stdout.write(f"  students: {existing} already present")
            students = list(Student.objects.filter(branch=branch))
            return students, list(
                StudentEnrollment.objects.filter(branch=branch, is_current=True)
                .select_related("school_class", "section")
            )

        by_class = {}
        for section in sections:
            by_class.setdefault(section.school_class_id, []).append(section)

        new = []
        for index in range(existing, target):
            gender = self.rng.choice([Gender.MALE, Gender.FEMALE])
            status = Student.Status.ACTIVE
            roll = self.rng.random()
            if roll > 0.95:
                status = self.rng.choice(
                    [Student.Status.WITHDRAWN, Student.Status.GRADUATED,
                     Student.Status.TRANSFERRED, Student.Status.INACTIVE]
                )
            new.append(
                Student(
                    branch=branch,
                    organization=branch.organization,
                    admission_no=f"{branch.code}-{self.today.year}-{index + 1:05d}",
                    full_name=self._name(gender),
                    father_name=self._name(Gender.MALE),
                    gender=gender,
                    date_of_birth=self._birthday(5, 18),
                    place_of_birth=self.rng.choice(CITIES),
                    nationality="Pakistani",
                    national_id=self._cnic(),
                    phone=self._phone(),
                    email="",
                    address=f"House {self.rng.randint(1, 900)}, {self.rng.choice(CITIES)}",
                    city=self.rng.choice(CITIES),
                    previous_institution=self.rng.choice(
                        ["", "", "City Public School", "Al-Noor Academy", "Government High School"]
                    ),
                    admission_date=self.today - dt.timedelta(days=self.rng.randint(30, 1500)),
                    is_boarder=self.rng.random() < 0.25,
                    status=status,
                )
            )
        Student.objects.bulk_create(new, batch_size=500)
        self._bump("students", len(new))

        students = list(Student.objects.filter(branch=branch))
        active = [s for s in students if s.status == Student.Status.ACTIVE]

        enrolled = set(
            StudentEnrollment.objects.filter(branch=branch).values_list(
                "student_id", flat=True
            )
        )
        enrollments = []
        histories = []
        rolls = {}
        for student in active:
            if student.pk in enrolled:
                continue
            school_class = self.rng.choice(classes)
            section = self.rng.choice(by_class[school_class.pk])
            rolls[section.pk] = rolls.get(section.pk, 0) + 1
            enrollments.append(
                StudentEnrollment(
                    branch=branch, organization=branch.organization,
                    student=student, academic_year=year,
                    school_class=school_class, section=section,
                    roll_number=f"{rolls[section.pk]:03d}",
                    start_date=year.start_date, is_current=True,
                )
            )
            histories.append(
                StudentClassHistory(
                    branch=branch, organization=branch.organization,
                    student=student, academic_year=year,
                    school_class=school_class, section=section,
                    moved_on=year.start_date, reason="Initial enrollment",
                )
            )
        StudentEnrollment.objects.bulk_create(enrollments, batch_size=500)
        StudentClassHistory.objects.bulk_create(histories, batch_size=500)
        self._bump("enrollments", len(enrollments))
        self._bump("class history", len(histories))

        profiles = [
            StudentProfile(
                branch=branch, organization=branch.organization, student=student,
                blood_group=self.rng.choice(["A+", "B+", "O+", "AB+", "O-"]),
                emergency_contact_name=self._name(Gender.MALE),
                emergency_contact_phone=self._phone(),
                transport_required=self.rng.random() < 0.3,
                hostel_room=f"H-{self.rng.randint(1, 60)}" if student.is_boarder else "",
            )
            for student in new
        ]
        StudentProfile.objects.bulk_create(profiles, batch_size=500)
        self._bump("student profiles", len(profiles))

        status_history = [
            StudentStatusHistory(
                branch=branch, organization=branch.organization, student=student,
                previous_status=Student.Status.ACTIVE, new_status=student.status,
                effective_date=self.today - dt.timedelta(days=self.rng.randint(1, 400)),
                reason="Demo status change",
            )
            for student in students
            if student.status != Student.Status.ACTIVE
        ]
        StudentStatusHistory.objects.bulk_create(status_history, batch_size=300)
        self._bump("student status history", len(status_history))

        documents = [
            StudentDocument(
                branch=branch, organization=branch.organization, student=student,
                document_type=self.rng.choice(
                    [StudentDocument.DocumentType.BIRTH_CERTIFICATE,
                     StudentDocument.DocumentType.ID_CARD,
                     StudentDocument.DocumentType.TRANSFER_CERTIFICATE]
                ),
                title="Demo document (no file attached)",
                file="students/documents/demo-placeholder.pdf",
                issued_on=self.today - dt.timedelta(days=self.rng.randint(100, 2000)),
            )
            for student in self.rng.sample(students, min(150, len(students)))
        ]
        StudentDocument.objects.bulk_create(documents, batch_size=200)
        self._bump("student documents", len(documents))

        current = list(
            StudentEnrollment.objects.filter(branch=branch, is_current=True)
            .select_related("school_class", "section")
        )
        return students, current

    def _guardians(self, branch, students):
        linked = set(
            StudentGuardian.objects.filter(branch=branch).values_list(
                "student_id", flat=True
            )
        )
        pending = [s for s in students if s.pk not in linked]
        if not pending:
            return

        guardians = [
            Guardian(
                branch=branch, organization=branch.organization,
                full_name=student.father_name or self._name(Gender.MALE),
                relation=Guardian.Relation.FATHER,
                national_id=self._cnic(),
                phone=self._phone(),
                alternate_phone=self._phone() if self.rng.random() < 0.4 else "",
                email="",
                occupation=self.rng.choice(
                    ["Shopkeeper", "Teacher", "Driver", "Engineer", "Farmer",
                     "Businessman", "Government Servant", "Labourer"]
                ),
                address=student.address,
            )
            for student in pending
        ]
        Guardian.objects.bulk_create(guardians, batch_size=500)
        self._bump("guardians", len(guardians))

        created = list(
            Guardian.objects.filter(branch=branch).order_by("-created_at")[: len(pending)]
        )
        links = [
            StudentGuardian(
                branch=branch, organization=branch.organization,
                student=student, guardian=guardian,
                relation="Father", is_primary=True,
                can_view_portal=True, can_collect_student=True,
            )
            for student, guardian in zip(pending, created)
        ]
        StudentGuardian.objects.bulk_create(links, batch_size=500)
        self._bump("student guardians", len(links))

    # ------------------------------------------------------------------
    # daily operations
    # ------------------------------------------------------------------
    def _attendance(self, branch, year, sections, enrollments, staff):
        days = self._school_days(self.opts["attendance_days"])
        if not days:
            return

        by_section = {}
        for enrollment in enrollments:
            by_section.setdefault(enrollment.section_id, []).append(enrollment.student_id)

        existing = set(
            AttendanceSession.objects.filter(branch=branch).values_list(
                "school_class_id", "section_id", "date", "period"
            )
        )
        sessions = []
        for section in sections:
            if not by_section.get(section.pk):
                continue
            for day in days:
                key = (section.school_class_id, section.pk, day, 0)
                if key in existing:
                    continue
                existing.add(key)
                sessions.append(
                    AttendanceSession(
                        branch=branch, organization=branch.organization,
                        academic_year=year, school_class_id=section.school_class_id,
                        section=section, date=day,
                        session_type=AttendanceSession.SessionType.DAILY,
                        taken_by=None,
                    )
                )
        AttendanceSession.objects.bulk_create(sessions, batch_size=300)
        self._bump("attendance sessions", len(sessions))

        statuses = (
            [AttendanceStatus.PRESENT] * 88
            + [AttendanceStatus.ABSENT] * 6
            + [AttendanceStatus.LATE] * 3
            + [AttendanceStatus.LEAVE] * 2
            + [AttendanceStatus.EXCUSED]
        )
        records = []
        for session in AttendanceSession.objects.filter(branch=branch, date__in=days):
            for student_id in by_section.get(session.section_id, []):
                status = self.rng.choice(statuses)
                records.append(
                    StudentAttendance(
                        branch=branch, organization=branch.organization,
                        session=session, student_id=student_id, date=session.date,
                        status=status,
                        minutes_late=self.rng.randint(5, 40)
                        if status == AttendanceStatus.LATE else 0,
                        remarks="",
                    )
                )
        StudentAttendance.objects.bulk_create(
            records, batch_size=2000, ignore_conflicts=True
        )
        self._bump("student attendance", len(records))

        staff_records = []
        marked = set(
            StaffAttendance.objects.filter(branch=branch).values_list("staff_id", "date")
        )
        for member in staff:
            for day in days:
                if (member.pk, day) in marked:
                    continue
                marked.add((member.pk, day))
                staff_records.append(
                    StaffAttendance(
                        branch=branch, organization=branch.organization,
                        staff=member, date=day,
                        status=self.rng.choice(statuses),
                        check_in=dt.time(7, self.rng.randint(40, 59)),
                        check_out=dt.time(14, self.rng.randint(0, 30)),
                    )
                )
        StaffAttendance.objects.bulk_create(
            staff_records, batch_size=1000, ignore_conflicts=True
        )
        self._bump("staff attendance", len(staff_records))

    def _hifz(self, branch, students, staff):
        active = [s for s in students if s.status == Student.Status.ACTIVE]
        already = set(
            HifzStudentProfile.objects.filter(branch=branch).values_list(
                "student_id", flat=True
            )
        )
        candidates = [s for s in active if s.pk not in already]
        chosen = self.rng.sample(candidates, min(int(len(active) * 0.35), len(candidates)))
        if not chosen:
            return

        profiles = [
            HifzStudentProfile(
                branch=branch, organization=branch.organization, student=student,
                stage=self.rng.choice(
                    [HifzStudentProfile.Stage.QAIDA, HifzStudentProfile.Stage.NAZRA,
                     HifzStudentProfile.Stage.HIFZ, HifzStudentProfile.Stage.HIFZ,
                     HifzStudentProfile.Stage.REVISION]
                ),
                started_on=self.today - dt.timedelta(days=self.rng.randint(100, 1200)),
                current_para=self.rng.randint(1, 30),
                current_surah=self.rng.randint(1, 114),
                paras_memorized=Decimal(self.rng.randint(0, 30)),
                daily_target_lines=self.rng.choice([5, 8, 10, 12, 15]),
            )
            for student in chosen
        ]
        HifzStudentProfile.objects.bulk_create(profiles, batch_size=300)
        self._bump("hifz profiles", len(profiles))

        profiles = list(
            HifzStudentProfile.objects.filter(branch=branch).select_related("student")
        )
        teachers = [
            s for s in staff
            if s.is_teacher and s.status == Staff.Status.ACTIVE
        ] or staff

        assigned = set(
            HifzTeacherAssignment.objects.filter(
                branch=branch, is_active=True
            ).values_list("hifz_profile_id", flat=True)
        )
        teacher_links = [
            HifzTeacherAssignment(
                branch=branch, organization=branch.organization,
                hifz_profile=profile, teacher=self.rng.choice(teachers),
                start_date=profile.started_on or self.today,
            )
            for profile in profiles
            if profile.pk not in assigned
        ]
        HifzTeacherAssignment.objects.bulk_create(teacher_links, batch_size=300)
        self._bump("hifz teacher assignments", len(teacher_links))

        days = self._school_days(min(self.opts["attendance_days"], 8))
        entries = []
        for profile in profiles:
            for day in days:
                for lesson in (LessonType.SABAQ, LessonType.SABQI, LessonType.MANZIL):
                    start = self.rng.randint(1, 28)
                    entries.append(
                        DailyProgress(
                            branch=branch, organization=branch.organization,
                            hifz_profile=profile,
                            teacher=self.rng.choice(teachers),
                            date=day, lesson_type=lesson,
                            from_para=start, to_para=min(start + 1, 30),
                            surah=self.rng.randint(1, 114),
                            from_ayah=self.rng.randint(1, 50),
                            to_ayah=self.rng.randint(51, 120),
                            lines=Decimal(self.rng.randint(4, 20)),
                            pages=Decimal(self.rng.randint(1, 4)),
                            mistakes=self.rng.randint(0, 6),
                            hesitations=self.rng.randint(0, 4),
                            quality=self.rng.choice(list(Quality.values)),
                        )
                    )
        DailyProgress.objects.bulk_create(
            entries, batch_size=2000, ignore_conflicts=True
        )
        self._bump("hifz daily progress", len(entries))

        revisions = []
        assessments = []
        for profile in profiles:
            for _ in range(self.rng.randint(1, 3)):
                start = self.rng.randint(1, 25)
                revisions.append(
                    Revision(
                        branch=branch, organization=branch.organization,
                        hifz_profile=profile, teacher=self.rng.choice(teachers),
                        from_para=start, to_para=min(start + self.rng.randint(1, 5), 30),
                        scheduled_date=self.today - dt.timedelta(days=self.rng.randint(0, 60)),
                        status=self.rng.choice(list(Revision.Status.values)),
                        mistakes=self.rng.randint(0, 8),
                        quality=self.rng.choice(list(Quality.values)),
                    )
                )
            if self.rng.random() < 0.6:
                start = self.rng.randint(1, 25)
                total = Decimal("100.00")
                assessments.append(
                    HifzAssessment(
                        branch=branch, organization=branch.organization,
                        hifz_profile=profile, examiner=self.rng.choice(teachers),
                        title=f"Para {start} assessment",
                        date=self.today - dt.timedelta(days=self.rng.randint(0, 120)),
                        from_para=start, to_para=min(start + 2, 30),
                        total_marks=total,
                        obtained_marks=Decimal(self.rng.randint(35, 100)),
                        mistakes=self.rng.randint(0, 10),
                        result=self.rng.choice(list(HifzAssessment.Result.values)),
                    )
                )
        Revision.objects.bulk_create(revisions, batch_size=500)
        HifzAssessment.objects.bulk_create(assessments, batch_size=500)
        self._bump("hifz revisions", len(revisions))
        self._bump("hifz assessments", len(assessments))

    # ------------------------------------------------------------------
    # money
    # ------------------------------------------------------------------
    def _fees(self, branch, year, terms, classes, students, enrollments):
        from apps.fees.services import record_payment

        fee_types = []
        for name, frequency, _amount in FEE_TYPES:
            fee_type, created = FeeType.objects.get_or_create(
                branch=branch, name=name,
                defaults={
                    "organization": branch.organization,
                    "code": name[:4].upper(),
                    "frequency": frequency,
                    "is_refundable": name == "Hostel Fee",
                },
            )
            fee_types.append(fee_type)
            self._bump("fee types", int(created))

        tuition = fee_types[0]
        for school_class in classes:
            for fee_type, (_n, _f, base) in zip(fee_types, FEE_TYPES):
                amount = base + Decimal(school_class.level * 250)
                _s, created = FeeStructure.objects.get_or_create(
                    academic_year=year, school_class=school_class, fee_type=fee_type,
                    defaults={
                        "organization": branch.organization,
                        "branch": branch,
                        "amount": amount,
                        "is_mandatory": fee_type.frequency != FeeType.Frequency.ONE_TIME,
                    },
                )
                self._bump("fee structures", int(created))

        active = [e for e in enrollments]
        if not active:
            return

        # Per-student overrides and concessions.
        overrides = [
            StudentFee(
                branch=branch, organization=branch.organization,
                student_id=enrollment.student_id, academic_year=year,
                fee_type=tuition,
                amount=Decimal(self.rng.randrange(3000, 6000, 250)),
                effective_from=year.start_date,
                notes="Demo negotiated fee",
            )
            for enrollment in self.rng.sample(active, min(60, len(active)))
        ]
        StudentFee.objects.bulk_create(overrides, batch_size=200, ignore_conflicts=True)
        self._bump("student fees", len(overrides))

        discounts = [
            FeeDiscount(
                branch=branch, organization=branch.organization,
                name=self.rng.choice(["Sibling Discount", "Merit Scholarship", "Hardship Relief"]),
                student_id=enrollment.student_id, fee_type=tuition,
                discount_type=FeeDiscount.DiscountType.PERCENTAGE,
                value=Decimal(self.rng.choice([10, 15, 20, 25, 50])),
                valid_from=year.start_date,
                reason="Demo concession",
            )
            for enrollment in self.rng.sample(active, min(120, len(active)))
        ]
        FeeDiscount.objects.bulk_create(discounts, batch_size=200)
        self._bump("fee discounts", len(discounts))

        month = dt.date(self.today.year, self.today.month, 1)
        if FeeInvoice.objects.filter(branch=branch, period_month=month).exists():
            self.stdout.write("  invoices for this month already exist")
            return

        structures = {
            (s.school_class_id, s.fee_type_id): s
            for s in FeeStructure.objects.filter(academic_year=year, branch=branch)
        }
        overridden = {
            (sf.student_id, sf.fee_type_id): sf.amount
            for sf in StudentFee.objects.filter(academic_year=year, branch=branch)
        }
        concessions = {}
        for discount in FeeDiscount.objects.filter(branch=branch, is_active=True):
            concessions.setdefault(discount.student_id, []).append(discount)

        term = next((t for t in terms if t.is_current), terms[0] if terms else None)
        billable = [ft for ft in fee_types if ft.frequency == FeeType.Frequency.MONTHLY]

        invoices = []
        counter = FeeInvoice.objects.filter(branch=branch).count()
        for enrollment in active:
            counter += 1
            subtotal = Decimal("0.00")
            discount_total = Decimal("0.00")
            lines = []
            for fee_type in billable:
                if fee_type.name == "Hostel Fee" and self.rng.random() > 0.25:
                    continue
                if fee_type.name == "Transport Fee" and self.rng.random() > 0.3:
                    continue
                structure = structures.get((enrollment.school_class_id, fee_type.pk))
                if structure is None:
                    continue
                amount = overridden.get(
                    (enrollment.student_id, fee_type.pk), structure.amount
                )
                line_discount = Decimal("0.00")
                for concession in concessions.get(enrollment.student_id, []):
                    if concession.fee_type_id in (None, fee_type.pk):
                        line_discount += (amount * concession.value / Decimal("100")).quantize(
                            Decimal("0.01")
                        )
                line_discount = min(line_discount, amount)
                subtotal += amount
                discount_total += line_discount
                lines.append((fee_type, amount, line_discount))

            if not lines:
                continue
            invoice = FeeInvoice(
                branch=branch, organization=branch.organization,
                invoice_number=f"INV-{branch.code}-{counter:06d}",
                student_id=enrollment.student_id, academic_year=year, term=term,
                period_month=month,
                issue_date=month,
                due_date=month + dt.timedelta(days=10),
                subtotal=subtotal, discount_amount=discount_total,
                total_amount=subtotal - discount_total,
                status=FeeInvoice.Status.ISSUED,
            )
            invoice._lines = lines
            invoices.append(invoice)

        FeeInvoice.objects.bulk_create(invoices, batch_size=500)
        self._bump("fee invoices", len(invoices))

        stored = {i.invoice_number: i for i in FeeInvoice.objects.filter(branch=branch, period_month=month)}
        items = []
        for invoice in invoices:
            saved = stored.get(invoice.invoice_number)
            if saved is None:
                continue
            for fee_type, amount, line_discount in invoice._lines:
                items.append(
                    FeeInvoiceItem(
                        branch=branch, organization=branch.organization,
                        invoice=saved, fee_type=fee_type,
                        description=fee_type.name, quantity=1,
                        unit_amount=amount, discount_amount=line_discount,
                        line_total=amount - line_discount,
                    )
                )
        FeeInvoiceItem.objects.bulk_create(items, batch_size=1000)
        self._bump("fee invoice items", len(items))

        # One batch posting for the whole month's billing, so the ledger
        # balances without 1000 near-identical journal entries.
        billed = sum((i.total_amount for i in invoices), Decimal("0.00"))
        if billed > 0:
            post_journal_entry(
                branch=branch,
                date=month,
                lines=[
                    {"account": get_account(branch, CODE_RECEIVABLE), "debit": billed,
                     "description": f"Monthly fee billing {month:%Y-%m}"},
                    {"account": get_account(branch, CODE_TUITION_INCOME), "credit": billed,
                     "description": f"Monthly fee billing {month:%Y-%m}"},
                ],
                journal_type=Journal.JournalType.GENERAL,
                description=f"Demo batch billing for {month:%B %Y}",
                reference=f"BILL-{branch.code}-{month:%Y%m}",
                source_module="fees.batch",
                source_id=str(month),
            )

        method = PaymentMethod.objects.filter(branch=branch, is_active=True).first()
        cash = PaymentMethod.objects.filter(
            branch=branch, method_type="cash"
        ).first() or method
        payable = [i for i in stored.values() if i.total_amount > 0]
        paying = self.rng.sample(
            payable, min(int(len(payable) * self.opts["pay_ratio"]), len(payable))
        )
        paid = 0
        for invoice in paying:
            amount = invoice.total_amount
            if self.rng.random() < 0.25:
                amount = (amount / 2).quantize(Decimal("0.01"))
            try:
                record_payment(
                    invoice=invoice, amount=amount,
                    payment_method=self.rng.choice([cash, method]),
                    payment_date=month + dt.timedelta(days=self.rng.randint(0, 20)),
                    reference="", notes="Demo payment",
                )
                paid += 1
            except Exception:
                continue
        self._bump("fee payments", paid)

    def _staff_documents(self, branch):
        from apps.staff.models import StaffDocument

        staff = list(Staff.objects.filter(branch=branch))
        already = set(
            StaffDocument.objects.filter(branch=branch).values_list("staff_id", flat=True)
        )
        pending = [s for s in staff if s.pk not in already]
        if not pending:
            return
        documents = []
        for member in self.rng.sample(pending, min(30, len(pending))):
            for document_type, title in [
                (StaffDocument.DocumentType.CONTRACT, "Employment contract"),
                (StaffDocument.DocumentType.DEGREE, "Highest qualification"),
                (StaffDocument.DocumentType.ID_CARD, "National identity card"),
            ]:
                documents.append(
                    StaffDocument(
                        branch=branch, organization=branch.organization, staff=member,
                        document_type=document_type,
                        title=f"{title} (demo, no file attached)",
                        file="staff/documents/demo-placeholder.pdf",
                        issued_on=member.joining_date or self.today,
                        expires_on=self.today + dt.timedelta(days=self.rng.randint(200, 1500)),
                    )
                )
        StaffDocument.objects.bulk_create(documents, batch_size=200)
        self._bump("staff documents", len(documents))

    def _fee_adjustments(self, branch):
        """Waivers and refunds, through the services, so the ledger stays right."""
        from apps.fees.models import FeePayment, FeeRefund, FeeWaiver
        from apps.fees.services import refund_payment, waive_invoice_amount

        if not FeeWaiver.objects.filter(branch=branch).exists():
            unpaid = list(
                FeeInvoice.objects.filter(
                    branch=branch,
                    status__in=[FeeInvoice.Status.ISSUED, FeeInvoice.Status.OVERDUE],
                ).order_by("?")[:40]
            )
            waived = 0
            for invoice in unpaid:
                outstanding = (
                    invoice.total_amount - invoice.paid_amount - invoice.waiver_amount
                )
                if outstanding <= 0:
                    continue
                amount = (outstanding * Decimal("0.3")).quantize(Decimal("0.01"))
                try:
                    waive_invoice_amount(
                        invoice=invoice, amount=amount,
                        reason=self.rng.choice(
                            ["Financial hardship", "Orphan support", "Staff child concession"]
                        ),
                        waived_on=invoice.issue_date + dt.timedelta(days=5),
                    )
                    waived += 1
                except Exception:
                    continue
            self._bump("fee waivers", waived)

        if not FeeRefund.objects.filter(branch=branch).exists():
            payments = list(
                FeePayment.objects.filter(branch=branch, is_void=False).order_by("?")[:30]
            )
            refunded = 0
            for payment in payments:
                amount = (payment.amount * Decimal("0.25")).quantize(Decimal("0.01"))
                if amount <= 0:
                    continue
                try:
                    refund_payment(
                        payment=payment, amount=amount,
                        refund_date=payment.payment_date + dt.timedelta(days=3),
                        reason=self.rng.choice(
                            ["Withdrawal mid-month", "Duplicate payment", "Hostel not availed"]
                        ),
                    )
                    refunded += 1
                except Exception:
                    continue
            self._bump("fee refunds", refunded)

    def _payroll(self, branch, staff):
        components = []
        specs = [
            ("House Rent", "HRA", SalaryComponent.ComponentType.EARNING,
             SalaryComponent.CalculationType.PERCENT_OF_BASIC, Decimal("20.00")),
            ("Conveyance", "CONV", SalaryComponent.ComponentType.EARNING,
             SalaryComponent.CalculationType.FIXED, Decimal("3000.00")),
            ("Medical", "MED", SalaryComponent.ComponentType.EARNING,
             SalaryComponent.CalculationType.FIXED, Decimal("2000.00")),
            ("Provident Fund", "PF", SalaryComponent.ComponentType.DEDUCTION,
             SalaryComponent.CalculationType.PERCENT_OF_BASIC, Decimal("5.00")),
            ("Income Tax", "TAX", SalaryComponent.ComponentType.DEDUCTION,
             SalaryComponent.CalculationType.FIXED, Decimal("1500.00")),
        ]
        for name, code, kind, calculation, value in specs:
            component, created = SalaryComponent.objects.get_or_create(
                branch=branch, code=code,
                defaults={
                    "organization": branch.organization, "name": name,
                    "component_type": kind, "calculation_type": calculation,
                    "default_value": value,
                },
            )
            components.append((component, value))
            self._bump("salary components", int(created))

        structures = []
        for label, basic in [("Senior Scale", Decimal("90000.00")),
                             ("Standard Scale", Decimal("60000.00")),
                             ("Support Scale", Decimal("38000.00"))]:
            structure, created = SalaryStructure.objects.get_or_create(
                branch=branch, name=label,
                defaults={"organization": branch.organization, "basic_salary": basic},
            )
            structures.append(structure)
            self._bump("salary structures", int(created))
            for sequence, (component, value) in enumerate(components, start=1):
                _l, made = SalaryStructureLine.objects.get_or_create(
                    structure=structure, component=component,
                    defaults={
                        "organization": branch.organization, "branch": branch,
                        "value": value, "sequence": sequence,
                    },
                )
                self._bump("structure lines", int(made))

        salaried = set(
            EmployeeSalary.objects.filter(branch=branch, is_active=True).values_list(
                "staff_id", flat=True
            )
        )
        salaries = []
        for member in staff:
            if member.pk in salaried or member.status != Staff.Status.ACTIVE:
                continue
            structure = (
                structures[0] if member.basic_salary >= 80000
                else structures[1] if member.is_teacher else structures[2]
            )
            salaries.append(
                EmployeeSalary(
                    branch=branch, organization=branch.organization,
                    staff=member, structure=structure,
                    basic_salary=member.basic_salary or structure.basic_salary,
                    effective_from=member.joining_date or self.today,
                    bank_account_number=str(self.rng.randint(10**11, 10**12 - 1)),
                )
            )
        EmployeeSalary.objects.bulk_create(salaries, batch_size=200)
        self._bump("employee salaries", len(salaries))

        month = dt.date(self.today.year, self.today.month, 1)
        period, created = PayrollPeriod.objects.get_or_create(
            branch=branch, month=month,
            defaults={
                "organization": branch.organization,
                "name": f"{month:%B %Y} — {branch.code}",
                "start_date": month,
                "end_date": month + dt.timedelta(days=27),
                "payment_date": month + dt.timedelta(days=30),
            },
        )
        self._bump("payroll periods", int(created))

        if period.runs.exists():
            return
        from apps.payroll.services import approve_payroll_run, pay_salary, process_payroll

        try:
            run = process_payroll(period=period, run_date=month + dt.timedelta(days=27))
            approve_payroll_run(run=run)
            self._bump("payroll runs")
            self._bump("payroll items", run.items.count())

            method = PaymentMethod.objects.filter(branch=branch, is_active=True).first()
            paid = 0
            for item in run.items.all()[: int(run.items.count() * 0.8)]:
                pay_salary(
                    payroll_item=item, payment_method=method,
                    payment_date=month + dt.timedelta(days=30),
                )
                paid += 1
            self._bump("salary payments", paid)
        except Exception as error:  # pragma: no cover - demo data is best effort
            self.stderr.write(f"  payroll skipped: {error}")

    def _expenses(self, branch):
        """A handful of running costs, so the ledger is not only fee income."""
        pairs = [("5200", "Electricity and gas"), ("5300", "Building maintenance"),
                 ("5400", "Stationery and printing")]
        cash = get_account(branch, "1000")
        posted = 0
        for code, description in pairs:
            for offset in range(4):
                date = self.today - dt.timedelta(days=offset * 30)
                if date.year != self.today.year:
                    continue
                amount = Decimal(self.rng.randrange(15000, 90000, 500))
                try:
                    post_journal_entry(
                        branch=branch, date=date,
                        lines=[
                            {"account": get_account(branch, code), "debit": amount,
                             "description": description},
                            {"account": cash, "credit": amount, "description": description},
                        ],
                        journal_type=Journal.JournalType.CASH_PAYMENT,
                        description=f"Demo expense — {description}",
                        source_module="demo.expense",
                    )
                    posted += 1
                except Exception:
                    continue
        self._bump("expense entries", posted)

    # ------------------------------------------------------------------
    # exams
    # ------------------------------------------------------------------
    def _exams(self, branch, year, terms, classes, sections, class_subjects,
               enrollments, staff):
        from apps.exams.services import generate_results

        bands = [("A+", 90, 100, 4.0), ("A", 80, 89, 3.7), ("B", 70, 79, 3.3),
                 ("C", 60, 69, 3.0), ("D", 50, 59, 2.0), ("E", 40, 49, 1.0),
                 ("F", 0, 39, 0.0)]
        for name, low, high, points in bands:
            _g, created = Grade.objects.get_or_create(
                academic_year=year, name=name,
                defaults={
                    "organization": branch.organization, "branch": branch,
                    "min_percentage": Decimal(low), "max_percentage": Decimal(high),
                    "grade_point": Decimal(str(points)), "is_pass": low >= 40,
                },
            )
            self._bump("grades", int(created))

        term = next((t for t in terms if t.is_current), terms[0] if terms else None)
        exam_term, created = ExamTerm.objects.get_or_create(
            academic_year=year, name="Mid Term Examination",
            defaults={
                "organization": branch.organization, "branch": branch,
                "term": term, "sequence": 1,
            },
        )
        self._bump("exam terms", int(created))

        by_class = {}
        for enrollment in enrollments:
            by_class.setdefault(enrollment.school_class_id, []).append(enrollment)

        invigilators = [s for s in staff if s.status == Staff.Status.ACTIVE] or staff
        start = self.today - dt.timedelta(days=20)

        for school_class in classes[:6]:
            roster = by_class.get(school_class.pk, [])
            if not roster:
                continue
            exam, made = Exam.objects.get_or_create(
                branch=branch, exam_term=exam_term, school_class=school_class,
                name=f"Mid Term — {school_class.name}",
                defaults={
                    "organization": branch.organization,
                    "academic_year": year,
                    "start_date": start,
                    "end_date": start + dt.timedelta(days=6),
                    "status": Exam.Status.MARKING,
                },
            )
            if not made:
                continue
            self._bump("exams")

            papers = [cs for cs in class_subjects if cs.school_class_id == school_class.pk]
            exam_subjects = ExamSubject.objects.bulk_create(
                [
                    ExamSubject(
                        branch=branch, organization=branch.organization,
                        exam=exam, class_subject=class_subject,
                        total_marks=Decimal("100.00"),
                        passing_marks=Decimal("40.00"),
                    )
                    for class_subject in papers
                ],
                batch_size=100,
            )
            self._bump("exam subjects", len(exam_subjects))

            ExamSchedule.objects.bulk_create(
                [
                    ExamSchedule(
                        branch=branch, organization=branch.organization,
                        exam_subject=exam_subject, section=None,
                        date=start + dt.timedelta(days=index),
                        start_time=dt.time(9, 0), end_time=dt.time(11, 0),
                        room=f"Hall {self.rng.randint(1, 6)}",
                        invigilator=self.rng.choice(invigilators),
                    )
                    for index, exam_subject in enumerate(exam_subjects)
                ],
                batch_size=100,
            )
            self._bump("exam schedules", len(exam_subjects))

            student_exams = StudentExam.objects.bulk_create(
                [
                    StudentExam(
                        branch=branch, organization=branch.organization,
                        exam=exam, student_id=enrollment.student_id,
                        section_id=enrollment.section_id,
                        roll_number=enrollment.roll_number,
                        status=StudentExam.Status.APPEARED,
                    )
                    for enrollment in roster
                ],
                batch_size=500,
            )
            self._bump("student exams", len(student_exams))

            marks = []
            for student_exam in student_exams:
                for exam_subject in exam_subjects:
                    absent = self.rng.random() < 0.02
                    marks.append(
                        Mark(
                            branch=branch, organization=branch.organization,
                            student_exam=student_exam, exam_subject=exam_subject,
                            obtained_marks=Decimal(0) if absent
                            else Decimal(self.rng.randint(28, 99)),
                            is_absent=absent,
                        )
                    )
            Mark.objects.bulk_create(marks, batch_size=2000)
            self._bump("marks", len(marks))

            generate_results(exam=exam)
            self._bump("results", exam.student_exams.count() * len(exam_subjects))
            self._bump("result summaries", exam.student_exams.count())

    # ------------------------------------------------------------------
    # organization-wide
    # ------------------------------------------------------------------
    def _seed_organization_level(self, organization, branches):
        from apps.accounts.models import User

        self.stdout.write(self.style.MIGRATE_HEADING("\n== organization =="))

        for event, title, body in [
            ("fee.due", "Fee reminder", "Dear parent, the fee for {student} is due on {due}."),
            ("attendance.absent", "Absence notice", "{student} was marked absent on {date}."),
            ("exam.result_published", "Results published", "Results for {exam} are available."),
            ("general.announcement", "Announcement", "{message}"),
        ]:
            for channel in (Channel.IN_APP, Channel.EMAIL, Channel.SMS):
                _t, created = NotificationTemplate.objects.get_or_create(
                    organization=organization, event=event, channel=channel, language="en",
                    defaults={"title": title, "body": body},
                )
                self._bump("notification templates", int(created))

        users = list(User.objects.filter(organization=organization))
        branch = branches[0]
        notifications = []
        for index in range(120):
            notifications.append(
                Notification(
                    branch=branch, organization=organization,
                    event=self.rng.choice(
                        ["general.announcement", "fee.due", "attendance.absent"]
                    ),
                    title=self.rng.choice(
                        ["Parent-teacher meeting", "Fee reminder", "Holiday notice",
                         "Exam schedule published", "Absence notice"]
                    ),
                    body="Demo notification body.",
                    priority=self.rng.choice(list(Notification.Priority.values)),
                )
            )
        Notification.objects.bulk_create(notifications, batch_size=200)
        self._bump("notifications", len(notifications))

        recipients = []
        for notification in Notification.objects.filter(organization=organization)[:120]:
            for user in self.rng.sample(users, min(3, len(users))):
                recipients.append(
                    NotificationRecipient(
                        branch=notification.branch, organization=organization,
                        notification=notification, user=user,
                        channel=Channel.IN_APP,
                        address=str(user.pk),
                        status=self.rng.choice(
                            [NotificationRecipient.Status.SENT,
                             NotificationRecipient.Status.READ,
                             NotificationRecipient.Status.PENDING]
                        ),
                    )
                )
        NotificationRecipient.objects.bulk_create(
            recipients, batch_size=500, ignore_conflicts=True
        )
        self._bump("notification recipients", len(recipients))

        preferences = []
        for user in users:
            for channel in (Channel.EMAIL, Channel.SMS):
                preferences.append(
                    NotificationPreference(
                        branch=branch, organization=organization,
                        user=user, event="", channel=channel,
                        is_enabled=self.rng.random() < 0.8,
                    )
                )
        NotificationPreference.objects.bulk_create(
            preferences, batch_size=200, ignore_conflicts=True
        )
        self._bump("notification preferences", len(preferences))

        # Parent portal: give a sample of guardians a login and a request.
        portal_guardians = list(
            Guardian.objects.filter(organization=organization, user__isnull=True)[:40]
        )
        made_users = []
        for index, guardian in enumerate(portal_guardians):
            username = f"parent{index + 1:03d}"
            if User.objects.filter(username=username).exists():
                continue
            user = User(
                organization=organization, username=username,
                first_name="Demo", last_name="Parent",
                email=f"{username}@demo.invalid",
            )
            user.set_password("Madrasah#2026")
            made_users.append((user, guardian))
        User.objects.bulk_create([u for u, _g in made_users], batch_size=100)
        self._bump("parent users", len(made_users))

        from apps.accounts.models import Role, UserBranchAccess, UserRole

        parent_role = Role.objects.filter(organization=organization, name="Parent").first()
        accesses, roles, profiles = [], [], []
        for user, guardian in made_users:
            saved = User.objects.filter(username=user.username).first()
            if saved is None:
                continue
            guardian.user = saved
            accesses.append(
                UserBranchAccess(user=saved, branch=guardian.branch, is_default=True)
            )
            if parent_role:
                roles.append(UserRole(user=saved, role=parent_role))
            profiles.append(
                ParentPortalProfile(
                    branch=guardian.branch, organization=organization, guardian=guardian
                )
            )
        Guardian.objects.bulk_update([g for _u, g in made_users], ["user"], batch_size=100)
        UserBranchAccess.objects.bulk_create(accesses, batch_size=100, ignore_conflicts=True)
        UserRole.objects.bulk_create(roles, batch_size=100, ignore_conflicts=True)
        ParentPortalProfile.objects.bulk_create(profiles, batch_size=100, ignore_conflicts=True)
        self._bump("parent portal profiles", len(profiles))

        requests = []
        links = list(
            StudentGuardian.objects.filter(
                organization=organization, guardian__user__isnull=False
            ).select_related("guardian", "student")[:200]
        )
        for link in links:
            for _ in range(self.rng.randint(1, 3)):
                requests.append(
                    ParentRequest(
                        branch=link.branch, organization=organization,
                        guardian=link.guardian, student=link.student,
                        request_type=self.rng.choice(list(ParentRequest.RequestType.values)),
                        subject=self.rng.choice(
                            ["Leave application", "Fee query", "Result query",
                             "Meeting request", "Transport query"]
                        ),
                        message="Demo request raised through the parent portal.",
                        start_date=self.today + dt.timedelta(days=self.rng.randint(1, 20)),
                        end_date=self.today + dt.timedelta(days=self.rng.randint(21, 30)),
                        status=self.rng.choice(list(ParentRequest.Status.values)),
                    )
                )
        ParentRequest.objects.bulk_create(requests, batch_size=300)
        self._bump("parent requests", len(requests))

        # Saved reports and export history.
        from apps.reports.registry import REGISTRY

        admin = User.objects.filter(organization=organization, username="admin").first()
        saved = []
        exports = []
        for index, key in enumerate(list(REGISTRY)[:10]):
            saved.append(
                SavedReport(
                    organization=organization, name=f"Demo — {key.replace('_', ' ').title()}",
                    report_key=key, filters={"date_from": str(self.today.replace(day=1))},
                    branch=branches[index % len(branches)],
                    is_shared=index % 2 == 0, created_by=admin,
                )
            )
            for _ in range(self.rng.randint(2, 6)):
                exports.append(
                    ReportExport(
                        organization=organization, report_key=key,
                        branch=self.rng.choice(branches),
                        filters={}, row_count=self.rng.randint(20, 2000),
                        exported_by=admin,
                    )
                )
        SavedReport.objects.bulk_create(saved, batch_size=50, ignore_conflicts=True)
        ReportExport.objects.bulk_create(exports, batch_size=100)
        self._bump("saved reports", len(saved))
        self._bump("report exports", len(exports))

        self._subscription(organization)

    def _subscription(self, organization):
        from apps.subscriptions.models import (
            FeatureUsage,
            Plan,
            Subscription,
            SubscriptionInvoice,
        )

        plan = Plan.objects.filter(code="standard").first() or Plan.objects.first()
        if plan is None:
            return
        subscription = Subscription.objects.filter(organization=organization).first()
        if subscription is None:
            subscription = Subscription.objects.create(
                organization=organization, plan=plan,
                start_date=self.today - dt.timedelta(days=90),
                end_date=self.today + dt.timedelta(days=275),
                status=Subscription.Status.ACTIVE,
            )
            self._bump("subscriptions")

        invoices = []
        for offset in range(1, 7):
            start = (self.today.replace(day=1) - dt.timedelta(days=30 * offset)).replace(day=1)
            amount = plan.monthly_price
            invoices.append(
                SubscriptionInvoice(
                    organization=organization, subscription=subscription,
                    invoice_number=f"SUB-{start:%Y%m}",
                    period_start=start,
                    period_end=start + dt.timedelta(days=27),
                    amount=amount, tax_amount=Decimal("0.00"), total_amount=amount,
                    issue_date=start, due_date=start + dt.timedelta(days=14),
                    paid_on=start + dt.timedelta(days=self.rng.randint(1, 13)),
                    status=SubscriptionInvoice.Status.PAID,
                )
            )
        SubscriptionInvoice.objects.bulk_create(
            invoices, batch_size=50, ignore_conflicts=True
        )
        self._bump("subscription invoices", len(invoices))

        usage = []
        for offset in range(6):
            month = (self.today.replace(day=1) - dt.timedelta(days=30 * offset)).replace(day=1)
            for metric, limit in (("sms", plan.monthly_sms_limit),
                                  ("whatsapp", plan.monthly_whatsapp_limit)):
                usage.append(
                    FeatureUsage(
                        organization=organization, subscription=subscription,
                        metric=metric, period_month=month,
                        used=self.rng.randint(0, max(limit, 1)), limit=limit,
                    )
                )
        FeatureUsage.objects.bulk_create(usage, batch_size=50, ignore_conflicts=True)
        self._bump("feature usage", len(usage))

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @transaction.atomic
    def _flush(self, organization):
        """Remove demo business data, keeping the organization and logins."""
        from apps.audit.models import ActivityLog
        from apps.fees.models import FeePayment, FeeRefund, FeeWaiver
        from apps.finance.models import JournalEntry, Transaction
        from apps.payroll.models import PayrollItem, PayrollRun, SalaryPayment

        self.stdout.write("Flushing existing demo business data…")
        for model in (
            StudentAttendance, StaffAttendance, AttendanceSession,
            Mark, StudentExam, ExamSchedule, ExamSubject, Exam,
            DailyProgress, Revision, HifzAssessment, HifzTeacherAssignment,
            HifzStudentProfile,
            SalaryPayment, PayrollItem, PayrollRun,
            FeeRefund, FeeWaiver, FeePayment, FeeInvoiceItem, FeeInvoice,
            Transaction, JournalEntry,
            StudentGuardian, StudentDocument, StudentProfile,
            StudentStatusHistory, StudentClassHistory, StudentEnrollment,
            ParentRequest, ParentPortalProfile, Guardian,
        ):
            deleted = model.objects.all().delete()[0]
            if deleted:
                self.stdout.write(f"  {model.__name__}: {deleted}")
        Student.all_objects.all().delete()
        ActivityLog.objects.all().hard_delete() if hasattr(
            ActivityLog.objects.all(), "hard_delete"
        ) else None

    def _name(self, gender):
        first = self.rng.choice(
            FIRST_NAMES_F if gender == Gender.FEMALE else FIRST_NAMES_M
        )
        return f"{first} {self.rng.choice(LAST_NAMES)}"

    def _phone(self):
        return f"+92 3{self.rng.randint(0, 4)}{self.rng.randint(10**7, 10**8 - 1)}"

    def _cnic(self):
        return f"{self.rng.randint(10000, 99999)}-{self.rng.randint(1000000, 9999999)}-{self.rng.randint(0, 9)}"

    def _birthday(self, min_age, max_age):
        age = self.rng.randint(min_age, max_age)
        return self.today - dt.timedelta(days=age * 365 + self.rng.randint(0, 364))

    def _school_days(self, count):
        days = []
        day = self.today
        while len(days) < count:
            if day.weekday() < 5 and day.year == self.today.year:
                days.append(day)
            day -= dt.timedelta(days=1)
            if (self.today - day).days > 120:
                break
        return sorted(days)

    def _bump(self, key, amount=1):
        if amount:
            self.counts[key] = self.counts.get(key, 0) + amount

    def _report(self):
        self.stdout.write(self.style.MIGRATE_HEADING("\n== created =="))
        total = 0
        for key in sorted(self.counts):
            self.stdout.write(f"  {key:<28} {self.counts[key]:>7,}")
            total += self.counts[key]
        self.stdout.write(f"  {'TOTAL':<28} {total:>7,}")
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING("All of this is fictional demo data.")
        )
