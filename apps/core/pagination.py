from rest_framework.pagination import LimitOffsetPagination, PageNumberPagination


class DynamicPagination(LimitOffsetPagination):
    page_size = 10  # Default page size
    limit_query_param = 'limit'
    offset_query_param = 'offset'
    max_limit = 100
    page_query_param = 'page'
    
class StaticPagination(PageNumberPagination):
    page_size = 10  # Default page size
    page_size_query_param = 'page_size'  # Allows client to override via `?page_size=xxx`
    max_page_size = 100  # Maximum limit for page_size
    page_query_param = 'page'