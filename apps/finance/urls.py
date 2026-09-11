from django.urls import path

from . import views

app_name = "finance"

urlpatterns = [
    path("accounts/", views.AccountListView.as_view(), name="account_list"),
    path("accounts/new/", views.AccountCreateView.as_view(), name="account_create"),
    path("accounts/<uuid:pk>/edit/", views.AccountUpdateView.as_view(), name="account_update"),

    path("account-types/", views.AccountTypeListView.as_view(), name="accounttype_list"),
    path("account-types/new/", views.AccountTypeCreateView.as_view(), name="accounttype_create"),
    path("account-types/<uuid:pk>/edit/", views.AccountTypeUpdateView.as_view(), name="accounttype_update"),

    path("journals/", views.JournalListView.as_view(), name="journal_list"),
    path("journals/new/", views.JournalCreateView.as_view(), name="journal_create"),
    path("journals/<uuid:pk>/edit/", views.JournalUpdateView.as_view(), name="journal_update"),

    path("entries/", views.JournalEntryListView.as_view(), name="entry_list"),
    path("entries/new/", views.JournalEntryCreateView.as_view(), name="entry_create"),
    path("entries/<uuid:pk>/", views.JournalEntryDetailView.as_view(), name="entry_detail"),
    path("entries/<uuid:pk>/reverse/", views.JournalEntryReverseView.as_view(), name="entry_reverse"),

    path("periods/", views.FiscalPeriodListView.as_view(), name="period_list"),
    path("periods/new/", views.FiscalPeriodCreateView.as_view(), name="period_create"),
    path("periods/<uuid:pk>/edit/", views.FiscalPeriodUpdateView.as_view(), name="period_update"),
    path("periods/<uuid:pk>/close/", views.FiscalPeriodCloseView.as_view(), name="period_close"),

    path("payment-methods/", views.PaymentMethodListView.as_view(), name="method_list"),
    path("payment-methods/new/", views.PaymentMethodCreateView.as_view(), name="method_create"),
    path("payment-methods/<uuid:pk>/edit/", views.PaymentMethodUpdateView.as_view(), name="method_update"),

    path("trial-balance/", views.TrialBalanceView.as_view(), name="trial_balance"),
]
