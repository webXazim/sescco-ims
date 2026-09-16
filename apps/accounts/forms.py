from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm


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


class SesccoPasswordChangeForm(PasswordChangeForm):
    old_password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "input", "autocomplete": "current-password", "autofocus": True}),
    )
    new_password1 = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "input", "autocomplete": "new-password"}),
    )
    new_password2 = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "input", "autocomplete": "new-password"}),
    )
