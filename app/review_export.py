def bulk_review_export(listings, payload_builder):
    items = [payload_builder(row) for row in listings]
    return {
        "schema_version": 1,
        "count": len(items),
        "items": items,
    }
