from django.db import models
from django.utils import timezone



class SearchQuery(models.Model):
    query = models.CharField(max_length=200)
    timestamp = models.DateTimeField(default=timezone.now)
    results_file = models.CharField(max_length=200)
    results_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.query} - {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
