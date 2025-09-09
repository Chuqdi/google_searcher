from django.contrib import admin
from .models import SearchQuery

@admin.register(SearchQuery)
class SearchQueryAdmin(admin.ModelAdmin):
    list_display = ('query', 'timestamp', 'results_count', 'results_file')
    list_filter = ('timestamp',)
    search_fields = ('query',)
    readonly_fields = ('timestamp',)