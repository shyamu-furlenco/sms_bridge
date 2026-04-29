%sql

create table furlenco_analytics.user_defined_tables.feb_snapshot_noida as 

WITH all_snapshots AS (
  SELECT
    st.id                                                                          AS state_transition_id,
    st.entity_id,
    st.event_id,
    ev.name                                                                        AS event_name,
    CAST(st.snapshot:tenureStartDate              AS DATE)                         AS tsd,
    CAST(st.snapshot:tenureEndDate                AS DATE)                         AS ted,
    st.snapshot:tenureInMonths::INT                                                AS months,
    CAST(st.snapshot:renewalOverdueCycleStartDate AS DATE)                         AS ro_start,
    CAST(st.snapshot:renewalOverdueCycleEndDate   AS DATE)                         AS ro_end,
    CAST(st.snapshot:activationDate AS DATE) as activation_date,
    CAST(st.snapshot:pickupDate AS DATE) as pickup_date,
    st.snapshot:paymentDetails.payableAfterPaymentOffers.byCashPreTax::DOUBLE      AS pre_tax_amount,
    st.snapshot:paymentDetails.payableAfterPaymentOffers.byCashPostTax::DOUBLE     AS amount_paid,
    st.snapshot:currentPricingDetails:basePrice::DOUBLE                            AS base_price
  FROM furlenco_silver.order_management_systems_evolve.state_transitions st
  INNER JOIN furlenco_silver.order_management_systems_evolve.events ev
    ON st.event_id = ev.id
  LEFT JOIN furlenco_silver.panem_evolve.delivery_addresses pnm
    ON CAST(st.snapshot:deliveryAddressId AS INT) = CAST(pnm.id AS INT)
  WHERE st.entity_type = 'ITEM'
    -- AND st.entity_id = 1106173
    AND pnm.city_id    = 6
    AND st.snapshot:vertical::STRING   = 'FURLENCO_RENTAL'
    AND st.snapshot:tenureStartDate    IS NOT NULL
),

tenure_cycles AS (
  SELECT
    tsd              AS period_start,
    ted              AS period_end,
    activation_date,
    pickup_date,
    entity_id,
    months,
    pre_tax_amount,
    amount_paid,
    base_price,
    'TENURE'         AS period_type,
    state_transition_id,
    event_id,
    event_name
  FROM all_snapshots
  WHERE tsd IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (PARTITION BY entity_id, tsd, ted ORDER BY state_transition_id ASC) = 1
),

all_ro AS (
  SELECT
    ro_start,
    ro_end,
    activation_date,
    pickup_date,
    entity_id,
    base_price,
    state_transition_id,
    event_id,
    event_name
  FROM all_snapshots
  WHERE ro_start IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (PARTITION BY entity_id, ro_start, ro_end ORDER BY state_transition_id ASC) = 1
),

-- Overdue months where the customer didn't renew in the first overdue month;
-- the next tenure starts AFTER this period, so it's a standalone billing period.
-- (When ro_start = next tsd, the overdue is "absorbed" into that tenure row.)
pure_overdue AS (
  SELECT
    aro.ro_start         AS period_start,
    aro.ro_end           AS period_end,
    aro.activation_date,
    aro.pickup_date,
    aro.entity_id,
    NULL                 AS months,
    NULL::DOUBLE         AS pre_tax_amount,
    NULL::DOUBLE         AS amount_paid,
    aro.base_price,
    'PURE_OVERDUE'       AS period_type,
    aro.state_transition_id,
    aro.event_id,
    aro.event_name
  FROM all_ro aro
  LEFT JOIN tenure_cycles tc
    ON aro.entity_id = tc.entity_id
   AND aro.ro_start  = tc.period_start
  WHERE tc.period_start IS NULL
)
, final_output as (
SELECT
  ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY period_start) AS cycle_num,
  period_start,
  period_end,
  activation_date,
  pickup_date,
  entity_id,
  months,
  CASE
    WHEN period_type = 'PURE_OVERDUE' THEN base_price
    ELSE pre_tax_amount
  END AS cycle_amount,
  period_type,
  state_transition_id,
  event_id,
  event_name,
  DATEDIFF(DAY, period_start, period_end) + 1 AS days
FROM (
  SELECT * FROM tenure_cycles
  UNION ALL
  SELECT * FROM pure_overdue
)
)
SELECT * 
FROM final_output
WHERE 1=1
AND period_end >= '2026-02-01'
AND activation_date < '2026-03-01'

