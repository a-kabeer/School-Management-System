"""One modal workflow for the whole application.

A create, edit or quick view that fits in a dialog should not cost the reader
their place. These views answer the *same* URL two ways: as a full page for a
direct visit or a bookmark, and as a fragment when the page asks for one. The
form, its validation and its permissions are identical either way — only the
chrome differs — so there is no second implementation to keep in step.

On success the fragment answers ``204 No Content`` with a header rather than a
redirect: the page underneath decides what to do next. A quick-add started
from a combo box selects the record it just created; anything else reloads.
"""

from urllib.parse import quote

from django.http import HttpResponse

#: Request marker: the page is asking for a fragment, not a page.
MODAL_REQUEST_HEADER = "X-Modal"
#: Response markers the page reads after a successful save.
MODAL_SUCCESS_HEADER = "X-Modal-Success"
MODAL_OBJECT_ID_HEADER = "X-Modal-Object-Id"
MODAL_OBJECT_LABEL_HEADER = "X-Modal-Object-Label"


def wants_modal(request):
    """Whether this request came from the modal rather than the address bar."""
    return (
        request.headers.get(MODAL_REQUEST_HEADER) == "1"
        or request.GET.get("modal") == "1"
    )


def modal_success(obj=None):
    """The empty response that tells the page a modal save succeeded."""
    response = HttpResponse(status=204)
    response[MODAL_SUCCESS_HEADER] = "1"
    if obj is not None:
        response[MODAL_OBJECT_ID_HEADER] = str(obj.pk)
        # Headers are latin-1; a name in Urdu or Arabic has to travel encoded.
        response[MODAL_OBJECT_LABEL_HEADER] = quote(str(obj))
    return response


class ModalFormMixin:
    """Lets a create/update view render inside the shared modal."""

    modal_template_name = "components/modal_form.html"

    @property
    def in_modal(self):
        return wants_modal(self.request)

    def get_template_names(self):
        if self.in_modal:
            return [self.modal_template_name]
        return super().get_template_names()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["in_modal"] = self.in_modal
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        if not self.in_modal:
            return response
        # The redirect the page version would follow is meaningless inside a
        # dialog; the caller decides where to go instead.
        return modal_success(getattr(self, "object", None))


class ModalDetailMixin:
    """Lets a detail view render as a quick look inside the shared modal."""

    modal_template_name = None

    @property
    def in_modal(self):
        return wants_modal(self.request)

    def get_template_names(self):
        if self.in_modal and self.modal_template_name:
            return [self.modal_template_name]
        return super().get_template_names()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["in_modal"] = self.in_modal
        return context
