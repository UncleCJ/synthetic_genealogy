"""
The Archives view (archives.html), written from the volume rows that
volumes.py builds: parishes, their volumes by series, every volume as a
page strip with the people cited on it, and the farms most cited. Private
(holds names). The rows and their columns: docs/records.md, "Views".
"""
from sg.common import lineage
from sg.views import viewkit


def write(rows, parishes, path, proband_label):
    """The Archives view (archives.html), one self-contained page, private
    (holds names; keep it in data/): parishes with their archive codes on a
    map and in a list, each parish's volumes by series, every volume as a
    page strip with the people cited on each page, and the farms most cited
    across volumes. A chosen parish zooms the map onto its farms and
    villages; a volume's "map" button shows its farms coloured by page, so
    the order the book walks through the parish can be seen. Linked both
    ways with the geography view."""
    keep = ["person", "label", "kin", "branch", "lineage", "event", "event_date",
            "event_place", "tier", "resourced", "parish", "archive_code", "volume",
            "series", "vol", "years", "page", "row", "farm", "plac_detail", "image_id", "image_no",
            "url", "source_title", "mh_volume", "conflict", "ra_code", "code_from", "series_name",
            "place_id", "place", "village", "place_from", "notes", "errata", "mh_id",
            "ra_years", "ra_note", "ra_viewer", "ra_images", "ra_nad", "ra_pages", "ra_image_count", "ra_status", "cited_as", "lat", "lon", "lv"]
    data = [{k: r.get(k, "") or "" for k in keep} for r in rows if r["tier"] != "tree"]
    page = viewkit.embed(HTML.replace("__NAV__", viewkit.nav("archives.html")).replace("__FOLDJS__", viewkit.FOLD_JS + viewkit.OFFLINE_JS),
                         dict(rows=data, parishes=parishes, proband=proband_label))
    path.write_text(page, encoding="utf-8")


HTML = viewkit.template("archives")
HTML = HTML.replace("__LINEAGE_DARK__", lineage.css_vars(dark=True)).replace("__LINEAGE__", lineage.css_vars())
