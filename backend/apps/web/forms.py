from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class EmailAuthenticationForm(AuthenticationForm):
    """Lowercases the identifier so login matches RegisterForm's normalization."""

    def clean_username(self):
        return self.cleaned_data["username"].lower()


class RegisterForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
    password_confirm = forms.CharField(
        widget=forms.PasswordInput, label="Confirm password"
    )

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        confirm = cleaned.get("password_confirm")
        if password and confirm and password != confirm:
            self.add_error("password_confirm", "Passwords do not match.")
        if password:
            user = User(email=cleaned.get("email") or "")
            try:
                validate_password(password, user=user)
            except forms.ValidationError as exc:
                self.add_error("password", exc)
        return cleaned

    def save(self):
        return User.objects.create_user(
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password"],
        )
