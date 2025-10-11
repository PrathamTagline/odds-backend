
from sports.models import Sport, Competition, Event
from django.db import transaction
from datetime import datetime


def save_tree_data(tree_data: dict):
    """
    Save tree data into Sport, Competition, and Event models.

    - Insert new data if not present.
    - If competitions/events are missing in new payload but exist in DB → delete them.
    - Never delete Sport records.
    - Update existing records if data has changed.
    """
    with transaction.atomic():
        sports_data = tree_data.get("data") or {}
        # ----------------- Handle T1 -----------------
        for sport_item in sports_data.get("t1") or []:
            sport, created = Sport.objects.get_or_create(
                event_type_id=sport_item.get("etid"),
                tree="t1",
                defaults={
                    "oid": sport_item.get("oid"),
                    "name": sport_item.get("name") or "",
                }
            )
            # Update fields if not created or if data changed
            sport.oid = sport_item.get("oid")
            sport.name = sport_item.get("name") or ""
            sport.save()

            # Track competitions seen in this payload
            seen_competition_ids = set()

            for comp_item in sport_item.get("children") or []:
                competition, created = Competition.objects.get_or_create(
                    competition_id=comp_item.get("cid"),
                    sport=sport,
                    defaults={
                        "competition_name": comp_item.get("name") or "",
                        "competition_region": comp_item.get("region") or "",
                    }
                )
                # Update fields
                competition.competition_name = comp_item.get("name") or ""
                competition.competition_region = comp_item.get("region") or ""
                competition.save()

                seen_competition_ids.add(competition.competition_id)

                # Track events seen under this competition
                seen_event_ids = set()

                for event_item in comp_item.get("children") or []:
                    event, created = Event.objects.get_or_create(
                        event_id=event_item.get("gmid"),
                        defaults={
                            "event_name": event_item.get("name") or "",
                            "sport": sport,
                            "competition": competition,
                        }
                    )
                    # Update fields
                    event.event_name = event_item.get("name") or ""
                    event.sport = sport
                    event.competition = competition
                    event.save()
                    seen_event_ids.add(event.event_id)

                # Delete missing events for this competition
                Event.objects.filter(competition=competition).exclude(event_id__in=seen_event_ids).delete()

            # Delete missing competitions (and cascade delete events)
            Competition.objects.filter(sport=sport).exclude(competition_id__in=seen_competition_ids).delete()

        # ----------------- Handle T2 -----------------
        for sport_item in sports_data.get("t2") or []:
            sport, created = Sport.objects.get_or_create(
                event_type_id=sport_item.get("etid"),
                tree="t2",
                defaults={
                    "oid": sport_item.get("oid"),
                    "name": sport_item.get("name") or "",
                }
            )
            # Update fields
            sport.oid = sport_item.get("oid")
            sport.name = sport_item.get("name") or ""
            sport.save()

            # Track events seen directly under sport
            seen_event_ids = set()

            for event_item in sport_item.get("children") or []:
                event_date = None
                sdatetime = event_item.get("sdatetime")
                if sdatetime:
                    try:
                        event_date = datetime.strptime(sdatetime, "%m/%d/%Y %I:%M:%S %p")
                    except Exception:
                        pass

                event, created = Event.objects.get_or_create(
                    event_id=event_item.get("gmid"),
                    defaults={
                        "event_name": event_item.get("name") or "",
                        "sport": sport,
                        "event_open_date": event_date,
                    }
                )
                # Update fields
                event.event_name = event_item.get("name") or ""
                event.sport = sport
                event.event_open_date = event_date
                event.save()
                seen_event_ids.add(event.event_id)

            # Delete missing events under this sport (T2 has no competitions)
            Event.objects.filter(sport=sport, competition__isnull=True).exclude(event_id__in=seen_event_ids).delete()
