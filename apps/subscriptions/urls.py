from django.urls import path

from . import views

app_name = "subscriptions"

urlpatterns = [
    path("", views.SubscriptionDetailView.as_view(), name="detail"),
    path("invoices/", views.SubscriptionInvoiceListView.as_view(), name="invoice_list"),
]
