from django import forms

class SearchForm(forms.Form):
    query = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your search query...',
            'required': True
        })
    )