"""One-time merchant-side setup for Phase 15's PayPal billing: creates the Own Hardware
Catalog Product and Billing Plan in your sandbox account, then prints the plan ID to put
in .env as PAYPAL_OWN_HARDWARE_PLAN_ID. Not part of the running app — run this once
(re-run it if you ever want a new plan, e.g. once a real, non-placeholder price is
decided; PayPal plans are immutable once created).

Requires PAYPAL_CLIENT_ID/PAYPAL_CLIENT_SECRET already set in .env.

Usage (from backend/, with the venv active):
    python scripts/setup_paypal_plan.py
    python scripts/setup_paypal_plan.py --price 29.99   # override the placeholder price
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import paypal_client  # noqa: E402
from app.config import get_settings  # noqa: E402

# SANDBOX PLACEHOLDER — not a real, decided price. See docs/ROADMAP.md's Phase 15 entry:
# Own Hardware's actual price is a separate business decision, still pending.
PLACEHOLDER_MONTHLY_PRICE_USD = "19.99"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--price",
        default=PLACEHOLDER_MONTHLY_PRICE_USD,
        help=f"Monthly price in USD (default: {PLACEHOLDER_MONTHLY_PRICE_USD}, a sandbox placeholder)",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.paypal_client_id or not settings.paypal_client_secret:
        print("PAYPAL_CLIENT_ID/PAYPAL_CLIENT_SECRET must be set in .env first.", file=sys.stderr)
        sys.exit(1)

    print(f"Creating product against {settings.paypal_api_base} ...")
    product = paypal_client.create_product(
        name="Vero.ai — Own Hardware",
        description="Vero.ai Own Hardware plan: local AI processing, cloud-synced accounts/analytics.",
    )
    print(f"  Product created: {product['id']}")

    print(f"Creating plan at ${args.price}/month (SANDBOX PLACEHOLDER unless overridden) ...")
    plan = paypal_client.create_plan(
        product_id=product["id"], name="Vero.ai Own Hardware — Monthly", monthly_price_usd=args.price
    )
    print(f"  Plan created: {plan['id']}")
    print()
    print("Add this to your .env:")
    print(f"PAYPAL_OWN_HARDWARE_PLAN_ID={plan['id']}")


if __name__ == "__main__":
    main()
