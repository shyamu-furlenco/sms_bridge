%sql
-- ============================================================
-- RCA SUMMARY: Feb vs March Snapshot Comparison (Noida)
-- Feb  filter: period_end >= '2026-02-01' AND activation_date < '2026-03-01'
-- March filter: period_end >= '2026-03-01' AND activation_date < '2026-04-01'
-- ============================================================

-- This is part of new_state_transition_tenure notebook in databricks.

WITH
feb_agg AS (
  SELECT
    entity_id,
    MAX(activation_date)    AS activation_date,
    COUNT(*)                AS feb_cycles,
    SUM(cycle_amount)       AS feb_amount,
    MAX(period_end)         AS feb_max_end
  FROM furlenco_analytics.user_defined_tables.feb_snapshot_noida
  GROUP BY entity_id
),

march_agg AS (
  SELECT
    entity_id,
    MAX(activation_date)    AS activation_date,
    COUNT(*)                AS mar_cycles,
    SUM(cycle_amount)       AS mar_amount,
    MAX(period_end)         AS mar_max_end
  FROM furlenco_analytics.user_defined_tables.march_snapshot_noida
  GROUP BY entity_id
),

combined AS (
  SELECT
    COALESCE(f.entity_id, m.entity_id) AS entity_id,
    CASE
      WHEN f.entity_id IS NOT NULL AND m.entity_id IS NULL  THEN 'FEB_ONLY'
      WHEN f.entity_id IS NULL     AND m.entity_id IS NOT NULL THEN 'MARCH_ONLY'
      ELSE 'BOTH'
    END AS presence,
    COALESCE(f.activation_date, m.activation_date) AS activation_date,
    f.feb_cycles, f.feb_amount, f.feb_max_end,
    m.mar_cycles, m.mar_amount, m.mar_max_end
  FROM feb_agg f
  FULL OUTER JOIN march_agg m ON f.entity_id = m.entity_id
),

classified AS (
  SELECT
    c.*,
    i.state AS item_state,
    COALESCE(i.pickup_date, rto.created_at + INTERVAL '330' MINUTES) AS actual_pickup_dt,
    rto.id AS rto_order_id,
    CASE
      -- ═══ 1. FEB_ONLY: Items in Feb but NOT in March ═══
      WHEN c.presence = 'FEB_ONLY'
           AND i.state = 'PICKED_UP'
           AND COALESCE(i.pickup_date, rto.created_at + INTERVAL '330' MINUTES) < '2026-03-01'
        THEN '1A. Picked Up Before March'
      WHEN c.presence = 'FEB_ONLY'
           AND i.state = 'PICKED_UP'
           AND COALESCE(i.pickup_date, rto.created_at + INTERVAL '330' MINUTES) >= '2026-03-01'
        THEN '1B. Picked Up In/After March'
      WHEN c.presence = 'FEB_ONLY'
           AND rto.id IS NOT NULL
        THEN '1C. RTP Converted'
      WHEN c.presence = 'FEB_ONLY'
           AND c.feb_max_end < '2026-03-01'
        THEN '1D. All Cycles Ended Before March'
      WHEN c.presence = 'FEB_ONLY'
           AND i.state = 'CANCELLED'
        THEN '1E. Cancelled'
      WHEN c.presence = 'FEB_ONLY'
           AND c.feb_max_end >= '2026-03-01'
        THEN '1F. ⚠ Should Be in March (Needs Investigation)'
      WHEN c.presence = 'FEB_ONLY'
        THEN '1G. Other (Feb Only)'

      -- ═══ 2. MARCH_ONLY: Items in March but NOT in Feb ═══
      WHEN c.presence = 'MARCH_ONLY'
           AND c.activation_date >= '2026-03-01'
        THEN '2A. New Activation in March'
      WHEN c.presence = 'MARCH_ONLY'
           AND c.activation_date >= '2026-02-01'
           AND c.activation_date < '2026-03-01'
        THEN '2B. Activated in Feb (Missing from Feb Snapshot)'
      WHEN c.presence = 'MARCH_ONLY'
           AND c.activation_date < '2026-02-01'
        THEN '2C. Old Item Re-appeared in March'
      WHEN c.presence = 'MARCH_ONLY'
        THEN '2D. Other (March Only)'

      -- ═══ 3. BOTH: Items present in both months ═══
      WHEN c.presence = 'BOTH'
           AND c.feb_cycles = c.mar_cycles
           AND ROUND(COALESCE(c.feb_amount,0),2) = ROUND(COALESCE(c.mar_amount,0),2)
        THEN '3A. No Material Change'
      WHEN c.presence = 'BOTH'
           AND c.mar_cycles > c.feb_cycles
        THEN '3D. More Cycles in March (Renewed/Extended)'
      WHEN c.presence = 'BOTH'
           AND c.mar_cycles < c.feb_cycles
        THEN '3E. Fewer Cycles in March'
      WHEN c.presence = 'BOTH'
           AND ROUND(COALESCE(c.mar_amount,0),2) <> ROUND(COALESCE(c.feb_amount,0),2)
        THEN '3F. Amount Changed (Same Cycle Count)'
      WHEN c.presence = 'BOTH'
        THEN '3G. Other Change'
      ELSE '9. Unclassified'
    END AS rca_reason
  FROM combined c
  LEFT JOIN furlenco_silver.order_management_systems_evolve.items i
    ON c.entity_id = i.id
  LEFT JOIN furlenco_silver.order_management_systems_evolve.rent_to_purchase_items rtpi
    ON c.entity_id = rtpi.item_id
  LEFT JOIN furlenco_silver.order_management_systems_evolve.rent_to_purchase_orders rto
    ON rtpi.rent_to_purchase_order_id = rto.id AND rto.state <> 'CANCELLED'
)

SELECT
  presence,
  rca_reason,
  COUNT(*)                                                          AS item_count,
  ROUND(SUM(COALESCE(feb_amount, 0)), 2)                           AS feb_total_amount,
  ROUND(SUM(COALESCE(mar_amount, 0)), 2)                           AS mar_total_amount,
  ROUND(SUM(COALESCE(mar_amount,0)) - SUM(COALESCE(feb_amount,0)), 2) AS delta_amount,
  SUM(feb_cycles)                                                  AS feb_total_cycles,
  SUM(mar_cycles)                                                  AS mar_total_cycles
FROM classified
GROUP BY presence, rca_reason
ORDER BY rca_reason
