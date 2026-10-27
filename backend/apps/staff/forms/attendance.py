from django import forms


class StaffAttendanceActionForm(forms.Form):
    note = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "staff-input",
                "placeholder": "Optional note",
            }
        ),
    )


class StaffAttendanceReviewForm(forms.Form):
    action = forms.ChoiceField(
        choices=[
            ("approve", "Approve"),
            ("correct", "Correct and approve"),
        ],
    )
    clock_in_at = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(
            attrs={"class": "staff-input", "type": "datetime-local"}
        ),
    )
    clock_out_at = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(
            attrs={"class": "staff-input", "type": "datetime-local"}
        ),
    )
    review_note = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"class": "staff-input", "rows": 2}),
    )

    def clean(self):
        data = super().clean()
        if data.get("action") == "correct":
            if not data.get("clock_in_at") or not data.get("clock_out_at"):
                raise forms.ValidationError(
                    "Correction requires both clock-in and clock-out times."
                )
            if data["clock_out_at"] <= data["clock_in_at"]:
                raise forms.ValidationError(
                    "Clock-out must be after clock-in."
                )
            if len((data.get("review_note") or "").strip()) < 4:
                raise forms.ValidationError(
                    "Explain the correction in at least 4 characters."
                )
        return data
