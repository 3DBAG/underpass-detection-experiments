#!/usr/bin/env bash
set -euo pipefail

DB_NAME="${DB_NAME:-baseregisters}"
SCHEMA_NAME="${SCHEMA_NAME:-underpasses}"
TABLE_NAME="${TABLE_NAME:-extended_geometries}"
REPORT_FILE="${REPORT_FILE:-report.md}"
RUN_NUMBER="${RUN_NUMBER:-}"
RUN_DATE="${RUN_DATE:-$(date +%F)}"

if ! command -v psql >/dev/null 2>&1; then
  echo "error: psql is not available on PATH" >&2
  exit 1
fi

if [[ ! -f "$REPORT_FILE" ]]; then
  echo "error: report file not found: $REPORT_FILE" >&2
  exit 1
fi

if [[ -z "$RUN_NUMBER" ]]; then
  last_run="$(
    grep -E '^### Run [0-9]+ Coverage' "$REPORT_FILE" \
      | sed -E 's/^### Run ([0-9]+) Coverage.*$/\1/' \
      | sort -n \
      | tail -n 1 \
      || true
  )"
  if [[ -z "$last_run" ]]; then
    RUN_NUMBER=1
  else
    RUN_NUMBER=$((last_run + 1))
  fi
fi

PSQL=(psql -X -v ON_ERROR_STOP=1 -d "$DB_NAME")
TABLE_REF="${SCHEMA_NAME}.${TABLE_NAME}"

query() {
  "${PSQL[@]}" -At -F $'\t' -c "$1"
}

append_query_table() {
  local sql="$1"
  query "$sql" | while IFS=$'\t' read -r -a cols; do
    printf '|'
    for col in "${cols[@]}"; do
      printf ' %s |' "${col:-null}"
    done
    printf '\n'
  done
}

tmp_file="$(mktemp)"
trap 'rm -f "$tmp_file"' EXIT

