-- Databricks notebook source
-- MAGIC %md
-- MAGIC ## Feb vs March Noida Snapshot: Entity Comparison
-- MAGIC Tables: `furlenco_analytics.user_defined_tables.feb_snapshot_noida` and `march_snapshot_noida`

-- COMMAND ----------

-- CELL 1: Summary Counts
WITH feb AS (SELECT DISTINCT entity_id FROM furlenco_analytics.user_defined_tables.feb_snapshot_noida),
     mar AS (SELECT DISTINCT entity_id FROM furlenco_analytics.user_defined_tables.march_snapshot_noida)
SELECT
  COUNT(DISTINCT feb.entity_id)                                                                             AS feb_total,
  COUNT(DISTINCT mar.entity_id)                                                                             AS mar_total,
  COUNT(DISTINCT CASE WHEN feb.entity_id IS NOT NULL AND mar.entity_id IS NOT NULL THEN feb.entity_id END)  AS common_both,
  COUNT(DISTINCT CASE WHEN mar.entity_id IS NULL THEN feb.entity_id END)                                    AS feb_only,
  COUNT(DISTINCT CASE WHEN feb.entity_id IS NULL THEN mar.entity_id END)                                    AS mar_only
FROM feb
FULL OUTER JOIN mar ON feb.entity_id = mar.entity_id

-- COMMAND ----------

-- CELL 2: Feb-Only Entities (picked up / churned before March)
SELECT f.*
FROM furlenco_analytics.user_defined_tables.feb_snapshot_noida f
WHERE NOT EXISTS (
  SELECT 1
  FROM furlenco_analytics.user_defined_tables.march_snapshot_noida m
  WHERE m.entity_id = f.entity_id
)
ORDER BY f.entity_id

-- COMMAND ----------

-- CELL 3: March-Only Entities (new activations in March)
SELECT m.*
FROM furlenco_analytics.user_defined_tables.march_snapshot_noida m
WHERE NOT EXISTS (
  SELECT 1
  FROM furlenco_analytics.user_defined_tables.feb_snapshot_noida f
  WHERE f.entity_id = m.entity_id
)
ORDER BY m.entity_id

-- COMMAND ----------

-- CELL 4: Common Entities — Feb and March values side by side
SELECT
  f.entity_id,
  f.cycle_num           AS feb_cycle_num,        m.cycle_num           AS mar_cycle_num,
  f.period_start        AS feb_period_start,     m.period_start        AS mar_period_start,
  f.period_end          AS feb_period_end,        m.period_end          AS mar_period_end,
  f.activation_date     AS feb_activation_date,  m.activation_date     AS mar_activation_date,
  f.pickup_date         AS feb_pickup_date,       m.pickup_date         AS mar_pickup_date,
  f.months              AS feb_months,            m.months              AS mar_months,
  f.cycle_amount        AS feb_cycle_amount,      m.cycle_amount        AS mar_cycle_amount,
  f.period_type         AS feb_period_type,       m.period_type         AS mar_period_type,
  f.state_transition_id AS feb_st_id,             m.state_transition_id AS mar_st_id,
  f.event_id            AS feb_event_id,          m.event_id            AS mar_event_id,
  f.days                AS feb_days,              m.days                AS mar_days,
  f.realised_revenue    AS feb_realised_revenue,  m.realised_revenue    AS mar_realised_revenue
FROM furlenco_analytics.user_defined_tables.feb_snapshot_noida f
INNER JOIN furlenco_analytics.user_defined_tables.march_snapshot_noida m
  ON f.entity_id = m.entity_id
ORDER BY f.entity_id
