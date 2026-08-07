from django import forms


class StyledFormMixin:
    """Apply the shared prototype controls without duplicating widget setup."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.HiddenInput):
                continue
            if isinstance(widget, forms.CheckboxInput):
                existing = widget.attrs.get("class", "")
                widget.attrs["class"] = f"{existing} checkbox".strip()
                continue
            if isinstance(widget, forms.CheckboxSelectMultiple):
                existing = widget.attrs.get("class", "")
                widget.attrs["class"] = f"{existing} checkbox-options".strip()
                continue
            if isinstance(widget, forms.Textarea):
                css_class = "textarea"
            elif isinstance(widget, forms.Select):
                css_class = "select"
            else:
                css_class = "input"
            existing = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{existing} {css_class}".strip()


class StyledForm(StyledFormMixin, forms.Form):
    pass


class StyledModelForm(StyledFormMixin, forms.ModelForm):
    pass
