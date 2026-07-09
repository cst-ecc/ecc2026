from rest_framework.pagination import PageNumberPagination


class PaginationStandard(PageNumberPagination):
    """Pagination par défaut pour les nouvelles apps — mêmes réglages que
    REST_FRAMEWORK.DEFAULT_PAGINATION_CLASS (settings.py, 50/page), mais
    nommée et centralisée ici plutôt que répétée en dur à chaque vue.
    Autorise ?page_size=... jusqu'à 200, pour les cas où le frontend a
    besoin de récupérer davantage d'éléments en une fois (ex: export,
    liste déroulante longue) sans changer la valeur par défaut partout.
    """

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
