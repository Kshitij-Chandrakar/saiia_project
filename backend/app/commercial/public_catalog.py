"""Anonymous safe projection over the dedicated read-only catalog channel."""

import json
import logging

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from app.commercial import catalog_contract as c
from app.commercial.payable import payable

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/api/catalog")
def public_catalog(request: Request):
    headers = {"Cache-Control": "no-store"}
    conn = None
    try:
        conn = request.app.state.catalog_public.connect()
        conn.execute("SET TRANSACTION READ ONLY")
        row = conn.execute("SELECT public.catalog_public_read()").fetchone()[0]
        offers = []
        payable_prices = {}
        from app.answer_models import MODEL_CATALOG

        if not row or not isinstance(row["offers"], list):
            raise ValueError()
        for item in row["offers"]:
            raw = json.loads(item["snapshot"])
            if raw.get("contract_version") not in {
                "catalog.v1",
                "catalog.v2",
                "catalog.v3",
            }:
                continue  # Unsupported future versions are never advertised.
            raw["eligible_model_keys"] = tuple(sorted(MODEL_CATALOG))
            snapshot = c.OfferSnapshot.model_validate(raw)
            if (
                snapshot.fingerprint != item["fingerprint"]
                or snapshot.canonical_json() != item["snapshot"]
            ):
                raise ValueError()
            offer = c.public_projection(
                snapshot,
                c.Visibility.model_validate(item["visibility"]),
                at=c._instant(row["at"]),
            )
            if offer is not None:
                offers.append(offer.model_dump(mode="json"))
                for price in snapshot.terms.prices:
                    if getattr(snapshot.terms, "pricing_mode", None) == "priced":
                        try:
                            payable_prices[price.price_id] = payable(
                                snapshot, price.price_id
                            )
                        except ValueError:
                            continue  # Unsupported future rounding never invents a quote.
        conn.commit()
        return JSONResponse(
            {
                "catalog_revision": str(row["revision"]),
                "offers": offers,
                "payable_prices": payable_prices,
            },
            headers=headers,
        )
    except Exception:
        logger.exception("Public catalog unavailable", exc_info=False)
        return JSONResponse(
            {"detail": {"code": "catalog_unavailable"}},
            status_code=503,
            headers=headers,
        )
    finally:
        if conn is not None:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                logger.exception(
                    "Public catalog connection cleanup failed", exc_info=False
                )
