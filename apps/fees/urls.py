from django.urls import path

from . import views

app_name = "fees"

urlpatterns = [
    path("types/", views.FeeTypeListView.as_view(), name="type_list"),
    path("types/new/", views.FeeTypeCreateView.as_view(), name="type_create"),
    path("types/<uuid:pk>/edit/", views.FeeTypeUpdateView.as_view(), name="type_update"),

    path("structures/", views.FeeStructureListView.as_view(), name="structure_list"),
    path("structures/new/", views.FeeStructureCreateView.as_view(), name="structure_create"),
    path("structures/<uuid:pk>/edit/", views.FeeStructureUpdateView.as_view(), name="structure_update"),

    path("student-fees/", views.StudentFeeListView.as_view(), name="studentfee_list"),
    path("student-fees/new/", views.StudentFeeCreateView.as_view(), name="studentfee_create"),
    path("student-fees/<uuid:pk>/edit/", views.StudentFeeUpdateView.as_view(), name="studentfee_update"),

    path("discounts/", views.DiscountListView.as_view(), name="discount_list"),
    path("discounts/new/", views.DiscountCreateView.as_view(), name="discount_create"),
    path("discounts/<uuid:pk>/edit/", views.DiscountUpdateView.as_view(), name="discount_update"),

    path("invoices/", views.InvoiceListView.as_view(), name="invoice_list"),
    path("invoices/generate/", views.InvoiceGenerateView.as_view(), name="invoice_generate"),
    path("invoices/<uuid:pk>/", views.InvoiceDetailView.as_view(), name="invoice_detail"),
    path("invoices/<uuid:pk>/waive/", views.InvoiceWaiveView.as_view(), name="invoice_waive"),

    path("payments/", views.PaymentListView.as_view(), name="payment_list"),
    path("payments/new/", views.PaymentCreateView.as_view(), name="payment_create"),
    path("payments/<uuid:pk>/", views.PaymentDetailView.as_view(), name="payment_detail"),
    path("payments/<uuid:pk>/refund/", views.PaymentRefundView.as_view(), name="payment_refund"),
    path("payments/<uuid:pk>/void/", views.PaymentVoidView.as_view(), name="payment_void"),

    path("refunds/", views.RefundListView.as_view(), name="refund_list"),
]
