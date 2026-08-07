from __future__ import annotations

from django import forms

from .models import SavedView


class SavedViewCreateForm(forms.ModelForm):
    class Meta:
        model = SavedView
        fields = ("name",)
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "placeholder": "e.g. Aramco low stock",
                    "maxlength": 100,
                    "autocomplete": "off",
                }
            )
        }


class SavedViewRenameForm(forms.ModelForm):
    class Meta:
        model = SavedView
        fields = ("name",)
