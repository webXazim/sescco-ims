from django import forms
from django.contrib.auth.forms import AuthenticationForm


class InventoryAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(
            attrs={"class": "input", "autocomplete": "username", "autofocus": True}
        )
    )
    password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(
            attrs={"class": "input", "autocomplete": "current-password"}
        ),
    )
