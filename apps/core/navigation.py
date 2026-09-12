"""The sidebar, declared once.

Each entry names the permission that reveals it, so the menu and the view
enforce the same rule and cannot drift apart.
"""

from django.utils.translation import gettext_lazy as _

from .permissions import user_has_permission

NAVIGATION = [
    {"label": _("Dashboard"), "url_name": "core:dashboard", "icon": "bi-grid-1x2", "permission": "core.access_dashboard"},
    {"label": _("Academics"), "icon": "bi-journal-bookmark", "permission": "core.access_academics", "children": [
        {"label": _("Overview"), "url_name": "academics:overview"},
        {"label": _("Academic Years"), "url_name": "academics:year_list"},
        {"label": _("Terms"), "url_name": "academics:term_list"},
        {"label": _("Classes & Sections"), "url_name": "academics:class_list"},
        {"label": _("Subjects"), "url_name": "academics:subject_list"},
        {"label": _("Class Subjects"), "url_name": "academics:classsubject_list"},
        {"label": _("Teacher Assignments"), "url_name": "academics:assignment_list"},
        {"label": _("Timetable"), "url_name": "academics:timetable"},
    ]},
    {"label": _("Students"), "icon": "bi-people", "permission": "core.access_students", "children": [
        {"label": _("All Students"), "url_name": "students:student_list"},
        {"label": _("Admission"), "url_name": "students:student_create"},
        {"label": _("Guardians"), "url_name": "students:guardian_list"},
        {"label": _("Enrollments"), "url_name": "students:enrollment_list"},
    ]},
    {"label": _("Staff"), "icon": "bi-person-badge", "permission": "core.access_staff", "children": [
        {"label": _("All Staff"), "url_name": "staff:staff_list"},
        {"label": _("Departments"), "url_name": "staff:department_list"},
        {"label": _("Designations"), "url_name": "staff:designation_list"},
    ]},
    {"label": _("ID Cards"), "icon": "bi-person-vcard", "children": [
        {"label": _("Student Cards"), "url_name": "core:student_cards", "permission": "core.access_students"},
        {"label": _("Staff Cards"), "url_name": "core:staff_cards", "permission": "core.access_staff"},
    ]},
    {"label": _("Attendance"), "icon": "bi-calendar-check", "permission": "core.access_attendance", "children": [
        {"label": _("Today's Classes"), "url_name": "attendance:today"},
        {"label": _("Mark Attendance"), "url_name": "attendance:mark"},
        {"label": _("Attendance Sessions"), "url_name": "attendance:session_list"},
        {"label": _("Student Records"), "url_name": "attendance:record_list"},
        {"label": _("Check In / Out"), "url_name": "attendance:clock"},
        {"label": _("Staff Attendance"), "url_name": "attendance:staff_list"},
        {"label": _("Staff Monthly Report"), "url_name": "attendance:staff_month"},
    ]},
    {"label": _("Hifz"), "icon": "bi-book", "permission": "core.access_hifz", "children": [
        {"label": _("Hifz Students"), "url_name": "hifz:profile_list"},
        {"label": _("Daily Progress"), "url_name": "hifz:progress_list"},
        {"label": _("Assessments"), "url_name": "hifz:assessment_list"},
    ]},
    {"label": _("Fees"), "icon": "bi-receipt", "permission": "core.access_fees", "children": [
        {"label": _("Fee Types"), "url_name": "fees:type_list"},
        {"label": _("Fee Structures"), "url_name": "fees:structure_list"},
        {"label": _("Invoices"), "url_name": "fees:invoice_list"},
        {"label": _("Collect Payment"), "url_name": "fees:payment_create"},
        {"label": _("Payments"), "url_name": "fees:payment_list"},
    ]},
    {"label": _("Finance"), "icon": "bi-bank", "permission": "core.access_finance", "children": [
        {"label": _("Chart of Accounts"), "url_name": "finance:account_list"},
        {"label": _("Journals"), "url_name": "finance:journal_list"},
        {"label": _("Entries"), "url_name": "finance:entry_list"},
        {"label": _("Fiscal Periods"), "url_name": "finance:period_list"},
        {"label": _("Trial Balance"), "url_name": "finance:trial_balance"},
    ]},
    {"label": _("Payroll"), "icon": "bi-cash-stack", "permission": "core.access_payroll", "children": [
        {"label": _("Salary Components"), "url_name": "payroll:component_list"},
        {"label": _("Salary Structures"), "url_name": "payroll:structure_list"},
        {"label": _("Payroll Periods"), "url_name": "payroll:period_list"},
        {"label": _("Payroll Runs"), "url_name": "payroll:run_list"},
    ]},
    {"label": _("Exams"), "icon": "bi-mortarboard", "permission": "core.access_exams", "children": [
        {"label": _("Exam Terms"), "url_name": "exams:term_list"},
        {"label": _("Exams"), "url_name": "exams:exam_list"},
        {"label": _("Grading Scale"), "url_name": "exams:grade_list"},
        {"label": _("Results"), "url_name": "exams:result_list"},
    ]},
    {"label": _("Parents"), "icon": "bi-person-hearts", "permission": "core.access_parents", "children": [{"label": _("Parent Accounts"), "url_name": "parents:guardian_list"}]},
    {"label": _("Notifications"), "url_name": "notifications:list", "icon": "bi-bell", "permission": "core.access_notifications"},
    {"label": _("Reports"), "url_name": "reports:index", "icon": "bi-bar-chart-line", "permission": "core.access_reports"},
    {"label": _("Subscription"), "url_name": "subscriptions:detail", "icon": "bi-box-seam", "permission": "core.access_subscriptions"},
    {"label": _("Audit Log"), "url_name": "audit:list", "icon": "bi-shield-check", "permission": "core.access_audit"},
    {"label": _("Settings"), "icon": "bi-gear", "permission": "core.access_settings", "children": [
        {"label": _("Branches"), "url_name": "tenants:branch_list"},
        {"label": _("Users"), "url_name": "accounts:user_list"},
        {"label": _("Roles"), "url_name": "accounts:role_list"},
    ]},
]

PARENT_NAVIGATION = [
    {"label": _("My Children"), "url_name": "parents:portal_home", "icon": "bi-person-hearts", "permission": "core.access_parents"},
    {"label": _("Notifications"), "url_name": "notifications:list", "icon": "bi-bell", "permission": "core.access_notifications"},
]


def _resolve(url_name):
    from django.urls import NoReverseMatch, reverse
    if not url_name:
        return ""
    try:
        return reverse(url_name)
    except NoReverseMatch:
        return ""


def visible_navigation(user, branch=None, current_path=""):
    if user is None or not getattr(user, "is_authenticated", False):
        return []
    source = NAVIGATION if not getattr(user, "is_parent_account", False) else PARENT_NAVIGATION
    visible = []
    for item in source:
        permission = item.get("permission")
        if permission and not user_has_permission(user, permission, branch):
            continue
        entry = {k: v for k, v in item.items() if k != "children"}
        entry["url"] = _resolve(item.get("url_name"))
        entry["is_current"] = bool(entry["url"]) and entry["url"] == current_path
        children = []
        for child in item.get("children", ()):
            child_permission = child.get("permission")
            if child_permission and not user_has_permission(user, child_permission, branch):
                continue
            url = _resolve(child.get("url_name"))
            if not url:
                continue
            children.append({**child, "url": url, "is_current": url == current_path})
        if item.get("children") and not children:
            continue
        if children:
            entry["children"] = children
            entry["is_open"] = any(child["is_current"] for child in children) or any(current_path.startswith(child["url"]) for child in children)
        visible.append(entry)
    return visible
