# Load a licensed map extract

1. Obtain an OSM extract for the study area and record its date and source. Preserve original tags, feature identity and provenance. Follow OpenStreetMap's ODbL requirements when distributing derivatives. Keep proprietary or restricted source layers separate.
2. Load the extract into a staging database using osm2pgsql. Select explicit observations such as traffic_sign nodes, highway=traffic_signals nodes and highway=crossing nodes. Review how the source represents speed limits. A signed speed limit and a road's maxspeed tag describe different entities and should not be matched solely by proximity.
3. Normalize supported point candidates to a JSON array with id, kind, east and north in EPSG:26916, and integer value for speed limits. Preserve the extract date outside the list. Use ogr2ogr to import Chicago road centerlines to a staging table, transform to EPSG:26916 and populate road_centerlines.
4. Supply the normalized JSON to the live pipeline. Check candidate matches in the map context before accepting. The SQL views expose nearest matching baseline features and snapped road points for diagnostics.

[OpenStreetMap attribution and licensing](https://www.openstreetmap.org/copyright) · [osm2pgsql manual](https://osm2pgsql.org/doc/manual.html) · [Chicago data portal](https://data.cityofchicago.org/)
