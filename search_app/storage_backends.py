# search_app/storage_backends.py

from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings

class SearchResultsStorage(S3Boto3Storage):
    """Custom storage backend for search results"""
    bucket_name = settings.AWS_STORAGE_BUCKET_NAME
    location = 'search_results'  # This creates a folder structure in S3
    default_acl = 'private'  # Keep search results private
    file_overwrite = False  # Don't overwrite existing files
    custom_domain = False  # Use S3 URLs instead of custom domain for security

class PublicSearchResultsStorage(S3Boto3Storage):
    """Public storage backend for search results (if you want them accessible via URL)"""
    bucket_name = settings.AWS_STORAGE_BUCKET_NAME
    location = 'search_results'
    default_acl = 'public-read'  # Make files publicly accessible
    file_overwrite = False
    custom_domain = settings.AWS_S3_CUSTOM_DOMAIN