{
  printf '\n### Run %s Coverage - %s\n\n' "$RUN_NUMBER" "$RUN_DATE"
  printf '| Metric | Count |\n'
  printf '|---|---:|\n'
  append_query_table "
    WITH metrics(label, value, ord) AS (
      SELECT 'Total rows', count(*), 1 FROM ${TABLE_REF}
      UNION ALL
      SELECT 'Processed rows', count(*), 2 FROM ${TABLE_REF}
        WHERE underpass_source IS NOT NULL OR underpass_status IS NOT NULL
      UNION ALL
      SELECT 'Streetlidar success', count(*), 3 FROM ${TABLE_REF}
        WHERE underpass_source = 'streetlidar' AND underpass_status = 'success'
      UNION ALL
      SELECT 'Fallback rows', count(*), 4 FROM ${TABLE_REF}
        WHERE underpass_source = 'fallback'
      UNION ALL
      SELECT 'Still placeholder/null', count(*), 5 FROM ${TABLE_REF}
        WHERE underpass_source IS NULL AND underpass_status IS NULL
    )
    SELECT label, to_char(value, 'FM999,999,999,999')
    FROM metrics
    ORDER BY ord;
  "
  placeholder_count="$(query "
    SELECT to_char(count(*), 'FM999,999,999,999')
    FROM ${TABLE_REF}
    WHERE underpass_source IS NULL AND underpass_status IS NULL;
  ")"
  printf '\nThe %s unprocessed/placeholder rows have underpass_source/status still null.\n\n' "$placeholder_count"

  printf '### Status Counts\n\n'
  printf '| source | status | rows | z median | point median |\n'
  printf '|---|---|---:|---:|---:|\n'
  append_query_table "
    SELECT
      coalesce(underpass_source, 'null') AS source,
      coalesce(underpass_status, 'null') AS status,
      to_char(count(*), 'FM999,999,999,999') AS rows,
      coalesce(trim(to_char(round((percentile_cont(0.5) WITHIN GROUP (ORDER BY underpass_z))::numeric, 3), 'FM999,999,999,990.999')), 'null') AS z_median,
      coalesce(to_char(round((percentile_cont(0.5) WITHIN GROUP (ORDER BY underpass_point_count))::numeric), 'FM999,999,999,999'), 'null') AS point_median
    FROM ${TABLE_REF}
    GROUP BY underpass_source, underpass_status
    ORDER BY count(*) DESC, source, status;
  "

  printf '\n### Common Errors\n\n'
  printf '| status | error group | rows |\n'
  printf '|---|---|---:|\n'
  append_query_table "
    WITH grouped AS (
      SELECT
        coalesce(underpass_status, 'null') AS status,
        CASE
          WHEN underpass_error ~ '^Only [0-9]+ points inside polygon; minimum is [0-9]+$'
            THEN regexp_replace(underpass_error, '^Only [0-9]+ points inside polygon; minimum is ([0-9]+)$', 'Too few points inside polygon <\1')
          WHEN underpass_error ~ '^Selected more than [0-9]+ points$'
            THEN regexp_replace(underpass_error, '^Selected more than ([0-9]+) points$', 'Selected more than \1 points')
          ELSE coalesce(nullif(underpass_error, ''), 'null')
        END AS error_group
      FROM ${TABLE_REF}
      WHERE underpass_error IS NOT NULL OR underpass_status <> 'success'
    )
    SELECT status, error_group, to_char(count(*), 'FM999,999,999,999') AS rows
    FROM grouped
    GROUP BY status, error_group
    ORDER BY count(*) DESC, status, error_group;
  "

  printf '\n### Point Count Histogram\n\n'
  printf '| point count | rows | success | other |\n'
  printf '|---|---:|---:|---:|\n'
  append_query_table "
    WITH bucketed AS (
      SELECT
        CASE
          WHEN underpass_point_count IS NULL THEN 1
          WHEN underpass_point_count = 0 THEN 2
          WHEN underpass_point_count BETWEEN 1 AND 99 THEN 3
          WHEN underpass_point_count BETWEEN 100 AND 999 THEN 4
          WHEN underpass_point_count BETWEEN 1000 AND 9999 THEN 5
          WHEN underpass_point_count BETWEEN 10000 AND 99999 THEN 6
          WHEN underpass_point_count BETWEEN 100000 AND 999999 THEN 7
          WHEN underpass_point_count BETWEEN 1000000 AND 4999999 THEN 8
          ELSE 9
        END AS ord,
        CASE
          WHEN underpass_point_count IS NULL THEN 'null'
          WHEN underpass_point_count = 0 THEN '0'
          WHEN underpass_point_count BETWEEN 1 AND 99 THEN '1-99'
          WHEN underpass_point_count BETWEEN 100 AND 999 THEN '100-999'
          WHEN underpass_point_count BETWEEN 1000 AND 9999 THEN '1k-10k'
          WHEN underpass_point_count BETWEEN 10000 AND 99999 THEN '10k-100k'
          WHEN underpass_point_count BETWEEN 100000 AND 999999 THEN '100k-1M'
          WHEN underpass_point_count BETWEEN 1000000 AND 4999999 THEN '1M-5M'
          ELSE '>=5M'
        END AS bucket,
        underpass_source = 'streetlidar' AND underpass_status = 'success' AS success
      FROM ${TABLE_REF}
    )
    SELECT
      bucket,
      to_char(count(*), 'FM999,999,999,999'),
      to_char(count(*) FILTER (WHERE success), 'FM999,999,999,999'),
      to_char(count(*) FILTER (WHERE success IS NOT TRUE), 'FM999,999,999,999')
    FROM bucketed
    GROUP BY ord, bucket
    ORDER BY ord;
  "

  printf '\n### Success-only point count quantiles\n\n'
  printf '| Quantile | Value |\n'
  printf '|---|---:|\n'
  append_query_table "
    WITH success AS (
      SELECT underpass_point_count::numeric AS value
      FROM ${TABLE_REF}
      WHERE underpass_source = 'streetlidar'
        AND underpass_status = 'success'
        AND underpass_point_count IS NOT NULL
    ),
    metrics(label, value, ord) AS (
      SELECT 'min', min(value), 1 FROM success
      UNION ALL SELECT 'p01', percentile_cont(0.01) WITHIN GROUP (ORDER BY value), 2 FROM success
      UNION ALL SELECT 'p05', percentile_cont(0.05) WITHIN GROUP (ORDER BY value), 3 FROM success
      UNION ALL SELECT 'p10', percentile_cont(0.10) WITHIN GROUP (ORDER BY value), 4 FROM success
      UNION ALL SELECT 'p25', percentile_cont(0.25) WITHIN GROUP (ORDER BY value), 5 FROM success
      UNION ALL SELECT 'median', percentile_cont(0.50) WITHIN GROUP (ORDER BY value), 6 FROM success
      UNION ALL SELECT 'p75', percentile_cont(0.75) WITHIN GROUP (ORDER BY value), 7 FROM success
      UNION ALL SELECT 'p90', percentile_cont(0.90) WITHIN GROUP (ORDER BY value), 8 FROM success
      UNION ALL SELECT 'p95', percentile_cont(0.95) WITHIN GROUP (ORDER BY value), 9 FROM success
      UNION ALL SELECT 'p99', percentile_cont(0.99) WITHIN GROUP (ORDER BY value), 10 FROM success
      UNION ALL SELECT 'max', max(value), 11 FROM success
      UNION ALL SELECT 'avg', avg(value), 12 FROM success
    )
    SELECT label, coalesce(to_char(round(value), 'FM999,999,999,999'), 'null')
    FROM metrics
    ORDER BY ord;
  "

  printf '\n### Underpass Elevation Histogram\n\n'
  printf 'Rows with null underpass_z are omitted from this histogram.\n\n'
  printf '| underpass_z | rows | success | other |\n'
  printf '|---|---:|---:|---:|\n'
  append_query_table "
    WITH bucketed AS (
      SELECT
        CASE
          WHEN underpass_z < 1 THEN 1
          WHEN underpass_z < 1.5 THEN 2
          WHEN underpass_z < 2 THEN 3
          WHEN underpass_z < 2.5 THEN 4
          WHEN underpass_z = 2.5 THEN 5
          WHEN underpass_z < 3 THEN 6
          WHEN underpass_z < 3.5 THEN 7
          WHEN underpass_z = 3.5 THEN 8
          WHEN underpass_z < 4 THEN 9
          WHEN underpass_z < 5 THEN 10
          WHEN underpass_z < 10 THEN 11
          ELSE 12
        END AS ord,
        CASE
          WHEN underpass_z < 1 THEN '<1'
          WHEN underpass_z < 1.5 THEN '1-1.5'
          WHEN underpass_z < 2 THEN '1.5-2'
          WHEN underpass_z < 2.5 THEN '2-2.5'
          WHEN underpass_z = 2.5 THEN '=2.5'
          WHEN underpass_z < 3 THEN '2.5-3'
          WHEN underpass_z < 3.5 THEN '3-3.5'
          WHEN underpass_z = 3.5 THEN '=3.5'
          WHEN underpass_z < 4 THEN '3.5-4'
          WHEN underpass_z < 5 THEN '4-5'
          WHEN underpass_z < 10 THEN '5-10'
          ELSE '>=10'
        END AS bucket,
        underpass_source = 'streetlidar' AND underpass_status = 'success' AS success
      FROM ${TABLE_REF}
      WHERE underpass_z IS NOT NULL
    )
    SELECT
      bucket,
      to_char(count(*), 'FM999,999,999,999'),
      to_char(count(*) FILTER (WHERE success), 'FM999,999,999,999'),
      to_char(count(*) FILTER (WHERE success IS NOT TRUE), 'FM999,999,999,999')
    FROM bucketed
    GROUP BY ord, bucket
    ORDER BY ord;
  "

  printf '\n### Success-only underpass_z quantiles\n\n'
  printf '| Quantile | Value |\n'
  printf '|---|---:|\n'
  append_query_table "
    WITH success AS (
      SELECT underpass_z::numeric AS value
      FROM ${TABLE_REF}
      WHERE underpass_source = 'streetlidar'
        AND underpass_status = 'success'
        AND underpass_z IS NOT NULL
    ),
    metrics(label, value, ord) AS (
      SELECT 'min', min(value), 1 FROM success
      UNION ALL SELECT 'p01', percentile_cont(0.01) WITHIN GROUP (ORDER BY value), 2 FROM success
      UNION ALL SELECT 'p05', percentile_cont(0.05) WITHIN GROUP (ORDER BY value), 3 FROM success
      UNION ALL SELECT 'p10', percentile_cont(0.10) WITHIN GROUP (ORDER BY value), 4 FROM success
      UNION ALL SELECT 'p25', percentile_cont(0.25) WITHIN GROUP (ORDER BY value), 5 FROM success
      UNION ALL SELECT 'median', percentile_cont(0.50) WITHIN GROUP (ORDER BY value), 6 FROM success
      UNION ALL SELECT 'p75', percentile_cont(0.75) WITHIN GROUP (ORDER BY value), 7 FROM success
      UNION ALL SELECT 'p90', percentile_cont(0.90) WITHIN GROUP (ORDER BY value), 8 FROM success
      UNION ALL SELECT 'p95', percentile_cont(0.95) WITHIN GROUP (ORDER BY value), 9 FROM success
      UNION ALL SELECT 'p99', percentile_cont(0.99) WITHIN GROUP (ORDER BY value), 10 FROM success
      UNION ALL SELECT 'max', max(value), 11 FROM success
      UNION ALL SELECT 'avg', avg(value), 12 FROM success
    )
    SELECT label, coalesce(trim(to_char(round(value::numeric, 3), 'FM999,999,999,990.999')), 'null')
    FROM metrics
    ORDER BY ord;
  "
} > "$tmp_file"

cat "$tmp_file" >> "$REPORT_FILE"
echo "Appended Run ${RUN_NUMBER} Coverage - ${RUN_DATE} to ${REPORT_FILE}"
