from django.db import transaction
from django.db.models import Sum
from sports.models import Event, Competition
import json

def store_market_ids(event: Event, data: dict) -> None:
    """
    Extract all `mid` values from the given odds payload (any nesting level,
    including under 't1' and 't2'), and store them in the Event model.
    Also updates competition market count.
    """
    try:
        if not data:
            print(f"⚠️ Empty payload for event {event.event_name} ({event.event_id})")
            return

        # If data is a JSON string, decode it
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                print(f"⚠️ Invalid JSON for event {event.event_name}")
                return

        market_ids = []

        # ✅ Handle direct keys like t1, t2, etc.
        for key in ["t1", "t2", "data"]:
            section = data.get(key)
            if isinstance(section, list):
                for market in section:
                    if isinstance(market, dict):
                        mid = market.get("mid")
                        mname = market.get("mname")
                        if mid and mname:
                            market_ids.append({"marketId": str(mid), "marketName": mname})

        # ✅ Fallback: recursive search just in case
        def extract_markets(obj):
            if isinstance(obj, dict):
                mid = obj.get("mid")
                mname = obj.get("mname")
                if mid and mname:
                    market_ids.append({"marketId": str(mid), "marketName": mname})
                for v in obj.values():
                    extract_markets(v)
            elif isinstance(obj, list):
                for item in obj:
                    extract_markets(item)

        extract_markets(data)

        # Remove duplicates based on marketId
        seen = set()
        unique_markets = []
        for market in market_ids:
            mid = market["marketId"]
            if mid not in seen:
                seen.add(mid)
                unique_markets.append(market)

        market_ids = unique_markets
        print(f"✅ Extracted market IDs for event {event.event_name}: {market_ids}")

        # ✅ Save to DB
        with transaction.atomic():
            event.market_ids = market_ids
            event.market_count = len(market_ids)
            event.save()

            # ✅ Update related competition with total market count
            if event.competition_id:
                total_markets = Event.objects.filter(
                    competition_id=event.competition_id
                ).aggregate(total=Sum("market_count"))["total"] or 0

                Competition.objects.filter(id=event.competition_id).update(
                    market_count=total_markets
                )

        print(f"✅ Stored {len(market_ids)} market IDs for event {event.event_name} ({event.event_id})")

    except Exception as e:
        print(f"⚠️ Error extracting & saving mids for event {event.id}: {e}")
        import traceback
        print(traceback.format_exc())
