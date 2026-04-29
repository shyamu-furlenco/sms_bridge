
-- create materialized view analytics.

WITH all_snapshots AS (
  SELECT
    st.id                                                                                                         AS state_transition_id,
	st.entity_id,
    st.event_id,
    CAST(json_extract_path_text(st."snapshot", 'tenureStartDate',true) AS DATE)                                          AS tsd,
    CAST(json_extract_path_text(st."snapshot", 'tenureEndDate',true) AS DATE)                                            AS ted,
    json_extract_path_text(st."snapshot", 'tenureInMonths',true)::INT                                                    AS months,
    CAST(json_extract_path_text(st."snapshot", 'renewalOverdueCycleStartDate',true) AS DATE)                             AS ro_start,
    CAST(json_extract_path_text(st."snapshot", 'renewalOverdueCycleEndDate',true) AS DATE)                               AS ro_end,
	CAST(json_extract_path_text(st."snapshot",'activationDate',true) AS DATE) as activation_date,
    json_extract_path_text(st."snapshot", 'paymentDetails', 'payableAfterPaymentOffers', 'byCashPreTax',true)::FLOAT     AS pre_tax_amount,
    json_extract_path_text(st."snapshot", 'paymentDetails', 'payableAfterPaymentOffers', 'byCashPostTax',true)::FLOAT    AS amount_paid,
    json_extract_path_text(st."snapshot", 'currentPricingDetails', 'basePrice',true)::FLOAT                             AS base_price
  FROM order_management_systems_evolve.state_transitions st
  LEFT JOIN panem_evolve.delivery_addresses pnm
    ON CAST(json_extract_path_text(st."snapshot", 'deliveryAddressId',true) AS INT) = pnm.id
  WHERE st.entity_type = 'ITEM'
    AND pnm.city_id    = 6
    AND json_extract_path_text(st."snapshot", 'vertical',true) = 'FURLENCO_RENTAL'
    AND json_extract_path_text(st."snapshot", 'tenureStartDate',true) IS NOT NULL
),

tenure_cycles AS (
  SELECT
    tsd              AS period_start,
    ted              AS period_end,
	entity_id,
	activation_date,
    months,
    pre_tax_amount,
    amount_paid,
    base_price,
    'TENURE'         AS period_type,
    state_transition_id,
    event_id
  FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY entity_id, tsd, ted ORDER BY state_transition_id ASC) AS rn
    FROM all_snapshots
    WHERE tsd IS NOT NULL
  ) t
  WHERE rn = 1
),

all_ro AS (
  SELECT
    ro_start,
    ro_end,
	entity_id,
	activation_date,
    base_price,
    state_transition_id,
    event_id
  FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY entity_id, ro_start, ro_end ORDER BY state_transition_id ASC) AS rn
    FROM all_snapshots
    WHERE ro_start IS NOT NULL
  ) t
  WHERE rn = 1
),

-- Overdue months where the customer didn't renew in the first overdue month;
-- the next tenure starts AFTER this period, so it's a standalone billing period.
-- (When ro_start = next tsd, the overdue is "absorbed" into that tenure row.)
pure_overdue AS (
  SELECT
    aro.ro_start         AS period_start,
    aro.ro_end           AS period_end,
	aro.entity_id,
	aro.activation_date,
    NULL::INT            AS months,
    NULL::FLOAT          AS pre_tax_amount,
    NULL::FLOAT          AS amount_paid,
    aro.base_price,
    'PURE_OVERDUE'       AS period_type,
    aro.state_transition_id,
    aro.event_id
  FROM all_ro aro
  LEFT JOIN tenure_cycles tc
    ON aro.entity_id  = tc.entity_id
   AND aro.ro_start   = tc.period_start
  WHERE tc.period_start IS NULL
)

SELECT
  ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY period_start) AS cycle_num,
  period_start,
  period_end,
  entity_id,
  activation_date,
  months,
  CASE
    WHEN period_type = 'PURE_OVERDUE' THEN base_price
    ELSE pre_tax_amount
  END AS cycle_amount,
  period_type,
  state_transition_id,
  event_id,
  DATEDIFF(day, period_start, period_end) + 1 AS days
FROM (
  SELECT * FROM tenure_cycles
  UNION ALL
  SELECT * FROM pure_overdue
) combined
WHERE 1=1
AND period_end >= '2026-02-01'
AND activation_date < '2026-03-01'
