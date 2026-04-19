import json
import os
import re

import httpx
from anthropic import Anthropic
from loguru import logger

from api_client import post_to_command, send_sms

_MODEL = "claude-haiku-4-5-20251001"
_SHOPIFY_API_VERSION = "2024-01"

_SYSTEM = """You are a Shopify product listing specialist for a dropshipping store called Sable Store.
Given a product name and optional market context, write a complete product listing.

Rules:
- Title: clear, specific, benefit-forward. Under 60 chars. No ALL CAPS. No generic phrases.
- body_html: 3-4 short paragraphs. Use <p> and <ul><li> tags only. No markdown. Highlight the problem solved, key features, who it's for.
- vendor: always "Sable Store"
- product_type: match the category (e.g. "Beauty Tools", "Fitness Equipment", "Pet Accessories")
- tags: comma-separated string, 6-8 tags including category, use case, and 2-3 long-tail keywords
- price: realistic retail price in USD as a string with no $ symbol (e.g. "34.99")
- compare_at_price: exactly 20% higher than price, rounded to .99 (e.g. "41.99")
- status: always "draft"

Respond ONLY in this JSON, no preamble, no markdown fences:
{
  "title": "string",
  "body_html": "string",
  "vendor": "Sable Store",
  "product_type": "string",
  "tags": "string",
  "price": "string",
  "compare_at_price": "string",
  "status": "draft"
}"""


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)


def _shopify_url() -> str:
    store = os.environ.get("SHOPIFY_STORE", "")
    version = os.environ.get("SHOPIFY_API_VERSION", _SHOPIFY_API_VERSION)
    return f"https://{store}/admin/api/{version}/products.json"


def _create_shopify_product(listing: dict) -> dict:
    token = os.environ.get("SHOPIFY_ACCESS_TOKEN", "")
    payload = {
        "product": {
            "title": listing["title"],
            "body_html": listing["body_html"],
            "vendor": listing.get("vendor", "Sable Store"),
            "product_type": listing.get("product_type", ""),
            "tags": listing.get("tags", ""),
            "status": listing.get("status", "draft"),
            "variants": [
                {
                    "price": listing["price"],
                    "compare_at_price": listing.get("compare_at_price", ""),
                    "inventory_management": None,
                    "fulfillment_service": "manual",
                }
            ],
        }
    }
    resp = httpx.post(
        _shopify_url(),
        json=payload,
        headers={
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("product", {})


class ShopifyAgent:
    def run(self, product_name: str, opportunity: dict | None = None) -> dict:
        logger.info(f"--- ShopifyAgent starting for: {product_name} ---")
        result: dict = {
            "product_name": product_name,
            "shopify_product_id": None,
            "shopify_product_url": None,
            "listing": {},
            "status": "error",
            "error": None,
        }

        store = os.environ.get("SHOPIFY_STORE", "")
        if not store:
            msg = "SHOPIFY_STORE not configured. Set it in Railway env vars.\n— Sable"
            send_sms(os.environ.get("ETHAN_PHONE_NUMBER", ""), msg)
            result["error"] = "SHOPIFY_STORE not set"
            return result

        try:
            user_payload = {
                "product_name": product_name,
                "opportunity_context": opportunity or {},
            }
            client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
            message = client.messages.create(
                model=_MODEL,
                max_tokens=800,
                system=_SYSTEM,
                messages=[{"role": "user", "content": json.dumps(user_payload)}],
            )
            listing = _parse_json(message.content[0].text)
            result["listing"] = listing

            shopify_product = _create_shopify_product(listing)
            product_id = str(shopify_product.get("id", ""))
            admin_url = f"https://{store}/admin/products/{product_id}"

            result["shopify_product_id"] = product_id
            result["shopify_product_url"] = admin_url
            result["status"] = "success"

            body = (
                f"Shopify product created (draft):\n"
                f"{listing['title']}\n"
                f"Price: ${listing['price']} (was ${listing.get('compare_at_price', '')})\n"
                f"Admin: {admin_url}\n\n"
                f"Text BRAND {product_name} to schedule social posts.\n— Sable"
            )

        except httpx.HTTPStatusError as exc:
            logger.error(f"Shopify API error: {exc.response.status_code} — {exc.response.text}")
            result["error"] = f"Shopify API {exc.response.status_code}"
            body = f"Shopify listing failed for '{product_name}' — API returned {exc.response.status_code}. Check token and store URL.\n— Sable"

        except (json.JSONDecodeError, KeyError) as exc:
            logger.error(f"ShopifyAgent listing parse failed: {exc}")
            result["error"] = str(exc)
            body = f"ShopifyAgent couldn't parse Claude's listing for '{product_name}'. Check Railway logs.\n— Sable"

        except Exception as exc:
            logger.error(f"ShopifyAgent failed: {exc}")
            result["error"] = str(exc)
            body = f"ShopifyAgent failed for '{product_name}': {exc}\n— Sable"

        send_sms(os.environ.get("ETHAN_PHONE_NUMBER", ""), body)
        post_to_command("shopify_agent", result)
        logger.info("--- ShopifyAgent complete ---")
        return result
