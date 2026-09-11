from django.urls import path

from . import views

app_name = "payroll"

urlpatterns = [
    path("components/", views.SalaryComponentListView.as_view(), name="component_list"),
    path("components/new/", views.SalaryComponentCreateView.as_view(), name="component_create"),
    path("components/<uuid:pk>/edit/", views.SalaryComponentUpdateView.as_view(), name="component_update"),

    path("structures/", views.SalaryStructureListView.as_view(), name="structure_list"),
    path("structures/new/", views.SalaryStructureCreateView.as_view(), name="structure_create"),
    path("structures/<uuid:pk>/", views.SalaryStructureDetailView.as_view(), name="structure_detail"),
    path("structures/<uuid:pk>/edit/", views.SalaryStructureUpdateView.as_view(), name="structure_update"),
    path("structures/lines/new/", views.StructureLineCreateView.as_view(), name="structureline_create"),

    path("salaries/", views.EmployeeSalaryListView.as_view(), name="salary_list"),
    path("salaries/new/", views.EmployeeSalaryCreateView.as_view(), name="salary_create"),
    path("salaries/<uuid:pk>/edit/", views.EmployeeSalaryUpdateView.as_view(), name="salary_update"),

    path("periods/", views.PayrollPeriodListView.as_view(), name="period_list"),
    path("periods/new/", views.PayrollPeriodCreateView.as_view(), name="period_create"),
    path("periods/<uuid:pk>/edit/", views.PayrollPeriodUpdateView.as_view(), name="period_update"),

    path("runs/", views.PayrollRunListView.as_view(), name="run_list"),
    path("runs/process/", views.ProcessPayrollView.as_view(), name="run_process"),
    path("runs/<uuid:pk>/", views.PayrollRunDetailView.as_view(), name="run_detail"),
    path("runs/<uuid:pk>/approve/", views.ApprovePayrollRunView.as_view(), name="run_approve"),

    path("items/<uuid:pk>/pay/", views.PaySalaryView.as_view(), name="item_pay"),
    path("payments/", views.SalaryPaymentListView.as_view(), name="payment_list"),
]
