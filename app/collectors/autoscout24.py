import os

class AutoScout24Collector:
    name = "AutoScout24"

    @property
    def configured(self) -> bool:
        return bool(os.getenv("AUTOSCOUT24_API_URL") and os.getenv("AUTOSCOUT24_API_TOKEN"))

    def search(self, criteria, page: int = 1, page_size: int = 50) -> list[dict]:
        """Adapter shell for AutoScout24 Search API.

        AutoScout24's Search API is a contract-gated GraphQL service. The exact
        schema/endpoint is supplied with the account. We keep the adapter ready
        and activate it once AUTOSCOUT24_API_URL/TOKEN are available.
        """
        if not self.configured:
            return []
        raise NotImplementedError(
            "AutoScout24 Search API credentials are configured, but the account-specific GraphQL schema still needs mapping."
        )
